"""Paste a section copied from another DjangoPress site.

The editor's "Copy section" puts the section's stored HTML on the clipboard behind a
marker comment that names the source (site, section, language, origin). Pasting reads
that clip, cleans it, makes it fit this page (a free section name, a form this site has)
and reports what needs a look (links to pages this site lacks). Its images are copied
into this site's library only when the section is added, so a discarded paste leaves
nothing behind.
"""
import json
import os
import re
from urllib.parse import unquote, urljoin, urlparse

from bs4 import BeautifulSoup
from django.core.files.base import ContentFile
from django.utils.text import slugify

from djangopress.core.models import DynamicForm, Page, SiteImage, SiteSettings
from djangopress.editor_v2 import structure

MARKER_RE = re.compile(r'<!--\s*djangopress:section\s+(\{.*?\})\s*-->', re.DOTALL)
FORM_RE = re.compile(r'^/forms/([^/]+)/submit/?$')
URL_RE = re.compile(r'''url\(\s*(['"]?)([^'")]+)\1\s*\)''')
PLACEHOLDER_HOSTS = ('placehold.co', 'via.placeholder.com', 'placeholder.com')
NOT_PAGES = ('/media/', '/static/', '/forms/', '/editor-v2/', '/backoffice/', '/admin/')


def _soup(html):
    return BeautifulSoup(html or '', 'html.parser')


def read_clip(text):
    """(section_html, meta) from what the operator pasted: a "Copy section" clip or plain HTML."""
    text = (text or '').strip()
    meta = {}
    found = MARKER_RE.search(text)
    if found:
        try:
            meta = json.loads(found.group(1))
        except ValueError:
            meta = {}
        text = MARKER_RE.sub('', text).strip()
    if not text:
        raise ValueError('Nothing to paste: copy a section first (right-click a section → Copy section)')
    soup = _soup(text)
    section = soup.find('section')
    if section is None:
        if not soup.get_text(strip=True) and soup.find(True) is None:
            raise ValueError('That is not a section: copy one with right-click → Copy section')
        wrapper = _soup('<section data-section="pasted" id="pasted"></section>').section
        for node in list(soup.contents):
            wrapper.append(node.extract())
        section = wrapper
    return str(section), meta


DROP_TAGS = ['script', 'object', 'embed', 'link', 'meta', 'base', 'applet', 'frame', 'frameset']
URL_ATTRS = ('href', 'src', 'action', 'formaction', 'xlink:href', 'data', 'poster')
SAFE_DATA_RE = re.compile(r'^data:image/(png|jpe?g|gif|webp|avif);', re.I)


def _unsafe_url(attr, value):
    v = re.sub(r'[\s\x00-\x1f]+', '', value or '').lower()
    if v.startswith(('javascript:', 'vbscript:')):
        return True
    return v.startswith('data:') and not (attr == 'src' and SAFE_DATA_RE.match(v))


def _clean(section):
    """Drop what could run code (in the editor's preview, or for visitors once added) and the editor's own state.
    A form's rendered CSRF input (copied from a live page) goes back to {% csrf_token %}: the copied value is the
    copier's own secret and would fail every visitor's submission."""
    for tag in section.find_all(DROP_TAGS):
        tag.decompose()
    for iframe in section.find_all('iframe'):
        src = (iframe.get('src') or '').strip().lower()
        if iframe.has_attr('srcdoc') or not src.startswith(('https://', 'http://')):
            iframe.decompose()
    for token in section.find_all('input', attrs={'name': 'csrfmiddlewaretoken'}):
        token.replace_with('{% csrf_token %}')
    for el in [section, *section.find_all(True)]:
        for attr in list(el.attrs):
            low = attr.lower()
            if low.startswith('on') or low.startswith('data-ev2') or low == 'contenteditable':
                del el[attr]
            elif low in URL_ATTRS and _unsafe_url(low, el.get(attr)):
                del el[attr]
        classes = [c for c in (el.get('class') or []) if not c.startswith('ev2-')]
        if classes:
            el['class'] = classes
        elif el.has_attr('class'):
            del el['class']


def _page_names(page):
    used = set()
    for html in (page.html_content_i18n or {}).values():
        used |= {s.get('data-section') for s in _soup(html).find_all('section')}
    return used


def _free_name(page, section):
    base = slugify(section.get('data-section') or '') or 'pasted'
    used = _page_names(page)
    name = base if base not in used else structure.next_free_section_name(_soup(''), base, extra_used=used)
    section['data-section'] = name
    section['id'] = name
    return name


def _image_urls(section):
    """[(element, attribute, url)] for every image the section shows."""
    found = []
    for img in section.find_all(['img', 'source']):
        if img.get('src'):
            found.append((img, 'src', img['src']))
    for el in [section, *section.find_all(style=True)]:
        for m in URL_RE.finditer(el.get('style') or ''):
            found.append((el, 'style', m.group(2)))
    return found


def _absolute(section, origin):
    if not origin:
        return
    for el, attr, url in _image_urls(section):
        if url.startswith('/') and not url.startswith('//'):
            full = urljoin(origin, url)
            el[attr] = full if attr == 'src' else el[attr].replace(url, full)


def _media_base():
    """Where this site's files live: its own bucket folder, or /media/ for local storage."""
    from django.core.files.storage import default_storage
    return default_storage.url('')


def _external(url, own_origin=''):
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        return False
    return not any(parsed.hostname.endswith(h) for h in PLACEHOLDER_HOSTS) and not _own(url, own_origin)


