/**
 * Section Modal — standalone modal for generating + inserting new sections.
 *
 * Listens for `inserter:activated` to open, handles the full
 * generate -> preview A/B/C -> apply flow via the modal UI.
 * Generation is the Chat pipeline (/chat/stream/, scope "new"): three
 * directions in the page's own style, design-checked, arriving one by one.
 */

import { events } from '../lib/events.js';
import { noteSaveAfterReload } from '../lib/save-notes.js';
import { api } from '../lib/api.js';
import { SSEClient } from '../lib/sse-client.js';
import {
    getInsertState,
    previewInPlaceholder,
    resetPlaceholder,
    removePlaceholder,
} from './section-inserter.js';

const config = () => window.EDITOR_CONFIG || {};
function withEditableId(body) {
    const cfg = config();
    if (cfg.contentTypeId && cfg.objectId) { body.content_type_id = cfg.contentTypeId; body.object_id = cfg.objectId; }
    return body;
}

// DOM references (cached on init)
let modal, backdrop, closeBtn, promptInput, statusEl;
let generateBtn, applyBtn, discardBtn, tabsContainer;

let options = [];      // [{key, name, html, why}, ...] in arrival order
let stream = null;
let activeOption = 0;
let unsubs = [];

// ---------------------------------------------------------------------------
// DOM helpers
// ---------------------------------------------------------------------------

function $(id) { return document.getElementById(id); }

function cacheDom() {
    modal         = $('ev2-section-modal');
    backdrop      = modal?.querySelector('.ev2-section-modal-backdrop');
    closeBtn      = $('ev2-section-modal-close');
    promptInput   = $('ev2-section-modal-prompt');
    statusEl      = $('ev2-section-modal-status');
    generateBtn   = $('ev2-section-modal-generate');
    applyBtn      = $('ev2-section-modal-apply');
    discardBtn    = $('ev2-section-modal-discard');
    tabsContainer = $('ev2-section-modal-tabs');
}

// ---------------------------------------------------------------------------
// Open / Close
// ---------------------------------------------------------------------------

function open() {
    if (!modal) return;
    modal.classList.remove('hidden');
    promptInput.value = '';
    hideStatus();
    showGeneratePhase();
    if (!(window.EDITOR_CONFIG || {}).aiEnabled) {
        setStatus('Generating a section with AI needs a superuser account. A section catalogue is coming next.', 'error');
        generateBtn.disabled = true;
    } else {
        generateBtn.disabled = false;
    }
    promptInput.focus();
}

function close() {
    if (!modal) return;
    stream?.abort();
    stream = null;
    modal.classList.add('hidden');
    options = [];
    activeOption = 0;
}

function closeAndCleanup() {
    close();
    removePlaceholder();
}

// ---------------------------------------------------------------------------
// UI state helpers
// ---------------------------------------------------------------------------

function showGeneratePhase() {
    generateBtn.style.display = '';
    applyBtn.style.display = 'none';
    discardBtn.style.display = 'none';
    tabsContainer.style.display = 'none';
    tabsContainer.innerHTML = '';
    promptInput.disabled = false;
}

function showResultPhase() {
    generateBtn.style.display = 'none';
    applyBtn.style.display = '';
    discardBtn.style.display = '';
    promptInput.disabled = false;
    if (options.length >= 1) {
        tabsContainer.style.display = '';
        tabsContainer.innerHTML = options
            .map((o, i) => `<button class="ev2-option-tab${i === activeOption ? ' active' : ''}" data-option="${i}" title="${String(o.name || '').replace(/"/g, '&quot;')}">${String.fromCharCode(65 + i)}</button>`)
            .join('');
        tabsContainer.querySelectorAll('.ev2-option-tab').forEach(btn => {
            btn.addEventListener('click', () => switchTab(parseInt(btn.dataset.option, 10)));
        });
    }
}

function setStatus(text, type) {
    if (!statusEl) return;
    statusEl.style.display = '';
    statusEl.className = 'ev2-section-modal-status ' + type;
    statusEl.textContent = text;
}

function hideStatus() {
    if (!statusEl) return;
    statusEl.style.display = 'none';
    statusEl.className = 'ev2-section-modal-status';
    statusEl.textContent = '';
}

// ---------------------------------------------------------------------------
// Generate
// ---------------------------------------------------------------------------

