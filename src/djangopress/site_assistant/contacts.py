"""Contact checks for the assistant's validate_contacts tool. Read-only.

Collects phone numbers, emails and WhatsApp links from SiteSettings, every
active page and global section, in every language, and reports issues as
'wrong' (broken), 'inconsistent' (differs from Settings / elsewhere) or
'cant_verify' (a check that couldn't run, e.g. offline DNS).
"""
import json
import re
import urllib.parse
import urllib.request

from bs4 import BeautifulSoup, NavigableString

PHONE_RE = re.compile(r'(?<![\w/=])(?:\+|00)?\d[\d\s.\-()]{7,}\d(?![\w/])')
EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)*')
EMAIL_OK_RE = re.compile(r'^[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[a-z]{2,}$', re.IGNORECASE)
TEMPLATE_RE = re.compile(r'\{\{.*?\}\}|\{%.*?%\}', re.DOTALL)
WHATSAPP_RE = re.compile(r'(?:wa\.me/|whatsapp\.com/send/?\?phone=)\+?(\d+)', re.IGNORECASE)


def normalise_phone(text):
    """Digits with the country code: '289 000 000' → '351289000000'."""
    raw = str(text or '').strip()
    digits = re.sub(r'\D', '', raw)
    if raw.startswith('00'):
        digits = digits[2:]
    elif not raw.startswith('+') and len(digits) == 9 and digits[0] in '29':
        digits = '351' + digits
    return digits


def phone_is_valid(raw):
    norm = normalise_phone(raw)
    if norm.startswith('351'):
        return len(norm) == 12 and norm[3] in '239'
    international = str(raw).strip().startswith(('+', '00'))
    return international and 8 <= len(norm) <= 15


def mail_domain_status(domain):
    """'ok' (has MX), 'no_mx' (no mail server / domain doesn't exist) or 'unknown'."""
    try:
        import dns.resolver
    except ImportError:
        dns = None
    if dns is not None:
        try:
            dns.resolver.resolve(domain, 'MX', lifetime=5)
            return 'ok'
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            return 'no_mx'
        except Exception:
            return 'unknown'
    url = 'https://dns.google/resolve?' + urllib.parse.urlencode({'name': domain, 'type': 'MX'})
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (DjangoPress contact check)',
                                                   'Accept': 'application/dns-json'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        return 'unknown'
    if data.get('Status') == 3:
        return 'no_mx'
    if data.get('Status') != 0:
        return 'unknown'
    return 'ok' if any(a.get('type') == 15 for a in data.get('Answer') or []) else 'no_mx'


def _section_of(node):
    section = node.find_parent(attrs={'data-section': True}) if hasattr(node, 'find_parent') else None
    return section.get('data-section') if section is not None else None


def _sources():
    """(label, {lang: html}) for every active page and global section."""
    from djangopress.core.models import GlobalSection, Page
    for page in Page.objects.filter(is_active=True):
        yield page.default_title or f'Page {page.pk}', page.html_content_i18n or {}
    for section in GlobalSection.objects.filter(is_active=True):
        yield section.name or section.key, section.html_template_i18n or {}


def collect():
    """Every contact found in the content: [{kind, value, norm, where, link_text?}]."""
    found = []
    for label, copies in _sources():
        for lang, html in copies.items():
            if not html:
                continue
            soup = BeautifulSoup(html, 'html.parser')
            for a in soup.find_all('a', href=True):
                href = a['href'].strip()
                if TEMPLATE_RE.search(href):      # {{ CONTACT_EMAIL }} etc. render from Settings
                    continue
                where = {'source': label, 'section': _section_of(a), 'lang': lang}
                text = TEMPLATE_RE.sub(' ', a.get_text(' ', strip=True))
                if href.lower().startswith('tel:'):
                    number = urllib.parse.unquote(href[4:])
                    found.append({'kind': 'phone', 'value': number, 'norm': normalise_phone(number),
                                  'where': where, 'link_text': text, 'link': True})
                elif href.lower().startswith('mailto:'):
                    address = urllib.parse.unquote(href[7:].split('?')[0]).strip()
                    found.append({'kind': 'email', 'value': address, 'norm': address.lower(),
                                  'where': where, 'link_text': text, 'link': True})
                else:
                    match = WHATSAPP_RE.search(href)
                    if match:
                        found.append({'kind': 'whatsapp', 'value': match.group(1),
                                      'norm': normalise_phone('+' + match.group(1)), 'where': where})
            for node in soup.find_all(string=True):
                if not isinstance(node, NavigableString) or node.find_parent(['script', 'style']):
                    continue
                link = node.find_parent('a', href=True)
                if link is not None and link['href'].lower().startswith(('tel:', 'mailto:')):
                    continue
                where = {'source': label, 'section': _section_of(node), 'lang': lang}
                text = TEMPLATE_RE.sub(' ', str(node))
                for match in PHONE_RE.finditer(text):
                    norm = normalise_phone(match.group())
                    if 9 <= len(norm) <= 15:
                        found.append({'kind': 'phone', 'value': match.group().strip(), 'norm': norm, 'where': where})
                for match in EMAIL_RE.finditer(text):
                    found.append({'kind': 'email', 'value': match.group(), 'norm': match.group().lower(), 'where': where})
    return found


def _settings_where(field):
    return {'source': 'Settings', 'section': field, 'lang': None}


