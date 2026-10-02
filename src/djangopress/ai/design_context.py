"""What the site already looks like, for AI section and element work.

A generated section looks basic when the model only sees the target and a
generic rule set. This collects what makes this site look like itself: its
colours and fonts, its best-crafted sections (as HTML references), the class
combinations it repeats for each role (eyebrows, titles, buttons, cards…) and
the media library images a new section can use instead of placeholders.
"""
import re
import unicodedata
from collections import Counter

from bs4 import BeautifulSoup

from djangopress.core.models import Page, SiteImage, SiteSettings
from djangopress.editor_v2.design_tokens import _site_html, collect_tokens

REFERENCE_CAP = 6000
REFERENCE_COUNT = 3
IMAGE_LIMIT = 12
EYEBROW_MAX_TEXT = 40
BODY_MIN_TEXT = 60


def _label(name):
    return re.sub(r'[-_]+', ' ', name or '').strip().title()


def _html(obj, lang):
    copies = getattr(obj, 'html_content_i18n', None) or {}
    settings = SiteSettings.load()
    default = settings.get_default_language() if settings else 'pt'
    return copies.get(lang) or copies.get(default) or next(iter(copies.values()), '') or ''


def _homepage():
    settings = SiteSettings.load()
    if settings and settings.homepage_id:
        return Page.objects.filter(pk=settings.homepage_id).first()
    return Page.objects.filter(is_active=True).order_by('sort_order', 'pk').first()


def _sections(html):
    return BeautifulSoup(html or '', 'html.parser').find_all('section', attrs={'data-section': True})


def _richness(section):
    classes = set()
    for el in [section, *section.find_all(True)]:
        classes.update(el.get('class') or [])
    return len(classes)


def _cap(html):
    if len(html) <= REFERENCE_CAP:
        return html
    return html[:REFERENCE_CAP] + '\n<!-- … cut -->'


def _references(page, target_name, lang):
    """The page's own most crafted sections first; the home hero only fills in when the page
    has little of its own (a page can have its own style, e.g. alternative proposals)."""
    picked, names = [], set()

    def add(section, page_title):
        name = section.get('data-section')
        if name in names or name == target_name:
            return
        names.add(name)
        picked.append({'name': name, 'label': _label(name), 'page': page_title, 'html': _cap(str(section))})

    own = [s for s in _sections(_html(page, lang)) if s.get('data-section') != target_name]
    own.sort(key=_richness, reverse=True)
    title = getattr(page, 'default_title', '') or ''
    for section in own[:REFERENCE_COUNT]:
        add(section, title)
    if len(picked) < 2:
        home = _homepage()
        same_page = isinstance(page, Page) and home is not None and page.pk == home.pk
        if home is not None and not same_page:
            home_sections = _sections(_html(home, lang))
            if home_sections:
                add(home_sections[0], home.default_title)
    return picked


def _text(el):
    return ' '.join(el.get_text(' ', strip=True).split())


def _classes(el):
    return ' '.join(el.get('class') or [])


def _has(classes, *prefixes):
    return any(c.split(':')[-1].startswith(prefixes) for c in classes)


ROLES = [
    ('eyebrow', lambda el, c: el.name in ('p', 'span', 'div') and 'uppercase' in c and _has(c, 'tracking-')
        and 0 < len(_text(el)) <= EYEBROW_MAX_TEXT),
    ('section title', lambda el, c: el.name == 'h2'),
    ('body text', lambda el, c: el.name == 'p' and len(_text(el)) > BODY_MIN_TEXT),
    ('primary button', lambda el, c: el.name in ('a', 'button') and _has(c, 'bg-') and _has(c, 'px-')),
    ('text link', lambda el, c: el.name == 'a' and not _has(c, 'bg-')
        and ('underline' in c or any(x.split(':')[-1].startswith('text-[#') for x in c))),
    ('card', lambda el, c: el.name in ('div', 'article', 'li') and _has(c, 'p-', 'px-')
        and _has(c, 'rounded', 'border', 'shadow') and el.find(['h3', 'h4']) is not None),
    ('divider', lambda el, c: el.name == 'hr' or 'h-px' in c or 'h-[1px]' in c),
]


def _count_roles(chunks):
    counts = {role: Counter() for role, _test in ROLES}
    for chunk in chunks:
        for el in BeautifulSoup(chunk or '', 'html.parser').find_all(True):
            classes = el.get('class') or []
            if not classes:
                continue
            for role, test in ROLES:
                if test(el, classes):
                    counts[role][_classes(el)] += 1
    return counts


def _vocabulary(page_html=''):
    """Per role, the page's own class combination; the rest of the site fills the roles the page lacks."""
    page_counts = _count_roles([page_html]) if page_html else {role: Counter() for role, _t in ROLES}
    site_counts = _count_roles(_site_html())
    vocab = []
    for role, _test in ROLES:
        counts = page_counts[role] or site_counts[role]
        if counts:
            classes, count = counts.most_common(1)[0]
            vocab.append({'role': role, 'classes': classes, 'count': count})
    return vocab


WEIGHT_RE = re.compile(r'^font-(thin|extralight|light|normal|medium|semibold|bold|extrabold|black)$')
SIZE_RE = re.compile(r'^((?:sm|md|lg|xl|2xl):)?text-(?:\[(\d+(?:\.\d+)?)px\]|(xs|sm|base|lg|xl|[2-9]xl))$')
NAMED_SIZES = {'xs': 12, 'sm': 14, 'base': 16, 'lg': 18, 'xl': 20, '2xl': 24, '3xl': 30, '4xl': 36, '5xl': 48,
               '6xl': 60, '7xl': 72, '8xl': 96, '9xl': 128}
