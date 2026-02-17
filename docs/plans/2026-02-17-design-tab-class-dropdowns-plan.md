# Design Tab — Tailwind Class Dropdowns Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add categorized Tailwind class dropdowns to the Design tab so users can discover and change valid CSS values without memorizing Tailwind's scale.

**Architecture:** A pure data module (`tailwind-classes.js`) defines category groups with prefix patterns and valid values. Sidebar's `renderDesignTab()` uses this data to render `<select>` dropdowns above the existing textarea. A parser splits the class string into recognized categories + unrecognized leftovers, and a builder reconstructs the string from dropdown selections. Both the dropdowns and textarea stay in sync via shared update logic.

**Tech Stack:** Vanilla ES modules (no build step), Tailwind CSS class names

---

### Task 1: Create the Tailwind classes data module

**Files:**
- Create: `editor_v2/static/editor_v2/js/lib/tailwind-classes.js`

**Step 1: Create the data module**

Create `editor_v2/static/editor_v2/js/lib/tailwind-classes.js` with:

```js
/**
 * Tailwind CSS class definitions for the Design tab dropdowns.
 * Pure data — no DOM logic.
 */

// --- Color palette ---

export const COLOR_FAMILIES = [
    'slate', 'gray', 'zinc', 'neutral', 'stone',
    'red', 'orange', 'amber', 'yellow', 'lime',
    'green', 'emerald', 'teal', 'cyan', 'sky',
    'blue', 'indigo', 'violet', 'purple', 'fuchsia',
    'pink', 'rose',
];

export const COLOR_SHADES = [
    '50', '100', '200', '300', '400', '500', '600', '700', '800', '900', '950',
];

/** Standalone color keywords (no shade suffix). */
export const COLOR_KEYWORDS = ['white', 'black', 'transparent', 'current'];

// --- Spacing scale (shared by padding, margin, gap) ---

const SPACING = [
    '0', 'px', '0.5', '1', '1.5', '2', '2.5', '3', '3.5', '4', '5', '6', '7', '8',
    '9', '10', '11', '12', '14', '16', '20', '24', '28', '32', '36', '40', '44',
    '48', '52', '56', '60', '64', '72', '80', '96',
];

const SPACING_WITH_AUTO = ['auto', ...SPACING];

// --- Category definitions ---

/**
 * Each category: { label, prefixes[], values[], type? }
 *
 * `prefixes` — Tailwind prefixes that map to this category.
 *   e.g. ['p', 'px', 'py', 'pt', 'pr', 'pb', 'pl'] for padding.
 *   The first prefix is the "canonical" one shown in the dropdown.
 *
 * `values` — the valid suffixes (after the dash).
 *
 * `type` — 'color' for two-select color pickers, 'default' (omit) for single select.
 */
export const CATEGORIES = [
    // --- Typography ---
    {
        group: 'Typography',
        items: [
            {
                label: 'Font Size',
                prefixes: ['text'],
                values: ['xs', 'sm', 'base', 'lg', 'xl', '2xl', '3xl', '4xl', '5xl', '6xl', '7xl', '8xl', '9xl'],
            },
            {
                label: 'Font Weight',
                prefixes: ['font'],
                values: ['thin', 'extralight', 'light', 'normal', 'medium', 'semibold', 'bold', 'extrabold', 'black'],
            },
            {
                label: 'Text Align',
                prefixes: ['text'],
                values: ['left', 'center', 'right', 'justify'],
            },
            {
                label: 'Text Color',
                prefixes: ['text'],
                type: 'color',
            },
        ],
    },
    // --- Spacing ---
    {
        group: 'Spacing',
        items: [
            {
                label: 'Padding',
                prefixes: ['p', 'px', 'py', 'pt', 'pr', 'pb', 'pl'],
                values: SPACING,
            },
            {
                label: 'Margin',
                prefixes: ['m', 'mx', 'my', 'mt', 'mr', 'mb', 'ml'],
                values: SPACING_WITH_AUTO,
            },
            {
                label: 'Gap',
                prefixes: ['gap', 'gap-x', 'gap-y'],
                values: SPACING,
            },
        ],
    },
    // --- Layout ---
    {
        group: 'Layout',
        items: [
            {
                label: 'Display',
                prefixes: [''],
                values: ['block', 'inline-block', 'inline', 'flex', 'inline-flex', 'grid', 'inline-grid', 'hidden'],
                exact: true,   // match the full class, not prefix-value
            },
            {
                label: 'Border Radius',
                prefixes: ['rounded'],
                values: ['none', 'sm', '', 'md', 'lg', 'xl', '2xl', '3xl', 'full'],
            },
            {
                label: 'Shadow',
                prefixes: ['shadow'],
                values: ['none', 'sm', '', 'md', 'lg', 'xl', '2xl', 'inner'],
            },
            {
                label: 'Opacity',
                prefixes: ['opacity'],
                values: ['0', '5', '10', '15', '20', '25', '30', '35', '40', '45', '50',
                         '55', '60', '65', '70', '75', '80', '85', '90', '95', '100'],
            },
        ],
    },
    // --- Background ---
    {
        group: 'Background',
        items: [
            {
                label: 'Background',
                prefixes: ['bg'],
                type: 'color',
            },
        ],
    },
];

// --- Lookup sets for disambiguation ---

/** Font size values — used to distinguish text-lg (size) from text-red-500 (color). */
export const FONT_SIZE_VALUES = new Set(
    CATEGORIES[0].items[0].values
);

/** Text align values — used to distinguish text-center (align) from text-sm (size). */
export const TEXT_ALIGN_VALUES = new Set(
    CATEGORIES[0].items[2].values
);

/** Display values — matched as exact class names (no prefix). */
export const DISPLAY_VALUES = new Set(
    CATEGORIES[2].items[0].values
);
```

