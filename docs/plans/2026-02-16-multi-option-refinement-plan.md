# Multi-Option Refinement — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Present 3 AI-generated variations for section/element refinement in editor v2, letting users preview each via tabs and only templatize the chosen one.

**Architecture:** Add `multi_option` parameter to prompt builders and service methods. One new `_split_multi_options()` helper parses the LLM response. Two new API endpoints (`refine-multi`, `apply-option`). Frontend routes section/element refinement through the multi-option flow with A/B/C tabs.

**Tech Stack:** Django, BeautifulSoup, Gemini LLM, vanilla JS (ES modules), CSS

---

### Task 1: Add `_split_multi_options()` helper to services

**Files:**
- Modify: `ai/services.py:165` (add after `_extract_html_from_response`)

**Step 1: Add the helper method**

Insert after `_extract_html_from_response` (after line 165):

```python
def _split_multi_options(self, content: str) -> list:
    """
    Split an LLM response containing multiple options separated by
    <!-- OPTION_N --> markers into a list of HTML strings.

    Returns:
        List of HTML strings (1-3 items). Falls back to [full_content]
        if no markers found.
    """
    import re
    # First extract from markdown code blocks if present
    html = self._extract_html_from_response(content)

    # Split on <!-- OPTION_N --> markers
    parts = re.split(r'<!--\s*OPTION_\d+\s*-->', html)

    # Filter out empty/whitespace-only parts
    options = [p.strip() for p in parts if p.strip()]

    if not options:
        return [html]

    return options[:3]  # Cap at 3
```

**Step 2: Commit**

```bash
git add ai/services.py
git commit -m "Add _split_multi_options helper for parsing multi-option LLM responses"
```

---

### Task 2: Add multi_option support to section refinement prompt

**Files:**
- Modify: `ai/utils/prompts.py:912-972` (`get_section_refinement_prompt`)

**Step 1: Add `multi_option` parameter to the signature**

At line 925, add `multi_option: bool = False,` after `languages: list = None,`:

```python
    @staticmethod
    def get_section_refinement_prompt(
        site_name: str,
        site_description: str,
        project_briefing: str,
        default_language: str,
        full_page_html: str,
        section_name: str,
        user_request: str,
        page_title: str = '',
        page_slug: str = '',
        design_guide: str = '',
        conversation_history: str = '',
        pages: list = None,
        languages: list = None,
        multi_option: bool = False,
    ) -> tuple:
```

**Step 2: Add multi-option instruction block**

At line 971, before `{design_guidelines}`, insert a conditional block:

Replace line 971:
```python
- No markdown code blocks, no explanations{design_guidelines}
```

With:
```python
- No markdown code blocks, no explanations{f'''

## Multiple Options
Return exactly 3 distinct variations of the section. Separate them with HTML comment markers on their own line:
<!-- OPTION_1 -->
(first variation — full <section> block)
<!-- OPTION_2 -->
(second variation — full <section> block)
<!-- OPTION_3 -->
(third variation — full <section> block)

Make each variation meaningfully different: vary layout structure, visual emphasis, spacing, or content arrangement. All 3 must satisfy the user request and include the complete <section data-section="{section_name}"> wrapper.''' if multi_option else ''}{design_guidelines}
```

**Step 3: Commit**

```bash
git add ai/utils/prompts.py
git commit -m "Add multi_option support to section refinement prompt"
```

---

### Task 3: Add multi_option support to element refinement prompt

**Files:**
- Modify: `ai/utils/prompts.py:1027-1083` (`get_element_refinement_prompt`)

**Step 1: Add `multi_option` parameter to the signature**

At line 1039, add `multi_option: bool = False,` after `conversation_history: str = '',`:

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
        multi_option: bool = False,
    ) -> tuple:
