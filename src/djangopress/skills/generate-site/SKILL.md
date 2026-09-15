---
name: generate-site
description: Set up a new DjangoPress site and generate all content from a markdown briefing. Claude Code writes HTML directly following djangopress-html-reference conventions. Handles environment setup, settings, pages, header, footer, menu items.
argument-hint: [briefing-file.md]
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, AskUserQuestion
---

This skill references `djangopress-html-reference` for all HTML conventions and `edit-site` for the operational patterns.

# DjangoPress Site Setup & Generation

You are setting up and/or generating a complete DjangoPress site. The briefing file path (if provided) is: `$ARGUMENTS`

If no argument was provided, check if the project already has content. If it's a fresh project, ask the user for the path to their briefing file or offer to create one from the template at `briefings/TEMPLATE.md`.

## Overview

You will orchestrate the full pipeline, skipping steps that are already done:
1. **Setup** — verify project structure, .env, dependencies, Claude Code integration
2. **Briefing** — parse the briefing to understand the business
3. **Settings** — configure SiteSettings with business details + design system
4. **Pages** — generate pages one by one in the default language only
5. **Menu** — create menu items linking to all pages
6. **Header** — write the header template (default language only)
7. **Footer** — write the footer template (default language only)
8. **Translate** — *deferred by default on first generation* — see the phase for when to run it
9. **Images** — leave placeholders for later processing
10. **Review** — final verification and summary

**Default stopping point on a first generation: end of Phase 7.** Phase 8 (translation) is a separate, later step — see "Core Principle" below.

**Your advantage as Claude Code:** You read the briefing, understand the business context, choose appropriate design values, write HTML directly with full creative control, review quality, and fix issues — no external LLM delegation needed.

---

## Core Principle: Design-first, translate-last (and *much* later)

**Generate and iterate in the default language only. Translation is a separate, later phase — not part of the first generation.**

A multilingual site is iterated heavily during design — sections get rewritten, layouts change, copy gets refined, whole pages get redesigned. Producing N language variants every time multiplies the work, burns tokens on text that will be rewritten anyway, and makes DOM divergence between languages almost inevitable (which breaks the editor v2 nth-child selectors).

**On a first generation, Phase 8 is skipped by default.** Stop after Phase 7 with the site fully in the default language. Translation is run later — once design and content have actually stabilized — by re-invoking this skill (it will detect the existing content and jump straight to Phase 8) or by explicit user request.

Rule of thumb for every i18n field (`html_content_i18n`, `title_i18n`, `slug_i18n`, `label_i18n`, `meta_*_i18n`, `site_description_i18n`, `contact_address_i18n`, `html_template_i18n`, etc.):

- **During Phases 3 → 7**: write only the default language key. Other language keys stay absent.
- **Phase 8 (Translate)**: a *deferred* single pass that fills every other language by mirroring the default-language content with DOM preserved exactly — only text nodes change. Run only when design has stabilized.
- **After Phase 8**: any further iteration on content goes back to default-language-only; re-run the translation pass before the next deploy.

When in doubt about whether design has stabilized, **default to skipping Phase 8** — premature translation always costs more than late translation.

Exception: brand-name fields that don't actually translate (e.g. `site_name_i18n` for "Cuíca") can be written for all languages at once in Phase 3, since the value is identical.

---

## Phase 1: Project Setup

### 1a. Check project status

```bash
# Check for .env
test -f .env && echo "ENV: EXISTS" || echo "ENV: MISSING"

# Check if djangopress is installed
pip show djangopress 2>/dev/null | head -3 || echo "NOT INSTALLED"

# Check if migrations have been run
test -f db.sqlite3 && echo "DB: EXISTS" || echo "DB: NO DB"

# Check existing content
python manage.py shell -c "
from djangopress.core.models import SiteSettings, Page
s = SiteSettings.objects.first()
if s:
    print(f'Site: {s.get_site_name()}')
    print(f'Domain: {s.domain or \"NOT SET\"}')
    print(f'Languages: {s.get_language_codes()}')
    print(f'Pages: {Page.objects.count()}')
    print(f'Briefing: {\"SET\" if s.project_briefing else \"EMPTY\"}')
else:
    print('NO_SETTINGS')
" 2>/dev/null || echo "DJANGO NOT READY"
```

