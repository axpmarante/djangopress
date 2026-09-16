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
        index = element_children(parent).index(current) + 1
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
            if any(item in g['container'].parents or item is g['container'] for item in other['items']):
                g['nested'] = True
                break
    return groups
