"""
Editable components — Splide sliders and lightbox galleries — recognised by
structure, and the deterministic operations the editor's component panel runs
on them. Mirror of static/editor_v2/js/lib/components.js: keep the detection
rules in step (shared fixtures in tests/fixtures/components/).
"""
import copy
import json
import re

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from djangopress.editor_v2.structure import strip_ids

KINDS = ('slider', 'text-slider', 'gallery')
TEXT_SLIDE_MIN_CHARS = 40
SKIP_TAGS = {'img', 'svg', 'script', 'style', 'picture', 'video', 'iframe', 'source', 'br', 'template'}
INLINE_TAGS = {'strong', 'em', 'b', 'i', 'br', 'span', 'a', 'small', 'sup', 'sub', 'u', 'mark'}
RUNTIME_INJECTED_CLASSES = {'splide__slide--clone', 'splide__arrows', 'splide__pagination', 'splide__sr'}
# Classes a runtime (Splide, the editor) toggles on live elements; never stored.
RUNTIME_CLASS_RE = re.compile(
    r'^(ev2-|is-(active|visible|prev|next|initialized|rendered|overflow|focus-in)$|splide--|splide__slide--clone$)'
)

_SCRATCH = BeautifulSoup('', 'html.parser')


def _classes(el):
    return el.get('class', []) if isinstance(el, Tag) else []


def _is_runtime(el):
    return bool(RUNTIME_INJECTED_CLASSES & set(_classes(el))) or el.get('data-editor-skip') == 'true'


def _children(el):
    return [c for c in el.find_all(True, recursive=False) if not _is_runtime(c)]


# --- text ------------------------------------------------------------------

def read_text(el):
    """Visible text with source whitespace collapsed; <br> becomes a newline."""
    parts = []

    def walk(node):
        for child in node.children:
            if isinstance(child, Comment):
                continue
            if isinstance(child, NavigableString):
                parts.append(re.sub(r'\s+', ' ', str(child)))
            elif isinstance(child, Tag):
                if child.name == 'br':
                    parts.append('\n')
                elif child.name not in ('script', 'style', 'template'):
                    walk(child)

    walk(el)
    return '\n'.join(line.strip() for line in ''.join(parts).split('\n')).strip()


def write_text(el, value):
    """Replace el's content with plain text; newlines become <br/>."""
    el.clear()
    for i, line in enumerate((value or '').split('\n')):
        if i:
            el.append(_SCRATCH.new_tag('br'))
        el.append(NavigableString(line))


def _is_leafy(el):
    return all(c.name in INLINE_TAGS for c in el.find_all(True, recursive=False))


def is_editable_leaf(el):
    """Only <br> children: the panel can rewrite it without losing formatting."""
    return all(c.name == 'br' for c in el.find_all(True, recursive=False))


def text_leaves(item):
    """Outermost elements holding only inline content and some text, in document order."""
    if _is_leafy(item) and read_text(item):
        return [item]
    out = []

    def walk(node):
        for child in node.find_all(True, recursive=False):
            if _is_runtime(child) or child.name in SKIP_TAGS or child.get('aria-hidden') == 'true':
                continue
            if _is_leafy(child):
                if read_text(child):
                    out.append(child)
            else:
                walk(child)

    walk(item)
    return out


# --- recognition -------------------------------------------------------------

def image_of(item):
    candidates = ([item] if item.name == 'img' else []) + item.find_all('img')
    for img in candidates:
        if img.get('aria-hidden') != 'true':
            return img
    return None


def lightbox_link_of(el):
    if el.name == 'a' and el.has_attr('data-lightbox'):
        return el
    links = el.select('a[data-lightbox]')
    return links[0] if len(links) == 1 else None


def splide_slides(root):
    lst = root.select_one('.splide__list')
    if lst is None:
        return []
    return [c for c in lst.find_all('li', recursive=False)
            if 'splide__slide' in _classes(c) and not _is_runtime(c)]


def gallery_items(root):
    # A lightbox link without an image (a hidden "show 4, lightbox has 12" extra)
    # is not an item: it stays where it is and no panel verb touches it.
    return [c for c in _children(root) if lightbox_link_of(c) is not None and image_of(c) is not None]


def _is_image_slide(slide):
    return image_of(slide) is not None and len(read_text(slide)) < TEXT_SLIDE_MIN_CHARS