**Step 2: Commit**

```bash
git add editor_v2/static/editor_v2/js/lib/tailwind-classes.js
git commit -m "Add Tailwind class definitions data module for Design tab dropdowns"
```

---

### Task 2: Add class parsing and building utilities

**Files:**
- Create: `editor_v2/static/editor_v2/js/lib/class-parser.js`

**Step 1: Create the parser module**

Create `editor_v2/static/editor_v2/js/lib/class-parser.js`:

```js
/**
 * Parse and build Tailwind class strings for the Design tab dropdowns.
 */

import {
    CATEGORIES, COLOR_FAMILIES, COLOR_SHADES, COLOR_KEYWORDS,
    FONT_SIZE_VALUES, TEXT_ALIGN_VALUES, DISPLAY_VALUES,
} from './tailwind-classes.js';

// Build a set of all color-family names for fast lookup
const COLOR_FAMILY_SET = new Set(COLOR_FAMILIES);
const COLOR_KEYWORD_SET = new Set(COLOR_KEYWORDS);

/**
 * Determine if a class like "text-red-500" is a color class.
 * Returns { family, shade } or null.
 */
function parseColorClass(prefix, cls) {
    // e.g. prefix='text', cls='text-red-500' → suffix='red-500'
    const suffix = cls.slice(prefix.length + 1); // +1 for the dash
    if (!suffix) return null;

    // Check keyword colors: text-white, bg-black, bg-transparent, text-current
    if (COLOR_KEYWORD_SET.has(suffix)) {
        return { family: suffix, shade: '' };
    }

    // Check family-shade: text-red-500
    const dashIdx = suffix.lastIndexOf('-');
    if (dashIdx === -1) return null;
    const family = suffix.slice(0, dashIdx);
    const shade = suffix.slice(dashIdx + 1);
    if (COLOR_FAMILY_SET.has(family) && COLOR_SHADES.includes(shade)) {
        return { family, shade };
    }
    return null;
}

/**
 * Parse a space-separated class string into:
 *   { matched: Map<categoryKey, { prefix, value, color? }>, unmatched: string[] }
 *
 * categoryKey = "group:label", e.g. "Typography:Font Size"
 */
export function parseClasses(classString) {
    const tokens = classString.split(/\s+/).filter(Boolean);
    const matched = new Map();
    const claimed = new Set();

    for (const group of CATEGORIES) {
        for (const cat of group.items) {
            const key = `${group.group}:${cat.label}`;

            if (cat.exact) {
                // Display — match full class name
                for (const cls of tokens) {
                    if (cat.values.includes(cls) && !claimed.has(cls)) {
                        matched.set(key, { prefix: '', value: cls });
                        claimed.add(cls);
                        break;
                    }
                }
                continue;
            }

            for (const prefix of cat.prefixes) {
                if (matched.has(key)) break;
                for (const cls of tokens) {
                    if (claimed.has(cls)) continue;

                    if (cat.type === 'color') {
                        // Color category — must start with prefix-
                        if (!cls.startsWith(prefix + '-')) continue;
                        // Disambiguate text- prefix: skip if it's a font size or alignment
                        if (prefix === 'text') {
                            const afterDash = cls.slice(5); // 'text-'.length = 5
                            if (FONT_SIZE_VALUES.has(afterDash)) continue;
                            if (TEXT_ALIGN_VALUES.has(afterDash)) continue;
                        }
                        const color = parseColorClass(prefix, cls);
                        if (color) {
                            matched.set(key, { prefix, value: cls, color });
                            claimed.add(cls);
                            break;
                        }
                    } else {
                        // Non-color category
                        for (const val of cat.values) {
                            const expected = val === '' ? prefix : `${prefix}-${val}`;
                            if (cls === expected) {
                                // Disambiguate text- prefix
                                if (prefix === 'text' && cat.label === 'Font Size' && TEXT_ALIGN_VALUES.has(val)) continue;
                                if (prefix === 'text' && cat.label === 'Text Align' && FONT_SIZE_VALUES.has(val)) continue;
                                matched.set(key, { prefix, value: val, fullClass: cls });
                                claimed.add(cls);
                                break;
                            }
                        }
                        if (matched.has(key)) break;
                    }
                }
                if (matched.has(key)) break;
            }
        }
    }

    const unmatched = tokens.filter(cls => !claimed.has(cls));
    return { matched, unmatched };
}

/**
 * Build a class string from dropdown selections + unmatched classes.
 *
 * @param {Map<string, { prefix, value, color? }>} matched
 * @param {string[]} unmatched
 * @returns {string}
 */
export function buildClassString(matched, unmatched) {
    const parts = [...unmatched];

    for (const [key, entry] of matched) {
        if (!entry || entry.value === '') continue; // "None" selected

        // Find the category definition to check if it's exact
        const [groupName, catLabel] = key.split(':');
        const group = CATEGORIES.find(g => g.group === groupName);
        const cat = group?.items.find(i => i.label === catLabel);

        if (cat?.exact) {
            parts.push(entry.value);
        } else if (cat?.type === 'color') {
            const { family, shade } = entry.color || {};
            if (family) {
                if (COLOR_KEYWORD_SET.has(family)) {
                    parts.push(`${entry.prefix}-${family}`);
                } else if (shade) {
                    parts.push(`${entry.prefix}-${family}-${shade}`);
                }
            }
        } else {
            if (entry.value === '' && entry.prefix) {
                // Bare prefix class like "rounded" or "shadow"
                parts.push(entry.prefix);
            } else {
                parts.push(`${entry.prefix}-${entry.value}`);
            }
        }
    }

    return parts.join(' ');
}
```

