"""
Run the in-site AI layout cases (docs/evals/2026-10-01-ai-design-cases.md)
against the demo site, through the same endpoints the editor and the Home chat
call. Restores the demo database from a snapshot before every case.

Usage (from the demo site directory, with its dev server running):

    EVAL_OUT=/tmp/ai-eval/baseline EVAL_CASES=N1,N2   # optional; default: all
    EVAL_SITE_URL=http://localhost:8134                # demo dev server
    .venv/bin/python manage.py shell < ../djangopress/docs/evals/run_ai_design_cases.py

Writes <EVAL_OUT>/results.json, <EVAL_OUT>/index.html and screenshots.
Refuses to run on anything but the demo-ai-lab site.
"""
import html as html_lib
import json
import os
import re
import sqlite3
import subprocess
import time
from pathlib import Path

from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connections
from django.test import Client

from djangopress.ai.models import AICallLog
from djangopress.core.management.commands.check_site import SiteChecker
from djangopress.core.models import Page
from djangopress.editor_v2 import components

DB = Path('db.sqlite3').resolve()
if DB.parent.name != 'demo-ai-lab':
    raise SystemExit(f'Evals only run on the demo-ai-lab site, not {DB.parent.name}')

OUT = Path(os.environ.get('EVAL_OUT', '/tmp/ai-eval/run')).resolve()
OUT.mkdir(parents=True, exist_ok=True)
SITE_URL = os.environ.get('EVAL_SITE_URL', 'http://localhost:8134').rstrip('/')
ONLY = [c.strip() for c in os.environ.get('EVAL_CASES', '').split(',') if c.strip()]
SNAPSHOT = OUT / 'snapshot.sqlite3'
SHOTS = OUT / 'shots'
SHOTS.mkdir(exist_ok=True)

# --- the cases ------------------------------------------------------------------
# kind: refine (editor, section) · element (editor, element) · create (editor, new
# section) · assistant (Home chat). `apply`: which option the operator applies.

def R(page, section, text, apply=0):
    return {'kind': 'refine', 'page': page, 'section': section, 'text': text, 'apply': apply}

def E(page, section, element, text):
    return {'kind': 'element', 'page': page, 'section': section, 'element': element, 'text': text, 'apply': 0}

def C(page, after, text):
    return {'kind': 'create', 'page': page, 'after': after, 'text': text, 'apply': 0}

def A(text):
    return {'kind': 'assistant', 'text': text}

