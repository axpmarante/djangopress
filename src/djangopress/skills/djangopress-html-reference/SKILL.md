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

**Image overlay pattern — pointer-events trap:** Any absolutely-positioned element layered on top of an `<img>` will intercept clicks and prevent the editor from selecting the image. This breaks the editor's image-swap flow for the hidden `<img>` underneath. Apply `pointer-events-none` to decorative overlays (gradients, tints, corner accents) so clicks fall through to the image. Keep `pointer-events` enabled on overlays that contain editable children (captions, badges with text):

```html
<div class="group relative aspect-[3/4] overflow-hidden rounded-lg">
    <img src="..." alt="..." class="w-full h-full object-cover">

    <!-- Decorative gradient — NOT editable, must not block clicks to <img> -->
    <div class="absolute inset-0 bg-gradient-to-t from-black to-transparent pointer-events-none"></div>

    <!-- Caption with editable text — KEEP clickable (no pointer-events-none) -->
    <div class="absolute bottom-6 left-6 right-6">
        <h3>Title</h3>
        <p>Caption text</p>
    </div>
</div>
```

Rule of thumb: if an overlay has no editable text/links, add `pointer-events-none`. Otherwise leave it clickable so its children can be reached.

**Decorative & duplicate images — `aria-hidden="true"`:** Mark any `<img>` that is purely decorative or a visual duplicate of another image with `aria-hidden="true"` and an empty `alt=""`. The editor v2's "Images" sidebar tab uses this attribute to filter such images out of the discoverable list, so the user only sees one editable entry per logical image.

The two patterns that require this:

1. **Marquee / scrolling-row duplicates** — when CSS `transform: translateX(-50%)` needs the image set duplicated in the DOM to produce a seamless loop. The duplicate copies are decorative; the originals are the source of truth.

   ```html
   <div class="marquee-track">
     <!-- Originals: editable -->
     <img src="/media/photo-1.jpg" alt="Praia ao pôr do sol" />
     <img src="/media/photo-2.jpg" alt="Terrace ao entardecer" />
     <!-- Duplicates: decorative, NOT editable -->
     <img src="/media/photo-1.jpg" alt="" aria-hidden="true" />
     <img src="/media/photo-2.jpg" alt="" aria-hidden="true" />
   </div>
   ```

2. **Pure decoration** — images used as visual texture (corner accents, ornamental dividers) that have no semantic content the user would want to swap.

Splide-injected clones (`.splide__slide--clone`) are filtered automatically by the editor without needing this attribute.

You can also opt an `<img>` (or any wrapper) out of the editor with `data-editor-skip="true"` if neither `aria-hidden` nor a Splide-clone class fits the situation.

**Splide carousel warning:** The editor v2 filters out Splide-injected elements (cloned slides, arrows, pagination) when computing `nth-child` indices. This means the stored HTML and the live DOM have different `nth-child` counts inside carousels. Structure carousels so that editable text is inside the slide but addressable via its parent `data-section` container — do not rely on `nth-child` addressing within Splide `<li class="splide__slide">` elements.

**Lightbox gallery pattern:** Use `data-lightbox="group-name"` on `<a>` tags wrapping images. All elements sharing the same group name become a navigable gallery:
```html
<a href="/media/site_images/photo.jpg" data-lightbox="gallery" data-alt="Caption">
    <img src="/media/site_images/photo.jpg" alt="Caption" class="w-full h-full object-cover">
</a>
```

**Marquee pattern (`dp-marquee`):** Auto-scrolling row of items (images, logos, cards). The user lists originals; `marquee.js` clones the track contents once at runtime — marking clones with `aria-hidden="true"` + `data-editor-skip="true"` — so `translateX(-50%)` loops seamlessly. The editor filters those clones from selectors and the Images sidebar, so only originals appear and `nth-child` paths stay stable.

```html
<div class="dp-marquee-group space-y-4 md:space-y-6">   <!-- optional wrapper: hovering any row pauses all -->
    <div class="dp-marquee" data-marquee-direction="ltr" data-marquee-speed="70">
        <div class="dp-marquee-track">
            <img src="..." alt="..." class="h-48 md:h-72 w-auto object-cover" />
            <img src="..." alt="..." class="h-48 md:h-72 w-auto object-cover" />
            <!-- list as many originals as you want; clones are added by JS -->
        </div>
    </div>
    <div class="dp-marquee" data-marquee-direction="rtl" data-marquee-speed="60">
        <div class="dp-marquee-track">
            <img src="..." alt="..." class="h-48 md:h-72 w-auto object-cover" />
        </div>
    </div>
</div>
```

