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
4. **Pages** — generate pages one by one, reviewing quality after each
5. **Menu** — create menu items linking to all pages
6. **Header & Footer** — write HTML templates directly
7. **Images** — leave placeholders for later processing
8. **Review** — final verification and summary

**Your advantage as Claude Code:** You read the briefing, understand the business context, choose appropriate design values, write HTML directly with full creative control, review quality, and fix issues — no external LLM delegation needed.

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

```python
python manage.py shell -c "
from djangopress.core.models import SiteSettings
settings, _ = SiteSettings.objects.get_or_create(pk=1)

# Domain — SET THIS FIRST before any media uploads
settings.domain = '<domain-identifier>'

# Languages
settings.enabled_languages = [
    {'code': '<default>', 'name': '<Default Language>'},
    {'code': '<other>', 'name': '<Other Language>'},
]
settings.default_language = '<default>'

# Site name (same in all languages — it's a brand name)
settings.site_name_i18n = {'<lang1>': '<Site Name>', '<lang2>': '<Site Name>'}

# Site description (translated)
settings.site_description_i18n = {
    '<lang1>': '<Description in lang1>',
    '<lang2>': '<Description in lang2>',
}

# Project briefing (critical for AI generation)
settings.project_briefing = '''<business description>'''

# Contact info
settings.contact_email = '<email>'
settings.contact_phone = '<phone>'
settings.contact_address_i18n = {
    '<lang1>': '<address>',
    '<lang2>': '<address>',
}

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

Generate each page by writing the HTML directly. **Home page must be generated FIRST** — it establishes the visual style.

For each page, follow the edit-site temp file pattern:

### 4a. Write an enriched brief (internal planning)

Before writing HTML, plan the page:
- What sections does it need? (hero, features, about, cta, etc.)
- What content fits this business and page type?
- What tone and style match the briefing?
- Each section must have `data-section="name"` and `id="name"` attributes

### 4b. Write HTML to temp file

Write the page HTML for each language to a temp file. Follow `djangopress-html-reference` conventions strictly.

```bash
# Write HTML for each language using the Write tool
# File: /tmp/dp-page-new-<lang>.html
```

The HTML must:
- Use Tailwind CSS classes referencing the design system values from Phase 3
- Include `data-section="<name>"` and `id="<name>"` on every `<section>` tag
- Contain real, meaningful content — not lorem ipsum
- Include image placeholders with `data-image-prompt` and `data-image-name` attributes on `<img>` tags, using `https://placehold.co/WxH?text=Label` as placeholder `src`
- Be fully translated for each language variant

### 4c. Save via Django shell

```python
python manage.py shell -c "
from djangopress.core.models import Page

# Read HTML from temp files
html_content = {}
for lang in ['<lang1>', '<lang2>']:
    with open(f'/tmp/dp-page-new-{lang}.html') as f:
        html_content[lang] = f.read()

# Home page slug must be 'home' in ALL languages
page = Page.objects.create(
    title_i18n={'<lang1>': '<Title>', '<lang2>': '<Title>'},
    slug_i18n={'<lang1>': '<slug>', '<lang2>': '<slug>'},
    html_content_i18n=html_content,
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

After all pages are generated:

```python
python manage.py shell -c "
from djangopress.core.models import Page, MenuItem

# Clear existing menu items
MenuItem.objects.filter(parent__isnull=True).delete()

# Create menu items for all active pages in sort order
pages = Page.objects.filter(is_active=True).order_by('sort_order', 'id')
for i, page in enumerate(pages):
    MenuItem.objects.create(
        label_i18n=page.title_i18n,
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

Write header HTML for each language to `/tmp/dp-header-<lang>.html`. The header template uses Django template syntax with variables like `{{ site_name }}`, `{{ menu_items }}`, `{% for item in menu_items %}`, etc. Refer to `djangopress-html-reference` for the exact template variables and conventions.

### 6b. Save via Django shell

```python
python manage.py shell -c "
from djangopress.core.models import GlobalSection

section, created = GlobalSection.objects.get_or_create(
    key='main-header',
    defaults={
        'name': 'Main Header',
        'section_type': 'header',
        'html_template_i18n': {},
        'is_active': True,
    }
)

html_template = {}
for lang in ['<lang1>', '<lang2>']:
    with open(f'/tmp/dp-header-{lang}.html') as f:
        html_template[lang] = f.read()

section.html_template_i18n = html_template
section.save()
print(f'Header generated ({sum(len(v) for v in section.html_template_i18n.values())} chars)')
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

Write footer HTML for each language to `/tmp/dp-footer-<lang>.html`. Include site name, contact info, social media links, copyright notice, and navigation links using Django template syntax from `djangopress-html-reference`.

### 7b. Save via Django shell

```python
python manage.py shell -c "
from djangopress.core.models import GlobalSection

section, created = GlobalSection.objects.get_or_create(
    key='main-footer',
    defaults={
        'name': 'Main Footer',
        'section_type': 'footer',
        'html_template_i18n': {},
        'is_active': True,
    }
)

html_template = {}
for lang in ['<lang1>', '<lang2>']:
    with open(f'/tmp/dp-footer-{lang}.html') as f:
        html_template[lang] = f.read()

section.html_template_i18n = html_template
section.save()
print(f'Footer generated ({sum(len(v) for v in section.html_template_i18n.values())} chars)')
"
```

### 7c. Clean up

```bash
rm -f /tmp/dp-footer-*.html
```

---

## Phase 8: Images

Image placeholders are already embedded in the HTML from Phase 4 (using `data-image-prompt`, `data-image-name`, and `placehold.co` src). These placeholders can be resolved later via:

- The backoffice image management UI
- A dedicated image processing step
- The `/improve-site` skill

The generate-site skill focuses on content structure — getting all pages, header, footer, and menu items in place with quality HTML. Image generation is a separate concern that can be handled afterwards.

---

## Phase 9: Final Review

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
- Note that images are placeholders (can be processed later)
- Any errors that occurred
- Suggest next steps:
  1. Visit `/backoffice/settings/` to upload logos and configure the design system
  2. **Upload logos AFTER the domain is set** (already set from Phase 3)
  3. Configure SEO & Code settings at `/backoffice/settings/seo/`
  4. Refine pages via the inline editor (`?edit=v2`) or chat refinement
  5. Process image placeholders via backoffice or a dedicated step
  6. The project briefing is the most important field for AI quality

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
