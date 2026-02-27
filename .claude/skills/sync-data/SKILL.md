---
name: sync-data
description: Sync database content between local and a deployed Railway site. Push local → remote via push_data, or pull remote → local via pull_data. Handles SYNC_SECRET setup, code deployment, and data transfer.
argument-hint: [push|pull] [project-url-or-name]
allowed-tools: Bash, Read, Edit, Grep, Glob, AskUserQuestion
---

# Sync Data with Railway

Sync database content (pages, settings, media records, forms, header/footer, menu items) between local and a deployed Railway site.

**Two directions:**
- **Push** (`push_data`): local → remote — overwrite production with local content
- **Pull** (`pull_data`): remote → local — overwrite local with production content

The argument provided is: `$ARGUMENTS`

Parse `$ARGUMENTS` to determine direction and target:
- If it contains "pull", use pull direction
- If it contains "push" or no direction keyword, use push direction
- Extract the URL if provided (anything starting with `https://`)

---

## Phase 1: Pre-flight Check

### Verify project directory

```bash
pwd
railway status
```

- Must be linked to a Railway project. If not, tell the user to run `/deploy-site` first.
- If `railway` command fails, tell user to install: `npm install -g @railway/cli && railway login`

### Determine target URL

1. From `$ARGUMENTS` if it looks like a URL (`https://...`)
2. Otherwise, get it from Railway:

```bash
railway variables --json 2>&1 | python -c "import sys,json; v=json.load(sys.stdin); print(v.get('RAILWAY_SERVICE_WEB_URL',''))"
```

Store as `TARGET_URL` for later use.

### Verify commands exist

```bash
python manage.py push_data --help 2>&1 | head -5
python manage.py pull_data --help 2>&1 | head -5
```

If the commands don't exist, the project needs the data sync API. Tell the user:

```
This project doesn't have the data sync API yet.
You need to pull the latest changes from the djangopress template:

    git fetch upstream && git merge upstream/main
```

---

## Phase 2: Ensure SYNC_SECRET

### Check local .env

```bash
grep SYNC_SECRET .env
```

If not set or empty:

```bash
# Generate a new secret
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Add it to `.env`:
```
SYNC_SECRET=<generated-value>
```

### Check Railway env vars

```bash
railway variables --json 2>&1 | python -c "import sys,json; v=json.load(sys.stdin); print(v.get('SYNC_SECRET','NOT SET'))"
```

If `NOT SET`, set it to the same value as local:

```bash
railway variables --set "SYNC_SECRET=<same-value-as-local>"
```

**CRITICAL:** Local and Railway must have the **same** SYNC_SECRET value.

---

## Phase 3: Ensure Endpoints are Deployed

Check if the remote endpoints exist:

```bash
# Check push endpoint (POST-only, so GET returns 405)
curl -s -o /dev/null -w "%{http_code}" https://<TARGET_URL>/backoffice/api/data-sync/
# Check pull endpoint (GET-only, so should return 401 without auth)
curl -s -o /dev/null -w "%{http_code}" https://<TARGET_URL>/backoffice/api/data-sync-export/
```

- **405** or **401** = endpoint exists and is live. Continue to Phase 4.
- **404** = endpoint not deployed yet. Deploy first:

```bash
railway up -d
```

Wait for deployment to complete:

```bash
sleep 60
curl -s -o /dev/null -w "%{http_code}" https://<TARGET_URL>/backoffice/api/data-sync/
```

Repeat until you get 405. If it takes more than 3 minutes, check logs:

```bash
railway logs --lines 30
```

---

## Phase 4a: Push Data (local → remote)

### Dry run first

```bash
python manage.py push_data https://<TARGET_URL> --dry-run
```

### Confirm with user

```
AskUserQuestion:
Question: "Ready to push local data to <TARGET_URL>? This will replace pages, settings, forms, media records, header/footer, and menu items on the remote site. Users and AI data are NOT affected."
Options:
- "Push now" — Replace remote content with local data
- "Dry run only" — Just show what would be sent
- "Cancel" — Don't push anything
```

### Execute push

```bash
echo "yes" | python manage.py push_data https://<TARGET_URL>
```

### Verify

```bash
curl -s -o /dev/null -w "%{http_code}" https://<TARGET_URL>/
```

A `302` or `200` means the site is serving content.

---

## Phase 4b: Pull Data (remote → local)

### Dry run first

```bash
python manage.py pull_data https://<TARGET_URL> --dry-run
```

### Confirm with user

```
AskUserQuestion:
Question: "Ready to pull data from <TARGET_URL>? This will REPLACE local pages, settings, forms, media records, header/footer, and menu items with production content. Local users and AI data are preserved."
Options:
- "Pull now" — Replace local content with remote data
- "Dry run only" — Just show what would be fetched
- "Cancel" — Don't pull anything
```

### Execute pull

```bash
echo "yes" | python manage.py pull_data https://<TARGET_URL>
```

---

## Phase 5: Summary

```
Data sync complete!

Direction: <push|pull>
Target: https://<TARGET_URL>/
Objects synced: <count from output>
Payload size: <size from output>

What was synced:
  - Pages + page versions (last 3 per page)
  - SiteSettings (design system, branding, contact info)
  - GlobalSections (header, footer)
  - MenuItems
  - SiteImages (media library records — files live in GCS)
  - DynamicForms + submissions

What was NOT synced (preserved on target):
  - Users / superuser credentials
  - AI refinement sessions
  - News posts
  - Assistant sessions
  - Blueprints

Live site: https://<TARGET_URL>/
Backoffice: https://<TARGET_URL>/backoffice/
```

---

## Error Handling

- **HTTP 401/403:** SYNC_SECRET mismatch between local and Railway. Verify both match.
- **HTTP 500 "SYNC_SECRET is not configured":** The secret is not set on the target. Run `railway variables --set "SYNC_SECRET=<value>"` and redeploy.
- **HTTP 404:** The data sync endpoints aren't deployed. Run `railway up -d` and wait for deployment.
- **Connection refused / timeout:** Railway site might be sleeping or deploying. Wait and retry.
- **"dumpdata failed":** Check that all models exist (run `python manage.py migrate` first).
- **Large payload (>50MB):** The site has many images in the media library. The 50MB limit is set in `DATA_UPLOAD_MAX_MEMORY_SIZE` in settings.py — increase if needed on both local and remote.
