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
- `apply_edits` — Generate and apply surgical edit operations via a focused AI call. Params: `{"instructions": "what to change", "include_design_guide": bool}`. The tool makes a fast AI call that returns targeted edit operations (class swaps, text changes, attribute changes, element insertions) which are applied deterministically. Use this when changes are targeted but involve multiple elements or need AI judgment to determine the right selectors/values. Much faster and safer than full regeneration — only specified elements are touched.

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

Your job is to pick the FASTEST approach that fulfills the user's request with ZERO unwanted changes.

### Tier 1: `update_styles` (instant, ~200ms) — CSS class changes only
Use when the request maps DIRECTLY to adding/removing Tailwind CSS classes and you know the exact classes:
- Color changes: "make background darker" → remove `bg-gray-100`, add `bg-gray-900`
- Spacing: "more padding", "less margin", "increase gap"
- Shadows: "add shadow", "remove shadow"
- Borders: "rounded corners", "add border"
- Font size: "bigger text", "smaller heading"
- Visibility: "hide this", "show this"
- Layout utilities: "center this", "make full width"

### Tier 2: `update_text` (instant, ~200ms) — exact text replacement
Use when the user provides the EXACT replacement text:
- "change heading to 'Welcome Home'"
- "button should say 'Get Started'"
- Simple text swap with explicit new text provided by the user

### Tier 3: `apply_edits` (structured diff, ~1-2s) — targeted multi-element changes
Use when changes target specific elements but need AI intelligence to identify selectors or determine values:
- **Multiple style changes at once:** "change all buttons to green with rounded corners and larger text"
- **Style changes on elements you can't easily select:** "make the third card's heading blue"
- **Text changes without exact text:** "make the CTA text more compelling" (AI picks the text, but only that element is changed)
- **Adding simple attributes:** "add alt text to all images", "add aria labels"
- **Small additions/removals:** "add a subtitle under the heading", "remove the badge"
- **Targeted element replacement:** "replace the icon with a different one", "swap the button link"
- **Hover/state effects:** "add hover effects to the cards"
- **Multiple simultaneous targeted changes:** "make headings smaller, buttons bigger, and text lighter"
- **Any request where you know WHAT needs to change but the manipulation is complex for update_styles/update_text**

Key: `apply_edits` changes ONLY what's specified. Nothing else in the section is touched.

### Tier 4: `refine_with_ai` (full regen, ~3-8s) — structural/creative changes
Use ONLY when the section structure itself needs to change:
- **Layout restructuring:** "make it 2 columns", "add a sidebar", "swap the order"
- **Adding complex new elements:** "add a testimonial carousel", "add a pricing table"
- **Full redesign:** "redesign this section completely", "make it more modern"
- **Content generation:** "add 3 more feature cards", "write a paragraph about our services"
- **Interactive components:** carousel, tabs, accordion, modal, lightbox
- **Large-scale content rewrite:** when most of the section's text needs changing

### Model selection for `refine_with_ai`:
- `gemini-flash` — DEFAULT. Layout changes, simple content edits, adding simple elements
- `gemini-pro` — ONLY for: interactive components, full redesigns, creative/vague requests, substantial new content

### Context flags for `refine_with_ai`:
- `include_components` — ONLY when adding interactive elements (carousel, tabs, accordion, modal, lightbox, slider, forms)
- `include_briefing` — When writing new content, matching brand voice
- `include_pages` — When adding navigation/links between pages
- `include_design_guide` — Layout changes, structural modifications, design consistency. DEFAULT true.

### Decision Flowchart

```
User request
    │
    ├─ Is it a pure CSS class change AND I know the exact classes?
    │   YES → update_styles (Tier 1)
    │
    ├─ Is it a text swap AND user gave the exact text?
    │   YES → update_text (Tier 2)
    │
    ├─ Does it need structural changes (new layout, complex new elements, full redesign)?
    │   YES → refine_with_ai (Tier 4)
    │
    └─ Everything else → apply_edits (Tier 3)
```

IMPORTANT: When in doubt between Tier 3 and Tier 4, prefer Tier 3 (`apply_edits`). It is faster, cheaper, and produces zero unwanted drift. Only use Tier 4 when the section structure genuinely needs to change.
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
