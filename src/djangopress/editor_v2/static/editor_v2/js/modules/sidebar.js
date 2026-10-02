import { events } from '../lib/events.js';
import { $, $$, getCssSelector, isTextElement, resolveSelector } from '../lib/dom.js';
import { findComponent } from '../lib/components.js';
import { prependComponentCard } from './component-panel.js';
import { renderDesignPanel, unmountDesignPanel } from './design-panel.js';
import { renderContentPanel } from './content-panel.js';
import { renderStructurePanel } from './structure-panel.js';

let activeTab = 'content';
let selectedEl = null;
const handlers = {};

// --- Escape ---

function esc(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// --- Media collection detection ---

function findMediaCollection(el) {
    let current = el;
    const section = el.closest('[data-section]');
    const boundary = section || el.closest('.editor-v2-content') || document.body;
    while (current && current !== boundary.parentElement) {
        if (current.hasAttribute && current.hasAttribute('data-media-collection')) {
            return current;
        }
        current = current.parentElement;
    }
    return null;
}

function renderMediaCollection(container, collectionEl) {
    const type = collectionEl.getAttribute('data-media-collection') || 'media';
    const section = collectionEl.closest('[data-section]');
    const sectionName = section ? section.getAttribute('data-section') : null;
    // Filter out Splide cloned slides (type:"loop" clones elements)
    const imgs = Array.from(collectionEl.querySelectorAll('img'))
        .filter(img => !img.closest('.splide__slide--clone'));

    let html = '<div class="ev2-media-collection-header">';
    html += `<h4>${imgs.length} image${imgs.length !== 1 ? 's' : ''}</h4>`;
    html += `<span class="ev2-media-collection-badge">${esc(type)}</span>`;
    html += '</div>';

    if (imgs.length > 0) {
        html += '<div class="ev2-media-grid">';
        imgs.forEach((img, i) => {
            const src = img.getAttribute('src') || '';
            const alt = img.getAttribute('alt') || '';
            const sel = getCssSelector(img) || '';
            html += `<div class="ev2-media-thumb" data-media-select="${esc(sel)}" title="${esc(alt || `Image ${i + 1}`)}">`;
            html += `<img src="${esc(src)}" alt="${esc(alt)}" />`;
            html += `<span class="ev2-media-thumb-index">${i + 1}</span>`;
            html += '</div>';
        });
        html += '</div>';
    }

    if (sectionName) {
        html += '<button type="button" class="ev2-btn-change-img" id="ev2-media-process-btn">Process Section Images</button>';
    }

    html += '<p class="ev2-media-hint">Click a thumbnail to edit individually</p>';

    container.innerHTML = html;

    for (const thumb of container.querySelectorAll('.ev2-media-thumb')) {
        thumb.addEventListener('click', () => {
            const sel = thumb.dataset.mediaSelect;
            if (!sel) return;
            const imgEl = resolveSelector(sel);
            if (imgEl) {
                events.emit('selection:request', imgEl);
                imgEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        });
    }

    const processBtn = container.querySelector('#ev2-media-process-btn');
    if (processBtn && sectionName) {
        processBtn.addEventListener('click', () => {
            events.emit('process-images:open', { section: sectionName });
        });
    }
}

// --- Content tab ---

function renderContentTab() {
    const c = $('#ev2-tab-content');
    if (!c) return;
    // A container inside a media collection keeps its thumbnail grid (gallery-like blocks
    // that are not a recognised component).
    if (selectedEl && selectedEl.tagName !== 'IMG' && !isTextElement(selectedEl) && !findComponent(selectedEl)
        && !selectedEl.hasAttribute('data-section')) {
        const collectionEl = findMediaCollection(selectedEl);
        if (collectionEl) {
            renderMediaCollection(c, collectionEl);
            return;
        }
    }
    renderContentPanel(c, selectedEl);
    if (selectedEl) prependComponentCard(c, selectedEl);
}

function renderDesignTab() {
    const container = $('#ev2-tab-content');
    if (!container) return;
    if (!selectedEl) {
        container.innerHTML = '<p class="ev2-placeholder ev2-empty-state">Select an element to edit its design</p>';
        return;
    }
    renderDesignPanel(container, selectedEl);
}

// --- Structure tab ---

function renderStructureTab() {
    const container = $('#ev2-tab-content');
    if (container) renderStructurePanel(container, selectedEl);
}

function renderActiveTab() {
    if (activeTab !== 'design') unmountDesignPanel();
    if (activeTab === 'content') renderContentTab();
    else if (activeTab === 'design') renderDesignTab();
    else if (activeTab === 'structure') renderStructureTab();
}

// --- Tab switching ---

function onTabClick(e) {
    const btn = e.target.closest('.ev2-tab[data-tab]');
    if (!btn) return;
    const tab = btn.dataset.tab;
    if (tab === activeTab) return;

    $$('.ev2-tab').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    activeTab = tab;
    renderActiveTab();
    events.emit('sidebar:tab-changed', tab);
}

// --- Selection handler ---

function onSelectionChanged(el) {
    selectedEl = el;
    renderActiveTab();
}

function onSwitchTab(tab) {
    const btn = $(`.ev2-tab[data-tab="${tab}"]`);
    if (!btn) return;
    $$('.ev2-tab').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    activeTab = tab;
    renderActiveTab();
    events.emit('sidebar:tab-changed', tab);
}

// --- Language bar ---

function onLangClick(e) {
    const btn = e.target.closest('.ev2-lang-btn');
    if (!btn || btn.classList.contains('active')) return;
    const lang = btn.dataset.lang;
    const url = new URL(window.location.href);
    url.pathname = url.pathname.replace(/^\/[a-z]{2}(\/|$)/, `/${lang}$1`);
    url.searchParams.set('edit', 'v2');
    window.location.href = url.toString();
}

// --- Save / Discard / Status ---

function onSaveClick() { events.emit('changes:save'); }
function onDiscardClick() { events.emit('changes:discard'); renderActiveTab(); }

function onChangesCount(count) {
    const saveBtn = $('#ev2-save-btn');
    const discardBtn = $('#ev2-discard-btn');
    const status = $('#ev2-status');
    const topSave = $('#ev2-save-topbar-btn');
    const badge = $('#ev2-change-count');

    if (saveBtn) saveBtn.disabled = count === 0;
    if (discardBtn) discardBtn.disabled = count === 0;
    if (status) status.textContent = count === 0 ? 'No changes' : `${count} change${count !== 1 ? 's' : ''}`;
    if (topSave) topSave.disabled = count === 0;
    if (badge) {
        badge.textContent = count;
        badge.classList.toggle('hidden', count === 0);
    }
}

function onChangesSaved() {
    const status = $('#ev2-status');
    if (status) {
        status.textContent = 'Saved';
        setTimeout(() => { status.textContent = 'No changes'; }, 2000);
    }
}

function onChangesError(msg) {
    const status = $('#ev2-status');
    if (status) {
        status.textContent = msg || 'Save failed';
        status.style.color = '#dc2626';
        setTimeout(() => { status.style.color = ''; }, 3000);
    }
}

function onUndoState({ canUndo, canRedo }) {
    const undoBtn = $('#ev2-undo-btn');
    const redoBtn = $('#ev2-redo-btn');
    if (undoBtn) undoBtn.disabled = !canUndo;
    if (redoBtn) redoBtn.disabled = !canRedo;
}

// --- Bind / Unbind helpers ---

function bindEl(selector, event, fn) {
    const el = $(selector);
    if (el) { el.addEventListener(event, fn); return el; }
    return null;
}

function unbindEl(selector, event, fn) {
    const el = $(selector);
    if (el) el.removeEventListener(event, fn);
}

// --- Lifecycle ---

export function init() {
    handlers.tabClick = onTabClick;
    handlers.langClick = onLangClick;
    handlers.saveClick = onSaveClick;
    handlers.discardClick = onDiscardClick;
    handlers.undoClick = () => events.emit('changes:undo');
    handlers.redoClick = () => events.emit('changes:redo');
    handlers.topbarSave = () => events.emit('changes:save');
    handlers.selectionChanged = onSelectionChanged;
    handlers.changesCount = onChangesCount;
    handlers.changesSaved = onChangesSaved;
    handlers.changesError = onChangesError;
    handlers.undoState = onUndoState;
    handlers.switchTab = onSwitchTab;

    // DOM event listeners
    bindEl('.ev2-tabs', 'click', handlers.tabClick);
    bindEl('.ev2-language-bar', 'click', handlers.langClick);
    bindEl('#ev2-save-btn', 'click', handlers.saveClick);
    bindEl('#ev2-discard-btn', 'click', handlers.discardClick);
    bindEl('#ev2-undo-btn', 'click', handlers.undoClick);
    bindEl('#ev2-redo-btn', 'click', handlers.redoClick);
    bindEl('#ev2-save-topbar-btn', 'click', handlers.topbarSave);

    // Event bus listeners
    events.on('selection:changed', handlers.selectionChanged);
    events.on('changes:count', handlers.changesCount);
    events.on('changes:saved', handlers.changesSaved);
    events.on('changes:error', handlers.changesError);
    events.on('changes:undo-state', handlers.undoState);
    events.on('sidebar:switch-tab', handlers.switchTab);

    renderActiveTab();
}

export function destroy() {
    unbindEl('.ev2-tabs', 'click', handlers.tabClick);
    unbindEl('.ev2-language-bar', 'click', handlers.langClick);
    unbindEl('#ev2-save-btn', 'click', handlers.saveClick);
    unbindEl('#ev2-discard-btn', 'click', handlers.discardClick);
    unbindEl('#ev2-undo-btn', 'click', handlers.undoClick);
    unbindEl('#ev2-redo-btn', 'click', handlers.redoClick);
    unbindEl('#ev2-save-topbar-btn', 'click', handlers.topbarSave);

    events.off('selection:changed', handlers.selectionChanged);
    events.off('changes:count', handlers.changesCount);
    events.off('changes:saved', handlers.changesSaved);
    events.off('changes:error', handlers.changesError);
    events.off('changes:undo-state', handlers.undoState);
    events.off('sidebar:switch-tab', handlers.switchTab);

    selectedEl = null;
    activeTab = 'content';
}
