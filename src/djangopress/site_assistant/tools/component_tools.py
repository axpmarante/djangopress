"""Sliders and galleries on the active page, through the editor's component
operations (editor_v2.component_ops): every language, alt text per language."""
from bs4 import BeautifulSoup

from djangopress.editor_v2 import components
from djangopress.site_assistant import photos
from djangopress.site_assistant.tools.page_tools import _default_lang, _get_page


def _path(section, root):
    """`section[data-section="x"] > div:nth-child(1) > …` from the section down to root."""
    steps = []
    node = root
    while node is not section:
        siblings = [c for c in node.parent.find_all(True, recursive=False)]
        steps.append(f'{node.name}:nth-child({siblings.index(node) + 1})')
        node = node.parent
    return ' > '.join([f'section[data-section="{section["data-section"]}"]', *reversed(steps)])


def _label(item, kind):
    if kind == 'text-slider':
        leaves = components.text_leaves(item)
        text = components.read_text(leaves[0]) if leaves else ''
        return text[:60]
    img = components.image_of(item)
    if img is None:
        return ''
    return (img.get('alt') or img.get('src', '').rsplit('/', 1)[-1])[:60]


def _components(page, lang):
    """[{section, kind, root, items}] in page order."""
    soup = BeautifulSoup((page.html_content_i18n or {}).get(lang, ''), 'html.parser')
    found = []
    for section in soup.find_all('section', attrs={'data-section': True}):
        roots = []
        for el in section.select('.splide') + section.find_all('img'):
            hit = components.find_for(el)
            if hit and all(hit[0] is not r for r, _k in roots):
                roots.append(hit)
        for root, kind in roots:
            found.append({'section': section['data-section'], 'kind': kind, 'root': _path(section, root),
                          'items': [_label(i, kind) for i in components.items(root, kind)]})
    return found


def _find(page, lang, section, number):
    mine = [c for c in _components(page, lang) if c['section'] == section]
    if not mine:
        have = sorted({f'"{c["section"]}"' for c in _components(page, lang)})
        raise ValueError(f'No slider or gallery in section "{section}". '
                         f'Sections with one: {", ".join(have) or "none"}')
    if not 1 <= number <= len(mine):
        raise ValueError(f'Section "{section}" has {len(mine)} slider(s)/gallery(ies)')
    return mine[number - 1]


def _run(context, params, op, make_args):
    page = _get_page(context)
    if not page:
        return {'success': False, 'message': 'Active page not found'}
    from djangopress.editor_v2.component_ops import run_component_op
    lang = _default_lang()
    try:
        comp = _find(page, lang, params.get('section'), int(params.get('component') or 1))
        args = make_args(comp, lang)
        out = run_component_op(page, comp['root'], comp['kind'], op, args, lang, context.get('user'),
                               checkpoint=False)
    except (ValueError, TypeError) as e:
        return {'success': False, 'message': str(e)}
    if out['focus'] is None:
        return {'success': False, 'message': 'That slider/gallery could not be found in the page'}
    note = f' (not changed in: {", ".join(out["skipped"])})' if out['skipped'] else ''
    return {'success': True, 'message': f'{out["label"]} in {comp["kind"]} of section "{comp["section"]}"{note}'}


def _index(value, comp):
    """1-based tool index → 0-based component index."""
    n = int(value)
    if not 1 <= n <= len(comp['items']):
        raise ValueError(f'Item {n} not found; this {comp["kind"]} has {len(comp["items"])} items')
    return n - 1


def list_components(params, context):
    page = _get_page(context)
    if not page:
        return {'success': False, 'message': 'Active page not found'}
    found = _components(page, _default_lang())
    public = [{k: c[k] for k in ('section', 'kind', 'items')} for c in found]
    return {'success': True, 'components': public,
            'message': f'{len(found)} slider(s)/gallery(ies) on this page. Items are numbered from 1.'}


def reorder_items(params, context):
    def args(comp, lang):
        order = [int(i) - 1 for i in params.get('order') or []]
        return {'order': order}
    return _run(context, params, 'reorder', args)


def replace_item_image(params, context):
    def args(comp, lang):
        return {'index': _index(params.get('index'), comp),
                'image': photos.image_payload(photos.resolve_image(params.get('image')), lang)}
    return _run(context, params, 'replace_image', args)


def add_item_images(params, context):
    def args(comp, lang):
        after = params.get('after') or len(comp['items'])
        images = [photos.image_payload(photos.resolve_image(ref), lang) for ref in params.get('images') or []]
        return {'after': _index(after, comp), 'images': images}
    return _run(context, params, 'add_images', args)


def remove_item(params, context):
    return _run(context, params, 'remove', lambda comp, lang: {'index': _index(params.get('index'), comp)})


COMPONENT_TOOLS = {
    'list_components': list_components,
    'reorder_items': reorder_items,
    'replace_item_image': replace_item_image,
    'add_item_images': add_item_images,
    'remove_item': remove_item,
}
