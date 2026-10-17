"""Tests for core.services.webhooks — the signed webhook a form sends for each submission."""

import hmac
import hashlib
import io
import json
import socket
import urllib.error
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from djangopress.core.models import DynamicForm, FormSubmission, Page
from djangopress.core.services import webhooks
from djangopress.core.services.forms import process_submission

Status = FormSubmission.WebhookStatus

URL = 'https://crm.example.test/api/inbound/forms/0b6e/'
NOW = datetime(2026, 10, 17, 12, 0, 0, tzinfo=dt_timezone.utc)

# hmac.new(b's3cr3t', b'1700000000.' + '{"nome":"Café São João"}'.encode(), sha256).hexdigest()
# The receiving side (the CRM) pins the same value.
FIXED_VECTOR = '880f93d6c5eba8ae54345fc9bb868570ae8516bc6f42b475fed3262c540fb4d7'


def ok(status=200):
    """What the HTTP client returns: a context manager with a .status."""
    response = MagicMock()
    response.status = status
    response.__enter__.return_value = response
    return response


def http_error(code):
    return urllib.error.HTTPError(URL, code, 'Server Error', {}, None)


def patch_http(**kwargs):
    return patch.object(webhooks._opener, 'open', **kwargs)


class WebhookTestCase(TestCase):

    def setUp(self):
        self.form = DynamicForm.objects.create(
            name='Pedido de proposta', slug='proposta', webhook_url=URL, webhook_secret='s3cr3t',
        )
        self.submission = FormSubmission.objects.create(
            form=self.form, language='pt', webhook_status=Status.PENDING,
            data={'nome': 'Café São João', 'email': 'ana@example.pt'},
        )

    def reload(self):
        self.submission.refresh_from_db()
        return self.submission


class SignatureTest(WebhookTestCase):

    def test_signature_matches_fixed_vector(self):
        body = '{"nome":"Café São João"}'.encode()
        signature = webhooks.sign('s3cr3t', '1700000000', body)
        self.assertEqual(signature, FIXED_VECTOR)
        # The same formula, written out: HMAC-SHA256 hex of "{timestamp}.{body}".
        self.assertEqual(signature, hmac.new(b's3cr3t', b'1700000000.' + body, hashlib.sha256).hexdigest())


class PayloadTest(WebhookTestCase):

    @override_settings(CUSTOM_DOMAINS=['pwd.example.pt', 'www.pwd.example.pt'],
                       ALLOWED_HOSTS=['localhost', '.railway.app', 'pwd.example.pt', 'www.pwd.example.pt'])
    def test_payload_has_spec_keys_and_drops_honeypot(self):
        page = Page.objects.create(title_i18n={'pt': 'Contacto'}, slug_i18n={'pt': 'contacto'}, sort_order=5)
        self.submission.source_page = page
        self.submission.data = {**self.submission.data, 'website_url': 'http://spam.example'}
        self.submission.save()

        payload = webhooks.build_payload(self.submission)

        self.assertEqual(set(payload), {
            'event', 'submission_id', 'form_slug', 'form_name', 'site', 'language',
            'source_page', 'submitted_at', 'data',
        })
        self.assertEqual(payload['event'], 'form_submission')
        self.assertEqual(payload['submission_id'], self.submission.pk)
        self.assertEqual(payload['form_slug'], 'proposta')
        self.assertEqual(payload['form_name'], 'Pedido de proposta')
        self.assertEqual(payload['site'], 'pwd.example.pt')
        self.assertEqual(payload['language'], 'pt')
        self.assertEqual(payload['source_page'], 'https://pwd.example.pt' + page.get_absolute_url('pt'))
        self.assertEqual(payload['submitted_at'], self.submission.created_at.isoformat())
        self.assertEqual(payload['data'], {'nome': 'Café São João', 'email': 'ana@example.pt'})
        json.dumps(payload)  # serialisable as is

    @override_settings(CUSTOM_DOMAINS=[], ALLOWED_HOSTS=['localhost', '.railway.app'])
    def test_site_is_empty_when_no_public_host_is_known(self):
        payload = webhooks.build_payload(self.submission)
        self.assertEqual(payload['site'], '')
        self.assertEqual(payload['source_page'], '')

    @override_settings(CUSTOM_DOMAINS=[], ALLOWED_HOSTS=['localhost', '.railway.app', 'pwd-landing.up.railway.app'])
    def test_site_falls_back_to_the_railway_host(self):
        self.assertEqual(webhooks.build_payload(self.submission)['site'], 'pwd-landing.up.railway.app')

    @override_settings(CUSTOM_DOMAINS=['pwd.example.pt'])
    def test_source_page_is_empty_without_a_page(self):
        self.assertEqual(webhooks.build_payload(self.submission)['source_page'], '')


