/**
 * Design panel — element-aware design controls for the selected element.
 *
 * The rows come from lib/design-controls.js (per element type, from
 * lib/element-types.js). Values are read and written through
 * lib/class-model.js for the screen being edited (viewport: desktop / tablet
 * / mobile), and every change is emitted as the existing change:classes /
 * change:attribute events, so saving, checkpoints, all-language writes and
 * Undo work as before.
 */
import { events } from '../lib/events.js';
import { api } from '../lib/api.js';
import { getCssSelector, isRuntimeClass } from '../lib/dom.js';
import { DEVICES, classesOf, readValues, writeValue, writeValues } from '../lib/class-model.js';
import { elementType } from '../lib/element-types.js';
import { COMMON, PANELS, icon } from '../lib/design-controls.js';
import { composeBgImage, extractYouTubeId, hexToRgb, parseBgImage, rgbToHex, videoDisplayUrl } from '../lib/background.js';
import { alertDialog } from '../lib/dialog.js';
import { getViewport, setViewport } from './viewport.js';
import { getPendingCount, saveNow } from './changes.js';

const TYPE_NAMES = { section: 'Section', container: 'Container', button: 'Button', link: 'Link', heading: 'Heading', text: 'Text', image: 'Image', other: 'Element' };
const TYPE_ICONS = {
    section: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18"/>',
    container: '<rect x="3" y="4" width="7" height="16" rx="1"/><rect x="14" y="4" width="7" height="16" rx="1"/>',
    button: '<rect x="3" y="7" width="18" height="10" rx="5"/><path d="M8 12h8"/>',
    link: '<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/>',
    heading: '<path d="M6 4v16M18 4v16M6 12h12"/>',
    text: '<path d="M4 6h16M4 12h16M4 18h10"/>',
    image: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m21 17-5-5-9 8"/>',
    other: '<rect x="4" y="4" width="16" height="16" rx="2"/>',
};
const DEVICE_ICONS = {
    desktop: '<rect x="2" y="3" width="20" height="13" rx="2"/><path d="M8 21h8M12 16v5"/>',
    tablet: '<rect x="5" y="2" width="14" height="20" rx="2"/><path d="M12 18h.01"/>',
    mobile: '<rect x="7" y="2" width="10" height="20" rx="2"/><path d="M12 18h.01"/>',
};
const RESET_ICON = '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>';
const LARGER = { mobile: 'tablet', tablet: 'desktop' };
const NULL = '__null__';

const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const same = (a, b) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
const encode = v => (v === null || v === undefined ? NULL : typeof v === 'string' ? v : JSON.stringify(v));
const decode = s => (s === NULL ? null : /^-?\d+(\.\d+)?$|^(true|false)$/.test(s) ? JSON.parse(s) : s);

// ---- tokens -------------------------------------------------------------------

let tokens = null;
let tokensLoading = null;
export function setTokens(t) { tokens = t; }
function loadTokens() {
    if (tokens || tokensLoading) return tokensLoading;
    tokensLoading = api.get('/design-tokens/').then(t => { tokens = t; }).catch(() => {
        tokens = { colors: [{ name: 'White', value: '#FFFFFF' }, { name: 'Black', value: '#000000' }], fonts: [], spacing: { S: 40, M: 64, L: 104, XL: 152 }, buttonSizes: { S: [10, 18, 13], M: [14, 28, 15], L: [18, 36, 17] } };
    });
    return tokensLoading;
}

// ---- mount state --------------------------------------------------------------

const initialClasses = new Map();   // selector → class list when first selected (the "page as opened" state)
const initialAttrs = new Map();     // selector → {attr: value}
const moreOpen = new Set();
let mount = null;                   // { container, el, selector, type, hover }
let pendingOld = null;              // class string before a slider drag started
let subscribed = false;
let picking = null;                 // { target, container } while "Copy style from…" waits for a click
const notices = new Map();          // selector → message shown in the actions block
const similarCounts = new Map();    // "tag|classes" → { count, pages }

// What "Copy style" takes for each element type: the properties its panel shows (layout
// properties such as display stay with the element) and the raw classes of its option rows.
const KIND_PROPS = {
    fontFamily: ['fontFamily'], buttonSize: ['paddingTop', 'paddingBottom', 'paddingX', 'fontSize'],
    buttonStyle: ['bgColor', 'borderWidth', 'borderColor', 'textColor', 'textDecoration'], buttonColor: ['bgColor', 'textColor'],
    padY: ['paddingTop', 'paddingBottom'], box: ['marginTop', 'marginBottom', 'marginX', 'paddingTop', 'paddingBottom', 'paddingX'],
    focal: ['objectPosition'], textTone: ['textColor'],
};
function copyRules(type) {
    const rows = [...PANELS[type], COMMON].flatMap(g => [...g.rows, ...(g.more || [])]);
    const props = new Set(rows.flatMap(r => [...(r.prop ? [r.prop] : []), ...(KIND_PROPS[r.kind] || []), ...(r.items || []).map(i => i.prop).filter(Boolean)]));
    props.delete('display');
    const raw = new Set(rows.flatMap(r => (r.kind === 'classChoice' ? r.options.flatMap(o => o[2]) : r.kind === 'classToggles' ? r.items.flatMap(i => i[2]) : [])));
    return cls => raw.has(cls) || [...props].some(p => classesOf([cls], p).length);
}

const realList = el => Array.from(el.classList).filter(c => !isRuntimeClass(c));

function subscribe() {
    if (subscribed) return;
    subscribed = true;
    events.on('viewport:changed', () => rerender());
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape' && picking) {
            picking = null;
            document.body.classList.remove('ev2-dp-picking');
            if (mount) notices.set(mount.selector, '');
            rerender();
        }
    });
    events.on('changes:applied', change => { if (mount && change.selector === mount.selector) rerender(); });
    events.on('change:attribute', change => {   // e.g. the image picker set a new background
        if (mount && !mount.emitting && change.selector === mount.selector) rerender();
    });
}

