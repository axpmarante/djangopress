/**
 * Right-click menu: only about the thing you right-clicked.
 *
 * Every menu has the same shape — the usual actions for that kind of thing,
 * "Ask AI…", one row of move / duplicate / remove, and a "More" made for that
 * kind (button, link, text, heading, image, slider, gallery, section, block).
 * Nothing about the section unless the section itself was right-clicked.
 * Items that need a panel (link, alt text, slides) open the sidebar on it.
 *
 * Menu data: items are {label, icon, hint, cls, disabled, action, children},
 * {row: [{title, icon, cls, on, disabled, action}]}, null (a separator) or
 * false (left out).
 */
import { events } from '../lib/events.js';
import { $, getContentWrapper, getCssSelector, isRuntimeClass, isRuntimeInjected } from '../lib/dom.js';
import { insertBefore, insertAfterSection } from './section-inserter.js';
import {
    duplicateElement, moveElement, duplicateSection, moveSection, removeElement, removeSection,
    canMove, canMoveSection, retagElement, renameSection,
} from '../lib/structural.js';
import { findComponent, itemsOf } from '../lib/components.js';
import { elementType } from '../lib/element-types.js';
import { itemRole, hasFormatting } from '../lib/content-model.js';
import { setText, setAttr, setClasses, setFocusPoint, setNewTab, opensInNewTab, focusPointOf } from '../lib/edits.js';
import { confirmDialog, promptDialog } from '../lib/dialog.js';
import { api } from '../lib/api.js';
import { makeClip } from '../lib/section-clip.js';

const handlers = {};
let menu;

