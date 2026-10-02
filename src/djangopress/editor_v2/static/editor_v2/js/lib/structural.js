/**
 * Client wrappers for the structural verbs (duplicate / move / insert /
 * remove). Each verb POSTs, then reloads the page and re-selects the node
 * whose selector the server returned. State survives the reload in
 * sessionStorage under one key.
 */
import { api } from './api.js';
import { events } from './events.js';
import { isRuntimeInjected, resolveSelector } from './dom.js';
import { alertDialog, confirmDialog } from './dialog.js';
import { getPendingCount, saveNow } from '../modules/changes.js';

const AFTER_RELOAD_KEY = 'ev2-after-reload';
const config = () => window.EDITOR_CONFIG || {};

function body(extra) {
    const cfg = config();
    const b = { page_id: cfg.pageId, ...extra };
    if (cfg.contentTypeId && cfg.objectId) {
        b.content_type_id = cfg.contentTypeId;
        b.object_id = cfg.objectId;
    }
    return b;
}

function reloadWith(state, label) {
    try { sessionStorage.setItem(AFTER_RELOAD_KEY, JSON.stringify(state || {})); } catch (_) {}
    if (label) {
        try { sessionStorage.setItem('ev2-toast-pending', JSON.stringify({ label })); } catch (_) {}
    }
    window.location.reload();
}

async function run(endpoint, payload, afterState, label) {
    if (getPendingCount() > 0 && !(await saveNow())) return null;
    try {
        const res = await api.post(endpoint, body(payload));
        if (!res.success) { alertDialog({ title: 'That didn\'t work', message: res.error || 'The operation failed.', tone: 'error' }); return null; }
        if (res.moved === false) return res; // edge no-op: nothing changed
        if (res.skipped_languages && res.skipped_languages.length) {
            await alertDialog({ title: 'Done, with one gap', tone: 'warning',
                message: `Not applied in ${res.skipped_languages.join(', ').toUpperCase()}: that part of the page is different there.` });
        }
        reloadWith(afterState ? afterState(res) : null, res.label || label);
        return res;
    } catch (err) {
        alertDialog({ title: 'That didn\'t work', message: String(err.message || err), tone: 'error' });
        return null;
    }
}

export function duplicateElement(selector) {
    return run('/duplicate-element/', { selector }, r => ({ selector: r.selector }), 'Duplicated element');
}

export function moveElement(selector, direction) {
    return run('/move-element/', { selector, direction }, r => ({ selector: r.selector }), 'Moved element');
}

export function insertElement(selector, position, html, { after = null } = {}) {
    return run('/insert-element/', { selector, position, html }, r => ({ selector: r.selector, after }), 'Inserted element');
}

export function duplicateSection(name) {
    return run('/duplicate-section/', { section_name: name },
        r => ({ selector: `section[data-section="${r.section_name}"]` }), 'Duplicated section');
}

export function moveSection(name, direction) {
    return run('/move-section/', { section_name: name, direction },
        () => ({ selector: `section[data-section="${name}"]` }), 'Moved section');
}

export function retagElement(selector, tag) {
    return run('/retag-element/', { selector, tag }, r => ({ selector: r.selector }), 'Changed heading level');
}

export function renameSection(name, newName) {
    return run('/rename-section/', { section_name: name, new_name: newName },
        r => ({ selector: `section[data-section="${r.section_name}"]` }), 'Renamed section');
}

export function placeSection(name, before) {
    return run('/move-section/', { section_name: name, before }, () => ({ selector: `section[data-section="${name}"]` }), 'Moved section');
}

export async function removeElement(selector) {
    const ok = await confirmDialog({ title: 'Remove this element?', danger: true, confirmLabel: 'Remove',
        message: 'It is removed in every language. You can bring it back with Undo or from the version history.' });
    if (!ok) return null;
    return run('/remove-element/', { selector }, null, 'Removed element');
}

export async function removeSection(name) {
    const ok = await confirmDialog({ title: `Remove the section "${name}"?`, danger: true, confirmLabel: 'Remove section',
        message: 'It is removed in every language. You can bring it back with Undo or from the version history.' });
    if (!ok) return null;
    return run('/remove-section/', { section_name: name }, null, 'Removed section');
}

/** True when `el` has an element sibling in that direction (ignoring runtime clones). */
export function canMove(el, direction) {
    if (!el?.parentElement) return false;
    const siblings = Array.from(el.parentElement.children).filter(s => !isRuntimeInjected(s));
    const i = siblings.indexOf(el);
    return direction === 'up' ? i > 0 : i >= 0 && i < siblings.length - 1;
}

export function canMoveSection(sectionEl, direction) {
    const sections = Array.from(document.querySelectorAll('.editor-v2-content [data-section]'));
    const i = sections.indexOf(sectionEl);
    return direction === 'up' ? i > 0 : i >= 0 && i < sections.length - 1;
}

/** Called once after all modules are initialised: re-select what a verb just produced. */
export function restoreSelection() {
    let state = null;
    try {
        const raw = sessionStorage.getItem(AFTER_RELOAD_KEY);
        sessionStorage.removeItem(AFTER_RELOAD_KEY);
        state = raw ? JSON.parse(raw) : null;
    } catch (_) { state = null; }
    if (!state?.selector) return;
    const el = resolveSelector(state.selector);
    if (!el) return;
    events.emit('selection:request', el);
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    if (state.after === 'inline-edit') events.emit('inline-edit:trigger', { element: el });
    if (state.after === 'image-picker') events.emit('image-picker:open');
}
