/**
 * Add a section: a popover (Describe | Paste) and a result dock at the bottom of the
 * page, so the page and the preview in the placeholder stay visible.
 *
 * Describe: three directions in the page's style (Chat pipeline, scope "new"), one
 * card each, arriving one by one; refine one into a new card; add it without a reload.
 * Paste: a section copied with "Copy section" (this site or another one), inspected by
 * /paste-section/inspect/; added as copied, or fitted to this site's design by the AI
 * first (mode "fit"). Its images are copied into the library when it is added.
 */

import { events } from '../lib/events.js';
import { api } from '../lib/api.js';
import { SSEClient } from '../lib/sse-client.js';
import { getContentWrapper } from '../lib/dom.js';
import { thumbnail } from '../lib/chat-preview.js';
import { clipMeta, looksLikeSection } from '../lib/section-clip.js';
import { getPendingCount, saveNow } from './changes.js';
import { getInsertState, previewInPlaceholder, resetPlaceholder, removePlaceholder, commitPlaceholder } from './section-inserter.js';

const config = () => window.EDITOR_CONFIG || {};
const esc = (s) => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const label = (name) => { const s = String(name || '').replace(/[-_]+/g, ' ').trim(); return s.charAt(0).toUpperCase() + s.slice(1); };
const letter = (i) => String.fromCharCode(65 + i);
const uid = () => Math.random().toString(36).slice(2, 10);
const THUMB = 190;

const DESCRIBE_CARDS = [
    { key: 'refined', name: "In the page's style" },
    { key: 'bold', name: 'Bolder' },
    { key: 'layout', name: 'Another layout' },
];
const STARTERS = [
    ['FAQ', 'Frequently asked questions: 5 questions and answers about '],
    ['Testimonials', 'Three short testimonials from customers, with name and context'],
    ['Opening hours', 'Opening hours and address, with a button to book'],
    ['Team', 'The team: photo, name and role for each person'],
    ['Gallery', 'A photo gallery from the media library'],
    ['Call to action', 'A call to action band inviting visitors to '],
];

let pop = null, dock = null;
let unsubs = [];
let tab = 'describe';
let describeText = '';
let pasteState = null;   // {clip, html, name, source, checks, images, mode} | {error}
let flow = null;         // {kind, text, insertAfter, cards, active, source, running, stream, runId, expect, refining, adding, error}

// ── DOM ──

function ensureDom() {
    pop = document.getElementById('ev2-add-pop');
    if (!pop) {
        pop = document.createElement('div');
        pop.id = 'ev2-add-pop';
        pop.className = 'ev2-add-pop';
        pop.setAttribute('role', 'dialog');
        pop.setAttribute('aria-label', 'Add a section');
        pop.hidden = true;
        document.body.appendChild(pop);
    }
    dock = document.getElementById('ev2-add-dock');
    if (!dock) {
        dock = document.createElement('div');
        dock.id = 'ev2-add-dock';
        dock.className = 'ev2-add-dock';
        dock.hidden = true;
        document.body.appendChild(dock);
    }
}

function place() {
    const rect = getContentWrapper()?.getBoundingClientRect();
    if (!rect || !pop) return;
    pop.style.top = `${Math.max(rect.top, 44) + 12}px`;
    pop.style.right = `${Math.max(16, window.innerWidth - rect.right + 16)}px`;
    dock.style.left = `${rect.left + rect.width / 2}px`;
}

function withEditableId(body) {
    const cfg = config();
    if (cfg.contentTypeId && cfg.objectId) { body.content_type_id = cfg.contentTypeId; body.object_id = cfg.objectId; }
    return body;
}

// ── Popover ──

function openPopover(nextTab = 'describe') {
    tab = nextTab;
    pop.hidden = false;
    place();
    renderPopover();
    if (tab === 'describe') loadMatches();
    pop.querySelector(tab === 'describe' ? '#ev2-add-prompt' : '#ev2-add-pastein')?.focus();
}

