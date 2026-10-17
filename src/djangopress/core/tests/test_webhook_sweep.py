"""Tests for core.services.webhook_sweep — the timer that retries form webhooks without traffic or a cron."""

import os
import signal
import threading
from unittest.mock import MagicMock, patch

from django.contrib.staticfiles.handlers import StaticFilesHandler
from django.core.handlers.wsgi import WSGIHandler
from django.core.management import call_command
from django.core.signals import request_started
from django.test import TestCase
from gunicorn.workers.base import Worker

from djangopress.core.models import DynamicForm, FormSubmission
from djangopress.core.services import webhook_sweep, webhooks

Status = FormSubmission.WebhookStatus
URL = 'https://crm.example.test/api/inbound/forms/0b6e/'


class _Stop(BaseException):
    """Ends the timer loop in a test (the loop swallows every Exception, by design)."""


def ok(status=200):
    response = MagicMock()
    response.status = status
    response.__enter__.return_value = response
    return response


class FreshProcessMixin:
    """Each test starts as a process where the sweep was never started, and never starts a real thread."""

    def setUp(self):
        super().setUp()
        started = patch.object(webhook_sweep, '_started_pid', None)
        started.start()
        self.addCleanup(started.stop)


class SweepOnceTest(TestCase):

    def test_calls_deliver_due_when_a_form_has_a_webhook(self):
        DynamicForm.objects.create(name='Pedido', slug='pedido', webhook_url=URL, webhook_secret='s')
        with patch.object(webhooks, 'deliver_due', return_value=2) as deliver_due:
            self.assertEqual(webhook_sweep.sweep_once(), 2)
        deliver_due.assert_called_once_with()

    def test_does_nothing_when_no_form_has_a_webhook(self):
        DynamicForm.objects.create(name='Contacto', slug='contacto')
        with patch.object(webhooks, 'deliver_due') as deliver_due:
            self.assertEqual(webhook_sweep.sweep_once(), 0)
        deliver_due.assert_not_called()

    def test_errors_are_swallowed_and_logged(self):
        DynamicForm.objects.create(name='Pedido', slug='pedido', webhook_url=URL, webhook_secret='s')
        with patch.object(webhooks, 'deliver_due', side_effect=RuntimeError('database is locked')), \
                self.assertLogs('djangopress.core.services.webhook_sweep', level='ERROR') as logs:
            self.assertEqual(webhook_sweep.sweep_once(), 0)
        self.assertIn('database is locked', '\n'.join(logs.output))

    def test_a_pass_retries_a_pending_row_whose_wait_is_over(self):
        form = DynamicForm.objects.create(name='Pedido', slug='pedido', webhook_url=URL, webhook_secret='s')
        submission = FormSubmission.objects.create(
            form=form, language='pt', data={'email': 'ana@example.pt'},
            webhook_status=Status.PENDING, webhook_attempts=1, webhook_last_error='HTTP 503',
        )
        with patch.object(webhooks._opener, 'open', return_value=ok()) as open_:
            self.assertEqual(webhook_sweep.sweep_once(), 1)
        open_.assert_called_once()
        submission.refresh_from_db()
        self.assertEqual(submission.webhook_status, Status.DELIVERED)


class TimerLoopTest(TestCase):

    def test_the_timer_runs_a_pass_every_interval(self):
        sleeps = []

        def sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps) == 3:
                raise _Stop

        with patch.object(webhook_sweep.time, 'sleep', side_effect=sleep), \
                patch.object(webhook_sweep, 'sweep_once') as sweep_once, self.assertRaises(_Stop):
            webhook_sweep._loop(webhook_sweep.SWEEP_INTERVAL)
        self.assertEqual(sleeps, [300, 300, 300])
        self.assertEqual(sweep_once.call_count, 2)

    def test_the_timer_function_calls_deliver_due(self):
        DynamicForm.objects.create(name='Pedido', slug='pedido', webhook_url=URL, webhook_secret='s')
        with patch.object(webhook_sweep.time, 'sleep', side_effect=[None, _Stop]), \
                patch.object(webhooks, 'deliver_due', return_value=0) as deliver_due, self.assertRaises(_Stop):
            webhook_sweep._loop(webhook_sweep.SWEEP_INTERVAL)
        deliver_due.assert_called_once_with()

    def test_an_error_in_a_pass_does_not_stop_the_timer(self):
        DynamicForm.objects.create(name='Pedido', slug='pedido', webhook_url=URL, webhook_secret='s')
        with patch.object(webhook_sweep.time, 'sleep', side_effect=[None, None, _Stop]), \
                patch.object(webhooks, 'deliver_due', side_effect=RuntimeError('boom')) as deliver_due, \
                self.assertLogs('djangopress.core.services.webhook_sweep', level='ERROR'), self.assertRaises(_Stop):
            webhook_sweep._loop(webhook_sweep.SWEEP_INTERVAL)
        self.assertEqual(deliver_due.call_count, 2)


