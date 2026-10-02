"""Three design directions for one section or element, each its own call.

One call that returns three variations has to keep them short and fails as a
whole when one is malformed. Here each direction is a separate generation with
the site's design context, run in parallel; each is design-checked and sent to
the caller as soon as it is ready, and a failed one does not cost the others.
"""
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

from djangopress.ai.design_check import check_and_fix
from djangopress.ai.design_context import build_design_context, render_design_context
from djangopress.ai.services import ContentGenerationService
from djangopress.ai.utils.llm_config import get_ai_model

DIRECTIONS = [
    {'key': 'refined', 'name': 'Close to current',
     'brief': 'Keep the structure and the order of the content. Raise the craft: a clearer type scale, a better '
              'spacing rhythm, and the details this site uses elsewhere (eyebrows, dividers, accents).'},
    {'key': 'bold', 'name': 'Bolder',
     'brief': 'More presence: stronger contrast or a colour band from the site palette, larger display type, '
              'real imagery from the library where it helps. Still unmistakably this site.'},
    {'key': 'layout', 'name': 'New layout',
     'brief': 'A different layout pattern that this site already uses elsewhere (split, cards, editorial list, '
              'feature grid), keeping all the content and its meaning.'},
]
REFINED = {'key': 'next', 'name': 'Refined',
           'brief': 'Apply the request to this version and keep everything else about it.'}


def _generate(page, scope, target, instructions, direction, *, lang, history, base_html, images, block, model):
    from django.db import connection
    try:
        service = ContentGenerationService(model_name=model)
        common = dict(instructions=instructions, conversation_history=history or [], lang=lang, page=page,
                      model_override=model, skip_component_selection=True, base_html=base_html,
                      direction={'name': direction['name'], 'brief': direction['brief']}, design_context=block)
        page_id = getattr(page, 'pk', None)
        if scope == 'element':
            result = service.refine_element_only(page_id=page_id, selector=target, **common)
        else:
            result = service.refine_section_only(page_id=page_id, section_name=target, reference_images=images,
                                                 **common)
        options = result.get('options') or []
        if not options or not options[0].get('html'):
            raise ValueError('The model returned no HTML')
        return options[0]['html']
    finally:
        connection.close()


def generate_directions(page, scope, target, instructions, *, lang=None, history=None, base_html=None, images=None,
                        context=None, on_option=None, is_cancelled=None, keys=None, directions=None, model=None):
    """[{key, name, html, why, notes} | {key, name, error}] in direction order; on_option(item) as each finishes."""
    chosen = directions or [d for d in DIRECTIONS if keys is None or d['key'] in keys]
    if context is None:
        context = build_design_context(page, target if scope == 'section' else None, lang=lang, query=instructions)
    block = render_design_context(context)
    model = model or get_ai_model('refinement_element' if scope == 'element' else 'generation')
    cancelled = is_cancelled or (lambda: False)

    results = {}
    pool = ThreadPoolExecutor(max_workers=len(chosen) or 1)
    try:
        futures = {pool.submit(_generate, page, scope, target, instructions, d, lang=lang, history=history,
                               base_html=base_html, images=images, block=block, model=model): d for d in chosen}
        pending = set(futures)
        while pending and not cancelled():
            done, pending = wait(pending, timeout=0.5, return_when=FIRST_COMPLETED)
            for future in done:
                d = futures[future]
                try:
                    checked = check_and_fix(future.result(), context.get('colors'), context.get('fonts'))
                    item = {'key': d['key'], 'name': d['name'], 'html': checked['html'], 'why': checked['why'],
                            'notes': checked['notes']}
                except Exception as exc:
                    item = {'key': d['key'], 'name': d['name'], 'error': str(exc)}
                if cancelled():
                    break
                results[d['key']] = item
                if on_option:
                    on_option(item)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return [results[d['key']] for d in chosen if d['key'] in results]
