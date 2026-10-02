"""Request-path code logs through logging, not print(): in production print() wrote whole
prompts and pages to stdout, Railway dropped logs over 500 lines a second and the real
errors went missing. Management commands may print (that is their output)."""
import logging
import re
from pathlib import Path

from django.test import SimpleTestCase

from djangopress.core.debug_log import debug

ROOT = Path(__file__).resolve().parents[2]
SKIP = ('tests', 'management', 'migrations')
PRINT_RE = re.compile(r'^\s*print\(', re.M)


class NoPrintTest(SimpleTestCase):
    def test_request_path_modules_do_not_print(self):
        offenders = []
        for path in ROOT.rglob('*.py'):
            if any(part in SKIP for part in path.relative_to(ROOT).parts):
                continue
            count = len(PRINT_RE.findall(path.read_text(encoding='utf-8')))
            if count:
                offenders.append(f'{path.relative_to(ROOT)} ({count})')
        self.assertEqual(offenders, [])


class DebugLogTest(SimpleTestCase):
    def test_debug_goes_to_the_callers_logger_at_debug_level(self):
        with self.assertLogs(__name__, level='DEBUG') as logs:
            debug('Prompt', 123, end='')
        self.assertEqual(logs.records[0].levelno, logging.DEBUG)
        self.assertEqual(logs.records[0].getMessage(), 'Prompt 123')

    def test_nothing_is_built_when_debug_is_off(self):
        class Loud:
            def __str__(self):
                raise AssertionError('formatted although debug is off')
        logging.getLogger(__name__).setLevel(logging.INFO)
        try:
            debug(Loud())
        finally:
            logging.getLogger(__name__).setLevel(logging.NOTSET)
