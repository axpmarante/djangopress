# DjangoPress — Project Reference

## What Is This

DjangoPress is a **reusable CMS blueprint** — the Django equivalent of WordPress. It is the starting template for new website projects at the agency. Copy this repo, configure the design system, feed it a project brief, and let LLMs generate the entire site.

## Core Philosophy

- **Everything lives in the database.** Pages, headers, footers, site settings, design tokens — all DB-driven via the backoffice. No file-based templates for content.
- **LLMs generate the HTML.** The primary workflow is: project briefing + design system → AI generates pages with Tailwind CSS → user refines via AI tools or inline editor.
- **Clear section markup.** All generated HTML must use `data-section="name"` and `id="name"` on `<section>` tags so individual sections can be referenced, edited, or regenerated independently.
- **Decoupled apps.** Feature apps (news, blog, shop, etc.) are optional plugins bolted onto the core CMS. They don't depend on each other.
- **Multi-language by default.** All content uses JSON fields (`{"pt": "...", "en": "..."}`) — no gettext .po files for user content.

## Architecture

```
config/          → Django settings, root URLs, WSGI/ASGI
core/            → The CMS engine: Page, SiteSettings, GlobalSection, SiteImage models
backoffice/      → Admin dashboard: page management, settings, media library, AI tools
editor/         → Inline editor: frontend JS + API endpoints for ?edit=true mode
ai/              → LLM integration: page generation, refinement, bulk analysis
news/            → Decoupled blog/news app (optional)
templates/       → base.html + partials (admin toolbar only)
static/          → CSS/JS assets
```

## Key Models (core app)

| Model | Purpose |
|-------|---------|
| `SiteSettings` | Singleton. Branding, contact info, design system (colors, fonts, spacing, buttons), languages, SEO. Accessed via `SiteSettings.load()`. |
| `Page` | A website page. `title_i18n` / `slug_i18n` (JSON), `html_content` (Tailwind HTML with `{{ trans.field }}`), `content` (JSON translations). |
| `GlobalSection` | Site-wide sections (header, footer). `key` (slug), `html_template` (Django template), `content` (JSON translations). Cached per language. |
| `SiteImage` | Media library. Multi-language titles/alt text, categories, tags. |
| `PageVersion` | Page revision history for rollback. |
| `Contact` | Contact form submissions. |

## How Pages Work

1. `PageView` (core/views.py) catches all URLs via `i18n_patterns`
2. Root URL (`/`) defaults to slug `home` — this slug must be `home` in ALL languages
3. The page's `html_content` is rendered as a Django template with `{{ trans.field }}` variables
4. Translations come from `page.content["translations"][language]`
5. The rendered HTML is injected into `base.html` → `core/page.html`

## How GlobalSections Work (Header/Footer)

- Stored in DB as `GlobalSection` with a unique `key` (e.g. `main-header`, `main-footer`)
- `base.html` loads them via `{% load_global_section 'main-header' fallback_template='partials/header.html' %}`
- They render as Django templates with `{{ trans.field }}` from their own `content` JSON
- Full Django template syntax available: `{% url %}`, `{% csrf_token %}`, `{% if %}`, `{% for %}`, etc.
- **Goal:** Remove fallback templates entirely — everything from DB (WordPress-like)
- **Caching:** Uses `LocMemCache` by default (per-process). Restart server or disable cache in dev to see DB changes instantly.

## The Editor App (Inline Editor)

The `editor` app is the **inline editing system**. It powers the `?edit=true` mode for staff users.

**What it is:** A lightweight frontend editor that lets staff click elements on the live site and tweak text, CSS classes, attributes, and images — then save changes back to the DB.


### How it works:
1. Staff visits any page with `?edit=true` in the URL
2. `base.html` loads the editor sidebar, image modal, and 4 JS files
3. `SimpleSelector` — click any element to select it
4. `SimpleSidebar` — Content/Design/Structure/AI tabs for the selected element
5. `SimpleTracker` — tracks all changes, undo/redo, batched save
6. Changes are persisted via `/editor/api/*` endpoints to `Page.html_content` and `Page.content`

