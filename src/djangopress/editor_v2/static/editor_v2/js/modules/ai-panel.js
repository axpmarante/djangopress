/**
 * Chat tab — AI changes to the selected section or element (or the whole page).
 *
 * A specific request ("title in gold") is edited and applied at once, with Undo.
 * An open one ("more elegant") gets three design directions built from the
 * site's own style; they arrive one by one as tiles, preview live in the page,
 * can be compared with the original, refined further, or applied without a
 * reload. Server: /editor-v2/api/chat/stream/ (editor_v2/chat.py).
 * Page scope keeps the single-result flow (/refine-page/stream/).
 */
import { events } from '../lib/events.js';
import { noteSaveAfterReload } from '../lib/save-notes.js';
import { $, getElementLabel, getCssSelector, initDynamicComponents, resolveSelector } from '../lib/dom.js';
import { api } from '../lib/api.js';
import { SSEClient } from '../lib/sse-client.js';
import { classifyIntent, intentLabel } from '../lib/chat-intent.js';
import { thumbnail, compareView, swapNode, staticHtml, findTarget } from '../lib/chat-preview.js';

const MAX_IMAGES = 5;
const MAX_IMAGE_BYTES = 10 * 1024 * 1024;
const TILE_WIDTH = 84;
const LETTERS = { refined: 'A', bold: 'B', layout: 'C', next: 'New' };
const DIRECTION_ORDER = [
    { key: 'refined', name: 'Close to current' },
    { key: 'bold', name: 'Bolder' },
    { key: 'layout', name: 'New layout' },
];
const SUGGESTIONS = {
    section: [
        ['✦ More elegant', 'Make this section more elegant, at the level of the best sections of the site.'],
        ["Match the site's style", 'Make this section match the style of the rest of the site.'],
        ['Tighter spacing', 'Reduce the vertical spacing of this section.'],
        ['Bigger title', 'Make the title of this section bigger.'],
    ],
    element: [
        ['✦ More elegant', 'Make this more elegant, in the style of the rest of the site.'],
        ['Brand colour', "Use the site's main colour on this."],
        ['Bigger', 'Make this bigger.'],
        ['More spacing', 'Add more spacing around this.'],
    ],
    page: [],
};
const ICONS = {
    target: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18"/></svg>',
    clip: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>',
    send: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M5 12h14M13 6l6 6-6 6"/></svg>',
    stop: '<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><rect x="5" y="5" width="14" height="14" rx="2"/></svg>',
};

