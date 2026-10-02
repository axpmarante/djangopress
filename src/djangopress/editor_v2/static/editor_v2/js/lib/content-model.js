/**
 * What the Content, Structure and Images tabs say about the page, in the
 * operator's words: the role of each writable item (eyebrow, heading, text,
 * button, link, image), a one-line description of a section, the kind of a
 * link (page, section, phone, email, WhatsApp, web), whether a photo is sharp
 * at the size it is shown, and the same item's text in another language copy.
 * Pure helpers over the DOM; no saving here.
 */
import { elementType } from './element-types.js';
import { detectKind, itemsOf } from './components.js';
import { isRuntimeInjected } from './dom.js';

export const ROLE_LABELS = {
    section: 'Section', eyebrow: 'Eyebrow', heading: 'Heading', text: 'Text',
    button: 'Button', link: 'Link', image: 'Image',
};
const TEXT_TAGS = new Set(['P', 'SPAN', 'SMALL', 'LI', 'BLOCKQUOTE', 'LABEL', 'FIGCAPTION', 'DT', 'DD', 'DIV', 'STRONG', 'EM']);
const BLOCK_TAGS = new Set(['DIV', 'P', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'UL', 'OL', 'LI', 'IMG', 'PICTURE', 'SECTION',
    'ARTICLE', 'FIGURE', 'BLOCKQUOTE', 'TABLE', 'FORM', 'IFRAME', 'VIDEO', 'SVG']);
const EYEBROW_MAX = 40;

function hasBlockChildren(el) {
    return Array.from(el.children).some(c => BLOCK_TAGS.has(c.tagName.toUpperCase()));
}

function text(el) {
    return (el.textContent || '').replace(/\s+/g, ' ').trim();
}

function looksLikeEyebrow(el) {
    const t = text(el);
    if (!t || t.length > EYEBROW_MAX) return false;
    const classes = Array.from(el.classList).map(c => c.split(':').pop());
    if (classes.includes('uppercase') && classes.some(c => c.startsWith('tracking-'))) return true;
    if (!el.isConnected) return false;
    const cs = getComputedStyle(el);
    return cs.textTransform === 'uppercase' && cs.letterSpacing !== 'normal' && parseFloat(cs.letterSpacing) > 0;
}

/** eyebrow | heading | text | button | link | image | null */
export function itemRole(el) {
    if (!el || el.nodeType !== 1) return null;
    const tag = el.tagName.toUpperCase();
    if (tag === 'IMG' || tag === 'PICTURE') return 'image';
    if (tag === 'A' || tag === 'BUTTON') return elementType(el) === 'button' ? 'button' : 'link';
    if (/^H[1-6]$/.test(tag)) return 'heading';
    if (!TEXT_TAGS.has(tag)) return null;
    if (tag === 'DIV' && (el.children.length > 0 || !text(el))) return null;
    if (!text(el)) return null;
    return looksLikeEyebrow(el) ? 'eyebrow' : 'text';
}

/** {items: [{el, role}], components: [{root, kind, count}]} in page order. Sliders and galleries are
 * listed as components (their Content card edits them); slider clones and editor-only nodes are skipped. */
export function sectionOutline(section) {
    const items = [];
    const components = [];
    const walk = (el) => {
        for (const child of el.children) {
            if (isRuntimeInjected(child) || child.getAttribute('data-editor-skip') === 'true') continue;
            if (child.tagName === 'SCRIPT' || child.tagName === 'STYLE') continue;
            const kind = detectKind(child);
            if (kind) {
                const comp = { root: child, kind };
                components.push({ ...comp, count: itemsOf(comp).length });
                continue;
            }
            const role = itemRole(child);
            if (role && (role === 'image' || !hasBlockChildren(child))) {
                items.push({ el: child, role });
                continue;
            }
            walk(child);
        }
    };
    if (section) walk(section);
    return { items, components };
}

