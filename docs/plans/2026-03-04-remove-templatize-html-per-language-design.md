# Remove Templatize Step — HTML Per Language Design

**Date:** 2026-03-04
**Status:** Approved
**Motivation:** Remove `{{ trans.xxx }}` template variable system to reduce complexity, improve compatibility with smaller/faster LLM models, and simplify the generation pipeline.

---

## Summary

Replace the current templatize + translate pipeline with a simpler architecture where each language gets its own full HTML copy. LLMs only ever output clean HTML — no JSON, no template variables. Python handles all data structure and storage.

### Current Flow (Being Replaced)
```
LLM generates HTML → Python templatizes (BeautifulSoup extracts text, creates {{ trans.xxx }})
→ LLM translates text strings → Python builds translations JSON
```

### New Flow
```
LLM generates HTML in default language → Python saves it → Done
Translation happens later via Bulk Translate (separate user action)
```

---

## 1. Data Model Changes

### Page Model

```python
# REMOVE
html_content = TextField()    # Templatized HTML with {{ trans.xxx }}
content = JSONField()         # {"translations": {"pt": {...}, "en": {...}}}

# ADD
html_content_i18n = JSONField(default=dict)
# Structure: {"pt": "<full HTML>", "en": "<full HTML>"}
# Before translation: only default language key exists
# After Bulk Translate: all translated languages have their own HTML
```

- `title_i18n` and `slug_i18n` — unchanged
- `content` field — removed (translations are embedded in per-language HTML)

### GlobalSection Model

```python
# REMOVE
html_template = TextField()   # Django template with {{ trans.xxx }}
content = JSONField()         # {"translations": {...}}

# ADD
html_template_i18n = JSONField(default=dict)
# Structure: {"pt": "<full django template>", "en": "<full django template>"}
```

### Key Rule

**Default language = structural source of truth.** Bulk Translate always rebuilds other languages from the default language's HTML structure + translated text.

---

## 2. Rendering Changes

### PageView (core/views.py)

```python
def get_context_data(self, **kwargs):
    lang = get_language()
    default_lang = site_settings.default_language

    # Pick the right language's HTML, fallback to default
    html = page.html_content_i18n.get(lang, page.html_content_i18n.get(default_lang, ''))

    # Still use Django Template engine for {{ LOGO.url }}, {% url %}, etc.
    # But NO 'trans' in context — text is already in the HTML
    template = Template(html)
    rendered = template.render(RequestContext(request, context))

    context['page_content'] = rendered
```

### GlobalSection (section_tags.py)

Same approach — pick `html_template_i18n[lang]`, render as Django template with site context (LOGO, THEME, etc.) but no `trans`.

---

## 3. Generation Flow (Simplified)

```python
def generate_page(brief, model, ...):
    default_lang = site_settings.default_language

    # Step 1: LLM generates clean HTML (same prompt as today's Step 1)
    html = llm.generate(prompt, model=model)

    # Step 2: Generate metadata (title/slug) — parallel, same as today
    metadata = llm.generate_metadata(brief, model="gemini-lite")

    # No templatize. No translate.
    return {
        "html_content_i18n": {default_lang: html},
        "title_i18n": metadata["title_i18n"],
        "slug_i18n": metadata["slug_i18n"],
    }
```

Pipeline goes from 3 steps to 2 (HTML + metadata in parallel).

---

## 4. Bulk Translate (New Feature)

### Backoffice View

New view at `/backoffice/ai/bulk-translate/`.

**UI:**
- Lists all pages with translation status (which languages have HTML)
- User selects pages + target languages
- "Translate" button kicks off the process
- Progress indicator per page

### Translation Flow (Per Page, Per Language)

```
1. Take default language HTML from html_content_i18n[default_lang]
2. For each target language:
   a. Send to LLM: "Here is an HTML page in {source_lang}.
      Output the exact same HTML with all visible text translated to {target_lang}.
      Keep all HTML tags, CSS classes, attributes, and structure identical."
   b. LLM returns clean HTML in target language
   c. Python saves: page.html_content_i18n[target_lang] = translated_html
```

**The LLM prompt is simple** — "translate this HTML." No JSON, no variable naming. This is a task small models handle well.

### GlobalSections

Header and footer are included in Bulk Translate. Same flow.

### Title & Slug Translation

`title_i18n` and `slug_i18n` are also translated during Bulk Translate if they only have the default language.