def detect(root):
    """'slider' | 'text-slider' | 'gallery' | None for a candidate component root."""
    if not isinstance(root, Tag):
        return None
    if 'splide' in _classes(root):
        slides = splide_slides(root)
        if not slides:
            return None
        images = sum(1 for s in slides if _is_image_slide(s))
        return 'slider' if images * 2 > len(slides) else 'text-slider'
    n = len(gallery_items(root))
    if n >= 2 or (n >= 1 and root.get('data-media-collection') == 'lightbox'):
        return 'gallery'
    return None


def find_for(el):
    """(root, kind) of the component containing el, or None. A .splide ancestor wins."""
    section = el if el.has_attr('data-section') else el.find_parent(attrs={'data-section': True})
    if section is None:
        return None
    splide = el if 'splide' in _classes(el) else el.find_parent(class_='splide')
    if splide is not None and splide is not section and any(p is section for p in splide.parents):
        kind = detect(splide)
        return (splide, kind) if kind else None
    node = el
    while node is not None and node is not section:
        if detect(node) == 'gallery':
            return node, 'gallery'
        node = node.parent
    return None


def _same_kind(a, b):
    # slider vs text-slider only depends on caption length, which differs between
    # translations; the operations are identical, so either one matches the other.
    sliders = ('slider', 'text-slider')
    return a == b or (a in sliders and b in sliders)


def find_component(soup, root_selector, kind):
    root = soup.select_one(root_selector)
    return root if root is not None and _same_kind(detect(root), kind) else None


def items(root, kind):
    return splide_slides(root) if kind in ('slider', 'text-slider') else gallery_items(root)


def min_items(root, kind):
    if kind == 'gallery' and root.get('data-media-collection') != 'lightbox':
        return 2
    return 1


# --- operations ----------------------------------------------------------------
# Each returns the index the panel should focus and raises ValueError on bad
# arguments. They never look at other languages: the endpoint applies them to
# each language copy in turn.

SETTING_KEYS = frozenset({
    'type', 'rewind', 'autoplay', 'interval', 'speed', 'arrows', 'pagination',
    'pauseOnHover', 'perPage', 'breakpoints',
})
_BOOL_SETTINGS = {'rewind', 'autoplay', 'arrows', 'pagination', 'pauseOnHover'}
_INT_RANGES = {'interval': (1000, 60000), 'speed': (100, 5000), 'perPage': (1, 8)}


_TEMPLATE_SYNTAX_RE = re.compile(r'\{[{%#]')


def _require_plain(value):
    """Page HTML is rendered as a Django template: typed {{ / {% / {# would break the page."""
    if isinstance(value, str) and _TEMPLATE_SYNTAX_RE.search(value):
        raise ValueError("Text can't contain {{, {% or {# — they would break the page")
    return value


def _defuse(value):
    """Same risk for text we didn't type (library alt text): break the sequence instead of refusing."""
    return _TEMPLATE_SYNTAX_RE.sub(lambda m: '{ ' + m.group(0)[1], value) if isinstance(value, str) else value


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _require_index(its, index):
    if not _is_int(index) or not 0 <= index < len(its):
        raise ValueError('Item not found')


def _safe_url(url):
    if not isinstance(url, str) or not url.strip():
        raise ValueError('Missing image URL')
    if not url.startswith(('http://', 'https://', '/')):
        raise ValueError('Image URL must be http(s) or site-relative')
    return url


def reorder(root, kind, order):
    its = items(root, kind)
    if not isinstance(order, list) or not all(_is_int(i) for i in order) or sorted(order) != list(range(len(its))):
        raise ValueError('order must list every item exactly once')
    markers = []
    for it in its:
        marker = _SCRATCH.new_tag('ev2-slot')
        it.replace_with(marker)
        markers.append(marker)
    for marker, old in zip(markers, order):
        marker.replace_with(its[old])
    return 0


def remove(root, kind, index):
    its = items(root, kind)
    _require_index(its, index)
    if len(its) <= min_items(root, kind):
        raise ValueError("This is the minimum number of items — it can't be removed")
    its[index].decompose()
    return min(index, len(its) - 2)


def _validate_setting(key, value):
    if key not in SETTING_KEYS:
        raise ValueError(f'Unknown setting: {key}')
    if value is None:
        return
    if key == 'type' and value not in ('slide', 'loop', 'fade'):
        raise ValueError('type must be slide, loop or fade')
    if key in _BOOL_SETTINGS and not isinstance(value, bool):
        raise ValueError(f'{key} must be true or false')
    if key in _INT_RANGES:
        lo, hi = _INT_RANGES[key]
        if not _is_int(value) or not lo <= value <= hi:
            raise ValueError(f'{key} must be a whole number between {lo} and {hi}')
    if key == 'breakpoints':
        if not isinstance(value, dict) or not all(str(k).isdigit() and isinstance(v, dict) for k, v in value.items()):
            raise ValueError('breakpoints must map pixel widths to option objects')


