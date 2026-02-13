/**
 * AI Panel — Section refinement chat in the sidebar AI tab.
 */
import { events } from '../lib/events.js';
import { $ } from '../lib/dom.js';
import { api } from '../lib/api.js';

function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

const config = () => window.EDITOR_CONFIG || {};
let unsubs = [];
let currentSection = null;
let sessionId = null;
let messages = [];
let pendingResult = null;
let activeTab = null;

export function init() {
    unsubs.push(events.on('sidebar:tab-changed', (tab) => {
        activeTab = tab;
        if (tab === 'ai') render();
    }));
    unsubs.push(events.on('selection:changed', (el) => {
        const sec = el?.closest?.('[data-section]');
        const name = sec?.getAttribute('data-section') || null;
        if (name !== currentSection) { currentSection = name; sessionId = null; messages = []; pendingResult = null; }
        if (activeTab === 'ai') render();
    }));
    unsubs.push(events.on('context:ai-refine', (data) => {
        currentSection = data?.section || null;
        sessionId = null; messages = []; pendingResult = null;
        events.emit('sidebar:switch-tab', 'ai');
    }));
}

export function destroy() {
    unsubs.forEach(u => u());
    unsubs = [];
    currentSection = null; sessionId = null; messages = []; pendingResult = null; activeTab = null;
}

function render() {
    const container = $('#ev2-tab-content');
    if (!container) return;

    if (!config().aiEnabled) {
        container.innerHTML = '<p class="ev2-placeholder ev2-empty-state">AI features require superuser access.</p>';
        return;
    }
    if (!currentSection) {
        container.innerHTML = '<p class="ev2-placeholder ev2-empty-state">Select a section to use AI refinement.</p>';
        return;
    }

    container.innerHTML = `
        <div style="padding:8px 0;font-size:12px;color:var(--ev2-text-faint);">
            Refining: <strong style="color:var(--ev2-text);">${esc(currentSection)}</strong>
        </div>
        <div class="ev2-ai-messages" id="ev2-ai-msgs"></div>
        <div class="ev2-ai-input-row">
            <input class="ev2-ai-input" id="ev2-ai-input" type="text" placeholder="Describe changes..." />
            <button class="ev2-ai-send" id="ev2-ai-send">Send</button>
        </div>`;

    renderMessages();
    const input = $('#ev2-ai-input');
    const btn = $('#ev2-ai-send');
    input?.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } });
    btn?.addEventListener('click', send);
    input?.focus();
}

function renderMessages() {
    const list = $('#ev2-ai-msgs');
    if (!list) return;
    let html = '';
    for (const m of messages) {
        html += `<div class="ev2-ai-message ${esc(m.role)}">${esc(m.content)}</div>`;
    }
    if (pendingResult) {
        html += `<div style="display:flex;gap:8px;padding:8px 0;">
            <button id="ev2-ai-apply" class="ev2-btn-primary" style="flex:1;padding:6px;font-size:12px;">Apply</button>
            <button id="ev2-ai-discard" class="ev2-btn-secondary" style="flex:1;padding:6px;font-size:12px;">Discard</button>
        </div>`;
    }
    list.innerHTML = html;
    list.scrollTop = list.scrollHeight;

    $('#ev2-ai-apply')?.addEventListener('click', applyResult);
    $('#ev2-ai-discard')?.addEventListener('click', discardResult);
}

async function send() {
    const input = $('#ev2-ai-input');
    const text = input?.value?.trim();
    if (!text || !currentSection) return;
    input.value = '';

    messages.push({ role: 'user', content: text });
    pendingResult = null;
    renderMessages();
    setLoading(true);

    try {
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
        } else {
            messages.push({ role: 'assistant', content: 'Error: ' + (res.error || 'Unknown error') });
        }
    } catch (err) {
        messages.push({ role: 'assistant', content: 'Request failed: ' + (err.message || err) });
    }
    setLoading(false);
    renderMessages();
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
    if (!pendingResult || !currentSection) return;
    try {
        await api.post('/save-ai-section/', {
            page_id: config().pageId,
            section_name: currentSection,
            html_template: pendingResult.html_template,
            content: pendingResult.content,
        });
        pendingResult = null;
        window.location.reload();
    } catch (err) {
        messages.push({ role: 'assistant', content: 'Save failed: ' + (err.message || err) });
        renderMessages();
    }
}

function discardResult() {
    pendingResult = null;
    renderMessages();
    $('#ev2-ai-input')?.focus();
}