- If djangopress is not installed → tell user to run `pip install -r requirements.txt`
- If settings exist with pages → **warn the user** that existing content may conflict. Ask if they want to continue.
- If everything is set up with content → skip to whichever phase is needed.

### 1b. Set up Claude Code integration

If `.claude/skills` doesn't exist or isn't a symlink:

```bash
# Find the djangopress package location
DJANGOPRESS_PATH=$(python -c "import djangopress; import os; print(os.path.dirname(os.path.dirname(djangopress.__path__[0])))")

# Symlink .claude/skills to the package's skills
mkdir -p .claude
ln -sfn "$DJANGOPRESS_PATH/.claude/skills" .claude/skills

# Generate CLAUDE.md from the child project template if it doesn't exist
if [ ! -f CLAUDE.md ]; then
    PROJECT_NAME=$(basename $(pwd))
    sed "s/{{PROJECT_NAME}}/$PROJECT_NAME/g" "$DJANGOPRESS_PATH/.claude/child-claude-md-template.md" > CLAUDE.md
    echo "Generated CLAUDE.md for $PROJECT_NAME"
fi
```

### 1c. Settings template

djangopress.settings auto-loads `.env` from the working directory, so child settings are simple:

```python
from djangopress.settings import *  # noqa: F401,F403
from djangopress.settings import env
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = env('SECRET_KEY', default='django-insecure-change-me')
ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3', 'OPTIONS': {'timeout': 20, 'transaction_mode': 'IMMEDIATE'}}}
TEMPLATES[0]['DIRS'] = ([BASE_DIR / 'templates'] if (BASE_DIR / 'templates').exists() else []) + TEMPLATES[0]['DIRS']
STATICFILES_DIRS = ([BASE_DIR / 'static'] if (BASE_DIR / 'static').exists() else []) + STATICFILES_DIRS
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_ROOT = BASE_DIR / 'media'
LOCALE_PATHS = [BASE_DIR / 'locale']
ALLOWED_HOSTS += ['.railway.app']
CSRF_TRUSTED_ORIGINS += ['https://*.railway.app']
```

The `env` object is provided by djangopress — use it for child-specific overrides like `SECRET_KEY` and `DATABASES`.

### 1d. Environment configuration

If `.env` doesn't exist:

1. Copy the example: `cp .env.example .env`
2. Generate a unique SECRET_KEY:
   ```bash
   python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
   ```
3. Ask the user which AI providers they have keys for (Gemini, OpenAI, Anthropic)
4. Ask if they have an existing DjangoPress project to copy keys from
5. Write the `.env` file with the provided values

### 1e. GCS Storage Setup (Recommended)

**IMPORTANT:** Configure Google Cloud Storage now so that images generated during content creation are stored in GCS from the start. This avoids needing to manually upload local media files when deploying to Railway (where the filesystem is ephemeral).

If the user has an existing DjangoPress project with GCS configured:

```bash
# Copy GCS config from existing project
grep "^GS_BUCKET_NAME=" ../djangopress/.env >> .env
grep "^GS_PROJECT_ID=" ../djangopress/.env >> .env
grep "^GCS_CREDENTIALS_JSON=" ../djangopress/.env >> .env
```

