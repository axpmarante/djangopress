const isMac = navigator.platform.includes('Mac');
const registry = new Map();

function normalizeCombo(combo) {
    return combo.toLowerCase().split('+').sort().join('+');
}

function comboFromEvent(e) {
    const parts = [];
    if (isMac ? e.metaKey : e.ctrlKey) parts.push('ctrl');
    if (e.shiftKey) parts.push('shift');
    if (e.altKey) parts.push('alt');
    const key = e.key.toLowerCase();
    if (!['control', 'meta', 'shift', 'alt'].includes(key)) {
        parts.push(key);
    }
    return parts.sort().join('+');
}

function isInputFocused(e) {
    const tag = e.target.tagName;
    return tag === 'INPUT' || tag === 'TEXTAREA' || e.target.isContentEditable;
}

document.addEventListener('keydown', (e) => {
    if (isInputFocused(e)) return;
    const combo = comboFromEvent(e);
    const entry = registry.get(combo);
    if (entry) {
        e.preventDefault();
        entry.callback(e);
    }
});

export const shortcuts = {
    register(combo, callback, description = '') {
        registry.set(normalizeCombo(combo), { callback, description });
    },

    unregister(combo) {
        registry.delete(normalizeCombo(combo));
    },

    getAll() {
        const result = [];
        registry.forEach(({ description }, combo) => {
            result.push({ combo, description });
        });
        return result;
    }
};
