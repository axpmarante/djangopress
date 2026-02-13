# Editor v2 Unified Chat Refinement — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rewrite the editor v2 AI panel as a unified chat supporting page, section, and element scopes with persistent conversation history.

**Architecture:** Add three new backend endpoints (`refine-page`, `save-ai-page`, `session`) to `editor/api_views.py`, register them in `editor_v2/urls.py`, then rewrite `ai-panel.js` with a scope selector bar, scrollable message list, and per-scope API routing. The existing section/element endpoints stay unchanged.

**Tech Stack:** Django views, `ContentGenerationService`, `RefinementSession` model, ES module JS, CSS.

---

### Task 1: Add `refine_page` endpoint to `editor/api_views.py`

This endpoint refines the full page HTML without saving to DB — same pattern as existing `refine_section` but calling `refine_page_with_html()`.

**Files:**
- Modify: `editor/api_views.py` (add new function after `save_ai_element` at ~line 800)

**Step 1: Write the endpoint**

Add at the end of `editor/api_views.py` (before any closing comments), after the existing `save_ai_element` function:

```python
@superuser_required
@require_http_methods(["POST"])
def refine_page(request):
    """
    Refine the full page using AI without saving to DB.
    Returns html_template and content for client-side preview.

    POST /editor-v2/api/refine-page/
    {
        "page_id": 1,
        "instructions": "Make the hero section more impactful",
        "conversation_history": [{"role": "user", "content": "..."}, ...],
        "session_id": null
    }
    """
    try:
        data = json.loads(request.body)
        page_id = data.get('page_id')
        instructions = data.get('instructions', '').strip()
        conversation_history = data.get('conversation_history', [])
        session_id = data.get('session_id')

        if not page_id:
            return JsonResponse({'success': False, 'error': 'Missing page_id'}, status=400)
        if not instructions:
            return JsonResponse({'success': False, 'error': 'Missing instructions'}, status=400)

        from core.models import Page
        try:
            page = Page.objects.get(id=page_id)
        except Page.DoesNotExist:
            return JsonResponse({'success': False, 'error': f'Page {page_id} not found'}, status=404)

        # Load or create session
        from ai.models import RefinementSession
        if session_id:
            try:
                session = RefinementSession.objects.get(id=session_id, page=page)
            except RefinementSession.DoesNotExist:
                session = None
        else:
            session = None

        if not session:
            session = RefinementSession(
                page=page,
                title=instructions[:80],
                model_used='gemini-pro',
                created_by=request.user if request.user.is_authenticated else None,
            )
            session.save()

        session.add_user_message(instructions)
        history = session.get_history_for_prompt()

        # Create version for rollback
        page.create_version(
            user=request.user,
            change_summary=f'Before editor refine-page: {instructions[:100]}'
        )

        # Call AI — full page refinement (gemini-pro)
        from ai.services import ContentGenerationService
        service = ContentGenerationService()
        result = service.refine_page_with_html(
            page_id=page_id,
            instructions=instructions,
            model_override='gemini-pro',
            conversation_history=history or None,
        )

        # Build assistant message
        assistant_msg = f"I've refined the page based on your instructions."
        session.add_assistant_message(assistant_msg, ['full-page'])
        session.save()

        return JsonResponse({
            'success': True,
            'page': {
                'html_template': result.get('html_content', ''),
                'content': result.get('content', {}),
            },
            'assistant_message': assistant_msg,
            'session_id': session.id,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
```

**Step 2: Verify the file has no syntax errors**

Run: `python -c "import py_compile; py_compile.compile('editor/api_views.py', doraise=True)"`
Expected: no output (success)

**Step 3: Commit**

```bash
git add editor/api_views.py
git commit -m "Add refine_page endpoint for editor v2 full-page AI refinement"
```

---

### Task 2: Add `save_ai_page` endpoint to `editor/api_views.py`

Saves the full page result when the user clicks Apply. Replaces `page.html_content` and `page.content` entirely.

**Files:**
- Modify: `editor/api_views.py` (add after `refine_page`)

**Step 1: Write the endpoint**

Add after the `refine_page` function:

