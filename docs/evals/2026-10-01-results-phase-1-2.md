# In-site AI eval — baseline vs phases 1–2

**Date:** 2026-10-01 · **Cases:** `docs/evals/2026-10-01-ai-design-cases.md` · **Runner:** `docs/evals/run_ai_design_cases.py`
**Baseline:** demo-ai-lab, engine `feature/gemini-models` (Gemini 3.8 Flash / 3.5 Flash-Lite / 3.1 Pro, old pipeline).
**After:** demo-ai-eval (same content), engine with phases 1–2 (`feature/ai-design-pipeline` + backoffice). The assistant changes made later the same day (Stop, report, web search) were not in this run.

| Case | Before | After |
|---|---|---|
| N1 two columns | ✕ 120 s, 5 calls, 51k tok — rejected "27 % of original" | ✓ 25 s, 2 calls, 26k |
| N2 testimonials restyle | ✕ 268 s, 54k — rejected | ✓ 24 s, 27k |
| N3 new section hours + map | ✓ 80 s | ✓ 74 s |
| N4 new gallery | ✓ 70 s | ✓ 154 s |
| N5 element button | ✕ (runner bug: target had no button) | ✓ 12 s, 5k |
| N6 simplify pillars | ✕ 122 s — rejected | ✓ 24 s |
| N7 mobile grid | ✕ 60 s — rejected | ✓ 13 s |
| N8 assistant FAQ before contacts | ✓ but section only in one language | ✓ in both, **but via a whole-page refine: 4 other EN sections re-translated** |
| N9 menu cards | ✓ 93 s | ✓ 39 s |
| N10 group menus, cross-page style | ✓ 100 s | ✓ 81 s |
| C1 pick option 2, then dark | ✕ 226 s, 10 calls — rejected | ✓ 94 s, 4 calls |
| C2 title style across 3 sections | ✕ 276 s, 15 calls, 152k — rejected | ✓ 60 s, 6 calls, 75k |
| C3 list sections, remove "the fifth" | ✓ (asked) | ✓ (asked) |
| C4 change, then "go back" | ✓ 70 s | ✓ 51 s |
| C5 ambiguous button colour | ✓ (asked) | ✓ (asked) |
| C6 sentence PT, then EN only | ✓ 159 s, 18 calls | ✓ 138 s, 9 calls |
| C7 three constraints, one section | ✕ 423 s, 16 calls, 174k — rejected | ✓ 102 s, 6 calls, 95k |
| C8 preference, newsletter, awards | ✓ | ✓ preference saved to the design guide and respected; **newsletter added via whole-page refine (11 EN sections re-translated)**; `validate_forms` crashed |
| C9 detour then back | ✓ 186 s | ✓ 78 s |
| C10 ambiguous "remove the gallery" | ✓ (asked) | ✓ (asked) |

**Result:** 12/20 → 20/20 complete. Every editor section/element refine, which always failed before (length check against the whole page), now works in 12–102 s, with fewer calls and tokens.

**What this run says to do next**
1. **Phase 4 first:** an `insert_section` tool with a position (before/after a section), plus read-section and add/remove-class tools. Today the assistant adds a section by regenerating the whole page, which re-translates every other section.
2. **Fix `validate_forms`** ("string indices must be integers, not 'str'").
3. **Phase 3 (design context):** design quality is now the limit, not plumbing. Judge it from the screenshots in the run folders.
