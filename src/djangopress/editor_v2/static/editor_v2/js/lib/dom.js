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

/**
 * True when an <img> should be visible to the editor's discovery features
 * (Images sidebar tab, contained-images panel). Filters Splide runtime clones,
 * decorative duplicates marked aria-hidden, and explicit data-editor-skip
 * opt-outs.
 *
 * Note: only checks aria-hidden ON THE IMG itself. Splide adds aria-hidden
 * to inactive slides at runtime, so checking ancestors would drop legitimate
 * non-active slides.
 */
export function isEditableImage(img) {
    if (!img || img.tagName !== 'IMG') return false;
    if (img.getAttribute('aria-hidden') === 'true') return false;
    if (img.closest('.splide__slide--clone')) return false;
    if (img.closest('[data-editor-skip="true"]')) return false;
    return true;
}

/** All editable images inside `scope` (not recursing into editor-skip subtrees). */
export function getEditableImages(scope) {
    if (!scope) return [];
    return $$('img', scope).filter(isEditableImage);
}

/**
 * Top-level editable descendants of `scope` — used to build the
 * "container view" in the Content tab. Walks the tree but does NOT
 * recurse into descendants that are themselves editable: clicking the
 * outer card surfaces both the link wrapper AND the image inside it,
 * not the spans nested inside the heading.
 *
 * Returns elements in DOM order. Excludes `scope` itself.
 */
const EDITABLE_DESCENDANT_TAGS = new Set([
    'IMG', 'A', 'BUTTON',
    'H1', 'H2', 'H3', 'H4', 'H5', 'H6',
    'P', 'LI', 'BLOCKQUOTE',
]);

export function getEditableTopLevelDescendants(scope) {
    if (!scope) return [];
    const items = [];

    function walk(el) {
        for (const child of el.children) {
            if (child.closest('.splide__slide--clone')) continue;
            if (child.closest('[data-editor-skip="true"]')) continue;

            if (EDITABLE_DESCENDANT_TAGS.has(child.tagName)) {
                // Leaf candidate: filter on aria-hidden directly. (For images,
                // isEditableImage already checks this and clone/skip ancestors.)
                if (child.tagName === 'IMG') {
                    if (!isEditableImage(child)) continue;
                } else if (child.getAttribute('aria-hidden') === 'true') {
                    continue;
                }
                items.push(child);
                // Do NOT recurse into already-collected editable elements.
            } else {
                // Container: recurse regardless of aria-hidden. Splide adds
                // aria-hidden="true" to inactive slides at runtime; we still
                // want to surface their images so the editor can swap them.
                walk(child);
            }
        }
    }

    walk(scope);
    return items;
}

/**
 * Find the visual "card" scope around an element — the closest ancestor
 * before a list/grid of peer cards. Used by the Content tab to surface
 * editable elements that are visually part of the same card but live as
 * siblings under a shared wrapper (image-as-background patterns).
 *
 * Algorithm: walk up from `el` until reaching the [data-section] root or
 * until the parent has at least one *other* child with editable
 * descendants of its own (= we hit a multi-card list/grid). The last
 * single-card ancestor is the scope.
 *
 * Returns `el` itself if no broader scope is found.
 */
export function findCardScope(el) {
    if (!el) return null;
    const section = el.closest('[data-section]');
    if (!section) return null;

    let current = el;
    while (current && current !== section) {
        const parent = current.parentElement;
        if (!parent) break;
        const peerContainers = Array.from(parent.children).filter(c => {
            if (c === current) return false;
            // Layered overlays (absolute/fixed) aren't independent cards —
            // they're stacked layers of the SAME visual card (image-as-bg
            // plus gradient plus content overlay). Skip them when deciding
            // whether to stop walking.
            const pos = getComputedStyle(c).position;
            if (pos === 'absolute' || pos === 'fixed') return false;
            return getEditableTopLevelDescendants(c).length > 0;
        });
        if (peerContainers.length > 0) return current;
        current = parent;
    }
    return current;
}

export function getTransVar(el) {
    return null;
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
