---
name: edit-site
description: Edit DjangoPress site content — create/edit pages, sections, header, footer, menu, translations, images, forms, settings. Claude Code writes HTML directly following djangopress-html-reference conventions. Use when user asks to create, edit, modify, refine, or update any part of a site.
argument-hint:
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, AskUserQuestion
---

# Edit DjangoPress Site Content

This skill references `djangopress-html-reference` for all HTML conventions. Load that skill for the complete rules on data-section attributes, editor v2 compatibility, database structure, GlobalSection template syntax, translation rules, and image/storage conventions.

The argument provided is: `$ARGUMENTS`

Parse `$ARGUMENTS` to determine what the user wants to edit or create, then use the appropriate section below.

---

## General Workflow

All edit-site operations follow this five-step pattern:

```
1. Read current state    → manage.py shell (inspect site, pages, settings, languages)
2. Write HTML            → Write tool to /tmp/dp-<type>-<id>-<lang>.html
3. Save to DB            → manage.py shell (load file, save to model)
4. Verify                → manage.py shell (confirm saved, print preview)
5. Clean up              → rm /tmp/dp-*.html
```

**Before any operation, always read site context first:**

```bash
python manage.py shell -c "
from djangopress.core.models import SiteSettings, Page, GlobalSection, MenuItem
s = SiteSettings.load()
print('=== Site Context ===')
print(f'Site name: {s.site_name_i18n}')
print(f'Languages: {s.get_language_codes()}')
print(f'Default language: {s.get_default_language()}')
print(f'Briefing: {s.get_project_briefing()[:500]}')
print(f'Design guide: {s.design_guide[:500] if s.design_guide else \"None\"}')
print()
print('=== Design System ===')
print(f'Colors: primary={s.primary_color}, secondary={s.secondary_color}, accent={s.accent_color}')
print(f'Background: {s.background_color}, Text: {s.text_color}, Heading: {s.heading_color}')
print(f'Fonts: heading={s.heading_font}, body={s.body_font}')
print(f'Buttons: style={s.button_style}, radius={s.button_radius}')
print(f'Primary button: bg={s.primary_button_bg}, text={s.primary_button_text}, hover={s.primary_button_hover}')
print(f'Secondary button: bg={s.secondary_button_bg}, text={s.secondary_button_text}, hover={s.secondary_button_hover}')
print(f'Container: {s.container_width_class}, Border radius: {s.border_radius_class}, Shadow: {s.shadow_class}')
print()
print('=== Pages ===')
for p in Page.objects.all().order_by('sort_order'):
    print(f'  [{p.id}] {p.title_i18n} (slug: {p.slug_i18n}, active: {p.is_active}, order: {p.sort_order})')
print()
print('=== GlobalSections ===')
for gs in GlobalSection.objects.all():
    print(f'  [{gs.id}] key={gs.key}, name={gs.name}, type={gs.section_type}, active={gs.is_active}')
print()
print('=== Menu ===')
for m in MenuItem.objects.filter(parent__isnull=True).order_by('sort_order'):
    label = m.label_i18n
    children = m.children.all().order_by('sort_order')
    print(f'  [{m.id}] {label} → page={m.page_id}, url={m.url}, order={m.sort_order}')
    for c in children:
        print(f'    [{c.id}] {c.label_i18n} → page={c.page_id}, url={c.url}, order={c.sort_order}')
"
```

---

## Create Page

### Step 1: Read site context

Run the general workflow context command above. Note the languages, design system values, and existing pages (to determine next `sort_order`).

### Step 2: Plan sections

Decide which sections the page needs (e.g., hero, about, features, cta). Each section must have a unique `data-section` name and `id` attribute.

### Step 3: Write HTML for each language

Use the Write tool to create `/tmp/dp-page-new-<lang>.html` for each language. Follow `djangopress-html-reference` conventions:

- Each `<section>` has `data-section="name"` and `id="name"`
- Tailwind CSS only, responsive mobile-first
- No `<html>`, `<head>`, `<body>`, `<header>`, `<nav>`, `<footer>` tags
- Real text in the target language — no template variables
- DOM structure identical between languages (only text changes)
- Use design system colors, fonts, button styles from SiteSettings

### Step 4: Save to DB

