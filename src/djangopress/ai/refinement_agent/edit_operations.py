"""Structured edit operations executor for the Refinement Agent.

Takes a list of structured edit operations and applies them to HTML via BeautifulSoup.
Used by the apply_edits tool to execute LLM-generated edit plans.
"""

from bs4 import BeautifulSoup, NavigableString


VALID_ACTIONS = {
    'add_class',
    'remove_class',
    'set_text',
    'set_html',
    'set_attribute',
    'remove_attribute',
    'insert_before',
    'insert_after',
    'remove',
    'wrap',
}


def _strip_wrapper(html):
    """Strip <html><body> wrapper if BeautifulSoup added it."""
    if html.startswith('<html><body>'):
        html = html[12:-14]
    return html


def _select_elements(soup, selector):
    """Select elements by CSS selector, falling back to root section."""
    if selector:
        return soup.select(selector)
    # Fall back to root section element
    root = soup.find('section') or next(
        (c for c in soup.children if not isinstance(c, NavigableString)), None
    )
    return [root] if root else []


def _op_add_class(elements, params):
    """Add CSS classes to element(s)."""
    classes = params.get('classes', '')
    if not classes:
        return 'No classes specified'
    for el in elements:
        current = set(el.get('class', []))
        for cls in classes.split():
            current.add(cls)
        el['class'] = sorted(current)
    return None


def _op_remove_class(elements, params):
    """Remove CSS classes from element(s). Supports pattern removal (e.g. 'bg-' removes all bg-* classes)."""
    classes = params.get('classes', '')
    if not classes:
        return 'No classes specified'
    for el in elements:
        current = set(el.get('class', []))
        for cls in classes.split():
            if cls.endswith('-'):
                # Pattern removal: "bg-" removes all bg-* classes
                current = {c for c in current if not c.startswith(cls)}
            else:
                current.discard(cls)
        if current:
            el['class'] = sorted(current)
        elif 'class' in el.attrs:
            del el['class']
    return None


def _op_set_text(elements, params):
    """Set text content of element(s)."""
    text = params.get('text')
    if text is None:
        return 'No text specified'
    for el in elements:
        el.clear()
        el.append(text)
    return None


def _op_set_html(elements, params):
    """Set inner HTML of element(s)."""
    html = params.get('html')
    if html is None:
        return 'No html specified'
    for el in elements:
        el.clear()
        fragment = BeautifulSoup(html, 'html.parser')
        for child in list(fragment.children):
            el.append(child.extract())
    return None


def _op_set_attribute(elements, params):
    """Set an attribute on element(s)."""
    attr = params.get('attr')
    value = params.get('value')
    if not attr:
        return 'No attr specified'
    if value is None:
        return 'No value specified'
    for el in elements:
        el[attr] = value
    return None


def _op_remove_attribute(elements, params):
    """Remove an attribute from element(s)."""
    attr = params.get('attr')
    if not attr:
        return 'No attr specified'
    for el in elements:
        if attr in el.attrs:
            del el[attr]
    return None


def _op_insert_before(elements, params):
    """Insert HTML before element(s)."""
    html = params.get('html')
    if html is None:
        return 'No html specified'
    for el in elements:
        fragment = BeautifulSoup(html, 'html.parser')
        for child in reversed(list(fragment.children)):
            el.insert_before(child.extract())
    return None


def _op_insert_after(elements, params):
    """Insert HTML after element(s)."""
    html = params.get('html')
    if html is None:
        return 'No html specified'
    for el in elements:
        fragment = BeautifulSoup(html, 'html.parser')
        # Insert children in order after the element
        ref = el
        for child in list(fragment.children):
            ref.insert_after(child.extract())
            ref = child
    return None


def _op_remove(elements, params):
    """Remove element(s) from the DOM."""
    for el in elements:
        el.decompose()
    return None


def _op_wrap(elements, params):
    """Wrap element's children in new HTML. The html must contain {children} placeholder."""
    html = params.get('html')
    if html is None:
        return 'No html specified'
    if '{children}' not in html:
        return 'Wrap html must contain {children} placeholder'
    for el in elements:
        # Capture current children
        children = list(el.children)
        # Parse wrapper with placeholder replaced by a marker
        marker = '<!--WRAP_CHILDREN-->'
        wrapper_html = html.replace('{children}', marker)
        wrapper_soup = BeautifulSoup(wrapper_html, 'html.parser')
        # Find the marker and replace with children
        marker_node = wrapper_soup.find(string=marker)
        if not marker_node:
            return 'Could not locate {children} placeholder in parsed wrapper'
        parent_of_marker = marker_node.parent
        # Clear the element and insert the wrapper structure
        el.clear()
        for wrapper_child in list(wrapper_soup.children):
            el.append(wrapper_child.extract())
        # Now replace the marker text with the original children
        marker_node = el.find(string=marker)
        if marker_node:
            target_parent = marker_node.parent
            marker_node.extract()
            for child in children:
                target_parent.append(child)
    return None


_ACTION_HANDLERS = {
    'add_class': _op_add_class,
    'remove_class': _op_remove_class,
    'set_text': _op_set_text,
    'set_html': _op_set_html,
    'set_attribute': _op_set_attribute,
    'remove_attribute': _op_remove_attribute,
    'insert_before': _op_insert_before,
    'insert_after': _op_insert_after,
    'remove': _op_remove,
    'wrap': _op_wrap,
}


def apply_edits(html, edits):
    """Apply a list of structured edit operations to HTML.

    Args:
        html: The HTML string to edit.
        edits: List of dicts, each with 'action', 'selector', and action-specific params.

    Returns:
        Dict with keys:
            success (bool): True if all edits applied without errors.
            html (str): The resulting HTML.
            applied (int): Number of edits successfully applied.
            errors (list[str]): List of error messages for failed edits.
    """
    if not edits:
        return {'success': True, 'html': html, 'applied': 0, 'errors': []}

    soup = BeautifulSoup(html, 'html.parser')
    applied = 0
    errors = []

    for i, edit in enumerate(edits):
        action = edit.get('action', '')
        if action not in VALID_ACTIONS:
            errors.append(f'Edit {i}: unknown action "{action}"')
            continue

        selector = edit.get('selector', '')

        # For remove action on already-decomposed elements, select fresh each time
        elements = _select_elements(soup, selector)
        if not elements:
            errors.append(f'Edit {i} ({action}): no elements matched selector "{selector or "(root)"}"')
            continue

        handler = _ACTION_HANDLERS[action]
        error = handler(elements, edit)
        if error:
            errors.append(f'Edit {i} ({action}): {error}')
        else:
            applied += 1

    result_html = _strip_wrapper(str(soup))

    return {
        'success': len(errors) == 0,
        'html': result_html,
        'applied': applied,
        'errors': errors,
    }
