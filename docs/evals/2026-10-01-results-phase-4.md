# In-site AI eval — phase 4 (assistant tools)

**Date:** 2026-10-01 · **Site:** demo-ai-eval · **Engine:** `feature/assistant-tools` · **Cases:** Part 3 of `2026-10-01-ai-design-cases.md` plus N8 and C8 re-run · **Runner:** `run_ai_design_cases.py` (emails to an in-memory outbox)

| Case | Result |
|---|---|
| N8 FAQ before the contacts | ✓ 62 s · `insert_section` after `boas-praticas`: **only the new section** appears, in PT and EN. Before this phase a whole-page refine re-translated 4 other sections. |
| N11 slider photo first | ✓ 9 s · `list_components` → `reorder_items`, no AI call for the change; only `proposta-2›foto-foie` changed |
| N12 better photo for the top | ✓ turn 1 shows 8 candidates (4 library, 4 Unsplash) and changes nothing; turn 2 (thumbnail click) sets it on `reservas-hero` in PT and EN. The model also added a translucent text panel for readability (extra styling, undoable). |
| N13 test the booking form | ✓ 8 s · both emails (`[TESTE] …` notification and confirmation) went only to the operator; no submission left; pages unchanged |
| N14 check the contacts | ✓ reports the landline on 14 places vs the mobile in Settings, changes nothing. **First run invented a source** ("confirmado pelo site oficial checkinfaro.pt" with no web search). Fixed: the tool says when the web was not checked, and the prompt allows only sources a tool returned. Re-run: it ran the web check, and its sources are real. |
| C11 change the top background, then "Desfaz isso" | ✓ `undo_last_change`; every page **byte-identical** to the start |
| C12 FAQ, then "Undo this" | ✓ `insert_section`, then the undo endpoint; every page byte-identical to the start |
| C8 preference, newsletter, awards | ✓ after fixes. Preference saved to the design guide; newsletter added with `insert_section` (only that section is new; 11 sections re-translated before) and a new form, then tested with `test_form`; awards: a cited web search, then **asks** whether to rework the existing `reconhecimento` strip or add a new section. The first run exposed `update_form` writing `None` into fields not given (fixed), and 8 steps ran out. |

**Fixes made from this run**
- `FormService.update` ignores fields passed as `None`.
- `validate_contacts` without `check_web` says the web wasn't checked; the facts rule now limits citations to tool-returned sources.
- The executor's step limit goes from 8 to 12. `read_section`, `list_components` and `web_search` now use steps before the change. Two turns (C8 turn 3, C11 turn 1) ran out at 8 and finish at 12.

**Seen, not changed**
- On background changes the model sometimes adds readability styling (a translucent panel) nobody asked for. It's undoable and reported in the summary.
- Replies still mention section ids and paths (`reservas-hero`, `/reservas`); acceptable for the operator, not for clients.

## Several pages in one request (same day, later)

The changes:
- every page tool takes `page`;
- the prompt carries a site map with every page's sections;
- new tools `find_elements` and `restyle_elements` for site-wide styles;
- when the step limit is hit, the model still writes its summary.

| Case | Result |
|---|---|
| N15 hours strip on the three proposals | ✓ 77 s · one turn, `insert_section` with `page` on proposta-1/2/3, each right before `contactos`, PT and EN, with exactly the given hours; nothing else changed |
| N16 contact titles in capitals on every page | ✓ 24 s · `update_element_styles` with `add_classes: uppercase` on the 5 pages that have `contactos` (one was already uppercase); first run ran out of steps after doing it, fixed by the closing summary |
| C13 the N15 request, then "Desfaz isso" | ✓ one undo restores all three pages; byte-identical to the start |
| C5 "muda a cor dos botões" → "em todas as páginas, dourado da marca" | ✓ asks first; then `find_elements` (5 calls) + `restyle_elements`: main buttons on 3 pages and the header, 39 s; says which ones already were gold. Before `find_elements` existed it read sections one by one and ran out of steps with nothing changed. |
| C10 "tira a galeria" → "a da proposta-1" | ✓ asks for confirmation on the right page |