```bash
python manage.py shell -c "
from djangopress.core.models import Page

html = {}
for lang in ['pt', 'en']:
    with open(f'/tmp/dp-page-new-{lang}.html', 'r') as f:
        html[lang] = f.read()

page = Page.objects.create(
    title_i18n={'pt': 'Serviços', 'en': 'Services'},
    slug_i18n={'pt': 'servicos', 'en': 'services'},
    html_content_i18n=html,
    meta_title_i18n={'pt': 'Serviços - Nome do Site', 'en': 'Services - Site Name'},
    meta_description_i18n={'pt': 'Descrição SEO da página de serviços.', 'en': 'SEO description for the services page.'},
    is_active=True,
    sort_order=10,
)
print(f'Created page {page.id}: {page.default_title}')
"
```

### Step 5: Create associated MenuItem

```bash
python manage.py shell -c "
from djangopress.core.models import Page, MenuItem

page = Page.objects.get(slug_i18n__pt='servicos')
last_order = MenuItem.objects.filter(parent__isnull=True).order_by('-sort_order').values_list('sort_order', flat=True).first() or 0

MenuItem.objects.create(
    label_i18n={'pt': 'Serviços', 'en': 'Services'},
    page=page,
    sort_order=last_order + 1,
    is_active=True,
)
print('MenuItem created')
"
```

### Step 6: Clean up temp files

```bash
rm /tmp/dp-page-new-*.html
```

---

## Edit Section

### Step 1: Read current page HTML

```bash
python manage.py shell -c "
from djangopress.core.models import Page

page = Page.objects.get(id=<PAGE_ID>)
for lang, html in page.html_content_i18n.items():
    print(f'=== {lang} ({len(html)} chars) ===')
    print(html)
    print()
"
```

### Step 2: Create a version for rollback safety

```bash
python manage.py shell -c "
from djangopress.core.models import Page, ContentVersion

page = Page.objects.get(id=<PAGE_ID>)
ContentVersion.create_for(page, change_summary='Before edit-site update')
print('Version created')
"
```

### Step 3: Edit the target section

Identify the target section by its `data-section` attribute. Edit only that section — keep everything else intact. The DOM structure must remain identical between languages; only text content changes.

Use the Write tool to write the full HTML (edited section + all other sections unchanged) to `/tmp/dp-page-<PAGE_ID>-<lang>.html` for each language.

### Step 4: Save to DB

```bash
python manage.py shell -c "
from djangopress.core.models import Page

page = Page.objects.get(id=<PAGE_ID>)
for lang in ['pt', 'en']:
    with open(f'/tmp/dp-page-<PAGE_ID>-{lang}.html', 'r') as f:
        page.html_content_i18n[lang] = f.read()
page.save()
print(f'Saved page {page.id}: {page.default_title}')
"
```

### Step 5: Verify

```bash
python manage.py shell -c "
from djangopress.core.models import Page

page = Page.objects.get(id=<PAGE_ID>)
for lang, html in page.html_content_i18n.items():
    print(f'=== {lang} ({len(html)} chars) ===')
    # Print first 500 chars as preview
    print(html[:500])
    print('...')
    print()
"
```

### Step 6: Clean up

```bash
rm /tmp/dp-page-<PAGE_ID>-*.html
```

---

## Add Section to Existing Page

### Step 1: Read current HTML

```bash
python manage.py shell -c "
from djangopress.core.models import Page

page = Page.objects.get(id=<PAGE_ID>)
for lang, html in page.html_content_i18n.items():
    print(f'=== {lang} ({len(html)} chars) ===')
    print(html)
    print()
"
```

### Step 2: Create a version for rollback safety

```bash
python manage.py shell -c "
from djangopress.core.models import Page, ContentVersion

page = Page.objects.get(id=<PAGE_ID>)
ContentVersion.create_for(page, change_summary='Before adding new section')
print('Version created')
"
```

### Step 3: Write new section

Write a new `<section>` element with unique `data-section` and `id` attributes. The section must follow `djangopress-html-reference` conventions — Tailwind CSS, responsive, real text in the target language.

### Step 4: Insert at correct position

Read the existing HTML, insert the new section at the desired position (e.g., before the CTA, after the hero). Write the complete HTML (existing sections + new section) to `/tmp/dp-page-<PAGE_ID>-<lang>.html` for each language. Ensure identical DOM structure across all languages.

### Step 5: Save to DB