function renderPopover() {
    pop.dataset.tab = tab;
    const ai = !!config().aiEnabled;
    pop.innerHTML = `<div class="ev2-add-head"><h3>Add a section</h3>
        <button type="button" class="ev2-add-x" data-act="close" title="Close" aria-label="Close">×</button></div>
        <div class="ev2-add-tabs" role="tablist">
          <button type="button" role="tab" class="ev2-add-tab${tab === 'describe' ? ' is-on' : ''}" data-tab="describe" aria-selected="${tab === 'describe'}">Describe</button>
          <button type="button" role="tab" class="ev2-add-tab${tab === 'paste' ? ' is-on' : ''}" data-tab="paste" aria-selected="${tab === 'paste'}">Paste</button>
        </div>` + (tab === 'describe' ? describeBody(ai) : pasteBody(ai));
    const prompt = pop.querySelector('#ev2-add-prompt');
    if (prompt) prompt.value = describeText;
    if (tab === 'paste') afterPasteRender();
}

function describeBody(ai) {
    if (!ai) return '<div class="ev2-add-body"><p class="ev2-add-msg">Designing a section with AI needs a superuser account.</p></div>';
    return `<div class="ev2-add-body">
        <div class="ev2-add-matches" aria-live="polite"></div>
        <textarea id="ev2-add-prompt" class="ev2-add-ta" rows="3" placeholder="What should the section say or show? e.g. The chef's book: cover, a quote from him and a button to order it"></textarea>
        <div class="ev2-add-starters">${STARTERS.map(([name, text]) => `<button type="button" class="ev2-add-starter" data-text="${esc(text)}">${esc(name)}</button>`).join('')}</div>
        <p class="ev2-add-msg" hidden></p>
        <div class="ev2-add-foot"><small>Enter to design 3 options · Shift+Enter for a new line</small>
          <button type="button" class="ev2-add-btn is-primary" data-act="design">Design 3 options</button></div>
      </div>`;
}

function pasteBody(ai) {
    const p = pasteState;
    if (!p || !p.html) {
        return `<div class="ev2-add-body">
            <p class="ev2-add-note">Copy a section with right-click → <b>Copy section</b>, on this site or another DjangoPress site, then paste it here.</p>
            <textarea id="ev2-add-pastein" class="ev2-add-ta" rows="3" placeholder="Paste the copied section here (⌘V / Ctrl+V)"></textarea>
            <p class="ev2-add-msg"${p?.error ? '' : ' hidden'}>${esc(p?.error || '')}</p>
            <div class="ev2-add-foot"><small></small>
              <button type="button" class="ev2-add-btn" data-act="read-clipboard">Paste from clipboard</button></div>
          </div>`;
    }
    const from = p.source?.site ? `Copied from ${esc(p.source.site)}` : 'Pasted HTML';
    const fit = p.mode === 'fit';
    return `<div class="ev2-add-body">
        <div class="ev2-add-clip"><span class="ev2-add-clip-thumb"></span><span class="ev2-add-clip-text"><b>${esc(label(p.source?.section || p.name))}</b><small>${from}</small></span>
          <button type="button" class="ev2-add-link" data-act="clear-clip">Change</button></div>
        <label class="ev2-add-choice${fit ? '' : ' is-on'}"><input type="radio" name="ev2-paste-mode" value="copied"${fit ? '' : ' checked'}>
          <span><b>Paste as copied</b><small>Keeps its own colours and fonts. Instant.</small></span></label>
        <label class="ev2-add-choice${fit ? ' is-on' : ''}${ai ? '' : ' is-disabled'}"><input type="radio" name="ev2-paste-mode" value="fit"${fit ? ' checked' : ''}${ai ? '' : ' disabled'}>
          <span><b>Fit to this site</b><small>AI swaps colours, fonts and the type scale for this site's. Text, images and layout stay. About 20 seconds.</small></span></label>
        ${p.checks?.length ? `<ul class="ev2-add-checks">${p.checks.map(c => `<li class="${c.level === 'warn' ? 'warn' : 'ok'}">${esc(c.text)}</li>`).join('')}</ul>` : ''}
        <p class="ev2-add-msg" hidden></p>
        <div class="ev2-add-foot"><small></small>
          <button type="button" class="ev2-add-btn is-primary" data-act="paste">${fit ? 'Fit and paste' : 'Paste'}</button></div>
      </div>`;
}

function afterPasteRender() {
    const box = pop.querySelector('.ev2-add-clip-thumb');
    if (box && pasteState?.html) box.appendChild(thumbnail(pasteState.html, 92));
}