**Step 2: Commit**

```bash
git add editor_v2/static/editor_v2/js/lib/class-parser.js
git commit -m "Add class parsing and building utilities for Design tab dropdowns"
```

---

### Task 3: Add CSS for class dropdowns

**Files:**
- Modify: `editor_v2/static/editor_v2/css/editor.css`

**Step 1: Add styles after the existing Design Tab section (~line 1329)**

Add these styles after the existing `.ev2-btn-sm-primary:hover` rule in the Design tab CSS section:

```css
/* --------------------------------------------------------------------------
   Design Tab — Tailwind Class Dropdowns
   -------------------------------------------------------------------------- */
.ev2-class-group {
  margin-bottom: 14px;
}

.ev2-class-group-label {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--ev2-text-faint);
  margin-bottom: 6px;
}

.ev2-class-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 5px;
}

.ev2-class-row label {
  font-size: 12px;
  color: var(--ev2-text-secondary);
  white-space: nowrap;
  min-width: 80px;
}

.ev2-class-select {
  flex: 1;
  font-size: 12px;
  padding: 4px 6px;
  border: 1px solid var(--ev2-border);
  border-radius: var(--ev2-radius);
  background: var(--ev2-bg);
  color: var(--ev2-text);
  font-family: var(--ev2-font);
  cursor: pointer;
  max-width: 140px;
}

.ev2-class-select:focus {
  outline: none;
  border-color: var(--ev2-primary);
  box-shadow: 0 0 0 2px var(--ev2-primary-alpha);
}

.ev2-class-select:has(option[value=""]:checked) {
  color: var(--ev2-text-faint);
}

/* Color picker: two selects side by side */
.ev2-color-selects {
  display: flex;
  gap: 4px;
  flex: 1;
}

.ev2-color-selects .ev2-class-select {
  max-width: none;
}

.ev2-color-selects .ev2-class-select:first-child {
  flex: 1.2;
}

.ev2-color-selects .ev2-class-select:last-child {
  flex: 0.8;
}
```