```bash
python manage.py shell -c "
from djangopress.core.models import Page

page = Page.objects.get(id=<PAGE_ID>)
for lang in ['pt', 'en']:
    with open(f'/tmp/dp-page-<PAGE_ID>-{lang}.html', 'r') as f:
        page.html_content_i18n[lang] = f.read()
page.save()
print(f'Saved page {page.id} with new section')
"
```

### Step 6: Clean up

```bash
rm /tmp/dp-page-<PAGE_ID>-*.html
```

---

## Edit Header/Footer (GlobalSections)

GlobalSections use **Django template syntax** (unlike Pages which use raw HTML). See `djangopress-html-reference` for available template tags and context variables.

### Step 1: Read current template

```bash
python manage.py shell -c "
from djangopress.core.models import GlobalSection

gs = GlobalSection.objects.get(key='main-header')
print(f'Name: {gs.name}')
print(f'Type: {gs.section_type}')
print(f'Active: {gs.is_active}')
for lang, html in gs.html_template_i18n.items():
    print(f'=== {lang} ({len(html)} chars) ===')
    print(html)
    print()
"
```

For footer, use `key='main-footer'`.

### Step 2: Write template HTML

Use the Write tool to create `/tmp/dp-header-<lang>.html` (or `/tmp/dp-footer-<lang>.html`).

The template must include:
- `{% load i18n %}` and `{% load section_tags %}` at the top
- Menu iteration using `{% for item in MENU_ITEMS %}` pattern
- Language switcher (if multilingual site)
- Logo via `{{ LOGO.url }}` or `{{ LOGO_DARK_BG.url }}`
- Contact info via `{{ CONTACT_EMAIL }}`, `{{ CONTACT_PHONE }}`
- Social media via `{{ SOCIAL_MEDIA.instagram }}`, `{{ SOCIAL_MEDIA.facebook }}`, etc.
- Navigation links via `{% url 'core:home' %}`, `{% url 'core:page' slug='about' %}`

**Menu iteration pattern:**
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

**Language switcher pattern:**
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

**Footer multilingual links pattern:**
```django
{% if LANGUAGE_CODE == 'pt' %}
  <a href="{% url 'core:page' slug='politica-privacidade' %}">Política de Privacidade</a>
{% else %}
  <a href="{% url 'core:page' slug='privacy-policy' %}">Privacy Policy</a>
{% endif %}
```

### Step 3: Save to DB

```bash
python manage.py shell -c "
from djangopress.core.models import GlobalSection

gs = GlobalSection.objects.get(key='main-header')
for lang in ['pt', 'en']:
    with open(f'/tmp/dp-header-{lang}.html', 'r') as f:
        gs.html_template_i18n[lang] = f.read()
gs.save()
print(f'Saved GlobalSection: {gs.key}')
"
```

To create a new GlobalSection:

```bash
python manage.py shell -c "
from djangopress.core.models import GlobalSection

html = {}
for lang in ['pt', 'en']:
    with open(f'/tmp/dp-header-{lang}.html', 'r') as f:
        html[lang] = f.read()

gs = GlobalSection.objects.create(
    key='main-header',
    name='Main Header',
    section_type='header',
    html_template_i18n=html,
    is_active=True,
    order=0,
)
print(f'Created GlobalSection {gs.id}: {gs.key}')
"
```

### Step 4: Clean up

```bash
rm /tmp/dp-header-*.html /tmp/dp-footer-*.html
```

### Step 5: Verify

Open the site in the browser to confirm header/footer renders correctly.

---

## Menu Management

### List current menu items

```bash
python manage.py shell -c "
from djangopress.core.models import MenuItem

for item in MenuItem.objects.filter(parent__isnull=True, is_active=True).order_by('sort_order'):
    page_info = f'page={item.page_id}' if item.page else f'url={item.url}'
    print(f'[{item.id}] {item.label_i18n} → {page_info}, order={item.sort_order}, css={item.css_class}')
    for child in item.children.all().order_by('sort_order'):
        child_info = f'page={child.page_id}' if child.page else f'url={child.url}'
        print(f'  [{child.id}] {child.label_i18n} → {child_info}, order={child.sort_order}')
"
```

### Add internal link (to a page)

