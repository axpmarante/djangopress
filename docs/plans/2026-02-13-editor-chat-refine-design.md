# Editor v2 Unified Chat Refinement — Design Document

## Problem

The editor v2 AI panel only supports section/element refinement with a simple input. The full chat refinement experience (persistent conversation, multi-turn context) only exists in the backoffice at `/backoffice/ai/chat/refine/`. Users must leave the editor to do conversational refinement, losing the live preview advantage.

## Solution

Rewrite the editor v2 AI panel as a unified chat that supports three scopes — full page, section, and element — while keeping one persistent conversation. The user picks a scope via a selector bar, types instructions, sees a live DOM preview, and applies or discards. Conversation history persists across scope changes and editor reloads via `RefinementSession`.

## Design

### 1. Scope Selector

A bar above the chat showing available targets:

```
[Page] [hero ▼] [cta_button]
```

- **Page** — always visible, targets full page refinement
- **Section** — shows currently selected section name, updates on canvas clicks
- **Element** — shows currently selected element ID (only stored `data-element-id`), updates on canvas clicks

Active scope is highlighted. Canvas selection updates the chips but does NOT auto-switch scope — user explicitly clicks the scope they want. Default is "Page" when nothing selected, "Section" when a section is clicked.

### 2. Chat Behavior

**One `RefinementSession` per editor session.** Created on first message, reused across scope changes. If the user reloads the editor, the session's message history is loaded and displayed (read-only).

**Message flow:**
1. User types instruction with an active scope
2. Message appears in chat with scope badge (`[page]`, `[hero]`, `[cta_button]`)
3. API call based on scope (see Backend section)
4. Assistant response appears with scope badge
5. Live DOM preview of the result
6. Apply/Discard buttons appear below the last message

**Conversation history** is sent with every request so the LLM has full multi-turn context. Cross-scope context is preserved (e.g., "Make this match the hero style" works even when targeting the footer).

### 3. Backend Endpoints

**New endpoints:**

- `POST /editor-v2/api/refine-page/` — calls `ContentGenerationService.refine_page_with_html()` without saving. Creates `PageVersion` for rollback. Returns `{ success, page: { html_template, content }, assistant_message, session_id }`.

- `POST /editor-v2/api/save-ai-page/` — saves full page result when user clicks Apply. Accepts `{ page_id, html_template, content }`. Replaces `page.html_content` and `page.content`.

- `GET /editor-v2/api/session/<page_id>/` — loads the most recent session's messages on editor init. Returns `{ session_id, messages: [{ role, content, scope }] }`.

**Existing endpoints (unchanged):**

- `POST /editor-v2/api/refine-section/` — section refinement without saving
- `POST /editor-v2/api/save-ai-section/` — save section result
- `POST /editor-v2/api/refine-element/` — element refinement without saving
- `POST /editor-v2/api/save-ai-element/` — save element result

### 4. Frontend — Rewritten `ai-panel.js`

**On editor init:** Fetch session history via GET endpoint, display as read-only messages, set `sessionId`.

**State:**
- `activeScope` = `'page'` | `'section'` | `'element'`
- `currentSection`, `currentElementId` — updated by canvas selection
- `sessionId`, `messages`, `pendingResult`, `originalHtml` — same as current

**Render structure:**
```
[scope bar: Page | Section:hero | Element:cta_btn]
[messages area - scrollable]
[apply/discard bar - when pending]
[style tags row]
[input row: textarea + send]
[enhance | suggest links]
```

**Messages:** Each shows role, scope badge, content. System notes for scope changes.

**Live preview:**
- Page: replace `.editor-v2-content` innerHTML with de-templatized result
- Section: replace `[data-section="name"]` outerHTML (existing)
- Element: replace `[data-element-id="id"]` outerHTML (existing)
- Discard restores `originalHtml` in all cases

**Apply:** Calls the corresponding save endpoint for the scope, then reloads page.

**Style tools:** Tag chips, enhance, suggest stay below the input — same as current implementation.

### 5. What's NOT in Scope (Future)

- **Reference image uploads** — add later
- **Image processing Phase 2** — add later
- **Draft persistence model** — save proposed changes as drafts that persist across sessions. Planned as a follow-up feature.
- **Model selector** — add later (currently hardcoded gemini-flash for section/element, gemini-pro for page)