class DeliverTest(WebhookTestCase):

    def test_deliver_2xx_marks_delivered_with_headers(self):
        self.submission.webhook_last_error = 'HTTP 500'
        self.submission.webhook_next_attempt_at = NOW
        self.submission.save()

        with patch_http(return_value=ok(201)) as opener:
            self.assertTrue(webhooks.deliver(self.submission, now=NOW))

        (request,), kwargs = opener.call_args
        self.assertEqual(kwargs['timeout'], 5)
        self.assertEqual(request.full_url, URL)
        self.assertEqual(request.get_method(), 'POST')
        headers = {k.lower(): v for k, v in request.header_items()}
        self.assertEqual(headers['content-type'], 'application/json; charset=utf-8')
        timestamp = headers['x-djangopress-timestamp']
        self.assertEqual(timestamp, str(int(NOW.timestamp())))
        # The signed bytes are the bytes on the wire, accents and all.
        body = request.data
        self.assertEqual(body, json.dumps(webhooks.build_payload(self.submission), ensure_ascii=False).encode())
        self.assertIn('Café São João'.encode(), body)
        self.assertEqual(headers['x-djangopress-signature'], webhooks.sign('s3cr3t', timestamp, body))

        sub = self.reload()
        self.assertEqual(sub.webhook_status, Status.DELIVERED)
        self.assertEqual(sub.webhook_delivered_at, NOW)
        self.assertIsNone(sub.webhook_next_attempt_at)
        self.assertEqual(sub.webhook_last_error, '')
        self.assertEqual(sub.webhook_attempts, 0)

    def test_deliver_error_schedules_retry_by_delay_table(self):
        self.assertEqual(webhooks.RETRY_DELAYS, (60, 300, 1800, 7200, 43200))
        self.assertEqual(webhooks.MAX_ATTEMPTS, 5)
        for attempts, delay in [(1, 60), (2, 300), (3, 1800), (4, 7200)]:
            with self.subTest(attempts=attempts):
                self.submission.webhook_status = Status.PENDING
                self.submission.webhook_attempts = attempts - 1
                self.submission.save()
                with patch_http(side_effect=http_error(500)):
                    self.assertFalse(webhooks.deliver(self.submission, now=NOW))
                sub = self.reload()
                self.assertEqual(sub.webhook_status, Status.PENDING)
                self.assertEqual(sub.webhook_attempts, attempts)
                self.assertEqual(sub.webhook_next_attempt_at, NOW + timedelta(seconds=delay))
                self.assertIn('500', sub.webhook_last_error)
                self.assertIsNone(sub.webhook_delivered_at)

    def test_fifth_failed_attempt_marks_failed(self):
        self.submission.webhook_attempts = 4
        self.submission.save()
        with patch_http(side_effect=http_error(503)):
            self.assertFalse(webhooks.deliver(self.submission, now=NOW))
        sub = self.reload()
        self.assertEqual(sub.webhook_status, Status.FAILED)
        self.assertEqual(sub.webhook_attempts, 5)
        self.assertIsNone(sub.webhook_next_attempt_at)
        self.assertIn('503', sub.webhook_last_error)

    def test_non_2xx_answer_is_an_error(self):
        with patch_http(return_value=ok(302)):
            self.assertFalse(webhooks.deliver(self.submission, now=NOW))
        sub = self.reload()
        self.assertEqual(sub.webhook_status, Status.PENDING)
        self.assertEqual(sub.webhook_attempts, 1)
        self.assertIn('302', sub.webhook_last_error)

    def test_deliver_never_raises_on_timeout_or_connection_error(self):
        errors = [
            TimeoutError('timed out'),
            socket.timeout('timed out'),
            urllib.error.URLError('connection refused'),
            urllib.error.URLError(socket.gaierror('name not known')),
            ConnectionResetError('reset by peer'),
            ValueError('unknown url type'),
            RuntimeError('anything at all'),
        ]
        for error in errors:
            with self.subTest(error=repr(error)):
                self.submission.webhook_attempts = 0
                self.submission.save()
                with patch_http(side_effect=error):
                    self.assertFalse(webhooks.deliver(self.submission, now=NOW))
                sub = self.reload()
                self.assertEqual(sub.webhook_status, Status.PENDING)
                self.assertEqual(sub.webhook_attempts, 1)
                self.assertTrue(sub.webhook_last_error)

    def test_only_http_urls_are_called(self):
        for url in ('file:///etc/passwd', 'ftp://crm.example.test/x', ''):
            with self.subTest(url=url):
                self.form.webhook_url = url
                self.form.save()
                self.submission.webhook_attempts = 0
                self.submission.save()
                with patch_http() as opener:
                    self.assertFalse(webhooks.deliver(self.submission, now=NOW))
                opener.assert_not_called()
                sub = self.reload()
                self.assertEqual(sub.webhook_attempts, 1)
                self.assertTrue(sub.webhook_last_error)


