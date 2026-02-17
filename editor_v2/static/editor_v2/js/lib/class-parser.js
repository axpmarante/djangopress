/**
 * Parse and build Tailwind class strings for the Design tab dropdowns.
 */

import {
    CATEGORIES, HOVER_CATEGORIES, COLOR_FAMILIES, COLOR_SHADES, COLOR_KEYWORDS,
    FONT_SIZE_VALUES, TEXT_ALIGN_VALUES, DISPLAY_VALUES,
} from './tailwind-classes.js';

// Build sets for fast lookup
const COLOR_FAMILY_SET = new Set(COLOR_FAMILIES);
const COLOR_KEYWORD_SET = new Set(COLOR_KEYWORDS);
const COLOR_SHADE_SET = new Set(COLOR_SHADES);

/**
 * Determine if a class like "text-red-500" is a color class.
 * Returns { family, shade } or null.
 */
function parseColorClass(prefix, cls) {
    const suffix = cls.slice(prefix.length + 1); // skip prefix + dash
    if (!suffix) return null;

    // Keyword colors: text-white, bg-black, bg-transparent, text-current
    if (COLOR_KEYWORD_SET.has(suffix)) {
        return { family: suffix, shade: '' };
    }

    // Family-shade: text-red-500, bg-slate-100
    const dashIdx = suffix.lastIndexOf('-');
    if (dashIdx === -1) return null;
    const family = suffix.slice(0, dashIdx);
    const shade = suffix.slice(dashIdx + 1);
    if (COLOR_FAMILY_SET.has(family) && COLOR_SHADE_SET.has(shade)) {
        return { family, shade };
    }
    return null;
}

/**
 * Parse a space-separated class string into:
 *   { matched: Map<categoryKey, { prefix, value, color? }>, unmatched: string[] }
 *
 * categoryKey = "group:label", e.g. "Typography:Font Size"
 *
 * @param {string} classString
 * @param {object} [options]
 * @param {Array} [options.extraCategories] — additional category groups to parse (e.g. HOVER_CATEGORIES)
 */
export function parseClasses(classString, { extraCategories = [] } = {}) {
    const tokens = classString.split(/\s+/).filter(Boolean);
    const matched = new Map();
    const claimed = new Set();

    const allCategories = [...CATEGORIES, ...extraCategories];

    for (const group of allCategories) {
        for (const cat of group.items) {
            const key = `${group.group}:${cat.label}`;

            if (cat.exact) {
                // Display — match full class name
                for (const cls of tokens) {
                    if (cat.values.includes(cls) && !claimed.has(cls)) {
                        matched.set(key, { prefix: '', value: cls });
                        claimed.add(cls);
                        break;
                    }
                }
                continue;
            }

            for (const prefix of cat.prefixes) {
                if (matched.has(key)) break;
                for (const cls of tokens) {
                    if (claimed.has(cls)) continue;

                    if (cat.type === 'color') {
                        // Color category — must start with prefix-
                        if (!cls.startsWith(prefix + '-')) continue;
                        // Disambiguate text- prefix: skip if it's a font size or alignment
                        if (prefix === 'text') {
                            const afterDash = cls.slice(5); // 'text-'.length = 5
                            if (FONT_SIZE_VALUES.has(afterDash)) continue;
                            if (TEXT_ALIGN_VALUES.has(afterDash)) continue;
                        }
                        const color = parseColorClass(prefix, cls);
                        if (color) {
                            matched.set(key, { prefix, value: cls, color });
                            claimed.add(cls);
                            break;
                        }
                    } else {
                        // Non-color category — check each value
                        for (const val of cat.values) {
                            const expected = val === '' ? prefix : `${prefix}-${val}`;
                            if (cls === expected) {
                                // Disambiguate text- prefix
                                if (prefix === 'text' && cat.label === 'Font Size' && TEXT_ALIGN_VALUES.has(val)) continue;
                                if (prefix === 'text' && cat.label === 'Text Align' && FONT_SIZE_VALUES.has(val)) continue;
                                matched.set(key, { prefix, value: val, fullClass: cls });
                                claimed.add(cls);
                                break;
                            }
                        }
                        if (matched.has(key)) break;
                    }
                }
                if (matched.has(key)) break;
            }
        }
    }

    const unmatched = tokens.filter(cls => !claimed.has(cls));
    return { matched, unmatched };
}

/**
 * Build a class string from dropdown selections + unmatched classes.
 *
 * @param {Map<string, { prefix, value, color? }>} matched
 * @param {string[]} unmatched
 * @param {object} [options]
 * @param {Array} [options.extraCategories] — additional category groups (e.g. HOVER_CATEGORIES)
 * @returns {string}
 */
export function buildClassString(matched, unmatched, { extraCategories = [] } = {}) {
    const parts = [...unmatched];
    const allCategories = [...CATEGORIES, ...extraCategories];

    for (const [key, entry] of matched) {
        if (!entry) continue;

        const [groupName, catLabel] = key.split(':');
        const group = allCategories.find(g => g.group === groupName);
        const cat = group?.items.find(i => i.label === catLabel);

        if (cat?.exact) {
            // Display values are full class names
            if (entry.value) parts.push(entry.value);
        } else if (cat?.type === 'color') {
            const { family, shade } = entry.color || {};
            if (family) {
                if (COLOR_KEYWORD_SET.has(family)) {
                    parts.push(`${entry.prefix}-${family}`);
                } else if (shade) {
                    parts.push(`${entry.prefix}-${family}-${shade}`);
                }
            }
        } else {
            // Standard prefix-value
            if (entry.value === '' && entry.prefix) {
                parts.push(entry.prefix); // bare prefix: "rounded", "shadow"
            } else if (entry.value !== undefined && entry.value !== null) {
                parts.push(`${entry.prefix}-${entry.value}`);
            }
        }
    }

    return parts.join(' ');
}
