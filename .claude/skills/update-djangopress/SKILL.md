---
name: update-djangopress
description: Update a DjangoPress child project to the latest engine version. Handles pip upgrade, migrations, skill refresh, and optional Railway redeployment.
argument-hint:
allowed-tools: Bash, Read, Edit, Grep, Glob, AskUserQuestion
---

# Update DjangoPress Site

You are updating a DjangoPress child project to the latest engine version.

## Step 1: Check Current Version

```bash
python -c "import djangopress; print(f'Current: {djangopress.__version__}')"
pip show djangopress | grep Location
```

Determine if this is an editable install (local repo) or a published package.

## Step 2: Upgrade the Package

### Editable install (local development)

```bash
# Find the djangopress source repo
DJANGOPRESS_PATH=$(python -c "import djangopress; import os; print(os.path.dirname(os.path.dirname(djangopress.__path__[0])))")
echo "Source: $DJANGOPRESS_PATH"

# Pull latest changes
cd "$DJANGOPRESS_PATH" && git pull && cd -

# Reinstall to pick up changes
pip install -e "$DJANGOPRESS_PATH"
```

### Published package

```bash
pip install --upgrade djangopress
```

### Verify upgrade

```bash
python -c "import djangopress; print(f'Updated to: {djangopress.__version__}')"
```

## Step 3: Run Migrations

```bash
python manage.py migrate
```

If migrations fail, check the error — it may indicate a dependency issue or a model change that requires data migration.

## Step 4: Validate Configuration

```bash
python manage.py check
```

Fix any warnings or errors before proceeding.

### Verify settings load order (GCS)

Ensure the child project's `config/settings.py` loads `.env` BEFORE `from djangopress.settings import *`. If the order is wrong, GCS storage won't activate and images will be saved locally instead of Google Cloud Storage. The correct order is:

```python
env.read_env(BASE_DIR / '.env')           # FIRST: load env vars
from djangopress.settings import *        # THEN: djangopress sees GS_BUCKET_NAME
```

Quick check:
```bash
python manage.py shell -c "from django.conf import settings; print('Storage:', settings.STORAGES['default']['BACKEND'])"
```

If it shows `FileSystemStorage` but GCS is configured in `.env`, the load order is wrong.

## Step 5: Install Optional Dependencies

Check if playwright is installed (used for section screenshot previews in the backoffice page editor and explorer):

```bash
python -c "from playwright.sync_api import sync_playwright; print('Playwright: OK')" 2>/dev/null || echo "Playwright: NOT INSTALLED"
```

If not installed, install it:

```bash
pip install playwright
playwright install chromium
```

Verify:
```bash
python -c "from playwright.sync_api import sync_playwright; print('Playwright: OK')"
```

## Step 6: Check for Content Fixes

```bash
# Check for any legacy {{ trans.xxx }} template variables that need fixing
python manage.py fix_i18n_html --dry-run
```

If issues are found, run without `--dry-run` to fix them:
```bash
python manage.py fix_i18n_html
```

## Step 7: Refresh Skills Symlink

Ensure the skills symlink points to the correct location (new skills may have been added):

```bash
DJANGOPRESS_PATH=$(python -c "import djangopress; import os; print(os.path.dirname(os.path.dirname(djangopress.__path__[0])))")

# Re-create symlink
mkdir -p .claude
ln -sfn "$DJANGOPRESS_PATH/.claude/skills" .claude/skills

# Update CLAUDE.md from latest template if it exists
if [ -f "$DJANGOPRESS_PATH/.claude/child-claude-md-template.md" ]; then
    PROJECT_NAME=$(basename $(pwd))
    sed "s/{{PROJECT_NAME}}/$PROJECT_NAME/g" "$DJANGOPRESS_PATH/.claude/child-claude-md-template.md" > CLAUDE.md
    echo "CLAUDE.md updated"
fi

# Verify skills
ls .claude/skills/
```

## Step 8: Restart Dev Server

If the dev server is running, restart it to pick up the new code:

```bash
# Check if server is running
lsof -i :8000 2>/dev/null | grep LISTEN && echo "Server running on :8000" || echo "No server running"
```

Tell the user to restart the dev server if it's running.

## Step 9: Redeploy to Railway (if deployed)

Check if this project is deployed:

```bash
railway status 2>/dev/null && echo "DEPLOYED" || echo "NOT DEPLOYED"
```

If deployed, ask the user if they want to redeploy:

```
AskUserQuestion:
Question: "This project is deployed on Railway. Do you want to redeploy with the updated engine?"
Options:
- "Redeploy now" — push code and run migrations on Railway
- "Skip" — update locally only, deploy later
```

If redeploying:

```bash
railway up -d
```

Wait for deployment, then run remote migrations:

```bash
# Check deployment status after ~60 seconds
railway logs --lines 10
```

## Summary

Report to the user:
- Previous version → new version
- Migrations applied (if any)
- Content fixes applied (if any)
- Skills refreshed
- Railway redeployment status (if applicable)
