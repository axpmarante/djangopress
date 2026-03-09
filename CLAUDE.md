# DjangoPress — Project Reference

## What Is This

DjangoPress is a **reusable CMS blueprint** — the Django equivalent of WordPress. It is a GitHub template repository. Each new website project is created from this template, then customized with the client's branding, content, and features.

**Workflow:** Create repo from template → configure `.env` → run migrations → set up SiteSettings (branding, design system, languages) → write project brief → AI generates the entire site → refine via chat or inline editor.

## Core Philosophy

- **Everything lives in the database.** Pages, headers, footers, site settings, design tokens — all DB-driven via the backoffice. No file-based templates for content.
- **LLMs generate the HTML.** The primary workflow is: project briefing + design system → AI generates pages with Tailwind CSS → user refines via AI chat or inline editor.
- **Per-language HTML.** LLM generates clean HTML with real text in the default language. A second LLM call translates the full HTML to each additional language. Each language gets its own complete HTML copy — no template variables, no JSON translation dicts.
- **Clear section markup.** All generated HTML must use `data-section="name"` and `id="name"` on `<section>` tags so individual sections can be referenced, edited, or regenerated independently.
- **Decoupled apps.** Feature apps (news, blog, shop, etc.) are optional plugins bolted onto the core CMS. They don't depend on each other.
- **Multi-language by default.** All content uses JSON fields (`{"pt": "...", "en": "..."}`) — no gettext .po files for user content.

---

## New Project Setup

When starting a new site:

### 1. Create the project directory

```bash
cd /path/to/DjangoSites
mkdir my-project-name && cd my-project-name
git init
```

### 2. Install djangopress

```bash
python -m venv venv
source venv/bin/activate

# For local development (editable install from local repo):
echo 'djangopress @ file:///path/to/djangopress' > requirements.txt
pip install -r requirements.txt

# Create thin config files
mkdir config && touch config/__init__.py
```

Create `config/settings.py`:
```python
from djangopress.settings import *  # noqa: F401,F403
import environ
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
env = environ.Env()
env.read_env(BASE_DIR / '.env')

SECRET_KEY = env('SECRET_KEY', default='django-insecure-change-me')
ENVIRONMENT = env('ENVIRONMENT', default='development')
DEBUG_MODE = env('DEBUG_MODE', default='False') == 'True'
DEBUG = ENVIRONMENT == 'development' or DEBUG_MODE
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

### 9. Project structure

The CMS engine lives in the `djangopress` pip package. A child project directory contains only:

- `config/` — thin settings, urls, wsgi (imports from djangopress)
- `.env` — secrets and API keys
- `requirements.txt` — points to djangopress package
- `manage.py` — Django entry point
- `db.sqlite3` — local database
- Custom decoupled apps (if needed) — e.g. `properties/`, `blog/`

### 10. What you WILL customize

- `.env` — secrets and API keys
- `SiteSettings` in the database — all branding, design, content
- `config/settings.py` — add `INSTALLED_APPS += ['my_app']` for custom apps
- `config/urls.py` — override to register custom app URLs before core catch-all
- Add new **decoupled apps** if the site needs features beyond pages (blog, shop, booking, etc.)

---

## Claude Code Skills

DjangoPress ships with Claude Code skills (`.claude/skills/`) that automate common workflows.

### User-Invocable Skills

| Skill | Usage | What It Does |
|-------|-------|-------------|
| `/new-site` | `/new-site my-project` | Interactive setup wizard for a freshly cloned project. Walks through `.env`, dependencies, migrations, SiteSettings configuration, and validates everything is ready for content generation. **Start here for every new site.** |
| `/add-app` | `/add-app properties` | Scaffolds a full decoupled feature app using the **news app as reference** (`docs/decoupled-app-reference.md`). Creates models (I18nModelMixin, category, layout), public views, template tags, backoffice CRUD, AI endpoints, editor v2 integration, and URL registration. |
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
1. Create project dir, install djangopress pip package
2. /new-site my-project          ← configures everything interactively
3. /generate-content             ← generates pages, header, footer, images
4. /add-app blog                 ← if the site needs extra features

# Option B: Briefing-driven (fastest for new sites)
1. /create-briefing My Client     ← researches client, writes briefing interactively
2. /generate-site briefings/my-client.md  ← everything in one go
3. /deploy-site my-client         ← deploy to Railway

# After making local changes to a deployed site:
/sync-data                        ← push local DB content to Railway
```