TYPE_TAGS = ('h1', 'h2', 'h3', 'h4', 'p')


def size_of(cls):
    """('md:', 44) for md:text-[44px] / ('', 18) for text-lg; None for anything else."""
    m = SIZE_RE.match(cls)
    if not m:
        return None
    px = float(m.group(2)) if m.group(2) else NAMED_SIZES[m.group(3)]
    return m.group(1) or '', int(px) if px == int(px) else px


def _typography(page_html):
    """Per tag on this page: the usual weight and the font sizes used, per breakpoint."""
    soup = BeautifulSoup(page_html or '', 'html.parser')
    out = {}
    for tag in TYPE_TAGS:
        weights, sizes = Counter(), {}
        for el in soup.find_all(tag):
            for cls in el.get('class') or []:
                if WEIGHT_RE.match(cls):
                    weights[cls] += 1
                found = size_of(cls)
                if found:
                    sizes.setdefault(found[0], set()).add(found[1])
        if weights or sizes:
            out[tag] = {'weight': weights.most_common(1)[0][0] if weights else None,
                        'sizes': {bp: sorted(v) for bp, v in sizes.items()}}
    return out


def _words(text):
    text = unicodedata.normalize('NFKD', (text or '').lower())
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    return {w[:6] for w in re.findall(r'[a-z0-9]+', text) if len(w) >= 4}


def _images(query, lang):
    wanted = _words(query)
    ranked = []
    images = (SiteImage.objects.filter(is_active=True).exclude(image='').exclude(image__isnull=True)
              .order_by('-uploaded_at', '-pk'))
    for order, img in enumerate(images):
        about = ' '.join([img.get_title(lang) or '', img.get_alt_text(lang) or '', img.tags or '', img.description or ''])
        score = len(wanted & _words(about))
        ranked.append((-score, order, img))
    ranked.sort(key=lambda r: (r[0], r[1]))
    return [{'id': img.pk, 'url': img.image.url, 'alt': img.get_alt_text(lang) or img.get_title(lang) or ''}
            for _s, _o, img in ranked[:IMAGE_LIMIT]]


def _forms():
    from djangopress.core.models import DynamicForm
    return [{'slug': f.slug, 'name': f.name} for f in DynamicForm.objects.filter(is_active=True).order_by('name')]


def build_design_context(page, target_name=None, *, lang=None, query=''):
    settings = SiteSettings.load()
    lang = lang or (settings.get_default_language() if settings else 'pt')
    tokens = collect_tokens()
    return {
        'colors': tokens['colors'],
        'fonts': tokens['fonts'],
        'design_guide': (settings.design_guide if settings else '') or '',
        'references': _references(page, target_name, lang),
        'vocabulary': _vocabulary(_html(page, lang)),
        'typography': _typography(_html(page, lang)),
        'images': _images(query, lang),
        'forms': _forms(),
    }


def render_design_context(ctx):
    parts = ['## Site design',
             'The result must look like it belongs to this site: same palette, fonts, type scale, spacing rhythm '
             'and details as the reference sections. Never fall back to generic Tailwind styling.']
    if ctx.get('colors'):
        parts.append('\n### Palette (use only these colours, as arbitrary values like `bg-[#HEX]`)')
        parts += [f"- {c['name']}: {c['value']}" for c in ctx['colors']]
    if ctx.get('fonts'):
        parts.append('\n### Fonts')
        parts += [f"- {f['role']}: {f['family']}" for f in ctx['fonts']]
    if ctx.get('vocabulary'):
        parts.append('\n### Design vocabulary (reuse these exact class combinations for these roles)')
        parts += [f"- {v['role']}: `{v['classes']}` (used {v['count']}×)" for v in ctx['vocabulary']]
    if ctx.get('typography'):
        parts.append("\n### Type scale on this page (keep these weights and sizes)")
        for tag, t in ctx['typography'].items():
            sizes = '; '.join(f"{bp or 'base'} {'/'.join(str(x) for x in v)}px" for bp, v in t['sizes'].items())
            parts.append(f"- {tag}: {t['weight'] or 'regular'}{' · ' + sizes if sizes else ''}")
    if ctx.get('references'):
        parts.append('\n### Reference sections (the site\'s most crafted sections: match their craft, spacing and '
                     'details; do not copy their content)')
        for ref in ctx['references']:
            where = f" ({ref['page']})" if ref.get('page') else ''
            parts.append(f"\n#### {ref['label']}{where}\n```html\n{ref['html']}\n```")
    if ctx.get('images'):
        parts.append('\n### Library images (for any new image use one of these real URLs, with a fitting alt text; '
                     'use a placeholder only when none fits)')
        parts += [f"- {i['url']} — {i['alt']}" for i in ctx['images']]
    if 'forms' in ctx:
        if ctx['forms']:
            parts.append('\n### Forms on this site (a form posts only to one of these; never invent another slug)')
            parts += [f"- {f['name']}: `action=\"/forms/{f['slug']}/submit/\"`" for f in ctx['forms']]
        else:
            parts.append('\n### Forms\nThis site has no forms: link to the contact details instead of adding a form.')
    if ctx.get('design_guide'):
        parts.append(f"\n### Design guide\n{ctx['design_guide']}")
    return '\n'.join(parts)


def matches_summary(ctx):
    colors = [c['value'] for c in ctx.get('colors', []) if c['value'] not in ('#FFFFFF', '#000000')][:5]
    fonts = []
    for f in ctx.get('fonts', []):
        if f['family'] not in fonts:
            fonts.append(f['family'])
    return {'colors': colors, 'fonts': fonts[:2], 'references': [r['label'] for r in ctx.get('references', [])][:3]}
