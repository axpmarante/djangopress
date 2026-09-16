"""Adapter: one standalone HTML document → DjangoPress-legal parts (spec §7).

Pure functions on BeautifulSoup trees; no database access. `adapt()` (Task 5)
orchestrates them and returns an AdaptResult.
"""

import re
from collections import Counter
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Comment, Tag
from django.utils.text import slugify

from djangopress.core.middleware import NON_I18N_PATHS

EDITABLE_TAGS = {'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'span', 'a', 'li', 'td', 'th', 'label', 'button', 'blockquote'}
FORBIDDEN_IN_PAGE = ('html', 'head', 'body', 'header', 'nav', 'footer')
NON_OVERLAY_TAGS = {'img', 'a', 'button', 'input', 'select', 'textarea', 'form', 'svg', 'video', 'iframe'}
SECTION_NAME_RE = re.compile(r'^[a-z][a-z0-9-]*$')
TEMPLATE_SYNTAX_RE = re.compile(r'{{|{%|{#')
BODY_SELECTOR_RE = re.compile(r'(?<![\w.#\-\[])body(?=\s*[{,])')
HEX_RE = re.compile(r'#[0-9a-fA-F]{6}\b')
CONFIG_COLOR_RE = re.compile(r"""([A-Za-z][\w-]*)\s*:\s*['"](#[0-9a-fA-F]{6})['"]""")
FONT_FAMILY_BLOCK_RE = re.compile(r'fontFamily\s*:\s*\{(.*?)\}', re.S)
FONT_ENTRY_RE = re.compile(r"""([A-Za-z][\w-]*)\s*:\s*\[\s*['"]([^'"]+)['"]""")
GOOGLE_FAMILY_RE = re.compile(r'family=([^:&]+)')
BODY_RULE_RE = re.compile(r'(?<![\w.#-])body(?:\.bg-white)?\s*\{([^}]*)\}')
CSS_BG_RE = re.compile(r'background(?:-color)?\s*:\s*(#[0-9a-fA-F]{6})')
CSS_COLOR_RE = re.compile(r'(?<![-\w])color\s*:\s*(#[0-9a-fA-F]{6})')
MAX_W_RE = re.compile(r'^max-w-(\w+|\[\d+px\])$')
ROUNDED_RE = re.compile(r'^rounded(?:-(\w+))?$')
SHADOW_RE = re.compile(r'^shadow(?:-(\w+))?$')
CONTAINER_CHOICES = {'full', 'xs', 'sm', 'md', 'lg', 'xl', '2xl', '3xl', '4xl', '5xl', '6xl', '7xl'}
RADIUS_MAP = {None: 'md', 'none': 'none', 'sm': 'sm', 'md': 'md', 'lg': 'lg', 'xl': 'xl', '2xl': '2xl', '3xl': '3xl', 'full': 'full'}
SHADOW_MAP = {None: 'md', 'none': 'none', 'sm': 'sm', 'md': 'md', 'lg': 'lg', 'xl': 'xl', '2xl': '2xl'}
PLACEHOLDER_HOST = 'placehold.co'
SWITCHER_TOKEN = '__DP_LANGUAGE_SWITCHER__'


@dataclass
class AdaptResult:
    page_html: str = ''
    header_html: str = ''
    footer_html: str = ''
    head_code: str = ''
    settings: dict = field(default_factory=dict)
    meta_title: str = ''
    meta_description: str = ''
    sections: list = field(default_factory=list)
    menu: list = field(default_factory=list)
    changes: Counter = field(default_factory=Counter)
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    @property
    def ok(self):
        return not self.errors

    def as_report(self):
        return {
            'ok': self.ok, 'errors': self.errors, 'warnings': self.warnings, 'changes': dict(self.changes),
            'sections': self.sections, 'menu': self.menu, 'settings': self.settings,
            'meta_title': self.meta_title, 'meta_description': self.meta_description,
        }


def soup_of(html):
    return BeautifulSoup(html, 'html.parser')


def check_complete(raw):
    """Truncation guard: the builder contract says the document ends with </html>."""
    errors = []
    low = raw.lower()
    if '</html>' not in low.rstrip()[-300:]:
        errors.append('truncated: document does not end with </html>')
    for tag in ('<header', '<main', '<footer'):
        if tag not in low:
            errors.append(f'missing {tag}> element')
    return errors


def split_document(soup):
    header = soup.find('header')
    main = soup.find('main')
    footer = soup.find('footer')
    body = soup.body or soup
    trailing = [s for s in body.find_all('script', recursive=False)]
    return header, main, footer, trailing


def lift_head(soup):
    """Pull tailwind.config, <style>, lucide and meta out of <head>; drop the duplicate CDN and font links."""
    head = soup.head or soup
    removed = Counter()
    config_js, css_blocks, extra = '', [], []
    google_families = []
    for script in head.find_all('script'):
        src = script.get('src', '')
        text = script.get_text()
        if 'cdn.tailwindcss.com' in src:
            removed['tailwind-cdn'] += 1
        elif 'tailwind.config' in text:
            config_js = text.strip()
        elif 'lucide' in src:
            extra.append(f'<script src="{src}"></script>')
        elif src:
            removed['other-script'] += 1
        elif text.strip():
            extra.append(f'<script>{text.strip()}</script>')
    for style in head.find_all('style'):
        css_blocks.append(style.get_text().strip())
    for link in head.find_all('link'):
        href = link.get('href', '')
        if 'fonts.googleapis.com' in href or 'fonts.gstatic.com' in href:
            removed['google-fonts-link'] += 1
            for fam in GOOGLE_FAMILY_RE.findall(href):
                google_families.append(fam.replace('+', ' '))
    title = soup.title.get_text(strip=True) if soup.title else ''
    desc_tag = head.find('meta', attrs={'name': 'description'})
    css = '\n'.join(b for b in css_blocks if b)
    parts = []
    if config_js:
        parts.append(f'<script>\n{config_js}\n</script>')
    if css:
        parts.append(f'<style>\n{css}\n</style>')
    parts.extend(extra)
    return {
        'head_code': '\n'.join(parts), 'css': css, 'config_js': config_js,
        'meta_title': title, 'meta_description': desc_tag.get('content', '').strip() if desc_tag else '',
        'google_families': google_families, 'removed': removed,
    }


def fix_body_rules(css):
    """base.html hardcodes <body class="bg-white">; `body {}` loses to it. Raise specificity."""
    return BODY_SELECTOR_RE.subn('body.bg-white', css)


def extract_fonts(config_js, google_families):
    families = {}
    m = FONT_FAMILY_BLOCK_RE.search(config_js or '')
    if m:
        for name, first in FONT_ENTRY_RE.findall(m.group(1)):
            families[name] = first.strip()
    heading = families.get('display') or families.get('heading') or families.get('serif')
    body = families.get('sans') or families.get('body')
    if not heading:
        others = [v for k, v in families.items() if v != body]
        heading = others[0] if others else None
    if not heading and google_families:
        heading = google_families[0]
    if not body and google_families:
        body = google_families[1] if len(google_families) > 1 else google_families[0]
    return (heading or 'Inter', body or heading or 'Inter')


def _class_tokens(tag):
    return tag.get('class', []) if tag else []


def _color_from_classes(tokens, prefix, config):
    for t in tokens:
        if t.startswith(prefix + '[#') and t.endswith(']'):
            return t[len(prefix) + 1:-1].lower()
        if t.startswith(prefix):
            name = t[len(prefix):]
            if name in config:
                return config[name]
            if name == 'white':
                return '#ffffff'
            if name == 'black':
                return '#000000'
    return None


def extract_colors(config_js, css, root, cta_texts=()):
    config = {k: v.lower() for k, v in CONFIG_COLOR_RE.findall(config_js or '')}
    background = text = None
    m = BODY_RULE_RE.search(css or '')
    if m:
        bg = CSS_BG_RE.search(m.group(1))
        fg = CSS_COLOR_RE.search(m.group(1))
        background = bg.group(1).lower() if bg else None
        text = fg.group(1).lower() if fg else None
    if not background:
        background = _color_from_classes(_class_tokens(root.body), 'bg-', config) or '#ffffff'
    if not text:
        text = _color_from_classes(_class_tokens(root.body), 'text-', config) or '#1f2937'

    wanted = {t.strip().lower() for t in cta_texts if t.strip()}
    button = None
    for tag in root.find_all(['a', 'button']):
        if tag.get_text(' ', strip=True).lower() in wanted and _color_from_classes(_class_tokens(tag), 'bg-', config):
            button = tag
            break
    if button is None:
        header = root.find('header')
        for tag in (header.find_all(['a', 'button']) if header else []):
            if _color_from_classes(_class_tokens(tag), 'bg-', config):
                button = tag
                break
    primary = _color_from_classes(_class_tokens(button), 'bg-', config) if button else None
    if not primary:
        primary = next((v for v in config.values() if v not in (background, text)), '#1e3a8a')
    button_text = (_color_from_classes(_class_tokens(button), 'text-', config) if button else None) or '#ffffff'

    usage = Counter()
    for tag in root.find_all(class_=True):
        for t in tag['class']:
            for prefix in ('bg-', 'text-', 'border-'):
                if t.startswith(prefix) and t[len(prefix):] in config:
                    usage[config[t[len(prefix):]]] += 1
    rest = [c for c, _ in usage.most_common() if c not in (background, text, primary)]
    rest += [c for c in config.values() if c not in rest and c not in (background, text, primary)]
    secondary = rest[0] if rest else text
    accent = rest[1] if len(rest) > 1 else primary
    return {
        'background_color': background, 'text_color': text, 'heading_color': text,
        'primary_color': primary, 'primary_button_bg': primary, 'primary_button_text': button_text,
        'secondary_color': secondary, 'accent_color': accent,
    }


def infer_layout(root):
    widths, radii, shadows = Counter(), Counter(), Counter()
    for tag in root.find_all(class_=True):
        for t in tag['class']:
            m = MAX_W_RE.match(t)
            if m:
                v = m.group(1)
                if v.startswith('['):
                    px = int(v[1:-3])
                    v = '6xl' if px <= 1152 else '7xl' if px <= 1280 else 'full'
                if v in CONTAINER_CHOICES:
                    widths[v] += 1
            m = ROUNDED_RE.match(t)
            if m and m.group(1) in RADIUS_MAP:
                radii[RADIUS_MAP[m.group(1)]] += 1
            m = SHADOW_RE.match(t)
            if m and m.group(1) in SHADOW_MAP:
                shadows[SHADOW_MAP[m.group(1)]] += 1
    return {
        'container_width': widths.most_common(1)[0][0] if widths else '7xl',
        'border_radius_preset': radii.most_common(1)[0][0] if radii else 'none',
        'shadow_preset': shadows.most_common(1)[0][0] if shadows else 'none',
    }


# --- part 2: structure ------------------------------------------------------

SWITCHER_HTML = (
    '{% load i18n %}<form action="{% url \'set_language\' %}" method="post" class="inline-block">{% csrf_token %}'
    '<input name="next" type="hidden" value="{{ request.path }}">'
    '<select name="language" onchange="this.form.submit()" class="bg-transparent cursor-pointer CLASSES">'
    '{% get_current_language as LANGUAGE_CODE %}{% get_available_languages as LANGUAGES %}'
    '{% for lang_code, lang_name in LANGUAGES %}<option value="{{ lang_code }}" {% if lang_code == LANGUAGE_CODE %}selected{% endif %}>'
    '{{ lang_code|upper }}</option>{% endfor %}</select></form>'
)


def _unique(name, seen):
    base = name if SECTION_NAME_RE.match(name) else 's-' + re.sub(r'[^a-z0-9-]', '', name.lower()) or 's'
    if not SECTION_NAME_RE.match(base):
        base = 'section'
    candidate, n = base, 2
    while candidate in seen:
        candidate, n = f'{base}-{n}', n + 1
    seen.add(candidate)
    return candidate


def name_sections(main, contact_phone=''):
    """Every direct child of <main> becomes a <section data-section=id id=...>; names synthesised when missing."""
    for child in list(main.children):
        if isinstance(child, Comment):
            child.extract()
            continue
        if getattr(child, 'name', None) is None:
            if str(child).strip():
                child.wrap(Tag(name='section'))
            continue
        if child.name != 'section':
            child.wrap(Tag(name='section'))
    seen, names = set(), []
    sections = main.find_all('section', recursive=False)
    for i, sec in enumerate(sections):
        name = (sec.get('id') or '').strip().lower()
        if not name:
            if i == 0:
                name = 'hero'
            elif sec.find('form') or (contact_phone and contact_phone in sec.get_text(' ')):
                name = 'contact'
            else:
                heading = sec.find(['h1', 'h2', 'h3'])
                name = slugify(heading.get_text(' ', strip=True)) if heading else 'section'
        name = _unique(name or 'section', seen)
        sec['id'] = name
        sec['data-section'] = name
        names.append(name)
    return names


def prefix_links(root, lang, codes):
    n = 0
    for a in root.find_all('a', href=True):
        href = a['href'].strip()
        new = href
        if href.startswith('#'):
            new = f'/{lang}/{href}'
        elif href == '/':
            new = f'/{lang}/'
        elif href.startswith('/') and not href.startswith('//'):
            if not href.startswith(NON_I18N_PATHS) and not any(href == f'/{c}' or href.startswith(f'/{c}/') for c in codes):
                new = f'/{lang}{href}'
        if new != href:
            a['href'] = new
            n += 1
    return n


def inject_language_switcher(header):
    """Replace <div data-slot="language-switcher"> (or append to <nav>) with a token swapped after serialisation."""
    slot = header.find(attrs={'data-slot': 'language-switcher'})
    nav = header.find('nav') or header
    first_link = nav.find('a')
    classes = ' '.join(c for c in _class_tokens(first_link) if c.startswith(('text-', 'uppercase', 'tracking-', 'font-')))
    if slot is not None:
        slot.replace_with(SWITCHER_TOKEN)
    else:
        nav.append(SWITCHER_TOKEN)
    return SWITCHER_HTML.replace('CLASSES', classes)


def find_template_syntax(html):
    return bool(TEMPLATE_SYNTAX_RE.search(html))


def apply_editor_contract(root, changes):
    for el in root.find_all(class_=True):
        classes = el['class']
        if not ({'absolute', 'fixed'} & set(classes)) or el.name in NON_OVERLAY_TAGS:
            continue
        if el.find(['img', 'svg', 'video', 'input', 'button']):
            continue
        if el.name in EDITABLE_TAGS and el.get_text(strip=True):
            continue
        if any(d.name in EDITABLE_TAGS and d.get_text(strip=True) for d in el.find_all(True)):
            continue
        if 'pointer-events-none' not in classes:
            classes.append('pointer-events-none')
            changes['pointer-events-none'] += 1
    seen = set()
    for img in root.find_all('img'):
        if any(c.startswith('splide') for p in img.parents for c in _class_tokens(p)):
            continue
        src = img.get('src', '')
        if src in seen and img.get('aria-hidden') != 'true':
            img['aria-hidden'] = 'true'
            img['alt'] = ''
            changes['duplicate-img-decorative'] += 1
        seen.add(src)


def normalise_images(root, image_urls, changes, warnings, part):
    counter = 0
    for img in root.find_all('img'):
        src = img.get('src', '').strip()
        section = img.find_parent('section')
        sec_name = section.get('id', part) if section else part
        counter += 1
        if PLACEHOLDER_HOST in src:
            pass
        elif src in image_urls or src.startswith(('/media/', '/static/')):
            if not img.get('alt') and img.get('aria-hidden') != 'true':
                img['alt'] = img.get('data-image-name') or sec_name
                changes['alt-filled'] += 1
            continue
        else:
            warnings.append(f'{part}/{sec_name}: image {src[:80]!r} not in the inventory — replaced by a placeholder')
            img['src'] = f'https://{PLACEHOLDER_HOST}/1200x800?text={sec_name}'
            changes['img-replaced'] += 1
        if not img.get('data-image-name'):
            img['data-image-name'] = f'{sec_name}-img-{counter}'
        if not img.get('data-image-prompt'):
            img['data-image-prompt'] = img.get('alt') or f'photo for {sec_name}'
        if img.get('aria-hidden') == 'true':
            img['alt'] = ''
        elif not img.get('alt'):
            img['alt'] = img['data-image-name']


def extract_menu(header):
    nav = header.find('nav') or header
    items = []
    for a in nav.find_all('a', href=True):
        label = a.get_text(' ', strip=True)
        if label:
            items.append({'label': label, 'href': a['href']})
    return items


def adapt(raw, *, lang, languages, image_map, cta_texts=(), contact_phone=''):
    result = AdaptResult()
    result.errors.extend(check_complete(raw))
    if result.errors:
        return result
    soup = soup_of(raw)
    header, main, footer, trailing = split_document(soup)
    if header is None or main is None or footer is None:
        result.errors.append('document must have one <header>, one <main> and one <footer>')
        return result

    head = lift_head(soup)
    css, n = fix_body_rules(head['css'])
    result.changes['body-rule-rewritten'] = n
    result.changes.update(head['removed'])
    head_code = head['head_code'].replace(head['css'], css) if head['css'] else head['head_code']
    result.head_code = head_code
    result.meta_title, result.meta_description = head['meta_title'], head['meta_description']

    heading_font, body_font = extract_fonts(head['config_js'], head['google_families'])
    result.settings = {'heading_font': heading_font, 'body_font': body_font}
    result.settings.update(extract_colors(head['config_js'], css, soup, cta_texts))
    result.settings.update(infer_layout(soup))

    for part, tag in (('header', header), ('footer', footer)):
        if find_template_syntax(str(tag)):
            result.errors.append(f'{part}: contains Django template syntax ({{{{, {{% or {{#) — not allowed')
    for tag in FORBIDDEN_IN_PAGE:
        if main.find(tag):
            result.errors.append(f'page: contains <{tag}> inside <main> — forbidden in page HTML')
    if main.find('style'):
        result.errors.append('page: <style> inside <main> — CSS belongs in <head>')
    if result.errors:
        return result

    result.sections = name_sections(main, contact_phone)
    codes = list(languages)
    for tag in (header, main, footer):
        result.changes['links-prefixed'] += prefix_links(tag, lang, codes)
    image_urls = {v['url'] for v in image_map.values() if v.get('url')}
    for part, tag in (('header', header), ('page', main), ('footer', footer)):
        apply_editor_contract(tag, result.changes)
        normalise_images(tag, image_urls, result.changes, result.warnings, part)
    if main.find('script'):
        result.warnings.append('page: inline <script> inside a section (kept)')
    result.menu = extract_menu(header)

    switcher = ''
    if len(codes) > 1:
        switcher = inject_language_switcher(header)
    else:
        slot = header.find(attrs={'data-slot': 'language-switcher'})
        if slot is not None:
            slot.decompose()

    result.header_html = str(header).replace(SWITCHER_TOKEN, switcher)
    result.footer_html = str(footer)
    page = ''.join(str(c) for c in main.children).strip()
    if trailing:
        page += '\n' + '\n'.join(str(s) for s in trailing)
    result.page_html = page
    return result
