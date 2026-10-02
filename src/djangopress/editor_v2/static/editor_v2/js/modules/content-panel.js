/**
 * Content tab: what the selection says, in the operator's words.
 *
 * Section (or any block): every writable item as one short form, named by role.
 * Heading/text: the text, its level (H1–H4 / text), the other items of the block.
 * Button/link: the label and where it goes (page, section, phone, email,
 * WhatsApp, web address), new tab. Image: replace, alt (with "Describe the
 * photo"), focus point, sharpness at the size it is shown.
 * Every text field also shows the other languages' text (read-only).
 *
 * Saving goes through the usual events: change:content (plain text only —
 * formatted text is edited on the page), change:attribute, change:classes.
 */
import { events } from '../lib/events.js';
import { api } from '../lib/api.js';
import { getCssSelector, findCardScope, isRuntimeInjected } from '../lib/dom.js';
import { confirmDialog } from '../lib/dialog.js';
import { retagElement } from '../lib/structural.js';
import { setText, setAttr, setFocusPoint, setNewTab, opensInNewTab, focusPointOf } from '../lib/edits.js';
import {
    ROLE_LABELS, itemRole, sectionOutline, describeSection, hasFormatting, parseHref, buildHref,
    imageQuality, isPlaceholder, otherLanguageText,
} from '../lib/content-model.js';

const config = () => window.EDITOR_CONFIG || {};
const ICONS = {
    section: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18"/>',
    eyebrow: '<path d="M4 8h16"/><path d="M4 14h9" opacity=".5"/>',
    heading: '<path d="M6 4v16M18 4v16M6 12h12"/>',
    text: '<path d="M4 6h16M4 12h16M4 18h10"/>',
    button: '<rect x="3" y="7" width="18" height="10" rx="2"/><path d="M8 12h8"/>',
    link: '<path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1"/><path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1"/>',
    image: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m21 16-5-5-9 9"/>',
    block: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 12h18"/>',
    spark: '<path d="M12 2l2.4 6.6L21 11l-6.6 2.4L12 20l-2.4-6.6L3 11l6.6-2.4z" fill="currentColor" stroke="none"/>',
};
const KINDS = [['page', 'Page'], ['section', 'Section'], ['phone', 'Phone'], ['email', 'Email'], ['whatsapp', 'WhatsApp'], ['url', 'Web address']];
const LEVELS = [['h1', 'H1'], ['h2', 'H2'], ['h3', 'H3'], ['h4', 'H4'], ['p', 'Text']];
const FOCUS = [['top', 'Top'], ['center', 'Center'], ['bottom', 'Bottom'], ['left', 'Left'], ['right', 'Right']];
const ALT_MAX = 125;

let copiesPromise = null;
let targetsPromise = null;
let unsubs = [];
let shown = null;               // {container, el, root}: what the tab shows now
let listening = false;

/** Show the current element again (its text may have gained formatting on the page). */
function rerender() {
    if (shown && shown.root.isConnected && shown.container.contains(shown.root) && (!shown.el || shown.el.isConnected)) {
        renderContentPanel(shown.container, shown.el);
    }
}

function listenOnce() {
    if (listening) return;
    listening = true;
    events.on('inline-edit:end', rerender);
}

