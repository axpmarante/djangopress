---
name: update-site
description: Update site content — pages, sections, elements, images, settings, header, footer, menu, forms. Auto-loaded when the user asks to change, edit, refine, or update any part of a DjangoPress site.
argument-hint:
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, AskUserQuestion
---

# Update DjangoPress Site Content

This skill provides the patterns for updating any part of a DjangoPress site via the Django shell. Use these when the user asks to change, edit, refine, or update content.

The argument provided is: `$ARGUMENTS`

Parse `$ARGUMENTS` to determine what the user wants to update, then use the appropriate section below.

---

## Inspect Current State

Before making changes, check what exists:

```python
python manage.py shell -c "
from djangopress.core.models import SiteSettings, Page, GlobalSection, MenuItem
s = SiteSettings.objects.first()
print(f'Site: {s.get_site_name()}')
print(f'Domain: {s.domain}')
print(f'Languages: {s.get_language_codes()}')
print(f'Default language: {s.get_default_language()}')
print()
print('Pages:')
for p in Page.objects.filter(is_active=True).order_by('sort_order'):
    print(f'  [{p.id}] {p.default_title} (/{p.default_slug}/)')
print()
print('GlobalSections:')
for gs in GlobalSection.objects.filter(is_active=True):
    print(f'  {gs.key} ({gs.section_type})')
print()
print(f'Menu items: {MenuItem.objects.filter(is_active=True).count()}')
"
```

---

## Update a Page

### Read page content
```python
python manage.py shell -c "
from djangopress.core.models import Page, SiteSettings
page = Page.objects.get(id=<ID>)  # or .get(slug_i18n__contains='<slug>')
lang = SiteSettings.objects.first().get_default_language()
html = page.html_content_i18n.get(lang, '')
print(f'Title: {page.title_i18n}')
print(f'Slug: {page.slug_i18n}')
print(f'HTML length: {len(html)} chars')
print(html[:5000])
"
```

### AI refine entire page
```python
python manage.py shell -c "
from ai.services import ContentGenerationService
from djangopress.core.models import Page

service = ContentGenerationService()
result = service.refine_page_with_html(
    page_id=<ID>,
    instructions='''<what to change>''',
    handle_images=True,
)

page = Page.objects.get(id=<ID>)
page.html_content_i18n = result.get('html_content_i18n', page.html_content_i18n)
page.save()
print('Page refined and saved')
"
```

### Update page title or slug
```python
python manage.py shell -c "
from djangopress.core.models import Page
page = Page.objects.get(id=<ID>)
page.title_i18n = {'pt': 'Novo Título', 'en': 'New Title'}
page.slug_i18n = {'pt': 'novo-titulo', 'en': 'new-title'}
page.save()
print(f'Updated: {page.title_i18n}')
"
```

### Create a new page
```python
python manage.py shell -c "
from ai.services import ContentGenerationService
from djangopress.core.models import Page, SiteSettings

service = ContentGenerationService()
settings = SiteSettings.objects.first()

result = service.generate_page(
    brief='''<page description>''',
    language=settings.get_default_language(),
)

page = Page.objects.create(
    title_i18n=result.get('title_i18n', {}),
    slug_i18n=result.get('slug_i18n', {}),
    html_content_i18n=result.get('html_content_i18n', {}),
    is_active=True,
    sort_order=<order>,
)
print(f'Created: {page.default_title} (/{page.default_slug}/) ID={page.id}')
"
```

### Delete a page
```python
python manage.py shell -c "
from djangopress.core.models import Page, MenuItem
page = Page.objects.get(id=<ID>)
MenuItem.objects.filter(page=page).delete()
print(f'Deleting: {page.default_title}')
page.delete()
print('Deleted')
"
```

### Reorder pages
```python
python manage.py shell -c "
from djangopress.core.models import Page
# Set sort_order for each page
for order, page_id in enumerate([<id1>, <id2>, <id3>]):
    Page.objects.filter(id=page_id).update(sort_order=order * 10)
    p = Page.objects.get(id=page_id)
    print(f'{p.sort_order}: {p.default_title}')
"
```

