# Site Assistant v2 — Design Document

**Date:** 2026-03-04
**Status:** Approved
**Scope:** Service layer extraction, native function calling, router pattern, prompt restructuring

---

## Problem Statement

The current site assistant has several architectural issues:

1. **XML-based tool calling** — LLM outputs `<actions>` and `<response>` XML tags parsed with regex. Fragile, produces hallucinated JSON, and requires complex `_parse_response()` machinery.
2. **No service layer** — Business logic is duplicated across backoffice views, AI views, editor_v2 views, and assistant tools. The assistant tools are the weakest implementation (no slug dedup, no all-language propagation, no validation).
3. **Bloated prompts** — Tool definitions (~1500 tokens) + response protocol (~500 tokens) sent on every LLM call. System prompt is ~3000 tokens.
4. **Unnecessary tool calls** — Simple greetings ("hi") trigger 2 LLM calls because the assistant fetches `list_pages` + `get_stats` before responding.
5. **Bilingual responses** — Assistant responds in multiple languages instead of the site's default language.
6. **Missing capabilities** — Can't edit header/footer, no briefing management guidance.
7. **Dead code** — `update_translations` tool always returns an error but is still in tool definitions.
8. **Confirmation bug** — `delete_form` described as destructive in prompt but not in server-side `DESTRUCTIVE_TOOLS` set.

---

## Architecture Overview

```
                     USER MESSAGE
              POST /site-assistant/api/chat/
                         │
                         ▼
              ┌─────────────────────┐
              │   CONTEXT BUILDER   │
              │                     │
              │ Builds site snapshot│
              │ once per request    │
              └────────┬────────────┘
                       │
                       ▼
              ┌─────────────────────┐
              │  PHASE 1 — ROUTER   │
              │  (gemini-lite)      │
              │                     │
              │ Classifies intent   │
              │ Selects tool cats   │
              │ OR responds directly│
              └────────┬────────────┘
                       │
            ┌──────────┴──────────┐
            │                     │
     direct_response         intents[]
            │                     │
            ▼                     ▼
     Return immediately  ┌─────────────────────┐
     (0 tool calls)      │ PHASE 2 — EXECUTOR  │
                         │ (gemini-flash)       │
                         │                      │
                         │ Native function      │
                         │ calling loop         │
                         │ Only relevant tools  │
                         └──────────────────────┘
                                  │
                                  ▼
                         ┌─────────────────────┐
                         │   SERVICE LAYER      │
                         │                      │
                         │ PageService          │
                         │ MenuService          │
                         │ SettingsService      │
                         │ FormService          │
                         │ MediaService         │
                         │ GlobalSectionService │
                         │ NewsService          │
                         └──────────────────────┘
```

---

## Component 1: Service Layer

### Purpose

Single source of truth for all business logic. Views, assistant tools, management commands, and AI views all call the same services. No duplicate code.

### Directory Structure

```
core/
  services/
    __init__.py              → exports all services
    pages.py                 → PageService
    menu.py                  → MenuService
    settings.py              → SettingsService
    forms.py                 → FormService
    media.py                 → MediaService
    global_sections.py       → GlobalSectionService
    i18n.py                  → auto_translate_field() helper

news/
    services.py              → NewsService

ai/
    services.py              → ContentGenerationService (already exists)
```

### Design Principles

1. **Plain Python classes with static/classmethods** — no HTTP, no request objects, no Django messages framework.
2. **Consistent return format** — `{"success": True, "page": page_obj, "message": "..."}` or `{"success": False, "error": "..."}`.
3. **All business logic centralized** — validation, slug dedup, all-language propagation, version creation, cache clearing.
4. **Views become thin HTTP adapters** — parse request → call service → format HTTP response.
5. **Tools become thin LLM adapters** — parse LLM params → call service → format for LLM.

### Auto-Translation Helper (`core/services/i18n.py`)

All services that handle `_i18n` fields share a common pattern:

```python
def auto_translate_field(value, value_i18n=None):
    """Build a complete i18n dict from a single-language value.

    - If value_i18n provided with all languages, use as-is
    - If value provided (default lang), translate to other languages
    - Uses gemini-flash for translation (same as page translation pipeline)
    """
```

This means the LLM only needs to provide values in the default language. The service handles translation to other enabled languages.

