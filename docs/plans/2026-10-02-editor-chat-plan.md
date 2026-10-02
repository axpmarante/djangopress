# Editor Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (native, chosen for the Design panel and kept here). Steps use checkbox (`- [ ]`) syntax.

**Goal:** the editor Chat tab gives quick edits applied at once, or three real design directions built from the site's own design language, with compare/refine/apply-without-reload, cancel and reference images.

**Architecture:**
- **Server** (four new modules):
  - `ai/design_context.py`: what the site looks like;
  - `ai/design_check.py`: deterministic fixes on generated HTML;
  - `ai/directions.py`: three parallel generations;
  - `editor_v2/chat.py`: turn orchestration (quick vs explore).
- **Endpoints:** one new SSE endpoint plus a cancel endpoint, in `editor_v2/chat_views.py`.
- **Existing services:** they gain `page` / `base_html` / `direction` / `design_context` kwargs.
- **Client:** `ai-panel.js` is rewritten around two small pure helpers (`lib/chat-intent.js`, `lib/chat-preview.js`) that the browser harness can test.

**Tech stack:** Django 6, BeautifulSoup, Gemini via `LLMBase`, ES modules, SSE.

**Spec:** `docs/plans/2026-10-02-editor-chat-design.md`

## Global Constraints

- **Users:** the Chat is superuser-only (`@superuser_required`). UI copy is in English.
- **Saving:** every save goes through `editor_v2/ai_apply.py` (checkpoint, then the other languages). Undo = the editor's `history:undo`.
- **Old endpoints stay working:** `refine-multi/*`, `refine-page/stream`, `apply-option`. They are still used by the section inserter and page scope.
- **No new dependencies.** There is no build step.
- **Tests:**
  - Python tests run from `~/Documents/djangopress-sites/demo-ai-lab` with `.venv/bin/python manage.py test <label>`. The full suite is green before merge.
  - JS helpers are tested with the browser harnesses `editor_v2/tests/js/*_test.html` (title `PASS n`).
- **Evals:** only on `demo-ai-*` copies.
- **Commits:** end with `Claude-Session: https://claude.ai/code/session_01WSpzVT1ezgnAA6UbDJmNtS`. No Co-Authored-By.

## Review Focus

1. **A direction that fails or times out** must not lose the ones that arrived. Cancel mid-run keeps what is shown and leaves no stuck "running" UI (T3, T5, T6).
2. **News posts (non-Page editables):** the chat endpoint, the services, logging (`AICallLog.page` is a Page FK) and `apply-option` must all work (T3, T5).
3. **Attribute-only copy to other languages:** only when the visible text is the same. `alt`/`title`/`aria-label`/`placeholder` changes count as text, and so are translated (T4).
4. **Preview clones in the sidebar** (thumbnails/compare) must never carry `data-section`/`id`. Otherwise `document.querySelector('[data-section=x]')` and the editor's selection hit the clone (T6 harness).
5. **Apply without reload:** the swapped node is re-initialised (sliders) and the history buttons refreshed. A second Apply / Undo afterwards acts on the right node (browser check, T6).

---

### Task 1: Design context

**Files:**
- Create `src/djangopress/ai/design_context.py`
- Test `src/djangopress/ai/tests/test_design_context.py`

**Interfaces — produces:**
- `build_design_context(page, target_name=None, *, lang=None, query='') -> dict` with keys:
  - `colors: [{'name','value'}]`
  - `fonts: [{'role','family'}]`
  - `design_guide: str`
  - `references: [{'name','label','page','html'}]`
  - `vocabulary: [{'role','classes','count'}]`
  - `images: [{'id','url','alt'}]`
- `render_design_context(ctx) -> str`: the markdown block for prompts. It starts with `## Site design`.
- `matches_summary(ctx) -> {'colors': [hex ≤5], 'fonts': [family ≤2], 'references': [label ≤3]}`

**Rules:**
- **Colours and fonts:** come from `editor_v2.design_tokens.collect_tokens()`.
- **Reference candidates:**
  - the other sections on the page (the target is excluded);
  - the homepage's first section (`SiteSettings.homepage_id`, else the first active page), when the homepage is another page.
