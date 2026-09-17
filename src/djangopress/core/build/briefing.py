"""Parse a content-only site briefing (briefings/<slug>.md) into a Briefing.

The briefing describes WHAT the site says; design lives in the concepts.
Grammar of a `## Content` line:
    - (required)? <Kind>: <text> [— keywords: a, b, c] [→ <href>]
"""

import re
from dataclasses import dataclass, field

from django.utils.text import slugify

HEADING_RE = re.compile(r'^(#{2,3})\s+(.*?)\s*$')
CONTENT_LINE_RE = re.compile(r'^-\s*(?P<req>\(required\)\s*)?(?P<kind>[^:]+?):\s*(?P<rest>.*)$')
KEYWORDS_SPLIT_RE = re.compile(r'\s+[—-]\s+keywords:\s*', re.I)
HREF_SPLIT_RE = re.compile(r'\s+→\s+|\s+->\s+')
HREF_LIKE_RE = re.compile(r'^(?:/|#|https?://|tel:|mailto:)')
MENU_JSON_RE = re.compile(r'(briefings/[\w.-]+-menu\.json)')
HEX_RE = re.compile(r'#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b')
WIDTH_RE = re.compile(r'([\wÀ-ÿ /]+?)\s+(\d{3,4})\s*px', re.I)
BULLET_RE = re.compile(r'^-\s*(?:\*\*(?P<bkey>[^*]+)\*\*|(?P<key>[^:]+?))\s*:\s*(?P<val>.*)$')
PAGE_RE = re.compile(r'^-\s*\*\*(?P<name>[^*]+)\*\*\s*:\s*(?P<desc>.*)$')
LANG_RE = re.compile(r'([a-z]{2})(?:\s*\(([^)]*)\))?')
NOTE_BULLET_RE = re.compile(r'^[-*]\s+')
EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')
TRAILING_PAREN_RE = re.compile(r'\s*\([^()]*\)\s*$')


def _strip_trailing_paren(value):
    """Remove a trailing " (...)" annotation (only when the parenthesis closes the line)."""
    return TRAILING_PAREN_RE.sub('', value or '').strip()


def _extract_email(value):
    """First token that looks like an email address, else the value with any trailing
    " (...)" annotation removed."""
    m = EMAIL_RE.search(value or '')
    if m:
        return m.group(0)
    return _strip_trailing_paren(value)


@dataclass
class ContentItem:
    id: str
    kind: str
    text: str
    required: bool = False
    keywords: list = field(default_factory=list)
    href: str | None = None
    menu_json: str | None = None


@dataclass
class Briefing:
    title: str = ''
    business: str = ''
    default_language: str = 'pt'
    languages: list = field(default_factory=list)          # codes, default first
    language_names: dict = field(default_factory=dict)     # code -> name
    contact: dict = field(default_factory=dict)            # email, phone, address, maps_url
    hours: list = field(default_factory=list)              # raw lines
    social: dict = field(default_factory=dict)             # instagram -> url
    pages: list = field(default_factory=list)              # [{name, slug, description}]
    content: dict = field(default_factory=dict)            # page slug -> [ContentItem]
    header: str = ''
    footer: str = ''
    constraints: dict = field(default_factory=dict)        # brand_colors, logo, direction, mode, avoid, references, image_max_widths
    images: dict = field(default_factory=dict)             # strategy, sources, constraints
    domain: str = ''
    notes: dict = field(default_factory=dict)              # lowercased "key: value" lines from Additional Notes
    has_open_questions: bool = False


def _sections(text):
    """Split markdown into an ordered list of (level, heading, body_lines)."""
    out = []
    current = None
    for line in text.splitlines():
        m = HEADING_RE.match(line)
        if m:
            current = (len(m.group(1)), m.group(2).strip(), [])
            out.append(current)
        elif current is not None:
            current[2].append(line)
    return out


def _bullets(lines):
    """`- Key: value` and `- **Key**: value` lines -> {key.lower(): value}."""
    result = {}
    for line in lines:
        m = BULLET_RE.match(line.strip())
        if m:
            key = (m.group('bkey') or m.group('key')).strip().lower()
            result[key] = m.group('val').strip()
    return result