---

## Update a Section (within a page)

### Read a specific section
```python
python manage.py shell -c "
from djangopress.core.models import Page, SiteSettings
from bs4 import BeautifulSoup

page = Page.objects.get(id=<ID>)
lang = SiteSettings.objects.first().get_default_language()
soup = BeautifulSoup(page.html_content_i18n.get(lang, ''), 'html.parser')

# List all sections
for section in soup.find_all('section'):
    name = section.get('data-section', 'unnamed')
    print(f'Section: {name} ({len(str(section))} chars)')

# Read a specific section
target = soup.find('section', {'data-section': '<section-name>'})
if target:
    print(str(target)[:3000])
"
```

### AI refine a specific section

Use `refine_page_with_html` with instructions targeting the section:

```python
python manage.py shell -c "
from ai.services import ContentGenerationService
from djangopress.core.models import Page

service = ContentGenerationService()
result = service.refine_page_with_html(
    page_id=<ID>,
    instructions='''Update the <section-name> section: <what to change>. Keep all other sections exactly as they are.''',
    handle_images=True,
)

page = Page.objects.get(id=<ID>)
page.html_content_i18n = result.get('html_content_i18n', page.html_content_i18n)
page.save()
print('Section refined')
"
```

### Manually edit a section's HTML

For direct HTML changes without AI:

```python
python manage.py shell -c "
from djangopress.core.models import Page, SiteSettings
from bs4 import BeautifulSoup

page = Page.objects.get(id=<ID>)
settings = SiteSettings.objects.first()

for lang in settings.get_language_codes():
    html = page.html_content_i18n.get(lang, '')
    soup = BeautifulSoup(html, 'html.parser')
    section = soup.find('section', {'data-section': '<section-name>'})
    if section:
        # Example: change text, classes, attributes
        heading = section.find('h2')
        if heading:
            heading.string = '<new text>'
        page.html_content_i18n[lang] = str(soup)

page.save()
print('Section updated in all languages')
"
```

---

## Update an Element (within a section)

### Change text content
```python
python manage.py shell -c "
from djangopress.core.models import Page, SiteSettings
from bs4 import BeautifulSoup

page = Page.objects.get(id=<ID>)
settings = SiteSettings.objects.first()

for lang in settings.get_language_codes():
    soup = BeautifulSoup(page.html_content_i18n.get(lang, ''), 'html.parser')
    # Find by CSS selector patterns
    element = soup.select_one('[data-section=\"hero\"] h1')
    if element:
        element.string = '<new text for this language>'
    page.html_content_i18n[lang] = str(soup)

page.save()
print('Element text updated')
"
```

### Change CSS classes
```python
python manage.py shell -c "
from djangopress.core.models import Page, SiteSettings
from bs4 import BeautifulSoup

page = Page.objects.get(id=<ID>)
settings = SiteSettings.objects.first()

for lang in settings.get_language_codes():
    soup = BeautifulSoup(page.html_content_i18n.get(lang, ''), 'html.parser')
    element = soup.select_one('[data-section=\"hero\"]')
    if element:
        element['class'] = ['bg-blue-900', 'text-white', 'py-24']  # replace classes
    page.html_content_i18n[lang] = str(soup)

page.save()
print('Classes updated')
"
```

### Change an attribute (href, src, etc.)
```python
python manage.py shell -c "
from djangopress.core.models import Page, SiteSettings
from bs4 import BeautifulSoup

page = Page.objects.get(id=<ID>)
settings = SiteSettings.objects.first()

for lang in settings.get_language_codes():
    soup = BeautifulSoup(page.html_content_i18n.get(lang, ''), 'html.parser')
    link = soup.select_one('[data-section=\"cta\"] a')
    if link:
        link['href'] = '/contact/'
    page.html_content_i18n[lang] = str(soup)

page.save()
print('Attribute updated')
"
```

---

## Update Images

