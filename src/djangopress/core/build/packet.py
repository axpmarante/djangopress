"""Assemble docs/build-packet.json: every fact the builders and checks need."""

import re
from urllib.request import urlopen  # patched in tests

from django.utils.text import slugify

VERTICALS = {
    'restaurant': {
        'keywords': ['restaurante', 'restaurant', 'cozinha', 'chef', 'menu', 'carta', 'gastron'],
        'specialization': 'hospitality, restaurants and premium consumer brands',
        'jsonld': 'Restaurant',
        'families': ['editorial', 'cinematic hospitality', 'Mediterranean modernism', 'vernacular / regional',
                     'cultural / craft', 'publication / magazine', 'immersive photography', 'expressive typography',
                     'contemporary luxury', 'retro-modern'],
    },
    'hospitality': {
        'keywords': ['hotel', 'alojamento', 'lodging', 'apartamento', 'guest', 'villa', 'resort', 'turismo rural'],
        'specialization': 'hospitality, resorts and boutique lodging',
        'jsonld': 'LodgingBusiness',
        'families': ['resort lifestyle', 'cinematic hospitality', 'Mediterranean modernism', 'artistic minimalism',
                     'immersive photography', 'contemporary luxury', 'editorial', 'narrative / storytelling'],
    },
    'real-estate': {
        'keywords': ['imobili', 'real estate', 'propert', 'moradia', 'apartamentos para venda', 'realtor'],
        'specialization': 'real estate, architecture and premium property brands',
        'jsonld': 'RealEstateAgent',
        'families': ['architectural modernism', 'contemporary luxury', 'gallery / museum', 'editorial',
                     'artistic minimalism', 'product-led', 'publication / magazine'],
    },
    'legal': {
        'keywords': ['advogad', 'law firm', 'legal', 'jurídic', 'juridic', 'solicitor'],
        'specialization': 'professional services, law and finance brands',
        'jsonld': 'LegalService',
        'families': ['architectural modernism', 'contemporary luxury', 'gallery / museum', 'publication / magazine',
                     'artistic minimalism', 'editorial'],
    },
    'retail': {
        'keywords': ['loja', 'shop', 'store', 'retail', 'produtos', 'boutique', 'e-commerce'],
        'specialization': 'retail, product and lifestyle brands',
        'jsonld': 'Store',
        'families': ['product-led', 'graphic-design-led', 'fashion editorial', 'retro-modern', 'postmodern',
                     'editorial', 'neo-brutalism', 'expressive typography'],
    },
    'tourism': {
        'keywords': ['tour', 'passeio', 'boat', 'barco', 'transfer', 'excurs', 'experiênc', 'experience', 'activit'],
        'specialization': 'travel, tours and outdoor experience brands',
        'jsonld': 'TouristInformationCenter',
        'families': ['immersive photography', 'resort lifestyle', 'narrative / storytelling', 'cinematic hospitality',
                     'graphic-design-led', 'vernacular / regional', 'editorial'],
    },
    'services': {
        'keywords': [],
        'specialization': 'service businesses and professional brands',
        'jsonld': 'LocalBusiness',
        'families': ['editorial', 'architectural modernism', 'artistic minimalism', 'graphic-design-led',
                     'contemporary luxury', 'publication / magazine', 'expressive typography'],
    },
}

LANG_NAMES = {'pt': 'Português', 'en': 'English', 'fr': 'Français', 'de': 'Deutsch', 'es': 'Español', 'it': 'Italiano'}
INVENTORY_ROW_RE = re.compile(r'^\|\s*(?P<group>[^|]+?)\s*\|\s*(?P<count>\d+)\s*\|\s*(?P<width>[^|]*?)\s*\|\s*(?P<source>[^|]*?)\s*\|\s*(?P<url>https?://\S+)\s*\|')


def detect_vertical(briefing):
    override = (briefing.notes.get('vertical') or '').strip().lower()
    if override in VERTICALS:
        return override
    haystack = (briefing.business + ' ' + briefing.title).lower()
    for name, spec in VERTICALS.items():
        if any(k in haystack for k in spec['keywords']):
            return name
    return 'services'


def parse_inventory(audit_text):
    """Rows of the audit's `## Image Inventory` table that carry a URL and a count > 0."""
    rows = []
    in_table = False
    for line in audit_text.splitlines():
        if line.startswith('## '):
            in_table = line.strip().lower() == '## image inventory'
            continue
        if not in_table:
            continue
        m = INVENTORY_ROW_RE.match(line.strip())
        if m and int(m.group('count')) > 0:
            width_m = re.match(r'(\d{3,4})', m.group('width'))
            rows.append({
                'group': m.group('group'),
                'key': slugify(m.group('group')) + '-1',
                'width': int(width_m.group(1)) if width_m else None,
                'url': m.group('url').rstrip('|').strip(),
            })
    return rows


def download(url):
    return urlopen(url, timeout=30).read()


def _menu_items(menu, lang):
    items = []
    for category, entries in (menu.get(lang) or next(iter(menu.values()), {})).items():
        for e in entries:
            items.append({'name': e.get('title', ''), 'price': e.get('price', ''), 'category': category})
    return items


def _item_dict(item, menus, lang):
    d = {'id': item.id, 'kind': item.kind, 'text': item.text}
    if item.keywords:
        d['keywords'] = item.keywords
    if item.href:
        d['href'] = item.href
    if item.menu_json and item.menu_json in menus:
        d['items'] = _menu_items(menus[item.menu_json], lang)
    return d


def build_packet(briefing, *, site_slug, image_map, menus):
    vertical = detect_vertical(briefing)
    spec = VERTICALS[vertical]
    lang = briefing.default_language
    content = {}
    for page, items in briefing.content.items():
        content[page] = {
            'required': [_item_dict(i, menus, lang) for i in items if i.required],
            'optional': [_item_dict(i, menus, lang) for i in items if not i.required],
        }
    first_sentence = re.split(r'(?<=[.!?])\s', briefing.business.strip(), maxsplit=1)[0]
    return {
        'site': {
            'slug': site_slug, 'name': briefing.title, 'default_language': lang,
            'default_language_name': briefing.language_names.get(lang, LANG_NAMES.get(lang, lang)),
            'languages': briefing.languages, 'lang_prefix': f'/{lang}',
        },
        'business': {
            'type': vertical,
            'jsonld_type': briefing.notes.get('jsonld') or spec['jsonld'],
            'specialization': spec['specialization'],
            'positioning': first_sentence,
            'prose': briefing.business,
            'cuisine': briefing.notes.get('cuisine', ''),
            'price_range': briefing.notes.get('price range', '€€'),
        },
        'families': spec['families'],
        'facts': {
            'phone': briefing.contact.get('phone', ''), 'email': briefing.contact.get('email', ''),
            'address': briefing.contact.get('address', ''), 'maps_url': briefing.contact.get('maps_url', ''),
            'hours': briefing.hours, 'social': briefing.social,
        },
        'pages': briefing.pages,
        'content': content,
        'images': {
            'strategy': briefing.images.get('strategy', 'skip'),
            'map': image_map,
            'constraints': briefing.constraints.get('image_max_widths', {}),
        },
        'design_constraints': briefing.constraints,
        'header': briefing.header,
        'footer': briefing.footer,
    }
