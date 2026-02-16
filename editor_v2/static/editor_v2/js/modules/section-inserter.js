/**
 * Section Inserter — renders insertion lines between sections and manages
 * the placeholder element where a new section will be inserted.
 *
 * Emits:
 *   inserter:activated  { afterSection }  — when a placeholder is inserted
 *
 * Listens:
 *   inserter:refresh   — re-renders insertion lines (e.g. after page save)
 *   inserter:cancel    — removes the active placeholder
 */

import { events } from '../lib/events.js';
import { getContentWrapper, getSections } from '../lib/dom.js';

// ---------------------------------------------------------------------------
// Module state
// ---------------------------------------------------------------------------
let lines = [];        // DOM references to insertion-line elements
let placeholder = null; // the active placeholder element
let insertAfter = null; // section name the placeholder follows (null = top)

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/** Remove all insertion-line elements from the DOM. */
function removeLines() {
    lines.forEach(el => el.remove());
    lines = [];
}

/**
 * Create a single insertion-line div with its "+" button.
 * @param {string|null} afterSectionName — data-section value, or null for top
 */
function createLine(afterSectionName) {
    const div = document.createElement('div');
    div.className = 'ev2-insert-line';

    const btn = document.createElement('button');
    btn.className = 'ev2-insert-line-btn';
    btn.title = 'Insert new section';
    btn.textContent = '+';
    btn.addEventListener('click', (e) => {
        e.stopPropagation();
        insertPlaceholder(afterSectionName);
    });

    div.appendChild(btn);
    return div;
}

/**
 * Insert a placeholder element at the chosen position.
 * @param {string|null} afterSectionName
 */
function insertPlaceholder(afterSectionName) {
    removePlaceholder();
    removeLines();

    insertAfter = afterSectionName;

    const wrapper = getContentWrapper();
    if (!wrapper) return;

    placeholder = document.createElement('div');
    placeholder.className = 'ev2-section-placeholder';
    placeholder.textContent = 'New section \u2014 describe it in the AI panel \u2192';

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

/** Render insertion lines between every pair of sections. */
export function renderLines() {
    removeLines();

    // Don't show lines while a placeholder is active.
    if (placeholder) return;

    const wrapper = getContentWrapper();
    if (!wrapper) return;

    const sections = getSections();

    if (sections.length === 0) {
        // Empty page — single line inside <main> or wrapper.
        const main = wrapper.querySelector('main') || wrapper;
        const line = createLine(null);
        main.prepend(line);
        lines.push(line);
        return;
    }

    // Line before the first section (afterSectionName = null → insert at top).
    // Use parentNode because sections live inside <main>, not directly in wrapper.
    const firstLine = createLine(null);
    sections[0].parentNode.insertBefore(firstLine, sections[0]);
    lines.push(firstLine);

    // Line after each section (afterSectionName = that section's name).
    for (const section of sections) {
        const name = section.getAttribute('data-section');
        const line = createLine(name);
        section.parentNode.insertBefore(line, section.nextSibling);
        lines.push(line);
    }
}

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
}

/** Reset placeholder back to its default prompt text. */
export function resetPlaceholder() {
    if (!placeholder) return;
    placeholder.classList.remove('ev2-preview-active');
    placeholder.textContent = 'New section \u2014 describe it in the AI panel \u2192';
}

/** Remove the placeholder from the DOM and reset state. */
export function removePlaceholder() {
    if (placeholder) {
        placeholder.remove();
        placeholder = null;
    }
    insertAfter = null;
}

/** Return the current insertion state, or null if no placeholder is active. */
export function getInsertState() {
    if (!placeholder) return null;
    return { afterSection: insertAfter };
}

/** Tear down — remove all DOM elements created by this module. */
export function destroy() {
    removeLines();
    removePlaceholder();
}

/** Initialise the module. */
export function init() {
    renderLines();
    events.on('inserter:refresh', renderLines);
    events.on('inserter:cancel', removePlaceholder);
}
