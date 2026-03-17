---
name: migrate-to-litestream
description: Migrate a DjangoPress site from PostgreSQL on Railway to SQLite + Litestream + GCS. Use this skill when the user wants to switch a deployed site from Postgres to SQLite, set up Litestream replication, or move to file-based database sync. Also triggers for requests about database backup to GCS, removing Postgres from Railway, or setting up Litestream for a DjangoPress project.
argument-hint: [project-name]
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, AskUserQuestion
---

# Migrate DjangoPress Site to Litestream + GCS

Migrate a deployed DjangoPress site from PostgreSQL on Railway to SQLite with Litestream replication to Google Cloud Storage. After migration, the site uses SQLite in both development and production, with Litestream continuously backing up to GCS.

The argument provided is: `$ARGUMENTS`

## What This Migration Does

- Replaces PostgreSQL with SQLite in production
- Adds Litestream for continuous backup/replication to GCS
- Creates a Dockerfile (replacing the Procfile-based buildpack deploy)
- Adds sync scripts for explicit dev↔prod database synchronization
- Uses separate GCS paths for dev and prod (`/dev/` and `/prod/`)

## Prerequisites

- The site must already be deployed on Railway
- GCS must be configured in `.env` (`GS_BUCKET_NAME`, `GCS_CREDENTIALS_JSON`)
- Litestream v0.3.13 must be installed locally (`~/bin/litestream` or `/usr/local/bin/litestream`)
- `gcloud` CLI must be available for `gcloud storage` commands

---

## Phase 1: Pre-flight Check

### Verify project directory

```bash
pwd
basename "$(pwd)"
git remote -v
```

If `$ARGUMENTS` is provided and doesn't match the current directory, look for the target project in `../` and `cd` to it.

If the current directory is the `djangopress` template repo (remote shows `axpmarante/djangopress`), STOP — this skill is for child projects only.

### Check Railway status

```bash
railway status
```

Must be linked to a Railway project. If not, tell the user to deploy first with `/deploy-site-railway`.

### Check GCS configuration

```bash
grep GS_BUCKET_NAME .env
grep GCS_CREDENTIALS_JSON .env
```

Both must be set. If not, the user needs to configure GCS first — this skill depends on it for Litestream replication.

### Check Litestream is installed

```bash
~/bin/litestream version 2>/dev/null || litestream version 2>/dev/null
```

Expected: `v0.3.13`. If not installed:

```bash
curl -L https://github.com/benbjohnson/litestream/releases/download/v0.3.13/litestream-v0.3.13-darwin-arm64.zip -o /tmp/litestream.zip
unzip -o /tmp/litestream.zip -d /tmp/
mkdir -p ~/bin && mv /tmp/litestream ~/bin/litestream && chmod +x ~/bin/litestream
rm /tmp/litestream.zip
```

### Compare local and production data

Check if local SQLite is the source of truth or if a `pull_data` is needed first:

```bash
# Local page count
python manage.py shell -c "
from djangopress.core.models import Page
print(f'Local pages: {Page.objects.filter(is_active=True).count()}')
"
```

Then check production (get the public DATABASE_URL):

```bash
railway variables -s Postgres --kv 2>&1 | grep DATABASE_PUBLIC_URL
```

```bash
ENVIRONMENT=production DATABASE_URL="<DATABASE_PUBLIC_URL>" python manage.py shell -c "
from djangopress.core.models import Page
print(f'Prod pages: {Page.objects.filter(is_active=True).count()}')
"
```

If production has more data than local, run `pull_data` first:

```bash
echo "yes" | python manage.py pull_data https://<site-url>
```

If local has equal or more data, proceed — local is the source of truth.

### Derive the site slug

Used for GCS paths. Derive from the directory name:

```bash
SITE_SLUG=$(basename "$(pwd)")
```

This gives paths like `gs://bucket/<site-slug>/db/dev/` and `gs://bucket/<site-slug>/db/prod/`.

---

## Phase 2: Add Litestream Infrastructure

### Step 1: Update `config/settings.py`

Replace the DATABASES block (find the line with `env.db('DATABASE_URL'` or similar):

```python
# Database — SQLite in all environments
# In production, Litestream handles backup/replication to GCS
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'OPTIONS': {
            'timeout': 20,
            'transaction_mode': 'IMMEDIATE',
        },
    }
}
```

### Step 2: Update `requirements.txt`

Ensure `gunicorn>=22.0` is present. If `djangopress` points to a specific tag, update to `@main`:

```
djangopress @ git+https://github.com/axpmarante/djangopress.git@main
gunicorn>=22.0
```

### Step 3: Update `.gitignore`

Add before the Claude AI section:

```
# Litestream
*.sqlite3-wal
*.sqlite3-shm
```

