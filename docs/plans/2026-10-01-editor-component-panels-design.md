# Editor v2 — Component Panels for Sliders, Testimonials and Galleries

**Date:** 2026-10-01
**Status:** Draft for review
**Repo:** djangopress (engine, `src/djangopress/editor_v2/`, `static/js/lightbox.js`, skills, `check_site`). No changes to djangopress-manager.
**Goal:** A non-technical editor selects a slider, a testimonial slider or a lightbox gallery and gets one panel for it: thumbnails of every item, drag to reorder, replace an image, add/remove items, and plain controls for the slider settings. The same panel works on every site because it reads the conventions the sites already use.

---

## Context

The inline editor has no notion of a component. The Content tab picks controls by tag name (`sidebar.js:renderContentTab`): an `<img>` inside a slide gets the same fields as any image, slides appear as a generic "N repeated items" group (add = exact copy, swap with neighbour, remove, each with a full page reload), and nothing edits `data-splide` (autoplay, effect, arrows, dots), lightbox captions (`data-alt`) or reaches slides that are not currently visible.

Measured on 2026-10-01: 19 local sites use Splide or `data-lightbox`; only 4 carry `data-media-collection` (the marker the AI component registry defines). The build-site fast path does not emit it. So recognition must be structural.

Bugs found while reading the code that affect this work:

1. **Clones in loop sliders.** Only `restoreSelection` uses the clone-aware `resolveSelector`; `sidebar.js` (thumbnails, child list, tree), `selection.js` (breadcrumb), `images-panel.js` and `changes.js` (undo/discard) use `document.querySelector`, which hits a Splide clone first in `type:"loop"` sliders.
2. **Runtime classes saved to the DB.** The Design tab strips only `ev2-*` classes, so saving a slide's classes stores Splide's `is-active` / `is-visible` / `is-prev` / `is-next`.
3. **Lightbox opens in edit mode.** `static/js/lightbox.js` binds clicks with no edit-mode guard.
4. **Alt overwritten in every language.** `update_page_attribute` applies `alt` to all language copies, erasing translated alt text.

### Decisions already taken

- HTML per language remains the single source of truth (2026-09-16). No block model, no catalogue, no presets. The panels are deterministic editors over existing HTML conventions.
- Approach A (2026-10-01): adapters recognise components by structure; `data-media-collection` is honoured as a hint when present. No new required annotation, no migration.
- First version covers image sliders/carousels, text sliders (testimonials) and lightbox galleries. Tabs, accordions and the marquee follow the same pattern later.
- New text typed in one language is auto-translated into the others on save.

---

## 1. Recognition — the adapter registry

New module `editor_v2/static/editor_v2/js/lib/components.js`, an ordered list of adapters with one interface:

```js
{
  kind: 'slider' | 'text-slider' | 'gallery',
  label: 'Slider',                       // shown in the panel heading
  match(el) -> rootEl | null,            // nearest component root containing el
  items(root) -> [itemEl],               // real items in order, runtime-injected nodes excluded
  preview(item) -> { thumb, text },      // thumbnail URL and/or first line of text
  fields(item) -> [{ key, label, control, read(item) }],   // per-item fields
  settings: [{ key, label, control, read(root), toOptions(value, opts) }]   // may be empty
}
```

**slider** — root is the nearest `.splide` ancestor. Items are `ul.splide__list > li.splide__slide` that are not runtime-injected (`isRuntimeInjected`: clones, arrows, pagination). Matches when most items contain an `<img>` and less than ~40 characters of visible text outside `alt`. Covers hero fades and photo carousels, single- and multi-item.

**text-slider** — same root and items; matches when most items are text (blockquote / paragraphs, no image or only a small avatar). Covers testimonials.

**gallery** — root is the nearest element that has two or more item children, where an item is a child that is, or contains exactly one, `a[data-lightbox] > img`. Items are those children in order.

**Hint:** for a `.splide` the slides decide (`slider` vs `text-slider`); `data-media-collection="lightbox"` lets a container with a single lightbox item count as a `gallery`.

**Every item has the same field model:** its first non-decorative `<img>` (if any), its lightbox link (if any), and its *text leaves* — the outermost elements whose children are only inline tags (`strong`, `em`, `span`, `a`, `br`, …) and that contain text. A leaf whose only child elements are `<br>` is editable in the panel; a leaf with inline formatting is shown read-only ("double-click it on the page to edit") so the panel never strips formatting. A survey of the 19 sites (2026-10-01) found most Splide sliders are text or card sliders (`div` per slide, some with an image) and lightbox links often carry caption overlays, so the kind only changes the heading, the add button and the settings, not the fields.

