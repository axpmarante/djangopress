# Style Calibration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove hardcoded aggressive design guidelines from AI prompts and add tag chips, "Enhance" button, and "Suggest" button to all instruction inputs so users can control the style of generated layouts.

**Architecture:** Delete `_get_design_quality_guidelines()` and its 5 call sites in `prompts.py`. Add a single `/ai/api/enhance-prompt/` endpoint (gemini-flash) for both enhance and suggest modes. Create a reusable Django template partial + JS for the backoffice instruction textareas, and extend the editor v2 AI panel with the same features.

**Tech Stack:** Django, Tailwind CSS, vanilla JS (backoffice), ES modules (editor v2), Google Gemini Flash API

---

### Task 1: Remove Hardcoded Design Quality Guidelines

**Files:**
- Modify: `ai/utils/prompts.py:36-79` (delete function), lines 384, 704, 821, 991, 1104 (delete call sites)

**Step 1: Delete the function and all call sites**

In `ai/utils/prompts.py`:

1. Delete the entire `_get_design_quality_guidelines()` method (lines 36-79)
2. Remove `{PromptTemplates._get_design_quality_guidelines()}` from 5 locations:
   - Line 384 in `get_global_section_refinement_prompt()`
   - Line 704 in `get_page_generation_html_prompt()`
   - Line 821 in `get_page_refinement_html_prompt()`
   - Line 991 in `get_section_refinement_prompt()`
   - Line 1104 in `get_element_refinement_prompt()`

Each call site is a single line in an f-string between `## Your Task` / `## Task` and `## Technical Requirements`. Just delete the line — the two sections flow together naturally.

**Step 2: Verify no other references**

```bash
grep -r "_get_design_quality_guidelines" --include="*.py" .
```

Expected: No results.

**Step 3: Commit**

```bash
git add ai/utils/prompts.py
git commit -m "Remove hardcoded design quality guidelines from AI prompts"
```

---

### Task 2: Add enhance-prompt API Endpoint

**Files:**
- Modify: `ai/views.py` (add endpoint)
- Modify: `ai/urls.py` (add URL pattern)

**Step 1: Add the endpoint to `ai/views.py`**

Add after the existing endpoints (before any helper functions at the bottom):

```python
@superuser_required
@require_http_methods(["POST"])
def enhance_prompt_api(request):
    """
    Enhance or suggest a style prompt using AI.

    POST /ai/api/enhance-prompt/
    Body: {
        "text": "make it clean and add a button",
        "section_html": "<section ...>...</section>",  // optional, for suggest mode
        "mode": "enhance" | "suggest"
    }
    """
    try:
        data = json.loads(request.body)
        text = data.get('text', '').strip()
        section_html = data.get('section_html', '').strip()
        mode = data.get('mode', 'enhance')

        if mode == 'suggest' and not section_html:
            return JsonResponse({'success': False, 'error': 'section_html required for suggest mode'}, status=400)

        if mode == 'suggest':
            system_prompt = (
                "You are a web design consultant. Analyze the provided HTML section and suggest "
                "3-5 specific visual and layout improvements. Write as a single instruction paragraph "
                "that a user can send to an AI to refine the section. Be specific about layout changes, "
                "spacing, colors, typography, and visual effects. Reference Tailwind CSS patterns. "
                "Keep it under 150 words. Return ONLY the instruction text, no markdown formatting."
            )
            user_prompt = f"Current instruction draft:\n{text}\n\nHTML section to analyze:\n{section_html}" if text else f"HTML section to analyze:\n{section_html}"
        else:
            if not text:
                return JsonResponse({'success': False, 'error': 'text required for enhance mode'}, status=400)
            system_prompt = (
                "You are a web design prompt specialist. Expand the user's rough design instruction "
                "into a clear, detailed directive for a web designer. Be specific about layout, spacing, "
                "typography, color usage, and visual feel. Reference Tailwind CSS patterns where relevant. "
                "Keep it under 150 words. Return ONLY the enhanced instruction text, no markdown formatting."
            )
            user_prompt = text

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]

        llm = LLMBase()
        model = 'gemini-flash'
        actual_model, provider = _get_model_info(model)
        t0 = time.time()

        try:
            response = llm.get_completion(messages, tool_name=model)
            usage = _extract_usage(response)
            log_ai_call(
                action='enhance_prompt', model_name=actual_model, provider=provider,
                system_prompt=system_prompt, user_prompt=user_prompt,
                response_text=response.choices[0].message.content,
                duration_ms=int((time.time() - t0) * 1000),
                user=request.user, **usage,
            )
        except Exception as e:
            log_ai_call(
                action='enhance_prompt', model_name=actual_model, provider=provider,
                system_prompt=system_prompt, user_prompt=user_prompt,
                duration_ms=int((time.time() - t0) * 1000),
                user=request.user, success=False, error_message=str(e),
            )
            raise

        enhanced_text = response.choices[0].message.content.strip()

        return JsonResponse({
            'success': True,
            'text': enhanced_text,
        })

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
```

