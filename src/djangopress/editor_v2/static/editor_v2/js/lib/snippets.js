// editor_v2/static/editor_v2/js/lib/snippets.js
/**
 * Minimal HTML snippets for the "Add …" verbs. Classes are copied from the
 * nearest element of the same kind inside the section so the new element
 * matches the site; defaults are used only when nothing similar exists.
 */

const PLACEHOLDER_IMG = 'data:image/svg+xml;utf8,' + encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600" viewBox="0 0 800 600">'
    + '<rect width="800" height="600" fill="#e5e7eb"/>'
    + '<text x="400" y="310" font-family="sans-serif" font-size="28" fill="#6b7280" text-anchor="middle">Choose an image</text>'
    + '</svg>');

const DEFAULTS = {
    paragraph: { tag: 'p',   classes: 'text-base text-gray-600', text: 'New paragraph' },
    heading:   { tag: 'h3',  classes: 'text-2xl font-bold',       text: 'New heading' },
    button:    { tag: 'a',   classes: 'inline-block px-6 py-3 rounded-lg bg-gray-900 text-white font-semibold', text: 'New button', attrs: { href: '#' } },
    image:     { tag: 'img', classes: 'w-full h-auto rounded-lg', attrs: { src: PLACEHOLDER_IMG, alt: '' } },
};

/** What to do once the new element is selected after reload. */
export const PRIMITIVES = [
    { kind: 'paragraph', label: 'Add Paragraph After', after: 'inline-edit' },
    { kind: 'heading',   label: 'Add Heading After',   after: 'inline-edit' },
    { kind: 'button',    label: 'Add Button After',    after: 'inline-edit' },
    { kind: 'image',     label: 'Add Image After',     after: 'image-picker' },
];

function esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function cleanClasses(el) {
    return Array.from(el.classList).filter(c => !c.startsWith('ev2-')).join(' ');
}

function looksLikeButton(a) {
    const cls = a.className || '';
    return /\bbg-/.test(cls) || /\bborder\b|\bborder-/.test(cls);
}

/** Nearest element inside the section to copy classes from, or null. */
function findModel(kind, anchorEl) {
    const section = anchorEl.closest('[data-section]');
    if (!section) return null;
    const d = DEFAULTS[kind];
    const siblings = Array.from(anchorEl.parentElement?.children || []);
    const pool = [...siblings, ...Array.from(section.querySelectorAll(d.tag))];
    for (const el of pool) {
        if (el.tagName.toLowerCase() !== d.tag) continue;
        if (kind === 'button' && !looksLikeButton(el)) continue;
        if (kind === 'heading' && el === anchorEl) continue;
        if (cleanClasses(el)) return el;
    }
    return null;
}

export function buildSnippet(kind, anchorEl) {
    const d = DEFAULTS[kind];
    if (!d) throw new Error(`Unknown primitive: ${kind}`);
    const model = findModel(kind, anchorEl);
    const tag = model ? model.tagName.toLowerCase() : d.tag;
    const classes = model ? cleanClasses(model) : d.classes;
    const attrs = Object.entries(d.attrs || {}).map(([k, v]) => ` ${k}="${esc(v)}"`).join('');
    if (tag === 'img') return `<img class="${esc(classes)}"${attrs}>`;
    return `<${tag} class="${esc(classes)}"${attrs}>${esc(d.text)}</${tag}>`;
}