**Addressing:** the client sends `root` as a selector computed with clone-free indices (`getCssSelector`, which already skips runtime-injected nodes) plus an item **index**. Never an `nth-child` path into the slide list.

The Python side mirrors the same rules in `editor_v2/components.py` (`find_component(soup, root_selector, kind)`, `items(root, kind)`); stored HTML contains no Splide clones, so the server needs no clone filtering. A shared fixture set (below) keeps the two in step.

---

## 2. The panel

When the selection is inside a recognised component, the Content tab renders a **component card** first and the existing element fields below it. The generic repeat panel (`prependRepeatPanel`) is suppressed inside recognised components so the verbs are not offered twice.

Heading: `Slider · 5 images`, `Testimonials · 4`, `Gallery · 8`.

**Item list** — one row per item: drag handle, thumbnail or first line of text, index. The row that contains the current selection is highlighted. Clicking a row scrolls the page to the component and, for sliders, calls the mounted Splide instance's `go(i)` so hidden slides become reachable and clickable. Rows expand to show per-item fields:

| Kind | Per-item fields |
|---|---|
| slider | Replace image (existing picker), Alt text |
| text-slider | Quote / main text, Author / secondary line (the item's text elements in order; generic: every editable text leaf of the item, labelled by tag) |
| gallery | Replace image, Alt text, Caption (`data-alt` on the link) |

Each row has **Remove** (confirm; disabled at the minimum: 1 slide, or 2 gallery items unless the container carries `data-media-collection="lightbox"`, because a single item would no longer be recognised as a gallery). Text fields can't be emptied (an empty leaf would disappear from the field list and break index parity between languages) — remove the item instead.

**Add** — sliders and galleries: `+ Add images` opens the image picker in a new multi-select mode (library and upload); chosen images are inserted after the selected item (or at the end). Text sliders: `+ Add testimonial` opens a small inline form with the same fields as an item.

**Settings** (slider and text-slider only), read from and written to `data-splide`:

| Control | `data-splide` |
|---|---|
| Effect: Slide / Fade | `type`: `slide` or `loop` (Slide + Loop on) / `fade` |
| Loop | `type:"loop"` for slide; `rewind:true` for fade |
| Autoplay | `autoplay` |
| Seconds per slide | `interval` (ms) |
| Transition speed | `speed` (ms), slow / normal / fast → 1200 / 800 / 400 |
| Arrows | `arrows` |
| Dots | `pagination` |
| Pause on hover | `pauseOnHover` |
| Items per row: desktop / tablet / mobile | `perPage` and `breakpoints["1024"].perPage`, `breakpoints["768"].perPage` — shown only when the slider is multi-item (`perPage` > 1 or breakpoints present) and not fade |

Keys the panel does not know (`arrowPath`, `gap`, `focus`, …) are preserved untouched. If `data-splide` is not valid JSON the settings block shows "These settings can't be edited here" and the rest of the panel still works; the server refuses `set_settings` on an invalid attribute rather than overwriting it.

Out of scope: creating a new slider, styling slides (Design tab unchanged), tabs/accordion/marquee.

---

## 3. Saving — endpoint, languages, undo

**Endpoint:** `POST /editor-v2/api/component/`, `@editor_required`, body `{page_id | content_type_id+object_id, root, kind, op, args, lang}`. It runs through `_run_structural_verb`, so each operation writes a checkpoint (undo/redo covers it), applies to every language copy, and reports `skipped_languages` when a copy has drifted (component not found, or a different item count).

Operations (pure functions in `editor_v2/components.py`, each taking a component root Tag):

| op | args | Languages |
|---|---|---|
| `reorder` | `order: [int]` (a permutation of current indices) | all, identical |
| `remove` | `index` | all |
| `set_settings` | `settings: {…}` merged into the parsed `data-splide` | all |
| `replace_image` | `index, image: {id?, url, alt_i18n?}` | `src`, lightbox `href` and `srcset` removal in all; `alt` per language (see below) |
| `add_images` | `after, images: [{id?, url, alt_i18n?}]` | all; each new item is a clone of item `after` (or the last) with image, alt, `href`, `data-alt` rewritten |
| `add_text_item` | `after, fields: {key: text}` | all; typed text written in `lang`, translated into the others |
| `update_item` | `index, fields: {alt?, caption?, key: text}` | `lang` only (same rule as inline text editing) |

New items are always cloned from an existing item of the same component, so they keep the site's classes; ids are stripped (`strip_ids`).

**Per-language alt text:** when the picked image comes from the media library, each language takes `SiteImage.alt_text_i18n[lang]`; languages without one get the current-language alt translated. `replace_image` never overwrites a language's alt with another language's text. The existing attribute endpoint keeps its behaviour for other attributes but stops propagating `alt` across languages (bug 4).

**Translation:** `add_text_item` and missing alts use the existing `ContentGenerationService.translate_html` (`ai/services.py`) during the request; the client shows "Translating…". On failure the other languages keep the source text and the response lists `untranslated_languages`. Success toast: "Added · translated to EN (review)" with a link to the EN view; failure toast: "Not translated to EN — edit it there." No persistent "needs review" marker in the HTML.

**Applying in place:** the response includes `html` — the component root's new outer HTML for the current language. The client swaps the root, re-mounts Splide / lightbox for it, re-renders the panel and keeps the same item selected. Drag-and-drop sends one `reorder`. Settings changes are debounced (600 ms) and remount the slider so the effect is visible immediately. Any client-side failure falls back to the existing reload-and-reselect path.

**Pending inline edits:** before any component operation the client saves pending changes (`changes.save()`), because swapping the root would leave queued selectors stale. The existing structural verbs reload without doing this; they get the same guard.

---

## 4. Bug fixes in scope

1. All sidebar / selection / images-panel / changes lookups go through `resolveSelector` (clone-aware), not `document.querySelector`.
2. Class saving strips Splide runtime classes (`is-active`, `is-visible`, `is-prev`, `is-next`, `is-clone`) along with `ev2-*`.
3. `static/js/lightbox.js` does not open when the page is in edit mode (`document.body` / `.editor-v2-content` present or `window.EDITOR_CONFIG` set).
4. `alt` is no longer copied across languages by `update_page_attribute`.

---

## 5. Skills, AI registry and `check_site`

- `skills/djangopress-html-reference/SKILL.md` — new short section "Editable components": the three shapes the panel recognises (Splide structure with one image per image slide; text slides as blockquote + author line; lightbox items as sibling children each holding one `a[data-lightbox] > img`, caption in `data-alt`), `data-splide` must be valid JSON in single-quoted attribute, keep `data-media-collection` optional.
- `ai/utils/components/slider.py`, `carousel.py`, `lightbox.py` — examples aligned with those shapes; fix the selector prompt examples in `ai/utils/components/__init__.py` that use names that do not exist (`splide`, `alpine-tabs`, `alpine-accordion`).
- `check_site` — new check `components`: every `.splide` and every `data-lightbox` group matches an adapter (Python `components.py`), `data-splide` parses, item counts match across languages. Warning level.
- `skills/edit-site/SKILL.md` — one line: staff reorder/add/remove slides and gallery items themselves; don't assume order is fixed.
- `skills/djangopress-architecture/SKILL.md` and engine `CLAUDE.md` — the endpoint and the adapter registry.

---

## 6. Testing

- **Python unit** (`editor_v2/tests/test_components.py`): `find_component` / `items` on fixtures (hero fade slider, multi-item loop carousel, testimonials, lightbox grid with wrappers, lightbox grid of bare links, a `.splide` that is neither); each op on each kind; `set_settings` preserves unknown keys and handles invalid JSON; `add_images` clones classes and rewrites `href`/`data-alt`; per-language alt from `alt_text_i18n`.
- **Python API** (`editor_v2/tests/test_component_api.py`): endpoint applies to all languages, checkpoint created, drifted language reported, `update_item` touches only `lang`, translation mocked (success and failure), permission check.
- **Fixtures** live as HTML files shared by the Python tests and the browser check, so JS and Python recognition agree.
- **Browser check** (Playwright, on checkinfaro-v3 page 6 with `?edit=v2`): select a slide image → panel shows `Slider · N images`; drag reorder persists after reload; add two images; change Effect to Slide and see it remount; testimonials add in PT shows EN translation; gallery click does not open the lightbox.
- Existing suites (`test_structure.py`, `test_structural_api.py`, `test_history.py`) stay green.

---

## Files

| Area | Files |
|---|---|
| Client | new `js/lib/components.js`, new `js/modules/component-panel.js`; `sidebar.js` (card + suppress repeat panel), `image-picker.js` (multi-select), `lib/structural.js` (pending-save guard), `lib/dom.js` / `selection.js` / `images-panel.js` / `changes.js` (resolveSelector), `css/editor.css`; asset version bumps in `base.html` |
| Server | new `editor_v2/components.py`, endpoint in `editor_v2/api_views.py`, route in `editor_v2/urls.py`, alt fix in `update_page_attribute` |
| Site runtime | `static/js/lightbox.js` edit-mode guard |
| Checks / AI / docs | `core/management/commands/check_site.py`, `ai/utils/components/*`, skills listed above, `CLAUDE.md` |