Attributes on `.dp-marquee`:
- `data-marquee-direction` — `ltr` (default) or `rtl`
- `data-marquee-speed` — seconds per cycle (default: `60`; bigger number = slower)
- `data-marquee-fade` — `false` disables the edge fade mask (default: enabled, fades to transparent)
- `data-marquee-pause` — `false` disables pause-on-hover (default: pauses)

Notes:
- The fade is a CSS `mask-image`, so it goes to transparent regardless of background colour — no need for matching gradient overlays.
- For a seamless loop the originals should ideally be wide enough to fill the viewport on their own; if the strip is too narrow there will be empty space at the edges of the cycle.
- Sizing the items is up to you (use Tailwind on each `<img>` or child). The track is `display: flex` with a `gap` of 1rem (mobile) / 1.5rem (md+).

**YouTube video background pattern:** To use a YouTube video as a full-bleed hero background (autoplaying, muted, looping, no controls), embed via `<iframe>` with specific URL params + `allow` attribute + a sizing trick that mimics `object-fit: cover`:

```html
<section data-section="hero" id="hero" class="relative min-h-screen overflow-hidden">
    <div class="absolute inset-0 z-0">
        <iframe
            src="https://www.youtube.com/embed/VIDEO_ID?autoplay=1&mute=1&loop=1&playlist=VIDEO_ID&controls=0&modestbranding=1&rel=0&playsinline=1&iv_load_policy=3&disablekb=1&fs=0"
            title="Background video"
            frameborder="0"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
            referrerpolicy="strict-origin-when-cross-origin"
            allowfullscreen
            style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:100vw;height:56.25vw;min-width:177.77vh;min-height:100vh;pointer-events:none;border:0">
        </iframe>
        <div class="absolute inset-0 bg-gradient-to-b from-black/70 via-black/40 to-black"></div>
    </div>
    <div class="relative z-10">...hero text...</div>
</section>
```

**Required URL params** (all critical):
- `autoplay=1&mute=1` — autoplay only works when muted (Chrome/Safari policy)
- `loop=1&playlist=VIDEO_ID` — looping requires `playlist` set to the same video ID (YouTube quirk)
- `controls=0&modestbranding=1&rel=0&iv_load_policy=3&disablekb=1&fs=0` — hide every chrome element
- `playsinline=1` — needed for iOS autoplay

**Required iframe attributes:**
- `allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"` — must include `autoplay` explicitly; modern browsers enforce Permissions-Policy
- `referrerpolicy="strict-origin-when-cross-origin"` — matches YouTube's recommended referrer

**The `100vw / 56.25vw / 177.77vh / 100vh` sizing trick** mimics `object-fit: cover` for iframes:
- `width:100vw; height:56.25vw` — at viewport width, iframe stays 16:9 (56.25 = 9/16 × 100)
- `min-width:177.77vh; min-height:100vh` — at viewport height, iframe stays 16:9 (177.77 = 16/9 × 100)
- Combined: iframe always fully covers the viewport, cropping whichever axis is shorter

**Overlay:** add a gradient overlay above the iframe for text legibility. `pointer-events:none` on the iframe prevents the user from accidentally clicking YouTube links/controls.

**Troubleshooting autoplay:** if the video shows a play button instead of playing, check (in order): (1) `mute=1` present in URL, (2) `allow` includes `autoplay`, (3) browser ad-blocker not blocking the embed, (4) video owner allows embedding (check via `https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=VIDEO_ID&format=json` — a 401 or restricted response means embedding is disabled).

## Rulings Every Site Hits

Verified once, paid for once. Each of these was rediscovered inside a site session before it was written down here. Do not re-derive them.

**1. Internal links carry the language prefix — including the default language.**
Canonical URLs carry the language prefix for every language. The model's `get_absolute_url()` and the middleware tolerate the unprefixed default-language form, so nothing will error if you omit it — but an unprefixed link inside an `/en/` page silently drops the visitor into the default language. Page HTML is raw, with no `{% url %}`, so write the prefix literally:

```html
<!-- wrong -->            <!-- right -->
<a href="/reservas/">     <a href="/pt/reservas/">
<a href="/#menu">         <a href="/pt/#menu">
```

In the English copy of the page the same link is `/en/reservations/`. Header and footer are Django templates and keep using `{% url 'core:page' slug='...' %}`. `manage.py check_site` reports violations under `[links]`.

