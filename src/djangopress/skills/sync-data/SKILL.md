---
name: sync-data
description: Sync database between local and production via Litestream + GCS. Push local → prod or pull prod → local. Uses SQLite file replication through Google Cloud Storage — no JSON fixtures, no API endpoints needed. Use this whenever the user wants to push local changes to production or pull production data locally.
argument-hint: [push|pull]
allowed-tools: Bash, Read, Grep, Glob, AskUserQuestion
---

# Sync Data via Litestream + GCS

Sync database content between local development and production. Data flows through Google Cloud Storage as Litestream replicas — the database file is replicated directly, not serialized to JSON.

The argument provided is: `$ARGUMENTS`

Parse `$ARGUMENTS`:
- If it contains "pull", use pull direction
- If it contains "push" or no direction keyword, use push direction

---

## Pre-flight Check

### Verify project directory

```bash
pwd
railway status
```

Must be in a DjangoPress child project linked to Railway.

### Verify Litestream infrastructure

```bash
ls litestream.yml scripts/sync-to-prod.sh scripts/pull-from-prod.sh
```

If missing, tell the user to run `/migrate-to-litestream` first.

### Verify GCS credentials

Check if credentials file exists:

```bash
ls /tmp/gcs-credentials.json 2>/dev/null
```

If not, extract from `.env`:

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
export GOOGLE_APPLICATION_CREDENTIALS=/tmp/gcs-credentials.json
```

### Verify Litestream is installed

```bash
~/bin/litestream version 2>/dev/null || litestream version 2>/dev/null
```

If not installed, install v0.3.13:
```bash
curl -L https://github.com/benbjohnson/litestream/releases/download/v0.3.13/litestream-v0.3.13-darwin-arm64.zip -o /tmp/litestream.zip
unzip -o /tmp/litestream.zip -d /tmp/
mkdir -p ~/bin && mv /tmp/litestream ~/bin/litestream && chmod +x ~/bin/litestream
rm /tmp/litestream.zip
```

---

## Push Flow (dev → prod)

### Step 1: Replicate local DB to GCS

Enable WAL mode and run Litestream to replicate the current database state:

```bash
sqlite3 db.sqlite3 'PRAGMA journal_mode=WAL;'
GOOGLE_APPLICATION_CREDENTIALS=/tmp/gcs-credentials.json ~/bin/litestream replicate -config litestream.yml &
sleep 10
pkill -f "litestream replicate"
sleep 2
```

### Step 2: Sync dev → prod

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/tmp/gcs-credentials.json
bash scripts/sync-to-prod.sh
```

This backs up the current prod replica, then copies dev → prod in GCS.

### Step 3: Redeploy Railway

```bash
railway up -d
```

The entrypoint will restore the updated database from GCS on boot.

### Step 4: Verify

```bash
sleep 70
railway logs --lines 10 --filter "entrypoint"
```

Expected: `[entrypoint] Database restored from GCS`

Check the site loads:
```bash
DOMAIN=$(railway variables --kv 2>&1 | grep RAILWAY_PUBLIC_DOMAIN | cut -d= -f2)
curl -s -o /dev/null -w "%{http_code}" "https://$DOMAIN/"
```

Expected: 200 or 302.

---

## Pull Flow (prod → dev)

### Step 1: Pull from production

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/tmp/gcs-credentials.json
bash scripts/pull-from-prod.sh
```

This backs up the local DB, restores from the prod GCS replica, and sets WAL mode.

### Step 2: Verify

```bash
python manage.py shell -c "
from djangopress.core.models import Page
print(f'Pages: {Page.objects.count()}')
"
```

---

## Error Handling

- **No GCS credentials:** `GCS_CREDENTIALS_JSON` must be set in `.env`. This is also needed for media storage.
- **No dev replica in GCS:** Run Litestream locally first to create the initial replica.
- **No prod replica in GCS:** The site hasn't been deployed yet, or was deployed before Litestream. Run `/deploy-site-railway` first.
- **`gcloud` not found:** Install the Google Cloud SDK: `brew install google-cloud-sdk`
- **Litestream restore fails:** Check that the GCS path exists: `gcloud storage ls gs://corporate-django-sites-media/<slug>/db/prod/`