const config = () => window.EDITOR_CONFIG || {};
const apiBase = () => config().apiBase || '/editor-v2/api';
function esc(s) { return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
function withEditableId(body) {
    const cfg = config();
    if (cfg.contentTypeId && cfg.objectId) { body.content_type_id = cfg.contentTypeId; body.object_id = cfg.objectId; }
    return body;
}
/** News posts and other non-Page objects: no one-click Undo, no page-wide refine. */
const isPage = () => !config().contentTypeId;
function uid() { return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`; }

// ── State ──
let unsubs = [];
let activeTab = null;
let scope = 'page';                // 'page' | 'section' | 'element'
let currentSection = null;
let currentSelector = null;
let sessionId = null;
let sessionsList = [];
let sessionLoaded = false;
let freshChat = false;
let thread = [];                   // user | assistant | progress | result | applied items
let history = [];                  // [{role, content}] sent to the model
let mode = 'auto';                 // composer intent: auto | quick | explore
let attachments = [];              // [{file, url}]
let refining = null;               // {key, name, html, scope, section, selector}: the next turn starts from this option
let preview = null;                // {resultId, key, node (in the page), original (the live original node), originalHtml, compare}
let run = null;                    // the running turn
let matches = null;
let matchesKey = null;

// ── Lifecycle ──

export function init() {
    unsubs.push(events.on('sidebar:tab-changed', (tab) => {
        // An option shown in the page must not be edited by the other tabs: they save by
        // selector against the stored section.
        if (tab !== 'ai') restorePreview();
        activeTab = tab;
        if (tab === 'ai') { loadSession(); render(); }
    }));
    unsubs.push(events.on('selection:changed', (el) => {
        if (run) return;                                   // the running target stays put
        if (preview) {
            const inside = el && (preview.node?.contains(el) || preview.wrapper?.contains(el) || preview.compare?.contains(el));
            if (inside) return;                            // a click on the option keeps the option's target
            restorePreview();
        }
        const sec = el?.closest?.('[data-section]');
        const isSection = el?.hasAttribute?.('data-section');
        currentSection = sec?.getAttribute('data-section') || null;
        currentSelector = (!isSection && el) ? getCssSelector(el) : null;
        if (isSection && currentSection) scope = 'section';
        else if (currentSelector) scope = 'element';
        if (activeTab === 'ai') render();
    }));
    unsubs.push(events.on('context:ai-refine', (data) => {
        restorePreview();
        currentSection = data?.section || null;
        currentSelector = data?.selector || null;
        scope = data?.selector ? 'element' : 'section';
        sessionId = null; thread = []; history = []; refining = null;
        freshChat = true;
        events.emit('sidebar:switch-tab', 'ai');
    }));
}

export function destroy() {
    unsubs.forEach(u => u());
    unsubs = [];
    stopRun(true);
    restorePreview();
    attachments.forEach(a => URL.revokeObjectURL(a.url));
    activeTab = null; scope = 'page'; currentSection = null; currentSelector = null;
    sessionId = null; sessionsList = []; sessionLoaded = false; freshChat = false;
    thread = []; history = []; mode = 'auto'; attachments = []; refining = null; matches = null; matchesKey = null;
}

async function loadSession(targetSessionId) {
    if (!config().pageId) return;
    const isInitial = !sessionLoaded;
    sessionLoaded = true;
    const wantFresh = freshChat;
    freshChat = false;
    try {
        const qs = targetSessionId ? `?session_id=${targetSessionId}` : '';
        const res = await api.get(`/session/${config().pageId}/${qs}`);
        if (!res.success) return;
        sessionsList = res.sessions || [];
        if (!wantFresh && res.session_id && (isInitial || targetSessionId)) {
            sessionId = res.session_id;
            history = (res.messages || []).map(m => ({ role: m.role, content: m.content }));
            thread = history.map(m => ({ type: m.role, text: m.content }));
        }
        if (activeTab === 'ai') render();
    } catch (err) {
        console.warn('Failed to load session:', err);
    }
}

// ── Target ──

function targetLabel() {
    if (scope === 'section') return `Section · ${currentSection}`;
    if (scope === 'element') {
        const el = resolveSelector(currentSelector);
        return `Element · ${el ? getElementLabel(el) : 'element'}`;
    }
    return 'Whole page';
}

async function loadMatches() {
    if (scope === 'page') return;
    const key = `${scope}|${currentSection}|${currentSelector}`;
    if (key === matchesKey) return;
    matchesKey = key;
    const params = new URLSearchParams(withEditableId({ page_id: config().pageId || '', scope }));
    if (scope === 'element') params.set('selector', currentSelector || ''); else params.set('section_name', currentSection || '');
    try {
        const res = await api.get(`/chat/context/?${params}`);
        if (res.success && key === matchesKey) { matches = res.matches; renderHeader(); }
    } catch (_) { /* only a hint; every run sends it again */ }
}

// ── Render ──

function render() {
    const container = $('#ev2-tab-content');
    if (!container) return;
    if (!config().aiEnabled) {
        container.innerHTML = '<p class="ev2-placeholder ev2-empty-state">AI features require superuser access.</p>';
        return;
    }
    container.innerHTML = `
        <div class="ev2-chat">
            <div class="ev2-chat-head" id="ev2-chat-head"></div>
            <div class="ev2-chat-thread" id="ev2-chat-thread" aria-live="polite"></div>
            <div class="ev2-chat-composer">
                <div class="ev2-chat-suggs" id="ev2-chat-suggs"></div>
                <div class="ev2-chat-box" id="ev2-chat-box">
                    <div class="ev2-chat-refining" id="ev2-chat-refining" hidden></div>
                    <div class="ev2-chat-atts" id="ev2-chat-atts" hidden></div>
                    <textarea id="ev2-ai-input" rows="2" placeholder="Ask for a change, or drop a reference image…"></textarea>
                    <div class="ev2-chat-box-foot">
                        <div class="ev2-chat-box-left">
                            <button type="button" class="ev2-chat-icon" id="ev2-chat-clip" title="Attach reference images (up to 5)">${ICONS.clip}</button>
                            <input type="file" id="ev2-chat-file" accept="image/*" multiple hidden>
                            <button type="button" class="ev2-chat-intent" id="ev2-chat-intent" title="Auto decides from your words. Click to force a quick edit or 3 directions."></button>
                        </div>
                        <button type="button" class="ev2-chat-send" id="ev2-ai-send" title="Send">${ICONS.send}</button>
                    </div>
                </div>
            </div>
        </div>`;
    renderHeader();
    renderThread();
    renderComposer();
    bindComposer();
    loadMatches();
    $('#ev2-ai-input')?.focus();
}

function renderHeader() {
    const head = $('#ev2-chat-head');
    if (!head) return;
    const sessions = sessionsList.map(s => `<option value="${s.id}" ${s.id === sessionId ? 'selected' : ''}>${esc(s.title || `Session ${s.id}`)}</option>`).join('');
    const seg = [
        currentSelector ? ['element', 'Element'] : null,
        currentSection ? ['section', 'Section'] : null,
        isPage() ? ['page', 'Page'] : null,
    ].filter(Boolean).map(([value, label]) =>
        `<button type="button" data-scope="${value}" class="${scope === value ? 'is-on' : ''}" ${run ? 'disabled' : ''}>${label}</button>`).join('');
    let line = '';
    if (scope !== 'page' && matches) {
        const dots = (matches.colors || []).map(c => `<span class="ev2-chat-dot" style="background:${esc(c)}"></span>`).join('');
        const fonts = (matches.fonts || []).map(f => `<span class="ev2-chat-pill">${esc(f)}</span>`).join('');
        const refs = (matches.references || []).length ? `<span class="ev2-chat-pill">style of: ${esc(matches.references.join(', '))}</span>` : '';
        line = `<div class="ev2-chat-matches" title="What the AI is told about this site's design">
            <span>Matches:</span>${dots ? `<span class="ev2-chat-pill">${dots} palette</span>` : ''}${fonts}${refs}</div>`;
    }
    head.innerHTML = `
        <div class="ev2-chat-row">
            <span class="ev2-chat-chip">${ICONS.target}${esc(targetLabel())}</span>
            <div class="ev2-chat-seg" role="group" aria-label="Scope">${seg}</div>
        </div>
        ${line}
        ${config().pageId ? `<div class="ev2-chat-row ev2-chat-sessions">
            <select id="ev2-session-select" aria-label="Conversation" ${run ? 'disabled' : ''}>
                ${sessionId ? '' : '<option value="" selected>New conversation</option>'}${sessions}
            </select>
            <button type="button" class="ev2-chat-link" id="ev2-new-chat" ${run ? 'disabled' : ''}>New chat</button>
        </div>` : ''}`;
    head.querySelectorAll('[data-scope]').forEach(b => b.addEventListener('click', () => {
        if (b.dataset.scope === scope) return;
        restorePreview();
        scope = b.dataset.scope;
        matches = null; matchesKey = null; refining = null;
        render();
    }));
    $('#ev2-session-select')?.addEventListener('change', async (e) => {
        if (!e.target.value) return;
        restorePreview();
        refining = null;
        await loadSession(parseInt(e.target.value, 10));
    });
    $('#ev2-new-chat')?.addEventListener('click', () => {
        restorePreview();
        sessionId = null; thread = []; history = []; refining = null;
        render();
    });
}

function tileLabel(tile) {
    if (tile.key === 'original') return ['Original', 'current'];
    if (tile.key === 'prev') return ['Before', tile.name];
    if (tile.key === 'page') return ['Page', 'new version'];
    const letter = LETTERS[tile.key];
    return letter ? [letter, tile.name] : [tile.name, ''];
}

function renderResult(item) {
    const card = document.createElement('div');
    card.className = 'ev2-chat-result';
    const made = item.tiles.filter(t => !['original', 'prev'].includes(t.key));
    const ready = made.filter(t => t.state === 'ready').length;
    const head = item.applied ? `Applied ${item.appliedLabel}` : item.page ? 'Page change'
        : item.refine ? 'New version' : `${ready} of ${made.length} directions`;
    card.innerHTML = `<div class="ev2-chat-result-head"><b>${esc(head)}</b><span class="ev2-chat-muted">${esc(item.scopeLabel)}</span></div>
        <div class="ev2-chat-result-body"><div class="ev2-chat-tiles"></div></div>`;
    const body = card.querySelector('.ev2-chat-result-body');
    const tiles = card.querySelector('.ev2-chat-tiles');
    item.tiles.forEach(tile => {
        const [title, sub] = tileLabel(tile);
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = `ev2-chat-tile is-${tile.state}${item.active === tile.key ? ' is-on' : ''}`;
        btn.disabled = tile.state !== 'ready' || !!item.applied;
        btn.title = tile.state === 'failed' ? (tile.error || "Couldn't make this one") : `${title} ${sub}`.trim();
        const thumbBox = document.createElement('div');
        thumbBox.className = 'ev2-chat-tile-thumb';
        const html = tile.key === 'original' ? item.originalHtml : tile.html;
        if (tile.state === 'ready' && html && !item.page) thumbBox.appendChild(thumbnail(html, TILE_WIDTH));
        if (tile.state === 'failed') thumbBox.textContent = '✕';
        const lbl = document.createElement('span');
        lbl.className = 'ev2-chat-tile-lbl';
        const subText = tile.state === 'loading' ? 'generating' : tile.state === 'failed' ? "couldn't make it" : sub;
        lbl.innerHTML = `${esc(title)}<small>${esc(subText)}</small>`;
        btn.append(thumbBox, lbl);
        btn.addEventListener('click', () => showTile(item, tile.key));
        tiles.appendChild(btn);
    });
    const active = item.tiles.find(t => t.key === item.active);
    if (active?.why) {
        const why = document.createElement('div');
        why.className = 'ev2-chat-why';
        why.innerHTML = `<b>Why it fits</b><span>${esc(active.why)}</span>`;
        body.appendChild(why);
    }
    if (active?.notes?.length) {
        const notes = document.createElement('div');
        notes.className = 'ev2-chat-notes';
        notes.textContent = `Matched to the site: ${active.notes.slice(0, 3).join(' · ')}`;
        body.appendChild(notes);
    }
    if (item.applied) return card;
    const actions = document.createElement('div');
    actions.className = 'ev2-chat-actions';
    const isOption = active && active.key !== 'original' && active.state === 'ready';
    const add = (label, cls, fn, enabled = true) => {
        const b = document.createElement('button');
        b.type = 'button'; b.className = `ev2-chat-btn ${cls}`; b.textContent = label; b.disabled = !enabled;
        b.addEventListener('click', fn);
        actions.appendChild(b);
    };
    add(item.applying ? 'Saving…' : 'Apply', 'is-primary', () => applyTile(item), isOption && !item.applying && !run);
    if (!item.page) {
        add('Refine this one…', '', () => startRefining(item), isOption && !run);
        add(preview?.compare && preview.resultId === item.id ? 'Single view' : 'Compare', '', () => toggleCompare(item), isOption);
        add('Regenerate', 'is-ghost', () => send(item.instructions, {
            mode: 'explore', regenerate: true, target: { scope: item.scope, section: item.section, selector: item.selector },
            base: item.refine ? item.base : null,
        }), !run);
    } else {
        add('Discard', 'is-ghost', () => { restorePreview(); item.applied = true; item.appliedLabel = '— discarded'; renderThread(); });
    }
    body.appendChild(actions);
    return card;
}

function renderThread() {
    const list = $('#ev2-chat-thread');
    if (!list) return;
    list.innerHTML = '';
    if (!thread.length) {
        list.innerHTML = `<div class="ev2-chat-empty">${scope === 'page'
            ? 'Describe a change to the whole page.'
            : 'Ask for a specific change and it is applied at once, or for something open (“more elegant”) to see 3 directions in the site’s style.'}</div>`;
    }
    for (const item of thread) {
        if (item.type === 'user') {
            const el = document.createElement('div');
            el.className = 'ev2-chat-user';
            el.textContent = item.text;
            if (item.images?.length) {
                const atts = document.createElement('div');
                atts.className = 'ev2-chat-user-atts';
                item.images.forEach(url => { const img = document.createElement('img'); img.src = url; img.alt = ''; atts.appendChild(img); });
                el.appendChild(atts);
            }
            list.appendChild(el);
        } else if (item.type === 'assistant') {
            const el = document.createElement('div');
            el.className = 'ev2-chat-ai';
            el.textContent = item.text;
            list.appendChild(el);
        } else if (item.type === 'progress') {
            list.appendChild(renderProgress(item));
        } else if (item.type === 'result') {
            list.appendChild(renderResult(item));
        } else if (item.type === 'applied') {
            const el = document.createElement('div');
            el.className = 'ev2-chat-applied';
            const langs = item.translated?.length ? ` Updated ${item.translated.join(', ').toUpperCase()}.` : '';
            const missing = item.untranslated?.length ? ` Not translated: ${item.untranslated.join(', ').toUpperCase()}.` : '';
            el.innerHTML = `<span>✓ ${esc(item.text)}${esc(langs)}${esc(missing)}</span>`;
            if (item.undo && !isPage()) {
                const note = document.createElement('small');
                note.textContent = 'To undo, restore from Versions.';
                el.appendChild(note);
            } else if (item.undo) {
                const undo = document.createElement('button');
                undo.type = 'button'; undo.className = 'ev2-chat-btn is-ghost'; undo.textContent = 'Undo';
                undo.addEventListener('click', () => events.emit('history:undo'));
                el.appendChild(undo);
            }
            list.appendChild(el);
        }
    }
    list.scrollTop = list.scrollHeight;
}

function renderProgress(item) {
    const el = document.createElement('div');
    el.className = `ev2-chat-progress is-${item.state}`;
    el.dataset.id = item.id;
    const running = item.state === 'running';
    const steps = item.steps.map(s => {
        const state = s.state === 'done' ? 'done' : running ? 'now' : 'idle';
        return `<div class="ev2-chat-step is-${state}"><i></i>${esc(s.label)}</div>`;
    }).join('') || (running ? '<div class="ev2-chat-step is-now"><i></i>Starting…</div>' : '');
    const foot = running
        ? `<span class="ev2-chat-muted" data-elapsed>${elapsed(item)}</span><button type="button" class="ev2-chat-btn is-ghost" data-cancel ${item.stopping ? 'disabled' : ''}>${item.stopping ? 'Stopping…' : 'Cancel'}</button>`
        : `<span class="ev2-chat-muted">${esc(item.state === 'stopped' ? `Stopped after ${elapsed(item)}`
            : item.state === 'error' ? (item.error || 'Something went wrong') : `Done in ${elapsed(item)}`)}</span>`;
    el.innerHTML = `${steps}<div class="ev2-chat-progress-foot">${foot}</div>`;
    el.querySelector('[data-cancel]')?.addEventListener('click', () => stopRun());
    return el;
}

function elapsed(item) {
    const s = Math.round(((item.ended || Date.now()) - item.started) / 1000);
    return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
}

function renderComposer() {
    const suggs = $('#ev2-chat-suggs');
    if (suggs) {
        const list = run ? [] : (SUGGESTIONS[scope] || []);
        suggs.innerHTML = list.map(([label], i) => `<button type="button" class="ev2-chat-sugg" data-i="${i}">${esc(label)}</button>`).join('');
        suggs.hidden = !list.length;
        suggs.querySelectorAll('[data-i]').forEach(b => b.addEventListener('click', () => send(list[parseInt(b.dataset.i, 10)][1])));
    }
    const ref = $('#ev2-chat-refining');
    if (ref) {
        ref.hidden = !refining;
        ref.innerHTML = refining ? `<span>Refining <b>${esc(`${LETTERS[refining.key] || ''} ${refining.name}`.trim())}</b> — the next message changes this option</span><button type="button" aria-label="Stop refining">✕</button>` : '';
        ref.querySelector('button')?.addEventListener('click', () => { refining = null; renderComposer(); });
    }
    const atts = $('#ev2-chat-atts');
    if (atts) {
        atts.hidden = !attachments.length;
        atts.innerHTML = attachments.map((a, i) => `<span class="ev2-chat-att"><img src="${a.url}" alt=""><button type="button" data-i="${i}" aria-label="Remove image">✕</button></span>`).join('');
        atts.querySelectorAll('[data-i]').forEach(b => b.addEventListener('click', () => {
            const [gone] = attachments.splice(parseInt(b.dataset.i, 10), 1);
            URL.revokeObjectURL(gone.url);
            renderComposer();
        }));
    }
    const clip = $('#ev2-chat-clip');
    if (clip) clip.hidden = scope !== 'section';           // reference images guide whole sections
    updateIntent();
    const sendBtn = $('#ev2-ai-send');
    if (sendBtn) {
        sendBtn.innerHTML = run ? ICONS.stop : ICONS.send;
        sendBtn.title = run ? 'Stop' : 'Send';
        sendBtn.classList.toggle('is-stop', !!run);
    }
}

function updateIntent() {
    const btn = $('#ev2-chat-intent');
    if (!btn) return;
    btn.hidden = scope === 'page';
    if (btn.hidden) return;
    const text = $('#ev2-ai-input')?.value || '';
    btn.textContent = refining ? 'New version of this option'
        : intentLabel(mode, classifyIntent(text) || (attachments.length ? 'explore' : null));
    btn.classList.toggle('is-forced', mode !== 'auto');
}

function bindComposer() {
    const input = $('#ev2-ai-input');
    input?.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
    });
    input?.addEventListener('input', updateIntent);
    input?.addEventListener('paste', e => {
        const files = [...(e.clipboardData?.files || [])].filter(f => f.type.startsWith('image/'));
        if (files.length) { e.preventDefault(); addFiles(files); }
    });
    $('#ev2-ai-send')?.addEventListener('click', () => (run ? stopRun() : send()));
    $('#ev2-chat-intent')?.addEventListener('click', () => {
        mode = { auto: 'quick', quick: 'explore', explore: 'auto' }[mode];
        updateIntent();
    });
    const file = $('#ev2-chat-file');
    $('#ev2-chat-clip')?.addEventListener('click', () => file?.click());
    file?.addEventListener('change', () => { addFiles([...file.files]); file.value = ''; });
    const box = $('#ev2-chat-box');
    box?.addEventListener('dragover', e => { e.preventDefault(); box.classList.add('is-drop'); });
    box?.addEventListener('dragleave', () => box.classList.remove('is-drop'));
    box?.addEventListener('drop', e => {
        e.preventDefault();
        box.classList.remove('is-drop');
        addFiles([...(e.dataTransfer?.files || [])]);
    });
}

function addFiles(files) {
    if (scope !== 'section') {
        events.emit('toast:show', { text: 'Reference images work on a whole section: select the section first.' });
        return;
    }
    const problems = [];
    for (const f of files) {
        if (!f.type.startsWith('image/')) { problems.push(`${f.name} is not an image`); continue; }
        if (f.size > MAX_IMAGE_BYTES) { problems.push(`${f.name} is larger than 10 MB`); continue; }
        if (attachments.length >= MAX_IMAGES) { problems.push(`At most ${MAX_IMAGES} images`); break; }
        attachments.push({ file: f, url: URL.createObjectURL(f) });
    }
    if (problems.length) events.emit('toast:show', { text: problems.join('. ') });
    renderComposer();
}

// ── Preview in the page ──

function resultById(id) { return thread.find(i => i.id === id); }

/** Put `next` (a node, or HTML) where `node` is; the selection follows when it was on or inside it. */
function place(node, next) {
    if (!node) return null;
    const selected = node.classList.contains('ev2-selected') || !!node.querySelector('.ev2-selected');
    let placed;
    if (typeof next === 'string') {
        placed = swapNode(node, next);
    } else {
        node.replaceWith(next);
        placed = next;
    }
    if (selected && placed !== node) events.emit('selection:request', placed);
    return placed;
}

function showTile(item, key) {
    const tile = item.tiles.find(t => t.key === key);
    if (!tile || tile.state !== 'ready' || item.applied) return;
    if (preview && preview.resultId !== item.id) restorePreview();
    if (item.page) { showPagePreview(item, tile); return; }
    if (!preview) {
        const node = findTarget(item);
        if (!node) return;
        preview = { resultId: item.id, key: 'original', node, original: node, originalHtml: staticHtml(node), compare: null };
        item.originalHtml = preview.originalHtml;
    }
    closeCompare();
    if (key === 'original') {
        if (preview.node !== preview.original) preview.node = place(preview.node, preview.original);
    } else {
        preview.node = place(preview.node, tile.html);
    }
    preview.key = key;
    item.active = key;
    renderThread();
}

function restorePreview() {
    if (!preview) return;
    closeCompare();
    const item = resultById(preview.resultId);
    if (preview.wrapper) {
        preview.wrapper.innerHTML = preview.originalHtml;
        initDynamicComponents(preview.wrapper);
    } else if (preview.node !== preview.original) {
        place(preview.node, preview.original);
    }
    if (item) item.active = 'original';
    preview = null;
}

function toggleCompare(item) {
    if (!preview || preview.resultId !== item.id || preview.key === 'original') return;
    if (preview.compare) { closeCompare(); renderThread(); return; }
    const tile = item.tiles.find(t => t.key === preview.key);
    const [title, sub] = tileLabel(tile);
    const view = compareView(preview.originalHtml, tile.html, ['Original', sub ? `${title} · ${sub}` : title]);
    preview.node.hidden = true;
    preview.node.after(view);
    preview.compare = view;
    view.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    renderThread();
}

function closeCompare() {
    if (!preview?.compare) return;
    preview.compare.remove();
    preview.compare = null;
    preview.node.hidden = false;
}

function showPagePreview(item, tile) {
    if (!preview) {
        const wrapper = document.querySelector('.editor-v2-content [data-section]')?.parentElement;
        if (!wrapper) return;
        preview = { resultId: item.id, key: 'original', wrapper, originalHtml: wrapper.innerHTML, compare: null };
    }
    preview.wrapper.innerHTML = tile.key === 'original' ? preview.originalHtml : tile.html;
    initDynamicComponents(preview.wrapper);
    preview.key = tile.key;
    item.active = tile.key;
    renderThread();
}

// ── Apply ──

async function applyTile(item) {
    const tile = item.tiles.find(t => t.key === item.active);
    if (!tile || tile.key === 'original') return;
    item.applying = true;
    renderThread();
    try {
        if (item.page) {
            const saved = await api.post('/save-ai-page/', withEditableId({ page_id: config().pageId, html: tile.html }));
            noteSaveAfterReload(saved, 'AI page change applied');
            setTimeout(() => window.location.reload(), 300);
            return;
        }
        const index = ['refined', 'bold', 'layout'].indexOf(tile.key) + 1;
        const res = await api.post('/apply-option/', withEditableId({
            page_id: config().pageId, scope: item.scope, section_name: item.section, selector: item.selector,
            html: tile.html, option_index: index || 1, session_id: sessionId,
        }));
        if (!res.success) throw new Error(res.error || 'Save failed');
        closeCompare();
        const node = preview?.resultId === item.id ? preview.node : findTarget(item);
        const saved = place(node, res.html || tile.html);
        if (preview?.resultId === item.id) preview = null;
        const [title, sub] = tileLabel(tile);
        Object.assign(item, { applying: false, applied: true, appliedLabel: sub ? `${title} · ${sub}` : title });
        thread.push({ type: 'applied', text: `Applied ${item.appliedLabel}.`, translated: res.translated_languages,
                      untranslated: res.untranslated_languages, undo: true });
        history.push({ role: 'assistant', content: `Applied ${item.appliedLabel} to ${item.scopeLabel}.` });
        afterSave(saved, `Applied ${item.appliedLabel}`);
    } catch (err) {
        item.applying = false;
        thread.push({ type: 'assistant', text: `Couldn't save: ${err.message || err}` });
    }
    renderThread();
}

