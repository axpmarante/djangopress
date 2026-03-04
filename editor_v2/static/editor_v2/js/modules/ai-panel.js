/**
 * AI Panel — Unified chat with session switcher and scope selector.
 * Uses SSE streaming for real-time progress during AI refinement.
 */
import { events } from '../lib/events.js';
import { $, getCssSelector, getElementLabel, initDynamicComponents } from '../lib/dom.js';
import { api } from '../lib/api.js';
import { SSEClient } from '../lib/sse-client.js';

function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

const config = () => window.EDITOR_CONFIG || {};
function withEditableId(body) {
    const cfg = config();
    if (cfg.contentTypeId && cfg.objectId) { body.content_type_id = cfg.contentTypeId; body.object_id = cfg.objectId; }
    return body;
}
let unsubs = [];

// Step label mapping for progress events
const STEP_LABELS = {
    prepare: 'Preparing...',
    component_selection: 'Selecting components...',
    refine_html: 'Generating HTML...',
    templatize_translate: 'Translating...',
    processing_options: 'Processing options...',
    complete: 'Finishing up...',
};

// State
let activeScope = 'page';        // 'page' | 'section' | 'element'
let currentSection = null;
let currentSelector = null;
let sessionId = null;
let sessionsList = [];            // [{id, title, updated_at}, ...]
let messages = [];
let pendingResult = null;
let pendingScope = null;
let originalHtml = null;
let activeTab = null;
let sessionLoaded = false;
let freshChat = false;            // true when context menu triggers a new chat
let options = [];               // multi-option: array of {html} objects
let activeOption = 0;           // which option tab is active (0, 1, 2)
let multiOption = true;         // true = 3 variations, false = single (faster)
let lockedSection = null;       // snapshot of currentSection at send() time
let lockedSelector = null;      // snapshot of currentSelector at send() time
let lockedScope = null;         // snapshot of activeScope at send() time
let activeSSE = null;           // current SSEClient instance (for abort)

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
        const selector = (!isSection && el) ? getCssSelector(el) : null;

        currentSection = sectionName;
        currentSelector = selector;

        if (isSection && sectionName) {
            activeScope = 'section';
        } else if (selector) {
            activeScope = 'element';
        }
        if (activeTab === 'ai') render();
    }));
    unsubs.push(events.on('context:ai-refine', (data) => {
        currentSection = data?.section || null;
        currentSelector = data?.selector || null;
        activeScope = data?.selector ? 'element' : 'section';
        // Start a fresh chat targeting the clicked section/element
        sessionId = null;
        messages = [];
        pendingResult = null;
        pendingScope = null;
        originalHtml = null;
        options = [];
        activeOption = 0;
        freshChat = true;
        events.emit('sidebar:switch-tab', 'ai');
    }));
}

export function destroy() {
    unsubs.forEach(u => u());
    unsubs = [];
    if (activeSSE) { activeSSE.abort(); activeSSE = null; }
    restorePreview();
    activeScope = 'page'; currentSection = null; currentSelector = null;
    sessionId = null; sessionsList = []; messages = [];
    pendingResult = null; pendingScope = null;
    originalHtml = null; activeTab = null; sessionLoaded = false; freshChat = false;
    options = []; activeOption = 0;
}

