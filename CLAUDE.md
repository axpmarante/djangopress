# DjangoPress — Project Reference

## What Is This

DjangoPress is a **reusable CMS blueprint** — the Django equivalent of WordPress. It is a GitHub template repository. Each new website project is created from this template, then customized with the client's branding, content, and features.

**Workflow:** Create repo from template → configure `.env` → run migrations → set up SiteSettings (branding, design system, languages) → write project brief → AI generates the entire site → refine via chat or inline editor.

## Core Philosophy

- **Everything lives in the database.** Pages, headers, footers, site settings, design tokens — all DB-driven via the backoffice. No file-based templates for content.
- **LLMs generate the HTML.** The primary workflow is: project briefing + design system → AI generates pages with Tailwind CSS → user refines via AI chat or inline editor.
- **Two-step generation.** Step 1: LLM writes clean HTML with real text in the default language. Step 2: a second LLM call extracts text, assigns `{{ trans.xxx }}` variables, and translates to all languages. Python does the actual HTML replacement.
- **Clear section markup.** All generated HTML must use `data-section="name"` and `id="name"` on `<section>` tags so individual sections can be referenced, edited, or regenerated independently.
- **Decoupled apps.** Feature apps (news, blog, shop, etc.) are optional plugins bolted onto the core CMS. They don't depend on each other.
- **Multi-language by default.** All content uses JSON fields (`{"pt": "...", "en": "..."}`) — no gettext .po files for user content.

---

## New Project Setup

When starting a new site from this template:

### 1. Create the repo and clone

Using the GitHub CLI (recommended):

```bash
cd /path/to/DjangoSites
gh repo create my-project-name --template axpmarante/djangopress --private --clone --description "Project description"
```

Or via GitHub web: go to `github.com/axpmarante/djangopress` → **"Use this template"** → create repo → clone it manually.

### 2. Set up upstream remote

This allows the child project to pull future djangopress engine updates:

```bash
cd my-project-name
git remote add upstream https://github.com/axpmarante/djangopress.git
```

### 3. Environment

```bash
cp .env.example .env
```

Generate a unique secret key and fill in API keys:

```bash
# Generate a SECRET_KEY:
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Edit `.env`:
```
SECRET_KEY=<paste-generated-key>
ENVIRONMENT=development
GEMINI_API_KEY=<your-gemini-key>        # Required for AI features
OPENAI_API_KEY=<optional>
ANTHROPIC_API_KEY=<optional>
UNSPLASH_ACCESS_KEY=<optional>          # Stock photos in Process Images
```

If you have an existing djangopress project, copy the AI provider keys, GCS credentials, and Mailgun config from its `.env`. The `SECRET_KEY` must be unique per project.

### 4. Install & migrate

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 8000
```

### 5. Configure the site

Go to `/backoffice/settings/` and fill in:

- **Site Name** (all languages) — e.g. `{"pt": "O Moinho", "en": "The Windmill"}`
- **Site Description** (all languages)
- **Project Briefing** (plain text) — detailed description of the business, services, tone, target audience. This is the most important field — the AI reads it for every generation.
- **Domain** — e.g. `windmillrestaurant-pt` (used as GCS folder name in production). **Set this BEFORE uploading any media (logos, images).** Changing the domain after uploads requires migrating files with `python manage.py migrate_storage_folder --from default`.
- **Languages** — enable the languages you need, set default
- **Contact info** — email, phone, address, social media URLs
- **Logos** — upload light and dark background versions (after setting the domain)
- **Design System** — colors, fonts, buttons, spacing, shadows
- **Design Guide** — freeform markdown with UI patterns and conventions (optional, AI uses this for consistency)

### 6. Generate content

Go to `/backoffice/ai/` → use **Bulk Pages** to describe all pages at once, or **Generate Page** one at a time. Then use **Chat Refine** to iterate on each page conversationally.

### 7. Generate header/footer