**Step 2: Commit**

```bash
git add editor_v2/static/editor_v2/css/editor.css
git commit -m "Add CSS for Tailwind class dropdown rows in Design tab"
```

---

### Task 4: Render dropdowns in sidebar and wire up sync

**Files:**
- Modify: `editor_v2/static/editor_v2/js/modules/sidebar.js:1-3` (imports)
- Modify: `editor_v2/static/editor_v2/js/modules/sidebar.js:204-328` (renderDesignTab)

This is the main integration task. It modifies `renderDesignTab()` to insert the categorized dropdowns between the section background controls and the textarea.

**Step 1: Add imports at top of sidebar.js**

Add to the existing imports (line 1-3):

```js
import { CATEGORIES, COLOR_FAMILIES, COLOR_SHADES, COLOR_KEYWORDS } from '../lib/tailwind-classes.js';
import { parseClasses, buildClassString } from '../lib/class-parser.js';
```

**Step 2: Add dropdown rendering helper**

Add a new function `renderClassDropdowns(classes)` after the `esc()` function (around line 13). This function returns an HTML string:

```js
// --- Tailwind class dropdowns ---

function renderClassDropdowns(classes) {
    const { matched } = parseClasses(classes);
    let html = '';

    for (const group of CATEGORIES) {
        html += `<div class="ev2-class-group">`;
        html += `<div class="ev2-class-group-label">${esc(group.group)}</div>`;

        for (const cat of group.items) {
            const key = `${group.group}:${cat.label}`;
            const entry = matched.get(key);
            const dataKey = key; // stored in data-cat attribute

            html += `<div class="ev2-class-row">`;
            html += `<label>${esc(cat.label)}</label>`;

            if (cat.type === 'color') {
                // Two-select color picker
                const family = entry?.color?.family || '';
                const shade = entry?.color?.shade || '';
                const prefix = cat.prefixes[0];
                const isKeyword = ['white', 'black', 'transparent', 'current'].includes(family);

                html += `<div class="ev2-color-selects">`;
                // Family select
                html += `<select class="ev2-class-select" data-cat="${esc(dataKey)}" data-color="family" data-prefix="${esc(prefix)}">`;
                html += `<option value="">None</option>`;
                for (const kw of COLOR_KEYWORDS) {
                    html += `<option value="${kw}"${family === kw ? ' selected' : ''}>${kw}</option>`;
                }
                for (const f of COLOR_FAMILIES) {
                    html += `<option value="${f}"${family === f ? ' selected' : ''}>${f}</option>`;
                }
                html += `</select>`;
                // Shade select
                html += `<select class="ev2-class-select" data-cat="${esc(dataKey)}" data-color="shade" data-prefix="${esc(prefix)}"${isKeyword || !family ? ' disabled' : ''}>`;
                html += `<option value="">—</option>`;
                for (const s of COLOR_SHADES) {
                    html += `<option value="${s}"${shade === s ? ' selected' : ''}>${s}</option>`;
                }
                html += `</select>`;
                html += `</div>`;
            } else if (cat.exact) {
                // Display — exact match values
                const current = entry?.value || '';
                html += `<select class="ev2-class-select" data-cat="${esc(dataKey)}" data-exact="true">`;
                html += `<option value="">None</option>`;
                for (const v of cat.values) {
                    html += `<option value="${v}"${current === v ? ' selected' : ''}>${v}</option>`;
                }
                html += `</select>`;
            } else {
                // Standard prefix-value dropdown
                const current = entry?.value ?? '';
                const hasMatch = !!entry;
                // For categories with bare prefix (rounded, shadow), value='' means the bare prefix
                html += `<select class="ev2-class-select" data-cat="${esc(dataKey)}" data-prefix="${esc(cat.prefixes[0])}">`;
                html += `<option value="__none__"${!hasMatch ? ' selected' : ''}>None</option>`;
                for (const v of cat.values) {
                    const display = v === '' ? `${cat.prefixes[0]} (default)` : `${cat.prefixes[0]}-${v}`;
                    html += `<option value="${v}"${hasMatch && current === v ? ' selected' : ''}>${display}</option>`;
                }
                html += `</select>`;
            }

            html += `</div>`;
        }

        html += `</div>`;
    }

    return html;
}
```

