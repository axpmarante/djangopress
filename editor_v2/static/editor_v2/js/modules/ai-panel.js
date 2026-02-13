/**
 * AI Panel — Unified chat with session switcher and scope selector.
 */
import { events } from '../lib/events.js';
import { $, hasStoredElementId } from '../lib/dom.js';
import { api } from '../lib/api.js';

function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

const config = () => window.EDITOR_CONFIG || {};
let unsubs = [];

// State
let activeScope = 'page';        // 'page' | 'section' | 'element'
let currentSection = null;
let currentElementId = null;
let sessionId = null;
let sessionsList = [];            // [{id, title, updated_at}, ...]
let messages = [];
let pendingResult = null;
let pendingScope = null;
let originalHtml = null;
let activeTab = null;
let sessionLoaded = false;

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
    sessionId = null; sessionsList = []; messages = [];
    pendingResult = null; pendingScope = null;
    originalHtml = null; activeTab = null; sessionLoaded = false;
}

async function loadSession(targetSessionId) {
    if (!config().pageId) return;
    const isInitial = !sessionLoaded;
    sessionLoaded = true;
    try {
        const qs = targetSessionId ? `?session_id=${targetSessionId}` : '';
        const res = await api.get(`/session/${config().pageId}/${qs}`);
        if (res.success) {
            sessionsList = res.sessions || [];
            if (res.session_id) {
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
        ${pendingResult ? `<div class="ev2-ai-actions">
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
        </div>`;

    renderMessages();

    const input = $('#ev2-ai-input');
    input?.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
    });
    $('#ev2-ai-send')?.addEventListener('click', send);
    $('#ev2-ai-apply')?.addEventListener('click', applyResult);
    $('#ev2-ai-discard')?.addEventListener('click', discardResult);
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
        await loadSession(parseInt(id));
    });
    $('#ev2-new-chat')?.addEventListener('click', () => {
        restorePreview();
        sessionId = null;
        messages = [];
        pendingResult = null;
        pendingScope = null;
        originalHtml = null;
        render();
    });
}

// ── Scope selector: Page / Section / Element ──

function buildScopeSelect() {
    let options = '<option value="page"' + (activeScope === 'page' ? ' selected' : '') + '>Full Page</option>';
    if (currentSection) {
        options += `<option value="section"${activeScope === 'section' ? ' selected' : ''}>Section: ${esc(currentSection)}</option>`;
    }
    if (currentElementId) {
        options += `<option value="element"${activeScope === 'element' ? ' selected' : ''}>Element: ${esc(currentElementId)}</option>`;
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

// ── Send ──

async function send() {
    const input = $('#ev2-ai-input');
    const text = input?.value?.trim();
    if (!text) return;

    if (activeScope === 'section' && !currentSection) return;
    if (activeScope === 'element' && (!currentElementId || !currentSection)) return;

    input.value = '';
    restorePreview();
    pendingResult = null;
    pendingScope = null;

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
            // Refresh sessions list so the new/updated session appears in dropdown
            refreshSessionsList();
        } else {
            messages.push({ role: 'assistant', content: 'Error: ' + (res.error || 'Unknown error'), scope: scopeLabel });
        }
    } catch (err) {
        messages.push({ role: 'assistant', content: 'Request failed: ' + (err.message || err), scope: scopeLabel });
    }
    setLoading(false);
    render();
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
}

// ── Apply / Discard ──

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
