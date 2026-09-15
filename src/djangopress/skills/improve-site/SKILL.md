---
name: improve-site
description: Improve a DjangoPress site based on its last quality report. Reads the lowest-scoring categories, fixes issues using the correct DjangoPress workflows (SiteSettings, Page HTML via /tmp/, GlobalSections, DynamicForms), then re-analyzes. Requires the site slug as argument.
---

# Improve Site Quality

Read the last quality report for a DjangoPress site, fix the lowest-scoring issues using proper DjangoPress workflows, and re-analyze to measure improvement.

## Usage

```
/improve-site <slug>
```

## Prerequisites

- DjangoPress Manager running on `localhost:9000`
- The site must have at least one quality report (run `/analyze-site <slug>` first if none exists)
- Playwright CLI installed

## CRITICAL: How Content Works in DjangoPress

DjangoPress stores ALL content in the SQLite database, NOT in files. You cannot fix issues by editing template files or Python code. Everything goes through `manage.py shell`.

There are four types of content, each with its own fix workflow:

| Type | What it stores | How to edit |
|------|---------------|-------------|
| **SiteSettings** | SEO defaults, contact info, social media, design system (colors, fonts, buttons) | `SiteSettings.load()` → set fields → `.save()` |
| **Page** | Page HTML content, titles, slugs, meta tags (all i18n) | Write HTML to `/tmp/dp-page-<id>-<lang>.html` → load via shell → save to model |
| **GlobalSection** | Header and footer templates (Django template syntax) | Write HTML to `/tmp/dp-header-<lang>.html` → load via shell → save to model |
| **DynamicForm** | Form definitions (fields_schema JSON) | Create/update via shell |

**The `/edit-site` skill has the complete workflow for each type. This skill tells you WHAT to fix; `/edit-site` tells you HOW.**

---

## Process

### Step 1: Get the quality report and site path

```bash
cd /Users/antoniomarante/Documents/DjangoSites/djangopress-manager
python manage.py shell -c "
from manager.models import Site
import json
s = Site.objects.get(slug='<SLUG>')
print('Path:', s.path)
print('Total:', s.quality_score_total)
print()
for cat, data in sorted(s.quality_score.items(), key=lambda x: x[1].get('score', 0)):
    print(f'  {cat}: {data.get(\"score\", \"?\")}/100 — {data.get(\"details\", \"\")}')
"
```

### Step 2: Identify what to fix and classify each issue

Sort categories by score (ascending). Focus on the 2-3 lowest. For each issue, classify it by fix type:

| Category | Typical issues | Fix type |
|----------|---------------|----------|
| **SEO** | Missing meta description, OG tags, page titles | **SiteSettings** (site-wide defaults) + **Page** (per-page meta) |
| **Content** | Placeholder text, missing pages, thin content | **Page** (edit HTML content) |
| **Images** | Missing alt text, broken URLs, placeholders | **Page** (edit `<img>` tags in page HTML) |
| **Mobile** | Horizontal scroll, fixed widths, unresponsive layout | **Page** + **GlobalSection** (fix Tailwind classes in HTML) |
| **Accessibility** | Missing alt text, heading hierarchy, ARIA labels | **Page** + **GlobalSection** (fix HTML attributes) |
| **Design** | Inconsistent colors, fonts, spacing | **SiteSettings** (design system) + **Page** (section CSS classes) |
| **Links** | Broken internal links, 404s | **Page** (fix `<a href>`) + **Menu** (fix MenuItem records) |
| **Forms** | Missing contact form, missing fields, no CSRF | **DynamicForm** (create/update schema) + **Page** (embed form HTML) |
| **Compliance** | No cookie banner, no privacy page, no contact info | **Page** (create privacy page) + **GlobalSection** (add cookie banner to footer) + **SiteSettings** (contact info) |
| **Performance** | Large images, slow load | Usually outside DjangoPress scope — note for user |

### Step 3: Navigate to the child site

```bash
cd <SITE_PATH>
```

