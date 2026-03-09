import time
import traceback

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.conf import settings
from django.utils import timezone


ACTION_CHOICES = [
    ('generate_page', 'Generate Page'),
    ('refine_page', 'Refine Page'),
    ('chat_refine', 'Chat Refine'),
    ('refine_section', 'Refine Section'),
    ('refine_header', 'Refine Header'),
    ('refine_footer', 'Refine Footer'),
    ('templatize', 'Templatize'),
    ('generate_metadata', 'Generate Metadata'),
    ('analyze_images', 'Analyze Images'),
    ('analyze_bulk', 'Analyze Bulk Pages'),
    ('generate_design_guide', 'Generate Design Guide'),
    ('suggest_sections', 'Suggest Sections'),
    ('fill_section', 'Fill Section'),
    ('select_components', 'Select Components'),
    ('refine_element', 'Refine Element'),
    ('templatize_v2', 'Templatize V2'),
]


class AICallLog(models.Model):
    """Log of every AI/LLM API call for debugging and analytics."""
    created_at = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=100)
    provider = models.CharField(max_length=20)
    page = models.ForeignKey(
        'core.Page', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ai_call_logs',
    )
    section_name = models.CharField(max_length=100, blank=True, default='')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True,
    )
    system_prompt = models.TextField(blank=True, default='')
    user_prompt = models.TextField(blank=True, default='')
    response_text = models.TextField(blank=True, default='')
    prompt_tokens = models.IntegerField(default=0)
    completion_tokens = models.IntegerField(default=0)
    total_tokens = models.IntegerField(default=0)
    duration_ms = models.IntegerField(default=0)
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True, default='')
    routing_tier = models.CharField(max_length=20, blank=True, default='')
    routing_ms = models.IntegerField(default=0)
    assistant_session = models.ForeignKey(
        'site_assistant.AssistantSession', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ai_call_logs',
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        status = 'OK' if self.success else 'ERR'
        return f"[{status}] {self.action} — {self.model_name} ({self.total_tokens} tok)"


def log_ai_call(action, model_name, provider, system_prompt='', user_prompt='',
                response_text='', prompt_tokens=0, completion_tokens=0,
                total_tokens=0, duration_ms=0, success=True, error_message='',
                page=None, section_name='', user=None,
                routing_tier='', routing_ms=0, assistant_session=None):
    """Log an AI API call to the database."""
    try:
        AICallLog.objects.create(
            action=action,
            model_name=model_name,
            provider=provider,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_text=response_text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            duration_ms=duration_ms,
            success=success,
            error_message=error_message,
            page=page,
            section_name=section_name or '',
            user=user,
            routing_tier=routing_tier,
            routing_ms=routing_ms,
            assistant_session=assistant_session,
        )
    except Exception:
        traceback.print_exc()


class RefinementSession(models.Model):
    """A conversational refinement session for a page."""
    page = models.ForeignKey(
        'core.Page',
        on_delete=models.CASCADE,
        related_name='refinement_sessions',
        null=True, blank=True,
    )
    # Generic FK for any content type (NewsPost, PropertyListing, etc.)
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True, blank=True,
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')

    title = models.CharField(max_length=200, blank=True, default='')
    messages = models.JSONField(default=list)
    model_used = models.CharField(max_length=50, default='gemini-pro')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        target = f"page {self.page_id}" if self.page_id else f"{self.content_type} #{self.object_id}" if self.content_type else "no target"
        return f"Session #{self.pk} — {self.title or 'Untitled'} ({target})"

    def add_user_message(self, content, reference_images_count=0):
        self.messages.append({
            'role': 'user',
            'content': content,
            'timestamp': timezone.now().isoformat(),
            'reference_images_count': reference_images_count,
        })

    def add_assistant_message(self, summary, sections_changed):
        self.messages.append({
            'role': 'assistant',
            'content': summary,
            'timestamp': timezone.now().isoformat(),
            'sections_changed': sections_changed or [],
        })

    def get_history_for_prompt(self):
        """Build a compact history string for injection into the LLM prompt.

        Returns only completed turn pairs (user + assistant), excludes the
        last user message (which becomes the active instruction), and caps
        at the most recent 10 turns.
        """
        pairs = []
        i = 0
        msgs = self.messages
        while i < len(msgs) - 1:
            if msgs[i]['role'] == 'user' and i + 1 < len(msgs) and msgs[i + 1]['role'] == 'assistant':
                pairs.append((msgs[i], msgs[i + 1]))
                i += 2
            else:
                i += 1

        # Cap at last 10 turns
        pairs = pairs[-10:]

        if not pairs:
            return ''

        lines = []
        for idx, (user_msg, asst_msg) in enumerate(pairs, 1):
            instruction = user_msg['content']
            if len(instruction) > 120:
                instruction = instruction[:117] + '...'
            sections = asst_msg.get('sections_changed', [])
            section_info = f" [sections: {', '.join(sections)}]" if sections else ''
            lines.append(f"{idx}. User asked: \"{instruction}\" -> {asst_msg['content']}{section_info}")

        return '\n'.join(lines)


class DesignConsistencyReport(models.Model):
    """Persisted design consistency analysis report."""
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
    )
    custom_rules = models.TextField(blank=True, default='')
    model_used = models.CharField(max_length=50, default='')
    report_data = models.JSONField(default=list)
    summary = models.JSONField(default=dict)
    issue_statuses = models.JSONField(default=dict)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        total = self.summary.get('total_issues', 0)
        return f"Report #{self.pk} — {total} issues ({self.created_at:%Y-%m-%d %H:%M})"

    def get_open_count(self):
        total = self.summary.get('total_issues', 0)
        return total - len(self.issue_statuses)

    def get_ignored_count(self):
        return sum(1 for v in self.issue_statuses.values() if v == 'ignored')

    def get_wont_fix_count(self):
        return sum(1 for v in self.issue_statuses.values() if v == 'wont_fix')