/** The sidebar shows another tab in the shared container: stop acting on it. */
export function unmountDesignPanel() {
    mount = null;
    picking = null;
    pendingOld = null;
    document.body.classList.remove('ev2-dp-picking');
}

export function renderDesignPanel(container, el) {
    subscribe();
    if (picking && el !== picking.target) {
        const { target } = picking;
        picking = null;
        document.body.classList.remove('ev2-dp-picking');
        if (elementType(el) === elementType(target)) copyStyle(el, target);
        else notices.set(getCssSelector(target) || '', `That is a ${TYPE_NAMES[elementType(el)].toLowerCase()}; pick another ${TYPE_NAMES[elementType(target)].toLowerCase()} to copy its style.`);
        renderDesignPanel(container, target);
        events.emit('selection:request', target);
        return;
    }
    const selector = getCssSelector(el) || '';
    if (!mount || mount.el !== el) pendingOld = null;
    mount = { container, el, selector, type: elementType(el), hover: mount && mount.el === el ? mount.hover : false };
    if (!initialClasses.has(selector)) {
        initialClasses.set(selector, realList(el));
        initialAttrs.set(selector, { id: el.getAttribute('id'), href: el.getAttribute('href'), target: el.getAttribute('target'), style: el.getAttribute('style') });
    }
    if (!tokens) {
        container.innerHTML = '<p class="ev2-placeholder ev2-empty-state">Loading design options…</p>';
        loadTokens().then(() => { if (mount && mount.container === container && mount.el === el) rerender(); });
        return;
    }
    render();
}

function rerender() {
    // only while the Design tab still shows this panel (the container is shared with other tabs)
    if (!mount || !mount.container.isConnected || !mount.container.querySelector(':scope > .ev2-dp')) return;
    const scroller = mount.container.closest('.ev2-sidebar-body, .ev2-tab-content') || mount.container;
    const top = scroller.scrollTop;
    render();
    scroller.scrollTop = top;
}

// ---- reading and writing ----------------------------------------------------------

const device = () => getViewport() || 'desktop';

function read(prop, state = '', dev = device()) {
    return readValues(realList(mount.el), prop, state)[dev];
}

/** Apply a class list to the element. live = during a drag (no change event yet). */
function setClasses(list, live = false) {
    const el = mount.el;
    const old = realList(el).join(' ');
    if (live && pendingOld === null) pendingOld = old;
    const runtime = Array.from(el.classList).filter(isRuntimeClass);
    el.className = [...runtime, ...list].join(' ');
    if (live) return;
    const oldValue = pendingOld ?? old;
    pendingOld = null;
    const value = list.join(' ');
    if (value !== oldValue) events.emit('change:classes', { type: 'classes', selector: mount.selector, value, oldValue });
}

function write(prop, value, { state = '', live = false, unsetAs } = {}) {
    setClasses(writeValue(realList(mount.el), prop, device(), value, state, unsetAs === undefined ? {} : { unsetAs }), live);
}

function emitAttr(attr, value) {
    const el = mount.el;
    const oldValue = el.getAttribute(attr) || '';
    if (value) el.setAttribute(attr, value); else el.removeAttribute(attr);
    if ((value || '') !== oldValue) {
        mount.emitting = true;
        events.emit('change:attribute', { type: 'attribute', selector: mount.selector, attribute: attr, value: value || '', oldValue, tagName: el.tagName.toLowerCase() });
        mount.emitting = false;
    }
}

function emitStyle(applyFn) {
    const el = mount.el;
    const oldStyle = el.getAttribute('style') || '';
    applyFn(el.style);
    const newStyle = el.getAttribute('style') || '';
    if (oldStyle !== newStyle) {
        mount.emitting = true;
        events.emit('change:attribute', { type: 'attribute', selector: mount.selector, attribute: 'style', value: newStyle, oldValue: oldStyle, tagName: el.tagName.toLowerCase() });
        mount.emitting = false;
    }
}

/** Write a class list to another element (the section's inner container). */
function setClassesOn(el, list) {
    const selector = getCssSelector(el);
    const oldValue = realList(el).join(' ');
    const runtime = Array.from(el.classList).filter(isRuntimeClass);
    el.className = [...runtime, ...list].join(' ');
    if (selector && list.join(' ') !== oldValue) events.emit('change:classes', { type: 'classes', selector, value: list.join(' '), oldValue });
}

// changed dot and reset for one property
function propChanged(prop, state = '') {
    const dev = device();
    const now = readValues(realList(mount.el), prop, state);
    if (dev !== 'desktop') return !same(now[dev], now[LARGER[dev]]);
    return !same(now.desktop, readValues(initialClasses.get(mount.selector) || [], prop, state).desktop);
}
function resetProp(prop, state = '') {
    const dev = device();
    const list = realList(mount.el);
    if (dev !== 'desktop') {
        const now = readValues(list, prop, state);
        const values = { ...now };
        values[dev] = now[LARGER[dev]];
        if (dev === 'tablet' && same(now.mobile, now.tablet)) values.mobile = values.tablet;
        setClasses(writeValues(list, prop, values, state));
        return;
    }
    const mine = new Set(classesOf(list, prop).filter(c => stateOf(c) === state));
    const original = classesOf(initialClasses.get(mount.selector) || [], prop).filter(c => stateOf(c) === state);
    const at = list.findIndex(c => mine.has(c));
    const kept = list.filter(c => !mine.has(c));
    const insert = at < 0 ? kept.length : list.slice(0, at).filter(c => !mine.has(c)).length;
    setClasses([...kept.slice(0, insert), ...original, ...kept.slice(insert)]);
}
const stateOf = cls => (/(^|:)hover:/.test(cls) ? 'hover' : '');

// ---- section helpers ------------------------------------------------------------

