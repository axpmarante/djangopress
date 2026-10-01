# Element-aware Design Panel — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** replace the editor's Design tab with a panel that adapts to the selected element, edits per screen size with a truthful preview, and writes clean Tailwind classes.

**Architecture:** three pure ES modules, then the UI on top, then an iframe preview and a shared restyle service.
- **Pure modules:**
  - `lib/class-model.js`: properties ↔ classes, effective values per screen, mobile-first writes with Elementor-style cascading.
  - `lib/element-types.js`: classifies the selected element.
  - `lib/design-controls.js`: the control definitions per type.
- **UI:** a new `modules/design-panel.js` renders the controls and emits the existing `change:classes` / `change:attribute` events, so saving, checkpoints, every-language writes and Undo keep working unchanged.
- **Server:**
  - a design-tokens endpoint feeds the swatches and fonts;
  - an `?ev2_frame=1` page mode plus a bridge give the true-width preview;
  - `core/services/restyle.py` is extracted from the assistant's `style_tools` and serves both the assistant and a new `restyle-similar` endpoint.

**Tech Stack:** Django 6 (engine `djangopress`), vanilla ES modules (no build), Tailwind Play CDN at runtime, Playwright for the browser harnesses.

**Spec:** `docs/plans/2026-10-01-design-panel-design.md` (approved 2026-10-01). Mockup: https://claude.ai/artifact/CxRgw6z2HeuZjdhdSskAmf

## Global Constraints

- **Branch:** `feature/design-panel`.
- **Python tests:** `cd ~/Documents/djangopress-sites/demo-ai-lab && .venv/bin/python manage.py test djangopress.<app>`.
- **JS harnesses:** pages under `src/djangopress/editor_v2/tests/js/`, served with `python3 -m http.server` from `src/djangopress/editor_v2` and opened with `playwright-cli`. The title must read `PASS n` (any `FAIL` fails the step).
- **Browser checks:** only on a demo copy (`demo-ai-eval`, temp server on port 8199), never on a client site. Undo anything a check saves.
- **Breakpoints:** md = 768, lg = 1024 (Tailwind v3 defaults; no config).
- **Writes are mobile-first:** base = mobile, `md:` when tablet ≠ mobile, `lg:` when desktop ≠ tablet. Classes of other properties are untouched and **order is preserved**.
- **Colours** are written as `[#HEX]` (uppercase); strength as `/NN`.
- **UI copy:** English.
- **Commits:** no `Co-Authored-By`; end with `Claude-Session: https://claude.ai/code/session_01WSpzVT1ezgnAA6UbDJmNtS`; no merge or push.
- **Cache-busting:** bump `editor.js?v=` and `editor.css?v=` in `templates/base.html` when JS/CSS change.

## Review Focus

1. **An element authored mobile-first with responsive classes** (`text-4xl md:text-6xl`): editing desktop changes desktop (and tablet, which shared its value), mobile stays at 36px.
2. **Changing padding-top on an element with `py-4`:** becomes `pt-* pb-4`-equivalent with no `p-*` and no lost bottom padding.
3. **An element with `text-[#C42014]` set to Gold from the swatches:** exactly one text colour class remains.
4. **Tablet/Mobile preview with unsaved edits:** the iframe shows them; saving and reloading keeps them.
5. **Apply to all similar while the page has unsaved edits:** the edits are saved first and nothing is lost; one Undo per page restores it.

---

### Task 1: Class model (`lib/class-model.js`)

**Files:**
- Create: `editor_v2/static/editor_v2/js/lib/class-model.js`
- Create: `editor_v2/tests/js/class_model_test.html`

**Interfaces (produces):**
- `PROPERTIES`: `{ [name]: { families: [...], kind: 'size'|'spacing'|'color'|'enum'|'number', ... } }`. Names used by later tasks:
  - text: `fontSize`, `fontWeight`, `fontFamily`, `lineHeight`, `letterSpacing`, `textAlign`, `textColor`, `textTransform`, `fontStyle`, `textDecoration`, `textShadow`, `maxWidth`;
  - spacing: `marginTop`, `marginBottom`, `marginX`, `paddingTop`, `paddingBottom`, `paddingX`;
  - surface: `bgColor`, `borderWidth`, `borderColor`, `borderStyle`, `borderRadius`, `shadow`, `opacity`, `display`;
  - grid/flex: `gridCols`, `gap`, `alignItems`, `justifyContent`;
  - size and image: `width`, `aspectRatio`, `objectFit`, `objectPosition`, `minHeight`, `grayscale`, `brightness`.