Verify GCS is working:
```python
python manage.py shell -c "
from django.core.files.storage import default_storage
from djangopress.core.models import SiteSettings
backend = default_storage.__class__.__name__
print(f'Storage: {backend}')
if 'DomainBased' in backend:
    print('GCS: YES — images will be stored in GCS')
    s = SiteSettings.objects.first()
    domain = s.domain if s else None
    if domain:
        print(f'GCS folder: {domain}/')
    else:
        print('WARNING: SiteSettings.domain is NOT SET — files will go to default/ folder')
        print('The domain MUST be set before generating images (Phase 3 handles this)')
else:
    print('GCS: NO — images will be stored locally')
    print('WARNING: Set GS_BUCKET_NAME, GS_PROJECT_ID, and GCS_CREDENTIALS_JSON in .env')
    print('to store images in GCS. Otherwise you will need to upload them manually before deploying.')
"
```

If GCS is not configured, use `AskUserQuestion` to ask the user:
- **"Set up GCS now"** — ask for credentials or copy from an existing project
- **"Continue without GCS"** — images will be stored locally; the deploy skill will handle uploading them later

### 1f. Install dependencies & migrate

If not already done:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt    # requirements.txt points to djangopress package
python manage.py migrate
```

Ask if they want to create a superuser now: `python manage.py createsuperuser`

**IMPORTANT:** Never commit `.env` to git. It's already in `.gitignore`.

---

## Phase 2: Read and Understand the Briefing

Read the briefing file and extract:
- Business name, description, tone
- Languages (default + additional)
- Contact info and social media
- Pages to generate (with descriptions)
- Header/footer instructions
- Design preferences
- Image strategy
- Domain identifier

Summarize what you understood and confirm with the user before proceeding.

If no briefing file exists, gather project details interactively:
1. **Project/Business name** — e.g. "Prestige Real Estate Algarve"
2. **Languages needed** — e.g. Portuguese + English (ask for default language)
3. **Domain identifier** — e.g. `prestige-realestate-pt` (used as GCS folder name)
4. **Business description** — 2-3 sentences about what the business does, target audience, tone
5. **Contact info** — email, phone, address
6. **Social media URLs** — any of: Facebook, Instagram, LinkedIn, Twitter/X, YouTube, TikTok, Pinterest, WhatsApp
7. **Pages to generate** — list of pages with descriptions

---

## Phase 3: Configure SiteSettings

Read the briefing and choose appropriate design system values yourself based on the business type, industry, and design preferences. Then write all settings via `manage.py shell`.

**Reminder (design-first, translate-last):** for i18n fields, write only the default-language key. Phase 8 will fill the rest. Brand-name fields like `site_name_i18n` that are identical across languages are the exception — write them for all enabled languages here.

```python
python manage.py shell -c "
from djangopress.core.models import SiteSettings
settings, _ = SiteSettings.objects.get_or_create(pk=1)

# Domain — SET THIS FIRST before any media uploads
settings.domain = '<domain-identifier>'

# Languages — record the full enabled set even though we'll only write content in <default> for now
settings.enabled_languages = [
    {'code': '<default>', 'name': '<Default Language>'},
    {'code': '<other>', 'name': '<Other Language>'},
]
settings.default_language = '<default>'

# Site name (brand — identical in every language, so write all)
settings.site_name_i18n = {'<default>': '<Site Name>', '<other>': '<Site Name>'}

# Site description (translates — default language only for now)
settings.site_description_i18n = {'<default>': '<Description in default lang>'}

# Project briefing (critical for AI generation)
settings.project_briefing = '''<business description>'''

# Contact info
settings.contact_email = '<email>'
settings.contact_phone = '<phone>'
settings.contact_address_i18n = {'<default>': '<address>'}

# Social media (set whichever apply)
settings.facebook_url = '<url>'
settings.instagram_url = '<url>'
settings.linkedin_url = '<url>'
settings.youtube_url = '<url>'
settings.twitter_url = '<url>'
settings.whatsapp_number = '<+351...>'
settings.tiktok_url = '<url>'
settings.pinterest_url = '<url>'

