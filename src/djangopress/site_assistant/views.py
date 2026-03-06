import json

from djangopress.core.decorators import superuser_required, SuperuserRequiredMixin
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.views import View
from django.views.decorators.http import require_http_methods

from djangopress.ai.utils.llm_config import MODEL_CONFIG, get_ai_model
from djangopress.core.models import Page

from .models import AssistantSession
from .services import AssistantService


class AssistantPageView(SuperuserRequiredMixin, View):
    """Render the Site Assistant chat UI."""

    def get(self, request):
        session_id = request.GET.get('session')
        session = None
        if session_id:
            try:
                session = AssistantSession.objects.get(pk=session_id, created_by=request.user)
            except AssistantSession.DoesNotExist:
                pass

        pages = Page.objects.all().order_by('sort_order', 'created_at')
        sessions = AssistantSession.objects.filter(created_by=request.user)[:20]
        models = list(MODEL_CONFIG.keys())

        return render(request, 'site_assistant/assistant.html', {
            'current_session': session,
            'pages': pages,
            'sessions': sessions,
            'models': models,
            'default_model': get_ai_model('assistant_executor'),
        })


@superuser_required
@require_http_methods(["POST"])
def chat_api(request):
    """Handle a chat message: router + native FC executor."""
    # Support both multipart (with images) and JSON body
    reference_images = []
    if request.content_type and 'multipart' in request.content_type:
        message = request.POST.get('message', '').strip()
        session_id = request.POST.get('session_id') or None
        model = request.POST.get('model') or get_ai_model('assistant_executor')
        active_page_id = request.POST.get('active_page_id') or None
        if active_page_id:
            active_page_id = int(active_page_id)
        for f in request.FILES.getlist('reference_images'):
            reference_images.append({'bytes': f.read(), 'mime_type': f.content_type})
    else:
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
        message = data.get('message', '').strip()
        session_id = data.get('session_id')
        model = data.get('model') or get_ai_model('assistant_executor')
        active_page_id = data.get('active_page_id')

    if not message:
        return JsonResponse({'success': False, 'error': 'Empty message'}, status=400)

    # Get or create session
    if session_id:
        try:
            session = AssistantSession.objects.get(pk=session_id, created_by=request.user)
        except AssistantSession.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Session not found'}, status=404)
    else:
        session = AssistantSession.objects.create(
            created_by=request.user,
            model_used=model,
        )

    # Update model if changed
    if session.model_used != model:
        session.model_used = model
        session.save(update_fields=['model_used'])

    # Update active page if specified
    if active_page_id:
        try:
            page = Page.objects.get(pk=active_page_id)
            session.set_active_page(page)
        except Page.DoesNotExist:
            pass
    elif active_page_id == 0 or active_page_id == '':
        session.set_active_page(None)

    # Process message
    service = AssistantService(session)
    result = service.handle_message(message, user=request.user, reference_images=reference_images or None)

    return JsonResponse({
        'success': True,
        'session_id': session.id,
        'response': result['response'],
        'actions': result['actions'],
        'steps': result.get('steps', []),
        'set_active_page': result.get('set_active_page'),
    })


@superuser_required
@require_http_methods(["GET"])
def sessions_api(request):
    """List user's sessions."""
    sessions = AssistantSession.objects.filter(created_by=request.user)[:30]
    data = []
    for s in sessions:
        data.append({
            'id': s.id,
            'title': s.title or f'Session #{s.id}',
            'active_page_id': s.active_page_id,
            'model_used': s.model_used,
            'message_count': len(s.messages),
            'updated_at': s.updated_at.isoformat(),
        })
    return JsonResponse({'success': True, 'sessions': data})


@superuser_required
@require_http_methods(["GET"])
def session_detail_api(request, session_id):
    """Get full session data including messages."""
    session = get_object_or_404(AssistantSession, pk=session_id, created_by=request.user)
    return JsonResponse({
        'success': True,
        'session': {
            'id': session.id,
            'title': session.title or f'Session #{session.id}',
            'messages': session.messages,
            'active_page_id': session.active_page_id,
            'model_used': session.model_used,
            'updated_at': session.updated_at.isoformat(),
        },
    })
