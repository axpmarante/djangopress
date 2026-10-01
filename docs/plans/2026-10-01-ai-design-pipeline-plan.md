# AI Design Pipeline — Phases 1 & 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In-site Gemini layout changes (editor refine/new section/element/page, site assistant) are produced, validated and saved correctly in every language, with Gemini 3 settings suited to design work.

**Architecture:**
- **LLM layer:** `ai/utils/llm_config.py` learns per-task settings without touching its 82 call sites. `get_ai_model(task)` returns a `str` subclass that carries the task. The layer also gains `system_instruction`, `finish_reason`, real usage and no silent provider switch.
- **One apply service:** `editor_v2/ai_apply.py` is the single path that writes AI section and page output. It checkpoints, writes the edited language, translates the others and localizes links. Editor endpoints and assistant tools call it.
- **Generators and the refinement agent** read the language being edited and validate per scope.

**Tech Stack:** Django, BeautifulSoup, google-genai 2.23 (ThinkingConfig.thinking_level, system_instruction, response_mime_type, usage_metadata, FinishReason), vanilla JS editor.

**Spec:** `docs/plans/2026-10-01-ai-design-pipeline-design.md`

## Global Constraints

- **Branch:** `feature/ai-design-pipeline` in `~/Documents/djangopress-sites/djangopress`. Paths are relative to `src/djangopress/` unless they start with `docs/`.
- **Tests:** run from the demo site, never a client site: `cd ~/Documents/djangopress-sites/demo-ai-lab && .venv/bin/python manage.py test djangopress.<app> 2>&1 | tail -4`. Full suite: `manage.py test djangopress`.
- **No real LLM calls in unit tests** (mock `LLMBase` / the genai client).
- **Commits:**
  - no `Co-Authored-By` line;
  - end with `Claude-Session: https://claude.ai/code/session_01WSpzVT1ezgnAA6UbDJmNtS`;
  - no merges, no pushes.
- **Gemini 3:** `temperature` 1.0 for every task. Thinking levels per the spec table: design `high`, `assistant_executor` `medium`, everything else `low`.
- **Evals:** only on `demo-ai-lab` (`docs/evals/run_ai_design_cases.py`).

## Review Focus

1. **Editing in EN on a page whose EN copy is empty:** the AI must read and write the copy the operator sees (the default). It must not write an empty-based EN page.
2. **Translation fails for one language:** the source language is still saved, the response lists the untranslated language, and the page structure stays aligned.
3. **The model returns 3 options where one is malformed** (no closing `</section>`): the request fails with a clear error. It must not save a half option.
4. **Duplicate data-section from "new section"** (the model names it like an existing one): renamed on insert, in all languages, with matching anchors.
5. **Internal links in a translated copy pointing at a page with no slug in that language:** only the language prefix is swapped, and the link is not dropped.

---

### Task 1: LLM layer — task-aware settings, system instruction, finish reason, real usage, no silent fallback

**Files:**
- Modify: `ai/utils/llm_config.py`
- Create: `ai/tests/test_llm_settings.py`, plus `ai/tests/__init__.py` if missing

**Interfaces:**
- **Produces:**
  - `ModelKey(str)` with `.task`;
  - `get_ai_model(task) -> ModelKey`;
  - `TASK_SETTINGS: dict[task, {'temperature': float, 'thinking_level': str}]`;
  - `settings_for(tool_name) -> dict`;
  - `StandardizedLLMResponse(content, usage, finish_reason=None)` exposes `.finish_reason` (`'STOP'`, `'MAX_TOKENS'`, …);
  - `get_completion(..., json_output=False)`.

- [ ] **Step 1 — tests** (mock `LLMBase._clients[ModelProvider.GOOGLE]` with a fake whose `models.generate_content(model, contents, config)` records `config` and returns an object with `.text`, `.candidates[0].finish_reason`, `.usage_metadata`):
  - `get_ai_model('refinement_section')` is `'gemini-flash'` and its `.task == 'refinement_section'`;
  - `MODEL_CONFIG[get_ai_model(...)]` works;
  - the call with `tool_name=get_ai_model('refinement_section')`:
    - sends `config.temperature == 1.0`;
    - sends `config.thinking_config.thinking_level` equal to HIGH;
    - sends `config.system_instruction` equal to the system message;
    - the first content part does **not** start with the system text;
  - a plain `'gemini-lite'` gets the tier default (`low`);
  - `finish_reason == 'MAX_TOKENS'` is exposed on the response;
  - usage comes from `usage_metadata` (prompt, candidates and thoughts counts);
  - when the fake raises `RuntimeError('boom')` twice, `get_completion` raises it and the OpenAI client is never called;
  - a 503-style error followed by success retries once and succeeds;
  - `json_output=True` sets `response_mime_type == 'application/json'`.
