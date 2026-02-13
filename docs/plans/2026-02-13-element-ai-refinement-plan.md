# Element-Level AI Refinement — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow users to AI-refine individual elements (buttons, cards, divs) in editor v2, not just entire sections.

**Architecture:** New `refine_element` / `save_ai_element` endpoints mirror the existing section refinement pattern. A dedicated prompt sends the parent section as context and returns only the target element. The AI panel detects section vs element selection and calls the appropriate endpoint.

**Tech Stack:** Django, BeautifulSoup, Gemini LLM, vanilla JS (ES modules)

---

### Task 1: Element Refinement Prompt

**Files:**
- Modify: `ai/utils/prompts.py` (add after `get_section_refinement_prompt` ending at line 1070)

**Step 1: Add `get_element_refinement_prompt()` static method**

Add this method right after `get_section_refinement_prompt()` (after line 1070):

```python
@staticmethod
def get_element_refinement_prompt(
    site_name: str,
    site_description: str,
    project_briefing: str,
    default_language: str,
    section_html: str,
    section_name: str,
    element_id: str,
    element_html: str,
    user_request: str,
    design_guide: str = '',
    conversation_history: str = '',
) -> tuple:
    """
    Generate prompt for element-level refinement.
    Sends the parent section for design context but asks the LLM to return
    ONLY the target element — even cheaper than section refinement.

    Returns:
        Tuple of (system_prompt, user_prompt)
    """
    lang_name = {'pt': 'Portuguese', 'en': 'English', 'es': 'Spanish', 'fr': 'French', 'de': 'German', 'it': 'Italian'}.get(default_language, default_language.upper())

    design_guidelines = ""
    if design_guide:
        design_guidelines = "\n\n## Design Guide\nFollow these design patterns and conventions:\n" + design_guide

    system_prompt = f"""You are a senior frontend designer specializing in Tailwind CSS. Your goal is to edit ONE specific element within a webpage section.

## Your Task
Edit ONLY the element with `data-element-id="{element_id}"` based on the user's instructions. Return ONLY that single element — nothing else.
{PromptTemplates._get_design_quality_guidelines()}
## Technical Requirements
- Use Tailwind CSS classes inline for all styling
- Make responsive: `md:text-6xl`, `lg:grid-cols-3`, `sm:flex-row`
- The element MUST keep its `data-element-id="{element_id}"` attribute
- Preserve `data-element-id` on any editable child elements
- You may restructure the element's children freely
- You may change/add/remove classes, attributes, and child elements
- All text is in {lang_name} — keep it that way, do NOT use template variables

## Images
- **PRESERVE existing image `src` URLs exactly as they are.** Do NOT replace, remove, or change any existing `src` attribute unless the user explicitly asks to change the image itself.
- When adding NEW images, use placeholder: `src="https://placehold.co/WIDTHxHEIGHT?text=Label"` with `data-image-prompt="description"` and `data-image-name="slug_name"`

## CRITICAL: Return ONLY the Target Element
- Output ONLY the single element with `data-element-id="{element_id}"` and its children
- Do NOT return the parent section or any sibling elements
- Do NOT include `<html>`, `<head>`, `<body>`, `<section>`, `<header>`, `<nav>`, or `<footer>` tags
- Do NOT include `<script>` or `<link>` tags

## Important
- Return ONLY the updated element HTML
- Do NOT use `{{{{{{ trans.xxx }}}}}}` or any template variables
- Do NOT wrap the output in JSON
- No markdown code blocks, no explanations{design_guidelines}
{PromptTemplates._get_components_reference()}"""

    history_block = ""
    if conversation_history:
        history_block = f"""
# PREVIOUS REFINEMENTS

This element has been refined through a conversation:

{conversation_history}

Do NOT undo any of these previous changes unless specifically asked to.

---
"""

    user_prompt = f"""# SECTION CONTEXT (for design consistency — do NOT output the full section)

The element lives inside `<section data-section="{section_name}">`. Here is the full section so you can see the surrounding design, colors, spacing, and style:

```html
{section_html}
```

---

# ELEMENT TO EDIT

The element with `data-element-id="{element_id}"`:

```html
{element_html}
```

---
{history_block}
# USER REQUEST

Edit the element with `data-element-id="{element_id}"`:

{user_request}

---

Return ONLY the updated element. Nothing else. All text in {lang_name}. No template variables, no JSON, no code blocks."""

    return (system_prompt, user_prompt)
```

