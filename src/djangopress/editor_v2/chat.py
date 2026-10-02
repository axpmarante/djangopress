"""One turn of the editor Chat on a section or an element.

Two kinds of request:
- quick (specific: a colour, a size, a text): the router edits the HTML directly
  and the change is applied at once (Undo covers it);
- explore (open: "more elegant", "redesign", "3 options"): three design
  directions, each built from the site's design context, streamed one by one.
  Nothing is saved until the operator applies one.

A follow-up on an option that was never applied (base_html) makes one new
version of that option. Events go out through emit(event, data).
"""
import re
import unicodedata

from bs4 import BeautifulSoup

from djangopress.ai.design_context import build_design_context, matches_summary
from djangopress.ai.directions import DIRECTIONS, FIT, NEW_SECTION_DIRECTIONS, REFINED, generate_directions
from djangopress.editor_v2 import ai_apply
from djangopress.site_assistant import cancel

EXPLORE_RE = re.compile(
    r'eleg|redesenh|redesign|refaz|rethink|repens|modern|ideia|idea|\bopc|option|proposta|direc|direction|'
    r'diferente|different|inspir|surpreend|surprise|criativ|creative|premium|sofistic|sophistic|luxo|luxur|'
    r'layout|\b3\b|\btres\b|\bthree\b|variac|variation|alternativ')
QUICK_RE = re.compile(
    r'\bcor\b|\bcores\b|colou?r|dourad|\bgold|vermelh|\bred\b|azul|\bblue|verde|green|\bpret|black|branc|white|'
    r'maior|menor|bigger|smaller|larger|tamanho|\bsize|padding|margin|espac|spacing|negrito|\bbold\b|italic|'
    r'sublinh|underline|centr|center|alinh|align|arredond|rounded|sombra|shadow|fonte|\bfont|esconde|\bhide|'
    r'\btexto\b|\btext\b|troca|replace')
QUICK_ONE = {'key': 'quick', 'name': 'Edit', 'brief': 'Do exactly what was asked and change nothing else.'}
LABELS = {
    'routing': 'Reading the request',
    'context': "Reading the site's style",
    'directions': 'Designing 3 directions',
    'refine': 'Making a new version of this option',
    'fit': "Fitting it to this site's design",
    'generate': 'Making the change',
    'check': "Checking against the site's palette and fonts",
    'apply': 'Saving and updating the other languages',
}


def _plain(text):
    text = unicodedata.normalize('NFKD', (text or '').lower())
    return ''.join(ch for ch in text if not unicodedata.combining(ch))


def classify_intent(text):
    """'explore' | 'quick' | None (the router decides). Explore wins when both match."""
    plain = _plain(text)
    if EXPLORE_RE.search(plain):
        return 'explore'
    if QUICK_RE.search(plain):
        return 'quick'
    return None


def _section_name(page, scope, target, lang):
    if scope != 'element':
        return target
    copies = getattr(page, 'html_content_i18n', None) or {}
    html = copies.get(lang) or next(iter(copies.values()), '') or ''
    el = BeautifulSoup(html, 'html.parser').select_one(target)
    section = el.find_parent('section', attrs={'data-section': True}) if el is not None else None
    return section.get('data-section') if section is not None else None


def _apply(page, scope, target, html, lang, user):
    if scope == 'element':
        return ai_apply.apply_element_html(page, target, html, lang, user=user)
    return ai_apply.apply_section_html(page, html, lang, section_name=target, user=user)


