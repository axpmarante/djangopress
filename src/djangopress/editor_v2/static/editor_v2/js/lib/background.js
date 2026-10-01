/**
 * Section background helpers (moved from the sidebar): the background image
 * and its overlay live in the inline style as
 * "linear-gradient(rgba…, rgba…), url('…')", plus a data-overlay attribute.
 */

export function hexToRgb(hex) {
    const m = String(hex || '').replace('#', '').match(/.{2}/g);
    if (!m) return { r: 0, g: 0, b: 0 };
    return { r: parseInt(m[0], 16), g: parseInt(m[1], 16), b: parseInt(m[2], 16) };
}

export function rgbToHex(rgb) {
    if (!rgb) return '';
    if (rgb.startsWith('#')) return rgb.toUpperCase();
    const match = rgb.match(/(\d+)/g);
    if (!match || match.length < 3) return '';
    return '#' + match.slice(0, 3).map(n => parseInt(n).toString(16).padStart(2, '0')).join('').toUpperCase();
}

/** "url(...)" or "linear-gradient(rgba(...), rgba(...)), url(...)" → { url, overlayColor, overlayOpacity } */
export function parseBgImage(bgImage) {
    if (!bgImage || bgImage === 'none') return { url: '', overlayColor: '', overlayOpacity: 0 };
    let url = '';
    let overlayColor = '';
    let overlayOpacity = 0;
    const urlMatch = bgImage.match(/url\(["']?([^"')]+)["']?\)/);
    if (urlMatch) url = urlMatch[1];
    const gradMatch = bgImage.match(/linear-gradient\(\s*rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)/);
    if (gradMatch) {
        overlayOpacity = parseFloat(gradMatch[4]);
        overlayColor = '#' + [gradMatch[1], gradMatch[2], gradMatch[3]].map(n => parseInt(n).toString(16).padStart(2, '0')).join('').toUpperCase();
    }
    return { url, overlayColor, overlayOpacity };
}

export function composeBgImage(url, overlayColor, overlayOpacity) {
    if (overlayOpacity > 0 && overlayColor) {
        const { r, g, b } = hexToRgb(overlayColor);
        const rgba = `rgba(${r}, ${g}, ${b}, ${overlayOpacity})`;
        return url ? `linear-gradient(${rgba}, ${rgba}), url('${url}')` : `linear-gradient(${rgba}, ${rgba})`;
    }
    return url ? `url('${url}')` : '';
}

export function extractYouTubeId(url) {
    if (!url) return null;
    const m = url.match(/(?:youtube\.com\/watch\?.*v=|youtube\.com\/embed\/|youtu\.be\/)([a-zA-Z0-9_-]{11})/);
    return m ? m[1] : null;
}

export function videoDisplayUrl(url) {
    const id = extractYouTubeId(url);
    return id ? `https://www.youtube.com/watch?v=${id}` : (url || '');
}