```bash
python manage.py shell -c "
from djangopress.core.models import Page, MenuItem

page = Page.objects.get(slug_i18n__pt='servicos')
MenuItem.objects.create(
    label_i18n={'pt': 'Serviços', 'en': 'Services'},
    page=page,
    sort_order=5,
    is_active=True,
)
print('Internal menu item created')
"
```

### Add external link

```bash
python manage.py shell -c "
from djangopress.core.models import MenuItem

MenuItem.objects.create(
    label_i18n={'pt': 'Blog Externo', 'en': 'External Blog'},
    url='https://blog.example.com',
    sort_order=10,
    is_active=True,
    open_in_new_tab=True,
)
print('External menu item created')
"
```

### Add CTA button

```bash
python manage.py shell -c "
from djangopress.core.models import Page, MenuItem

page = Page.objects.get(slug_i18n__pt='contacto')
MenuItem.objects.create(
    label_i18n={'pt': 'Contacte-nos', 'en': 'Contact Us'},
    page=page,
    css_class='btn-primary',
    sort_order=99,
    is_active=True,
)
print('CTA menu item created')
"
```

### Add submenu item

```bash
python manage.py shell -c "
from djangopress.core.models import Page, MenuItem

parent = MenuItem.objects.get(label_i18n__pt='Serviços')
child_page = Page.objects.get(slug_i18n__pt='consultoria')
MenuItem.objects.create(
    label_i18n={'pt': 'Consultoria', 'en': 'Consulting'},
    page=child_page,
    parent=parent,
    sort_order=1,
    is_active=True,
)
print('Submenu item created')
"
```

### Reorder menu items

```bash
python manage.py shell -c "
from djangopress.core.models import MenuItem

# Define new order: list of (menu_item_id, new_sort_order)
new_order = [
    (1, 0),   # Home first
    (3, 1),   # About second
    (5, 2),   # Services third
    (7, 3),   # Contact last
]
for item_id, order in new_order:
    MenuItem.objects.filter(id=item_id).update(sort_order=order)
print('Menu reordered')
"
```

### Rebuild menu from pages

```bash
python manage.py shell -c "
from djangopress.core.models import Page, MenuItem

# Delete all existing menu items
MenuItem.objects.all().delete()
print('Deleted all menu items')

# Create menu items from active pages
for i, page in enumerate(Page.objects.filter(is_active=True).order_by('sort_order')):
    MenuItem.objects.create(
        label_i18n=page.title_i18n,
        page=page,
        sort_order=i,
        is_active=True,
    )
    print(f'Created menu item for: {page.default_title}')

print('Menu rebuilt from pages')
"
```

---

## Translations

### Step 1: Read HTML from default language

```bash
python manage.py shell -c "
from djangopress.core.models import Page, SiteSettings

s = SiteSettings.load()
default_lang = s.get_default_language()
page = Page.objects.get(id=<PAGE_ID>)
html = page.html_content_i18n.get(default_lang, '')
print(f'=== {default_lang} ({len(html)} chars) ===')
print(html)
"
```

### Step 2: Write HTML for each additional language

For each non-default language, write a translated version to `/tmp/dp-page-<PAGE_ID>-<lang>.html`. Critical rules:

- **DOM structure must be identical** — same tags, nesting, classes, attributes
- Only text content changes
- The editor v2 uses `nth-child` selectors — if DOM diverges between languages, inline editing breaks

### Step 3: Save all languages at once

```bash
python manage.py shell -c "
from djangopress.core.models import Page, ContentVersion

page = Page.objects.get(id=<PAGE_ID>)
ContentVersion.create_for(page, change_summary='Adding translations')

for lang in ['pt', 'en']:
    with open(f'/tmp/dp-page-<PAGE_ID>-{lang}.html', 'r') as f:
        page.html_content_i18n[lang] = f.read()
page.save()
print(f'Saved translations for page {page.id}')
"
```

### Step 4: Translate page metadata

```bash
python manage.py shell -c "
from djangopress.core.models import Page

page = Page.objects.get(id=<PAGE_ID>)
page.title_i18n = {'pt': 'Serviços', 'en': 'Services'}
page.slug_i18n = {'pt': 'servicos', 'en': 'services'}
page.meta_title_i18n = {'pt': 'Serviços - Nome do Site', 'en': 'Services - Site Name'}
page.meta_description_i18n = {'pt': 'Descrição SEO em português.', 'en': 'SEO description in English.'}
page.save()
print('Metadata translations saved')
"
```