async function loadMatches() {
    const box = pop.querySelector('.ev2-add-matches');
    if (!box) return;
    const params = new URLSearchParams(withEditableId({ page_id: config().pageId || '', scope: 'section', section_name: '' }));
    try {
        const res = await api.get(`/chat/context/?${params}`);
        if (!res.success || !box.isConnected) return;
        const m = res.matches || {};
        const dots = (m.colors || []).map(c => `<span class="ev2-add-sw" style="background:${esc(c)}"></span>`).join('');
        box.innerHTML = 'Matches: ' + (dots ? `<span class="ev2-add-chip">${dots} palette</span>` : '')
            + (m.fonts || []).map(f => `<span class="ev2-add-chip">${esc(f)}</span>`).join('')
            + (m.references?.length ? `<span class="ev2-add-chip">style of: ${esc(m.references.join(', '))}</span>` : '');
    } catch (_) { /* only a hint */ }
}

function showMessage(text) {
    const msg = pop.querySelector('.ev2-add-msg');
    if (msg) { msg.textContent = text; msg.hidden = !text; }
}

// ── Paste ──

async function readClipboard() {
    let text = '';
    try { text = await navigator.clipboard.readText(); } catch (_) { text = ''; }
    if (!looksLikeSection(text)) {
        pasteState = { error: text ? "The clipboard doesn't hold a section. Copy one with right-click → Copy section, or paste its HTML above." : '' };
        if (!pop.hidden && tab === 'paste') renderPopover();
        return;
    }
    await inspect(text);
}

async function inspect(text) {
    try {
        const res = await api.post('/paste-section/inspect/', withEditableId({ page_id: config().pageId, html: text, language: config().language }));
        if (!res.success) throw new Error(res.error || "Couldn't read that section");
        pasteState = { clip: text, html: res.html, name: res.name, source: { ...(clipMeta(text) || {}), ...(res.source || {}) },
                       checks: res.checks || [], images: res.images || 0, mode: config().aiEnabled ? 'fit' : 'copied' };
        if (getInsertState()) previewInPlaceholder(res.html);
    } catch (err) {
        pasteState = { error: err.message || String(err) };
    }
    if (!pop.hidden && tab === 'paste') renderPopover();
}

// ── Runs (describe / refine / fit) ──

function newFlow(kind, extra) {
    stopRun(false);
    const insert = getInsertState();
    flow = { kind, insertAfter: insert ? insert.afterSection : null, cards: [], active: null, running: false,
             stream: null, runId: null, expect: {}, refining: false, adding: false, error: '', ...extra };
}

function addCard(card) {
    const c = { id: uid(), state: 'wait', html: '', why: '', sub: '', ...card };
    flow.cards.push(c);
    return c;
}

function startRun(body, expect) {
    const mine = flow;
    mine.running = true;
    mine.error = '';
    mine.expect = expect;
    mine.runId = `add-${uid()}`;
    const finish = () => {
        if (flow !== mine || !mine.running) return;
        mine.running = false;
        mine.cards.filter(c => c.state === 'wait').forEach(c => { c.state = 'failed'; c.sub = "Couldn't be made"; });
        renderDock();
    };
    mine.stream = new SSEClient(`${config().apiBase || '/editor-v2/api'}/chat/stream/`, {
        csrfToken: config().csrfToken,
        onEvent: (name, data) => {
            if (flow !== mine) return;
            const card = mine.cards.find(c => c.id === mine.expect[data?.key]);
            if (name === 'option' && card) {
                Object.assign(card, { state: 'ready', html: data.html, why: data.why || '' });
                const showing = mine.cards.find(c => c.id === mine.active);
                if (card.focus || !showing || showing.state !== 'ready' || (mine.kind === 'paste' && card.key !== 'copied')) show(card);
                renderDock();
            } else if (name === 'option_failed' && card) {
                Object.assign(card, { state: 'failed', sub: "Couldn't be made" });
                renderDock();
            } else if (name === 'error') {
                mine.error = data?.error || 'Something went wrong';
                finish();
            } else if (name === 'complete') {
                finish();
            }
        },
        onError: (data) => { if (flow === mine) mine.error = data?.error || 'Network error'; finish(); },
    });
    renderDock();
    mine.stream.start(withEditableId({
        page_id: config().pageId, scope: 'new', insert_after: mine.insertAfter, conversation_history: [],
        session_id: null, run_id: mine.runId, language: config().language, ...body,
    })).then(finish);
}