### API Endpoints (all require staff auth):
- `POST /editor/api/update-page-content/` — update translation text
- `POST /editor/api/update-page-classes/` — update element CSS classes
- `POST /editor/api/update-page-attribute/` — update element attributes (href, src, etc.)
- `GET /editor/api/media-library/` — browse images with filtering
- `GET /editor/api/images/` — get all images for the modal
- `POST /editor/api/images/upload/` — upload new image

### Key files:
- `editor/api_views.py` — all API endpoints
- `editor/templates/editor/partials/simple_sidebar.html` — editor sidebar UI
- `editor/templates/editor/partials/image_modal.html` — image picker/uploader
- `editor/static/editor/js/simple-selector.js` — element selection
- `editor/static/editor/js/simple-sidebar.js` — sidebar tabs UI
- `editor/static/editor/js/simple-tracker.js` — change tracking & save
- `editor/static/editor/js/image-modal.js` — image library modal

**Note:** `editor/models.py` and `editor/admin.py` are empty — the editor has no models, it reads/writes `core.Page` and `core.SiteImage`.

## Design System

Configured at `/backoffice/settings/` and available in all templates via `core.context_processors.site_settings`:

- `THEME.colors` — primary, secondary, accent, text, background, heading
- `THEME.typography` — font families, sizes for h1-h6
- `THEME.layout` — container width, border radius, spacing, shadows
- `THEME.buttons` — style, size, colors
- `SITE_NAME_I18N`, `SITE_DESCRIPTION_I18N`, `LOGO`, `CONTACT_EMAIL`, `SOCIAL_MEDIA`, etc.

LLMs should read these values when generating HTML to stay on-brand.

## HTML Generation Rules

When generating `html_content` for pages or GlobalSections:

1. **Use Tailwind CSS only** — loaded via CDN in base.html
2. **Use `{{ trans.field }}` for all text** — never hardcode strings
3. **Every `<section>` must have `data-section="name"` and `id="name"`** — for targeting
4. **Alpine.js is available** (`x-data`, `x-show`, `@click`, etc.) — loaded in base.html
5. **Use context variables** for dynamic data: `{{ SITE_NAME }}`, `{{ LOGO.url }}`, `{{ CONTACT_EMAIL }}`, `{{ SOCIAL_MEDIA.instagram }}`, etc.
6. **For GlobalSections:** use `{% load i18n %}`, `{% url 'core:home' %}`, `{% url 'core:page' slug='...' %}`, `{% url 'set_language' %}`, `{% csrf_token %}`
7. **Responsive by default** — mobile-first with `md:` / `lg:` breakpoints

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
- `/backoffice/ai/` → AI content generation interface
- `/ai/` → AI API endpoints
- `/editor/api/*` → inline editor API (staff only)

## AI Workflow

1. User provides a **project brief** (business name, industry, services, tone)
2. AI reads the **design system** from SiteSettings
3. AI generates full page HTML with `data-section` tags and `{{ trans.field }}` variables
4. AI generates the matching translations JSON
5. Content is saved to `Page.html_content` and `Page.content`
6. User can **refine** individual sections or the whole page via AI tools in backoffice
7. User can **inline edit** on the live site with `?edit=true` (staff only)

## Adding a New Decoupled App

1. `python manage.py startapp appname`
2. Add to `INSTALLED_APPS` in settings
3. Create models, views, templates within the app
4. Add URL patterns in `appname/urls.py`
5. Include in `config/urls.py`
6. The app should NOT import from other apps (except `core` for shared models like SiteSettings)

## Development Notes

- **Stack:** Django 5.1, Tailwind CSS (CDN), Alpine.js, SQLite (dev) / PostgreSQL (prod)
- **Deployment:** Railway-ready with WhiteNoise for static files, optional GCS for media
- **Email:** Anymail with Mailgun
- **No npm build step for the site** — Tailwind via CDN, no bundler needed
- **Cache in dev:** Default `LocMemCache` is per-process. Restart server to see GlobalSection changes, or set `DummyCache` in dev settings.
- **The home page slug must be `home` in all languages** — the view defaults to this slug for the root URL.

## Git Conventions

- **Do not include `Co-Authored-By` lines in commit messages.**

## Commands

```bash
python manage.py runserver 8000    # Dev server
python manage.py createsuperuser   # Create admin user
python manage.py shell             # Django shell (for DB operations)
```