### Step 5: Translate menu labels

```bash
python manage.py shell -c "
from djangopress.core.models import MenuItem

for item in MenuItem.objects.all():
    print(f'[{item.id}] label_i18n = {item.label_i18n}')
    # Update as needed:
    # item.label_i18n = {'pt': '...', 'en': '...'}
    # item.save()
"
```

### Step 6: Clean up

```bash
rm /tmp/dp-page-<PAGE_ID>-*.html
```

---

## Images

### List media library

```bash
python manage.py shell -c "
from djangopress.core.models import SiteImage

for img in SiteImage.objects.filter(is_active=True):
    print(f'[{img.id}] key={img.key}')
    print(f'  URL: {img.image.url}')
    print(f'  Alt: {img.alt_text_i18n}')
    print(f'  Title: {img.title_i18n}')
    print(f'  Tags: {img.tags}')
    print(f'  Description: {img.description[:100] if img.description else \"None\"}')
    print()
"
```

### Use placeholder images (before real images are available)

In HTML, use placehold.co with descriptive `data-image-*` attributes:

```html
<img src="https://placehold.co/1200x600?text=Hero+Image"
     data-image-name="hero_image"
     data-image-prompt="Modern restaurant interior, warm lighting"
     alt="Restaurant interior" />
```

### Use real images from media library

Match images to content using the `description` field, then use the GCS URL:

```html
<img src="https://storage.googleapis.com/bucket/folder/site_images/restaurant.jpg"
     alt="Restaurant interior" />
```

After resolving placeholders, **remove** the `data-image-name` and `data-image-prompt` attributes.

### Replace placeholders with real images in existing HTML

```bash
python manage.py shell -c "
from djangopress.core.models import Page, SiteImage, ContentVersion

page = Page.objects.get(id=<PAGE_ID>)
ContentVersion.create_for(page, change_summary='Replacing image placeholders')

# Build mapping of placeholder names to real URLs
images = {img.key: img.image.url for img in SiteImage.objects.filter(is_active=True) if img.key}
print('Available images:', list(images.keys()))

# Replace in HTML for each language
import re
for lang in page.html_content_i18n:
    html = page.html_content_i18n[lang]
    # Find all data-image-name attributes and replace their src
    for key, url in images.items():
        html = re.sub(
            rf'src=\"https://placehold\.co/[^\"]+\"(\s+)data-image-name=\"{key}\"(\s+)data-image-prompt=\"[^\"]+\"',
            f'src=\"{url}\"',
            html,
        )
    page.html_content_i18n[lang] = html

page.save()
print(f'Updated images in page {page.id}')
"
```

---

## Settings

### Read current settings

```bash
python manage.py shell -c "
from djangopress.core.models import SiteSettings

s = SiteSettings.load()
print('=== Identity ===')
print(f'Site name: {s.site_name_i18n}')
print(f'Description: {s.site_description_i18n}')
print(f'Default language: {s.default_language}')
print(f'Enabled languages: {s.enabled_languages}')
print()
print('=== Contact ===')
print(f'Email: {s.contact_email}')
print(f'Phone: {s.contact_phone}')
print(f'Address: {s.contact_address_i18n}')
print()
print('=== Social Media ===')
print(f'Facebook: {s.facebook_url}')
print(f'Instagram: {s.instagram_url}')
print(f'LinkedIn: {s.linkedin_url}')
print(f'YouTube: {s.youtube_url}')
print(f'Twitter: {s.twitter_url}')
print(f'WhatsApp: {s.whatsapp_number}')
print(f'TikTok: {s.tiktok_url}')
print(f'Pinterest: {s.pinterest_url}')
print()
print('=== Design System ===')
print(f'Colors: primary={s.primary_color}, secondary={s.secondary_color}, accent={s.accent_color}')
print(f'Background: {s.background_color}, Text: {s.text_color}, Heading: {s.heading_color}')
print(f'Heading font: {s.heading_font}, Body font: {s.body_font}')
print(f'H1: font={s.h1_font}, size={s.h1_size}')
print(f'H2: font={s.h2_font}, size={s.h2_size}')
print(f'H3: font={s.h3_font}, size={s.h3_size}')
print(f'Container: {s.container_width_class}')
print(f'Border radius: {s.border_radius_class}')
print(f'Shadow: {s.shadow_class}')
print(f'Buttons: style={s.button_style}, size={s.button_size}, radius={s.button_radius}')
print(f'Primary button: bg={s.primary_button_bg}, text={s.primary_button_text}, hover={s.primary_button_hover}')
print(f'Secondary button: bg={s.secondary_button_bg}, text={s.secondary_button_text}, hover={s.secondary_button_hover}')
"
```

