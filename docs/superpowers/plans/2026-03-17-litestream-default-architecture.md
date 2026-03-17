# Litestream Default Architecture — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make SQLite + Litestream + GCS the default architecture for all new DjangoPress sites, removing all Postgres sync infrastructure.

**Architecture:** Update `site_template/` with Litestream files (Dockerfile, entrypoint, sync scripts). Rewrite deploy and sync skills. Remove push_data/pull_data commands and API endpoints. Update all documentation.

**Tech Stack:** Litestream v0.3.13, GCS, Docker, Django 6.0, gunicorn, SQLite WAL mode.

**Spec:** `docs/superpowers/specs/2026-03-17-litestream-default-architecture-design.md`

**Working directory:** `/Users/antoniomarante/Documents/DjangoSites/djangopress`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `site_template/Procfile` | Delete | Replaced by Dockerfile CMD |
| `site_template/Dockerfile` | Create | Railway container with Litestream |
| `site_template/.dockerignore` | Create | Exclude venv, .git, db.sqlite3, media |
| `site_template/litestream.yml` | Create | Local dev Litestream config with `__SITE_SLUG__` |
| `site_template/scripts/entrypoint.sh` | Create | Railway boot: restore, migrate, replicate |
| `site_template/scripts/sync-to-prod.sh` | Create | Dev→prod sync via GCS |
| `site_template/scripts/pull-from-prod.sh` | Create | Prod→dev restore from GCS |
| `site_template/config/settings.py` | Modify | Hardcode SQLite DATABASES |
| `site_template/requirements.txt` | Modify | Add gunicorn>=22.0 |
| `site_template/.env.example` | Modify | Remove DATABASE_URL, add LITESTREAM_REPLICA_PATH |
| `scripts/new_site.sh` | Modify | Replace `__SITE_SLUG__` placeholders |
| `src/djangopress/skills/deploy-site-railway/SKILL.md` | Rewrite | Deploy with Litestream (no Postgres) |
| `src/djangopress/skills/sync-data/SKILL.md` | Rewrite | Sync via Litestream + GCS |
| `src/djangopress/skills/generate-site/SKILL.md` | Modify | Update DATABASE reference |
| `src/djangopress/core/management/commands/push_data.py` | Delete | No longer needed |
| `src/djangopress/core/management/commands/pull_data.py` | Delete | No longer needed |
| `src/djangopress/backoffice/api_views.py` | Modify | Remove sync functions |
| `src/djangopress/backoffice/urls.py` | Modify | Remove sync routes |
| `CLAUDE.md` | Modify | Update commands, skills, setup |

---

## Task 1: Update Site Template — Config and Requirements

**Files:**
- Modify: `site_template/config/settings.py:24-27`
- Modify: `site_template/requirements.txt`
- Modify: `site_template/.env.example`
- Delete: `site_template/Procfile`

- [ ] **Step 1: Update `site_template/config/settings.py`**

Replace lines 24-27:
```python
# --- Database ---
DATABASES = {
    'default': env.db('DATABASE_URL', default=f'sqlite:///{BASE_DIR / "db.sqlite3"}')
}
```

