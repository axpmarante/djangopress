from django.conf import settings
from django.db import models
from django.utils import timezone


class AssistantSession(models.Model):
    title = models.CharField(max_length=200, blank=True, default='')
    messages = models.JSONField(default=list)
    active_page = models.ForeignKey(
        'core.Page', null=True, blank=True, on_delete=models.SET_NULL
    )
    model_used = models.CharField(max_length=50, default='gemini-flash')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return self.title or f'Session #{self.pk}'

    def add_message(self, role, content, actions=None):
        msg = {
            'role': role,
            'content': content,
            'timestamp': timezone.now().isoformat(),
        }
        if actions:
            msg['actions'] = actions
        self.messages.append(msg)
        self.save(update_fields=['messages', 'updated_at'])
        return msg

    def get_history_for_prompt(self, max_turns=10):
        """Return last N completed turns, compacted for prompt injection."""
        recent = self.messages[-(max_turns * 2):]
        lines = []
        for msg in recent:
            role = msg['role']
            content = msg['content']
            if role == 'user':
                lines.append(f'User: {content}')
            elif role == 'assistant':
                action_summary = ''
                if msg.get('actions'):
                    tools = [a.get('tool', '?') for a in msg['actions']]
                    action_summary = f' [tools: {", ".join(tools)}]'
                lines.append(f'Assistant: {content}{action_summary}')
        return '\n'.join(lines)

    def set_active_page(self, page):
        self.active_page = page
        self.save(update_fields=['active_page', 'updated_at'])
