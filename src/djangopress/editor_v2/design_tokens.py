"""The site's colours, fonts and size presets for the editor's Design panel:
SiteSettings first (only fields the site actually set), then the colours and
fonts its pages and header/footer use most."""
import re
from collections import Counter

from djangopress.core.models import GlobalSection, Page, SiteSettings

NAMED_COLORS = [
    ('primary_color', 'Primary'), ('primary_color_hover', 'Primary hover'), ('secondary_color', 'Secondary'),
    ('accent_color', 'Accent'), ('background_color', 'Background'), ('text_color', 'Text'),
    ('heading_color', 'Heading'), ('primary_button_bg', 'Button'), ('primary_button_text', 'Button text'),
    ('secondary_button_bg', 'Button 2'), ('secondary_button_text', 'Button 2 text'),
]
HEX_CLASS_RE = re.compile(r'\[(#[0-9A-Fa-f]{6})\]')
FONT_CLASS_RE = re.compile(r"font-\['?([A-Za-z][\w ]*?)'?\]")
SITE_COLORS = 8
SITE_FONTS = 4
SPACING = {'S': 40, 'M': 64, 'L': 104, 'XL': 152}
SPACING_FACTOR = {'tight': 0.75, 'normal': 1, 'relaxed': 1.25, 'loose': 1.5}
BUTTON_SIZES = {'S': [10, 18, 13], 'M': [14, 28, 15], 'L': [18, 36, 17]}


def _hex(value):
    value = (value or '').strip()
    return value.upper() if re.fullmatch(r'#[0-9A-Fa-f]{6}', value) else None


def _site_html():
    settings = SiteSettings.load()
    lang = settings.get_default_language() if settings else 'pt'
    for page in Page.objects.filter(is_active=True):
        copies = page.html_content_i18n or {}
        yield copies.get(lang) or next(iter(copies.values()), '') or ''
    for section in GlobalSection.objects.filter(is_active=True):
        copies = section.html_template_i18n or {}
        yield copies.get(lang) or next(iter(copies.values()), '') or ''


def collect_tokens():
    settings = SiteSettings.load()
    html = list(_site_html())

    colors, seen = [], set()

    def add(name, value):
        if value and value not in seen:
            seen.add(value)
            colors.append({'name': name, 'value': value})

    for field, name in NAMED_COLORS:
        value = getattr(settings, field, '')
        if value == SiteSettings._meta.get_field(field).default:   # never set by this site
            continue
        add(name, _hex(value))
    used = Counter(m.upper() for chunk in html for m in HEX_CLASS_RE.findall(chunk))
    extra = 0
    for value, _count in used.most_common():
        if extra >= SITE_COLORS:
            break
        if value not in seen:
            add(value, value)
            extra += 1
    add('White', '#FFFFFF')
    add('Black', '#000000')

    fonts, families = [], set()

    def add_font(role, family):
        family = (family or '').strip().replace('_', ' ')
        if family and family not in families:
            families.add(family)
            fonts.append({'role': role, 'family': family})

    add_font('Headings', settings.heading_font)
    add_font('Body', settings.body_font)
    for n in range(1, 7):
        add_font(f'H{n}', getattr(settings, f'h{n}_font', ''))
    page_fonts = Counter(m.replace('_', ' ') for chunk in html for m in FONT_CLASS_RE.findall(chunk))
    for family, _count in page_fonts.most_common(SITE_FONTS):
        add_font('Used on the site', family)

    factor = SPACING_FACTOR.get(getattr(settings, 'spacing_scale', 'normal'), 1)
    spacing = {k: int(round(v * factor / 4)) * 4 for k, v in SPACING.items()}
    return {'colors': colors, 'fonts': fonts, 'spacing': spacing, 'buttonSizes': BUTTON_SIZES}