function bgType() {
    const bg = parseBgImage(mount.el.style.backgroundImage);
    if (bg.url) return 'image';
    if (read('bgColor') || mount.el.style.backgroundColor) return 'color';
    return 'none';
}
function innerContainer() {
    return Array.from(mount.el.children).find(c => /(^|\s)max-w-/.test(c.className)) || null;
}
function naturalDisplay() {
    const values = readValues(realList(mount.el), 'display');
    const shown = DEVICES.map(d => values[d]).find(v => v && v !== 'hidden');
    if (shown) return shown;
    const computed = getComputedStyle(mount.el).display;
    if (computed && computed !== 'none') return computed === 'inline' ? 'inline' : computed;
    return ['A', 'SPAN', 'STRONG', 'EM', 'SMALL'].includes(mount.el.tagName) ? 'inline' : 'block';
}

// ---- rendering -------------------------------------------------------------------

const panelApi = {
    read: (prop, state) => read(prop, state),
    bgType: () => bgType(),
    innerContainer: () => innerContainer(),
    isGrid: () => /(^|\s)(inline-)?grid(\s|$)/.test(mount.el.className) || getComputedStyle(mount.el).display.includes('grid'),
};

function render() {
    const { container, el, type } = mount;
    const groups = [...PANELS[type], COMMON];
    const dev = device();
    const label = (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 42) || `<${el.tagName.toLowerCase()}>`;
    const section = el.closest('[data-section]');
    const crumbs = type === 'section'
        ? `<span>Section</span>`
        : `<button type="button" class="ev2-dp-crumb" data-select-section="1">Section · ${esc(section?.getAttribute('data-section') || '')}</button><span>›</span><span class="ev2-dp-here">${TYPE_NAMES[type]}</span>`;
    const deviceNote = dev === 'desktop' ? 'Changes apply to every screen size'
        : `Size, spacing, columns and alignment changes apply to ${dev} only`;
    container.innerHTML = `
        <div class="ev2-dp">
          <div class="ev2-dp-head">
            <div class="ev2-dp-crumbs">${crumbs}</div>
            <div class="ev2-dp-title"><span class="ev2-dp-icon">${icon(TYPE_ICONS[type], 16)}</span>
              <div><div class="ev2-dp-name">${TYPE_NAMES[type]}</div><div class="ev2-dp-sub">${esc(label)}</div></div></div>
            <div class="ev2-dp-seg ev2-dp-devices">${DEVICES.slice().reverse().map(d =>
                `<button type="button" data-device="${d}" class="${d === dev ? 'is-on' : ''}" title="${d}">${icon(DEVICE_ICONS[d])}<span>${d[0].toUpperCase() + d.slice(1)}</span></button>`).join('')}</div>
            <div class="ev2-dp-note${dev === 'desktop' ? '' : ' is-device'}">${deviceNote}</div>
          </div>
          ${groups.map(g => renderGroup(g)).join('')}
          ${renderActions()}
          <details class="ev2-dp-group" data-group="advanced"><summary>Advanced</summary><div class="ev2-dp-body">
            <span class="ev2-dp-meta">Tailwind classes. Edit them directly for anything the controls don't cover.</span>
            <textarea class="ev2-dp-classes" spellcheck="false" aria-label="CSS classes">${esc(realList(el).join(' '))}</textarea>
          </div></details>
        </div>`;
    bind(container);
    countSimilar();
}

const PLURAL = { section: 'sections', container: 'grids', button: 'buttons', link: 'links', heading: 'headings', text: 'texts', image: 'images', other: 'elements' };

function similarKey() {
    return `${mount.el.tagName.toLowerCase()}|${(initialClasses.get(mount.selector) || []).join(' ')}`;
}

function renderActions() {
    const notice = notices.get(mount.selector);
    const known = similarCounts.get(similarKey());
    const hint = known
        ? (known.count > 1 ? `${known.count} ${PLURAL[mount.type]} with this style on ${known.pages} page${known.pages === 1 ? '' : 's'} · one Undo per page reverts it`
            : 'No other element has exactly this style')
        : 'Counting similar elements…';
    return `<div class="ev2-dp-actions">
        <div class="ev2-dp-actions-line">
          <button type="button" class="ev2-dp-btn" data-act="apply-similar"${known && known.count <= 1 ? ' disabled' : ''}>Apply to all similar</button>
          <button type="button" class="ev2-dp-btn" data-act="copy-style">${picking ? 'Click an element…' : 'Copy style from…'}</button>
          <button type="button" class="ev2-dp-btn" data-act="reset-element">Reset this element</button>
        </div>
        <span class="ev2-dp-meta" data-role="similar">${hint}</span>
        ${notice ? `<p class="ev2-dp-notice">${esc(notice)}</p>` : ''}
      </div>`;
}

function countSimilar() {
    const key = similarKey();
    if (similarCounts.has(key) || !(initialClasses.get(mount.selector) || []).length) return;
    const [tag, classes] = key.split('|');
    api.get('/restyle-similar/', { tag, classes }).then(res => {
        similarCounts.set(key, { count: res.count || 0, pages: res.pages || 0 });
        if (mount && similarKey() === key) rerender();
    }).catch(() => similarCounts.set(key, { count: 0, pages: 0 }));
}

/** Take the panel's properties (and the panel's raw classes) from `source`; other classes stay. */
function copyStyle(source, target) {
    const isStyle = copyRules(elementType(target));
    const keep = realList(target).filter(c => !isStyle(c));
    const take = realList(source).filter(isStyle);
    const selector = getCssSelector(target) || '';
    const oldValue = realList(target).join(' ');
    const runtime = Array.from(target.classList).filter(isRuntimeClass);
    target.className = [...runtime, ...keep, ...take].join(' ');
    const value = [...keep, ...take].join(' ');
    if (value !== oldValue) events.emit('change:classes', { type: 'classes', selector, value, oldValue });
    notices.set(selector, `Copied the style of “${(source.textContent || source.tagName).trim().slice(0, 30)}”.`);
}

function renderGroup(g) {
    const rows = g.rows.filter(r => !r.when || r.when(panelApi));
    const more = (g.more || []).filter(r => !r.when || r.when(panelApi));
    if (!rows.length && !more.length) return '';
    const key = `${mount.selector}|${g.key}`;
    return `<details class="ev2-dp-group" data-group="${g.key}"${g.closed ? '' : ' open'}><summary>${g.title}</summary><div class="ev2-dp-body">
        ${rows.map(renderRow).join('')}
        ${more.length ? `<details class="ev2-dp-more" data-more="${g.key}" data-more-key="${esc(key)}"${moreOpen.has(key) ? ' open' : ''}>
            <summary>More options <span class="ev2-dp-count">· ${more.length}</span></summary>
            <div class="ev2-dp-more-body">${more.map(renderRow).join('')}</div></details>` : ''}
      </div></details>`;
}

