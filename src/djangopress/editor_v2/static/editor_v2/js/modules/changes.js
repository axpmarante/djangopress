import { events } from '../lib/events.js';
import { api } from '../lib/api.js';
import { shortcuts } from '../lib/shortcuts.js';

// --- State ---
let pending = new Map();   // key: "selector:type:attribute?" -> change
let undoStack = [];
let redoStack = [];

function changeKey(c) {
    return `${c.selector}:${c.type}:${c.attribute || ''}`;
}

function getConfig() {
    const cfg = window.EDITOR_CONFIG || {};
    return {
        pageId: cfg.pageId,
        language: cfg.language,
        contentTypeId: cfg.contentTypeId || null,
        objectId: cfg.objectId || null,
    };
}

/** Add content_type_id/object_id to an API body if editing non-Page content. */
function withEditableId(body, cfg) {
    if (cfg.contentTypeId && cfg.objectId) {
        body.content_type_id = cfg.contentTypeId;
        body.object_id = cfg.objectId;
    }
    return body;
}

// --- DOM helpers ---

function findElement(selector) {
    return selector ? document.querySelector(selector) : null;
}

function applyToDOM(change) {
    const el = findElement(change.selector);
    if (!el) return;
    if (change.type === 'content') {
        el.textContent = change.value;
    } else if (change.type === 'classes') {
        el.className = change.value;
    } else if (change.type === 'attribute') {
        el.setAttribute(change.attribute, change.value);
    }
}

function reverseChange(change) {
    return { ...change, value: change.oldValue, oldValue: change.value };
}

// --- Emit helpers ---

function emitCount() {
    events.emit('changes:count', pending.size);
}

function emitUndoState() {
    events.emit('changes:undo-state', {
        canUndo: undoStack.length > 0,
        canRedo: redoStack.length > 0,
    });
}

// --- Recording ---

function record(change) {
    const key = changeKey(change);
    const existing = pending.get(key);
    if (existing) {
        // Keep original oldValue, update value
        existing.value = change.value;
    } else {
        pending.set(key, { ...change });
    }
    undoStack.push({ ...change });
    redoStack = [];
    emitCount();
    emitUndoState();
}

// --- Undo / Redo ---

function undo() {
    if (undoStack.length === 0) return;
    const change = undoStack.pop();
    const reversed = reverseChange(change);
    applyToDOM(reversed);
    redoStack.push(change);

    // Update pending map
    const key = changeKey(change);
    const entry = pending.get(key);
    if (entry) {
        // Walk undo stack to find latest value for this key, or remove if back to original
        const latest = findLatestInStack(undoStack, key);
        if (latest) {
            entry.value = latest.value;
        } else {
            pending.delete(key);
        }
    }
    emitCount();
    emitUndoState();
}

function redo() {
    if (redoStack.length === 0) return;
    const change = redoStack.pop();
    applyToDOM(change);
    undoStack.push(change);

    // Update pending map
    const key = changeKey(change);
    const existing = pending.get(key);
    if (existing) {
        existing.value = change.value;
    } else {
        pending.set(key, { ...change });
    }
    emitCount();
    emitUndoState();
}

function findLatestInStack(stack, key) {
    for (let i = stack.length - 1; i >= 0; i--) {
        if (changeKey(stack[i]) === key) return stack[i];
    }
    return null;
}

// --- Save ---

async function save() {
    if (pending.size === 0) {
        console.log('[ev2] save: no pending changes');
        return;
    }
    const cfg = getConfig();
    const { pageId, language } = cfg;
    const changes = Array.from(pending.values());
    console.log(`[ev2] save: ${changes.length} changes, page=${pageId}, lang=${language}`);

    const contentChanges = changes.filter(c => c.type === 'content');
    const classChanges = changes.filter(c => c.type === 'classes');
    const attrChanges = changes.filter(c => c.type === 'attribute');

    try {
        for (const c of contentChanges) {
            console.log('[ev2] save content:', c.fieldKey);
            await api.post('/update-page-content/', withEditableId({
                page_id: pageId,
                field_key: c.fieldKey,
                selector: c.selector,
                language: language,
                value: c.value,
            }, cfg));
        }
        for (const c of classChanges) {
            console.log('[ev2] save classes:', c.selector);
            await api.post('/update-page-classes/', withEditableId({
                page_id: pageId,
                selector: c.selector,
                new_classes: c.value,
            }, cfg));
        }
        for (const c of attrChanges) {
            console.log('[ev2] save attr:', c.selector, c.attribute);
            await api.post('/update-page-attribute/', withEditableId({
                page_id: pageId,
                selector: c.selector,
                attribute: c.attribute,
                value: c.value,
                old_value: c.oldValue,
                tag_name: c.tagName,
            }, cfg));
        }

        pending.clear();
        undoStack = [];
        redoStack = [];
        emitCount();
        emitUndoState();
        events.emit('changes:saved');
        console.log('[ev2] save: success');
    } catch (err) {
        console.error('[ev2] save error:', err);
        events.emit('changes:error', err.message || 'Save failed');
    }
}

// --- Discard ---

function discard() {
    // Reverse all pending changes in LIFO order from undo stack
    const reversed = [...undoStack].reverse();
    for (const change of reversed) {
        applyToDOM(reverseChange(change));
    }
    pending.clear();
    undoStack = [];
    redoStack = [];
    emitCount();
    emitUndoState();
}

// --- Event handlers (stored for cleanup) ---

const handlers = {
    content: (c) => record(c),
    classes: (c) => record(c),
    attribute: (c) => record(c),
    save: () => save(),
    discard: () => discard(),
};

// --- Public API ---

export function init() {
    events.on('change:content', handlers.content);
    events.on('change:classes', handlers.classes);
    events.on('change:attribute', handlers.attribute);
    events.on('changes:save', handlers.save);
    events.on('changes:discard', handlers.discard);

    shortcuts.register('ctrl+z', undo, 'Undo');
    shortcuts.register('ctrl+shift+z', redo, 'Redo');
    shortcuts.register('ctrl+s', () => save(), 'Save changes');

    emitCount();
    emitUndoState();
}

export function getPendingCount() {
    return pending.size;
}

export function destroy() {
    events.off('change:content', handlers.content);
    events.off('change:classes', handlers.classes);
    events.off('change:attribute', handlers.attribute);
    events.off('changes:save', handlers.save);
    events.off('changes:discard', handlers.discard);

    shortcuts.unregister('ctrl+z');
    shortcuts.unregister('ctrl+shift+z');
    shortcuts.unregister('ctrl+s');

    pending.clear();
    undoStack = [];
    redoStack = [];
}