```

**Step 2: Add multi-option instruction block**

At line 1082, before `{design_guidelines}`, insert:

Replace line 1082:
```python
- No markdown code blocks, no explanations{design_guidelines}
```

With:
```python
- No markdown code blocks, no explanations{f'''

## Multiple Options
Return exactly 3 distinct variations of the element. Separate them with HTML comment markers on their own line:
<!-- OPTION_1 -->
(first variation — the element with data-element-id="{element_id}")
<!-- OPTION_2 -->
(second variation)
<!-- OPTION_3 -->
(third variation)

Make each variation meaningfully different: vary styling, layout, or visual approach. All 3 must satisfy the user request and keep the data-element-id="{element_id}" attribute.''' if multi_option else ''}{design_guidelines}
```

**Step 3: Commit**

```bash
git add ai/utils/prompts.py
git commit -m "Add multi_option support to element refinement prompt"
```

---

### Task 4: Add multi_option path in `refine_section_only()`

**Files:**
- Modify: `ai/services.py:946-1107` (`refine_section_only`)

**Step 1: Add `multi_option` parameter**

At line 952, add `multi_option: bool = False,` after `conversation_history: list = None,`:

```python
    def refine_section_only(
        self,
        page_id: int,
        section_name: str,
        instructions: str,
        conversation_history: list = None,
        multi_option: bool = False,
        model_override: str = None
    ) -> Dict:
```

**Step 2: Pass `multi_option` to prompt builder**

Find the call to `PromptTemplates.get_section_refinement_prompt(` and add `multi_option=multi_option,` to its arguments.

**Step 3: Add multi-option return path**

Replace lines 1095-1107 (the Step 2 templatize block and return):

```python
        print(f"Section '{section_name}': {len(section_html)} chars")

        # Step 2: Templatize + translate just the section
        section_data = self._templatize_and_translate(section_html, languages, default_language, model)

        # Build assistant message for chat display
        assistant_message = f"I've updated the {section_name} section based on your instructions."

        return {
            'html_template': section_data['html_content'],
            'content': section_data['content'],
            'assistant_message': assistant_message,
        }
```

With:

```python
        print(f"Section '{section_name}': {len(section_html)} chars")

        if multi_option:
            # Multi-option: split into options, skip templatize, return raw HTML
            options = self._split_multi_options(refined_html)
            # Validate each option has the target section
            validated = []
            for i, opt_html in enumerate(options):
                opt_soup = BeautifulSoup(opt_html, 'html.parser')
                opt_section = opt_soup.find('section', attrs={'data-section': section_name})
                if opt_section:
                    validated.append({'html': str(opt_section)})
                elif opt_soup.find('section'):
                    # Has a section but wrong name — use it anyway
                    validated.append({'html': str(opt_soup.find('section'))})
                else:
                    validated.append({'html': opt_html})
                print(f"  Option {i+1}: {len(validated[-1]['html'])} chars")

            assistant_message = f"Here are {len(validated)} variations for the {section_name} section."
            return {
                'options': validated,
                'assistant_message': assistant_message,
            }

        # Step 2: Templatize + translate just the section
        section_data = self._templatize_and_translate(section_html, languages, default_language, model)

        # Build assistant message for chat display
        assistant_message = f"I've updated the {section_name} section based on your instructions."

        return {
            'html_template': section_data['html_content'],
            'content': section_data['content'],
            'assistant_message': assistant_message,
        }
```

**Step 4: Commit**

```bash
git add ai/services.py
git commit -m "Add multi_option path to refine_section_only — skip templatize, return 3 options"
```

---

### Task 5: Add multi_option path in `refine_element_only()`

**Files:**
- Modify: `ai/services.py:1109-1260` (`refine_element_only`)

**Step 1: Add `multi_option` parameter**

At line 1115, add `multi_option: bool = False,` after `conversation_history: list = None,`:

```python
    def refine_element_only(
        self,
        page_id: int,
        section_name: str,
        element_id: str,
        instructions: str,
        conversation_history: list = None,
        multi_option: bool = False,
        model_override: str = None
    ) -> Dict:
```

**Step 2: Pass `multi_option` to prompt builder**

Find the call to `PromptTemplates.get_element_refinement_prompt(` and add `multi_option=multi_option,` to its arguments.

**Step 3: Add multi-option return path**

Insert after the line that computes `element_result_html` (around line 1237, after the `print(f"Element '{element_id}':...")`), before the "Step 2: Templatize" comment at line 1240:

```python
        if multi_option:
            # Multi-option: split into options, skip templatize, return raw HTML
            options = self._split_multi_options(refined_html)
            validated = []
            for i, opt_html in enumerate(options):
                opt_soup = BeautifulSoup(opt_html, 'html.parser')
                opt_el = opt_soup.find(attrs={'data-element-id': element_id})
                if opt_el:
                    validated.append({'html': str(opt_el)})
                else:
                    validated.append({'html': opt_html})
                print(f"  Option {i+1}: {len(validated[-1]['html'])} chars")

            assistant_message = f"Here are {len(validated)} variations for the {element_id} element."
            return {
                'options': validated,
                'assistant_message': assistant_message,
            }
```

The existing single-option flow (templatize + return) continues unchanged below.

**Step 4: Commit**

```bash
git add ai/services.py
git commit -m "Add multi_option path to refine_element_only — skip templatize, return 3 options"
```

---

### Task 6: Add `refine_multi` API endpoint

**Files:**
- Modify: `editor_v2/api_views.py` (add after `save_ai_element` ending at line 1045)
- Modify: `editor_v2/urls.py` (add URL pattern)

**Step 1: Add the endpoint**

Insert after line 1045 in `editor_v2/api_views.py`:

```python
@superuser_required
@require_http_methods(["POST"])
def refine_multi(request):
    """
    Refine a section or element, returning 3 variations for the user to pick from.
    No templatize step — returns raw HTML with real text.

    POST /editor-v2/api/refine-multi/
    {
        "page_id": 1,
        "scope": "section" | "element",
        "section_name": "hero",
        "element_id": null,
        "instructions": "Make it bolder",
        "conversation_history": [...],
        "session_id": null
    }
    """
    try:
        data = json.loads(request.body)
        page_id = data.get('page_id')
        scope = data.get('scope', 'section')
        section_name = data.get('section_name')
        element_id = data.get('element_id')
        instructions = data.get('instructions', '').strip()
        conversation_history = data.get('conversation_history', [])
        session_id = data.get('session_id')

        if not page_id or not instructions:
            return JsonResponse({'success': False, 'error': 'Missing page_id or instructions'}, status=400)

        if scope == 'element' and (not element_id or not section_name):
            return JsonResponse({'success': False, 'error': 'Missing element_id or section_name for element scope'}, status=400)

        if scope == 'section' and not section_name:
            return JsonResponse({'success': False, 'error': 'Missing section_name for section scope'}, status=400)

        page = Page.objects.get(pk=page_id)

        # Load or create RefinementSession
        session = None
        if session_id:
            try:
                session = RefinementSession.objects.get(id=session_id, page=page)
            except RefinementSession.DoesNotExist:
                session = None

        if not session:
            prefix = f'[{element_id}]' if scope == 'element' else f'[{section_name}]'
            session = RefinementSession(
                page=page,
                title=f'{prefix} {instructions[:60]}',
                model_used='gemini-flash',
                created_by=request.user if request.user.is_authenticated else None,
            )
            session.save()

        session.add_user_message(instructions)

        from ai.services import ContentGenerationService
        service = ContentGenerationService(model_name='gemini-flash')

        if scope == 'element':
            result = service.refine_element_only(
                page_id=page_id,
                section_name=section_name,
                element_id=element_id,
                instructions=instructions,
                conversation_history=conversation_history,
                multi_option=True,
            )
        else:
            result = service.refine_section_only(
                page_id=page_id,
                section_name=section_name,
                instructions=instructions,
                conversation_history=conversation_history,
                multi_option=True,
            )

        assistant_msg = result.get('assistant_message', 'Here are 3 variations.')
        target = f'{section_name}/{element_id}' if scope == 'element' else section_name
        session.add_assistant_message(assistant_msg, [target])
        session.save()

        return JsonResponse({
            'success': True,
            'options': result.get('options', []),
            'assistant_message': assistant_msg,
            'session_id': session.id,
        })

    except Page.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Page not found'}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
```

**Step 2: Register the URL**

In `editor_v2/urls.py`, add after the `save-ai-element` line (line 27):

```python
    path('api/refine-multi/', api_views.refine_multi, name='api_refine_multi'),
```

**Step 3: Commit**

```bash
git add editor_v2/api_views.py editor_v2/urls.py
git commit -m "Add refine-multi API endpoint returning 3 variations"
```

---

### Task 7: Add `apply_option` API endpoint

**Files:**
- Modify: `editor_v2/api_views.py` (add after `refine_multi`)
- Modify: `editor_v2/urls.py` (add URL pattern)

**Step 1: Add the endpoint**

Insert after `refine_multi` in `editor_v2/api_views.py`:

```python
@superuser_required
@require_http_methods(["POST"])
def apply_option(request):
    """
    Templatize + translate the chosen option HTML, then save it to the page.

    POST /editor-v2/api/apply-option/
    {
        "page_id": 1,
        "scope": "section" | "element",
        "section_name": "hero",
        "element_id": null,
        "html": "<section data-section='hero'>...</section>"
    }
    """
    try:
        data = json.loads(request.body)
        page_id = data.get('page_id')
        scope = data.get('scope', 'section')
        section_name = data.get('section_name')
        element_id = data.get('element_id')
        html = data.get('html', '').strip()

        if not page_id or not html:
            return JsonResponse({'success': False, 'error': 'Missing page_id or html'}, status=400)

        page = Page.objects.get(pk=page_id)

        # Templatize + translate the chosen option
        from ai.services import ContentGenerationService
        from core.models import SiteSettings
        site_settings = SiteSettings.objects.first()
        default_language = site_settings.get_default_language() if site_settings else 'pt'
        languages = site_settings.get_language_codes() if site_settings else ['pt', 'en']

        service = ContentGenerationService(model_name='gemini-flash')
        templatized = service._templatize_and_translate(html, languages, default_language, 'gemini-flash')

        html_template = templatized['html_content']
        content = templatized['content']

        # Create version for rollback
        change_target = element_id or section_name
        page.create_version(
            user=request.user,
            change_summary=f'AI multi-option applied: {change_target}'
        )

        if scope == 'element' and element_id:
            # Surgical element replacement (same as save_ai_element)
            soup = BeautifulSoup(page.html_content, 'html.parser')
            old_element = soup.find(attrs={'data-element-id': element_id})
            if not old_element:
                return JsonResponse({'success': False, 'error': f'Element "{element_id}" not found'}, status=400)

            new_soup = BeautifulSoup(html_template, 'html.parser')
            new_element = new_soup.find(attrs={'data-element-id': element_id})
            if not new_element:
                children = list(new_soup.children)
                new_element = children[0] if children else new_soup

            old_element.replace_with(new_element)
            page.html_content = str(soup)
        else:
            # Surgical section replacement (same as save_ai_section)
            soup = BeautifulSoup(page.html_content, 'html.parser')
            old_section = soup.find('section', attrs={'data-section': section_name})
            if not old_section:
                return JsonResponse({'success': False, 'error': f'Section "{section_name}" not found'}, status=400)

            new_soup = BeautifulSoup(html_template, 'html.parser')
            new_section = new_soup.find('section', attrs={'data-section': section_name})
            if not new_section:
                new_section = new_soup.find('section')
            if not new_section:
                return JsonResponse({'success': False, 'error': 'No section found in templatized HTML'}, status=400)

            old_section.replace_with(new_section)
            page.html_content = str(soup)

        # Merge translations
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
            'message': f'{scope.capitalize()} saved successfully',
            'page_id': page.id,
        })

    except Page.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Page not found'}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
