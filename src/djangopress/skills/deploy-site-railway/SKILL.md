---
name: deploy-site-railway
description: Deploy a DjangoPress site to Railway with SQLite + Litestream + GCS. Handles first-time deployments and redeployments. No Postgres needed — database is SQLite replicated to Google Cloud Storage via Litestream. Use this skill when deploying any DjangoPress site to production, and when taking a deployed site live on its final custom domain (Cloudflare DNS in front of Railway, via the djangopress-manager's go_live).
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

- **If linked to a project and the user asked to go live on a domain:** Jump to **Go Live on the Final Domain**.
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

### Custom Domain Setup

Don't add custom domains here by hand. Taking the site live on its final domain is its own flow, run after the site works on `*.up.railway.app`: see **Go Live on the Final Domain** below.

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
  - Go live on the final domain: /deploy-site-railway go-live <domain>
  - Monitor logs: railway logs
```

---

## Go Live on the Final Domain

Use when the user wants the deployed site on its own domain (e.g. "mete online no domínio final", "go live on example.pt"). Cloudflare is the DNS in front of Railway. The **djangopress-manager** already implements this end to end (`manage.py go_live <slug>`); use it, don't hand-roll Cloudflare API calls. It gets the details right that a manual setup gets wrong:

- copies the domain's existing mail/service records (MX, SPF, DKIM, DMARC, `mail.`/`webmail.` …) into the new zone, and pins anything that pointed at the old apex to its old IP;
- creates the Railway CNAMEs **DNS-only** — Railway can't validate a proxied CNAME, so the proxy is turned on only after Railway issues the certificate (the manager's **Verificar** does that);
- adds the `_railway-verify` ownership TXTs (the CLI never returns them; without them Railway doesn't route the domain);
- SSL **Full**, a `www → apex` 301, and `CUSTOM_DOMAINS=<domain>,www.<domain>` on Railway (which the engine settings add to `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`).

Paths below assume the manager lives next to the sites: `MANAGER=~/Documents/djangopress-sites/djangopress-manager`. The Cloudflare token (`CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`) lives in the manager's `.env` — never print it.

### Step 1: Read-only checks (do these yourself)

```bash
dig +short NS <domain>          # who serves DNS today
dig +short A <domain>           # is an old site live there? It goes offline when the nameservers switch
dig +short MX <domain>          # mail that must keep working
curl -sI https://<domain> | head -3
```

Tell the user what's live on the domain today and that it will be replaced. `SiteSettings.gcs_folder` must be set (media stays in that folder whatever the domain); if it's empty, set it to the current folder before anything else.

### Step 2: Preparar (local manager DB only)

The site must be registered in the manager (`Site` with `slug` = the project folder). Run the same thing the Domain card's **Preparar** does:

```bash
cd $MANAGER && .venv/bin/python manage.py shell -c "
from manager.models import Site
from manager.domain_views import _preconditions
from manager.services.domains.dns_snapshot import snapshot_with_warnings
site = Site.objects.get(slug='<slug>')
problem = _preconditions(site)
print('preconditions:', problem or 'OK')
if not problem:
    found, warnings = snapshot_with_warnings('<domain>')
    site.live_domain, site.domain_records = '<domain>', [r.to_dict() for r in found]
    site.domain_status, site.domain_error = Site.DomainStatus.PREPARED, ''
    site.save()
    for d in site.domain_records: print('  ', d)
    print('warnings:', warnings)
"
```

Show the user the records that will be copied and any warnings. Fix any precondition problem first (engine version, settings overriding `ALLOWED_HOSTS`, no Railway project).

If the Railway custom domains were **already added by hand**, `go_live` stops ("já existe no Railway mas não tenho os registos DNS"). Either remove them in Railway, or save the targets the `railway domain <host> --json` output gave you: `site.railway_dns = {'<domain>': [{'name': '<domain>', 'type': 'CNAME', 'value': '<target>.up.railway.app'}], 'www.<domain>': [...]}`.

### Step 3: Executar — the user runs it

Creating a Cloudflare zone and DNS records is an outward-facing change, and auto mode blocks it. Give the user the commands **one per line**, ready to paste into their terminal:

```
cd ~/Documents/djangopress-sites/djangopress-manager
source .venv/bin/activate
python manage.py go_live <slug>
```

(Or, inside Claude Code, one line: `! ~/Documents/djangopress-sites/djangopress-manager/.venv/bin/python ~/Documents/djangopress-sites/djangopress-manager/manage.py go_live <slug>`.) Alternatively the user can press **Executar** on the site's Domain card in the manager (`http://localhost:9000`).

The command ends by printing the two Cloudflare nameservers.

### Step 4: Switch the nameservers (user, at the registrar)

At the domain's registrar, replace the current nameservers with the two Cloudflare ones. For `.pt` domains this is done at DNS.PT (or the registrar's panel) — leave the IP/glue fields empty.

### Step 5: Verify

Once the nameservers propagate (`dig +short NS <domain>` shows Cloudflare — minutes to a few hours), the user presses **Verificar** on the Domain card. It checks that Railway routes the domain, both certificates are VALID (and only then turns the Cloudflare proxy on for `@`/`www`), HTTPS, the www 301, MX and SPF, and marks the site live. Don't turn the proxy on by hand before Railway's certificate is valid.

Then confirm yourself:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://<domain>/
curl -sI https://www.<domain>/ | grep -iE '^(HTTP|location)'
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
