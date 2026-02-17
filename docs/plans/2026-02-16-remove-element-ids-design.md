# Remove data-element-id: CSS Selector Addressing

## Problem

The inline editor uses `data-element-id` attributes to address elements for editing, removal, AI refinement, and translation mapping. Only elements tagged by the AI during generation get these IDs, making ~60% of page elements non-editable. Users can select untagged elements but can't act on them.

## Decision

Remove `data-element-id` entirely. Replace with CSS selector paths relative to the parent `<section data-section="...">`. Every element becomes addressable and fully editable.

## Why Selectors Work

The stability concern (AI edits changing DOM structure and breaking selectors) is a non-issue because:
- Selectors are generated and consumed within a single request
- After any AI edit, the page reloads — fresh DOM, fresh selectors
- AI refinement sends/receives full HTML, not selectors

## Design

### Addressing System

Every element is addressed by a CSS selector path from its section:

```
section[data-section="hero"] > div:nth-child(1) > h1:nth-child(1)
```

A new `getCssSelector(el)` utility generates this client-side. The backend uses BeautifulSoup's `select_one()` to resolve the same path.

### Translation Key Detection

Currently: `data-element-id="hero_title"` maps to `{{ trans.hero_title }}`.

New approach: the editor reads `{{ trans.xxx }}` directly from the element's text content to find the translation key. No ID lookup needed — the key is already in the template text.

### API Contract Change

All endpoints switch from:
```json
{"element_id": "hero_title", "section_name": "hero"}
```
to:
```json
{"selector": "section[data-section='hero'] > div > h1"}
```

### AI Prompt Changes

**Step 1 (HTML generation):** Remove the `data-element-id` instruction. LLM generates clean HTML with real text only.

**Step 2 (Templatization):** LLM derives variable names from section name + element purpose (e.g. `hero_heading`, `hero_paragraph_1`). No longer uses element IDs as naming hints.

**Element refinement:** Mark the target element with a temporary `data-target="true"` attribute in the HTML sent to the LLM. Prompt says "Edit ONLY the element marked with data-target." Strip marker from response.

### Affected Files

**AI Prompts** (`ai/utils/prompts.py`):
- `get_page_generation_prompt()` — remove data-element-id instruction
- `get_templatize_prompt()` — derive var names from context, not IDs
- `get_section_refinement_prompt()` — no change
- `get_element_refinement_prompt()` — use data-target marker
- `get_section_generation_prompt()` — remove data-element-id instruction

**Backend** (`editor_v2/api_views.py`):
- `update_page_content()` — use selector, detect trans var from text
- `update_page_element_classes()` — use selector
- `update_page_element_attribute()` — use selector
- `remove_element()` — use selector
- `apply_option()` — use selector for element scope
- `save_ai_element()` — use selector
- `refine_element()` — mark target element, strip marker from response
- `refine_multi()` — same for element scope

**Backend** (`ai/services.py`):
- `refine_element_only()` — mark target with data-target, strip from response
- `_templatize_and_translate()` — no ID-based naming

**Frontend** (`editor_v2/static/editor_v2/js/`):
- `lib/dom.js` — add `getCssSelector(el)`, remove `hasStoredElementId()`
- `modules/selection.js` — remove snap-to-`[data-element-id]`, select any element
- `modules/sidebar.js` — detect trans var from text content, work for any element
- `modules/context-menu.js` — all actions for any element, compute selector on demand
- `modules/ai-panel.js` — send selector instead of element_id
- `modules/changes.js` — use selector to find elements

**Other**:
- `site_assistant/tools/page_tools.py` — use selectors
- `site_assistant/prompts.py` — remove data-element-id references