def _parse_content_line(line, page_slug, index):
    m = CONTENT_LINE_RE.match(line.strip())
    if not m:
        raise ValueError(f'Malformed content line (expected "- (required) Kind: text"): {line.strip()!r}')
    rest = m.group('rest').strip()
    keywords = []
    parts = KEYWORDS_SPLIT_RE.split(rest, maxsplit=1)
    if len(parts) == 2:
        rest, kw = parts
        keywords = [k.strip() for k in kw.split(',') if k.strip()]
    href = None
    arrows = list(HREF_SPLIT_RE.finditer(rest))
    if arrows:
        last = arrows[-1]
        candidate_text, candidate_href = rest[:last.start()].strip(), rest[last.end():].strip()
        if HREF_LIKE_RE.match(candidate_href.strip('`').strip()):
            rest, href = candidate_text, candidate_href.strip('`').strip()
    menu = MENU_JSON_RE.search(rest)
    return ContentItem(
        id=f'{page_slug}-{index}',
        kind=m.group('kind').strip(),
        text=rest.strip(),
        required=bool(m.group('req')),
        keywords=keywords,
        href=href,
        menu_json=menu.group(1) if menu else None,
    )


def _parse_languages(lines):
    b = _bullets(lines)
    default = 'pt'
    names = {}
    codes = []
    m = LANG_RE.match(b.get('default', 'pt'))
    if m:
        default = m.group(1)
        names[default] = (m.group(2) or default).strip()
    codes.append(default)
    for m in LANG_RE.finditer(b.get('additional', '')):
        code = m.group(1)
        if code not in codes:
            codes.append(code)
            names[code] = (m.group(2) or code).strip()
    return default, codes, names


def _parse_constraints(lines):
    b = _bullets(lines)
    colors = HEX_RE.findall(b.get('brand colors', ''))
    logo = b.get('logo / brand assets', b.get('logo', '')).strip()
    widths = {}
    for label, px in WIDTH_RE.findall(b.get('image constraints', '')):
        widths[label.strip().lower().replace(' ', '-')] = int(px)
    return {
        'brand_colors': colors,
        'logo': None if logo.lower() in ('', 'none') else logo,
        'direction': b.get('direction', '').strip(),
        'mode': 'bold' if b.get('mode', '').strip().lower().startswith('bold') else 'conventional',
        'avoid': [a.strip() for a in re.split(r';|\n', b.get('avoid', '')) if a.strip()],
        'references': [r.strip() for r in b.get('references', '').split(',') if r.strip()],
        'image_max_widths': widths,
    }


def parse_briefing(text):
    briefing = Briefing()
    first = next((l for l in text.splitlines() if l.startswith('# ')), '')
    briefing.title = first[2:].split('—')[0].strip()

    current_h2 = ''
    for level, heading, lines in _sections(text):
        key = heading.lower()
        body = '\n'.join(lines).strip()
        if level == 2:
            current_h2 = key
        if level == 2 and key == 'open questions':
            briefing.has_open_questions = bool(body)
        elif level == 2 and key == 'business':
            briefing.business = body
        elif level == 2 and key == 'languages':
            briefing.default_language, briefing.languages, briefing.language_names = _parse_languages(lines)
        elif level == 2 and key == 'contact':
            b = _bullets(lines)
            briefing.contact = {
                'email': _extract_email(b.get('email', '')),
                'phone': _strip_trailing_paren(b.get('phone', '')),
                'address': _strip_trailing_paren(b.get('address', '')),
                'maps_url': b.get('google maps', ''),
            }
        elif level == 3 and key == 'opening hours':
            briefing.hours = [l.strip()[2:].strip() for l in lines if l.strip().startswith('- ')]
        elif level == 2 and key == 'social media':
            briefing.social = {k: v for k, v in _bullets(lines).items() if v}
        elif level == 2 and key == 'pages':
            for line in lines:
                m = PAGE_RE.match(line.strip())
                if m:
                    name = m.group('name').strip()
                    slug = 'home' if name.lower() in ('home', 'início', 'inicio') else slugify(name)
                    briefing.pages.append({'name': name, 'slug': slug, 'description': m.group('desc').strip()})
        elif level == 2 and key == 'content':
            pass
        elif level == 3 and current_h2 == 'content':
            name = heading.strip()
            page_slug = 'home' if name.lower() in ('home', 'início', 'inicio') else slugify(name)
            items = []
            for line in lines:
                if line.strip().startswith('- '):
                    items.append(_parse_content_line(line, page_slug, len(items) + 1))
            briefing.content[page_slug] = items
        elif level == 2 and key == 'header':
            briefing.header = body
        elif level == 2 and key == 'footer':
            briefing.footer = body
        elif level == 2 and key in ('design constraints', 'design preferences'):
            briefing.constraints = _parse_constraints(lines)
        elif level == 2 and key == 'images':
            briefing.images = _bullets(lines)
        elif level == 2 and key == 'domain':
            briefing.domain = body.strip('`').strip()
        elif level == 2 and key == 'additional notes':
            for line in lines:
                candidate = NOTE_BULLET_RE.sub('', line.strip())
                if ':' in candidate and not candidate.startswith('#'):
                    k, v = candidate.split(':', 1)
                    briefing.notes[k.strip().lower()] = v.strip()
    return briefing
