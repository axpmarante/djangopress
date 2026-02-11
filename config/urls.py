"""URL Configuration for DjangoPress"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls.i18n import i18n_patterns
from django.contrib.sitemaps.views import sitemap
from django.http import HttpResponse
from core.sitemaps import PageSitemap

sitemaps = {
    'pages': PageSitemap,
}


def robots_txt(request):
    lines = [
        "User-agent: *",
        "Allow: /",
        f"Sitemap: {request.build_absolute_uri('/sitemap.xml')}",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")


urlpatterns = [
    path('django-admin/', admin.site.urls),  # Django admin (fallback/advanced)
    path('ai/', include('ai.urls')),  # AI content generation
    path('backoffice/', include('backoffice.urls')),  # Custom backoffice
    path('editor/', include('editor.urls')),  # Inline editor
    path('site-assistant/', include('site_assistant.urls')),  # Site Assistant
    path('i18n/', include('django.conf.urls.i18n')),
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),
    path('robots.txt', robots_txt, name='robots_txt'),
]

# Serve media/static files in development (must be before i18n catch-all)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Add i18n patterns for core URLs
# prefix_default_language=True means ALL languages get a URL prefix
# Our DynamicLanguageMiddleware handles unprefixed URLs by routing them to the default language
# This allows the default language to be changed in the database without code changes
urlpatterns += i18n_patterns(
    path('site-assistant/', include('site_assistant.urls')),  # Before core catch-all
    path('', include('core.urls')),
    prefix_default_language=True,  # All languages use prefixes (middleware handles unprefixed URLs)
)