function rowShell(row, control, changed) {
    const resettable = changed !== undefined;
    return `<div class="ev2-dp-row${changed ? ' is-changed' : ''}" data-control="${row.id}">
        ${row.label ? `<span class="ev2-dp-label">${row.label}</span>` : '<span></span>'}
        <div class="ev2-dp-control">${control}</div>
        ${resettable ? `<button type="button" class="ev2-dp-reset" data-reset="${row.id}" title="Reset">${icon(RESET_ICON, 13)}</button>` : '<span></span>'}
      </div>`;
}

function seg(options, current, attr = 'data-val') {
    return `<div class="ev2-dp-seg">${options.map(([v, label, title]) =>
        `<button type="button" ${attr}="${esc(encode(v))}" class="${same(current, v) ? 'is-on' : ''}" title="${esc(title || '')}">${label}</button>`).join('')}</div>`;
}

function swatches(current) {
    const cur = String(current ?? '').split('/')[0].toUpperCase();
    const known = tokens.colors.find(c => c.value.toUpperCase() === cur);
    return `<div class="ev2-dp-swatches">${tokens.colors.map(c =>
        `<button type="button" class="ev2-dp-swatch${c.value.toUpperCase() === cur ? ' is-on' : ''}" style="background:${esc(c.value)}" data-val="${esc(c.value)}" title="${esc(c.name)}"></button>`).join('')}
        <label class="ev2-dp-swatch ev2-dp-swatch-custom${cur && !known ? ' is-on' : ''}" title="Other colour"><input type="color" data-color="1" value="${/^#[0-9A-F]{6}$/.test(cur) ? cur.toLowerCase() : '#000000'}"></label>
        <span class="ev2-dp-swatch-name">${esc(known ? known.name : cur || 'None')}</span></div>`;
}

function slider(row, value) {
    const v = value ?? (row.fallback ? row.fallback(mount.el) : row.min);
    const shown = Math.round(Number(v) * 1000) / 1000;
    return `<div class="ev2-dp-slider"><input type="range" min="${row.min}" max="${row.max}" step="${row.step}" value="${shown}" aria-label="${esc(row.label)}">
        <div class="ev2-dp-num"><input type="number" min="${row.min}" max="${row.max}" step="${row.step}" value="${shown}" aria-label="${esc(row.label)} value"><span>${row.unit}</span></div></div>`;
}

