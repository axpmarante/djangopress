"""Endpoints of the editor Chat: one streamed turn, and Stop."""
import json
import queue
import threading

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from djangopress.ai.design_context import build_design_context, matches_summary
from djangopress.ai.utils.sse import sse_event, sse_response
from djangopress.core.decorators import superuser_required
from djangopress.editor_v2 import chat
from djangopress.editor_v2.api_views import _detect_language_from_request, _get_editable_object, _get_or_create_session
from djangopress.site_assistant import cancel

MAX_IMAGES = 5
MAX_IMAGE_BYTES = 10 * 1024 * 1024
TURN_TIMEOUT = 300


def _error(message):
    return sse_response(iter([sse_event({'error': message}, event='error')]))


def _start_worker(fn):
    def run():
        from django.db import connection
        try:
            fn()
        finally:
            connection.close()
    threading.Thread(target=run, daemon=True).start()


def _read_request(request):
    """(data, images) from a JSON body or a multipart form (payload + reference_images)."""
    if request.content_type.startswith('multipart/'):
        data = json.loads(request.POST.get('payload') or '{}')
        files = request.FILES.getlist('reference_images')
        if len(files) > MAX_IMAGES:
            raise ValueError(f'At most {MAX_IMAGES} reference images')
        images = []
        for f in files:
            if not (f.content_type or '').startswith('image/'):
                raise ValueError(f'{f.name} is not an image')
            if f.size > MAX_IMAGE_BYTES:
                raise ValueError(f'{f.name} is larger than 10 MB')
            images.append({'bytes': f.read(), 'mime_type': f.content_type})
        return data, images
    return json.loads(request.body or b'{}'), []


@superuser_required
@require_http_methods(["POST"])
def chat_stream(request):
    """POST /editor-v2/api/chat/stream/ — events: step, context, option, option_failed, applied, complete, error."""
    try:
        data, images = _read_request(request)
    except json.JSONDecodeError:
        return _error('Invalid JSON')
    except ValueError as e:
        return _error(str(e))

    instructions = (data.get('instructions') or '').strip()
    scope = data.get('scope') if data.get('scope') in ('section', 'element') else 'section'
    target = data.get('selector') if scope == 'element' else data.get('section_name')
    if not instructions:
        return _error('Missing instructions')
    if not target:
        return _error('Pick a section or an element first')
    if images and scope == 'element':
        return _error('Reference images work on a whole section: select the section and send again')
    try:
        page = _get_editable_object(data)
    except Exception:
        page = None
    if page is None:
        return _error('Page or editable object not found')

    lang = _detect_language_from_request(request, data)
    label = 'element' if scope == 'element' else target
    session = _get_or_create_session(page, data.get('session_id'), f'[{label}] {instructions[:60]}', request.user)
    session.add_user_message(instructions, reference_images_count=len(images))
    session.save()
    run_id = data.get('run_id')
    q = queue.Queue()
    done = object()

    def worker():
        try:
            result = chat.run_turn(
                page, scope=scope, target=target, instructions=instructions, mode=data.get('mode') or 'auto',
                lang=lang, history=data.get('conversation_history') or [], base_html=data.get('base_html') or None,
                images=images or None, user=request.user, run_id=run_id, emit=lambda e, d: q.put((e, d)))
            session.add_assistant_message(result['message'], [label])
            session.save()
            q.put(('complete', {'success': True, 'session_id': session.id, **result}))
        except Exception as e:
            import traceback
            traceback.print_exc()
            q.put(('error', {'error': str(e), 'session_id': session.id}))
        finally:
            cancel.clear(run_id)
            q.put(done)

    _start_worker(worker)

    def stream():
        while True:
            try:
                item = q.get(timeout=TURN_TIMEOUT)
            except queue.Empty:
                yield sse_event({'error': 'The AI took too long'}, event='error')
                return
            if item is done:
                return
            event, payload = item
            yield sse_event(payload, event=event)

    return sse_response(stream())


@superuser_required
@require_http_methods(["POST"])
def chat_cancel(request):
    """Stop a running Chat turn; directions already shown stay."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    if not cancel.request_cancel(data.get('run_id')):
        return JsonResponse({'success': False, 'error': 'Invalid run_id'}, status=400)
    return JsonResponse({'success': True})


@superuser_required
@require_http_methods(["GET"])
def chat_context(request):
    """The "Matches" line before any request: palette, fonts and reference sections for this target."""
    data = request.GET
    try:
        page = _get_editable_object(data)
    except Exception:
        page = None
    if page is None:
        return JsonResponse({'success': False, 'error': 'Page or editable object not found'}, status=400)
    lang = _detect_language_from_request(request, data)
    scope = 'element' if data.get('scope') == 'element' else 'section'
    target = data.get('selector') if scope == 'element' else data.get('section_name')
    section = chat._section_name(page, scope, target, lang) if target else None
    return JsonResponse({'success': True, 'matches': matches_summary(build_design_context(page, section, lang=lang))})