**Step 2: Commit**

```bash
git add ai/utils/prompts.py
git commit -m "Add element-level AI refinement prompt"
```

---

### Task 2: Service Method

**Files:**
- Modify: `ai/services.py` (add `refine_element_only()` after `refine_section_only` ending at line 1107)

**Step 1: Add `refine_element_only()` method**

Add right after `refine_section_only()` (after line 1107, before `def process_page_images`):

```python
def refine_element_only(
    self,
    page_id: int,
    section_name: str,
    element_id: str,
    instructions: str,
    conversation_history: list = None,
    model_override: str = None
) -> Dict:
    """
    Refine a single element within a section without saving to DB.
    Returns the element's html_template and content (translations).

    Args:
        page_id: ID of the page
        section_name: data-section attribute of parent section
        element_id: data-element-id attribute of target element
        instructions: User's refinement instructions
        conversation_history: List of {role, content} dicts for chat context
        model_override: Override the default model

    Returns:
        Dict with 'html_template', 'content', and 'assistant_message'
    """
    from core.models import Page, SiteSettings
    from bs4 import BeautifulSoup

    print(f"\n=== Refining Element Only ===")
    print(f"Page ID: {page_id}, Section: {section_name}, Element: {element_id}")
    print(f"Instructions: {instructions}")

    try:
        page = Page.objects.get(id=page_id)
    except Page.DoesNotExist:
        raise ValueError(f"Page with ID {page_id} not found")

    site_settings = SiteSettings.objects.first()
    default_language = site_settings.get_default_language() if site_settings else 'pt'
    site_name = site_settings.get_site_name(default_language) if site_settings else 'Website'
    site_description = site_settings.get_site_description(default_language) if site_settings else ''
    project_briefing = site_settings.get_project_briefing() if site_settings else ''
    languages = site_settings.get_language_codes() if site_settings else ['pt', 'en']
    design_guide = site_settings.design_guide if site_settings else ''
    model = model_override or self.model_name

    # De-templatize full page HTML, then extract parent section
    current_html = page.html_content or ''
    current_translations = (page.content or {}).get('translations', {})

    if current_translations.get(default_language):
        clean_html = self._detemplatize_html(current_html, current_translations, default_language)
    else:
        clean_html = current_html

    # Extract the parent section for context
    soup = BeautifulSoup(clean_html, 'html.parser')
    section_el = soup.find('section', attrs={'data-section': section_name})
    if not section_el:
        raise ValueError(f"Section '{section_name}' not found in page HTML")
    section_html = str(section_el)

    # Extract the target element
    element_el = section_el.find(attrs={'data-element-id': element_id})
    if not element_el:
        raise ValueError(f"Element '{element_id}' not found in section '{section_name}'")
    element_html = str(element_el)

    # Build conversation history string for prompt
    history_text = ''
    if conversation_history:
        for msg in conversation_history:
            role = msg.get('role', 'user')
            content = msg.get('content', '')
            if role == 'user':
                history_text += f"\nUser: {content}"
            elif role == 'assistant':
                history_text += f"\nAssistant: {content}"

    # Step 1: Refine element HTML
    print(f"\n--- Step 1: Refine element '{element_id}' in {default_language.upper()} ---")

    system_prompt, user_prompt = PromptTemplates.get_element_refinement_prompt(
        site_name=site_name,
        site_description=site_description,
        project_briefing=project_briefing,
        default_language=default_language,
        section_html=section_html,
        section_name=section_name,
        element_id=element_id,
        element_html=element_html,
        user_request=instructions,
        design_guide=design_guide,
        conversation_history=history_text,
    )

    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': user_prompt}
    ]

    actual_model, provider_str = self._get_model_info(model)
    t0 = time.time()
    try:
        response = self.llm.get_completion(messages, tool_name=model)
        usage = self._extract_usage(response)
        log_ai_call(
            action='refine_element', model_name=actual_model, provider=provider_str,
            system_prompt=system_prompt, user_prompt=user_prompt,
            response_text=response.choices[0].message.content,
            duration_ms=int((time.time() - t0) * 1000),
            page=page, section_name=f'{section_name}/{element_id}', **usage,
        )
    except Exception as e:
        log_ai_call(
            action='refine_element', model_name=actual_model, provider=provider_str,
            system_prompt=system_prompt, user_prompt=user_prompt,
            duration_ms=int((time.time() - t0) * 1000),
            page=page, section_name=f'{section_name}/{element_id}',
            success=False, error_message=str(e),
        )
        raise

    refined_html = self._extract_html_from_response(response.choices[0].message.content)

    if not refined_html or len(refined_html.strip()) < 10:
        raise ValueError("Step 1 returned empty or too-short HTML")

    print(f"Step 1 produced {len(refined_html)} chars of refined element HTML")

    # Verify the response contains the target element
    result_soup = BeautifulSoup(refined_html, 'html.parser')
    target_el = result_soup.find(attrs={'data-element-id': element_id})

    if target_el:
        element_result_html = str(target_el)
    else:
        # LLM returned the element without the wrapper or changed structure
        # Use the full response as the element
        print(f"WARNING: data-element-id='{element_id}' not found in response, using full response")
        element_result_html = refined_html

    print(f"Element '{element_id}': {len(element_result_html)} chars")

    # Step 2: Templatize + translate just the element
    element_data = self._templatize_and_translate(element_result_html, languages, default_language, model)

    assistant_message = f"I've updated the {element_id} element based on your instructions."

    return {
        'html_template': element_data['html_content'],
        'content': element_data['content'],
        'assistant_message': assistant_message,
    }
```

