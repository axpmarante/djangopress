---
name: new-site
description: Interactive setup wizard for a new DjangoPress site cloned from the template. Guides through environment, database, settings, and initial configuration.
argument-hint: [project-name]
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, AskUserQuestion
---

# New DjangoPress Site Setup

You are setting up a **new website** from the DjangoPress template. This is a child project — the CMS engine (`core/`, `ai/`, `editor/`, `backoffice/`) is shared and should NOT be modified. All customization happens through the database (SiteSettings) and `.env`.

Walk the user through each step interactively. Check what's already done and skip completed steps. Ask questions to gather project details.

## Step 1: Verify Repository Structure

Check if this looks like a freshly cloned DjangoPress template:

```bash
# Check for .env (not .env.example)
test -f .env && echo "EXISTS" || echo "MISSING"

# Check if upstream remote is configured
git remote -v

# Check if migrations have been run
test -f db.sqlite3 && echo "DB EXISTS" || echo "NO DB"
```

If `.env` is missing, proceed to Step 2. If upstream remote is missing, set it up:
```bash
git remote add upstream https://github.com/axpmarante/djangopress.git
```

## Step 2: Environment Configuration

If `.env` doesn't exist:

1. Copy the example: `cp .env.example .env`
2. Generate a unique SECRET_KEY:
   ```bash
   python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
   ```
3. Ask the user which AI providers they have keys for (Gemini, OpenAI, Anthropic)
4. Ask if they have an existing DjangoPress project to copy keys from
5. Write the `.env` file with the provided values

**IMPORTANT:** Never commit `.env` to git. It's already in `.gitignore`.

## Step 3: Install Dependencies & Migrate

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
```

Ask if they want to create a superuser now: `python manage.py createsuperuser`

## Step 4: Gather Project Details

Ask the user for the following information. These will be used to configure SiteSettings:

1. **Project/Business name** — e.g. "Prestige Real Estate Algarve"
2. **Languages needed** — e.g. Portuguese + English (ask for default language)
3. **Domain identifier** — e.g. `prestige-realestate-pt` (used as GCS folder name)
4. **Business description** — 2-3 sentences about what the business does, target audience, tone
5. **Contact info** — email, phone, address
6. **Social media URLs** — any of: Facebook, Instagram, LinkedIn, Twitter/X

## Step 5: Configure SiteSettings via Django Shell

Use the Django shell to set up the initial configuration. This is faster and more reliable than the web UI for the initial setup:

```python
python manage.py shell -c "
from core.models import SiteSettings
settings, _ = SiteSettings.objects.get_or_create(pk=1)

# Domain — SET THIS FIRST before any media uploads
settings.domain = '<domain-identifier>'

# Languages
settings.enabled_languages = [
    {'code': '<default>', 'name': '<Default Language>'},
    {'code': '<other>', 'name': '<Other Language>'},
]
settings.default_language = '<default>'

# Site name (same in all languages — it's a brand name)
settings.site_name_i18n = {'<lang1>': '<Site Name>', '<lang2>': '<Site Name>'}

# Site description (translated)
settings.site_description_i18n = {
    '<lang1>': '<Description in lang1>',
    '<lang2>': '<Description in lang2>',
}

# Project briefing (critical for AI generation)
settings.project_briefing = '''<business description>'''

# Contact info
settings.contact_email = '<email>'
settings.contact_phone = '<phone>'
settings.contact_address_i18n = {
    '<lang1>': '<address>',
    '<lang2>': '<address>',
}

# Social media
settings.facebook_url = '<url>'
settings.instagram_url = '<url>'

settings.save()
print('SiteSettings configured successfully!')
print(f'Domain: {settings.domain}')
print(f'Languages: {settings.get_language_codes()}')
print(f'Default: {settings.get_default_language()}')
"
```

## Step 6: Verify & Next Steps

Start the dev server and verify:
```bash
python manage.py runserver 8000
```

Tell the user:
1. Visit `http://localhost:8000/backoffice/settings/` to upload logos and configure the design system (colors, fonts)
2. **Upload logos AFTER the domain is set** (it's already set from Step 5)
3. Use `/generate-content` skill (or go to `/backoffice/ai/`) to start generating pages
4. The project briefing is the most important field for AI quality — encourage them to make it detailed

## Important Reminders

- **Never modify core engine files** (`core/`, `ai/`, `editor/`, `backoffice/`, `templates/base.html`) for a standard site
- **Domain must be set before uploading media** when using GCS
- **Home page slug must be `home` in ALL languages**
- To pull future DjangoPress updates: `git fetch upstream && git merge upstream/main`