---

## Architecture

```
config/          → Django settings, root URLs, WSGI/ASGI, storage backends
core/            → CMS engine: Page, SiteSettings, GlobalSection, SiteImage, ContentVersion
backoffice/      → Admin dashboard: page management, settings, media library, AI tools
editor_v2/       → Inline editor: ES modules, API views, AI chat refinement
ai/              → LLM integration: generation, refinement, chat, bulk analysis, image processing
site_assistant/  → AI chat assistant: manage entire site via natural language (superuser)
news/            → Decoupled blog/news app (optional)
templates/       → base.html + partials (admin toolbar only)
static/          → CSS/JS assets
```

## Key Models (core app)

| Model | Purpose |
|-------|---------|
| `SiteSettings` | Singleton. Branding, contact info, social media (7 platforms), design system (colors, fonts, spacing, buttons), languages, project briefing, design guide, SEO, Open Graph defaults, custom code injection (head/body), `homepage` (FK to Page), `ai_model_config` (JSON for per-task model overrides). Accessed via `SiteSettings.load()`. |
| `Page` | A website page. `title_i18n` / `slug_i18n` (JSON), `html_content_i18n` (per-language Tailwind HTML: `{"pt": "<html>...", "en": "<html>..."}`). |
| `GlobalSection` | Site-wide sections (header, footer). `key` (slug), `html_template_i18n` (per-language Django template HTML: `{"pt": "<html>...", "en": "<html>..."}`). |
| `SiteImage` | Media library. Multi-language titles/alt text (`title_i18n`, `alt_text_i18n`), categories, tags. Supports images and file attachments. |
| `ContentVersion` | Generic revision history for rollback. Uses `content_type` + `object_id` to version any model (Page, NewsPost, etc.). Auto-created before AI edits. |
| `MenuItem` | Navigation menu items with hierarchy support. `label_i18n` (per-language labels), optional `page` FK or custom `url`, `parent` FK for sub-items. |
| `DynamicForm` | DB-driven form definitions. `slug` determines submission URL (`/forms/<slug>/submit/`), `fields_schema` (JSON) for validation/labels, i18n success messages, optional confirmation email. A default `contact` form is seeded on migrate. |
| `FormSubmission` | Form submissions stored as JSON (`data` field). Tracks source page, language, IP, read status. Managed at `/backoffice/forms/`. |

### AI Models (ai app)

| Model | Purpose |
|-------|---------|
| `RefinementSession` | Chat-based refinement conversation. Stores message history (user + assistant). Supports generic FK (`content_type` + `object_id`) for any model, plus backward-compatible `page` FK. |
| `AICallLog` | Audit log for every LLM API call. Tracks action, model, provider, tokens, duration, prompts, response, success/error, and optional `assistant_session` FK linking to the site assistant session that triggered it. Created via `log_ai_call()` helper. Browseable at `/backoffice/ai/logs/`. |

### Site Assistant Models (site_assistant app)

| Model | Purpose |
|-------|---------|
| `AssistantSession` | Chat session for the site assistant. Stores `messages` (JSON list), `active_page` FK, `model_used`, `title` (auto-generated from first message). Sessions are displayed with `#ID` for easy tracking. |

## How Pages Work

1. `PageView` (core/views.py) catches all URLs via `i18n_patterns`
2. Root URL (`/`) defaults to slug `home` — **this slug must be `home` in ALL languages**
3. The current language is detected from the URL prefix (e.g., `/pt/about/` → `pt`)
4. The page's `html_content_i18n[language]` is loaded — each language has its own complete HTML with real text (no template variables)
5. The HTML is rendered as a Django template (for `{% url %}` tags etc.) and injected into `base.html` → `core/page.html`

