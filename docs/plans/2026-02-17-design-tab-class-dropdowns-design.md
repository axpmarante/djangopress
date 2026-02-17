# Design Tab — Tailwind Class Dropdowns

## Problem

The Design tab shows a raw textarea with all CSS classes as a space-separated string. Users don't know what valid Tailwind options are available, making it hard to change values like font size, spacing, or colors without memorizing the Tailwind scale.

## Solution

Add categorized `<select>` dropdowns above the existing textarea. Each dropdown shows the valid Tailwind values for a specific property. Changing a dropdown updates the element's classes immediately and syncs the textarea. The textarea remains as a fallback for power users.

## Category Groups

### Typography
- **Font Size** — `text-{size}`: xs, sm, base, lg, xl, 2xl–9xl
- **Font Weight** — `font-{weight}`: thin, extralight, light, normal, medium, semibold, bold, extrabold, black
- **Text Align** — `text-{align}`: left, center, right, justify
- **Text Color** — `text-{family}-{shade}`: two-select picker (family + shade)

### Spacing
- **Padding** — `p-{n}`, `px-{n}`, `py-{n}`: 0, 0.5, 1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24
- **Margin** — `m-{n}`, `mx-{n}`, `my-{n}`: same scale + auto
- **Gap** — `gap-{n}`: same spacing scale

### Layout
- **Display** — block, inline-block, inline, flex, grid, hidden
- **Border Radius** — `rounded-{size}`: none, sm, (default), md, lg, xl, 2xl, 3xl, full
- **Shadow** — `shadow-{size}`: none, sm, (default), md, lg, xl, 2xl, inner
- **Opacity** — `opacity-{n}`: 0, 5, 10, 20, 25, 30, 40, 50, 60, 70, 75, 80, 90, 95, 100

### Background
- **Background Color** — `bg-{family}-{shade}`: two-select picker (family + shade)

## Color Picker

Color categories use a two-select row:
- First select: color family (slate, gray, zinc, neutral, stone, red, orange, amber, yellow, lime, green, emerald, teal, cyan, sky, blue, indigo, violet, purple, fuchsia, pink, rose, white, black)
- Second select: shade (50–950), disabled for white/black
- "None" option removes the color class

## UI Layout (top to bottom)

1. Element info (existing)
2. Background controls (existing — image, video, overlay — sections only)
3. **Class dropdowns** (new — grouped with subtle section headers)
4. CSS Classes textarea (existing — raw fallback, stays in sync)

Each dropdown row: label on left, `<select>` on right, compact single-line.

## Parsing

The `text-` prefix is ambiguous (size, alignment, color). Resolution order:
1. Alignment: left, center, right, justify
2. Font size: xs, sm, base, lg, xl, 2xl–9xl
3. Color: `text-{family}-{shade}` or `text-white`/`text-black`

Unrecognized classes pass through untouched — visible only in the textarea.

## Architecture

**New file: `editor_v2/static/editor_v2/js/lib/tailwind-classes.js`**
- Pure data module: category definitions, color families, shades, value scales
- No DOM logic

**Modified: `editor_v2/static/editor_v2/js/modules/sidebar.js`**
- `parseClasses(classString)` — maps classes to category → value, collects unrecognized
- `buildClassString(parsedMap, unrecognized)` — reconstructs full class string
- `renderClassDropdowns(container, classes)` — renders grouped dropdowns
- Dropdown `change` events update DOM + textarea + emit `change:classes`
- Textarea `input` event re-parses and updates dropdowns

**No server changes** — the existing `/editor-v2/api/update-page-classes/` API accepts a full class string.

## Sync Behavior

- Dropdown change → update element classes in DOM → update textarea → emit `change:classes`
- Textarea edit → re-parse → update dropdown selections → emit `change:classes`
- Both paths converge on the same save flow in `changes.js`