**Step 3: Insert dropdowns into renderDesignTab()**

In `renderDesignTab()`, insert the dropdowns HTML **before** the CSS Classes textarea section. Replace lines 309-312:

```js
    // --- Tailwind class dropdowns ---
    html += '<div class="ev2-design-section" id="ev2-class-dropdowns">';
    html += renderClassDropdowns(classes);
    html += '</div>';

    // --- CSS Classes (always shown) ---
    html += `<div class="ev2-design-section"><label class="ev2-label">CSS Classes</label>
        <textarea class="ev2-textarea" id="ev2-classes-input" data-selector="${esc(selector)}">${esc(classes)}</textarea>
        <p class="ev2-hint">Space-separated Tailwind classes</p></div>`;
```

**Step 4: Add dropdown event binding**

After the existing textarea event binding (after line 328), add dropdown change handlers:

```js
    // --- Bind class dropdowns ---
    const dropdownContainer = container.querySelector('#ev2-class-dropdowns');
    if (dropdownContainer) {
        dropdownContainer.addEventListener('change', (e) => {
            const select = e.target.closest('.ev2-class-select');
            if (!select) return;

            // Re-parse current classes from the textarea
            const currentClasses = selectedEl.className.split(/\s+/).filter(c => !c.startsWith('ev2-')).join(' ');
            const { matched, unmatched } = parseClasses(currentClasses);

            const catKey = select.dataset.cat;
            const colorRole = select.dataset.color; // 'family' or 'shade' for color pickers

            if (colorRole) {
                // Color picker change
                const prefix = select.dataset.prefix;
                const row = select.closest('.ev2-class-row');
                const familySel = row.querySelector('[data-color="family"]');
                const shadeSel = row.querySelector('[data-color="shade"]');
                const family = familySel.value;
                const shade = shadeSel.value;
                const isKeyword = ['white', 'black', 'transparent', 'current'].includes(family);

                // Enable/disable shade select
                shadeSel.disabled = !family || isKeyword;

                if (!family) {
                    matched.delete(catKey);
                } else {
                    matched.set(catKey, {
                        prefix,
                        value: isKeyword ? `${prefix}-${family}` : `${prefix}-${family}-${shade || '500'}`,
                        color: { family, shade: isKeyword ? '' : (shade || '500') },
                    });
                    // If shade was empty, auto-select 500
                    if (!isKeyword && !shade) shadeSel.value = '500';
                }
            } else {
                // Standard or exact dropdown
                const val = select.value;
                if (val === '__none__' || val === '') {
                    matched.delete(catKey);
                } else {
                    const prefix = select.dataset.prefix || '';
                    const isExact = select.dataset.exact === 'true';
                    if (isExact) {
                        matched.set(catKey, { prefix: '', value: val });
                    } else {
                        const fullClass = val === '' ? prefix : `${prefix}-${val}`;
                        matched.set(catKey, { prefix, value: val, fullClass });
                    }
                }
            }

            // Rebuild and apply
            const newClasses = buildClassString(matched, unmatched);
            const ev2Classes = selectedEl.className.split(/\s+/).filter(c => c.startsWith('ev2-'));
            const oldValue = currentClasses;
            selectedEl.className = [...ev2Classes, ...newClasses.split(/\s+/).filter(Boolean)].join(' ');

            // Sync textarea
            if (textarea) textarea.value = newClasses;

            events.emit('change:classes', {
                type: 'classes', selector, value: newClasses, oldValue,
            });
        });
    }
```

