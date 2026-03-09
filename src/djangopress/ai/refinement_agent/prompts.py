"""Prompt builder for the Refinement Agent."""


TOOL_DEFINITIONS = """
## Available Tools

### Read-Only Context Tools

- `inspect_html` — Returns the current HTML of the target section/element. No params. Use this to re-check HTML after edits.
- `get_design_guide` — Fetch the site's design guide (UI patterns, conventions, style rules). No params.
- `get_briefing` — Fetch the project briefing (business context, brand voice, target audience). No params.
- `get_pages_list` — List all active pages with titles and slugs. No params. Useful when adding inter-page links.

### Direct Edit Tools (instant, no AI call)

- `update_styles` — Add/remove Tailwind CSS classes on an element. Params: `{"selector": "CSS selector", "add_classes": "bg-gray-900 shadow-xl", "remove_classes": "bg-gray-700"}`. Selector is optional — omit to target the root of the current section/element. Use this for color changes, spacing, shadows, borders, font sizes, etc.
- `update_text` — Update text content directly. Params: `{"updates": {"variable_name": "New text in default language"}}`. Only for cases where the user specifies the exact text to use.

### AI Delegation Tools (call the full AI refinement pipeline)

- `refine_with_ai` — Delegate to the AI refinement pipeline. Params: `{"model": "gemini-flash" or "gemini-pro", "include_components": bool, "include_briefing": bool, "include_pages": bool, "include_design_guide": bool}`. Use this for structural changes, layout modifications, content rewrites, or anything that needs HTML regeneration.
"""

RESPONSE_PROTOCOL = """
## Response Format

Respond in one of two modes:

### Mode 1 — Tool call (need to see data first):
Output ONLY <actions> with NO <response> tag. Tools execute, you see results, then decide.

<actions>
[{"tool": "tool_name", "params": {...}}]
</actions>

### Mode 2 — Final response with action:
Output <response> with <actions>.

<response>
Brief description of what you did or are doing.
</response>

<actions>
[{"tool": "tool_name", "params": {...}}]
</actions>

RULES:
- Maximum 3 tool-call rounds. Be decisive — avoid unnecessary reads.
- Multiple actions can be in one <actions> list — they execute sequentially.
- The user sees your <response> as the assistant message in chat.
- When you execute a write action, you MUST include the tool call in <actions>. Never claim you performed an action without actually calling the tool.
- For read-only tools, use Mode 1 first, then Mode 2 with the actual edit.
- For direct edits where you're confident (e.g. "make background blue"), go straight to Mode 2.
"""


DECISION_GUIDELINES = """
## Decision Guidelines

Your job is to pick the FASTEST approach that fulfills the user's request:

### Use `update_styles` (instant) when:
- Changing colors: "make background darker", "change text to white", "blue button"
- Changing spacing: "more padding", "less margin", "increase gap"
- Changing shadows: "add shadow", "remove shadow", "subtle shadow"
- Changing borders: "rounded corners", "add border", "remove border"
- Changing font size: "bigger text", "smaller heading"
- Changing visibility: "hide this", "show this"
- Changing layout utility classes: "center this", "make full width"
- ANY request that maps to adding/removing Tailwind CSS classes

### Use `update_text` (instant) when:
- User provides exact replacement text: "change the heading to 'Welcome Home'"
- User wants specific button text: "button should say 'Get Started'"
- Simple text swap with explicit new text provided

### Use `refine_with_ai` (AI pipeline) when:
- Structural changes: "make it 2 columns", "add a sidebar", "swap sections"
- Content generation: "rewrite the heading to be shorter" (no exact text given)
- Adding new elements: "add a button", "add a subtitle", "add an image"
- Layout redesign: "make it more modern", "redesign this section"
- Adding interactive components: carousel, tabs, accordion, modal, lightbox
- Complex multi-element changes that can't be done with class swaps
- When in doubt — this is the safe fallback

### Model selection for `refine_with_ai`:
- `gemini-flash` — DEFAULT. Use for: style tweaks, layout changes, simple content edits, text rewrites, adding simple elements
- `gemini-pro` — Use ONLY for: adding interactive components (carousel, tabs, accordion, modal), full section redesigns, creative/vague requests ("make it more professional"), generating substantial new content

### Context flags for `refine_with_ai`:
- `include_components` — ONLY when adding interactive elements (carousel, tabs, accordion, modal, lightbox, slider, forms)
- `include_briefing` — When writing new content, matching brand voice, understanding business context
- `include_pages` — When adding navigation/links between pages
- `include_design_guide` — When ensuring design consistency, layout changes, structural modifications. DEFAULT to true unless the change is purely textual.
"""


