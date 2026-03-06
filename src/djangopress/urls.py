"""
DjangoPress URL configuration.

Child sites import with:
    from djangopress.urls import urlpatterns

Then append custom URL patterns if needed.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls.i18n import i18n_patterns
from django.contrib.sitemaps.views import sitemap
from django.http import HttpResponse

from djangopress.core.sitemaps import PageSitemap
from djangopress.core.views import set_language, form_submit

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
    path('django-admin/', admin.site.urls),
    path('ai/', include('djangopress.ai.urls')),
    path('backoffice/', include('djangopress.backoffice.urls')),
    path('editor-v2/', include('djangopress.editor_v2.urls')),
    path('site-assistant/', include('djangopress.site_assistant.urls')),
    path('i18n/', include('django.conf.urls.i18n')),
    path('set-language/', set_language, name='set_language'),
    path('forms/<slug:slug>/submit/', form_submit, name='form_submit'),
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),
    path('robots.txt', robots_txt, name='robots_txt'),
]

# Serve media/static files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# i18n patterns for content pages
urlpatterns += i18n_patterns(
    path('', include('djangopress.news.urls')),
    path('', include('djangopress.core.urls')),
    prefix_default_language=True,
)