- `readValues(classList, prop, state='') → { mobile, tablet, desktop }`: values in px / hex / keyword, `null` = unset.
- `writeValue(classList, prop, device, value, state='') → string[]`: the new class list with Elementor cascading and mobile-first emission.
- `classesOf(classList, prop) → string[]`: the classes that belong to a property (used by Copy style).
- `isRuntimeClass` is reused from `lib/dom.js` (runtime classes are never read or written).

- [ ] **Step 1: Write the failing harness.** It follows the `components_test.html` pattern (`eq`, `PASS n` title). The cases (each one `eq`):
  - `readValues(['text-4xl','md:text-6xl'],'fontSize')` → `{mobile:36, tablet:60, desktop:60}`
  - `readValues(['text-[40px]','lg:text-[64px]'],'fontSize')` → `{mobile:40, tablet:40, desktop:64}`
  - `readValues(['max-md:text-[40px]','text-[64px]'],'fontSize')` → `{mobile:40, tablet:64, desktop:64}`
  - `writeValue(['text-4xl','md:text-6xl'],'fontSize','desktop',72)` → `['text-4xl','md:text-[72px]']`; tablet shared desktop's value and follows it, while mobile had its own (36) and stays.
  - `writeValue(['text-[40px]'],'fontSize','desktop',48)` → `['text-[48px]']`; there are no overrides, so every screen changes.
  - `writeValue(['text-[64px]'],'fontSize','mobile',40)` → `['text-[40px]','md:text-[64px]']`
  - `writeValue(['py-4','font-bold'],'paddingTop','desktop',24)` → `['pt-6','pb-4','font-bold']`
    - `py` is split into its two axes; order is kept, with the new classes at the old one's position.
  - `writeValue(['text-[#C42014]','uppercase'],'textColor','desktop','#E3A11C')` → `['text-[#E3A11C]','uppercase']`
  - `writeValue(['text-white'],'textColor','desktop','#E3A11C')` → `['text-[#E3A11C]']`; palette and hex colour classes are both recognised.
  - `readValues(['text-xl','text-[#14171B]'],'fontSize')` → `{mobile:20,tablet:20,desktop:20}`; size and colour share the `text-` prefix and must be told apart.
  - `readValues(['bg-[#C42014]','hover:bg-[#6B1712]'],'bgColor','hover')` → `{mobile:'#6B1712',tablet:'#6B1712',desktop:'#6B1712'}`
  - `writeValue(['bg-[#C42014]'],'bgColor','desktop','#14171B','hover')` → `['bg-[#C42014]','hover:bg-[#14171B]']`
  - `writeValue(['pt-0'],'paddingTop','desktop',22)` → `['pt-[22px]']`; a value that isn't a multiple of 4 becomes arbitrary.
  - `writeValue(['grid','grid-cols-3'],'gridCols','tablet',2)` → `['grid','grid-cols-2','lg:grid-cols-3']`
  - `writeValue(['hidden','md:block'],'display','mobile','block')` → `['block']`; base is mobile, and this removes the now-redundant `md:block`.
  - `writeValue(['ev2-selected','text-[40px]'],'fontSize','desktop',50)` keeps `ev2-selected` untouched.
