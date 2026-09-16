"""Content contract: every (required) briefing item must be present in the shipped HTML (spec §8.3)."""

import re
import unicodedata

from bs4 import BeautifulSoup

TIME_RE = re.compile(r'\d{1,2}[:h]\d{2}')


def normalise(text):
    text = unicodedata.normalize('NFC', text or '')
    return re.sub(r'\s+', ' ', text).strip().casefold()


def loose(text):
    """normalise() with anything that isn't a letter, digit or space stripped — for
    punctuation-insensitive verbatim matching (quotes, dashes, em/en spacing)."""
    text = re.sub(r'[^\w\s]', '', normalise(text), flags=re.UNICODE)
    return re.sub(r'\s+', ' ', text).strip()


def _digits(text):
    return re.sub(r'\D', '', text or '')


def _haystack(parts):
    texts, hrefs, raw = [], [], []
    for html in parts.values():
        soup = BeautifulSoup(html, 'html.parser')
        texts.append(soup.get_text(' '))
        texts.extend(img.get('alt', '') for img in soup.find_all('img'))
        hrefs.extend(a['href'].strip() for a in soup.find_all('a', href=True))
        raw.append(html)
    return normalise(' '.join(texts)), set(hrefs)


def _price_forms(price):
    p = price.strip().replace(',', '.')
    return {p, p.replace('.', ',')}


def check_contract(packet, parts, lang):
    text, hrefs = _haystack(parts)
    loose_text = loose(text)
    misses = []

    def matches(s):
        return normalise(s) in text or loose(s) in loose_text

    def miss(item, reason):
        misses.append({'id': item['id'], 'kind': item['kind'], 'text': item.get('text', ''), 'reason': reason})

    for page in packet['content'].values():
        for item in page['required']:
            if (item.get('kind') or '').casefold() == 'contact':
                # facts (phone/email/address/hours) are checked separately below.
                continue
            if item.get('items'):
                for entry in item['items']:
                    if not matches(entry['name']):
                        miss(item, f"menu item {entry['name']!r} not found")
                        break
                    if entry.get('price') and not any(f in text for f in _price_forms(entry['price'])):
                        miss(item, f"price {entry['price']!r} for {entry['name']!r} not found")
                        break
            elif item.get('href'):
                href = item['href']
                wanted = f'/{lang}{href}' if href.startswith('/') and not href.startswith(f'/{lang}/') else href
                if wanted not in hrefs:
                    miss(item, f'no link to {wanted}')
                elif not matches(item['text']):
                    miss(item, f"CTA label {item['text']!r} not found")
            elif item.get('keywords'):
                if not any(normalise(k) in text for k in item['keywords']):
                    miss(item, f"none of the keywords {item['keywords']} found")
            elif not matches(item.get('text', '')):
                miss(item, f"text {item['text']!r} not found verbatim")

    facts = packet['facts']
    fact_item = {'id': 'facts', 'kind': 'Contact', 'text': ''}
    if facts.get('phone') and _digits(facts['phone']) not in _digits(text):
        miss(fact_item, f"phone {facts['phone']!r} not found")
    if facts.get('email') and normalise(facts['email']) not in text:
        miss(fact_item, f"email {facts['email']!r} not found")
    if facts.get('address') and normalise(facts['address']) not in text:
        miss(fact_item, f"address {facts['address']!r} not found")
    for line in facts.get('hours', []):
        for t in TIME_RE.findall(line):
            canon = t.replace('h', ':')
            if canon not in text and canon.replace(':', 'h') not in text:
                miss(fact_item, f'opening hours {t} (from {line!r}) not found')
                break
    return misses
