/**
 * Viewport switcher — toggle desktop / tablet / mobile preview.
 *
 * Constrains .editor-v2-content width to simulate different viewports
 * while keeping all editing functionality intact.
 */

const STORAGE_KEY = 'ev2-viewport';

const VIEWPORTS = {
    desktop: null,      // full width (no constraint)
    tablet:  'viewport-tablet',
    mobile:  'viewport-mobile',
};

let content;
let buttons;
let current = 'desktop';

function apply(viewport) {
    // Remove all viewport classes
    Object.values(VIEWPORTS).forEach(cls => {
        if (cls) content.classList.remove(cls);
    });

    // Toggle body background for constrained modes
    document.body.classList.toggle('ev2-viewport-constrained', viewport !== 'desktop');

    // Apply new viewport class
    const cls = VIEWPORTS[viewport];
    if (cls) content.classList.add(cls);

    // Update active button
    buttons.forEach(btn => {
        btn.classList.toggle('active', btn.dataset.viewport === viewport);
    });

    current = viewport;
    localStorage.setItem(STORAGE_KEY, viewport);
}

export function init() {
    content = document.querySelector('.editor-v2-content');
    buttons = document.querySelectorAll('.ev2-viewport-btn');

    if (!content || !buttons.length) return;

    // Restore saved preference
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved && VIEWPORTS.hasOwnProperty(saved)) {
        apply(saved);
    }

    // Click handlers
    buttons.forEach(btn => {
        btn.addEventListener('click', () => {
            apply(btn.dataset.viewport);
        });
    });
}