```python
@superuser_required
@require_http_methods(["POST"])
def save_ai_page(request):
    """
    Save full-page AI refinement result.

    POST /editor-v2/api/save-ai-page/
    {
        "page_id": 1,
        "html_template": "<section ...>...</section>...",
        "content": {"translations": {"pt": {...}, "en": {...}}}
    }
    """
    try:
        data = json.loads(request.body)
        page_id = data.get('page_id')
        html_template = data.get('html_template', '').strip()
        content = data.get('content', {})

        if not page_id or not html_template:
            return JsonResponse({'success': False, 'error': 'Missing page_id or html_template'}, status=400)

        from core.models import Page
        try:
            page = Page.objects.get(id=page_id)
        except Page.DoesNotExist:
            return JsonResponse({'success': False, 'error': f'Page {page_id} not found'}, status=404)

        # Create version for rollback
        page.create_version(
            user=request.user,
            change_summary='Before save-ai-page (full page replacement)'
        )

        page.html_content = html_template
        if content:
            page.content = content
        page.save()

        return JsonResponse({
            'success': True,
            'message': 'Page saved successfully',
            'page_id': page.id,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
```

**Step 2: Verify syntax**

Run: `python -c "import py_compile; py_compile.compile('editor/api_views.py', doraise=True)"`

**Step 3: Commit**

```bash
git add editor/api_views.py
git commit -m "Add save_ai_page endpoint for full-page save"
```

---

### Task 3: Add `get_editor_session` endpoint to `editor/api_views.py`

Loads the most recent session for a page so the editor can display conversation history on init.

**Files:**
- Modify: `editor/api_views.py` (add after `save_ai_page`)

**Step 1: Write the endpoint**

```python
@superuser_required
@require_http_methods(["GET"])
def get_editor_session(request, page_id):
    """
    Load the most recent RefinementSession for the editor.

    GET /editor-v2/api/session/<page_id>/
    Returns session messages for display in the chat panel.
    """
    try:
        from ai.models import RefinementSession

        session = RefinementSession.objects.filter(
            page_id=page_id
        ).order_by('-updated_at').first()

        if not session:
            return JsonResponse({
                'success': True,
                'session_id': None,
                'messages': [],
            })

        return JsonResponse({
            'success': True,
            'session_id': session.id,
            'messages': session.messages or [],
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
```

**Step 2: Verify syntax**

Run: `python -c "import py_compile; py_compile.compile('editor/api_views.py', doraise=True)"`

**Step 3: Commit**

```bash
git add editor/api_views.py
git commit -m "Add get_editor_session endpoint for loading chat history"
```

---

### Task 4: Register new URLs in `editor_v2/urls.py`

**Files:**
- Modify: `editor_v2/urls.py`

**Step 1: Add three new URL patterns**

Add after the existing `save-ai-element` line:

```python
    # AI full-page refinement endpoints
    path('api/refine-page/', api_views.refine_page, name='api_refine_page'),
    path('api/save-ai-page/', api_views.save_ai_page, name='api_save_ai_page'),

    # Session history endpoint
    path('api/session/<int:page_id>/', api_views.get_editor_session, name='api_get_session'),
```

**Step 2: Verify Django URL resolution works**

Run: `python -c "from django.core.management import execute_from_command_line; execute_from_command_line(['manage.py', 'check'])"`
Expected: `System check identified no issues`

**Step 3: Commit**

```bash
git add editor_v2/urls.py
git commit -m "Register refine-page, save-ai-page, session URLs in editor v2"
```

---

### Task 5: Rewrite `ai-panel.js` with unified chat and scope selector

This is the main frontend change. The current file (`editor_v2/static/editor_v2/js/modules/ai-panel.js`, 327 lines) gets fully rewritten.

**Files:**
- Modify: `editor_v2/static/editor_v2/js/modules/ai-panel.js` (full rewrite)

**Step 1: Write the new `ai-panel.js`**

Key changes from current implementation:
- Add `activeScope` state: `'page'` | `'section'` | `'element'`
- Scope selector bar at top of panel with three chips: Page, Section, Element
- Canvas selection updates `currentSection`/`currentElementId` chips but does NOT reset session or messages
- `sessionId` persists across scope changes (one session per editor load)
- On init, fetch session history via `GET /editor-v2/api/session/<page_id>/`
- Messages display with scope badges (`[page]`, `[hero]`, `[cta_button]`)
- `send()` routes to `/refine-page/`, `/refine-section/`, or `/refine-element/` based on `activeScope`
- Page preview: replace `.editor-v2-content` innerHTML with de-templatized result
- Page apply: call `/save-ai-page/` then reload
- Section/element apply: call existing `/save-ai-section/` or `/save-ai-element/` then reload
- Style tools (tags, enhance, suggest) stay below the input

