/**
 * Class model for the Design panel: maps design properties (font size,
 * padding-top, text colour, columns…) to Tailwind classes and back.
 *
 * - Reads every class that sets a property, including responsive variants
 *   (md:, lg:, max-md:, max-lg:, md:max-lg:), arbitrary values ([40px],
 *   [#C42014]) and the hover state, and resolves the value on each screen:
 *   mobile (< 768), tablet (768–1023), desktop (≥ 1024).
 * - Writes Elementor-style: a change on a screen also reaches the smaller
 *   screens that had the same value, then the property is re-emitted
 *   mobile-first (base, md:, lg:) in the place its old classes were.
 *   Classes of other properties, unknown variants (sm:, xl:, focus:…) and
 *   runtime classes are never touched.
 */
import { isRuntimeClass } from './dom.js';

export const DEVICES = ['mobile', 'tablet', 'desktop'];

// ---- variants ---------------------------------------------------------------

const SCREEN_VARIANTS = {
    '': { screens: ['mobile', 'tablet', 'desktop'], rank: 0 },
    'sm': { screens: ['tablet', 'desktop'], rank: 0.5 },     // ≥640: folded into tablet+desktop
    'md': { screens: ['tablet', 'desktop'], rank: 1 },
    'lg': { screens: ['desktop'], rank: 2 },
    'xl': { screens: ['desktop'], rank: 2.5 },               // ≥1280 / ≥1536: folded into desktop
    '2xl': { screens: ['desktop'], rank: 2.6 },
    'max-lg': { screens: ['mobile', 'tablet'], rank: 3 },
    'md:max-lg': { screens: ['tablet'], rank: 4 },
    'max-md': { screens: ['mobile'], rank: 5 },
};

/** Split "md:hover:text-[a:b]" into ['md', 'hover'] and 'text-[a:b]' (colons inside [] belong to the value). */
function splitVariants(cls) {
    const parts = [];
    let depth = 0, start = 0;
    for (let i = 0; i < cls.length; i++) {
        const ch = cls[i];
        if (ch === '[') depth++;
        else if (ch === ']') depth--;
        else if (ch === ':' && depth === 0) { parts.push(cls.slice(start, i)); start = i + 1; }
    }
    return { variants: parts, utility: cls.slice(start) };
}

/** { screen: key of SCREEN_VARIANTS, state: '' | 'hover' } or null for variants we don't manage. */
function parseVariants(variants) {
    let state = '';
    const screen = [];
    for (const v of variants) {
        if (v === 'hover') { if (state) return null; state = 'hover'; }
        else screen.push(v);
    }
    const key = screen.join(':');
    return key in SCREEN_VARIANTS ? { screen: key, state } : null;
}

// ---- values -----------------------------------------------------------------

