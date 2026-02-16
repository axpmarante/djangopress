# Multi-Option Refinement — Design Document

**Date:** 2026-02-16
**Status:** Approved

## Problem

When refining a section or element in the editor, the AI returns a single result. If the user doesn't like it, they must type another instruction, wait for another LLM call, and hope the next one is better. This back-and-forth is slow and frustrating.

## Solution

Present 3 distinct variations from a single LLM call. The user previews each option live in the DOM via tabs, picks one, and only then does templatize+translate run on the chosen option. This speeds up iteration without increasing cost.

## Scope

- **Section refinement** in editor v2 — yes
- **Element refinement** in editor v2 — yes
- **Page refinement** — no (stays single-result, already a heavier operation)
- **Backoffice generation/chat refine** — no (out of scope)

## Design

### 1. Prompt Changes

The `get_section_refinement_prompt()` and `get_element_refinement_prompt()` functions gain a `multi_option=True` parameter. When enabled, an instruction block is appended:

```
## Multiple Options
Return exactly 3 distinct variations of the result. Separate them with HTML comment markers:
<!-- OPTION_1 -->
(first variation HTML)
<!-- OPTION_2 -->
(second variation HTML)
<!-- OPTION_3 -->
(third variation HTML)

Make each variation meaningfully different: vary layout, visual emphasis, spacing, or structural approach. All 3 must satisfy the user's request.
```

When `multi_option=False` (default), prompts behave exactly as today. Nothing breaks.

### 2. Backend — Service Methods

`refine_section_only()` and `refine_element_only()` gain a `multi_option=True` parameter.

When `multi_option=True`:
1. Prompt includes the 3-option instruction block
2. LLM response is parsed by `_split_multi_options(html_response)` — splits on `<!-- OPTION_N -->` markers
3. Each option goes through BeautifulSoup validation (verify target section/element is present)
4. **No templatize step** — returns raw HTML with real text in the default language
5. Returns `{ options: [{ html }, { html }, { html }], assistant_message }`

**Fallback:** If the LLM returns fewer than 3 options (markers missing), return what we got. Frontend disables empty tabs.

### 3. API Endpoints

Two new endpoints in `editor_v2/api_views.py`:

**`POST /editor-v2/api/refine-multi/`**

Request:
```json
{
  "page_id": 1,
  "scope": "section",
  "section_name": "hero",
  "element_id": null,
  "instructions": "Make it bolder",
  "conversation_history": [...],
  "session_id": null
}
```

Response:
```json
{
  "success": true,
  "options": [
    { "html": "<section ...>...</section>" },
    { "html": "<section ...>...</section>" },
    { "html": "<section ...>...</section>" }
  ],
  "assistant_message": "Here are 3 variations...",
  "session_id": 42
}
```

Routes to `refine_section_only(multi_option=True)` or `refine_element_only(multi_option=True)` based on the `scope` field. Manages `RefinementSession` as usual.

**`POST /editor-v2/api/apply-option/`**

Request:
```json
{
  "page_id": 1,
  "scope": "section",
  "section_name": "hero",
  "element_id": null,
  "html": "<section ...>...</section>"
}
```

Response:
```json
{
  "success": true,
  "message": "Section saved",
  "page_id": 1
}
```

Runs `_templatize_and_translate()` on the chosen HTML, then does the same surgical save as existing `save_ai_section` / `save_ai_element` (BeautifulSoup find-and-replace, translation merge, PageVersion creation).

Existing single-option endpoints are unchanged.

### 4. Frontend — ai-panel.js

**New state:**
- `options[]` — array of 0-3 raw HTML strings
- `activeOption` — index (0, 1, or 2) of the previewed option

**`send()` change:**
- When `activeScope` is `'section'` or `'element'`, calls `/refine-multi/` instead of `/refine-section/` or `/refine-element/`
- On success, stores `options` array, sets `activeOption = 0`, calls `showPreview()`

**Option tabs — rendered between messages and Apply/Discard:**
```
[ A ]  [ B ]  [ C ]        [Apply] [Discard]
```

Clicking a tab:
1. Updates `activeOption`
2. Restores original DOM HTML
3. Injects the selected option's raw HTML into the DOM (no detemplatize needed — it's already real text in the default language)

**Apply:** Posts `options[activeOption]` to `/apply-option/` with scope info. Server templatizes, saves, page reloads.

**Discard:** Restores original DOM, clears `options` and `activeOption`.

**Page scope unchanged** — `activeScope === 'page'` still routes to the existing single-result `/refine-page/` endpoint.

### 5. CSS

Minimal additions to `editor.css`:
- `.ev2-option-tabs` — flex row container
- `.ev2-option-tab` — pill button matching existing `.ev2-scope-chip` style
- `.ev2-option-tab.active` — accent background, white text

### 6. Cost Analysis

| Flow | Before | After |
|------|--------|-------|
| Step 1 (LLM generation) | 1 call | 1 call (same, asks for 3 in one prompt) |
| Step 2 (templatize) | 1 call | 1 call (only on chosen option) |
| Total LLM calls | 2 | 2 |

Output tokens increase ~3x for Step 1 (3 HTML blocks instead of 1), but input tokens are identical. Net cost increase is modest since Gemini charges less for output than input. Templatize cost is unchanged.

### 7. No New Models or Migrations

Everything uses existing models (`RefinementSession`, `PageVersion`, `Page`). No new DB fields.
