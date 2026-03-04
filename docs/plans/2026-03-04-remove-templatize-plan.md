# Remove Templatize — HTML Per Language Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the `{{ trans.xxx }}` template variable system with full HTML copies per language, eliminating the templatize step entirely.

**Architecture:** Pages and GlobalSections store per-language HTML in a JSONField (`html_content_i18n` / `html_template_i18n`). LLMs only output clean HTML. Translation is deferred to a separate "Bulk Translate" action. Refinements optionally propagate to other languages.

**Tech Stack:** Django 6.0, JSONField, BeautifulSoup (for HTML manipulation in editor), existing LLM infrastructure.

**Design Doc:** `docs/plans/2026-03-04-remove-templatize-html-per-language-design.md`

---

### Task 1: Add New Model Fields (Non-Breaking)

Add `html_content_i18n` and `html_template_i18n` alongside existing fields. No breaking changes — old code continues working.

**Files:**
- Modify: `core/models.py` (Page model ~line 715, GlobalSection ~line 1029, PageVersion ~line 1096)

**Step 1: Add html_content_i18n to Page model**

After the existing `html_content` field (~line 718), add:

```python
html_content_i18n = models.JSONField(
    default=dict, blank=True,
    help_text='Per-language HTML content. Structure: {"pt": "<html>...", "en": "<html>..."}'
)
```

**Step 2: Add html_template_i18n to GlobalSection model**

After the existing `html_template` field (~line 1035), add:

```python
html_template_i18n = models.JSONField(
    default=dict, blank=True,
    help_text='Per-language Django template HTML. Structure: {"pt": "<html>...", "en": "<html>..."}'
)
```

**Step 3: Add html_content_i18n to PageVersion model**

After the existing `html_content` field (~line 1098), add:

```python
html_content_i18n = models.JSONField(
    default=dict, blank=True,
    help_text='Per-language HTML content snapshot.'
)
```

**Step 4: Create and run migration**

```bash
python manage.py makemigrations core
python manage.py migrate
```

**Step 5: Update Page.save_version to copy new field**

In `Page.create_version()` (~line 954), add:
```python
version.html_content_i18n = self.html_content_i18n
```

**Step 6: Update Page.restore_to_version to restore new field**

In `Page.restore_to_version()` (~line 950), add:
```python
self.html_content_i18n = version.html_content_i18n
```

**Step 7: Commit**

```bash
git add core/models.py core/migrations/
git commit -m "feat: add html_content_i18n and html_template_i18n fields"
```

---

### Task 2: Update Page Rendering (PageView)

Make PageView read from `html_content_i18n` with fallback to `html_content` for backward compatibility.

**Files:**
- Modify: `core/views.py` (PageView.get_context_data ~line 27-99)

**Step 1: Update get_context_data to use html_content_i18n**

Replace the rendering logic (~lines 51-67). The new logic:

```python
# Get current language
language = get_language()
default_lang = settings.get('default_language', 'pt')

# Try new per-language HTML first, fall back to old templatized approach
html_i18n = page_obj.html_content_i18n or {}
if html_i18n and html_i18n.get(language):
    html = html_i18n.get(language)
elif html_i18n and html_i18n.get(default_lang):
    html = html_i18n.get(default_lang)
else:
    # Backward compat: old templatized HTML with {{ trans.xxx }}
    html = page_obj.html_content or ''
    translations = (page_obj.content or {}).get('translations', {})
    trans = translations.get(language, translations.get(default_lang, {}))
    # trans will be added to context below

# Render as Django template (for {{ LOGO.url }}, {% url %}, etc.)
try:
    template = Template(html)
    render_context = {**context}
    if not html_i18n:
        render_context['trans'] = trans  # Only for old format
    page_content = template.render(RequestContext(self.request, render_context))
except Exception as e:
    # Error handling...
```

**Step 2: Verify page rendering still works**

