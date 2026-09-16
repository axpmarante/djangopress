/**
 * Floating toolbar shown above the selected element with the structural
 * verbs. The context menu remains the complete list; this is the
 * discoverable subset.
 */
import { events } from '../lib/events.js';
import { getCssSelector } from '../lib/dom.js';
import {
    duplicateElement, moveElement, removeElement,
    duplicateSection, moveSection, removeSection,
    canMove, canMoveSection,
} from '../lib/structural.js';

let bar = null;
let current = null;
let unsubs = [];
const handlers = {};

const BUTTONS = [
    { verb: 'duplicate', title: 'Duplicate', icon: '⧉' },
    { verb: 'up',        title: 'Move up',   icon: '↑' },
    { verb: 'down',      title: 'Move down', icon: '↓' },
    { verb: 'remove',    title: 'Remove',    icon: '✕', cls: 'danger' },
    { verb: 'ai',        title: 'Refine with AI', icon: '✦' },
];

function build() {
    bar = document.createElement('div');
    bar.id = 'ev2-element-toolbar';
    bar.className = 'ev2-element-toolbar hidden';
    bar.innerHTML = BUTTONS.map(b =>
        `<button type="button" class="ev2-element-toolbar-btn${b.cls ? ' ev2-element-toolbar-btn--' + b.cls : ''}" data-verb="${b.verb}" title="${b.title}">${b.icon}</button>`
    ).join('');
    bar.addEventListener('mousedown', e => e.preventDefault());
    bar.addEventListener('click', onClick);
    document.body.appendChild(bar);
}

function position() {
    if (!current || !bar) return;
    const rect = current.getBoundingClientRect();
    const h = bar.offsetHeight || 32;
    let top = rect.top - h - 30;                // leave room for the label badge
    if (top < 4) top = rect.bottom + 8;
    const left = Math.max(4, Math.min(rect.right - bar.offsetWidth, window.innerWidth - bar.offsetWidth - 4));
    bar.style.top = `${top}px`;
    bar.style.left = `${left}px`;
}

function refresh() {
    if (!bar) return;
    if (!current || !current.closest('[data-section]')) { bar.classList.add('hidden'); return; }
    const isSection = current.hasAttribute('data-section');
    const aiEnabled = !!(window.EDITOR_CONFIG || {}).aiEnabled;
    bar.querySelector('[data-verb="up"]').disabled = isSection ? !canMoveSection(current, 'up') : !canMove(current, 'up');
    bar.querySelector('[data-verb="down"]').disabled = isSection ? !canMoveSection(current, 'down') : !canMove(current, 'down');
    bar.querySelector('[data-verb="ai"]').style.display = aiEnabled ? '' : 'none';
    bar.classList.remove('hidden');
    position();
}

function onClick(e) {
    const btn = e.target.closest('[data-verb]');
    if (!btn || btn.disabled || !current) return;
    e.preventDefault();
    e.stopPropagation();
    const verb = btn.dataset.verb;
    const section = current.closest('[data-section]');
    const name = section?.getAttribute('data-section');
    const isSection = current === section;
    const selector = getCssSelector(current);

    if (verb === 'duplicate') isSection ? duplicateSection(name) : duplicateElement(selector);
    else if (verb === 'up') isSection ? moveSection(name, 'up') : moveElement(selector, 'up');
    else if (verb === 'down') isSection ? moveSection(name, 'down') : moveElement(selector, 'down');
    else if (verb === 'remove') isSection ? removeSection(name) : removeElement(selector);
    else if (verb === 'ai') events.emit('context:ai-refine', isSection ? { section: name } : { section: name, selector });
}

export function init() {
    build();
    unsubs.push(events.on('selection:changed', (el) => { current = el; refresh(); }));
    unsubs.push(events.on('inline-edit:start', () => bar.classList.add('hidden')));
    unsubs.push(events.on('inline-edit:end', () => refresh()));
    handlers.reposition = () => position();
    window.addEventListener('scroll', handlers.reposition, true);
    window.addEventListener('resize', handlers.reposition);
}

export function destroy() {
    unsubs.forEach(u => u());
    unsubs = [];
    window.removeEventListener('scroll', handlers.reposition, true);
    window.removeEventListener('resize', handlers.reposition);
    bar?.remove();
    bar = null;
    current = null;
}