CASES = {
    'N1': [R('home', 'conceito', 'Passa esta secção para duas colunas: texto à esquerda, foto à direita. No telemóvel a foto fica por cima.')],
    'N2': [R('home', 'testemunhos', 'Torna os testemunhos mais elegantes: aspas grandes, fundo creme e o nome do autor mais discreto.')],
    'N3': [C('home', 'carta', 'Acrescenta uma secção com o horário e o mapa (Google Maps), no estilo do resto do site.')],
    'N4': [C('proposta-2', 'chef', 'Acrescenta uma galeria de 6 fotos de pratos da biblioteca de imagens, que abram em grande ao clicar.')],
    'N5': [E('reservas', 'reservas-hero', 'a', 'Dá mais destaque a este botão, na cor principal da marca.')],
    'N6': [R('proposta-1', 'pilares', 'Simplifica: só 3 pilares lado a lado, com um ícone simples cada e menos texto.')],
    'N7': [R('home', 'fotos', 'No telemóvel esta grelha de fotos fica muito alta. Mostra 2 colunas e fotos mais baixas.')],
    'N8': [A('Na página Reservas, acrescenta uma secção de perguntas frequentes com 5 perguntas sobre reservas de grupos, antes dos contactos.')],
    'N9': [R('proposta-2', 'carta', 'Mostra os pratos da carta em cartões com foto, nome e preço, 3 por linha.')],
    'N10': [C('reservas', 'grupos', 'Acrescenta uma secção com 3 menus de grupo, com o mesmo estilo dos cartões da secção eventos da página inicial.')],
    'C1': [R('proposta-2', 'sala', 'Redesenha esta secção, quero ver 3 propostas.', apply=1),
           R('proposta-2', 'sala', 'Gosto desta, mas com fundo escuro.')],
    'C2': [R('home', 'conceito', 'Títulos com letra serifada grande e um traço dourado por baixo.'),
           R('home', 'chef', 'Aplica o mesmo estilo de título a esta secção.'),
           R('home', 'eventos', 'E nesta também, o mesmo estilo de título.')],
    'C3': [A('Que secções tem a página inicial?'), A('Remove a quinta.')],
    'C4': [A('Põe a foto do topo da página Reservas a ocupar o ecrã inteiro.'),
           A('Não, volta atrás e só aumenta o tamanho do título.')],
    'C5': [A('Muda a cor dos botões.'), A('Em todas as páginas, para o dourado da marca.')],
    'C6': [A("Na página proposta-2, acrescenta uma frase no manifesto: 'Cozinha de mercado desde 2014'."),
           A('E em inglês como ficou?'), A("Muda para 'Market cuisine since 2014'.")],
    'C7': [R('home', 'eventos', 'Quero 3 cartões: casamentos, empresas, aniversários.'),
           R('home', 'eventos', 'Os cartões estão muito altos.'),
           R('home', 'eventos', 'Põe uma foto em cada um, da biblioteca de imagens.')],
    'C8': [A('Para este site prefiro sempre fundos claros e sem sombras.'),
           A('Cria uma secção de newsletter antes do rodapé na página inicial.'),
           A('Agora uma de prémios na proposta-3.')],
    'C9': [A('Na proposta-3, põe a secção de reconhecimento numa faixa horizontal.'),
           A('Já agora, qual é o título SEO dessa página?'),
           A('Volta à faixa do reconhecimento e põe os logótipos a preto e branco.')],
    'C10': [A('Tira a galeria.'), A('Não, a da página proposta-1, não a da página inicial.')],
}

GENERIC_CLASS_RE = re.compile(r'^(?:[a-z]+:)*(?:bg|text|border|from|to|via|ring)-(?:gray|slate|zinc|neutral|stone|blue|indigo|sky|red|green|emerald|yellow|amber|purple|pink)-\d{2,3}$')

# --- database snapshot -------------------------------------------------------------

def _copy(src_path, dst_path):
    connections.close_all()
    src, dst = sqlite3.connect(src_path), sqlite3.connect(dst_path)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()

def take_snapshot():
    if not SNAPSHOT.exists():
        _copy(DB, SNAPSHOT)

def restore():
    _copy(SNAPSHOT, DB)
    cache.clear()

# --- page helpers ------------------------------------------------------------------

def page_by_slug(slug):
    for p in Page.objects.all():
        if (p.slug_i18n or {}).get('pt') == slug:
            return p
    raise LookupError(slug)

def page_path(page):
    slug = (page.slug_i18n or {}).get('pt')
    return '/pt/' if slug == 'home' else f'/pt/{slug}/'

def sections(html):
    soup = BeautifulSoup(html or '', 'html.parser')
    return {s.get('data-section'): s for s in soup.find_all('section')}

def state():
    return {p.id: dict(p.html_content_i18n or {}) for p in Page.objects.all()}

def css_path(el):
    """Editor-style selector from the element's section (nth-child among element siblings)."""
    parts = []
    node = el
    while node is not None and not node.has_attr('data-section'):
        parent = node.parent
        index = [c for c in parent.find_all(True, recursive=False)].index(node) + 1
        parts.insert(0, f'{node.name}:nth-child({index})')
        node = parent
    return f'section[data-section="{node["data-section"]}"] > ' + ' > '.join(parts)

def site_classes(snapshot_state):
    found = set()
    for langs in snapshot_state.values():
        for html in langs.values():
            for el in BeautifulSoup(html or '', 'html.parser').find_all(class_=True):
                found.update(el.get('class', []))
    return found

# --- calls ---------------------------------------------------------------------------

def client_for():
    user = get_user_model().objects.filter(is_superuser=True).order_by('id').first()
    c = Client(HTTP_HOST='localhost')
    c.force_login(user)
    return c

def post(c, url, body, referer):
    return c.post(url, data=json.dumps(body), content_type='application/json', HTTP_REFERER=referer)