function renderRow(row) {
    const el = mount.el;
    switch (row.kind) {
    case 'seg': return rowShell(row, seg(row.options, read(row.prop, row.state)), propChanged(row.prop, row.state));
    case 'slider': return rowShell(row, slider(row, read(row.prop, row.state)), propChanged(row.prop, row.state));
    case 'percent': {
        const v = read(row.prop);
        const pct = typeof v === 'string' && v.endsWith('%') ? parseFloat(v) : v === 'full' ? 100 : null;
        return rowShell(row, slider({ ...row, unit: '%' }, pct ?? 100), propChanged(row.prop));
    }
    case 'swatches': return rowShell(row, swatches(read(row.prop, row.state)), propChanged(row.prop, row.state));
    case 'alpha': {
        const v = String(read(row.prop) || '');
        const alpha = v.includes('/') ? Number(v.split('/')[1]) : 100;
        return rowShell(row, slider({ ...row, min: 20, max: 100, step: 5, unit: '%' }, alpha));
    }
    case 'toggles': return rowShell(row, `<div class="ev2-dp-toggles">${row.items.map((it, i) =>
        `<button type="button" class="ev2-dp-toggle${same(read(it.prop), it.on) ? ' is-on' : ''}" data-toggle="${i}">${it.label}</button>`).join('')}</div>`);
    case 'fontFamily': {
        const families = tokens.fonts.map(f => [f.family, esc(f.family), f.role]);
        const cur = read('fontFamily');
        if (cur && !families.some(f => f[0] === cur)) families.push([cur, esc(cur), 'Current']);
        return rowShell(row, seg(families, cur), propChanged('fontFamily'));
    }
    case 'classChoice': {
        const list = realList(el);
        const cur = row.options.slice().reverse().find(([, , cls]) => cls.length && cls.every(c => list.includes(c)))?.[0] ?? row.options[0][0];
        return rowShell(row, seg(row.options.map(([v, l]) => [v, l]), cur, 'data-choice'));
    }
    case 'classToggles': {
        const list = realList(el);
        return rowShell(row, `<div class="ev2-dp-toggles">${row.items.map(([k, l, cls], i) =>
            `<button type="button" class="ev2-dp-toggle${cls.every(c => list.includes(c)) ? ' is-on' : ''}" data-class-toggle="${i}">${l}</button>`).join('')}</div>`);
    }
    case 'box': return `<div class="ev2-dp-row ev2-dp-row-wide" data-control="box">${renderBox()}</div>`;
    case 'show': {
        const values = readValues(realList(el), 'display');
        return rowShell(row, `<div class="ev2-dp-toggles">${DEVICES.slice().reverse().map(d =>
            `<button type="button" class="ev2-dp-toggle${values[d] === 'hidden' ? '' : ' is-on'}" data-show="${d}">${d[0].toUpperCase() + d.slice(1)}</button>`).join('')}</div>`);
    }
    case 'attr': return rowShell(row, `<input type="text" class="ev2-dp-text" data-attr="${row.attr}" value="${esc(el.getAttribute(row.attr) || '')}" placeholder="${esc(row.placeholder || '')}">`);
    case 'newTab': return rowShell(row, `<label class="ev2-dp-check"><input type="checkbox" data-newtab="1" ${el.getAttribute('target') === '_blank' ? 'checked' : ''}> Open in a new tab</label>`);
    case 'hoverSwitch': return `<div class="ev2-dp-state"><span class="ev2-dp-sub">${mount.hover ? 'When the mouse is over it' : 'Normal state'}</span>
        <div class="ev2-dp-seg"><button type="button" data-hover="0" class="${mount.hover ? '' : 'is-on'}">Normal</button><button type="button" data-hover="1" class="${mount.hover ? 'is-on' : ''}">Hover</button></div></div>`;
    case 'buttonStyle': return rowShell(row, seg([['filled', 'Filled'], ['outline', 'Outline'], ['link', 'Text link']], buttonStyle()));
    case 'buttonSize': {
        const sizes = tokens.buttonSizes;
        const cur = Object.keys(sizes).find(k => same(read('paddingTop'), sizes[k][0]) && same(read('paddingX'), sizes[k][1])) || null;
        return rowShell(row, seg(Object.keys(sizes).map(k => [k, k]), cur));
    }
    case 'buttonColor': {
        const state = mount.hover ? 'hover' : '';
        const style = buttonStyle();
        if (row.role === 'text' && style !== 'filled') return '';
        const prop = row.role === 'fill' ? (style === 'filled' ? 'bgColor' : 'textColor') : 'textColor';
        const id = row.role === 'fill' && mount.hover ? 'hoverFill' : row.id;
        return rowShell({ ...row, id, label: row.role === 'fill' && style !== 'filled' ? 'Colour' : row.label }, swatches(read(prop, state)), propChanged(prop, state));
    }
    case 'imageReplace': return rowShell(row, `<div class="ev2-dp-thumbrow"><span class="ev2-dp-thumb" style="background-image:url('${esc(el.currentSrc || el.getAttribute('src') || '')}')"></span><button type="button" class="ev2-dp-btn" data-act="replace-image">Replace…</button></div>`);
    case 'focal': {
        const [x, y] = String(read('objectPosition') || '50% 50%').split(' ').map(parseFloat);
        return rowShell(row, `<div><div class="ev2-dp-focal" data-focal="objectPosition" style="background-image:url('${esc(el.currentSrc || el.getAttribute('src') || '')}')"><span class="ev2-dp-dot" style="left:${x}%;top:${y}%"></span></div>
            <div class="ev2-dp-meta">Click the part that must always stay in view</div></div>`, propChanged('objectPosition'));
    }
    case 'bgType': return rowShell(row, seg([['none', 'None'], ['color', 'Colour'], ['image', 'Image']], bgType(), 'data-bgtype'));
    case 'bgImage': {
        const bg = parseBgImage(el.style.backgroundImage);
        return rowShell(row, `<div class="ev2-dp-thumbrow"><span class="ev2-dp-thumb" style="background-image:url('${esc(bg.url)}')"></span>
            <button type="button" class="ev2-dp-btn" data-act="bg-image">Change…</button><button type="button" class="ev2-dp-btn ev2-dp-btn-quiet" data-act="bg-image-remove">Remove</button></div>`);
    }
    case 'overlay': {
        const o = overlayNow();
        return rowShell(row, slider({ ...row, min: 0, max: 90, step: 5, unit: '%' }, Math.round(o.opacity * 100)));
    }
    case 'overlayColor': return rowShell(row, swatches(overlayNow().color));
    case 'bgFocal': {
        const pos = (el.style.backgroundPosition || '50% 50%').replace('center', '50%');
        const [x, y] = pos.split(' ').map(v => parseFloat(v) || 50);
        const bg = parseBgImage(el.style.backgroundImage);
        return rowShell(row, `<div><div class="ev2-dp-focal" data-focal="bg" style="background-image:url('${esc(bg.url)}')"><span class="ev2-dp-dot" style="left:${x}%;top:${y}%"></span></div>
            <div class="ev2-dp-meta">Click the part that must always stay in view</div></div>`);
    }
    case 'bgFixed': return rowShell(row, `<div class="ev2-dp-toggles"><button type="button" class="ev2-dp-toggle${el.style.backgroundAttachment === 'fixed' ? ' is-on' : ''}" data-act="bg-fixed">Fixed background (parallax)</button></div>`);
    case 'textTone': {
        const c = String(read('textColor') || '').split('/')[0].toUpperCase();
        const tone = !c ? null : isLight(c) ? 'light' : 'dark';
        return rowShell(row, seg([['dark', 'Dark text'], ['light', 'Light text']], tone, 'data-tone'), propChanged('textColor'));
    }
    case 'padY': {
        const sp = tokens.spacing;
        const cur = Object.keys(sp).find(k => same(read('paddingTop'), sp[k]) && same(read('paddingBottom'), sp[k])) || null;
        return rowShell(row, seg(Object.keys(sp).map(k => [k, k]), cur), propChanged('paddingTop') || propChanged('paddingBottom'));
    }
    case 'contentWidth': {
        const inner = innerContainer();
        const v = readValues(realList(inner), 'maxWidth')[device()];
        const options = [[640, 'Narrow'], [896, 'Normal'], [1152, 'Wide'], ['none', 'Full']];
        return rowShell(row, seg(options, v, 'data-width'));
    }
    case 'video': return renderVideoRow(row);
    default: return '';
    }
}

function renderBox() {
    const v = k => read(k) ?? 0;
    const inp = (k, title) => `<input class="ev2-dp-bm-val${v(k) ? ' is-set' : ''}" value="${v(k)}" data-box="${k}" inputmode="numeric" aria-label="${title}" title="${title} (px)">`;
    return `<div class="ev2-dp-box"><span class="ev2-dp-box-tag">Margin</span><div class="ev2-dp-bm-grid">
        <span style="grid-column:2;grid-row:1">${inp('marginTop', 'Margin top')}</span>
        <span style="grid-column:1;grid-row:2">${inp('marginX', 'Margin left/right')}</span>
        <div class="ev2-dp-bm-inner"><div class="ev2-dp-bm-grid">
          <span style="grid-column:2;grid-row:1">${inp('paddingTop', 'Padding top')}</span>
          <span style="grid-column:1;grid-row:2">${inp('paddingX', 'Padding left/right')}</span>
          <div class="ev2-dp-bm-content" style="grid-column:2;grid-row:2">Padding</div>
          <span style="grid-column:3;grid-row:2">${inp('paddingX', 'Padding left/right')}</span>
          <span style="grid-column:2;grid-row:3">${inp('paddingBottom', 'Padding bottom')}</span>
        </div></div>
        <span style="grid-column:3;grid-row:2">${inp('marginX', 'Margin left/right')}</span>
        <span style="grid-column:2;grid-row:3">${inp('marginBottom', 'Margin bottom')}</span>
      </div></div>`;
}