**Step 2: Add URL pattern**

In `ai/urls.py`, add alongside existing patterns:

```python
path('api/enhance-prompt/', views.enhance_prompt_api, name='enhance_prompt_api'),
```

**Step 3: Verify imports**

Check that `LLMBase`, `_get_model_info`, `_extract_usage`, `log_ai_call` are already imported in `ai/views.py` (they should be — they're used by other endpoints).

**Step 4: Commit**

```bash
git add ai/views.py ai/urls.py
git commit -m "Add enhance-prompt API endpoint for style prompt assistance"
```

---

### Task 3: Create Reusable Style Prompt Tools for Backoffice

**Files:**
- Create: `backoffice/templates/backoffice/partials/style_tags.html`
- Create: `static/js/style-prompt-tools.js`

**Step 1: Create the template partial**

`backoffice/templates/backoffice/partials/style_tags.html`:

This partial renders tag chips and enhance/suggest buttons below a textarea. It expects one template variable: `target_id` (the ID of the textarea to modify).

```html
{% comment %}
Style prompt tools: tag chips + enhance button.
Include below any instruction textarea. Pass target_id as the textarea's DOM id.
Usage: {% include 'backoffice/partials/style_tags.html' with target_id='brief' %}
{% endcomment %}
<div class="style-prompt-tools mt-2" data-target="{{ target_id }}">
    <div class="flex flex-wrap gap-1.5 mb-2">
        {% for tag in "minimal,bold,corporate,playful,dark theme,spacious,compact,flat,rounded,sharp,gradients,card-heavy,asymmetric,centered,image-rich,monochrome,vibrant"|make_list_from_csv %}
        {% endfor %}
        <button type="button" class="style-tag px-2 py-0.5 text-xs rounded-full border border-gray-300 text-gray-600 hover:border-purple-400 hover:text-purple-600 transition-colors cursor-pointer" data-tag="minimal">minimal</button>
        <button type="button" class="style-tag px-2 py-0.5 text-xs rounded-full border border-gray-300 text-gray-600 hover:border-purple-400 hover:text-purple-600 transition-colors cursor-pointer" data-tag="bold">bold</button>
        <button type="button" class="style-tag px-2 py-0.5 text-xs rounded-full border border-gray-300 text-gray-600 hover:border-purple-400 hover:text-purple-600 transition-colors cursor-pointer" data-tag="corporate">corporate</button>
        <button type="button" class="style-tag px-2 py-0.5 text-xs rounded-full border border-gray-300 text-gray-600 hover:border-purple-400 hover:text-purple-600 transition-colors cursor-pointer" data-tag="playful">playful</button>
        <button type="button" class="style-tag px-2 py-0.5 text-xs rounded-full border border-gray-300 text-gray-600 hover:border-purple-400 hover:text-purple-600 transition-colors cursor-pointer" data-tag="dark theme">dark theme</button>
        <button type="button" class="style-tag px-2 py-0.5 text-xs rounded-full border border-gray-300 text-gray-600 hover:border-purple-400 hover:text-purple-600 transition-colors cursor-pointer" data-tag="spacious">spacious</button>
        <button type="button" class="style-tag px-2 py-0.5 text-xs rounded-full border border-gray-300 text-gray-600 hover:border-purple-400 hover:text-purple-600 transition-colors cursor-pointer" data-tag="compact">compact</button>
        <button type="button" class="style-tag px-2 py-0.5 text-xs rounded-full border border-gray-300 text-gray-600 hover:border-purple-400 hover:text-purple-600 transition-colors cursor-pointer" data-tag="flat">flat</button>
        <button type="button" class="style-tag px-2 py-0.5 text-xs rounded-full border border-gray-300 text-gray-600 hover:border-purple-400 hover:text-purple-600 transition-colors cursor-pointer" data-tag="rounded">rounded</button>
        <button type="button" class="style-tag px-2 py-0.5 text-xs rounded-full border border-gray-300 text-gray-600 hover:border-purple-400 hover:text-purple-600 transition-colors cursor-pointer" data-tag="sharp">sharp</button>
        <button type="button" class="style-tag px-2 py-0.5 text-xs rounded-full border border-gray-300 text-gray-600 hover:border-purple-400 hover:text-purple-600 transition-colors cursor-pointer" data-tag="gradients">gradients</button>
        <button type="button" class="style-tag px-2 py-0.5 text-xs rounded-full border border-gray-300 text-gray-600 hover:border-purple-400 hover:text-purple-600 transition-colors cursor-pointer" data-tag="card-heavy">card-heavy</button>
        <button type="button" class="style-tag px-2 py-0.5 text-xs rounded-full border border-gray-300 text-gray-600 hover:border-purple-400 hover:text-purple-600 transition-colors cursor-pointer" data-tag="asymmetric">asymmetric</button>
        <button type="button" class="style-tag px-2 py-0.5 text-xs rounded-full border border-gray-300 text-gray-600 hover:border-purple-400 hover:text-purple-600 transition-colors cursor-pointer" data-tag="centered">centered</button>
        <button type="button" class="style-tag px-2 py-0.5 text-xs rounded-full border border-gray-300 text-gray-600 hover:border-purple-400 hover:text-purple-600 transition-colors cursor-pointer" data-tag="image-rich">image-rich</button>
        <button type="button" class="style-tag px-2 py-0.5 text-xs rounded-full border border-gray-300 text-gray-600 hover:border-purple-400 hover:text-purple-600 transition-colors cursor-pointer" data-tag="monochrome">monochrome</button>
        <button type="button" class="style-tag px-2 py-0.5 text-xs rounded-full border border-gray-300 text-gray-600 hover:border-purple-400 hover:text-purple-600 transition-colors cursor-pointer" data-tag="vibrant">vibrant</button>
    </div>
    <button type="button" class="style-enhance-btn inline-flex items-center gap-1 text-xs text-purple-600 hover:text-purple-800 font-medium transition-colors">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
        Enhance with AI
    </button>
</div>
```

**Step 2: Create the JS module**

`static/js/style-prompt-tools.js`:

```javascript
/**
 * Style Prompt Tools — tag chips + enhance button for instruction textareas.
 * Auto-initializes on DOMContentLoaded for all .style-prompt-tools containers.
 */
(function() {
    function init() {
        document.querySelectorAll('.style-prompt-tools').forEach(container => {
            const targetId = container.dataset.target;
            const textarea = document.getElementById(targetId);
            if (!textarea) return;

            // Tag chip click: append/remove tag text
            container.querySelectorAll('.style-tag').forEach(btn => {
                btn.addEventListener('click', () => {
                    const tag = btn.dataset.tag;
                    const current = textarea.value.trim();
                    // Check if tag is already present (word boundary match)
                    const regex = new RegExp('(^|[,;.\\s])' + tag.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '([,;.\\s]|$)', 'i');
                    if (regex.test(current)) {
                        // Remove the tag
                        textarea.value = current.replace(regex, '$1').replace(/\s{2,}/g, ' ').replace(/^[,;.\s]+|[,;.\s]+$/g, '').trim();
                        btn.classList.remove('border-purple-500', 'text-purple-700', 'bg-purple-50');
                        btn.classList.add('border-gray-300', 'text-gray-600');
                    } else {
                        // Append the tag
                        textarea.value = current ? current + ', ' + tag : tag;
                        btn.classList.add('border-purple-500', 'text-purple-700', 'bg-purple-50');
                        btn.classList.remove('border-gray-300', 'text-gray-600');
                    }
                    textarea.focus();
                });
            });

            // Enhance button
            const enhanceBtn = container.querySelector('.style-enhance-btn');
            if (enhanceBtn) {
                enhanceBtn.addEventListener('click', async () => {
                    const text = textarea.value.trim();
                    if (!text) return;

                    const origText = enhanceBtn.innerHTML;
                    enhanceBtn.innerHTML = '<span class="animate-pulse">Enhancing...</span>';
                    enhanceBtn.disabled = true;

                    try {
                        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value
                            || document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
                        const res = await fetch('/ai/api/enhance-prompt/', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'X-CSRFToken': csrfToken,
                            },
                            body: JSON.stringify({ text, mode: 'enhance' }),
                        });
                        const data = await res.json();
                        if (data.success && data.text) {
                            textarea.value = data.text;
                        }
                    } catch (err) {
                        console.error('Enhance failed:', err);
                    }

                    enhanceBtn.innerHTML = origText;
                    enhanceBtn.disabled = false;
                    textarea.focus();
                });
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
```

**Step 3: Commit**

```bash
git add backoffice/templates/backoffice/partials/style_tags.html static/js/style-prompt-tools.js
git commit -m "Add reusable style prompt tools partial and JS"
```

---

### Task 4: Add Style Prompt Tools to Backoffice AI Pages

**Files:**
- Modify: `backoffice/templates/backoffice/ai_generate_page.html` (after brief textarea, ~line 63)
- Modify: `backoffice/templates/backoffice/ai_chat_refine.html` (after message input, ~line 126)
- Modify: `backoffice/templates/backoffice/header_edit.html` (after ai_instructions textarea, ~line 217)
- Modify: `backoffice/templates/backoffice/footer_edit.html` (after ai_instructions textarea, ~line 219)

**Step 1: Add to each template**

For each template, add two things:

1. Include the partial below the instruction textarea:
```html
{% include 'backoffice/partials/style_tags.html' with target_id='<textarea_id>' %}
```

Where `<textarea_id>` is:
- `ai_generate_page.html`: `brief`
- `ai_chat_refine.html`: `messageInput`
- `header_edit.html`: `ai_instructions`
- `footer_edit.html`: `ai_instructions`

2. Load the JS at the bottom of each template (in the `extra_js` block or before `</body>`):
```html
<script src="{% static 'js/style-prompt-tools.js' %}"></script>
```

**Step 2: Commit**

```bash
git add backoffice/templates/backoffice/ai_generate_page.html backoffice/templates/backoffice/ai_chat_refine.html backoffice/templates/backoffice/header_edit.html backoffice/templates/backoffice/footer_edit.html
git commit -m "Add style tags and enhance button to backoffice AI instruction inputs"
```

---

### Task 5: Add Tags, Enhance, and Suggest to Editor v2 AI Panel

**Files:**
- Modify: `editor_v2/static/editor_v2/js/modules/ai-panel.js`
- Modify: `editor_v2/static/editor_v2/css/editor.css`

**Step 1: Update `render()` in ai-panel.js**

Add tag chips and action buttons between the "Refining..." label and the messages area. Tags are rendered as small clickable chips. Two action links: "Enhance" (always) and "Suggest" (when section/element selected).

In the `render()` function, update the `container.innerHTML` to include:

```javascript
const tags = ['minimal','bold','corporate','playful','dark theme','spacious','compact','flat','rounded','sharp','gradients','card-heavy','asymmetric','centered','image-rich','monochrome','vibrant'];
const tagChips = tags.map(t => `<button class="ev2-style-tag" data-tag="${esc(t)}">${esc(t)}</button>`).join('');

container.innerHTML = `
    <div style="padding:8px 0;font-size:12px;color:var(--ev2-text-faint);">
        Refining ${targetLabel}
    </div>
    <div class="ev2-ai-messages" id="ev2-ai-msgs"></div>
    <div class="ev2-ai-input-row">
        <input class="ev2-ai-input" id="ev2-ai-input" type="text" placeholder="Describe changes..." />
        <button class="ev2-ai-send" id="ev2-ai-send">Send</button>
    </div>
    <div class="ev2-style-tools">
        <div class="ev2-style-tags">${tagChips}</div>
        <div class="ev2-style-actions">
            <button class="ev2-style-action" id="ev2-enhance-btn">Enhance</button>
            <button class="ev2-style-action" id="ev2-suggest-btn">Suggest</button>
        </div>
    </div>`;
```

After the existing event listeners, add:

```javascript
// Tag chip click handlers
container.querySelectorAll('.ev2-style-tag').forEach(btn => {
    btn.addEventListener('click', () => {
        const tag = btn.dataset.tag;
        const input = $('#ev2-ai-input');
        if (!input) return;
        const current = input.value.trim();
        const regex = new RegExp('(^|[,;.\\s])' + tag.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '([,;.\\s]|$)', 'i');
        if (regex.test(current)) {
            input.value = current.replace(regex, '$1').replace(/\s{2,}/g, ' ').replace(/^[,;.\s]+|[,;.\s]+$/g, '').trim();
            btn.classList.remove('active');
        } else {
            input.value = current ? current + ', ' + tag : tag;
            btn.classList.add('active');
        }
        input.focus();
    });
});

// Enhance button
$('#ev2-enhance-btn')?.addEventListener('click', async () => {
    const input = $('#ev2-ai-input');
    const text = input?.value?.trim();
    if (!text) return;
    const btn = $('#ev2-enhance-btn');
    btn.textContent = 'Enhancing...';
    btn.disabled = true;
    try {
        const res = await api.post('/enhance-prompt/', { text, mode: 'enhance' });
        if (res.success && res.text) input.value = res.text;
    } catch (err) { console.error('Enhance failed:', err); }
    btn.textContent = 'Enhance';
    btn.disabled = false;
    input.focus();
});

// Suggest button
$('#ev2-suggest-btn')?.addEventListener('click', async () => {
    const input = $('#ev2-ai-input');
    const btn = $('#ev2-suggest-btn');
    // Get current section HTML from DOM
    const secEl = currentSection ? document.querySelector(`[data-section="${currentSection}"]`) : null;
    if (!secEl) return;
    btn.textContent = 'Suggesting...';
    btn.disabled = true;
    try {
        const res = await api.post('/enhance-prompt/', {
            text: input?.value?.trim() || '',
            section_html: secEl.outerHTML,
            mode: 'suggest',
        });
        if (res.success && res.text) input.value = res.text;
    } catch (err) { console.error('Suggest failed:', err); }
    btn.textContent = 'Suggest';
    btn.disabled = false;
    input.focus();
});
```

Note: The `api.post()` helper already prepends the `apiBase` (`/editor-v2/api`), but the enhance endpoint is at `/ai/api/enhance-prompt/`. Either:
- Add a URL to editor_v2/urls.py that proxies to the ai endpoint, OR
- Use `fetch()` directly for this one call (simpler)

Recommend: Use `fetch()` directly since `api.post()` prepends `/editor-v2/api`. The enhance/suggest buttons should call:
```javascript
const csrfToken = config().csrfToken;
const res = await fetch('/ai/api/enhance-prompt/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
    body: JSON.stringify({ text, mode: 'enhance' }),
}).then(r => r.json());
```

**Step 2: Add CSS for tag chips and action buttons**

In `editor_v2/static/editor_v2/css/editor.css`:

```css
/* Style prompt tools */
.ev2-style-tools { padding: 4px 0; }
.ev2-style-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 6px; }
.ev2-style-tag {
    padding: 1px 8px;
    font-size: 11px;
    border-radius: 99px;
    border: 1px solid var(--ev2-border);
    color: var(--ev2-text-faint);
    background: transparent;
    cursor: pointer;
    transition: all 0.15s;
}
.ev2-style-tag:hover { border-color: var(--ev2-accent); color: var(--ev2-accent); }
.ev2-style-tag.active { border-color: var(--ev2-accent); color: var(--ev2-accent); background: rgba(99,102,241,0.1); }
.ev2-style-actions { display: flex; gap: 8px; }
.ev2-style-action {
    font-size: 11px;
    color: var(--ev2-accent);
    background: none;
    border: none;
    cursor: pointer;
    padding: 0;
    font-weight: 500;
}
.ev2-style-action:hover { text-decoration: underline; }
.ev2-style-action:disabled { opacity: 0.5; cursor: default; text-decoration: none; }
```

**Step 3: Commit**

```bash
git add editor_v2/static/editor_v2/js/modules/ai-panel.js editor_v2/static/editor_v2/css/editor.css
git commit -m "Add style tags, enhance, and suggest to editor v2 AI panel"
```

---

### Task 6: Cache Bust and Final Verification

**Files:**
- Modify: `templates/base.html`

**Step 1: Bump cache versions**

In `templates/base.html`:
- CSS: `editor.css?v=7` → `?v=8`
- JS: `editor.js?v=12` → `?v=13`

**Step 2: Manual verification checklist**

1. Open a page in backoffice → AI Generate Page → verify tag chips and enhance button below brief textarea
2. Open chat refine → verify tags + enhance below message input
3. Open header/footer edit → verify tags + enhance below AI instructions
4. Click a tag → check it appends to textarea, chip highlights
5. Click same tag again → check it removes from textarea, chip un-highlights
6. Type "clean, spacious layout" → click Enhance → verify enhanced text replaces input
7. Open editor v2 (`?edit=v2`) → select a section → AI tab → verify tags + enhance + suggest
8. Click Suggest → verify it analyzes the section and populates the input
9. Generate a page without any style tags → verify it produces a neutral/moderate layout (no aggressive asymmetry, py-32 heroes, etc.)

**Step 3: Commit**

```bash
git add templates/base.html
git commit -m "Bump editor cache versions for style calibration"
```