- [ ] **Step 2 — run, expect failures.**
- [ ] **Step 3 — implement:**
  - `class ModelKey(str)` (`__new__(cls, value, task=None)`, keeps `.task`).
  - `TASK_SETTINGS` built from the spec table.
  - `TIER_DEFAULT_THINKING = {'gemini-pro': 'high', 'gemini-flash': 'medium', 'gemini-lite': 'low'}`.
  - `settings_for(tool_name)` returns `TASK_SETTINGS[tool_name.task]` when present, else `{'temperature': 1.0, 'thinking_level': TIER_DEFAULT_THINKING.get(str(tool_name), 'medium')}`.
  - `get_ai_model` returns `ModelKey(model, task)`.
  - **Google branch of `get_completion`:**
    - system text goes to `system_instruction` instead of being merged into the first user turn;
    - `temperature` and `thinking_config=types.ThinkingConfig(thinking_level=…)` come from `settings_for`;
    - top_p/top_k are dropped (model defaults);
    - `response_mime_type` when `json_output`;
    - finish reason read from `response.candidates[0].finish_reason` (streaming: the last chunk that has candidates);
    - usage from `usage_metadata`;
    - the OpenAI fallback block is replaced by one retry for errors whose text contains 429/500/502/503/504/`UNAVAILABLE`/`RESOURCE_EXHAUSTED` (sleep 2 s), then re-raise.
  - `get_completion_with_tools` and `get_vision_completion` apply the same `settings_for` (the executor passes `get_ai_model('assistant_executor')`).
- [ ] **Step 4 — run, expect pass; run `djangopress.ai djangopress.site_assistant djangopress.editor_v2`.**
- [ ] **Step 5 — commit** `feat(ai): Gemini 3 per-task settings, system instruction, finish reason, real usage, no silent fallback`.

### Task 2: Validation per scope, and generators read the editing language

**Files:**
- Modify: `ai/services.py`
- Test: `ai/tests/test_html_validation.py`, `ai/tests/test_generators_lang.py`

**Interfaces:**
- **Consumes:** `StandardizedLLMResponse.finish_reason` (Task 1).
- **Produces:**
  - `validate_html_structure(html, original_html=None, scope='page')`;
  - `_extract_html_from_response(content, original_html=None, scope='page', finish_reason=None)`;
  - `_validate_options(options, scope, section_name=None) -> list[{'html'}]`, which raises `ValueError` on any malformed option;
  - a `lang=None` keyword on `refine_section_only`, `refine_element_only`, `generate_section` and `refine_page_with_html` (which already has `language`; it now uses it).

- [ ] **Step 1 — tests:**
  - **Section scope:**
    - a 4 KB section against a 40 KB page passes;
    - an unclosed `<section>` fails;
    - `finish_reason='MAX_TOKENS'` raises "cut off (output limit)";
    - page scope still fails below 50 %.
  - **`_validate_options`:**
    - for section scope with `section_name='x'`: an option with `data-section="y"` is renamed to `x`; an option without `</section>` raises;
    - element scope requires a `[data-target]` element.
  - **Generators read the editing language:** with a page `{'pt': A, 'en': B}` and a mocked LLM that captures the user prompt, `refine_section_only(..., lang='en')` sends B's section text, not A's. `lang='en'` with an empty EN copy falls back to PT.
- [ ] **Step 2 — run, expect failures.**
- [ ] **Step 3 — implement:**
  - `scope` in `validate_html_structure`: the length check runs only when `scope == 'page'`.
  - `_extract_html_from_response`: raises `ValueError('The answer was cut off (output limit) — try a smaller change or fewer options')` when `finish_reason == 'MAX_TOKENS'`.
  - The four generators:
    - use `current_lang = lang if html_i18n.get(lang) else default_language`, and add "The page text is in {current_lang}." to the user prompt;
    - pass `scope` (`'section'` for section and new section, `'element'` for element, `'page'` for page) and the response's `finish_reason`.
  - The multi-option loops use `_validate_options`.
