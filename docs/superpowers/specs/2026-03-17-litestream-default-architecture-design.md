# DjangoPress — Litestream as Default Architecture

## Problem

DjangoPress currently uses PostgreSQL in production and SQLite in development. Syncing between them requires custom management commands (`push_data`/`pull_data`) that serialize to JSON fixtures — a process that is slow, error-prone, and non-incremental. After a successful PoC and migration of all 6 deployed sites to SQLite + Litestream + GCS, the package should adopt this as the default architecture.

## Solution

Make SQLite + Litestream + GCS the standard architecture for all new DjangoPress sites. Remove all PostgreSQL-related sync infrastructure. Update the site template, deployment skill, and sync skill accordingly.

## Scope

**In scope:**
- `site_template/` — add Litestream files, remove Procfile
- `scripts/new_site.sh` — configure Litestream slug on site creation
- Skills — rewrite `/deploy-site-railway` and `/sync-data`
- Management commands — remove `push_data`, `pull_data`
- API endpoints — remove `data-sync`, `data-sync-export`
- `CLAUDE.md` — update all references
- Package settings — remove `SYNC_SECRET` references

**Out of scope:**
- DjangoPress Manager updates (separate sub-project)
- Migration of existing sites (handled by `/migrate-to-litestream` skill)

---

## 1. Site Template Changes

### Files to Remove
- `Procfile` — replaced by Dockerfile CMD

### Files to Add

**`Dockerfile`:**
Multi-stage build: Alpine stage downloads Litestream v0.3.13, Python 3.13-slim stage installs git + sqlite3, copies Litestream binary, installs pip packages, runs collectstatic with dummy SECRET_KEY, sets entrypoint.

**`.dockerignore`:**
Excludes venv/, .git/, db.sqlite3, media/, .env, __pycache__/, .claude/, briefings/, *.log.

**`litestream.yml`:**
```yaml
dbs:
  - path: ./db.sqlite3
    replicas:
      - type: gcs
        bucket: corporate-django-sites-media
        path: __SITE_SLUG__/db/dev/
        sync-interval: 1s
```
`__SITE_SLUG__` is replaced by `new_site.sh` during project creation.

**`scripts/entrypoint.sh`:**
Boot sequence for Railway:
1. Write GCS credentials from env var to temp file
2. Generate litestream.yml with production paths (uses `LITESTREAM_REPLICA_PATH` env var, defaults to `__SITE_SLUG__/db/prod/`)
3. Restore db.sqlite3 from GCS if it doesn't exist
4. Set WAL mode
5. Run migrations
6. Launch Litestream replicate with gunicorn as subprocess

`__SITE_SLUG__` in the default REPLICA_PATH is replaced by `new_site.sh`.

**`scripts/sync-to-prod.sh`:**
Dev→prod sync helper. Derives slug from `basename $(pwd)`. Stops Litestream, backs up prod in GCS, copies dev→prod via `gcloud storage rsync`, prints instructions to redeploy.

**`scripts/pull-from-prod.sh`:**
Prod→dev pull helper. Derives slug from `basename $(pwd)`. Stops Litestream, backs up local DB, restores from prod GCS path, sets WAL mode.

### Files to Modify

**`config/settings.py`:**
Replace the DATABASES block:
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

**`requirements.txt`:**
Add `gunicorn>=22.0` (currently only in the package as a transitive dependency).

**`.env.example`:**
- Remove the DATABASE_URL section (no longer needed)
- Add under GCS section:
```
# LITESTREAM_REPLICA_PATH=my-site/db/prod/
```

**`.gitignore`** (if present in template):
Add `*.sqlite3-wal`, `*.sqlite3-shm`.

---

## 2. `new_site.sh` Changes

After copying the template (step 1), add a new step that replaces `__SITE_SLUG__` with the project name:

```bash
# Replace __SITE_SLUG__ placeholders
sed -i.bak "s|__SITE_SLUG__|$PROJECT_NAME|g" litestream.yml scripts/entrypoint.sh
rm -f litestream.yml.bak scripts/entrypoint.sh.bak
```

Update the "Next steps" output at the end to reference the new sync workflow instead of Postgres.

