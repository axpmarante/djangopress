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
    """
    robots.txt with explicit allowlist for AI crawlers.

    Most AI agents (ChatGPT, Claude, Gemini, Perplexity, etc.) are opt-in by
    default when a site is silent about them. Explicitly allowing them signals
    that this content is safe to index, cite, and recommend.
    """
    ai_bots = [
        "GPTBot",           # OpenAI (ChatGPT training)
        "ChatGPT-User",     # ChatGPT browsing
        "OAI-SearchBot",    # OpenAI SearchGPT
        "Google-Extended",  # Google Gemini/Bard training
        "anthropic-ai",     # Anthropic training
        "ClaudeBot",        # Claude crawler
        "Claude-Web",       # Claude browsing
        "PerplexityBot",    # Perplexity
        "Perplexity-User",  # Perplexity live search
        "Applebot-Extended",  # Apple Intelligence
        "CCBot",            # Common Crawl (training data)
        "FacebookBot",      # Meta training
        "Meta-ExternalAgent",  # Meta agents
        "Amazonbot",        # Amazon AI
        "cohere-ai",        # Cohere
        "YouBot",           # You.com
        "DuckAssistBot",    # DuckDuckGo AI
    ]

    lines = [
        "# Default: allow all",
        "User-agent: *",
        "Allow: /",
        "",
        "# Explicit allowlist for AI crawlers",
    ]

    for bot in ai_bots:
        lines.append(f"User-agent: {bot}")
        lines.append("Allow: /")
        lines.append("")

    lines.append(f"Sitemap: {request.build_absolute_uri('/sitemap.xml')}")
    lines.append(f"Llms: {request.build_absolute_uri('/llms.txt')}")

    return HttpResponse("\n".join(lines), content_type="text/plain")


def llms_txt(request):
    """
    llms.txt — emerging standard for LLM/AI agent discovery.

    Spec: https://llmstxt.org/

    Generates a markdown index of the site from SiteSettings + active Pages,
    optimized for AI agents to understand the site structure and recommend
    content. Zero configuration — works out of the box for any DjangoPress site.
    """
    from djangopress.core.models import Page, SiteSettings
    from django.utils.translation import get_language

    settings_obj = SiteSettings.load()
    lang = settings_obj.get_default_language() if settings_obj else 'pt'

    # Site name and description
    site_name = ''
    site_description = ''
    if settings_obj:
        if isinstance(settings_obj.site_name_i18n, dict):
            site_name = settings_obj.site_name_i18n.get(lang) or next(
                iter(settings_obj.site_name_i18n.values()), ''
            )
        if isinstance(settings_obj.site_description_i18n, dict):
            site_description = settings_obj.site_description_i18n.get(lang) or next(
                iter(settings_obj.site_description_i18n.values()), ''
            )

    lines = [f"# {site_name}" if site_name else "# Site"]
    if site_description:
        lines.append("")
        lines.append(f"> {site_description}")

    # Pages section — exclude A/B test variants (sort_order >= 1000 by convention)
    # and hidden slugs
    active_pages = (
        Page.objects.filter(is_active=True)
        .filter(sort_order__lt=1000)
        .order_by('sort_order', 'id')
    )
    if active_pages.exists():
        lines.append("")
        lines.append("## Pages")
        lines.append("")
        base_url = request.build_absolute_uri('/').rstrip('/')
        for page in active_pages:
            title = ''
            slug = ''
            description = ''
            if isinstance(page.title_i18n, dict):
                title = page.title_i18n.get(lang) or next(iter(page.title_i18n.values()), '')
            if isinstance(page.slug_i18n, dict):
                slug = page.slug_i18n.get(lang) or next(iter(page.slug_i18n.values()), '')
            if isinstance(page.meta_description_i18n, dict):
                description = page.meta_description_i18n.get(lang) or next(
                    iter(page.meta_description_i18n.values()), ''
                )
            if not slug:
                continue
            # Strip A/B suffix from title (e.g. "PicklyMenu [B]" -> skipped via sort_order, but also visual)
            import re as _re
            title = _re.sub(r'\s*\[[A-Z]\]\s*$', '', title)
            url = f"{base_url}/{lang}/{slug}/" if slug != 'home' else f"{base_url}/{lang}/"
            line = f"- [{title}]({url})"
            if description:
                line += f": {description}"
            lines.append(line)

    # Contact / metadata
    if settings_obj:
        contact_lines = []
        if getattr(settings_obj, 'contact_email', ''):
            contact_lines.append(f"- Email: {settings_obj.contact_email}")
        if getattr(settings_obj, 'contact_phone', ''):
            contact_lines.append(f"- Phone: {settings_obj.contact_phone}")
        if contact_lines:
            lines.append("")
            lines.append("## Contact")
            lines.append("")
            lines.extend(contact_lines)

    lines.append("")
    lines.append("---")
    lines.append(f"Generated by DjangoPress · {request.build_absolute_uri('/')}")

    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")


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
    path('llms.txt', llms_txt, name='llms_txt'),
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