Go to `/backoffice/settings/header/` and `/backoffice/settings/footer/` → use "Quick AI Edit" to generate or refine the header and footer with optional reference images.

### 8. Process images

After generating pages with image placeholders, go to `/backoffice/page/<id>/images/` (or click "Process Images" from the page edit view). Use "AI Suggest Prompts" to auto-fill generation prompts and find matching library images, then "Process Selected" to replace placeholders with real images. Three sources available: AI-generated, media library, and Unsplash stock photos (if `UNSPLASH_ACCESS_KEY` is set in `.env`).

### 9. What NOT to modify for a standard site

These files rarely need changes for a new site — everything is DB-driven:

- `core/` — the CMS engine (models, views, templatetags) — shared across all sites
- `editor_v2/` — inline editing system — shared
- `ai/` — AI generation/refinement — shared
- `templates/base.html` — master layout — shared
- `config/urls.py` — URL routing — shared

### 10. What you WILL customize

- `.env` — secrets and API keys
- `SiteSettings` in the database — all branding, design, content
- Add new **decoupled apps** if the site needs features beyond pages (blog, shop, booking, etc.)
- `static/` — custom CSS/JS if needed (rare — Tailwind covers most cases)

---

## Claude Code Skills

DjangoPress ships with Claude Code skills (`.claude/skills/`) that automate common workflows. These are inherited by every child project cloned from the template.

### User-Invocable Skills

| Skill | Usage | What It Does |
|-------|-------|-------------|
| `/new-site` | `/new-site my-project` | Interactive setup wizard for a freshly cloned project. Walks through `.env`, dependencies, migrations, SiteSettings configuration, and validates everything is ready for content generation. **Start here for every new site.** |
| `/add-app` | `/add-app properties` | Scaffolds a new decoupled feature app with i18n models, views, templates, and URL registration. Handles the `i18n_patterns` registration before the `core.urls` catch-all. |
| `/generate-content` | `/generate-content` | Guides through the full content pipeline: pre-flight check, page planning, bulk/individual generation, chat refinement, header/footer, image processing, design system polish. |
| `/create-briefing` | `/create-briefing O Moinho` | **Interactive briefing generator.** Researches the client online (website, social media, reviews), asks targeted questions to fill gaps, and writes a complete `briefings/<slug>.md` file ready for `/generate-site`. Accepts a client name or URL as argument. |
| `/generate-site` | `/generate-site briefings/my-site.md` | **Full site generation from a markdown briefing.** Reads the briefing, configures SiteSettings, generates all pages, header/footer, menu items, processes images. Claude Code reviews quality and fixes issues. Also available as `python manage.py generate_site` for batch use. |
| `/deploy-site` | `/deploy-site my-project` | **Deploy to Railway.** Creates Railway project + Postgres, sets env vars, deploys code, migrates data from local SQLite to remote Postgres, generates domain. Handles redeployments (code, data, or both). |
| `/sync-data` | `/sync-data` | **Push local DB to production.** Syncs pages, settings, forms, media records, header/footer, and menu items to a deployed Railway site via the `push_data` management command. Handles SYNC_SECRET setup and endpoint verification. |

### Auto-Loaded Skills (Claude uses automatically)

| Skill | Purpose |
|-------|---------|
| `djangopress-architecture` | CMS architecture reference — request flow, data model, AI pipeline, URL structure, common gotchas. Loaded automatically when architectural questions arise. |

### Typical New Site Flow

```
# Option A: Interactive setup + interactive generation (highest quality)
1. Clone template → cd into project
2. /new-site my-project          ← configures everything interactively
3. /generate-content             ← generates pages, header, footer, images
4. /add-app blog                 ← if the site needs extra features

# Option B: Briefing-driven (fastest for new sites)
1. /create-briefing My Client     ← researches client, writes briefing interactively
2. /generate-site briefings/my-client.md  ← everything in one go
3. /deploy-site my-client         ← deploy to Railway

# Option C: New project from scratch
1. ./scripts/new_site.sh my-project briefings/my-site.md
2. cd ../my-project && source venv/bin/activate
3. /generate-site briefings/my-site.md
4. /deploy-site my-project        ← deploy to Railway

# After making local changes to a deployed site:
/sync-data                        ← push local DB content to Railway
```