class DeliverDueTest(WebhookTestCase):

    def make(self, status, next_attempt_at=None):
        return FormSubmission.objects.create(
            form=self.form, data={'nome': 'X'}, webhook_status=status, webhook_next_attempt_at=next_attempt_at,
        )

    def test_deliver_due_picks_only_pending_and_due(self):
        due_new = self.make(Status.PENDING)
        due_retry = self.make(Status.PENDING, NOW - timedelta(seconds=1))
        later = self.make(Status.PENDING, NOW + timedelta(minutes=5))
        delivered = self.make(Status.DELIVERED)
        failed = self.make(Status.FAILED)
        none = self.make(Status.NONE)
        self.submission.delete()

        with patch_http(return_value=ok()) as opener:
            self.assertEqual(webhooks.deliver_due(now=NOW), 2)

        self.assertEqual(opener.call_count, 2)
        for sub in (due_new, due_retry):
            sub.refresh_from_db()
            self.assertEqual(sub.webhook_status, Status.DELIVERED)
        for sub, status in ((later, Status.PENDING), (delivered, Status.DELIVERED),
                            (failed, Status.FAILED), (none, Status.NONE)):
            sub.refresh_from_db()
            self.assertEqual(sub.webhook_status, status)
            self.assertEqual(sub.webhook_attempts, 0)

    def test_deliver_due_counts_only_what_was_delivered(self):
        self.make(Status.PENDING)
        with patch_http(side_effect=http_error(500)):
            self.assertEqual(webhooks.deliver_due(now=NOW), 0)

    def test_one_broken_submission_does_not_stop_the_others(self):
        second = self.make(Status.PENDING)
        real_deliver = webhooks.deliver

        def flaky(submission, **kwargs):
            if submission.pk == self.submission.pk:
                raise RuntimeError('database is locked')
            return real_deliver(submission, **kwargs)

        with patch.object(webhooks, 'deliver', side_effect=flaky), patch_http(return_value=ok()):
            self.assertEqual(webhooks.deliver_due(now=NOW), 1)
        second.refresh_from_db()
        self.assertEqual(second.webhook_status, Status.DELIVERED)

    def test_command_runs_deliver_due_and_reports(self):
        out = io.StringIO()
        with patch_http(return_value=ok()):
            call_command('deliver_form_webhooks', stdout=out)
        self.assertIn('1 submissões entregues', out.getvalue())
        self.assertEqual(self.reload().webhook_status, Status.DELIVERED)


