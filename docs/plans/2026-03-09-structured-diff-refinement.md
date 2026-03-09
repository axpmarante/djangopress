# Structured Diff Refinement Tier — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a new `apply_edits` tool to the Refinement Agent that uses a focused LLM call to generate surgical edit operations (class swaps, text changes, attribute edits, element insertions/removals), applied deterministically by BeautifulSoup — eliminating unwanted drift when only small changes are needed.

**Architecture:** New tool `apply_edits` in `ai/refinement_agent/tools.py` makes a dedicated gemini-flash call with a specialized prompt that returns a JSON list of edit operations. A new `edit_operations.py` module applies those operations via BeautifulSoup. The routing agent's decision guidelines are updated to prefer this mid-tier over full AI regen when changes are targeted but too complex for simple `update_styles`/`update_text`.

**Tech Stack:** Python, BeautifulSoup4, gemini-flash (via LLMBase), JSON edit operations

---

### Task 1: Create the edit operations executor

**Files:**
- Create: `src/djangopress/ai/refinement_agent/edit_operations.py`

**Step 1: Create the edit operations module**

This module takes a list of structured edit operations and applies them to HTML via BeautifulSoup. Each operation is a dict with an `action` key and action-specific params.

```python
"""Apply structured edit operations to HTML via BeautifulSoup."""

import logging
import re
from bs4 import BeautifulSoup, NavigableString

logger = logging.getLogger(__name__)


VALID_ACTIONS = {
    'add_class', 'remove_class', 'set_text', 'set_html',
    'set_attribute', 'remove_attribute', 'insert_before',
    'insert_after', 'remove', 'wrap',
}


def apply_edits(html: str, edits: list) -> dict:
    """
    Apply a list of edit operations to HTML.

    Args:
        html: The target HTML string (section or element)
        edits: List of edit operation dicts

    Returns:
        dict with 'success', 'html', 'applied', 'errors'
    """
    soup = BeautifulSoup(html, 'html.parser')
    applied = []
    errors = []

    for i, edit in enumerate(edits):
        action = edit.get('action', '')
        if action not in VALID_ACTIONS:
            errors.append(f"Edit {i}: unknown action '{action}'")
            continue

        try:
            result = _apply_single_edit(soup, edit)
            if result.get('success'):
                applied.append(f"Edit {i}: {action} — {result.get('message', 'ok')}")
            else:
                errors.append(f"Edit {i}: {action} — {result.get('message', 'failed')}")
        except Exception as e:
            errors.append(f"Edit {i}: {action} — exception: {e}")

    new_html = str(soup)
    # Strip wrapper if BeautifulSoup added <html><body>
    if new_html.startswith('<html><body>'):
        new_html = new_html[12:-14]

    return {
        'success': len(applied) > 0,
        'html': new_html,
        'applied': applied,
        'errors': errors,
    }


def _find_elements(soup, selector: str) -> list:
    """Find elements by CSS selector. Returns list."""
    if not selector:
        # Target root element
        root = soup.find('section') or next(soup.children, None)
        return [root] if root and hasattr(root, 'get') else []
    return soup.select(selector)


def _apply_single_edit(soup, edit: dict) -> dict:
    action = edit['action']
    selector = edit.get('selector', '')

    if action == 'add_class':
        elements = _find_elements(soup, selector)
        if not elements:
            return {'success': False, 'message': f'No elements found for: {selector or "(root)"}'}
        classes = edit.get('classes', '').split()
        for el in elements:
            current = set(el.get('class', []))
            current.update(classes)
            el['class'] = sorted(current)
        return {'success': True, 'message': f'Added {classes} to {len(elements)} element(s)'}

    elif action == 'remove_class':
        elements = _find_elements(soup, selector)
        if not elements:
            return {'success': False, 'message': f'No elements found for: {selector or "(root)"}'}
        classes = edit.get('classes', '').split()
        for el in elements:
            current = set(el.get('class', []))
            for cls in classes:
                current.discard(cls)
                # Pattern removal: "bg-" removes all bg-* classes
                if cls.endswith('-'):
                    current = {c for c in current if not c.startswith(cls)}
            if current:
                el['class'] = sorted(current)
            elif 'class' in el.attrs:
                del el['class']
        return {'success': True, 'message': f'Removed {classes} from {len(elements)} element(s)'}

    elif action == 'set_text':
        elements = _find_elements(soup, selector)
        if not elements:
            return {'success': False, 'message': f'No elements found for: {selector or "(root)"}'}
        text = edit.get('text', '')
        for el in elements:
            el.string = text
        return {'success': True, 'message': f'Set text on {len(elements)} element(s)'}

    elif action == 'set_html':
        elements = _find_elements(soup, selector)
        if not elements:
            return {'success': False, 'message': f'No elements found for: {selector or "(root)"}'}
        inner_html = edit.get('html', '')
        new_content = BeautifulSoup(inner_html, 'html.parser')
        for el in elements:
            el.clear()
            for child in list(new_content.children):
                el.append(child.__copy__() if hasattr(child, '__copy__') else NavigableString(str(child)))
        return {'success': True, 'message': f'Set inner HTML on {len(elements)} element(s)'}

    elif action == 'set_attribute':
        elements = _find_elements(soup, selector)
        if not elements:
            return {'success': False, 'message': f'No elements found for: {selector or "(root)"}'}
        attr = edit.get('attr', '')
        value = edit.get('value', '')
        if not attr:
            return {'success': False, 'message': 'No attr specified'}
        for el in elements:
            el[attr] = value
        return {'success': True, 'message': f'Set {attr} on {len(elements)} element(s)'}

    elif action == 'remove_attribute':
        elements = _find_elements(soup, selector)
        if not elements:
            return {'success': False, 'message': f'No elements found for: {selector or "(root)"}'}
        attr = edit.get('attr', '')
        if not attr:
            return {'success': False, 'message': 'No attr specified'}
        for el in elements:
            if attr in el.attrs:
                del el[attr]
        return {'success': True, 'message': f'Removed {attr} from {len(elements)} element(s)'}

    elif action == 'insert_before':
        elements = _find_elements(soup, selector)
        if not elements:
            return {'success': False, 'message': f'No elements found for: {selector or "(root)"}'}
        new_html = edit.get('html', '')
        fragment = BeautifulSoup(new_html, 'html.parser')
        for el in elements:
            for child in reversed(list(fragment.children)):
                el.insert_before(child.__copy__() if hasattr(child, '__copy__') else NavigableString(str(child)))
        return {'success': True, 'message': f'Inserted before {len(elements)} element(s)'}

    elif action == 'insert_after':
        elements = _find_elements(soup, selector)
        if not elements:
            return {'success': False, 'message': f'No elements found for: {selector or "(root)"}'}
        new_html = edit.get('html', '')
        fragment = BeautifulSoup(new_html, 'html.parser')
        for el in elements:
            for child in list(fragment.children):
                el.insert_after(child.__copy__() if hasattr(child, '__copy__') else NavigableString(str(child)))
        return {'success': True, 'message': f'Inserted after {len(elements)} element(s)'}

    elif action == 'remove':
        elements = _find_elements(soup, selector)
        if not elements:
            return {'success': False, 'message': f'No elements found for: {selector or "(root)"}'}
        for el in elements:
            el.decompose()
        return {'success': True, 'message': f'Removed {len(elements)} element(s)'}

    elif action == 'wrap':
        elements = _find_elements(soup, selector)
        if not elements:
            return {'success': False, 'message': f'No elements found for: {selector or "(root)"}'}
        wrapper_html = edit.get('html', '')
        if '{children}' not in wrapper_html:
            return {'success': False, 'message': 'wrap html must contain {children} placeholder'}
        for el in elements:
            children_html = ''.join(str(c) for c in el.children)
            final_html = wrapper_html.replace('{children}', children_html)
            new_el = BeautifulSoup(final_html, 'html.parser')
            el.replace_with(new_el)
        return {'success': True, 'message': f'Wrapped {len(elements)} element(s)'}

    return {'success': False, 'message': f'Unhandled action: {action}'}
```