With:
```python
# --- Database — SQLite in all environments ---
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

- [ ] **Step 2: Update `site_template/requirements.txt`**

Current:
```
djangopress @ git+https://github.com/axpmarante/djangopress.git@main
```

Replace with:
```
djangopress @ git+https://github.com/axpmarante/djangopress.git@main
gunicorn>=22.0
```

- [ ] **Step 3: Update `site_template/.env.example`**

Remove the DATABASE section (lines 13-20):
```
# ===== DATABASE =====
# SQLite (default — no config needed):
#   Uses db.sqlite3 in project root automatically
#
# PostgreSQL (for high-traffic sites):
#   DATABASE_URL=postgres://user:password@host:5432/dbname
#
# Railway provides DATABASE_URL automatically when you add a Postgres plugin.
```

Replace with:
```
# ===== DATABASE =====
# SQLite is used in all environments. Litestream replicates to GCS.
# No configuration needed — works out of the box.
# LITESTREAM_REPLICA_PATH=my-site/db/prod/
```

- [ ] **Step 4: Delete `site_template/Procfile`**

```bash
rm site_template/Procfile
```

- [ ] **Step 5: Commit**

```bash
git add site_template/config/settings.py site_template/requirements.txt site_template/.env.example
git rm site_template/Procfile
git commit -m "update site template: SQLite default, remove Procfile"
```

---

## Task 2: Add Litestream Files to Site Template

**Files:**
- Create: `site_template/Dockerfile`
- Create: `site_template/.dockerignore`
- Create: `site_template/litestream.yml`
- Create: `site_template/scripts/entrypoint.sh`
- Create: `site_template/scripts/sync-to-prod.sh`
- Create: `site_template/scripts/pull-from-prod.sh`

- [ ] **Step 1: Create `site_template/Dockerfile`**

```dockerfile
FROM alpine:3.19 AS litestream
ARG LITESTREAM_VERSION=v0.3.13
RUN wget -q "https://github.com/benbjohnson/litestream/releases/download/${LITESTREAM_VERSION}/litestream-${LITESTREAM_VERSION}-linux-amd64.tar.gz" -O /tmp/litestream.tar.gz && tar -xzf /tmp/litestream.tar.gz -C /usr/local/bin/ && rm /tmp/litestream.tar.gz

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

- [ ] **Step 2: Create `site_template/.dockerignore`**

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

- [ ] **Step 3: Create `site_template/litestream.yml`**

```yaml
# Local development config — points to /dev/ path in GCS.
# In production, entrypoint.sh generates a separate config with /prod/ path.
dbs:
  - path: ./db.sqlite3
    replicas:
      - type: gcs
        bucket: corporate-django-sites-media
        path: __SITE_SLUG__/db/dev/
        sync-interval: 1s
```

- [ ] **Step 4: Create `site_template/scripts/entrypoint.sh`**

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
REPLICA_PATH="${LITESTREAM_REPLICA_PATH:-__SITE_SLUG__/db/prod/}"

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

- [ ] **Step 5: Create `site_template/scripts/sync-to-prod.sh`**

```bash
#!/bin/bash
set -e
SITE_SLUG=$(basename "$(pwd)")
BUCKET="gs://corporate-django-sites-media"
DEV_PATH="$SITE_SLUG/db/dev"
PROD_PATH="$SITE_SLUG/db/prod"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

echo "=== Sync Dev → Prod ($SITE_SLUG) ==="
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
    echo "Run Litestream locally first to create the replica."
    exit 1
fi

echo "3. Backing up current prod..."
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
echo "  1. Deploy to Railway: railway up -d"
echo "  2. Verify the site works"
```

- [ ] **Step 6: Create `site_template/scripts/pull-from-prod.sh`**

```bash
#!/bin/bash
set -e
SITE_SLUG=$(basename "$(pwd)")
DB_PATH="db.sqlite3"
BUCKET="gs://corporate-django-sites-media"
PROD_PATH="$SITE_SLUG/db/prod"

echo "=== Pull Prod → Dev ($SITE_SLUG) ==="
echo ""

if [ -z "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
    echo "ERROR: GOOGLE_APPLICATION_CREDENTIALS not set"
    echo "Run: export GOOGLE_APPLICATION_CREDENTIALS=/tmp/gcs-credentials.json"
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
litestream restore -o "$DB_PATH" "gcs://corporate-django-sites-media/$PROD_PATH"

sqlite3 "$DB_PATH" "PRAGMA journal_mode=WAL;"

echo ""
echo "=== Pull complete ==="
echo "Local database now matches production."
echo "To remove backup: rm ${DB_PATH}.bak"
```

- [ ] **Step 7: Make scripts executable and commit**

