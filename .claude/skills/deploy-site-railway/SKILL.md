---
name: deploy-site-railway
description: Deploy a DjangoPress site to Railway with Postgres, data migration, and environment setup.
argument-hint: [project-name]
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, AskUserQuestion
---

# Railway Deployment Skill

You are deploying a DjangoPress site to Railway. This skill handles first-time deployments and redeployments, including data migration from local SQLite to Railway Postgres.

The argument provided is: `$ARGUMENTS`

---

## Phase 1: Pre-flight Check

### Confirm the correct project directory

**CRITICAL:** Before doing anything, verify you are in the right project folder. The user may ask to deploy a child project (e.g. `centianes-boattrip`) while your working directory is the `djangopress` template itself. Deploying the wrong folder is a serious mistake.

1. Check the current working directory:

```bash
pwd
```

2. Check if the folder name matches `$ARGUMENTS` (if provided). Also check git status to confirm this is a proper project:

```bash
basename "$(pwd)"
git remote -v
```

3. **If the current directory does NOT match the project the user wants to deploy** (e.g. you're in `djangopress` but they asked to deploy `centianes-boattrip`):
   - Look for the target project as a sibling folder: `ls ../` to find it
   - Tell the user: "You're currently in `<current-folder>`, but the project `<target>` is at `../<target>/`. I need to work from that directory."
   - Use `AskUserQuestion` to confirm: "Should I deploy from `../<target>/`?"
   - Once confirmed, `cd` into the correct project directory before continuing

4. **If the current directory IS the `djangopress` template repo** (check: `git remote -v` shows `axpmarante/djangopress`), **STOP and warn the user.** You should almost never deploy the template itself — only child projects cloned from it.

### Check deployment status

Determine if this is a first deployment or redeployment:

```bash
railway status
```

- **If linked to a project:** This is a redeployment. Jump to the **Redeployment Flow** section.
- **If not linked / command fails:** This is a first-time deployment. Continue with Phase 2.

### Check content

Check the project has content worth deploying:

```python
python manage.py shell -c "
from core.models import SiteSettings, Page, GlobalSection
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

If `NO_SETTINGS` or 0 pages, warn the user that there's no content to deploy and suggest running `/generate-site` first.

### Derive project name

1. From `$ARGUMENTS` if provided
2. Otherwise from `SiteSettings.domain`
3. Otherwise from the current folder name
4. Otherwise ask the user

---

## Phase 2: Create Deployment Files (if missing)

Check if `Procfile` and `gunicorn.conf.py` exist. The djangopress package includes these files, but if they're missing (e.g. custom deployment), create them:

**Procfile:**
```
web: python manage.py migrate && python manage.py collectstatic --noinput && gunicorn config.wsgi:application -c gunicorn.conf.py --bind 0.0.0.0:$PORT
```

**gunicorn.conf.py:**
```python
workers = 2
timeout = 120
```

These should already exist in the template. If they do, skip this step.

---

## Phase 3: Create Railway Project

```bash
railway init -n "<project-name>" -w "PWD"
```

Both `-n` and `-w` flags make this non-interactive. Confirm success by checking output.

---

## Phase 4: Add Postgres Database

```bash
railway add -d postgres
```

Railway automatically creates a `DATABASE_URL` variable on the database service.

Wait a few seconds for the database to provision:
```bash
sleep 5
railway status
```

---

## Phase 5: Create Web Service + Set Environment Variables

Create and link the web service:

```bash
railway add -s "web"
railway service link web
```

### Set environment variables

**IMPORTANT:** Set each variable individually with `--skip-deploys` to avoid triggering partial deploys. Use `railway variables --set` for each.

First, generate a new SECRET_KEY for production:

```python
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Then set all variables. Read `.env` to find which keys have values:

```bash
# Core settings (always set)
railway variables --set "SECRET_KEY=<generated-key>" --skip-deploys
railway variables --set "ENVIRONMENT=production" --skip-deploys
railway variables --set 'DATABASE_URL=${{Postgres.DATABASE_URL}}' --skip-deploys
```

For each of these keys, check if they're set in `.env` and copy the value if so:
- `GEMINI_API_KEY`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `UNSPLASH_ACCESS_KEY`
- `GS_BUCKET_NAME`
- `GS_PROJECT_ID`
- `MAILGUN_API_KEY`
- `MAILGUN_API_URL`
- `DEFAULT_FROM_EMAIL`

```bash
# Example for each key that has a value in .env:
railway variables --set "GEMINI_API_KEY=<value>" --skip-deploys
```

### GCS_CREDENTIALS_JSON (special handling)

This value is a full JSON string with special characters that break shell escaping. Use Python to set it:

```python
python -c "
import subprocess, os
from pathlib import Path
import environ

env = environ.Env()
env.read_env(Path('.env'))

creds = env('GCS_CREDENTIALS_JSON', default='')
if creds:
    result = subprocess.run(
        ['railway', 'variables', '--set', f'GCS_CREDENTIALS_JSON={creds}', '--skip-deploys'],
        capture_output=True, text=True
    )
    print('GCS credentials set' if result.returncode == 0 else f'Failed: {result.stderr}')
else:
    print('No GCS credentials found in .env — skipping')
"
```

### Media files warning

If GCS is NOT configured (no `GS_BUCKET_NAME` in `.env`), warn the user:

```
⚠️  No Google Cloud Storage configured. Media files (images uploaded locally)
will NOT be available on Railway — Railway's filesystem is ephemeral.

Options:
1. Set up GCS before deploying (recommended for sites with images)
2. Deploy without images and set up GCS later
3. Continue anyway (images will 404 on the live site)
```

Use `AskUserQuestion` to let the user decide.

---

## Phase 6: Deploy

```bash
railway up -d
```

The `-d` flag detaches. Then monitor deployment:

```bash
# Wait for deploy to start
sleep 10

# Check deployment status
railway logs --lines 50
```

If you see errors in logs, diagnose and fix them. Common issues:
- Missing environment variable → set it with `railway variables --set`
- Module not found → check `requirements.txt`
- Migration error → check the error and fix the migration

Wait until you see gunicorn starting successfully (e.g., `Listening at: http://0.0.0.0:<port>`).

---

## Phase 7: Generate Domain

```bash
railway domain --service web
```

Capture the `*.railway.app` URL from the output. This is the live site URL.

---

## Phase 7b: Upload Local Media to GCS (if needed)

If GCS is configured (`GS_BUCKET_NAME` is set), check whether media files exist locally but not in GCS. This happens when images were generated during development without GCS configured.

```bash
# Check if local media files exist
ls media/site_images/ 2>/dev/null | head -5
```

If local media files exist, check the GCS storage status:

```python
python manage.py shell -c "
from django.core.files.storage import default_storage
backend = default_storage.__class__.__name__
print(f'Storage: {backend}')
print(f'GCS active: {\"DomainBased\" in backend}')
"
```

If GCS is active but images are local (generated before GCS was configured), upload them:

```bash
# Get the domain folder name from SiteSettings
DOMAIN=$(python manage.py shell -c "from core.models import SiteSettings; s=SiteSettings.objects.first(); print(s.domain if s else 'default')")

# Upload all local media to GCS
gsutil -m cp -r media/site_images "gs://<GS_BUCKET_NAME>/${DOMAIN}/"
```

Read `GS_BUCKET_NAME` from `.env` to fill in the bucket name. If `gsutil` is not available, use Python:

```python
python manage.py shell -c "
from django.core.files.storage import default_storage
from pathlib import Path
import os

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

If GCS is NOT configured and there are local media files, warn the user that images will 404 on the live site (same warning as Phase 5).

---

## Phase 8: Migrate Data (SQLite → Postgres)

> **Preferred method:** Use `python manage.py push_data https://<DOMAIN>.railway.app` instead of dumpdata/loaddata. See `/sync-data` skill. The method below is a manual fallback.

### Get the public DATABASE_URL

Railway's `DATABASE_URL` uses internal hostnames (`postgres.railway.internal`) not accessible from outside Railway's network. We need the public URL:

```bash
railway variables -s Postgres
```

Find the `DATABASE_PUBLIC_URL` value from the output. It looks like `postgresql://postgres:xxx@xxx.railway.app:port/railway`.

Store it in a shell variable for the subsequent commands:

```bash
export REMOTE_DB="<DATABASE_PUBLIC_URL value>"
```

### Export data from local SQLite

```bash
python manage.py dumpdata core ai.RefinementSession \
  --natural-foreign --natural-primary \
  --exclude core.PageVersion \
  --indent 2 -o data_export.json
```

This exports:
- All `core` models: Pages, SiteSettings, GlobalSections, SiteImages, DynamicForms, FormSubmissions, MenuItems
- AI refinement sessions

**Excluded:**
- `core.PageVersion` — the `post_save` signal auto-creates these when Pages are loaded, so including them causes duplicate key errors
- `auth`, `contenttypes`, `sessions`, `admin` — these are created by migrations on Railway

### Load into Railway Postgres

```bash
DATABASE_URL="$REMOTE_DB" ENVIRONMENT=production python manage.py loaddata data_export.json
```

This runs loaddata locally but points Django at the remote Postgres via the public DATABASE_URL.

Clean up:

```bash
rm data_export.json
```

### Verify data migrated

```bash
DATABASE_URL="$REMOTE_DB" ENVIRONMENT=production python manage.py shell -c "
from core.models import SiteSettings, Page, GlobalSection
print(f'Settings: {\"YES\" if SiteSettings.objects.exists() else \"NO\"}')
print(f'Pages: {Page.objects.filter(is_active=True).count()}')
print(f'Header: {\"YES\" if GlobalSection.objects.filter(key=\"main-header\").exists() else \"NO\"}')
print(f'Footer: {\"YES\" if GlobalSection.objects.filter(key=\"main-footer\").exists() else \"NO\"}')
"
```

---

## Phase 9: Create Superuser

Ask the user for admin credentials:

```
AskUserQuestion:
Question: "What admin credentials should we create for the Railway deployment?"
Options:
- "Same as local" — I'll reuse my local credentials
- "Create new" — I'll provide username/email/password
```

If "Same as local", ask for just the password (we can't read it from the DB).

If "Create new", ask for username, email, and password.

Then create:

```bash
DATABASE_URL="$REMOTE_DB" ENVIRONMENT=production python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(is_superuser=True).exists():
    User.objects.create_superuser('<username>', '<email>', '<password>')
    print('Superuser created')
else:
    print('Superuser already exists')
"
```

---

## Phase 10: Summary

Verify the site is live:

```bash
curl -s -o /dev/null -w "%{http_code}" https://<domain>.railway.app/
```

A `302` (redirect to language prefix) or `200` means success.

Print a deployment summary:

```
Deployment complete!

🌐 Live URL: https://<domain>.railway.app/
🔧 Backoffice: https://<domain>.railway.app/backoffice/

Data migrated:
  - X pages
  - Header: ✓/✗
  - Footer: ✓/✗
  - Settings: ✓

Environment:
  - DATABASE_URL: Postgres (Railway)
  - GCS Media: ✓/✗
  - Email (Mailgun): ✓/✗

Next steps:
  - Visit the live site and verify all pages render correctly
  - Test the contact form
  - Set up a custom domain in Railway dashboard if needed
  - Monitor logs: railway logs -f
```

---

## Redeployment Flow

When `railway status` shows an existing linked project, ask the user what to update:

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

Migrations run automatically via the Procfile command chain.

Monitor deployment:
```bash
sleep 10
railway logs --lines 30
```

### Data redeployment

First, get the public DATABASE_URL:

```bash
railway variables -s Postgres
```

Extract `DATABASE_PUBLIC_URL` and store it:

```bash
export REMOTE_DB="<DATABASE_PUBLIC_URL value>"
```

Then export, flush, and reload:

```bash
# Export from local
python manage.py dumpdata core ai.RefinementSession \
  --natural-foreign --natural-primary \
  --exclude core.PageVersion \
  --indent 2 -o data_export.json

# Flush remote database (preserves schema, clears data)
DATABASE_URL="$REMOTE_DB" ENVIRONMENT=production python manage.py flush --no-input

# Load fresh data
DATABASE_URL="$REMOTE_DB" ENVIRONMENT=production python manage.py loaddata data_export.json

# Clean up
rm data_export.json
```

**Important:** `flush` deletes all data including the superuser. Recreate it after loading data:

```bash
DATABASE_URL="$REMOTE_DB" ENVIRONMENT=production python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(is_superuser=True).exists():
    User.objects.create_superuser('<username>', '<email>', '<password>')
    print('Superuser recreated')
"
```

### Code + Data

Run both sequences above: deploy code first, then sync data after the deployment succeeds.

---

## Error Handling

- **Wrong project directory:** If `git remote -v` shows `axpmarante/djangopress`, you're in the template repo — NOT a child project. `cd` to the correct child project folder before deploying. Always verify with `pwd` and `basename` before proceeding.
- **`railway` command not found:** Tell the user to install Railway CLI: `npm install -g @railway/cli` then `railway login`
- **Not logged in:** Run `railway login` and retry
- **Project creation fails:** Check workspace name, suggest `railway whoami` to verify auth
- **Database not ready:** Wait and retry — Postgres can take 10-30 seconds to provision
- **`dumpdata` fails:** Check for circular references, try excluding problematic models one at a time
- **`loaddata` fails with unique constraint on PageVersion:** PageVersion is excluded from dumpdata by default. If using an old export, re-run dumpdata with `--exclude core.PageVersion`
- **`loaddata` fails with other constraint violations:** Try flushing the remote DB first: `DATABASE_URL="$REMOTE_DB" ENVIRONMENT=production python manage.py flush --no-input`
- **`railway run` DNS errors / can't connect to Postgres:** Railway's internal hostnames (`postgres.railway.internal`) aren't accessible from outside Railway's network. Use `DATABASE_PUBLIC_URL` instead — get it with `railway variables -s Postgres`
- **Deploy fails:** Read logs carefully. Fix the issue locally, commit, and `railway up -d` again
- **502 after deploy:** Check logs — usually a crashed gunicorn worker. Look for import errors or missing env vars
- **CSRF verification failed (403):** Ensure `CSRF_TRUSTED_ORIGINS` includes `https://*.up.railway.app` in settings.py (Railway domains are `xxx.up.railway.app`)
- **DisallowedHost error:** Ensure `ALLOWED_HOSTS` includes `.railway.app` (dot prefix) — this matches multi-level subdomains like `*.up.railway.app`