def read_sse(response):
    if not getattr(response, 'streaming', False):
        return [('error', {'error': f'HTTP {response.status_code}: {response.content[:300]!r}'})]
    text = b''.join(response.streaming_content).decode('utf-8', 'replace')
    events = []
    for block in text.split('\n\n'):
        name, data = 'message', None
        for line in block.splitlines():
            if line.startswith('event:'):
                name = line[6:].strip()
            elif line.startswith('data:'):
                data = line[5:].strip()
        if data:
            try:
                events.append((name, json.loads(data)))
            except ValueError:
                events.append((name, {'raw': data}))
    return events

def editor_turn(c, turn, history):
    page = page_by_slug(turn['page'])
    referer = f'http://localhost{page_path(page)}?edit=v2'
    record = {'kind': turn['kind'], 'text': turn['text']}
    t0 = time.time()
    if turn['kind'] == 'create':
        res = post(c, '/editor-v2/api/refine-multi/', {
            'page_id': page.id, 'mode': 'create', 'insert_after': turn['after'],
            'instructions': turn['text'], 'conversation_history': history, 'session_id': None,
        }, referer)
        payload = res.json() if res['Content-Type'].startswith('application/json') else {'error': f'HTTP {res.status_code}'}
        if not payload.get('success', bool(payload.get('options'))):
            payload.setdefault('error', payload.get('error') or f'HTTP {res.status_code}')
    else:
        body = {'page_id': page.id, 'scope': 'section', 'instructions': turn['text'],
                'conversation_history': history, 'session_id': None, 'multi_option': True}
        if turn['kind'] == 'element':
            sec = sections(page.html_content_i18n.get('pt'))[turn['section']]
            body.update(scope='element', selector=css_path(sec.find(turn['element'])))
        else:
            body['section_name'] = turn['section']
        events = read_sse(post(c, '/editor-v2/api/refine-multi/stream/', body, referer))
        done = [d for n, d in events if n == 'complete']
        errors = [d for n, d in events if n == 'error']
        payload = done[-1] if done else {'error': (errors[-1].get('error') if errors else 'no complete event')}
    record['seconds'] = round(time.time() - t0, 1)
    options = payload.get('options') or []
    record['options'] = len(options)
    record['assistant_message'] = payload.get('assistant_message', '')
    if payload.get('error') or not options:
        record['error'] = str(payload.get('error') or 'no options returned')[:500]
        return record, None
    chosen = options[min(turn['apply'], len(options) - 1)]['html']
    apply_body = {'page_id': page.id, 'scope': 'element' if turn['kind'] == 'element' else 'section',
                  'section_name': turn.get('section'), 'selector': body.get('selector') if turn['kind'] == 'element' else None,
                  'html': chosen}
    if turn['kind'] == 'create':
        apply_body.update(mode='insert', insert_after=turn['after'], section_name=None)
    res = post(c, '/editor-v2/api/apply-option/', apply_body, referer)
    ok = res.status_code == 200 and res.json().get('success')
    record['applied_option'] = turn['apply'] + 1
    if not ok:
        record['error'] = f'apply-option failed: {res.status_code} {res.content[:300]!r}'
    return record, payload.get('assistant_message', '')

def assistant_turn(c, turn, session_id):
    t0 = time.time()
    body = {'message': turn['text']}
    if session_id:
        body['session_id'] = session_id
    res = post(c, '/site-assistant/api/chat/', body, 'http://localhost/backoffice/')
    record = {'kind': 'assistant', 'text': turn['text'], 'seconds': round(time.time() - t0, 1)}
    data = res.json() if res['Content-Type'].startswith('application/json') else {}
    if not data.get('success'):
        record['error'] = str(data.get('error') or f'HTTP {res.status_code}')[:500]
        return record, session_id
    record['response'] = data.get('response', '')
    record['actions'] = [f"{a.get('tool')}:{'ok' if a.get('success') else 'FAIL'} {str(a.get('message', ''))[:120]}" for a in data.get('actions', [])]
    return record, data.get('session_id')

# --- checks ---------------------------------------------------------------------------

