/**
 * Component panel — a card at the top of the Content tab for a recognised
 * slider, text slider or lightbox gallery: item list (drag to reorder),
 * per-item fields, add / remove, slider settings. Every change is one
 * POST /component/ applied server-side to every language copy; the returned
 * HTML replaces the component in place (full reload as the fallback).
 */
import { events } from '../lib/events.js';
import { api } from '../lib/api.js';
import { getCssSelector, resolveSelector } from '../lib/dom.js';
import { duplicateElement } from '../lib/structural.js';
import {
    findComponent, itemsOf, itemFields, componentLabel, minItems, readSliderOptions,
    settingsFromOptions, settingsDiff, canSwapInPlace,
} from '../lib/components.js';
import { getPendingCount, saveNow } from './changes.js';

const AFTER_RELOAD_KEY = 'ev2-after-reload';
const expanded = new Map();          // root selector -> open item index
let settingsOpen = false;
let settingsTimer = null;
let pendingSettings = null;       // {rootSel, kind, opts, before, after} not yet sent
let busy = false;

const cfg = () => window.EDITOR_CONFIG || {};
const esc = (s) => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

// --- rendering ---

export function prependComponentCard(container, selectedEl) {
    const comp = selectedEl ? findComponent(selectedEl) : null;
    if (!comp) return false;
    const rootSel = getCssSelector(comp.root);
    if (!rootSel) return false;
    comp.rootSel = rootSel;
    const items = itemsOf(comp);
    const current = items.findIndex(it => it === selectedEl || it.contains(selectedEl));
    if (current >= 0) expanded.set(rootSel, current);
    const open = expanded.has(rootSel) ? Math.min(expanded.get(rootSel), items.length - 1) : -1;
    const { title, noun } = componentLabel(comp);

    const card = document.createElement('div');
    card.className = 'ev2-comp-card';
    card.innerHTML = `
        <div class="ev2-comp-head"><span class="ev2-comp-title">${esc(title)}</span><span class="ev2-comp-count">${items.length} ${esc(noun)}</span></div>
        <ol class="ev2-comp-list">${items.map((it, i) => rowHtml(comp, it, i, i === open, items.length)).join('')}</ol>
        <div class="ev2-comp-add">${addHtml(comp)}</div>
        ${comp.kind === 'gallery' ? '' : settingsHtml(comp)}
        <div class="ev2-comp-status" aria-live="polite"></div>`;
    container.insertBefore(card, container.firstChild);
    bindCard(card, comp, rootSel);
    return true;
}

function rowHtml(comp, item, i, isOpen, n) {
    const f = itemFields(item);
    const thumb = f.image
        ? `<img class="ev2-comp-thumb" src="${esc(f.image.getAttribute('src'))}" alt="">`
        : `<span class="ev2-comp-thumb ev2-comp-thumb-text">${i + 1}</span>`;
    // Text sliders are known by their first line; image items by caption / alt (overlay labels like "Ver" say nothing).
    const imageLabel = f.link?.getAttribute('data-alt') || f.image?.getAttribute('alt');
    const summary = (comp.kind === 'text-slider' ? f.texts[0]?.value || imageLabel : imageLabel || f.texts[0]?.value) || `Item ${i + 1}`;
    return `<li class="ev2-comp-row${isOpen ? ' is-open' : ''}" data-index="${i}">
        <div class="ev2-comp-row-head" data-act="open">
            <span class="ev2-comp-grip" title="Drag to reorder" aria-hidden="true">⋮⋮</span>${thumb}
            <span class="ev2-comp-summary">${esc(summary.slice(0, 70))}</span>
        </div>
        ${isOpen ? `<div class="ev2-comp-fields">${fieldsHtml(comp, f, i, n)}</div>` : ''}
    </li>`;
}

function field(key, label, value, multiline) {
    const input = multiline
        ? `<textarea data-field="${key}" rows="${Math.min(6, Math.max(2, Math.ceil(value.length / 38)))}">${esc(value)}</textarea>`
        : `<input type="text" data-field="${key}" value="${esc(value)}">`;
    return `<label class="ev2-comp-field"><span>${esc(label)}</span>${input}</label>`;
}

