"""Photos: search the library and Unsplash, and put a photo behind a section."""
import re

from bs4 import BeautifulSoup

from djangopress.site_assistant import photos
from djangopress.site_assistant.tools.page_tools import _default_lang, _get_page, _section_names

URL_RE = re.compile(r'''url\((["']?).*?\1\)''')


def find_photos(params, context):
    query = (params.get('query') or '').strip()
    if not query:
        return {'success': False, 'message': 'Missing query'}
    found, note = photos.find_photos(query, source=params.get('source') or 'both',
                                     orientation=params.get('orientation'))
    message = f'{len(found)} photo(s) found. ' + note
    if found:
        message += ' The user sees them as thumbnails and can click one; otherwise pick one by its ref.'
    return {'success': True, 'photos': found, 'message': message.strip()}


def _layer_img(section):
    """The <img> used as a full-bleed background layer, if any."""
    for img in section.find_all('img'):
        classes = set(img.get('class') or [])
        if 'absolute' in classes and ('inset-0' in classes or {'w-full', 'h-full'} <= classes):
            return img
    return None


def _set_background(section, url, alt):
    """Returns how it was applied: 'style', 'layer' or 'added'."""
    for el in [section, *section.find_all(style=True)]:
        style = el.get('style') or ''
        if 'background-image' in style and URL_RE.search(style):
            el['style'] = URL_RE.sub(lambda m: f"url('{url}')", style)
            return 'style'
    img = _layer_img(section)
    if img is not None:
        img['src'] = url
        img['alt'] = alt
        for attr in ('srcset', 'sizes'):
            img.attrs.pop(attr, None)
        link = img.find_parent('a', attrs={'data-lightbox': True})
        if link is not None and link.find_parent('section') is section:
            link['href'] = url
        return 'layer'
    style = (section.get('style') or '').strip().rstrip(';')
    extra = f"background-image: url('{url}'); background-size: cover; background-position: center"
    section['style'] = f'{style}; {extra}' if style else extra
    return 'added'


def set_section_background(params, context):
    page = _get_page(context)
    if not page:
        return {'success': False, 'message': 'Active page not found'}
    name = params.get('section_name')
    lang = _default_lang()
    if name not in _section_names(page, lang):
        return {'success': False,
                'message': f'Section "{name}" not found. Sections on this page: {", ".join(_section_names(page, lang))}'}
    try:
        image = photos.resolve_image(params.get('image'))
    except ValueError as e:
        return {'success': False, 'message': str(e)}

    url = image.image.url
    html_i18n = dict(page.html_content_i18n or {})
    how, missing = None, []
    for code, html in html_i18n.items():
        if not html:
            continue
        soup = BeautifulSoup(html, 'html.parser')
        section = soup.find('section', attrs={'data-section': name})
        if section is None:
            missing.append(code)
            continue
        mode = _set_background(section, url, photos.image_payload(image, code)['alt'])
        how = how or mode
        html_i18n[code] = str(soup)
    page.html_content_i18n = html_i18n
    page.save()

    message = f'Background of section "{name}" set to library image {image.pk}'
    if how == 'added':
        message += ' (the section had no background before; check that the text is still readable)'
    if missing:
        message += f' (section missing in: {", ".join(missing)})'
    return {'success': True, 'message': message}


PHOTO_TOOLS = {
    'find_photos': find_photos,
    'set_section_background': set_section_background,
}
