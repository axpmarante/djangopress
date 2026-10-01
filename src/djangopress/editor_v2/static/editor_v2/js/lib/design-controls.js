/**
 * What the Design panel shows for each element type: groups of rows, the
 * common ones visible and the rest under "More options". Pure data; the
 * panel (modules/design-panel.js) renders and runs them.
 *
 * Row kinds that work on one class-model property: seg, slider, swatches,
 * toggles. The others are handled by name in the panel.
 */

const ICON = {
    alignL: '<path d="M4 6h16M4 12h10M4 18h14"/>', alignC: '<path d="M4 6h16M7 12h10M5 18h14"/>',
    alignR: '<path d="M4 6h16M10 12h10M6 18h14"/>',
};
export const icon = (paths, size = 14) => `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths}</svg>`;

const ALIGN = { kind: 'seg', id: 'textAlign', prop: 'textAlign', label: 'Align',
    options: [['left', icon(ICON.alignL), 'Left'], ['center', icon(ICON.alignC), 'Centre'], ['right', icon(ICON.alignR), 'Right']] };
const SHADOW = { kind: 'seg', id: 'shadow', prop: 'shadow', label: 'Shadow', options: [[null, 'None'], ['md', 'Soft'], ['2xl', 'Strong']] };
export const TEXT_SHADOWS = { soft: '0 2px 18px rgba(0,0,0,.35)', strong: '0 3px 6px rgba(0,0,0,.6)' };

const TYPOGRAPHY = {
    key: 'typography', title: 'Typography',
    rows: [
        { kind: 'fontFamily', id: 'fontFamily', label: 'Font' },
        { kind: 'slider', id: 'fontSize', prop: 'fontSize', label: 'Size', min: 10, max: 120, step: 1, unit: 'px', fallback: el => parseFloat(getComputedStyle(el).fontSize) },
        { kind: 'seg', id: 'fontWeight', prop: 'fontWeight', label: 'Weight', options: [[300, 'Light'], [400, 'Regular'], [500, 'Medium'], [600, 'Semi'], [700, 'Bold']] },
        ALIGN,
        { kind: 'swatches', id: 'textColor', prop: 'textColor', label: 'Colour' },
    ],
    more: [
        { kind: 'seg', id: 'lineHeight', prop: 'lineHeight', label: 'Line height', options: [['tight', 'Tight'], ['normal', 'Normal'], ['relaxed', 'Relaxed']] },
        { kind: 'slider', id: 'letterSpacing', prop: 'letterSpacing', label: 'Letter spacing', min: -0.05, max: 0.3, step: 0.01, unit: 'em', fallback: () => 0 },
        { kind: 'seg', id: 'textTransform', prop: 'textTransform', label: 'Case', options: [[null, 'Aa', 'As typed'], ['uppercase', 'AA', 'Uppercase'], ['lowercase', 'aa', 'Lowercase']] },
        { kind: 'toggles', id: 'textStyle', label: 'Style', items: [
            { prop: 'fontStyle', on: 'italic', off: null, label: '<i>Italic</i>' },
            { prop: 'textDecoration', on: 'underline', off: null, label: '<u>Underline</u>' },
        ] },
        { kind: 'alpha', id: 'textAlpha', prop: 'textColor', label: 'Colour strength' },
        { kind: 'seg', id: 'textShadow', prop: 'textShadow', label: 'Text shadow', options: [[null, 'None'], [TEXT_SHADOWS.soft, 'Soft'], [TEXT_SHADOWS.strong, 'Strong']] },
        { kind: 'slider', id: 'maxWidth', prop: 'maxWidth', label: 'Max width', min: 200, max: 1400, step: 10, unit: 'px', fallback: el => Math.round(el.getBoundingClientRect().width) },
    ],
};

const SPACING = { key: 'spacing', title: 'Spacing', rows: [{ kind: 'box', id: 'box', label: '' }] };