function afterSave(node, text) {
    node?.classList?.add('ev2-chat-flash');
    setTimeout(() => node?.classList?.remove('ev2-chat-flash'), 1200);
    events.emit('history:refresh');
    events.emit('toast:show', { text, withUndo: isPage() });
}

function startRefining(item) {
    const tile = item.tiles.find(t => t.key === item.active);
    if (!tile || tile.key === 'original') return;
    refining = { key: tile.key, name: tile.name, html: tile.html, scope: item.scope, section: item.section, selector: item.selector };
    renderComposer();
    $('#ev2-ai-input')?.focus();
}

// ── Send / stream ──

async function send(textArg, opts = {}) {
    if (run) return;
    const input = $('#ev2-ai-input');
    const text = (textArg ?? input?.value ?? '').trim();
    if (!text) return;
    const base = opts.regenerate ? (opts.base || null) : refining;
    // A refine or a Regenerate goes to its own card's target, whatever is selected now.
    const target = opts.target || (base ? { scope: base.scope, section: base.section, selector: base.selector }
        : { scope, section: currentSection, selector: currentSelector });
    if (target.scope === 'section' && !target.section) return;
    if (target.scope === 'element' && !target.selector) return;
    if (input && textArg === undefined) input.value = '';

    restorePreview();
    const images = opts.regenerate ? [] : attachments;
    if (!opts.regenerate) attachments = [];
    refining = null;

    thread.push({ type: 'user', text, images: images.map(a => a.url) });
    const progress = { type: 'progress', id: uid(), steps: [], state: 'running', started: Date.now() };
    thread.push(progress);
    run = { runId: `run-${uid()}`, progressId: progress.id, resultId: null, scope: target.scope, section: target.section,
            selector: target.selector, text, base };
    run.timer = setInterval(() => {
        const el = document.querySelector(`.ev2-chat-progress[data-id="${progress.id}"] [data-elapsed]`);
        if (el) el.textContent = elapsed(progress);
    }, 1000);
    const priorHistory = history.slice();
    history.push({ role: 'user', content: text });
    renderHeader();
    renderThread();
    renderComposer();

    if (target.scope === 'page') { sendPage(text, progress, priorHistory); return; }

    const payload = withEditableId({
        page_id: config().pageId, scope: target.scope, section_name: target.section, selector: target.selector,
        instructions: text, mode: opts.mode || mode, session_id: sessionId, run_id: run.runId,
        conversation_history: priorHistory, base_html: base?.html || null,
    });
    let body = payload;
    if (images.length) {
        body = new FormData();
        body.append('payload', JSON.stringify(payload));
        images.forEach(a => body.append('reference_images', a.file, a.file.name));
    }
    const sse = new SSEClient(`${apiBase()}/chat/stream/`, {
        csrfToken: config().csrfToken,
        onEvent: (name, data) => onEvent(name, data, progress),
        onError: (data) => finishRun(progress, { error: data?.error || 'Request failed' }),
    });
    run.sse = sse;
    await sse.start(body);
    if (run && run.sse === sse) finishRun(progress, { error: 'The connection closed before the end' });
}

