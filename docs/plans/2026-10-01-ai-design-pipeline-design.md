# In-site AI design pipeline — Phases 1 & 2 (plumbing + model configuration)

**Date:** 2026-10-01
**Status:** Draft for review
**Repo:** djangopress (engine). Branch `feature/ai-design-pipeline` (on top of `feature/gemini-models`).
**Goal:** make the in-site Gemini pipeline (editor AI Refine, new section, element refine, page refine, site assistant) produce and save layout changes reliably in every language, with model settings that suit design work, so that the later context work (Phases 3–5) can be judged on model quality, not on broken plumbing.

---

## Context

A code survey (2026-10-01) and the first eval run on the demo site found that most layout requests fail or are saved wrongly before model quality even matters. Case N1 on `demo-ai-lab` ("two columns, photo on the right"): the model produced 3 valid options, and all were rejected with "New HTML is only 31 % the size of original (13 608 vs 43 201 chars) — possible truncation". The run took 130 s and 5 AI calls (including a Gemini Pro fallback), about 52 k tokens, all discarded.

The whole programme, for orientation:
1. **Plumbing** (this spec).
2. **Model configuration** (this spec).
3. **Design context pack:** theme, tokens, section contract, html-reference rules, media library, art direction. Own spec.
4. **Site-assistant layout tools:** insert/read section, add/remove classes, multi-language refine. Own spec.
5. **Verification:** section checks and later a visual check. Own spec.

Yardstick: the 20 cases in `docs/evals/2026-10-01-ai-design-cases.md`, run with `docs/evals/run_ai_design_cases.py` on `demo-ai-lab`. The baseline run is recorded before this work starts.

---

## Phase 1 — Plumbing

### 1.1 Truncation detection that doesn't reject normal output

**Problem:** `validate_html_structure` compares the new HTML with `original_html` and fails below 50 % (`ai/services.py:73-80`). `refine_section_only` passes the **whole page** as the original (`:1293`), and `refine_element_only` passes the whole **section** while expecting one element back (`:1649`). A normal section is almost always under half the page, so it is rejected.

**Change:**
- **Detect real truncation from the API:**
  - `LLMBase` returns Gemini's `finish_reason`.
  - `MAX_TOKENS` raises "The answer was cut off (output limit)" — a clear error. This applies to every scope.
- **Structural completeness, per scope:**
  - **Section / new section:** each option parses to exactly one root `<section>` with a closing tag. For refine, `data-section` must equal the target name. Tag balance is checked as today.
  - **Element:** each option parses to exactly one root element with the same tag as the target.
- **Length ratio** stays only for **page** scope (whole page against whole page), where silent truncation is plausible.
- The ratio check is removed for section and element scope: a valid "simplify" request can legitimately shrink a section below 50 %.

### 1.2 Element direct edits must return the element

**Problem:** the refinement agent edits the parent section in `context['target_html']`. A direct edit returns that **section** as the option (`ai/refinement_agent/agent.py:155`), and `apply_option` replaces the *element* with it (`editor_v2/api_views.py:1404-1419`), nesting the whole section inside the element.

**Change:** for element scope, the agent returns the edited element, re-selected by the same selector from the edited section. As a guard, `apply_option` refuses element HTML whose root is a `<section>`.

### 1.3 Work in the language being edited

**Problem:** every generator reads the **default-language** HTML (`ai/services.py:1203, 1407, 1554`; `agent.py:225`). `apply_option` saves into the language detected from the Referer and translates into the others. Editing on `/en/` therefore saves PT text into `en`, then "translates" it into `pt`.

**Change:**
- Each generator takes `lang` (the editing language, already detected by the endpoints) and reads that language's HTML.
- The default-language fallback stays only for an empty copy, as `_edit_lang` does in editor_v2.
- Prompts state which language the text is in.

### 1.4 One save path for AI section/page output, all languages

**Problem:**
- `apply_option` saves the source language, then translates per language.
- The site assistant's `refine_section` / `refine_page` save **only the default language** (`site_assistant/tools/page_tools.py:100-144`, `core/services/pages.py:428-471`), so the languages drift.
- `save_ai_page` saves one language.

**Change:**
- New service, `editor_v2/ai_apply.py`:
  - `apply_section_html(page, section_name, html, source_lang, mode='replace'|'insert', insert_after=None)`;
  - `apply_page_html(page, html, source_lang)`.
- **Behaviour:**
  1. Checkpoint first (`create_version(kind='checkpoint')`), so Undo covers AI changes.
  2. Write the source language.
  3. Translate the new or changed section into every other language with `translate_html`.
  4. Fix internal links (1.5).
  5. Write those languages.
  6. Report `translated_languages` / `untranslated_languages`. A failed translation leaves the source text, as the component panel does.
- **Callers:** `apply_option`, `save_ai_page` and the assistant tools `refine_section`, `refine_page` all call it.
- **Header / footer:** `refine_header` / `refine_footer` already use their own GlobalSection path and are unchanged.

### 1.5 Internal links follow the language

**Problem:** `translate_html` is told not to change URLs, so `/pt/reservas/` stays inside the EN copy (`check_site` "links" fails).

**Change:** after translation, a deterministic `localize_internal_links(html, target_lang)` maps `/<src-lang>/<slug>/` to `/<target-lang>/<slug-in-target>/`. It uses `Page.slug_i18n`, keeps anchors and query strings, and leaves external links untouched. Unknown slugs only get the language prefix swapped.

### 1.6 Editor page scope works end to end