def check(check_web=False):
    """{'issues': [...], 'sources': [...], 'web_answer': str|None}"""
    from djangopress.core.models import SiteSettings
    settings = SiteSettings.load()
    issues = []
    seen = set()

    def add(level, what, where, **extra):
        key = (level, what, where.get('source'), where.get('section'), where.get('lang'))
        if key not in seen:
            seen.add(key)
            issues.append({'level': level, 'what': what, 'where': where, **extra})

    differing = {}   # (kind, norm) -> {'value', 'ref', 'places': [where]}

    def differs(kind, value, norm, ref, where):
        entry = differing.setdefault((kind, norm), {'value': value, 'ref': ref, 'places': []})
        if where not in entry['places']:
            entry['places'].append(where)

    found = collect()
    phone_ref = {normalise_phone(v) for v in (settings.contact_phone, settings.whatsapp_number) if v}
    email_ref = (settings.contact_email or '').strip().lower()

    # Settings themselves
    for field in ('contact_phone', 'whatsapp_number'):
        value = getattr(settings, field) or ''
        if value and not phone_is_valid(value):
            add('wrong', f'{field.replace("_", " ").capitalize()} "{value}" is not a valid phone number', _settings_where(field))
    if email_ref and not EMAIL_OK_RE.match(email_ref):
        add('wrong', f'Contact email "{email_ref}" is not a valid address', _settings_where('contact_email'))
    maps = (settings.google_maps_embed_url or '').strip()
    if maps and not ('google.com/maps/embed' in maps or 'output=embed' in maps):
        add('wrong', 'The Google Maps URL in Settings is not an embed URL (it must start with '
                     'https://www.google.com/maps/embed), so the map will not show', _settings_where('google_maps_embed_url'))

    for item in found:
        where, value, norm = item['where'], item['value'], item['norm']
        if item['kind'] == 'phone':
            if not phone_is_valid(value):
                add('wrong', f'"{value}" is not a valid phone number', where)
                continue
            shown = PHONE_RE.search(item.get('link_text') or '')
            if item.get('link') and shown and normalise_phone(shown.group()) != norm:
                add('wrong', f'The phone link shows {shown.group().strip()} but dials {value}', where)
            elif phone_ref and norm not in phone_ref:
                differs('Phone', value, norm, settings.contact_phone or settings.whatsapp_number, where)
        elif item['kind'] == 'email':
            if not EMAIL_OK_RE.match(value):
                add('wrong', f'"{value}" is not a valid email address', where)
                continue
            shown = EMAIL_RE.search(item.get('link_text') or '')
            if item.get('link') and shown and shown.group().lower() != norm:
                add('wrong', f'The email link shows {shown.group()} but writes to {value}', where)
            elif email_ref and norm != email_ref:
                differs('Email', value, norm, email_ref, where)
        elif item['kind'] == 'whatsapp' and settings.whatsapp_number:
            if norm != normalise_phone(settings.whatsapp_number):
                differs('WhatsApp link', f'+{norm}', norm, settings.whatsapp_number, where)

    for (kind, _norm), entry in differing.items():
        pages = {}
        for w in entry['places']:
            pages.setdefault(w['source'], set()).add((w.get('lang') or '').upper())
        summary = ', '.join(f'{src} ({"/".join(sorted(l for l in langs if l))})' if any(langs) else src
                            for src, langs in pages.items())
        n = len(entry['places'])
        add('inconsistent', f'{kind} {entry["value"]} differs from Settings ({entry["ref"]}); '
                            f'used in {n} place{"s" if n != 1 else ""}: {summary}',
            entry['places'][0], places=entry['places'])

    domains = {}
    for address in {email_ref, *(i['norm'] for i in found if i['kind'] == 'email')}:
        if address and EMAIL_OK_RE.match(address):
            domains.setdefault(address.split('@')[1], address)
    for domain, address in sorted(domains.items()):
        status = mail_domain_status(domain)
        if status == 'no_mx':
            add('wrong', f'The domain of {address} ({domain}) has no mail server, so emails to it bounce',
                {'source': 'Email domain', 'section': None, 'lang': None})
        elif status == 'unknown':
            add('cant_verify', f'Could not check the mail server of {domain} (no DNS access)',
                {'source': 'Email domain', 'section': None, 'lang': None})

    sources, web_answer = [], None
    if check_web:
        sources, web_answer = _web_check(settings, phone_ref, add)
    return {'issues': issues, 'sources': sources, 'web_answer': web_answer}


def _web_check(settings, phone_ref, add):
    from djangopress.ai.utils.llm_config import LLMBase
    lang = settings.get_default_language() if settings else 'pt'
    name = settings.get_site_name(lang) if hasattr(settings, 'get_site_name') else ''
    address = (settings.contact_address_i18n or {}).get(lang) or next(iter((settings.contact_address_i18n or {}).values()), '')
    query = f'{name} {address} telefone morada contacto'.strip()
    where = {'source': 'Web', 'section': None, 'lang': None}
    try:
        found = LLMBase().web_search(query)
    except Exception as e:
        add('cant_verify', f'Web search failed: {e}', where)
        return [], None
    text, sources = found.get('text') or '', found.get('sources') or []
    for match in PHONE_RE.finditer(text):
        norm = normalise_phone(match.group())
        if 9 <= len(norm) <= 15 and phone_ref and norm not in phone_ref:
            add('inconsistent', f'The web lists the phone {match.group().strip()}; the site has {settings.contact_phone}',
                where, sources=sources)
    return sources, text
