import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import View, ListView, DetailView
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.utils import timezone

from .models import Conversation, Message, ChatVELExecution


class ConversationListView(LoginRequiredMixin, ListView):
    """List all conversations for the user"""
    model = Conversation
    template_name = 'chat/list.html'
    context_object_name = 'conversations'

    def get_queryset(self):
        return Conversation.objects.filter(
            user=self.request.user,
            is_archived=False
        ).order_by('-last_message_at', '-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add archived count for UI
        context['archived_count'] = Conversation.objects.filter(
            user=self.request.user,
            is_archived=True
        ).count()
        return context


class NewConversationView(LoginRequiredMixin, View):
    """Create a new conversation"""

    def get(self, request):
        # Support query params for scoped conversations
        context_type = request.GET.get('context_type', 'general')
        context_id = request.GET.get('context_id')

        title = "New Conversation"

        # Generate title based on context
        if context_type == 'project' and context_id:
            from para.models import Project
            try:
                project = Project.objects.get(id=context_id, user=request.user)
                title = f"Chat: {project.name}"
            except Project.DoesNotExist:
                context_type = 'general'
                context_id = None
        elif context_type == 'area' and context_id:
            from para.models import Area
            try:
                area = Area.objects.get(id=context_id, user=request.user)
                title = f"Chat: {area.name}"
            except Area.DoesNotExist:
                context_type = 'general'
                context_id = None

        conversation = Conversation.objects.create(
            user=request.user,
            title=title,
            context_type=context_type,
            context_id=int(context_id) if context_id else None,
            last_message_at=timezone.now(),
        )
        return redirect('chat:detail', pk=conversation.pk)

    def post(self, request):
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            data = {}

        context_type = data.get('context_type', 'general')
        context_id = data.get('context_id')
        title = data.get('title', 'New Conversation')

        conversation = Conversation.objects.create(
            user=request.user,
            title=title,
            context_type=context_type,
            context_id=context_id,
            model_name=data.get('model_name', 'gemini-flash'),
            last_message_at=timezone.now(),
        )

        # Enable V2 if requested
        if data.get('use_v2', False):
            conversation.enable_v2()

        return JsonResponse({
            'id': conversation.id,
            'redirect_url': f'/chat/{conversation.id}/',
            'use_v2': conversation.use_v2,
        })


class ConversationDetailView(LoginRequiredMixin, DetailView):
    """View a specific conversation"""
    model = Conversation
    template_name = 'chat/detail.html'
    context_object_name = 'conversation'

    def get_queryset(self):
        return Conversation.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Sidebar conversations
        context['conversations'] = Conversation.objects.filter(
            user=self.request.user,
            is_archived=False
        ).order_by('-last_message_at', '-created_at')[:15]

        # All messages for this conversation
        context['messages'] = self.object.messages.all()

        # Get pending confirmations
        pending = ChatVELExecution.objects.filter(
            message__conversation=self.object,
            requires_confirmation=True,
            confirmed=False,
            status='confirmation_required'
        ).select_related('message')
        context['pending_confirmations'] = pending

        # Get context object if scoped
        context['context_object'] = self.object.get_context_object()

        # Available models for switching (from llm_config.py MODEL_CONFIG)
        context['available_models'] = [
            ('gemini-flash', 'Gemini 3.0 Flash'),
            ('gemini-lite', 'Gemini 2.5 Lite'),
            ('gemini-pro', 'Gemini 3.0 Pro'),
            ('claude', 'Claude Sonnet 4.5'),
            ('gpt-5.2', 'GPT-5.2'),
            ('gpt-5-mini', 'GPT-5 Mini'),
        ]

        return context


class SendMessageAPI(LoginRequiredMixin, View):
    """API endpoint for sending messages"""

    def post(self, request, pk):
        conversation = get_object_or_404(
            Conversation, pk=pk, user=request.user
        )

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        user_content = data.get('content', '').strip()

        if not user_content:
            return JsonResponse({'error': 'Message cannot be empty'}, status=400)

        # Route based on conversation chat_version
        chat_version = getattr(conversation, 'chat_version', 'v2')

        if chat_version == 'v4':
            # V4 Architecture - Multi-Agent
            from .v4 import ChatServiceV4
            service = ChatServiceV4(request.user, conversation)
            response = service.process(user_content)

            # Convert V4 response to UI format
            result = {
                'success': response.success,
                'response': response.response,
                'route_type': response.route_type.value if hasattr(response.route_type, 'value') else str(response.route_type),
                'steps_executed': response.steps_executed,
                'awaiting_user': response.awaiting_user,
                'processing_time_ms': 0,
            }
            if response.error:
                result['error'] = response.error
            if response.execution_id:
                result['execution_id'] = response.execution_id
            # Add token info
            result['input_tokens'] = response.input_tokens
            result['output_tokens'] = response.output_tokens
            # Add affected entities for UI linking
            if response.affected_entities:
                result['affected_entities'] = response.affected_entities

        elif chat_version == 'v3':
            # V3 Architecture - Agentic Loop
            from .v3.service import ChatServiceV3
            service = ChatServiceV3(conversation)
            response = service.send_message(user_content)

            # Convert V3 response to UI format
            result = {
                'success': response.success,
                'response': response.message,
                'route_type': response.route_type.value if hasattr(response.route_type, 'value') else response.route_type,
                'iterations': response.iterations,
                'processing_time_ms': 0,  # V3 doesn't track this yet
            }
            if response.error:
                result['error'] = response.error
            # Add token info
            result['input_tokens'] = response.input_tokens
            result['output_tokens'] = response.output_tokens

        elif chat_version == 'v2':
            # V2 Architecture (chat_version is now the single source of truth)
            from .v2 import ChatServiceV2
            from ai_assistant.llm_config import LLMBase
            llm_client = LLMBase()
            service = ChatServiceV2(request.user, conversation, llm_client=llm_client)
            response = service.send_message(user_content)

            # Convert V2 response to match V1 format for UI compatibility
            result = {
                'success': response.success,
                'response': response.message,
                'route_type': response.route_type,
                'processing_time_ms': response.processing_time_ms,
            }
            if response.error:
                result['error'] = response.error
            if response.data:
                result['data'] = response.data
        else:
            # V1 Architecture (original)
            from .v1 import ChatService
            service = ChatService(request.user, conversation)
            result = service.send_message(user_content)

        return JsonResponse(result)


class ConfirmActionAPI(LoginRequiredMixin, View):
    """API endpoint for confirming VEL actions"""

    def post(self, request, pk):
        conversation = get_object_or_404(
            Conversation, pk=pk, user=request.user
        )

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        confirmation_token = data.get('token')
        action = data.get('action', 'confirm')  # 'confirm' or 'cancel'

        if not confirmation_token:
            return JsonResponse({'error': 'Token required'}, status=400)

        from .v1 import ChatService
        service = ChatService(request.user, conversation)

        if action == 'confirm':
            result = service.confirm_action(confirmation_token)
        else:
            result = service.cancel_action(confirmation_token)

        return JsonResponse(result)


class MessagesAPI(LoginRequiredMixin, View):
    """API endpoint for fetching messages (for refresh/polling)"""

    def get(self, request, pk):
        conversation = get_object_or_404(
            Conversation, pk=pk, user=request.user
        )

        # Optional: get messages after a certain ID
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
                    'has_vel_commands': m.has_vel_commands,
                    'is_error': m.is_error,
                }
                for m in messages
            ],
            'total_count': conversation.messages.count(),
        })