**Step 5: Sync textarea → dropdowns**

Modify the existing textarea `input` handler to also re-render the dropdowns:

```js
    if (textarea) {
        textarea.addEventListener('input', () => {
            const newClasses = textarea.value;
            const ev2Classes = selectedEl.className.split(/\s+/).filter(c => c.startsWith('ev2-'));
            const oldValue = selectedEl.className.split(/\s+/).filter(c => !c.startsWith('ev2-')).join(' ');
            selectedEl.className = [...ev2Classes, ...newClasses.split(/\s+/).filter(Boolean)].join(' ');
            events.emit('change:classes', {
                type: 'classes', selector, value: newClasses, oldValue,
            });
            // Sync dropdowns
            if (dropdownContainer) {
                dropdownContainer.innerHTML = renderClassDropdowns(newClasses);
            }
        });
    }
```

**Step 6: Commit**

```bash
git add editor_v2/static/editor_v2/js/modules/sidebar.js
git commit -m "Add Tailwind class dropdowns to Design tab with textarea sync"
```

---

### Task 5: Manual testing checklist

No code changes — verify everything works in the browser.

**Test on:** `http://127.0.0.1:8000/<lang>/<page>/?edit=v2`

1. **Select a text element** (e.g. `<h1>`) → Design tab shows:
   - Grouped dropdowns with current values detected (Font Size, Font Weight, etc.)
   - Textarea below with full class string
2. **Change Font Size dropdown** from `text-4xl` to `text-6xl` → element updates live, textarea reflects new value
3. **Change Text Color** family to `red`, shade to `500` → `text-red-500` appears in textarea, element turns red
4. **Select "None"** on a dropdown → that class is removed from textarea and element
5. **Type in textarea** to add `underline` → dropdowns don't break, unrecognized class preserved
6. **Select a section** → background controls appear above the dropdowns, dropdowns still work
7. **Click Save** → changes persist after reload
8. **Edge case:** element with no recognized Tailwind classes → all dropdowns show "None", textarea has the raw classes
9. **Edge case:** element with `rounded` (bare prefix, no suffix) → Border Radius dropdown shows "rounded (default)"

**Commit (if any fixes needed).**
