"""
Stop a running assistant turn. The turn runs inside one request; the Stop
button sends another request, which may land on another gunicorn worker, so
the signal is a small file in the shared temp directory (no cache is shared
between workers). The running turn checks it before each step.
"""
import re
import tempfile
from pathlib import Path

_RUN_ID_RE = re.compile(r'^[A-Za-z0-9-]{8,64}$')
_DIR = Path(tempfile.gettempdir()) / 'djangopress-assistant-cancel'


def _path(run_id):
    if not run_id or not _RUN_ID_RE.match(str(run_id)):
        return None
    return _DIR / str(run_id)


def request_cancel(run_id):
    path = _path(run_id)
    if path is None:
        return False
    _DIR.mkdir(parents=True, exist_ok=True)
    path.touch()
    return True


def is_cancelled(run_id):
    path = _path(run_id)
    return bool(path and path.exists())


def clear(run_id):
    path = _path(run_id)
    if path and path.exists():
        path.unlink()