function fieldsHtml(comp, f, i, n) {
    let h = '';
    if (f.image) {
        h += `<div class="ev2-comp-image"><img src="${esc(f.image.getAttribute('src'))}" alt="">
              <button type="button" class="ev2-btn-sm ev2-btn-sm-primary" data-act="replace">Replace image</button></div>`;
        h += field('alt', 'Alt text (describes the image)', f.image.getAttribute('alt') || '', false);
    }
    if (f.link && comp.kind === 'gallery') {
        h += field('caption', 'Caption (shown when the image is enlarged)', f.link.getAttribute('data-alt') || '', false);
    }
    f.texts.forEach((t, k) => {
        h += t.editable
            ? field(`text-${k}`, t.label, t.value, true)
            : `<div class="ev2-comp-field"><span>${esc(t.label)}</span><p class="ev2-comp-readonly">${esc(t.value)}</p>
               <p class="ev2-comp-hint">Formatted text — double-click it on the page to edit.</p></div>`;
    });
    const atMin = n <= minItems(comp);
    h += `<div class="ev2-comp-row-actions">
        <button type="button" class="ev2-btn-sm" data-act="up" ${i === 0 ? 'disabled' : ''}>↑ Earlier</button>
        <button type="button" class="ev2-btn-sm" data-act="down" ${i === n - 1 ? 'disabled' : ''}>↓ Later</button>
        <button type="button" class="ev2-btn-sm ev2-btn-sm-danger" data-act="remove" ${atMin ? 'disabled title="This is the minimum number of items"' : ''}>Remove</button>
    </div>`;
    return h;
}

function addHtml(comp) {
    if (comp.kind === 'text-slider') {
        return `<button type="button" class="ev2-btn-sm ev2-btn-sm-primary" data-act="add-text">+ Add slide</button>
                <div class="ev2-comp-addform" hidden></div>`;
    }
    return `<button type="button" class="ev2-btn-sm ev2-btn-sm-primary" data-act="add-images">+ Add images</button>`;
}

function settingsHtml(comp) {
    const { ok, opts } = readSliderOptions(comp.root);
    if (!ok) return `<div class="ev2-comp-settings"><p class="ev2-comp-hint">These slider settings can't be edited here.</p></div>`;
    // A change not yet sent keeps showing across a re-render.
    const s = pendingSettings?.rootSel === comp.rootSel ? pendingSettings.after : settingsFromOptions(opts);
    const check = (k, label) => `<label class="ev2-comp-check"><input type="checkbox" data-set="${k}" ${s[k] ? 'checked' : ''}> ${label}</label>`;
    const num = (k, label, min, max) => `<label class="ev2-comp-num"><span>${label}</span><input type="number" data-set="${k}" min="${min}" max="${max}" value="${s[k]}"></label>`;
    const opt = (v, label, cur) => `<option value="${v}" ${cur === v ? 'selected' : ''}>${label}</option>`;
    return `<details class="ev2-comp-settings" ${settingsOpen ? 'open' : ''}>
        <summary>Slider settings</summary>
        <label class="ev2-comp-num"><span>Effect</span><select data-set="effect">${opt('slide', 'Slide', s.effect)}${opt('fade', 'Fade', s.effect)}</select></label>
        ${check('loop', 'Loop back to the start')}
        ${check('autoplay', 'Play automatically')}
        ${num('seconds', 'Seconds per slide', 1, 30)}
        <label class="ev2-comp-num"><span>Transition</span><select data-set="speed">${opt('slow', 'Slow', s.speed)}${opt('normal', 'Normal', s.speed)}${opt('fast', 'Fast', s.speed)}</select></label>
        ${check('arrows', 'Arrows')}
        ${check('dots', 'Dots')}
        ${check('pauseOnHover', 'Pause on hover')}
        ${s.multi && s.effect !== 'fade' ? `<div class="ev2-comp-perrow"><span>Items per row</span>
            ${num('perPage', 'Desktop', 1, 8)}${num('tablet', 'Tablet', 1, 8)}${num('mobile', 'Mobile', 1, 8)}</div>` : ''}
    </details>`;
}

