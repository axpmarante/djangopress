/**
 * One-click Undo / Redo over server-side version checkpoints.
 * In-memory (unsaved) edits are undone by changes.js; once nothing is pending,
 * Ctrl+Z falls through to `history:undo` handled here.
 */
import { events } from '../lib/events.js';
import { api } from '../lib/api.js';
import { $ } from '../lib/dom.js';
import { getPendingCount } from './changes.js';
import { alertDialog } from '../lib/dialog.js';

const config = () => window.EDITOR_CONFIG || {};
let state = { undo: null, redo: null };
let unsubs = [];
let toastTimer = null;

async function refresh() {
    const pageId = config().pageId;
    if (!pageId || config().contentTypeId) { render(); return; }
    try {
        const res = await api.get(`/history/${pageId}/`);
        if (res.success) state = { undo: res.undo, redo: res.redo };
    } catch (_) { state = { undo: null, redo: null }; }
    render();
}

function render() {
    const u = $('#ev2-undo-topbar-btn'), r = $('#ev2-redo-topbar-btn'), l = $('#ev2-undo-label');
    if (u) { u.disabled = !state.undo; u.title = state.undo ? `Undo: ${state.undo.label}` : 'Nothing to undo'; }
    if (l) l.textContent = state.undo ? `Undo ${shorten(state.undo.label)}` : 'Undo';
    if (r) { r.disabled = !state.redo; r.title = state.redo ? `Redo: ${state.redo.label}` : 'Nothing to redo'; }
}

function shorten(s) { return s.length > 22 ? s.slice(0, 21) + '…' : s; }

function body() {
    const cfg = config();
    const b = { page_id: cfg.pageId };
    if (cfg.contentTypeId && cfg.objectId) { b.content_type_id = cfg.contentTypeId; b.object_id = cfg.objectId; }
    return b;
}

async function run(direction) {
    if (direction === 'undo' && !state.undo) return;
    if (direction === 'redo' && !state.redo) return;
    const expectedVersion = state[direction]?.version_number;
    try {
        const res = await api.post(`/${direction}/`, { ...body(), expected_version: expectedVersion });
        if (!res.success) { alertDialog({ title: `Couldn't ${direction}`, message: res.error || '', tone: 'error' }); return; }
        try { sessionStorage.setItem('ev2-toast-pending', JSON.stringify({ label: `${direction === 'undo' ? 'Undone' : 'Redone'}: ${res.label}`, noUndoToast: true })); } catch (_) {}
        window.location.reload();
    } catch (err) { alertDialog({ title: `Couldn't ${direction}`, message: err.message || '', tone: 'error' }); }
}

/** Entry point for the topbar buttons and the toast's Undo link: block on unsaved edits first. */
function runFromUi(direction) {
    if (getPendingCount() > 0) {
        alertDialog({ title: 'Unsaved changes', message: 'Save or discard your changes first.', tone: 'warning' });
        return;
    }
    run(direction);
}

function showToast(text, withUndo) {
    const t = $('#ev2-toast'), txt = $('#ev2-toast-text'), btn = $('#ev2-toast-undo');
    if (!t) return;
    if (txt) txt.textContent = text;
    if (btn) btn.style.display = withUndo ? '' : 'none';
    t.classList.remove('hidden');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.add('hidden'), 6000);
}

function toastFromReload() {
    let st = null;
    try { st = JSON.parse(sessionStorage.getItem('ev2-toast-pending') || 'null'); sessionStorage.removeItem('ev2-toast-pending'); } catch (_) {}
    if (st?.label) showToast(st.label, !st.noUndoToast);
}

export async function init() {
    $('#ev2-undo-topbar-btn')?.addEventListener('click', () => runFromUi('undo'));
    $('#ev2-redo-topbar-btn')?.addEventListener('click', () => runFromUi('redo'));
    $('#ev2-toast-undo')?.addEventListener('click', () => runFromUi('undo'));
    // Ctrl+Z/Ctrl+Shift+Z (changes.js) only emit these once nothing is pending,
    // so they bypass the unsaved-changes guard above.
    unsubs.push(events.on('history:undo', () => run('undo')));
    unsubs.push(events.on('history:redo', () => run('redo')));
    unsubs.push(events.on('changes:saved', refresh));
    unsubs.push(events.on('history:refresh', refresh));
    unsubs.push(events.on('toast:show', ({ text, withUndo }) => showToast(text, withUndo)));
    await refresh();
    toastFromReload();
}

export function destroy() { unsubs.forEach(u => u()); unsubs = []; clearTimeout(toastTimer); }