async function generate() {
    if (generateBtn?.disabled) return;
    const text = promptInput?.value?.trim();
    if (!text) return;

    const insertState = getInsertState();
    if (!insertState) return;

    generateBtn.disabled = true;
    options = [];
    activeOption = 0;
    let failed = 0;
    setStatus("Designing 3 options in this page's style…", 'loading');

    const finish = (message, type) => {
        stream = null;
        generateBtn.disabled = false;
        if (options.length) {
            setStatus(message || `Choose an option (${options.map((_, i) => String.fromCharCode(65 + i)).join('/')}) then click Apply`, type || 'success');
        } else {
            setStatus(message || "Couldn't make any option this time. Try again or change the description.", 'error');
            showGeneratePhase();
        }
    };
    stream = new SSEClient(`${config().apiBase || '/editor-v2/api'}/chat/stream/`, {
        csrfToken: config().csrfToken,
        onEvent: (name, data) => {
            if (name === 'option') {
                options.push(data);
                if (options.length === 1) previewInPlaceholder(data.html);
                showResultPhase();
                if (options.length < 3) setStatus(`${options.length} of 3 ready — the others are on the way…`, 'loading');
            } else if (name === 'option_failed') {
                failed += 1;
            } else if (name === 'complete') {
                finish(failed && options.length ? `${options.length} options ready (${failed} couldn't be made). Choose one, then Apply.` : '');
            } else if (name === 'error') {
                finish(`Error: ${data.error || 'Generation failed'}`, 'error');
            }
        },
        onError: (data) => finish(`Request failed: ${data?.error || 'network error'}`, 'error'),
    });
    await stream.start(withEditableId({
        page_id: config().pageId,
        scope: 'new',
        insert_after: insertState.afterSection || null,
        instructions: text,
        mode: 'explore',
        conversation_history: [],
        session_id: null,
    }));
    if (stream) finish();
}

// ---------------------------------------------------------------------------
// Tab switching (A / B / C preview)
// ---------------------------------------------------------------------------

function switchTab(index) {
    if (index === activeOption || !options[index]) return;
    activeOption = index;
    previewInPlaceholder(options[index].html);
    const o = options[index];
    setStatus(`${String.fromCharCode(65 + index)} · ${o.name || ''}${o.why ? ` — ${o.why}` : ''}`, 'success');

    tabsContainer.querySelectorAll('.ev2-option-tab').forEach(btn => {
        btn.classList.toggle('active', parseInt(btn.dataset.option, 10) === index);
    });
}

// ---------------------------------------------------------------------------
// Apply
// ---------------------------------------------------------------------------

async function apply() {
    const chosen = options[activeOption];
    if (!chosen) return;

    const insertState = getInsertState();

    applyBtn.textContent = 'Saving & translating...';
    applyBtn.disabled = true;
    discardBtn.disabled = true;

    try {
        const saved = await api.post('/apply-option/', withEditableId({
            page_id: config().pageId,
            scope: 'new-section',
            section_name: null,
            selector: null,
            html: chosen.html,
            mode: 'insert',
            insert_after: insertState?.afterSection || null,
        }));
        noteSaveAfterReload(saved, 'New section added');

        applyBtn.textContent = 'Saved!';
        applyBtn.style.background = '#10b981';
        setStatus('Section saved! Reloading...', 'success');
        setTimeout(() => window.location.reload(), 600);
    } catch (err) {
        applyBtn.textContent = 'Apply';
        applyBtn.disabled = false;
        discardBtn.disabled = false;
        setStatus('Save failed: ' + (err.message || err), 'error');
    }
}

// ---------------------------------------------------------------------------
// Discard
// ---------------------------------------------------------------------------

function discard() {
    resetPlaceholder();
    options = [];
    activeOption = 0;
    hideStatus();
    showGeneratePhase();
    promptInput.focus();
}

// ---------------------------------------------------------------------------
// Event binding
// ---------------------------------------------------------------------------

function bindEvents() {
    // Close triggers
    closeBtn?.addEventListener('click', closeAndCleanup);
    backdrop?.addEventListener('click', closeAndCleanup);

    // Escape key
    document.addEventListener('keydown', onKeyDown);

    // Generate
    generateBtn?.addEventListener('click', generate);
    promptInput?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (generateBtn.style.display !== 'none' && !generateBtn.disabled) {
                generate();
            }
        }
    });

    // Apply / Discard
    applyBtn?.addEventListener('click', apply);
    discardBtn?.addEventListener('click', discard);
}

function onKeyDown(e) {
    if (e.key === 'Escape' && modal && !modal.classList.contains('hidden')) {
        e.stopPropagation();
        closeAndCleanup();
    }
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export function init() {
    cacheDom();
    if (!modal) return;

    bindEvents();

    unsubs.push(events.on('inserter:activated', () => {
        open();
    }));

    unsubs.push(events.on('inserter:cancelled', () => {
        close();
    }));
}

export function destroy() {
    unsubs.forEach(u => u());
    unsubs = [];
    document.removeEventListener('keydown', onKeyDown);
    close();
}