- [ ] **Step 2:** serve the harness and open it in Playwright. Expected: the title is `FAIL …` (module missing).
- [ ] **Step 3: Implement.**
  - **Matching:** each property lists `families` as `{ re, toValue, fromValue, axis }`.
  - **Variants:** a class is split into its variant stack (`max-md:`, `md:`, `lg:`, `md:max-lg:`, `hover:`) and its utility.
  - **Screen windows:** each variant stack maps to the screens it covers:
    - base → all;
    - `md:` → tablet + desktop;
    - `lg:` → desktop;
    - `max-md:` → mobile;
    - `max-lg:` → mobile + tablet;
    - `md:max-lg:` → tablet.
  - **Effective values:** later, more specific variants win, as in CSS source order. Use Tailwind's own order: base < `md:` < `lg:`, with `max-*` applied after the min variants on their screens.
  - **Writing:** compute the current `{m, t, d}`, apply the cascade rule (spec §2), remove all classes of the property for that state, and emit base = m, then `md:` if t ≠ m, then `lg:` if d ≠ t. Insert at the index of the first removed class, else append.
  - **Spacing scale:** `n*4` px → `n` (and `0.5`, `1.5`, `2.5`, `3.5`); otherwise `[Npx]`.
  - **Font size scale:** xs 12, sm 14, base 16, lg 18, xl 20, 2xl 24, 3xl 30, 4xl 36, 5xl 48, 6xl 60, 7xl 72, 8xl 96, 9xl 128. Always write `[Npx]`.
- [ ] **Step 4:** rerun. Expected: `PASS 16`.
- [ ] **Step 5:** commit `feat(editor): class model that reads and writes responsive Tailwind values`.

### Task 2: Element types (`lib/element-types.js`)

**Files:**
- Create: `editor_v2/static/editor_v2/js/lib/element-types.js`
- Create: `editor_v2/tests/js/element_types_test.html`
- Create: `editor_v2/tests/fixtures/elements/types.html`

**Interfaces:** `elementType(el) → 'section'|'container'|'button'|'link'|'heading'|'text'|'image'|'other'`, using the rules in spec §1. Component roots return `'other'` (their Content panel handles them), via `findComponent` from `lib/components.js`.

- [ ] **Step 1:** a fixture with one example per type, each marked `data-expect="<type>"`. It must include:
  - a padded `<a class="px-6 py-3 bg-[#C42014]">` → button;
  - a bare `<a>` inside a `<p>` → link;
  - a `div.grid` with 3 children → container;
  - a `div` with 1 child → other;
  - an `<img>` → image;
  - a slider root → other.

  Then the harness loops over them.
- [ ] **Step 2:** run. Expected: `FAIL`.
- [ ] **Step 3:** implement. Container detection uses `getComputedStyle(el).display` (`grid`/`flex`/`inline-flex`) plus ≥ 2 element children that aren't runtime clones.
- [ ] **Step 4:** run. Expected: `PASS 8`.
- [ ] **Step 5:** commit.

### Task 3: Design tokens endpoint

**Files:**
- Modify: `editor_v2/api_views.py` (new view `design_tokens`), `editor_v2/urls.py` (`api/design-tokens/`, name `api_design_tokens`)
- Create: `editor_v2/design_tokens.py`
- Test: `editor_v2/tests/test_design_tokens.py`

**Interfaces:** `GET /editor-v2/api/design-tokens/` returns:
```json
{"success": true,
 "colors": [{"name": "Primary", "value": "#C42014"}, ...],
 "fonts": [{"role": "Headings", "family": "Fraunces"}, {"role": "Body", "family": "Inter Tight"}],
 "spacing": {"S": 40, "M": 64, "L": 104, "XL": 152},
 "buttonSizes": {"S": [10, 18, 13], "M": [14, 28, 15], "L": [18, 36, 17]}}
```

- [ ] **Step 1: Tests.**
  - Named SiteSettings colours come first, in field order, without duplicates (`primary_color == heading_color` → listed once).
  - Then the 8 most frequent `[#hex]` colours from active pages and header/footer, named by hex.
  - White and black are present once.
  - Fonts: heading and body, plus distinct `hN_font`.
  - `editor_required`: staff 200, anonymous 302/403.
- [ ] **Step 2:** run. Expected: errors (no URL).
- [ ] **Step 3:** implement `collect_tokens()` in `design_tokens.py`. Hex regex: `\[(#[0-9A-Fa-f]{6})\]` over `html_content_i18n` default-language copies and global sections. Uppercase it.
- [ ] **Step 4:** run. Expected: OK. Then the full `djangopress.editor_v2`.
- [ ] **Step 5:** commit.

### Task 4: Shared restyle service + `restyle-similar` endpoint

**Files:**
- Create: `core/services/restyle.py`
- Modify: `site_assistant/tools/style_tools.py` (call the service), `editor_v2/api_views.py` + `urls.py` (`api/restyle-similar/`, name `api_restyle_similar`)
- Test: `editor_v2/tests/test_restyle_similar.py`; keep `site_assistant/tests/test_site_styles.py` green