```bash
chmod +x site_template/scripts/entrypoint.sh site_template/scripts/sync-to-prod.sh site_template/scripts/pull-from-prod.sh
git add site_template/Dockerfile site_template/.dockerignore site_template/litestream.yml site_template/scripts/
git commit -m "add Litestream infrastructure to site template"
```

---

## Task 3: Update `new_site.sh`

**Files:**
- Modify: `scripts/new_site.sh`

- [ ] **Step 1: Add slug replacement after template copy**

After line 71 (`echo "  Template copied"`), add:

```bash
# --- Step 1b: Replace __SITE_SLUG__ placeholders ---
echo "  Replacing site slug placeholders..."
sed -i.bak "s|__SITE_SLUG__|$PROJECT_NAME|g" litestream.yml scripts/entrypoint.sh
rm -f litestream.yml.bak scripts/entrypoint.sh.bak
echo "  Slug set to: $PROJECT_NAME"
```

- [ ] **Step 2: Update the "Next steps" output**

Replace lines 181-205 (the final output) — update to remove Postgres references:

Find the section starting with `echo "Next steps:"` and replace the deployment instructions. Change:
```
  # Or set up manually:
  python manage.py createsuperuser
  python manage.py runserver 8000
  # Visit http://localhost:8000/backoffice/settings/
```

To:
```
  # Or set up manually:
  python manage.py createsuperuser
  python manage.py runserver 8000
  # Visit http://localhost:8000/backoffice/settings/

  # Deploy to Railway:
  claude /deploy-site-railway $PROJECT_NAME
```

- [ ] **Step 3: Commit**

```bash
git add scripts/new_site.sh
git commit -m "update new_site.sh: configure Litestream slug on site creation"
```

---

## Task 4: Remove push_data/pull_data Commands

**Files:**
- Delete: `src/djangopress/core/management/commands/push_data.py`
- Delete: `src/djangopress/core/management/commands/pull_data.py`

- [ ] **Step 1: Delete the command files**

```bash
rm src/djangopress/core/management/commands/push_data.py
rm src/djangopress/core/management/commands/pull_data.py
```

- [ ] **Step 2: Commit**

```bash
git rm src/djangopress/core/management/commands/push_data.py src/djangopress/core/management/commands/pull_data.py
git commit -m "remove push_data/pull_data commands (replaced by Litestream)"
```

---

## Task 5: Remove Sync API Endpoints

**Files:**
- Modify: `src/djangopress/backoffice/api_views.py:1285-1388`
- Modify: `src/djangopress/backoffice/urls.py:115-117`

- [ ] **Step 1: Remove sync functions from `api_views.py`**

Delete these functions (approximately lines 1285-1388):
- `_check_sync_auth(request)`
- `_truncate_sync_tables()`
- `_load_fixture(fixture_data)`
- `data_sync_receive(request)`
- `data_sync_export(request)`

Also remove the `import hmac` and `import os` if they are only used by these functions (check first).

- [ ] **Step 2: Remove sync routes from `urls.py`**

Delete lines 115-117:
```python
    # Data Sync API (no staff_member_required — uses SYNC_SECRET Bearer auth)
    path('api/data-sync/', api_views.data_sync_receive, name='api_data_sync'),
    path('api/data-sync-export/', api_views.data_sync_export, name='api_data_sync_export'),
```

- [ ] **Step 3: Commit**

```bash
git add src/djangopress/backoffice/api_views.py src/djangopress/backoffice/urls.py
git commit -m "remove data sync API endpoints (replaced by Litestream)"
```

---

## Task 6: Rewrite Deploy Skill

**Files:**
- Rewrite: `src/djangopress/skills/deploy-site-railway/SKILL.md`

- [ ] **Step 1: Rewrite the skill**

Replace the entire content of `src/djangopress/skills/deploy-site-railway/SKILL.md` with a new version that:

**Frontmatter:**
```yaml
---
name: deploy-site-railway
description: Deploy a DjangoPress site to Railway with SQLite + Litestream + GCS. Handles first-time deployments and redeployments. No Postgres needed — database is SQLite replicated to Google Cloud Storage via Litestream.
argument-hint: [project-name]
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, AskUserQuestion
---
```

**Phases:**
1. Pre-flight check — verify directory, check `railway status`, check content exists, derive project name (keep same logic as current)
2. Verify deployment files — check Dockerfile, entrypoint.sh, litestream.yml exist (from template). If missing, tell user to recreate from template.
3. Create Railway project — `railway init -n "<name>" -w "PWD"` (same)
4. Create web service — `railway add -s "web"` (NO `railway add -d postgres`)
5. Link service — `railway service link web`
6. Set env vars — use `--skip-deploys`:
   - `SECRET_KEY` (generate new)
   - `ENVIRONMENT=production`
   - `DJANGO_SETTINGS_MODULE=config.settings`
   - `GCS_BUCKET_NAME`, `GS_BUCKET_NAME`, `GS_PROJECT_ID`
   - `LITESTREAM_REPLICA_PATH=<slug>/db/prod/`
   - `GCS_CREDENTIALS_JSON` (special handling with Python subprocess)
   - AI keys (GEMINI, OPENAI, ANTHROPIC) if present in .env
   - Email keys (MAILGUN) if present in .env
   - NO `DATABASE_URL`
7. Replicate local DB to GCS — extract GCS creds, enable WAL, run litestream replicate, sync-to-prod.sh
8. Deploy — `railway up -d`, monitor logs
9. Generate domain — `railway domain --service web`
10. Create superuser — via `railway run` or note for user
11. Summary — show URL, sync commands, what was deployed

**Redeployment flow:**
- Code only: `railway up -d`
- Data only: run `sync-to-prod.sh` then `railway up -d`
- Code + Data: both

**Error handling:** same patterns but remove Postgres-specific errors, add Litestream-specific ones (GCS auth, restore failures).

- [ ] **Step 2: Commit**

```bash
git add src/djangopress/skills/deploy-site-railway/SKILL.md
git commit -m "rewrite deploy skill for Litestream (no Postgres)"
```

---

## Task 7: Rewrite Sync Data Skill

**Files:**
- Rewrite: `src/djangopress/skills/sync-data/SKILL.md`

- [ ] **Step 1: Rewrite the skill**

Replace the entire content with:

**Frontmatter:**
```yaml
---
name: sync-data
description: Sync database between local and production via Litestream + GCS. Push local → prod or pull prod → local. Uses SQLite file replication — no JSON fixtures, no API endpoints, no SYNC_SECRET needed.
argument-hint: [push|pull]
allowed-tools: Bash, Read, Grep, Glob, AskUserQuestion
---
```

**Push flow:**
1. Pre-flight — verify `litestream.yml` exists, verify GCS credentials (`/tmp/gcs-credentials.json` or extract from .env), verify `gcloud` CLI available
2. Replicate — start Litestream locally, wait ~10 seconds, stop
3. Sync — run `scripts/sync-to-prod.sh`
4. Redeploy — `railway up -d`
5. Verify — check logs, curl site

**Pull flow:**
1. Pre-flight — same GCS checks
2. Pull — run `scripts/pull-from-prod.sh`
3. Verify — check page count locally

**No SYNC_SECRET, no push_data/pull_data, no HTTP API.**

- [ ] **Step 2: Commit**

```bash
git add src/djangopress/skills/sync-data/SKILL.md
git commit -m "rewrite sync-data skill for Litestream (no push_data/pull_data)"
```

---

## Task 8: Update generate-site Skill

**Files:**
- Modify: `src/djangopress/skills/generate-site/SKILL.md:97`

- [ ] **Step 1: Update the DATABASE reference**