def _own(url, own_origin=''):
    """By address, not by file name: every site keeps its images under site_images/."""
    base = _media_base()
    if base.startswith(('http://', 'https://')):
        return url.startswith(base)
    origin = (own_origin or '').rstrip('/')
    return bool(origin) and url.startswith(origin + base)


def _forms(section):
    """Point forms at one of this site's forms; return the checks to show."""
    checks = []
    active = list(DynamicForm.objects.filter(is_active=True).order_by('name'))
    slugs = {f.slug: f for f in active}
    fallback = slugs.get('contact') or (active[0] if active else None)
    for form in section.find_all('form'):
        m = FORM_RE.match(form.get('action') or '')
        if not m or m.group(1) in slugs:
            continue
        if fallback is None:
            checks.append({'level': 'warn', 'text': "This site has no forms: the form in this section won't send. "
                                                    "Add one in Forms, or remove it."})
            continue
        form['action'] = f'/forms/{fallback.slug}/submit/'
        checks.append({'level': 'warn', 'text': f'Form "{m.group(1)}" doesn\'t exist here: it will post to {fallback.name}'})
    return checks


def _page_paths():
    settings = SiteSettings.load()
    codes = settings.get_language_codes() if settings else ['pt', 'en']
    slugs = {''}
    for p in Page.objects.filter(is_active=True):
        slugs |= {s.strip('/') for s in (p.slug_i18n or {}).values() if s}
    home = settings.homepage if settings else None
    if home:
        slugs |= {s.strip('/') for s in (home.slug_i18n or {}).values() if s}
    return codes, slugs


def _links(section):
    codes, slugs = _page_paths()
    missing = []
    for a in section.find_all('a', href=True):
        href = a['href']
        if not href.startswith('/') or href.startswith('//') or href.startswith(NOT_PAGES):
            continue
        parts = [p for p in urlparse(href).path.split('/') if p]
        if parts and parts[0] in codes:
            parts = parts[1:]
        if '/'.join(parts) not in slugs and href not in missing:
            missing.append(href)
    if not missing:
        return []
    shown = ', '.join(missing[:3]) + ('…' if len(missing) > 3 else '')
    noun = 'link goes to a page' if len(missing) == 1 else 'links go to pages'
    return [{'level': 'warn', 'text': f"{len(missing)} {noun} this site doesn't have ({shown})"}]


def inspect(page, clip, lang, own_origin=''):
    """{html, name, source, checks, images} for the paste preview. Nothing is saved."""
    html, meta = read_clip(clip)
    section = _soup(html).find('section')
    _clean(section)
    _absolute(section, meta.get('origin'))
    name = _free_name(page, section)
    checks = []
    images = len({url for _el, _attr, url in _image_urls(section) if _external(url, own_origin)})
    if images:
        noun = 'image' if images == 1 else 'images'
        checks.append({'level': 'ok', 'text': f"{images} {noun} will be copied to this site's library"})
    checks += _forms(section)
    checks += _links(section)
    source_lang = meta.get('lang')
    if source_lang and source_lang != lang:
        checks.append({'level': 'warn', 'text': f'The text is in {source_lang.upper()}; you are editing {lang.upper()}'})
    settings = SiteSettings.load()
    others = [c for c in (settings.get_language_codes() if settings else []) if c != lang]
    if others:
        checks.append({'level': 'ok', 'text': f"Text stays as copied; {', '.join(c.upper() for c in others)} "
                                               f"{'is' if len(others) == 1 else 'are'} translated when you add it"})
    source = {k: meta[k] for k in ('site', 'section', 'lang') if meta.get(k)}
    return {'html': str(section), 'name': name, 'source': source, 'checks': checks, 'images': images}


def fetch_image(url):
    from djangopress.editor_v2.api_views import _fetch_image_bytes
    return _fetch_image_bytes(url)


def _save_image(url, data, mime, alt):
    filename = os.path.basename(unquote(urlparse(url).path)) or 'image'
    stem, ext = os.path.splitext(filename)
    ext = ext or '.' + (mime.split('/')[-1] if '/' in mime else 'jpg')
    base_key = slugify(stem) or 'image'
    key, n = base_key, 1
    while SiteImage.objects.filter(key=key).exists():
        key, n = f'{base_key}-{n}', n + 1
    title = stem.replace('-', ' ').replace('_', ' ').strip()[:100]
    image = SiteImage(key=key, title_i18n={'pt': title, 'en': title},
                      alt_text_i18n={'pt': alt, 'en': alt} if alt else {}, is_active=True)
    image.image.save(f'{slugify(stem) or "image"}{ext.lower()}', ContentFile(data), save=True)
    return image


def copy_images(html, own_origin=''):
    """Copy the section's outside images into this site's library and point the HTML at them.
    {html, copied, kept, created}: an image that can't be read stays linked where it is; `created`
    holds the new library rows, so a failed insert can remove them."""
    section = _soup(html).find('section')
    if section is None:
        raise ValueError('That is not a section')
    found = _image_urls(section)
    alts = {}
    for el, attr, url in found:
        if attr == 'src' and el.get('alt'):
            alts.setdefault(url, el['alt'])
    new_urls, kept, created = {}, 0, []
    for url in dict.fromkeys(u for _el, _attr, u in found if _external(u, own_origin)):
        try:
            data, mime = fetch_image(url)
            image = _save_image(url, data, mime, alts.get(url, ''))
            created.append(image)
            new_urls[url] = image.image.url
        except Exception:
            kept += 1
    for el, attr, url in found:
        if url in new_urls:
            el[attr] = new_urls[url] if attr == 'src' else el[attr].replace(url, new_urls[url])
    return {'html': str(section), 'copied': len(new_urls), 'kept': kept, 'created': created}
