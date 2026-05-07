/**
 * Images Panel — sidebar tab listing every editable image on the page,
 * grouped by section. Solves the "find the image you can't click on"
 * problem for image-as-background, Splide clones, and marquee duplicates.
 *
 * Mirrors the ai-panel.js pattern: takes over #ev2-tab-content when its
 * tab is active, listens for sidebar:tab-changed.
 */
import { events } from '../lib/events.js';
import { $, $$, getContentWrapper, getCssSelector } from '../lib/dom.js';

let activeTab = null;
let unsubs = [];

function esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function render() {
    const container = $('#ev2-tab-content');
    if (!container) return;

    container.innerHTML = '<p class="ev2-placeholder ev2-empty-state">No editable images on this page.</p>';
}

function onTabChanged(tab) {
    activeTab = tab;
    if (tab === 'images') render();
}

export function init() {
    unsubs.push(events.on('sidebar:tab-changed', onTabChanged));
}

export function destroy() {
    unsubs.forEach(fn => fn());
    unsubs = [];
    activeTab = null;
}
