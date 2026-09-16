"""
Pure BeautifulSoup helpers for structural editing (no Django imports).

Selectors follow the editor's shape:
    section[data-section="x"] > div:nth-child(2) > h3:nth-child(1)
`nth-child` counts element siblings only, which is what soupsieve does too.
"""
import copy
import re

from bs4 import BeautifulSoup, Tag

EDITOR_CLASS_PREFIX = 'ev2-'
NTH_RE = re.compile(r'^(?P<tag>[a-z0-9]+):nth-child\((?P<n>\d+)\)$')

# Tags that are never content items: a pair of these is decoration, not a repeat group.
DECORATIVE_TAGS = frozenset((
    'br', 'hr', 'wbr', 'svg', 'path', 'g', 'use', 'circle', 'rect', 'line',
    'polyline', 'polygon', 'source', 'track', 'option',
))


# ---------------------------------------------------------------------------
# Signatures and repeat groups (Phase 0 heuristic, mirrored in lib/dom.js)
# ---------------------------------------------------------------------------

def element_children(tag):
    return [c for c in tag.children if isinstance(c, Tag)]


def signature_of(tag):
    classes = sorted(c for c in (tag.get('class') or []) if not c.startswith(EDITOR_CLASS_PREFIX))
    return f"{tag.name}|{' '.join(classes)}"


def child_signature_of(tag):
    return ','.join(signature_of(c) for c in element_children(tag))


def path_from_section(tag, section):
    """Selector path of `tag` relative to `section` (without the section prefix)."""
    parts = []
    current = tag
    while current is not None and current is not section:
        parent = current.parent
        if parent is None:
            break
        index = next(i for i, c in enumerate(element_children(parent)) if c is current) + 1
        parts.insert(0, f'{current.name}:nth-child({index})')
        current = parent
    return ' > '.join(parts)


def find_repeat_groups(section):
    """
    Return every sibling group inside `section` whose members share a signature.

    A group is a dict: container, items, signature, size, nested, ambiguous,
    container_path. Groups of exactly two whose members have different child
    signatures are marked ambiguous ('pair-with-different-children'): they are
    usually two columns, not two cards.
    """
    groups = []
    for container in [section] + section.find_all(True):
        children = element_children(container)
        by_sig = {}
        for child in children:
            if child.name in DECORATIVE_TAGS:
                continue
            by_sig.setdefault(signature_of(child), []).append(child)
        for sig, items in by_sig.items():
            if len(items) < 2:
                continue
            ambiguous = ''
            if len(items) == 2 and child_signature_of(items[0]) != child_signature_of(items[1]):
                ambiguous = 'pair-with-different-children'
            groups.append({
                'container': container,
                'items': items,
                'signature': sig,
                'size': len(items),
                'nested': False,
                'ambiguous': ambiguous,
                'container_path': path_from_section(container, section),
            })
    # Mark nested groups: container lives inside an item of another group.
    for g in groups:
        for other in groups:
            if other is g:
                continue
            if any(item is g['container'] or any(item is anc for anc in g['container'].parents)
                   for item in other['items']):
                g['nested'] = True
                break
    return groups


# ---------------------------------------------------------------------------
# Selector arithmetic
# ---------------------------------------------------------------------------

def split_last(selector):
    """('head', 'tag', n) for a selector ending in `tag:nth-child(n)`, else None."""
    head, _sep, last = selector.rpartition(' > ')
    m = NTH_RE.match(last)
    if not m:
        return None
    return head, m.group('tag'), int(m.group('n'))


def with_last(selector, tag, n):
    """Rebuild `selector` with a new last part `tag:nth-child(n)`."""
    parts = split_last(selector)
    head = parts[0] if parts else selector
    return f'{head} > {tag}:nth-child({n})'


def shift_last_index(selector, delta):
    """Return `selector` with the last `:nth-child(n)` moved by `delta` (same tag)."""
    parts = split_last(selector)
    if not parts:
        return selector
    head, tag, n = parts
    return with_last(selector, tag, max(1, n + delta))


def adjacent_sibling(tag, direction):
    """Previous/next element sibling, or None."""
    if direction == 'up':
        return tag.find_previous_sibling(True)
    if direction == 'down':
        return tag.find_next_sibling(True)
    raise ValueError(f'direction must be "up" or "down", got {direction!r}')


def strip_ids(tag):
    """Remove `id` from `tag` and every descendant (ids must stay unique)."""
    if tag.has_attr('id'):
        del tag['id']
    for t in tag.find_all(id=True):
        del t['id']


# ---------------------------------------------------------------------------
# Element verbs
# ---------------------------------------------------------------------------

def duplicate_node(soup, selector):
    """Clone the node at `selector` right after itself. Returns the clone's selector."""
    node = soup.select_one(selector)
    if node is None:
        return None
    clone = copy.copy(node)
    strip_ids(clone)
    node.insert_after(clone)
    return shift_last_index(selector, 1)


def move_node(soup, selector, direction):
    """Swap the node with its previous/next element sibling. Returns the new selector, or None."""
    node = soup.select_one(selector)
    if node is None:
        return None
    other = adjacent_sibling(node, direction)
    if other is None:
        return None
    node = node.extract()
    if direction == 'up':
        other.insert_before(node)
        return shift_last_index(selector, -1)
    other.insert_after(node)
    return shift_last_index(selector, 1)