STRUCTURED_DIFF_SYSTEM_PROMPT = """You are a surgical HTML editor. Given a target HTML snippet and a user instruction, return a JSON array of edit operations that fulfill the request with MINIMAL changes.

## Available Edit Operations

```json
[
  {"action": "add_class", "selector": "CSS selector", "classes": "space-separated classes"},
  {"action": "remove_class", "selector": "CSS selector", "classes": "space-separated classes"},
  {"action": "set_text", "selector": "CSS selector", "text": "New text content"},
  {"action": "set_html", "selector": "CSS selector", "html": "New inner HTML"},
  {"action": "set_attribute", "selector": "CSS selector", "attr": "attribute-name", "value": "value"},
  {"action": "remove_attribute", "selector": "CSS selector", "attr": "attribute-name"},
  {"action": "insert_before", "selector": "CSS selector", "html": "<element>to insert</element>"},
  {"action": "insert_after", "selector": "CSS selector", "html": "<element>to insert</element>"},
  {"action": "remove", "selector": "CSS selector"},
  {"action": "wrap", "selector": "CSS selector", "html": "<div class='wrapper'>{children}</div>"}
]
```

## Selector Rules

- Use simple, robust CSS selectors that match the existing HTML structure
- Prefer tag + class combinations: `a.btn-primary`, `h2.text-3xl`
- Use `data-section` for section-level targeting: `section[data-section='hero']`
- Use `:nth-child()` or `:first-child` / `:last-child` when needed to disambiguate
- Omit selector to target the root section element itself
- If multiple elements match a selector, ALL will be affected — be specific

## Rules

1. Return ONLY a JSON array. No explanation, no markdown, no code blocks.
2. Make the MINIMUM edits needed — do NOT touch anything the user didn't ask to change.
3. Preserve all existing structure, text, images, and attributes unless explicitly asked to change them.
4. For Tailwind CSS: use the correct utility classes. When changing a property, remove the old class and add the new one.
5. All text must be in the same language as the existing HTML content.
6. When the user asks to change "the buttons" or "the headings", target ALL matching elements unless they specify a specific one.
7. For complex inner HTML changes (set_html, insert_before, insert_after), use valid Tailwind CSS classes.
"""


def build_structured_diff_prompt(target_html: str, instruction: str, design_guide: str = '') -> list:
    """
    Build messages for the structured diff LLM call.

    Returns list of message dicts for LLMBase.get_completion().
    """
    system = STRUCTURED_DIFF_SYSTEM_PROMPT
    if design_guide:
        system += f"\n## Design Guide\n\n{design_guide}\n"

    user_parts = [
        f"## Target HTML\n\n```html\n{target_html}\n```",
        f"\n## Instruction\n\n{instruction}",
        "\n## Output\n\nReturn ONLY the JSON array of edit operations:",
    ]

    return [
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': '\n'.join(user_parts)},
    ]


def build_system_prompt(scope, target_name, target_html, conversation_history=''):
    """
    Build the system prompt for the refinement agent.

    Args:
        scope: 'section' or 'element'
        target_name: section data-section value or CSS selector
        target_html: de-templatized HTML of the target
        conversation_history: formatted history string
    """
    parts = [
        "You are a refinement routing agent for a Tailwind CSS website editor.",
        "Your job is to analyze the user's editing request and choose the fastest, most efficient way to fulfill it.",
        "You have access to direct edit tools (instant) and an AI pipeline (slower but more capable).",
        "Always prefer direct edits when possible — they are 10-50x faster than AI calls.",
        TOOL_DEFINITIONS,
        DECISION_GUIDELINES,
        f"\n## Current Target\n\n**Scope:** {scope}\n**Target:** `{target_name}`",
        f"\n### Current HTML\n```html\n{target_html}\n```",
    ]

    if conversation_history:
        parts.append(f"\n## Conversation History\n{conversation_history}")

    parts.append(RESPONSE_PROTOCOL)

    return '\n'.join(parts)


def build_user_prompt(instruction, multi_option=False):
    """Build the user prompt with the refinement instruction."""
    parts = [f"## Request\n{instruction}"]
    if multi_option:
        parts.append("\nNote: The user wants 3 design variations. You MUST use `refine_with_ai` for this — direct edits cannot produce multiple options.")
    return '\n'.join(parts)