async function loadSession(targetSessionId) {
    if (!config().pageId) return;
    const isInitial = !sessionLoaded;
    sessionLoaded = true;

    // If freshChat flag is set, only fetch the sessions list (for the dropdown)
    // but don't load any session content — we want an empty chat.
    const wantFresh = freshChat;
    freshChat = false;

    try {
        const qs = targetSessionId ? `?session_id=${targetSessionId}` : '';
        const res = await api.get(`/session/${config().pageId}/${qs}`);
        if (res.success) {
            sessionsList = res.sessions || [];
            if (wantFresh) {
                // Keep sessionId=null and messages=[] — fresh chat
            } else if (res.session_id) {
                sessionId = res.session_id;
                messages = (res.messages || []).map(m => ({
                    role: m.role,
                    content: m.content,
                    scope: m.sections_changed?.[0] || 'page',
                }));
            } else if (isInitial) {
                sessionId = null;
                messages = [];
            }
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

    container.innerHTML = `
        ${buildSessionBar()}
        ${buildScopeSelect()}
        <div class="ev2-ai-messages" id="ev2-ai-msgs"></div>
        ${(options.length > 0 || pendingResult) ? `<div class="ev2-ai-actions">
            ${options.length > 1 ? `<div class="ev2-option-tabs">
                ${options.map((_, i) => `<button class="ev2-option-tab ${i === activeOption ? 'active' : ''}" data-option="${i}">${String.fromCharCode(65 + i)}</button>`).join('')}
            </div>` : ''}
            <button id="ev2-ai-apply" class="ev2-btn-primary" style="flex:1;padding:6px;font-size:12px;">Apply</button>
            <button id="ev2-ai-discard" class="ev2-btn-secondary" style="flex:1;padding:6px;font-size:12px;">Discard</button>
        </div>` : ''}
        <div class="ev2-ai-input-row">
            <textarea class="ev2-ai-input" id="ev2-ai-input" rows="2" placeholder="Describe changes..."></textarea>
            <button class="ev2-ai-send" id="ev2-ai-send">Send</button>
        </div>
        <div class="ev2-style-actions">
            <button class="ev2-style-action" id="ev2-enhance-btn">Enhance</button>
            <button class="ev2-style-action" id="ev2-suggest-btn">Suggest</button>
            ${activeScope !== 'page' ? `<label class="ev2-style-action ev2-multi-toggle" title="Generate 3 design variations to choose from">
                <input type="checkbox" id="ev2-multi-toggle" ${multiOption ? 'checked' : ''}>
                <span>3 options</span>
            </label>` : ''}
        </div>`;

    renderMessages();

    const input = $('#ev2-ai-input');
    input?.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
    });
    $('#ev2-ai-send')?.addEventListener('click', send);
    $('#ev2-ai-apply')?.addEventListener('click', applyResult);
    $('#ev2-ai-discard')?.addEventListener('click', discardResult);
    // Option tab click handlers
    container.querySelectorAll('.ev2-option-tab').forEach(btn => {
        btn.addEventListener('click', () => {
            const idx = parseInt(btn.dataset.option, 10);
            if (idx === activeOption || !options[idx]) return;
            restorePreview();
            activeOption = idx;
            showMultiPreview(idx);
            container.querySelectorAll('.ev2-option-tab').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        });
    });
    $('#ev2-multi-toggle')?.addEventListener('change', (e) => {
        multiOption = e.target.checked;
    });
    bindSessionBar();
    bindScopeSelect();
    bindStyleTools();
    input?.focus();
}

// ── Session bar: dropdown of past sessions + New Chat button ──

function buildSessionBar() {
    let options = '';
    if (!sessionId && messages.length === 0) {
        options += '<option value="" selected>New conversation</option>';
    }
    for (const s of sessionsList) {
        const sel = s.id === sessionId ? 'selected' : '';
        const label = esc(s.title || `Session ${s.id}`);
        options += `<option value="${s.id}" ${sel}>${label}</option>`;
    }
    if (sessionsList.length === 0 && !sessionId) {
        options = '<option value="" selected>No sessions yet</option>';
    }

    return `<div class="ev2-session-bar">
        <select class="ev2-session-select" id="ev2-session-select">${options}</select>
        <button class="ev2-new-chat" id="ev2-new-chat">New Chat</button>
    </div>`;
}

function bindSessionBar() {
    $('#ev2-session-select')?.addEventListener('change', async (e) => {
        const id = e.target.value;
        if (!id) return;
        restorePreview();
        pendingResult = null;
        pendingScope = null;
        originalHtml = null;
        options = [];
        activeOption = 0;
        await loadSession(parseInt(id));
    });
    $('#ev2-new-chat')?.addEventListener('click', () => {
        restorePreview();
        sessionId = null;
        messages = [];
        pendingResult = null;
        pendingScope = null;
        originalHtml = null;
        options = [];
        activeOption = 0;
        render();
    });
}

// ── Scope selector: Page / Section / Element ──

function buildScopeSelect() {
    let options = '<option value="page"' + (activeScope === 'page' ? ' selected' : '') + '>Full Page</option>';
    if (currentSection) {
        options += `<option value="section"${activeScope === 'section' ? ' selected' : ''}>Section: ${esc(currentSection)}</option>`;
    }
    if (currentSelector) {
        const el = document.querySelector(currentSelector);
        const label = el ? getElementLabel(el) : 'element';
        options += `<option value="element"${activeScope === 'element' ? ' selected' : ''}>Element: ${esc(label)}</option>`;
    }

    return `<div class="ev2-scope-row">
        <span class="ev2-scope-label">Target</span>
        <select class="ev2-scope-select" id="ev2-scope-select">${options}</select>
    </div>`;
}

function bindScopeSelect() {
    $('#ev2-scope-select')?.addEventListener('change', (e) => {
        restorePreview();
        pendingResult = null;
        pendingScope = null;
        options = [];
        activeOption = 0;
        activeScope = e.target.value;
        render();
    });
}

