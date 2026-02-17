# Remove data-element-id: Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove `data-element-id` from the entire system and replace with CSS selector paths, making every page element fully selectable and editable.

**Architecture:** CSS selector paths (`section[data-section="hero"] > div:nth-child(1) > h1:nth-child(1)`) replace `data-element-id` as the universal element addressing mechanism. Selectors are generated client-side and resolved server-side via `soup.select_one()`. AI element refinement uses a temporary `data-target="true"` marker instead of element IDs.

**Tech Stack:** JavaScript (ES modules), Python/Django, BeautifulSoup, Gemini LLM prompts

---

## Task 1: Add `getCssSelector()` to dom.js

**Files:**
- Modify: `editor_v2/static/editor_v2/js/lib/dom.js`

### Step 1: Replace `getElementId` and `hasStoredElementId` with `getCssSelector`

Remove the `_idCounter` variable (line 1), `getElementId()` (lines 11–17), and `hasStoredElementId()` (lines 20–23).

Add a new `getCssSelector(el)` function that builds a path from the element up to its `[data-section]` ancestor:

```javascript
/**
 * Generate a CSS selector path from el up to its nearest section ancestor.
 * Returns null if el is outside a section.
 * Example: section[data-section="hero"] > div:nth-child(1) > h1:nth-child(1)
 */
export function getCssSelector(el) {
    const section = el.closest('[data-section]');
    if (!section) return null;
    const sectionAttr = section.getAttribute('data-section');
    if (el === section) return `section[data-section="${sectionAttr}"]`;

    const parts = [];
    let current = el;
    while (current && current !== section) {
        const parent = current.parentElement;
        if (!parent) break;
        const siblings = Array.from(parent.children);
        const index = siblings.indexOf(current) + 1;
        parts.unshift(`${current.tagName.toLowerCase()}:nth-child(${index})`);
        current = parent;
    }
    return `section[data-section="${sectionAttr}"] > ${parts.join(' > ')}`;
}
```

Also add a `getElementLabel(el)` for human-readable display in the AI panel scope selector (replaces showing the raw element_id):

```javascript
/** Short human-readable label like "h1" or "div.hero-content" */
export function getElementLabel(el) {
    const tag = el.tagName.toLowerCase();
    const section = el.getAttribute('data-section');
    if (section) return section;
    const cls = el.classList[0];
    return cls ? `${tag}.${cls}` : tag;
}
```

Remove the `getElementId` and `hasStoredElementId` exports. Add `getCssSelector` and `getElementLabel` exports.

### Step 2: Commit

```bash
git add editor_v2/static/editor_v2/js/lib/dom.js
git commit -m "feat: add getCssSelector(), remove getElementId/hasStoredElementId from dom.js"
```

---

## Task 2: Update AI prompts — remove data-element-id instructions

**Files:**
- Modify: `ai/utils/prompts.py`

### Step 1: Update `get_page_generation_prompt()` (~line 668)

Remove:
```
- Use `data-element-id="unique_id"` on editable text elements (headings, paragraphs, buttons, links)
```

### Step 2: Update `get_page_refinement_prompt()` (~line 780)

Remove:
```
- Use `data-element-id="unique_id"` on editable text elements
```

### Step 3: Update `get_section_refinement_prompt()` (~line 966)

Remove:
```
- Use `data-element-id="unique_id"` on editable text elements
```

### Step 4: Update `get_section_generation_prompt()` (~line 1086)

Remove:
```
- Use `data-element-id="unique_id"` on editable text elements (headings, paragraphs, buttons, links)
```

### Step 5: Update `get_element_refinement_prompt()` (lines 1172–1291)

This is the biggest change. Replace all references to `data-element-id="{element_id}"` with `data-target="true"`.

**Method signature change:** Remove `element_id` parameter, add nothing (the caller marks the element with `data-target` before calling).

**System prompt changes:**

Replace:
```
Edit ONLY the element with `data-element-id="{element_id}"` based on the user's instructions.
```
With:
```
Edit ONLY the element marked with `data-target="true"` based on the user's instructions.
```

