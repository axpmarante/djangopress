from django.shortcuts import render
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.conf import settings
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
            # Always allow access to backoffice panel (for login and management)
            if request.path.startswith('/backoffice/'):
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
