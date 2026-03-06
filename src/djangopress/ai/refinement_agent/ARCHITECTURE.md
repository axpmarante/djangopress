# Refinement Agent — Architecture Reference

## What It Does

The Refinement Agent is a lightweight LLM-powered router that sits between the editor's chat panel and the AI refinement pipeline. It analyzes each user request and picks the fastest execution path:

- **Direct edit** (~200ms) — CSS class swap or text replacement via BeautifulSoup, no AI call
- **AI delegation with minimal context** (~3s) — gemini-flash with only the context needed
- **Full AI pipeline** (~5-8s) — gemini-pro with all context (current behavior, unchanged)

## Why It Exists

Before the agent, every refinement request — whether "make background blue" or "redesign the entire hero with a testimonial carousel" — went through the same expensive pipeline:

1. Component selection LLM call (gemini-flash, ~1-3s)
2. Main refinement LLM call (gemini-pro, ~3-8s) with ALL context: project briefing, design guide, all pages list, full page HTML, component references

The agent eliminates unnecessary work. A CSS color change doesn't need project briefing, component references, or gemini-pro.

## Architecture

```
User instruction (from editor chat)
      |
      v
┌─────────────────────────┐
│   refine_multi()        │  editor_v2/api_views.py
│   (API endpoint)        │
└────────┬────────────────┘
         |
         v
┌─────────────────────────┐
│   RefinementAgent       │  ai/refinement_agent/agent.py
│   .handle()             │
│                         │
│   gemini-flash LLM      │  1-3 iterations
│   XML tool-use loop     │
│                         │
│   Tools:                │
│   ├─ inspect_html       │  read target HTML
│   ├─ get_design_guide   │  fetch design guide
│   ├─ get_briefing       │  fetch project briefing
│   ├─ get_pages_list     │  fetch all page slugs
│   ├─ update_styles      │  direct CSS class change
│   ├─ update_text        │  direct text replacement
│   └─ refine_with_ai     │  delegate to AI pipeline
└────────┬────────────────┘
         |
         v (one of three paths)
┌─────────────────────────┐
│ A) Direct edit result   │  {options: [{html}], routing_tier: 'direct_edit'}
│ B) AI delegation result │  {options: [{html}...], routing_tier: 'ai_flash' or 'ai_pro'}
│ C) Fallback result      │  {options: [{html}...], routing_tier: 'fallback'}
└─────────────────────────┘
         |
         v
┌─────────────────────────┐
│  Same response format   │  {options: [...], assistant_message, session_id}
│  back to editor JS      │
└─────────────────────────┘
```

## File Structure

```
ai/refinement_agent/
├── __init__.py
├── ARCHITECTURE.md      ← this file
├── agent.py             ← RefinementAgent class with tool-use loop
├── prompts.py           ← System prompt, tool definitions, decision guidelines
└── tools.py             ← Tool implementations + registry
```

## How the Agent Loop Works

Follows the same pattern as `site_assistant/services.py` but simplified (3 iterations max vs 8).

### XML Response Format

The agent communicates via XML tags in its LLM output:

**Mode 1 — Tool call (need data first):**
```xml
<actions>
[{"tool": "get_design_guide", "params": {}}]
</actions>
```

**Mode 2 — Final response with action:**
```xml
<response>
I've updated the background to a darker shade.
</response>
<actions>
[{"tool": "update_styles", "params": {"add_classes": "bg-gray-900", "remove_classes": "bg-white"}}]
</actions>
```

**Mode 3 — Delegate to AI pipeline:**
```xml
<response>
Let me redesign this section with a testimonial carousel.
</response>
<actions>
[{"tool": "refine_with_ai", "params": {"model": "gemini-pro", "include_components": true, "include_briefing": true}}]
</actions>
```

### Loop Flow

```
1. Build system prompt (includes target HTML, tool definitions, decision guidelines)
2. Build user prompt (instruction + multi_option flag)
3. Call gemini-flash
4. Parse XML response
5. Execute tools:
   - Read-only tool (inspect_html, get_design_guide, etc.)
     → feed results back as user message, loop to step 3
   - Direct edit tool (update_styles, update_text)
     → modify HTML in context, return {options: [{html}]}
   - Delegation tool (refine_with_ai)
     → call ContentGenerationService with agent-chosen model + context flags, return its result
6. If max iterations (3) reached without result → fallback to full AI pipeline
```

## Tools Reference

### Read-Only Tools

| Tool | What it returns | When the agent uses it |
|------|----------------|----------------------|
| `inspect_html` | Current target section/element HTML | Re-check after a direct edit |
| `get_design_guide` | Site's design guide markdown | Before layout changes for consistency |
| `get_briefing` | Project briefing text | Before content rewrites for brand voice |
| `get_pages_list` | All active pages (ID, title, slug) | When adding inter-page links |

### Direct Edit Tools (no AI call)

| Tool | Params | What it does |
|------|--------|-------------|
| `update_styles` | `{selector?, add_classes, remove_classes}` | Add/remove Tailwind CSS classes via BeautifulSoup |
| `update_text` | `{updates: {old_text: new_text}}` | Find and replace text in de-templatized HTML |

### AI Delegation Tools

