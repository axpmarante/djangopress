/**
 * True-width tablet/mobile preview. In Tablet or Mobile the page is shown in an
 * iframe of that width (?ev2_frame=1), so Tailwind's responsive rules apply as on
 * a device. The desktop DOM stays the source of truth: unsaved changes are
 * mirrored into the frame, the selection follows both ways, and the Design panel
 * edits that screen's values.
 */
import { events } from '../lib/events.js';
import { getCssSelector, resolveSelector } from '../lib/dom.js';
import { getPendingChanges } from './changes.js';
import { getSelected } from './selection.js';
import { getViewport } from './viewport.js';

const WIDTHS = { tablet: 768, mobile: 390 };
let stage = null;
let frame = null;
let ready = false;
let queue = [];

function frameUrl() {
    const url = new URL(location.href);
    url.searchParams.delete('edit');
    url.searchParams.set('ev2_frame', '1');
    url.hash = '';
    return url.toString();
}

function post(msg) {
    if (!frame || !ready) { if (msg.ev2 === 'apply') queue.push(...msg.changes); return; }
    frame.contentWindow.postMessage(msg, location.origin);
}

function syncSelection() {
    const el = getSelected();
    const selector = el ? getCssSelector(el) : null;
    if (selector) post({ ev2: 'select', selector });
}

function show(device) {
    document.body.classList.add('ev2-device-mode');
    if (!stage) {
        stage = document.createElement('div');
        stage.className = 'ev2-device-stage';
        frame = document.createElement('iframe');
        frame.className = 'ev2-device-frame';
        frame.title = 'Device preview';
        stage.appendChild(frame);
        document.body.appendChild(stage);
        ready = false;
        queue = [];
        frame.src = frameUrl();
    }
    stage.hidden = false;
    frame.style.width = `${WIDTHS[device]}px`;
}

function hide() {
    document.body.classList.remove('ev2-device-mode');
    if (stage) stage.hidden = true;
}

function onViewport(device) {
    if (device === 'tablet' || device === 'mobile') show(device);
    else hide();
}

function onMessage(e) {
    if (!frame || e.source !== frame.contentWindow || e.origin !== location.origin || !e.data) return;
    if (e.data.ev2 === 'ready') {
        ready = true;
        const changes = [...getPendingChanges(), ...queue];
        queue = [];
        if (changes.length) post({ ev2: 'apply', changes });
        syncSelection();
    } else if (e.data.ev2 === 'clicked') {
        const el = resolveSelector(e.data.selector);
        if (el) events.emit('selection:request', el);
    }
}

const mirror = change => { if (frame) post({ ev2: 'apply', changes: [change] }); };

export function init() {
    window.addEventListener('message', onMessage);
    events.on('viewport:changed', onViewport);
    events.on('change:classes', mirror);
    events.on('change:attribute', mirror);
    events.on('change:content', mirror);
    events.on('changes:applied', mirror);
    events.on('selection:changed', () => { if (frame && !stage.hidden) syncSelection(); });
    events.on('changes:discard', () => { if (frame) { ready = false; frame.src = frameUrl(); } });
    onViewport(getViewport());
}
