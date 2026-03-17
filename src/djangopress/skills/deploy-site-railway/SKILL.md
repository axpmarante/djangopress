---
name: deploy-site-railway
description: Deploy a DjangoPress site to Railway with SQLite + Litestream + GCS. Handles first-time deployments and redeployments. No Postgres needed — database is SQLite replicated to Google Cloud Storage via Litestream. Use this skill when deploying any DjangoPress site to production.
argument-hint: [project-name]
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, AskUserQuestion
---

# Railway Deployment Skill

Deploy a DjangoPress site to Railway using SQLite + Litestream + GCS. The database is SQLite in both development and production, with Litestream continuously replicating to Google Cloud Storage.

The argument provided is: `$ARGUMENTS`

---

## Phase 1: Pre-flight Check

### Confirm the correct project directory

**CRITICAL:** Before doing anything, verify you are in the right project folder.

1. Check the current working directory:

```bash
pwd
basename "$(pwd)"
git remote -v
```

2. **If the current directory does NOT match `$ARGUMENTS`**: look for the target as a sibling folder (`ls ../`), confirm with user, then `cd` to it.

3. **If the current directory IS the `djangopress` template repo** (remote shows `axpmarante/djangopress`), **STOP and warn the user.**

### Check deployment status

```bash
railway status
```

- **If linked to a project:** This is a redeployment. Jump to the **Redeployment Flow** section.
- **If not linked / command fails:** This is a first-time deployment. Continue with Phase 2.

### Check content

```python
python manage.py shell -c "
from djangopress.core.models import SiteSettings, Page, GlobalSection
s = SiteSettings.objects.first()
if s:
    print(f'Site: {s.get_site_name()}')
    print(f'Domain: {s.domain or \"NOT SET\"}')
    print(f'Languages: {s.get_language_codes()}')
    print(f'Pages: {Page.objects.filter(is_active=True).count()}')
    print(f'Header: {\"YES\" if GlobalSection.objects.filter(key=\"main-header\", is_active=True).exists() else \"NO\"}')
    print(f'Footer: {\"YES\" if GlobalSection.objects.filter(key=\"main-footer\").exists() else \"NO\"}')
else:
    print('NO_SETTINGS')
"
```

If `NO_SETTINGS` or 0 pages, warn the user and suggest `/generate-site` first.

### Derive project name

1. From `$ARGUMENTS` if provided
2. Otherwise from `SiteSettings.domain`
3. Otherwise from the current folder name
4. Otherwise ask the user

---

## Phase 2: Verify Deployment Files

Check that the Litestream infrastructure exists:

```bash
ls Dockerfile scripts/entrypoint.sh litestream.yml gunicorn.conf.py .dockerignore
```

All must exist. If any are missing, the site was likely created before the Litestream template update. Tell the user to run `/migrate-to-litestream` first, or create the missing files from the site template.

---

## Phase 3: Create Railway Project

```bash
railway init -n "<project-name>" -w "PWD"
```

Both `-n` and `-w` flags make this non-interactive.

---

## Phase 4: Create Web Service + Set Environment Variables

Create and link the web service (NO Postgres):

```bash
railway add -s "web"
railway service link web
```

### Set environment variables

**IMPORTANT:** Set each variable individually with `--skip-deploys`.

Generate a new SECRET_KEY:

```python
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Set core variables:

```bash
railway variables --set "SECRET_KEY=<generated-key>" --skip-deploys
railway variables --set "ENVIRONMENT=production" --skip-deploys
railway variables --set "DJANGO_SETTINGS_MODULE=config.settings" --skip-deploys
railway variables --set "LITESTREAM_REPLICA_PATH=<project-slug>/db/prod/" --skip-deploys
```

For each of these keys, check `.env` and copy the value if set:
- `GCS_BUCKET_NAME` / `GS_BUCKET_NAME` / `GS_PROJECT_ID`
- `GEMINI_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`
- `UNSPLASH_ACCESS_KEY`
- `MAILGUN_API_KEY` / `MAILGUN_API_URL` / `DEFAULT_FROM_EMAIL`

### GCS_CREDENTIALS_JSON (special handling)

Use Python to set it (JSON with special characters breaks shell escaping):

```python
python -c "
import subprocess
from pathlib import Path
import environ

env = environ.Env()
env.read_env(Path('.env'))