function ensureResult() {
    if (run.resultId) return resultById(run.resultId);
    const base = run.base;
    const item = {
        type: 'result', id: uid(), scope: run.scope, section: run.section, selector: run.selector,
        scopeLabel: run.scope === 'element' ? 'element' : run.section, instructions: run.text,
        active: 'original', refine: !!base, base, originalHtml: (() => { const n = findTarget(run); return n ? staticHtml(n) : ''; })(),
        tiles: [{ key: 'original', name: 'Original', state: 'ready' }],
    };
    if (base) {
        const letter = LETTERS[base.key];
        item.tiles.push({ key: 'prev', name: letter ? `${letter} · ${base.name}` : base.name, state: 'ready', html: base.html });
        item.tiles.push({ key: 'next', name: 'Refined', state: 'loading' });
    } else {
        DIRECTION_ORDER.forEach(d => item.tiles.push({ ...d, state: 'loading' }));
    }
    thread.splice(thread.findIndex(i => i.id === run.progressId), 0, item);
    run.resultId = item.id;
    return item;
}

function onEvent(name, data, progress) {
    if (!run) return;
    if (name === 'step') {
        const step = progress.steps.find(s => s.key === data.key);
        if (step) Object.assign(step, data); else progress.steps.push({ ...data });
        if ((data.key === 'directions' || data.key === 'refine') && data.state === 'running') ensureResult();
    } else if (name === 'context') {
        matches = data.matches;
        renderHeader();
    } else if (name === 'option' || name === 'option_failed') {
        const item = ensureResult();
        const tile = item.tiles.find(t => t.key === data.key);
        if (tile) Object.assign(tile, data, { state: name === 'option' ? 'ready' : 'failed' });
        if (name === 'option' && !preview) { showTile(item, data.key); return; }
    } else if (name === 'applied') {
        const saved = place(findTarget(run), data.html);
        thread.splice(thread.findIndex(i => i.id === progress.id) + 1, 0, {
            type: 'applied', text: data.message || 'Done.', translated: data.translated, untranslated: data.untranslated, undo: true,
        });
        afterSave(saved, data.message || 'AI change applied');
    } else if (name === 'complete') {
        sessionId = data.session_id || sessionId;
        if (data.message) history.push({ role: 'assistant', content: data.message });
        finishRun(progress, { cancelled: !!data.cancelled });
        refreshSessionsList();
        return;
    } else if (name === 'error') {
        sessionId = data.session_id || sessionId;
        finishRun(progress, { error: data.error || 'Something went wrong' });
        return;
    }
    renderThread();
}

