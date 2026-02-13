# Element-Level AI Refinement — Design

## Problem

Editor v2's AI refinement only works at the section level. Users want to refine smaller elements (buttons, cards, feature blocks) with more targeted prompts, mirroring the page→section progression.

## Approach

New dedicated endpoint, service method, and prompt for element refinement. Same architecture as section refinement but scoped one level tighter: the **section** provides context, the **element** is the target.

## Frontend — AI Panel (`ai-panel.js`)

The AI tab adapts based on what's selected:

| Selection | Behavior |
|-----------|----------|
| `<section>` element | Existing section refinement (`/refine-section/`) |
| Element with `data-element-id` | New element refinement (`/refine-element/`) |
| Element without ID, not a section | "Select a section or labeled element to use AI refinement" |

Header adapts: "Refining section: **hero**" vs "Refining element: **hero_cta_button**".

API call for element refinement:
```javascript
api.post('/refine-element/', {
    page_id, section_name, element_id,
    instructions, conversation_history, session_id
})
```

Apply calls `/save-ai-element/`, then `window.location.reload()`.

## Backend — API Endpoints (`editor/api_views.py`)

### `refine_element` (POST)
- `@superuser_required`
- Input: `page_id`, `section_name`, `element_id`, `instructions`, `conversation_history`, `session_id`
- Creates/loads `RefinementSession` with title `[element_id] {instructions[:60]}`
- Calls `service.refine_element_only(...)`
- Returns: `{ element: { html_template, content }, assistant_message, session_id }`

### `save_ai_element` (POST)
- `@superuser_required`
- Input: `page_id`, `section_name`, `element_id`, `html_template`, `content`
- BeautifulSoup finds element by `[data-element-id="xxx"]` in page HTML
- Replaces element, merges translations, creates PageVersion
- Returns success

Both endpoints registered in `editor_v2/urls.py` and `editor/urls.py`.

## AI Service (`ai/services.py`)

### `refine_element_only()`

1. Load page, de-templatize the **parent section's** HTML (not full page — section is enough context)
2. Extract the target element's HTML from the de-templatized section
3. Build prompt via `PromptTemplates.get_element_refinement_prompt()`
4. Call LLM → extract the target element from response
5. Templatize + translate the element fragment
6. Return `{ html_template, content, assistant_message }`

## Prompt (`ai/utils/prompts.py`)

### `get_element_refinement_prompt()`

**System prompt:**
- "Edit ONLY the element with `data-element-id="{element_id}"`. Return ONLY that element."
- May restructure children freely
- Must keep `data-element-id` on the element and on editable children
- Tailwind CSS, responsive, preserve `data-overlay`/`data-bg-video` if present

**User prompt:**
- Section HTML as context (not full page)
- Target element HTML highlighted
- Conversation history
- User's instructions
- "Return ONLY the updated element. Nothing else."

## Edge Cases

- **Element ID preservation:** Prompt enforces it, save endpoint validates before replacing
- **Translation merging:** Only update keys from the refined element, preserve everything else
- **Tag changes:** Allowed — BeautifulSoup finds by `data-element-id`, not tag name
- **Nested element IDs:** Prompt tells LLM to preserve `data-element-id` on editable children
- **No new models/migrations:** Reuses `RefinementSession` and `PageVersion`

## Files to Modify

1. `editor_v2/static/editor_v2/js/modules/ai-panel.js` — detect section vs element, call appropriate endpoint
2. `editor/api_views.py` — new `refine_element` and `save_ai_element` endpoints
3. `ai/services.py` — new `refine_element_only()` method
4. `ai/utils/prompts.py` — new `get_element_refinement_prompt()`
5. `editor_v2/urls.py` — register new endpoints
6. `editor/urls.py` — register new endpoints (shared)
7. `templates/base.html` — cache bust
