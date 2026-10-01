/**
 * What kind of element is selected, so the Design panel can show the
 * controls that fit it: section, container, button, link, heading, text,
 * image or other. Slider and gallery roots are "other" here; their Content
 * panel manages them.
 */
import { isRuntimeClass } from './dom.js';
import { findComponent } from './components.js';

const HEADINGS = new Set(['H1', 'H2', 'H3', 'H4', 'H5', 'H6']);
const TEXTS = new Set(['P', 'LI', 'BLOCKQUOTE', 'SPAN', 'LABEL', 'SMALL', 'FIGCAPTION', 'DT', 'DD']);
const BUTTON_LOOK = /^(?:[\w-]+:)*(?:bg-|border(?:-|$)|p[xy]?-|rounded)/;
const LAYOUT_CLASSES = new Set(['grid', 'inline-grid', 'flex', 'inline-flex']);

function realChildren(el) {
    return Array.from(el.children).filter(c => !Array.from(c.classList).some(isRuntimeClass));
}

function isLayout(el) {
    if (Array.from(el.classList).some(c => LAYOUT_CLASSES.has(c))) return true;
    const display = window.getComputedStyle(el).display;
    return /(^|-)grid$|(^|-)flex$/.test(display);
}

export function elementType(el) {
    if (!el || el.nodeType !== 1) return 'other';
    if (el.hasAttribute('data-section')) return 'section';
    const comp = findComponent(el);
    if (comp && comp.root === el) return 'other';
    const tag = el.tagName;
    if (tag === 'IMG' || tag === 'PICTURE') return 'image';
    if (tag === 'BUTTON' || el.getAttribute('role') === 'button') return 'button';
    if (tag === 'A') {
        return Array.from(el.classList).some(c => BUTTON_LOOK.test(c)) ? 'button' : 'link';
    }
    if (HEADINGS.has(tag)) return 'heading';
    if (TEXTS.has(tag)) return 'text';
    if (isLayout(el) && realChildren(el).length >= 2) return 'container';
    return 'other';
}
