# Editor Tabs Refresh Implementation Plan

> **For agentic workers:** executed natively (superpowers:executing-plans), TDD per task, one fresh review at the end.

**Goal:** Content, Structure and Images tabs as in the approved mockup.
**Architecture:**
- **Server:** five small verbs/endpoints in `editor_v2` (plus one AI service).
- **Client:**
  - a pure `lib/content-model.js`, tested in a harness;
  - three panel modules (`content-panel.js`, `structure-panel.js`, `images-panel.js`) that `sidebar.js` delegates to;
  - a `.ev2-cp/.ev2-sp/.ev2-mp` CSS block in `editor.css`.

**Spec:** `docs/plans/2026-10-02-editor-tabs-design.md`

## Global Constraints

- **Saving:**
  - text changes go through `change:content`; formatted text is never overwritten with `textContent`;
  - attribute changes go through `change:attribute`, class changes through `change:classes`;
  - structural verbs checkpoint, apply to every language and reload.
- **Access:** `editor_required` on the new endpoints, except describe-image, which is `superuser_required` (AI).
- **Tests:** Python tests run from demo-ai-lab (`.venv/bin/python manage.py test …`). JS harnesses live under `editor_v2/tests/js/` (title `PASS n`). The full suite is green before review.
- **Commits:** end with the `Claude-Session` line; no Co-Authored-By.

## Review Focus

1. **Formatted paragraph** (bold or link inside): the sidebar never wipes the formatting.
2. **Links across languages:** a Page link saved while editing EN is localised back into PT. External, `tel:` and `#anchor` links are unchanged in every language.
3. **Retag:** keeps the element's classes, attributes and children in every language, and refuses tags outside h1–h4/p.
4. **Drag to the same place:** a no-op, with no checkpoint spam.
5. **Images tab:** images inside slider clones are not counted twice, and an image that hasn't loaded yet isn't flagged as low resolution.

### Task 1: Server verbs and read endpoints

- **What:**
  - `update_page_element_attribute` localises internal `href`s per language;
  - `structure.retag_element(soup, selector, tag)` plus `POST api/retag-element/`;
  - `structure.place_section(soup, name, before)` plus a `before` parameter on `api/move-section/`;
  - `GET api/link-targets/`;
  - `GET api/page-copies/`.
- **Tests:** `editor_v2/tests/test_editor_tabs_api.py`:
  - a `/pt/reservas/` href saved from PT becomes `/en/book-a-table/` in EN;
  - an external href and `tel:` are the same in every language;
  - an EN-side edit is localised back into PT;
  - retag h2→h3 in both languages keeps the classes and the children;
  - retag to `div` is refused;
  - retag creates one checkpoint;
  - place_section before X, and to the end;
  - placing at the same position → `moved: False`, no checkpoint;
  - link-targets lists active pages with their URL in the editing language and their section names;
  - page-copies returns every language for a Page and for a NewsPost (content_type).
- **Commit:** `feat(editor): link localisation per language, retag and place-section verbs, link targets and page copies`

### Task 2: Describe the photo

- **What:** `ContentGenerationService.describe_image_alt(image_bytes, mime_type, languages) -> {lang: alt}` (vision, `image_analysis` model, JSON; action `analyze_images`). Plus `POST api/describe-image/ {selector, page_id|content_type_id+object_id}`:
  - resolves the img in the editing language;
  - gets the bytes from the SiteImage whose file name the src ends with, or fetches the URL (UA header, 10 s, ≤10 MB), but only when that src is in the page HTML;
  - writes the alt to the other languages (same selector, per language, one save);
  - returns `{alts, current}`.
- **Tests:** `test_describe_image.py` (LLM and fetch mocked):
  - the SiteImage path;
  - the URL path;
  - a src not on the page → 400;
  - other languages written, current not;
  - a non-superuser editor → refused.
- **Commit:** `feat(editor): describe a photo — alt text in every language from the image`

### Task 3: `lib/content-model.js` (pure)

- **Exports:**
  - `itemRole(el)`: eyebrow | heading | text | button | link | image | null;
  - `sectionItems(section)`: `[{el, role}]` in DOM order, skipping components and clones;
  - `describeItems(items, component)`: "Photo + title + 2 texts + 2 buttons";
  - `parseHref(href) -> {kind, value, message?}`;
  - `buildHref(kind, value, message) -> href`;
  - `imageQuality(img) -> {state: 'sharp'|'soft'|'unknown', natural, shown}`;
  - `hasFormatting(el)`;
  - `otherLanguageText(copyHtml, selector)`;
  - `isPlaceholder(img)`.
- **Harness:** `tests/js/content_model_test.html` with a fixture section that has an eyebrow, a heading, a formatted paragraph, a button, a WhatsApp link, an image, a slider and a runtime clone.
- **Commit:** `feat(editor): content model — roles, link kinds, image quality, other-language text`

### Task 4: Content panel

- **What:** `modules/content-panel.js` per spec §1. `sidebar.js` renderContentTab delegates to it, keeping the component card and the media collection. CSS block. The link picker uses `link-targets`; the other-language line uses `page-copies`, cached per page load and refreshed after `changes:saved`.
- **Harness:** `tests/js/content_panel_test.html` (fetch stubbed):
  - the section form lists roles and types into the page;
  - a formatted paragraph is read-only and offers inline editing;
  - picking Page → `change:attribute` with `/pt/reservas/`;
  - Phone → `tel:+351…`;
  - new tab → target and rel;
  - focus point → `change:classes` swaps `object-*`;
  - heading level → POST retag-element;
  - the EN line shows the copy's text.
- **Browser check** on demo-ai-eval.
- **Commit:** `feat(editor): Content tab — section form, roles, link picker, heading level, image card, other language`

### Task 5: Structure panel

- **What:** `modules/structure-panel.js` per spec §2. Drag uses native HTML5 DnD on section rows and computes `before`. Hide on mobile toggles `max-md:hidden` via `change:classes`. Search filters.
- **Harness:** `tests/js/structure_panel_test.html`:
  - rows and descriptions;
  - the selected section is open with its items;
  - a search filter;
  - a drop computes `before` (POST body);
  - hide on mobile emits the class change;
  - Header/Footer rows.
- **Commit:** `feat(editor): Structure tab — outline with names, actions, drag to reorder, hide on mobile`

### Task 6: Images panel

- **What:** rewrite `modules/images-panel.js` per spec §3.
- **Harness:** `tests/js/images_panel_test.html`:
  - counts per filter;
  - clones not counted;
  - an unloaded image is not flagged;
  - the inline card's alt edit emits `change:attribute`;
  - Generate emits `process-images:open`.
- **Commit:** `feat(editor): Images tab — status filters, alt captions, inline card, generate placeholders`

### Task 7: Docs, checklist, verification

- **What:**
  - the engine `CLAUDE.md` entry;
  - `docs/evals/2026-10-02-editor-tabs-manual-tests.md` (pt);
  - the full suite;
  - all harnesses;
  - the browser pass for each tab.
- **Commit:** `docs: editor tabs — Content, Structure, Images; manual checklist`
