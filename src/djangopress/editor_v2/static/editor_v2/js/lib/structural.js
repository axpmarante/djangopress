/**
 * Client wrappers for the structural verbs (duplicate / move / insert /
 * remove). Each verb POSTs, then reloads the page and re-selects the node
 * whose selector the server returned. State survives the reload in
 * sessionStorage under one key.
 */
import { api } from './api.js';
import { events } from './events.js';
import { isRuntimeInjected } from './dom.js';

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

function reloadWith(state) {
    try { sessionStorage.setItem(AFTER_RELOAD_KEY, JSON.stringify(state || {})); } catch (_) {}
    window.location.reload();
}

async function run(endpoint, payload, afterState) {
    try {
        const res = await api.post(endpoint, body(payload));
        if (!res.success) { alert(res.error || 'Operation failed'); return null; }
        if (res.moved === false) return res; // edge no-op: nothing changed
        if (res.skipped_languages && res.skipped_languages.length) {
            alert(`Applied, but not in: ${res.skipped_languages.join(', ')} (element not found there).`);
        }
        reloadWith(afterState ? afterState(res) : null);
        return res;
    } catch (err) {
        alert('Operation failed: ' + (err.message || err));
        return null;
    }
}

export function duplicateElement(selector) {
    return run('/duplicate-element/', { selector }, r => ({ selector: r.selector }));
}

export function moveElement(selector, direction) {
    return run('/move-element/', { selector, direction }, r => ({ selector: r.selector }));
}

export function insertElement(selector, position, html, { after = null } = {}) {
    return run('/insert-element/', { selector, position, html }, r => ({ selector: r.selector, after }));
}

export function duplicateSection(name) {
    return run('/duplicate-section/', { section_name: name },
        r => ({ selector: `section[data-section="${r.section_name}"]` }));
}

export function moveSection(name, direction) {
    return run('/move-section/', { section_name: name, direction },
        () => ({ selector: `section[data-section="${name}"]` }));
}

export function removeElement(selector) {
    if (!confirm('Remove this element? This can be undone via version history.')) return Promise.resolve(null);
    return run('/remove-element/', { selector }, null);
}

export function removeSection(name) {
    if (!confirm(`Remove section "${name}"? This can be undone via version history.`)) return Promise.resolve(null);
    return run('/remove-section/', { section_name: name }, null);
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
    const el = document.querySelector(state.selector);
    if (!el) return;
    events.emit('selection:request', el);
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    if (state.after === 'inline-edit') events.emit('inline-edit:trigger', { element: el });
    if (state.after === 'image-picker') events.emit('image-picker:open');
}