```

**Step 2: Register the URL**

In `editor_v2/urls.py`, add after `refine-multi`:

```python
    path('api/apply-option/', api_views.apply_option, name='api_apply_option'),
```

**Step 3: Add necessary imports**

Verify `editor_v2/api_views.py` has `from bs4 import BeautifulSoup` — it should already be imported.

**Step 4: Commit**

```bash
git add editor_v2/api_views.py editor_v2/urls.py
git commit -m "Add apply-option API endpoint — templatize chosen option and save"
```

---

### Task 8: Update ai-panel.js — state, send(), and preview for multi-option

**Files:**
- Modify: `editor_v2/static/editor_v2/js/modules/ai-panel.js`

**Step 1: Add new state variables**

At line 22, after `let originalHtml = null;`, add:

```javascript
let options = [];               // multi-option: array of {html} objects
let activeOption = 0;           // which option tab is active (0, 1, 2)
```

**Step 2: Update `send()` to route section/element through refine-multi**

Replace lines 259-276 (the element and section branches) with:

```javascript
        } else if (activeScope === 'element') {
            res = await api.post('/refine-multi/', {
                page_id: config().pageId,
                scope: 'element',
                section_name: currentSection,
                element_id: currentElementId,
                instructions: text,
                conversation_history: history,
                session_id: sessionId,
            });
        } else {
            res = await api.post('/refine-multi/', {
                page_id: config().pageId,
                scope: 'section',
                section_name: currentSection,
                instructions: text,
                conversation_history: history,
                session_id: sessionId,
            });
        }