**Problem:**
- `refine_page_stream` returns `{page: {html_content_i18n}}` (`api_views.py:2463`).
- The panel sends `pendingResult.html_template` to `save-ai-page` (`ai-panel.js:500, 545`), which is `undefined`, so `detemplatize(undefined)` throws (`ai-panel.js:53`).
- Page scope is the panel's default.

**Change:**
- The stream's `complete` payload returns `html` (the editing language).
- The panel previews it and posts `{page_id, html}` to `save-ai-page`.
- `save-ai-page` calls `apply_page_html` (1.4).
- The legacy `html_template`/`content` fields are dropped from this flow.

### 1.7 The conversation knows what was applied

**Problem:** the editor's chat history only contains "Here are 3 variations…". The model never learns which option the operator applied.

**Change:**
- `apply_option` appends an assistant message to the refinement session: "Applied option N to `<section>`." The panel sends the option index it applies.
- The next turn re-reads the section from the database, so it naturally starts from the applied HTML. The message makes that explicit in the history.

### 1.8 New sections get unique names

**Problem:** `generate_section` lets the model name the section, with no uniqueness check (`ai/services.py:1491`).

**Change:** on insert, a `data-section` / `id` that already exists on the page (in any language) is renamed with `next_free_section_name` from `editor_v2/structure.py`. In-section `#anchors` are rewritten to match.

---

## Phase 2 — Model configuration (Gemini 3)

### 2.1 Per-task generation settings

`ModelConfig` keeps the model; a new `TASK_SETTINGS` map in `ai/utils/llm_config.py` gives each task its sampling and thinking:

| Task (`AI_MODEL_DEFAULTS` key) | temperature | thinking_level |
|---|---|---|
| `generation`, `refinement_page`, `refinement_section`, `refinement_element`, `header_footer`, `design_guide` | 1.0 | `high` |
| `assistant_executor` | 1.0 | `medium` |
| `assistant_router`, `metadata`, `translation`, `consistency`, `image_analysis` | 1.0 | `low` |

- **Temperature:** Gemini 3 is tuned for its default of 1.0; the current 0.3 everywhere narrows the 3 variations. Values are model defaults; the table makes them explicit and adjustable in one place.
- **Wiring:** `get_completion` / `get_completion_with_tools` / `get_vision_completion` take an optional `task` and apply its settings via `types.ThinkingConfig(thinking_level=…)`. Callers already resolve the model through `get_ai_model(task)`, so they pass the same `task`.
- **Non-Google providers:** unchanged.

### 2.2 System prompts as system instructions

**Problem:** Gemini calls fold the system message into the first user turn (`llm_config.py:265-301`).

**Change:** pass it as `GenerateContentConfig.system_instruction`, as the function-calling path already does.

### 2.3 JSON where JSON is expected

The router, the refinement agent's action output and `apply_edits` parse JSON out of free text. They request `response_mime_type='application/json'`, with a `response_json_schema` where the shape is fixed (router, `apply_edits`). The free-text fallback parser stays for robustness.

### 2.4 No silent provider switch

**Problem:** a Gemini error currently falls back to `gpt-5-mini` with a 10 k-token cap (`llm_config.py:566-579`), which truncates 3-option output and hides the real error.

**Change:**
- Remove the cross-provider fallback.
- Retry once on transient errors (429/5xx) with a short backoff.
- Otherwise raise the original error; the UI shows it.

### 2.5 Real token usage

Use `usage_metadata` (`prompt_token_count`, `candidates_token_count`, `thoughts_token_count`) instead of chars/4 in `AICallLog`. This is needed for honest cost numbers in the evals.

---

## Out of scope (later specs)

- **Phase 3 — design context pack:** theme, tokens, section contract, html-reference rules, media library, art direction, removing the "minimal change" bias.
- **Phase 4 — assistant tools:** insert section, read section, add/remove classes.
- **Phase 5 — visual verification.**
- **Merging the XML refinement agent into the native function-calling assistant.**

---

## Testing

- **Unit tests:**
  - `validate_html_structure` per scope: a section shorter than 50 % of the page passes; an unclosed section fails; `MAX_TOKENS` raises.
  - Agent element direct edit returns the element.
  - `apply_option` refuses a section for element scope.
  - Generators read the editing language.
  - `apply_section_html` / `apply_page_html`: checkpoint, all languages, translation mocked (success and failure), links localized.
  - `localize_internal_links` covers home, nested, anchors, query, external and unknown links.
  - Page-scope `save-ai-page` with `html`.
  - `apply_option` records "Applied option N".
  - Duplicate section names are renamed.
  - `TASK_SETTINGS` reach the Gemini config, checked with a mocked client.
  - `system_instruction` is set.
  - No fallback to OpenAI.
  - Usage comes from `usage_metadata`.
- **Existing suites stay green.**
- **Eval:** re-run the 20 cases on `demo-ai-lab` and compare with the baseline. Expected: N1, N2, N6, N7, N9, C1, C2 and C7 now produce and apply; every language is updated; failures left are model or context quality (Phase 3) or missing assistant tools (N8 → Phase 4).

## Files

| Area | Files |
|---|---|
| Validation, generators | `ai/services.py` |
| LLM layer | `ai/utils/llm_config.py` |
| Agent | `ai/refinement_agent/agent.py` |
| Apply / translate / links | new `editor_v2/ai_apply.py`, `editor_v2/api_views.py` (`apply_option`, `save_ai_page`, `refine_page_stream` payload) |
| Assistant | `site_assistant/tools/page_tools.py`, `core/services/pages.py` |
| Editor panel | `editor_v2/static/editor_v2/js/modules/ai-panel.js` |
| Tests | `ai/tests/`, `editor_v2/tests/`, `site_assistant/tests/` |
