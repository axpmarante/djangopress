---
name: djangopress-architecture
description: DjangoPress CMS architecture knowledge. Auto-loaded when questions arise about how the CMS works, page rendering, template system, translations, GlobalSections, or the AI generation pipeline.
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
  → Renders page.html_content as a Django template
  → {{ trans.field }} variables resolved from page.content["translations"][lang]
  → Result injected into base.html (which loads header/footer GlobalSections)
  → Response
```

## Key Rendering Chain

1. **base.html** — master layout, loads Google Fonts, Tailwind CDN, Alpine.js, Splide, lightbox
2. **GlobalSections** (header/footer) — loaded via `{% load_global_section 'main-header' %}` template tag, rendered as Django templates with their own `{{ trans.field }}` context
3. **Page content** — the `html_content` field rendered as a Django template, sandwiched between header and footer
4. **Context processor** (`core/context_processors.py`) — injects `THEME.*`, `SITE_NAME`, `LOGO`, `CONTACT_*`, `SOCIAL_MEDIA`, `OG_IMAGE`, `DEFAULT_OG_DESCRIPTION_I18N`, `CUSTOM_HEAD_CODE`, `CUSTOM_BODY_CODE` into every template

## Data Architecture

**Everything is DB-driven:**
- `SiteSettings` (singleton, pk=1) — branding, design system, languages, project briefing, social media, OG defaults, custom code injection
- `Page` — website pages with `html_content` (Tailwind HTML) and `content` (translation JSON)
- `GlobalSection` — header/footer with `html_template` and `content` JSON
- `SiteImage` — media library with i18n title/alt text
- `PageVersion` — auto-created before AI edits for rollback
- `MenuItem` — navigation items with hierarchy support

**Translation pattern (all models):**
```json
{
  "translations": {
    "pt": {"hero_title": "Bem-vindo", "hero_subtitle": "..."},
    "en": {"hero_title": "Welcome", "hero_subtitle": "..."}
  }
}
```

## AI Generation Pipeline

1. **Generate HTML** — LLM writes clean HTML with real text in default language (no template variables)
2. **Templatize + Translate** — second LLM call extracts text, assigns `{{ trans.xxx }}` variable names (snake_case only), translates to all enabled languages
3. **Python replacement** — code replaces text in HTML with `{{ trans.xxx }}` placeholders
4. **Metadata** — third LLM call suggests title_i18n and slug_i18n

Key files: `ai/services.py` (ContentGenerationService), `ai/utils/prompts.py` (PromptTemplates), `ai/utils/llm_config.py` (LLMBase)

## URL Structure

- Non-i18n: `/backoffice/`, `/ai/`, `/editor-v2/`, `/django-admin/`, `/media/`, `/static/`
- i18n (all inside `i18n_patterns`): `/en/`, `/pt/about/`, `/en/contact/`
- Default language URLs have no prefix (handled by DynamicLanguageMiddleware)
- `core.urls` is a **catch-all** — any app with public URLs must be registered BEFORE it in `i18n_patterns`

## What NOT to Modify in Child Projects

These are the shared CMS engine — modify only in the upstream djangopress repo:
- `core/` — models, views, templatetags, middleware, context processors
- `ai/` — LLM integration, generation, refinement, prompts
- `editor_v2/` — inline editor JS and API
- `backoffice/` — admin dashboard views and templates
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
- **LocMemCache is per-process** — restart dev server to see GlobalSection DB changes
- **LLM templatize can corrupt pages** — use `Page.restore_to_version()` to recover
- **Decoupled app URLs** must be registered in `i18n_patterns` BEFORE `core.urls`