Replace:
```
- The element MUST keep its `data-element-id="{element_id}"` attribute
- Preserve `data-element-id` on any editable child elements
```
With:
```
- The element MUST keep its `data-target="true"` attribute
- Do NOT add `data-target` to any other elements
```

**Multi-option block:** Replace all `data-element-id="{element_id}"` with `data-target="true"`.

**User prompt changes:**

Replace:
```
The element with `data-element-id="{element_id}"`:
```
With:
```
The element marked with `data-target="true"`:
```

Replace:
```
Edit the element with `data-element-id="{element_id}"`:
```
With:
```
Edit the element marked with `data-target="true"`:
```

### Step 6: Update `get_templatize_and_translate_prompt()` (~line 1478–1483)

Remove the `data-element-id` naming rule:
```
- For elements with `data-element-id`, convert the ID to snake_case: `data-element-id="stack-heading"` → variable name `stack_heading`
```

Keep the rest of the naming rules:
```
- Use descriptive names based on the `data-section` attribute and element role: `hero_title`, `hero_subtitle`, `features_card1_title`, `cta_button`
```

### Step 7: Commit

```bash
git add ai/utils/prompts.py
git commit -m "feat: remove data-element-id from all AI prompts, use data-target for element refinement"
```

---

## Task 3: Backend API views — switch from element_id to selector

**Files:**
- Modify: `editor_v2/api_views.py`

All endpoints switch from `soup.find(attrs={'data-element-id': element_id})` to `soup.select_one(selector)`.

### Step 1: Update `update_page_content()` (lines 300–362)

Change line 323:
```python
# OLD
element_id = data.get('element_id') or field_key.replace('_', '-')
...
element = soup.find(attrs={'data-element-id': element_id})
```

To:
```python
# NEW
selector = data.get('selector')
...
if selector:
    element = soup.select_one(selector)
else:
    element = None
```

The function currently also uses `element_id` in error messages — update those to use `selector`.

### Step 2: Update `update_page_element_classes()` (lines 367–458)

Change:
```python
# OLD
element_id = data.get('element_id')
if not page_id or not element_id: ...
element = soup.find(attrs={'data-element-id': element_id})
if not element:
    element = soup.find(attrs={'id': element_id})
```

To:
```python
# NEW
selector = data.get('selector')
if not page_id or not selector: ...
element = soup.select_one(selector)
```

Update error messages and response JSON: replace `element_id` with `selector`.

### Step 3: Update `update_page_element_attribute()` (lines 463–567)

Change:
```python
# OLD
element_id = data.get('element_id')
if element_id:
    element = soup.find(attrs={'data-element-id': element_id})
    if not element:
        element = soup.find(attrs={'id': element_id})
```

To:
```python
# NEW
selector = data.get('selector')
if selector:
    element = soup.select_one(selector)
```

Keep the `old_value + tag_name` fallback for when selector is missing.

### Step 4: Update `refine_element()` (lines 837–938)

Change:
```python
# OLD
element_id = data.get('element_id')
if not page_id or not section_name or not element_id: ...
result = service.refine_element_only(
    page_id=page_id,
    section_name=section_name,
    element_id=element_id,
    ...
)
```

To:
```python
# NEW
selector = data.get('selector')
if not page_id or not selector: ...
result = service.refine_element_only(
    page_id=page_id,
    selector=selector,
    ...
)
```

Note: `section_name` is no longer needed as a separate param — the selector already includes the section context. The service method will extract the section from the selector.

### Step 5: Update `save_ai_element()` (lines 943–1045)

Change element finding:
```python
# OLD
element_id = data.get('element_id')
old_element = soup.find(attrs={'data-element-id': element_id})
new_element = new_soup.find(attrs={'data-element-id': element_id})
```

To:
```python
# NEW
selector = data.get('selector')
old_element = soup.select_one(selector)
# For the new HTML, find the element marked with data-target or use the root element
new_element = new_soup.find(attrs={'data-target': 'true'})
if new_element:
    del new_element['data-target']  # strip marker
if not new_element:
    children = list(new_soup.children)
    new_element = children[0] if children else new_soup
```

### Step 6: Update `refine_multi()` (lines 1050–1151)

