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
    return [c for c in _children(root) if lightbox_link_of(c) is not None]


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


def find_component(soup, root_selector, kind):
    root = soup.select_one(root_selector)
    return root if root is not None and detect(root) == kind else None


def items(root, kind):
    return splide_slides(root) if kind in ('slider', 'text-slider') else gallery_items(root)


def min_items(root, kind):
    if kind == 'gallery' and root.get('data-media-collection') != 'lightbox':
        return 2
    return 1
