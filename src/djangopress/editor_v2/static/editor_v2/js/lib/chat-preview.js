/**
 * Copies of AI options for the Chat tab (thumbnails, compare view) and the live
 * swap after Apply. A copy never keeps `data-section`, `id` or handlers, so the
 * editor's selection and every `[data-section="x"]` lookup still find only the
 * real section.
 */
import { initDynamicComponents, isRuntimeClass, isRuntimeInjected, resolveSelector } from './dom.js';

const CANVAS = 1280;

function firstElement(html) {
    const tpl = document.createElement('template');
    tpl.innerHTML = (html || '').trim();
    return tpl.content.firstElementChild;
}

export function cleanClone(html) {
    const root = firstElement(html);
    if (!root) return document.createElement('div');
    root.querySelectorAll('script').forEach(s => s.remove());
    for (const el of [root, ...root.querySelectorAll('*')]) {
        for (const attr of [...el.attributes]) {
            const name = attr.name.toLowerCase();
            if (name === 'id' || name === 'data-section' || name.startsWith('data-ev2') || name.startsWith('on')) {
                el.removeAttribute(attr.name);
            }
        }
        [...el.classList].filter(c => c.startsWith('ev2-')).forEach(c => el.classList.remove(c));
    }
    root.inert = true;
    root.setAttribute('aria-hidden', 'true');
    return root;
}

/** The node's HTML as stored: no slider clones/arrows, no editor or runtime state classes. */
export function staticHtml(node) {
    const copy = node.cloneNode(true);
    copy.querySelectorAll('*').forEach(el => { if (isRuntimeInjected(el)) el.remove(); });
    for (const el of [copy, ...copy.querySelectorAll('*')]) {
        [...el.classList].filter(isRuntimeClass).forEach(c => el.classList.remove(c));
        if (el.classList.length === 0) el.removeAttribute('class');
    }
    return copy.outerHTML;
}

/** A scaled copy of the option as the site would render it at 1280 px. */
export function thumbnail(html, width) {
    const box = document.createElement('div');
    box.className = 'ev2-chat-thumb';
    const inner = document.createElement('div');
    inner.className = 'ev2-chat-thumb-inner';
    inner.style.width = `${CANVAS}px`;
    inner.style.transform = `scale(${width / CANVAS})`;
    inner.appendChild(cleanClone(html));
    box.appendChild(inner);
    return box;
}

/** Original and option side by side, at half size, for the page canvas. */
export function compareView(originalHtml, optionHtml, labels) {
    const view = document.createElement('div');
    view.className = 'ev2-chat-compare';
    [originalHtml, optionHtml].forEach((html, i) => {
        const pane = document.createElement('div');
        pane.className = 'ev2-chat-compare-pane';
        const cap = document.createElement('span');
        cap.className = 'ev2-chat-compare-cap';
        cap.textContent = labels[i];
        const scale = document.createElement('div');
        scale.className = 'ev2-chat-compare-scale';
        scale.appendChild(cleanClone(html));
        pane.append(cap, scale);
        view.appendChild(pane);
    });
    return view;
}

/** Replace a live node with saved HTML; returns the new node, components re-initialised. */
export function swapNode(node, html) {
    const next = firstElement(html);
    if (!node || !next) return node;
    node.replaceWith(next);
    // Only the new node: re-mounting the page's other sliders doubles their handlers.
    if (window.Splide && next.classList.contains('splide') && !next.__splide) next.__splide = new window.Splide(next).mount();
    initDynamicComponents(next);
    return next;
}

/** The live node a Chat result is about; element selectors skip slider clones like the rest of the editor. */
export function findTarget(item) {
    if (item.scope === 'element') return resolveSelector(item.selector);
    return item.section ? document.querySelector(`.editor-v2-content [data-section="${CSS.escape(item.section)}"]`) : null;
}