### Update site identity

```bash
python manage.py shell -c "
from djangopress.core.models import SiteSettings

s = SiteSettings.load()
s.site_name_i18n = {'pt': 'Novo Nome', 'en': 'New Name'}
s.site_description_i18n = {'pt': 'Descrição do site em português.', 'en': 'Site description in English.'}
s.save()
print('Site identity updated')
"
```

### Update contact info

```bash
python manage.py shell -c "
from djangopress.core.models import SiteSettings

s = SiteSettings.load()
s.contact_email = 'info@example.com'
s.contact_phone = '+351 912 345 678'
s.contact_address_i18n = {'pt': 'Rua Exemplo, 123, Lisboa', 'en': '123 Example Street, Lisbon'}
s.save()
print('Contact info updated')
"
```

### Update social media

```bash
python manage.py shell -c "
from djangopress.core.models import SiteSettings

s = SiteSettings.load()
s.facebook_url = 'https://facebook.com/example'
s.instagram_url = 'https://instagram.com/example'
s.linkedin_url = 'https://linkedin.com/company/example'
s.youtube_url = 'https://youtube.com/@example'
s.twitter_url = 'https://twitter.com/example'
s.whatsapp_number = '+351912345678'
s.tiktok_url = 'https://tiktok.com/@example'
s.pinterest_url = 'https://pinterest.com/example'
s.save()
print('Social media updated')
"
```

### Update design system colors

```bash
python manage.py shell -c "
from djangopress.core.models import SiteSettings

s = SiteSettings.load()
s.primary_color = '#1a56db'
s.secondary_color = '#6b7280'
s.accent_color = '#f59e0b'
s.background_color = '#ffffff'
s.text_color = '#1f2937'
s.heading_color = '#111827'
s.save()
print('Colors updated')
"
```

### Update design system typography

```bash
python manage.py shell -c "
from djangopress.core.models import SiteSettings

s = SiteSettings.load()
s.heading_font = 'Inter'
s.body_font = 'Open Sans'
s.h1_font = 'Inter'
s.h1_size = 'text-5xl'
s.h2_font = 'Inter'
s.h2_size = 'text-3xl'
s.h3_font = 'Inter'
s.h3_size = 'text-2xl'
s.save()
print('Typography updated')
"
```

### Update button styles

```bash
python manage.py shell -c "
from djangopress.core.models import SiteSettings

s = SiteSettings.load()
s.button_style = 'filled'
s.button_size = 'md'
s.button_radius = 'rounded-lg'
s.primary_button_bg = '#1a56db'
s.primary_button_text = '#ffffff'
s.primary_button_hover = '#1e40af'
s.secondary_button_bg = '#ffffff'
s.secondary_button_text = '#1a56db'
s.secondary_button_hover = '#f3f4f6'
s.save()
print('Button styles updated')
"
```

### Update SEO metadata for a page

```bash
python manage.py shell -c "
from djangopress.core.models import Page

page = Page.objects.get(id=<PAGE_ID>)
page.meta_title_i18n = {'pt': 'Título SEO em PT', 'en': 'SEO Title in EN'}
page.meta_description_i18n = {'pt': 'Descrição meta em português, 150-160 caracteres.', 'en': 'Meta description in English, 150-160 characters.'}
page.save()
print(f'SEO metadata updated for page {page.id}')
"
```

---

## Form Management

### List all forms

```bash
python manage.py shell -c "
from djangopress.core.models import DynamicForm

for form in DynamicForm.objects.all():
    print(f'[{form.id}] name={form.name}, slug={form.slug}, active={form.is_active}')
    print(f'  Submission URL: /forms/{form.slug}/submit/')
    print(f'  Fields: {list(form.fields_schema.keys()) if form.fields_schema else \"None\"}')
    print(f'  Success message: {form.success_message_i18n}')
    print(f'  Email subject: {form.email_subject_i18n}')
    print(f'  Send confirmation: {form.send_confirmation_email}')
    print()
"
```

