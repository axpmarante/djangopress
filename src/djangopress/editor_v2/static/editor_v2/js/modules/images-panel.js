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

/**
 * Walk all sections and return the editable images, grouped by section
 * in DOM order. Within each section, dedup by src URL — first occurrence
 * wins, and the count of duplicates is attached as `dupCount` (>= 1).
 *
 * Filters applied:
 *   1. Only <img> inside [data-section]
 *   2. Drop [aria-hidden="true"] (and any descendant of an aria-hidden ancestor)
 *   3. Drop descendants of .splide__slide--clone (Splide runtime clones)
 *   4. Drop descendants of [data-editor-skip="true"] (explicit opt-out)
 */
function discoverImages() {
    const wrapper = getContentWrapper();
    if (!wrapper) return [];

    const sections = $$('[data-section]', wrapper);
    const groups = [];

    for (const section of sections) {
        const sectionName = section.getAttribute('data-section') || '';
        const imgs = $$('img', section).filter(img => {
            if (img.getAttribute('aria-hidden') === 'true') return false;
            if (img.closest('.splide__slide--clone')) return false;
            if (img.closest('[data-editor-skip="true"]')) return false;
            if (img.parentElement && img.parentElement.closest('[aria-hidden="true"]')) return false;
            return true;
        });

        const seen = new Map();
        for (const img of imgs) {
            const src = img.getAttribute('src') || '';
            const key = src.trim();
            if (!key) continue;
            const existing = seen.get(key);
            if (existing) {
                existing.dupCount += 1;
            } else {
                seen.set(key, {
                    img,
                    src,
                    alt: img.getAttribute('alt') || '',
                    dupCount: 1,
                });
            }
        }

        const entries = Array.from(seen.values());
        if (entries.length > 0) {
            groups.push({ section: sectionName, entries });
        }
    }

    return groups;
}

function render() {
    const container = $('#ev2-tab-content');
    if (!container) return;

    const groups = discoverImages();
    const total = groups.reduce((acc, g) => acc + g.entries.length, 0);

    if (total === 0) {
        container.innerHTML = '<p class="ev2-placeholder ev2-empty-state">No editable images on this page.</p>';
        return;
    }

    let html = '<pre style="font-family:var(--ev2-font-mono);font-size:11px;white-space:pre-wrap;">';
    for (const group of groups) {
        html += `\n${esc(group.section)} (${group.entries.length})`;
        for (const entry of group.entries) {
            const dup = entry.dupCount > 1 ? ` × ${entry.dupCount}` : '';
            html += `\n  ${esc(entry.src)}${dup}`;
        }
    }
    html += '\n</pre>';
    container.innerHTML = html;

    console.log('[images-panel] discovered', { total, groups });
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