Change:
```python
# OLD
element_id = data.get('element_id')
if scope == 'element' and (not element_id or not section_name): ...
result = service.refine_element_only(
    page_id=page_id,
    section_name=section_name,
    element_id=element_id,
    ...
)
```

To:
```python
# NEW
selector = data.get('selector')
if scope == 'element' and not selector: ...
result = service.refine_element_only(
    page_id=page_id,
    selector=selector,
    ...
)
```

### Step 7: Update `apply_option()` (lines 1156–1285)

Change element replacement (line 1222–1239):
```python
# OLD
elif scope == 'element' and element_id:
    old_element = soup.find(attrs={'data-element-id': element_id})
    new_element = new_soup.find(attrs={'data-element-id': element_id})
```

To:
```python
# NEW
elif scope == 'element' and selector:
    old_element = soup.select_one(selector)
    # Templatized output won't have the selector match — just use first element
    children = list(new_soup.children)
    new_element = children[0] if children else None
```

Also remove `element_id` from the version summary. Update the `section_name` extraction: since the selector contains the section info, extract it with a regex if needed for session labeling:
```python
import re
section_match = re.search(r'data-section="([^"]+)"', selector or '')
section_from_selector = section_match.group(1) if section_match else section_name
```

### Step 8: Update `remove_element()` (lines 1776–1839)

Change:
```python
# OLD
element_id = data.get('element_id')
if not page_id or not element_id: ...
element = soup.find(attrs={'data-element-id': element_id})
```

To:
```python
# NEW
selector = data.get('selector')
if not page_id or not selector: ...
element = soup.select_one(selector)
```

### Step 9: Commit

```bash
git add editor_v2/api_views.py
git commit -m "feat: switch all editor API endpoints from element_id to CSS selector addressing"
```

---

## Task 4: Backend AI services — `refine_element_only()` with data-target

**Files:**
- Modify: `ai/services.py` (lines 1298–1467)

### Step 1: Update method signature

```python
# OLD
def refine_element_only(self, page_id, section_name, element_id, instructions, ...)

# NEW
def refine_element_only(self, page_id, selector, instructions, ...)
```

Remove `section_name` and `element_id` params — derive everything from `selector`.

### Step 2: Update element extraction

```python
# OLD
section_el = soup.find('section', attrs={'data-section': section_name})
element_el = section_el.find(attrs={'data-element-id': element_id})

# NEW
element_el = soup.select_one(selector)
if not element_el:
    raise ValueError(f"Element not found for selector: {selector}")
# Extract section from the element's ancestor
section_el = element_el.find_parent('section', attrs={'data-section': True})
if not section_el:
    raise ValueError(f"Element is not inside a data-section")
section_name = section_el['data-section']
```

### Step 3: Add data-target marker before sending to LLM

```python
# Mark the target element for the LLM
element_el['data-target'] = 'true'
section_html = str(section_el)
element_html = str(element_el)
# Remove marker from the soup (don't persist it)
del element_el['data-target']
```

### Step 4: Update prompt call

```python
# OLD
system_prompt, user_prompt = PromptTemplates.get_element_refinement_prompt(
    ..., element_id=element_id, element_html=element_html, ...
)

# NEW
system_prompt, user_prompt = PromptTemplates.get_element_refinement_prompt(
    ..., element_html=element_html, ...
)
```

Note: The prompt no longer needs `element_id` — it references `data-target="true"` instead.

### Step 5: Update multi-option validation

```python
# OLD
opt_el = opt_soup.find(attrs={'data-element-id': element_id})

# NEW
opt_el = opt_soup.find(attrs={'data-target': 'true'})
if opt_el:
    del opt_el['data-target']  # strip marker before returning
```

### Step 6: Update single-option validation

```python
# OLD
target_el = result_soup.find(attrs={'data-element-id': element_id})

# NEW
target_el = result_soup.find(attrs={'data-target': 'true'})
if target_el:
    del target_el['data-target']  # strip marker
```

### Step 7: Commit

```bash
git add ai/services.py
git commit -m "feat: refine_element_only uses CSS selector + data-target marker"
```

---

## Task 5: Frontend selection.js — remove snap-to-element-id

**Files:**
- Modify: `editor_v2/static/editor_v2/js/modules/selection.js`