export function sectionItems(section) {
    return sectionOutline(section).items;
}

const NOUNS = { heading: 'title', text: 'text', button: 'button', link: 'link', image: 'photo' };

/** "Slider (5 slides) + title + 2 texts + button + 2 photos" */
export function describeSection(section) {
    const { items, components } = sectionOutline(section);
    const parts = components.map(c => (c.kind === 'gallery' ? `Gallery (${c.count} photos)` : `Slider (${c.count} slides)`));
    const counts = new Map();
    for (const { role } of items) {
        if (!NOUNS[role]) continue;
        counts.set(role, (counts.get(role) || 0) + 1);
    }
    for (const [role, n] of counts) parts.push(n === 1 ? NOUNS[role] : `${n} ${NOUNS[role]}s`);
    const line = parts.join(' + ') || 'Empty';
    return line.charAt(0).toUpperCase() + line.slice(1);
}

export function hasFormatting(el) {
    return !!el && el.children.length > 0;
}

/** {kind: page|section|phone|email|whatsapp|url, value, message?} */
export function parseHref(href) {
    const h = (href || '').trim();
    if (h.startsWith('tel:')) return { kind: 'phone', value: h.slice(4) };
    if (h.startsWith('mailto:')) return { kind: 'email', value: h.slice(7) };
    const wa = h.match(/^https?:\/\/(?:wa\.me\/(\d+)|api\.whatsapp\.com\/send\/?\?(?:.*&)?phone=(\d+))([^#]*)/);
    if (wa) {
        const digits = wa[1] || wa[2];
        const query = new URLSearchParams((h.split('?')[1] || '').split('#')[0]);
        const out = { kind: 'whatsapp', value: `+${digits}` };
        if (query.get('text')) out.message = query.get('text');
        return out;
    }
    if (h.startsWith('#')) return { kind: 'section', value: h };
    if (h.startsWith('/')) return { kind: h.includes('#') ? 'section' : 'page', value: h };
    return { kind: 'url', value: h };
}

export function buildHref(kind, value, message) {
    const v = (value || '').trim();
    if (kind === 'phone') return `tel:${v.replace(/[^\d+]/g, '')}`;
    if (kind === 'email') return `mailto:${v}`;
    if (kind === 'whatsapp') {
        const digits = v.replace(/\D/g, '');
        return `https://wa.me/${digits}${message ? `?text=${encodeURIComponent(message)}` : ''}`;
    }
    if (kind === 'url' && v && !/^([a-z][a-z0-9+.-]*:|\/|#)/i.test(v)) return `https://${v}`;
    return v;
}

const SOFT_BELOW = 1.2;     // natural width under 1.2 × the shown width looks soft on ordinary screens

/** {state: sharp|soft|unknown, natural: {w, h}, shown} — unknown until the image has loaded. */
export function imageQuality(img) {
    const natural = { w: img?.naturalWidth || 0, h: img?.naturalHeight || 0 };
    const shown = img?.isConnected ? Math.round(img.getBoundingClientRect().width) : 0;
    if (!img || !img.complete || !natural.w || !shown) return { state: 'unknown', natural, shown };
    return { state: natural.w < shown * SOFT_BELOW ? 'soft' : 'sharp', natural, shown };
}

export function isPlaceholder(img) {
    return !!img && ((img.getAttribute('src') || '').includes('placehold.co') || img.hasAttribute('data-image-prompt'));
}

/** The text at `selector` in another language copy of the page (stored HTML), or null. */
export function otherLanguageText(copyHtml, selector) {
    if (!copyHtml || !selector) return null;
    const doc = new DOMParser().parseFromString(`<body>${copyHtml}</body>`, 'text/html');
    let el = null;
    try { el = doc.body.querySelector(selector); } catch (_) { return null; }
    if (!el) return null;
    if (el.tagName === 'IMG') return el.getAttribute('alt') || '';
    return text(el);
}