**Interfaces:**
- `restyle.find(tags, has_classes=(), exact_classes=None, text_contains='', pages=None, include_globals=False, lang=None) → [{'page'|'section', 'where', 'classes', 'tag'}]`
- `restyle.apply(tags, has_classes=(), exact_classes=None, add=(), remove=(), pages=None, include_globals=False, checkpoint=callable) → [{'label', 'count'}]`
- `exact_classes` matches the element's whole class list (order-insensitive, runtime classes ignored). That is the editor's "same tag and same class list".
- **Endpoint:** `POST {tag, classes: [original], add: [...], remove: [...], include_globals}`.
  - It checkpoints every changed page with `create_version(kind='checkpoint', change_summary='Apply to all similar', user=request.user)` and every global section with `create_version`.
  - It returns `{success, changed: [{label, count}], total}`.
  - It also has a `GET` variant that returns the counts only, for the button's "6 buttons on 4 pages".

- [ ] **Step 1: Tests.**
  - Exact-class match across 2 pages and 2 languages; another button with one extra class is not changed.
  - Header is changed only with `include_globals`.
  - Checkpoint created per changed page.
  - The `GET` count matches.
  - Staff only.
- [ ] **Step 2:** run. Expected: errors.
- [ ] **Step 3:** move the matching and writing loops from `style_tools.py` into `restyle.py`. `style_tools` then passes `checkpoint` via `changes.page_checkpoint(context, page)` / `global_section_checkpoint`.
- [ ] **Step 4:** run `djangopress.editor_v2` and `djangopress.site_assistant`. Expected: OK.
- [ ] **Step 5:** commit.

### Task 5: Panel framework (`modules/design-panel.js`) and controls

**Files:**
- Create: `editor_v2/static/editor_v2/js/modules/design-panel.js`, `editor_v2/static/editor_v2/js/lib/design-controls.js`
- Modify:
  - `modules/sidebar.js`: `renderDesignTab()` delegates to `renderDesignPanel(container, el)`. The section background image, overlay and video code moves into the section panel's Background group; behaviour is unchanged.
  - `modules/changes.js`: undo/redo for `classes` keeps runtime classes.
  - `css/editor.css`: panel styles from the mockup, `ev2-dp-*` prefix.
  - `templates/base.html`: version bump; `EDITOR_CONFIG.designTokensUrl`.
- Test: `editor_v2/tests/js/design_panel_test.html` (mounts the panel on fixtures with a stub `events`)

**Interfaces:**
- `design-controls.js`: `CONTROLS[type] = [{ group, more: bool, rows: [{ id, label, control: 'seg'|'slider'|'swatches'|'toggles'|'focal'|'text'|'box', prop, options?, min?, max?, step?, unit?, state? }] }]`, with every group and row from spec §1. Common groups are appended for every type.
- `design-panel.js`:
  - `renderDesignPanel(container, el)`;
  - device state, read from and set by `viewport.js`'s current mode;
  - **writing a value:** `writeValue` on the element's class list, sets `el.className` with runtime classes kept, then emits `change:classes {selector, value, oldValue}`;
  - **changed dot and reset:** the dot compares against the classes captured on first selection (`initialClasses` map by selector); reset writes that property's classes back.

- [ ] **Step 1: Harness tests.** Load the type fixture and the panel against the stub tokens, then:
  - a button shows groups `Button, Colours, Link, Spacing, Visibility & border`;
  - clicking `Size L` emits one `change:classes` whose value contains `py-[18px]` (or `py-4.5`) and `px-9`;
  - the `More options` count for headings reads `7`;
  - Reset restores the original class list;
  - the hover switch writes `hover:bg-[…]`;
  - runtime class `ev2-selected` survives;
  - section `Space top/bottom XL` writes `py-[152px]`.
- [ ] **Step 2:** run. Expected: `FAIL`.
- [ ] **Step 3:** implement the framework, the controls (seg / slider / swatches with Other colour / toggles / focal / text / box model) and every type's rows.
  - **Section background:** writes `bg-[#hex]` and removes the inline `background-color` (`change:attribute style`).
  - **Image / overlay:** reuse `parseBgImage` / `composeBgImage` and `image-picker:open {mode:'background'}`.
  - **Anchor:** edits the `id` attribute through `change:attribute`.
  - **Link URL and new tab:** edit `href` and `target`/`rel` via `change:attribute`.
