/**
 * Section Inserter — manages the placeholder element where a new section
 * will be inserted.  Triggered via the context menu ("Insert Section
 * Before / After").
 *
 * Emits:
 *   inserter:activated  { afterSection }  — when a placeholder is inserted
 *   inserter:cancelled                    — when the user cancels
 *
 * Listens:
 *   inserter:cancel    — removes the active placeholder
 */

import { events } from '../lib/events.js';
import { getContentWrapper, getSections, initDynamicComponents } from '../lib/dom.js';

// ---------------------------------------------------------------------------
// Module state
// ---------------------------------------------------------------------------
let placeholder = null; // the active placeholder element
let insertAfter = null; // section name the placeholder follows (null = top)

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/** Populate a placeholder element with label text and cancel button. */
function buildPlaceholderContent(el) {
    el.innerHTML = '';
    const label = document.createElement('span');
    label.className = 'ev2-placeholder-label';
    label.textContent = 'New section \u2014 describe it in the modal';
    el.appendChild(label);

    const cancelBtn = document.createElement('button');
    cancelBtn.className = 'ev2-placeholder-cancel';
    cancelBtn.title = 'Cancel';
    cancelBtn.textContent = '\u00d7';
    cancelBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        removePlaceholder();
        events.emit('inserter:cancelled');
    });
    el.appendChild(cancelBtn);
}

/**
 * Insert a placeholder element at the chosen position.
 * @param {string|null} afterSectionName
 */
function insertPlaceholder(afterSectionName) {
    removePlaceholder();
    setInserting(true);

    insertAfter = afterSectionName;

    const wrapper = getContentWrapper();
    if (!wrapper) return;

    placeholder = document.createElement('div');
    placeholder.className = 'ev2-section-placeholder';
    buildPlaceholderContent(placeholder);

    // Sections live inside <main>, not directly in .editor-v2-content
    const container = wrapper.querySelector('main') || wrapper;

    if (afterSectionName === null) {
        // Insert before the first section, or append if the page is empty.
        const sections = getSections();
        if (sections.length > 0) {
            sections[0].parentNode.insertBefore(placeholder, sections[0]);
        } else {
            container.appendChild(placeholder);
        }
    } else {
        const target = wrapper.querySelector(`[data-section="${CSS.escape(afterSectionName)}"]`);
        if (target) {
            target.parentNode.insertBefore(placeholder, target.nextSibling);
        } else {
            // Fallback — section not found; append at end
            container.appendChild(placeholder);
        }
    }

    placeholder.scrollIntoView({ behavior: 'smooth', block: 'center' });

    events.emit('inserter:activated', { afterSection: afterSectionName });
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/** Insert a placeholder before a given section. */
export function insertBefore(sectionName) {
    const sections = getSections();
    let prev = null;
    for (const s of sections) {
        if (s.getAttribute('data-section') === sectionName) break;
        prev = s.getAttribute('data-section');
    }
    insertPlaceholder(prev);
}

/** Insert a placeholder after a given section. */
export function insertAfterSection(sectionName) {
    insertPlaceholder(sectionName);
}

/** Show an HTML preview inside the placeholder. */
export function previewInPlaceholder(html) {
    if (!placeholder) return;
    placeholder.classList.add('ev2-preview-active');
    placeholder.innerHTML = html;
    initDynamicComponents(placeholder);
}

/** Reset placeholder back to its default prompt text. */
export function resetPlaceholder() {
    if (!placeholder) return;
    placeholder.classList.remove('ev2-preview-active');
    buildPlaceholderContent(placeholder);
}

/** Remove the placeholder from the DOM and reset state. */
export function removePlaceholder() {
    if (placeholder) {
        placeholder.remove();
        placeholder = null;
    }
    insertAfter = null;
    setInserting(false);
}

// ---------------------------------------------------------------------------
// Insertion bars (hover "+" between sections)
// ---------------------------------------------------------------------------
let bars = [];

function makeBar(index, afterName) {
    const bar = document.createElement('div');
    bar.className = 'ev2-insert-bar';
    bar.id = `ev2-insert-bar-${index}`;
    bar.innerHTML = '<div class="ev2-insert-bar-line"></div><button type="button" class="ev2-insert-bar-btn" title="Insert section here">+</button>';
    bar.querySelector('button').addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        insertPlaceholder(afterName);
    });
    return bar;
}

function renderBars() {
    removeBars();
    const sections = getSections();
    if (sections.length === 0) return;
    sections.forEach((section, i) => {
        const prev = i === 0 ? null : sections[i - 1].getAttribute('data-section');
        const bar = makeBar(i, prev);
        section.parentNode.insertBefore(bar, section);
        bars.push(bar);
    });
    const last = sections[sections.length - 1];
    const tail = makeBar(sections.length, last.getAttribute('data-section'));
    last.parentNode.insertBefore(tail, last.nextSibling);
    bars.push(tail);
}

function removeBars() {
    bars.forEach(b => b.remove());
    bars = [];
}

function setInserting(on) {
    const wrapper = getContentWrapper();
    if (wrapper) wrapper.classList.toggle('ev2-inserting', on);
}

/** Return the current insertion state, or null if no placeholder is active. */
export function getInsertState() {
    if (!placeholder) return null;
    return { afterSection: insertAfter };
}

/** Tear down — remove all DOM elements created by this module. */
export function destroy() {
    removePlaceholder();
    removeBars();
}

/** Initialise the module. */
export function init() {
    events.on('inserter:cancel', removePlaceholder);
    renderBars();
}