const config = () => window.EDITOR_CONFIG || {};
function esc(s) { return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
function plain(el) { return (el.textContent || '').replace(/\s+/g, ' ').trim(); }
function short(text, n = 26) { return text.length > n ? `${text.slice(0, n - 1)}…` : text; }
function label(name) { const s = (name || '').replace(/[-_]+/g, ' ').trim(); return s.charAt(0).toUpperCase() + s.slice(1); }

function copy(text, done = 'Copied') {
    return Promise.resolve()
        .then(() => navigator.clipboard.writeText(text))
        .then(() => events.emit('toast:show', { text: done }))
        .catch(() => events.emit('toast:show', { text: "Couldn't copy" }));
}

/** Select `el` and open a sidebar tab on it; `then(container)` runs once the tab has rendered. */
function openInPanel(el, tab, then) {
    events.emit('selection:request', el);
    events.emit('sidebar:switch-tab', tab);
    if (then) setTimeout(() => { const c = document.getElementById('ev2-tab-content'); if (c) then(c); }, 80);
}

function elementRow(el, selector) {
    return { row: [
        { title: 'Move up', icon: '↑', disabled: !canMove(el, 'up'), action: () => moveElement(selector, 'up') },
        { title: 'Move down', icon: '↓', disabled: !canMove(el, 'down'), action: () => moveElement(selector, 'down') },
        { title: 'Duplicate', icon: '⧉', action: () => duplicateElement(selector) },
        { title: 'Remove', icon: '✕', cls: 'danger', action: () => removeElement(selector) },
    ] };
}

const copyHtml = (el) => ({ label: 'Copy HTML', icon: '</>', action: () => copy(el.outerHTML) });

/** The most common class list among the page's buttons (links that look like buttons). */
function pageButtonClasses(except) {
    const counts = new Map();
    for (const a of document.querySelectorAll('.editor-v2-content a, .editor-v2-content button')) {
        if (a === except || isRuntimeInjected(a) || elementType(a) !== 'button') continue;
        const cls = [...a.classList].filter(c => !isRuntimeClass(c)).join(' ');
        if (cls) counts.set(cls, (counts.get(cls) || 0) + 1);
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] || null;
}

function retag(el, tag) {
    const selector = getCssSelector(el);
    const others = [...document.querySelectorAll('.editor-v2-content h1')]
        .filter(h => h !== el && !h.closest('.splide__slide--clone') && !isRuntimeInjected(h));
    if (tag !== 'h1' || !others.length) return retagElement(selector, tag);
    return confirmDialog({ title: 'Make this a second H1?', confirmLabel: 'Make it H1',
        message: 'This page already has an H1. Search engines expect one per page.' })
        .then(ok => (ok ? retagElement(selector, tag) : null));
}

async function describeMissingAlts(images) {
    let done = 0;
    for (const img of images) {
        events.emit('toast:show', { text: `Describing photo ${done + 1} of ${images.length}…` });
        try {
            const params = { page_id: config().pageId, selector: getCssSelector(img), src: img.getAttribute('src') };
            if (config().contentTypeId) { params.content_type_id = config().contentTypeId; params.object_id = config().objectId; }
            const res = await api.post('/describe-image/', params);
            if (res.success && res.current) { setAttr(img, 'alt', res.current); done += 1; }
        } catch (_) { /* go on with the next photo */ }
    }
    events.emit('toast:show', { text: `Described ${done} of ${images.length} photos. Save to keep them.` });
}

function kindOf(el) {
    if (el.hasAttribute('data-section')) return { kind: 'section' };
    const comp = findComponent(el);
    const role = itemRole(el);
    if (comp && (el === comp.root || !role)) return { kind: comp.kind === 'gallery' ? 'gallery' : 'slider', comp };
    if (role === 'eyebrow') return { kind: 'text' };
    return { kind: role || 'block' };
}

function sectionMenu(el, ai) {
    const name = el.getAttribute('data-section');
    const hidden = el.classList.contains('max-md:hidden');
    const own = [...el.classList].filter(c => !isRuntimeClass(c));
    return { title: `Section · ${label(name)}`, items: [
        ai && { label: 'Ask AI about this section…', icon: '✦', cls: 'ai', action: () => events.emit('context:ai-refine', { section: name }) },
        { label: 'Copy section', icon: '⎘', hint: 'Paste it on any DjangoPress site',
          action: async () => copy(await makeClip(el), 'Section copied. Paste it with Add a section → Paste, on this site or another.') },
        { label: 'Add section above', icon: '↥', action: () => insertBefore(name) },
        { label: 'Add section below', icon: '↧', action: () => insertAfterSection(name) },
        { row: [
            { title: 'Move up', icon: '↑', disabled: !canMoveSection(el, 'up'), action: () => moveSection(name, 'up') },
            { title: 'Move down', icon: '↓', disabled: !canMoveSection(el, 'down'), action: () => moveSection(name, 'down') },
            { title: 'Duplicate', icon: '⧉', action: () => duplicateSection(name) },
            { title: hidden ? 'Show on mobile' : 'Hide on mobile', icon: '◐', on: hidden,
              action: () => setClasses(el, hidden ? own.filter(c => c !== 'max-md:hidden') : [...own, 'max-md:hidden']) },
        ] },
        null,
        { label: 'More', icon: '⋯', children: [
            { label: 'Fix section images', icon: '⬡', action: () => events.emit('process-images:open', { section: name }) },
            { label: 'Background…', icon: '▤', action: () => openInPanel(el, 'design') },
            { label: 'Rename section…', icon: '✎', action: async () => {
                const next = await promptDialog({ title: 'Rename section', value: label(name), confirmLabel: 'Rename',
                    message: 'Used in links to this section (#name). Changes in every language.' });
                if (next && next.trim() && next.trim() !== label(name)) renameSection(name, next.trim());
            } },
            copyHtml(el),
        ] },
        { label: 'Remove section', icon: '✕', cls: 'danger', action: () => removeSection(name) },
    ] };
}

/** {title, items} for the thing at `el`. */
export function menuFor(el) {
    const ai = !!config().aiEnabled;
    const { kind, comp } = kindOf(el);
    if (kind === 'section') return sectionMenu(el, ai);

    const section = el.closest('[data-section]');
    const name = section?.getAttribute('data-section');
    const target = comp && (kind === 'slider' || kind === 'gallery') ? comp.root : el;
    const selector = getCssSelector(target);
    const row = !!selector && elementRow(target, selector);
    const ask = ai && !!section && { label: 'Ask AI…', icon: '✦', cls: 'ai',
                                     action: () => events.emit('context:ai-refine', { section: name, selector }) };

    if (kind === 'slider' || kind === 'gallery') {
        const n = itemsOf(comp).length;
        const addButton = (c) => c.querySelector('[data-act="add-text"], [data-act="add-images"]')?.click();
        if (kind === 'slider') {
            return { title: `Slider · ${n} slides`, items: [
                { label: 'Edit slides…', icon: '☰', action: () => openInPanel(target, 'content') },
                { label: 'Add a slide', icon: '+', action: () => openInPanel(target, 'content', addButton) },
                ask, row, null,
                { label: 'More', icon: '⋯', children: [
                    { label: 'Slider settings…', icon: '⚙', action: () => openInPanel(target, 'content', (c) => {
                        const d = c.querySelector('details.ev2-comp-settings');
                        if (d) { d.open = true; d.scrollIntoView({ block: 'nearest' }); }
                    }) },
                    copyHtml(target),
                ] },
            ] };
        }
        const missing = [...target.querySelectorAll('img')]
            .filter(i => !(i.getAttribute('alt') || '').trim() && !i.closest('.splide__slide--clone'));
        return { title: `Gallery · ${n} photos`, items: [
            { label: 'Add photos…', icon: '+', action: () => openInPanel(target, 'content', addButton) },
            { label: 'Edit photos…', icon: '☰', action: () => openInPanel(target, 'content') },
            ask, row, null,
            { label: 'More', icon: '⋯', children: [
                ai && { label: 'Describe missing alts', icon: '✦', hint: missing.length ? String(missing.length) : '',
                        disabled: !missing.length, action: () => describeMissingAlts(missing) },
                copyHtml(target),
            ] },
        ] };
    }

    if (kind === 'button' || kind === 'link') {
        const href = el.getAttribute('href') || '';
        const isLink = el.tagName === 'A';
        const newTab = opensInNewTab(el);
        const buttonClasses = kind === 'link' ? pageButtonClasses(el) : null;
        return { title: `${kind === 'button' ? 'Button' : 'Link'} · ${short(plain(el))}`, items: [
            { label: kind === 'button' ? 'Edit label' : 'Edit text', icon: '✎', hint: 'Dbl-click',
              action: () => events.emit('inline-edit:trigger', { element: el }) },
            isLink && { label: 'Change link…', icon: '↗',
                        action: () => openInPanel(el, 'content', (c) => c.querySelector('.ev2-cp-kinds .is-on')?.focus()) },
            ask, row, null,
            { label: 'More', icon: '⋯', children: [
                isLink && { label: 'Open in a new tab', icon: '⧉', hint: newTab ? 'on' : 'off', action: () => setNewTab(el, !newTab) },
                !!href && { label: 'Copy link', icon: '⎘', action: () => copy(href) },
                kind === 'button'
                    ? { label: 'Button style…', icon: '◑', action: () => openInPanel(el, 'design') }
                    : { label: 'Turn into a button', icon: '▭', disabled: !buttonClasses,
                        action: () => setClasses(el, buttonClasses.split(' ')) },
                copyHtml(el),
            ] },
        ] };
    }

    if (kind === 'heading' || kind === 'text') {
        const tag = el.tagName.toLowerCase();
        const levels = kind === 'heading'
            ? { row: [['h1', 'H1'], ['h2', 'H2'], ['h3', 'H3'], ['h4', 'H4'], ['p', 'Text']].map(([t, l]) =>
                ({ title: l, icon: l, on: t === tag, disabled: t === tag, action: () => retag(el, t) })) }
            : /^h[1-6]$|^p$/.test(tag) && { label: 'Make it a heading', icon: 'H',
                children: ['h2', 'h3', 'h4'].map(t => ({ label: t.toUpperCase(), action: () => retag(el, t) })) };
        return { title: kind === 'heading' ? `Heading · ${tag.toUpperCase()}` : 'Text', items: [
            { label: 'Edit text', icon: '✎', hint: 'Dbl-click', action: () => events.emit('inline-edit:trigger', { element: el }) },
            ask, row, null,
            { label: 'More', icon: '⋯', children: [
                levels,
                { label: 'Copy text', icon: '⎘', action: () => copy(plain(el)) },
                kind === 'text' && { label: 'Clear formatting', icon: '⌫', disabled: !hasFormatting(el),
                                     action: () => setText(el, plain(el), 'text') },
                copyHtml(el),
            ] },
        ] };
    }

    if (kind === 'image') {
        const src = el.getAttribute('src') || '';
        const file = decodeURIComponent((src.split('/').pop() || '').split('?')[0]);
        const focus = focusPointOf(el);
        return { title: `Image · ${short(file, 22) || 'photo'}`, items: [
            { label: 'Replace image…', icon: '⇄',
              action: () => { events.emit('selection:request', el); setTimeout(() => events.emit('image-picker:open', {}), 0); } },
            { label: 'Edit alt text', icon: '✎', action: () => openInPanel(el, 'content', (c) => c.querySelector('#ev2-cp-alt')?.focus()) },
            ask, row, null,
            { label: 'More', icon: '⋯', children: [
                ai && { label: 'Describe the photo', icon: '✦',
                        action: () => openInPanel(el, 'content', (c) => c.querySelector('[data-action="describe"]')?.click()) },
                { label: 'Focus point', icon: '◎', children: [['top', 'Top'], ['center', 'Center'], ['bottom', 'Bottom'], ['left', 'Left'], ['right', 'Right']]
                    .map(([p, l]) => ({ label: l, hint: p === focus ? '✓' : '', action: () => setFocusPoint(el, p) })) },
                !!src && { label: 'Open original', icon: '↗', action: () => window.open(src, '_blank', 'noopener') },
                !!src && { label: 'Copy image address', icon: '⎘', action: () => copy(src) },
                copyHtml(el),
            ] },
        ] };
    }

    return { title: 'Block', items: [ask, row, null, { label: 'More', icon: '⋯', children: [copyHtml(el)] }] };
}

// ── Rendering ──

/** Drop left-out items (false) and separators that would be first, last or doubled. */
function tidy(items) {
    const kept = (items || []).filter(i => i !== false && i !== undefined);
    return kept.filter((item, i) => item !== null
        || (i > 0 && i < kept.length - 1 && kept[i - 1] !== null));
}

function buildList(items, container) {
    for (const item of tidy(items)) {
        if (item === null) { container.insertAdjacentHTML('beforeend', '<div class="ev2-context-sep"></div>'); continue; }
        if (item.row) {
            const row = document.createElement('div');
            row.className = 'ev2-context-row';
            for (const b of item.row) {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = `ev2-context-rowbtn${b.cls ? ` is-${b.cls}` : ''}${b.on ? ' is-on' : ''}`;
                btn.title = b.title;
                btn.setAttribute('aria-label', b.title);
                btn.textContent = b.icon;
                btn.disabled = !!b.disabled;
                btn.addEventListener('click', (e) => { e.stopPropagation(); hideMenu(); b.action(); });
                row.appendChild(btn);
            }
            container.appendChild(row);
            continue;
        }
        const row = document.createElement('div');
        row.className = `ev2-context-item${item.cls ? ` ev2-context-item--${item.cls}` : ''}`
            + `${item.disabled ? ' ev2-context-item--disabled' : ''}${item.children ? ' has-sub' : ''}`;
        row.tabIndex = 0;
        row.setAttribute('role', 'menuitem');
        row.innerHTML = `<span class="ev2-context-icon">${esc(item.icon || '')}</span><span class="ev2-context-label">${esc(item.label)}</span>`
            + (item.hint ? `<span class="ev2-context-hint">${esc(item.hint)}</span>` : '')
            + (item.children ? '<span class="ev2-context-chev">›</span>' : '');
        if (item.children) {
            const sub = document.createElement('div');
            sub.className = 'ev2-context-menu ev2-context-sub';
            buildList(item.children, sub);
            row.appendChild(sub);
            const open = () => {
                row.parentElement.querySelectorAll(':scope > .has-sub.is-open').forEach(o => { if (o !== row) o.classList.remove('is-open'); });
                row.classList.add('is-open');
                placeSub(sub);
            };
            row.addEventListener('mouseenter', open);
            row.addEventListener('click', (e) => { e.stopPropagation(); open(); });
            row.addEventListener('keydown', (e) => {
                if (e.key === 'ArrowRight' || e.key === 'Enter') { open(); sub.querySelector('.ev2-context-item, .ev2-context-rowbtn')?.focus(); }
            });
        } else {
            row.addEventListener('mouseenter', () => row.parentElement.querySelectorAll(':scope > .has-sub.is-open').forEach(o => o.classList.remove('is-open')));
            if (!item.disabled) {
                const run = (e) => { e.stopPropagation(); hideMenu(); item.action(); };
                row.addEventListener('click', run);
                row.addEventListener('keydown', (e) => { if (e.key === 'Enter') run(e); });
            }
        }
        container.appendChild(row);
    }
}

function placeSub(sub) {
    sub.style.left = '100%';
    sub.style.right = 'auto';
    sub.style.top = '-6px';
    if (sub.getBoundingClientRect().right > window.innerWidth - 4) { sub.style.left = 'auto'; sub.style.right = '100%'; }
    const r = sub.getBoundingClientRect();
    if (r.bottom > window.innerHeight - 4) sub.style.top = `${-6 - (r.bottom - window.innerHeight + 4)}px`;
}

function showMenu(x, y, { title, items }) {
    menu.innerHTML = `<div class="ev2-context-head">${esc(title)}</div>`;
    buildList(items, menu);
    menu.classList.remove('hidden');
    const { width, height } = menu.getBoundingClientRect();
    const left = x + width > window.innerWidth - 4 ? x - width : x;
    const top = y + height > window.innerHeight - 4 ? y - height : y;
    menu.style.left = `${Math.min(Math.max(4, left), Math.max(4, window.innerWidth - width - 4))}px`;
    menu.style.top = `${Math.min(Math.max(4, top), Math.max(4, window.innerHeight - height - 4))}px`;
}

function hideMenu() {
    if (menu) menu.classList.add('hidden');
}

function onContextMenu(e) {
    const wrapper = getContentWrapper();
    if (!wrapper?.contains(e.target) || isRuntimeInjected(e.target)) return;
    e.preventDefault();
    const el = e.target;
    events.emit('selection:request', el);
    showMenu(e.clientX, e.clientY, menuFor(el));
}

function onKeydown(e) {
    if (e.key === 'Escape') hideMenu();
}

export function init() {
    menu = $('#ev2-context-menu');
    if (!menu) return;
    menu.setAttribute('role', 'menu');
    handlers.contextmenu = onContextMenu;
    handlers.click = (e) => { if (!menu.contains(e.target)) hideMenu(); };
    handlers.keydown = onKeydown;
    handlers.scroll = hideMenu;
    document.addEventListener('contextmenu', handlers.contextmenu);
    document.addEventListener('click', handlers.click);
    document.addEventListener('keydown', handlers.keydown);
    window.addEventListener('scroll', handlers.scroll, true);
}

export function destroy() {
    document.removeEventListener('contextmenu', handlers.contextmenu);
    document.removeEventListener('click', handlers.click);
    document.removeEventListener('keydown', handlers.keydown);
    window.removeEventListener('scroll', handlers.scroll, true);
    hideMenu();
}