All `manage.py shell` commands from here run inside the **child site**, not the manager.

### Step 4: Read site context

Before making any changes, read the current state:

```bash
python manage.py shell -c "
from djangopress.core.models import SiteSettings, Page, GlobalSection, MenuItem
s = SiteSettings.load()
print('=== Site Context ===')
print(f'Site name: {s.site_name_i18n}')
print(f'Languages: {s.get_language_codes()}')
print(f'Default language: {s.get_default_language()}')
print()
print('=== Design System ===')
print(f'Colors: primary={s.primary_color}, secondary={s.secondary_color}, accent={s.accent_color}')
print(f'Fonts: heading={s.heading_font}, body={s.body_font}')
print(f'Buttons: style={s.button_style}, radius={s.button_radius}')
print()
print('=== Contact ===')
print(f'Email: {s.contact_email}')
print(f'Phone: {s.contact_phone}')
print()
print('=== Pages ===')
for p in Page.objects.all().order_by('sort_order'):
    meta_desc = p.meta_description_i18n or {}
    has_meta = any(v for v in meta_desc.values())
    print(f'  [{p.id}] {p.title_i18n} (slug: {p.slug_i18n}) meta_desc: {\"yes\" if has_meta else \"MISSING\"}')
print()
print('=== GlobalSections ===')
for gs in GlobalSection.objects.all():
    print(f'  [{gs.id}] key={gs.key}, active={gs.is_active}')
print()
print('=== Forms ===')
from djangopress.core.models import DynamicForm
for form in DynamicForm.objects.all():
    print(f'  [{form.id}] slug={form.slug}, fields={list(form.fields_schema.keys()) if form.fields_schema else \"None\"}')
"
```

### Step 5: Apply fixes by type

#### Fix Type A: SiteSettings (SEO defaults, contact, design)

For missing contact info, social media, or design inconsistencies:

```bash
python manage.py shell -c "
from djangopress.core.models import SiteSettings
s = SiteSettings.load()
# Example fixes:
s.contact_email = 'info@example.com'
s.contact_phone = '+351 912 345 678'
# s.facebook_url = 'https://facebook.com/...'
# s.primary_color = '#1a56db'
s.save()
print('SiteSettings updated')
"
```

#### Fix Type B: Page content (HTML, meta tags, images, links, accessibility)

This is the most common fix type. Follow the `/edit-site` workflow:

1. **Read current page HTML:**
```bash
python manage.py shell -c "
from djangopress.core.models import Page
page = Page.objects.get(id=<PAGE_ID>)
for lang, html in page.html_content_i18n.items():
    print(f'=== {lang} ({len(html)} chars) ===')
    print(html)
"
```

2. **Create a version for rollback safety:**
```bash
python manage.py shell -c "
from djangopress.core.models import Page
page = Page.objects.get(id=<PAGE_ID>)
page.create_version(change_summary='Before improve-site fixes')
print('Version created')
"
```

3. **Write fixed HTML** to `/tmp/dp-page-<PAGE_ID>-<lang>.html` for each language using the Write tool. Common fixes in the HTML:
   - Add `alt="descriptive text"` to `<img>` tags
   - Fix heading hierarchy (ensure single `<h1>`, then `<h2>`, `<h3>`)
   - Add `aria-label` attributes where needed
   - Fix Tailwind responsive classes (`sm:`, `md:`, `lg:` breakpoints)
   - Replace `w-[fixed]` with responsive alternatives
   - Fix broken `<a href>` links
   - Replace placeholder text with real content
   - Ensure DOM structure is identical across languages (only text changes)

4. **Save to DB:**
```bash
python manage.py shell -c "
from djangopress.core.models import Page
page = Page.objects.get(id=<PAGE_ID>)
for lang in page.html_content_i18n.keys():
    with open(f'/tmp/dp-page-<PAGE_ID>-{lang}.html', 'r') as f:
        page.html_content_i18n[lang] = f.read()
page.save()
print(f'Saved page {page.id}')
"
```