### PageService (`core/services/pages.py`)

```python
class PageService:
    @staticmethod
    def list(active_only=False) -> dict

    @staticmethod
    def get(page_id=None, title=None) -> dict

    @staticmethod
    def get_info(page_id) -> dict
        # Returns page with parsed section names and content previews

    @staticmethod
    def create(title=None, slug=None, title_i18n=None, slug_i18n=None,
               html_content_i18n=None, is_active=True, user=None) -> dict
        # - Auto-translates title/slug to other languages
        # - Validates slug uniqueness across all languages
        # - Auto-generates slug from title if not provided

    @staticmethod
    def update_meta(page_id, title_i18n=None, slug_i18n=None,
                    is_active=None, sort_order=None) -> dict
        # - Validates slug uniqueness excluding self

    @staticmethod
    def delete(page_id) -> dict

    @staticmethod
    def reorder(order) -> dict

    @staticmethod
    def update_element_styles(page, selector=None, section_name=None,
                               new_classes="", user=None) -> dict
        # - Creates version before mutation
        # - Applies to ALL language copies

    @staticmethod
    def update_element_attribute(page, selector, attribute, value,
                                  user=None) -> dict
        # - Creates version before mutation
        # - Applies to ALL language copies

    @staticmethod
    def remove_section(page, section_name, user=None) -> dict
        # - Creates version, removes from ALL language copies

    @staticmethod
    def reorder_sections(page, order, user=None) -> dict

    @staticmethod
    def save_section_html(page, section_name, new_html, lang=None, user=None) -> dict
```

Key consolidation: `_apply_structural_change_to_all_langs()` from editor_v2 moves into PageService. Slug dedup from `update_page_settings()` API view moves into PageService.

### MenuService (`core/services/menu.py`)

```python
class MenuService:
    @staticmethod
    def list() -> dict                    # Tree structure with children

    @staticmethod
    def create(label=None, label_i18n=None, page_id=None, url=None,
               parent_id=None, sort_order=0) -> dict
        # - Auto-translates label
        # - Validates parent exists and nesting depth <= 1

    @staticmethod
    def update(menu_item_id, **kwargs) -> dict

    @staticmethod
    def delete(menu_item_id) -> dict

    @staticmethod
    def reorder(items) -> dict
```

### SettingsService (`core/services/settings.py`)

```python
class SettingsService:
    EDITABLE_FIELDS = { ... }             # Allowlist

    @staticmethod
    def get(fields=None) -> dict          # Read settings

    @staticmethod
    def update(updates) -> dict           # Update with allowlist validation + cache clear

    @staticmethod
    def get_snapshot() -> dict
        # Compact site state for router/executor:
        # {site_name, page_count, page_list, menu_summary,
        #  languages, default_lang, stats, installed_apps}
```

### GlobalSectionService (`core/services/global_sections.py`)

```python
class GlobalSectionService:
    @staticmethod
    def get(key) -> dict                  # Get section by key

    @staticmethod
    def get_html(key, lang=None) -> dict  # Get rendered HTML

    @staticmethod
    def refine(key, instructions, model='gemini-pro', user=None) -> dict
        # Delegates to ContentGenerationService.refine_global_section()
```

### FormService (`core/services/forms.py`)

```python
class FormService:
    @staticmethod
    def list() -> dict                    # With submission counts

    @staticmethod
    def create(name, slug, ...) -> dict   # Slug uniqueness validation

    @staticmethod
    def update(form_id=None, slug=None, **kwargs) -> dict

    @staticmethod
    def delete(form_id=None, slug=None) -> dict

    @staticmethod
    def list_submissions(form_slug=None, limit=10) -> dict
```

### MediaService (`core/services/media.py`)

```python
class MediaService:
    @staticmethod
    def list(search="", limit=20, file_type=None) -> dict

    @staticmethod
    def get(image_id) -> dict
```

### NewsService (`news/services.py`)

```python
class NewsService:
    @staticmethod
    def list(limit=None, published_only=False, category_id=None) -> dict

    @staticmethod
    def get(post_id=None, title=None) -> dict

    @staticmethod
    def create(title=None, title_i18n=None, slug_i18n=None,
               excerpt_i18n=None, ...) -> dict

    @staticmethod
    def update(post_id, **kwargs) -> dict

    @staticmethod
    def list_categories() -> dict
```