---

## 3. Skill Changes

### `/deploy-site-railway` — Rewrite

Remove all Postgres-related phases:
- `railway add -d postgres`
- `DATABASE_URL=${{Postgres.DATABASE_URL}}`
- Data migration via dumpdata/loaddata
- `DATABASE_PUBLIC_URL` usage

Replace with Litestream deployment flow:
1. Pre-flight check (same)
2. Create deployment files — verify Dockerfile and scripts exist (from template)
3. Create Railway project — `railway init` (same)
4. Create web service — `railway add -s "web"` (same, no Postgres)
5. Set env vars — same keys minus DATABASE_URL, plus `LITESTREAM_REPLICA_PATH=<slug>/db/prod/`
6. Replicate local SQLite to GCS — run Litestream locally, then `sync-to-prod.sh`
7. Deploy — `railway up -d`
8. Generate domain (same)
9. Create superuser (same approach but via Railway exec or first-boot)
10. Verify and summarize

### `/sync-data` — Rewrite

Complete rewrite. Two modes:

**Push (dev → prod):**
1. Ensure Litestream has replicated locally (start, wait, stop)
2. Run `scripts/sync-to-prod.sh`
3. Redeploy Railway: `railway up -d`
4. Verify site works

**Pull (prod → dev):**
1. Run `scripts/pull-from-prod.sh`
2. Verify local data

No more SYNC_SECRET, no more HTTP API, no more JSON fixtures.

### `/migrate-to-litestream` — Keep

Remains useful for existing sites still on Postgres. No changes needed.

---

## 4. Package Code to Remove

### Management Commands
- `src/djangopress/core/management/commands/push_data.py` — delete
- `src/djangopress/core/management/commands/pull_data.py` — delete

### API Endpoints
In `src/djangopress/backoffice/api_views.py`, remove:
- `data_sync_receive()` function
- `data_sync_export()` function
- `_check_sync_auth()` helper
- `_truncate_sync_tables()` helper
- `_load_fixture()` helper

In `src/djangopress/backoffice/urls.py`, remove:
- `path('api/data-sync/', ...)` route
- `path('api/data-sync-export/', ...)` route

### Settings References
Remove any references to `SYNC_SECRET` in the package settings or documentation.

---

## 5. CLAUDE.md Updates

### Commands Section
Remove:
```
python manage.py push_data https://my-site.railway.app
python manage.py pull_data https://my-site.railway.app
```

Add:
```
bash scripts/sync-to-prod.sh          # Push local DB to production via GCS
bash scripts/pull-from-prod.sh        # Pull production DB to local via GCS
```

### Skills Table
- Update `/deploy-site-railway` description: "Deploy to Railway with SQLite + Litestream + GCS"
- Update `/sync-data` description: "Push/pull DB between local and production via Litestream + GCS"
- Remove references to Postgres in skill descriptions

### Typical New Site Flow
Update step 4:
```
4. /deploy-site-railway my-client  ← deploy to Railway (SQLite + Litestream)
```

Remove "After making local changes" section referencing `/sync-data push` — replace with:
```
# After making local changes to a deployed site:
/sync-data push                    ← replicate local DB to GCS, sync to prod
```

### New Project Setup
Remove DATABASE_URL references from the environment setup section.

---

## 6. GCS Bucket Convention

All sites use the same bucket (`corporate-django-sites-media`) with paths:
```
gs://corporate-django-sites-media/<site-slug>/db/dev/   — local dev backup
gs://corporate-django-sites-media/<site-slug>/db/prod/  — production backup
gs://corporate-django-sites-media/<site-slug>/          — media files (existing)
```

The `db/` prefix separates database replicas from media files within each site's folder.

---

## Success Criteria

1. `new_site.sh` creates a project with Litestream infrastructure ready to use
2. `/deploy-site-railway` deploys without Postgres, using Litestream + GCS
3. `/sync-data push` replicates local → GCS → prod successfully
4. `/sync-data pull` restores prod → local successfully
5. `push_data` and `pull_data` commands no longer exist
6. No references to Postgres remain in the default deployment flow
