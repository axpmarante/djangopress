---
name: djangopress-html-reference
description: DjangoPress HTML conventions, database structure, editor v2 compatibility rules, GlobalSection patterns, i18n rules, and image/storage conventions. Auto-loaded when writing or modifying HTML for any DjangoPress site.
---

# DjangoPress HTML Reference

## Page HTML Rules

- Each `<section>` MUST have `data-section="name"` and `id="name"`
- Names: unique, descriptive, English (hero, about, services, testimonials, cta, pricing, team, gallery, faq, contact)
- **No `<html>`, `<head>`, `<body>`, `<header>`, `<nav>`, `<footer>` in Page HTML** — these come from `base.html` and GlobalSections. (GlobalSections DO use `<header>`, `<nav>`, `<footer>` — this rule applies only to `Page.html_content_i18n`.)
- Tailwind CSS only (CDN loaded)
- Alpine.js available for interactivity (`x-data`, `x-show`, `@click`)
- Responsive mobile-first: `sm:`, `md:`, `lg:`
- Pre-loaded components: Splide.js (carousel), lightbox.js (gallery)
- Raw HTML with real text in target language — no template variables
- DOM structure must be deterministic (editor v2 uses `nth-child` selectors)

**Editor v2 editable tags** (inline text edit via double-click):
`H1, H2, H3, H4, H5, H6, P, SPAN, A, LI, TD, TH, LABEL, BUTTON, BLOCKQUOTE`

**Splide carousel warning:** The editor v2 filters out Splide-injected elements (cloned slides, arrows, pagination) when computing `nth-child` indices. This means the stored HTML and the live DOM have different `nth-child` counts inside carousels. Structure carousels so that editable text is inside the slide but addressable via its parent `data-section` container — do not rely on `nth-child` addressing within Splide `<li class="splide__slide">` elements.

**Lightbox gallery pattern:** Use `data-lightbox="group-name"` on `<a>` tags wrapping images. All elements sharing the same group name become a navigable gallery:
```html
<a href="/media/site_images/photo.jpg" data-lightbox="gallery" data-alt="Caption">
    <img src="/media/site_images/photo.jpg" alt="Caption" class="w-full h-full object-cover">
</a>
```

## Database Structure

**Page:**
```
html_content_i18n     → {"pt": "<section>...</section>", "en": "..."} — CANONICAL field for page HTML
title_i18n            → {"pt": "Título", "en": "Title"}
slug_i18n             → {"pt": "titulo", "en": "title"}
meta_title_i18n       → {"pt": "...", "en": "..."} (SEO)
meta_description_i18n → {"pt": "...", "en": "..."} (SEO)
og_image              → ImageField (per-page Open Graph image for social sharing)
is_active             → Boolean
sort_order            → Integer
```

Note: Legacy fields `html_content` (TextField) and `content` (JSONField) exist but are NOT used. Always use `html_content_i18n` as the canonical field.

**Safety: create a version before destructive edits:**
```python
from djangopress.core.models import ContentVersion
ContentVersion.create_for(page, change_summary='Before edit-site update')
```

**GlobalSection:**
```
key                   → "main-header", "main-footer" (unique slug)
name                  → Human-readable name (required, e.g. "Main Header")
section_type          → "header", "footer", "announcement", "sidebar", "custom"
html_template_i18n    → {"pt": "{% url ... %}...", "en": "..."} (Django template syntax)
is_active             → Boolean
order                 → Integer (when multiple sections of same type exist)
```

**SiteSettings (singleton) — accessed via `SiteSettings.load()`:**
```
# Identity
site_name_i18n, site_description_i18n, contact_address_i18n → per-language JSON
default_language      → "pt"
enabled_languages     → [{"code": "pt", "name": "Português"}, ...]
project_briefing      → Markdown (project description)
design_guide          → Markdown (UI conventions)

# Contact
contact_email, contact_phone
facebook_url, instagram_url, linkedin_url, youtube_url, twitter_url
whatsapp_number, tiktok_url, pinterest_url

# Design system — colors
primary_color, secondary_color, accent_color → hex strings
background_color, text_color, heading_color → hex strings

# Design system — typography
heading_font, body_font → Google Font names
h1_font, h2_font, h3_font, h4_font, h5_font, h6_font → per-heading font overrides
h1_size, h2_size, h3_size, h4_size, h5_size, h6_size → Tailwind size classes

# Design system — layout & components
container_width_class → e.g. "max-w-7xl"
border_radius_class   → rounded-none, rounded, rounded-lg, rounded-xl, rounded-2xl, rounded-full
spacing_class         → spacing scale
shadow_class          → shadow-none, shadow, shadow-md, shadow-lg, shadow-xl
button_style, button_size, button_radius, button_padding
primary_button_bg, primary_button_text, primary_button_hover
secondary_button_bg, secondary_button_text, secondary_button_hover

# Storage
gcs_folder            → GCS folder name for media storage
```

**MenuItem:**
```
label_i18n      → {"pt": "Início", "en": "Home"}
page            → FK to Page (or None for external URL)
url             → custom URL (if page is None)
parent          → FK to parent MenuItem (submenus)
sort_order      → Integer
is_active       → Boolean
open_in_new_tab → Boolean (for external links, CTAs)
css_class       → CharField (extra CSS classes, e.g. for CTA button styling)
```