function finishRun(progress, { error = null, cancelled = false } = {}) {
    if (!run) return;
    clearInterval(run.timer);
    clearTimeout(run.stopTimer);
    progress.ended = Date.now();
    progress.state = error ? 'error' : (cancelled || progress.stopping) ? 'stopped' : 'done';
    progress.error = error;
    const item = run.resultId && resultById(run.resultId);
    if (item) item.tiles.forEach(t => { if (t.state === 'loading') { t.state = 'failed'; t.error = progress.state === 'stopped' ? 'Stopped' : 'Not made'; } });
    run = null;
    renderHeader();
    renderThread();
    renderComposer();
}

async function stopRun(silent = false) {
    if (!run) return;
    const current = run;
    const progress = thread.find(i => i.id === current.progressId);
    if (progress) progress.stopping = true;
    if (current.page) {
        current.sse?.abort();
        if (progress) finishRun(progress, { cancelled: true });
        return;
    }
    if (!silent) renderThread();
    try { await api.post('/chat/cancel/', { run_id: current.runId }); } catch (_) { /* the timer below still ends it */ }
    // The server ends the stream at its next check; if it doesn't, stop listening.
    if (run === current) {
        current.stopTimer = setTimeout(() => {
            if (run === current) { current.sse?.abort(); finishRun(progress, { cancelled: true }); }
        }, 6000);
    }
}

