"""JSON-LD for SiteSettings.custom_head_code, built from the packet's facts."""

import re

DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
DAY_TOKENS = {
    'segunda': 0, 'seg': 0, 'monday': 0, 'mon': 0, 'terça': 1, 'terca': 1, 'ter': 1, 'tuesday': 1, 'tue': 1,
    'quarta': 2, 'qua': 2, 'wednesday': 2, 'wed': 2, 'quinta': 3, 'qui': 3, 'thursday': 3, 'thu': 3,
    'sexta': 4, 'sex': 4, 'friday': 4, 'fri': 4, 'sábado': 5, 'sabado': 5, 'sáb': 5, 'sab': 5, 'saturday': 5, 'sat': 5,
    'domingo': 6, 'dom': 6, 'sunday': 6, 'sun': 6,
}
CLOSED_WORDS = ('encerrado', 'fechado', 'closed')
TIME_RANGE_RE = re.compile(r'(\d{1,2})[:h](\d{2})\s*[–\-—a]+\s*(\d{1,2})[:h](\d{2})')
WORD_RE = re.compile(r'[a-záéíóúâêôãõç]+', re.I)
RANGE_WORDS = ('a', 'to', '-', '–', 'até')
GEO_RES = (re.compile(r'@(-?\d+\.\d+),(-?\d+\.\d+)'), re.compile(r'[?&]q=(-?\d+\.\d+),(-?\d+\.\d+)'),
           re.compile(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)'))


def _days_from(text):
    tokens = [w.lower() for w in WORD_RE.findall(text)]
    idx = [(i, DAY_TOKENS[t]) for i, t in enumerate(tokens) if t in DAY_TOKENS]
    if not idx:
        return []
    if len(idx) == 2 and any(t in RANGE_WORDS for t in tokens[idx[0][0] + 1:idx[1][0]]):
        a, b = idx[0][1], idx[1][1]
        return [DAYS[i % 7] for i in range(a, b + 1 if b >= a else b + 8)]
    return [DAYS[d] for _, d in idx]


def parse_hours_line(line):
    if any(w in line.lower() for w in CLOSED_WORDS) and not TIME_RANGE_RE.search(line):
        return []
    head = line.split(':', 1)[0] if re.match(r'^[^\d]*:', line) else line
    days = _days_from(head)
    specs = []
    for o1, o2, c1, c2 in TIME_RANGE_RE.findall(line):
        spec = {'@type': 'OpeningHoursSpecification', 'opens': f'{int(o1):02d}:{o2}', 'closes': f'{int(c1):02d}:{c2}'}
        if days:
            spec['dayOfWeek'] = days
        else:
            spec['description'] = line.strip()
        specs.append(spec)
    return specs


def geo_from_maps_url(url):
    for rx in GEO_RES:
        m = rx.search(url or '')
        if m:
            return {'@type': 'GeoCoordinates', 'latitude': float(m.group(1)), 'longitude': float(m.group(2))}
    return None


def build_jsonld(packet):
    facts, biz, site = packet['facts'], packet['business'], packet['site']
    data = {'@context': 'https://schema.org', '@type': biz['jsonld_type'], 'name': site['name']}
    if facts.get('phone'):
        data['telephone'] = facts['phone']
    if facts.get('email'):
        data['email'] = facts['email']
    if facts.get('address'):
        data['address'] = facts['address']
    geo = geo_from_maps_url(facts.get('maps_url', ''))
    if geo:
        data['geo'] = geo
    hours = [s for line in facts.get('hours', []) for s in parse_hours_line(line)]
    if hours:
        data['openingHoursSpecification'] = hours
    first = next((v['url'] for v in packet['images']['map'].values() if v.get('url')), None)
    if first:
        data['image'] = first
    social = [u for u in facts.get('social', {}).values() if u.startswith('http')]
    if social:
        data['sameAs'] = social
    if biz['jsonld_type'] == 'Restaurant':
        data['servesCuisine'] = biz.get('cuisine') or biz.get('positioning', '')
        data['priceRange'] = biz.get('price_range') or '€€'
    return data