### Process image placeholders on a page
```python
python manage.py shell -c "
from ai.services import ContentGenerationService
from djangopress.core.models import Page, SiteSettings
from bs4 import BeautifulSoup

service = ContentGenerationService()
settings = SiteSettings.objects.first()
languages = settings.get_language_codes()
default_lang = settings.get_default_language()

page = Page.objects.get(id=<ID>)
html = page.html_content_i18n.get(default_lang, '')
soup = BeautifulSoup(html, 'html.parser')

images = []
for idx, img in enumerate(soup.find_all('img')):
    src = img.get('src', '')
    prompt = img.get('data-image-prompt', '')
    name = img.get('data-image-name', '')
    if prompt or name or 'placehold.co' in src:
        images.append({'index': idx, 'src': src, 'alt': img.get('alt',''), 'name': name, 'prompt': prompt})

if images:
    suggestions = service.analyze_page_images(page_id=page.id, images=images)
    decisions = [{'image_name': img.get('name',''), 'image_src': img.get('src',''), 'action': 'generate', 'prompt': next((s for s in suggestions if s.get('index')==img['index']), {}).get('prompt', img.get('prompt','')), 'aspect_ratio': '16:9'} for img in images]
    result = service.process_page_images(page_id=page.id, image_decisions=decisions, languages=languages)
    print(f'Processed: {len(result.get(\"processed\", []))} images')
else:
    print('No placeholder images found')
"
```

### Replace a specific image
```python
python manage.py shell -c "
from djangopress.core.models import Page, SiteSettings, SiteImage
from bs4 import BeautifulSoup

page = Page.objects.get(id=<ID>)
settings = SiteSettings.objects.first()

# Find image in library
image = SiteImage.objects.filter(title_i18n__contains='<search>').first()
# Or by ID: image = SiteImage.objects.get(id=<IMAGE_ID>)

if image:
    for lang in settings.get_language_codes():
        soup = BeautifulSoup(page.html_content_i18n.get(lang, ''), 'html.parser')
        img = soup.select_one('[data-image-name=\"<name>\"]')
        if img:
            img['src'] = image.image.url
            img['alt'] = image.get_alt_text(lang)
        page.html_content_i18n[lang] = str(soup)
    page.save()
    print(f'Image replaced with: {image.image.url}')
"
```

---

## Update Settings

### Site identity
```python
python manage.py shell -c "
from djangopress.core.models import SiteSettings
s = SiteSettings.objects.first()
s.site_name_i18n = {'pt': '<nome>', 'en': '<name>'}
s.site_description_i18n = {'pt': '<descrição>', 'en': '<description>'}
s.project_briefing = '''<updated briefing>'''
s.save()
print('Identity updated')
"
```

### Contact info
```python
python manage.py shell -c "
from djangopress.core.models import SiteSettings
s = SiteSettings.objects.first()
s.contact_email = '<email>'
s.contact_phone = '<phone>'
s.contact_address_i18n = {'pt': '<morada>', 'en': '<address>'}
s.save()
print('Contact updated')
"
```

### Social media
```python
python manage.py shell -c "
from djangopress.core.models import SiteSettings
s = SiteSettings.objects.first()
s.facebook_url = '<url>'
s.instagram_url = '<url>'
s.linkedin_url = '<url>'
s.youtube_url = '<url>'
s.twitter_url = '<url>'
s.whatsapp_number = '<+351...>'
s.tiktok_url = '<url>'
s.pinterest_url = '<url>'
s.save()
print('Social media updated')
"
```

### Design system
```python
python manage.py shell -c "
from djangopress.core.models import SiteSettings
s = SiteSettings.objects.first()
s.primary_color = '#<hex>'
s.secondary_color = '#<hex>'
s.accent_color = '#<hex>'
s.heading_font = '<Google Font name>'
s.body_font = '<Google Font name>'
s.border_radius_class = 'rounded-xl'     # rounded-none, rounded, rounded-lg, rounded-xl, rounded-2xl, rounded-full
s.shadow_class = 'shadow-lg'             # shadow-none, shadow, shadow-md, shadow-lg, shadow-xl
s.save()
print('Design system updated')
"
```