### Step 1: Update imports

```javascript
// OLD
import { $, getContentWrapper, getAncestors, getTagLabel, isEditable, getElementId } from '../lib/dom.js';

// NEW
import { $, getContentWrapper, getAncestors, getTagLabel, isEditable, getCssSelector } from '../lib/dom.js';
```

### Step 2: Remove snap-to-element-id in `onContentClick()` (line 113)

```javascript
// OLD
const target = e.target.closest('[data-element-id], [data-section]') || e.target;

// NEW — select whatever the user clicked (any element is now editable)
const target = e.target;
```

### Step 3: Update breadcrumb IDs to use CSS selectors

In `updateBreadcrumbs()` (line 65):
```javascript
// OLD
const id = getElementId(crumb.el);
return `<span class="ev2-breadcrumb${active}" data-crumb-id="${id}">${crumb.label}</span>${sep}`;

// NEW
const sel = getCssSelector(crumb.el) || '';
return `<span class="ev2-breadcrumb${active}" data-crumb-selector="${sel}">${crumb.label}</span>${sep}`;
```

In `onBreadcrumbClick()` (lines 127–137):
```javascript
// OLD
const id = crumb.dataset.crumbId;
if (!id) return;
const target = wrapper.querySelector(`[data-element-id="${id}"]`) || document.getElementById(id);

// NEW
const sel = crumb.dataset.crumbSelector;
if (!sel) return;
const target = document.querySelector(sel);
```

### Step 4: Commit

```bash
git add editor_v2/static/editor_v2/js/modules/selection.js
git commit -m "feat: selection.js uses CSS selectors, removes snap-to-element-id"
```

---

## Task 6: Frontend sidebar.js — use CSS selector

**Files:**
- Modify: `editor_v2/static/editor_v2/js/modules/sidebar.js`

### Step 1: Update imports (line 3)

```javascript
// OLD
import { $, $$, getElementId, isTextElement, getTransVar, getSections, getTagLabel } from '../lib/dom.js';

// NEW
import { $, $$, getCssSelector, isTextElement, getTransVar, getSections, getTagLabel } from '../lib/dom.js';
```

### Step 2: Update Content tab — `renderTextField()` (lines 33–52)

```javascript
// OLD
const elId = getElementId(selectedEl);
...
const fieldKey = transVar || elId.replace(/-/g, '_');
...
html += `<input ... data-element-id="${esc(elId)}" ... />`;

// NEW
const selector = getCssSelector(selectedEl) || '';
...
const fieldKey = transVar || '';  // only use transVar — no ID fallback
...
html += `<input ... data-selector="${esc(selector)}" ... />`;
```

For `renderTextField`, if the element has a `{{ trans.xxx }}` variable, use that as `fieldKey`. If not, use the empty string — the content change event will carry the `selector` for the backend to identify the element.

Similarly update `renderImageFields()` and `renderLinkFields()` — replace `data-element-id="${esc(elId)}"` with `data-selector="${esc(selector)}"` on all inputs.

### Step 3: Update `onContentInput()` (lines 94–114)

```javascript
// OLD
const elId = input.dataset.elementId;
events.emit('change:attribute', { type: 'attribute', elementId: elId, ... });
events.emit('change:content', { type: 'content', elementId: elId, ... });

// NEW
const selector = input.dataset.selector;
events.emit('change:attribute', { type: 'attribute', selector, ... });
events.emit('change:content', { type: 'content', selector, ... });
```

### Step 4: Update Design tab — `renderDesignTab()` (line 139, 238)

```javascript
// OLD
const elId = getElementId(selectedEl);
...
<textarea ... data-element-id="${esc(elId)}">

// NEW
const selector = getCssSelector(selectedEl) || '';
...
<textarea ... data-selector="${esc(selector)}">
```

Update the class change handler (line 251):
```javascript
// OLD
events.emit('change:classes', { type: 'classes', elementId: elId, ... });

// NEW
events.emit('change:classes', { type: 'classes', selector, ... });
```

