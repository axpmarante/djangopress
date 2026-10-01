"""
Component panel endpoint — one POST for every slider / gallery operation.
The operation itself lives in editor_v2.component_ops (shared with the site
assistant): checkpointed (undoable) and applied to every language copy.
"""
import json

from bs4 import BeautifulSoup
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from djangopress.core.decorators import editor_required
from djangopress.editor_v2 import components
from djangopress.editor_v2.api_views import _detect_language_from_request, _get_editable_object, _get_page_html
from djangopress.editor_v2.component_ops import LABELS, run_component_op


def _error(message, status=400):
    return JsonResponse({'success': False, 'error': message}, status=status)


@editor_required
@require_http_methods(["POST"])
def component_op(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return _error('Invalid JSON')
    root_sel, kind, op = data.get('root'), data.get('kind'), data.get('op')
    count, args = data.get('count'), data.get('args') or {}
    if not root_sel or kind not in components.KINDS or op not in LABELS \
            or not isinstance(count, int) or not isinstance(args, dict):
        return _error('Missing or invalid root / kind / op / count / args')
    try:
        page = _get_editable_object(data)
    except Exception:
        page = None
    if not page:
        return _error('Page or editable object not found')

    lang = _detect_language_from_request(request, data)
    try:
        outcome = run_component_op(page, root_sel, kind, op, args, lang, request.user, count=count)
    except ValueError as e:
        return _error(str(e))
    if outcome['focus'] is None:
        return _error('This part of the page changed. Reload the page and try again.', status=409)

    html, _lang = _get_page_html(page, lang)
    fresh = components.find_component(BeautifulSoup(html or '', 'html.parser'), root_sel, kind)
    return JsonResponse({
        'success': True,
        'index': outcome['focus'],
        'html': str(fresh) if fresh is not None else None,
        'skipped_languages': outcome['skipped'],
        'translated_languages': outcome['translated'],
        'untranslated_languages': outcome['untranslated'],
        'label': outcome['label'],
        'page_id': page.id,
    })