// ── Messages ──

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

// ── Send (SSE streaming) ──

async function send() {
    const input = $('#ev2-ai-input');
    const text = input?.value?.trim();
    if (!text) return;

    if (activeScope === 'section' && !currentSection) return;
    if (activeScope === 'element' && !currentSelector) return;

    input.value = '';
    restorePreview();
    pendingResult = null;
    pendingScope = null;

    // Lock target identity so selection changes during processing don't matter
    lockedSection = currentSection;
    lockedSelector = currentSelector;
    lockedScope = activeScope;

    let scopeLabel = 'page';
    if (activeScope === 'section') scopeLabel = currentSection;
    if (activeScope === 'element') scopeLabel = 'element';

    messages.push({ role: 'user', content: text, scope: scopeLabel });
    renderMessages();
    setLoading(true);

    const history = messages.filter(m => m.role !== 'system').slice(0, -1).map(m => ({ role: m.role, content: m.content }));
    const apiBase = config().apiBase || '/editor-v2/api';

    let url, body;

    if (activeScope === 'page') {
        url = `${apiBase}/refine-page/stream/`;
        body = withEditableId({
            page_id: config().pageId,
            instructions: text,
            conversation_history: history,
            session_id: sessionId,
        });
    } else if (activeScope === 'element') {
        url = `${apiBase}/refine-multi/stream/`;
        body = withEditableId({
            page_id: config().pageId,
            scope: 'element',
            selector: currentSelector,
            instructions: text,
            conversation_history: history,
            session_id: sessionId,
            multi_option: multiOption,
        });
    } else {
        url = `${apiBase}/refine-multi/stream/`;
        body = withEditableId({
            page_id: config().pageId,
            scope: 'section',
            section_name: currentSection,
            instructions: text,
            conversation_history: history,
            session_id: sessionId,
            multi_option: multiOption,
        });
    }

    activeSSE = new SSEClient(url, {
        csrfToken: config().csrfToken,
        onProgress: (data) => {
            // Update the thinking indicator with the current step label
            if (data.step) {
                const label = STEP_LABELS[data.step] || data.step;
                const statusSuffix = data.status === 'done' ? ' Done.' : '';
                updateThinkingLabel(label + statusSuffix);
            }
        },
        onComplete: (res) => {
            activeSSE = null;
            if (res.success) {
                sessionId = res.session_id || sessionId;
                const msg = res.assistant_message || 'Changes ready to apply.';
                messages.push({ role: 'assistant', content: msg, scope: scopeLabel });

                if (res.options) {
                    // Multi-option response (section/element)
                    options = res.options;
                    activeOption = 0;
                    pendingScope = lockedScope;
                    if (options.length > 0) showMultiPreview(0);
                } else if (res.page || res.page_data?.page) {
                    // Single-option response (page scope)
                    // page_data wrapping comes from run_with_progress; direct complete has .page
                    pendingResult = res.page || res.page_data?.page;
                    pendingScope = lockedScope;
                    options = [];
                    if (pendingResult) showPreview();
                }
                refreshSessionsList();
            } else {
                messages.push({ role: 'assistant', content: 'Error: ' + (res.error || 'Unknown error'), scope: scopeLabel });
            }
            setLoading(false);
            render();
        },
        onError: (data) => {
            activeSSE = null;
            messages.push({ role: 'assistant', content: 'Error: ' + (data.error || 'Request failed'), scope: scopeLabel });
            setLoading(false);
            render();
        },
    });

    await activeSSE.start(body);
}

async function refreshSessionsList() {
    try {
        const res = await api.get(`/session/${config().pageId}/`);
        if (res.success) sessionsList = res.sessions || [];
    } catch (_) {}
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

    // Content overlay — blocks page interaction during AI processing
    const overlayId = 'ev2-ai-processing-overlay';
    if (loading && lockedScope !== 'page') {
        if (!document.getElementById(overlayId)) {
            const overlay = document.createElement('div');
            overlay.id = overlayId;
            overlay.className = 'ev2-ai-overlay';
            overlay.innerHTML = '<div class="ev2-ai-overlay-spinner"></div><div class="ev2-ai-overlay-label">Refining...</div>';
            document.body.appendChild(overlay);
        }
    } else {
        document.getElementById(overlayId)?.remove();
    }
}

/**
 * Update the thinking indicator text with the current step label.
 * Also updates the overlay label if visible.
 */