Update `emitStyleChange()` and `emitAttrChange()` (lines 371–397):
```javascript
// OLD
function emitStyleChange(elementId, applyFn) { ... elementId, ... }
function emitAttrChange(elementId, attr, value) { ... elementId, ... }

// NEW
function emitStyleChange(selector, applyFn) { ... selector, ... }
function emitAttrChange(selector, attr, value) { ... selector, ... }
```

And all call sites that pass `elId` to these functions.

### Step 5: Update Structure tab — `renderStructureTab()` (lines 451–505)

```javascript
// OLD
const selectedId = selectedEl ? getElementId(selectedEl) : null;
...
const sectionId = getElementId(section);
const isCurrent = sectionId === selectedId;
html += `... data-tree-id="${esc(sectionId)}" ...`;

// NEW
const selectedSel = selectedEl ? getCssSelector(selectedEl) : null;
...
const sectionSel = getCssSelector(section) || '';
const isCurrent = sectionSel === selectedSel;
html += `... data-tree-selector="${esc(sectionSel)}" ...`;
```

Same for child and grandchild elements.

Update `onTreeClick()` (lines 507–517):
```javascript
// OLD
const id = item.dataset.treeId;
const el = document.querySelector(`[data-element-id="${id}"]`) || document.getElementById(id);

// NEW
const sel = item.dataset.treeSelector;
if (!sel) return;
const el = document.querySelector(sel);
```

### Step 6: Commit

```bash
git add editor_v2/static/editor_v2/js/modules/sidebar.js
git commit -m "feat: sidebar.js uses CSS selectors for all element addressing"
```

---

## Task 7: Frontend changes.js — use CSS selector

**Files:**
- Modify: `editor_v2/static/editor_v2/js/modules/changes.js`

### Step 1: Update `changeKey()` (line 10–12)

```javascript
// OLD
function changeKey(c) {
    return `${c.elementId}:${c.type}:${c.attribute || ''}`;
}

// NEW
function changeKey(c) {
    return `${c.selector}:${c.type}:${c.attribute || ''}`;
}
```

### Step 2: Update `findElement()` (lines 21–23)

```javascript
// OLD
function findElement(elementId) {
    return document.querySelector(`[data-element-id="${elementId}"]`);
}

// NEW
function findElement(selector) {
    return selector ? document.querySelector(selector) : null;
}
```

### Step 3: Update `applyToDOM()` (lines 25–35)

```javascript
// OLD
const el = findElement(change.elementId);

// NEW
const el = findElement(change.selector);
```

### Step 4: Update `save()` API payloads (lines 137–165)

Content changes:
```javascript
// OLD
await api.post('/update-page-content/', {
    page_id: pageId,
    field_key: c.fieldKey,
    element_id: c.elementId,
    language: language,
    value: c.value,
});

// NEW
await api.post('/update-page-content/', {
    page_id: pageId,
    field_key: c.fieldKey,
    selector: c.selector,
    language: language,
    value: c.value,
});
```

Class changes:
```javascript
// OLD
await api.post('/update-page-classes/', {
    page_id: pageId,
    element_id: c.elementId,
    new_classes: c.value,
});

// NEW
await api.post('/update-page-classes/', {
    page_id: pageId,
    selector: c.selector,
    new_classes: c.value,
});
```

Attribute changes:
```javascript
// OLD
await api.post('/update-page-attribute/', {
    page_id: pageId,
    element_id: c.elementId,
    attribute: c.attribute,
    value: c.value,
    old_value: c.oldValue,
    tag_name: c.tagName,
});

// NEW
await api.post('/update-page-attribute/', {
    page_id: pageId,
    selector: c.selector,
    attribute: c.attribute,
    value: c.value,
    old_value: c.oldValue,
    tag_name: c.tagName,
});
```

### Step 5: Commit

```bash
git add editor_v2/static/editor_v2/js/modules/changes.js
git commit -m "feat: changes.js uses CSS selectors for element tracking and API calls"
```

---

## Task 8: Frontend context-menu.js — use CSS selector

**Files:**
- Modify: `editor_v2/static/editor_v2/js/modules/context-menu.js`

### Step 1: Update imports (line 6)

```javascript
// OLD
import { $, getContentWrapper, isTextElement, hasStoredElementId } from '../lib/dom.js';

// NEW
import { $, getContentWrapper, isTextElement, getCssSelector } from '../lib/dom.js';
```

