/**
 * Structure tab: the page as a table of contents. Sections by name with what
 * is inside described in words; open one to see its titles, texts, buttons
 * and photos. Move, duplicate, hide on mobile, remove; "+ Add section" after
 * any section; drag a section by its handle to place it elsewhere (every
 * language, one checkpoint — the move-section verb with `before`).
 */
import { events } from '../lib/events.js';
import { getCssSelector } from '../lib/dom.js';
import { moveSection, canMoveSection, duplicateSection, removeSection, placeSection } from '../lib/structural.js';
import { insertAfterSection } from './section-inserter.js';
import { ROLE_LABELS, sectionOutline, describeSection } from '../lib/content-model.js';

const config = () => window.EDITOR_CONFIG || {};
const HIDE_CLASS = 'max-md:hidden';
const open = new Set();
let query = '';
let dragName = null;

const SVG = (d, fill = false) => `<svg viewBox="0 0 24 24" ${fill ? 'fill="currentColor"' : 'fill="none" stroke="currentColor" stroke-width="2"'} aria-hidden="true">${d}</svg>`;
const ICONS = {
    grip: SVG('<circle cx="9" cy="6" r="1.6"/><circle cx="15" cy="6" r="1.6"/><circle cx="9" cy="12" r="1.6"/><circle cx="15" cy="12" r="1.6"/><circle cx="9" cy="18" r="1.6"/><circle cx="15" cy="18" r="1.6"/>', true),
    chev: SVG('<path d="m9 6 6 6-6 6"/>'),
    section: SVG('<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18"/>'),
    up: SVG('<path d="M12 19V5M5 12l7-7 7 7"/>'),
    down: SVG('<path d="M12 5v14M5 12l7 7 7-7"/>'),
    copy: SVG('<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/>'),
    eye: SVG('<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>'),
    eyeOff: SVG('<path d="M3 3l18 18"/><path d="M10.6 5.1A10 10 0 0 1 12 5c6 0 10 7 10 7a17 17 0 0 1-3.2 4M6.6 6.6C3.9 8.4 2 12 2 12s4 7 10 7a9.6 9.6 0 0 0 5.4-1.6"/>'),
    trash: SVG('<path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14"/>'),
    search: SVG('<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>'),
    item: {
        eyebrow: SVG('<path d="M4 8h16"/><path d="M4 14h9" opacity=".5"/>'),
        heading: SVG('<path d="M6 4v16M18 4v16M6 12h12"/>'),
        text: SVG('<path d="M4 6h16M4 12h16M4 18h10"/>'),
        button: SVG('<rect x="3" y="7" width="18" height="10" rx="2"/><path d="M8 12h8"/>'),
        link: SVG('<path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1"/><path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1"/>'),
        image: SVG('<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m21 16-5-5-9 9"/>'),
        component: SVG('<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 12h18"/>'),
    },
};