- **Reference selection:**
  - each candidate is scored by its number of distinct classes;
  - the home hero comes first, then the best two others (three at most);
  - each is capped at `REFERENCE_CAP = 6000` characters, with a `<!-- … cut -->` marker.
- **Labels:** the label is `data-section` turned to words, title case.
- **Vocabulary roles:** taken from all active pages plus global sections, in the default language. The most common class string per role:
  - `eyebrow` = p/span/div with `uppercase` + a `tracking-` class and text ≤ 40 characters;
  - `section title` = h2;
  - `body text` = p with text > 60 characters;
  - `primary button` = a/button with a `bg-` class and a `px-` class;
  - `text link` = an `a` with classes and no `bg-`;
  - `card` = div/article/li with a `p-`/`px-` class and one of `rounded`/`border`/`shadow`, containing an h3/h4;
  - `divider` = `hr` or an element with `h-px`/`h-[1px]`.
- **Library images:** `SiteImage(is_active=True)` with an image file. They are ranked by word overlap of `query` with title/alt/tags/description, then newest. At most 12.

- [ ] **Step 1: Write the failing tests** for:
  - references exclude the target, put the home hero first and are capped;
  - labels;
  - the vocabulary finds an eyebrow, a title and a button with counts;
  - images ranked by overlap and limited to 12;
  - `render_design_context` contains the reference HTML, the vocabulary lines and the image URLs;
  - `matches_summary` shape.

  Fixtures: a homepage with `hero` (rich classes) and a page with `sobre`, `eventos` (cards) and the target `contactos`. SiteImages are created with `SimpleUploadedFile`.
- [ ] **Step 2: Run** `manage.py test djangopress.ai.tests.test_design_context`. Expected: ImportError / FAIL.
- [ ] **Step 3: Implement** `design_context.py`.
- [ ] **Step 4: Run** the same command. Expected: OK.
- [ ] **Step 5: Commit** `feat(ai): design context — reference sections, design vocabulary, library images`.

### Task 2: Design check

**Files:**
- Create `src/djangopress/ai/design_check.py`
- Test `src/djangopress/ai/tests/test_design_check.py`

**Interfaces — produces:**
`check_and_fix(html, colors, fonts) -> {'html': str, 'notes': [str], 'why': str}`
- `colors` / `fonts` are the shapes from Task 1.

**Rules:**
- **WHY comment:** `<!-- WHY: … -->` anywhere → `why` (the first one), and every one is removed.
- **Chromatic Tailwind palette classes** (any variant prefix; utilities bg/text/border/from/via/to/ring/fill/stroke/divide/outline/decoration/accent/placeholder/shadow; hues red…rose; shades 50…950; optional `/NN`) → `<prefix><utility>-[#HEX]` with the nearest site colour among the chromatic site colours (saturation > 0.15). If the site has none, all colours are candidates.
- **Neutral Tailwind classes** (slate/gray/zinc/neutral/stone) → snapped only when a site colour is within `NEUTRAL_SNAP = 60` (redmean distance). Otherwise they are kept.
- **Palette approximation:** the shade colours are derived from the 500 value: mix with white for 50–400 (0.95, 0.9, 0.75, 0.6, 0.3) and with black for 600–950 (0.15, 0.3, 0.45, 0.6, 0.75).
- **Arbitrary hex** `[#xxxxxx]` not in the site colours:
  - distance < `HEX_SNAP = 40` → snapped;
  - otherwise a note `off-palette colour #XXXXXX`.
- **Fonts** `font-['X']` / `font-[X]` whose family is not a site font → the heading font on h1–h6 (or inside one), otherwise the body font. Note `font X → Y`.
- **Fonts, missing roles:** the heading font comes from the role `Headings`, else the first font; the body font from `Body`, else the first.
- **Placeholders:** `placehold.co` images → a note `N placeholder image(s)`.