function stopRun(render = true) {
    if (!flow?.running) return;
    flow.stream?.abort();
    api.post('/chat/cancel/', { run_id: flow.runId }).catch(() => {});
    flow.running = false;
    flow.cards.filter(c => c.state === 'wait').forEach(c => { c.state = 'failed'; c.sub = 'Stopped'; });
    if (render) renderDock();
}

function designFrom(text) {
    newFlow('describe', { text });
    const expect = {};
    DESCRIBE_CARDS.forEach((d, i) => { expect[d.key] = addCard({ name: `${letter(i)} · ${d.name}` }).id; });
    startRun({ instructions: text, mode: 'explore' }, expect);
}

function design() {
    const text = (pop.querySelector('#ev2-add-prompt')?.value || '').trim();
    if (!text) { showMessage('Describe the section first.'); return; }
    if (!getInsertState()) return;
    describeText = text;
    pop.hidden = true;
    designFrom(text);
}

function pasteNow() {
    const p = pasteState;
    if (!p?.html || !getInsertState()) return;
    if (p.mode !== 'fit') { addSection({ html: p.html }, 'paste'); return; }
    pop.hidden = true;
    newFlow('paste', { source: p.source, pasteImages: p.images, text: "Fit this section to this site's design." });
    const copied = addCard({ key: 'copied', name: 'As copied', sub: 'Its own colours and fonts', state: 'ready', html: p.html });
    const fitted = addCard({ key: 'fit', name: 'Fitted to this site', sub: 'Palette, fonts, type scale' });
    flow.active = copied.id;
    startRun({ instructions: flow.text, mode: 'fit', base_html: p.html }, { fit: fitted.id });
}

function refineSend() {
    const text = (dock.querySelector('#ev2-add-refine')?.value || '').trim();
    const base = flow?.cards.find(c => c.id === flow.active);
    if (!text || !base?.html || flow.running) return;
    const n = flow.cards.filter(c => c.base === base.id).length;
    const root = base.name.split(' · ')[0];
    const card = addCard({ name: `${root} · refined${n ? ` ${n + 1}` : ''}`, base: base.id, focus: true });
    flow.refining = false;
    startRun({ instructions: text, mode: 'explore', base_html: base.html }, { next: card.id });
}