### Step 4: Create `litestream.yml`

```yaml
# Local development config — points to /dev/ path in GCS.
# In production, entrypoint.sh generates a separate config with /prod/ path.
dbs:
  - path: ./db.sqlite3
    replicas:
      - type: gcs
        bucket: <GS_BUCKET_NAME from .env>
        path: <SITE_SLUG>/db/dev/
        sync-interval: 1s
```

Read `GS_BUCKET_NAME` from `.env` to fill in the bucket name.

### Step 5: Create `.dockerignore`

```
venv/
.venv/
.git/
.gitignore
db.sqlite3
db.sqlite3-wal
db.sqlite3-shm
db.sqlite3.bak*
media/
staticfiles/
.env
.env.*
.DS_Store
__pycache__/
*.pyc
.idea/
.vscode/
.claude/
briefings/
docs/
*.log
.server.log*
.playwright-cli/
```

### Step 6: Create `Dockerfile`

```dockerfile
# --- Build stage: download Litestream ---
FROM alpine:3.19 AS litestream
ARG LITESTREAM_VERSION=v0.3.13
RUN wget -q "https://github.com/benbjohnson/litestream/releases/download/${LITESTREAM_VERSION}/litestream-${LITESTREAM_VERSION}-linux-amd64.tar.gz" \
    -O /tmp/litestream.tar.gz \
    && tar -xzf /tmp/litestream.tar.gz -C /usr/local/bin/ \
    && rm /tmp/litestream.tar.gz

# --- App stage ---
FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends git sqlite3 && rm -rf /var/lib/apt/lists/*

COPY --from=litestream /usr/local/bin/litestream /usr/local/bin/litestream

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN SECRET_KEY=build-only-dummy-key ENVIRONMENT=production python manage.py collectstatic --noinput

RUN chmod +x scripts/entrypoint.sh

CMD ["scripts/entrypoint.sh"]
```

### Step 7: Create `scripts/entrypoint.sh`

```bash
#!/bin/bash
set -e

DB_PATH="/app/db.sqlite3"
LITESTREAM_CONFIG="/app/litestream.yml"
GCS_CREDS_FILE="/tmp/gcs-credentials.json"

if [ -n "$GCS_CREDENTIALS_JSON" ]; then
    echo "$GCS_CREDENTIALS_JSON" > "$GCS_CREDS_FILE"
    export GOOGLE_APPLICATION_CREDENTIALS="$GCS_CREDS_FILE"
    echo "[entrypoint] GCS credentials written to $GCS_CREDS_FILE"
else
    echo "[entrypoint] WARNING: GCS_CREDENTIALS_JSON not set"
fi

BUCKET="${GCS_BUCKET_NAME:-corporate-django-sites-media}"
REPLICA_PATH="${LITESTREAM_REPLICA_PATH:-<SITE_SLUG>/db/prod/}"

cat > "$LITESTREAM_CONFIG" <<YAML
dbs:
  - path: ${DB_PATH}
    replicas:
      - type: gcs
        bucket: ${BUCKET}
        path: ${REPLICA_PATH}
        sync-interval: 1s
YAML
echo "[entrypoint] Litestream config written (bucket=$BUCKET path=$REPLICA_PATH)"

echo "[entrypoint] Attempting database restore from GCS..."
if [ ! -f "$DB_PATH" ]; then
    if litestream restore -o "$DB_PATH" "gcs://${BUCKET}/${REPLICA_PATH}" 2>/dev/null; then
        echo "[entrypoint] Database restored from GCS"
    else
        echo "[entrypoint] No existing replica found — starting fresh"
    fi
else
    echo "[entrypoint] Database already exists — skipping restore"
fi

sqlite3 "$DB_PATH" "PRAGMA journal_mode=WAL;" 2>/dev/null || true

echo "[entrypoint] Running migrations..."
python manage.py migrate --noinput

echo "[entrypoint] Starting Litestream replication + gunicorn..."
exec litestream replicate -config "$LITESTREAM_CONFIG" -exec "gunicorn config.wsgi:application -c gunicorn.conf.py --bind 0.0.0.0:${PORT:-8000}"
```

Replace `<SITE_SLUG>` with the actual site slug in the `REPLICA_PATH` default.

### Step 8: Create `scripts/sync-to-prod.sh`

