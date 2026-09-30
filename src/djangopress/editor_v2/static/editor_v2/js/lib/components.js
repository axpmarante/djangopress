/**
 * Editable components — Splide sliders and lightbox galleries — recognised by
 * structure in the live DOM. Mirror of editor_v2/components.py: keep the rules
 * in step (shared fixtures in editor_v2/tests/fixtures/components/, harness
 * in editor_v2/tests/js/components_test.html).
 */
import { isRuntimeInjected } from './dom.js';

const TEXT_SLIDE_MIN_CHARS = 40;
const SKIP_TAGS = new Set(['IMG', 'SVG', 'SCRIPT', 'STYLE', 'PICTURE', 'VIDEO', 'IFRAME', 'SOURCE', 'BR', 'TEMPLATE']);
const INLINE_TAGS = new Set(['STRONG', 'EM', 'B', 'I', 'BR', 'SPAN', 'A', 'SMALL', 'SUP', 'SUB', 'U', 'MARK']);
export const SPEED_PRESETS = { slow: 1200, normal: 800, fast: 400 };

const tagOf = (el) => el.tagName.toUpperCase();
const realChildren = (el) => Array.from(el.children).filter(c => !isRuntimeInjected(c));

// --- text ---

export function readText(el) {
    const parts = [];
    (function walk(node) {
        for (const child of node.childNodes) {
            if (child.nodeType === Node.TEXT_NODE) parts.push(child.nodeValue.replace(/\s+/g, ' '));
            else if (child.nodeType === Node.ELEMENT_NODE) {
                const tag = tagOf(child);
                if (tag === 'BR') parts.push('\n');
                else if (tag !== 'SCRIPT' && tag !== 'STYLE' && tag !== 'TEMPLATE') walk(child);
            }
        }
    })(el);
    return parts.join('').split('\n').map(l => l.trim()).join('\n').trim();
}

const isLeafy = (el) => Array.from(el.children).every(c => INLINE_TAGS.has(tagOf(c)));
const isEditableLeaf = (el) => Array.from(el.children).every(c => tagOf(c) === 'BR');

function textLeaves(item) {
    if (isLeafy(item) && readText(item)) return [item];
    const out = [];
    (function walk(node) {
        for (const child of node.children) {
            if (isRuntimeInjected(child) || SKIP_TAGS.has(tagOf(child)) || child.getAttribute('aria-hidden') === 'true') continue;
            if (isLeafy(child)) { if (readText(child)) out.push(child); }
            else walk(child);
        }
    })(item);
    return out;
}

function labelFor(el) {
    const tag = tagOf(el);
    if (tag === 'BLOCKQUOTE') return 'Quote';
    if (tag === 'CITE') return 'Author';
    if (/^H[1-6]$/.test(tag)) return 'Title';
    if (tag === 'A' || tag === 'BUTTON') return 'Button';
    return 'Text';
}

// --- recognition ---

function imageOf(item) {
    const candidates = [...(tagOf(item) === 'IMG' ? [item] : []), ...item.querySelectorAll('img')];
    return candidates.find(img => img.getAttribute('aria-hidden') !== 'true' && !img.closest('.splide__slide--clone')) || null;
}

function lightboxLinkOf(el) {
    if (tagOf(el) === 'A' && el.hasAttribute('data-lightbox')) return el;
    const links = el.querySelectorAll('a[data-lightbox]');
    return links.length === 1 ? links[0] : null;
}

function splideSlides(root) {
    const list = root.querySelector('.splide__list');
    if (!list) return [];
    return Array.from(list.children).filter(c => tagOf(c) === 'LI' && c.classList.contains('splide__slide') && !isRuntimeInjected(c));
}

const galleryItems = (root) => realChildren(root).filter(c => lightboxLinkOf(c));
const isImageSlide = (slide) => !!imageOf(slide) && readText(slide).length < TEXT_SLIDE_MIN_CHARS;

export function detectKind(root) {
    if (!root || !root.classList) return null;
    if (root.classList.contains('splide')) {
        const slides = splideSlides(root);
        if (!slides.length) return null;
        const images = slides.filter(isImageSlide).length;
        return images * 2 > slides.length ? 'slider' : 'text-slider';
    }
    const n = galleryItems(root).length;
    if (n >= 2 || (n >= 1 && root.getAttribute('data-media-collection') === 'lightbox')) return 'gallery';
    return null;
}

