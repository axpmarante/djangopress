/**
 * Tailwind CSS class definitions for the Design tab dropdowns.
 * Pure data — no DOM logic.
 */

// --- Color palette ---

export const COLOR_FAMILIES = [
    'slate', 'gray', 'zinc', 'neutral', 'stone',
    'red', 'orange', 'amber', 'yellow', 'lime',
    'green', 'emerald', 'teal', 'cyan', 'sky',
    'blue', 'indigo', 'violet', 'purple', 'fuchsia',
    'pink', 'rose',
];

export const COLOR_SHADES = [
    '50', '100', '200', '300', '400', '500', '600', '700', '800', '900', '950',
];

/** Standalone color keywords (no shade suffix). */
export const COLOR_KEYWORDS = ['white', 'black', 'transparent', 'current'];

// --- Spacing scale (shared by padding, margin, gap) ---

const SPACING = [
    '0', 'px', '0.5', '1', '1.5', '2', '2.5', '3', '3.5', '4', '5', '6', '7', '8',
    '9', '10', '11', '12', '14', '16', '20', '24', '28', '32', '36', '40', '44',
    '48', '52', '56', '60', '64', '72', '80', '96',
];

const SPACING_WITH_AUTO = ['auto', ...SPACING];

// --- Category definitions ---

/**
 * Each category: { label, prefixes[], values[], type? }
 *
 * `prefixes` — Tailwind prefixes that map to this category.
 *   e.g. ['p', 'px', 'py', 'pt', 'pr', 'pb', 'pl'] for padding.
 *   The first prefix is the "canonical" one shown in the dropdown.
 *
 * `values` — the valid suffixes (after the dash).
 *
 * `type` — 'color' for two-select color pickers, 'default' (omit) for single select.
 *
 * `exact` — true if the class is a standalone keyword (e.g. 'flex', 'hidden').
 */
export const CATEGORIES = [
    // --- Typography ---
    {
        group: 'Typography',
        items: [
            {
                label: 'Font Size',
                prefixes: ['text'],
                values: ['xs', 'sm', 'base', 'lg', 'xl', '2xl', '3xl', '4xl', '5xl', '6xl', '7xl', '8xl', '9xl'],
            },
            {
                label: 'Font Weight',
                prefixes: ['font'],
                values: ['thin', 'extralight', 'light', 'normal', 'medium', 'semibold', 'bold', 'extrabold', 'black'],
            },
            {
                label: 'Text Align',
                prefixes: ['text'],
                values: ['left', 'center', 'right', 'justify'],
            },
            {
                label: 'Text Color',
                prefixes: ['text'],
                type: 'color',
            },
        ],
    },
    // --- Spacing ---
    {
        group: 'Spacing',
        items: [
            {
                label: 'Padding',
                prefixes: ['p', 'px', 'py', 'pt', 'pr', 'pb', 'pl'],
                values: SPACING,
            },
            {
                label: 'Margin',
                prefixes: ['m', 'mx', 'my', 'mt', 'mr', 'mb', 'ml'],
                values: SPACING_WITH_AUTO,
            },
            {
                label: 'Gap',
                prefixes: ['gap', 'gap-x', 'gap-y'],
                values: SPACING,
            },
        ],
    },
    // --- Layout ---
    {
        group: 'Layout',
        items: [
            {
                label: 'Display',
                prefixes: [''],
                values: ['block', 'inline-block', 'inline', 'flex', 'inline-flex', 'grid', 'inline-grid', 'hidden'],
                exact: true,
            },
            {
                label: 'Border Radius',
                prefixes: ['rounded'],
                values: ['none', 'sm', '', 'md', 'lg', 'xl', '2xl', '3xl', 'full'],
            },
            {
                label: 'Shadow',
                prefixes: ['shadow'],
                values: ['none', 'sm', '', 'md', 'lg', 'xl', '2xl', 'inner'],
            },
            {
                label: 'Opacity',
                prefixes: ['opacity'],
                values: ['0', '5', '10', '15', '20', '25', '30', '35', '40', '45', '50',
                         '55', '60', '65', '70', '75', '80', '85', '90', '95', '100'],
            },
        ],
    },
    // --- Background ---
    {
        group: 'Background',
        items: [
            {
                label: 'Background',
                prefixes: ['bg'],
                type: 'color',
            },
        ],
    },
];

// --- Hover state categories (shown for buttons/links) ---

export const HOVER_CATEGORIES = [
    {
        group: 'Hover',
        items: [
            {
                label: 'Text Color',
                prefixes: ['hover:text'],
                type: 'color',
                variant: 'hover',
            },
            {
                label: 'Background',
                prefixes: ['hover:bg'],
                type: 'color',
                variant: 'hover',
            },
            {
                label: 'Border Color',
                prefixes: ['hover:border'],
                type: 'color',
                variant: 'hover',
            },
        ],
    },
];

// --- Lookup sets for disambiguation ---

/** Font size values — used to distinguish text-lg (size) from text-red-500 (color). */
export const FONT_SIZE_VALUES = new Set(
    CATEGORIES[0].items[0].values
);

/** Text align values — used to distinguish text-center (align) from text-sm (size). */
export const TEXT_ALIGN_VALUES = new Set(
    CATEGORIES[0].items[2].values
);

/** Display values — matched as exact class names (no prefix). */
export const DISPLAY_VALUES = new Set(
    CATEGORIES[2].items[0].values
);
