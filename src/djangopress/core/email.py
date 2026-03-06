"""Email helpers for dynamic form submissions."""

import logging

from django.core.mail import EmailMessage
from django.conf import settings

logger = logging.getLogger(__name__)


def send_form_notification(form_def, submission):
    """Send notification email to site owner with submission data."""
    to_email = form_def.get_notification_email()
    if not to_email:
        logger.warning(f"No notification email for form '{form_def.name}', skipping.")
        return False

    # Build field lines with labels
    lines = []
    for item in submission.get_display_fields():
        value = item['value']
        if isinstance(value, bool):
            value = 'Yes' if value else 'No'
        lines.append(f"{item['label']}: {value}")

    body = f"New submission to \"{form_def.name}\"\n\n" + "\n".join(lines)

    if submission.language:
        body += f"\n\nLanguage: {submission.language}"
    if submission.ip_address:
        body += f"\nIP: {submission.ip_address}"

    # Reply-to from submitter's email field
    reply_to_field = form_def.get_reply_to_field()
    reply_to = submission.data.get(reply_to_field, '')
    reply_to_list = [reply_to] if reply_to else []

    try:
        email = EmailMessage(
            subject=f"[{form_def.name}] New submission",
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[to_email],
            reply_to=reply_to_list,
        )
        email.send(fail_silently=False)
        submission.notification_sent = True
        submission.save(update_fields=['notification_sent'])
        return True
    except Exception as e:
        logger.error(f"Failed to send form notification for '{form_def.name}': {e}")
        return False


def send_form_confirmation(form_def, submission, lang='en'):
    """Send auto-reply confirmation to the submitter."""
    if not form_def.send_confirmation_email:
        return False

    reply_to_field = form_def.get_reply_to_field()
    to_email = submission.data.get(reply_to_field, '')
    if not to_email:
        logger.warning(f"No submitter email found in field '{reply_to_field}', skipping confirmation.")
        return False

    subject_i18n = form_def.confirmation_subject_i18n or {}
    body_i18n = form_def.confirmation_body_i18n or {}

    subject = subject_i18n.get(lang, subject_i18n.get('en', f'Confirmation: {form_def.name}'))
    body = body_i18n.get(lang, body_i18n.get('en', 'Thank you for your submission.'))

    try:
        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[to_email],
        )
        email.send(fail_silently=False)
        return True
    except Exception as e:
        logger.error(f"Failed to send confirmation email for '{form_def.name}': {e}")
        return False
