"""Form webhooks — POST each submission, signed, to the URL set on its DynamicForm.

The visitor never waits for this: process_submission saves the submission as
`pending` and a daemon thread delivers it after the commit. A failed delivery is
retried on the RETRY_DELAYS schedule, with no traffic and no cron: the retry sweep
(core.services.webhook_sweep) runs deliver_due() every 5 minutes in each process
that serves requests; the next submission's thread and `manage.py
deliver_form_webhooks` do it too. 1 initial attempt plus 5 retries, and the 6th
failure (MAX_ATTEMPTS) marks it `failed`. After that only `resend` (or
`deliver_form_webhooks --include-failed`) sends it again.

The receiver verifies X-DjangoPress-Signature = HMAC-SHA256 hex of
"{X-DjangoPress-Timestamp}.{raw body}" with the shared secret: the form's own
webhook_secret, else the FORM_WEBHOOK_SECRET setting (secret_for).
"""

import contextlib
import hashlib
import hmac
import json
import logging
import os
import threading
import urllib.error
import urllib.request
from datetime import timedelta
from urllib.parse import urlparse

from django.conf import settings
from django.db import connection
from django.db.models import Q
from django.utils import timezone

from djangopress.core.models import FormSubmission

logger = logging.getLogger(__name__)

RETRY_DELAYS = (60, 300, 1800, 7200, 43200)   # seconds to wait after the 1st, 2nd... failed attempt
MAX_ATTEMPTS = 6                               # 1 initial attempt + len(RETRY_DELAYS) retries
TIMEOUT = 5                                    # seconds
HONEYPOT_FIELD = 'website_url'                 # same as core.views.form_submit
ERROR_MAX_LENGTH = 500

Status = FormSubmission.WebhookStatus


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is not a delivery: urllib would re-send a redirected POST as a
    GET with no body and report 200."""

    def redirect_request(self, *args, **kwargs):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def _site_host():
    """The public host: the first custom domain, else Railway's RAILWAY_PUBLIC_DOMAIN,
    else the Railway host in ALLOWED_HOSTS (not the '.railway.app' wildcard), else ''."""
    domains = [d for d in getattr(settings, 'CUSTOM_DOMAINS', None) or [] if d]
    if domains:
        return domains[0]
    railway = os.environ.get('RAILWAY_PUBLIC_DOMAIN', '').strip()
    if railway:
        return railway
    for host in settings.ALLOWED_HOSTS:
        if host.endswith('.railway.app') and not host.startswith(('.', '*')):
            return host
    return ''


def _source_page_url(submission, site):
    page = submission.source_page
    if page is None or not site:
        return ''
    try:
        path = page.get_absolute_url(submission.language or None)
    except Exception:
        logger.exception('Webhook: no URL for page %s', page.pk)
        return ''
    return f'https://{site}{path}' if path else ''


def build_payload(submission):
    site = _site_host()
    return {
        'event': 'form_submission',
        'submission_id': submission.pk,
        'form_slug': submission.form.slug,
        'form_name': submission.form.name,
        'site': site,
        'language': submission.language,
        'source_page': _source_page_url(submission, site),
        'submitted_at': submission.created_at.isoformat(),
        'data': {k: v for k, v in submission.data.items() if k != HONEYPOT_FIELD},
    }


def secret_for(form):
    """The form's own webhook secret, else the site-wide FORM_WEBHOOK_SECRET from the environment."""
    return form.webhook_secret or getattr(settings, 'FORM_WEBHOOK_SECRET', '')


def sign(secret, timestamp, body):
    """HMAC-SHA256 hex of b"{timestamp}." + body."""
    return hmac.new(secret.encode(), timestamp.encode() + b'.' + body, hashlib.sha256).hexdigest()


def _describe(exc):
    if isinstance(exc, urllib.error.HTTPError):
        with contextlib.suppress(Exception):
            exc.close()
        text = f'HTTP {exc.code} {exc.reason}'
    else:
        text = f'{type(exc).__name__}: {exc}'
    return text[:ERROR_MAX_LENGTH]