// --- interaction ---

function afterIndex(rootSel, n) {
    const i = expanded.get(rootSel);
    return Number.isInteger(i) && i >= 0 && i < n ? i : n - 1;
}

function bindCard(card, comp, rootSel) {
    card.addEventListener('click', (e) => {
        const btn = e.target.closest('[data-act]');
        if (!btn || btn.disabled || busy) return;
        const row = btn.closest('.ev2-comp-row');
        const i = row ? Number(row.dataset.index) : null;
        const n = itemsOf(comp).length;
        switch (btn.dataset.act) {
            case 'open': return focusItem(comp, rootSel, i);
            case 'up': return move(comp, n, i, -1);
            case 'down': return move(comp, n, i, 1);
            case 'remove':
                if (confirm('Remove this item? You can undo it afterwards.')) runOp(comp, 'remove', { index: i });
                return;
            case 'replace': return pickImages(false, imgs => runOp(comp, 'replace_image', { index: i, image: imgs[0] }, i));
            case 'add-images': return pickImages(true, imgs => runOp(comp, 'add_images', { after: afterIndex(rootSel, n), images: imgs }));
            case 'add-text': return showAddForm(card, comp, rootSel);
            case 'add-text-submit': return submitAddForm(card, comp, rootSel);
            case 'add-text-cancel': card.querySelector('.ev2-comp-addform').hidden = true; return;
        }
    });
    card.addEventListener('change', (e) => {
        const input = e.target.closest('[data-field]');
        if (input) {
            const i = Number(input.closest('.ev2-comp-row').dataset.index);
            const key = input.dataset.field;
            if (key.startsWith('text-')) {
                if (!input.value.trim()) { alert("Text can't be empty — remove the item instead."); return; }
                runOp(comp, 'update_item', { index: i, texts: { [key.slice(5)]: input.value } }, i);
            } else {
                runOp(comp, 'update_item', { index: i, [key]: input.value }, i);
            }
            return;
        }
        if (e.target.closest('[data-set]')) scheduleSettings(card, comp, rootSel);
    });
    card.querySelector('details.ev2-comp-settings')?.addEventListener('toggle', (e) => { settingsOpen = e.target.open; });
    bindDrag(card, comp);
}

function bindDrag(card, comp) {
    let from = null;
    card.querySelectorAll('.ev2-comp-row').forEach(row => {
        const grip = row.querySelector('.ev2-comp-grip');
        grip.addEventListener('mousedown', () => row.setAttribute('draggable', 'true'));
        row.addEventListener('dragstart', (e) => {
            from = Number(row.dataset.index);
            row.classList.add('is-dragging');
            e.dataTransfer.effectAllowed = 'move';
        });
        row.addEventListener('dragend', () => {
            row.removeAttribute('draggable');
            row.classList.remove('is-dragging');
            card.querySelectorAll('.is-drop-target').forEach(r => r.classList.remove('is-drop-target'));
        });
        row.addEventListener('dragover', (e) => { if (from !== null) { e.preventDefault(); row.classList.add('is-drop-target'); } });
        row.addEventListener('dragleave', () => row.classList.remove('is-drop-target'));
        row.addEventListener('drop', (e) => {
            e.preventDefault();
            const to = Number(row.dataset.index);
            const start = from;
            from = null;
            if (start === null || start === to) return;
            const order = [...Array(itemsOf(comp).length).keys()];
            order.splice(start, 1);
            order.splice(to, 0, start);
            runOp(comp, 'reorder', { order }, to);
        });
    });
}

function focusItem(comp, rootSel, i) {
    const item = itemsOf(comp)[i];
    if (!item) return;
    expanded.set(rootSel, i);
    comp.root.__splide?.go(i);
    comp.root.scrollIntoView({ behavior: 'smooth', block: 'center' });
    const f = itemFields(item);
    events.emit('selection:request', f.image || f.texts[0]?.el || item);
}