**Step 2: Commit**

```bash
git add ai/services.py
git commit -m "Add refine_element_only service method"
```

---

### Task 3: API Endpoints

**Files:**
- Modify: `editor/api_views.py` (add after `save_ai_section` ending at line 590, before `update_section_video` at line 593)

**Step 1: Add `refine_element` endpoint**

Insert after line 590 (after `save_ai_section`), before the `update_section_video` function:

```python
@superuser_required
@require_http_methods(["POST"])
def refine_element(request):
    """
    Refine a single element using AI without saving to DB.
    Returns the element's html_template and content for client-side preview.

    Expected POST data:
    {
        "page_id": 1,
        "section_name": "hero",
        "element_id": "hero_cta_button",
        "instructions": "Make it larger with a gradient background",
        "conversation_history": [{"role": "user", "content": "..."}, ...],
        "session_id": null,
        "model": "gemini-flash"
    }
    """
    try:
        data = json.loads(request.body)
        page_id = data.get('page_id')
        section_name = data.get('section_name')
        element_id = data.get('element_id')
        instructions = data.get('instructions', '').strip()
        conversation_history = data.get('conversation_history', [])
        model = data.get('model', 'gemini-flash')
        session_id = data.get('session_id')

        if not page_id or not section_name or not element_id:
            return JsonResponse({
                'success': False,
                'error': 'Missing page_id, section_name, or element_id'
            }, status=400)

        if not instructions:
            return JsonResponse({
                'success': False,
                'error': 'Missing instructions'
            }, status=400)

        page = Page.objects.get(pk=page_id)

        # Load or create RefinementSession
        session = None
        if session_id:
            try:
                session = RefinementSession.objects.get(id=session_id, page=page)
            except RefinementSession.DoesNotExist:
                session = None

        if not session:
            session = RefinementSession(
                page=page,
                title=f'[{element_id}] {instructions[:60]}',
                model_used=model,
                created_by=request.user if request.user.is_authenticated else None,
            )
            session.save()

        session.add_user_message(instructions)

        from ai.services import ContentGenerationService
        service = ContentGenerationService(model_name=model)
        result = service.refine_element_only(
            page_id=page_id,
            section_name=section_name,
            element_id=element_id,
            instructions=instructions,
            conversation_history=conversation_history,
            model_override=model,
        )

        assistant_msg = result.get('assistant_message', 'Changes applied.')
        session.add_assistant_message(assistant_msg, [f'{section_name}/{element_id}'])
        session.save()

        return JsonResponse({
            'success': True,
            'element': {
                'html_template': result['html_template'],
                'content': result['content'],
            },
            'assistant_message': assistant_msg,
            'session_id': session.id,
        })

    except Page.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Page not found'
        }, status=400)
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
```