---

## Architecture

```
config/          → Django settings, root URLs, WSGI/ASGI, storage backends
core/            → CMS engine: Page, SiteSettings, GlobalSection, SiteImage, PageVersion
backoffice/      → Admin dashboard: page management, settings, media library, AI tools
editor_v2/       → Inline editor: ES modules, API views, AI chat refinement
ai/              → LLM integration: generation, refinement, chat, bulk analysis, image processing
news/            → Decoupled blog/news app (optional)
templates/       → base.html + partials (admin toolbar only)
static/          → CSS/JS assets
```

## Key Models (core app)

| Model | Purpose |
|-------|---------|
| `SiteSettings` | Singleton. Branding, contact info, social media (7 platforms), design system (colors, fonts, spacing, buttons), languages, project briefing, design guide, SEO, Open Graph defaults, custom code injection (head/body). Accessed via `SiteSettings.load()`. |
| `Page` | A website page. `title_i18n` / `slug_i18n` (JSON), `html_content` (Tailwind HTML with `{{ trans.field }}`), `content` (JSON translations). |
| `GlobalSection` | Site-wide sections (header, footer). `key` (slug), `html_template` (Django template), `content` (JSON translations). Cached per language. |
| `SiteImage` | Media library. Multi-language titles/alt text (`title_i18n`, `alt_text_i18n`), categories, tags. |
| `PageVersion` | Page revision history for rollback. Auto-created before AI edits. |
| `DynamicForm` | DB-driven form definitions. `slug` determines submission URL (`/forms/<slug>/submit/`), `fields_schema` (JSON) for validation/labels, i18n success messages, optional confirmation email. A default `contact` form is seeded on migrate. |
| `FormSubmission` | Form submissions stored as JSON (`data` field). Tracks source page, language, IP, read status. Managed at `/backoffice/forms/`. |

### AI Models (ai app)

| Model | Purpose |
|-------|---------|
| `RefinementSession` | Chat-based refinement conversation. Stores message history (user + assistant), linked to a Page. |

## How Pages Work

1. `PageView` (core/views.py) catches all URLs via `i18n_patterns`
2. Root URL (`/`) defaults to slug `home` — **this slug must be `home` in ALL languages**
3. The page's `html_content` is rendered as a Django template with `{{ trans.field }}` variables
4. Translations come from `page.content["translations"][language_code]`
5. The rendered HTML is injected into `base.html` → `core/page.html`

## How GlobalSections Work (Header/Footer)

- Stored in DB as `GlobalSection` with a unique `key` (e.g. `main-header`, `main-footer`)
- `base.html` loads them via `{% load_global_section 'main-header' fallback_template='partials/header.html' %}`
- They render as Django templates with `{{ trans.field }}` from their own `content` JSON
- Full Django template syntax available: `{% url %}`, `{% csrf_token %}`, `{% if %}`, `{% for %}`, etc.
- **Caching:** Uses `LocMemCache` by default (per-process). Restart server or set `DummyCache` in dev to see DB changes instantly.

## The Editor (Inline Editor)

The `editor_v2` app powers the `?edit=v2` (or `?edit=true`) mode for staff users.

### How it works:
1. Staff visits any page with `?edit=v2` or `?edit=true` in the URL
2. `base.html` loads the editor panel and ES module JS
3. ES module architecture with selector, sidebar, tracker, and AI chat
4. Supports section/element/full-page AI refinement with session history
5. Version navigation for page rollback
6. Changes are persisted via `/editor-v2/api/*` endpoints to `Page.html_content` and `Page.content`

