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

function onThumbClick(selector) {
    if (!selector) return;
    const img = document.querySelector(selector);
    if (!img) return;

    events.emit('selection:request', img);

    img.scrollIntoView({ behavior: 'smooth', block: 'center' });

    img.classList.remove('ev2-image-flash');
    void img.offsetWidth;
    img.classList.add('ev2-image-flash');
    setTimeout(() => img.classList.remove('ev2-image-flash'), 1300);

    events.emit('image-picker:open');
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

    let html = '<div class="ev2-images-panel">';
    for (const group of groups) {
        html += `<div class="ev2-images-panel-group">`;
        html += `<div class="ev2-images-panel-header">`;
        html += `<span class="ev2-images-panel-section">${esc(group.section)}</span>`;
        html += `<span class="ev2-images-panel-count">${group.entries.length}</span>`;
        html += `</div>`;
        html += `<div class="ev2-images-panel-grid">`;
        for (let i = 0; i < group.entries.length; i++) {
            const entry = group.entries[i];
            const sel = getCssSelector(entry.img) || '';
            if (!sel) continue;
            const filename = (entry.src.split('/').pop() || '').split('?')[0];
            const dup = entry.dupCount > 1 ? `<span class="ev2-images-panel-dup">×${entry.dupCount}</span>` : '';
            const title = entry.alt || filename || `Image ${i + 1}`;
            html += `<button type="button" class="ev2-images-panel-thumb" data-img-selector="${esc(sel)}" title="${esc(title)}">`;
            html += `<img src="${esc(entry.src)}" alt="" loading="lazy" />`;
            html += dup;
            html += `<span class="ev2-images-panel-thumb-label">${esc(filename)}</span>`;
            html += `</button>`;
        }
        html += `</div></div>`;
    }
    html += '</div>';

    container.innerHTML = html;

    container.querySelectorAll('.ev2-images-panel-thumb').forEach(btn => {
        btn.addEventListener('click', () => onThumbClick(btn.dataset.imgSelector));
    });
}

function onTabChanged(tab) {
    activeTab = tab;
    if (tab === 'images') render();
}

export function init() {
    unsubs.push(events.on('sidebar:tab-changed', onTabChanged));
    unsubs.push(events.on('change:attribute', (data) => {
        if (activeTab === 'images' && data && data.attribute === 'src' && data.tagName === 'img') {
            render();
        }
    }));
}

export function destroy() {
    unsubs.forEach(fn => fn());
    unsubs = [];
    activeTab = null;
}
