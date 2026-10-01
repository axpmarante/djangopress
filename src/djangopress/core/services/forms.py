"""FormService — dynamic form management."""

import logging
from djangopress.core.models import DynamicForm, FormSubmission

logger = logging.getLogger(__name__)


class FormService:

    @staticmethod
    def list():
        """List all dynamic forms with submission counts."""
        forms = DynamicForm.objects.all()
        data = []
        for f in forms:
            data.append({
                'id': f.id,
                'name': f.name,
                'slug': f.slug,
                'notification_email': f.notification_email,
                'is_active': f.is_active,
                'submission_count': f.submissions.count(),
            })
        return {'success': True, 'forms': data, 'message': f'{len(data)} forms found'}

    @staticmethod
    def create(name, slug, notification_email='', fields_schema=None,
               success_message_i18n=None, is_active=True):
        """Create a dynamic form."""
        if not name or not slug:
            return {'success': False, 'error': 'Missing name or slug'}

        if DynamicForm.objects.filter(slug=slug).exists():
            return {'success': False, 'error': f'Form with slug "{slug}" already exists'}

        form = DynamicForm.objects.create(
            name=name,
            slug=slug,
            notification_email=notification_email,
            fields_schema=fields_schema or [],
            success_message_i18n=success_message_i18n or {},
            is_active=is_active,
        )
        return {
            'success': True,
            'form': form,
            'message': f'Created form "{name}" (slug: {slug}). Action URL: /forms/{slug}/submit/',
        }

    @staticmethod
    def update(form_id=None, slug=None, **kwargs):
        """Update a form. Lookup by form_id or slug."""
        if not form_id and not slug:
            return {'success': False, 'error': 'Provide form_id or slug'}

        try:
            if form_id:
                form = DynamicForm.objects.get(pk=form_id)
            else:
                form = DynamicForm.objects.get(slug=slug)
        except DynamicForm.DoesNotExist:
            return {'success': False, 'error': 'Form not found'}

        updated = []
        for field in ('name', 'notification_email', 'fields_schema', 'success_message_i18n', 'is_active'):
            if kwargs.get(field) is not None:      # None = not given (the assistant passes every key)
                setattr(form, field, kwargs[field])
                updated.append(field)

        if updated:
            form.save()

        return {'success': True, 'form': form, 'message': f'Updated form "{form.name}": {", ".join(updated)}'}

    @staticmethod
    def delete(form_id=None, slug=None):
        """Delete a form and all its submissions."""
        if not form_id and not slug:
            return {'success': False, 'error': 'Provide form_id or slug'}

        try:
            if form_id:
                form = DynamicForm.objects.get(pk=form_id)
            else:
                form = DynamicForm.objects.get(slug=slug)
        except DynamicForm.DoesNotExist:
            return {'success': False, 'error': 'Form not found'}

        name = form.name
        form.delete()
        return {'success': True, 'message': f'Deleted form "{name}" and all its submissions'}

    @staticmethod
    def list_submissions(form_slug=None, limit=10):
        """List recent form submissions."""
        qs = FormSubmission.objects.select_related('form').order_by('-created_at')
        if form_slug:
            qs = qs.filter(form__slug=form_slug)
        submissions = qs[:limit]
        data = []
        for s in submissions:
            data.append({
                'id': s.id,
                'form': s.form.name,
                'data': s.data,
                'is_read': s.is_read,
                'created_at': s.created_at.isoformat(),
            })
        return {'success': True, 'submissions': data, 'message': f'{len(data)} recent submissions'}


def process_submission(form_def, data, lang, ip, user_agent, *, source_page=None, notify_to=None, subject_prefix=''):
    """Validate → save → notify → confirm. The public form view and the assistant's
    test_form share it. notify_to sends both emails only to that address.

    Returns {'errors', 'submission', 'notification_sent', 'confirmation_sent'};
    with errors nothing is saved or sent.
    """
    from djangopress.core.email import send_form_confirmation, send_form_notification

    errors = form_def.validate_submission(data)
    if errors:
        return {'errors': errors, 'submission': None, 'notification_sent': False, 'confirmation_sent': False}
    submission = FormSubmission.objects.create(
        form=form_def, data=data, source_page=source_page, language=lang or '',
        ip_address=ip, user_agent=user_agent or '',
    )
    notified = send_form_notification(form_def, submission, to_override=notify_to, subject_prefix=subject_prefix)
    confirmed = False
    if form_def.send_confirmation_email:
        confirmed = send_form_confirmation(form_def, submission, lang=lang or 'en',
                                           to_override=notify_to, subject_prefix=subject_prefix)
    return {'errors': {}, 'submission': submission, 'notification_sent': notified, 'confirmation_sent': confirmed}
