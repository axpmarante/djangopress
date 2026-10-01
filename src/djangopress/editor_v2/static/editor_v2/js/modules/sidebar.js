import { events } from '../lib/events.js';
import { api } from '../lib/api.js';
import { $, $$, getCssSelector, isTextElement, getSections, getTagLabel, getEditableTopLevelDescendants, getAncestors, findCardScope, resolveSelector, isRuntimeClass } from '../lib/dom.js';
import { moveSection, canMoveSection } from '../lib/structural.js';
import { insertAfterSection } from './section-inserter.js';
import { findComponent } from '../lib/components.js';
import { prependComponentCard } from './component-panel.js';
import { renderDesignPanel } from './design-panel.js';

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
    if (!selectedEl) {
        c.innerHTML = '<p class="ev2-placeholder ev2-empty-state">Select an element to edit</p>';
        return;
    }
    const tag = selectedEl.tagName;
    const selector = getCssSelector(selectedEl) || '';

    if (tag === 'IMG') {
        renderImageFields(c, selector);
    } else if (isTextElement(selectedEl) && tag !== 'A') {
        renderTextField(c, selector);
        appendChildrenPanel(c);
    } else if (tag === 'A') {
        renderLinkFields(c, selector);
        appendChildrenPanel(c);
    } else {
        const collectionEl = findComponent(selectedEl) ? null : findMediaCollection(selectedEl);
        if (collectionEl) {
            renderMediaCollection(c, collectionEl);
        } else {
            const descendants = getEditableTopLevelDescendants(selectedEl);
            if (descendants.length > 0) {
                c.innerHTML = '';
                appendChildrenPanel(c);
            } else {
                c.innerHTML = '<p class="ev2-placeholder ev2-empty-state">Select a text element to edit content</p>';
            }
        }
    }

    prependComponentCard(c, selectedEl);
    prependContentBreadcrumb(c);
}

/**
 * Show a mini-breadcrumb at the top of the Content tab (sticky) so the
 * user can navigate UP without re-clicking the page. Clicking a crumb
 * re-selects that ancestor; the Content tab re-renders showing its
 * children panel, giving back the overview list.
 */
function prependContentBreadcrumb(container) {
    if (!selectedEl) return;

    // Trim ancestors to start at the closest [data-section] (inclusive).
    // The wrapper / main / outer divs aren't useful navigation targets —
    // sections are the meaningful editing scope.
    const ancestors = getAncestors(selectedEl).reverse();
    const sectionIdx = ancestors.findIndex(a => a.hasAttribute('data-section'));
    const trimmed = sectionIdx >= 0 ? ancestors.slice(sectionIdx) : [];

    // If selectedEl IS the section, trimmed is empty and we render just the
    // current crumb. If selectedEl is outside any section, render nothing.
    if (trimmed.length === 0 && !selectedEl.hasAttribute('data-section')) return;

    const wrap = document.createElement('div');
    wrap.className = 'ev2-content-breadcrumb';

    for (let i = 0; i < trimmed.length; i++) {
        const a = trimmed[i];
        const crumb = document.createElement('button');
        crumb.type = 'button';
        crumb.className = 'ev2-content-crumb';
        crumb.textContent = getTagLabel(a);
        crumb.title = 'Select this parent';
        crumb.addEventListener('click', () => events.emit('selection:request', a));
        wrap.appendChild(crumb);

        const sep = document.createElement('span');
        sep.className = 'ev2-content-crumb-sep';
        sep.textContent = '›';
        wrap.appendChild(sep);
    }

    const here = document.createElement('span');
    here.className = 'ev2-content-crumb ev2-content-crumb-current';
    here.textContent = getTagLabel(selectedEl);
    wrap.appendChild(here);

    container.insertBefore(wrap, container.firstChild);
}

function appendChildrenPanel(container) {
    // Use the card scope around selectedEl, not just its descendants — that
    // way image-as-background patterns surface (the <img> sibling of an
    // overlay div is in the same card, even though it isn't a descendant).
    const scope = findCardScope(selectedEl) || selectedEl;
    const items = getEditableTopLevelDescendants(scope).filter(i => i !== selectedEl);
    if (items.length === 0) return;

    const wrap = document.createElement('div');
    wrap.className = 'ev2-children-panel';

    const heading = document.createElement('div');
    heading.className = 'ev2-children-heading';
    const scopeLabel = scope === selectedEl
        ? ''
        : ` in this ${getTagLabel(scope)}`;
    heading.textContent = `${items.length} ${items.length === 1 ? 'element' : 'elements'}${scopeLabel}`;
    wrap.appendChild(heading);

    const list = document.createElement('div');
    list.className = 'ev2-children-list';

    for (const child of items) {
        const sel = getCssSelector(child) || '';
        if (!sel) continue;
        const row = document.createElement('button');
        row.type = 'button';
        row.className = 'ev2-children-row';
        row.dataset.childSelector = sel;
        row.title = `Edit ${child.tagName.toLowerCase()}`;

        if (child.tagName === 'IMG') {
            const src = child.getAttribute('src') || '';
            const alt = child.getAttribute('alt') || '';
            row.innerHTML = `
                <img class="ev2-children-thumb" src="${esc(src)}" alt="" loading="lazy" />
                <span class="ev2-children-tag">img</span>
                <span class="ev2-children-preview">${esc(alt || (src.split('/').pop() || '').split('?')[0])}</span>`;
        } else {
            const tag = child.tagName.toLowerCase();
            const text = (child.textContent || '').trim().slice(0, 80);
            row.innerHTML = `
                <span class="ev2-children-tag">${esc(tag)}</span>
                <span class="ev2-children-preview">${esc(text || '(empty)')}</span>`;
        }

        row.addEventListener('click', () => {
            const target = resolveSelector(sel);
            if (!target) return;
            events.emit('selection:request', target);
            target.scrollIntoView({ behavior: 'smooth', block: 'center' });
        });
        list.appendChild(row);
    }

    wrap.appendChild(list);
    container.appendChild(wrap);
}

