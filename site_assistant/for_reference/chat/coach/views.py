"""
Executive Coach Views

URL endpoints for the coach chat interface.
"""

import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import View
from django.http import JsonResponse
from django.utils import timezone

from chat.models import Conversation


class CoachChatView(LoginRequiredMixin, View):
    """Main coach chat page."""

    def get(self, request):
        # Get or create the coach conversation for this user
        # Each user has one coach conversation (persistent)
        conversation, created = Conversation.objects.get_or_create(
            user=request.user,
            context_type='coach',
            is_archived=False,
            defaults={
                'title': 'Executive Coach',
                'chat_version': 'v2',
                'last_message_at': timezone.now(),
            }
        )

        # If we found an archived one, unarchive it
        if not created and conversation.is_archived:
            conversation.is_archived = False
            conversation.save(update_fields=['is_archived'])

        messages = conversation.messages.order_by('created_at')

        # Time-based greeting context
        from .context import fetch_coach_context
        from .prompts import get_time_of_day

        journal_context = fetch_coach_context(request.user)
        time_of_day = get_time_of_day()

        context = {
            'conversation': conversation,
            'messages': messages,
            'journal_context': journal_context,
            'time_of_day': time_of_day,
            'is_coach': True,
        }

        return render(request, 'chat/coach/chat.html', context)


class CoachSendMessageView(LoginRequiredMixin, View):
    """API endpoint for sending messages to the coach."""

    def post(self, request):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        user_content = data.get('content', '').strip()
        if not user_content:
            return JsonResponse({'error': 'Message cannot be empty'}, status=400)

        # Get coach conversation
        conversation = Conversation.objects.filter(
            user=request.user,
            context_type='coach',
            is_archived=False
        ).first()

        if not conversation:
            conversation = Conversation.objects.create(
                user=request.user,
                title='Executive Coach',
                context_type='coach',
                chat_version='v2',
                last_message_at=timezone.now(),
            )

        # Process with coach service
        from .service import CoachService
        from ai_assistant.llm_config import LLMBase

        llm_client = LLMBase()
        service = CoachService(request.user, conversation, llm_client=llm_client)
        response = service.send_message(user_content)

        return JsonResponse({
            'success': response.success,
            'response': response.message,
            'route_type': response.route_type,
            'processing_time_ms': response.processing_time_ms,
            'input_tokens': response.input_tokens,
            'output_tokens': response.output_tokens,
        })


class CoachNewConversationView(LoginRequiredMixin, View):
    """Start a fresh coach conversation."""

    def post(self, request):
        # Archive the old coach conversation if exists
        Conversation.objects.filter(
            user=request.user,
            context_type='coach',
            is_archived=False
        ).update(is_archived=True)

        # Create new coach conversation
        conversation = Conversation.objects.create(
            user=request.user,
            title='Executive Coach',
            context_type='coach',
            chat_version='v2',
            last_message_at=timezone.now(),
        )

        return JsonResponse({
            'success': True,
            'conversation_id': conversation.id,
            'redirect_url': '/chat/coach/',
        })


class CoachMessagesView(LoginRequiredMixin, View):
    """API endpoint for fetching messages (for refresh/polling)."""

    def get(self, request):
        conversation = Conversation.objects.filter(
            user=request.user,
            context_type='coach',
            is_archived=False
        ).first()

        if not conversation:
            return JsonResponse({'messages': [], 'total_count': 0})

        after_id = request.GET.get('after')
        messages = conversation.messages.all()
        if after_id:
            messages = messages.filter(id__gt=int(after_id))

        return JsonResponse({
            'messages': [
                {
                    'id': m.id,
                    'role': m.role,
                    'content': m.content,
                    'created_at': m.created_at.isoformat(),
                }
                for m in messages.order_by('created_at')
            ],
            'total_count': conversation.messages.count(),
        })
