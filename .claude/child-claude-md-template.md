# {{PROJECT_NAME}} — DjangoPress Site

This is a **DjangoPress child project**. The CMS engine is installed as the `djangopress` pip package. All content lives in the database — pages, headers, footers, settings, design tokens. Customization is done through the backoffice UI, AI tools, or Django shell.

## Updating DjangoPress

```bash
# Local editable install (development):
cd /path/to/djangopress && git pull
pip install -e /path/to/djangopress
python manage.py migrate
# Restart dev server

# Published package:
pip install --upgrade djangopress
python manage.py migrate
```

Always run `migrate` after upgrading — new versions may include schema changes.
If deployed on Railway: `railway up -d` after upgrading to redeploy.

---

## Managing Content

### Backoffice Dashboard

| URL | What It Does |
|-----|-------------|
| `/backoffice/` | Dashboard — overview of all pages, recent activity |
| `/backoffice/pages/` | List all pages, reorder, create new |
| `/backoffice/page/<id>/edit/` | Edit page content, HTML, settings |
| `/backoffice/page/<id>/images/` | Process images — replace placeholders with AI-generated, library, or Unsplash photos |
| `/backoffice/menu/` | Manage navigation menu items and hierarchy |
| `/backoffice/media/` | Media library — upload, browse, manage images |
| `/backoffice/forms/` | Manage dynamic forms (contact, etc.) |
| `/backoffice/forms/<id>/submissions/` | View form submissions |

### Site Settings

| URL | What It Does |
|-----|-------------|
| `/backoffice/settings/` | Main settings hub |
| `/backoffice/settings/general/` | Site name, description, domain, project briefing |
| `/backoffice/settings/languages/` | Enable/disable languages, set default |
| `/backoffice/settings/contact/` | Email, phone, address, social media URLs |
| `/backoffice/settings/design/` | Design system — colors, fonts, buttons, spacing |
| `/backoffice/settings/seo/` | OG image, meta defaults, custom head/body code |
| `/backoffice/settings/header/` | Edit header (with AI refinement) |
| `/backoffice/settings/footer/` | Edit footer (with AI refinement) |
| `/backoffice/settings/ai-models/` | Override AI model selection per task |

### AI Content Tools

| URL | What It Does |
|-----|-------------|
| `/backoffice/ai/generate/page/` | Generate a new page from a brief |
| `/backoffice/ai/bulk/pages/` | Describe multiple pages at once, generate in bulk |
| `/backoffice/ai/chat/refine/<page_id>/` | Chat-based page refinement — iterative conversation with AI |
| `/backoffice/ai/bulk-translate/` | Translate pages to other languages |
| `/backoffice/ai/design-consistency/` | Analyze and fix design consistency across pages |
| `/backoffice/ai/logs/` | Browse AI call history (model, tokens, duration) |

### Inline Editor

Visit any page with `?edit=v2` (or `?edit=true`) to enter inline editing mode:
- Click any text to edit it directly
- Select a section → AI can refine just that section
- Select an element → AI can refine just that element
- Full-page AI refinement via the chat sidebar
- Language bar to switch between language versions
- Version history for rollback

### Site Assistant

`/site-assistant/` (superuser only) — manage the entire site via natural language chat. Can create/edit pages, update settings, refine content, manage menus.

---

## AI Refinement via Django Shell

For programmatic content management:

### Refine a page section
```python
python manage.py shell -c "
from ai.services import ContentGenerationService
service = ContentGenerationService()
result = service.refine_page_with_html(
    page_id=<ID>,
    instructions='Make the hero section more compelling, add a stronger CTA',
    handle_images=True,
)
from core.models import Page
page = Page.objects.get(id=<ID>)
page.html_content_i18n = result.get('html_content_i18n', page.html_content_i18n)
page.save()
print('Refined and saved')
"
```

### Update SiteSettings
```python
python manage.py shell -c "
from core.models import SiteSettings
s = SiteSettings.objects.first()
s.primary_color = '#0d9488'
s.heading_font = 'Playfair Display'
s.project_briefing = '''Updated business description...'''
s.save()
print('Settings updated')
"
```

### Refine header or footer
```python
python manage.py shell -c "
from ai.services import ContentGenerationService
from core.models import GlobalSection
service = ContentGenerationService()
result = service.refine_global_section(
    section_key='main-header',  # or 'main-footer'
    refinement_instructions='Add a language switcher dropdown, make the logo larger',
)
section = GlobalSection.objects.get(key='main-header')
section.html_template_i18n = result.get('html_template_i18n', {})
section.save()
print('Header updated')
"
```

