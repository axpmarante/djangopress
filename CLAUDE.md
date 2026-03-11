# DjangoPress — Project Reference

## What Is This

DjangoPress is a **reusable CMS blueprint** — the Django equivalent of WordPress. The CMS engine is installed as the `djangopress` pip package. Each site is a child project with thin config files that import from the package.

**Workflow:** Create project → `pip install djangopress` → configure `.env` → set up SiteSettings → AI generates the entire site → refine via chat or inline editor.

## Core Philosophy

- **Everything lives in the database.** Pages, headers, footers, site settings, design tokens — all DB-driven via the backoffice.
- **LLMs generate the HTML.** Project briefing + design system → AI generates pages with Tailwind CSS → user refines via AI chat or inline editor.
- **Per-language HTML.** Each language gets its own complete HTML copy in `html_content_i18n` / `html_template_i18n` JSON fields. Real text embedded directly — no template variables.
- **Clear section markup.** All generated HTML must use `data-section="name"` and `id="name"` on `<section>` tags.
- **Decoupled apps.** Feature apps (news, blog, shop, etc.) are optional plugins bolted onto the core CMS.

---

## New Project Setup

Use the `/new-site` skill for interactive setup, or manually:

### 1. Create the project directory

```bash
cd /path/to/DjangoSites
mkdir my-project && cd my-project
git init
```

### 2. Install djangopress

```bash
python -m venv .venv && source .venv/bin/activate

# For local development (editable install):
echo 'djangopress @ file:///path/to/djangopress' > requirements.txt
pip install -r requirements.txt

# Create thin config files
mkdir config && touch config/__init__.py
```

Create `config/settings.py`:
```python
from djangopress.settings import *  # noqa: F401,F403
from djangopress.settings import env
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = env('SECRET_KEY', default='django-insecure-change-me')
ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'
DATABASES = {'default': env.db('DATABASE_URL', default=f'sqlite:///{BASE_DIR / "db.sqlite3"}')}
TEMPLATES[0]['DIRS'] = ([BASE_DIR / 'templates'] if (BASE_DIR / 'templates').exists() else []) + TEMPLATES[0]['DIRS']
STATICFILES_DIRS = ([BASE_DIR / 'static'] if (BASE_DIR / 'static').exists() else []) + STATICFILES_DIRS
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_ROOT = BASE_DIR / 'media'
LOCALE_PATHS = [BASE_DIR / 'locale']
ALLOWED_HOSTS += ['.railway.app']
CSRF_TRUSTED_ORIGINS += ['https://*.railway.app']
```

> **Note:** djangopress.settings auto-loads `.env` from the working directory. No need to call `env.read_env()` in child settings. The `env` object is imported to use `env()` and `env.db()` for child-specific overrides.

Create `config/urls.py`:
```python
from djangopress.urls import urlpatterns  # noqa: F401
```

Create `config/wsgi.py`:
```python
import os
from django.core.wsgi import get_wsgi_application
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
application = get_wsgi_application()
```

### 3. Environment & migrate

```bash
cp .env.example .env
# Generate SECRET_KEY:
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
# Edit .env with SECRET_KEY, GEMINI_API_KEY, etc.
python manage.py migrate
python manage.py createsuperuser
```

### 4. Configure & generate

Go to `/backoffice/settings/` to configure branding, languages, design system. Then use `/generate-site` or `/backoffice/ai/` to generate content.

### 5. Project structure

A child project directory contains only:
- `config/` — thin settings, urls, wsgi (imports from djangopress)
- `.env` — secrets and API keys (never committed)
- `requirements.txt` — points to djangopress package
- `manage.py` — Django entry point
- `db.sqlite3` — local database
- `.claude/skills/` — symlinked to djangopress package skills
- Custom decoupled apps (if needed) — e.g. `properties/`, `blog/`

---

## Claude Code Skills

Skills are symlinked from the djangopress package to `.claude/skills/` in each child project. They update automatically when the package is upgraded.

| Skill | Usage | What It Does |
|-------|-------|-------------|
| `/create-briefing` | `/create-briefing O Moinho` | Researches client online, writes a briefing markdown file. |
| `/generate-site` | `/generate-site briefings/my-site.md` | Full setup + generation — env, settings, pages, header/footer, menu, images. Handles fresh and existing projects. |
| `/add-app` | `/add-app properties` | Scaffolds a decoupled feature app (models, views, templates, URLs). |
| `/update-site` | `/update-site` | Update site content — pages, sections, elements, images, settings, header/footer, menu, forms. Auto-loaded for content changes. |
| `/update-djangopress` | `/update-djangopress` | Update to latest djangopress version — pip upgrade, migrations, skill refresh, optional Railway redeploy. |
| `/deploy-site-railway` | `/deploy-site-railway my-project` | Deploy to Railway with Postgres, env vars, data migration. |
| `/sync-data` | `/sync-data push` | Push/pull DB content between local and Railway. |
| `/migrate-sites` | `/migrate-sites` | Batch migration tracker for existing client sites. |

The `djangopress-architecture` skill is auto-loaded when Claude needs deep architecture reference (models, rendering, AI pipeline, URL patterns, editor internals).

### Typical New Site Flow

```
# Full flow
1. /create-briefing My Client     ← researches client, writes briefing
2. /generate-site briefings/my-client.md  ← sets up project + generates everything
3. /add-app blog                  ← if extra features needed
4. /deploy-site-railway my-client ← deploy to Railway

# After making local changes to a deployed site:
/sync-data push                   ← push local DB to Railway
```

---

## Updating Child Projects

```bash
# Local editable install (development):
cd /path/to/djangopress && git pull
cd /path/to/child-project
pip install -e /path/to/djangopress
python manage.py migrate

# Published package (production):
pip install --upgrade djangopress
python manage.py migrate
```

**After upgrading, always:**
1. `python manage.py migrate` — apply schema changes
2. `python manage.py check` — validate configuration
3. Restart dev server
4. If deployed: `railway up -d` to redeploy

---

## Git Conventions

- **Do not include `Co-Authored-By` lines in commit messages.**

## Key Reminders

- **Home page slug must be `home` in ALL languages**
- **Set domain BEFORE uploading media** (GCS uses domain as folder name)
- **Decoupled app URLs** must register BEFORE `core.urls` (catch-all)

## Commands

```bash
python manage.py runserver 8000                        # Dev server
python manage.py createsuperuser                       # Create admin user
python manage.py migrate                               # Run migrations
python manage.py shell                                 # Django shell
python manage.py generate_site briefings/my-site.md    # Generate full site from briefing
python manage.py generate_site briefings/my-site.md --dry-run      # Preview plan
python manage.py generate_site briefings/my-site.md --skip-images  # Skip image processing
python manage.py push_data https://my-site.railway.app             # Push local DB to production
python manage.py pull_data https://my-site.railway.app             # Pull remote DB to local
python manage.py migrate_storage_folder                # Copy GCS files from default/ to domain
python manage.py fix_i18n_html --dry-run               # Check for legacy {{ trans.xxx }} vars
python manage.py bump_version patch                    # 1.0.0 → 1.0.1
python manage.py bump_version minor                    # 1.0.1 → 1.1.0
railway up -d                                          # Redeploy to Railway
railway logs -f                                        # Stream Railway logs
```
