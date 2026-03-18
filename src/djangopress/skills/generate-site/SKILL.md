---
name: generate-site
description: Set up a new DjangoPress site and/or generate a full site from a markdown briefing — environment, settings, pages, header, footer, images, menu items. Handles fresh projects and existing ones.
argument-hint: [briefing-file.md]
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, AskUserQuestion
---

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
6. **Header & Footer** — generate with AI
7. **Images** — process image placeholders on all pages
8. **Review** — final verification and summary

**Your advantage as Claude Code:** You can read the briefing, understand the business context, choose appropriate design values, review generated HTML for quality, and fix issues — things a non-interactive script cannot do.

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

Use the `SiteGenerator` to configure all settings from the briefing. The `configure_settings()` method handles identity, contact, social media, **and design system** (colors, fonts, layout, buttons) automatically — it calls an LLM to choose appropriate design values based on the business type and design preferences in the briefing.

```python
python manage.py shell -c "
from ai.site_generator import SiteGenerator
gen = SiteGenerator('<briefing-path>')
plan = gen.plan()
gen.configure_settings(plan)
print('Settings configured!')
"
```

This sets domain, languages, site name, description, project briefing, contact info, social media, AND the full design system (colors, fonts, heading sizes, layout, buttons) — all from the briefing.

If no briefing file exists (interactive mode), configure via Django shell directly:

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

**Manual override:** If you need to tweak individual design values after generation:

```python
python manage.py shell -c "
from djangopress.core.models import SiteSettings
s = SiteSettings.objects.first()
s.primary_color = '#0d9488'
s.heading_font = 'Playfair Display'
s.save()
print('Updated')
"
```

---

## Phase 4: Generate Pages

Generate each page using the AI service. **Home page must be generated FIRST** — it establishes the visual style.

For each page:

### 4a. Write an enriched brief

You understand the business context, so enrich the briefing's page description:

```
Create a [Page Name] page for [Business Name].

[Original page description from briefing, expanded with your understanding]

Design direction: [from design preferences section]
Additional context: [relevant notes]

Include image placeholders with data-image-prompt and data-image-name attributes on <img> tags.
Use https://placehold.co/WxH?text=Label as placeholder src.
```

### 4b. Generate via Django shell

```python
python manage.py shell -c "
from ai.services import ContentGenerationService
from djangopress.core.models import Page, SiteSettings

service = ContentGenerationService()
settings = SiteSettings.objects.first()

result = service.generate_page(
    brief='''<your enriched brief>''',
    language=settings.get_default_language(),
)

# Home page slug must be 'home' in ALL languages
slug_i18n = result.get('slug_i18n', {})
# For home page: slug_i18n = {lang: 'home' for lang in settings.get_language_codes()}

page = Page.objects.create(
    title_i18n=result.get('title_i18n', {}),
    slug_i18n=slug_i18n,
    html_content_i18n=result.get('html_content_i18n', {}),
    is_active=True,
    sort_order=0,
)
print(f'Created: {page.default_title} (/{page.default_slug}/) ID={page.id}')
print(f'Languages: {list(result.get(\"html_content_i18n\", {}).keys())}')
"
```

### 4c. Review the generated HTML

After each page, read its HTML and check:
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

### 4d. Refine if needed

If you spot issues, refine the page:

```python
python manage.py shell -c "
from ai.services import ContentGenerationService
from djangopress.core.models import Page

service = ContentGenerationService()
result = service.refine_page_with_html(
    page_id=<ID>,
    instructions='Fix: <specific issue>',
    handle_images=True,
)

page = Page.objects.get(id=<ID>)
page.html_content_i18n = result.get('html_content_i18n', page.html_content_i18n)
page.save()
print('Refined and saved')
"
```

### 4e. After the home page

Optionally generate a design guide to improve consistency for subsequent pages:

```python
python manage.py shell -c "
from ai.utils.llm_config import LLMBase
from djangopress.core.models import SiteSettings, Page

settings = SiteSettings.objects.first()
home = Page.objects.filter(is_active=True).order_by('sort_order').first()

default_lang = settings.get_default_language()
home_html = (home.html_content_i18n or {}).get(default_lang, '')

llm = LLMBase()
messages = [
    {'role': 'system', 'content': 'You are a senior UI/UX designer. Analyze this page and write a concise design guide in markdown that captures its visual patterns, component styles, and conventions.'},
    {'role': 'user', 'content': f'Site: {settings.get_site_name()}\nBriefing: {settings.project_briefing}\nPage HTML:\n{home_html[:8000]}'},
]
response = llm.get_completion(messages, tool_name='gemini-pro')
guide = response.choices[0].message.content

settings.design_guide = guide
settings.save()
print(f'Design guide saved ({len(guide)} chars)')
"
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

## Phase 6: Generate Header

The header needs menu items to exist first (they're included in the prompt context).

```python
python manage.py shell -c "
from ai.services import ContentGenerationService
from djangopress.core.models import GlobalSection