# Design system — Claude chooses values based on business type and briefing
settings.primary_color = '<hex>'       # Main brand color
settings.secondary_color = '<hex>'     # Supporting color
settings.accent_color = '<hex>'        # Accent/highlight color
settings.background_color = '<hex>'    # Page background (usually #ffffff or #f9fafb)
settings.text_color = '<hex>'          # Body text (usually dark gray)
settings.heading_color = '<hex>'       # Heading text color

settings.heading_font = '<Google Font>'  # e.g. 'Playfair Display', 'Montserrat'
settings.body_font = '<Google Font>'     # e.g. 'Inter', 'Open Sans', 'Lato'

settings.button_style = '<style>'        # 'rounded', 'pill', 'square'
settings.button_radius = '<radius>'      # e.g. '0.375rem', '9999px'
settings.primary_button_bg = '<hex>'
settings.primary_button_text = '<hex>'
settings.primary_button_hover = '<hex>'
settings.secondary_button_bg = '<hex>'
settings.secondary_button_text = '<hex>'
settings.secondary_button_hover = '<hex>'

settings.container_width_class = 'max-w-7xl'   # or 'max-w-6xl', 'max-w-5xl'
settings.border_radius_class = 'rounded-lg'     # or 'rounded-xl', 'rounded-2xl'
settings.shadow_class = 'shadow-md'              # or 'shadow-lg', 'shadow-sm'

settings.save()
print('SiteSettings configured successfully!')
print(f'Domain: {settings.domain}')
print(f'Languages: {settings.get_language_codes()}')
print(f'Default: {settings.get_default_language()}')
"
```

### Verify domain is set (critical for GCS)

After configuring settings, verify the domain was set correctly:

```python
python manage.py shell -c "
from djangopress.core.models import SiteSettings
s = SiteSettings.objects.first()
print(f'Domain: {s.domain}')
assert s.domain, 'ERROR: domain is not set! Set it before generating any images.'
"
```

---

## Phase 4: Generate Pages

**Note:** New sites already come with a Privacy & Cookies Policy page from the template. You do NOT need to create it — just generate the business-specific pages.

Generate each page by writing the HTML directly **in the default language only**. Other languages are deferred to Phase 8. **Home page must be generated FIRST** — it establishes the visual style.

For each page, follow the edit-site temp file pattern:

### 4a. Write an enriched brief (internal planning)

Before writing HTML, plan the page:
- What sections does it need? (hero, features, about, cta, etc.)
- What content fits this business and page type?
- What tone and style match the briefing?
- Each section must have `data-section="name"` and `id="name"` attributes

### 4b. Write HTML to temp file

Write the page HTML in the default language to a single temp file. Follow `djangopress-html-reference` conventions strictly.

```bash
# Write the Write tool to:
# /tmp/dp-page-new-<default-lang>.html
```

The HTML must:
- Use Tailwind CSS classes referencing the design system values from Phase 3
- Include `data-section="<name>"` and `id="<name>"` on every `<section>` tag
- Contain real, meaningful content — not lorem ipsum
- Include image placeholders with `data-image-prompt` and `data-image-name` attributes on `<img>` tags, using `https://placehold.co/WxH?text=Label` as placeholder `src`
- Be written in the default language only — Phase 8 will translate while preserving DOM exactly

### 4c. Save via Django shell

```python
python manage.py shell -c "
from djangopress.core.models import Page

default_lang = '<default>'

with open(f'/tmp/dp-page-new-{default_lang}.html') as f:
    default_html = f.read()

# Home page slug must be 'home' in ALL languages — even though only default is written now,
# Phase 8 will keep the slug as 'home' for every other language too.
page = Page.objects.create(
    title_i18n={default_lang: '<Title>'},
    slug_i18n={default_lang: '<slug>'},
    html_content_i18n={default_lang: default_html},
    meta_title_i18n={default_lang: '<Meta title>'},
    meta_description_i18n={default_lang: '<Meta description>'},
    is_active=True,
    sort_order=0,
)
print(f'Created: {page.default_title} (/{page.default_slug}/) ID={page.id}')
"
```

### 4d. Review and refine

