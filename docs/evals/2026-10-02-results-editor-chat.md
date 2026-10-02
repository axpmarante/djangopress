# Editor Chat on the section cases

**Date:** 2026-10-02 · **Cases:** N1, N2, N6, N7, N9, C1, C2, C7 from `docs/evals/2026-10-01-ai-design-cases.md` · **Runner:** `docs/evals/run_ai_design_cases.py` with `EVAL_ENDPOINT=chat` (mode `auto`, as the operator gets it)
**Before:** the "After" column of `2026-10-01-results-phase-1-2.md`: `refine-multi/stream`, one flash call returning 3 options.
**Now:** branch `feature/editor-chat`. A specific request is a quick edit (router, applied at once). Anything else gets three directions: three parallel gemini-pro calls with the site's design context, then the design check.

## Results

| Case | Before | Now | Path taken |
|---|---|---|---|
| N1 two columns, photo on top on mobile | ✓ 25 s, 2 calls, 27k | ✓ **16 s, 1 call, 4k** | quick (router edited the grid classes) |
| N2 more elegant testimonials | ✓ 24 s, 2 calls, 27k | ✓ 108 s, 4 calls, 120k | 3 directions |
| N6 simplify pillars | ✓ 24 s, 2 calls, 21k | ✓ 86 s, 4 calls, 87k | 3 directions |
| N7 mobile photo grid | ✓ 13 s, 2 calls, 22k | ✓ **9 s, 1 call, 3k** | quick |
| N9 dishes as cards | ✓ 39 s, 2 calls, 29k | ✓ 74 s, 4 calls, 90k | 3 directions |
| C1 redesign → apply 2 → "dark background" | ✓ 94 s, 4 calls, 41k | ✓ 61 s (46 + 15), 5 calls, 76k | 3 directions, then quick |
| C2 title style across 3 sections | ✓ 60 s, 6 calls, 75k | ✓ 187 s (156 + 22 + 9), 9 calls, 114k | router asked for a redesign on turn 1, then quick ×2 |
| C7 3 cards → shorter → photos | ✓ 102 s, 6 calls, 96k | ✓ 153 s (113 + 13 + 28), 7 calls, 126k | 3 directions, then quick ×2 |

**8 of 8 complete.**

Checks after every case:
- **Colours:** no generic Tailwind palette classes. The design check had nothing to snap; the context alone kept the models on the palette.
- **Site check:** no new problems.
- **Languages:** nothing left in one language only.
- **Section names:** no problems.

The router took the specific requests (N1, N7, and the follow-ups in C1, C2 and C7) as quick edits. These are now 3–10× faster and use a fraction of the tokens.

**Timing.** The total time of an explore turn is the time of the slowest direction: 46–156 s. In the editor the first direction shows up much earlier; the browser checks measured it at 28 s. The runner reads the whole stream at once, so it can't measure that.

The C2 turn took 156 s, which is above the 120 s production gunicorn timeout. Directions now stop waiting at 100 s, and the ones not ready are reported as "took too long" (commit after the review).

## Design verdict (screenshots: scratchpad `ai-eval/chat/shots/`)

**The look of the site.** The directions read as part of this site, not as generic sections:
- the site's eyebrow style (`text-[11px] uppercase tracking-[0.14em]` in brand red or saffron);
- Fraunces display titles at the site's sizes;
- the bordered white card pattern (`border-[#E7DFD3] bg-white`);
- the gold rule and the checkered motif from the design guide.

**Why it fits.** Most directions explain themselves in a sentence that names the reused detail, e.g. "Títulos em Fraunces com o traço dourado (saffron #E3A11C)…" or "uses the site's bordered card pattern…".

**Case by case:**
- **N9:** all three directions built a real menu card grid. One used the menu-panel colour band (bordeaux) from the design guide.
- **C7:** the three event cards use the site's card pattern and type scale. This is a clear step up from the plain cards before.
- **N2 and N6:** quieter, editorial versions with generous spacing. The before/after difference is less dramatic than in N9/C7, because these sections were already reasonably styled.

**Weaknesses:**
- **WHY line:** it is missing in about 1 of 6 directions; the model dropped it.
- **Placeholders:** C7's Bolder and New layout still used placeholder images twice. The note in the UI shows it.
- **Off-palette colour:** `#6B1712` (the design guide's bordeaux) is reported as off-palette, because the tokens only list the colours used most often. That is harmless, but it shows the tokens and the design guide can disagree.

**Broken images in N2 and N9 screenshots: an artifact of the demo copy, not of the feature.** demo-ai-eval's media library rows point to `…/demo-ai-eval/site_images/…`, which doesn't exist in GCS (HTTP 404). The page images live under `…/checkinfaro-v3/…` (HTTP 200). The directions used the library URLs, as instructed. On a real site those are the real files.

## Cost

An explore turn is about 90–120k tokens: three pro calls, each with the design context of about 5k tokens plus the page. That is 3–4× the old single flash call. A quick edit is now 3–4k tokens, down from ~25k.

In practice, the specific edits that make up most of the day get much cheaper. The design explorations cost more, and they are now worth looking at.

## Follow-ups (not done)

- Report the first-option time in the runner: read the stream incrementally.
- Fix the demo copy's media library (or point design_context at URLs already used on the pages when a library URL 404s).
- Keep the colours the design guide names among the tokens, so they are not reported as off-palette.
