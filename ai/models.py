from django.db import models
from django.conf import settings
from django.utils import timezone


class RefinementSession(models.Model):
    """A conversational refinement session for a page."""
    page = models.ForeignKey(
        'core.Page',
        on_delete=models.CASCADE,
        related_name='refinement_sessions'
    )
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
        return f"Session #{self.pk} — {self.title or 'Untitled'} (page {self.page_id})"

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