def _post(submission, now):
    """One POST. Returns None when the receiver answered 2xx, else the error text.
    Never raises."""
    try:
        url = submission.form.webhook_url
        if urlparse(url).scheme not in ('http', 'https'):
            return 'webhook_url is empty or not an http(s) URL'
        body = json.dumps(build_payload(submission), ensure_ascii=False).encode()
        timestamp = str(int(now.timestamp()))
        request = urllib.request.Request(url, data=body, method='POST', headers={
            'Content-Type': 'application/json; charset=utf-8',
            'User-Agent': 'DjangoPress-Webhook',
            'X-DjangoPress-Timestamp': timestamp,
            'X-DjangoPress-Signature': sign(secret_for(submission.form), timestamp, body),
        })
        with _opener.open(request, timeout=TIMEOUT) as response:
            status = response.status
        return None if 200 <= status < 300 else f'HTTP {status}'
    except Exception as exc:
        return _describe(exc)


def deliver(submission, *, now=None):
    """POST the submission once and record the outcome. True when delivered."""
    now = now or timezone.now()
    error = _post(submission, now)
    if error is None:
        submission.webhook_status = Status.DELIVERED
        submission.webhook_delivered_at = now
        submission.webhook_next_attempt_at = None
        submission.webhook_last_error = ''
        submission.save(update_fields=['webhook_status', 'webhook_delivered_at',
                                       'webhook_next_attempt_at', 'webhook_last_error'])
        return True

    submission.webhook_attempts += 1
    submission.webhook_last_error = error
    if submission.webhook_attempts >= MAX_ATTEMPTS:
        submission.webhook_status = Status.FAILED
        submission.webhook_next_attempt_at = None
    else:
        submission.webhook_status = Status.PENDING
        submission.webhook_next_attempt_at = now + timedelta(seconds=RETRY_DELAYS[submission.webhook_attempts - 1])
    submission.save(update_fields=['webhook_status', 'webhook_attempts', 'webhook_last_error',
                                   'webhook_next_attempt_at'])
    logger.warning('Webhook for submission %s failed (attempt %s): %s',
                   submission.pk, submission.webhook_attempts, error)
    return False


def deliver_due(*, now=None, include_failed=False):
    """Deliver the pending submissions whose time has come. Returns how many were delivered.

    include_failed also `resend`s the submissions that were already `failed` when the
    call started (one that fails for the last time during this call is left alone)."""
    now = now or timezone.now()
    rows = FormSubmission.objects.select_related('form', 'source_page').order_by('created_at', 'pk')
    due = list(
        rows.filter(webhook_status=Status.PENDING)
        .filter(Q(webhook_next_attempt_at__isnull=True) | Q(webhook_next_attempt_at__lte=now))
    )
    failed = list(rows.filter(webhook_status=Status.FAILED)) if include_failed else []
    delivered = 0
    for submission in due:
        try:
            delivered += bool(deliver(submission, now=now))
        except Exception:
            logger.exception('Webhook for submission %s could not be recorded', submission.pk)
    for submission in failed:
        try:
            delivered += bool(resend(submission))
        except Exception:
            logger.exception('Webhook for submission %s could not be resent', submission.pk)
    return delivered


def resend(submission):
    """Start over: zero attempts, pending, deliver now. True when delivered."""
    submission.webhook_status = Status.PENDING
    submission.webhook_attempts = 0
    submission.webhook_next_attempt_at = None
    submission.webhook_delivered_at = None
    submission.save(update_fields=['webhook_status', 'webhook_attempts',
                                   'webhook_next_attempt_at', 'webhook_delivered_at'])
    return deliver(submission)


def run_in_background(submission_id):
    """What the delivery thread runs: this submission, then whatever else is due."""
    try:
        submission = (FormSubmission.objects.select_related('form', 'source_page')
                      .filter(pk=submission_id, webhook_status=Status.PENDING).first())
        if submission is not None:
            deliver(submission)
        deliver_due()
    except Exception:
        logger.exception('Webhook delivery thread failed for submission %s', submission_id)
    finally:
        if not connection.in_atomic_block:
            connection.close()    # this thread's own connection


def deliver_in_background(submission_id):
    threading.Thread(target=run_in_background, args=(submission_id,), daemon=True,
                     name=f'form-webhook-{submission_id}').start()