### Read form field schema

```bash
python manage.py shell -c "
from djangopress.core.models import DynamicForm
import json

form = DynamicForm.objects.get(slug='contact')
print(json.dumps(form.fields_schema, indent=2, ensure_ascii=False))
"
```

### Create a new form

```bash
python manage.py shell -c "
from djangopress.core.models import DynamicForm

form = DynamicForm.objects.create(
    name='Contact Form',
    slug='contact',
    fields_schema={
        'name': {
            'type': 'text',
            'label': {'pt': 'Nome', 'en': 'Name'},
            'required': True,
        },
        'email': {
            'type': 'email',
            'label': {'pt': 'Email', 'en': 'Email'},
            'required': True,
        },
        'phone': {
            'type': 'tel',
            'label': {'pt': 'Telefone', 'en': 'Phone'},
            'required': False,
        },
        'message': {
            'type': 'textarea',
            'label': {'pt': 'Mensagem', 'en': 'Message'},
            'required': True,
        },
    },
    success_message_i18n={
        'pt': 'Mensagem enviada com sucesso! Entraremos em contacto em breve.',
        'en': 'Message sent successfully! We will get back to you soon.',
    },
    email_subject_i18n={
        'pt': 'Nova mensagem de contacto',
        'en': 'New contact message',
    },
    send_confirmation_email=True,
    is_active=True,
)
print(f'Created form {form.id}: {form.name} (slug: {form.slug})')
"
```

### Update form fields

```bash
python manage.py shell -c "
from djangopress.core.models import DynamicForm

form = DynamicForm.objects.get(slug='contact')
# Add a new field
form.fields_schema['subject'] = {
    'type': 'select',
    'label': {'pt': 'Assunto', 'en': 'Subject'},
    'required': True,
    'choices': [
        {'value': 'general', 'label': {'pt': 'Geral', 'en': 'General'}},
        {'value': 'support', 'label': {'pt': 'Suporte', 'en': 'Support'}},
        {'value': 'sales', 'label': {'pt': 'Vendas', 'en': 'Sales'}},
    ],
}
form.save()
print('Form fields updated')
"
```

### Update form messages

```bash
python manage.py shell -c "
from djangopress.core.models import DynamicForm

form = DynamicForm.objects.get(slug='contact')
form.success_message_i18n = {
    'pt': 'Obrigado! A sua mensagem foi recebida.',
    'en': 'Thank you! Your message has been received.',
}
form.email_subject_i18n = {
    'pt': 'Nova mensagem do website',
    'en': 'New website message',
}
form.save()
print('Form messages updated')
"
```

### Embed form in page HTML

The form submission URL is `/forms/<slug>/submit/` (outside i18n_patterns). The HTML in the page is raw HTML — it is not auto-generated from `fields_schema`. The frontend form fields **must match the field names** defined in the schema.

Example form HTML for a contact section:

```html
<section data-section="contact" id="contact" class="py-20 bg-gray-50">
  <div class="max-w-3xl mx-auto px-4">
    <h2 class="text-3xl font-bold text-center mb-12">Contacte-nos</h2>
    <form action="/forms/contact/submit/" method="post">
      {% csrf_token %}
      <div class="grid gap-6">
        <div>
          <label for="name" class="block text-sm font-medium text-gray-700 mb-1">Nome</label>
          <input type="text" id="name" name="name" required
                 class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent" />
        </div>
        <div>
          <label for="email" class="block text-sm font-medium text-gray-700 mb-1">Email</label>
          <input type="email" id="email" name="email" required
                 class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent" />
        </div>
        <div>
          <label for="message" class="block text-sm font-medium text-gray-700 mb-1">Mensagem</label>
          <textarea id="message" name="message" rows="5" required
                    class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"></textarea>
        </div>
        <div>
          <button type="submit"
                  class="w-full px-6 py-3 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 transition-colors">
            Enviar Mensagem
          </button>
        </div>
      </div>
    </form>
  </div>
</section>
```

**Note:** Form HTML in pages uses raw HTML. The `{% csrf_token %}` tag works because GlobalSections (header) provide the template context. The `fields_schema` JSON defines backend validation and labels — the frontend form must use matching field `name` attributes.