---

## Component 2: Router (Phase 1)

### Purpose

Lightweight intent classifier using gemini-lite (~200ms, ~300 tokens). Determines whether the request needs tools and which categories to load. For greetings and simple questions, responds directly without any tool calls.

### Router Prompt

```
You classify site management requests for {site_name}.
Respond ONLY with JSON, no other text.

Site: {page_count} pages, {menu_count} menu items, {image_count} images
Pages: {page_names_with_ids_brief}
Active page: {active_page_name or "none selected"}
Apps: {app_list}
Default language: {default_lang}

Categories:
- greeting: Greetings, thanks, general chat
- question: Questions answerable from the snapshot above
- pages: Create, list, find, delete, reorder pages
- page_edit: Modify sections/styles/text on the active page
- navigation: Menu items, links, navigation structure
- settings: Site config, contact info, design system colors/fonts
- briefing: Read or update the project briefing
- header_footer: Regenerate or edit header/footer with AI
- forms: Dynamic forms and submissions
- media: Browse/search image library
- news: Blog/news posts and categories
- stats: Detailed site statistics

Rules:
- If greeting or answerable from snapshot, write answer in direct_response (in {default_lang}).
- If it needs tools, set direct_response to null.
- A request can need multiple categories.
- "delete" requests need the relevant category.

Conversation context:
{last_3_turns_summary}

Message: {user_message}

JSON:
```

### Router Output

```json
{
  "intents": ["pages", "navigation"],
  "needs_active_page": false,
  "direct_response": null
}
```

Or for a greeting:
```json
{
  "intents": ["greeting"],
  "direct_response": "Olá! Como posso ajudar a gerir o site?"
}
```

### Multi-Step Handling

The router selects tool categories, not individual steps. The executor loop handles multi-step execution:

```
"Create an About page and add it to the menu"
→ Router: {"intents": ["pages", "navigation"]}
→ Executor gets: page tools + menu tools (union)
→ Executor loop: create_page → create_menu_item → text response
```

### Mid-Execution Tool Discovery

If the executor discovers it needs tools the router didn't select, a meta-tool allows dynamic expansion:

```python
types.FunctionDeclaration(
    name="request_additional_tools",
    description="Request tools from another category if needed mid-task",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "categories": types.Schema(type="ARRAY", items=types.Schema(type="STRING")),
        },
        required=["categories"],
    ),
)
```

When called, the service dynamically adds tool declarations and continues the loop.

---

## Component 3: Executor (Phase 2)

### Purpose

The main LLM agent using gemini-flash with native Gemini function calling. Receives only the tool categories selected by the router. Handles the tool execution loop.

### System Instruction

Split into focused sections (~800-1000 tokens total):

**Identity:**
```
You are the Site Assistant for {site_name}.
You help site managers manage their website through natural conversation.
Always respond in {default_lang}.
```

**Site Context:**
```
## Site Overview
Pages ({page_count}): {page_list_with_ids}
Menu: {menu_summary}
Languages: {languages} (default: {default_lang})
{installed_apps_section}
```

**Active Page Context** (refreshed after page-context mutations):
```
## Active Page: "{page_title}" (ID: {page_id})
Sections: {section_list_with_previews}
Languages: {page_languages}
```

**Behavior Rules:**
```
## Rules
- Provide text in {default_lang}. Translations are automatic. Only use
  _i18n params if the user explicitly wants different text per language.
- Use the lightest tool: CSS change → update_element_styles.
  Structural redesign → refine_section. Full page redesign → refine_page.
- For destructive actions (delete_page, delete_menu_item, delete_form):
  NEVER call the tool directly. Respond with a confirmation question first.
  Only call the delete tool after the user explicitly confirms.
- To update the project briefing, use update_settings with
  {"updates": {"project_briefing": "new text"}}.
- Never claim you performed an action without calling the tool.
- Keep responses concise and actionable.
```

**No tool definitions in the prompt** — they are passed as native `FunctionDeclaration` objects separately.

### Native Function Calling Loop