**2. Version before you mutate, with the model's own method.**
`page.create_version(change_summary='...')` and `section.create_version(change_summary='...')` both exist. Never create `ContentVersion` or `PageVersion` rows by hand. (`ContentVersion`'s snapshot field is `snapshot`, for the record.)

**3. `SiteImage.key` must be ASCII.**
`django.utils.text.slugify` keeps accented letters, so "Caril de Camarão" becomes `dish-caril-de-camarão` and later lookups by the ASCII form miss. Fold first:

```python
import unicodedata
from django.utils.text import slugify
ascii_name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode()
key = f'dish-{slugify(ascii_name)}'
```

**4. Print HTML to PDF with the bundled Chromium, not `require('playwright')`.**
`require('playwright')` does not resolve from a temp directory (the npx cache is not on the module path). Use the binary Playwright already installed:

```bash
CHROME=$(ls -d ~/Library/Caches/ms-playwright/chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium | tail -1)
"$CHROME" --headless --disable-gpu --no-pdf-header-footer --virtual-time-budget=10000 \
  --print-to-pdf=/tmp/out.pdf /tmp/in.html
```

`--virtual-time-budget` lets Google Fonts load before the PDF is written; without it the PDF prints in a fallback font.

**5. Always the site's own venv.**
`.venv/bin/python manage.py ...`. A script under `scripts/` run directly needs the repo root on `sys.path`, so either run it with `PYTHONPATH=.` or put this at the top:

```python
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

**6. No git worktrees for site work.**
`.env` and `.venv` are git-ignored, so a fresh worktree cannot run `manage.py`. Work on a branch in the existing checkout.

**7. Verification is `python manage.py check_site`.**
It encodes every convention on this page as a named check (`sections`, `links`, `images`, `dom-parity`, `home`, `seo`, ...). Run it after every save with `--only <checks relevant to what you changed>` and in full before declaring a site done. Do not write per-site verification scripts.

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

**Versioning: snapshot before every content mutation — REQUIRED.**

`Page` has a built-in `create_version(change_summary=...)` method that writes the current `title_i18n`, `slug_i18n`, `html_content_i18n`, and `is_active` into a `PageVersion` row, then auto-prunes to keep only the most recent 20 snapshots. **Always call it before any script that mutates a Page** so the edit can be reverted:

```python
page = Page.objects.get(id=<ID>)
page.create_version(change_summary='Before: mosaic layout redesign')   # snapshot first
# ...mutate page.html_content_i18n / title_i18n / etc...
page.save()
```

Related helpers on `Page`:
- `page.get_latest_version()` — most recent `PageVersion`
- `page.get_version_count()` — total stored
- `page.restore_to_version(version_number)` — revert (auto-snapshots current state before restoring)

For `GlobalSection` (header/footer), use `ContentVersion` via the generic content-type relation — see the model definition. For `SiteSettings`, versioning is not built in; snapshot `settings.__dict__` manually if the change is risky.

Skip only for trivial reversible edits that don't touch HTML (e.g., toggling `is_active`).

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
homepage              → FK to Page (front page — MUST be set after creating the home page)
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

**New site defaults:** Every new site (created via `new_site.sh`) starts with:
- Privacy & Cookies Policy page (PT + EN, GDPR-compliant, sort_order=999)
- Contact form (slug: `contact`)
- Header GlobalSection (sticky nav, menu, language switcher, mobile menu)
- Footer GlobalSection (3-column: brand, contact, links + privacy link)

These can be refined via `edit-site` but don't need to be created from scratch.

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
- Prerequisites: `GS_BUCKET_NAME` and `GCS_CREDENTIALS_JSON` in `.env`
- `SiteSettings.gcs_folder` is set automatically by `new_site.sh` to the project slug (e.g., `demo-restaurant`). This MUST be set before any image uploads — otherwise images go to a `default/` folder
- `SiteSettings.domain` is NOT required at creation time — it can be set later when deploying

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
from djangopress.core.models import Page
page = Page.objects.get(id=<ID>)
page.create_version(change_summary='edit-site update')
page.html_content_i18n['<lang>'] = open('/tmp/dp-page-<ID>-<lang>.html').read()
page.save()
print('Saved')
"

# 3. Clean up
rm /tmp/dp-page-*.html
```

Same pattern for GlobalSections using `GlobalSection.html_template_i18n`.

After every save, verify what you touched:

```bash
python manage.py check_site --only sections,images,anchors,links,forbidden-tag   # after a page save
python manage.py check_site --only global-section                                # after a header/footer save
python manage.py check_site                                                      # before saying a site is done
```