# Ensure section exists
section, created = GlobalSection.objects.get_or_create(
    key='main-header',
    defaults={
        'name': 'Main Header',
        'section_type': 'header',
        'html_template_i18n': {},
        'is_active': True,
    }
)

service = ContentGenerationService()
result = service.refine_global_section(
    section_key='main-header',
    refinement_instructions='''<header instructions from briefing>''',
)

section.html_template_i18n = result.get('html_template_i18n', {})
section.save()
print(f'Header generated ({sum(len(v) for v in section.html_template_i18n.values())} chars)')
"
```

---

## Phase 7: Generate Footer

Same pattern as header:

```python
python manage.py shell -c "
from ai.services import ContentGenerationService
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

service = ContentGenerationService()
result = service.refine_global_section(
    section_key='main-footer',
    refinement_instructions='''<footer instructions from briefing>''',
)

section.html_template_i18n = result.get('html_template_i18n', {})
section.save()
print(f'Footer generated ({sum(len(v) for v in section.html_template_i18n.values())} chars)')
"
```

---

## Phase 8: Process Images

For each page with image placeholders:

```python
python manage.py shell -c "
from ai.services import ContentGenerationService
from djangopress.core.models import Page, SiteSettings
from bs4 import BeautifulSoup

service = ContentGenerationService()
settings = SiteSettings.objects.first()
languages = settings.get_language_codes()

page = Page.objects.get(id=<PAGE_ID>)
default_lang = settings.get_default_language()
html = (page.html_content_i18n or {}).get(default_lang, '')
soup = BeautifulSoup(html, 'html.parser')

# Find placeholder images
images = []
for idx, img in enumerate(soup.find_all('img')):
    src = img.get('src', '')
    name = img.get('data-image-name', '')
    prompt = img.get('data-image-prompt', '')
    alt = img.get('alt', '')
    if prompt or name or 'placehold.co' in src:
        images.append({'index': idx, 'src': src, 'alt': alt, 'name': name, 'prompt': prompt})

if images:
    # AI suggests prompts
    suggestions = service.analyze_page_images(page_id=page.id, images=images)

    # Build decisions — use 'generate' for AI images, 'unsplash' for stock photos
    decisions = []
    for img_data in images:
        suggestion = next((s for s in suggestions if s.get('index') == img_data['index']), {})
        decisions.append({
            'image_name': img_data.get('name', ''),
            'image_src': img_data.get('src', ''),
            'action': 'generate',  # or 'unsplash' or 'library'
            'prompt': suggestion.get('prompt', img_data.get('prompt', '')),
            'aspect_ratio': suggestion.get('aspect_ratio', '16:9'),
        })

    result = service.process_page_images(page_id=page.id, image_decisions=decisions, languages=languages)
    print(f'Processed: {len(result.get(\"processed\", []))}, Failed: {len(result.get(\"failed\", []))}')
else:
    print('No placeholder images found')
"
```

Repeat for each page. Adjust `action` based on the briefing's image strategy preference.

**Note:** Image processing is the slowest step (AI generation takes ~30s per image). If the site has many images, consider using `--skip-images` in the management command and processing images later via the backoffice UI, which gives more control.

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
- Number of images processed
- Any errors that occurred
- Suggest next steps:
  1. Visit `/backoffice/settings/` to upload logos and configure the design system
  2. **Upload logos AFTER the domain is set** (already set from Phase 3)
  3. Configure SEO & Code settings at `/backoffice/settings/seo/`
  4. Refine pages via the inline editor (`?edit=v2`) or chat refinement
  5. The project briefing is the most important field for AI quality

---

## Error Handling

- **Page generation fails:** Log the error, retry once with a simplified brief. If still fails, skip and continue.
- **Header/footer fails:** Retry once. Fallback templates will render if generation fails.
- **Image processing fails:** Note it in summary, continue. Images can always be processed later via backoffice.
- **Unexpected errors:** Read the traceback, diagnose the issue, attempt to fix it.

## Non-Interactive Alternative

For batch generation without Claude Code reviewing each step:

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