## How GlobalSections Work (Header/Footer)

- Stored in DB as `GlobalSection` with a unique `key` (e.g. `main-header`, `main-footer`)
- `base.html` loads them via `{% load_global_section 'main-header' fallback_template='partials/header.html' %}`
- Per-language HTML is stored in `html_template_i18n[language]` — each language has its own complete template with real text
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
6. Changes are persisted via `/editor-v2/api/*` endpoints to `Page.html_content_i18n`
7. Language bar in sidebar switches between language versions for preview
8. Applying AI changes auto-translates the modified section/element to other languages

### Editor API Endpoints (all require staff auth):
- `POST /editor-v2/api/update-page-content/` — update page text content in html_content_i18n
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

## Site Assistant

The `site_assistant` app provides a chat-based interface at `/site-assistant/` (superuser only) for managing the entire site via natural language.

### Architecture

Two-phase executor with native Gemini function calling:
- **Phase 1 (Router):** `gemini-lite` classifies user intents and determines which tool categories are needed, or returns a direct response for simple questions.
- **Phase 2 (Executor):** `gemini-flash` runs a native function-calling loop — calls tools, gets results, calls more tools or returns a final text response. Max 8 iterations.

### Key Components

- `site_assistant/models.py` — `AssistantSession` (chat history, active page tracking)
- `site_assistant/services.py` — `AssistantService` (two-phase router → executor flow)
- `site_assistant/router.py` — Intent classification via LLM
- `site_assistant/prompts.py` — System prompts for router and executor
- `site_assistant/tool_declarations.py` — Gemini function declarations per intent category
- `site_assistant/tools/` — Tool implementations:
  - `site_tools.py` — list/create/update/delete pages, menu items, settings, header/footer refinement
  - `page_tools.py` — element styles, attributes, section operations, AI refinement (delegates to `ContentGenerationService`)
  - `news_tools.py` — news post CRUD (if news app is installed)

### API Endpoints

- `GET /site-assistant/` — Chat UI
- `POST /site-assistant/api/chat/` — Send message (supports multipart with reference images)
- `GET /site-assistant/api/sessions/` — List user's recent sessions
- `GET /site-assistant/api/sessions/<id>/` — Load full session with messages

### AI Call Tracking

When the site assistant triggers AI operations (e.g., `refine_section`, `refine_page`), the `AssistantSession` is linked to the resulting `AICallLog` entries via `assistant_session` FK. This allows filtering AI logs by session in `/backoffice/ai/logs/`.

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

When generating HTML for pages or GlobalSections:

1. **Use Tailwind CSS only** — loaded via CDN in base.html
2. **Write real text in the target language** — no template variables for content. Text is embedded directly in the HTML.
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

## Multi-Language Content

Each language gets its own complete HTML copy stored in JSON fields:

- **`Page.html_content_i18n`**: `{"pt": "<section>...texto em PT...</section>", "en": "<section>...text in EN...</section>"}`
- **`GlobalSection.html_template_i18n`**: Same structure for headers/footers
- **`Page.title_i18n`** / **`Page.slug_i18n`**: `{"pt": "Sobre", "en": "About"}`

No `{{ trans.xxx }}` variables — text is embedded directly in each language's HTML. Translation between languages is done by sending the HTML to an LLM (gemini-flash) which returns a fully translated copy.

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
- `/site-assistant/` → AI chat assistant (superuser only)
- `/site-assistant/api/*` → assistant API endpoints
- `/backoffice/ai/logs/` → AI call logs (browseable, filterable by action/model/session)

## AI System

### Available LLM Models

Configured in `ai/utils/llm_config.py`. Supports OpenAI, Anthropic, and Google (Gemini) providers. Models are selected per-task with defaults that can be overridden per-site via `SiteSettings.ai_model_config` (JSON field).