---

## 5. Refinement Flow (Section / Element / Page)

### Unified Flow

```
1. User refines in language X (via chat refine, editor section/element/page)
2. LLM returns refined HTML for that scope
3. Python patches language X's HTML in html_content_i18n[X]
4. IF other languages exist in html_content_i18n:
   → UI shows: "Propagate changes to other languages?"
     with checkboxes for each existing language
   → If user selects languages:
     - For each selected language:
       - Send the refined scope to LLM: "Translate this to {lang}"
       - Patch that language's HTML (anchored by data-section / CSS selector / full replace)
   → If user skips: only language X is updated
5. Save page
```

### Scope-Specific Anchoring

- **Section refine:** match by `data-section="name"` attribute across languages
- **Element refine:** match by CSS selector (same as current)
- **Page refine:** replace entire `html_content_i18n[lang]`

### UI Integration

**Chat refine page** (`ai_refine_page.html`): After AI responds with new HTML, a "Propagate to translations" section appears below the preview (only visible if translations exist in other languages).

**Inline editor** (`editor_v2`): After saving a refined section/element/page, a modal appears: "Update translations?" with language checkboxes.

---

## 6. Editor Changes (editor_v2)

### Current Approach
Editor updates `trans.field_name` in translations JSON, or modifies CSS classes in the templatized HTML.

### New Approach
Editor directly modifies the current language's HTML in `html_content_i18n[lang]`.

- **Text edits:** Update text directly in the HTML (BeautifulSoup find element → replace text content)
- **CSS class changes:** Update in current language's HTML AND propagate to all other language copies (classes are structural, not content)
- **Attribute changes (href, src):** Propagate to all languages (structural)
- **AI refinement (section/element/page):** Follow the unified refinement flow above (ask to propagate)

### API Changes

- `update_page_content` — now updates text in `html_content_i18n[lang]` directly instead of modifying a translation key
- `update_page_classes` — updates class in `html_content_i18n[lang]` and propagates to all other language copies
- `update_page_attribute` — same propagation as classes

---

## 7. Migration Strategy

### Data Migration

Convert existing pages from `html_content` + `content` → `html_content_i18n`:

```python
for page in Page.objects.all():
    html_content_i18n = {}
    translations = page.content.get('translations', {})

    for lang in enabled_languages:
        trans = translations.get(lang, {})
        if trans or lang == default_lang:
            # Render templatized HTML with that language's translations
            template = Template(page.html_content)
            rendered = template.render(Context({'trans': trans}))
            html_content_i18n[lang] = rendered

    page.html_content_i18n = html_content_i18n
    page.save()
```

Same approach for GlobalSections.

### Field Migration

1. Add `html_content_i18n` field (JSONField, default=dict)
2. Run data migration (render existing translations into per-language HTML)
3. Remove `html_content` and `content` fields
4. Add `html_template_i18n` to GlobalSection
5. Run data migration for GlobalSections
6. Remove `html_template` and `content` from GlobalSection

---

## 8. What Stays the Same

- `title_i18n`, `slug_i18n` — unchanged
- `Page.get_by_slug()` — unchanged
- `PageVersion` — stores snapshots (now of `html_content_i18n`)
- Image processing — unchanged (operates on HTML)
- `data-section` + `id` attributes — unchanged, now serve as cross-language anchors
- Site settings, design system — unchanged
- Base template (`base.html`) — unchanged (still loads GlobalSections)

## 9. What Gets Removed

- `_templatize_and_translate()` in `ai/services.py`
- `{{ trans.xxx }}` variable system entirely
- `content` field on Page model
- `content` field on GlobalSection model
- Translation-related prompt templates in `ai/utils/prompts.py`
- `trans` context variable in rendering

## 10. Benefits

- **Simpler generation:** 3 steps → 2 steps, no templatize
- **Smaller model friendly:** LLMs only output clean HTML, no JSON or variable naming
- **Simpler rendering:** No Django Template engine needed for `trans` context (still needed for `{{ LOGO.url }}`, etc.)
- **Simpler editor:** Direct HTML manipulation instead of translation key indirection
- **Deferred translation:** Users generate content first, translate when ready
- **Better translation quality:** "Translate this HTML" is a simpler task for LLMs than "extract text into named variables and translate"
- **No extraction bugs:** No variable naming conflicts, no template validation issues