function show(card) {
    if (!card || card.state !== 'ready') return;
    const first = !flow.cards.some(c => c.shown);
    flow.active = card.id;
    card.shown = true;
    previewInPlaceholder(card.html);
    // The dock covers the bottom of the canvas: bring the preview's top just under the toolbar.
    if (first) document.querySelector('.ev2-section-placeholder')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ── Dock ──

function renderDock() {
    if (!flow) { dock.hidden = true; return; }
    dock.hidden = false;
    place();
    const active = flow.cards.find(c => c.id === flow.active);
    const ready = active?.state === 'ready';
    const count = flow.cards.filter(c => c.state === 'ready').length;
    const title = flow.kind === 'paste' ? `Pasted from ${esc(flow.source?.site || 'another site')}`
        : flow.running ? 'Designing options' : `${count} option${count === 1 ? '' : 's'}`;
    const short = flow.text.length > 60 ? `${flow.text.slice(0, 59)}…` : flow.text;
    const sub = flow.kind === 'paste'
        ? (flow.running ? "Fitting it to this site's design…" : flow.pasteImages ? `${flow.pasteImages} image${flow.pasteImages === 1 ? '' : 's'} to copy when added` : '')
        : flow.running ? "in this page's style · about a minute" : `“${esc(short)}”`;
    const headAct = flow.running ? '<button type="button" class="ev2-add-btn is-ghost" data-act="stop">Stop</button>'
        : flow.kind === 'describe' ? '<button type="button" class="ev2-add-btn is-ghost" data-act="edit">Edit description</button>' : '';
    const canRefine = ready && !flow.running && config().aiEnabled;
    dock.innerHTML = `
        <div class="ev2-add-dock-head"><b class="ev2-add-dock-title">${title}</b><span class="ev2-add-dock-sub">${sub}</span>${headAct}</div>
        <div class="ev2-add-cards${flow.cards.length === 2 ? ' is-two' : ''}">${flow.cards.map(c => `
          <button type="button" class="ev2-add-card is-${c.state}${c.id === flow.active ? ' is-on' : ''}" data-card="${c.id}"${c.state === 'ready' ? '' : ' aria-disabled="true"'}>
            <span class="ev2-add-card-thumb">${c.state === 'wait' ? '<span class="ev2-add-spin" aria-label="Designing"></span>' : c.state === 'failed' ? '<span class="ev2-add-failed">✕</span>' : ''}</span>
            <span class="ev2-add-card-meta"><span class="ev2-add-card-name">${esc(c.name)}</span>
              <small>${esc(c.state === 'wait' ? 'Designing…' : c.sub || (c.id === flow.active ? 'Showing in the page' : 'Ready'))}</small></span>
          </button>`).join('')}</div>
        ${active?.why ? `<div class="ev2-add-why"><b>Why it fits:</b> ${esc(active.why)}</div>` : ''}
        ${flow.error ? `<div class="ev2-add-why is-error">${esc(flow.error)}</div>` : ''}
        ${flow.refining ? `<div class="ev2-add-refine"><textarea id="ev2-add-refine" class="ev2-add-ta" rows="1" placeholder="What should change in this version?"></textarea>
            <button type="button" class="ev2-add-btn is-primary" data-act="refine-send">Refine</button></div>` : ''}
        <div class="ev2-add-dock-foot">
          <button type="button" class="ev2-add-btn is-ghost" data-act="discard">Discard</button>
          ${flow.kind === 'describe' ? `<button type="button" class="ev2-add-btn is-ghost" data-act="regenerate"${flow.running ? ' disabled' : ''}>Regenerate</button>` : ''}
          <span class="ev2-add-spacer"></span>
          ${flow.refining ? '<button type="button" class="ev2-add-btn" data-act="refine-cancel">Back</button>'
            : `<button type="button" class="ev2-add-btn" data-act="refine"${canRefine ? '' : ' disabled'}>Refine this one…</button>`}
          <button type="button" class="ev2-add-btn is-primary" data-act="add"${ready && !flow.adding ? '' : ' disabled'}>${flow.adding ? 'Adding…' : 'Add this section'}</button>
        </div>`;
    const width = flow.cards.length === 2 ? THUMB * 2 - 40 : THUMB;   // two cards are wider
    flow.cards.forEach(c => {
        if (c.state === 'ready') dock.querySelector(`[data-card="${c.id}"] .ev2-add-card-thumb`)?.appendChild(thumbnail(c.html, width));
    });
    if (flow.refining) dock.querySelector('#ev2-add-refine')?.focus();
}

async function addSection(card, kind) {
    const insert = getInsertState();
    if (!insert || !card?.html) return;
    if (getPendingCount() > 0 && !(await saveNow())) return;
    if (flow) { flow.adding = true; renderDock(); }
    const body = withEditableId({ page_id: config().pageId, html: card.html, insert_after: insert.afterSection || null,
                                  language: config().language });
    try {
        const res = kind === 'paste'
            ? await api.post('/paste-section/apply/', body)
            : await api.post('/apply-option/', { ...body, scope: 'new-section', section_name: null, selector: null, mode: 'insert' });
        if (!res.success) throw new Error(res.error || "Couldn't add the section");
        const node = commitPlaceholder(res.html || card.html);
        closeAll(false);
        if (node) events.emit('selection:request', node);
        events.emit('history:refresh');
        events.emit('toast:show', { text: addedText(res, kind), withUndo: true });
    } catch (err) {
        const text = `Couldn't add it: ${err.message || err}`;
        if (flow) { flow.adding = false; flow.error = text; renderDock(); } else showMessage(text);
    }
}

function addedText(res, kind) {
    if (kind !== 'paste') return 'Section added';
    const parts = ['Section added'];
    if (res.copied_images) parts.push(`${res.copied_images} image${res.copied_images === 1 ? '' : 's'} copied to the library`);
    if (res.kept_images) parts.push(`${res.kept_images} image${res.kept_images === 1 ? '' : 's'} still linked to the other site`);
    return parts.join(' · ');
}

// ── Open / close ──

function closeAll(removeSlot = true) {
    stopRun(false);
    flow = null;
    pasteState = null;
    describeText = '';
    pop.hidden = true;
    dock.hidden = true;
    dock.innerHTML = '';
    if (removeSlot) removePlaceholder();
}

function editDescription() {
    stopRun(false);
    describeText = flow?.text || describeText;
    flow = null;
    dock.hidden = true;
    resetPlaceholder();
    openPopover('describe');
}

// ── Events ──

function onPopClick(e) {
    const t = e.target.closest('[data-act], .ev2-add-tab, .ev2-add-starter');   // the popover itself carries data-tab
    if (!t) return;
    if (t.dataset.tab) {
        describeText = pop.querySelector('#ev2-add-prompt')?.value ?? describeText;
        tab = t.dataset.tab;
        renderPopover();
        if (tab === 'describe') loadMatches();
        if (tab === 'paste' && !pasteState?.html) readClipboard();
        return;
    }
    if (t.classList.contains('ev2-add-starter')) {
        const box = pop.querySelector('#ev2-add-prompt');
        box.value = t.dataset.text;
        box.focus();
        box.setSelectionRange(box.value.length, box.value.length);
        return;
    }
    const act = t.dataset.act;
    if (act === 'close') closeAll();
    else if (act === 'design') design();
    else if (act === 'read-clipboard') readClipboard();
    else if (act === 'paste') pasteNow();
    else if (act === 'clear-clip') { pasteState = null; resetPlaceholder(); renderPopover(); }
}

function onPopChange(e) {
    if (e.target.name === 'ev2-paste-mode' && pasteState) {
        pasteState.mode = e.target.value;
        renderPopover();
    }
}

function onPopKey(e) {
    if (e.target.id === 'ev2-add-prompt' && e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); design(); }
}