The full rewritten module:

```javascript
/**
 * AI Panel — Unified chat with page/section/element scope selector.
 */
import { events } from '../lib/events.js';
import { $, hasStoredElementId } from '../lib/dom.js';
import { api } from '../lib/api.js';

function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

const config = () => window.EDITOR_CONFIG || {};
const STYLE_TAGS = ['minimal','bold','corporate','playful','dark theme','spacious','compact','flat','rounded','sharp','gradients','card-heavy','asymmetric','centered','image-rich','monochrome','vibrant'];
let unsubs = [];

// State
let activeScope = 'page';        // 'page' | 'section' | 'element'
let currentSection = null;
let currentElementId = null;
let sessionId = null;
let messages = [];
let pendingResult = null;
let pendingScope = null;         // scope of the pending result
let originalHtml = null;
let activeTab = null;
let sessionLoaded = false;

// Replace {{ trans.xxx }} with real text for live preview
function detemplatize(html, translations, lang) {
    const trans = translations?.[lang] || {};
    return html.replace(/\{\{\s*trans\.(\w+)\s*\}\}/g, (_, key) => trans[key] || key);
}

export function init() {
    unsubs.push(events.on('sidebar:tab-changed', (tab) => {
        activeTab = tab;
        if (tab === 'ai') {
            loadSession();
            render();
        }
    }));
    unsubs.push(events.on('selection:changed', (el) => {
        const sec = el?.closest?.('[data-section]');
        const sectionName = sec?.getAttribute('data-section') || null;
        const isSection = el?.hasAttribute?.('data-section');
        const elId = (!isSection && el && hasStoredElementId(el)) ? el.getAttribute('data-element-id') : null;

        currentSection = sectionName;
        currentElementId = elId;

        // Auto-switch scope based on selection (but don't reset chat)
        if (isSection && sectionName) {
            activeScope = 'section';
        } else if (elId) {
            activeScope = 'element';
        }
        if (activeTab === 'ai') render();
    }));
    unsubs.push(events.on('context:ai-refine', (data) => {
        currentSection = data?.section || null;
        currentElementId = data?.elementId || null;
        activeScope = data?.elementId ? 'element' : 'section';
        events.emit('sidebar:switch-tab', 'ai');
    }));
}

export function destroy() {
    unsubs.forEach(u => u());
    unsubs = [];
    restorePreview();
    activeScope = 'page'; currentSection = null; currentElementId = null;
    sessionId = null; messages = []; pendingResult = null; pendingScope = null;
    originalHtml = null; activeTab = null; sessionLoaded = false;
}

// Load session history on first AI tab open
async function loadSession() {
    if (sessionLoaded || !config().pageId) return;
    sessionLoaded = true;
    try {
        const res = await api.get(`/session/${config().pageId}/`);
        if (res.success && res.session_id) {
            sessionId = res.session_id;
            // Convert stored messages to display format
            messages = (res.messages || []).map(m => ({
                role: m.role,
                content: m.content,
                scope: m.sections_changed?.[0] || 'page',
            }));
            if (activeTab === 'ai') render();
        }
    } catch (err) {
        console.warn('Failed to load session:', err);
    }
}

function render() {
    const container = $('#ev2-tab-content');
    if (!container) return;

    if (!config().aiEnabled) {
        container.innerHTML = '<p class="ev2-placeholder ev2-empty-state">AI features require superuser access.</p>';
        return;
    }

    // Build scope bar
    const scopeBar = buildScopeBar();
    const tagChips = STYLE_TAGS.map(t => `<button class="ev2-style-tag" data-tag="${esc(t)}">${esc(t)}</button>`).join('');

    container.innerHTML = `
        ${scopeBar}
        <div class="ev2-ai-messages" id="ev2-ai-msgs"></div>
        ${pendingResult ? `<div class="ev2-ai-actions" id="ev2-ai-actions">
            <button id="ev2-ai-apply" class="ev2-btn-primary" style="flex:1;padding:6px;font-size:12px;">Apply</button>
            <button id="ev2-ai-discard" class="ev2-btn-secondary" style="flex:1;padding:6px;font-size:12px;">Discard</button>
        </div>` : ''}
        <div class="ev2-ai-input-row">
            <textarea class="ev2-ai-input" id="ev2-ai-input" rows="2" placeholder="Describe changes..."></textarea>
            <button class="ev2-ai-send" id="ev2-ai-send">Send</button>
        </div>
        <div class="ev2-style-tools">
            <div class="ev2-style-tags">${tagChips}</div>
            <div class="ev2-style-actions">
                <button class="ev2-style-action" id="ev2-enhance-btn">Enhance</button>
                <button class="ev2-style-action" id="ev2-suggest-btn">Suggest</button>
            </div>
        </div>`;

    renderMessages();

    const input = $('#ev2-ai-input');
    const btn = $('#ev2-ai-send');
    input?.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
    });
    btn?.addEventListener('click', send);
    $('#ev2-ai-apply')?.addEventListener('click', applyResult);
    $('#ev2-ai-discard')?.addEventListener('click', discardResult);
    bindScopeBar();
    bindStyleTools();
    input?.focus();
}

function buildScopeBar() {
    const pageActive = activeScope === 'page' ? 'active' : '';
    const sectionActive = activeScope === 'section' ? 'active' : '';
    const elementActive = activeScope === 'element' ? 'active' : '';

    const sectionLabel = currentSection ? esc(currentSection) : '—';
    const elementLabel = currentElementId ? esc(currentElementId) : '—';

    const sectionDisabled = !currentSection ? 'disabled' : '';
    const elementDisabled = !currentElementId ? 'disabled' : '';

    return `<div class="ev2-scope-bar">
        <button class="ev2-scope-chip ${pageActive}" data-scope="page">Page</button>
        <button class="ev2-scope-chip ${sectionActive}" data-scope="section" ${sectionDisabled}>${sectionLabel}</button>
        <button class="ev2-scope-chip ${elementActive}" data-scope="element" ${elementDisabled}>${elementLabel}</button>
    </div>`;
}

function bindScopeBar() {
    document.querySelectorAll('.ev2-scope-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            if (chip.disabled) return;
            const scope = chip.dataset.scope;
            if (scope === 'section' && !currentSection) return;
            if (scope === 'element' && !currentElementId) return;
            restorePreview();
            pendingResult = null;
            pendingScope = null;
            activeScope = scope;
            render();
        });
    });
}

function renderMessages() {
    const list = $('#ev2-ai-msgs');
    if (!list) return;
    let html = '';
    for (const m of messages) {
        const badge = m.scope ? `<span class="ev2-scope-badge">${esc(String(m.scope))}</span>` : '';
        html += `<div class="ev2-ai-message ${esc(m.role)}">${badge}${esc(m.content)}</div>`;
    }
    list.innerHTML = html;
    list.scrollTop = list.scrollHeight;
}

async function send() {
    const input = $('#ev2-ai-input');
    const text = input?.value?.trim();
    if (!text) return;

    // Validate scope target
    if (activeScope === 'section' && !currentSection) return;
    if (activeScope === 'element' && (!currentElementId || !currentSection)) return;

    input.value = '';
    restorePreview();
    pendingResult = null;
    pendingScope = null;

    // Scope label for badge
    let scopeLabel = 'page';
    if (activeScope === 'section') scopeLabel = currentSection;
    if (activeScope === 'element') scopeLabel = currentElementId;

    messages.push({ role: 'user', content: text, scope: scopeLabel });
    renderMessages();
    setLoading(true);

    try {
        const history = messages.filter(m => m.role !== 'system').slice(0, -1).map(m => ({ role: m.role, content: m.content }));
        let res;

        if (activeScope === 'page') {
            res = await api.post('/refine-page/', {
                page_id: config().pageId,
                instructions: text,
                conversation_history: history,
                session_id: sessionId,
            });
        } else if (activeScope === 'element') {
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
            const msg = res.assistant_message || 'Changes ready to apply.';
            messages.push({ role: 'assistant', content: msg, scope: scopeLabel });
            pendingResult = res.page || res.section || res.element;
            pendingScope = activeScope;
            if (pendingResult) showPreview();
        } else {
            messages.push({ role: 'assistant', content: 'Error: ' + (res.error || 'Unknown error'), scope: scopeLabel });
        }
    } catch (err) {
        messages.push({ role: 'assistant', content: 'Request failed: ' + (err.message || err), scope: scopeLabel });
    }
    setLoading(false);
    render();
}

function setLoading(loading) {
    const list = $('#ev2-ai-msgs');
    if (!list) return;
    const existing = list.querySelector('.ev2-ai-thinking');
    if (loading && !existing) {
        const el = document.createElement('div');
        el.className = 'ev2-ai-message assistant ev2-ai-thinking';
        el.textContent = 'Thinking...';
        el.style.opacity = '0.6';
        list.appendChild(el);
        list.scrollTop = list.scrollHeight;
    } else if (!loading && existing) {
        existing.remove();
    }
    const input = $('#ev2-ai-input');
    const btn = $('#ev2-ai-send');
    if (input) input.disabled = loading;
    if (btn) btn.disabled = loading;
}

async function applyResult() {
    if (!pendingResult || !pendingScope) return;
    try {
        if (pendingScope === 'page') {
            await api.post('/save-ai-page/', {
                page_id: config().pageId,
                html_template: pendingResult.html_template,
                content: pendingResult.content,
            });
        } else if (pendingScope === 'element') {
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
        pendingResult = null;
        pendingScope = null;
        window.location.reload();
    } catch (err) {
        messages.push({ role: 'assistant', content: 'Save failed: ' + (err.message || err), scope: '' });
        render();
    }
}

function discardResult() {
    restorePreview();
    pendingResult = null;
    pendingScope = null;
    render();
}

// Live DOM preview
function showPreview() {
    if (!pendingResult) return;
    const lang = config().language || 'pt';
    const translations = pendingResult.content?.translations || {};
    const previewHtml = detemplatize(pendingResult.html_template, translations, lang);

    if (pendingScope === 'page') {
        const wrapper = document.querySelector('.editor-v2-content');
        if (!wrapper) return;
        if (!originalHtml) originalHtml = wrapper.innerHTML;
        wrapper.innerHTML = previewHtml;
    } else if (pendingScope === 'element' && currentElementId) {
        const el = document.querySelector(`[data-element-id="${currentElementId}"]`);
        if (!el) return;
        if (!originalHtml) originalHtml = el.outerHTML;
        el.outerHTML = previewHtml;
    } else if (pendingScope === 'section' && currentSection) {
        const sec = document.querySelector(`[data-section="${currentSection}"]`);
        if (!sec) return;
        if (!originalHtml) originalHtml = sec.outerHTML;
        sec.outerHTML = previewHtml;
    }
}

// Restore original HTML after discard
function restorePreview() {
    if (!originalHtml) return;
    if (pendingScope === 'page') {
        const wrapper = document.querySelector('.editor-v2-content');
        if (wrapper) wrapper.innerHTML = originalHtml;
    } else if (pendingScope === 'element' && currentElementId) {
        const el = document.querySelector(`[data-element-id="${currentElementId}"]`);
        if (el) el.outerHTML = originalHtml;
    } else if (pendingScope === 'section' && currentSection) {
        const sec = document.querySelector(`[data-section="${currentSection}"]`);
        if (sec) sec.outerHTML = originalHtml;
    }
    originalHtml = null;
}

async function fetchEnhance(payload) {
    const res = await fetch('/ai/api/enhance-prompt/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': config().csrfToken },
        body: JSON.stringify(payload),
    });
    return res.json();
}

function bindStyleTools() {
    const input = $('#ev2-ai-input');
    if (!input) return;

    document.querySelectorAll('.ev2-style-tag').forEach(btn => {
        btn.addEventListener('click', () => {
            const tag = btn.dataset.tag;
            const current = input.value.trim();
            const escaped = tag.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
            const regex = new RegExp('(^|[,;.\\s])' + escaped + '([,;.\\s]|$)', 'i');
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

    $('#ev2-enhance-btn')?.addEventListener('click', async () => {
        const text = input.value.trim();
        if (!text) return;
        const btn = $('#ev2-enhance-btn');
        btn.textContent = 'Enhancing...'; btn.disabled = true;
        try {
            const res = await fetchEnhance({ text, mode: 'enhance' });
            if (res.success && res.text) input.value = res.text;
        } catch (err) { console.error('Enhance failed:', err); }
        btn.textContent = 'Enhance'; btn.disabled = false;
        input.focus();
    });

    $('#ev2-suggest-btn')?.addEventListener('click', async () => {
        const secEl = currentSection ? document.querySelector(`[data-section="${currentSection}"]`) : null;
        if (!secEl) return;
        const btn = $('#ev2-suggest-btn');
        btn.textContent = 'Suggesting...'; btn.disabled = true;
        try {
            const res = await fetchEnhance({ text: input.value.trim() || '', section_html: secEl.outerHTML, mode: 'suggest' });
            if (res.success && res.text) input.value = res.text;
        } catch (err) { console.error('Suggest failed:', err); }
        btn.textContent = 'Suggest'; btn.disabled = false;
        input.focus();
    });
}
```

