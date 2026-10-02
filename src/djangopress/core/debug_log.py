"""Developer output on the request path (prompts, HTML sizes, timings).

These were print() calls: in production they wrote whole prompts and pages to stdout, Railway
dropped logs over 500 lines a second and the real errors went missing. They are DEBUG records
now, on the calling module's logger: off unless ENABLE_DEBUG_LOGGING is set.
"""
import logging
import sys


def debug(*args, **_print_kwargs):
    """print()-compatible: the arguments are joined with spaces, print's keyword arguments ignored."""
    logger = logging.getLogger(sys._getframe(1).f_globals.get('__name__', 'djangopress'))
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(' '.join(str(a) for a in args))