def run_turn(page, *, scope, target, instructions, mode='auto', lang=None, history=None, base_html=None,
             images=None, user=None, run_id=None, emit):
    """Returns {'mode', 'message', 'cancelled'}; the caller sends 'complete'."""
    def step(key, state, label=None):
        emit('step', {'key': key, 'label': label or LABELS.get(key, key), 'state': state})

    def cancelled():
        return cancel.is_cancelled(run_id)

    def stopped(resolved):
        return {'mode': resolved, 'message': 'Stopped.', 'cancelled': True}

    def emit_option(item):
        emit('option' if 'html' in item else 'option_failed', item)

    requested = mode if mode in ('quick', 'explore') else 'auto'
    resolved = requested if requested != 'auto' else (classify_intent(instructions) or ('explore' if images else 'quick'))
    if scope == 'new':
        resolved = 'explore'                 # a new section is always designed, never a quick edit
    section = None if scope == 'new' else _section_name(page, scope, target, lang)
    if cancelled():
        return stopped(resolved)

    def context():
        step('context', 'running')
        ctx = build_design_context(page, section, lang=lang, query=instructions)
        emit('context', {'matches': matches_summary(ctx)})
        step('context', 'done')
        return ctx

    if base_html:
        kind = 'fit' if mode == 'fit' else 'refine'
        ctx = context()
        step(kind, 'running')
        items = generate_directions(page, scope, target, instructions, lang=lang, history=history, base_html=base_html,
                                    images=images, context=ctx, on_option=emit_option, is_cancelled=cancelled,
                                    directions=[FIT if kind == 'fit' else REFINED])
        step(kind, 'done')
        if cancelled():
            return stopped(kind)
        ok = [i for i in items if 'html' in i]
        if kind == 'fit':
            return {'mode': 'fit', 'cancelled': False,
                    'message': "Here it is in this site's style." if ok else "Couldn't fit it to this site."}
        return {'mode': 'refine', 'cancelled': False,
                'message': 'Here is a new version of that option.' if ok else "Couldn't make a new version."}

    if resolved == 'quick':
        from djangopress.ai.refinement_agent.agent import RefinementAgent
        step('routing', 'running')
        routed = RefinementAgent().handle(instructions, scope, target, page, conversation_history=history, lang=lang,
                                          delegate=False)
        step('routing', 'done')
        if cancelled():
            return stopped('quick')
        if not routed.get('delegate'):
            step('apply', 'running')
            saved = _apply(page, scope, target, routed['options'][0]['html'], lang, user)
            step('apply', 'done')
            message = routed.get('assistant_message') or 'Done.'
            emit('applied', {'html': saved['html'], 'scope': scope, 'target': target, 'message': message,
                             'translated': saved['translated_languages'], 'untranslated': saved['untranslated_languages']})
            return {'mode': 'quick', 'message': message, 'cancelled': False}
        if requested == 'quick':
            ctx = context()
            step('generate', 'running')
            items = generate_directions(page, scope, target, instructions, lang=lang, history=history, images=images,
                                        context=ctx, is_cancelled=cancelled, directions=[QUICK_ONE])
            step('generate', 'done')
            if cancelled():
                return stopped('quick')
            if not items or 'html' not in items[0]:
                raise ValueError(items[0]['error'] if items else "Couldn't make the change")
            step('apply', 'running')
            saved = _apply(page, scope, target, items[0]['html'], lang, user)
            step('apply', 'done')
            emit('applied', {'html': saved['html'], 'scope': scope, 'target': target, 'message': 'Done.',
                             'translated': saved['translated_languages'], 'untranslated': saved['untranslated_languages']})
            return {'mode': 'quick', 'message': 'Done.', 'cancelled': False}
        step('routing', 'done', 'Needs a new design — 3 directions')
        resolved = 'explore'

    ctx = context()
    step('directions', 'running')
    items = generate_directions(page, scope, target, instructions, lang=lang, history=history, images=images,
                                context=ctx, on_option=emit_option, is_cancelled=cancelled)
    step('directions', 'done')
    if cancelled():
        return stopped('explore')
    step('check', 'done')
    names = {d['key']: d['name'] for d in (NEW_SECTION_DIRECTIONS if scope == 'new' else DIRECTIONS)}
    made = [f"{chr(65 + n)} {names.get(i['key'], i['key'])}" for n, i in enumerate(items) if 'html' in i]
    subject = 'a new section' if scope == 'new' else (section or 'this element')
    message = (f"Three directions for {subject}: " + ', '.join(made) + '.') if made \
        else "Couldn't make any direction this time."
    return {'mode': 'explore', 'message': message, 'cancelled': False}
