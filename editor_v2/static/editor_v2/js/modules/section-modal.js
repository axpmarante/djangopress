/**
 * Section Modal — standalone modal for generating + inserting new sections.
 *
 * Listens for `inserter:activated` to open, handles the full
 * generate -> preview A/B/C -> apply flow via the modal UI.
 */

import { events } from '../lib/events.js';
import { api } from '../lib/api.js';
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

let options = [];      // [{html}, ...]
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
    promptInput.focus();
}

function close() {
    if (!modal) return;
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
    if (options.length > 1) {
        tabsContainer.style.display = '';
        tabsContainer.innerHTML = options
            .map((_, i) => `<button class="ev2-option-tab${i === activeOption ? ' active' : ''}" data-option="${i}">${String.fromCharCode(65 + i)}</button>`)
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
    const text = promptInput?.value?.trim();
    if (!text) return;

    const insertState = getInsertState();
    if (!insertState) return;

    generateBtn.disabled = true;
    setStatus('Generating 3 options...', 'loading');

    try {
        const res = await api.post('/refine-multi/', withEditableId({
            page_id: config().pageId,
            mode: 'create',
            insert_after: insertState.afterSection || null,
            instructions: text,
            conversation_history: [],
            session_id: null,
        }));

        if (res.success && res.options) {
            options = res.options;
            activeOption = 0;
            setStatus('Choose an option (A/B/C) then click Apply', 'success');
            showResultPhase();
            if (options.length > 0) previewInPlaceholder(options[0].html);
        } else {
            setStatus('Error: ' + (res.error || 'Generation failed'), 'error');
            showGeneratePhase();
        }
    } catch (err) {
        setStatus('Request failed: ' + (err.message || err), 'error');
        showGeneratePhase();
    }

    generateBtn.disabled = false;
}

// ---------------------------------------------------------------------------
// Tab switching (A / B / C preview)
// ---------------------------------------------------------------------------

function switchTab(index) {
    if (index === activeOption || !options[index]) return;
    activeOption = index;
    previewInPlaceholder(options[index].html);

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

    applyBtn.textContent = 'Saving...';
    applyBtn.disabled = true;
    discardBtn.disabled = true;

    try {
        await api.post('/apply-option/', withEditableId({
            page_id: config().pageId,
            scope: 'new-section',
            section_name: null,
            selector: null,
            html: chosen.html,
            mode: 'insert',
            insert_after: insertState?.afterSection || null,
        }));

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
            if (generateBtn.style.display !== 'none') {
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