function esc(s) { return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
function icon(name) { return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">${ICONS[name] || ICONS.block}</svg>`; }
function editableParams() {
    const cfg = config();
    const p = { page_id: cfg.pageId || '' };
    if (cfg.contentTypeId && cfg.objectId) { p.content_type_id = cfg.contentTypeId; p.object_id = cfg.objectId; }
    return p;
}
function sectionLabel(name) { const s = (name || '').replace(/[-_]+/g, ' ').trim(); return s.charAt(0).toUpperCase() + s.slice(1); }
function plain(el) { return (el.textContent || '').replace(/\s+/g, ' ').trim(); }

function pageCopies() {
    if (!copiesPromise) copiesPromise = api.get('/page-copies/', editableParams()).then(r => r.copies || {}).catch(() => ({}));
    return copiesPromise;
}
function linkTargets() {
    if (!targetsPromise) targetsPromise = api.get('/link-targets/').then(r => r.pages || []).catch(() => []);
    return targetsPromise;
}

export function init() {
    unsubs.push(events.on('changes:saved', () => { copiesPromise = null; }));
}
export function destroy() {
    unsubs.forEach(u => u());
    unsubs = [];
    if (listening) events.off('inline-edit:end', rerender);
    listening = false;
    shown = null;
    copiesPromise = null;
    targetsPromise = null;
}

// ── Pieces ──

function roleOf(el) {
    if (el.hasAttribute('data-section')) return 'section';
    return itemRole(el) || 'block';
}

function header(el, role) {
    const section = el.closest('[data-section]');
    const crumbs = [`<span class="ev2-cp-crumb-root">Page</span>`];
    if (section && section !== el) {
        crumbs.push(`<button type="button" class="ev2-cp-crumb" data-select="section">${esc(sectionLabel(section.dataset.section))}</button>`);
        crumbs.push(`<span class="ev2-cp-here">${esc(ROLE_LABELS[role] || 'Block')}</span>`);
    } else if (section) {
        crumbs.push(`<span class="ev2-cp-here">${esc(sectionLabel(section.dataset.section))}</span>`);
    }
    const title = role === 'section' ? sectionLabel(el.dataset.section) : (ROLE_LABELS[role] || 'Block');
    const sub = role === 'section' || role === 'block' ? describeSection(el) : subFor(el, role);
    const lang = config().language || '';
    const name = (config().languageNames || {})[lang] || lang.toUpperCase();
    const multi = (config().languages || []).length > 1;
    return `<div class="ev2-cp-head">
        <nav class="ev2-cp-crumbs" aria-label="Where you are">${crumbs.join('<span class="ev2-cp-sep">›</span>')}</nav>
        <div class="ev2-cp-title"><span class="ev2-cp-kind ${role === 'section' ? 'is-section' : ''}">${icon(role === 'section' ? 'section' : role)}</span>
            <div><h2>${esc(title)}</h2><div class="ev2-cp-sub">${esc(sub)}</div></div></div>
        ${multi ? `<div class="ev2-cp-lang"><span>${esc(lang.toUpperCase())}</span>Editing ${esc(name)}. Each language keeps its own text.</div>` : ''}
    </div>`;
}

function subFor(el, role) {
    if (role === 'heading') return `Heading (${el.tagName.toLowerCase()})`;
    if (role === 'eyebrow') return 'Small label above a title';
    if (role === 'text') return 'Paragraph';
    if (role === 'image') return isPlaceholder(el) ? 'Placeholder, waiting for a photo' : 'Photo';
    const { kind } = parseHref(el.getAttribute('href'));
    const goes = { page: 'a page', section: 'a section', phone: 'a phone call', email: 'an email', whatsapp: 'WhatsApp', url: 'a web address' }[kind];
    return `${role === 'button' ? 'Button' : 'Link'} to ${goes}`;
}

/** The read-only line(s) with this item's text in the other languages. */
function otherLanguages(holder, el) {
    const current = config().language;
    const others = (config().languages || []).filter(c => c !== current);
    const selector = getCssSelector(el);
    if (!others.length || !selector) return;
    pageCopies().then(copies => {
        holder.innerHTML = others.map(code => {
            const value = otherLanguageText(copies[code], selector);
            return `<div class="ev2-cp-other-line"><b>${esc(code.toUpperCase())}</b> ${value ? esc(value) : '<i>missing</i>'}</div>`;
        }).join('');
    });
}

function textField(el, role, { compact = false } = {}) {
    const wrap = document.createElement('div');
    wrap.className = 'ev2-cp-field';
    wrap.dataset.role = role;
    const value = plain(el);
    const long = value.length > 60 || role === 'text';
    wrap.innerHTML = `<div class="ev2-cp-field-top">
            ${compact ? `<span class="ev2-cp-kind is-small">${icon(role)}</span>` : ''}
            <label data-role-label>${esc(ROLE_LABELS[role] || 'Text')}</label>
            <span class="ev2-cp-meta">${compact ? '<button type="button" class="ev2-cp-open" data-action="open">Open</button>' : `${value.length} characters`}</span>
        </div>`;
    if (hasFormatting(el)) {
        const ro = document.createElement('div');
        ro.className = 'ev2-cp-readonly';
        ro.innerHTML = `<div>${esc(value)}</div><div class="ev2-cp-help">Has formatting (bold, links…): edit it on the page.
            <button type="button" class="ev2-cp-btn is-small" data-action="edit-inline">Edit on the page</button></div>`;
        ro.querySelector('[data-action="edit-inline"]').addEventListener('click', () => {
            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            events.emit('inline-edit:trigger', { element: el });
        });
        wrap.appendChild(ro);
    } else {
        const input = document.createElement(long ? 'textarea' : 'input');
        input.className = `ev2-cp-input${role === 'heading' && !compact ? ' is-big' : ''}`;
        if (!long) input.type = 'text';
        input.value = value;
        input.setAttribute('aria-label', ROLE_LABELS[role] || 'Text');
        input.addEventListener('input', () => {
            if (hasFormatting(el)) { rerender(); return; }        // formatted on the page meanwhile: never flatten it
            setText(el, input.value);
            const meta = wrap.querySelector('.ev2-cp-meta');
            if (!compact && meta) meta.textContent = `${input.value.length} characters`;
        });
        wrap.appendChild(input);
    }
    const other = document.createElement('div');
    other.className = 'ev2-cp-other';
    wrap.appendChild(other);
    otherLanguages(other, el);
    wrap.querySelector('[data-action="open"]')?.addEventListener('click', () => select(el));
    return wrap;
}

function select(el) {
    events.emit('selection:request', el);
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function hoverLink(row, el) {
    row.addEventListener('mouseenter', () => el.classList.add('ev2-cp-hot'));
    row.addEventListener('mouseleave', () => el.classList.remove('ev2-cp-hot'));
}

function linkSummaryField(el, role) {
    const wrap = textField(el, role, { compact: true });
    const { kind, value } = parseHref(el.getAttribute('href'));
    const label = Object.fromEntries(KINDS)[kind] || 'Link';
    const line = document.createElement('div');
    line.className = 'ev2-cp-help';
    line.innerHTML = `Goes to: <b>${esc(label)}</b> ${esc(value || '—')}`;
    wrap.insertBefore(line, wrap.querySelector('.ev2-cp-other'));
    return wrap;
}

function imageSummaryField(el) {
    const wrap = document.createElement('div');
    wrap.className = 'ev2-cp-field';
    wrap.dataset.role = 'image';
    const src = el.getAttribute('src') || '';
    const file = decodeURIComponent((src.split('/').pop() || '').split('?')[0]) || 'image';
    const alt = el.getAttribute('alt') || '';
    wrap.innerHTML = `<div class="ev2-cp-field-top"><span class="ev2-cp-kind is-small">${icon('image')}</span><label data-role-label>Image</label>
            <span class="ev2-cp-meta"><button type="button" class="ev2-cp-open" data-action="open">Open</button></span></div>
        <div class="ev2-cp-mini"><img src="${esc(src)}" alt=""><div><b>${esc(file)}</b><span class="${alt ? '' : 'is-missing'}">${esc(alt || 'No alt text')}</span></div>
            <button type="button" class="ev2-cp-btn" data-action="replace">Replace</button></div>`;
    wrap.querySelector('[data-action="open"]').addEventListener('click', () => select(el));
    wrap.querySelector('[data-action="replace"]').addEventListener('click', () => { select(el); setTimeout(() => events.emit('image-picker:open', {}), 0); });
    return wrap;
}

// ── Views ──

function renderItemsForm(container, scope) {
    const { items, components } = sectionOutline(scope);
    const body = document.createElement('div');
    body.className = 'ev2-cp-body';
    if (!items.length && !components.length) {
        body.innerHTML = '<p class="ev2-cp-help">Nothing to write here. Pick a text, button or photo on the page.</p>';
    } else {
        body.innerHTML = '<p class="ev2-cp-help">Everything you can write here. Hover a field to see it on the page.</p>';
    }
    for (const comp of components) {
        const row = document.createElement('button');
        row.type = 'button';
        row.className = 'ev2-cp-comp';
        row.innerHTML = `<span class="ev2-cp-kind is-small">${icon('block')}</span><b>${comp.kind === 'gallery' ? 'Gallery' : 'Slider'}</b><span>${comp.count} ${comp.kind === 'gallery' ? 'photos' : 'slides'}</span><span class="ev2-cp-open">Edit</span>`;
        row.addEventListener('click', () => select(comp.root));
        hoverLink(row, comp.root);
        body.appendChild(row);
    }
    for (const { el, role } of items) {
        const field = role === 'image' ? imageSummaryField(el)
            : (role === 'button' || role === 'link') ? linkSummaryField(el, role)
                : textField(el, role, { compact: true });
        hoverLink(field, el);
        body.appendChild(field);
    }
    container.appendChild(body);
}

function renderTextView(container, el, role) {
    const body = document.createElement('div');
    body.className = 'ev2-cp-body';
    body.appendChild(textField(el, role));
    const tag = el.tagName.toLowerCase();
    if (/^h[1-6]$|^p$/.test(tag)) {
        const level = document.createElement('div');
        level.className = 'ev2-cp-field';
        level.innerHTML = `<div class="ev2-cp-field-top"><label>Level</label></div>
            <div class="ev2-cp-seg ev2-cp-level" role="group" aria-label="Heading level">${LEVELS.map(([t, l]) =>
                `<button type="button" data-tag="${t}" class="${t === tag ? 'is-on' : ''}">${l}</button>`).join('')}</div>
            <div class="ev2-cp-help ev2-cp-level-note">${tag === 'p' ? 'Make it a heading to give the page structure.' : 'Changes in every language.'}</div>`;
        level.querySelectorAll('[data-tag]').forEach(b => b.addEventListener('click', () => {
            if (b.dataset.tag === tag) return;
            const others = [...document.querySelectorAll('.editor-v2-content h1')]
                .filter(h => h !== el && !h.closest('.splide__slide--clone') && !isRuntimeInjected(h));
            const go = () => retagElement(getCssSelector(el), b.dataset.tag);
            if (b.dataset.tag !== 'h1' || !others.length) { go(); return; }
            confirmDialog({ title: 'Make this a second H1?', confirmLabel: 'Make it H1',
                message: 'This page already has an H1. Search engines expect one per page.' })
                .then(ok => { if (ok) go(); });
        }));
        body.appendChild(level);
    }
    appendSiblings(body, el);
    if (!hasFormatting(el)) {
        const tip = document.createElement('p');
        tip.className = 'ev2-cp-help';
        tip.textContent = 'Bold, italic and links: double-click the text on the page.';
        body.appendChild(tip);
    }
    container.appendChild(body);
}

function appendSiblings(body, el) {
    const scope = findCardScope(el) || el.parentElement;
    if (!scope) return;
    const peers = sectionOutline(scope).items.filter(i => i.el !== el);
    if (!peers.length) return;
    const wrap = document.createElement('div');
    wrap.className = 'ev2-cp-field';
    wrap.innerHTML = '<div class="ev2-cp-field-top"><label>Also in this block</label></div><div class="ev2-cp-chips"></div>';
    const chips = wrap.querySelector('.ev2-cp-chips');
    for (const { el: peer, role } of peers) {
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'ev2-cp-chip';
        chip.textContent = ROLE_LABELS[role];
        chip.title = plain(peer).slice(0, 80);
        chip.addEventListener('click', () => select(peer));
        hoverLink(chip, peer);
        chips.appendChild(chip);
    }
    body.appendChild(wrap);
}

function renderLinkView(container, el, role) {
    const body = document.createElement('div');
    body.className = 'ev2-cp-body';
    const label = textField(el, role);
    label.querySelector('[data-role-label]').textContent = 'Label';
    body.appendChild(label);

    const parsed = parseHref(el.getAttribute('href'));
    const goes = document.createElement('div');
    goes.className = 'ev2-cp-field';
    goes.innerHTML = `<div class="ev2-cp-field-top"><label>Goes to</label></div>
        <div class="ev2-cp-seg ev2-cp-kinds" role="group" aria-label="Link type">${KINDS.map(([k, l]) =>
            `<button type="button" data-kind="${k}" class="${k === parsed.kind ? 'is-on' : ''}">${l}</button>`).join('')}</div>
        <div class="ev2-cp-linkbody"></div>`;
    body.appendChild(goes);
    const linkBody = goes.querySelector('.ev2-cp-linkbody');
    const save = (href) => {
        setAttr(el, 'href', href);
        const raw = body.querySelector('.ev2-cp-raw');
        if (raw) raw.value = href;
        const resolved = linkBody.querySelector('.ev2-cp-resolved');
        if (resolved) resolved.textContent = href || '—';
    };
    const show = async (kind) => {
        goes.querySelectorAll('[data-kind]').forEach(b => b.classList.toggle('is-on', b.dataset.kind === kind));
        const current = parseHref(el.getAttribute('href'));
        const same = current.kind === kind;
        if (kind === 'page' || kind === 'section') {
            linkBody.innerHTML = '<div class="ev2-cp-help">Loading pages…</div>';
            const pages = await linkTargets();
            const here = config().pageId;
            const options = kind === 'page'
                ? pages.map(p => [p.url, p.title])
                : pages.flatMap(p => p.sections.map(s => [p.id === here ? `#${s.name}` : `${p.url}#${s.name}`, `${p.title} › ${s.label}`]));
            const value = same ? current.value : '';
            linkBody.innerHTML = `<select class="ev2-cp-input" aria-label="${kind === 'page' ? 'Page' : 'Section'}">
                    <option value="">Choose…</option>${options.map(([v, l]) => `<option value="${esc(v)}" ${v === value ? 'selected' : ''}>${esc(l)}</option>`).join('')}
                </select><div class="ev2-cp-resolved">${esc(value || '—')}</div>
                <div class="ev2-cp-help">The link points to each language's own page.</div>`;
            linkBody.querySelector('select').addEventListener('change', e => { if (e.target.value) save(e.target.value); });
        } else if (kind === 'whatsapp') {
            linkBody.innerHTML = `<input class="ev2-cp-input" placeholder="+351 912 345 678" aria-label="WhatsApp number" value="${esc(same ? current.value : '')}">
                <input class="ev2-cp-input" placeholder="First message (optional)" aria-label="First message" value="${esc(same ? current.message || '' : '')}">
                <div class="ev2-cp-resolved">${esc(same ? el.getAttribute('href') : '—')}</div>`;
            const [num, msg] = linkBody.querySelectorAll('input');
            const update = () => { if (num.value.replace(/\D/g, '')) save(buildHref('whatsapp', num.value, msg.value)); };
            num.addEventListener('input', update);
            msg.addEventListener('input', update);
        } else {
            const placeholder = { phone: '+351 912 345 678', email: 'geral@example.pt', url: 'https://…' }[kind];
            linkBody.innerHTML = `<input class="ev2-cp-input" placeholder="${placeholder}" aria-label="${kind}" value="${esc(same ? current.value : '')}">
                <div class="ev2-cp-resolved">${esc(same ? el.getAttribute('href') : '—')}</div>`;
            const input = linkBody.querySelector('input');
            input.addEventListener('input', () => { if (input.value.trim()) save(buildHref(kind, input.value)); });
        }
    };
    goes.querySelectorAll('[data-kind]').forEach(b => b.addEventListener('click', () => show(b.dataset.kind)));
    show(parsed.kind);

    if (el.tagName === 'A') {
        const newTab = document.createElement('div');
        newTab.className = 'ev2-cp-toggle';
        const on = opensInNewTab(el);
        newTab.innerHTML = `<span>Open in a new tab</span><button type="button" class="ev2-cp-switch" data-action="new-tab" aria-pressed="${on}" aria-label="Open in a new tab"></button>`;
        newTab.querySelector('button').addEventListener('click', (e) => {
            const next = e.currentTarget.getAttribute('aria-pressed') !== 'true';
            e.currentTarget.setAttribute('aria-pressed', String(next));
            setNewTab(el, next);
        });
        body.appendChild(newTab);
    }
    const adv = document.createElement('details');
    adv.className = 'ev2-cp-adv';
    adv.innerHTML = `<summary>Advanced</summary><label class="ev2-cp-help" for="ev2-cp-raw">Link as stored</label>
        <input id="ev2-cp-raw" class="ev2-cp-input ev2-cp-raw is-mono" value="${esc(el.getAttribute('href') || '')}">`;
    adv.querySelector('input').addEventListener('change', e => save(e.target.value.trim()));
    body.appendChild(adv);
    container.appendChild(body);
}

function renderImageView(container, el) {
    const body = document.createElement('div');
    body.className = 'ev2-cp-body';
    const src = el.getAttribute('src') || '';
    const section = el.closest('[data-section]');
    const card = document.createElement('div');
    card.className = 'ev2-cp-imgcard';
    card.innerHTML = `<div class="ev2-cp-imgprev"><img src="${esc(src)}" alt=""><span class="ev2-cp-size"></span></div>
        <div class="ev2-cp-imgacts">
            <button type="button" class="ev2-cp-btn is-primary" data-picker="library">Replace</button>
            <button type="button" class="ev2-cp-btn" data-picker="upload">Upload</button>
            ${config().unsplashEnabled ? '<button type="button" class="ev2-cp-btn" data-picker="unsplash">Unsplash</button>' : ''}
            ${section && isPlaceholder(el) ? `<button type="button" class="ev2-cp-btn" data-action="generate">${icon('spark')}Generate</button>` : ''}
        </div>`;
    const size = card.querySelector('.ev2-cp-size');
    const showQuality = () => {
        const q = imageQuality(el);
        if (q.state === 'unknown') { size.textContent = isPlaceholder(el) ? 'Placeholder' : ''; return; }
        size.textContent = `${q.natural.w} × ${q.natural.h} · ${q.state === 'sharp' ? 'sharp at this size' : `may look soft (shown at ${q.shown} px)`}`;
        size.classList.toggle('is-soft', q.state === 'soft');
    };
    showQuality();
    if (!el.complete) el.addEventListener('load', showQuality, { once: true });
    card.querySelectorAll('[data-picker]').forEach(b => b.addEventListener('click', () => events.emit('image-picker:open', { tab: b.dataset.picker })));
    card.querySelector('[data-action="generate"]')?.addEventListener('click', () => events.emit('process-images:open', { section: section.dataset.section }));
    body.appendChild(card);

    const alt = document.createElement('div');
    alt.className = 'ev2-cp-field';
    alt.dataset.role = 'image';
    const value = el.getAttribute('alt') || '';
    alt.innerHTML = `<div class="ev2-cp-field-top"><label for="ev2-cp-alt">Alt text</label><span class="ev2-cp-meta">${value.length} / ${ALT_MAX}</span></div>
        <textarea id="ev2-cp-alt" class="ev2-cp-input ev2-cp-alt" rows="2" placeholder="What the photo shows, for people who can't see it">${esc(value)}</textarea>
        <div class="ev2-cp-row">${config().aiEnabled ? `<button type="button" class="ev2-cp-btn" data-action="describe">${icon('spark')}Describe the photo</button>` : ''}
            <span class="ev2-cp-help">Read by screen readers and Google.</span></div>
        <div class="ev2-cp-other"></div>`;
    const area = alt.querySelector('textarea');
    const meta = alt.querySelector('.ev2-cp-meta');
    const onAlt = () => { setAttr(el, 'alt', area.value); meta.textContent = `${area.value.length} / ${ALT_MAX}`; meta.classList.toggle('is-over', area.value.length > ALT_MAX); };
    area.addEventListener('input', onAlt);
    otherLanguages(alt.querySelector('.ev2-cp-other'), el);
    alt.querySelector('[data-action="describe"]')?.addEventListener('click', async (e) => {
        const btn = e.currentTarget;
        btn.disabled = true;
        btn.lastChild.textContent = 'Looking at the photo…';
        try {
            const res = await api.post('/describe-image/', { ...editableParams(), selector: getCssSelector(el), src: el.getAttribute('src') });
            if (!res.success) throw new Error(res.error);
            area.value = res.current || area.value;
            onAlt();
            copiesPromise = null;
            otherLanguages(alt.querySelector('.ev2-cp-other'), el);
            btn.lastChild.textContent = res.saved_languages?.length ? `Done · also saved ${res.saved_languages.join(', ').toUpperCase()}` : 'Done';
        } catch (err) {
            btn.lastChild.textContent = 'Describe the photo';
            events.emit('toast:show', { text: `Couldn't describe the photo: ${err.message || err}` });
        }
        btn.disabled = false;
    });
    body.appendChild(alt);

    const focus = document.createElement('div');
    focus.className = 'ev2-cp-field';
    const currentFocus = focusPointOf(el);
    focus.innerHTML = `<div class="ev2-cp-field-top"><label>Focus point</label></div>
        <div class="ev2-cp-seg" role="group" aria-label="Focus point">${FOCUS.map(([k, l]) =>
            `<button type="button" data-focus="${k}" class="${k === currentFocus ? 'is-on' : ''}">${l}</button>`).join('')}</div>
        <div class="ev2-cp-help">Which part stays visible when the photo is cropped.</div>`;
    focus.querySelectorAll('[data-focus]').forEach(b => b.addEventListener('click', () => {
        setFocusPoint(el, b.dataset.focus);
        focus.querySelectorAll('[data-focus]').forEach(x => x.classList.toggle('is-on', x === b));
    }));
    body.appendChild(focus);

    const adv = document.createElement('details');
    adv.className = 'ev2-cp-adv';
    adv.innerHTML = `<summary>Advanced</summary><label class="ev2-cp-help" for="ev2-cp-src">Image address</label>
        <input id="ev2-cp-src" class="ev2-cp-input is-mono" value="${esc(src)}">`;
    adv.querySelector('input').addEventListener('change', e => {
        const value = e.target.value.trim();
        setAttr(el, 'src', value);
        const anchor = el.parentElement;
        if (anchor?.tagName === 'A' && anchor.hasAttribute('data-lightbox')) setAttr(anchor, 'href', value);
    });
    body.appendChild(adv);
    container.appendChild(body);
}

function renderNothingSelected(container) {
    const sections = [...document.querySelectorAll('.editor-v2-content [data-section]')];
    const body = document.createElement('div');
    body.className = 'ev2-cp-body';
    body.innerHTML = '<p class="ev2-cp-help">Click anything on the page to edit it, or start from a section:</p>';
    for (const s of sections) {
        const row = document.createElement('button');
        row.type = 'button';
        row.className = 'ev2-cp-section-row';
        row.innerHTML = `<span class="ev2-cp-kind is-section">${icon('section')}</span><span><b>${esc(sectionLabel(s.dataset.section))}</b><span>${esc(describeSection(s))}</span></span>`;
        row.addEventListener('click', () => select(s));
        hoverLink(row, s);
        body.appendChild(row);
    }
    container.appendChild(body);
}

/** Render the Content tab for `el` (or the page's sections when nothing is selected) into `container`. */
export function renderContentPanel(container, el) {
    listenOnce();
    document.querySelectorAll('.ev2-cp-hot').forEach(n => n.classList.remove('ev2-cp-hot'));
    container.innerHTML = '';
    const root = document.createElement('div');
    root.className = 'ev2-cp';
    container.appendChild(root);
    shown = { container, el, root };
    if (!el) { renderNothingSelected(root); return; }
    const role = roleOf(el);
    root.innerHTML = header(el, role);
    root.querySelector('[data-select="section"]')?.addEventListener('click', () => select(el.closest('[data-section]')));
    if (role === 'section' || role === 'block') renderItemsForm(root, el);
    else if (role === 'image') renderImageView(root, el);
    else if (role === 'button' || role === 'link') renderLinkView(root, el, role);
    else renderTextView(root, el, role);
}