After each page, read the saved HTML back and check:
1. All `<section>` tags have `data-section="name"` and `id="name"` attributes
2. All text is real text embedded directly in the HTML
3. The section structure matches what was requested
4. No empty sections or broken HTML
5. Image placeholders use `data-image-prompt` and `data-image-name`

```python
python manage.py shell -c "
from djangopress.core.models import Page
page = Page.objects.get(id=<ID>)
default_lang = list(page.html_content_i18n.keys())[0] if page.html_content_i18n else 'pt'
print(page.html_content_i18n.get(default_lang, '')[:3000])
"
```

If issues are found, write corrected HTML to temp file and re-save:

```python
python manage.py shell -c "
from djangopress.core.models import Page
page = Page.objects.get(id=<ID>)
with open('/tmp/dp-page-<ID>-<lang>.html') as f:
    page.html_content_i18n['<lang>'] = f.read()
page.save()
print('Refined and saved')
"
```

### 4e. After the home page — set homepage FK

**Critical:** Set `SiteSettings.homepage` to the home page. Without this, the site root URL shows an empty page.

```python
python manage.py shell -c "
from djangopress.core.models import Page, SiteSettings
home = Page.objects.get(slug_i18n__contains='home')
s = SiteSettings.load()
s.homepage = home
s.save()
print(f'Homepage set to: {home.default_title} (ID={home.id})')
"
```

### 4f. After the home page — write design guide

After generating the home page, write a design guide yourself. You already have full context of the HTML patterns, Tailwind classes, section structures, and component styles you used. Save it to `SiteSettings.design_guide` so subsequent pages maintain consistency.

```python
python manage.py shell -c "
from djangopress.core.models import SiteSettings
settings = SiteSettings.objects.first()

settings.design_guide = '''<design guide in markdown>'''

settings.save()
print(f'Design guide saved ({len(settings.design_guide)} chars)')
"
```

The design guide should capture:
- Color usage patterns (which colors for what purpose)
- Typography patterns (heading levels, font weights)
- Component styles (cards, buttons, CTAs, section spacing)
- Section structure conventions (padding, backgrounds, alternating patterns)
- Image placeholder conventions used

Then clean up temp files:

```bash
rm -f /tmp/dp-page-*.html
```

---

## Phase 5: Create Menu Items

After all pages are generated. Menu labels copy from page titles, which are still default-language-only at this point — that's fine, Phase 8 fills the other languages.

```python
python manage.py shell -c "
from djangopress.core.models import Page, MenuItem, SiteSettings

default_lang = SiteSettings.load().get_default_language()

# Clear existing menu items
MenuItem.objects.filter(parent__isnull=True).delete()

# Create menu items for all active pages in sort order
pages = Page.objects.filter(is_active=True).order_by('sort_order', 'id')
for i, page in enumerate(pages):
    MenuItem.objects.create(
        label_i18n={default_lang: page.title_i18n.get(default_lang, page.default_title)},
        page=page,
        sort_order=i * 10,
        is_active=True,
    )
    print(f'Menu: {page.default_title}')

print(f'Created {pages.count()} menu items')
"
```

---

## Phase 6: Refine Header

**New sites already include a default header** (sticky nav, menu items, language switcher, mobile menu). You can skip this phase if the default is acceptable, or refine it to match the site's design.

The header needs menu items to exist first. Write the header HTML template directly using Django template syntax from `djangopress-html-reference`.

### 6a. Write header HTML to temp file

Write the header HTML in the default language to `/tmp/dp-header-<default-lang>.html`. The header template uses Django template syntax with variables like `{{ site_name }}`, `{{ menu_items }}`, `{% for item in menu_items %}`, etc. Refer to `djangopress-html-reference` for the exact template variables and conventions. Phase 8 will translate the static text while preserving the template tags.

### 6b. Save via Django shell