```bash
#!/bin/bash
set -e

BUCKET="gs://<GS_BUCKET_NAME>"
DEV_PATH="<SITE_SLUG>/db/dev"
PROD_PATH="<SITE_SLUG>/db/prod"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

echo "=== Sync Dev → Prod ==="
echo ""

if [ -z "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
    echo "ERROR: GOOGLE_APPLICATION_CREDENTIALS not set"
    echo "Run: export GOOGLE_APPLICATION_CREDENTIALS=/tmp/gcs-credentials.json"
    exit 1
fi

echo "1. Stopping local Litestream (flushing pending WAL frames)..."
pkill -f "litestream replicate" 2>/dev/null && echo "   Stopped." || echo "   Not running."
sleep 2

echo "2. Checking dev replica..."
if ! gcloud storage ls "$BUCKET/$DEV_PATH/" > /dev/null 2>&1; then
    echo "ERROR: No dev replica found at $BUCKET/$DEV_PATH/"
    exit 1
fi

echo "3. Backing up current prod to $PROD_PATH-backup-$TIMESTAMP/..."
if gcloud storage ls "$BUCKET/$PROD_PATH/" > /dev/null 2>&1; then
    gcloud storage cp -r "$BUCKET/$PROD_PATH" "$BUCKET/$PROD_PATH-backup-$TIMESTAMP"
    echo "   Backup saved."
else
    echo "   No existing prod replica — skipping backup."
fi

echo "4. Copying dev replica to prod..."
gcloud storage rsync -r --delete-unmatched-destination-objects "$BUCKET/$DEV_PATH/" "$BUCKET/$PROD_PATH/"
echo "   Done."

echo ""
echo "=== Sync complete ==="
echo ""
echo "Next steps:"
echo "  1. Restart local Litestream:"
echo "     GOOGLE_APPLICATION_CREDENTIALS=/tmp/gcs-credentials.json litestream replicate -config litestream.yml"
echo "  2. Deploy to Railway: railway up -d"
echo "  3. Verify the site works"
```

Replace `<GS_BUCKET_NAME>` and `<SITE_SLUG>` with actual values.

### Step 9: Create `scripts/pull-from-prod.sh`

```bash
#!/bin/bash
set -e

DB_PATH="db.sqlite3"
BUCKET="gs://<GS_BUCKET_NAME>"
PROD_PATH="<SITE_SLUG>/db/prod"

echo "=== Pull Prod → Dev ==="
echo ""

if [ -z "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
    echo "ERROR: GOOGLE_APPLICATION_CREDENTIALS not set"
    exit 1
fi

echo "1. Checking prod replica..."
if ! gcloud storage ls "$BUCKET/$PROD_PATH/" > /dev/null 2>&1; then
    echo "ERROR: No prod replica found at $BUCKET/$PROD_PATH/"
    exit 1
fi

echo "2. Stopping local Litestream..."
pkill -f "litestream replicate" 2>/dev/null && echo "   Stopped." || echo "   Not running."
sleep 2

echo "3. Backing up local database..."
if [ -f "$DB_PATH" ]; then
    cp "$DB_PATH" "${DB_PATH}.bak"
    echo "   Saved to ${DB_PATH}.bak"
fi

rm -f "$DB_PATH" "${DB_PATH}-wal" "${DB_PATH}-shm"

echo "4. Restoring from prod replica..."
litestream restore -o "$DB_PATH" "gcs://<GS_BUCKET_NAME>/$PROD_PATH"

echo "5. Setting WAL mode..."
sqlite3 "$DB_PATH" "PRAGMA journal_mode=WAL;"

echo ""
echo "=== Pull complete ==="
echo "Local database now matches production."
echo ""
echo "Restart Litestream to resume dev replication:"
echo "  GOOGLE_APPLICATION_CREDENTIALS=/tmp/gcs-credentials.json litestream replicate -config litestream.yml"
```

Replace `<GS_BUCKET_NAME>` and `<SITE_SLUG>` with actual values.

### Step 10: Delete `Procfile`

```bash
rm -f Procfile
```

The Dockerfile CMD replaces the Procfile. If `gunicorn.conf.py` doesn't exist, create it:

```python
workers = 2
timeout = 120
```

### Step 11: Make scripts executable and commit

```bash
chmod +x scripts/entrypoint.sh scripts/sync-to-prod.sh scripts/pull-from-prod.sh
git add -A
git commit -m "migrate to SQLite + Litestream (replace Postgres)"
```

---

## Phase 3: Replicate Local SQLite to GCS

### Step 1: Extract GCS credentials

```bash
python -c "
from pathlib import Path
import environ
env = environ.Env()
env.read_env('.env')
creds = env('GCS_CREDENTIALS_JSON')
if creds.startswith(\"'\") and creds.endswith(\"'\"):
    creds = creds[1:-1]
Path('/tmp/gcs-credentials.json').write_text(creds)
print('Credentials written to /tmp/gcs-credentials.json')
"
```

### Step 2: Enable WAL mode and replicate

```bash
sqlite3 db.sqlite3 'PRAGMA journal_mode=WAL;'
```

Start replication, wait for snapshot upload (~5-10 seconds), then stop:

```bash
GOOGLE_APPLICATION_CREDENTIALS=/tmp/gcs-credentials.json ~/bin/litestream replicate -config litestream.yml &
sleep 10
pkill -f "litestream replicate"
sleep 2
```

Verify files appeared in GCS:

```bash
gcloud storage ls gs://<GS_BUCKET_NAME>/<SITE_SLUG>/db/dev/
```

### Step 3: Copy dev to prod in GCS

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/tmp/gcs-credentials.json
bash scripts/sync-to-prod.sh
```

---

## Phase 4: Update Railway and Deploy

### Step 1: Set new environment variables

```bash
railway variables --set "LITESTREAM_REPLICA_PATH=<SITE_SLUG>/db/prod/" --skip-deploys
```

### Step 2: Override DATABASE_URL

The Railway CLI doesn't support unsetting variables. Override it so it's harmless:

```bash
railway variables --set "DATABASE_URL=sqlite:///app/db.sqlite3" --skip-deploys
```

The settings.py no longer reads DATABASE_URL, so this value is ignored — it just prevents the old Postgres reference from being active.

### Step 3: Deploy

```bash
railway up -d
```

### Step 4: Monitor and verify

```bash
sleep 70
railway logs --lines 20
```

Expected:
```
[entrypoint] Database restored from GCS
[entrypoint] Running migrations...
[entrypoint] Starting Litestream replication + gunicorn...
```

Verify the site loads:

```bash
# Get the site domain from Railway or .env
curl -s -o /dev/null -w "%{http_code}" https://<SITE_DOMAIN>/
```

Expected: 200 or 302.

---

## Phase 5: Clean Up Postgres

Only proceed after confirming the site works on SQLite.

```
AskUserQuestion:
Question: "The site is now running on SQLite + Litestream. Do you want to remove the Postgres service from Railway? This saves ~$5-7/month but cannot be undone."
Options:
- "Yes, remove Postgres" — Delete the Postgres service
- "Keep it for now" — Leave Postgres running as a fallback
```

If the user says yes, they need to remove it from the Railway dashboard (Settings → Delete Service on the Postgres service). The CLI doesn't support deleting services.

---

## Phase 6: Summary

```
Migration complete!

Site: <SITE_NAME>
Database: SQLite + Litestream → GCS
GCS Bucket: <GS_BUCKET_NAME>
Dev replica: gs://<GS_BUCKET_NAME>/<SITE_SLUG>/db/dev/
Prod replica: gs://<GS_BUCKET_NAME>/<SITE_SLUG>/db/prod/

Sync commands:
  Push dev → prod:  bash scripts/sync-to-prod.sh && railway up -d
  Pull prod → dev:  bash scripts/pull-from-prod.sh

Before running sync scripts, set:
  export GOOGLE_APPLICATION_CREDENTIALS=/tmp/gcs-credentials.json

What changed:
  ✓ config/settings.py — SQLite with WAL mode + IMMEDIATE transactions
  ✓ Dockerfile — replaces Procfile, includes Litestream v0.3.13
  ✓ scripts/entrypoint.sh — GCS restore + migrate + Litestream + gunicorn
  ✓ scripts/sync-to-prod.sh — dev→prod sync with backup
  ✓ scripts/pull-from-prod.sh — prod→dev restore
  ✗ Procfile — deleted (replaced by Dockerfile CMD)
  ✗ Postgres — can be removed from Railway dashboard
```

---

## Rollback Plan

If the migration needs to be reversed:

1. Restore the `Procfile` from git: `git checkout HEAD~1 -- Procfile`
2. Restore `config/settings.py` DATABASE block to use `env.db('DATABASE_URL', ...)`
3. Re-add Postgres to Railway: `railway add -d postgres`
4. Set `DATABASE_URL`: `railway variables --set 'DATABASE_URL=${{Postgres.DATABASE_URL}}'`
5. Redeploy: `railway up -d`
6. Push data back: `echo "yes" | python manage.py push_data https://<site-url>`

---

## Error Handling

- **Litestream restore fails:** Check GCS credentials are valid and the replica path exists. Run `gcloud storage ls gs://<bucket>/<path>/` to verify.
- **collectstatic fails during Docker build:** The `SECRET_KEY=build-only-dummy-key` env var handles this. If it still fails, check that `djangopress.settings` can be imported without a `.env` file.
- **Site returns 500 after deploy:** Check `railway logs --lines 50` for the error. Common issues: missing env var, migration failure, or GCS credential format problem.
- **`gcloud storage rsync` fails:** Ensure the service account has Storage Object Admin permissions on the bucket.
- **WAL mode not set:** Litestream sets WAL mode automatically, but the entrypoint also runs `PRAGMA journal_mode=WAL` as a safeguard.
