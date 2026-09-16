"""Screening of concept files and live verification of the imported site (spec §8)."""

import json
import re
import socket
import subprocess
import sys
import time
from io import StringIO
from pathlib import Path

from django.core.management import call_command

from djangopress.core.build.adapter import adapt
from djangopress.core.build.contract import check_contract
from djangopress.core.build.importer import cta_texts_from
from djangopress.core.build.probe import run_probe
from djangopress.core.models import GlobalSection, Page

BLOCKING_KINDS = {'overflow', 'empty-section', 'hidden-content', 'console-error'}
RESIDUE_RE = re.compile(r'unresolved placeholder|leftover data-image-\* attribute')


def is_residue(failure):
    return failure.get('check') == 'images' and bool(RESIDUE_RE.search(failure.get('message', '')))


def _adapt(path, packet):
    return adapt(path.read_text(), lang=packet['site']['default_language'], languages=packet['site']['languages'],
                 image_map=packet['images']['map'], cta_texts=cta_texts_from(packet),
                 contact_phone=packet['facts'].get('phone', ''), site_name=packet['site']['name'])


def _fonts(settings):
    return [f for f in (settings.get('heading_font'), settings.get('body_font')) if f]


def screen_file(path, packet, *, probe=None, widths=(390, 834, 1440)):
    probe = probe or run_probe   # resolved at call time so tests can patch verify.run_probe
    path = Path(path)
    m = re.search(r'concept-([a-z])\.html$', path.name)
    key = m.group(1) if m else path.stem
    result = _adapt(path, packet)
    lang = packet['site']['default_language']
    missing = check_contract(packet, {'page': result.page_html, 'header': result.header_html, 'footer': result.footer_html}, lang) if result.ok else []
    probe_out = probe(path.resolve().as_uri(), widths=widths, cta_texts=cta_texts_from(packet), fonts=_fonts(result.settings)) if result.ok else {'available': True, 'defects': []}
    blocking = [d for d in probe_out['defects'] if d['kind'] in BLOCKING_KINDS]
    return {
        'key': key, 'file': str(path), 'hard_errors': result.errors, 'warnings': result.warnings,
        'defects': probe_out['defects'], 'content_missing': missing, 'probe_available': probe_out['available'],
        'clean': result.ok and not missing and not blocking,
    }


def run_check_site():
    out = StringIO()
    try:
        call_command('check_site', json=True, stdout=out)
    except SystemExit:
        pass
    failures = json.loads(out.getvalue() or '{"failures": []}')['failures']
    return [f for f in failures if not is_residue(f)], sum(1 for f in failures if is_residue(f))


def _port_open(port):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(('127.0.0.1', port)) == 0


def free_port():
    """Bind to an OS-assigned port on 127.0.0.1 and return its number."""
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _start_server(port):
    proc = subprocess.Popen([sys.executable, 'manage.py', 'runserver', f'127.0.0.1:{port}', '--noreload'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        if _port_open(port):
            return proc
        time.sleep(0.5)
    proc.terminate()
    raise RuntimeError(f'dev server did not answer on port {port}')


def ensure_server(port):
    """Start `manage.py runserver` on the given port, or on a free one if `port` is None.

    An explicit port is reused if something already answers there; `port=None` always starts a
    server of our own on a free port, so we never probe a server we did not start. Returns
    `(proc, port)` — `proc` is the Popen to stop, or None if an existing server was reused."""
    if port is None:
        port = free_port()
        return _start_server(port), port
    if _port_open(port):
        return None, port
    return _start_server(port), port


def verify_live(packet, *, port=None, probe=None, screenshot=True, widths=(390, 834, 1440)):
    probe = probe or run_probe
    lang = packet['site']['default_language']
    failures, residue = run_check_site()
    home = next((p for p in Page.objects.all() if (p.slug_i18n or {}).get(lang) == 'home'), None)
    parts = {
        'page': (home.html_content_i18n or {}).get(lang, '') if home else '',
        'header': ((GlobalSection.objects.filter(key='main-header').first() or GlobalSection()).html_template_i18n or {}).get(lang, ''),
        'footer': ((GlobalSection.objects.filter(key='main-footer').first() or GlobalSection()).html_template_i18n or {}).get(lang, ''),
    }
    missing = check_contract(packet, parts, lang)
    proc, port = ensure_server(port)
    try:
        from djangopress.core.models import SiteSettings
        s = SiteSettings.load()
        probe_out = probe(f'http://127.0.0.1:{port}/{lang}/', widths=widths, cta_texts=cta_texts_from(packet),
                          fonts=[s.heading_font.split(',')[0], s.body_font.split(',')[0]],
                          screenshot_path=Path('docs/screenshots/home-390.png') if screenshot else None)
    finally:
        if proc is not None:
            proc.terminate()
    blocking = [d for d in probe_out['defects'] if d['kind'] in BLOCKING_KINDS]
    return {
        'check_site': failures, 'residue': residue, 'content_missing': missing, 'probe': probe_out,
        'screenshot': 'docs/screenshots/home-390.png' if screenshot and probe_out['available'] else None,
        'clean': not failures and not missing and not blocking,
    }