- [ ] **Step 1: Write the failing tests:**
  - blue → the brand red;
  - `md:hover:bg-blue-600/80` keeps the variant and the opacity;
  - gray stays without a near neutral;
  - gray snaps when the site has a near grey;
  - near hex snapped, far hex noted;
  - foreign font on h2 → heading font, on p → body font;
  - WHY parsed and stripped;
  - placeholders counted;
  - the HTML is otherwise byte-stable (no reformatting of untouched markup beyond BeautifulSoup's).
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run.** Expected: OK.
- [ ] **Step 5: Commit** `feat(ai): design check — snap colours and fonts to the site, read the WHY line`.

### Task 3: Services accept page / base_html / direction / design_context; three directions in parallel

**Files:**
- Modify `src/djangopress/ai/services.py` (`refine_section_only`, `refine_element_only`)
- Modify `src/djangopress/ai/utils/prompts.py` (`get_section_refinement_prompt`, `get_element_refinement_prompt`)
- Create `src/djangopress/ai/directions.py`
- Test `src/djangopress/ai/tests/test_directions.py`

**Interfaces:**
- **Consumes:**
  - `build_design_context`, `render_design_context` (T1);
  - `check_and_fix` (T2).
- **Produces:**
  - new kwargs on the services `refine_section_only(...)` / `refine_element_only(...)`:
    - `page=None` (the object to use instead of `Page.objects.get(page_id)`);
    - `base_html=None` (replaces the target in the page HTML before prompting);
    - `direction=None` (`{'name','brief'}`);
    - `design_context=''` (the rendered block).

    `AICallLog.page` gets the page only if it is a `Page`.
  - prompt functions: the new kwargs `direction=None`, `design_context=''`.
    - When `direction` is given: a `## Direction` block plus the rule "Put `<!-- WHY: one sentence on how this fits the site -->` as the first child of the root element".
    - When `design_context` is given: it is appended to the user prompt, plus the rule "Reuse the site's design vocabulary and reference sections; prefer the listed library images over placeholders".
  - `ai/directions.py`:
    - `DIRECTIONS = [{'key':'refined','name':'Close to current','brief':…}, {'key':'bold','name':'Bolder','brief':…}, {'key':'layout','name':'New layout','brief':…}]`;
    - `generate_directions(page, scope, target, instructions, *, lang, history=None, base_html=None, images=None, context=None, on_option=None, is_cancelled=None, keys=None, model=None) -> list[dict]`. Each item is `{'key','name','html','why','notes'}` or `{'key','name','error'}`. `on_option(item)` is called as each one finishes (from the calling thread, in completion order). After cancel, no more `on_option`.
    - **Model:** `get_ai_model('generation')` for sections, `get_ai_model('refinement_element')` for elements, unless `model` is given.
    - **Prompt flags:** `skip_component_selection=True`.
    - **Each worker** closes its DB connection.

- [ ] **Step 1: Write the failing tests** (`ContentGenerationService.refine_section_only` is mocked by patching `djangopress.ai.directions.ContentGenerationService`):
  - three calls with the three different direction briefs and the same `design_context`;
  - one raising → the other two returned plus an error item;
  - `on_option` called three times;
  - `base_html` passed through;
  - `is_cancelled` true after the first → only one `on_option`;
  - the design check is applied (a blue class is snapped, `why` extracted).

  Prompt tests (no mocks):
  - `get_section_refinement_prompt(direction=…, design_context='## Site design …')` contains both blocks and the WHY rule, and not "Keep output concise";
  - with `multi_option=True` and no direction it is unchanged (still has the 3-variations block).

  Service tests with the LLM mocked:
  - `refine_section_only(page=newspost-like Page…, base_html=…)`: the prompt contains base_html in place of the stored section;
  - with a non-Page object (`NewsPost`), the call does not query `Page` and logs `page=None`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement** the prompts, the services and `directions.py`.
- [ ] **Step 4: Run** the new tests plus `djangopress.ai` and `djangopress.editor_v2`. Expected: OK.
- [ ] **Step 5: Commit** `feat(ai): three design directions in parallel, with the site's design context and check`.

### Task 4: Quick path — router without delegation, routing logs, attribute-only apply

**Files:**
- Modify `src/djangopress/ai/refinement_agent/agent.py`
- Modify `src/djangopress/ai/models.py` (the choice `refine_routing`, plus a migration)
- Modify `src/djangopress/editor_v2/ai_apply.py`
- Test `src/djangopress/ai/tests/test_refinement_routing.py` and `src/djangopress/editor_v2/tests/test_ai_apply.py` (append)

**Interfaces — produces:**
- `RefinementAgent.handle(..., delegate=True, page_object_ok=True, base_html=None)`:
  - when `delegate=False` and the agent would call `refine_with_ai` or fall back, it returns `{'delegate': True, 'assistant_message': str, 'routing_ms': int}` without generating;
  - `base_html` replaces the target HTML the agent edits;
  - every routing LLM call is logged with `log_ai_call(action='refine_routing', routing_tier=…, page=page if Page else None, section_name=target)`.
- **`ai_apply` change:** `apply_section_html` / `apply_element_html` copy attribute changes to the other languages without translating when the visible text is unchanged. The test is `_same_text(old_source_tag, new_tag)`: text nodes stripped and joined, plus `alt`/`title`/`aria-label`/`placeholder` values, equal. When the structure is also the same (tag-name sequence equal in the target language's copy), each attribute that changed in the source (old source vs new) is set in the target. For `href`, the localised link is set; removed attributes are removed. Unchanged attributes keep the target's value. In all other cases they translate, as now.
- **Return value:** both apply functions also return `'html'` = the saved fragment in the source language.

- [ ] **Step 1: Write the failing tests:**
  - **agent** (mock `LLMBase.get_completion` to return `<actions>[{"tool":"refine_with_ai","params":{}}]</actions>`):
    - `delegate=False` returns `{'delegate': True}` and the services are not called;
    - an `update_styles` action plus a response → a direct-edit option;
    - one `AICallLog(action='refine_routing')` per routing call.
  - **ai_apply:**
    - a class-only change on a section → `translate_snippet` not called, and EN gets the new classes while keeping its EN text;
    - an `href` change → localised in EN;
    - a text change → translated (called once);
    - an `alt` change → translated;
    - `'html'` returned.
- [ ] **Step 2: Run** `manage.py test djangopress.ai.tests.test_refinement_routing djangopress.editor_v2.tests.test_ai_apply`. Expected: FAIL.
- [ ] **Step 3: Implement**, then `manage.py makemigrations ai`.
- [ ] **Step 4: Run** the same tests plus `djangopress.site_assistant` (it uses `ai_apply`). Expected: OK.
- [ ] **Step 5: Commit** `feat(ai): router can stop before generating; class-only edits reach other languages without translation`.

### Task 5: Chat turn orchestration + endpoints

**Files:**
- Create `src/djangopress/editor_v2/chat.py`
- Create `src/djangopress/editor_v2/chat_views.py`
- Modify `src/djangopress/editor_v2/urls.py`
- Modify `src/djangopress/editor_v2/api_views.py`: `apply_option` returns `html`; `refine_multi_stream` / `refine_page_stream` use `_get_editable_object`; there is a shared `_get_or_create_session`.
- Test `src/djangopress/editor_v2/tests/test_chat.py`

**Interfaces — produces:**
- `chat.classify_intent(text) -> 'quick' | 'explore' | None`. The keywords cover PT and EN:
  - explore: elegant(e)/eleg, redesign/redesenha, more modern/moderno, ideas/ideias, options/opções/propostas, directions/direções, different/diferente, refazer/rethink, inspire/inspira, "3 ";
  - quick: colour words (cor, color, colour, gold, dourado, red, vermelho…), size words (maior, menor, bigger, smaller, size, tamanho), spacing (padding, margin, espaço, spacing), font weight (bold, negrito, itálico), text changes (muda o texto, change the text, replace … with, troca), align (centra, center, alinha).

  Explore wins when both match.
- `chat.run_turn(page, *, scope, target, instructions, mode, lang, history, base_html, images, user, session, run_id, emit)`. `emit(event, data)` sends the events in the spec:
  - `step {key,label,state}`;
  - `context {matches}`;
  - `option {...}`;
  - `option_failed`;
  - `applied {html, scope, target, translated, untranslated, message}`;
  - `complete {mode, session_id, message}`;
  - `error`.

  The resolved mode works as follows:
  - **`base_html`** → one generation (no direction, design context), sent as `option` key `next`, name `Refined`. Not applied.
  - **`quick`** → router with `delegate=False`. A direct edit → apply via `ai_apply` (`checkpoint=True`, user) and emit `applied`. A delegate → when the request was `auto`, switch to explore (step label "Needs a new design — 3 directions"); when explicit `quick`, one generation that is applied.
  - **`explore`** → step `context` (emit `context`), step `directions`, `generate_directions(...)` with `on_option`→emit, step `check`, then `complete`.
  - **`auto`** → `classify_intent`, else quick (the router decides).
- `chat_views.chat_stream` (POST, superuser): a JSON body or multipart (`payload` JSON field plus `reference_images` files, at most 5 and ≤ 10 MB each, `image/*` only). Errors come back as SSE `error`. It uses `_get_editable_object`, records the session messages (user, then assistant summary) and runs `run_turn` in a worker thread with a queue, as `refine_multi_stream` does. It clears the cancel flag at the end.
- `chat_views.chat_cancel` (POST `{run_id}`) → `site_assistant.cancel.request_cancel`.
- **URLs:** `api/chat/stream/` → `chat_stream`, `api/chat/cancel/` → `chat_cancel`.

- [ ] **Step 1: Write the failing tests** (`run_turn` tests with `generate_directions` / `RefinementAgent.handle` / `translate_snippet` patched; the endpoint tests read the SSE by joining `streaming_content`):
  - `classify_intent` table (PT and EN, explore wins);
  - **auto + "mais elegante"** → events context, option ×3, complete; nothing saved;
  - **auto + "título dourado"** with the agent returning a direct edit → `applied`, page saved, checkpoint created;
  - **auto + the agent delegating** → switches to directions;
  - **explicit quick + delegate** → one generation applied;
  - **`base_html`** → one `option` with key `next`, nothing saved;
  - **cancel** (`request_cancel` before the run) → `complete` with `cancelled: True`, no options after;
  - **endpoint, multipart:** 2 images reach `run_turn` as `[{'bytes','mime_type'}]`; a 6th image or a non-image → `error`;
  - **endpoint with a `NewsPost`** (content_type_id/object_id) → works and stores the session on the content type;
  - **non-superuser** → 302/403;
  - **`apply_option`** returns `html`;
  - **`refine_multi_stream` with a NewsPost** no longer errors "Page not found".
- [ ] **Step 2: Run** `manage.py test djangopress.editor_v2.tests.test_chat`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `djangopress.editor_v2`. Expected: OK.
- [ ] **Step 5: Commit** `feat(editor): chat turn endpoint — quick edits applied, three directions streamed, cancel, reference images`.

### Task 6: The Chat tab UI

**Files:**
- Create `src/djangopress/editor_v2/static/editor_v2/js/lib/chat-intent.js`
- Create `src/djangopress/editor_v2/static/editor_v2/js/lib/chat-preview.js`
- Rewrite `src/djangopress/editor_v2/static/editor_v2/js/modules/ai-panel.js`
- Modify `src/djangopress/editor_v2/static/editor_v2/js/lib/sse-client.js`: an `onEvent(name, data)` hook, and FormData bodies sent without a JSON content type.
- Modify `src/djangopress/editor_v2/static/editor_v2/css/editor.css`: the new `.ev2-chat*` block, following the mockup.
- Test `src/djangopress/editor_v2/tests/js/chat_test.html`

**Interfaces — produces:**
- `chat-intent.js`: `classifyIntent(text) -> 'quick'|'explore'|null` (the same keywords as Python), and `intentLabel(mode, guess) -> string`.
- `chat-preview.js`:
  - `cleanClone(html) -> DocumentFragment-ish Element`: strips `id`, `data-section`, `data-ev2-*`, scripts and inline handlers, and sets `inert`;
  - `thumbnail(html, width) -> HTMLElement` (a scaled 1280-px copy);
  - `compareView(originalHtml, optionHtml) -> HTMLElement` (two scaled copies with labels);
  - `swapNode(node, html) -> Element`: replaces the node with the first element of `html`, re-inits dynamic components, and returns the new node.
- `ai-panel.js` (state machine):
  - **Header:** target chip, and the Element/Section/Page seg (Page is shown only with no selection, or when chosen).
  - **"Matches" row:** filled from the `context` event (palette dots, fonts, "style of …").
  - **Thread:**
    - user bubbles with attachment chips;
    - a progress card (steps from `step` events, elapsed seconds, Cancel);
    - a result card with tiles: Original plus each option as it arrives (a shimmer until then; a failed tile shows "Couldn't make this one"). Clicking a tile previews it live in the page;
    - "Why it fits" for the active tile;
    - actions: Apply / Refine this one… / Regenerate / Compare;
    - an applied card (message, translated languages, Undo → `history:undo`).
  - **Composer:**
    - suggestion chips (section: "More elegant", "Match the site's style", "Tighter spacing", "Bigger title"; element: "Brand colour", "Bigger", "More spacing");
    - a refining chip when `base_html` is set;
    - a textarea, the clip (file input, drag, paste);
    - the intent toggle (Auto ▸ Quick ▸ 3 directions);
    - Send ↔ Stop.
  - **Page scope:** posts to the old `refine-page/stream/`, shows one tile "Page", and Apply uses `/save-ai-page/` + reload (unchanged behaviour).
  - **Apply (section/element):** `/apply-option/` → `swapNode(previewNode, res.html)`, `events.emit('history:refresh')`, `events.emit('toast:show', {text, withUndo:true})`, and an applied card. No reload.
  - **Quick `applied` event:** swap the live node with `data.html` the same way.

- [ ] **Step 1: Write the failing harness** `chat_test.html`:
  - the `classifyIntent` table (same cases as Python);
  - `cleanClone` strips `data-section`/`id`/onclick and is inert;
  - after inserting a thumbnail into the document, `document.querySelectorAll('[data-section="hero"]').length === 1`;
  - `compareView` has two panes with labels;
  - `swapNode` returns the new node, in the same place;
  - `intentLabel` strings.
- [ ] **Step 2: Run** `harness.sh tests/js/chat_test.html`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement** the helpers and the SSE client change. Run the harness: PASS. Then rewrite `ai-panel.js` and the CSS.
- [ ] **Step 4: Check in the browser** (temp server on demo-ai-eval, port 8199):
  1. a section: "Tighter spacing" → applied card, page not reloaded, Undo restores it;
  2. "More elegant" → three tiles arrive one by one, the live preview switches, Compare shows side by side, Original restores, "Refine this one…" → a new tile `Refined`, Apply without reload, then Undo;
  3. Cancel mid-run → the progress card ends "Stopped", the tiles shown so far stay;
  4. attach an image → it reaches the server (`AICallLog` vision);
  5. a news post edit page: the chat works.

  Also: there are no console errors, and the Design-panel harnesses still PASS.
- [ ] **Step 5: Commit** `feat(editor): new Chat tab — intent, directions tiles, compare, refine an option, apply without reload, cancel, attachments`.

### Task 7: Evals

**Files:**
- Modify `docs/evals/run_ai_design_cases.py`: `EVAL_ENDPOINT=chat` sends editor refine turns to `/editor-v2/api/chat/stream/` with `mode='explore'` and applies the `apply` index of the received options.
- Create `docs/evals/2026-10-02-results-editor-chat.md`

- [ ] **Step 1:** Run `N1,N2,N6,N7,N9,C1,C2,C7` on demo-ai-eval with `EVAL_ENDPOINT=chat`. Compare against `2026-10-01-results-phase-1-2.md`: pass/fail, time to first option, total time, tokens, design-check notes, and screenshots of the three directions for N2 and N9.
- [ ] **Step 2:** Write the results doc, with a short design verdict per case (does it look like the rest of the site).
- [ ] **Step 3: Commit** `docs(evals): editor chat directions on the section cases`.

### Task 8: Docs and the manual checklist

**Files:**
- Modify the engine `CLAUDE.md` (the editor AI section): the Chat modes, the directions, the design context and check, the endpoints.
- Create `docs/evals/2026-10-02-editor-chat-manual-tests.md`.
- Modify `docs/evals/2026-10-01-chat-manual-tests.md` if it references the old "3 options" checkbox.

- [ ] **Step 1:** Write the docs and the checklist (each step with its expected outcome).
- [ ] **Step 2: Run** the full suite `manage.py test djangopress`. Expected: OK.
- [ ] **Step 3: Commit** `docs: editor Chat — modes, directions, design context; manual checklist`.