- [ ] **Step 4:** run. Expected: `PASS 7`. Python `djangopress.editor_v2` still OK.
- [ ] **Step 5:** browser check on demo-ai-eval (8199):
  - select a heading, button, image, section and grid in turn; each shows its panel;
  - change one value per type and save; the page reloads with it;
  - Undo restores it.
- [ ] **Step 6:** commit.

### Task 6: True-width device preview (`?ev2_frame=1`)

**Files:**
- Modify:
  - `core/views.py` (or the page view's context): `ev2_frame` mode, allowed only for `editor_required` users, with `preview=true` honoured.
  - `templates/base.html`: in frame mode, no editor UI, but load `editor_v2/js/frame-bridge.js`.
  - `modules/viewport.js`: Tablet/Mobile show `<iframe class="ev2-device-frame">` of width 768/390 and hide `.editor-v2-content`.
- Create:
  - `editor_v2/static/editor_v2/js/frame-bridge.js`;
  - `editor_v2/static/editor_v2/js/modules/device-frame.js`, which owns the iframe, posts pending changes and receives selection.
- Test: `editor_v2/tests/test_frame_mode.py` (Python: staff gets the bridge and no editor UI; anonymous gets the normal page without the bridge).

**Interfaces:**
- **Parent → frame** (`postMessage`):
  - `{ev2: 'apply', changes: [{selector, type, value, attribute?}]}`;
  - `{ev2: 'select', selector}`.
- **Frame → parent:** `{ev2: 'clicked', selector}`, `{ev2: 'ready'}`.
- **Origin check:** same origin only.
- **Hidden elements:** in the frame, an element whose classes hide it on the frame's screen gets `style.setProperty('display', <its non-hidden display>, 'important')`, plus class `ev2-hidden-device` and `data-hidden-note`.

- [ ] **Step 1:** Python tests for frame mode (above). Run. Expected: FAIL.
- [ ] **Step 2:** implement the frame mode, the bridge and the device frame.
  - Inline edit, drag and structure actions in Tablet/Mobile show `alertDialog({title: 'Switch to Desktop to edit this'})`.
- [ ] **Step 3:** Python tests OK.
- [ ] **Step 4: browser check.**
  - Set mobile title size 40 on a desktop-64 heading. In the Mobile iframe it renders at 40 (`getComputedStyle` inside the frame); on Desktop it is 64. This holds before and after saving.
  - Hide an image on mobile: it shows hatched in the frame and is selectable.
- [ ] **Step 5:** commit.

### Task 7: Apply to all similar, Copy style, Reset (UI)

**Files:**
- Modify: `modules/design-panel.js`, `css/editor.css`
- Test: extend `design_panel_test.html`

- [ ] **Step 1: Harness tests.**
  - Copy style copies only the panel's properties' classes. The target keeps a non-panel class such as `js-hook`.
  - Reset element restores the initial classes.
- [ ] **Step 2:** run. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - **Apply to all similar:**
    - *Count:* `GET restyle-similar` with the initial classes fills "N … on M pages".
    - *Click:* saves pending changes (`saveNow`), then `POST`s the diff (initial → current classes), then reloads with a toast "Applied to N … on M pages", where Undo works per page.
  - **Copy style:** pick mode (cursor `copy`; Esc cancels); a click on an element of another type says so in a notice.
- [ ] **Step 4:** run the harness, then a browser check on demo-ai-eval:
  - Apply to all similar on a button; buttons change on the other pages;
  - Undo on this page reverts this page.
- [ ] **Step 5:** commit.

### Task 8: Docs, checklist, final checks

- [ ] **Docs:**
  - update the engine `CLAUDE.md` editor section (Design panel, class model, frame preview);
  - add `docs/evals/2026-10-01-design-panel-manual-tests.md`, which follows the chat checklist format and covers each type, devices, Apply to all, Copy, Reset and Undo.
- [ ] **Final checks:** full Python suite, all three JS harnesses `PASS`, version bump, commit.