```

Replace lines 278-286 (the success handler) with:

```javascript
        if (res.success) {
            sessionId = res.session_id || sessionId;
            const msg = res.assistant_message || 'Changes ready to apply.';
            messages.push({ role: 'assistant', content: msg, scope: scopeLabel });

            if (res.options) {
                // Multi-option response
                options = res.options;
                activeOption = 0;
                pendingScope = activeScope;
                if (options.length > 0) showMultiPreview(0);
            } else {
                // Single-option response (page scope)
                pendingResult = res.page;
                pendingScope = activeScope;
                options = [];
                if (pendingResult) showPreview();
            }
            refreshSessionsList();
        }
```

**Step 3: Add `showMultiPreview()` function**

After the existing `showPreview()` function (after line 391), add:

```javascript
function showMultiPreview(index) {
    if (!options[index]) return;
    const html = options[index].html;

    // Restore before switching
    if (originalHtml) restorePreview();

    if (pendingScope === 'element' && currentElementId) {
        const el = document.querySelector(`[data-element-id="${currentElementId}"]`);
        if (!el) return;
        if (!originalHtml) originalHtml = el.outerHTML;
        el.outerHTML = html;
    } else if (pendingScope === 'section' && currentSection) {
        const sec = document.querySelector(`[data-section="${currentSection}"]`);
        if (!sec) return;
        if (!originalHtml) originalHtml = sec.outerHTML;
        sec.outerHTML = html;
    }
}
```

**Step 4: Update `applyResult()` for multi-option**

Replace lines 326-358 with:

```javascript
async function applyResult() {
    try {
        if (options.length > 0 && pendingScope) {
            // Multi-option: send chosen option to apply-option endpoint
            const chosen = options[activeOption];
            if (!chosen) return;
            await api.post('/apply-option/', {
                page_id: config().pageId,
                scope: pendingScope,
                section_name: currentSection,
                element_id: currentElementId,
                html: chosen.html,
            });
        } else if (pendingResult && pendingScope) {
            // Single-option (page scope): existing flow
            if (pendingScope === 'page') {
                await api.post('/save-ai-page/', {
                    page_id: config().pageId,
                    html_template: pendingResult.html_template,
                    content: pendingResult.content,
                });
            }
        } else {
            return;
        }
        pendingResult = null;
        pendingScope = null;
        options = [];
        window.location.reload();
    } catch (err) {
        messages.push({ role: 'assistant', content: 'Save failed: ' + (err.message || err), scope: '' });
        render();
    }
}
```

**Step 5: Update `discardResult()` to clear options**

Replace lines 360-365:

```javascript
function discardResult() {
    restorePreview();
    pendingResult = null;
    pendingScope = null;
    options = [];
    activeOption = 0;
    render();
}
```

**Step 6: Reset options in `destroy()`**

In the `destroy()` function, add `options = []; activeOption = 0;` to the reset line.

**Step 7: Commit**

```bash
git add editor_v2/static/editor_v2/js/modules/ai-panel.js
git commit -m "Route section/element refinement through multi-option flow"
```

---

### Task 9: Update ai-panel.js — render option tabs in UI

**Files:**
- Modify: `editor_v2/static/editor_v2/js/modules/ai-panel.js`

**Step 1: Add option tabs to render()**

Replace lines 113-116 (the `pendingResult` ternary for Apply/Discard) with:

```javascript
        ${(options.length > 0 || pendingResult) ? `
        <div class="ev2-ai-actions">
            ${options.length > 1 ? `<div class="ev2-option-tabs">
                ${options.map((_, i) => `<button class="ev2-option-tab ${i === activeOption ? 'active' : ''}" data-option="${i}">${String.fromCharCode(65 + i)}</button>`).join('')}
            </div>` : ''}
            <button id="ev2-ai-apply" class="ev2-btn-primary" style="flex:1;padding:6px;font-size:12px;">Apply</button>
            <button id="ev2-ai-discard" class="ev2-btn-secondary" style="flex:1;padding:6px;font-size:12px;">Discard</button>
        </div>` : ''}