**Step 2: Verify JS has no syntax errors**

Run: `node -c editor_v2/static/editor_v2/js/modules/ai-panel.js`
Expected: no output (success)

**Step 3: Commit**

```bash
git add editor_v2/static/editor_v2/js/modules/ai-panel.js
git commit -m "Rewrite ai-panel.js with unified chat and page/section/element scope"
```

---

### Task 6: Add CSS for scope bar and chat improvements

**Files:**
- Modify: `editor_v2/static/editor_v2/css/editor.css`

**Step 1: Add scope bar and badge styles**

Add after the existing `.ev2-style-action` styles:

```css
/* ── Scope selector bar ── */
.ev2-scope-bar {
    display: flex;
    gap: 4px;
    padding: 8px 0;
    border-bottom: 1px solid var(--ev2-border);
    margin-bottom: 4px;
}

.ev2-scope-chip {
    padding: 4px 10px;
    font-size: 11px;
    border: 1px solid var(--ev2-border);
    border-radius: 12px;
    background: transparent;
    color: var(--ev2-text-faint);
    cursor: pointer;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 120px;
    transition: all 0.15s;
}

.ev2-scope-chip:hover:not(:disabled) {
    border-color: var(--ev2-accent);
    color: var(--ev2-text);
}

.ev2-scope-chip.active {
    background: var(--ev2-accent);
    color: #fff;
    border-color: var(--ev2-accent);
}

.ev2-scope-chip:disabled {
    opacity: 0.35;
    cursor: default;
}

/* ── Scope badge in messages ── */
.ev2-scope-badge {
    display: inline-block;
    font-size: 9px;
    padding: 1px 5px;
    border-radius: 8px;
    background: var(--ev2-bg-alt);
    color: var(--ev2-text-faint);
    margin-right: 4px;
    vertical-align: middle;
    font-weight: 600;
    text-transform: lowercase;
}

/* ── Apply/Discard bar ── */
.ev2-ai-actions {
    display: flex;
    gap: 8px;
    padding: 8px 0;
}

/* ── Textarea input (replaces single-line input) ── */
.ev2-ai-input {
    resize: none;
}
```