function renderVideoRow(row) {
    const el = mount.el;
    const iframe = el.querySelector(':scope > iframe');
    const video = el.querySelector(':scope > video');
    const src = iframe ? iframe.getAttribute('src') : (video?.querySelector('source')?.getAttribute('src') || video?.getAttribute('src') || '');
    if (iframe || video) {
        const yt = extractYouTubeId(src);
        return rowShell(row, `<div class="ev2-dp-video">${yt ? `<span class="ev2-dp-thumb" style="background-image:url('https://img.youtube.com/vi/${esc(yt)}/hqdefault.jpg')"></span>` : ''}
            <span class="ev2-dp-meta">${esc(videoDisplayUrl(src))}</span><button type="button" class="ev2-dp-btn ev2-dp-btn-quiet" data-act="video-remove">Remove video</button></div>`);
    }
    return rowShell(row, `<div class="ev2-dp-field"><input type="text" class="ev2-dp-text" data-video-url="1" placeholder="Paste a YouTube URL"><button type="button" class="ev2-dp-btn" data-act="video-set">Set</button></div>`);
}

function isLight(hex) {
    const { r, g, b } = hexToRgb(hex);
    return (r * 299 + g * 587 + b * 114) / 1000 > 150;
}
function overlayNow() {
    const el = mount.el;
    const attr = el.getAttribute('data-overlay') || '';
    const m = attr.match(/rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)/);
    if (m) return { color: rgbToHex(`rgb(${m[1]},${m[2]},${m[3]})`), opacity: parseFloat(m[4]) };
    const bg = parseBgImage(el.style.backgroundImage);
    return { color: bg.overlayColor || '#000000', opacity: bg.overlayOpacity || 0 };
}
function buttonStyle() {
    const bg = read('bgColor');
    if (bg && bg !== 'transparent') return 'filled';
    return (read('borderWidth') || 0) > 0 ? 'outline' : 'link';
}

// ---- actions ---------------------------------------------------------------------

function setOverlay(color, opacity) {
    const bg = parseBgImage(mount.el.style.backgroundImage);
    emitStyle(style => { style.backgroundImage = composeBgImage(bg.url, color, opacity); });
    const { r, g, b } = hexToRgb(color);
    emitAttr('data-overlay', opacity > 0 ? `rgba(${r}, ${g}, ${b}, ${opacity})` : '');
}

function setButtonStyle(style) {
    let list = realList(mount.el);
    const fill = read('bgColor') && read('bgColor') !== 'transparent' ? read('bgColor') : (read('textColor') || tokens.colors[0]?.value);
    const W = (l, prop, v) => writeValue(l, prop, 'desktop', v);
    if (style === 'filled') {
        list = W(list, 'bgColor', fill);
        list = W(list, 'textColor', '#FFFFFF');
        list = W(list, 'textDecoration', null);
        if (!readValues(list, 'paddingX').desktop) { list = W(list, 'paddingTop', 14); list = W(list, 'paddingBottom', 14); list = W(list, 'paddingX', 28); }
    } else if (style === 'outline') {
        list = W(list, 'bgColor', null);
        list = W(list, 'borderWidth', 1);
        list = W(list, 'borderColor', fill);
        list = W(list, 'textColor', fill);
        list = W(list, 'textDecoration', null);
        if (!readValues(list, 'paddingX').desktop) { list = W(list, 'paddingTop', 14); list = W(list, 'paddingBottom', 14); list = W(list, 'paddingX', 28); }
    } else {
        list = W(list, 'bgColor', null);
        list = W(list, 'borderWidth', null);
        list = W(list, 'borderColor', null);
        list = W(list, 'textColor', fill);
        for (const p of ['paddingTop', 'paddingBottom', 'paddingX']) list = W(list, p, null);
        list = W(list, 'textDecoration', 'underline');
    }
    setClasses(list);
}

async function setVideo(url) {
    const cfg = window.EDITOR_CONFIG || {};
    const body = { page_id: cfg.pageId, section_id: mount.el.getAttribute('data-section') || mount.el.id, video_url: url };
    if (cfg.contentTypeId && cfg.objectId) { body.content_type_id = cfg.contentTypeId; body.object_id = cfg.objectId; }
    try {
        await api.post('/update-section-video/', body);
        window.location.reload();
    } catch (err) {
        alertDialog({ title: url ? 'Could not set the video' : 'Could not remove the video', message: err.message || '', tone: 'error' });
    }
}

function rowById(id) {
    for (const g of [...PANELS[mount.type], COMMON]) {
        const r = [...g.rows, ...(g.more || [])].find(x => x.id === id || (x.kind === 'buttonColor' && id === 'hoverFill' && x.role === 'fill'));
        if (r) return r;
    }
    return null;
}