```

**Step 2: Add option tab click handlers**

After the existing `$('#ev2-ai-discard')?.addEventListener` line (around line 134), add:

```javascript
    // Option tab click handlers
    container.querySelectorAll('.ev2-option-tab').forEach(btn => {
        btn.addEventListener('click', () => {
            const idx = parseInt(btn.dataset.option, 10);
            if (idx === activeOption || !options[idx]) return;
            restorePreview();
            activeOption = idx;
            showMultiPreview(idx);
            // Update active tab styling
            container.querySelectorAll('.ev2-option-tab').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        });
    });
```

**Step 3: Commit**

```bash
git add editor_v2/static/editor_v2/js/modules/ai-panel.js
git commit -m "Add A/B/C option tabs to AI panel render"
```

---

### Task 10: Add CSS for option tabs

**Files:**
- Modify: `editor_v2/static/editor_v2/css/editor.css` (add before last line, line 1580)

**Step 1: Add styles**

Insert before the last closing brace (line 1580):

```css
/* ── Multi-option tabs ── */
.ev2-option-tabs {
    display: flex;
    gap: 4px;
    margin-right: 8px;
}

.ev2-option-tab {
    width: 28px;
    height: 28px;
    font-size: 11px;
    font-weight: 600;
    border-radius: 6px;
    border: 1px solid var(--ev2-border);
    background: transparent;
    color: var(--ev2-text-faint);
    cursor: pointer;
    transition: all 0.15s;
    display: flex;
    align-items: center;
    justify-content: center;
}

.ev2-option-tab:hover {
    border-color: var(--ev2-accent);
    color: var(--ev2-text);
}

.ev2-option-tab.active {
    background: var(--ev2-accent);
    color: #fff;
    border-color: var(--ev2-accent);
}
```

**Step 2: Commit**

```bash
git add editor_v2/static/editor_v2/css/editor.css
git commit -m "Add CSS for multi-option A/B/C tabs"
```

---

### Task 11: Cache bust and final verification

**Files:**
- Modify: `templates/base.html`

**Step 1: Bump cache versions**

Find the editor CSS and JS cache version strings in `templates/base.html` and increment both by 1.

**Step 2: Manual verification**

1. `python manage.py runserver 8000`
2. Open a page with `?edit=v2`
3. Select a section → AI tab → type "Make this more modern" → Send
4. Wait for response — should see A/B/C tabs appear with Apply/Discard
5. Click A, B, C tabs — each swaps the live DOM preview
6. Click Apply on preferred option → page reloads with changes
7. Click Discard → original DOM restored, tabs disappear
8. Test with element selection (element with `data-element-id`)
9. Test page scope → should still use single-option flow (no tabs)
10. Test edge case: if LLM returns only 1 option, no tabs shown, Apply/Discard work normally

**Step 3: Commit**

```bash
git add templates/base.html
git commit -m "Multi-option refinement: present 3 AI variations for section/element editing"
```