```python
python manage.py shell -c "
from djangopress.core.models import GlobalSection, SiteSettings

default_lang = SiteSettings.load().get_default_language()

section, created = GlobalSection.objects.get_or_create(
    key='main-header',
    defaults={
        'name': 'Main Header',
        'section_type': 'header',
        'html_template_i18n': {},
        'is_active': True,
    }
)

with open(f'/tmp/dp-header-{default_lang}.html') as f:
    section.html_template_i18n = {default_lang: f.read()}

section.save()
print(f'Header generated ({len(section.html_template_i18n[default_lang])} chars in {default_lang})')
"
```

### 6c. Clean up

```bash
rm -f /tmp/dp-header-*.html
```

---

## Phase 7: Refine Footer

**New sites already include a default footer** (3-column: brand, contact, links + privacy policy link). You can skip this phase if the default is acceptable, or refine it to match the site's design.

Same pattern as header — write the footer template HTML directly.

### 7a. Write footer HTML to temp file

Write the footer HTML in the default language to `/tmp/dp-footer-<default-lang>.html`. Include site name, contact info, social media links, copyright notice, and navigation links using Django template syntax from `djangopress-html-reference`.

### 7b. Save via Django shell

```python
python manage.py shell -c "
from djangopress.core.models import GlobalSection, SiteSettings

default_lang = SiteSettings.load().get_default_language()

section, created = GlobalSection.objects.get_or_create(
    key='main-footer',
    defaults={
        'name': 'Main Footer',
        'section_type': 'footer',
        'html_template_i18n': {},
        'is_active': True,
    }
)

with open(f'/tmp/dp-footer-{default_lang}.html') as f:
    section.html_template_i18n = {default_lang: f.read()}

section.save()
print(f'Footer generated ({len(section.html_template_i18n[default_lang])} chars in {default_lang})')
"
```

### 7c. Clean up

```bash
rm -f /tmp/dp-footer-*.html
```

---

## Phase 8: Translation Pass — DEFERRED BY DEFAULT

**Do not run this phase as part of a first generation.** Stop the run after Phase 7 and tell the user the site is ready for design iteration in the default language.

Run Phase 8 only when **all** of the following are true:

- The site already exists with content in the default language (i.e. this is not the first `generate-site` run).
- The user has explicitly indicated design is stable / they're preparing to deploy / they want translations now.
- More than one language is enabled in `SiteSettings.enabled_languages`.

If any of those is false, skip the entire phase. The Phase 10 final review will tell the user how to invoke translation later.

If you're unsure whether to run Phase 8, ask the user explicitly — *or* default to skipping it. Translating prematurely (before design has stabilized) wastes tokens, burns time, and produces output that will be discarded the next time a section is redesigned. **Late translation is always cheaper than premature translation.**

---

The translation pass mirrors every default-language i18n value into each other enabled language while preserving DOM structure exactly. **DOM identity across languages is non-negotiable** — the editor v2 uses `nth-child` selectors and any divergence (extra/missing tags, reordered children, different classes) will break inline editing.

### 8a. List what needs translation

```python
python manage.py shell -c "
from djangopress.core.models import SiteSettings, Page, MenuItem, GlobalSection

s = SiteSettings.load()
default_lang = s.get_default_language()
target_langs = [c for c in s.get_language_codes() if c != default_lang]

print(f'Default: {default_lang}')
print(f'Targets: {target_langs}')
print()
print(f'Pages: {Page.objects.count()}')
print(f'MenuItems: {MenuItem.objects.count()}')
print(f'GlobalSections: {GlobalSection.objects.filter(is_active=True).count()}')
print()
print('SiteSettings i18n fields to translate:')
for f in ['site_description_i18n', 'contact_address_i18n']:
    val = getattr(s, f, {}) or {}
    missing = [lc for lc in target_langs if not val.get(lc)]
    if missing:
        print(f'  {f}: missing {missing}')
"
```

### 8b. Translate each Page

For every Page, translate `title_i18n`, `slug_i18n`, `meta_title_i18n`, `meta_description_i18n`, and `html_content_i18n` from default into each target language.

