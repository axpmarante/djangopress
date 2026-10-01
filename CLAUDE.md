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
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'OPTIONS': {'timeout': 20, 'transaction_mode': 'IMMEDIATE'},
    }
}
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
| `/create-briefing` | `/create-briefing https://client.pt docs/brief.pdf` | Intake: researches the client without asking, writes a complete draft briefing plus a short list of questions with defaults, finalizes from the answers. |
| `/generate-site` | `/generate-site briefings/my-client.md` | Unattended build in the default language: settings, design guide, pages, header, footer, menu, SEO, verified by `check_site` and screenshots. Re-run on a built site for the translation pass. |
| `/mockup-site` | `/mockup-site master` | One master one-page at a time from the final briefing (gpt-image-2.5-sunburst); approve one; render sections one at a time with a check after each; regenerate one; report costs. |
| `/extract-design` | `/extract-design` | Sampled palette, font pair, layout tokens and per-section UI specs from the approved mockups → `docs/design-system.md`, briefing, SiteSettings. |
| `/add-app` | `/add-app properties` | Scaffolds a decoupled feature app (models, views, templates, URLs). |
| `/edit-site` | `/edit-site <what to change>` | Edit site content — pages, sections, header/footer, menu, forms, settings. Claude Code writes the HTML directly. |
| `/update-djangopress` | `/update-djangopress` | Update to latest djangopress version — pip upgrade, migrations, skill refresh, optional Railway redeploy. |
| `/deploy-site-railway` | `/deploy-site-railway my-project` | Deploy to Railway with SQLite + Litestream + GCS. |
| `/sync-data` | `/sync-data push` | Push/pull DB between local and production via Litestream + GCS. |
| `/migrate-sites` | `/migrate-sites` | Batch migration tracker for existing client sites. |
| `/migrate-to-litestream` | `/migrate-to-litestream windmill` | Migrate a deployed site from Postgres to SQLite + Litestream + GCS. |

The `djangopress-architecture` skill is auto-loaded when Claude needs deep architecture reference (models, rendering, AI pipeline, URL patterns, editor internals).

### Typical New Site Flow

```
1. /create-briefing <url and/or document>   ← research, one block of questions, FINAL briefing.md
2. /mockup-site master                      ← one master one-page; approve <n>, or master <note> for another
3. /mockup-site section next                ← one section at a time from the master; ok → next, or a note
4. /extract-design                          ← design system + per-section specs
5. /generate-site briefings/my-client.md    ← unattended build (gated on the master + design system)
6. /edit-site ...                           ← interactive refinement
7. /generate-site briefings/my-client.md    ← translation pass, once design is signed off
8. /deploy-site-railway my-client           ← deploy to Railway (SQLite + Litestream)
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
- **Editor structural verbs** (duplicate / move / insert element or section) are deterministic BeautifulSoup patches in `editor_v2/structure.py`, applied to every language copy. Never add an LLM call to them.
- **Editor operations must create a `kind='checkpoint'` PageVersion before mutating, or they are not undoable.**
- **Backoffice is deliberately short** (2026-10-01): Home (`/backoffice/`) is a site-assistant prompt for superusers and shortcuts for staff; the menu is Pages, Media, Forms, Navigation, Translate, News, Settings. Pages open in the visual editor (`?edit=v2`, `&preview=true` for drafts); "Settings" is the page settings screen. Tools kept in code but out of the menu, reachable by URL: `/site-assistant/`, `/backoffice/overview/` (old dashboard), `/backoffice/blueprint/`, `/backoffice/ai/logs/`, `/backoffice/benchmarks/`, `/backoffice/ai/design-consistency/reports/`. Don't add them back to the menu without asking.
- **Editor component panel** (sliders, galleries) recognises components by structure in `editor_v2/components.py` and `editor_v2/static/editor_v2/js/lib/components.js`. Change the two together and keep `editor_v2/tests/fixtures/components/` passing on both sides (`test_components` + the browser harness `editor_v2/tests/js/components_test.html`).

## Configuration

### Environment Variables

Optional environment variables (`.env`):

- `SECRET_KEY` — Django secret key (required for production)
- `GEMINI_API_KEY` — API key for Google Gemini (required for AI features)
- `CUSTOM_DOMAINS` — comma-separated hosts the site is served on (`example.pt,www.example.pt`). Appended to `ALLOWED_HOSTS` and (as `https://…`) to `CSRF_TRUSTED_ORIGINS`. Set on Railway by the manager's Domain card; no per-site settings edit needed.

---

## Commands

```bash
python manage.py runserver 8000                        # Dev server
python manage.py createsuperuser                       # Create admin user
python manage.py migrate                               # Run migrations
python manage.py shell                                 # Django shell
python manage.py generate_site briefings/my-site.md    # Generate full site from briefing
python manage.py generate_site briefings/my-site.md --dry-run      # Preview plan
python manage.py generate_site briefings/my-site.md --skip-images  # Skip image processing
bash scripts/sync-to-prod.sh                                       # Push local DB to production via GCS
bash scripts/pull-from-prod.sh                                     # Pull production DB to local via GCS
python manage.py migrate_storage_folder                # Copy GCS files from default/ to domain
python manage.py fix_i18n_html --dry-run               # Check for legacy {{ trans.xxx }} vars
python manage.py bump_version minor                    # bump the engine version — see "Releasing a version" below
python manage.py check_site                            # verify site conventions (run inside a child site); exit 1 on failures
python manage.py generate_mockup --prompt-file F --out P [--ref R ...]   # one gpt-image-2.5 render, cost logged
python manage.py crop_mockup SRC OUT --top 0.0 --bottom 0.2              # crop a band of a mockup
python manage.py sample_palette IMG --k 6 --json                         # dominant colors of a mockup
railway up -d                                          # Redeploy to Railway
railway logs -f                                        # Stream Railway logs
```

### Releasing a version

The version lives only in `src/djangopress/VERSION` (`pyproject.toml` reads it). The DjangoPress
Manager compares each site's installed version against this file, so a site is only offered
"Update DjangoPress" (pip upgrade + `migrate`) after a bump. **Bump whenever you add a migration**
— otherwise sites keep running new code against an old schema (e.g. "no column named kind").

1. Pick the part: `patch` for fixes, `minor` for features or any new migration, `major` for breaking changes.
2. Bump. This repo has no `manage.py`; run the command from any child site whose venv has the
   engine installed editable (`pip show djangopress` shows "Editable project location" pointing here):
   ```bash
   cd ../<site> && .venv/bin/python manage.py bump_version minor   # writes ../djangopress/src/djangopress/VERSION
   ```
   Or edit `src/djangopress/VERSION` by hand — it is one line, `X.Y.Z`.
3. Commit here: `chore: bump version to X.Y.Z (<what changed>)`.
4. Merge to `main` and push. Production sites install `djangopress @ git+…@main`, so a bump that
   stays on a feature branch reaches local sites but not Railway — deploying a migrated site then
   breaks production with the same missing-column error.
5. Update each site from the Manager (site page → Update DjangoPress, or bulk), which runs
   `pip install --upgrade [-e] <engine>` and `manage.py migrate`.
