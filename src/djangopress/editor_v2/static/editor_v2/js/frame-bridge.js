/**
 * Runs inside the editor's tablet/mobile preview iframe (?ev2_frame=1).
 * The page renders at the real width, so Tailwind's md:/lg: rules apply as on
 * a device. The parent editor sends its unsaved changes and the selection;
 * clicks on page content are sent back so the parent selects that element.
 * Elements hidden on this screen by a visibility class are shown hatched so
 * they stay selectable.
 */
import { getCssSelector, isRuntimeClass } from './lib/dom.js';
import { readValues } from './lib/class-model.js';

const parent = window.parent;
const send = msg => { if (parent && parent !== window) parent.postMessage({ ev2: msg.ev2, ...msg }, location.origin); };
const deviceLabel = () => (window.innerWidth < 768 ? 'mobile' : window.innerWidth < 1024 ? 'tablet' : 'desktop');
let selected = null;

function find(selector) {
    try { return selector ? document.querySelector(selector) : null; } catch (_) { return null; }
}

function apply(change) {
    const el = find(change.selector);
    if (!el) return;
    if (change.type === 'classes') {
        const runtime = Array.from(el.classList).filter(isRuntimeClass);
        el.className = [...runtime, ...String(change.value || '').split(/\s+/).filter(Boolean)].join(' ');
    } else if (change.type === 'attribute') {
        if (change.value) el.setAttribute(change.attribute, change.value);
        else el.removeAttribute(change.attribute);
    } else if (change.type === 'content') {
        if (change.format === 'html') el.innerHTML = change.value;
        else el.textContent = change.value;
    }
}

/** Show (hatched) page elements that a visibility class hides on this screen but not on all. */
function markHidden() {
    document.querySelectorAll('.ev2-hidden-device').forEach(el => {
        el.classList.remove('ev2-hidden-device');
        el.style.removeProperty('display');
        el.removeAttribute('data-hidden-note');
    });
    const device = deviceLabel();
    document.querySelectorAll('[data-section] [class*="hidden"], [data-section][class*="hidden"]').forEach(el => {
        const values = readValues(Array.from(el.classList), 'display');
        if (values[device] !== 'hidden') return;
        const shown = ['desktop', 'tablet', 'mobile'].map(d => values[d]).find(v => v && v !== 'hidden');
        if (!shown) return;                       // hidden everywhere: not a per-screen choice
        el.style.setProperty('display', shown, 'important');
        el.classList.add('ev2-hidden-device');
        el.setAttribute('data-hidden-note', `Hidden on ${device}`);
    });
}

function select(selector) {
    if (selected) selected.classList.remove('ev2-frame-selected');
    selected = find(selector);
    if (selected) {
        selected.classList.add('ev2-frame-selected');
        selected.scrollIntoView({ block: 'nearest' });
    }
}

window.addEventListener('message', e => {
    if (e.origin !== location.origin || e.source !== parent || !e.data || !e.data.ev2) return;
    if (e.data.ev2 === 'apply') {
        (e.data.changes || []).forEach(apply);
        markHidden();
        if (selected) selected.classList.add('ev2-frame-selected');
    } else if (e.data.ev2 === 'select') {
        select(e.data.selector);
    }
});

document.addEventListener('click', e => {
    const el = e.target.closest('[data-section] *, [data-section]');
    if (!el) return;
    e.preventDefault();
    e.stopPropagation();
    const selector = getCssSelector(el);
    if (selector) send({ ev2: 'clicked', selector });
}, true);

window.addEventListener('resize', markHidden);
markHidden();
send({ ev2: 'ready' });
