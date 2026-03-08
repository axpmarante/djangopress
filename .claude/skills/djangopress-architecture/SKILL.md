---
name: djangopress-architecture
description: DjangoPress CMS architecture knowledge. Auto-loaded when questions arise about how the CMS works, page rendering, template system, translations, GlobalSections, the AI generation pipeline, site assistant, or editor.
user-invocable: false
---

# DjangoPress Architecture Reference

This is a reusable CMS blueprint (the Django equivalent of WordPress). Each site is a clone of the template repo — the engine is shared, content lives in the database.

## Request Flow

```
Browser request
  → DynamicLanguageMiddleware (resolves language from URL prefix or default)
  → i18n_patterns routes to core.urls
  → PageView.get() catches all slugs
  → Looks up Page by slug_i18n[current_language]
  → Root URL (/) defaults to slug "home"
  → Loads page.html_content_i18n[language] — complete HTML with real text
  → Renders as Django template (for {% url %} tags etc.)
  → Result injected into base.html (which loads header/footer GlobalSections)
  → Response
```

## Key Rendering Chain

1. **base.html** — master layout, loads Google Fonts, Tailwind CDN, Alpine.js, Splide, lightbox
2. **GlobalSections** (header/footer) — loaded via `{% load_global_section 'main-header' %}` template tag, per-language Django templates with context vars (`{{ SITE_NAME }}`, `{% url %}`, etc.)
3. **Page content** — `html_content_i18n[language]` rendered as Django template, sandwiched between header and footer. Each language has its own complete HTML with real text embedded.
4. **Context processor** (`core/context_processors.py`) — injects `THEME.*`, `SITE_NAME`, `LOGO`, `CONTACT_*`, `SOCIAL_MEDIA`, `MENU_ITEMS`, `OG_IMAGE`, `DEFAULT_OG_DESCRIPTION_I18N`, `CUSTOM_HEAD_CODE`, `CUSTOM_BODY_CODE` into every template

## Data Architecture

**Everything is DB-driven:**
- `SiteSettings` (singleton) — branding, design system, languages, project briefing, social media, OG defaults, custom code injection, AI model config
- `Page` — website pages with `html_content_i18n` (per-language Tailwind HTML), `title_i18n`, `slug_i18n`
- `GlobalSection` — header/footer with `html_template_i18n` (per-language Django template HTML)
- `SiteImage` — media library with i18n title/alt text, supports images and files
- `PageVersion` — auto-created before AI edits for rollback
- `MenuItem` — navigation items with hierarchy support, i18n labels
- `DynamicForm` — DB-driven form definitions with i18n success messages
- `FormSubmission` — form submissions stored as JSON

**Per-language HTML pattern (v1.0.0+):**
```json
{
  "pt": "<section data-section=\"hero\">...texto em PT...</section>",
  "en": "<section data-section=\"hero\">...text in EN...</section>"
}
```
Each language gets its own complete HTML copy — no template variables for content text. Translation between languages is done by sending HTML to an LLM which returns a fully translated copy.

**GlobalSection templates** use Django template syntax (`{% url %}`, `{% for %}`, `{{ SITE_NAME }}`, etc.) but content text is embedded directly per language. Headers use `{% for item in MENU_ITEMS %}` with `get_menu_label`/`get_menu_url` template filters.

## AI Generation Pipeline

1. **Generate HTML** — LLM writes clean HTML with real text in default language. Every `<section>` must have `data-section="name"` and `id="name"`.
2. **Translate** — For each additional language, gemini-flash translates the full HTML and returns a complete copy. Stored in `html_content_i18n[lang]`.
3. **Metadata** — LLM suggests `title_i18n` and `slug_i18n` from the content.

Key files: `ai/services.py` (ContentGenerationService), `ai/utils/prompts.py` (PromptTemplates), `ai/utils/llm_config.py` (LLMBase)

### AI Call Logging

Every LLM call is logged to `AICallLog` with action, model, tokens, duration, prompts, response, and optional `assistant_session` FK linking to the site assistant session that triggered it.

### GlobalSection Refinement

`refine_global_section()` in `ai/services.py` handles header/footer AI refinement. **Note:** The prompt still uses `{{ trans.xxx }}` format for footer text. Includes truncation validation — rejects refined output if <40% of original length to prevent saving corrupted HTML.

## Site Assistant

The `site_assistant` app provides a chat-based interface for managing the entire site via natural language.

**Architecture:** Two-phase executor with native Gemini function calling.
- Phase 1: Router classifies intents (gemini-lite)
- Phase 2: Executor runs native FC loop with tool declarations (gemini-flash)

**Key files:**
- `site_assistant/models.py` — `AssistantSession` (chat history, active page)
- `site_assistant/services.py` — `AssistantService` (two-phase flow)
- `site_assistant/tools/` — Tool implementations (page_tools, site_tools, etc.)
- `site_assistant/router.py` — Intent classification
- `site_assistant/prompts.py` — System prompts

**URL:** `/site-assistant/` (superuser only)

## Editor (Inline Editor)

The `editor_v2` app powers `?edit=v2` (or `?edit=true`) mode for staff users. ES module architecture with selector, sidebar, tracker, and AI chat. Supports section/element/full-page AI refinement with session history. Language bar for switching between language versions.

**Key files:**
- `editor_v2/api_views.py` — API endpoints (update content, classes, attributes, AI refinement)
- `editor_v2/static/editor_v2/js/editor.js` — ES modules entry point

**Note:** Editor API endpoints are outside `i18n_patterns`, so `_detect_language_from_request()` extracts language from the Referer URL.

## URL Structure

- Non-i18n: `/backoffice/`, `/ai/`, `/editor-v2/`, `/site-assistant/`, `/django-admin/`, `/media/`, `/static/`, `/forms/<slug>/submit/`
- i18n (all inside `i18n_patterns`): `/en/`, `/pt/about/`, `/en/contact/`
- Default language URLs have no prefix (handled by DynamicLanguageMiddleware)
- `core.urls` is a **catch-all** — any app with public URLs must be registered BEFORE it in `i18n_patterns`

## What NOT to Modify in Child Projects

These are the shared CMS engine — modify only in the upstream djangopress repo:
- `core/` — models, views, templatetags, middleware, context processors
- `ai/` — LLM integration, generation, refinement, prompts
- `editor_v2/` — inline editor JS and API
- `backoffice/` — admin dashboard views and templates
- `site_assistant/` — AI chat assistant
- `templates/base.html` — master layout
- `config/` — settings, urls, storage backends

## What to Customize Per Site

- `.env` — secrets, API keys (never committed)
- `SiteSettings` in DB — all branding, design, content via `/backoffice/settings/`
- New decoupled apps — features beyond pages (blog, shop, booking, etc.)
- `static/` — custom CSS/JS (rare)

## Common Gotchas

- **Home page slug must be "home" in ALL languages**
- **Domain must be set BEFORE uploading media** (GCS uses domain as folder name)
- **GlobalSection caching removed** — DB query is trivial, no caching needed
- **Editor v1 removed** — only `editor_v2/` exists. `?edit=true` and `?edit=v2` both load v2.
- **Decoupled app URLs** must be registered in `i18n_patterns` BEFORE `core.urls`
- **Language switcher** uses custom `set_language` view in `core/views.py` (not Django's built-in)
- **Auto-translation on apply** — when user applies an AI change in the editor, only the modified section/element is translated and surgically replaced in other languages' HTML
