import { events } from '../lib/events.js';
import { $, getContentWrapper, getAncestors, getTagLabel, isEditable, getElementId } from '../lib/dom.js';

let selected = null;
let labelEl = null;
const handlers = {};

// Hover highlighting

function onMouseOver(e) {
    if (!isEditable(e.target)) return;
    e.target.classList.add('ev2-hover-outline');
}

function onMouseOut(e) {
    e.target.classList.remove('ev2-hover-outline');
}

// Label badge

function removeLabel() {
    if (labelEl) {
        labelEl.remove();
        labelEl = null;
    }
}

function positionLabel(el) {
    if (!labelEl) return;
    const rect = el.getBoundingClientRect();
    labelEl.style.position = 'fixed';
    labelEl.style.left = `${rect.left}px`;
    labelEl.style.top = `${Math.max(0, rect.top - 24)}px`;
    labelEl.style.zIndex = '100001';
}

function showLabel(el) {
    removeLabel();
    labelEl = document.createElement('div');
    labelEl.className = 'ev2-element-label';
    labelEl.textContent = getTagLabel(el);
    document.body.appendChild(labelEl);
    positionLabel(el);
}

// Breadcrumbs

function updateBreadcrumbs(el) {
    const container = $('#ev2-breadcrumbs');
    if (!container) return;

    if (!el) {
        container.innerHTML = '';
        events.emit('selection:breadcrumbs', []);
        return;
    }

    const ancestors = getAncestors(el).reverse();
    const chain = [...ancestors, el];
    const crumbs = chain.map(node => ({ el: node, label: getTagLabel(node) }));

    container.innerHTML = crumbs.map((crumb, i) => {
        const sep = i < crumbs.length - 1 ? ' <span class="ev2-breadcrumb-sep">\u203a</span> ' : '';
        const active = i === crumbs.length - 1 ? ' ev2-breadcrumb-active' : '';
        const id = getElementId(crumb.el);
        return `<span class="ev2-breadcrumb${active}" data-crumb-id="${id}">${crumb.label}</span>${sep}`;
    }).join('');

    events.emit('selection:breadcrumbs', crumbs);
}

// Core selection

function clearSelection() {
    if (selected) selected.classList.remove('ev2-selected');
    selected = null;
    removeLabel();
    updateBreadcrumbs(null);
    events.emit('selection:changed', null);
}

export function select(el) {
    if (!el || !isEditable(el)) return;
    if (selected === el) return;
    if (selected) selected.classList.remove('ev2-selected');

    selected = el;
    el.classList.remove('ev2-hover-outline');
    el.classList.add('ev2-selected');
    showLabel(el);
    updateBreadcrumbs(el);
    events.emit('selection:changed', el);
}

export function getSelected() {
    return selected;
}

// Click handling

function onContentClick(e) {
    const wrapper = getContentWrapper();
    if (!wrapper) return;

    if (e.target === wrapper) {
        clearSelection();
        return;
    }

    // Ignore clicks on non-editable elements (admin toolbar, editor UI)
    if (!isEditable(e.target)) return;

    const target = e.target.closest('[data-element-id], [data-section]') || e.target;
    if (wrapper.contains(target) && target !== wrapper) {
        e.preventDefault();
        select(target);
    }
}

function onEditorUiClick(e) {
    e.stopPropagation();
}

// Breadcrumb clicks

function onBreadcrumbClick(e) {
    const crumb = e.target.closest('.ev2-breadcrumb');
    if (!crumb) return;
    const id = crumb.dataset.crumbId;
    if (!id) return;

    const wrapper = getContentWrapper();
    if (!wrapper) return;

    const target = wrapper.querySelector(`[data-element-id="${id}"]`)
        || document.getElementById(id);
    if (target) select(target);
}

// Reposition label on scroll/resize

function onReposition() {
    if (selected && labelEl) positionLabel(selected);
}

// Lifecycle

export function init() {
    const wrapper = getContentWrapper();
    if (!wrapper) return;

    const sidebar = $('#ev2-sidebar');
    const topbar = $('#ev2-topbar');
    const breadcrumbs = $('#ev2-breadcrumbs');

    handlers.mouseover = onMouseOver;
    handlers.mouseout = onMouseOut;
    wrapper.addEventListener('mouseover', handlers.mouseover);
    wrapper.addEventListener('mouseout', handlers.mouseout);

    handlers.contentClick = onContentClick;
    wrapper.addEventListener('click', handlers.contentClick);

    handlers.uiClick = onEditorUiClick;
    if (sidebar) sidebar.addEventListener('click', handlers.uiClick);
    if (topbar) topbar.addEventListener('click', handlers.uiClick);

    if (breadcrumbs) {
        handlers.breadcrumbClick = onBreadcrumbClick;
        breadcrumbs.addEventListener('click', handlers.breadcrumbClick);
    }

    handlers.reposition = onReposition;
    window.addEventListener('scroll', handlers.reposition, true);
    window.addEventListener('resize', handlers.reposition);

    // Allow other modules to request element selection
    handlers.selectionRequest = (el) => select(el);
    events.on('selection:request', handlers.selectionRequest);
}

export function destroy() {
    const wrapper = getContentWrapper();
    const sidebar = $('#ev2-sidebar');
    const topbar = $('#ev2-topbar');
    const breadcrumbs = $('#ev2-breadcrumbs');

    if (wrapper) {
        wrapper.removeEventListener('mouseover', handlers.mouseover);
        wrapper.removeEventListener('mouseout', handlers.mouseout);
        wrapper.removeEventListener('click', handlers.contentClick);
    }
    if (sidebar) sidebar.removeEventListener('click', handlers.uiClick);
    if (topbar) topbar.removeEventListener('click', handlers.uiClick);
    if (breadcrumbs) breadcrumbs.removeEventListener('click', handlers.breadcrumbClick);
    window.removeEventListener('scroll', handlers.reposition, true);
    window.removeEventListener('resize', handlers.reposition);
    events.off('selection:request', handlers.selectionRequest);

    clearSelection();
}
