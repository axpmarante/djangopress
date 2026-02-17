import { events } from '../lib/events.js';
import { $, getContentWrapper, getCssSelector, isTextElement, getTransVar } from '../lib/dom.js';

let handlers = {};
let toolbar = null;
let activeEl = null;
let originalText = '';
let editing = false;

function positionToolbar(el) {
    const rect = el.getBoundingClientRect();
    const tb = toolbar;
    tb.classList.remove('hidden');
    const tbRect = tb.getBoundingClientRect();
    let top = rect.top - tbRect.height - 8;
    if (top < 4) top = rect.bottom + 8;
    let left = rect.left + (rect.width - tbRect.width) / 2;
    left = Math.max(4, Math.min(left, window.innerWidth - tbRect.width - 4));
    tb.style.position = 'fixed';
    tb.style.top = `${top}px`;
    tb.style.left = `${left}px`;
}

function startEdit(el) {
    if (editing) finishEdit();
    activeEl = el;
    originalText = el.textContent.trim();
    editing = true;
    el.setAttribute('contenteditable', 'true');
    el.focus();
    positionToolbar(el);
    events.emit('inline-edit:start', { selector: getCssSelector(el) });
}

function finishEdit(cancel) {
    if (!activeEl) return;
    const el = activeEl;
    if (cancel) {
        el.textContent = originalText;
    } else {
        const newText = el.textContent.trim();
        if (newText !== originalText) {
            events.emit('change:content', {
                type: 'content',
                selector: getCssSelector(el),
                fieldKey: getTransVar(el) || '',
                value: newText,
                oldValue: originalText,
            });
        }
    }
    el.removeAttribute('contenteditable');
    toolbar.classList.add('hidden');
    editing = false;
    activeEl = null;
    originalText = '';
    events.emit('inline-edit:end');
}

function onDblClick(e) {
    const el = e.target;
    if (!isTextElement(el)) return;
    e.preventDefault();
    e.stopPropagation();
    startEdit(el);
}

function onKeyDown(e) {
    if (!editing) return;
    if (e.key === 'Escape') {
        e.preventDefault();
        finishEdit(true);
    }
}

function onBlur(e) {
    if (!editing) return;
    // Delay to allow toolbar clicks to register
    setTimeout(() => {
        if (editing && activeEl && !activeEl.contains(document.activeElement)) {
            finishEdit(false);
        }
    }, 150);
}

function onToolbarMouseDown(e) {
    const btn = e.target.closest('[data-command]');
    if (!btn) return;
    e.preventDefault();
}

function onToolbarClick(e) {
    const btn = e.target.closest('[data-command]');
    if (!btn || !editing) return;
    e.preventDefault();
    const cmd = btn.dataset.command;
    if (cmd === 'bold') {
        document.execCommand('bold');
    } else if (cmd === 'italic') {
        document.execCommand('italic');
    } else if (cmd === 'link') {
        const url = prompt('Enter URL:');
        if (url) document.execCommand('createLink', false, url);
    }
    activeEl?.focus();
}

export function init() {
    toolbar = $('#ev2-floating-toolbar');
    if (!toolbar) return;
    const wrapper = getContentWrapper();
    if (!wrapper) return;

    handlers.dblclick = onDblClick;
    wrapper.addEventListener('dblclick', handlers.dblclick);

    handlers.keydown = onKeyDown;
    document.addEventListener('keydown', handlers.keydown);

    handlers.blur = onBlur;
    wrapper.addEventListener('focusout', handlers.blur);

    handlers.toolbarMouseDown = onToolbarMouseDown;
    toolbar.addEventListener('mousedown', handlers.toolbarMouseDown);

    handlers.toolbarClick = onToolbarClick;
    toolbar.addEventListener('click', handlers.toolbarClick);

    // Allow context menu to trigger inline editing
    handlers.trigger = ({ element }) => { if (element && isTextElement(element)) startEdit(element); };
    events.on('inline-edit:trigger', handlers.trigger);
}

export function destroy() {
    if (editing) finishEdit(true);
    const wrapper = getContentWrapper();
    if (wrapper) {
        wrapper.removeEventListener('dblclick', handlers.dblclick);
        wrapper.removeEventListener('focusout', handlers.blur);
    }
    document.removeEventListener('keydown', handlers.keydown);
    events.off('inline-edit:trigger', handlers.trigger);
    if (toolbar) {
        toolbar.removeEventListener('mousedown', handlers.toolbarMouseDown);
        toolbar.removeEventListener('click', handlers.toolbarClick);
        toolbar.classList.add('hidden');
    }
    handlers = {};
    toolbar = null;
    activeEl = null;
    editing = false;
    originalText = '';
}