On line 97, replace:
```python
DATABASES = {'default': env.db('DATABASE_URL', default=f'sqlite:///{BASE_DIR / "db.sqlite3"}')}
```

With:
```python
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3', 'OPTIONS': {'timeout': 20, 'transaction_mode': 'IMMEDIATE'}}}
```

- [ ] **Step 2: Commit**

```bash
git add src/djangopress/skills/generate-site/SKILL.md
git commit -m "update generate-site skill: SQLite config without DATABASE_URL"
```

---

## Task 9: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update Commands section**

Replace lines 182-183:
```
python manage.py push_data https://my-site.railway.app             # Push local DB to production
python manage.py pull_data https://my-site.railway.app             # Pull remote DB to local
```

With:
```
bash scripts/sync-to-prod.sh                                       # Push local DB to production via GCS
bash scripts/pull-from-prod.sh                                     # Pull production DB to local via GCS
```

- [ ] **Step 2: Update Skills table**

Change the `/deploy-site-railway` row:
```
| `/deploy-site-railway` | `/deploy-site-railway my-project` | Deploy to Railway with SQLite + Litestream + GCS. |
```

Change the `/sync-data` row:
```
| `/sync-data` | `/sync-data push` | Push/pull DB between local and production via Litestream + GCS. |
```

- [ ] **Step 3: Update Typical New Site Flow**

Change step 4 to:
```
4. /deploy-site-railway my-client ← deploy to Railway (SQLite + Litestream)
```

Change the "After making local changes" section to:
```
# After making local changes to a deployed site:
/sync-data push                   ← replicate local DB to GCS, sync to prod
```

- [ ] **Step 4: Update New Project Setup section**

In the `config/settings.py` example, replace:
```python
DATABASES = {'default': env.db('DATABASE_URL', default=f'sqlite:///{BASE_DIR / "db.sqlite3"}')}
```

With:
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'OPTIONS': {'timeout': 20, 'transaction_mode': 'IMMEDIATE'},
    }
}
```

Remove any references to `DATABASE_URL` or PostgreSQL in the setup instructions.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "update CLAUDE.md: Litestream architecture, remove Postgres references"
```

---

## Task 10: Clean Up Build Artifacts

**Files:**
- Delete stale files in `build/` directory

- [ ] **Step 1: Remove stale build artifacts**

```bash
rm -rf build/
```

- [ ] **Step 2: Commit**

```bash
git rm -rf build/
git commit -m "remove stale build artifacts"
```

---

## Task 11: Verify

- [ ] **Step 1: Check no Postgres references remain in the default flow**

```bash
grep -rn "push_data\|pull_data\|SYNC_SECRET\|DATABASE_URL.*postgres\|railway add -d postgres" \
  CLAUDE.md \
  site_template/ \
  scripts/new_site.sh \
  src/djangopress/skills/deploy-site-railway/ \
  src/djangopress/skills/sync-data/ \
  src/djangopress/skills/generate-site/
```

Expected: no results (or only in `/migrate-to-litestream` skill which is intentionally kept).

- [ ] **Step 2: Verify site_template has all required files**

```bash
ls -la site_template/Dockerfile site_template/.dockerignore site_template/litestream.yml site_template/gunicorn.conf.py site_template/scripts/entrypoint.sh site_template/scripts/sync-to-prod.sh site_template/scripts/pull-from-prod.sh
```

Expected: all files exist.

- [ ] **Step 3: Verify Procfile is gone**

```bash
ls site_template/Procfile 2>&1
```

Expected: `No such file or directory`.

- [ ] **Step 4: Verify push_data/pull_data are gone**

```bash
ls src/djangopress/core/management/commands/push_data.py src/djangopress/core/management/commands/pull_data.py 2>&1
```

Expected: `No such file or directory` for both.

- [ ] **Step 5: Verify sync API routes are gone**

```bash
grep "data-sync" src/djangopress/backoffice/urls.py
```

Expected: no results.