**Step 2: Verify module imports cleanly**

Run: `cd /Users/antoniomarante/Documents/DjangoSites/djangopress && source .venv/bin/activate && python -c "from djangopress.ai.refinement_agent.edit_operations import apply_edits, VALID_ACTIONS; print('OK', VALID_ACTIONS)"`
Expected: OK with set of valid actions printed

**Step 3: Commit**

```bash
git add src/djangopress/ai/refinement_agent/edit_operations.py
git commit -m "feat: add structured edit operations executor for refinement agent"
```

---

### Task 2: Add the `apply_edits` tool with dedicated LLM prompt

**Files:**
- Modify: `src/djangopress/ai/refinement_agent/tools.py`
- Modify: `src/djangopress/ai/refinement_agent/prompts.py`

**Step 1: Add the structured diff prompt to prompts.py**

Add after the existing `DECISION_GUIDELINES` constant:

```python
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
```

**Step 2: Add the `apply_edits` tool function to tools.py**

Add after the `update_text` function and before the AI delegation section:

```python
# ── Structured diff tool (LLM generates edits, BeautifulSoup applies) ────────

def apply_edits(params, context):
    """Use a focused LLM call to generate surgical edit operations, then apply them."""
    import json as json_mod
    from djangopress.ai.utils.llm_config import LLMBase
    from .edit_operations import apply_edits as execute_edits
    from .prompts import build_structured_diff_prompt

    target_html = context['target_html']
    instructions = params.get('instructions', context.get('instructions', ''))
    include_design_guide = params.get('include_design_guide', True)

    # Optionally fetch design guide
    design_guide = ''
    if include_design_guide:
        site_settings = context.get('site_settings')
        if site_settings:
            design_guide = site_settings.design_guide or ''

    messages = build_structured_diff_prompt(target_html, instructions, design_guide)

    llm = LLMBase()
    try:
        response = llm.get_completion(messages, tool_name='gemini-flash')
        raw = response.choices[0].message.content.strip()
    except Exception as e:
        return {'success': False, 'message': f'LLM call failed: {e}'}

    # Parse JSON from response — strip markdown code fences if present
    clean = raw
    if clean.startswith('```'):
        # Remove ```json ... ``` wrapper
        clean = re.sub(r'^```(?:json)?\s*', '', clean)
        clean = re.sub(r'\s*```$', '', clean)

    try:
        edits = json_mod.loads(clean)
    except json_mod.JSONDecodeError:
        return {'success': False, 'message': f'Failed to parse edits JSON: {raw[:300]}'}

    if not isinstance(edits, list):
        return {'success': False, 'message': f'Expected JSON array, got: {type(edits).__name__}'}

    # Apply the edits
    result = execute_edits(target_html, edits)

    if result['success']:
        context['target_html'] = result['html']

    return {
        'success': result['success'],
        'message': f"Applied {len(result['applied'])} edit(s). Errors: {len(result['errors'])}."
                   + (f" Errors: {'; '.join(result['errors'])}" if result['errors'] else ''),
        'html': result['html'],
        'edits_applied': result['applied'],
        'edits_errors': result['errors'],
    }