- [ ] **Step 4 — pass; run `djangopress.ai`.**
- [ ] **Step 5 — commit** `fix(ai): validate section/element output per scope; refine in the editing language`.

### Task 3: `editor_v2/ai_apply.py` — one save path for AI output

**Files:**
- Create: `editor_v2/ai_apply.py`
- Test: `editor_v2/tests/test_ai_apply.py`

**Interfaces:**
- **Produces:**
  - `localize_internal_links(html, source_lang, target_lang) -> str`;
  - `apply_section_html(page, html, source_lang, *, section_name=None, mode='replace', insert_after=None, user=None) -> dict(section_name, translated_languages, untranslated_languages)`;
  - `apply_page_html(page, html, source_lang, *, user=None) -> dict`;
  - `apply_element_html(page, selector, html, source_lang, *, user=None) -> dict`.
  - Translation is mocked in tests through `djangopress.editor_v2.ai_apply.translate_snippet`.

- [ ] **Step 1 — tests:**
  - **Section, replace:**
    - checkpoint created;
    - PT written;
    - EN gets the mocked translation;
    - links localized: `/pt/reservas/#x` becomes `/en/book-a-table/#x`, `/pt/` becomes `/en/`, an unknown `/pt/zzz/` becomes `/en/zzz/`, and `https://x.com/pt/` is unchanged.
  - **Insert:**
    - inserted after `insert_after` in every language;
    - a duplicate name `conceito` becomes `conceito-2` in every language, with `#conceito` anchors inside the new section rewritten.
  - **Translation failure:** EN keeps the source text, and `untranslated_languages == ['en']`.
  - **Empty EN copy:** an EN copy that is `''` stays untouched.
  - **Element:**
    - only that element is replaced;
    - a `<section>` root raises `ValueError`;
    - EN gets the translated element.
  - **Page:** PT replaced; EN replaced with the full-page translation, links localized.
- [ ] **Step 2 — run, expect failures.**
- [ ] **Step 3 — implement:**
  - `translate_snippet(html, src, dst)` uses `ContentGenerationService(model_name=get_ai_model('translation')).translate_html(...)`.
  - **Section and page:** BeautifulSoup replace/insert logic as in today's `apply_option`.
  - **Section names:** `structure.next_free_section_name` over the names used in every language.
  - **Checkpoints:** `page.create_version(user=..., change_summary=..., kind='checkpoint')` for `Page`; plain `create_version(change_summary=...)` otherwise.
  - **Links:** `localize_internal_links` builds a `{(lang, slug): page}` map from `Page.slug_i18n`.
- [ ] **Step 4 — pass.**
- [ ] **Step 5 — commit** `feat(editor): one apply path for AI output — checkpoint, all languages, localized links`.

### Task 4: Endpoints use the apply service, pass the language, and record the applied option

**Files:**
- Modify: `editor_v2/api_views.py` — `apply_option` (~1328), `save_ai_page` (~1835), `refine_page_stream` complete payload (~2463), `refine_multi` (~1180), `refine_multi_stream` (~2508)
- Test: `editor_v2/tests/test_ai_endpoints.py`

- [ ] **Step 1 — tests** (mock `ContentGenerationService` / the agent to return fixed options; mock `translate_snippet`):
  - **`apply_option`:**
    - section replace writes PT and EN with a link fix;
    - insert renames a duplicate section;
    - element scope with a `<section>` root returns 400;
    - `option_index: 2` with `session_id` appends "Applied option 2 to `<name>`." to the session.
  - **`save-ai-page`:** accepts `{html}`, writes all languages and checkpoints.
  - **`refine-page/stream`:** the complete payload has `html` (the editing language).
  - **Language:** `refine-multi/stream` with an `/en/` Referer calls the generator with `lang='en'`.