**Step 2: Add `save_ai_element` endpoint**

Insert right after `refine_element`:

```python
@superuser_required
@require_http_methods(["POST"])
def save_ai_element(request):
    """
    Save an AI-refined element to the page in DB.
    Finds the element by data-element-id and replaces it.

    Expected POST data:
    {
        "page_id": 1,
        "section_name": "hero",
        "element_id": "hero_cta_button",
        "html_template": "<a data-element-id='hero_cta_button' ...>...</a>",
        "content": {"translations": {"pt": {...}, "en": {...}}}
    }
    """
    try:
        data = json.loads(request.body)
        page_id = data.get('page_id')
        section_name = data.get('section_name')
        element_id = data.get('element_id')
        html_template = data.get('html_template', '')
        content = data.get('content', {})

        if not page_id or not element_id or not html_template:
            return JsonResponse({
                'success': False,
                'error': 'Missing page_id, element_id, or html_template'
            }, status=400)

        try:
            page = Page.objects.get(pk=page_id)
        except Page.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Page not found'
            }, status=400)

        # Create version for rollback
        page.create_version(
            user=request.user,
            change_summary=f'AI refined element: {element_id} in {section_name}'
        )

        # Parse current page HTML and find the target element
        soup = BeautifulSoup(page.html_content, 'html.parser')
        old_element = soup.find(attrs={'data-element-id': element_id})

        if not old_element:
            return JsonResponse({
                'success': False,
                'error': f'Element "{element_id}" not found in page HTML'
            }, status=400)

        # Parse the new element HTML
        new_element_soup = BeautifulSoup(html_template, 'html.parser')
        # Find the element with data-element-id, or use the first child
        new_element = new_element_soup.find(attrs={'data-element-id': element_id})
        if not new_element:
            # The parser might have the element at top level
            children = list(new_element_soup.children)
            new_element = children[0] if children else new_element_soup

        old_element.replace_with(new_element)

        # Save updated HTML
        new_html = str(soup)
        if new_html.startswith('<html><body>'):
            new_html = new_html[12:-14]
        page.html_content = new_html

        # Merge translations (don't overwrite other elements' translations)
        new_translations = content.get('translations', {})
        page_content = page.content or {}
        if 'translations' not in page_content:
            page_content['translations'] = {}

        for lang_code, lang_trans in new_translations.items():
            if lang_code not in page_content['translations']:
                page_content['translations'][lang_code] = {}
            page_content['translations'][lang_code].update(lang_trans)

        page.content = page_content
        page.save()

        return JsonResponse({
            'success': True,
            'message': f'Element "{element_id}" saved successfully',
            'page_id': page.id,
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
```

**Step 3: Commit**

```bash
git add editor/api_views.py
git commit -m "Add refine_element and save_ai_element API endpoints"
```

---

### Task 4: URL Registration

**Files:**
- Modify: `editor_v2/urls.py:24` (add after `save-ai-section` line)
- Modify: `editor/urls.py:23` (add after `save-ai-section` line)

**Step 1: Add to `editor_v2/urls.py`**

After line 24 (`api/save-ai-section/`), add:

```python
path('api/refine-element/', api_views.refine_element, name='api_refine_element'),
path('api/save-ai-element/', api_views.save_ai_element, name='api_save_ai_element'),
```

**Step 2: Add to `editor/urls.py`**

After line 23 (`api/save-ai-section/`), add the same two lines:

```python
path('api/refine-element/', api_views.refine_element, name='api_refine_element'),
path('api/save-ai-element/', api_views.save_ai_element, name='api_save_ai_element'),
```

**Step 3: Commit**

```bash
git add editor_v2/urls.py editor/urls.py
git commit -m "Register element refinement URL patterns"
```

---

### Task 5: AI Panel — Adapt for Element Selection

**Files:**
- Modify: `editor_v2/static/editor_v2/js/modules/ai-panel.js`

This is the main frontend change. The AI panel needs to detect whether the selected element is a section or a sub-element and call the appropriate endpoint.

**Step 1: Update state variables and selection handler**

Replace the state variables (lines 12-16) and `init()` selection handler (lines 23-27):

Current state variables (lines 12-16):
```javascript
let currentSection = null;
let sessionId = null;
let messages = [];
let pendingResult = null;
let activeTab = null;
```

