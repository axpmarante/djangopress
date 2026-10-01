"""Clean the HTML of an inline text edit (the floating toolbar's bold, italic
and links) down to inline formatting. Anything else is unwrapped (its text
stays) or dropped (scripts, styles, media)."""
import re

from bs4 import BeautifulSoup, Comment

INLINE_TAGS = {'a', 'strong', 'b', 'em', 'i', 'u', 'br', 'span', 'small', 'sup', 'sub', 'mark', 's'}
DROP_TAGS = {'script', 'style', 'iframe', 'object', 'embed', 'img', 'video', 'audio', 'svg', 'math',
             'form', 'input', 'button', 'select', 'textarea', 'template', 'noscript', 'link', 'meta'}
SAFE_HREF = re.compile(r'^(https?://|mailto:|tel:|/|#|\?|[\w\-./]+$)', re.IGNORECASE)


def clean_inline_html(value):
    """The cleaned inner HTML for an edited element."""
    soup = BeautifulSoup(str(value or ''), 'html.parser')
    for node in soup.find_all(string=lambda s: isinstance(s, Comment)):
        node.extract()
    for tag in soup.find_all(True):
        if tag.name in DROP_TAGS:
            tag.decompose()
    for tag in reversed(soup.find_all(True)):        # innermost first, so unwrapping keeps order
        if tag.name not in INLINE_TAGS:
            tag.unwrap()
            continue
        attrs = {}
        if tag.name == 'a':
            href = (tag.get('href') or '').strip()
            if href and SAFE_HREF.match(href) and not href.lower().startswith(('javascript:', 'data:', 'vbscript:')):
                attrs['href'] = href
            if tag.get('target') == '_blank':
                attrs['target'] = '_blank'
                attrs['rel'] = 'noopener'
            if tag.get('title'):
                attrs['title'] = tag['title']
        if tag.get('class'):
            attrs['class'] = tag['class']
        tag.attrs = attrs
    return str(soup).strip()
