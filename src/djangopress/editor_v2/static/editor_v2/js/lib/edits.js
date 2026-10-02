/**
 * Small edits the sidebar panels and the right-click menu make on a live
 * element, each recorded through the usual change events (saved with Save,
 * undone with Discard): text, an attribute, the class list, the photo's focus
 * point, "open in a new tab".
 */
import { events } from './events.js';
import { getCssSelector } from './dom.js';

export const FOCUS_RE = /^object-(top|bottom|left|right|center|left-top|left-bottom|right-top|right-bottom)$/;

export function setText(el, value, format = 'text') {
    const oldValue = format === 'html' ? el.innerHTML : el.textContent;
    if (format === 'html') el.innerHTML = value; else el.textContent = value;
    events.emit('change:content', { type: 'content', selector: getCssSelector(el) || '', fieldKey: '', value, oldValue, format });
}

export function setAttr(el, attribute, value) {
    const oldValue = el.getAttribute(attribute) || '';
    if (oldValue === value) return;
    if (value) el.setAttribute(attribute, value); else el.removeAttribute(attribute);
    events.emit('change:attribute', { type: 'attribute', selector: getCssSelector(el) || '', attribute, value, oldValue, tagName: el.tagName.toLowerCase() });
}

export function setClasses(el, classes) {
    const oldValue = el.getAttribute('class') || '';
    const value = classes.join(' ');
    if (value === oldValue) return;
    el.setAttribute('class', value);
    events.emit('change:classes', { type: 'classes', selector: getCssSelector(el) || '', value, oldValue });
}

/** Which part of a cropped photo stays visible: top | center | bottom | left | right. */
export function setFocusPoint(el, position) {
    const classes = [...el.classList].filter(c => !FOCUS_RE.test(c) && !c.startsWith('ev2-'));
    if (position !== 'center') classes.push(`object-${position}`);
    setClasses(el, classes);
}

export function focusPointOf(el) {
    return ([...el.classList].find(c => FOCUS_RE.test(c)) || 'object-center').replace('object-', '');
}

/** target="_blank" with rel="noopener" (other rel words such as nofollow are kept). */
export function setNewTab(el, on) {
    setAttr(el, 'target', on ? '_blank' : '');
    const rel = (el.getAttribute('rel') || '').split(/\s+/).filter(r => r && r !== 'noopener' && r !== 'noreferrer');
    if (on) rel.push('noopener');
    setAttr(el, 'rel', rel.join(' '));
}

export function opensInNewTab(el) {
    return el.getAttribute('target') === '_blank';
}