class EnsureStartedTest(FreshProcessMixin, TestCase):

    def test_starts_one_daemon_thread_at_most_once_per_process(self):
        with patch.object(webhook_sweep.threading, 'Thread') as thread:
            self.assertTrue(webhook_sweep.ensure_started())
            self.assertFalse(webhook_sweep.ensure_started())
        thread.assert_called_once()
        self.assertTrue(thread.call_args.kwargs['daemon'])
        self.assertEqual(thread.call_args.kwargs['name'], 'form-webhook-sweep')
        thread.return_value.start.assert_called_once_with()
        self.assertEqual(webhook_sweep._started_pid, os.getpid())

    def test_a_forked_process_starts_its_own(self):
        """Threads do not survive a fork: a child sees the parent's pid and starts again."""
        webhook_sweep._started_pid = os.getpid() + 1
        with patch.object(webhook_sweep.threading, 'Thread') as thread:
            self.assertTrue(webhook_sweep.ensure_started())
        thread.return_value.start.assert_called_once_with()

    def test_a_thread_that_cannot_start_is_logged_and_never_raises(self):
        with patch.object(webhook_sweep.threading, 'Thread') as thread, \
                self.assertLogs('djangopress.core.services.webhook_sweep', level='ERROR'):
            thread.return_value.start.side_effect = RuntimeError("can't start new thread")
            self.assertFalse(webhook_sweep.ensure_started())
        self.assertIsNone(webhook_sweep._started_pid)  # the next request may try again


class WhereItStartsTest(FreshProcessMixin, TestCase):
    """Only processes that serve requests start it: never management commands, migrations, tests or the shell."""

    def setUp(self):
        super().setUp()
        ensure = patch.object(webhook_sweep, 'ensure_started')
        self.ensure_started = ensure.start()
        self.addCleanup(ensure.stop)

    def test_a_request_through_a_real_wsgi_handler_starts_it(self):
        with patch.object(webhook_sweep, '_test_run', return_value=False):
            # the receiver CoreConfig.ready() connected
            request_started.send(sender=WSGIHandler, environ={})
            request_started.send(sender=StaticFilesHandler, environ={})  # runserver's handler for static files
        self.assertEqual(self.ensure_started.call_count, 2)

    def test_the_test_client_does_not_start_it(self):
        with patch.object(webhook_sweep, '_test_run', return_value=False):
            self.client.get('/django-admin/login/')  # request_started comes from the test client's own handler
        self.ensure_started.assert_not_called()

    def test_a_wsgi_request_inside_the_test_runner_does_not_start_it(self):
        """E.g. a LiveServerTestCase: a real WSGIHandler, but a test run."""
        request_started.send(sender=WSGIHandler, environ={})
        self.ensure_started.assert_not_called()

    def test_management_commands_do_not_start_it(self):
        call_command('check', verbosity=0)
        call_command('deliver_form_webhooks', stdout=MagicMock())
        call_command('migrate', '--check', verbosity=0)
        webhook_sweep.start_at_boot()  # what CoreConfig.ready() does: this process is no gunicorn worker
        self.ensure_started.assert_not_called()
        self.assertNotIn('form-webhook-sweep', [thread.name for thread in threading.enumerate()])

    def test_a_gunicorn_worker_starts_it_at_boot(self):
        """A gunicorn worker installs its SIGTERM handler before it loads the app, so ready() sees it."""
        worker = object.__new__(type('ThreadWorker', (Worker,), {}))
        with patch.object(webhook_sweep.signal, 'getsignal', return_value=worker.handle_exit) as getsignal:
            webhook_sweep.start_at_boot()
        getsignal.assert_called_with(signal.SIGTERM)
        self.ensure_started.assert_called_once_with()

    def test_the_gunicorn_master_does_not_start_it_at_boot(self):
        """With preload_app the master loads the app before it has any handler: SIGTERM is still the default."""
        with patch.object(webhook_sweep.signal, 'getsignal', return_value=signal.SIG_DFL):
            webhook_sweep.start_at_boot()
        self.ensure_started.assert_not_called()

    def test_the_receiver_never_raises(self):
        with patch.object(webhook_sweep, '_serves_requests', side_effect=RuntimeError('boom')), \
                self.assertLogs('djangopress.core.services.webhook_sweep', level='ERROR'):
            request_started.send(sender=WSGIHandler, environ={})
        self.ensure_started.assert_not_called()

    def test_start_at_boot_never_raises(self):
        with patch.object(webhook_sweep.signal, 'getsignal', side_effect=ValueError('no signals here')), \
                self.assertLogs('djangopress.core.services.webhook_sweep', level='ERROR'):
            webhook_sweep.start_at_boot()
        self.ensure_started.assert_not_called()