5. **Update page meta tags** (for SEO fixes):
```bash
python manage.py shell -c "
from djangopress.core.models import Page
page = Page.objects.get(id=<PAGE_ID>)
page.meta_title_i18n = {'pt': 'Título SEO', 'en': 'SEO Title'}
page.meta_description_i18n = {'pt': 'Descrição 150-160 chars.', 'en': 'Description 150-160 chars.'}
page.save()
print('Meta tags updated')
"
```

6. **Clean up:** `rm /tmp/dp-page-<PAGE_ID>-*.html`

**Repeat for each page that needs fixes.**

#### Fix Type C: GlobalSection (header/footer)

For header/footer issues (missing nav links, cookie banner, contact info in footer):

1. Read current template:
```bash
python manage.py shell -c "
from djangopress.core.models import GlobalSection
gs = GlobalSection.objects.get(key='main-footer')  # or main-header
for lang, html in gs.html_template_i18n.items():
    print(f'=== {lang} ===')
    print(html)
"
```

2. Write fixed template to `/tmp/dp-footer-<lang>.html` (or header). Remember:
   - GlobalSections use **Django template syntax** (`{% load i18n %}`, `{{ CONTACT_EMAIL }}`, etc.)
   - Use `{% for item in MENU_ITEMS %}` for navigation
   - Use `{{ LOGO.url }}` for logo
   - For cookie banner: add Alpine.js `x-data` consent component
   - For privacy link: `{% if LANGUAGE_CODE == 'pt' %}<a href="{% url 'core:page' slug='politica-privacidade' %}">...{% endif %}`

3. Save to DB:
```bash
python manage.py shell -c "
from djangopress.core.models import GlobalSection
gs = GlobalSection.objects.get(key='main-footer')
for lang in gs.html_template_i18n.keys():
    with open(f'/tmp/dp-footer-{lang}.html', 'r') as f:
        gs.html_template_i18n[lang] = f.read()
gs.save()
print('Footer updated')
"
```

4. Clean up: `rm /tmp/dp-footer-*.html`

#### Fix Type D: DynamicForm (contact form)

If the contact form is missing or incomplete:

```bash
python manage.py shell -c "
from djangopress.core.models import DynamicForm

form, created = DynamicForm.objects.get_or_create(
    slug='contact',
    defaults={
        'name': 'Contact Form',
        'fields_schema': {
            'name': {'type': 'text', 'label': {'pt': 'Nome', 'en': 'Name'}, 'required': True},
            'email': {'type': 'email', 'label': {'pt': 'Email', 'en': 'Email'}, 'required': True},
            'phone': {'type': 'tel', 'label': {'pt': 'Telefone', 'en': 'Phone'}, 'required': False},
            'message': {'type': 'textarea', 'label': {'pt': 'Mensagem', 'en': 'Message'}, 'required': True},
        },
        'success_message_i18n': {
            'pt': 'Mensagem enviada com sucesso!',
            'en': 'Message sent successfully!',
        },
        'is_active': True,
    },
)
print(f'Form {\"created\" if created else \"already exists\"}: {form.slug}')
"
```

Then embed the form HTML in the contact page using Fix Type B workflow.

#### Fix Type E: Create missing pages (privacy policy, etc.)

For compliance issues — create a privacy policy page:

1. Write HTML to `/tmp/dp-page-new-<lang>.html` for each language
2. Create the page:
```bash
python manage.py shell -c "
from djangopress.core.models import Page

html = {}
for lang in ['pt', 'en']:
    with open(f'/tmp/dp-page-new-{lang}.html', 'r') as f:
        html[lang] = f.read()

page = Page.objects.create(
    title_i18n={'pt': 'Política de Privacidade', 'en': 'Privacy Policy'},
    slug_i18n={'pt': 'politica-privacidade', 'en': 'privacy-policy'},
    html_content_i18n=html,
    meta_title_i18n={'pt': 'Política de Privacidade', 'en': 'Privacy Policy'},
    meta_description_i18n={'pt': 'Política de privacidade e proteção de dados.', 'en': 'Privacy policy and data protection.'},
    is_active=True,
    sort_order=99,
)
print(f'Created page {page.id}: {page.default_title}')
"
```
3. Add link in footer GlobalSection (Fix Type C)
4. Clean up: `rm /tmp/dp-page-new-*.html`