- [ ] **Step 2 — fail.**
- [ ] **Step 3 — implement:**
  - `apply_option` delegates to `apply_section_html` / `apply_element_html`; the old inline translate loop is removed. On `session_id` + `option_index`, `session.add_assistant_message(f'Applied option {n} to {target}.', [target])`.
  - `save_ai_page` takes `html` and keeps accepting `html_template` for older clients, then calls `apply_page_html`.
  - `refine_page_stream` complete payload: `'html': result['html_content_i18n'].get(lang)`.
  - `refine_multi*`: `lang = _detect_language_from_request(request, data)`, passed to the agent and the generators.
- [ ] **Step 4 — pass; run `djangopress.editor_v2`.**
- [ ] **Step 5 — commit** `fix(editor): AI endpoints save through the apply service, in the editing language`.

### Task 5: Refinement agent — language, element direct edits, JSON output

**Files:**
- Modify: `ai/refinement_agent/agent.py`, `ai/refinement_agent/tools.py`
- Test: `ai/tests/test_refinement_agent.py`

- [ ] **Step 1 — tests** (mock `LLMBase.get_completion` to return an `<actions>` block that calls `update_styles` on the target element):
  - with `scope='element'`, the returned option is the **element** (its root tag equals the selected element's tag), not the section;
  - `handle(..., lang='en')` reads the EN section;
  - agent calls request `json_output` where the reply is pure JSON (`apply_edits`).
- [ ] **Step 2 — fail.**
- [ ] **Step 3 — implement:**
  - `handle(..., lang=None)`: `_get_target_html(page, scope, target, lang or default)`, and `lang` is passed to its fallback service calls.
  - **Element direct-edit return:** `BeautifulSoup(context['target_html']).select_one(target_name)`; if found, return `str(el)`.
  - `apply_edits` LLM call: `json_output=True`.
  - The hard-coded `'gemini-flash'` becomes `get_ai_model('refinement_section')` / `get_ai_model('refinement_element')`.
- [ ] **Step 4 — pass.**
- [ ] **Step 5 — commit** `fix(ai): refinement agent works in the editing language and returns elements for element edits`.

### Task 6: Site assistant — refine section/page in every language; router JSON

**Files:**
- Modify: `site_assistant/tools/page_tools.py`, `site_assistant/router.py`
- Test: `site_assistant/tests/test_page_tools.py`

- [ ] **Step 1 — tests** (mock the service and `translate_snippet`):
  - the `refine_section` tool writes PT and EN through `apply_section_html`;
  - the `refine_page` tool writes all languages through `apply_page_html`;
  - the router call passes `json_output=True`.
- [ ] **Step 2 — fail.**
- [ ] **Step 3 — implement:** the tools call `apply_*_html(page, html, default_lang, user=context.get('user'))`; the router uses `get_completion(..., json_output=True)`.
- [ ] **Step 4 — pass; run `djangopress.site_assistant`.**
- [ ] **Step 5 — commit** `fix(assistant): AI section/page refines update every language`.

### Task 7: Editor panel — page scope end to end, and send the applied option

**Files:**
- Modify: `editor_v2/static/editor_v2/js/modules/ai-panel.js`; bump `editor.js?v=` in `templates/base.html`

- [ ] **Step 1:**
  - page-scope complete: `pendingResult = { html: res.html }`;
  - preview uses `pendingResult.html`;
  - apply posts `{page_id, html: pendingResult.html}` to `/save-ai-page/`;
  - `detemplatize` is removed from that path;
  - the multi-option apply sends `option_index: activeOption + 1` and `session_id: sessionId`.
- [ ] **Step 2 — verify in the browser on `demo-ai-lab`:**
  - page scope "make the hero title shorter" previews, then saves PT and EN;
  - a section refine applies option 2, and the next message's history contains "Applied option 2".
- [ ] **Step 3 — commit** `fix(editor): AI page refine previews and saves; panel reports the applied option`.

### Task 8: Eval re-run and comparison

- [ ] Run `docs/evals/run_ai_design_cases.py` on `demo-ai-lab` into `.../ai-eval/after-phase-1-2`. Write `docs/evals/2026-10-01-results-phase-1-2.md`:
  - a per-case table, baseline vs after: ok, changed / new, only one language, new site-check problems, seconds, calls, tokens;
  - the observations;
  - what Phase 3 (design context) must address.
- [ ] Commit `docs(evals): phase 1-2 results vs baseline`.