function sendPage(text, progress, priorHistory) {
    run.page = true;
    const labels = { prepare: 'Reading the page', refine_html: 'Rewriting the page', complete: 'Finishing' };
    const sse = new SSEClient(`${apiBase()}/refine-page/stream/`, {
        csrfToken: config().csrfToken,
        onProgress: (data) => {
            if (!data.step || !run) return;
            const step = progress.steps.find(s => s.key === data.step);
            if (step) step.state = data.status;
            else progress.steps.push({ key: data.step, label: labels[data.step] || data.step, state: data.status });
            renderThread();
        },
        onComplete: (res) => {
            if (!run) return;
            if (!res.success) { finishRun(progress, { error: res.error || 'Unknown error' }); return; }
            sessionId = res.session_id || sessionId;
            const page = res.page || res.page_data?.page || {};
            const html = res.html || (page.html_content_i18n || {})[config().language || 'pt'];
            if (html) {
                const item = {
                    type: 'result', id: uid(), page: true, scopeLabel: 'whole page', instructions: text, active: 'original',
                    tiles: [{ key: 'original', name: 'Original', state: 'ready' }, { key: 'page', name: 'Page', state: 'ready', html }],
                };
                thread.splice(thread.findIndex(i => i.id === progress.id), 0, item);
                showTile(item, 'page');
            }
            if (res.assistant_message) history.push({ role: 'assistant', content: res.assistant_message });
            finishRun(progress);
            refreshSessionsList();
        },
        onError: (data) => finishRun(progress, { error: data?.error || 'Request failed' }),
    });
    run.sse = sse;
    sse.start(withEditableId({ page_id: config().pageId, instructions: text, conversation_history: priorHistory, session_id: sessionId }));
}

async function refreshSessionsList() {
    try {
        const res = await api.get(`/session/${config().pageId}/`);
        if (res.success) { sessionsList = res.sessions || []; renderHeader(); }
    } catch (_) { /* the dropdown refreshes next time */ }
}