def compare(before, after, classes_before):
    changed, new, removed = [], [], []
    for pid, langs in after.items():
        for lang, html in langs.items():
            b, a = sections(before.get(pid, {}).get(lang)), sections(html)
            for name, sec in a.items():
                if name not in b:
                    new.append((pid, lang, name))
                elif str(sec) != str(b[name]):
                    changed.append((pid, lang, name))
            removed += [(pid, lang, n) for n in b if n not in a]
    touched = {(pid, name) for pid, _, name in changed + new}
    novel, generic = set(), set()
    for pid, name in touched:
        sec = sections(after[pid].get('pt')).get(name)
        if sec is None:
            continue
        for el in [sec] + sec.find_all(class_=True):
            for cls in el.get('class', []):
                if cls not in classes_before:
                    novel.add(cls)
                if GENERIC_CLASS_RE.match(cls):
                    generic.add(cls)
    langs_per_target = {}
    for pid, lang, name in changed + new:
        langs_per_target.setdefault((pid, name), set()).add(lang)
    one_language_only = sorted(f'{Page.objects.get(pk=pid).slug_i18n.get("pt")}›{name} ({",".join(sorted(l))})'
                               for (pid, name), l in langs_per_target.items() if len(l) < 2)
    dup = []
    for pid, langs in after.items():
        for lang, html in langs.items():
            names = [s.get('data-section') for s in BeautifulSoup(html or '', 'html.parser').find_all('section')]
            dup += [f'page {pid} {lang}: {n}' for n in set(names) if names.count(n) > 1]
            dup += [f'page {pid} {lang}: id≠data-section on {s.get("data-section")}' for s in BeautifulSoup(html or '', 'html.parser').find_all('section') if s.get('id') != s.get('data-section')]
    def label(items):
        return sorted({f'{Page.objects.get(pk=pid).slug_i18n.get("pt")}›{name}' for pid, _, name in items})
    return {
        'changed': label(changed), 'new': label(new), 'removed': label(removed),
        'only_one_language': one_language_only, 'section_name_problems': dup[:10],
        'novel_classes': len(novel), 'generic_palette_classes': sorted(generic)[:15],
    }, touched

def site_check_failures():
    checker = SiteChecker(only=['dom-parity', 'sections', 'links', 'components'])
    failures = checker.run()
    return [f"[{f['check']}] {f['message']}" for f in failures] + [f"[{w['check']}] {w['message']}" for w in checker.warnings]

# --- screenshots ----------------------------------------------------------------------

def pw(*args):
    return subprocess.run(['playwright-cli', '-s=eval', *args], capture_output=True, text=True, timeout=120, cwd=OUT)

def screenshot(case_id, touched):
    shots = []
    for pid, name in sorted(touched)[:3]:
        page = Page.objects.get(pk=pid)
        url = SITE_URL + page_path(page)
        for width, height in ((1440, 900), (390, 844)):
            pw('resize', str(width), str(height))
            pw('goto', url)
            pw('eval', f"() => {{ const s = document.querySelector('[data-section=\"{name}\"]'); if (s) s.scrollIntoView({{block: 'start'}}); return !!s; }}")
            time.sleep(1.2)
            fname = f'{case_id}-{page.slug_i18n.get("pt")}-{name}-{width}.png'
            pw('screenshot', f'--filename=shots/{fname}')
            if (SHOTS / fname).exists():
                shots.append(f'shots/{fname}')
    return shots

# --- run --------------------------------------------------------------------------------

def run_case(case_id, turns, classes_before, base_failures):
    restore()
    before = state()
    log_start = AICallLog.objects.order_by('-id').values_list('id', flat=True).first() or 0
    c = client_for()
    records, history, session_id = [], [], None
    for turn in turns:
        if turn['kind'] == 'assistant':
            rec, session_id = assistant_turn(c, turn, session_id)
        else:
            rec, assistant_msg = editor_turn(c, turn, history)
            history += [{'role': 'user', 'content': turn['text']},
                        {'role': 'assistant', 'content': assistant_msg or rec.get('error', '')}]
        records.append(rec)
    after = state()
    checks, touched = compare(before, after, classes_before)
    checks['new_site_check_problems'] = [f for f in site_check_failures() if f not in base_failures][:15]
    logs = AICallLog.objects.filter(id__gt=log_start)
    usage = {'calls': logs.count(),
             'prompt_tokens': sum(l.prompt_tokens for l in logs), 'completion_tokens': sum(l.completion_tokens for l in logs),
             'models': sorted(set(logs.values_list('model_name', flat=True)))}
    shots = screenshot(case_id, touched) if touched else []
    return {'case': case_id, 'turns': records, 'checks': checks, 'usage': usage, 'shots': shots,
            'ok': all('error' not in r for r in records)}

