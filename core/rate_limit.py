"""
Cache-based rate limiting.

Uses Django's cache backend to track request counts per IP.
Consistent with the pattern already used in core.views.form_submit.

Provides both a decorator (for individual views) and middleware
(for URL-prefix-based limiting).
"""
from functools import wraps
from django.core.cache import cache
from django.http import JsonResponse, HttpResponse


def _get_client_ip(request):
    """Extract client IP, respecting X-Forwarded-For for reverse proxies."""
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '0.0.0.0')


def _check_rate_limit(ip, group, max_requests, period):
    """Check and increment rate limit. Returns True if blocked."""
    key = f'ratelimit:{group}:{ip}'
    count = cache.get(key, 0)
    if count >= max_requests:
        return True
    cache.set(key, count + 1, period)
    return False


def rate_limit(max_requests, period, group=None):
    """
    Rate limit decorator for individual views.

    Args:
        max_requests: Maximum number of requests allowed in the period.
        period: Time window in seconds.
        group: Optional key prefix (defaults to view function name).

    Returns 429 JSON response when limit is exceeded.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            ip = _get_client_ip(request)
            if _check_rate_limit(ip, group or view_func.__name__, max_requests, period):
                return JsonResponse(
                    {'error': 'Too many requests. Please try again later.'},
                    status=429,
                )
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


# Rate limit rules: (path_prefix, method, group, max_requests, period_seconds)
RATE_LIMIT_RULES = [
    ('/backoffice/login/', 'POST', 'login', 5, 60),        # 5 login attempts/min
    ('/backoffice/auto-login/', 'POST', 'login', 5, 60),   # same pool as login
    ('/ai/api/', 'POST', 'ai_api', 30, 60),                # 30 AI calls/min
]


class RateLimitMiddleware:
    """Apply rate limiting by URL prefix and HTTP method."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        for prefix, method, group, max_req, period in RATE_LIMIT_RULES:
            if request.path.startswith(prefix) and request.method == method:
                ip = _get_client_ip(request)
                if _check_rate_limit(ip, group, max_req, period):
                    msg = 'Too many requests. Please try again later.'
                    if request.headers.get('Accept', '').startswith('text/html'):
                        return HttpResponse(msg, status=429, content_type='text/plain')
                    return JsonResponse({'error': msg}, status=429)
                break  # only first matching rule applies
        return self.get_response(request)