```

**Step 3: Update tool registries in tools.py**

Update the registry constants and `ALL_TOOLS` dict:

```python
DIRECT_EDIT_TOOLS = {'update_styles', 'update_text', 'apply_edits'}

ALL_TOOLS = {
    'inspect_html': inspect_html,
    'get_design_guide': get_design_guide,
    'get_briefing': get_briefing,
    'get_pages_list': get_pages_list,
    'update_styles': update_styles,
    'update_text': update_text,
    'apply_edits': apply_edits,
    'refine_with_ai': refine_with_ai,
}
```

**Step 4: Verify imports**

Run: `cd /Users/antoniomarante/Documents/DjangoSites/djangopress && source .venv/bin/activate && python -c "from djangopress.ai.refinement_agent.tools import ALL_TOOLS; print('Tools:', list(ALL_TOOLS.keys()))"`
Expected: Tools list includes `apply_edits`

**Step 5: Commit**

```bash
git add src/djangopress/ai/refinement_agent/tools.py src/djangopress/ai/refinement_agent/prompts.py
git commit -m "feat: add apply_edits tool with dedicated LLM prompt for structured diffs"
```

---

### Task 3: Update routing agent prompts with comprehensive decision guidelines

**Files:**
- Modify: `src/djangopress/ai/refinement_agent/prompts.py`

**Step 1: Update TOOL_DEFINITIONS to include apply_edits**

In the `TOOL_DEFINITIONS` constant, add after the `update_text` entry:

```
- `apply_edits` — Generate and apply surgical edit operations via a focused AI call. Params: `{"instructions": "what to change", "include_design_guide": bool}`. The tool makes a fast AI call that returns targeted edit operations (class swaps, text changes, attribute changes, element insertions) which are applied deterministically. Use this when changes are targeted but involve multiple elements or need AI judgment to determine the right selectors/values. Much faster and safer than full regeneration — only specified elements are touched.
```

**Step 2: Update DECISION_GUIDELINES with comprehensive routing**

Replace the entire `DECISION_GUIDELINES` constant with an expanded version that includes the structured diff tier and more comprehensive examples:

```python
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
```

**Step 3: Verify prompt builds**

Run: `cd /Users/antoniomarante/Documents/DjangoSites/djangopress && source .venv/bin/activate && python -c "from djangopress.ai.refinement_agent.prompts import build_system_prompt; p = build_system_prompt('section', 'hero', '<section>test</section>'); print('apply_edits' in p, 'Tier 3' in p)"`
Expected: `True True`

**Step 4: Commit**

```bash
git add src/djangopress/ai/refinement_agent/prompts.py
git commit -m "feat: comprehensive routing guidelines with structured diff as preferred mid-tier"
```

---

### Task 4: Update ARCHITECTURE.md

**Files:**
- Modify: `src/djangopress/ai/refinement_agent/ARCHITECTURE.md`

**Step 1: Update architecture doc**

Update the tier table, tool reference, decision examples, and ASCII diagram to include the new `apply_edits` tool. Add it as a new tier between direct edit and AI delegation. Update the file structure section to include `edit_operations.py`.

Key sections to update:
- "What It Does" intro — add structured diff tier
- ASCII diagram — add `apply_edits` path
- File Structure — add `edit_operations.py`
- Tools Reference → Direct Edit Tools table — add `apply_edits`
- Decision Examples table — add structured diff examples
- Context Flags section — note that `apply_edits` also accepts `include_design_guide`

**Step 2: Commit**

```bash
git add src/djangopress/ai/refinement_agent/ARCHITECTURE.md
git commit -m "docs: update refinement agent architecture with structured diff tier"
```

---

### Task 5: Manual integration test

**Step 1: Start dev server**

Run: `cd /path/to/child-project && python manage.py runserver 8000`

**Step 2: Test via editor**

1. Open a page in the editor (`?edit=true`)
2. Select a section
3. Test these requests and verify the routing tier in terminal output:
   - "make the buttons green with rounded corners" → should route to `apply_edits` (Tier 3)
   - "make background darker" → should route to `update_styles` (Tier 1)
   - "change heading to 'Hello World'" → should route to `update_text` (Tier 2)
   - "add a testimonial carousel" → should route to `refine_with_ai` (Tier 4)
4. Verify that `apply_edits` changes ONLY the targeted elements and nothing else

**Step 3: Check for regressions**

- Verify multi-option still works (should fall through to Tier 4 since `apply_edits` returns single option)
- Verify conversation history still works across turns
- Verify auto-translation still works after `apply_edits` changes
