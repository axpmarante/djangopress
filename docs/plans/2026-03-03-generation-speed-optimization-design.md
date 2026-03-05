# Site Generation Speed Optimization — Design

**Date:** 2026-03-03
**Goal:** Cut 4-page site generation from ~19 min to ~8-9 min without compromising HTML quality.

## Problem

The site generation pipeline is 100% LLM-bound (Python overhead <0.5%). The current sequential flow:

```
Settings(9s) → Pages(772s) → DesignGuide(56s) → Header(100s) → Footer(211s) = 1148s (19m)
```

Header, footer, and design guide all block on page generation completing, even though they don't depend on page HTML.

## Benchmark Baseline (2026-03-03, gemini-pro, 4 pages)

| Metric | Value |
|--------|-------|
| Total time | 19m 8s (1148s) |
| Page generation | 772s (67%) |
| Footer | 211s (18%) |
| Header | 100s (9%) |
| Design guide | 56s (5%) |
| LLM calls | 20 |
| Overhead | <0.5% |

Per-page breakdown (4 calls each): component_selection(flash ~9s) → html_gen(pro ~65-165s) → metadata(lite ~1s) || templatize(flash ~17-29s).

## Changes

### 1. Design guide from briefing (before pages)

**File:** `ai/site_generator.py` — `generate_design_guide()`

Currently generates the design guide by analyzing the home page HTML (runs after pages). Change to generate from briefing + design system settings (no page HTML needed). This lets it run **before** any page generation, so ALL pages benefit from consistent styling.

- Input: project briefing, design system settings (colors, fonts, spacing, buttons), page list from plan
- Model: gemini-flash (documentation task, not HTML generation)
- Expected time: ~15-20s (down from 55s with pro)
- Called right after `configure_settings`, before page generation

### 2. Full pipeline parallelization

**File:** `ai/site_generator.py` — orchestrator / `generate_all_pages()`

After home page is generated, submit all remaining work to a single `ThreadPoolExecutor(max_workers=6)`:
- Remaining pages (About, Services, Contact, etc.)
- Header generation
- Footer generation

Home page must still be first (slug = `home`, inter-page linking context). Menu items still run last (need all pages in DB).

### 3. Flash model for header and footer

**File:** `ai/site_generator.py` — `generate_header()`, `generate_footer()`

Use gemini-flash instead of gemini-pro for header/footer generation. These are structurally simple (nav bars, link columns, social icons). Flash handles them well at 2-3x speed.

- Footer: 211s → ~70s
- Header: 100s → ~35s

### 4. Component selection → gemini-lite

**File:** `ai/utils/components/__init__.py` — `select_components()`

Switch from gemini-flash to gemini-lite. Component selection is a simple classification ("does this page need a slider/gallery/tabs?"). Gemini-lite handles this at ~1s instead of ~9s per page.

## Projected Timeline

```
OPTIMIZED:
Settings(9s) → DesignGuide(~20s, flash)
             → Home(~200s, pro)
             → [About | Services | Contact | Header(~35s) | Footer(~70s)] (parallel, 6 workers)
               Critical path = max(Services ~296s)

Total: 9 + 20 + 200 + 296 = ~525s = ~8.7 min
```

**~54% faster** (19m → 8.7m) with zero quality compromise on page HTML (still gemini-pro).

## Files to Modify

| File | Change |
|------|--------|
| `ai/site_generator.py` | Rewrite `generate_design_guide()` for briefing-based input; restructure pipeline parallelization; use flash for header/footer |
| `ai/utils/components/__init__.py` | Switch model from gemini-flash to gemini-lite in `select_components()` |

## Verification

1. Run benchmark before changes (baseline exists: `bench_20260303_144602_gemini_pro.json`)
2. Apply changes
3. Run benchmark after: `python scripts/benchmark_generate.py --delay 0`
4. Compare: total time, per-page times, quality of generated HTML
5. Verify design guide is present and consistent across pages
6. Verify header/footer quality with flash model