function renderTextField(container, selector) {
    const fieldKey = '';
    const label = selectedEl.tagName.toLowerCase();
    const text = selectedEl.textContent.trim();
    const isLong = text.length > 80;

    let html = `<div class="ev2-field"><label class="ev2-label">${esc(label)}</label>`;
    if (isLong) {
        html += `<textarea class="ev2-textarea" data-field-key="${esc(fieldKey)}" data-selector="${esc(selector)}">${esc(text)}</textarea>`;
    } else {
        html += `<input class="ev2-input" type="text" data-field-key="${esc(fieldKey)}" data-selector="${esc(selector)}" value="${esc(text)}" />`;
    }
    html += '</div>';

    container.innerHTML = html;
    attachContentListeners(container);
}

function renderImageFields(container, selector) {
    const src = selectedEl.getAttribute('src') || '';
    const alt = selectedEl.getAttribute('alt') || '';
    container.innerHTML = `
        <div class="ev2-img-preview-wrap">
            <img src="${esc(src)}" alt="${esc(alt)}" class="ev2-img-preview" />
        </div>
        <div class="ev2-field">
            <button type="button" class="ev2-btn-change-img" id="ev2-change-img-btn">Change Image</button>
        </div>
        <div class="ev2-field"><label class="ev2-label">Alt text</label>
            <input class="ev2-input" type="text" data-attr="alt" data-selector="${esc(selector)}" value="${esc(alt)}" /></div>
        <div class="ev2-field"><label class="ev2-label">Image URL</label>
            <input class="ev2-input ev2-input-mono" type="text" data-attr="src" data-selector="${esc(selector)}" value="${esc(src)}" /></div>`;
    attachContentListeners(container);
    const changeBtn = container.querySelector('#ev2-change-img-btn');
    if (changeBtn) changeBtn.addEventListener('click', () => events.emit('image-picker:open'));
}

function renderLinkFields(container, selector) {
    const fieldKey = '';
    const label = selectedEl.tagName.toLowerCase();
    const text = selectedEl.textContent.trim();
    const href = selectedEl.getAttribute('href') || '';
    container.innerHTML = `
        <div class="ev2-field"><label class="ev2-label">${esc(label)}</label>
            <input class="ev2-input" type="text" data-field-key="${esc(fieldKey)}" data-selector="${esc(selector)}" value="${esc(text)}" />
            </div>
        <div class="ev2-field"><label class="ev2-label">Link URL</label>
            <input class="ev2-input" type="text" data-attr="href" data-selector="${esc(selector)}" value="${esc(href)}" /></div>`;
    attachContentListeners(container);
}

function attachContentListeners(container) {
    for (const input of $$('.ev2-input, .ev2-textarea', container)) {
        input.addEventListener('input', () => onContentInput(input));
    }
}

function onContentInput(input) {
    const selector = input.dataset.selector;
    const attr = input.dataset.attr;
    const fieldKey = input.dataset.fieldKey;
    const value = input.value;

    if (attr) {
        const oldValue = selectedEl.getAttribute(attr) || '';
        selectedEl.setAttribute(attr, value);
        events.emit('change:attribute', {
            type: 'attribute', selector, attribute: attr,
            value, oldValue, tagName: selectedEl.tagName.toLowerCase(),
        });

        // Keep <a data-lightbox> href in sync when an <img src> is edited
        // manually, so the lightbox opens the same image as the thumbnail.
        if (attr === 'src' && selectedEl.tagName === 'IMG') {
            const anchor = selectedEl.parentElement;
            if (anchor && anchor.tagName === 'A' && anchor.hasAttribute('data-lightbox')) {
                const anchorSelector = getCssSelector(anchor);
                const oldHref = anchor.getAttribute('href') || '';
                if (anchorSelector && oldHref !== value) {
                    anchor.setAttribute('href', value);
                    events.emit('change:attribute', {
                        type: 'attribute', selector: anchorSelector,
                        attribute: 'href', value, oldValue: oldHref, tagName: 'a',
                    });
                }
            }
        }
    } else {
        const oldValue = selectedEl.textContent;
        selectedEl.textContent = value;
        events.emit('change:content', {
            type: 'content', selector, fieldKey: fieldKey || '', value, oldValue,
        });
    }
}