### Step 2: Simplify `findRemovableElement()` → remove entirely

Currently walks up DOM to find nearest `hasStoredElementId()` ancestor. Since ALL elements are now addressable via CSS selectors, every element within a section is removable. Replace with a simpler check:

```javascript
/** Any element inside a section (but not the section itself) is removable. */
function isRemovable(el, section) {
    return el && el !== section && section.contains(el);
}
```

### Step 3: Update `buildItems()` (lines 33–77)

Replace all `hasStoredElementId` / `findRemovableElement` logic:

```javascript
function buildItems(el) {
    const items = [];
    const section = getSection(el);

    if (isTextElement(el)) {
        items.push({ label: 'Edit Text', icon: '✎', hint: 'Dbl-click', action: () => events.emit('inline-edit:trigger', { element: el }) });
    }
    items.push({ label: 'Edit Classes', icon: '◑', action: () => events.emit('sidebar:switch-tab', 'design') });

    if (section) {
        const name = section.getAttribute('data-section');
        const selector = getCssSelector(el);

        items.push(null); // separator

        // AI refine — available for any element (not the section itself)
        if (selector && el !== section) {
            items.push({ label: 'AI Refine Element', icon: '✦', action: () => events.emit('context:ai-refine', { section: name, selector }) });
        }
        items.push({ label: 'AI Refine Section', icon: '✦', action: () => events.emit('context:ai-refine', { section: name }) });

        items.push(null); // separator

        // Insert section
        items.push({ label: 'Insert Section Before', icon: '+', action: () => insertBefore(name) });
        items.push({ label: 'Insert Section After', icon: '+', action: () => insertAfterSection(name) });

        items.push(null); // separator

        // Remove — any element inside section is removable
        if (isRemovable(el, section)) {
            const label = 'Remove Element';
            items.push({ label, icon: '✕', cls: 'danger', action: () => confirmRemoveElement(selector) });
        }
        items.push({ label: 'Remove Section', icon: '✕', cls: 'danger', action: () => confirmRemoveSection(name) });
    }

    items.push(null);
    items.push({ label: 'Copy Element HTML', icon: '⎘', action: () => navigator.clipboard.writeText(el.outerHTML) });
    if (section && section !== el) {
        items.push({ label: 'Select Section', icon: '▢', action: () => events.emit('selection:request', section) });
    }
    return items;
}
```

### Step 4: Update `confirmRemoveElement()` and `removeElement()` to use selector

```javascript
function confirmRemoveElement(selector) {
    if (!confirm('Remove this element? This can be undone via version history.')) return;
    removeElement(selector);
}

async function removeElement(selector) {
    try {
        const res = await api.post('/remove-element/', {
            page_id: config().pageId,
            selector: selector,
        });
        if (res.success) {
            window.location.reload();
        } else {
            alert('Failed to remove element: ' + (res.error || 'Unknown error'));
        }
    } catch (err) {
        alert('Failed to remove element: ' + (err.message || err));
    }
}
```

### Step 5: Commit

```bash
git add editor_v2/static/editor_v2/js/modules/context-menu.js
git commit -m "feat: context-menu.js uses CSS selectors, every element is actionable"
```

---

## Task 9: Frontend ai-panel.js — use CSS selector

**Files:**
- Modify: `editor_v2/static/editor_v2/js/modules/ai-panel.js`

### Step 1: Update imports (line 5)

```javascript
// OLD
import { $, hasStoredElementId } from '../lib/dom.js';

// NEW
import { $, getCssSelector, getElementLabel } from '../lib/dom.js';
```

### Step 2: Update state variable (line 16)

```javascript
// OLD
let currentElementId = null;

// NEW
let currentSelector = null;
```

### Step 3: Update selection handler (lines 41–56)

```javascript
// OLD
const elId = (!isSection && el && hasStoredElementId(el)) ? el.getAttribute('data-element-id') : null;
currentElementId = elId;
if (isSection && sectionName) {
    activeScope = 'section';
} else if (elId) {
    activeScope = 'element';
}

// NEW
const selector = (!isSection && el) ? getCssSelector(el) : null;
currentSelector = selector;
if (isSection && sectionName) {
    activeScope = 'section';
} else if (selector) {
    activeScope = 'element';
}
```

