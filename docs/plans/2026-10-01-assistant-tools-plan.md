# Assistant Phase 4 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** the site assistant inserts sections where asked, reads and restyles precisely, edits sliders and galleries, finds photos and sets backgrounds, tests forms and checks contacts. Every change it makes can be undone per turn.

**Architecture:**
- **Undo backbone (Task 1):** a per-turn change tracker, `site_assistant/changes.py`, is the single place where checkpoints and snapshots happen. Tools call it before mutating. The session message keeps the turn's change log. A turn-undo service restores from it, through the editor's existing `_apply_snapshot_html` for pages, `GlobalSectionVersion.restore` for header and footer, and JSON snapshots for SiteSettings, menu items and forms.
- **Tools reuse existing deterministic code:** `editor_v2/ai_apply.py`, `editor_v2/components.py` and `ai/utils/unsplash.py`, plus the new shared runners described in the tasks.

**Spec:** `docs/plans/2026-10-01-assistant-tools-design.md`

## Global Constraints

- **Branch:** `feature/assistant-tools`. Tests run on the demo: `cd ~/Documents/djangopress-sites/demo-ai-lab && .venv/bin/python manage.py test djangopress.<app>`.
- **No real LLM, Unsplash, DNS or email calls in unit tests:** mock them; the email backend is locmem.
- **Commits:** no `Co-Authored-By`; end with `Claude-Session: https://claude.ai/code/session_01WSpzVT1ezgnAA6UbDJmNtS`; no merge or push.
- **Pages:** every page mutation by the assistant goes through `changes.page_checkpoint(context, page)`: one `kind='checkpoint'` per page per turn, labelled `Assistant: <request ≤60 chars>`.
- **Test emails** go to `settings.PWD_SUPERADMIN_EMAIL` (fallback: the request user's email) with the subject prefix `[TESTE] `.

## Review Focus

1. **Undoing a turn after the operator edited the same page in the editor:** the undo must ask first, not silently overwrite.
2. **A turn that touched two pages, the header and SiteSettings:** one Undo restores all four.
3. **`insert_section` "before" the first section:** the section is inserted at the top.
4. **Unsplash not configured:** `find_photos` still returns library results and says Unsplash is off.
5. **A form whose required field is a select or checkbox:** `test_form` builds a valid value.

---

### Task 1 — Undo backbone: tracker, change log, turn undo, `undo_last_change`
**Files:**
- Create: `site_assistant/changes.py`.
- Modify: `site_assistant/services.py`, `site_assistant/tools/page_tools.py`, `site_assistant/tools/site_tools.py` (settings, menu, forms writers), `site_assistant/views.py`, `site_assistant/urls.py`, `editor_v2/ai_apply.py` (`checkpoint=True` flag), `editor_v2/component_views.py` (runner, Task 4).
- Test: `site_assistant/tests/test_changes.py`.

**Interfaces:**
- `changes.start_turn(context, request_text)`.
- `changes.page_checkpoint(context, page)` and `changes.global_section_checkpoint(context, gs)`.
- `changes.snapshot(context, obj, label)` (before an update) and `changes.created(context, obj, label)` (after a create).
- `changes.finish_turn(context) -> list[dict]`.
- `changes.undo_turn(session, message_index, user, force=False) -> {'undone': [...], 'conflicts': [...]}`.
- Tool `undo_last_change`.
- Endpoint `POST /site-assistant/api/sessions/<id>/undo/ {message_index, force}`.
- `ai_apply.apply_*(..., checkpoint=True)`: callers that already checkpointed pass `False`.

**Tests:**
- One checkpoint per page per turn, labelled.
- The editor's `find_undo_target` returns that checkpoint.
- Undo restores a page and records `kind='undo'`.
- Settings restored from a snapshot; a created menu item and a created form are deleted.
- A global section is restored.
- A later page edit becomes a conflict and nothing changes without `force`; with `force` it restores.
- `undo_last_change` picks the last assistant turn that has changes.
- The assistant message stores `changes`.

### Task 2 — `insert_section`
- **Tool:** `insert_section(position, anchor_section, instructions)` → `generate_section(lang)` → `apply_section_html(mode='insert', insert_after=…, checkpoint=False)` after `page_checkpoint`.
- **Position:** "before X" means after the previous section, or top of the page when X is the first section. "start" means top; "end" means after the last named section.
- **Tests (mock the generator and the translation):**
  - each position;
  - only the new section is translated (the EN copies of other sections are byte-identical);
  - the name is unique.

### Task 3 — `read_section` and add/remove classes
- **`read_section(section_name)`:** HTML in the editing language, capped at 12 000 characters with a note.
- **`update_element_styles`:** gains `add_classes` / `remove_classes`. `PageService.update_element_classes(page, selector, add=, remove=)` applies to all languages, and the old `new_classes` behaviour stays.
- **Tests:** the cap; add/remove in PT and EN while keeping other classes; the old replace path still works.

### Task 4 — Sliders and galleries from the chat
- **`editor_v2/component_ops.py`:** `run_component_op(page, root, kind, op, args, lang, user, checkpoint=True)`, extracted from `component_views.component_op`. The endpoint calls it; its own tests stay green.
- **Tools:**
  - `list_components()` returns sliders and galleries on the active page: `{section, kind, root, items: [label]}`.
  - `reorder_items(section, order)`.
  - `replace_item_image(section, index, image_ref)`.
  - `add_item_images(section, after, image_refs)`.
  - `remove_item(section, index)`.
  - Indices are 1-based in the tools.
  - An image ref is a library id or an Unsplash id (downloaded first, Task 5).
- **Tests:** each tool on the shared fixtures, in all languages, through `page_checkpoint`.

### Task 5 — Photos: `find_photos`, `set_section_background`, Home thumbnails, editor Unsplash tab
- **`find_photos(query, source, orientation)`:**
  - **Library:** ranked by token overlap over title, alt, tags and description.
  - **Unsplash:** `unsplash.search_photos`.
  - **Result:** ≤8 `{ref: "lib:<id>" | "unsplash:<id>", source, title, thumb_url, credit}`; the tool result carries `photos`.
- **`ensure_library_image(ref) -> SiteImage`:** downloads Unsplash photos via `unsplash.download_photo` and keeps the credit.
- **`set_section_background(section_name, ref)`:**
  - with an inline `background-image` style, replace the url and keep the gradient;
  - with an absolute `<img>` layer (first `img` with `absolute inset-0`), replace its src;
  - applies to all languages, after `page_checkpoint`.
- **Home:** an assistant reply with `photos` renders clickable thumbnails. A click sends `Usa a foto <ref>`.
- **Editor image picker:** an Unsplash tab, when `EDITOR_CONFIG.unsplashEnabled`, using the existing `/ai/api/search-unsplash/` plus a new `/editor-v2/api/images/unsplash-import/`.
- **Tests:** ranking; Unsplash off; ensure-download (mocked); background style with and without a gradient; the `<img>` layer.

### Task 6 — Forms
- **`validate_forms`:** accepts string and dict schema entries.
- **`core/services/forms.py`:** `process_submission(form_def, data, lang, ip, user_agent, *, notify_to=None, subject_prefix='')`. `core/views.form_submit` calls it, with its rate limit and honeypot unchanged.
- **Email functions:** `send_form_notification` / `send_form_confirmation` accept `to_override` and `subject_prefix`.
- **`test_form(slug=None)`:**
  - builds data from the schema (text, email, tel, textarea, number, select, checkbox, date);
  - runs `process_submission` with `notify_to` set to the operator and `subject_prefix='[TESTE] '`;
  - deletes the submission;
  - reports each step.
- **Tests:**
  - the schema crash is fixed;
  - visitor submission is unchanged;
  - `test_form` sends `[TESTE]` only to the operator, deletes the submission, and builds select and checkbox values.

### Task 7 — `validate_contacts(check_web=False)`
- **Collect:** SiteSettings contacts plus tel/mailto/wa.me links and visible phones/emails in pages and global sections, in every language.
- **Checks:**
  - format;
  - MX through `dns.resolver` if importable, else `socket.getaddrinfo` of the domain, else "can't verify";
  - href vs text;
  - consistency;
  - maps embed.
- **`check_web`:** `LLMBase.web_search` for the business name and city, comparing phone and address, with sources.
- **Tests:** a mismatched `tel:`; a different phone on one page; a bad email; MX mocked; web check mocked.

### Task 8 — Prompts, evals, run
- **Executor prompt:** tool guidance per the spec.
- **Eval cases:** N11–N14 and C11 in the eval doc and runner. The runner gains a `turn_undo` step for C11.
- **Verification:**
  - the full suite;
  - re-run N8, C8, N11–N14 and C11 on `demo-ai-eval`;
  - a short results note in `docs/evals/`.