Replace with:
```javascript
let currentSection = null;
let currentElementId = null;
let refinementMode = null; // 'section' or 'element'
let sessionId = null;
let messages = [];
let pendingResult = null;
let activeTab = null;
```

Replace the selection handler inside `init()` (lines 23-27):
```javascript
unsubs.push(events.on('selection:changed', (el) => {
    const sec = el?.closest?.('[data-section]');
    const name = sec?.getAttribute('data-section') || null;
    if (name !== currentSection) { currentSection = name; sessionId = null; messages = []; pendingResult = null; }
    if (activeTab === 'ai') render();
}));
```

With:
```javascript
unsubs.push(events.on('selection:changed', (el) => {
    const sec = el?.closest?.('[data-section]');
    const sectionName = sec?.getAttribute('data-section') || null;
    const isSection = el?.hasAttribute?.('data-section');
    const elId = (!isSection && el?.getAttribute?.('data-element-id')) || null;

    const newMode = isSection ? 'section' : (elId ? 'element' : null);
    const newSection = sectionName;
    const newElementId = elId;

    // Reset session if target changed
    if (newMode !== refinementMode || newSection !== currentSection || newElementId !== currentElementId) {
        sessionId = null; messages = []; pendingResult = null;
    }
    currentSection = newSection;
    currentElementId = newElementId;
    refinementMode = newMode;
    if (activeTab === 'ai') render();
}));
```

Also update the `context:ai-refine` handler (lines 29-33). Replace:
```javascript
unsubs.push(events.on('context:ai-refine', (data) => {
    currentSection = data?.section || null;
    sessionId = null; messages = []; pendingResult = null;
    events.emit('sidebar:switch-tab', 'ai');
}));
```

With:
```javascript
unsubs.push(events.on('context:ai-refine', (data) => {
    currentSection = data?.section || null;
    currentElementId = data?.elementId || null;
    refinementMode = data?.elementId ? 'element' : 'section';
    sessionId = null; messages = []; pendingResult = null;
    events.emit('sidebar:switch-tab', 'ai');
}));
```

**Step 2: Update `destroy()`**

In `destroy()` (line 39), add the new state resets:

Replace:
```javascript
currentSection = null; sessionId = null; messages = []; pendingResult = null; activeTab = null;
```

With:
```javascript
currentSection = null; currentElementId = null; refinementMode = null; sessionId = null; messages = []; pendingResult = null; activeTab = null;
```

**Step 3: Update `render()` function**

Replace the empty-state check and header (lines 50-58):

```javascript
if (!currentSection) {
    container.innerHTML = '<p class="ev2-placeholder ev2-empty-state">Select a section to use AI refinement.</p>';
    return;
}

container.innerHTML = `
    <div style="padding:8px 0;font-size:12px;color:var(--ev2-text-faint);">
        Refining: <strong style="color:var(--ev2-text);">${esc(currentSection)}</strong>
    </div>
```

With:
```javascript
if (!refinementMode) {
    container.innerHTML = '<p class="ev2-placeholder ev2-empty-state">Select a section or labeled element to use AI refinement.</p>';
    return;
}

const targetLabel = refinementMode === 'element'
    ? `element: <strong style="color:var(--ev2-text);">${esc(currentElementId)}</strong> <span style="color:var(--ev2-text-faint)">in ${esc(currentSection)}</span>`
    : `section: <strong style="color:var(--ev2-text);">${esc(currentSection)}</strong>`;

container.innerHTML = `
    <div style="padding:8px 0;font-size:12px;color:var(--ev2-text-faint);">
        Refining ${targetLabel}
    </div>
```

**Step 4: Update `send()` function**

Replace the guard and API call (lines 96-116):

```javascript
const text = input?.value?.trim();
if (!text || !currentSection) return;
```

With:
```javascript
const text = input?.value?.trim();
if (!text || !refinementMode) return;
```

Replace the API call block (lines 105-116):

```javascript
const history = messages.slice(0, -1).map(m => ({ role: m.role, content: m.content }));
const res = await api.post('/refine-section/', {
    page_id: config().pageId,
    section_name: currentSection,
    instructions: text,
    conversation_history: history,
    session_id: sessionId,
});
if (res.success) {
    sessionId = res.session_id || sessionId;
    messages.push({ role: 'assistant', content: res.assistant_message || 'Changes ready to apply.' });
    pendingResult = res.section;
}
```

