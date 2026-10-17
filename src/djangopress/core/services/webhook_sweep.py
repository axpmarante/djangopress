"""The retry sweep for form webhooks: a timer in each process that serves requests.

A site has no worker, and no cron can reach its SQLite (a Railway cron runs in another container, and a second
`litestream replicate` would corrupt the replica). So each serving process retries its own webhooks: a daemon thread
calls `webhooks.deliver_due()` every SWEEP_INTERVAL seconds. Pending and failed-but-retrying submissions then go out
on their RETRY_DELAYS schedule with no new traffic. Two processes may POST the same submission at once; the receiver
is idempotent (the CRM keys a submission on its id and submitted_at).

Where it starts, only in processes that serve requests:

- a gunicorn worker, as it boots. `CoreConfig.ready()` calls `start_at_boot()`, which looks at the process's SIGTERM
  handler: a gunicorn worker installs its own (`Worker.handle_exit`) before it loads the app, and only a worker has
  it. So a site that restarts with pending rows retries them without waiting for a visitor. The gunicorn master
  never starts it, not even with `preload_app` (it loads the app before it installs any handler);
- any process, on the first request it serves through Django's own WSGI or ASGI handler (the `request_started`
  signal): runserver, a preloaded gunicorn worker, any other server.

Never in management commands (`migrate`, `shell`, `deliver_form_webhooks`, `check`...), which serve no request and
are no gunicorn worker. Never in tests: the test client sends `request_started` from its own handler (not a
WSGIHandler), and a real handler inside a test run (LiveServerTestCase) is recognised by `django.core.mail.outbox`,
which Django's test environment sets up.

At most one timer per process; a forked child (another pid) starts its own. Nothing here raises: every error is
logged. A pass does nothing when no form has a webhook_url.
"""

import contextlib
import logging
import os
import signal
import threading
import time

from django.core import mail
from django.core.handlers.asgi import ASGIHandler
from django.core.handlers.wsgi import WSGIHandler
from django.db import connection

from djangopress.core.models import DynamicForm
from djangopress.core.services import webhooks

logger = logging.getLogger(__name__)

SWEEP_INTERVAL = 300  # seconds between two passes
THREAD_NAME = 'form-webhook-sweep'

_lock = threading.Lock()
_started_pid = None  # the process that started the timer (a thread does not survive a fork)


def sweep_once():
    """One pass: deliver the webhooks that are due. Returns how many were delivered. Never raises."""
    try:
        if not DynamicForm.objects.exclude(webhook_url='').exists():
            return 0
        return webhooks.deliver_due()
    except Exception:
        logger.exception('Form webhook retry sweep failed')
        return 0
    finally:
        if not connection.in_atomic_block:
            with contextlib.suppress(Exception):
                connection.close()  # the timer thread's own connection: not held between passes


def _loop(interval):
    """What the timer thread runs, until the process ends."""
    while True:
        time.sleep(interval)
        sweep_once()


def ensure_started(interval=SWEEP_INTERVAL):
    """Start the timer in this process unless it already runs here. True when it was started. Never raises."""
    global _started_pid
    pid = os.getpid()
    try:
        with _lock:
            if _started_pid == pid:
                return False
            threading.Thread(target=_loop, args=(interval,), daemon=True, name=THREAD_NAME).start()
            _started_pid = pid
    except Exception:
        logger.exception('Form webhook retry sweep could not start')
        return False
    logger.info('Form webhook retry sweep started in process %s (every %s s)', pid, interval)
    return True


def _test_run():
    """Inside Django's test environment (setup_test_environment creates mail.outbox)."""
    return hasattr(mail, 'outbox')


def _serves_requests(sender):
    """The request came through Django's real WSGI/ASGI handler (or a subclass, e.g. runserver's static files
    handler), not the test client's."""
    return isinstance(sender, type) and issubclass(sender, (WSGIHandler, ASGIHandler)) and not _test_run()


def on_request_started(sender, **kwargs):
    """`request_started` receiver: the first real request of a process starts its timer. Never raises."""
    if _started_pid == os.getpid():
        return  # the usual case, without a lock
    try:
        if _serves_requests(sender):
            ensure_started()
    except Exception:
        logger.exception('Form webhook retry sweep: start on request failed')


def _in_gunicorn_worker():
    try:
        from gunicorn.workers.base import Worker
    except ImportError:
        return False
    handler = signal.getsignal(signal.SIGTERM)
    return isinstance(getattr(handler, '__self__', None), Worker)


def start_at_boot():
    """Called by CoreConfig.ready(): start now when this process is a gunicorn worker. Never raises."""
    try:
        if _in_gunicorn_worker():
            ensure_started()
    except Exception:
        logger.exception('Form webhook retry sweep: start at boot failed')