### Editor API Endpoints (all require staff auth):
- `POST /editor-v2/api/update-page-content/` — update translation text
- `POST /editor-v2/api/update-page-classes/` — update element CSS classes
- `POST /editor-v2/api/update-page-attribute/` — update element attributes (href, src, etc.)
- `POST /editor-v2/api/update-section-video/` — update/remove section background video
- `GET /editor-v2/api/media-library/` — browse images with filtering
- `POST /editor-v2/api/images/upload/` — upload new image
- `POST /editor-v2/api/refine-section/` — AI section refinement (superuser)
- `POST /editor-v2/api/save-ai-section/` — save AI-refined section (superuser)
- `POST /editor-v2/api/refine-element/` — AI element refinement (superuser)
- `POST /editor-v2/api/save-ai-element/` — save AI-refined element (superuser)
- `POST /editor-v2/api/refine-page/` — AI full-page refinement (superuser)
- `POST /editor-v2/api/save-ai-page/` — save AI-refined page (superuser)
- `GET /editor-v2/api/session/<page_id>/` — load chat session history (superuser)
- `GET /editor-v2/api/versions/<page_id>/` — list page versions (superuser)
- `GET /editor-v2/api/versions/<page_id>/<version>/` — get specific version (superuser)

## Design System

Configured at `/backoffice/settings/` and available in all templates via `core.context_processors.site_settings`:

- `THEME.primary_color`, `THEME.secondary_color`, `THEME.accent_color`, `THEME.text_color`, `THEME.background_color`, `THEME.heading_color`
- `THEME.heading_font`, `THEME.body_font`, `THEME.h1_font`/`THEME.h1_size` through `h6`
- `THEME.container_width_class`, `THEME.border_radius_class`, `THEME.spacing_class`, `THEME.shadow_class`
- `THEME.button_style`, `THEME.button_size`, `THEME.button_radius`, `THEME.button_padding`
- `THEME.primary_button_bg`, `THEME.primary_button_text`, `THEME.primary_button_hover`
- `THEME.secondary_button_bg`, `THEME.secondary_button_text`, `THEME.secondary_button_hover`
- `SITE_NAME_I18N`, `SITE_DESCRIPTION_I18N`, `LOGO`, `LOGO_DARK_BG`, `CONTACT_EMAIL`, `CONTACT_PHONE`, `SOCIAL_MEDIA`, etc.

The **Design Guide** (`SiteSettings.design_guide`) is a freeform markdown field injected into every AI prompt. Use it to document UI patterns, component conventions, and style rules that the design system fields can't capture (e.g. "cards always have a subtle shadow and rounded-xl corners", "use gradient backgrounds for hero sections").

## HTML Generation Rules

When generating `html_content` for pages or GlobalSections:

1. **Use Tailwind CSS only** — loaded via CDN in base.html
2. **Use `{{ trans.field }}` for all text** — never hardcode strings
3. **Every `<section>` must have `data-section="name"` and `id="name"`** — for targeting
4. **Alpine.js is available** (`x-data`, `x-show`, `@click`, etc.) — loaded in base.html
5. **Use context variables** for dynamic data: `{{ SITE_NAME }}`, `{{ LOGO.url }}`, `{{ CONTACT_EMAIL }}`, `{{ SOCIAL_MEDIA.instagram }}`, etc.
6. **For GlobalSections:** use `{% load i18n %}`, `{% url 'core:home' %}`, `{% url 'core:page' slug='...' %}`, `{% url 'set_language' %}`, `{% csrf_token %}`
7. **Responsive by default** — mobile-first with `sm:` / `md:` / `lg:` breakpoints
8. **Page content only** — do NOT include `<html>`, `<head>`, `<body>`, `<header>`, `<nav>`, or `<footer>` tags. Those are handled by `base.html` and GlobalSections.
9. **Interactive components are pre-loaded** — Splide.js (carousel), lightbox.js (gallery), Alpine.js (tabs, accordion, modal). Use HTML attributes to configure — no inline `<script>` needed. See prompt reference for patterns.

### Lightbox Gallery Pattern