def write_report(results):
    (OUT / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=1))
    esc = html_lib.escape
    rows = []
    for r in results:
        turns = ''.join(
            f"<li><b>{esc(t['text'])}</b> <small>({t.get('seconds')} s)</small>"
            + (f"<div class=err>✕ {esc(t['error'])}</div>" if t.get('error') else '')
            + (f"<div>{esc(t.get('response', '')[:600])}</div>" if t.get('response') else '')
            + (f"<div class=meta>{esc('; '.join(t.get('actions', [])))}</div>" if t.get('actions') else '')
            + (f"<div class=meta>{t.get('options')} options · applied #{t.get('applied_option')}</div>" if t.get('options') else '')
            + '</li>' for t in r['turns'])
        ck = r['checks']
        checks = (f"changed: {esc(', '.join(ck['changed']) or '—')}<br>new: {esc(', '.join(ck['new']) or '—')}"
                  f"<br>removed: {esc(', '.join(ck['removed']) or '—')}"
                  f"<br>only one language: {esc(', '.join(ck['only_one_language']) or '—')}"
                  f"<br>novel classes: {ck['novel_classes']} · generic palette: {esc(', '.join(ck['generic_palette_classes']) or '—')}"
                  f"<br>new site-check problems: {esc('; '.join(ck['new_site_check_problems']) or '—')}"
                  f"<br>section names: {esc('; '.join(ck['section_name_problems']) or 'ok')}")
        imgs = ''.join(f'<img src="{s}" loading="lazy">' for s in r['shots'])
        u = r['usage']
        rows.append(f"<section><h2>{r['case']} {'✓' if r['ok'] else '✕'}</h2><ol>{turns}</ol>"
                    f"<p class=meta>{checks}</p><p class=meta>{u['calls']} AI calls · {u['prompt_tokens']}+{u['completion_tokens']} tokens · {esc(', '.join(u['models']))}</p>"
                    f"<div class=shots>{imgs}</div></section>")
    (OUT / 'index.html').write_text(
        '<!doctype html><meta charset=utf-8><title>AI design eval</title><style>'
        'body{font:14px system-ui;margin:24px;max-width:1500px} section{border-top:1px solid #ddd;padding:12px 0}'
        '.err{color:#b91c1c}.meta{color:#555;font-size:12px}.shots{display:flex;gap:8px;flex-wrap:wrap}'
        '.shots img{max-height:420px;border:1px solid #ccc}</style>'
        f'<h1>AI design eval — {len(results)} cases</h1>' + ''.join(rows))

take_snapshot()
_snap_state = None
restore()
_snap_state = state()
CLASSES_BEFORE = site_classes(_snap_state)
BASE_FAILURES = set(site_check_failures())
pw('open', 'about:blank')
results = []
for case_id, turns in CASES.items():
    if ONLY and case_id not in ONLY:
        continue
    print(f'== {case_id}', flush=True)
    try:
        results.append(run_case(case_id, turns, CLASSES_BEFORE, BASE_FAILURES))
    except Exception as e:  # keep going; record the crash
        results.append({'case': case_id, 'turns': [{'text': '(runner)', 'error': f'{type(e).__name__}: {e}'}],
                        'checks': {'changed': [], 'new': [], 'removed': [], 'only_one_language': [], 'section_name_problems': [],
                                   'novel_classes': 0, 'generic_palette_classes': [], 'new_site_check_problems': []},
                        'usage': {'calls': 0, 'prompt_tokens': 0, 'completion_tokens': 0, 'models': []}, 'shots': [], 'ok': False})
    write_report(results)
restore()
pw('close')
print(f'done: {OUT}/index.html', flush=True)
