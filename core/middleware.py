from django.shortcuts import render
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.utils import translation
from django.conf import settings
from django.core.cache import cache
from .models import SiteSettings


class DomainMiddleware:
    """
    Middleware that captures the current domain and stores it in settings.
    This allows the storage backend to organize files by domain.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Get domain without port (e.g., example.com:8000 → example.com)
        domain = request.get_host().split(':')[0]

        # Store in settings for use by storage backend
        settings.CURRENT_DOMAIN = domain

        response = self.get_response(request)
        return response


class MaintenanceModeMiddleware:
    """Middleware to show maintenance page when maintenance mode is enabled"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        site_settings = SiteSettings.load()

        # Check if maintenance mode is enabled
        if site_settings.maintenance_mode:
            # Always allow access to backoffice panel and Django admin (for login and management)
            if request.path.startswith('/backoffice/') or request.path.startswith('/django-admin/'):
                return self.get_response(request)

            # Allow authenticated staff users to access the site
            if request.user.is_authenticated and request.user.is_staff:
                # Add a warning message for staff users
                if not request.path.startswith('/static/'):
                    messages.warning(
                        request,
                        _('⚠️ Maintenance mode is active. Regular visitors will see the maintenance page. You can disable it in the backoffice panel.')
                    )
            else:
                # Show maintenance page to non-staff users
                return render(request, 'core/maintenance.html', status=503)

        return self.get_response(request)


class DynamicLanguageMiddleware:
    """
    Middleware to handle dynamic default language without prefix.

    This middleware allows the default language (from SiteSettings) to be accessed
    without a language prefix, while non-default languages require a prefix.

    Examples:
    - If default is 'pt': /sobre/ works, /en/about/ works
    - If default is 'en': /about/ works, /pt/sobre/ works

    The default language can be changed in SiteSettings without restarting the server.

    HOW IT WORKS:
    - All languages are configured in i18n_patterns with prefix_default_language=True
    - This middleware intercepts requests without language prefix
    - It resolves the URL by prepending the default language prefix internally
    - The response is returned without redirecting (URL stays clean)
    """

    def __init__(self, get_response):
        self.get_response = get_response
        # Paths that should bypass language handling
        self.bypass_paths = ['/django-admin/', '/backoffice/', '/ai/', '/editor/', '/site-assistant/', '/i18n/', '/sitemap.xml', '/media/', '/static/']

    def __call__(self, request):
        from django.urls import resolve, Resolver404
        from django.http import Http404

        path = request.path_info

        # Skip processing for specific paths
        if any(path.startswith(bp) for bp in self.bypass_paths):
            return self.get_response(request)

        # Get default language from SiteSettings (with caching)
        default_language = cache.get('default_language_code')
        if default_language is None:
            try:
                site_settings = SiteSettings.objects.first()
                if site_settings:
                    default_language = site_settings.get_default_language()
                    cache.set('default_language_code', default_language, 60 * 60)
                else:
                    default_language = 'pt'
            except:
                default_language = 'pt'

        # Check if path starts with a language code
        path_parts = path.strip('/').split('/')
        first_part = path_parts[0] if path_parts and path_parts[0] else ''

        # Get available language codes
        available_languages = [lang[0] for lang in settings.LANGUAGES]

        # If path has a language prefix, let Django handle it normally
        if first_part in available_languages:
            # Activate the language from the URL
            if translation.get_language() != first_part:
                translation.activate(first_part)
                request.LANGUAGE_CODE = first_part
            response = self.get_response(request)
            return response

        # No language prefix detected - this is a request for the default language
        # We need to handle this specially because i18n_patterns expects a prefix

        # Activate default language
        translation.activate(default_language)
        request.LANGUAGE_CODE = default_language

        # Try to resolve the unprefixed URL with default language
        # We'll modify the path internally to include the language prefix
        prefixed_path = f'/{default_language}{path}'

        try:
            # Try to resolve the prefixed path to check if it exists
            resolve(prefixed_path)

            # If it resolves, modify the request path internally
            # This allows i18n_patterns to handle it correctly
            original_path = request.path_info
            request.path_info = prefixed_path
            request.path = prefixed_path

            # Process the request with the modified path
            response = self.get_response(request)

            # Restore original path (though this doesn't really matter at this point)
            request.path_info = original_path
            request.path = original_path

            return response

        except Resolver404:
            # Path doesn't exist even with language prefix
            # Let Django handle it normally (will raise 404)
            response = self.get_response(request)
            return response