// --- Design tab ---

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
    if (!container) return;

    const sections = getSections();
    if (sections.length === 0) {
        container.innerHTML = '<p class="ev2-placeholder ev2-empty-state">No sections found</p>';
        return;
    }

    const selectedSel = selectedEl ? getCssSelector(selectedEl) : null;
    let html = '<div class="ev2-tree">';

    for (const section of sections) {
        const sectionSel = getCssSelector(section) || '';
        const isCurrent = sectionSel === selectedSel;
        html += `<div class="ev2-tree-item${isCurrent ? ' current' : ''}" data-tree-selector="${esc(sectionSel)}">`;
        const name = section.getAttribute('data-section') || '';
        html += `<strong style="flex:1">${esc(getTagLabel(section))}</strong>`;
        html += `<span class="ev2-tree-actions">`;
        html += `<button type="button" data-tree-action="up" data-name="${esc(name)}" title="Move section up" ${canMoveSection(section, 'up') ? '' : 'disabled'}>▲</button>`;
        html += `<button type="button" data-tree-action="down" data-name="${esc(name)}" title="Move section down" ${canMoveSection(section, 'down') ? '' : 'disabled'}>▼</button>`;
        html += `<button type="button" data-tree-action="insert" data-name="${esc(name)}" title="Insert section after">+</button>`;
        html += `</span></div>`;

        // Show direct children with editable content
        for (const child of section.children) {
            const childSel = getCssSelector(child) || '';
            const isChildCurrent = childSel === selectedSel;
            const label = getTagLabel(child);
            html += `<div class="ev2-tree-item${isChildCurrent ? ' current' : ''}" data-tree-selector="${esc(childSel)}">`;
            html += `<span class="ev2-tree-indent"></span>${esc(label)}`;

            // Show text preview for text elements
            if (isTextElement(child)) {
                const preview = child.textContent.trim().slice(0, 30);
                if (preview) html += ` <span style="color:var(--ev2-text-faint)">${esc(preview)}${child.textContent.trim().length > 30 ? '...' : ''}</span>`;
            }
            html += '</div>';

            // One more level deep for key elements
            for (const grandchild of child.children) {
                if (!isTextElement(grandchild) && grandchild.tagName !== 'IMG' && grandchild.tagName !== 'A') continue;
                const gcSel = getCssSelector(grandchild) || '';
                const isGcCurrent = gcSel === selectedSel;
                html += `<div class="ev2-tree-item${isGcCurrent ? ' current' : ''}" data-tree-selector="${esc(gcSel)}">`;
                html += `<span class="ev2-tree-indent"></span><span class="ev2-tree-indent"></span>${esc(getTagLabel(grandchild))}`;
                if (isTextElement(grandchild)) {
                    const preview = grandchild.textContent.trim().slice(0, 25);
                    if (preview) html += ` <span style="color:var(--ev2-text-faint)">${esc(preview)}${grandchild.textContent.trim().length > 25 ? '...' : ''}</span>`;
                }
                html += '</div>';
            }
        }
    }
    html += '</div>';
    container.innerHTML = html;
}

function onTreeClick(e) {
    if (activeTab !== 'structure') return;
    const actionBtn = e.target.closest('[data-tree-action]');
    if (actionBtn) {
        e.stopPropagation();
        if (actionBtn.disabled) return;
        const name = actionBtn.dataset.name;
        const action = actionBtn.dataset.treeAction;
        if (action === 'up') moveSection(name, 'up');
        else if (action === 'down') moveSection(name, 'down');
        else if (action === 'insert') insertAfterSection(name);
        return;
    }
    const item = e.target.closest('.ev2-tree-item');
    if (!item) return;
    const sel = item.dataset.treeSelector;
    if (!sel) return;
    const el = resolveSelector(sel);
    if (el) {
        events.emit('selection:request', el);
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
}

function renderActiveTab() {
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
    handlers.treeClick = onTreeClick;

    // DOM event listeners
    bindEl('.ev2-tabs', 'click', handlers.tabClick);
    bindEl('.ev2-language-bar', 'click', handlers.langClick);
    bindEl('#ev2-save-btn', 'click', handlers.saveClick);
    bindEl('#ev2-discard-btn', 'click', handlers.discardClick);
    bindEl('#ev2-undo-btn', 'click', handlers.undoClick);
    bindEl('#ev2-redo-btn', 'click', handlers.redoClick);
    bindEl('#ev2-save-topbar-btn', 'click', handlers.topbarSave);
    bindEl('#ev2-tab-content', 'click', handlers.treeClick);

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
    unbindEl('#ev2-tab-content', 'click', handlers.treeClick);

    events.off('selection:changed', handlers.selectionChanged);
    events.off('changes:count', handlers.changesCount);
    events.off('changes:saved', handlers.changesSaved);
    events.off('changes:error', handlers.changesError);
    events.off('changes:undo-state', handlers.undoState);
    events.off('sidebar:switch-tab', handlers.switchTab);

    selectedEl = null;
    activeTab = 'content';
}