function move(comp, n, i, delta) {
    const j = i + delta;
    if (j < 0 || j >= n) return;
    const order = [...Array(n).keys()];
    [order[i], order[j]] = [order[j], order[i]];
    runOp(comp, 'reorder', { order }, j);
}

function pickImages(multiple, onPick) {
    events.emit('image-picker:open', { mode: 'pick', multiple, onPick });
}

function showAddForm(card, comp, rootSel) {
    const items = itemsOf(comp);
    const after = afterIndex(rootSel, items.length);
    const f = itemFields(items[after]);
    const editable = f.texts.map((t, k) => ({ ...t, k })).filter(t => t.editable);
    if (!editable.length) {   // only formatted text: copy the slide, edit it on the page
        duplicateElement(getCssSelector(items[after]));
        return;
    }
    const form = card.querySelector('.ev2-comp-addform');
    form.innerHTML = editable.map(t => `<label class="ev2-comp-field"><span>${esc(t.label)}</span>
            <textarea data-new="${t.k}" rows="2" placeholder="${esc(t.value.slice(0, 80))}"></textarea></label>`).join('')
        + (f.image ? '<p class="ev2-comp-hint">The new slide starts with the same image — replace it after adding.</p>' : '')
        + `<div class="ev2-comp-row-actions">
             <button type="button" class="ev2-btn-sm ev2-btn-sm-primary" data-act="add-text-submit">Add</button>
             <button type="button" class="ev2-btn-sm" data-act="add-text-cancel">Cancel</button></div>`;
    form.hidden = false;
    form.querySelector('textarea')?.focus();
}

function submitAddForm(card, comp, rootSel) {
    const texts = {};
    for (const ta of card.querySelectorAll('[data-new]')) {
        if (!ta.value.trim()) { alert('Fill in every field.'); ta.focus(); return; }
        texts[ta.dataset.new] = ta.value.trim();
    }
    runOp(comp, 'add_text_item', { after: afterIndex(rootSel, itemsOf(comp).length), texts });
}

function readSettingsForm(card, s) {
    for (const key of Object.keys(s)) {
        const input = card.querySelector(`[data-set="${key}"]`);
        if (!input) continue;
        if (input.type === 'checkbox') s[key] = input.checked;
        else if (input.type === 'number') {
            const v = parseInt(input.value, 10);
            s[key] = Number.isFinite(v) ? Math.min(Number(input.max), Math.max(Number(input.min), v)) : s[key];
        } else s[key] = input.value;
    }
    return s;
}

/** Record the change now (so a re-render or a running operation can't lose it); send it 600 ms later. */
function scheduleSettings(card, comp, rootSel) {
    if (!pendingSettings || pendingSettings.rootSel !== rootSel) {
        const { opts } = readSliderOptions(comp.root);
        pendingSettings = { rootSel, kind: comp.kind, opts, before: settingsFromOptions(opts) };
    }
    pendingSettings.after = readSettingsForm(card, { ...(pendingSettings.after || pendingSettings.before) });
    clearTimeout(settingsTimer);
    settingsTimer = setTimeout(flushSettings, 600);
}

function flushSettings() {
    const p = pendingSettings;
    if (!p) return;
    if (busy) { settingsTimer = setTimeout(flushSettings, 300); return; }   // wait for the running operation
    pendingSettings = null;
    const root = resolveSelector(p.rootSel);
    if (!root) return;
    const changes = settingsDiff(p.before, p.after, p.opts);
    if (!Object.keys(changes).length) return;
    const comp = { root, kind: p.kind, rootSel: p.rootSel };
    runOp(comp, 'set_settings', { settings: changes }, afterIndex(p.rootSel, itemsOf(comp).length));
}

// --- server round trip ---

function setBusy(on, text = '') {
    busy = on;
    const card = document.querySelector('.ev2-comp-card');
    card?.classList.toggle('is-busy', on);
    const status = card?.querySelector('.ev2-comp-status');
    if (status) status.textContent = text;
}