function onPopPaste(e) {
    if (e.target.id !== 'ev2-add-pastein') return;
    const text = e.clipboardData?.getData('text/plain') || '';
    if (!text) return;
    e.preventDefault();
    if (!looksLikeSection(text)) { showMessage("That isn't a section. Copy one with right-click → Copy section."); return; }
    inspect(text);
}

function onDockClick(e) {
    const t = e.target.closest('[data-act], [data-card]');
    if (!t || !flow) return;
    if (t.dataset.card) {
        const card = flow.cards.find(c => c.id === t.dataset.card);
        if (card?.state === 'ready') { show(card); renderDock(); }
        return;
    }
    const act = t.dataset.act;
    if (act === 'stop') stopRun();
    else if (act === 'discard') closeAll();
    else if (act === 'edit') editDescription();
    else if (act === 'regenerate') { resetPlaceholder(); designFrom(flow.text); }
    else if (act === 'refine') { flow.refining = true; renderDock(); }
    else if (act === 'refine-cancel') { flow.refining = false; renderDock(); }
    else if (act === 'refine-send') refineSend();
    else if (act === 'add') addSection(flow.cards.find(c => c.id === flow.active), flow.kind);
}

function onDockKey(e) {
    if (e.target.id === 'ev2-add-refine' && e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); refineSend(); }
}

function onKeyDown(e) {
    if (e.key !== 'Escape' || !pop) return;
    if (!pop.hidden) { e.stopPropagation(); closeAll(); }
    else if (flow?.refining) { flow.refining = false; renderDock(); }
}

export function init() {
    ensureDom();
    pop.addEventListener('click', onPopClick);
    pop.addEventListener('change', onPopChange);
    pop.addEventListener('keydown', onPopKey);
    pop.addEventListener('paste', onPopPaste);
    dock.addEventListener('click', onDockClick);
    dock.addEventListener('keydown', onDockKey);
    document.addEventListener('keydown', onKeyDown);
    window.addEventListener('resize', place);
    unsubs.push(events.on('inserter:activated', () => { closeAll(false); openPopover('describe'); }));
    unsubs.push(events.on('inserter:cancelled', () => closeAll(false)));
}

export function destroy() {
    unsubs.forEach(u => u());
    unsubs = [];
    document.removeEventListener('keydown', onKeyDown);
    window.removeEventListener('resize', place);
    if (pop) closeAll();
}