class ProcessSubmissionTest(WebhookTestCase):

    def submit(self, form, *, notify_to=None):
        return process_submission(form, {'nome': 'Ana'}, 'pt', '203.0.113.9', 'pytest', notify_to=notify_to)

    def test_no_webhook_url_keeps_status_none_and_sends_nothing(self):
        plain = DynamicForm.objects.create(name='Contacto', slug='contacto')
        with patch('djangopress.core.services.webhooks.threading.Thread') as thread, patch_http() as opener:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                result = self.submit(plain)
        self.assertEqual(result['submission'].webhook_status, Status.NONE)
        self.assertEqual(callbacks, [])
        thread.assert_not_called()
        opener.assert_not_called()

    def test_process_submission_marks_pending_and_starts_delivery_on_commit(self):
        with patch('djangopress.core.services.webhooks.threading.Thread') as thread:
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                result = self.submit(self.form)
            submission = result['submission']
            # Saved as pending, nothing started before the commit.
            submission.refresh_from_db()
            self.assertEqual(submission.webhook_status, Status.PENDING)
            self.assertEqual(len(callbacks), 1)
            thread.assert_not_called()

            callbacks[0]()

        thread.assert_called_once()
        self.assertTrue(thread.call_args.kwargs['daemon'])
        thread.return_value.start.assert_called_once_with()

        # What the thread runs: this submission first, then whatever else is due
        # (here also the pending one from setUp).
        with patch_http(return_value=ok()) as opener:
            thread.call_args.kwargs['target'](*thread.call_args.kwargs.get('args', ()))
        self.assertEqual(opener.call_count, 2)
        submission.refresh_from_db()
        self.assertEqual(submission.webhook_status, Status.DELIVERED)
        self.assertEqual(self.reload().webhook_status, Status.DELIVERED)

    def test_background_run_delivers_this_submission_then_whatever_is_due(self):
        other = FormSubmission.objects.create(form=self.form, data={'nome': 'B'}, webhook_status=Status.PENDING)
        with patch_http(return_value=ok()) as opener:
            webhooks.run_in_background(self.submission.pk)
        self.assertEqual(opener.call_count, 2)
        self.assertEqual(self.reload().webhook_status, Status.DELIVERED)
        other.refresh_from_db()
        self.assertEqual(other.webhook_status, Status.DELIVERED)

    def test_background_run_skips_a_submission_that_is_no_longer_pending(self):
        self.submission.webhook_status = Status.DELIVERED
        self.submission.save()
        with patch_http() as opener:
            webhooks.run_in_background(self.submission.pk)
        opener.assert_not_called()

    def test_background_run_never_raises(self):
        with patch.object(webhooks, 'deliver', side_effect=RuntimeError('database is locked')):
            webhooks.run_in_background(self.submission.pk)

    def test_a_test_send_never_reaches_the_webhook(self):
        # The site assistant's test_form passes notify_to and deletes the submission afterwards.
        with patch('djangopress.core.services.webhooks.threading.Thread') as thread:
            with self.captureOnCommitCallbacks(execute=True):
                result = self.submit(self.form, notify_to='equipa@example.pt')
        self.assertEqual(result['submission'].webhook_status, Status.NONE)
        thread.assert_not_called()

    def test_invalid_submission_starts_nothing(self):
        self.form.fields_schema = [{'name': 'email', 'type': 'email', 'required': True, 'label': 'Email'}]
        self.form.save()
        with patch('djangopress.core.services.webhooks.threading.Thread') as thread:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                result = process_submission(self.form, {}, 'pt', None, '')
        self.assertTrue(result['errors'])
        self.assertEqual(callbacks, [])
        thread.assert_not_called()


class ResendTest(WebhookTestCase):

    def test_resend_resets_attempts_and_delivers(self):
        self.submission.webhook_status = Status.FAILED
        self.submission.webhook_attempts = 5
        self.submission.webhook_last_error = 'HTTP 503'
        self.submission.save()

        with patch_http(return_value=ok()) as opener:
            self.assertTrue(webhooks.resend(self.submission))

        opener.assert_called_once()
        sub = self.reload()
        self.assertEqual(sub.webhook_status, Status.DELIVERED)
        self.assertEqual(sub.webhook_attempts, 0)
        self.assertIsNotNone(sub.webhook_delivered_at)

    def test_resend_that_fails_again_starts_the_schedule_over(self):
        self.submission.webhook_status = Status.FAILED
        self.submission.webhook_attempts = 5
        self.submission.save()

        with patch_http(side_effect=http_error(500)):
            self.assertFalse(webhooks.resend(self.submission))

        sub = self.reload()
        self.assertEqual(sub.webhook_status, Status.PENDING)
        self.assertEqual(sub.webhook_attempts, 1)
        self.assertIsNotNone(sub.webhook_next_attempt_at)