creds = env('GCS_CREDENTIALS_JSON', default='')
if creds:
    if creds.startswith(\"'\") and creds.endswith(\"'\"):
        creds = creds[1:-1]
    result = subprocess.run(
        ['railway', 'variables', '--set', f'GCS_CREDENTIALS_JSON={creds}', '--skip-deploys'],
        capture_output=True, text=True
    )
    print('GCS credentials set' if result.returncode == 0 else f'Failed: {result.stderr}')
else:
    print('No GCS credentials found in .env — skipping')
"
```

### GCS required warning

If GCS is NOT configured (no `GS_BUCKET_NAME` in `.env`), warn the user — GCS is required for both media storage and Litestream replication.

---

## Phase 5: Replicate Local Database to GCS

### Extract GCS credentials

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

### Enable WAL mode and replicate

```bash
sqlite3 db.sqlite3 'PRAGMA journal_mode=WAL;'
```

Start Litestream, wait for snapshot upload, stop:

```bash
GOOGLE_APPLICATION_CREDENTIALS=/tmp/gcs-credentials.json ~/bin/litestream replicate -config litestream.yml &
sleep 12
pkill -f "litestream replicate"
sleep 2
```

### Sync dev to prod

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/tmp/gcs-credentials.json
bash scripts/sync-to-prod.sh
```

---

## Phase 6: Deploy

```bash
railway up -d
```

Monitor deployment:

```bash
sleep 70
railway logs --lines 20
```

Expected output:
```
[entrypoint] Database restored from GCS
[entrypoint] Running migrations...
[entrypoint] Starting Litestream replication + gunicorn...
```

---

## Phase 7: Generate Domain

```bash
railway domain --service web
```

Capture the `*.railway.app` URL.

---

## Phase 8: Upload Local Media to GCS (if needed)

Check if local media files exist that haven't been uploaded to GCS:

```bash
ls media/site_images/ 2>/dev/null | head -5
```

If files exist, upload them using the Python storage backend:

```python
python manage.py shell -c "
from django.core.files.storage import default_storage
from pathlib import Path

media_dir = Path('media/site_images')
if not media_dir.exists():
    print('No local media files to upload')
else:
    files = list(media_dir.glob('*'))
    print(f'Uploading {len(files)} files to GCS...')
    for f in files:
        with open(f, 'rb') as fh:
            saved_name = default_storage.save(f'site_images/{f.name}', fh)
            print(f'  Uploaded: {saved_name}')
    print('Done!')
"
```

---

## Phase 9: Summary

Verify the site is live:

```bash
curl -s -o /dev/null -w "%{http_code}" https://<domain>.railway.app/
```

Print summary:

```
Deployment complete!

Live URL: https://<domain>.railway.app/
Backoffice: https://<domain>.railway.app/backoffice/

Database: SQLite + Litestream → GCS
  Dev replica: gs://corporate-django-sites-media/<slug>/db/dev/
  Prod replica: gs://corporate-django-sites-media/<slug>/db/prod/

Sync commands:
  Push dev → prod:  /sync-data push  (or: bash scripts/sync-to-prod.sh && railway up -d)
  Pull prod → dev:  /sync-data pull  (or: bash scripts/pull-from-prod.sh)

Next steps:
  - Visit the live site and verify all pages render correctly
  - Test the contact form
  - Set up a custom domain in Railway dashboard if needed
  - Monitor logs: railway logs
```

---

## Redeployment Flow

When `railway status` shows an existing linked project:

```
AskUserQuestion:
Question: "This project is already deployed to Railway. What would you like to update?"
Options:
- "Code + Data" — push code changes and sync database content
- "Code only" — push code changes (migrations run automatically)
- "Data only" — sync database content without redeploying code
```

### Code redeployment

```bash
railway up -d
```

Monitor:
```bash
sleep 30
railway logs --lines 20
```

### Data redeployment

Use the `/sync-data push` skill, or manually:

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/tmp/gcs-credentials.json
# Replicate local changes to GCS
GOOGLE_APPLICATION_CREDENTIALS=/tmp/gcs-credentials.json ~/bin/litestream replicate -config litestream.yml &
sleep 10 && pkill -f "litestream replicate" && sleep 2
# Sync to prod
bash scripts/sync-to-prod.sh
# Redeploy to pick up new data
railway up -d
```

### Code + Data

Deploy code first, then sync data after the deployment succeeds.

---

## Error Handling

- **Wrong project directory:** If `git remote -v` shows `axpmarante/djangopress`, you're in the template repo. `cd` to the correct child project.
- **`railway` command not found:** `npm install -g @railway/cli` then `railway login`
- **Missing Dockerfile/entrypoint:** Site was created before Litestream migration. Run `/migrate-to-litestream` first.
- **GCS credentials not set:** Both media and database replication require GCS. Set up `GCS_CREDENTIALS_JSON` in `.env` before deploying.
- **Litestream restore fails:** Check GCS credentials and that the replica path exists: `gcloud storage ls gs://bucket/slug/db/prod/`
- **Deploy fails:** Read logs. Common issues: missing env var, migration error, import error. Fix locally, commit, `railway up -d`.
- **502 after deploy:** Check logs — usually a crashed gunicorn worker from import errors or missing env vars.
- **CSRF verification failed (403):** Ensure `CSRF_TRUSTED_ORIGINS` includes `https://*.up.railway.app` in settings.py.
- **DisallowedHost error:** Ensure `ALLOWED_HOSTS` includes `.railway.app` (dot prefix).