### Languages
```python
python manage.py shell -c "
from djangopress.core.models import SiteSettings
s = SiteSettings.objects.first()
s.enabled_languages = [
    {'code': 'pt', 'name': 'Português'},
    {'code': 'en', 'name': 'English'},
]
s.default_language = 'pt'
s.save()
print(f'Languages: {s.get_language_codes()}')
"
```

---

## Update Header

### Read current header
```python
python manage.py shell -c "
from djangopress.core.models import GlobalSection, SiteSettings
header = GlobalSection.objects.get(key='main-header')
lang = SiteSettings.objects.first().get_default_language()
print(header.html_template_i18n.get(lang, '')[:3000])
"
```

### AI refine header
```python
python manage.py shell -c "
from ai.services import ContentGenerationService
from djangopress.core.models import GlobalSection

service = ContentGenerationService()
result = service.refine_global_section(
    section_key='main-header',
    refinement_instructions='''<what to change — e.g. add language switcher, change logo size, update navigation style>''',
)

header = GlobalSection.objects.get(key='main-header')
header.html_template_i18n = result.get('html_template_i18n', {})
header.save()
print(f'Header updated ({sum(len(v) for v in header.html_template_i18n.values())} chars)')
"
```

---

## Update Footer

### Read current footer
```python
python manage.py shell -c "
from djangopress.core.models import GlobalSection, SiteSettings
footer = GlobalSection.objects.get(key='main-footer')
lang = SiteSettings.objects.first().get_default_language()
print(footer.html_template_i18n.get(lang, '')[:3000])
"
```

### AI refine footer
```python
python manage.py shell -c "
from ai.services import ContentGenerationService
from djangopress.core.models import GlobalSection

service = ContentGenerationService()
result = service.refine_global_section(
    section_key='main-footer',
    refinement_instructions='''<what to change — e.g. update copyright year, add new links, change layout>''',
)

footer = GlobalSection.objects.get(key='main-footer')
footer.html_template_i18n = result.get('html_template_i18n', {})
footer.save()
print(f'Footer updated ({sum(len(v) for v in footer.html_template_i18n.values())} chars)')
"
```

---

## Update Menu Items

### List menu items
```python
python manage.py shell -c "
from djangopress.core.models import MenuItem
for item in MenuItem.objects.filter(is_active=True).order_by('sort_order'):
    parent = f' (under {item.parent.get_label()})' if item.parent else ''
    page_info = f' → /{item.page.default_slug}/' if item.page else f' → {item.url}'
    print(f'[{item.id}] {item.get_label()}{page_info}{parent}')
"
```

### Add a menu item
```python
python manage.py shell -c "
from djangopress.core.models import MenuItem, Page
page = Page.objects.get(id=<PAGE_ID>)
MenuItem.objects.create(
    label_i18n=page.title_i18n,
    page=page,
    sort_order=<order>,
    is_active=True,
)
print(f'Added: {page.default_title}')
"
```

### Rebuild menu from pages
```python
python manage.py shell -c "
from djangopress.core.models import Page, MenuItem
MenuItem.objects.all().delete()
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

## Update Forms

### List forms
```python
python manage.py shell -c "
from djangopress.core.models import DynamicForm
for form in DynamicForm.objects.all():
    print(f'[{form.id}] {form.name} (slug: {form.slug}, submissions: {form.submissions.count()})')
"
```

### Update form fields
```python
python manage.py shell -c "
from djangopress.core.models import DynamicForm
form = DynamicForm.objects.get(slug='contact')
print(f'Current fields: {form.fields_schema}')
# Update fields_schema as needed
form.save()
"
```

---

## Backoffice Quick Reference

For tasks better done via the web UI:

| Task | URL |
|------|-----|
| Upload logos | `/backoffice/settings/` |
| Design system (visual) | `/backoffice/settings/design/` |
| Process images (visual) | `/backoffice/page/<id>/images/` |
| Chat refine a page | `/backoffice/ai/chat/refine/<id>/` |
| Inline editor | Visit page with `?edit=v2` |
| Media library | `/backoffice/media/` |
| SEO & tracking code | `/backoffice/settings/seo/` |
