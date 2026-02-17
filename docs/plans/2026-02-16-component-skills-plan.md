# Component Skills Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the monolithic `_get_components_reference()` with a Component Registry + two-pass LLM flow so component docs can be richer without bloating every prompt.

**Architecture:** Each component is a Python module in `ai/utils/components/` with `INDEX_ENTRY` (compact) and `FULL_REFERENCE` (detailed). Pass 1 (gemini-flash) selects which components are needed from the index + user request + existing HTML. Pass 2 (main model) generates HTML with only the selected full references injected.

**Tech Stack:** Python, Django, google-genai (Gemini API)

---

### Task 1: Create Component Registry

**Files:**
- Create: `ai/utils/components/__init__.py`

**Step 1: Create the `ai/utils/components/` directory**

```bash
mkdir -p ai/utils/components
```

**Step 2: Write the ComponentRegistry**

Create `ai/utils/components/__init__.py`:

```python
"""
Component Registry — auto-discovers component skill modules and provides
index/reference access for the two-pass LLM prompt architecture.
"""
import importlib
import json
import pkgutil
import time
from pathlib import Path
from ai.models import log_ai_call


class ComponentRegistry:
    """Auto-discovers component modules and provides index/reference access."""

    _components = {}  # name -> module
    _discovered = False

    @classmethod
    def discover(cls):
        """Auto-import all component modules in this package."""
        if cls._discovered:
            return
        package_dir = Path(__file__).parent
        for finder, name, ispkg in pkgutil.iter_modules([str(package_dir)]):
            if name.startswith('_'):
                continue
            module = importlib.import_module(f'.{name}', package=__package__)
            if hasattr(module, 'NAME'):
                cls._components[module.NAME] = module
        cls._discovered = True

    @classmethod
    def get_index(cls) -> str:
        """Returns compact index of all components for prompt injection."""
        cls.discover()
        lines = ["## Available Interactive Components", ""]
        lines.append("The following components are available. If your task requires any of them, "
                      "their detailed usage patterns will be provided.")
        lines.append("")
        for name, module in sorted(cls._components.items()):
            lines.append(module.INDEX_ENTRY)
        return "\n".join(lines)

    @classmethod
    def get_references(cls, names: list) -> str:
        """Returns concatenated FULL_REFERENCE for the requested component names."""
        cls.discover()
        if not names:
            return ""
        parts = ["## Component Reference (Selected for This Task)", ""]
        for name in names:
            module = cls._components.get(name)
            if module:
                parts.append(module.FULL_REFERENCE)
                parts.append("")
        return "\n".join(parts)

    @classmethod
    def get_all_names(cls) -> list:
        """Returns list of all registered component names."""
        cls.discover()
        return sorted(cls._components.keys())

    @classmethod
    def select_components(cls, user_request: str, existing_html: str = "", llm=None) -> list:
        """
        Pass 1: Use gemini-flash to select which components are needed.

        Args:
            user_request: The user's generation/refinement instructions
            existing_html: Current page HTML (for refinements)
            llm: LLMBase instance

        Returns:
            List of component name strings (e.g. ["carousel", "lightbox"])
        """
        cls.discover()
        if not cls._components:
            return []

        index = cls.get_index()

        system_prompt = (
            "You are a component selector for a CMS page builder. "
            "Given a user request and optionally existing page HTML, determine which "
            "interactive components are needed.\n\n"
            f"{index}\n\n"
            "Return ONLY a JSON array of component names that are needed for this task.\n"
            "Examples: [\"carousel\", \"lightbox\"], [\"forms\"], []\n"
            "Return [] if no interactive components are needed (e.g. simple text edits, "
            "layout changes, color changes)."
        )

        user_prompt_parts = [f"# User Request\n{user_request}"]
        if existing_html:
            # Truncate very long HTML to keep pass 1 cheap
            html_preview = existing_html[:3000]
            if len(existing_html) > 3000:
                html_preview += "\n... (truncated)"
            user_prompt_parts.append(f"\n# Existing Page HTML\n{html_preview}")

        user_prompt = "\n".join(user_prompt_parts)

        if llm is None:
            from ai.utils.llm_config import LLMBase
            llm = LLMBase()

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ]

        t0 = time.time()
        try:
            response = llm.get_completion(messages, tool_name='gemini-flash')
            content = response.choices[0].message.content.strip()

            from ai.utils.llm_config import MODEL_CONFIG
            config = MODEL_CONFIG.get('gemini-flash')
            model_name = config.model_name if config else 'gemini-flash'

            # Extract usage
            usage = getattr(response, 'usage', None)
            usage_dict = {
                'prompt_tokens': getattr(usage, 'prompt_tokens', 0) or 0,
                'completion_tokens': getattr(usage, 'completion_tokens', 0) or 0,
                'total_tokens': getattr(usage, 'total_tokens', 0) or 0,
            } if usage else {}

            log_ai_call(
                action='select_components',
                model_name=model_name,
                provider='google',
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_text=content,
                duration_ms=int((time.time() - t0) * 1000),
                **usage_dict,
            )

            # Parse JSON array from response
            json_match = __import__('re').search(r'\[.*?\]', content, __import__('re').DOTALL)
            if json_match:
                selected = json.loads(json_match.group())
                # Validate names exist
                valid = [n for n in selected if n in cls._components]
                print(f"Component selection: {valid}")
                return valid
            return []
        except Exception as e:
            print(f"Component selection failed: {e}, falling back to empty")
            log_ai_call(
                action='select_components',
                model_name='gemini-flash',
                provider='google',
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                duration_ms=int((time.time() - t0) * 1000),
                success=False, error_message=str(e),
            )
            return []
```

**Step 3: Commit**