For `html_content_i18n`: read the default-language HTML, produce a translated copy where **only text nodes change** — every tag, attribute, class, and child ordering must match the default exactly. Image `src`, `data-image-name`, `data-image-prompt`, `href`, IDs, and `data-section` attributes stay identical. The `alt` attribute does translate.

Write the translated HTML to `/tmp/dp-page-<id>-<lang>.html` per language, then save:

```python
python manage.py shell -c "
from djangopress.core.models import Page, SiteSettings

s = SiteSettings.load()
default_lang = s.get_default_language()
target_langs = [c for c in s.get_language_codes() if c != default_lang]

page = Page.objects.get(id=<ID>)
page.create_version(change_summary='Translation pass')

for lang in target_langs:
    with open(f'/tmp/dp-page-{page.id}-{lang}.html') as f:
        page.html_content_i18n[lang] = f.read()
    # title/slug/meta filled in via translated values you write inline:
    # page.title_i18n[lang] = '<translated title>'
    # page.slug_i18n[lang] = '<translated slug>'  (home → 'home' in every language)
    # page.meta_title_i18n[lang] = '<translated meta title>'
    # page.meta_description_i18n[lang] = '<translated meta description>'

page.save()
"
```

After saving each language, verify DOM identity by counting tags. If counts differ, the translation broke structure — re-do that language.

```python
python manage.py shell -c "
from djangopress.core.models import Page
import re

page = Page.objects.get(id=<ID>)
for lang, html in page.html_content_i18n.items():
    tag_count = len(re.findall(r'<[a-z]', html))
    section_count = len(re.findall(r'data-section=', html))
    print(f'{lang}: tags={tag_count} sections={section_count} chars={len(html)}')
"
```

The tag count should match the default-language count within ±1 (small variance from optional self-closing differences is OK; large divergence is a bug).

### 8c. Translate MenuItems and GlobalSections

```python
python manage.py shell -c "
from djangopress.core.models import MenuItem, GlobalSection, SiteSettings

s = SiteSettings.load()
default_lang = s.get_default_language()
target_langs = [c for c in s.get_language_codes() if c != default_lang]

# Menu labels — fill from page.title_i18n which Phase 8b already populated
for item in MenuItem.objects.all():
    if item.page:
        for lang in target_langs:
            item.label_i18n[lang] = item.page.title_i18n.get(lang, item.label_i18n.get(default_lang, ''))
        item.save()

print('Menu labels filled from translated page titles.')
"
```

For each GlobalSection (header, footer), translate the static text while preserving every Django template tag (`{% ... %}`, `{{ ... }}`) literally — never translate variables or filter names.

```python
python manage.py shell -c "
from djangopress.core.models import GlobalSection, SiteSettings

s = SiteSettings.load()
default_lang = s.get_default_language()
target_langs = [c for c in s.get_language_codes() if c != default_lang]

for key in ['main-header', 'main-footer']:
    gs = GlobalSection.objects.get(key=key)
    for lang in target_langs:
        with open(f'/tmp/dp-{key.split(\"-\")[1]}-{lang}.html') as f:
            gs.html_template_i18n[lang] = f.read()
    gs.save()
    print(f'{key}: translated into {target_langs}')
"
```

### 8d. Translate SiteSettings i18n fields

```python
python manage.py shell -c "
from djangopress.core.models import SiteSettings

s = SiteSettings.load()
default_lang = s.get_default_language()
target_langs = [c for c in s.get_language_codes() if c != default_lang]

# Fill in translated values inline — example for two target languages:
# s.site_description_i18n['en'] = '<English description>'
# s.contact_address_i18n['en'] = '<English address>'

s.save()
print('SiteSettings i18n fields translated.')
"
```

### 8e. Final verification