/** The component containing `el` ({root, kind}) or null. A .splide ancestor wins over a gallery. */
export function findComponent(el) {
    const section = el?.closest?.('[data-section]');
    if (!section) return null;
    const splide = el.closest('.splide');
    if (splide && splide !== section && section.contains(splide)) {
        const kind = detectKind(splide);
        return kind ? { root: splide, kind } : null;
    }
    for (let node = el; node && node !== section; node = node.parentElement) {
        if (detectKind(node) === 'gallery') return { root: node, kind: 'gallery' };
    }
    return null;
}

export function itemsOf(comp) {
    return comp.kind === 'gallery' ? galleryItems(comp.root) : splideSlides(comp.root);
}

export function itemFields(item) {
    return {
        image: imageOf(item),
        link: lightboxLinkOf(item),
        texts: textLeaves(item).map(el => ({ el, editable: isEditableLeaf(el), value: readText(el), label: labelFor(el) })),
    };
}

export function minItems(comp) {
    return comp.kind === 'gallery' && comp.root.getAttribute('data-media-collection') !== 'lightbox' ? 2 : 1;
}

export function componentLabel(comp) {
    if (comp.kind === 'slider') return { title: 'Image slider', noun: 'images' };
    if (comp.kind === 'text-slider') return { title: 'Slider', noun: 'slides' };
    return { title: 'Gallery', noun: 'images' };
}

/** Raw stored HTML can be swapped in only when it has no Django template syntax to render. */
export function canSwapInPlace(html) {
    return !!html && !/\{[{%]/.test(html);
}

// --- slider settings (data-splide) ---

export function readSliderOptions(root) {
    const raw = root.getAttribute('data-splide');
    if (!raw) return { ok: true, opts: {} };
    try {
        const opts = JSON.parse(raw);
        return opts && typeof opts === 'object' && !Array.isArray(opts) ? { ok: true, opts } : { ok: false, opts: {} };
    } catch (_) {
        return { ok: false, opts: {} };
    }
}

function nearestSpeed(ms) {
    let best = 'normal';
    for (const [name, value] of Object.entries(SPEED_PRESETS)) {
        if (Math.abs(value - ms) < Math.abs(SPEED_PRESETS[best] - ms)) best = name;
    }
    return best;
}

function breakpointKeys(bps) {
    const keys = Object.keys(bps || {}).filter(k => /^\d+$/.test(k)).map(Number).sort((a, b) => a - b);
    const mobile = keys.find(k => k <= 800) ?? 768;
    const tablet = keys.filter(k => k > mobile && k <= 1280).pop() ?? 1024;
    return { mobile: String(mobile), tablet: String(tablet) };
}

export function settingsFromOptions(opts) {
    const type = opts.type || 'slide';
    const perPage = opts.perPage || 1;
    const bps = opts.breakpoints || {};
    const keys = breakpointKeys(bps);
    return {
        effect: type === 'fade' ? 'fade' : 'slide',
        loop: type === 'loop' || !!opts.rewind,
        autoplay: !!opts.autoplay,
        seconds: Math.max(1, Math.round((opts.interval ?? 5000) / 1000)),
        speed: nearestSpeed(opts.speed ?? 400),
        arrows: opts.arrows !== false,
        dots: opts.pagination !== false,
        pauseOnHover: opts.pauseOnHover !== false,
        multi: type !== 'fade' && (perPage > 1 || Object.keys(bps).length > 0),
        perPage,
        tablet: bps[keys.tablet]?.perPage ?? perPage,
        mobile: bps[keys.mobile]?.perPage ?? 1,
    };
}

/** The data-splide changes for the server (null deletes a key). */
export function settingsChanges(s, opts) {
    const c = {};
    if (s.effect === 'fade') { c.type = 'fade'; c.rewind = !!s.loop; }
    else if (s.loop) { c.type = 'loop'; c.rewind = null; }
    else { c.type = 'slide'; c.rewind = false; }
    c.autoplay = !!s.autoplay;
    c.interval = s.seconds * 1000;
    c.speed = SPEED_PRESETS[s.speed] ?? 800;
    c.arrows = !!s.arrows;
    c.pagination = !!s.dots;
    c.pauseOnHover = !!s.pauseOnHover;
    if (s.multi && s.effect !== 'fade') {
        c.perPage = s.perPage;
        const bps = JSON.parse(JSON.stringify(opts.breakpoints || {}));
        const keys = breakpointKeys(bps);
        bps[keys.tablet] = { ...(bps[keys.tablet] || {}), perPage: s.tablet };
        bps[keys.mobile] = { ...(bps[keys.mobile] || {}), perPage: s.mobile };
        c.breakpoints = bps;
    }
    return c;
}
