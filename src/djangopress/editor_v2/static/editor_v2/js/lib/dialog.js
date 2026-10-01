/**
 * Editor dialogs — the styled replacement for window.confirm / alert / prompt.
 *
 *   if (await confirmDialog({ title: 'Remove this element?', message: '…', confirmLabel: 'Remove', danger: true })) …
 *   alertDialog({ title: 'Could not save', message: err.message, tone: 'error' });
 *   const url = await promptDialog({ title: 'Link to', placeholder: 'https://…' });   // null when cancelled
 *
 * One dialog at a time; Esc / backdrop cancel, Enter confirms, Tab stays inside,
 * focus returns to where it was. Text is always set as text, never as HTML.
 */

const ICONS = {
    danger: '<path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M10 11v6M14 11v6"/>',
    warning: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
    error: '<circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/>',
    info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
    question: '<circle cx="12" cy="12" r="10"/><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3M12 17h.01"/>',
};

let current = null;
let counter = 0;

function open({ title, message = '', tone = 'question', confirmLabel = 'OK', cancelLabel = 'Cancel',
                showCancel = true, input = null }) {
    if (current) current.cancel();
    return new Promise(resolve => {
        const id = `ev2-dialog-${++counter}`;
        const previousFocus = document.activeElement;
        const root = document.createElement('div');
        root.className = `ev2-dialog ev2-dialog--${tone}`;
        root.innerHTML = `
            <div class="ev2-dialog-backdrop" data-act="cancel"></div>
            <div class="ev2-dialog-panel" role="${showCancel ? 'alertdialog' : 'dialog'}" aria-modal="true"
                 aria-labelledby="${id}-title" aria-describedby="${id}-message">
                <div class="ev2-dialog-head">
                    <span class="ev2-dialog-icon" aria-hidden="true">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                             stroke-linecap="round" stroke-linejoin="round">${ICONS[tone] || ICONS.question}</svg>
                    </span>
                    <div class="ev2-dialog-text">
                        <h2 class="ev2-dialog-title" id="${id}-title"></h2>
                        <p class="ev2-dialog-message" id="${id}-message"></p>
                    </div>
                </div>
                ${input ? '<input class="ev2-input ev2-dialog-input" type="text" autocomplete="off" spellcheck="false">' : ''}
                <div class="ev2-dialog-actions">
                    ${showCancel ? '<button type="button" class="ev2-dialog-btn ev2-dialog-btn--ghost" data-act="cancel"></button>' : ''}
                    <button type="button" class="ev2-dialog-btn ev2-dialog-btn--confirm" data-act="ok"></button>
                </div>
            </div>`;
        root.querySelector('.ev2-dialog-title').textContent = title || '';
        const messageEl = root.querySelector('.ev2-dialog-message');
        messageEl.textContent = message || '';
        messageEl.hidden = !message;
        root.querySelector('[data-act="ok"]').textContent = confirmLabel;
        const cancelBtn = root.querySelector('button[data-act="cancel"]');
        if (cancelBtn) cancelBtn.textContent = cancelLabel;
        const field = root.querySelector('.ev2-dialog-input');
        if (field) {
            field.value = input.value || '';
            field.placeholder = input.placeholder || '';
        }
        document.body.appendChild(root);
        requestAnimationFrame(() => root.classList.add('is-open'));

        const focusables = () => Array.from(root.querySelectorAll('input, button'));
        const finish = (value) => {
            if (current !== handle) return;
            current = null;
            window.removeEventListener('keydown', onKey, true);
            root.classList.remove('is-open');
            setTimeout(() => root.remove(), 160);
            if (previousFocus && typeof previousFocus.focus === 'function') previousFocus.focus({ preventScroll: true });
            resolve(value);
        };
        const ok = () => finish(field ? field.value.trim() : true);
        const cancel = () => finish(field ? null : false);
        const handle = { cancel };
        current = handle;

        function onKey(e) {
            // Capture phase on window: the editor's own Esc/Enter shortcuts never see these keys.
            if (e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); cancel(); return; }
            if (e.key === 'Enter' && !e.isComposing) {
                const onCancel = e.target?.dataset?.act === 'cancel';
                e.preventDefault(); e.stopImmediatePropagation();
                onCancel ? cancel() : ok();
                return;
            }
            if (e.key === 'Tab') {
                const items = focusables();
                const at = items.indexOf(document.activeElement);
                const next = e.shiftKey ? (at <= 0 ? items.length - 1 : at - 1) : (at + 1) % items.length;
                e.preventDefault(); e.stopImmediatePropagation();
                items[next]?.focus();
                return;
            }
            e.stopImmediatePropagation();   // typing in the field mustn't trigger editor shortcuts
        }
        window.addEventListener('keydown', onKey, true);
        root.addEventListener('click', (e) => {
            const act = e.target.closest('[data-act]')?.dataset.act;
            if (act === 'ok') ok();
            else if (act === 'cancel') cancel();
        });
        (field || root.querySelector('[data-act="ok"]')).focus({ preventScroll: true });
        if (field) field.select();
    });
}

/** Resolves true when confirmed, false otherwise. `danger` styles a destructive action. */
export function confirmDialog({ title, message = '', confirmLabel = 'Confirm', cancelLabel = 'Cancel', danger = false, tone } = {}) {
    return open({ title, message, confirmLabel, cancelLabel, tone: tone || (danger ? 'danger' : 'question') })
        .then(v => v === true);
}

/** A message with one button. tone: 'info' (default), 'warning' or 'error'. */
export function alertDialog({ title, message = '', tone = 'info', confirmLabel = 'OK' } = {}) {
    return open({ title, message, tone, confirmLabel, showCancel: false }).then(() => undefined);
}

/** Resolves the typed text (trimmed), or null when cancelled. */
export function promptDialog({ title, message = '', value = '', placeholder = '', confirmLabel = 'OK', cancelLabel = 'Cancel' } = {}) {
    return open({ title, message, tone: 'question', confirmLabel, cancelLabel, input: { value, placeholder } });
}