def set_settings(root, changes):
    if 'splide' not in _classes(root):
        raise ValueError('Settings apply to sliders only')
    if not isinstance(changes, dict) or not changes:
        raise ValueError('No settings to change')
    for key, value in changes.items():
        _validate_setting(key, value)
    raw = root.get('data-splide')
    try:
        opts = json.loads(raw) if raw else {}
    except ValueError:
        opts = None
    if not isinstance(opts, dict):
        raise ValueError("This slider's settings aren't valid JSON — fix them in the HTML first")
    for key, value in changes.items():
        if value is None:
            opts.pop(key, None)
        else:
            opts[key] = value
    root['data-splide'] = json.dumps(opts, ensure_ascii=False, separators=(',', ':'))
    return 0


def _set_image(item, url, alt):
    img = image_of(item)
    if img is None:
        raise ValueError('This item has no image')
    img['src'] = _safe_url(url)
    for attr in ('srcset', 'sizes'):
        if attr in img.attrs:
            del img[attr]
    alt = _defuse(alt)
    if alt is not None:
        img['alt'] = alt
    link = lightbox_link_of(item)
    if link is not None:
        link['href'] = url
        if alt is not None and link.has_attr('data-alt'):
            link['data-alt'] = alt


def replace_image(root, kind, index, url, alt):
    its = items(root, kind)
    _require_index(its, index)
    _set_image(its[index], url, alt)
    return index


def add_images(root, kind, after, images):
    its = items(root, kind)
    _require_index(its, after)
    if not images:
        raise ValueError('No images to add')
    anchor = its[after]
    for url, alt in images:
        clone = copy.copy(its[after])
        strip_ids(clone)
        _set_image(clone, url, alt)
        anchor.insert_after(clone)
        anchor = clone
    return after + 1


def _write_texts(item, texts):
    leaves = text_leaves(item)
    parsed = {}
    for key, value in texts.items():
        try:
            i = int(key)
        except (TypeError, ValueError):
            raise ValueError('Unknown text field')
        if not 0 <= i < len(leaves) or not is_editable_leaf(leaves[i]):
            raise ValueError('This text has formatting — edit it on the page instead')
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Text can't be empty — remove the item instead")
        parsed[i] = _require_plain(value.strip())
    for i, value in parsed.items():
        write_text(leaves[i], value)


def add_text_item(root, kind, after, texts):
    its = items(root, kind)
    _require_index(its, after)
    if not isinstance(texts, dict) or not texts:
        raise ValueError('Fill in the new item')
    clone = copy.copy(its[after])
    strip_ids(clone)
    _write_texts(clone, texts)
    its[after].insert_after(clone)
    return after + 1


def update_item(root, kind, index, alt=None, caption=None, texts=None):
    its = items(root, kind)
    _require_index(its, index)
    item = its[index]
    if alt is not None:
        img = image_of(item)
        if img is None:
            raise ValueError('This item has no image')
        img['alt'] = _require_plain(alt)
    if caption is not None:
        link = lightbox_link_of(item)
        if link is None:
            raise ValueError('This item has no lightbox link')
        link['data-alt'] = _require_plain(caption)
    if texts:
        _write_texts(item, texts)
    return index


# --- audit (check_site) ----------------------------------------------------------

def _where(el):
    section = el.find_parent(attrs={'data-section': True})
    return f' in section "{section["data-section"]}"' if section else ''


def audit(soup):
    """Problems that stop the editor's component panel from managing a slider or gallery."""
    problems = []
    for root in soup.select('.splide'):
        if not splide_slides(root):
            problems.append(f'slider{_where(root)} has no slides (needs .splide__track > ul.splide__list > li.splide__slide)')
        raw = root.get('data-splide')
        if raw:
            try:
                ok = isinstance(json.loads(raw), dict)
            except ValueError:
                ok = False
            if not ok:
                problems.append(f'slider{_where(root)}: data-splide is not a JSON object')
    groups = {}
    for a in soup.select('a[data-lightbox]'):
        groups.setdefault(a.get('data-lightbox'), []).append(a)
    for name, links in groups.items():
        if len(links) >= 2 and any(find_for(a) is None for a in links):
            problems.append(f'lightbox group "{name}": items are not siblings in one container — the editor cannot manage them')
    return problems