```python
python manage.py shell -c "
from djangopress.core.models import Page, MenuItem, SiteSettings

s = SiteSettings.load()
target_langs = [c for c in s.get_language_codes() if c != s.get_default_language()]

problems = []
for page in Page.objects.filter(is_active=True):
    for lang in target_langs:
        if not page.html_content_i18n.get(lang):
            problems.append(f'Page {page.id} ({page.default_title}): missing {lang}')

for item in MenuItem.objects.all():
    for lang in target_langs:
        if not item.label_i18n.get(lang):
            problems.append(f'MenuItem {item.id}: missing {lang}')

if problems:
    print('TRANSLATION GAPS:')
    for p in problems:
        print(f'  - {p}')
else:
    print('All Pages and MenuItems are translated for every enabled language.')
"
```

### 8f. Clean up

```bash
rm -f /tmp/dp-page-*.html /tmp/dp-header-*.html /tmp/dp-footer-*.html
```

---

## Phase 9: Images

Image placeholders are already embedded in the HTML from Phase 4 (using `data-image-prompt`, `data-image-name`, and `placehold.co` src). These placeholders can be resolved later via:

- The backoffice image management UI
- A dedicated image processing step
- The `/improve-site` skill

The generate-site skill focuses on content structure — getting all pages, header, footer, and menu items in place with quality HTML. Image generation is a separate concern that can be handled afterwards.

---

## Phase 10: Final Review

Verify the contact form exists:

```python
python manage.py shell -c "
from djangopress.core.models import DynamicForm
form = DynamicForm.objects.filter(slug='contact').first()
print(f'Contact form: {\"EXISTS\" if form else \"MISSING\"}')"
```

Start the dev server and provide a summary:

```bash
python manage.py runserver 8000
```

Report to the user:
- List all generated pages with their URLs
- Header and footer status
- Translation status — one of:
  - "Skipped — first generation; site is in `<default-lang>` only. Run translation later via `/generate-site` once design has stabilized." (the default outcome on a first run with multiple enabled languages)
  - "Not applicable — only one language enabled."
  - "Completed — all Pages, MenuItems, GlobalSections, and SiteSettings i18n fields are filled for every enabled language." (only when Phase 8 was actually run)
- Note that images are placeholders (can be processed later)
- Any errors that occurred
- Suggest next steps:
  1. Visit `/backoffice/settings/` to upload logos and configure the design system
  2. **Upload logos AFTER the domain is set** (already set from Phase 3)
  3. Configure SEO & Code settings at `/backoffice/settings/seo/`
  4. Refine pages via the inline editor (`?edit=v2`) or chat refinement — remember to **iterate in the default language only**, even after the first translation pass
  5. **When design has stabilized and you're ready to deploy:** re-invoke `/generate-site` (it will detect existing content and run Phase 8 translation) — do this *once*, late in the process, not during design iteration
  6. Process image placeholders via backoffice or a dedicated step
  7. The project briefing is the most important field for AI quality

---

## Error Handling

- **Page generation fails:** Review the error, fix the HTML, and retry. If the issue is with the Django shell save, check model constraints.
- **Header/footer fails:** Retry once. Fallback templates will render if generation fails.
- **Unexpected errors:** Read the traceback, diagnose the issue, attempt to fix it.

## Non-Interactive Alternative

For batch generation without Claude Code reviewing each step (uses Gemini/GPT pipeline):

```bash
# Dry run first — parse briefing, show plan
python manage.py generate_site briefings/my-site.md --dry-run

# Full generation
python manage.py generate_site briefings/my-site.md

# Fast iteration — skip images
python manage.py generate_site briefings/my-site.md --skip-images

# With Unsplash photos
python manage.py generate_site briefings/my-site.md --image-strategy unsplash_preferred
```

## Important Reminders

- **The CMS engine lives in the `djangopress` pip package** — no engine files in the project directory
- **Domain must be set before uploading media** when using GCS
- **Home page slug must be `home` in ALL languages**
- To update DjangoPress: `pip install --upgrade djangopress && python manage.py migrate`