Use `data-lightbox="group-name"` on `<a>` tags wrapping images. All elements sharing the same group name become a navigable gallery:

```html
<a href="{{ image.url }}" data-lightbox="my-gallery" data-alt="Caption">
    <img src="{{ image.url }}" alt="Caption" class="w-full h-full object-cover">
</a>
<!-- Hidden items are still navigable in lightbox -->
<a href="{{ extra.url }}" data-lightbox="my-gallery" data-alt="Caption" class="hidden"></a>
```

Key points: use `<a href="full-size-url">` for the lightbox source, `data-alt` for caption, different `data-lightbox` group names for independent galleries on the same page.

## Translation JSON Structure

```json
{
  "translations": {
    "en": { "hero_title": "Welcome", "hero_subtitle": "..." },
    "pt": { "hero_title": "Bem-vindo", "hero_subtitle": "..." }
  }
}
```

Both `Page.content` and `GlobalSection.content` use this structure.

## URL Patterns

- `/` → redirects to default language prefix
- `/en/` → home page (slug `home`)
- `/pt/` → home page (slug `home`)
- `/en/about/` → page with EN slug `about`
- `/backoffice/` → admin dashboard (login required)
- `/backoffice/settings/` → design system & site config
- `/backoffice/settings/header/` → header editor
- `/backoffice/settings/footer/` → footer editor
- `/backoffice/page/<id>/edit/` → page editor
- `/backoffice/page/<id>/images/` → process images (full page)
- `/backoffice/ai/` → AI content generation hub
- `/backoffice/ai/generate/page/` → generate a new page
- `/backoffice/ai/bulk/pages/` → bulk page creation
- `/backoffice/ai/chat/refine/<page_id>/` → chat-based page refinement
- `/forms/<slug>/submit/` → form submission endpoint (outside i18n_patterns)
- `/backoffice/forms/` → manage dynamic forms
- `/backoffice/forms/<id>/submissions/` → view form submissions
- `/ai/api/*` → AI API endpoints
- `/editor-v2/api/*` → inline editor API (staff only)

## AI System

### Available LLM Models

Configured in `ai/utils/llm_config.py`. Supports OpenAI, Anthropic, and Google (Gemini) providers. Default: `gemini-pro`. Models are selected per-request from the backoffice UI.

### AI API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/ai/api/generate-page/` | POST | Generate a new page (two-step: HTML → templatize + translate) |
| `/ai/api/refine-page-with-html/` | POST | Refine existing page via form |
| `/ai/api/chat-refine-page/` | POST | Chat-based iterative refinement (with session history) |
| `/ai/api/analyze-page-images/` | POST | AI suggests generation prompts, aspect ratios, and library matches per image |
| `/ai/api/process-page-images/` | POST | Replace image placeholders with library, AI-generated, or Unsplash images |
| `/ai/api/search-unsplash/` | POST | Search Unsplash photos (proxied, staff-only) |
| `/ai/api/save-page/` | POST | Save generated page to DB |
| `/ai/api/refine-header/` | POST | Refine header GlobalSection |
| `/ai/api/refine-footer/` | POST | Refine footer GlobalSection |
| `/ai/api/analyze-bulk-pages/` | POST | Analyze description, extract page structure |
| `/ai/api/generate-design-guide/` | POST | AI-generate a design guide from existing pages |

### Two-Step Generation Flow

1. **Step 1 (HTML):** LLM generates clean HTML with real text in the default language. No `{{ trans.xxx }}` variables — just plain readable HTML.
2. **Step 2 (Templatize + Translate):** Python extracts all visible text via BeautifulSoup and assigns variable names, then a LLM call translates to all enabled languages. Python replaces text in HTML with `{{ trans.var }}` variables.
3. **Step 3 (Metadata):** A third LLM call suggests `title_i18n` and `slug_i18n` from the brief. The user can override these or leave them blank to use the AI suggestions.

This avoids the LLM needing to output valid JSON-wrapped HTML, which was error-prone.