Run dev server and check existing pages render correctly (they'll use the old fallback path since `html_content_i18n` is empty).

```bash
python manage.py runserver 8000
```

**Step 3: Commit**

```bash
git add core/views.py
git commit -m "feat: update PageView to read from html_content_i18n with fallback"
```

---

### Task 3: Update GlobalSection Rendering

Make `load_global_section` read from `html_template_i18n` with fallback.

**Files:**
- Modify: `core/templatetags/section_tags.py` (load_global_section)

**Step 1: Update load_global_section tag**

After loading the GlobalSection from DB, try the new field first:

```python
# Try new per-language template first
html_i18n = section.html_template_i18n or {}
language = context.get('LANGUAGE_CODE', 'pt')

if html_i18n and html_i18n.get(language):
    html_template = html_i18n.get(language)
elif html_i18n and html_i18n.get(default_lang):
    html_template = html_i18n.get(default_lang)
else:
    # Backward compat: old templatized approach
    html_template = section.html_template
    translations = section.content.get('translations', {})
    trans = translations.get(language, translations.get('pt', {}))
    # Add trans to section_context below

section_context = {**context.flatten(), 'section': section}
if not html_i18n:
    section_context['trans'] = trans  # Only for old format

template = Template(html_template)
rendered = template.render(Context(section_context))
```

**Step 2: Verify header/footer rendering still works**

```bash
python manage.py runserver 8000
```

**Step 3: Commit**

```bash
git add core/templatetags/section_tags.py
git commit -m "feat: update load_global_section for html_template_i18n with fallback"
```

---

### Task 4: Simplify Page Generation Pipeline

Remove templatize + translate from `generate_page`. LLM generates HTML in default language only.

**Files:**
- Modify: `ai/services.py` (generate_page method ~line 599)
- Modify: `ai/utils/prompts.py` (if prompt changes needed)

**Step 1: Update generate_page return format**

In `generate_page()`, after Step 1 (HTML generation) completes, instead of calling `_templatize_and_translate`, wrap the HTML directly:

```python
# After Step 1 generates html_content:
default_lang = self._get_default_language()

# Skip templatize + translate entirely
result = {
    'html_content_i18n': {default_lang: html_content},
    # Keep backward compat fields during transition
    'html_content': html_content,
    'content': {'translations': {default_lang: {}}},
}

# Step 2: metadata (title/slug) still runs as before
# Merge metadata into result
result['title_i18n'] = metadata.get('title_i18n', {})
result['slug_i18n'] = metadata.get('slug_i18n', {})
```

Remove or skip the `_templatize_and_translate` call in the parallel execution pool.

**Step 2: Update save_page in ai/views.py**

Find the save endpoint and update to save `html_content_i18n`:

```python
page.html_content_i18n = page_data.get('html_content_i18n', {})
# Also save old field for backward compat during transition
page.html_content = page_data.get('html_content', '')
page.content = page_data.get('content', {})
```

**Step 3: Update save_page in backoffice/api_views.py**

Same change — save both old and new fields during transition.

**Step 4: Update ai_generate_page.html template**

Update JavaScript that handles the generation response to include `html_content_i18n` in the save payload.

**Step 5: Test page generation**

Generate a new page through the backoffice and verify:
- HTML is generated in default language
- No templatize/translate step runs
- Page saves correctly with `html_content_i18n`
- Page renders correctly

**Step 6: Commit**

```bash
git add ai/services.py ai/views.py backoffice/api_views.py backoffice/templates/
git commit -m "feat: simplify generation pipeline - skip templatize, use html_content_i18n"
```

---

### Task 5: Update Refinement Pipeline

Update `refine_page_with_html`, `refine_section_only`, and `chat_refine_page` to work with `html_content_i18n`.

**Files:**
- Modify: `ai/services.py` (refine methods)
- Modify: `ai/views.py` (refine endpoints)

**Step 1: Update chat_refine_page**

In the chat refine method, read HTML from `html_content_i18n[current_lang]` instead of de-templatizing:

```python
current_lang = get_language()
html_i18n = page.html_content_i18n or {}
current_html = html_i18n.get(current_lang, html_i18n.get(default_lang, page.html_content or ''))
```

After refinement, save back to the same language key:

```python
result_html_i18n = dict(page.html_content_i18n or {})
result_html_i18n[current_lang] = refined_html
return {'html_content_i18n': result_html_i18n, ...}
```

**Step 2: Update refine_section_only**

Same approach: read section from `html_content_i18n[current_lang]`, refine, save back.

**Step 3: Update refine_page_with_html**

Remove `_detemplatize_html` call. Read directly from `html_content_i18n`.

**Step 4: Update refine_global_section**

Read from `html_template_i18n[current_lang]`, refine, save back.

**Step 5: Update chat refine endpoint in ai/views.py**

Ensure the endpoint returns the language-keyed HTML and handles saving to the right field.

**Step 6: Test refinement**

Test chat refine on an existing page — verify it reads and saves correctly.

**Step 7: Commit**

```bash
git add ai/services.py ai/views.py
git commit -m "feat: update refinement pipeline for html_content_i18n"
```

---

### Task 6: Add Translation Propagation Support

Add the "Propagate to other languages?" mechanism to refinement endpoints and UI.

**Files:**
- Modify: `ai/services.py` (new method: `translate_html_section`)
- Modify: `ai/views.py` (refine endpoints return available_languages)
- Modify: `backoffice/templates/backoffice/ai_refine_page.html` (propagation UI)
- Modify: `ai/utils/prompts.py` (new: `get_html_translation_prompt`)

**Step 1: Add translate_html_section method to ContentGenerationService**

```python
def translate_html(self, html, source_lang, target_lang, model=None):
    """Translate HTML content from one language to another.
    LLM only outputs clean HTML — no JSON, no template variables."""
    prompt = PromptTemplates.get_html_translation_prompt(
        html=html,
        source_lang=source_lang,
        target_lang=target_lang,
    )
    model = model or 'gemini-flash'
    translated_html = self._call_llm(prompt, model=model)
    return translated_html
```

**Step 2: Add get_html_translation_prompt to PromptTemplates**

```python
@staticmethod
def get_html_translation_prompt(html, source_lang, target_lang):
    return f"""Translate this HTML from {source_lang} to {target_lang}.

RULES:
- Keep ALL HTML tags, CSS classes, attributes, and structure IDENTICAL
- Only translate visible text content
- Do NOT add, remove, or modify any HTML elements
- Do NOT change any class names, IDs, data attributes, or URLs
- Output ONLY the translated HTML, nothing else

HTML:
{html}"""
```

**Step 3: Add propagation endpoint**

New endpoint `POST /ai/api/propagate-translation/`:

```python
{
    "page_id": 1,
    "source_lang": "pt",
    "target_languages": ["en"],
    "scope": "section",          # "section", "element", or "page"
    "section_id": "hero",        # for section scope
    "html": "<section>...</section>"  # the refined HTML to translate
}
```

This endpoint:
1. For each target language, calls `translate_html`
2. Patches the corresponding section/element/page in `html_content_i18n[target_lang]`
3. Returns success/failure per language

**Step 4: Add propagation UI to chat refine page**

After AI refinement response, if `html_content_i18n` has more than one language, show:

```html
<div id="propagation-panel" class="hidden mt-4 p-4 bg-gray-50 rounded-lg">
    <p class="font-medium">Propagate changes to other languages?</p>
    <div class="flex gap-2 mt-2">
        <!-- Checkbox per existing language -->
    </div>
    <button onclick="propagateTranslations()">Propagate</button>
</div>
```

**Step 5: Test propagation**

1. Generate a page in Portuguese
2. Manually add English HTML to `html_content_i18n` (or use Bulk Translate once built)
3. Refine a section in Portuguese
4. Verify propagation UI appears
5. Click propagate → verify English section updates

**Step 6: Commit**

```bash
git add ai/services.py ai/views.py ai/utils/prompts.py backoffice/templates/
git commit -m "feat: add translation propagation for refinement"
```

---

### Task 7: Build Bulk Translate Feature

New backoffice view for translating pages to other languages.

**Files:**
- Create: `backoffice/templates/backoffice/ai_bulk_translate.html`
- Modify: `backoffice/views.py` (new view)
- Modify: `backoffice/urls.py` (new URL)
- Modify: `ai/views.py` (new API endpoint)
- Modify: `ai/services.py` (bulk translate method)
- Modify: `backoffice/templates/backoffice/includes/sidebar.html` (add menu item)

**Step 1: Add bulk_translate_page method to ContentGenerationService**

```python
def bulk_translate_page(self, page, target_languages, model=None):
    """Translate a page's HTML to multiple languages.
    Uses the default language HTML as source."""
    default_lang = self._get_default_language()
    source_html = (page.html_content_i18n or {}).get(default_lang, '')
    if not source_html:
        raise ValueError("No source HTML in default language")

    results = {}
    for lang in target_languages:
        if lang == default_lang:
            continue
        translated = self.translate_html(source_html, default_lang, lang, model=model)
        results[lang] = translated

    return results
```

**Step 2: Add API endpoint**

`POST /ai/api/bulk-translate/`:

```python
{
    "page_ids": [1, 2, 3],
    "target_languages": ["en", "fr"],
    "model": "gemini-flash"
}
```

Returns progress per page (or use SSE for streaming progress).

**Step 3: Create backoffice view**

New view at `/backoffice/ai/bulk-translate/` that:
- Lists all pages with their translation status
- Shows which languages each page has HTML for
- Lets user select pages + target languages
- Triggers translation via AJAX

**Step 4: Create template ai_bulk_translate.html**

Table layout:
- Column: Page title
- Columns: one per enabled language (checkbox if HTML exists, empty if not)
- Select all / select none
- Target language checkboxes
- "Translate" button

**Step 5: Add URL and sidebar link**

```python
# backoffice/urls.py
path('ai/bulk-translate/', views.ai_bulk_translate, name='ai_bulk_translate'),
```

Add to sidebar under AI section.

**Step 6: Add GlobalSection translation support**

Include header/footer in Bulk Translate — either on the same page or as checkboxes at the bottom.

**Step 7: Test Bulk Translate end-to-end**

1. Generate a page in Portuguese (default language only)
2. Go to Bulk Translate
3. Select the page + English as target
4. Click Translate
5. Verify English HTML appears in `html_content_i18n["en"]`
6. Visit the page in English — verify it renders

**Step 8: Commit**

```bash
git add backoffice/templates/backoffice/ai_bulk_translate.html backoffice/views.py backoffice/urls.py ai/views.py ai/services.py backoffice/templates/backoffice/includes/sidebar.html
git commit -m "feat: add Bulk Translate feature for per-language HTML"
```

---

### Task 8: Update Inline Editor (editor_v2)

Update editor API endpoints to work with per-language HTML.

**Files:**
- Modify: `editor_v2/api_views.py` (all API endpoints)

**Step 1: Update update_page_content**

Instead of updating a translation key in `content.translations`, directly modify the text in `html_content_i18n[lang]`:

```python
lang = data.get('language', get_language())
html_i18n = dict(page.html_content_i18n or {})
html = html_i18n.get(lang, '')

# Use BeautifulSoup to find and replace text
soup = BeautifulSoup(html, 'html.parser')
element = soup.select_one(selector)
if element:
    element.string = new_value  # or element.clear() + element.append(new_value)

html_i18n[lang] = str(soup)
page.html_content_i18n = html_i18n
page.save()
```

**Step 2: Update update_page_classes**

Update classes in current language's HTML AND propagate to all other language copies:

```python
html_i18n = dict(page.html_content_i18n or {})
for lang, html in html_i18n.items():
    soup = BeautifulSoup(html, 'html.parser')
    element = soup.select_one(selector)
    if element:
        element['class'] = new_classes
    html_i18n[lang] = str(soup)
page.html_content_i18n = html_i18n
page.save()
```

**Step 3: Update update_page_attribute**

Same as classes — propagate structural changes to all languages.

**Step 4: Update refine_section, save_ai_section, refine_element, save_ai_element, refine_page, save_ai_page**

All of these need to:
1. Read from `html_content_i18n[lang]` instead of `html_content`
2. Save back to `html_content_i18n[lang]`
3. Include available languages in response (for propagation UI)

**Step 5: Update editor JavaScript**

`editor_v2/static/editor_v2/js/` — update API calls to include `language` parameter and handle `html_content_i18n` responses.

**Step 6: Add propagation modal to editor**

After AI section/element/page refinement saves, show modal asking to propagate to other languages (if they exist).

**Step 7: Test inline editing**

1. Open page in editor mode
2. Edit text → verify it saves to correct language HTML
3. Edit classes → verify it propagates to all language copies
4. Refine section via AI → verify propagation modal appears

**Step 8: Commit**

```bash
git add editor_v2/
git commit -m "feat: update inline editor for per-language HTML"
```

---

### Task 9: Update Site Generator

Update `SiteGenerator` to create pages with `html_content_i18n`.

**Files:**
- Modify: `ai/site_generator.py` (~lines 700-772)

**Step 1: Update _generate_single_page**

Change page creation:

```python
page = Page.objects.create(
    html_content_i18n={default_lang: result['html_content_i18n'].get(default_lang, '')},
    title_i18n=result.get('title_i18n', {}),
    slug_i18n=result.get('slug_i18n', {}),
    # Keep old fields during transition
    html_content=result.get('html_content', ''),
    content=result.get('content', {}),
)
```

**Step 2: Update header/footer generation**

```python
section.html_template_i18n = {default_lang: generated_html}
# Keep old field during transition
section.html_template = generated_html
section.save()
```

**Step 3: Test generate_site command**

```bash
python manage.py generate_site briefings/test.md --dry-run
```

**Step 4: Commit**

```bash
git add ai/site_generator.py
git commit -m "feat: update site generator for html_content_i18n"
```

---

### Task 10: Update Refinement Agent & Site Assistant

Update auxiliary systems that read/write page HTML.

**Files:**
- Modify: `ai/refinement_agent/agent.py`
- Modify: `site_assistant/tools/page_tools.py`

**Step 1: Update refinement agent _get_target_html**

Remove de-templatize call, read directly from `html_content_i18n`:

```python
def _get_target_html(self, page, language=None):
    lang = language or get_language()
    html_i18n = page.html_content_i18n or {}
    return html_i18n.get(lang, html_i18n.get(self._get_default_language(), ''))
```

**Step 2: Update refinement agent HTML saving**

When tools save refined HTML, save to `html_content_i18n[lang]`.

**Step 3: Update site_assistant _save_soup_to_page**

```python
def _save_soup_to_page(page, soup, language=None):
    lang = language or get_language()
    html_i18n = dict(page.html_content_i18n or {})
    html_i18n[lang] = str(soup)
    page.html_content_i18n = html_i18n
    page.save()
```

**Step 4: Update all page.html_content reads in page_tools.py**

Replace `page.html_content` reads with `page.html_content_i18n.get(lang, ...)`.

**Step 5: Commit**

```bash
git add ai/refinement_agent/ site_assistant/
git commit -m "feat: update refinement agent and site assistant for html_content_i18n"
```

---

### Task 11: Update Backoffice Views & Templates

Update page listing, page edit, and other views that reference `html_content` or `content`.

**Files:**
- Modify: `backoffice/views.py`
- Modify: `backoffice/api_views.py`
- Modify: `backoffice/templates/backoffice/pages.html`
- Modify: `backoffice/templates/backoffice/page_edit.html`
- Modify: `backoffice/templates/backoffice/ai_refine_page.html`
- Modify: `backoffice/templates/backoffice/ai_generate_page.html`

**Step 1: Update backoffice views**

- `PageEditView`: check `page.html_content_i18n` instead of `page.html_content`
- Any `exclude(html_content='')` → `exclude(html_content_i18n={})`
- Settings views that read pages for design guide generation

**Step 2: Update page edit template**

Show translation status — which languages have HTML, which don't. Add link to Bulk Translate.

**Step 3: Update pages list template**

Add translation status column showing language badges (green for translated, gray for missing).

**Step 4: Update ai_refine_page.html**

Handle `html_content_i18n` in JavaScript — read/write the correct language's HTML. Add propagation panel.

**Step 5: Update ai_generate_page.html**

Handle `html_content_i18n` in the response — display default language HTML, include in save payload.

**Step 6: Update backoffice API views**

All endpoints that read/write `html_content` and `content` need dual support during transition.

**Step 7: Test all backoffice flows**

Walk through: pages list → page edit → generate page → refine page → process images.

**Step 8: Commit**

```bash
git add backoffice/
git commit -m "feat: update backoffice views and templates for html_content_i18n"
```

---

### Task 12: Data Migration (Existing Content)

Migrate existing pages from `html_content` + `content` → `html_content_i18n`.

**Files:**
- Create: `core/migrations/XXXX_migrate_html_content_i18n.py`

**Step 1: Write data migration**

```python
from django.db import migrations

def migrate_pages_forward(apps, schema_editor):
    """Render each language's HTML from templatized HTML + translations."""
    from django.template import Template, Context

    Page = apps.get_model('core', 'Page')
    for page in Page.objects.all():
        if page.html_content_i18n:
            continue  # Already migrated

        html = page.html_content or ''
        translations = (page.content or {}).get('translations', {})
        html_i18n = {}

        for lang, trans in translations.items():
            if trans:
                try:
                    template = Template(html)
                    rendered = template.render(Context({'trans': trans}))
                    html_i18n[lang] = rendered
                except Exception:
                    html_i18n[lang] = html  # Fallback to unrendered

        if not html_i18n and html:
            # No translations — store raw HTML under default language
            html_i18n['pt'] = html

        page.html_content_i18n = html_i18n
        page.save(update_fields=['html_content_i18n'])

def migrate_global_sections_forward(apps, schema_editor):
    """Same for GlobalSections."""
    from django.template import Template, Context

    GlobalSection = apps.get_model('core', 'GlobalSection')
    for section in GlobalSection.objects.all():
        if section.html_template_i18n:
            continue

        html = section.html_template or ''
        translations = (section.content or {}).get('translations', {})
        html_i18n = {}

        for lang, trans in translations.items():
            if trans:
                try:
                    template = Template(html)
                    rendered = template.render(Context({'trans': trans}))
                    html_i18n[lang] = rendered
                except Exception:
                    html_i18n[lang] = html

        if not html_i18n and html:
            html_i18n['pt'] = html

        section.html_template_i18n = html_i18n
        section.save(update_fields=['html_template_i18n'])

class Migration(migrations.Migration):
    dependencies = [
        ('core', 'XXXX_add_html_content_i18n'),  # Previous migration
    ]
    operations = [
        migrations.RunPython(migrate_pages_forward, migrations.RunPython.noop),
        migrations.RunPython(migrate_global_sections_forward, migrations.RunPython.noop),
    ]
```

**Step 2: Run migration on dev**

```bash
python manage.py migrate
```

**Step 3: Verify migrated data**

```bash
python manage.py shell -c "
from core.models import Page
for p in Page.objects.all():
    langs = list((p.html_content_i18n or {}).keys())
    print(f'{p.title_i18n}: {langs}')
"
```

**Step 4: Commit**

```bash
git add core/migrations/
git commit -m "data: migrate existing pages to html_content_i18n"
```

---

### Task 13: Remove Old Fields and Code (Final Cleanup)

Remove backward compatibility code, old fields, and dead code. **Only do this after all previous tasks are verified working.**

**Files:**
- Modify: `core/models.py` (remove html_content, content from Page; html_template, content from GlobalSection)
- Modify: `core/views.py` (remove fallback to old fields)
- Modify: `core/templatetags/section_tags.py` (remove fallback)
- Modify: `ai/services.py` (remove _templatize_and_translate, _detemplatize_html, _extract_text_from_html)
- Modify: `ai/utils/prompts.py` (remove get_translate_only_prompt)
- Modify: All files that still reference old fields

**Step 1: Remove old fields from models**

Remove from Page:
- `html_content`
- `content`

Remove from GlobalSection:
- `html_template`
- `content`

Remove from PageVersion:
- `html_content` (old one)
- `content`

**Step 2: Create migration**

```bash
python manage.py makemigrations core
python manage.py migrate
```

**Step 3: Remove fallback code from PageView**

Remove the `else` branch that reads `html_content` and builds `trans` context.

**Step 4: Remove fallback code from load_global_section**

Remove the `else` branch that reads `html_template` and builds `trans` context.

**Step 5: Remove dead methods from ai/services.py**

- `_templatize_and_translate()` (~170 lines)
- `_detemplatize_html()` (~20 lines)
- `_extract_text_from_html()` (~100 lines)

**Step 6: Remove get_translate_only_prompt from prompts.py**

**Step 7: Remove get_translation filter usage for Page/GlobalSection**

The `get_translation` filter in `section_tags.py` may still be used by SiteImage, DynamicForm, etc. Only remove Page/GlobalSection usage.

**Step 8: Remove dual-write code**

Search all files for `html_content =` (old field assignment) and remove. Search for `page.content =` and remove.

**Step 9: Run full verification**

```bash
python manage.py runserver 8000
# Test: page rendering, generation, refinement, editor, bulk translate
```

**Step 10: Commit**

```bash
git add -A
git commit -m "refactor: remove old templatize system and {{ trans.xxx }} variables"
```

---

## Execution Order & Dependencies

```
Task 1 (models) → Task 2 (PageView) → Task 3 (GlobalSection) → Task 4 (generation)
                                                                      ↓
Task 12 (migration) ← Task 11 (backoffice) ← Task 10 (agent/assistant) ← Task 9 (site_gen)
                                                                               ↑
                                                    Task 8 (editor) ← Task 7 (bulk translate) ← Task 6 (propagation) ← Task 5 (refinement)

Task 13 (cleanup) runs LAST after everything else is verified.
```

Tasks 1-5 are strictly sequential.
Tasks 6-7 depend on Task 5.
Tasks 8-11 can be parallelized after Task 7.
Task 12 can run after Task 1 but is best done after Task 11.
Task 13 runs last.
