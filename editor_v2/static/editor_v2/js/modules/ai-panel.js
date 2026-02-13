/**
 * AI Panel — Section refinement chat in the sidebar AI tab.
 */
import { events } from '../lib/events.js';
import { $, hasStoredElementId } from '../lib/dom.js';
import { api } from '../lib/api.js';

function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

const config = () => window.EDITOR_CONFIG || {};
const STYLE_TAGS = ['minimal','bold','corporate','playful','dark theme','spacious','compact','flat','rounded','sharp','gradients','card-heavy','asymmetric','centered','image-rich','monochrome','vibrant'];
let unsubs = [];
let currentSection = null;
let currentElementId = null;
let refinementMode = null; // 'section' or 'element'
let sessionId = null;
let messages = [];
let pendingResult = null;
let originalHtml = null; // stored for live preview restore (element or section)
let activeTab = null;

// Replace {{ trans.xxx }} with real text from translations for live preview
function detemplatize(html, translations, lang) {
    const trans = translations?.[lang] || {};
    return html.replace(/\{\{\s*trans\.(\w+)\s*\}\}/g, (_, key) => trans[key] || key);
}

export function init() {
    unsubs.push(events.on('sidebar:tab-changed', (tab) => {
        activeTab = tab;
        if (tab === 'ai') render();
    }));
    unsubs.push(events.on('selection:changed', (el) => {
        const sec = el?.closest?.('[data-section]');
        const sectionName = sec?.getAttribute('data-section') || null;
        const isSection = el?.hasAttribute?.('data-section');
        const elId = (!isSection && el && hasStoredElementId(el)) ? el.getAttribute('data-element-id') : null;

        const newMode = isSection ? 'section' : (elId ? 'element' : null);
        const newSection = sectionName;
        const newElementId = elId;

        if (newMode !== refinementMode || newSection !== currentSection || newElementId !== currentElementId) {
            restorePreview();
            sessionId = null; messages = []; pendingResult = null; originalHtml = null;
        }
        currentSection = newSection;
        currentElementId = newElementId;
        refinementMode = newMode;
        if (activeTab === 'ai') render();
    }));
    unsubs.push(events.on('context:ai-refine', (data) => {
        currentSection = data?.section || null;
        currentElementId = data?.elementId || null;
        refinementMode = data?.elementId ? 'element' : 'section';
        sessionId = null; messages = []; pendingResult = null;
        events.emit('sidebar:switch-tab', 'ai');
    }));
}

export function destroy() {
    unsubs.forEach(u => u());
    unsubs = [];
    restorePreview();
    currentSection = null; currentElementId = null; refinementMode = null; sessionId = null; messages = []; pendingResult = null; originalHtml = null; activeTab = null;
}

function render() {
    const container = $('#ev2-tab-content');
    if (!container) return;

    if (!config().aiEnabled) {
        container.innerHTML = '<p class="ev2-placeholder ev2-empty-state">AI features require superuser access.</p>';
        return;
    }
    if (!refinementMode) {
        container.innerHTML = '<p class="ev2-placeholder ev2-empty-state">Select a section or labeled element to use AI refinement.</p>';
        return;
    }

    const targetLabel = refinementMode === 'element'
        ? `element: <strong style="color:var(--ev2-text);">${esc(currentElementId)}</strong> <span style="color:var(--ev2-text-faint)">in ${esc(currentSection)}</span>`
        : `section: <strong style="color:var(--ev2-text);">${esc(currentSection)}</strong>`;

    const tagChips = STYLE_TAGS.map(t => `<button class="ev2-style-tag" data-tag="${esc(t)}">${esc(t)}</button>`).join('');

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

    renderMessages();
    const input = $('#ev2-ai-input');
    const btn = $('#ev2-ai-send');
    input?.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } });
    btn?.addEventListener('click', send);
    bindStyleTools();
    input?.focus();
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

    // Tag chips
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

    // Enhance button
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

    // Suggest button
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
    if (!text || !refinementMode) return;
    input.value = '';

    messages.push({ role: 'user', content: text });
    pendingResult = null;
    renderMessages();
    setLoading(true);

    try {
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
            // Live DOM preview
            if (pendingResult) showPreview();
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
        pendingResult = null;
        window.location.reload();
    } catch (err) {
        messages.push({ role: 'assistant', content: 'Save failed: ' + (err.message || err) });
        renderMessages();
    }
}

function discardResult() {
    restorePreview();
    pendingResult = null;
    renderMessages();
    $('#ev2-ai-input')?.focus();
}

// Live DOM preview: swap element or section with AI result
function showPreview() {
    if (!pendingResult) return;
    const lang = config().language || 'pt';
    const translations = pendingResult.content?.translations || {};
    const previewHtml = detemplatize(pendingResult.html_template, translations, lang);

    if (refinementMode === 'element' && currentElementId) {
        const el = document.querySelector(`[data-element-id="${currentElementId}"]`);
        if (!el) return;
        if (!originalHtml) originalHtml = el.outerHTML;
        el.outerHTML = previewHtml;
    } else if (refinementMode === 'section' && currentSection) {
        const sec = document.querySelector(`[data-section="${currentSection}"]`);
        if (!sec) return;
        if (!originalHtml) originalHtml = sec.outerHTML;
        sec.outerHTML = previewHtml;
    }
}

// Restore original HTML after discard
function restorePreview() {
    if (!originalHtml) return;
    if (refinementMode === 'element' && currentElementId) {
        const el = document.querySelector(`[data-element-id="${currentElementId}"]`);
        if (el) el.outerHTML = originalHtml;
    } else if (refinementMode === 'section' && currentSection) {
        const sec = document.querySelector(`[data-section="${currentSection}"]`);
        if (sec) sec.outerHTML = originalHtml;
    }
    originalHtml = null;
}