With:
```javascript
const history = messages.slice(0, -1).map(m => ({ role: m.role, content: m.content }));
let res;
if (refinementMode === 'element') {
    res = await api.post('/refine-element/', {
        page_id: config().pageId,
        section_name: currentSection,
        element_id: currentElementId,
        instructions: text,
        conversation_history: history,
        session_id: sessionId,
    });
} else {
    res = await api.post('/refine-section/', {
        page_id: config().pageId,
        section_name: currentSection,
        instructions: text,
        conversation_history: history,
        session_id: sessionId,
    });
}
if (res.success) {
    sessionId = res.session_id || sessionId;
    messages.push({ role: 'assistant', content: res.assistant_message || 'Changes ready to apply.' });
    pendingResult = res.element || res.section;
}
```

**Step 5: Update `applyResult()` function**

Replace the apply logic (lines 148-157):

```javascript
async function applyResult() {
    if (!pendingResult || !currentSection) return;
    try {
        await api.post('/save-ai-section/', {
            page_id: config().pageId,
            section_name: currentSection,
            html_template: pendingResult.html_template,
            content: pendingResult.content,
        });
```

With:
```javascript
async function applyResult() {
    if (!pendingResult || !refinementMode) return;
    try {
        if (refinementMode === 'element') {
            await api.post('/save-ai-element/', {
                page_id: config().pageId,
                section_name: currentSection,
                element_id: currentElementId,
                html_template: pendingResult.html_template,
                content: pendingResult.content,
            });
        } else {
            await api.post('/save-ai-section/', {
                page_id: config().pageId,
                section_name: currentSection,
                html_template: pendingResult.html_template,
                content: pendingResult.content,
            });
        }
```

**Step 6: Commit**

```bash
git add editor_v2/static/editor_v2/js/modules/ai-panel.js
git commit -m "Adapt AI panel for element-level refinement"
```

---

### Task 6: Context Menu — Add Element Refine Option

**Files:**
- Modify: `editor_v2/static/editor_v2/js/modules/context-menu.js:28-33`

**Step 1: Add element refine option**

Replace the AI refine block (lines 28-33):

```javascript
items.push(null); // separator
if (section) {
    const name = section.getAttribute('data-section');
    items.push({ label: `AI Refine Section`, icon: '✦', action: () => events.emit('context:ai-refine', { section: name }) });
    items.push(null);
}
```

With:
```javascript
items.push(null); // separator
if (section) {
    const name = section.getAttribute('data-section');
    const elId = el.getAttribute('data-element-id');
    if (elId && !el.hasAttribute('data-section')) {
        items.push({ label: 'AI Refine Element', icon: '✦', action: () => events.emit('context:ai-refine', { section: name, elementId: elId }) });
    }
    items.push({ label: 'AI Refine Section', icon: '✦', action: () => events.emit('context:ai-refine', { section: name }) });
    items.push(null);
}
```

**Step 2: Commit**

```bash
git add editor_v2/static/editor_v2/js/modules/context-menu.js
git commit -m "Add 'AI Refine Element' context menu option"
```

---

### Task 7: Cache Bust + Final Verification

**Files:**
- Modify: `templates/base.html` (lines 30 and 134)

**Step 1: Bump cache versions**

- CSS: `?v=6` → `?v=7`
- JS: `?v=9` → `?v=10`

**Step 2: Manual test**

1. Run `python manage.py runserver 8000`
2. Open a page with `?edit=v2`
3. Select a section → AI tab shows "Refining section: **hero**" → existing behavior works
4. Select a button with `data-element-id` → AI tab shows "Refining element: **hero_cta** in hero"
5. Type "Make this button larger with rounded corners" → Send
6. Wait for response → Apply → page reloads with changes
7. Right-click an element with `data-element-id` → see both "AI Refine Element" and "AI Refine Section"
8. Select an element without `data-element-id` → AI tab shows "Select a section or labeled element..."

**Step 3: Commit**

```bash
git add templates/base.html
git commit -m "Add element-level AI refinement to editor v2"
```
