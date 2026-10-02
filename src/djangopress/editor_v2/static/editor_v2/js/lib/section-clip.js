/**
 * "Copy section" clips: a section's stored HTML behind a marker comment that names
 * where it came from, so another DjangoPress site can paste it (editor_v2/paste.py).
 */
import { staticHtml } from './chat-preview.js';

const MARKER_RE = /<!--\s*djangopress:section\s+(\{[\s\S]*?\})\s*-->/;

export function makeClip(section) {
    const cfg = window.EDITOR_CONFIG || {};
    const meta = { site: cfg.siteName || location.host, section: section.getAttribute('data-section') || '',
                   lang: cfg.language || '', origin: location.origin };
    const copy = document.createElement('template');
    copy.innerHTML = staticHtml(section);
    const root = copy.content.firstElementChild;
    for (const el of [root, ...root.querySelectorAll('*')]) {
        [...el.classList].filter(c => c.startsWith('ev2-')).forEach(c => el.classList.remove(c));
        if (el.getAttribute('class') === '') el.removeAttribute('class');
        [...el.attributes].filter(a => a.name.startsWith('data-ev2') || a.name === 'contenteditable')
            .forEach(a => el.removeAttribute(a.name));
    }
    return `<!-- djangopress:section ${JSON.stringify(meta)} -->\n${root.outerHTML}`;
}

/** The clip's source ({site, section, lang, origin}) or null for plain HTML. */
export function clipMeta(text) {
    const m = MARKER_RE.exec(text || '');
    if (!m) return null;
    try { return JSON.parse(m[1]); } catch (_) { return null; }
}

/** Does this look like something the paste endpoint can take? */
export function looksLikeSection(text) {
    return /<section[\s>]/i.test(text || '') || !!clipMeta(text);
}
