# Add Section Feature — Design

## Summary

Allow users to insert new AI-generated sections at any position in a page, without rewriting the entire page. Uses insertion lines between sections, context menu items, and the existing multi-option (A/B/C) flow.

## Frontend — Insertion Lines

New module `section-inserter.js`:

- Renders thin horizontal insertion zones between every pair of `[data-section]` elements, plus before the first and after the last section.
- Each zone contains a `+` button, visible on hover.
- Clicking `+`:
  1. Inserts a placeholder `<div class="ev2-section-placeholder">` at that DOM position (dashed border, muted text: "New section — describe it in the AI panel").
  2. Stores `insertPosition = { afterSection: 'section-name' | null }` (null = insert at top).
  3. Switches sidebar to AI tab.
  4. Sets `activeScope = 'new-section'`.
  5. Focuses the AI input.

Insertion lines re-render on page load and after any apply/discard.

## Frontend — Context Menu

Two new items when a section is selected:

- **Insert Section Before** — inserts placeholder before the selected section.
- **Insert Section After** — inserts placeholder after the selected section.

Both trigger the same flow as clicking a `+` insertion line.

## Frontend — AI Panel "New Section" Mode

When `activeScope === 'new-section'`:

- Scope dropdown shows "New Section" (read-only).
- User types a description and hits Send.
- Request: `POST /refine-multi/` with `mode: 'create'`, `insert_after: 'section-name'`, `instructions`.
- Response: 3 options with A/B/C tabs (same multi-option UI).
- Preview: each option replaces the placeholder's innerHTML.
- Apply: calls `/apply-option/` with `mode: 'insert'`, `insert_after`.
- Discard: removes the placeholder, resets state.

## Backend — `refine-multi` Extension

When `mode == 'create'`:

- Loads page's full HTML + design system + project briefing for context.
- Builds a "generate new section" prompt (different from "refine existing").
- Calls LLM to produce 3 section variations.
- Returns `{ options: [{html}, {html}, {html}], assistant_message }`.

## Backend — `apply-option` Extension

When `mode == 'insert'`:

- Takes `insert_after` (section name or null for top of page).
- Uses BeautifulSoup to find the anchor section.
- Inserts the new templatized section HTML after it (or at the top if null).
- Merges new translation keys into `page.content`.
- Creates a PageVersion for rollback.

## Prompt Design

The "generate new section" prompt receives:

- Full page HTML (for context/style consistency).
- Design system (colors, fonts, spacing).
- Project briefing.
- The user's description of what the section should contain.
- Position context (which section it comes after/before).

It must output a complete `<section data-section="name" id="name">` with `data-element-id` on editable elements, using Tailwind CSS, matching the page's existing style.

## Files Touched

| File | Change |
|------|--------|
| `editor_v2/static/editor_v2/js/modules/section-inserter.js` | **New** — insertion lines + placeholder management |
| `editor_v2/static/editor_v2/js/modules/ai-panel.js` | Add `new-section` scope, send with `mode: 'create'`, preview in placeholder |
| `editor_v2/static/editor_v2/js/modules/context-menu.js` | Add "Insert Section Before/After" items |
| `editor_v2/static/editor_v2/js/editor.js` | Import and init `section-inserter` module |
| `editor_v2/static/editor_v2/css/editor.css` | Styles for insertion lines + placeholder |
| `editor_v2/api_views.py` | Extend `refine_multi` (mode=create) and `apply_option` (mode=insert) |
| `ai/services.py` | Add `generate_section()` method (or extend existing) |
| `ai/utils/prompts.py` | Add section generation prompt template |