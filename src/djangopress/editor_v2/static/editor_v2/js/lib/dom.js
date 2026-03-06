export function $(selector, context = document) {
    return context.querySelector(selector);
}

export function $$(selector, context = document) {
    return Array.from(context.querySelectorAll(selector));
}

/**
 * Check if an element was injected by Splide at runtime and doesn't exist
 * in the stored HTML. Covers: cloned slides, arrow buttons, pagination,
 * and screen-reader-only elements.
 */
function isSplideInjected(el) {
    const cls = el.classList;
    return cls.contains('splide__slide--clone')
        || cls.contains('splide__arrows')
        || cls.contains('splide__pagination')
        || cls.contains('splide__sr');
}

/**
 * Generate a CSS selector path from el up to its nearest section ancestor.
 * Returns null if el is outside a section.
 * Example: section[data-section="hero"] > div:nth-child(1) > h1:nth-child(1)
 */
export function getCssSelector(el) {
    const section = el.closest('[data-section]');
    if (!section) return null;
    const sectionAttr = section.getAttribute('data-section');
    if (el === section) return `section[data-section="${sectionAttr}"]`;

    const parts = [];
    let current = el;
    while (current && current !== section) {
        const parent = current.parentElement;
        if (!parent) break;
        // Exclude elements injected by Splide at runtime (cloned slides,
        // arrows, pagination, sr-only) so nth-child indices match the
        // original HTML stored in the database.
        const siblings = Array.from(parent.children)
            .filter(s => !isSplideInjected(s));
        const index = siblings.indexOf(current) + 1;
        parts.unshift(`${current.tagName.toLowerCase()}:nth-child(${index})`);
        current = parent;
    }
    return `section[data-section="${sectionAttr}"] > ${parts.join(' > ')}`;
}

/** Short human-readable label like "h1" or "div.hero-content" */
export function getElementLabel(el) {
    const tag = el.tagName.toLowerCase();
    const section = el.getAttribute('data-section');
    if (section) return section;
    const cls = el.classList[0];
    return cls ? `${tag}.${cls}` : tag;
}

export function getContentWrapper() {
    return $('.editor-v2-content');
}

export function getSections() {
    const wrapper = getContentWrapper();
    return wrapper ? $$('[data-section]', wrapper) : [];
}

export function getAncestors(el) {
    const wrapper = getContentWrapper();
    const ancestors = [];
    let current = el.parentElement;
    while (current && current !== wrapper) {
        ancestors.push(current);
        current = current.parentElement;
    }
    return ancestors;
}

export function getTagLabel(el) {
    const tag = el.tagName.toLowerCase();
    const section = el.dataset.section;
    if (section) return `${tag}.${section}`;
    const cls = el.classList[0];
    if (cls) return `${tag}.${cls}`;
    return tag;
}

export function isEditable(el) {
    const wrapper = getContentWrapper();
    if (!wrapper || !wrapper.contains(el)) return false;
    // Exclude admin toolbar and editor UI elements
    if (el.closest('#admin-toolbar, [id^="ev2-"]')) return false;
    // Exclude Splide-injected elements (they don't exist in stored HTML)
    if (el.closest('.splide__slide--clone, .splide__arrows, .splide__pagination, .splide__sr')) return false;
    return true;
}

const TEXT_TAGS = new Set([
    'H1', 'H2', 'H3', 'H4', 'H5', 'H6',
    'P', 'SPAN', 'A', 'LI', 'TD', 'TH',
    'LABEL', 'BUTTON', 'BLOCKQUOTE'
]);

export function isTextElement(el) {
    return TEXT_TAGS.has(el.tagName);
}

const TRANS_RE = /\{\{\s*trans\.(\w+)\s*\}\}/;

export function getTransVar(el) {
    const match = el.textContent.match(TRANS_RE);
    return match ? match[1] : null;
}

/**
 * Re-initialize JS-driven components (Splide, lightbox) inside a container.
 * Called after dynamically injecting HTML (e.g. section previews) since
 * Splide and lightbox only auto-init on DOMContentLoaded.
 */
export function initDynamicComponents(container) {
    if (window.Splide) {
        container.querySelectorAll('.splide').forEach(el => {
            new window.Splide(el).mount();
        });
    }

    container.querySelectorAll('[data-lightbox]').forEach(el => {
        el.addEventListener('click', (e) => {
            e.preventDefault();
            const group = el.dataset.lightbox;
            const groupEls = Array.from(document.querySelectorAll(`[data-lightbox="${group}"]`));
            const images = groupEls.map(a => ({
                src: a.href || a.dataset.src || a.src,
                alt: a.dataset.alt || '',
            }));
            const index = groupEls.indexOf(el);
            if (window.__lightbox) {
                window.__lightbox.open(images, Math.max(index, 0));
            }
        });
    });
}
