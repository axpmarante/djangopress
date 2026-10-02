/**
 * Images tab: every photo on the page, grouped by section, with what needs
 * fixing — missing alt text, AI placeholders still waiting, photos too small
 * for the size they are shown at. Click a photo to select it on the page and
 * fix it here (alt, replace, describe) without opening the full picker.
 * Slider clones, decorative duplicates and editor-skip images are left out
 * (getEditableImages); the same photo twice in a section shows once, ×N.
 */
import { events } from '../lib/events.js';
import { api } from '../lib/api.js';
import { $, getContentWrapper, getCssSelector, getEditableImages, resolveSelector } from '../lib/dom.js';
import { imageQuality, isPlaceholder } from '../lib/content-model.js';

const config = () => window.EDITOR_CONFIG || {};
const FILTERS = [['all', 'All'], ['alt', 'No alt text'], ['placeholder', 'Placeholder'], ['low', 'Low resolution']];
let activeTab = null;
let unsubs = [];
let filter = 'all';
let openSelector = null;
let reloadTimer = null;

function esc(s) { return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
function label(name) { const s = (name || '').replace(/[-_]+/g, ' ').trim(); return s.charAt(0).toUpperCase() + s.slice(1); }

function flagsOf(img) {
    const flags = [];
    if (!(img.getAttribute('alt') || '').trim()) flags.push('alt');
    if (isPlaceholder(img)) flags.push('placeholder');
    else if (imageQuality(img).state === 'soft') flags.push('low');
    return flags;
}

function discover() {
    const wrapper = getContentWrapper();
    if (!wrapper) return [];
    const groups = [];
    for (const section of wrapper.querySelectorAll('[data-section]')) {
        const seen = new Map();
        for (const img of getEditableImages(section)) {
            const src = (img.getAttribute('src') || '').trim();
            if (!src) continue;
            const entry = seen.get(src);
            if (entry) { entry.count += 1; continue; }
            seen.set(src, { img, src, selector: getCssSelector(img) || '', count: 1, flags: flagsOf(img) });
        }
        if (seen.size) groups.push({ section: section.getAttribute('data-section'), entries: [...seen.values()] });
    }
    return groups;
}

function select(img) {
    events.emit('selection:request', img);
    img.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function setAlt(img, value) {
    const oldValue = img.getAttribute('alt') || '';
    if (oldValue === value) return;
    img.setAttribute('alt', value);
    events.emit('change:attribute', { type: 'attribute', selector: getCssSelector(img) || '', attribute: 'alt', value, oldValue, tagName: 'img' });
}

function detailHtml(entry) {
    const q = imageQuality(entry.img);
    const size = q.state === 'unknown' ? (isPlaceholder(entry.img) ? 'AI placeholder' : '') :
        `${q.natural.w} × ${q.natural.h} · shown at ${q.shown} px${q.state === 'soft' ? ' · may look soft' : ''}`;
    return `<div class="ev2-mp-detail">
        <div class="ev2-mp-detail-top"><img src="${esc(entry.src)}" alt=""><div><b>${esc(decodeURIComponent((entry.src.split('/').pop() || '').split('?')[0]))}</b><span>${esc(size)}</span></div></div>
        <label class="ev2-mp-help" for="ev2-mp-alt">Alt text</label>
        <input id="ev2-mp-alt" class="ev2-mp-input" value="${esc(entry.img.getAttribute('alt') || '')}" placeholder="What the photo shows, for people who can't see it">
        <div class="ev2-mp-acts">
            <button type="button" class="ev2-mp-btn is-primary" data-action="replace">Replace…</button>
            ${config().aiEnabled && !isPlaceholder(entry.img) ? '<button type="button" class="ev2-mp-btn" data-action="describe">Describe the photo</button>' : ''}
            <button type="button" class="ev2-mp-btn is-ghost" data-action="show">Show on page</button>
        </div></div>`;
}

/** Render the Images tab into `container`. */
export function renderImagesPanel(container) {
    const groups = discover();
    const all = groups.flatMap(g => g.entries);
    if (!all.length) {
        container.innerHTML = '<p class="ev2-placeholder ev2-empty-state">No editable images on this page.</p>';
        return;
    }
    const count = (f) => (f === 'all' ? all.length : all.filter(e => e.flags.includes(f)).length);
    const chips = FILTERS.map(([f, l]) => {
        const n = count(f);
        if (f !== 'all' && !n) return '';
        return `<button type="button" class="ev2-mp-chip ${f === 'all' ? '' : 'is-warn'} ${filter === f ? 'is-on' : ''}" data-filter="${f}">${l} <b>${n}</b></button>`;
    }).join('');
    const parts = [];
    for (const group of groups) {
        const entries = group.entries.filter(e => filter === 'all' || e.flags.includes(filter));
        if (!entries.length) continue;
        const placeholders = group.entries.filter(e => e.flags.includes('placeholder')).length;
        parts.push(`<div class="ev2-mp-group"><div class="ev2-mp-group-head"><b>${esc(label(group.section))}</b>
            <span>${group.entries.length} ${group.entries.length === 1 ? 'photo' : 'photos'}</span>
            ${placeholders ? `<button type="button" class="ev2-mp-btn" data-generate="${esc(group.section)}">Generate ${placeholders} placeholder${placeholders === 1 ? '' : 's'}</button>` : ''}
            </div><div class="ev2-mp-grid">`);
        for (const entry of entries) {
            const names = { alt: 'No alt', low: 'Low res', placeholder: 'Placeholder' };
            const flag = entry.flags.length ? `<span class="ev2-mp-flags">${entry.flags.map(f =>
                `<span class="ev2-mp-flag ${f === 'placeholder' ? 'is-ph' : ''}">${names[f]}</span>`).join('')}</span>` : '';
            const alt = entry.img.getAttribute('alt') || '';
            const isOpen = openSelector === entry.selector;
            parts.push(`<button type="button" class="ev2-mp-thumb ${isOpen ? 'is-on' : ''}" data-selector="${esc(entry.selector)}" title="${esc(alt || 'No alt text')}">
                <span class="ev2-mp-img"><img src="${esc(entry.src)}" alt="" loading="lazy">${flag}${entry.count > 1 ? `<span class="ev2-mp-dup">×${entry.count}</span>` : ''}</span>
                <span class="ev2-mp-cap ${alt ? '' : 'is-missing'}">${esc(alt || 'No alt text')}</span></button>`);
            if (isOpen) parts.push(detailHtml(entry));
        }
        parts.push('</div></div>');
    }
    container.innerHTML = `<div class="ev2-mp">
        <div class="ev2-mp-head"><div class="ev2-mp-sum"><h2>Images on this page</h2><span class="ev2-mp-total">${all.length}</span></div>
            <div class="ev2-mp-chips">${chips}</div></div>
        <div class="ev2-mp-body">${parts.join('') || '<p class="ev2-mp-help">Nothing to fix here.</p>'}</div></div>`;

    container.querySelectorAll('.ev2-mp-chip').forEach(c => c.addEventListener('click', () => {
        filter = c.dataset.filter;
        openSelector = null;
        renderImagesPanel(container);
    }));
    container.querySelectorAll('[data-generate]').forEach(b => b.addEventListener('click', () => events.emit('process-images:open', { section: b.dataset.generate })));
    container.querySelectorAll('.ev2-mp-thumb').forEach(t => t.addEventListener('click', () => {
        const img = resolveSelector(t.dataset.selector);
        openSelector = openSelector === t.dataset.selector ? null : t.dataset.selector;
        if (img) {
            select(img);
            img.classList.remove('ev2-image-flash');
            void img.offsetWidth;
            img.classList.add('ev2-image-flash');
            setTimeout(() => img.classList.remove('ev2-image-flash'), 1300);
        }
        renderImagesPanel(container);
    }));
    const detail = container.querySelector('.ev2-mp-detail');
    if (detail) {
        const img = resolveSelector(openSelector);
        const input = detail.querySelector('input');
        input.addEventListener('input', () => { if (img) setAlt(img, input.value); });
        detail.querySelector('[data-action="replace"]').addEventListener('click', () => { if (img) { select(img); setTimeout(() => events.emit('image-picker:open', {}), 0); } });
        detail.querySelector('[data-action="show"]').addEventListener('click', () => img?.scrollIntoView({ behavior: 'smooth', block: 'center' }));
        detail.querySelector('[data-action="describe"]')?.addEventListener('click', async (e) => {
            const btn = e.currentTarget;
            btn.disabled = true;
            btn.textContent = 'Looking at the photo…';
            try {
                const params = { page_id: config().pageId, selector: openSelector, src: img?.getAttribute('src') };
                if (config().contentTypeId) { params.content_type_id = config().contentTypeId; params.object_id = config().objectId; }
                const res = await api.post('/describe-image/', params);
                if (!res.success) throw new Error(res.error);
                input.value = res.current || input.value;
                if (img) setAlt(img, input.value);
                btn.textContent = res.saved_languages?.length ? `Done · also saved ${res.saved_languages.join(', ').toUpperCase()}` : 'Done';
            } catch (err) {
                btn.textContent = 'Describe the photo';
                events.emit('toast:show', { text: `Couldn't describe the photo: ${err.message || err}` });
            }
            btn.disabled = false;
        });
    }
    // Low resolution is only known once a photo has loaded: count again when the stragglers arrive.
    for (const entry of all) {
        if (!entry.img.complete) entry.img.addEventListener('load', scheduleRender, { once: true });
    }
}

function scheduleRender() {
    clearTimeout(reloadTimer);
    reloadTimer = setTimeout(() => {
        const c = $('#ev2-tab-content');
        if (activeTab === 'images' && c && !c.contains(document.activeElement)) renderImagesPanel(c);
    }, 300);
}

function render() {
    const c = $('#ev2-tab-content');
    if (c) renderImagesPanel(c);
}

function onTabChanged(tab) {
    activeTab = tab;
    if (tab === 'images') render();
}

export function init() {
    unsubs.push(events.on('sidebar:tab-changed', onTabChanged));
    unsubs.push(events.on('change:attribute', (data) => {
        if (activeTab === 'images' && data && data.attribute === 'src' && data.tagName === 'img') render();
    }));
}

export function destroy() {
    unsubs.forEach(fn => fn());
    unsubs = [];
    activeTab = null;
    filter = 'all';
    openSelector = null;
}
