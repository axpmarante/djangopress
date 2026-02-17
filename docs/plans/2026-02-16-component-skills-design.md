# Component Skills Architecture for LLM Prompts

**Date:** 2026-02-16
**Status:** Approved

## Problem

The current prompt system injects a monolithic ~900-token component reference into every HTML-generating prompt, regardless of whether the request needs those components. This ceiling prevents adding richer, more detailed component documentation — adding more detail would bloat every prompt.

## Solution

Replace the monolithic `_get_components_reference()` with a **Component Registry + two-pass LLM flow**:

1. **Component skills** live as Python modules in `ai/utils/components/`, each with a compact `INDEX_ENTRY` and a rich `FULL_REFERENCE`.
2. **Pass 1 (skill selection):** A fast/cheap model (gemini-flash) sees the compact index + user request + existing page HTML → returns a JSON array of component names needed.
3. **Pass 2 (generation):** The main model (gemini-pro) sees core rules + full references for only the selected components → generates HTML.

## Component Skill Structure

Each component is a Python module:

```
ai/utils/components/
├── __init__.py          # ComponentRegistry + auto-discovery
├── carousel.py          # Splide.js carousel/slider
├── lightbox.py          # Image lightbox/gallery
├── tabs.py              # Alpine.js tabs
├── accordion.py         # Alpine.js accordion
├── modal.py             # Alpine.js modal
└── forms.py             # DynamicForm submission
```

Each module exports:

- `NAME` — identifier string (e.g. `"carousel"`)
- `DESCRIPTION` — one-line description for humans
- `INDEX_ENTRY` — 1-2 line summary with key attributes/patterns for the LLM index
- `FULL_REFERENCE` — rich, detailed documentation (can be 50-200+ lines)

## ComponentRegistry

`ai/utils/components/__init__.py` provides:

- `discover()` — auto-imports all `.py` files in the directory, registers by `NAME`
- `get_index()` — returns compact index of all components (~200 tokens), used in every HTML prompt
- `get_references(names)` — returns concatenated `FULL_REFERENCE` for selected component names
- `select_components(user_request, existing_html, llm)` — runs pass 1: sends index + request + HTML to gemini-flash, returns list of component names

## Pass 1 Prompt (Skill Selection)

```
You are a component selector. Given a user request and optionally existing page HTML,
return a JSON array of component names that are needed.

Available components:
{index}

Return ONLY a JSON array like: ["carousel", "lightbox"]
Return [] if no components are needed.
```

Uses gemini-flash. Tiny input (~300-500 tokens), tiny output (JSON array).

## Integration Points

### What changes:

- **`ai/utils/components/`** — new directory with 6 component modules + registry
- **`ai/utils/prompts.py`** — remove `_get_components_reference()`, update 5 prompt builders to accept `component_references` param, always inject compact index
- **`ai/services.py`** — add pass 1 call before each of the 5 HTML-generating methods: `generate_page()`, `refine_page()`, `refine_section_only()`, `refine_element_only()`, `generate_section()`

### What stays the same:

- All 9 other prompt builders (templatize, metadata, bulk analysis, etc.)
- Two-step generation flow (HTML → templatize)
- Model routing (gemini-pro for HTML gen, gemini-flash for templatize/translate)
- Chat refinement conversation history
- All API endpoints and editor integration
- `editor_v2/api_views.py` — delegates to services.py, no direct changes

## Adding New Components

1. Create `ai/utils/components/my_component.py` with `NAME`, `DESCRIPTION`, `INDEX_ENTRY`, `FULL_REFERENCE`
2. Done — registry auto-discovers it, index updates automatically, pass 1 can select it

## Trade-offs

- (+) Component docs can be as detailed as needed without bloating every prompt
- (+) Only relevant component docs are injected — targeted context
- (+) Easy to extend — drop a new .py file
- (+) Pass 1 understands nuanced requests (LLM-based, not keyword matching)
- (-) Adds one extra LLM call per HTML generation (but gemini-flash is fast and cheap)
- (-) Pass 1 could occasionally miss a component (index serves as fallback knowledge)