"""The image picker's Unsplash tab: search (key stays server-side) and import
the picked photo into the media library, credited, so it is used like any
library image."""
import json

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from djangopress.ai.utils import unsplash
from djangopress.core.decorators import editor_required


def _body(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


@editor_required
@require_http_methods(["POST"])
def unsplash_search(request):
    data = _body(request)
    query = ((data or {}).get('query') or '').strip()
    if not unsplash.is_configured():
        return JsonResponse({'success': False, 'error': 'Unsplash is not configured'}, status=400)
    if not query:
        return JsonResponse({'success': False, 'error': 'Type what the photo should show'}, status=400)
    results = unsplash.search_photos(query, per_page=18, orientation=(data or {}).get('orientation') or None)
    return JsonResponse({'success': True, 'results': results})


@editor_required
@require_http_methods(["POST"])
def unsplash_import(request):
    from djangopress.site_assistant import photos
    photo_id = str((_body(request) or {}).get('id') or '').strip()
    if not photo_id:
        return JsonResponse({'success': False, 'error': 'Missing photo id'}, status=400)
    try:
        image = photos.ensure_library_image(f'unsplash:{photo_id}')
    except ValueError as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    return JsonResponse({'success': True, 'image': {
        'id': image.id,
        'url': image.image.url,
        'title': next(iter((image.title_i18n or {}).values()), ''),
        'alt_text': next(iter((image.alt_text_i18n or {}).values()), ''),
    }})