**Per-task defaults:**
| Task | Default Model | Purpose |
|------|---------------|---------|
| `generation` | `gemini-pro` | Page HTML generation |
| `refinement_page` | `gemini-pro` | Full page AI refinement |
| `refinement_section` | `gemini-flash` | Section/element refinement |
| `header_footer` | `gemini-flash` | Header/footer refinement |
| `translation` | `gemini-lite` | HTML translation between languages |
| `metadata` | `gemini-lite` | Title/slug suggestion |
| `image_analysis` | `gemini-flash` | Image prompt analysis |
| `assistant_router` | `gemini-lite` | Site assistant intent classification |
| `assistant_executor` | `gemini-flash` | Site assistant tool execution |

**Available model keys:** `gpt-5`, `gpt-5-mini`, `claude`, `gemini-pro`, `gemini-flash`, `gemini-lite`

### AI API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/ai/api/generate-page/` | POST | Generate a new page (HTML + auto-translate to other languages) |
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

### Generation Flow

1. **Step 1 (HTML):** LLM generates clean HTML with real text in the default language. Plain readable HTML — no template variables.
2. **Step 2 (Translate):** For each additional language, the HTML is sent to gemini-flash which returns a fully translated copy. Each language's HTML is stored in `html_content_i18n[lang]`.
3. **Step 3 (Metadata):** A LLM call suggests `title_i18n` and `slug_i18n` from the brief. The user can override these or leave them blank to use the AI suggestions.

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

> **Full reference:** `docs/decoupled-app-reference.md` — comprehensive guide with code examples based on the **news** app.

Use `/add-app appname` to scaffold automatically, or follow the reference manually. The news app (`news/`) is the canonical template — copy its patterns for any new content type (properties, athletes, products, etc.).

**Key patterns (all documented in the reference):**
1. Models use `I18nModelMixin` from `core/mixins.py` with `_i18n` JSON fields
2. `html_content_i18n` stores per-language HTML (same as Page)
3. Category + Layout models per app
4. Public views render through DB-stored layouts (with fallback HTML)
5. Template tags (`{% latest_items 3 as items %}`) for embedding records in CMS pages
6. Editor v2 works automatically via `content_type_id`/`object_id` in template
7. AI endpoints use `RefinementSession` with generic FK for chat history
8. URLs registered in `i18n_patterns()` **before** `core.urls` (catch-all)
9. App should NOT import from other apps (except `core` for SiteSettings, SiteImage)

## Key Files Reference

### Config
- `config/settings.py` — all Django settings, env loading, storage config
- `config/urls.py` — root URL routing
- `config/storage_backends.py` — GCS domain-based storage backend
- `.env` — secrets (never committed)

### Core CMS
- `core/models.py` — Page, SiteSettings, GlobalSection, SiteImage, ContentVersion, MenuItem, DynamicForm, FormSubmission
- `core/mixins.py` — `I18nModelMixin`: shared mixin for language-aware field resolution (used by all decoupled apps)
- `core/services/global_sections.py` — `GlobalSectionService`: get, list, update, AI-refine GlobalSections
- `core/views.py` — PageView (catches all page URLs), set_language, form_submit
- `core/email.py` — form notification + confirmation email helpers
- `core/context_processors.py` — injects THEME, SITE_NAME, LOGO, MENU_ITEMS, etc. into all templates
- `core/templatetags/section_tags.py` — `load_global_section`, `get_menu_label`, `get_menu_url` filters
- `templates/base.html` — master layout, loads header/footer GlobalSections

### News (Reference App for Decoupled Apps)
- `docs/decoupled-app-reference.md` — **full guide for creating new apps** based on this pattern
- `news/models.py` — NewsPost, NewsCategory, NewsLayout, NewsGalleryImage (canonical model pattern)
- `news/public_views.py` — list/detail/category views with layout rendering + editor v2 support
- `news/urls.py` — public URL patterns (registered before core catch-all)
- `news/views.py` — backoffice CRUD + AI tool views
- `news/templatetags/news_tags.py` — template tags for embedding records in CMS pages
- `news/templates/news/base_news.html` — master template with editor config injection