class UpdateConversationAPI(LoginRequiredMixin, View):
    """API endpoint for updating conversation settings"""

    def post(self, request, pk):
        conversation = get_object_or_404(
            Conversation, pk=pk, user=request.user
        )

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        # Update allowed fields
        if 'title' in data:
            conversation.title = data['title'][:200]
        if 'model_name' in data:
            conversation.model_name = data['model_name']

        # Handle chat_version (new field)
        if 'chat_version' in data:
            version = data['chat_version']
            if version in ['v1', 'v2', 'v3', 'v4']:
                conversation.set_version(version)

        # Handle V2 toggle (legacy, still supported)
        elif 'use_v2' in data:
            if data['use_v2']:
                conversation.enable_v2()
            else:
                conversation.disable_v2()

        conversation.save()

        return JsonResponse({
            'success': True,
            'conversation': {
                'id': conversation.id,
                'title': conversation.title,
                'model_name': conversation.model_name,
                'use_v2': conversation.use_v2,
                'chat_version': conversation.chat_version,
            }
        })


class ArchiveConversationAPI(LoginRequiredMixin, View):
    """Archive a conversation"""

    def post(self, request, pk):
        conversation = get_object_or_404(
            Conversation, pk=pk, user=request.user
        )
        conversation.is_archived = True
        conversation.save(update_fields=['is_archived'])
        return JsonResponse({'success': True})


class UnarchiveConversationAPI(LoginRequiredMixin, View):
    """Unarchive a conversation"""

    def post(self, request, pk):
        conversation = get_object_or_404(
            Conversation, pk=pk, user=request.user
        )
        conversation.is_archived = False
        conversation.save(update_fields=['is_archived'])
        return JsonResponse({'success': True})


class DeleteConversationAPI(LoginRequiredMixin, View):
    """Delete a conversation"""

    def post(self, request, pk):
        conversation = get_object_or_404(
            Conversation, pk=pk, user=request.user
        )
        conversation.delete()
        return JsonResponse({'success': True})


class ArchivedConversationsView(LoginRequiredMixin, ListView):
    """List archived conversations"""
    model = Conversation
    template_name = 'chat/archived.html'
    context_object_name = 'conversations'

    def get_queryset(self):
        return Conversation.objects.filter(
            user=self.request.user,
            is_archived=True
        ).order_by('-last_message_at', '-created_at')
