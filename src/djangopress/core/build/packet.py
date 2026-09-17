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
        'structure': (
            'A restaurant one-page opens with a navigation that carries a reservation button, then a full-bleed hero with '
            'the dish or room photo and the reservation call to action. A short concept or intro section states the cuisine '
            'and the promise. Menu highlights follow with real item names and prices, then the chef or story section with a '
            'portrait. A gallery of the room and atmosphere gives the visitor the feel of the place, followed by reviews, '
            'awards and guide mentions as proof. Hours, address and a map sit together near the end, ahead of a reservation '
            'call-to-action band that repeats the button and the phone. The footer closes with contacts, hours, social '
            'links, privacy link and copyright.'
        ),
    },
    'hospitality': {
        'keywords': ['hotel', 'alojamento', 'lodging', 'apartamento', 'guest', 'villa', 'resort', 'turismo rural'],
        'specialization': 'hospitality, resorts and boutique lodging',
        'jsonld': 'LodgingBusiness',
        'families': ['resort lifestyle', 'cinematic hospitality', 'Mediterranean modernism', 'artistic minimalism',
                     'immersive photography', 'contemporary luxury', 'editorial', 'narrative / storytelling'],
        'structure': (
            'A lodging one-page opens with a hero built on the property photo and an availability or booking call to '
            'action. Rooms or units come next as cards with photos and "from" prices only when they are known. An amenities '
            'section lists what is included as an icon list. A location and experiences section places the property and '
            'what surrounds it, followed by guest reviews as proof. A gallery shows the property at large size, then a '
            'booking call-to-action band repeats the primary action. The footer closes with contacts, address, social links '
            'and legal links.'
        ),
    },
    'real-estate': {
        'keywords': ['imobili', 'real estate', 'propert', 'moradia', 'apartamentos para venda', 'realtor'],
        'specialization': 'real estate, architecture and premium property brands',
        'jsonld': 'RealEstateAgent',
        'families': ['architectural modernism', 'contemporary luxury', 'gallery / museum', 'editorial',
                     'artistic minimalism', 'product-led', 'publication / magazine'],
        'structure': (
            'A real-estate one-page opens with a hero holding a listing search or one featured property. Featured listings '
            'follow as cards with photo, location, key figures and price when known. A services section separates buying, '
            'selling and managing, then a why-us section with real numbers. Areas served are named explicitly, followed by '
            'client testimonials as proof. A contact form sits near the end with the phone beside it. The footer closes '
            'with contacts, licence details, social links and legal links.'
        ),
    },
    'legal': {
        'keywords': ['advogad', 'law firm', 'legal', 'jurídic', 'juridic', 'solicitor'],
        'specialization': 'professional services, law and finance brands',
        'jsonld': 'LegalService',
        'families': ['architectural modernism', 'contemporary luxury', 'gallery / museum', 'publication / magazine',
                     'artistic minimalism', 'editorial'],
        'structure': (
            'A law-firm one-page opens with a restrained hero: a headline, a short line on the firm and a consultation call '
            'to action. Practice areas come as a grid of cards, each with a short description. An about section presents '
            'the partners with photos, followed by a why-us or process section that explains how a matter is handled. '
            'Credentials such as bar registration, memberships and publications serve as proof. A contact form sits near '
            'the end with the phone number and the office address beside it. The footer closes with contacts, hours, legal '
            'and regulatory information and the privacy link.'
        ),
    },
    'retail': {
        'keywords': ['loja', 'shop', 'store', 'retail', 'produtos', 'boutique', 'e-commerce'],
        'specialization': 'retail, product and lifestyle brands',
        'jsonld': 'Store',
        'families': ['product-led', 'graphic-design-led', 'fashion editorial', 'retro-modern', 'postmodern',
                     'editorial', 'neo-brutalism', 'expressive typography'],
        'structure': (
            'A retail one-page opens with a hero built on the hero product or the current collection and a shop or visit '
            'call to action. Featured products or categories follow as a grid with photos and prices only when known. A '
            'value-propositions row states delivery, quality, origin or guarantees. A story section tells who makes or '
            'curates the products, followed by testimonials or press mentions as proof. A newsletter or contact section '
            'sits near the end. The footer closes with the shop address and hours, contacts, social links and legal links.'
        ),
    },
    'tourism': {
        'keywords': ['tour', 'passeio', 'boat', 'barco', 'transfer', 'excurs'],
        'specialization': 'travel, tours and outdoor experience brands',
        'jsonld': 'TouristInformationCenter',
        'families': ['immersive photography', 'resort lifestyle', 'narrative / storytelling', 'cinematic hospitality',
                     'graphic-design-led', 'vernacular / regional', 'editorial'],
        'structure': (
            'A tours-and-experiences one-page opens with a hero built on the experience photo and a book or ask call to '
            'action. Activities or tours follow as cards with duration and "from" price when known. A how-it-works section '
            'lays out the steps from booking to the day itself. A gallery shows the experience at large size, followed by '
            'reviews from the booking platforms as proof. An FAQ answers the practical questions, then a booking or contact '
            'form sits near the end with the phone or WhatsApp beside it. The footer closes with contacts, meeting point, '
            'social links and legal links.'
        ),
    },
    'construction': {
        'keywords': ['remodela', 'construç', 'construc', 'obras', 'renovation', 'canalizaç', 'canalizador',
                     'eletricista', 'plumb', 'reparaç', 'home repair'],
        'specialization': 'home services, construction and skilled trades',
        'jsonld': 'HomeAndConstructionBusiness',
        'families': ['vernacular / regional', 'architectural modernism', 'graphic-design-led', 'editorial',
                     'product-led', 'immersive photography', 'neo-brutalism', 'cultural / craft'],
        'structure': (
            'A construction or home-services one-page opens with a slim utility bar carrying the phone, a WhatsApp link and '
            'the 24 h availability, then a navigation with a quote button on the right. The hero is a large photo with a '
            'dark overlay, a direct headline and a quote-form card standing in the first viewport. An intro or why-us '
            'section follows with one photo and a row of stat tiles with real numbers. Services come as a grid of icon '
            'cards, each with a short description, followed by a service-area section naming the towns or region served. '
            'Proof arrives as a projects grid with a before/after pair, then testimonials placed beside the form. A '
            'coloured emergency or call-to-action band repeats the phone, and a multi-column footer closes with contacts, '
            'service links, hours and legal links.'
        ),
    },
    'services': {
        'keywords': [],
        'specialization': 'service businesses and professional brands',
        'jsonld': 'LocalBusiness',
        'families': ['editorial', 'architectural modernism', 'artistic minimalism', 'graphic-design-led',
                     'contemporary luxury', 'publication / magazine', 'expressive typography'],
        'structure': (
            'A service-business one-page opens with a hero holding the headline and the primary call to action, a form or a '
            'call button. Services follow as cards with short descriptions. A why-us section carries real numbers, then a '
            'process section lays out the steps of an engagement. A portfolio or cases section shows work done, followed by '
            'testimonials as proof. A contact form sits near the end with the phone beside it. The footer closes with '
            'contacts, hours, social links and legal links.'
        ),
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


def _form_fields(briefing):
    raw = briefing.notes.get('form fields', '')
    fields = [f.strip() for f in raw.split(',') if f.strip()]
    return fields or ['name', 'email', 'message']


def _form_service_options(briefing):
    raw = briefing.notes.get('form service options', '')
    return [o.strip() for o in raw.split(',') if o.strip()]


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
            'structure': spec['structure'],
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
        'notes': dict(briefing.notes),
        'form': {
            'slug': 'contact', 'action': '/forms/contact/submit/',
            'fields': _form_fields(briefing), 'service_options': _form_service_options(briefing),
        },
    }