function esc(s) { return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
function label(name) { const s = (name || '').replace(/[-_]+/g, ' ').trim(); return s.charAt(0).toUpperCase() + s.slice(1); }
function plain(el) { return (el.textContent || '').replace(/\s+/g, ' ').trim(); }
function sections() { return [...document.querySelectorAll('.editor-v2-content [data-section]')]; }

function matches(section) {
    if (!query) return true;
    const q = query.toLowerCase();
    return label(section.dataset.section).toLowerCase().includes(q) || plain(section).toLowerCase().includes(q);
}

function select(el) {
    events.emit('selection:request', el);
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function toggleHidden(section) {
    const oldValue = section.getAttribute('class') || '';
    const classes = oldValue.split(/\s+/).filter(Boolean);
    const next = classes.includes(HIDE_CLASS) ? classes.filter(c => c !== HIDE_CLASS) : [...classes, HIDE_CLASS];
    const value = next.join(' ');
    section.setAttribute('class', value);
    events.emit('change:classes', { type: 'classes', selector: getCssSelector(section) || '', value, oldValue });
}

function kidsHtml(section, selected) {
    const { items, components } = sectionOutline(section);
    const rows = components.map((c, i) => `<button type="button" class="ev2-sp-kid" data-comp="${i}">
            <span class="ev2-sp-kicon">${ICONS.item.component}</span><span class="ev2-sp-role">${c.kind === 'gallery' ? 'Gallery' : 'Slider'}</span>
            <span class="ev2-sp-val">${c.count} ${c.kind === 'gallery' ? 'photos' : 'slides'}</span></button>`);
    items.forEach(({ el, role }, i) => {
        const isSel = selected && (el === selected || el.contains(selected));
        const value = role === 'image' ? (el.getAttribute('alt') || (el.getAttribute('src') || '').split('/').pop()) : plain(el);
        rows.push(`<button type="button" class="ev2-sp-kid ${isSel ? 'is-sel' : ''}" data-item="${i}">
            <span class="ev2-sp-kicon">${ICONS.item[role] || ICONS.item.text}</span><span class="ev2-sp-role">${esc(ROLE_LABELS[role])}</span>
            ${role === 'image' ? `<img class="ev2-sp-thumb" src="${esc(el.getAttribute('src') || '')}" alt="">` : ''}
            <span class="ev2-sp-val">${esc(value)}</span></button>`);
    });
    return { html: rows.join('') || '<span class="ev2-sp-empty">Nothing to edit inside</span>', items, components };
}

function nextSectionName(name) {
    const all = sections();
    const i = all.findIndex(s => s.dataset.section === name);
    return i >= 0 && i < all.length - 1 ? all[i + 1].dataset.section : null;
}

/** Where a drop on `row` at clientY places the dragged section: the name it goes before (null = end). */
function dropBefore(row, clientY) {
    const rect = row.getBoundingClientRect();
    return clientY < rect.top + rect.height / 2 ? row.dataset.section : nextSectionName(row.dataset.section);
}

function bindDrag(row) {
    const name = row.dataset.section;
    row.addEventListener('dragstart', (e) => {
        dragName = name;
        e.dataTransfer?.setData('text/plain', name);
        if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move';
        row.classList.add('is-dragging');
    });
    row.addEventListener('dragend', () => {
        dragName = null;
        document.querySelectorAll('.ev2-sp-row.is-dragging, .ev2-sp-row.is-drop-before, .ev2-sp-row.is-drop-after')
            .forEach(r => r.classList.remove('is-dragging', 'is-drop-before', 'is-drop-after'));
    });
    row.addEventListener('dragover', (e) => {
        if (!dragName) return;
        e.preventDefault();
        const rect = row.getBoundingClientRect();
        const before = e.clientY < rect.top + rect.height / 2;
        row.classList.toggle('is-drop-before', before);
        row.classList.toggle('is-drop-after', !before);
    });
    row.addEventListener('dragleave', () => row.classList.remove('is-drop-before', 'is-drop-after'));
    row.addEventListener('drop', (e) => {
        e.preventDefault();
        row.classList.remove('is-drop-before', 'is-drop-after');
        const moving = dragName || e.dataTransfer?.getData('text/plain');
        dragName = null;
        if (!moving) return;
        const before = dropBefore(row, e.clientY);
        if (before === moving || nextSectionName(moving) === before) return;      // already there
        placeSection(moving, before);
    });
}

/** Render the Structure tab into `container`; `selected` is the editor's current selection (or null). */
export function renderStructurePanel(container, selected) {
    const all = sections();
    const current = selected?.closest?.('[data-section]');
    if (current) open.add(current.dataset.section);
    const title = config().pageTitle || 'This page';
    container.innerHTML = `<div class="ev2-sp">
        <div class="ev2-sp-head">
            <div class="ev2-sp-row1"><h2>${esc(title)}</h2><span class="ev2-sp-count">${all.length} ${all.length === 1 ? 'section' : 'sections'}</span></div>
            <label class="ev2-sp-search">${ICONS.search}<input class="ev2-sp-find" type="search" placeholder="Find a section, title or button…" aria-label="Find on this page" value="${esc(query)}"></label>
        </div>
        <div class="ev2-sp-tree" role="tree"></div>
        <p class="ev2-sp-foot">Drag a section by its handle to move it. Moving, duplicating and removing change every language, and Undo covers them.</p>
    </div>`;
    const tree = container.querySelector('.ev2-sp-tree');
    const parts = [];
    if (document.querySelector('header:not(.editor-v2-content header)')) {
        parts.push(`<div class="ev2-sp-global" data-global="header"><span class="ev2-sp-kicon">${ICONS.section}</span>Header<span>shared by all pages</span></div>`);
    }
    const visible = all.filter(matches);
    for (const section of visible) {
        const name = section.dataset.section;
        const isOpen = open.has(name) || !!query;
        const hidden = section.classList.contains(HIDE_CLASS);
        const isSel = selected === section;
        parts.push(`<div class="ev2-sp-item" data-section="${esc(name)}">
            <div class="ev2-sp-row ${isSel ? 'is-sel' : ''}" data-section="${esc(name)}" draggable="true" tabindex="0" role="treeitem" aria-expanded="${isOpen}">
                <span class="ev2-sp-grip" title="Drag to move">${ICONS.grip}</span>
                <button type="button" class="ev2-sp-chev" data-tool="toggle" aria-label="${isOpen ? 'Close' : 'Open'}">${ICONS.chev}</button>
                <span class="ev2-sp-kicon is-section">${ICONS.section}</span>
                <span class="ev2-sp-main"><span class="ev2-sp-name">${esc(label(name))}${hidden ? '<span class="ev2-sp-hidden">hidden on mobile</span>' : ''}</span>
                    <span class="ev2-sp-desc">${esc(describeSection(section))}</span></span>
                <span class="ev2-sp-tools">
                    <button type="button" data-tool="up" title="Move up" ${canMoveSection(section, 'up') ? '' : 'disabled'}>${ICONS.up}</button>
                    <button type="button" data-tool="down" title="Move down" ${canMoveSection(section, 'down') ? '' : 'disabled'}>${ICONS.down}</button>
                    <button type="button" data-tool="duplicate" title="Duplicate">${ICONS.copy}</button>
                    <button type="button" data-tool="hide" title="${hidden ? 'Show on mobile' : 'Hide on mobile'}">${hidden ? ICONS.eyeOff : ICONS.eye}</button>
                    <button type="button" data-tool="remove" title="Remove">${ICONS.trash}</button>
                </span>
            </div>
            ${isOpen ? '<div class="ev2-sp-kids"></div>' : ''}
        </div>`);
        if (!query) parts.push(`<div class="ev2-sp-insert"><button type="button" data-insert="${esc(name)}">+ Add section</button></div>`);
    }
    if (!visible.length) parts.push('<p class="ev2-sp-foot">Nothing on this page matches.</p>');
    if (document.querySelector('footer:not(.editor-v2-content footer)')) {
        parts.push(`<div class="ev2-sp-global" data-global="footer"><span class="ev2-sp-kicon">${ICONS.section}</span>Footer<span>shared by all pages</span></div>`);
    }
    tree.innerHTML = parts.join('');

    for (const item of tree.querySelectorAll('.ev2-sp-item')) {
        const name = item.dataset.section;
        const section = all.find(s => s.dataset.section === name);
        const row = item.querySelector('.ev2-sp-row');
        const kids = item.querySelector('.ev2-sp-kids');
        if (kids) {
            const { html, items, components } = kidsHtml(section, selected);
            kids.innerHTML = html;
            kids.querySelectorAll('[data-item]').forEach(b => b.addEventListener('click', () => select(items[+b.dataset.item].el)));
            kids.querySelectorAll('[data-comp]').forEach(b => b.addEventListener('click', () => select(components[+b.dataset.comp].root)));
        }
        row.addEventListener('click', (e) => {
            const tool = e.target.closest('[data-tool]')?.dataset.tool;
            if (tool === 'toggle') {
                if (open.has(name)) open.delete(name); else open.add(name);
                renderStructurePanel(container, selected);
            } else if (tool === 'up' || tool === 'down') moveSection(name, tool);
            else if (tool === 'duplicate') duplicateSection(name);
            else if (tool === 'remove') removeSection(name);
            else if (tool === 'hide') { toggleHidden(section); renderStructurePanel(container, selected); }
            else if (!tool) { open.add(name); select(section); }
        });
        row.addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target === row) { open.add(name); select(section); } });
        row.addEventListener('mouseenter', () => section.classList.add('ev2-cp-hot'));
        row.addEventListener('mouseleave', () => section.classList.remove('ev2-cp-hot'));
        bindDrag(row);
    }
    tree.querySelectorAll('[data-insert]').forEach(b => b.addEventListener('click', () => insertAfterSection(b.dataset.insert)));
    const find = container.querySelector('.ev2-sp-find');
    find.addEventListener('input', () => {
        query = find.value.trim();
        const pos = find.selectionStart;
        renderStructurePanel(container, selected);
        const again = container.querySelector('.ev2-sp-find');
        again.focus();
        try { again.setSelectionRange(pos, pos); } catch (_) { /* type=search may refuse */ }
    });
}