function onClick(e) {
    const t = e.target;
    const btn = t.closest('button');
    const focal = t.closest('.ev2-dp-focal');
    if (focal) {
        const r = focal.getBoundingClientRect();
        const x = Math.round((e.clientX - r.left) / r.width * 100);
        const y = Math.round((e.clientY - r.top) / r.height * 100);
        if (focal.dataset.focal === 'bg') emitStyle(style => { style.backgroundPosition = `${x}% ${y}%`; });
        else write('objectPosition', `${x}% ${y}%`);
        rerender();
        return;
    }
    if (!btn) return;
    const rowEl = btn.closest('[data-control]');
    const row = rowEl ? rowById(rowEl.dataset.control) : null;
    const el = mount.el;

    if (btn.dataset.device) { setViewport(btn.dataset.device); rerender(); return; }
    if (btn.dataset.selectSection) { events.emit('selection:request', el.closest('[data-section]')); return; }
    if (btn.dataset.hover !== undefined) { mount.hover = btn.dataset.hover === '1'; rerender(); return; }
    if (btn.dataset.reset) {
        const id = btn.dataset.reset;
        if (id === 'padY') { resetProp('paddingTop'); resetProp('paddingBottom'); }
        else if (id === 'hoverFill' || (row && row.kind === 'buttonColor')) {
            const state = mount.hover ? 'hover' : '';
            resetProp(buttonStyle() === 'filled' && row.role === 'fill' ? 'bgColor' : 'textColor', state);
        } else if (row && row.prop) resetProp(row.prop, row.state || '');
        else if (row && row.kind === 'fontFamily') resetProp('fontFamily');
        else if (row && row.kind === 'focal') resetProp('objectPosition');
        else if (row && row.kind === 'textTone') resetProp('textColor');
        rerender();
        return;
    }
    if (btn.dataset.act) { runAction(btn.dataset.act); return; }
    if (btn.dataset.show) {
        const values = readValues(realList(el), 'display');
        const natural = naturalDisplay();
        for (const d of DEVICES) if (values[d] === null) values[d] = natural;
        values[btn.dataset.show] = values[btn.dataset.show] === 'hidden' ? natural : 'hidden';
        const collapsed = DEVICES.every(d => values[d] === natural) && !readValues(initialClasses.get(mount.selector) || [], 'display').desktop
            ? { mobile: null, tablet: null, desktop: null } : values;
        setClasses(writeValues(realList(el), 'display', collapsed));
        rerender();
        return;
    }
    if (btn.dataset.toggle !== undefined && row) {
        const it = row.items[Number(btn.dataset.toggle)];
        write(it.prop, same(read(it.prop), it.on) ? it.off : it.on);
        rerender();
        return;
    }
    if (btn.dataset.classToggle !== undefined && row) {
        const [, , cls] = row.items[Number(btn.dataset.classToggle)];
        const list = realList(el);
        const on = cls.every(c => list.includes(c));
        setClasses(on ? list.filter(c => !cls.includes(c)) : [...list, ...cls.filter(c => !list.includes(c))]);
        rerender();
        return;
    }
    if (btn.dataset.choice !== undefined && row) {
        const all = new Set(row.options.flatMap(([, , cls]) => cls));
        const chosen = row.options.find(([v]) => encode(v) === btn.dataset.choice)[2];
        const list = realList(el).filter(c => !all.has(c) || chosen.includes(c));
        setClasses([...list, ...chosen.filter(c => !list.includes(c))]);
        rerender();
        return;
    }
    if (btn.dataset.bgtype) {
        const want = btn.dataset.bgtype;
        if (want === 'image') { events.emit('image-picker:open', { mode: 'background' }); return; }
        const bg = parseBgImage(el.style.backgroundImage);
        if (bg.url) emitStyle(style => { style.backgroundImage = composeBgImage('', bg.overlayColor, bg.overlayOpacity); });
        if (want === 'none') {
            write('bgColor', null);
            emitStyle(style => { style.backgroundColor = ''; });
        } else if (!read('bgColor')) {
            const inline = rgbToHex(el.style.backgroundColor);
            emitStyle(style => { style.backgroundColor = ''; });
            write('bgColor', inline || tokens.colors.find(c => c.name === 'Background')?.value || '#FFFFFF');
        }
        rerender();
        return;
    }
    if (btn.dataset.tone) {
        const light = btn.dataset.tone === 'light';
        const pick = tokens.colors.find(c => (light ? isLight(c.value) : !isLight(c.value)) && c.value !== (light ? '#FFFFFF' : '#000000'));
        write('textColor', pick ? pick.value : light ? '#FFFFFF' : '#14171B');
        rerender();
        return;
    }
    if (btn.dataset.width !== undefined) {
        const inner = innerContainer();
        if (inner) setClassesOn(inner, writeValue(realList(inner), 'maxWidth', device(), decode(btn.dataset.width)));
        rerender();
        return;
    }
    if (btn.dataset.val !== undefined && row) {
        const value = decode(btn.dataset.val);
        if (btn.classList.contains('ev2-dp-swatch')) {
            if (row.kind === 'buttonColor') {
                const state = mount.hover ? 'hover' : '';
                const style = buttonStyle();
                if (row.role === 'fill' && style === 'filled') write('bgColor', value, { state });
                else if (row.role === 'fill') { write('textColor', value, { state }); if (style === 'outline' && !state) write('borderColor', value); }
                else write('textColor', value, { state });
            } else if (row.kind === 'overlayColor') {
                setOverlay(value, overlayNow().opacity || 0.4);
            } else {
                const old = String(read(row.prop, row.state) || '');
                const alpha = row.prop === 'textColor' && old.includes('/') ? '/' + old.split('/')[1] : '';
                if (row.prop === 'bgColor' && el.style.backgroundColor) emitStyle(style => { style.backgroundColor = ''; });
                write(row.prop, value + alpha, { state: row.state || '' });
            }
        } else if (row.kind === 'buttonStyle') {
            setButtonStyle(value);
        } else if (row.kind === 'buttonSize') {
            const [py, px, fs] = tokens.buttonSizes[value];
            let list = realList(el);
            for (const [p, v] of [['paddingTop', py], ['paddingBottom', py], ['paddingX', px], ['fontSize', fs]]) list = writeValue(list, p, device(), v);
            setClasses(list);
        } else if (row.kind === 'padY') {
            const v = tokens.spacing[value];
            let list = realList(el);
            list = writeValue(list, 'paddingTop', device(), v);
            list = writeValue(list, 'paddingBottom', device(), v);
            setClasses(list);
        } else if (row.kind === 'fontFamily') {
            write('fontFamily', value);
        } else if (row.prop) {
            write(row.prop, value, { state: row.state || '' });
        }
        rerender();
    }
}