```bash
git add ai/utils/components/__init__.py
git commit -m "Add ComponentRegistry with auto-discovery and two-pass selection"
```

---

### Task 2: Create Component Skill Modules

**Files:**
- Create: `ai/utils/components/carousel.py`
- Create: `ai/utils/components/lightbox.py`
- Create: `ai/utils/components/tabs.py`
- Create: `ai/utils/components/accordion.py`
- Create: `ai/utils/components/modal.py`
- Create: `ai/utils/components/forms.py`

**Step 1: Create all 6 component modules**

Extract the content from the current `_get_components_reference()` in `ai/utils/prompts.py:36-150`. Each module gets a `NAME`, `DESCRIPTION`, `INDEX_ENTRY`, and `FULL_REFERENCE`.

The `INDEX_ENTRY` for each should be 1-2 lines capturing the essential pattern (class names, data attributes, init convention). The `FULL_REFERENCE` should be the current content from `_get_components_reference()` for that component — expanded with more detail, config options, and examples where useful.

Source for current content: `ai/utils/prompts.py` lines 36-150.

**Step 2: Commit**

```bash
git add ai/utils/components/carousel.py ai/utils/components/lightbox.py ai/utils/components/tabs.py ai/utils/components/accordion.py ai/utils/components/modal.py ai/utils/components/forms.py
git commit -m "Add 6 component skill modules: carousel, lightbox, tabs, accordion, modal, forms"
```

---

### Task 3: Update PromptTemplates to Accept Component References

**Files:**
- Modify: `ai/utils/prompts.py:36-150` (remove `_get_components_reference`)
- Modify: `ai/utils/prompts.py:680` (get_page_generation_html_prompt)
- Modify: `ai/utils/prompts.py:803` (get_page_refinement_html_prompt)
- Modify: `ai/utils/prompts.py:987` (get_section_refinement_prompt)
- Modify: `ai/utils/prompts.py:1117` (get_section_generation_prompt)
- Modify: `ai/utils/prompts.py:1246` (get_element_refinement_prompt)

**Step 1: Remove `_get_components_reference()` method**

Delete lines 36-150 (the static method and its return string).

**Step 2: Add `component_references` parameter to each of the 5 prompt builders**

Each method signature gets a new parameter: `component_references: str = ""`

**Step 3: Replace `{PromptTemplates._get_components_reference()}` with `{component_index}\n{component_references}`**

In each of the 5 methods, import the index at the top:

```python
from ai.utils.components import ComponentRegistry
component_index = ComponentRegistry.get_index()
```

Then in the system prompt string, replace:
```python
{PromptTemplates._get_components_reference()}
```
with:
```python
{component_index}
{component_references}
```

The `component_references` comes from the method parameter (filled in by services.py after pass 1).

**Step 4: Commit**

```bash
git add ai/utils/prompts.py
git commit -m "Update 5 prompt builders to use component index + selected references"
```

---

### Task 4: Integrate Pass 1 into Services

**Files:**
- Modify: `ai/services.py:533-544` (generate_page)
- Modify: `ai/services.py:882-910` (refine_page_with_html)
- Modify: `ai/services.py:1050-1065` (refine_section_only)
- Modify: `ai/services.py:1236-1250` (generate_section)
- Modify: `ai/services.py:1381-1400` (refine_element_only)

**Step 1: Add import at top of services.py**

```python
from .utils.components import ComponentRegistry
```

**Step 2: Add pass 1 before each prompt builder call**

For each of the 5 methods, add before the `PromptTemplates.get_*` call:

```python
# Pass 1: Select relevant component skills
selected_components = ComponentRegistry.select_components(
    user_request=instructions,  # or brief, or user_request — varies per method
    existing_html=clean_html,    # or current_html, or "" for new pages
    llm=self.llm,
)
component_references = ComponentRegistry.get_references(selected_components)
```

Then pass `component_references=component_references` to the prompt builder call.

**For each method specifically:**

1. **`generate_page()`** (line 533): `user_request=brief`, `existing_html=""`
2. **`refine_page_with_html()`** (line 882): `user_request=targeted_instructions`, `existing_html=clean_html`
3. **`refine_section_only()`** (line 1050): `user_request=instructions`, `existing_html=clean_html`
4. **`generate_section()`** (line 1236): `user_request=instructions`, `existing_html=clean_html`
5. **`refine_element_only()`** (line 1381): `user_request=instructions`, `existing_html=clean_html`

**Step 3: Commit**

```bash
git add ai/services.py
git commit -m "Integrate component skill selection (pass 1) into all HTML generation methods"
```

---

### Task 5: Manual Testing

**No files to modify — testing only.**

**Step 1: Start dev server**

```bash
python manage.py runserver 8000
```

**Step 2: Test via editor (section refinement)**

1. Open any page with `?edit=v2`
2. Right-click a section → "AI Refine"
3. Type: "add a testimonial carousel under the heading" → check console for pass 1 selecting `["carousel"]`
4. Type: "change the background color to blue" → check console for pass 1 returning `[]`

**Step 3: Test via chat refinement**

1. Go to `/backoffice/ai/chat/refine/<page_id>/`
2. Type: "add a photo gallery with lightbox and a FAQ accordion below it"
3. Check console for pass 1 selecting `["lightbox", "accordion"]`
4. Verify the generated HTML uses correct Splide/data-lightbox/Alpine patterns

**Step 4: Test via page generation**

1. Go to `/backoffice/ai/generate/page/`
2. Generate a page with brief: "A portfolio page with an image gallery, client testimonials carousel, and a contact form"
3. Check console for pass 1 selecting `["carousel", "lightbox", "forms"]`

**Step 5: Verify fallback**

1. If pass 1 fails (e.g. API error), verify it returns `[]` and generation proceeds without component references (graceful degradation)