from django.contrib import admin
from .models import Conversation, Message, ChatVELExecution


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ['created_at', 'role', 'content', 'input_tokens', 'output_tokens', 'has_vel_commands']
    fields = ['role', 'content', 'input_tokens', 'output_tokens', 'has_vel_commands', 'created_at']
    ordering = ['created_at']

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'user', 'context_type', 'model_name', 'get_message_count', 'total_input_tokens', 'total_output_tokens', 'last_message_at', 'is_archived']
    list_filter = ['context_type', 'model_name', 'is_archived', 'created_at']
    search_fields = ['title', 'user__username', 'user__email']
    readonly_fields = ['created_at', 'updated_at', 'total_input_tokens', 'total_output_tokens', 'last_message_at']
    inlines = [MessageInline]

    fieldsets = (
        (None, {
            'fields': ('user', 'title', 'model_name')
        }),
        ('Context', {
            'fields': ('context_type', 'context_id')
        }),
        ('Stats', {
            'fields': ('total_input_tokens', 'total_output_tokens', 'last_message_at')
        }),
        ('Status', {
            'fields': ('is_archived', 'created_at', 'updated_at')
        }),
    )


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'conversation', 'role', 'content_preview', 'input_tokens', 'output_tokens', 'has_vel_commands', 'created_at']
    list_filter = ['role', 'has_vel_commands', 'is_error', 'created_at']
    search_fields = ['content', 'conversation__title']
    readonly_fields = ['created_at', 'updated_at']

    def content_preview(self, obj):
        return obj.content[:100] + "..." if len(obj.content) > 100 else obj.content
    content_preview.short_description = "Content"


@admin.register(ChatVELExecution)
class ChatVELExecutionAdmin(admin.ModelAdmin):
    list_display = ['id', 'message', 'action', 'status', 'requires_confirmation', 'confirmed', 'created_at']
    list_filter = ['action', 'status', 'requires_confirmation', 'confirmed', 'created_at']
    search_fields = ['action', 'audit_id', 'result_summary']
    readonly_fields = ['created_at', 'updated_at', 'confirmed_at']