const PALETTE_RE = /^(slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-(50|[1-9]00|950)$/;
const KEYWORD_COLORS = { white: '#FFFFFF', black: '#000000', transparent: 'transparent', current: 'currentColor', inherit: 'inherit' };
const FONT_SIZES = { xs: 12, sm: 14, base: 16, lg: 18, xl: 20, '2xl': 24, '3xl': 30, '4xl': 36, '5xl': 48, '6xl': 60, '7xl': 72, '8xl': 96, '9xl': 128 };
const FONT_WEIGHTS = { thin: 100, extralight: 200, light: 300, normal: 400, medium: 500, semibold: 600, bold: 700, extrabold: 800, black: 900 };
const TRACKING = { tighter: -0.05, tight: -0.025, normal: 0, wide: 0.025, wider: 0.05, widest: 0.1 };
const MAX_W = { xs: 320, sm: 384, md: 448, lg: 512, xl: 576, '2xl': 672, '3xl': 768, '4xl': 896, '5xl': 1024, '6xl': 1152, '7xl': 1280 };
const RADIUS = { none: 0, sm: 2, '': 4, md: 6, lg: 8, xl: 12, '2xl': 16, '3xl': 24, full: 'full' };
const OBJECT_POS = { center: '50% 50%', top: '50% 0%', bottom: '50% 100%', left: '0% 50%', right: '100% 50%',
    'left-top': '0% 0%', 'right-top': '100% 0%', 'left-bottom': '0% 100%', 'right-bottom': '100% 100%' };

/** Arbitrary value inside [ ]: "40px" → 40, "2.5rem" → 40. */
function lengthPx(raw) {
    const m = /^(-?\d*\.?\d+)(px|rem)?$/.exec(String(raw));
    if (!m) return null;
    return m[2] === 'rem' ? Number(m[1]) * 16 : Number(m[1]);
}
function spacingPx(token) {
    if (token === 'px') return 1;
    if (token === '0') return 0;
    if (/^\d+(\.5)?$/.test(token)) return Number(token) * 4;
    const arb = /^\[(.+)\]$/.exec(token);
    return arb ? lengthPx(arb[1]) : null;
}
// Tailwind's default spacing scale (no config on DjangoPress sites)
const SPACING_STEPS = new Set(['0.5', '1', '1.5', '2', '2.5', '3', '3.5', '4', '5', '6', '7', '8', '9', '10', '11', '12', '14', '16',
    '20', '24', '28', '32', '36', '40', '44', '48', '52', '56', '60', '64', '72', '80', '96']);
function spacingToken(px) {
    if (px === 0) return '0';
    if (px === 1) return 'px';
    const step = String(px / 4);
    return SPACING_STEPS.has(step) ? step : `[${px}px]`;
}
function colorValue(token) {
    const m = /^\[(#[0-9a-fA-F]{3,8})\](?:\/(\d+))?$/.exec(token);
    if (m) return m[1].toUpperCase() + (m[2] ? `/${m[2]}` : '');
    const [base, alpha] = token.split('/');
    if (base in KEYWORD_COLORS) return KEYWORD_COLORS[base] + (alpha ? `/${alpha}` : '');
    if (PALETTE_RE.test(base)) return base + (alpha ? `/${alpha}` : '');
    return null;
}
function colorToken(value) {
    const [base, alpha] = String(value).split('/');
    const suffix = alpha ? `/${alpha}` : '';
    if (base.startsWith('#')) {
        if (base.toUpperCase() === '#FFFFFF') return `white${suffix}`;
        if (base.toUpperCase() === '#000000') return `black${suffix}`;
        return `[${base.toUpperCase()}]${suffix}`;
    }
    if (base === 'transparent' || base === 'currentColor') return base === 'currentColor' ? 'current' : base;
    return base + suffix;
}
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
/** A class of a property whose value we can't read: never shown, but removed when the property is written. */
const UNKNOWN = Object.freeze({ unknown: true });
const SIDE_RE = /^(t|b|l|r|s|e|x|y|tl|tr|bl|br|ss|se|es|ee)-/;
const SCREEN_W = { sm: 640, md: 768, lg: 1024, xl: 1280, '2xl': 1536 };

// ---- properties ---------------------------------------------------------------
// A family: { prefix, parse(rest) → value|null, write(value) → rest|null, spec, covers? }.
// `covers` lists the other properties a shorthand also sets (p- sets top, bottom and x).

const spacingFamily = (prefix, spec, covers) => ({
    prefix, spec, covers,
    parse: rest => spacingPx(rest),
    write: v => spacingToken(v),
    negative: prefix.startsWith('m'),
});
const enumFamily = (map) => ({  // map: utility → value
    exact: true,
    parse: util => (util in map ? map[util] : null),
    write: v => Object.keys(map).find(k => same(map[k], v)) ?? null,
});

export const PROPERTIES = {
    paddingTop: { families: [spacingFamily('p', 0, ['paddingBottom', 'paddingX']), spacingFamily('py', 1, ['paddingBottom']), spacingFamily('pt', 2)] },
    paddingBottom: { families: [spacingFamily('p', 0, ['paddingTop', 'paddingX']), spacingFamily('py', 1, ['paddingTop']), spacingFamily('pb', 2)] },
    paddingX: { families: [spacingFamily('p', 0, ['paddingTop', 'paddingBottom']), spacingFamily('px', 1)] },
    marginTop: { families: [spacingFamily('m', 0, ['marginBottom', 'marginX']), spacingFamily('my', 1, ['marginBottom']), spacingFamily('mt', 2)] },
    marginBottom: { families: [spacingFamily('m', 0, ['marginTop', 'marginX']), spacingFamily('my', 1, ['marginTop']), spacingFamily('mb', 2)] },
    marginX: { families: [spacingFamily('m', 0, ['marginTop', 'marginBottom']), spacingFamily('mx', 1)] },
    gap: { families: [spacingFamily('gap', 0)] },
    fontSize: { families: [{
        prefix: 'text', spec: 0,
        parse: rest => {
            const [size] = rest.split('/');
            if (size in FONT_SIZES) return FONT_SIZES[size];
            const arb = /^\[(?:length:)?(.+)\]$/.exec(size);
            if (!arb) return null;
            if (/^(clamp|calc|var|min|max)\(/.test(arb[1])) return arb[1];
            return lengthPx(arb[1]);
        },
        write: v => (typeof v === 'number' ? `[${v}px]` : `[${v}]`),
    }] },
    textColor: { families: [{ prefix: 'text', spec: 0, parse: colorValue, write: colorToken }] },
    bgColor: { families: [{ prefix: 'bg', spec: 0, parse: colorValue, write: colorToken }] },
    borderColor: { families: [{ prefix: 'border', spec: 0, parse: colorValue, write: colorToken }] },
    borderWidth: { families: [
        { exact: true, parse: u => (u === 'border' ? 1 : null), write: v => (v === 1 ? 'border' : null) },
        { prefix: 'border', spec: 0,
          parse: r => (/^(0|2|4|8)$/.test(r) ? Number(r) : (/^\[(\d+)px\]$/.exec(r) || [])[1] !== undefined ? Number(/^\[(\d+)px\]$/.exec(r)[1]) : null),
          write: v => ([0, 2, 4, 8].includes(v) ? String(v) : `[${v}px]`) },
    ] },
    borderStyle: { families: [enumFamily({ 'border-solid': 'solid', 'border-dashed': 'dashed', 'border-dotted': 'dotted', 'border-double': 'double', 'border-none': 'none' })] },
    fontWeight: { families: [{
        prefix: 'font', spec: 0,
        parse: r => (r in FONT_WEIGHTS ? FONT_WEIGHTS[r] : (/^\[(\d{3})\]$/.exec(r) || [])[1] ? Number(/^\[(\d{3})\]$/.exec(r)[1]) : null),
        write: v => Object.keys(FONT_WEIGHTS).find(k => FONT_WEIGHTS[k] === v) ?? `[${v}]`,
    }] },
    fontFamily: { families: [{
        prefix: 'font', spec: 0,
        parse: r => {
            if (['sans', 'serif', 'mono'].includes(r)) return r;
            const m = /^\[(?:family-name:)?'?([^',\]]+)'?(?:,[^\]]*)?\]$/.exec(r);
            return m && !/^\d+$/.test(m[1]) ? m[1].replace(/_/g, ' ') : null;
        },
        write: v => (['sans', 'serif', 'mono'].includes(v) ? v : `['${String(v).replace(/ /g, '_')}']`),
    }] },
    lineHeight: { families: [{
        prefix: 'leading', spec: 0,
        owns: true,
        parse: r => (['none', 'tight', 'snug', 'normal', 'relaxed', 'loose'].includes(r) ? r : /^(3|4|5|6|7|8|9|10)$/.test(r) ? `${Number(r) * 4}px` : (/^\[(.+)\]$/.exec(r) || [])[1] ?? null),
        write: v => (['none', 'tight', 'snug', 'normal', 'relaxed', 'loose'].includes(v) ? v : `[${v}]`),
    }] },
    letterSpacing: { families: [{
        prefix: 'tracking', spec: 0, owns: true,
        parse: r => (r in TRACKING ? TRACKING[r] : (/^\[(-?\d*\.?\d+)em\]$/.exec(r) || [])[1] !== undefined ? Number(/^\[(-?\d*\.?\d+)em\]$/.exec(r)[1]) : null),
        write: v => Object.keys(TRACKING).find(k => TRACKING[k] === v) ?? `[${v}em]`,
    }] },
    textAlign: { families: [enumFamily({ 'text-left': 'left', 'text-center': 'center', 'text-right': 'right', 'text-justify': 'justify', 'text-start': 'left', 'text-end': 'right' })] },
    textTransform: { families: [enumFamily({ uppercase: 'uppercase', lowercase: 'lowercase', capitalize: 'capitalize', 'normal-case': 'none' })] },
    fontStyle: { families: [enumFamily({ italic: 'italic', 'not-italic': 'normal' })] },
    textDecoration: { families: [enumFamily({ underline: 'underline', 'line-through': 'line-through', 'no-underline': 'none' })] },
    textShadow: { families: [{ exact: true, parse: u => (/^\[text-shadow:(.+)\]$/.exec(u) || [])[1]?.replace(/_/g, ' ') ?? null, write: v => (v === 'none' ? null : `[text-shadow:${String(v).replace(/ /g, '_')}]`) }] },
    maxWidth: { families: [{
        prefix: 'max-w', spec: 0,
        owns: true,
        parse: r => {
            if (r in MAX_W) return MAX_W[r];
            if (['none', 'full', 'prose'].includes(r)) return r;
            const screen = /^screen-(sm|md|lg|xl|2xl)$/.exec(r);
            if (screen) return SCREEN_W[screen[1]];
            const arb = /^\[(.+)\]$/.exec(r);
            return arb ? lengthPx(arb[1]) : null;
        },
        write: v => (typeof v === 'number' ? `[${v}px]` : v),
    }] },
    borderRadius: { families: [
        { exact: true, parse: u => (u === 'rounded' ? 4 : null), write: v => (v === 4 ? 'rounded' : null) },
        { prefix: 'rounded', spec: 0,
          owns: true,
          parse: r => (r in RADIUS ? RADIUS[r] : /^\[(.+)\]$/.test(r) ? lengthPx(/^\[(.+)\]$/.exec(r)[1]) : null),
          write: v => (v === 'full' ? 'full' : v === 0 ? 'none' : `[${v}px]`) },
    ] },
    shadow: { families: [
        { exact: true, parse: u => (u === 'shadow' ? 'default' : null), write: v => (v === 'default' ? 'shadow' : null) },
        { prefix: 'shadow', spec: 0, owns: true, parse: r => (['sm', 'md', 'lg', 'xl', '2xl', 'inner', 'none'].includes(r) || /^\[.+\]$/.test(r) ? r : null), write: v => v },
    ] },
    opacity: { families: [{
        prefix: 'opacity', spec: 0, owns: true,
        parse: r => (/^\d+$/.test(r) ? Number(r) : (/^\[(0?\.\d+|1)\]$/.exec(r) || [])[1] ? Math.round(Number(/^\[(0?\.\d+|1)\]$/.exec(r)[1]) * 100) : null),
        write: v => (v % 5 === 0 ? String(v) : `[${v / 100}]`),
    }] },
    display: { families: [enumFamily({ block: 'block', 'inline-block': 'inline-block', inline: 'inline', flex: 'flex', 'inline-flex': 'inline-flex', grid: 'grid', 'inline-grid': 'inline-grid', hidden: 'hidden', contents: 'contents',
        'list-item': 'list-item', table: 'table', 'table-row': 'table-row', 'table-cell': 'table-cell', 'flow-root': 'flow-root' })] },
    gridCols: { families: [{ prefix: 'grid-cols', spec: 0, owns: true, parse: r => (/^\d+$/.test(r) ? Number(r) : r === 'none' ? 'none' : null), write: v => String(v) }] },
    alignItems: { families: [enumFamily({ 'items-start': 'start', 'items-center': 'center', 'items-end': 'end', 'items-stretch': 'stretch', 'items-baseline': 'baseline' })] },
    justifyContent: { families: [enumFamily({ 'justify-start': 'start', 'justify-center': 'center', 'justify-end': 'end', 'justify-between': 'between', 'justify-around': 'around', 'justify-evenly': 'evenly' })] },
    width: { families: [{
        prefix: 'w', spec: 0, owns: true,
        parse: r => (r === 'full' ? 'full' : r === 'auto' ? 'auto' : /^\d+(\.5)?$/.test(r) ? `${Number(r) * 4}px` : (/^\[(\d+(?:\.\d+)?)%\]$/.exec(r) || [])[1] ? `${/^\[(\d+(?:\.\d+)?)%\]$/.exec(r)[1]}%`
            : /^\d+\/\d+$/.test(r) ? `${Math.round(r.split('/')[0] / r.split('/')[1] * 1000) / 10}%` : (/^\[(\d+)px\]$/.exec(r) || [])[1] ? `${/^\[(\d+)px\]$/.exec(r)[1]}px` : null),
        write: v => (v === 'full' || v === 'auto' ? v : `[${v}]`),
    }] },
    aspectRatio: { families: [{
        prefix: 'aspect', spec: 0, owns: true,
        parse: r => ({ auto: 'auto', square: '1/1', video: '16/9' }[r] ?? (/^\[(\d+\/\d+)\]$/.exec(r) || [])[1] ?? null),
        write: v => (v === 'auto' ? 'auto' : v === '1/1' ? 'square' : v === '16/9' ? 'video' : `[${v}]`),
    }] },
    objectFit: { families: [enumFamily({ 'object-cover': 'cover', 'object-contain': 'contain', 'object-fill': 'fill', 'object-none': 'none', 'object-scale-down': 'scale-down' })] },
    objectPosition: { families: [{
        prefix: 'object', spec: 0,
        parse: r => OBJECT_POS[r] ?? (/^\[(\d+)%_(\d+)%\]$/.exec(r) ? `${/^\[(\d+)%_(\d+)%\]$/.exec(r)[1]}% ${/^\[(\d+)%_(\d+)%\]$/.exec(r)[2]}%` : null),
        write: v => (Object.keys(OBJECT_POS).find(k => OBJECT_POS[k] === v) ?? `[${String(v).replace(' ', '_')}]`),
    }] },
    minHeight: { families: [{
        prefix: 'min-h', spec: 0, owns: true,
        parse: r => (r === 'screen' ? '100vh' : r === '0' ? 'auto' : r === 'full' ? '100%' : (/^\[(.+)\]$/.exec(r) || [])[1] ?? null),
        write: v => (v === 'auto' ? '0' : v === '100vh' ? 'screen' : v === '100%' ? 'full' : `[${v}]`),
    }] },
    grayscale: { families: [enumFamily({ grayscale: true, 'grayscale-0': false })] },
    brightness: { families: [{
        prefix: 'brightness', spec: 0,
        parse: r => (/^\d+$/.test(r) ? Number(r) : (/^\[(\d*\.?\d+)\]$/.exec(r) || [])[1] ? Math.round(Number(/^\[(\d*\.?\d+)\]$/.exec(r)[1]) * 100) : null),
        write: v => ([0, 50, 75, 90, 95, 100, 105, 110, 125, 150, 200].includes(v) ? String(v) : `[${v / 100}]`),
    }] },
};

// ---- matching -----------------------------------------------------------------

/** How a class sets `prop`: { value, variant, family, spec } or null. */
function match(cls, prop) {
    if (isRuntimeClass(cls)) return null;
    const { variants, utility } = splitVariants(cls);
    const variant = parseVariants(variants);
    if (!variant) return null;
    let util = utility, negative = false;
    if (util.startsWith('!')) util = util.slice(1);            // important modifier: same property
    if (util.startsWith('-')) { negative = true; util = util.slice(1); }
    for (const family of PROPERTIES[prop].families) {
        let value = null;
        if (family.exact) {
            if (negative) continue;
            value = family.parse(util);
        } else if (util.startsWith(family.prefix + '-')) {
            if (negative && !family.negative) continue;
            value = family.parse(util.slice(family.prefix.length + 1));
            if (value !== null && negative) value = -value;
        }
        if (value !== null && value !== undefined) return { value, variant, family, spec: family.spec || 0 };
    }
    // an owned prefix we couldn't read (max-w-[min(90vw,60rem)], leading-[1.1em]…): still this property's class
    for (const family of PROPERTIES[prop].families) {
        if (family.owns && !negative && util.startsWith(family.prefix + '-') && !SIDE_RE.test(util.slice(family.prefix.length + 1))) {
            return { value: UNKNOWN, variant, family, spec: family.spec || 0 };
        }
    }
    return null;
}

/** The classes in `list` that set `prop` (any screen or state). */
export function classesOf(list, prop) {
    return list.filter(c => match(c, prop));
}

/** { mobile, tablet, desktop } for `prop` in `state` ('' or 'hover'); null when unset. */
export function readValues(list, prop, state = '') {
    const best = {};
    list.forEach((cls, index) => {
        const m = match(cls, prop);
        if (!m || m.variant.state !== state || m.value === UNKNOWN) return;
        const { screens, rank } = SCREEN_VARIANTS[m.variant.screen];
        for (const device of screens) {
            const cur = best[device];
            const key = [rank, m.spec, index];
            if (!cur || key[0] > cur.key[0] || (key[0] === cur.key[0] && (key[1] > cur.key[1] || (key[1] === cur.key[1] && key[2] > cur.key[2])))) {
                best[device] = { key, value: m.value };
            }
        }
    });
    return Object.fromEntries(DEVICES.map(d => [d, best[d] ? best[d].value : null]));
}

// ---- writing ------------------------------------------------------------------

function prefixFor(screen, state) {
    return (screen ? screen + ':' : '') + (state ? state + ':' : '');
}

/** Variant/value pairs that produce `values` ({mobile, tablet, desktop}). */
function emission({ mobile: m, tablet: t, desktop: d }) {
    if (m === null && t === null && d === null) return [];
    if (m !== null && t !== null && d !== null) {
        const out = [['', m]];
        if (!same(t, m)) out.push(['md', t]);
        if (!same(d, t)) out.push(['lg', d]);
        return out;
    }
    if (m === null && t !== null && d !== null) return same(d, t) ? [['md', t]] : [['md', t], ['lg', d]];
    if (m === null && t === null) return [['lg', d]];
    // a smaller screen has a value a larger one doesn't: desktop-first variants
    const out = [];
    if (m !== null && same(m, t)) out.push(['max-lg', m]);
    else {
        if (m !== null) out.push(['max-md', m]);
        if (t !== null) out.push(['md:max-lg', t]);
    }
    if (d !== null) out.push(['lg', d]);
    return out;
}

function writeClass(prop, family, screen, state, value, negativeOk = true) {
    let v = value, neg = '';
    if (typeof v === 'number' && v < 0 && family.negative && negativeOk) { neg = '-'; v = -v; }
    const rest = family.write(v);
    if (rest === null || rest === undefined) return null;
    const util = family.exact ? rest : `${family.prefix}-${rest}`;
    return prefixFor(screen, state) + neg + util;
}

/** The family new classes for `prop` are written with (the most specific one, e.g. pt- not p-). */
function writingFamily(prop) {
    const families = PROPERTIES[prop].families;
    return families.reduce((a, b) => ((b.spec || 0) > (a.spec || 0) ? b : a), families[families.length - 1]);
}

/**
 * Set `prop` to `value` on `device` (state '' or 'hover') and return the new class list.
 * opts.unsetAs: value to assume for screens that have none (e.g. the element's natural
 * display), so a change on one screen doesn't leave the others undefined.
 */
export function writeValue(list, prop, device, value, state = '', opts = {}) {
    const cur = readValues(list, prop, state);
    if (opts.unsetAs !== undefined) for (const d of DEVICES) if (cur[d] === null) cur[d] = opts.unsetAs;
    const next = { ...cur };
    if (device === 'desktop') {
        next.desktop = value;
        if (same(cur.tablet, cur.desktop)) {
            next.tablet = value;
            if (same(cur.mobile, cur.tablet)) next.mobile = value;
        }
    } else if (device === 'tablet') {
        next.tablet = value;
        if (same(cur.mobile, cur.tablet)) next.mobile = value;
    } else {
        next.mobile = value;
    }
    return writeValues(list, prop, next, state);
}

/** Set exact values per screen ({mobile, tablet, desktop}, null = unset) and return the new class list. */
export function writeValues(list, prop, next, state = '') {
    // remove this property's classes (this state only); shorthands give back what they set elsewhere
    const removed = [];
    const expansions = [];
    let insertAt = -1;
    const kept = [];
    list.forEach(cls => {
        const m = match(cls, prop);
        if (!m || m.variant.state !== state) { kept.push(cls); return; }
        if (insertAt < 0) insertAt = kept.length;
        removed.push({ cls, m });
        for (const other of m.family.covers || []) {
            const overridden = list.some(c => {
                const o = match(c, other);
                return o && o.variant.screen === m.variant.screen && o.variant.state === state && o.spec > m.spec;
            });
            if (overridden || m.value === UNKNOWN) continue;
            const fam = writingFamily(other);
            const c = writeClass(other, fam, m.variant.screen, state, m.value);
            if (c) expansions.push(c);
        }
    });

    const family = writingFamily(prop);
    const fresh = emission(next).map(([screen, v]) => {
        // reuse the original spelling when the same variant already had this value (text-4xl stays text-4xl)
        const old = removed.find(r => r.m.variant.screen === screen && same(r.m.value, v) && r.m.family === family);
        return old ? old.cls : writeClass(prop, family, screen, state, v);
    }).filter(Boolean);
    const added = [...fresh, ...expansions];
    if (insertAt < 0) return [...kept, ...added];
    return [...kept.slice(0, insertAt), ...added, ...kept.slice(insertAt)];
}
