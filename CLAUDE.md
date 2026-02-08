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

### 1. Create the repo

Go to the template on GitHub → **"Use this template"** → name the new repo → clone it.

### 2. Environment

```bash
cp .env.example .env
```

Edit `.env`:
```
SECRET_KEY=<generate-a-real-key>
ENVIRONMENT=development
GEMINI_API_KEY=<your-gemini-key>        # Required for AI features
# OPENAI_API_KEY=<optional>
# ANTHROPIC_API_KEY=<optional>
```

### 3. Install & migrate

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 8000
```

### 4. Configure the site

Go to `/backoffice/settings/` and fill in:

- **Site Name** (all languages) — e.g. `{"pt": "O Moinho", "en": "The Windmill"}`
- **Site Description** (all languages)
- **Project Briefing** (all languages) — detailed description of the business, services, tone, target audience. This is the most important field — the AI reads it for every generation.
- **Domain** — e.g. `windmillrestaurant-pt` (used as GCS folder name in production)
- **Languages** — enable the languages you need, set default
- **Contact info** — email, phone, address, social media URLs
- **Logos** — upload light and dark background versions
- **Design System** — colors, fonts, buttons, spacing, shadows
- **Design Guide** — freeform markdown with UI patterns and conventions (optional, AI uses this for consistency)

### 5. Generate content

Go to `/backoffice/ai/` → use **Bulk Pages** to describe all pages at once, or **Generate Page** one at a time. Then use **Chat Refine** to iterate on each page conversationally.

### 6. Generate header/footer

Go to `/backoffice/ai/components/` → generate or refine the header and footer GlobalSections.

### 7. What NOT to modify for a standard site

These files rarely need changes for a new site — everything is DB-driven:

- `core/` — the CMS engine (models, views, templatetags) — shared across all sites
- `editor/` — inline editing system — shared
- `ai/` — AI generation/refinement — shared
- `templates/base.html` — master layout — shared
- `config/urls.py` — URL routing — shared

### 8. What you WILL customize

- `.env` — secrets and API keys
- `SiteSettings` in the database — all branding, design, content
- Add new **decoupled apps** if the site needs features beyond pages (blog, shop, booking, etc.)
- `static/` — custom CSS/JS if needed (rare — Tailwind covers most cases)

---

## Architecture

```
config/          → Django settings, root URLs, WSGI/ASGI, storage backends
core/            → CMS engine: Page, SiteSettings, GlobalSection, SiteImage, PageVersion
backoffice/      → Admin dashboard: page management, settings, media library, AI tools
editor/          → Inline editor: frontend JS + API for ?edit=true mode
ai/              → LLM integration: generation, refinement, chat, bulk analysis, image processing
news/            → Decoupled blog/news app (optional)
templates/       → base.html + partials (admin toolbar only)
static/          → CSS/JS assets
```

## Key Models (core app)

| Model | Purpose |
|-------|---------|
| `SiteSettings` | Singleton. Branding, contact info, design system (colors, fonts, spacing, buttons), languages, project briefing, design guide, SEO. Accessed via `SiteSettings.load()`. |
| `Page` | A website page. `title_i18n` / `slug_i18n` (JSON), `html_content` (Tailwind HTML with `{{ trans.field }}`), `content` (JSON translations). |
| `GlobalSection` | Site-wide sections (header, footer). `key` (slug), `html_template` (Django template), `content` (JSON translations). Cached per language. |
| `SiteImage` | Media library. Multi-language titles/alt text (`title_i18n`, `alt_text_i18n`), categories, tags. |
| `PageVersion` | Page revision history for rollback. Auto-created before AI edits. |
| `Contact` | Contact form submissions. |

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

## The Editor App (Inline Editor)

The `editor` app powers the `?edit=true` mode for staff users.

### How it works:
1. Staff visits any page with `?edit=true` in the URL
2. `base.html` loads the editor sidebar, image modal, and JS files
3. `SimpleSelector` — click any element to select it
4. `SimpleSidebar` — Content/Design/Structure/AI tabs for the selected element
5. `SimpleTracker` — tracks all changes, undo/redo, batched save
6. Changes are persisted via `/editor/api/*` endpoints to `Page.html_content` and `Page.content`

### Editor API Endpoints (all require staff auth):
- `POST /editor/api/update-page-content/` — update translation text
- `POST /editor/api/update-page-classes/` — update element CSS classes
- `POST /editor/api/update-page-attribute/` — update element attributes (href, src, etc.)
- `GET /editor/api/media-library/` — browse images with filtering
- `POST /editor/api/images/upload/` — upload new image

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
4. **Use `data-element-id="unique_id"` on editable elements** — for inline editor
5. **Alpine.js is available** (`x-data`, `x-show`, `@click`, etc.) — loaded in base.html
6. **Use context variables** for dynamic data: `{{ SITE_NAME }}`, `{{ LOGO.url }}`, `{{ CONTACT_EMAIL }}`, `{{ SOCIAL_MEDIA.instagram }}`, etc.
7. **For GlobalSections:** use `{% load i18n %}`, `{% url 'core:home' %}`, `{% url 'core:page' slug='...' %}`, `{% url 'set_language' %}`, `{% csrf_token %}`
8. **Responsive by default** — mobile-first with `sm:` / `md:` / `lg:` breakpoints
9. **Page content only** — do NOT include `<html>`, `<head>`, `<body>`, `<header>`, `<nav>`, or `<footer>` tags. Those are handled by `base.html` and GlobalSections.

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
- `/backoffice/page/<id>/edit/` → page editor
- `/backoffice/ai/` → AI content generation hub
- `/backoffice/ai/chat/refine/<page_id>/` → chat-based page refinement
- `/ai/api/*` → AI API endpoints
- `/editor/api/*` → inline editor API (staff only)

## AI System

### Available LLM Models

Configured in `ai/utils/llm_config.py`. Supports OpenAI, Anthropic, and Google (Gemini) providers. Default: `gemini-pro`. Models are selected per-request from the backoffice UI.

### AI API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/ai/api/generate-page/` | POST | Generate a new page (two-step: HTML → templatize + translate) |
| `/ai/api/refine-page-with-html/` | POST | Refine existing page via form |
| `/ai/api/chat-refine-page/` | POST | Chat-based iterative refinement (with session history) |
| `/ai/api/process-page-images/` | POST | Replace image placeholders with library or AI-generated images |
| `/ai/api/save-page/` | POST | Save generated page to DB |
| `/ai/api/refine-header/` | POST | Refine header GlobalSection |
| `/ai/api/refine-footer/` | POST | Refine footer GlobalSection |
| `/ai/api/analyze-bulk-pages/` | POST | Analyze description, extract page structure |
| `/ai/api/generate-design-guide/` | POST | AI-generate a design guide from existing pages |

### Two-Step Generation Flow

1. **Step 1 (HTML):** LLM generates clean HTML with real text in the default language. No `{{ trans.xxx }}` variables — just plain readable HTML.
2. **Step 2 (Templatize + Translate):** A second LLM call extracts all visible text, assigns variable names, and translates to all enabled languages. Python replaces text in HTML with `{{ trans.var }}` variables.

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
- User later clicks "Process Images" to replace placeholders with:
  - An existing image from the media library, OR
  - A newly AI-generated image (via Gemini image generation)

## Adding a New Decoupled App

1. `python manage.py startapp appname`
2. Add to `INSTALLED_APPS` in `config/settings.py`
3. Create models, views, templates within the app
4. Add URL patterns in `appname/urls.py`
5. Include in `config/urls.py`
6. The app should NOT import from other apps (except `core` for shared models like SiteSettings)

## Key Files Reference

### Config
- `config/settings.py` — all Django settings, env loading, storage config
- `config/urls.py` — root URL routing
- `config/storage_backends.py` — GCS domain-based storage backend
- `.env` — secrets (never committed)

### Core CMS
- `core/models.py` — Page, SiteSettings, GlobalSection, SiteImage, PageVersion, Contact
- `core/views.py` — PageView (catches all page URLs), set_language, contact form
- `core/context_processors.py` — injects THEME, SITE_NAME, LOGO, etc. into all templates
- `core/templatetags/section_tags.py` — `load_global_section`, `get_translation` filters
- `templates/base.html` — master layout, loads header/footer GlobalSections

### AI
- `ai/services.py` — `ContentGenerationService`: generate, refine, process images
- `ai/utils/prompts.py` — `PromptTemplates`: all LLM prompt builders
- `ai/utils/llm_config.py` — `LLMBase`: unified LLM client (OpenAI, Anthropic, Google), image generation, `optimize_generated_image()`
- `ai/views.py` — all AI API endpoints
- `ai/models.py` — `RefinementSession`

### Backoffice
- `backoffice/views.py` — dashboard, page editor, settings, AI tools views
- `backoffice/api_views.py` — settings API, media library API, page content API
- `backoffice/templates/backoffice/` — all admin templates

### Editor
- `editor/api_views.py` — inline editor API endpoints
- `editor/static/editor/js/` — selector, sidebar, tracker, image modal JS

## Development Notes

- **Stack:** Django 5.1, Tailwind CSS (CDN), Alpine.js, SQLite (dev) / PostgreSQL (prod)
- **Deployment:** Railway-ready with WhiteNoise for static files, optional GCS for media
- **Email:** Anymail with Mailgun
- **No npm build step** — Tailwind via CDN, no bundler needed
- **Cache in dev:** `LocMemCache` is per-process. Restart server to see GlobalSection changes, or set `DummyCache`.
- **Home page slug must be `home` in all languages** — PageView defaults to this slug for root URL.
- **GCS storage:** When `GS_BUCKET_NAME` is set in `.env`, media files are stored in Google Cloud Storage under a domain-based folder (from `SiteSettings.domain`).

## Git Conventions

- **Do not include `Co-Authored-By` lines in commit messages.**

## Commands

```bash
python manage.py runserver 8000    # Dev server
python manage.py createsuperuser   # Create admin user
python manage.py migrate           # Run migrations
python manage.py shell             # Django shell
```
