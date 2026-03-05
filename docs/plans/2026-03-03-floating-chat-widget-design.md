# Floating Chat Widget for Backoffice

**Date:** 2026-03-03
**Status:** Approved

## Overview

A floating chat bubble/panel present on all backoffice pages, powered by the existing site-assistant backend. It auto-detects which backoffice page the user is on and injects that context into conversations, enabling quick page edits and site management without leaving the current view.

## Decisions

- **Approach:** Include in `backoffice/base.html` via `{% include %}` — reuses 100% of existing site-assistant API
- **Context:** Full page context — auto-detects current page ID + backoffice section
- **Sessions:** Persistent — one session stays open across page navigations, stored in `localStorage`
- **Scope:** Backoffice only (`/backoffice/*` pages)
- **UI:** Slide-up panel from bottom-right corner (~400x550px)

## Architecture

### Files

| File | Change |
|------|--------|
| `backoffice/templates/backoffice/includes/chat_widget.html` | **New** — self-contained Alpine.js widget |
| `backoffice/templates/backoffice/base.html` | Add `{% block chat_context %}` + `{% include %}` |
| `backoffice/templates/backoffice/page_edit.html` | Override `{% block chat_context %}` with page ID |
| `backoffice/templates/backoffice/ai_chat_refine.html` | Override `{% block chat_context %}` with page ID |
| `backoffice/templates/backoffice/process_images.html` | Override `{% block chat_context %}` with page ID |
| `backoffice/templates/backoffice/header_edit.html` | Override `{% block chat_context %}` with section |
| `backoffice/templates/backoffice/footer_edit.html` | Override `{% block chat_context %}` with section |

No new Django views, models, or URL patterns required.

### Context Detection

The widget reads context from `window.__chatContext` (set via `{% block chat_context %}`):

| Backoffice page | Context |
|---|---|
| `/backoffice/page/<id>/edit/` | `{pageId: <id>, section: "page_edit", pageTitle: "..."}` |
| `/backoffice/ai/chat/refine/<id>/` | `{pageId: <id>, section: "chat_refine", pageTitle: "..."}` |
| `/backoffice/page/<id>/images/` | `{pageId: <id>, section: "process_images", pageTitle: "..."}` |
| `/backoffice/settings/header/` | `{section: "header_edit"}` |
| `/backoffice/settings/footer/` | `{section: "footer_edit"}` |
| Other pages | Fallback URL parsing extracts context from URL patterns |

The `pageId` maps to `active_page_id` in the site-assistant API. The `section` is prepended to messages as a system hint.

### API Integration

Uses existing endpoints — no changes needed:

- `POST /site-assistant/api/chat/` — send message with `session_id`, `message`, `active_page_id`
- `POST /site-assistant/api/confirm/` — destructive action confirmations
- `GET /site-assistant/api/sessions/` — session list for dropdown
- `GET /site-assistant/api/sessions/<id>/` — load full session

### UI States

**Closed:** Floating bubble (bottom-right, `z-50`) with chat icon. Unread dot indicator.

**Open:** 400x550px panel with:
- Header: title, context badge, minimize/new-session buttons
- Messages: user/assistant bubbles, action chips, tool result tables, confirmation cards
- Input: text field + send button, typing indicator

### Session Persistence

- `localStorage.chatWidgetSessionId` stores the current session ID
- Session persists across page navigations
- "New Session" button clears it and starts fresh
- Session dropdown shows recent sessions from `/site-assistant/api/sessions/`