**Step 2: Commit**

```bash
git add editor_v2/static/editor_v2/css/editor.css
git commit -m "Add CSS for scope bar, badges, and chat actions"
```

---

### Task 7: Cache bust and verify

**Files:**
- Modify: `templates/base.html`

**Step 1: Bump cache versions**

Update the CSS version from `?v=8` to `?v=9` and JS version from `?v=13` to `?v=14`:

In `templates/base.html`:
- Line 30: `editor.css' %}?v=8` → `editor.css' %}?v=9`
- Line 134: `editor.js' %}?v=13` → `editor.js' %}?v=14`

**Step 2: Commit**

```bash
git add templates/base.html
git commit -m "Cache bust editor v2 CSS v9, JS v14 for unified chat"
```

**Step 3: Manual verification**

1. Run `python manage.py runserver 8000`
2. Visit a page with `?edit=v2`
3. Click the AI tab — should see scope bar with [Page] active, empty chat
4. Click a section on the canvas — scope bar updates to show section name
5. Click an element with a stored `data-element-id` — scope bar shows element ID
6. Type "Make the hero more impactful" with Page scope → API call to `/refine-page/`
7. See live preview of full page replacement
8. Click Apply → page saves and reloads
9. Switch scope to a section, send instruction → uses `/refine-section/`
10. Session history preserved across scope switches
11. Reload editor → previous messages load from session endpoint