### AI
- `ai/services.py` — `ContentGenerationService`: generate, refine, process images, analyze page images
- `ai/site_generator.py` — `SiteGenerator` + `BriefingParser`: full site generation pipeline from markdown briefing
- `ai/management/commands/generate_site.py` — `generate_site` management command (non-interactive batch generation)
- `ai/utils/prompts.py` — `PromptTemplates`: all LLM prompt builders
- `ai/utils/llm_config.py` — `LLMBase`: unified LLM client (OpenAI, Anthropic, Google), image generation, `optimize_generated_image()`
- `ai/utils/unsplash.py` — Unsplash API client: `search_photos()`, `download_photo()`, `is_configured()`
- `ai/views.py` — all AI API endpoints
- `ai/models.py` — `RefinementSession`, `AICallLog`, `log_ai_call()`

### Site Assistant
- `site_assistant/models.py` — `AssistantSession`
- `site_assistant/services.py` — `AssistantService` (two-phase router → executor)
- `site_assistant/router.py` — Intent classification
- `site_assistant/prompts.py` — System prompts for router and executor
- `site_assistant/tools/site_tools.py` — Page/menu/settings/header/footer tools
- `site_assistant/tools/page_tools.py` — Element editing, AI refinement tools

### Backoffice
- `backoffice/views.py` — dashboard, page editor, process images, settings, AI tools, AI call logs views
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
- **Server log:** When the dev server is started by DjangoPress Manager, its stdout/stderr is written to `.server.log` in the project root. Read this file to see Django startup output, HTTP request logs, errors, and print statements. Previous sessions are kept as `.server.log.1` and `.server.log.2` (3 sessions total).

## Updating Child Projects

Child projects install `djangopress` as a pip package. To pull updates:

```bash
pip install --upgrade djangopress
# Or if using local editable install, just pull the latest djangopress repo
python manage.py migrate
```

### Migrating from Template Clone to Pip Package

Older child projects were cloned from the template repo and contained the full engine source. To convert:

1. Back up the database: `cp db.sqlite3 db.sqlite3.backup`
2. Remove embedded engine dirs: `rm -rf ai/ backoffice/ core/ editor_v2/ news/ site_assistant/ templates/ static/ scripts/ docs/`
3. Remove standalone engine files: `rm -f Procfile gunicorn.conf.py CLAUDE.md VERSION config/storage_backends.py config/asgi.py`
4. Create thin `config/settings.py` (imports from `djangopress.settings`) and `config/urls.py` (imports from `djangopress.urls`)
5. Update `requirements.txt` to point to djangopress package
6. `pip install -r requirements.txt && python manage.py migrate`
7. Run `python manage.py fix_i18n_html --dry-run` to verify no legacy `{{ trans.xxx }}` vars remain

### Legacy `{{ trans.xxx }}` Architecture (removed in v2.2.0)

The old system stored a single HTML template with `{{ trans.xxx }}` variables + a translations JSON dict. v2.2.0 completed the removal of all traces. Migration 0038 auto-populates `*_i18n` fields from old data. If any site still has `{{ trans.xxx }}` in content, run `python manage.py fix_i18n_html`.

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
# New projects: create dir, pip install djangopress, create thin config files (see New Project Setup above)
python manage.py push_data https://my-site.railway.app             # Push local DB to production
python manage.py push_data https://my-site.railway.app --dry-run   # Preview without sending
python manage.py pull_data https://my-site.railway.app             # Pull remote DB to local
python manage.py pull_data https://my-site.railway.app --dry-run   # Preview without loading
python manage.py bump_version                              # Show current version (from src/djangopress/VERSION)
python manage.py bump_version patch                        # 1.0.0 → 1.0.1 (bug fix)
python manage.py bump_version minor                        # 1.0.1 → 1.1.0 (new feature)
python manage.py bump_version major                        # 1.1.0 → 2.0.0 (breaking change)
railway up -d                                          # Redeploy code to Railway
railway logs -f                                        # Stream Railway deployment logs
railway run python manage.py shell                     # Django shell on Railway Postgres
```