### Chat Refinement

`/backoffice/ai/chat/refine/<page_id>/` provides conversational page editing:
- Messages are stored in `RefinementSession`
- Conversation history is injected into the prompt so the LLM doesn't undo previous changes
- Supports reference image uploads for visual guidance
- "Add image placeholders" checkbox tells the LLM to use `data-image-prompt` metadata on `<img>` tags
- "Process Images" button (Phase 2) lets users replace placeholders with library or AI-generated images

### Image Handling

When "Add image placeholders" is enabled during refinement:
- LLM adds `data-image-prompt="description"` and `data-image-name="slug"` to `<img>` tags
- Uses `https://placehold.co/WxH?text=Label` as placeholder src

**Process Images** (`/backoffice/page/<id>/images/`) is a dedicated full page for managing all images on a page:
- Auto-scans all `<img>` tags on page load (not just placeholder images)
- Each image card has: thumbnail preview, prompt textarea, aspect ratio selector (1:1, 16:9, 4:3, 3:2, 9:16), Generate/Library/Unsplash radio, library dropdown
- **AI Suggest Prompts** button calls `/ai/api/analyze-page-images/` which analyzes page context, project briefing, and media library to auto-fill prompts, aspect ratios, and show up to 3 matching library thumbnails per image
- Clicking a library suggestion thumbnail auto-selects "From Library" mode
- **Process Selected** calls `/ai/api/process-page-images/` to replace images with:
  - An existing image from the media library, OR
  - A newly AI-generated image (via Gemini image generation) at the selected aspect ratio, OR
  - An **Unsplash** stock photo (searched inline, downloaded and saved as a local SiteImage)

### Unsplash Integration

When `UNSPLASH_ACCESS_KEY` is set in `.env`, a third "Unsplash" radio option appears per image in Process Images. The flow:
1. Select "Unsplash" radio → search panel appears with a query pre-filled from the image prompt/alt/name
2. Click "Search" → thumbnails from Unsplash appear (9 results, photographer name on hover)
3. Click a thumbnail to select it
4. "Process Selected" downloads the full image, optimizes it, and saves it as a `SiteImage` with tags `unsplash, Photo by {photographer}`
5. Download tracking is triggered per Unsplash API guidelines

The API key is never exposed to the frontend — searches are proxied via `/ai/api/search-unsplash/`. The client lives in `ai/utils/unsplash.py` and uses `urllib` (no extra dependencies).

## Adding a New Decoupled App

1. `python manage.py startapp appname`
2. Add to `INSTALLED_APPS` in `config/settings.py`
3. Create models, views, templates within the app
4. Add URL patterns in `appname/urls.py`
5. Include in `config/urls.py` — if the app has public-facing URLs, add them inside `i18n_patterns()` **before** `core.urls` (which is a catch-all):
   ```python
   urlpatterns += i18n_patterns(
       path('', include('myapp.urls')),    # <-- before core
       path('', include('core.urls')),
       prefix_default_language=True,
   )
   ```
6. The app should NOT import from other apps (except `core` for shared models like SiteSettings)

## Key Files Reference

### Config
- `config/settings.py` — all Django settings, env loading, storage config
- `config/urls.py` — root URL routing
- `config/storage_backends.py` — GCS domain-based storage backend
- `.env` — secrets (never committed)

### Core CMS
- `core/models.py` — Page, SiteSettings, GlobalSection, SiteImage, PageVersion, DynamicForm, FormSubmission
- `core/views.py` — PageView (catches all page URLs), set_language, form_submit
- `core/email.py` — form notification + confirmation email helpers
- `core/context_processors.py` — injects THEME, SITE_NAME, LOGO, etc. into all templates
- `core/templatetags/section_tags.py` — `load_global_section`, `get_translation` filters
- `templates/base.html` — master layout, loads header/footer GlobalSections