### Generate a new page
```python
python manage.py shell -c "
from ai.services import ContentGenerationService
from core.models import Page, SiteSettings
service = ContentGenerationService()
settings = SiteSettings.objects.first()
result = service.generate_page(
    brief='Create an About Us page for the business. Include team section, mission statement, and history.',
    language=settings.get_default_language(),
)
page = Page.objects.create(
    title_i18n=result.get('title_i18n', {}),
    slug_i18n=result.get('slug_i18n', {}),
    html_content_i18n=result.get('html_content_i18n', {}),
    is_active=True,
    sort_order=10,
)
print(f'Created: {page.default_title} (/{page.default_slug}/)')
"
```

### Process images on a page
```python
python manage.py shell -c "
from ai.services import ContentGenerationService
from core.models import Page, SiteSettings
from bs4 import BeautifulSoup
service = ContentGenerationService()
settings = SiteSettings.objects.first()
page = Page.objects.get(id=<ID>)
default_lang = settings.get_default_language()
html = (page.html_content_i18n or {}).get(default_lang, '')
soup = BeautifulSoup(html, 'html.parser')
images = []
for idx, img in enumerate(soup.find_all('img')):
    prompt = img.get('data-image-prompt', '')
    name = img.get('data-image-name', '')
    if prompt or name or 'placehold.co' in img.get('src', ''):
        images.append({'index': idx, 'src': img.get('src',''), 'alt': img.get('alt',''), 'name': name, 'prompt': prompt})
if images:
    suggestions = service.analyze_page_images(page_id=page.id, images=images)
    decisions = [{'image_name': img.get('name',''), 'image_src': img.get('src',''), 'action': 'generate', 'prompt': next((s for s in suggestions if s.get('index')==img['index']), {}).get('prompt', img.get('prompt','')), 'aspect_ratio': '16:9'} for img in images]
    result = service.process_page_images(page_id=page.id, image_decisions=decisions, languages=settings.get_language_codes())
    print(f'Processed: {len(result.get(\"processed\", []))} images')
else:
    print('No placeholder images found')
"
```

---

## Project Structure

```
config/settings.py    → imports from djangopress.settings, overrides project-specific values
config/urls.py        → imports from djangopress.urls (override to add custom app URLs)
config/wsgi.py        → WSGI entry point
.env                  → secrets, API keys (never committed)
requirements.txt      → points to djangopress package
manage.py             → Django entry point
db.sqlite3            → local database
.claude/skills/       → symlinked to djangopress package skills
```

## Adding Custom Apps

For features beyond pages (blog, shop, booking, etc.), use `/add-app appname`. Custom apps go in the project root and register their URLs before the core catch-all.

To add a custom app's URLs, override `config/urls.py`:
```python
from djangopress.urls import urlpatterns as base_urlpatterns
from django.conf.urls.i18n import i18n_patterns

urlpatterns = base_urlpatterns  # non-i18n patterns from djangopress

# Add custom app URLs before core catch-all in i18n_patterns
from django.urls import include
# Override i18n_patterns to insert custom app before core
```

## Key Reminders

- **Home page slug must be `home` in ALL languages**
- **Set domain BEFORE uploading media** (GCS uses domain as folder name)
- **Project briefing** is the most important field for AI quality — keep it detailed
- **Design Guide** (`/backoffice/settings/design/`) lets you document UI patterns the AI should follow

## Claude Code Skills

| Skill | What It Does |
|-------|-------------|
| `/generate-site` | Full setup + generation from briefing — env, settings, pages, header/footer, images |
| `/create-briefing` | Research client online, write briefing interactively |
| `/edit-site` | Edit site content — pages, sections, elements, images, settings, header/footer, menu |
| `/update-djangopress` | Update to latest djangopress — pip upgrade, migrations, skill refresh, redeploy |
| `/add-app` | Scaffold a decoupled feature app |
| `/deploy-site-railway` | Deploy to Railway with Postgres |
| `/sync-data` | Push/pull DB content between local and Railway |

## Commands

```bash
python manage.py runserver 8000                        # Dev server
python manage.py migrate                               # Run migrations
python manage.py createsuperuser                       # Create admin user
python manage.py shell                                 # Django shell
python manage.py generate_site briefings/my-site.md    # Generate full site from briefing
python manage.py push_data https://site.railway.app    # Push local DB to production
python manage.py pull_data https://site.railway.app    # Pull remote DB to local
python manage.py fix_i18n_html --dry-run               # Check for legacy template vars
python manage.py migrate_storage_folder                # Copy GCS files to domain folder
railway up -d                                          # Redeploy to Railway
```

## Git Conventions

- **Do not include `Co-Authored-By` lines in commit messages.**