| Tool | Params | What it does |
|------|--------|-------------|
| `refine_with_ai` | `{model, include_components, include_briefing, include_pages, include_design_guide}` | Calls `ContentGenerationService.refine_section_only()` or `refine_element_only()` with agent-chosen model and context flags |

## Context Flags

When the agent delegates to `refine_with_ai`, it controls what context the AI pipeline receives:

| Flag | What it controls | Token cost | When to include |
|------|-----------------|-----------|-----------------|
| `include_components` | ComponentRegistry.select_components() LLM call + component references | ~1,500 tokens + 1-3s latency | Adding carousel, tabs, accordion, modal, lightbox, slider, forms |
| `include_briefing` | Project briefing in prompt | ~1,000-5,000 tokens | Writing new content, matching brand voice |
| `include_pages` | All pages list in prompt | ~200-500 tokens | Adding navigation/links between pages |
| `include_design_guide` | Design guide in prompt | ~500-2,000 tokens | Layout changes, structural modifications, design consistency |

These flags map to `skip_*` parameters on `ContentGenerationService.refine_section_only()` and `refine_element_only()`.

## Decision Examples

| User says | Agent reasoning | Path | Speed |
|-----------|----------------|------|-------|
| "make background darker" | CSS class change | `update_styles` | ~200ms |
| "add more padding" | CSS class change | `update_styles` | ~200ms |
| "add shadow" | CSS class change | `update_styles` | ~200ms |
| "change heading to Welcome" | Text replacement | `update_text` | ~200ms |
| "make it 2 columns" | Layout change | `get_design_guide` → `refine_with_ai(gemini-flash)` | ~3s |
| "rewrite heading shorter" | Content rewrite | `get_briefing` → `refine_with_ai(gemini-flash)` | ~3s |
| "add testimonial carousel" | New interactive component | `refine_with_ai(gemini-pro, include_components=true)` | ~5-8s |
| "redesign this completely" | Creative, needs everything | `refine_with_ai(gemini-pro, include_components=true, include_briefing=true, include_pages=true)` | ~5-8s |

## Integration Points

### Entry Point: `editor_v2/api_views.py` → `refine_multi()`

The agent is called instead of direct `ContentGenerationService` calls:

```python
if use_agent and mode != 'create':
    agent = RefinementAgent()
    result = agent.handle(instruction=instructions, scope=scope, ...)
```

`mode='create'` (new section generation) always bypasses the agent and uses the full pipeline.

### Feature Flag: `config/settings.py`

```python
USE_REFINEMENT_AGENT = env('USE_REFINEMENT_AGENT', default='True') == 'True'
```

Set `USE_REFINEMENT_AGENT=False` in `.env` to disable the agent and fall back to the old direct pipeline.

### Fallback Behavior

The agent falls back to the full AI pipeline (gemini-pro, all context) when:
- The feature flag is `False`
- The agent raises an exception
- Max iterations (3) reached without a result
- The agent responds without calling any tool

### Services Layer: `ai/services.py`

`refine_section_only` and `refine_element_only` accept context-skipping flags:

```python
def refine_section_only(self, ...,
    skip_component_selection=False,
    skip_briefing=False,
    skip_pages_list=False,
    skip_design_guide=False,
)
```

### Prompt Layer: `ai/utils/prompts.py`

`get_section_refinement_prompt` and `get_element_refinement_prompt` accept:

```python
include_component_index: bool = True  # When False, skip ComponentRegistry.get_index() (~900 tokens saved)
```

### Analytics: `ai/models.py` → `AICallLog`

Two fields track routing decisions:
- `routing_tier` — `'direct_edit'`, `'ai_flash'`, `'ai_pro'`, or `'fallback'`
- `routing_ms` — milliseconds spent in agent routing before the main AI call

## Terminal Logging

The agent prints decisions to stdout for dev server visibility:

```
Agent iteration 1: has_response=True, actions=['update_styles']
Agent: executing update_styles({"add_classes": "bg-gray-900", "remove_classes": "bg-white"})
Agent: direct edit complete in 187ms
```

```
Agent iteration 1: has_response=False, actions=['get_design_guide']
Agent: executing get_design_guide({})
Agent iteration 2: has_response=True, actions=['refine_with_ai']
Agent: executing refine_with_ai({"model": "gemini-flash", "include_design_guide": true})
Agent: delegated to AI pipeline (ai_flash) after 523ms routing
```

## Relationship to Site Assistant

The Refinement Agent follows the same architectural pattern as `site_assistant/`:

| Aspect | Site Assistant | Refinement Agent |
|--------|---------------|-----------------|
| Location | `site_assistant/` | `ai/refinement_agent/` |
| Purpose | General site management chat | Editor refinement routing |
| Model | gemini-flash | gemini-flash |
| Max iterations | 8 | 3 |
| XML format | Same `<response>` + `<actions>` | Same |
| Tool dispatch | `ToolRegistry.execute()` | `tools.execute()` |
| Session storage | `AssistantSession` model | None (stateless per request) |
| Verification | Hallucination detection + retry | None (simpler scope) |
| Confirmation flow | `<pending_confirmation>` for destructive ops | None (no destructive ops) |

The agent is intentionally simpler — it only needs to route a single refinement request, not manage a full conversation.