function runAction(act) {
    const el = mount.el;
    if (act === 'copy-style') {
        picking = picking ? null : { target: el };
        document.body.classList.toggle('ev2-dp-picking', !!picking);
        notices.set(mount.selector, picking ? `Click another ${TYPE_NAMES[mount.type].toLowerCase()} to copy its style. Esc cancels.` : '');
        rerender();
        return;
    }
    if (act === 'reset-element') {
        setClasses(initialClasses.get(mount.selector) || []);
        const attrs = initialAttrs.get(mount.selector) || {};
        for (const [attr, value] of Object.entries(attrs)) {
            if ((el.getAttribute(attr) || null) !== (value || null)) emitAttr(attr, value || '');
        }
        notices.set(mount.selector, 'Back to how it was when the page was opened.');
        rerender();
        return;
    }
    if (act === 'apply-similar') { applySimilar(); return; }
    if (act === 'replace-image') { events.emit('image-picker:open'); return; }
    if (act === 'bg-image') { events.emit('image-picker:open', { mode: 'background' }); return; }
    if (act === 'bg-image-remove') {
        const bg = parseBgImage(el.style.backgroundImage);
        emitStyle(style => { style.backgroundImage = composeBgImage('', bg.overlayColor, bg.overlayOpacity); });
        rerender();
        return;
    }
    if (act === 'bg-fixed') {
        emitStyle(style => { style.backgroundAttachment = style.backgroundAttachment === 'fixed' ? '' : 'fixed'; });
        rerender();
        return;
    }
    if (act === 'video-remove') { setVideo(''); return; }
    if (act === 'video-set') {
        const url = mount.container.querySelector('[data-video-url]')?.value.trim();
        if (url) setVideo(url);
    }
}

async function applySimilar() {
    const initial = initialClasses.get(mount.selector) || [];
    const current = realList(mount.el);
    const add = current.filter(c => !initial.includes(c));
    const remove = initial.filter(c => !current.includes(c));
    if (!add.length && !remove.length) {
        notices.set(mount.selector, 'Change this element first; the same change is then applied to the others.');
        rerender();
        return;
    }
    if (getPendingCount() > 0 && !(await saveNow())) return;
    try {
        const pageId = (window.EDITOR_CONFIG || {}).pageId;
        const res = await api.post('/restyle-similar/', { tag: mount.el.tagName.toLowerCase(), classes: initial, add, remove, page_id: pageId });
        const pages = res.changed.length;
        const label = `Applied to ${res.total} ${PLURAL[mount.type]} on ${pages} page${pages === 1 ? '' : 's'}`;
        // the toast's Undo reverts this page's latest checkpoint: offer it only when this page was changed
        try { sessionStorage.setItem('ev2-toast-pending', JSON.stringify({ label, noUndoToast: !res.current_page_changed })); } catch (_) {}
        window.location.reload();
    } catch (err) {
        alertDialog({ title: 'Could not apply it to the others', message: err.message || '', tone: 'error' });
    }
}

function onInput(e) {
    const t = e.target;
    const rowEl = t.closest('[data-control]');
    const row = rowEl ? rowById(rowEl.dataset.control) : null;
    if (t.classList.contains('ev2-dp-classes')) {
        setClasses(t.value.split(/\s+/).filter(Boolean));
        return;
    }
    if (t.dataset.box) return;   // box values commit on change
    if (t.dataset.color) return; // colour picker commits on change
    if (t.dataset.attr || t.dataset.videoUrl) return;
    if (!row || (t.type !== 'range' && t.type !== 'number')) return;
    const n = Number(t.value);
    if (Number.isNaN(n)) return;
    rowEl.querySelectorAll('input').forEach(i => { if (i !== t) i.value = t.value; });
    applyNumber(row, n, true);
}

function applyNumber(row, n, live) {
    if (row.kind === 'overlay') { setOverlay(overlayNow().color, n / 100); return; }
    if (row.kind === 'alpha') {
        const base = String(read(row.prop) || '').split('/')[0];
        if (base) write(row.prop, n >= 100 ? base : `${base}/${n}`, { live });
        return;
    }
    if (row.kind === 'percent') { write(row.prop, n >= 100 ? 'full' : `${n}%`, { live }); return; }
    write(row.prop, n, { state: row.state || '', live });
}

function onChange(e) {
    const t = e.target;
    const rowEl = t.closest('[data-control]');
    const row = rowEl ? rowById(rowEl.dataset.control) : null;
    if (t.dataset.box) {
        const n = parseInt(t.value, 10);
        write(t.dataset.box, Number.isNaN(n) ? null : n);
        rerender();
        return;
    }
    if (t.dataset.color && row) {
        const value = t.value.toUpperCase();
        const fake = document.createElement('button');
        fake.className = 'ev2-dp-swatch';
        fake.dataset.val = value;
        rowEl.querySelector('.ev2-dp-control').appendChild(fake);
        fake.click();
        return;
    }
    if (t.dataset.attr) {
        emitAttr(t.dataset.attr, t.value.trim());
        return;
    }
    if (t.dataset.newtab) {
        emitAttr('target', t.checked ? '_blank' : '');
        emitAttr('rel', t.checked ? 'noopener' : '');
        return;
    }
    if (row && (t.type === 'range' || t.type === 'number')) {
        const n = Number(t.value);
        if (!Number.isNaN(n)) applyNumber(row, n, false);
        rerender();
    }
}

function bind(container) {
    if (container.dataset.ev2DpBound) return;
    container.dataset.ev2DpBound = '1';
    const ours = e => mount && mount.container === container && e.target.closest('.ev2-dp');
    container.addEventListener('click', e => { if (ours(e)) onClick(e); });
    container.addEventListener('input', e => { if (ours(e)) onInput(e); });
    container.addEventListener('change', e => { if (ours(e)) onChange(e); });
    container.addEventListener('toggle', e => {
        const d = e.target;
        if (d.matches?.('details.ev2-dp-more')) d.open ? moreOpen.add(d.dataset.moreKey) : moreOpen.delete(d.dataset.moreKey);
    }, true);
}