### Step 6: Verify fixes

Start the dev server if not running:

```bash
curl -s -X POST http://localhost:9000/site/<SLUG>/start/ \
  -H "X-Requested-With: XMLHttpRequest" \
  -H "X-CSRFToken: $(curl -s -c - http://localhost:9000/ | grep csrftoken | awk '{print $NF}')" \
  -b "csrftoken=$(curl -s -c - http://localhost:9000/ | grep csrftoken | awk '{print $NF}')"
```

Use Playwright to visually verify the pages look correct. Check mobile view too:

```bash
playwright-cli screenshot --viewport-size=375,667 http://localhost:<PORT>/ /tmp/mobile-check.png
```

Read the screenshot to confirm no layout issues.

### Step 7: Re-analyze

Run the analyze-site skill to get a new score:

```
/analyze-site <SLUG>
```

This creates a new QualityReport for comparison.

### Step 8: Report improvements

Present a comparison table:

```
Site: <Name> (<slug>)

| Category      | Before | After | Change |
|---------------|--------|-------|--------|
| Content       | 85     | 85    | —      |
| SEO           | 60     | 90    | +30    |
| Performance   | 90     | 90    | —      |
| Images        | 70     | 95    | +25    |
| Links         | 100    | 100   | —      |
| Mobile        | 55     | 85    | +30    |
| Design        | 85     | 85    | —      |
| Accessibility | 70     | 85    | +15    |
| Forms         | 40     | 80    | +40    |
| Compliance    | 20     | 75    | +55    |
|---------------|--------|-------|--------|
| **Total**     | **68** | **87**| **+19**|
```

List what was fixed:
- Which pages were edited
- What SiteSettings were updated
- Whether new pages were created (privacy policy, etc.)
- Whether forms were created/updated

### Step 9: Commit changes

```bash
cd <SITE_PATH>
git add -A
git commit -m "improve site quality: fix <list of categories improved>"
```

---

## Decision Guide

When looking at a low-scoring category, use this to decide the fix approach:

| Issue | Fix approach |
|-------|-------------|
| Missing meta description on pages | **Page** → update `meta_description_i18n` |
| Missing OG tags | **SiteSettings** site-wide defaults handle this via the base template |
| Placeholder text in pages | **Page** → rewrite HTML content |
| Missing alt text on images | **Page** → edit `<img>` tags in page HTML |
| Broken image URLs | **Page** → fix `src` attributes |
| Horizontal scroll on mobile | **Page** + **GlobalSection** → fix Tailwind classes |
| No contact form | **DynamicForm** → create + **Page** → embed HTML |
| No cookie banner | **GlobalSection** → add to footer template |
| No privacy page | **Page** → create new page + **GlobalSection** → add footer link |
| Missing contact info | **SiteSettings** → update contact fields |
| Inconsistent colors | **SiteSettings** → update design system + **Page** → fix inline styles |
| Broken nav links | **MenuItem** records → update via shell |
| Missing header/footer | **GlobalSection** → create via `/edit-site` workflow |

## Important Notes

- Always call `page.create_version(change_summary='...')` before editing any Page (rollback safety — snapshots to PageVersion, auto-prunes old ones)
- DOM structure must be identical across languages — only text changes
- GlobalSections use Django template syntax; Pages use raw HTML
- Focus on the 2-3 worst categories for maximum impact
- Make minimal, targeted fixes — don't redesign the whole site
- If a category scores below 40, warn the user it may need significant work
- Test changes visually before committing
- The goal is incremental improvement, not perfection