**SiteImage:**
```
image          → ImageField (stored in GCS)
image.url      → full GCS URL (https://storage.googleapis.com/<bucket>/<gcs_folder>/site_images/...)
title_i18n     → {"pt": "...", "en": "..."}
alt_text_i18n  → {"pt": "...", "en": "..."}
key            → unique slug identifier
tags           → comma-separated string
description    → AI-generated semantic description (useful for matching images to content)
file           → FileField (for PDFs/documents, separate from image)
file_type      → "image" or "document"
is_active      → Boolean
```

**DynamicForm:**
```
name           → Human-readable name
slug           → URL identifier (submission URL: /forms/<slug>/submit/)
fields_schema  → JSON defining form fields, validation, labels
success_message_i18n → {"pt": "...", "en": "..."} — shown after submission
send_confirmation_email → Boolean
email_subject_i18n → {"pt": "...", "en": "..."}
is_active      → Boolean
```

## GlobalSections (Header/Footer)

GlobalSections use **Django template syntax** (unlike Pages which use raw HTML).

Available template tags and context variables:
```
{% load i18n %}, {% load section_tags %}
{% url 'core:home' %}, {% url 'core:page' slug='about' %}
{% url 'set_language' %}, {% csrf_token %}
{{ SITE_NAME }}, {{ LOGO.url }}, {{ LOGO_DARK_BG.url }}
{{ CONTACT_EMAIL }}, {{ CONTACT_PHONE }}
{{ SOCIAL_MEDIA.instagram }}, {{ SOCIAL_MEDIA.facebook }}, etc.
{{ LANGUAGE_CODE }}, {{ LANGUAGE_CODES }}, {{ DEFAULT_LANGUAGE }}
{{ request.path }}
```

Menu iteration pattern:
```django
{% for item in MENU_ITEMS %}
  {% if item.children.all %}
    <div x-data="{open: false}" @mouseenter="open = true" @mouseleave="open = false">
      <button>{{ item|get_menu_label:LANGUAGE_CODE }}</button>
      <div x-show="open" x-cloak x-transition>
        {% for child in item.children.all %}
          <a href="{{ child|get_menu_url:LANGUAGE_CODE }}">{{ child|get_menu_label:LANGUAGE_CODE }}</a>
        {% endfor %}
      </div>
    </div>
  {% else %}
    <a href="{{ item|get_menu_url:LANGUAGE_CODE }}">{{ item|get_menu_label:LANGUAGE_CODE }}</a>
  {% endif %}
{% endfor %}
```

Language switcher pattern:
```django
<form action="{% url 'set_language' %}" method="post">
  {% csrf_token %}
  <input name="next" type="hidden" value="{{ request.path }}">
  <select name="language" onchange="this.form.submit()">
    {% get_available_languages as LANGUAGES %}
    {% for lang_code, lang_name in LANGUAGES %}
      <option value="{{ lang_code }}" {% if lang_code == LANGUAGE_CODE %}selected{% endif %}>
        {{ lang_code|upper }}
      </option>
    {% endfor %}
  </select>
</form>
```

Footer multilingual links:
```django
{% if LANGUAGE_CODE == 'pt' %}
  <a href="{% url 'core:page' slug='politica-privacidade' %}">Política de Privacidade</a>
{% else %}
  <a href="{% url 'core:page' slug='privacy-policy' %}">Privacy Policy</a>
{% endif %}
```

## Translations

Each language gets its own complete HTML copy. Text is embedded directly — no translation variables.

```python
page.html_content_i18n = {
    "pt": '<section data-section="hero"><h1>Bem-vindo</h1></section>',
    "en": '<section data-section="hero"><h1>Welcome</h1></section>'
}
```

**Critical rule:** DOM structure (tags, nesting, classes, attributes) MUST be identical between languages. Only text content changes. The editor v2 uses `nth-child` selectors — if DOM diverges between languages, inline editing breaks.

## Images & Storage

Images are **always stored in Google Cloud Storage**, even in development. This ensures URLs are consistent between dev and prod — when the DB is replicated via Litestream, image URLs are already correct.

- Storage backend: `DomainBasedStorage` (extends `GoogleCloudStorage`)
- Folder: `SiteSettings.gcs_folder` (fallback: `SiteSettings.domain`)
- URL format: `https://storage.googleapis.com/<bucket>/<gcs_folder>/site_images/<filename>`
- `SiteImage.image.url` returns the full GCS URL
- Prerequisites: `GS_BUCKET_NAME` and `GCS_CREDENTIALS_JSON` in `.env`, `SiteSettings.gcs_folder` configured

Placeholder pattern (before image is resolved):
```html
<img src="https://placehold.co/1200x600?text=Hero+Image"
     data-image-name="hero_image"
     data-image-prompt="Modern restaurant interior, warm lighting"
     alt="Restaurant interior" />
```

Real image (from media library):
```html
<img src="https://storage.googleapis.com/bucket/folder/site_images/restaurant.jpg"
     alt="Restaurant interior" />
```

After resolving placeholders, remove `data-image-name` and `data-image-prompt` attributes.

## Temporary File Pattern

Standard pattern for writing HTML to the database:

```bash
# 1. Claude writes HTML with the Write tool
#    /tmp/dp-page-<id>-<lang>.html

# 2. Load into DB via manage.py shell
python manage.py shell -c "
from djangopress.core.models import Page, ContentVersion
page = Page.objects.get(id=<ID>)
ContentVersion.create_for(page, change_summary='edit-site update')
page.html_content_i18n['<lang>'] = open('/tmp/dp-page-<ID>-<lang>.html').read()
page.save()
print('Saved')
"

# 3. Clean up
rm /tmp/dp-page-*.html
```

Same pattern for GlobalSections using `GlobalSection.html_template_i18n`.