```python
def _execute_phase2(self, message, intents, context):
    # Build system instruction
    system_instruction = self._build_executor_prompt(context)

    # Build tool declarations from router intents
    tool_declarations = build_tool_declarations(intents)

    # Build conversation contents
    contents = self._build_contents(message, context)

    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        tools=tool_declarations,
        temperature=0.3,
    )

    for iteration in range(MAX_TOOL_ITERATIONS):
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=contents,
            config=config,
        )

        # Check for function calls
        function_calls = self._extract_function_calls(response)

        if not function_calls:
            # Text response — done
            return response.text

        # Execute each function call
        for fc in function_calls:
            if fc.name == "request_additional_tools":
                # Dynamic tool expansion
                new_tools = build_tool_declarations(fc.args["categories"])
                tool_declarations = merge_tools(tool_declarations, new_tools)
                config = config._replace(tools=tool_declarations)
                result = {"success": True, "message": "Tools added"}
            else:
                result = ToolRegistry.execute(fc.name, dict(fc.args), context)

            # Append function call + result to contents
            contents.append(response.candidates[0].content)
            contents.append(types.Content(role="user", parts=[
                types.Part.from_function_response(name=fc.name, response=result)
            ]))

        # Refresh system instruction if page context mutated
        if any(fc.name in PAGE_CONTEXT_MUTATIONS for fc in function_calls):
            system_instruction = self._build_executor_prompt(context)
            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=tool_declarations,
                temperature=0.3,
            )
```

### Context Refresh Strategy

- **Site overview** (page list, stats, menu): built once. Tool results carry updates.
- **Active page context** (sections, elements): refreshed after `PAGE_CONTEXT_MUTATIONS`.

```python
PAGE_CONTEXT_MUTATIONS = {
    'set_active_page', 'create_page',
    'refine_section', 'refine_page',
    'remove_section', 'reorder_sections',
    'update_element_styles', 'update_element_attribute',
    'refine_header', 'refine_footer',
}
```

---

## Component 4: Destructive Action Confirmation

### Approach

Conversation-based confirmation. No special XML tags, no `confirm_api` endpoint.

**Prompt rule:**
```
For destructive actions (delete_page, delete_menu_item, delete_form):
NEVER call the tool directly. Respond with a confirmation question first.
Only call the delete tool after the user explicitly confirms.
```

**Server-side safety net:**
```python
DESTRUCTIVE_TOOLS = {'delete_page', 'delete_menu_item', 'delete_form'}

# In ToolRegistry.execute():
if tool_name in DESTRUCTIVE_TOOLS:
    history = context.get('session').messages
    if not _has_recent_confirmation(history):
        return {
            'success': False,
            'message': 'Ask the user for confirmation before deleting.'
        }
```

**Flow:**
1. User: "Delete the FAQ page"
2. LLM responds with text: "Tem certeza que quer apagar a página FAQ?"
3. User: "sim"
4. Router classifies → Executor calls `delete_page(page_id=X)`

If the LLM ignores the prompt rule and calls delete directly, the server-side check blocks it and instructs the LLM to ask first.

---

## Component 5: Tool Declarations

### Location

`site_assistant/tool_declarations.py` — all FunctionDeclaration objects organized by category.

### Tool Categories

| Category | Tools | Count |
|----------|-------|-------|
| pages | list_pages, get_page_info, create_page, update_page_meta, delete_page, reorder_pages, set_active_page | 7 |
| page_edit | refine_section, refine_page, update_element_styles, update_element_attribute, remove_section, reorder_sections | 6 |
| navigation | list_menu_items, create_menu_item, update_menu_item, delete_menu_item | 4 |
| settings | get_settings, update_settings | 2 |
| header_footer | refine_header, refine_footer | 2 |
| forms | list_forms, create_form, update_form, delete_form, list_form_submissions | 5 |
| media | list_images | 1 |
| news | list_news_posts, get_news_post, create_news_post, update_news_post, list_news_categories | 5 |
| stats | get_stats | 1 |
| **Total** | | **33** |

Plus the `request_additional_tools` meta-tool (always included).

### Simplified Tool Params

Tools accept default-language values with optional i18n override:

```python
# create_page accepts:
#   title: str (default language, auto-translated)
#   title_i18n: dict (explicit per-language, optional)
#   slug: str (optional, auto-generated from title)
```

This means the LLM typically does:
```
create_page(title="Sobre Nós")
```

