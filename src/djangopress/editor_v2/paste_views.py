"""Endpoints for pasting a section copied from another DjangoPress site (see paste.py)."""
import json

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from djangopress.core.decorators import superuser_required
from djangopress.editor_v2 import ai_apply, paste
from djangopress.editor_v2.api_views import _detect_language_from_request, _get_editable_object


def _read(request):
    data = json.loads(request.body or b'{}')
    try:
        page = _get_editable_object(data)
    except Exception:
        page = None
    return data, page


@superuser_required
@require_http_methods(["POST"])
def paste_inspect(request):
    """POST /editor-v2/api/paste-section/inspect/ {html} → {html, name, source, checks, images}."""
    try:
        data, page = _read(request)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    if page is None:
        return JsonResponse({'success': False, 'error': 'Page or editable object not found'}, status=400)
    try:
        result = paste.inspect(page, data.get('html') or '', _detect_language_from_request(request, data))
    except ValueError as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    return JsonResponse({'success': True, **result})


@superuser_required
@require_http_methods(["POST"])
def paste_apply(request):
    """POST /editor-v2/api/paste-section/apply/ {html, insert_after} — copies the images, then inserts."""
    try:
        data, page = _read(request)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    if page is None:
        return JsonResponse({'success': False, 'error': 'Page or editable object not found'}, status=400)
    html = (data.get('html') or '').strip()
    if not html:
        return JsonResponse({'success': False, 'error': 'Missing html'}, status=400)
    lang = _detect_language_from_request(request, data)
    try:
        copied = paste.copy_images(html)
        result = ai_apply.apply_section_html(page, copied['html'], lang, mode='insert',
                                             insert_after=data.get('insert_after') or None, user=request.user)
    except ValueError as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    return JsonResponse({
        'success': True,
        'section_name': result.get('section_name'),
        'html': result.get('html'),
        'translated_languages': result['translated_languages'],
        'untranslated_languages': result['untranslated_languages'],
        'copied_images': copied['copied'],
        'kept_images': copied['kept'],
    })