### Step 4: Update context:ai-refine handler (lines 57–62)

```javascript
// OLD
currentElementId = data?.elementId || null;
activeScope = data?.elementId ? 'element' : 'section';

// NEW
currentSelector = data?.selector || null;
activeScope = data?.selector ? 'element' : 'section';
```

### Step 5: Update `buildScopeSelect()` (lines 213–214)

```javascript
// OLD
if (currentElementId) {
    options += `<option value="element"${activeScope === 'element' ? ' selected' : ''}>Element: ${esc(currentElementId)}</option>`;
}

// NEW
if (currentSelector) {
    // Show human-readable label, not the raw selector
    const el = document.querySelector(currentSelector);
    const label = el ? getElementLabel(el) : 'element';
    options += `<option value="element"${activeScope === 'element' ? ' selected' : ''}>Element: ${esc(label)}</option>`;
}
```

### Step 6: Update `send()` — validation and API calls (lines 257, 266, 284–301)

Validation:
```javascript
// OLD
if (activeScope === 'element' && (!currentElementId || !currentSection)) return;

// NEW
if (activeScope === 'element' && !currentSelector) return;
```

Scope label:
```javascript
// OLD
if (activeScope === 'element') scopeLabel = currentElementId;

// NEW
if (activeScope === 'element') scopeLabel = 'element';
```

Element API call:
```javascript
// OLD
res = await api.post('/refine-multi/', {
    page_id: config().pageId,
    scope: 'element',
    section_name: currentSection,
    element_id: currentElementId,
    instructions: text,
    ...
});

// NEW
res = await api.post('/refine-multi/', {
    page_id: config().pageId,
    scope: 'element',
    selector: currentSelector,
    instructions: text,
    ...
});
```

### Step 7: Update `applyResult()` — apply-option call (lines 373–378)

```javascript
// OLD
await api.post('/apply-option/', {
    page_id: config().pageId,
    scope: pendingScope,
    section_name: currentSection,
    element_id: currentElementId,
    html: chosen.html,
});

// NEW
await api.post('/apply-option/', {
    page_id: config().pageId,
    scope: pendingScope,
    section_name: currentSection,
    selector: currentSelector,
    html: chosen.html,
});
```

### Step 8: Update live preview functions (lines 432–478)

`showPreview()`:
```javascript
// OLD
} else if (pendingScope === 'element' && currentElementId) {
    const el = document.querySelector(`[data-element-id="${currentElementId}"]`);

// NEW
} else if (pendingScope === 'element' && currentSelector) {
    const el = document.querySelector(currentSelector);
```

`showMultiPreview()`:
```javascript
// OLD
if (pendingScope === 'element' && currentElementId) {
    const el = document.querySelector(`[data-element-id="${currentElementId}"]`);

// NEW
if (pendingScope === 'element' && currentSelector) {
    const el = document.querySelector(currentSelector);
```

`restorePreview()`:
```javascript
// OLD
} else if (pendingScope === 'element' && currentElementId) {
    const el = document.querySelector(`[data-element-id="${currentElementId}"]`);

// NEW
} else if (pendingScope === 'element' && currentSelector) {
    const el = document.querySelector(currentSelector);
```

### Step 9: Update `destroy()` reset (line 69)

```javascript
// OLD
currentSection = null; currentElementId = null;

// NEW
currentSection = null; currentSelector = null;
```

### Step 10: Commit

```bash
git add editor_v2/static/editor_v2/js/modules/ai-panel.js
git commit -m "feat: ai-panel.js uses CSS selectors for element targeting"
```

---

## Task 10: Update site_assistant — tools and prompts

**Files:**
- Modify: `site_assistant/tools/page_tools.py`
- Modify: `site_assistant/prompts.py`

### Step 1: Update `update_element_styles()` in page_tools.py (lines 73–103)

```python
# OLD
element_id = params.get('element_id')
if element_id:
    element = soup.find(attrs={'data-element-id': element_id})

# NEW
selector = params.get('selector')
element_id = params.get('element_id')  # keep for backward compat with section_name
if selector:
    element = soup.select_one(selector)
elif element_id:
    element = soup.find(attrs={'data-element-id': element_id})
```