### AI
- `ai/services.py` — `ContentGenerationService`: generate, refine, process images, analyze page images
- `ai/site_generator.py` — `SiteGenerator` + `BriefingParser`: full site generation pipeline from markdown briefing
- `ai/management/commands/generate_site.py` — `generate_site` management command (non-interactive batch generation)
- `ai/utils/prompts.py` — `PromptTemplates`: all LLM prompt builders
- `ai/utils/llm_config.py` — `LLMBase`: unified LLM client (OpenAI, Anthropic, Google), image generation, `optimize_generated_image()`
- `ai/utils/unsplash.py` — Unsplash API client: `search_photos()`, `download_photo()`, `is_configured()`
- `ai/views.py` — all AI API endpoints
- `ai/models.py` — `RefinementSession`

### Backoffice
- `backoffice/views.py` — dashboard, page editor, process images, settings, AI tools views
- `backoffice/api_views.py` — settings API, media library API, page content API
- `backoffice/templates/backoffice/` — all admin templates

### Editor
- `editor_v2/api_views.py` — inline editor API endpoints
- `editor_v2/static/editor_v2/js/` — editor ES modules

## Development Notes

- **Stack:** Django 6.0, Tailwind CSS (CDN), Alpine.js, Python 3.10+
- **Database:** SQLite by default. PostgreSQL via `DATABASE_URL` env var (e.g. `postgres://user:pass@host:5432/dbname`). Railway provides `DATABASE_URL` automatically when you add a Postgres plugin.
- **Dependencies:** `requirements.txt` lists only direct dependencies (12 packages). Transitive deps are resolved by pip. Key packages: Django, gunicorn, whitenoise, django-anymail, django-environ, django-storages, psycopg (PostgreSQL), openai, anthropic, google-genai, Pillow, beautifulsoup4.
- **Deployment:** Railway-ready with WhiteNoise for static files, optional GCS for media
- **Email:** Anymail with Mailgun
- **No npm build step** — Tailwind via CDN, no bundler needed
- **Cache in dev:** `LocMemCache` is per-process. Restart server to see GlobalSection changes, or set `DummyCache`.
- **Home page slug must be `home` in all languages** — PageView defaults to this slug for root URL.
- **GCS storage:** When `GS_BUCKET_NAME` is set in `.env`, media files are stored in Google Cloud Storage under a domain-based folder (from `SiteSettings.domain`).

## Syncing Template Updates to Child Projects

The upstream remote should already be configured (see New Project Setup step 2). To pull updates:

```bash
git fetch upstream
git merge upstream/main
```

The first merge requires `--allow-unrelated-histories` since GitHub template repos don't share git history. Resolve conflicts by taking the upstream version for core engine files (`core/`, `ai/`, `backoffice/`, `editor_v2/`, `config/`, `templates/`). Site-specific content lives in the database and `.env`, so it won't conflict.

## Git Conventions

- **Do not include `Co-Authored-By` lines in commit messages.**

## Commands

```bash
python manage.py runserver 8000                        # Dev server
python manage.py createsuperuser                       # Create admin user
python manage.py migrate                               # Run migrations
python manage.py shell                                 # Django shell
python manage.py migrate_storage_folder                # Copy GCS files from default/ to current domain
python manage.py migrate_storage_folder --from old-dom # Copy from specific folder
python manage.py migrate_storage_folder --dry-run      # Preview without copying
python manage.py generate_site briefings/my-site.md    # Generate full site from briefing
python manage.py generate_site briefings/my-site.md --dry-run      # Preview plan
python manage.py generate_site briefings/my-site.md --skip-images  # Skip image processing
./scripts/new_site.sh my-project                       # Create new project from template
./scripts/new_site.sh my-project briefings/my-site.md  # Create + copy briefing
python manage.py push_data https://my-site.railway.app             # Push local DB to production
python manage.py push_data https://my-site.railway.app --dry-run   # Preview without sending
railway up -d                                          # Redeploy code to Railway
railway logs -f                                        # Stream Railway deployment logs
railway run python manage.py shell                     # Django shell on Railway Postgres
```