export const COMMON = {
    key: 'visibility', title: 'Visibility & border', closed: true,
    rows: [
        { kind: 'show', id: 'show', label: 'Show on' },
        { kind: 'slider', id: 'borderWidth', prop: 'borderWidth', label: 'Border', min: 0, max: 8, step: 1, unit: 'px', fallback: () => 0 },
        { kind: 'swatches', id: 'borderColor', prop: 'borderColor', label: 'Border colour', when: p => (p.read('borderWidth') || 0) > 0 },
        { kind: 'seg', id: 'borderStyle', prop: 'borderStyle', label: 'Border style', when: p => (p.read('borderWidth') || 0) > 0,
          options: [[null, 'Solid'], ['dashed', 'Dashed'], ['dotted', 'Dotted']] },
        { kind: 'slider', id: 'opacity', prop: 'opacity', label: 'Opacity', min: 10, max: 100, step: 5, unit: '%', fallback: () => 100 },
        { kind: 'attr', id: 'anchor', attr: 'id', label: 'Anchor', placeholder: 'e.g. grupos  →  link as #grupos' },
    ],
};

export const PANELS = {
    heading: [TYPOGRAPHY, SPACING],
    text: [TYPOGRAPHY, SPACING],
    link: [TYPOGRAPHY, {
        key: 'link', title: 'Link',
        rows: [
            { kind: 'swatches', id: 'hoverText', prop: 'textColor', state: 'hover', label: 'Hover colour' },
            { kind: 'attr', id: 'href', attr: 'href', label: 'Goes to', placeholder: '/page/ or https://…' },
            { kind: 'newTab', id: 'newTab', label: 'New tab' },
        ],
    }, SPACING],
    button: [
        {
            key: 'button', title: 'Button',
            rows: [
                { kind: 'buttonStyle', id: 'buttonStyle', label: 'Style' },
                { kind: 'buttonSize', id: 'buttonSize', label: 'Size' },
                { kind: 'seg', id: 'borderRadius', prop: 'borderRadius', label: 'Corners', options: [[0, 'Square'], [4, 'Soft'], ['full', 'Round']] },
            ],
            more: [
                { kind: 'classChoice', id: 'icon', label: 'Icon', options: [
                    ['none', 'None', []],
                    ['before', '← Before', ["before:content-['←']", 'before:mr-2']],
                    ['after', 'After →', ["after:content-['→']", 'after:ml-2']],
                ] },
                { kind: 'seg', id: 'width', prop: 'width', label: 'Width', options: [[null, 'Fit text'], ['full', 'Full width']] },
                { kind: 'slider', id: 'btnFontSize', prop: 'fontSize', label: 'Text size', min: 11, max: 24, step: 1, unit: 'px', fallback: el => parseFloat(getComputedStyle(el).fontSize) },
                { kind: 'toggles', id: 'btnCase', label: 'Letters', items: [{ prop: 'textTransform', on: 'uppercase', off: null, label: 'UPPERCASE' }] },
                SHADOW,
                { kind: 'classChoice', id: 'hoverFx', label: 'On hover', options: [
                    ['colour', 'Colour', []],
                    ['lift', 'Lift', ['transition', 'hover:-translate-y-0.5', 'hover:shadow-lg']],
                    ['underline', 'Underline', ['hover:underline']],
                ] },
            ],
        },
        { key: 'colours', title: 'Colours', rows: [
            { kind: 'hoverSwitch', id: 'hoverSwitch', label: '' },
            { kind: 'buttonColor', id: 'fill', role: 'fill', label: 'Fill' },
            { kind: 'buttonColor', id: 'text', role: 'text', label: 'Text' },
        ] },
        { key: 'link', title: 'Link', rows: [
            { kind: 'attr', id: 'href', attr: 'href', label: 'Goes to', placeholder: '/page/ or https://…' },
            { kind: 'newTab', id: 'newTab', label: 'New tab' },
        ] },
        { ...SPACING, closed: true },
    ],
    image: [{
        key: 'image', title: 'Image',
        rows: [
            { kind: 'imageReplace', id: 'imageReplace', label: 'Image' },
            { kind: 'seg', id: 'aspectRatio', prop: 'aspectRatio', label: 'Shape', options: [[null, 'Original'], ['1/1', '1:1'], ['4/3', '4:3'], ['16/9', '16:9'], ['3/4', '3:4']] },
            { kind: 'percent', id: 'width', prop: 'width', label: 'Width', min: 20, max: 100, step: 5 },
            { kind: 'seg', id: 'borderRadius', prop: 'borderRadius', label: 'Corners', options: [[0, 'Square'], [12, 'Soft'], [24, 'Round']] },
        ],
        more: [
            { kind: 'focal', id: 'objectPosition', prop: 'objectPosition', label: 'Focus point' },
            { kind: 'seg', id: 'objectFit', prop: 'objectFit', label: 'Fit', options: [['cover', 'Fill frame'], ['contain', 'Whole image']] },
            SHADOW,
            { kind: 'toggles', id: 'imgFilters', label: 'Filters', items: [{ prop: 'grayscale', on: true, off: null, label: 'Black & white' }] },
            { kind: 'classChoice', id: 'zoom', label: 'On hover', options: [['none', 'Nothing', []], ['zoom', 'Zoom in', ['transition-transform', 'duration-300', 'hover:scale-105']]] },
            { kind: 'slider', id: 'brightness', prop: 'brightness', label: 'Brightness', min: 50, max: 150, step: 5, unit: '%', fallback: () => 100 },
        ],
    }, SPACING],
    section: [
        {
            key: 'background', title: 'Background',
            rows: [
                { kind: 'bgType', id: 'bgType', label: 'Type' },
                { kind: 'swatches', id: 'bgColor', prop: 'bgColor', label: 'Colour', when: p => p.bgType() === 'color' },
                { kind: 'bgImage', id: 'bgImage', label: 'Image', when: p => p.bgType() === 'image' },
                { kind: 'overlay', id: 'overlay', label: 'Darken', when: p => p.bgType() === 'image' },
                { kind: 'textTone', id: 'textTone', label: 'Text on it' },
                { kind: 'video', id: 'video', label: 'Video' },
            ],
            more: [
                { kind: 'overlayColor', id: 'overlayColor', label: 'Overlay colour', when: p => p.bgType() === 'image' },
                { kind: 'bgFocal', id: 'bgFocal', label: 'Focus point', when: p => p.bgType() === 'image' },
                { kind: 'bgFixed', id: 'bgFixed', label: 'Scrolling', when: p => p.bgType() === 'image' },
            ],
        },
        {
            key: 'layout', title: 'Layout',
            rows: [
                { kind: 'padY', id: 'padY', label: 'Space top/bottom' },
                { kind: 'contentWidth', id: 'contentWidth', label: 'Content width', when: p => !!p.innerContainer() },
                { ...ALIGN, label: 'Align content' },
            ],
            more: [
                { kind: 'seg', id: 'minHeight', prop: 'minHeight', label: 'Height', options: [[null, 'Fit content'], ['50vh', 'Half screen'], ['100vh', 'Full screen']] },
                { kind: 'classChoice', id: 'valign', label: 'Vertical align', when: p => !!p.read('minHeight'), options: [
                    ['none', 'Top', []], ['center', 'Middle', ['grid', 'content-center']], ['end', 'Bottom', ['grid', 'content-end']],
                ] },
                { kind: 'classToggles', id: 'dividers', label: 'Dividers', items: [
                    ['top', 'Line on top', ['border-t', 'border-black/10']],
                    ['bottom', 'Line at bottom', ['border-b', 'border-black/10']],
                ] },
            ],
        },
    ],
    container: [
        {
            key: 'layout', title: 'Layout',
            rows: [
                { kind: 'seg', id: 'gridCols', prop: 'gridCols', label: 'Columns', when: p => p.isGrid(), options: [[1, '1'], [2, '2'], [3, '3'], [4, '4']] },
                { kind: 'slider', id: 'gap', prop: 'gap', label: 'Gap', min: 0, max: 96, step: 4, unit: 'px', fallback: () => 0 },
                { kind: 'seg', id: 'alignItems', prop: 'alignItems', label: 'Align items', options: [['start', 'Top'], ['center', 'Middle'], [null, 'Same height']] },
            ],
            more: [
                { kind: 'classChoice', id: 'reverse', label: 'On mobile', options: [
                    ['none', 'Same order', []],
                    ['reverse', 'Reverse', ['max-md:flex', 'max-md:flex-col-reverse']],
                ] },
                { kind: 'seg', id: 'justifyContent', prop: 'justifyContent', label: 'Distribute', options: [[null, 'Start'], ['center', 'Centre'], ['between', 'Spread']] },
            ],
        },
        SPACING,
    ],
    other: [SPACING],
};