function toastText(res) {
    let text = res.label || 'Saved';
    const up = (list) => list.map(l => l.toUpperCase()).join(', ');
    if (res.translated_languages?.length) text += ` · translated to ${up(res.translated_languages)} (review it there)`;
    if (res.untranslated_languages?.length) text += ` · not translated to ${up(res.untranslated_languages)} — edit it there`;
    return text;
}

function swapRoot(oldRoot, html) {
    const tpl = document.createElement('template');
    tpl.innerHTML = html.trim();
    const fresh = tpl.content.firstElementChild;
    if (!fresh) return null;
    try { oldRoot.__splide?.destroy(true); } catch (_) { /* already gone */ }
    oldRoot.replaceWith(fresh);
    if (fresh.classList.contains('splide') && window.Splide) {
        fresh.__splide = new window.Splide(fresh).mount();
        holdAutoplay(fresh);
    }
    return fresh;
}

async function runOp(comp, op, args, focus = null) {
    if (busy) return;
    busy = true;   // before any await: a second click must not start a parallel operation
    try {
        await runOpNow(comp, op, args, focus);
    } finally {
        setBusy(false);
    }
}

async function runOpNow(comp, op, args, focus) {
    if (getPendingCount() > 0 && !(await saveNow())) return;
    const c = cfg();
    const rootSel = comp.rootSel || getCssSelector(comp.root);
    // The card may be older than the page: an earlier operation can have swapped the root.
    const root = comp.root?.isConnected ? comp.root : resolveSelector(rootSel);
    if (!rootSel || !root) { window.location.reload(); return; }
    comp = { root, kind: comp.kind, rootSel };
    const body = {
        page_id: c.pageId, language: c.language, root: rootSel, kind: comp.kind,
        count: itemsOf(comp).length, op, args,
    };
    if (c.contentTypeId && c.objectId) { body.content_type_id = c.contentTypeId; body.object_id = c.objectId; }
    const translating = ['add_text_item', 'add_images', 'replace_image'].includes(op) && (c.languages || []).length > 1;
    setBusy(true, translating ? 'Saving and translating…' : 'Saving…');
    let res;
    try {
        res = await api.post('/component/', body);
    } catch (err) {
        alert(err.message || 'Could not save');
        return;
    }
    if (!res.success) { alert(res.error || 'Could not save'); return; }

    const index = focus ?? res.index ?? 0;
    expanded.set(rootSel, index);
    if (res.skipped_languages?.length) {
        alert(`Saved, but not in ${res.skipped_languages.join(', ').toUpperCase()}: this part of the page is different there.`);
    }
    const fresh = canSwapInPlace(res.html) ? swapRoot(comp.root, res.html) : null;
    if (!fresh) {
        try {
            sessionStorage.setItem(AFTER_RELOAD_KEY, JSON.stringify({ selector: rootSel }));
            sessionStorage.setItem('ev2-toast-pending', JSON.stringify({ label: toastText(res) }));
        } catch (_) { /* private mode */ }
        window.location.reload();
        return;
    }
    events.emit('history:refresh');
    events.emit('toast:show', { text: toastText(res), withUndo: true });
    const next = { root: fresh, kind: comp.kind };
    const item = itemsOf(next)[index];
    fresh.__splide?.go(index);
    const f = item ? itemFields(item) : null;
    events.emit('selection:request', f?.image || f?.texts[0]?.el || item || fresh);
}

// --- lifecycle ---

/** Autoplay would move the slide being edited out from under the cursor: keep it paused. */
function holdAutoplay(el) {
    const splide = el.__splide;
    if (!splide || splide.__ev2Held) return;
    splide.__ev2Held = true;
    splide.Components?.Autoplay?.pause();
    splide.on?.('autoplay:play', () => splide.Components.Autoplay.pause());
}

export function init() {
    const hold = () => document.querySelectorAll('.editor-v2-content .splide').forEach(holdAutoplay);
    hold();
    setTimeout(hold, 0);   // Splide may mount / start autoplay after the editor initialises
}

export function destroy() {
    clearTimeout(settingsTimer);
    expanded.clear();
}
