/**
 * "Copy section" clips: a section's stored HTML behind a marker comment that names
 * where it came from, so another DjangoPress site can paste it (editor_v2/paste.py).
 */
import { staticHtml } from './chat-preview.js';
import { api } from './api.js';
import { getPendingCount, saveNow } from '../modules/changes.js';

const MARKER_RE = /<!--\s*djangopress:section\s+(\{[\s\S]*?\})\s*-->/;

/** The section as saved (template tags such as {% csrf_token %} intact), or null when it isn't saved yet. */
async function storedSection(name, lang) {
    const cfg = window.EDITOR_CONFIG || {};
    const params = { page_id: cfg.pageId || '' };
    if (cfg.contentTypeId && cfg.objectId) { params.content_type_id = cfg.contentTypeId; params.object_id = cfg.objectId; }
    try {
        const res = await api.get('/page-copies/', params);
        const html = res?.success ? (res.copies || {})[lang] : '';
        if (!html) return null;
        const tpl = document.createElement('template');
        tpl.innerHTML = html;
        const found = tpl.content.querySelector(`section[data-section="${CSS.escape(name)}"]`);
        return found ? found.outerHTML : null;
    } catch (_) {
        return null;
    }
}

/** A "Copy section" clip. The stored copy is preferred: the live page is rendered, so it holds this
 *  visitor's CSRF token and the site's own values where the template had tags. */
export async function makeClip(section) {
    const cfg = window.EDITOR_CONFIG || {};
    const name = section.getAttribute('data-section') || '';
    const meta = { site: cfg.siteName || location.host, section: name, lang: cfg.language || '', origin: location.origin };
    if (getPendingCount() > 0) await saveNow();         // the stored copy should include what is on screen
    const stored = await storedSection(name, cfg.language || '');
    if (stored) return `<!-- djangopress:section ${JSON.stringify(meta)} -->\n${stored}`;
    const copy = document.createElement('template');
    copy.innerHTML = staticHtml(section);
    const root = copy.content.firstElementChild;
    root.querySelectorAll('input[name="csrfmiddlewaretoken"]').forEach(i => i.replaceWith('{% csrf_token %}'));
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