Instead of the current:
```
create_page(title_i18n={"pt": "Sobre Nós", "en": "About Us"}, slug_i18n={"pt": "sobre-nos", "en": "about-us"})
```

---

## File Changes Summary

### New Files

| File | Purpose |
|------|---------|
| `core/services/__init__.py` | Exports all services |
| `core/services/pages.py` | PageService |
| `core/services/menu.py` | MenuService |
| `core/services/settings.py` | SettingsService |
| `core/services/forms.py` | FormService |
| `core/services/media.py` | MediaService |
| `core/services/global_sections.py` | GlobalSectionService |
| `core/services/i18n.py` | auto_translate_field() helper |
| `news/services.py` | NewsService |
| `site_assistant/router.py` | Router (gemini-lite classifier) |
| `site_assistant/tool_declarations.py` | Native FC FunctionDeclaration schemas |

### Rewritten Files

| File | Changes |
|------|---------|
| `site_assistant/services.py` | Router → Executor pattern, native FC loop |
| `site_assistant/prompts.py` | Router prompt + Executor system instruction (no tool defs, no XML protocol) |
| `site_assistant/tools/site_tools.py` | Thin adapters calling services |
| `site_assistant/tools/page_tools.py` | Thin adapters calling PageService |
| `site_assistant/tools/news_tools.py` | Thin adapters calling NewsService |
| `site_assistant/tools/__init__.py` | Simplified registry |

### Modified Files

| File | Changes |
|------|---------|
| `site_assistant/views.py` | Remove `confirm_api`, simplify `chat_api` |
| `ai/utils/llm_config.py` | Add `get_completion_with_tools()` for native FC |

### Deleted Code

| What | Why |
|------|-----|
| `_parse_response()` in services.py | Replaced by native FC structured response |
| `_format_tool_results()` in services.py | Replaced by `Part.from_function_response()` |
| `TOOL_DEFINITIONS` in prompts.py | Replaced by FunctionDeclaration objects |
| `RESPONSE_PROTOCOL` in prompts.py | Gone — no XML format needed |
| `_verify_actions()` / `_retry_for_verification()` | Simplified — native FC constrains tool names |
| `confirm_api()` in views.py | Conversation-based confirmation instead |
| `update_translations` tool | Dead code (always returned error) |

### Gradual View Migration (Later)

Views in `backoffice/views.py`, `backoffice/api_views.py`, `editor_v2/api_views.py`, and `ai/views.py` can migrate to use services incrementally. The services are designed to work immediately for the assistant tools; view migration is a follow-up.

---

## Cost Comparison

| Scenario | Current (v1) | New (v2) |
|----------|-------------|----------|
| "hi" | 2 flash calls (~8K tokens) | 1 lite call (~300 tokens) |
| "how many pages?" | 2 flash calls (~8K tokens) | 1 lite call (~300 tokens) |
| "rename the hero title" | 1-2 flash calls (~4-8K tokens) | 1 lite + 1-2 flash (~4-6K tokens) |
| "create page + add to menu" | 2-3 flash calls (~12K tokens) | 1 lite + 2-3 flash (~10K tokens) |
| Complex multi-step | 4-8 flash calls (~30K+ tokens) | 1 lite + 3-6 flash (~20K tokens) |

The router adds ~200ms latency but saves tokens because:
- Greetings/questions skip Phase 2 entirely
- Executor prompt is smaller (no tool definitions, only relevant context)
- Native FC handles tool call formatting natively

---

## Implementation Order

1. **Service layer** — `core/services/` with all services. Foundation for everything else.
2. **LLM native FC support** — Add `get_completion_with_tools()` to `LLMBase`.
3. **Router** — `site_assistant/router.py` with gemini-lite classification.
4. **Tool declarations** — `site_assistant/tool_declarations.py` with FunctionDeclaration schemas.
5. **Executor rewrite** — `site_assistant/services.py` with native FC loop.
6. **Prompt restructuring** — `site_assistant/prompts.py` with new prompt architecture.
7. **Tool adapters** — Rewrite tools as thin adapters to services.
8. **New tools** — `refine_header`, `refine_footer`.
9. **View cleanup** — Remove `confirm_api`, simplify `chat_api`.
10. **Testing** — End-to-end testing of all flows.