function updateThinkingLabel(label) {
    const thinking = document.querySelector('.ev2-ai-thinking');
    if (thinking) {
        thinking.textContent = label;
        const list = thinking.parentElement;
        if (list) list.scrollTop = list.scrollHeight;
    }
    // Also update overlay label if present
    const overlayLabel = document.querySelector('#ev2-ai-processing-overlay .ev2-ai-overlay-label');
    if (overlayLabel) {
        overlayLabel.textContent = label;
    }
}

// ── Apply / Discard ──

async function applyResult() {
    const applyBtn = $('#ev2-ai-apply');
    const discardBtn = $('#ev2-ai-discard');
    if (applyBtn) { applyBtn.textContent = 'Saving...'; applyBtn.disabled = true; }
    if (discardBtn) discardBtn.disabled = true;

    // Show overlay to block editor interaction during save + templatize
    setLoading(true);

    try {
        if (options.length > 0 && pendingScope) {
            // Multi-option: send chosen option to apply-option endpoint
            const chosen = options[activeOption];
            if (!chosen) return;
            await api.post('/apply-option/', withEditableId({
                page_id: config().pageId,
                scope: pendingScope,
                section_name: lockedSection,
                selector: lockedSelector,
                html: chosen.html,
            }));
        } else if (pendingResult && pendingScope) {
            // Single-option (page scope): existing flow
            if (pendingScope === 'page') {
                await api.post('/save-ai-page/', withEditableId({
                    page_id: config().pageId,
                    html_template: pendingResult.html_template,
                    content: pendingResult.content,
                }));
            }
        } else {
            setLoading(false);
            return;
        }
        pendingResult = null;
        pendingScope = null;
        options = [];

        // Visual feedback before reload
        if (applyBtn) {
            applyBtn.textContent = 'Saved!';
            applyBtn.style.background = '#10b981';
        }
        setTimeout(() => window.location.reload(), 600);
    } catch (err) {
        setLoading(false);
        if (applyBtn) { applyBtn.textContent = 'Apply'; applyBtn.disabled = false; }
        if (discardBtn) discardBtn.disabled = false;
        messages.push({ role: 'assistant', content: 'Save failed: ' + (err.message || err), scope: '' });
        render();
    }
}

function discardResult() {
    restorePreview();
    pendingResult = null;
    pendingScope = null;
    options = [];
    activeOption = 0;
    lockedSection = null;
    lockedSelector = null;
    lockedScope = null;
    render();
}

// ── Live DOM preview ──

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
    } else if (pendingScope === 'element' && lockedSelector) {
        const el = document.querySelector(lockedSelector);
        if (!el) return;
        if (!originalHtml) originalHtml = el.outerHTML;
        el.outerHTML = previewHtml;
    } else if (pendingScope === 'section' && lockedSection) {
        const sec = document.querySelector(`[data-section="${lockedSection}"]`);
        if (!sec) return;
        if (!originalHtml) originalHtml = sec.outerHTML;
        sec.outerHTML = previewHtml;
    }
}

function showMultiPreview(index) {
    if (!options[index]) return;
    const html = options[index].html;

    // Restore before switching
    if (originalHtml) restorePreview();

    if (pendingScope === 'element' && lockedSelector) {
        const el = document.querySelector(lockedSelector);
        if (!el) return;
        if (!originalHtml) originalHtml = el.outerHTML;
        el.outerHTML = html;
        // Re-init dynamic components in the replaced element's parent
        const parent = document.querySelector(lockedSelector)?.parentElement;
        if (parent) initDynamicComponents(parent);
    } else if (pendingScope === 'section' && lockedSection) {
        const sec = document.querySelector(`[data-section="${lockedSection}"]`);
        if (!sec) return;
        if (!originalHtml) originalHtml = sec.outerHTML;
        sec.outerHTML = html;
        // Re-init dynamic components in the new section
        const newSec = document.querySelector(`[data-section="${lockedSection}"]`);
        if (newSec) initDynamicComponents(newSec);
    }
}

function restorePreview() {
    if (!originalHtml) return;
    if (pendingScope === 'page') {
        const wrapper = document.querySelector('.editor-v2-content');
        if (wrapper) wrapper.innerHTML = originalHtml;
    } else if (pendingScope === 'element' && lockedSelector) {
        const el = document.querySelector(lockedSelector);
        if (el) el.outerHTML = originalHtml;
    } else if (pendingScope === 'section' && lockedSection) {
        const sec = document.querySelector(`[data-section="${lockedSection}"]`);
        if (sec) sec.outerHTML = originalHtml;
    }
    originalHtml = null;
}

// ── Style tools (Enhance / Suggest) ──

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