### Step 2: Update `update_element_attribute()` in page_tools.py (lines 115–137)

```python
# OLD
element_id = params.get('element_id')
element = soup.find(attrs={'data-element-id': element_id})

# NEW
selector = params.get('selector')
element_id = params.get('element_id')  # backward compat
if selector:
    element = soup.select_one(selector)
elif element_id:
    element = soup.find(attrs={'data-element-id': element_id})
```

### Step 3: Update tool descriptions in prompts.py (lines 36–37)

```python
# OLD
- `update_element_styles` — Change CSS classes. Params: `{"element_id": "...", "new_classes": "..."}`
- `update_element_attribute` — Change href, src, etc. Params: `{"element_id": "...", "attribute": "href", "value": "/new-url/"}`

# NEW
- `update_element_styles` — Change CSS classes. Params: `{"selector": "section[data-section='hero'] > div > h1", "new_classes": "text-4xl font-bold"}`
- `update_element_attribute` — Change href, src, etc. Params: `{"selector": "section[data-section='hero'] > a", "attribute": "href", "value": "/new-url/"}`
```

### Step 4: Update page context builder in prompts.py (lines 122–129)

```python
# OLD
elements = soup.find_all(attrs={'data-element-id': True})
if elements:
    lines.append("\n### Editable Elements")
    for el in elements[:20]:
        eid = el['data-element-id']
        classes = ' '.join(el.get('class', []))[:60]
        lines.append(f"- `{eid}` ({el.name}): classes=`{classes}`")

# NEW — show sections and their key children
sections = soup.find_all('section', attrs={'data-section': True})
if sections:
    lines.append("\n### Page Sections")
    for sec in sections:
        sec_name = sec['data-section']
        lines.append(f"- `{sec_name}`: {len(list(sec.descendants))} elements")
```

### Step 5: Commit

```bash
git add site_assistant/tools/page_tools.py site_assistant/prompts.py
git commit -m "feat: site_assistant uses CSS selectors, remove data-element-id references"
```

---

## Task 11: Update CLAUDE.md and base.html cache busters

**Files:**
- Modify: `CLAUDE.md` (line 5 of HTML Generation Rules)
- Modify: `templates/base.html` (CSS and JS version bumps)

### Step 1: Update CLAUDE.md HTML Generation Rules

Remove rule 4:
```
4. **Use `data-element-id="unique_id"` on editable elements** — for inline editor
```

### Step 2: Bump CSS and JS cache versions in base.html

```html
<!-- CSS: v12 → v13 -->
<link href="{% static 'editor_v2/css/editor.css' %}?v=13" rel="stylesheet">

<!-- JS: v17 → v18 -->
<script type="module" src="{% static 'editor_v2/js/editor.js' %}?v=18"></script>
```

### Step 3: Commit

```bash
git add CLAUDE.md templates/base.html
git commit -m "docs: remove data-element-id from HTML rules, bump editor cache versions"
```

---

## Verification

1. Open any page with `?edit=v2`
2. **Click any element** — should select it (no snap-to-tagged-element behavior)
3. **Sidebar Content tab** — shows text field for text elements (with `{{ trans.xxx }}` if present)
4. **Sidebar Design tab** — shows CSS classes, edit them, save → changes persist
5. **Edit text** — change text in sidebar, save → translation JSON updated
6. **AI Refine Element** — right-click any element, AI Refine Element → generates 3 options → preview → apply
7. **AI Refine Section** — right-click section → works as before
8. **Remove Element** — right-click any element → Remove Element → element removed after confirm
9. **Remove Section** — right-click → Remove Section → section removed after confirm
10. **AI Panel** — select element, scope shows "Element: h1" (human label), send refinement → 3 options → apply
11. **Breadcrumbs** — click breadcrumb items → navigates to correct element
12. **Structure tab** — tree shows sections and children, click to navigate
13. **Generate new page** — AI should NOT produce `data-element-id` attributes
14. **Existing pages** — old pages with `data-element-id` still work (selectors address by DOM position, not by ID)
