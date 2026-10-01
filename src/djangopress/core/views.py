import re

from django.conf import settings
from django.views.generic import TemplateView
from django.contrib import messages
from django.http import Http404, HttpResponseRedirect, JsonResponse
from django.utils import translation
from django.utils.translation import get_language
from django.views.decorators.http import require_POST

from django.core.cache import cache
from django.urls import translate_url

from .models import Page, DynamicForm, FormSubmission, SiteSettings


class PageView(TemplateView):
    """Dynamic page view that renders pages from the Page model"""
    template_name = 'core/page.html'

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        if request.user.is_authenticated:
            # Authenticated users get no-store to prevent stale content after edits
            response['Cache-Control'] = 'no-store'
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get the page slug from URL or resolve homepage
        page_slug = kwargs.get('slug')
        if not page_slug:
            site_settings = SiteSettings.load()
            homepage = None
            if site_settings and site_settings.homepage_id:
                homepage = site_settings.homepage
            if not homepage:
                homepage = Page.objects.filter(is_active=True).order_by('sort_order', 'pk').first()
            if homepage:
                current_lang = get_language() or 'pt'
                page_slug = homepage.get_slug(current_lang)
            if not page_slug:
                raise Http404("No pages exist yet")

        # Get current language
        current_lang = get_language()

        # Preview mode: staff can see inactive pages with ?preview=true
        preview_mode = (
            self.request.user.is_staff and self.request.GET.get('preview') == 'true'
        )

        # Get the page object via cached slug index
        page_obj = Page.get_by_slug(page_slug, current_lang, include_inactive=preview_mode)
        if not page_obj:
            raise Http404(f"Page '{page_slug}' not found for language '{current_lang}'")

        context['page_obj'] = page_obj
        context['page'] = page_slug
        context['preview_mode'] = preview_mode

        # Render page HTML content
        language = current_lang or 'pt'

        # Get default language from SiteSettings
        site_settings = SiteSettings.load()
        default_lang = site_settings.get_default_language() if site_settings else 'pt'

        # Get per-language HTML (with fallback to default language)
        html_i18n = page_obj.html_content_i18n or {}
        html = html_i18n.get(language) or html_i18n.get(default_lang) or ''

        if html:
            from django.template import Template, RequestContext

            try:
                template = Template(html)
                render_context = {
                    'LANGUAGE_CODE': language,
                    'page': page_obj,
                    **context,
                }
                context['page_content'] = template.render(
                    RequestContext(self.request, render_context)
                )
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Template error rendering page '{page_slug}' (id={page_obj.id}): {e}")
                if self.request.user.is_staff:
                    context['page_content'] = (
                        f'<div class="max-w-3xl mx-auto my-12 p-6 bg-red-50 border border-red-200 rounded-lg">'
                        f'<h2 class="text-xl font-bold text-red-700 mb-2">Template Error</h2>'
                        f'<p class="text-red-600 mb-4">{e}</p>'
                        f'<p class="text-sm text-red-500">This page has corrupted template syntax. '
                        f'Go to <a href="/backoffice/page/{page_obj.id}/edit/" class="underline">Page Settings</a> '
                        f'to restore from a previous version.</p></div>'
                    )
                else:
                    raise
        else:
            context['page_content'] = ''

        # Enable edit mode for authenticated users with ?edit=true or ?edit=v2
        edit_param = self.request.GET.get('edit')
        if self.request.user.is_authenticated and edit_param in ('true', 'v2'):
            context['edit_mode'] = 'v2'
        else:
            context['edit_mode'] = False

        # SEO context
        context['seo_title'] = page_obj.get_meta_title(language)
        context['seo_description'] = page_obj.get_meta_description(language)
        context['og_image_url'] = page_obj.og_image.url if page_obj.og_image else None
        context['canonical_url'] = self.request.build_absolute_uri(page_obj.get_absolute_url())

        return context


@require_POST
def form_submit(request, slug):
    """Handle dynamic form submissions."""
    from .services.forms import process_submission

    try:
        form_def = DynamicForm.objects.get(slug=slug, is_active=True)
    except DynamicForm.DoesNotExist:
        if _is_ajax(request):
            return JsonResponse({'success': False, 'error': 'Form not found.'}, status=404)
        raise Http404("Form not found.")

    # Get IP early (needed for rate limiting)
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    ip = x_forwarded.split(',')[0].strip() if x_forwarded else request.META.get('REMOTE_ADDR')

    # Collect POST fields, excluding Django internals
    data = {}
    for key, value in request.POST.items():
        if key in ('csrfmiddlewaretoken',):
            continue
        data[key] = True if value == 'on' else value

    # Honeypot check — bots fill hidden fields, humans don't
    HONEYPOT_FIELD = 'website_url'
    if data.pop(HONEYPOT_FIELD, ''):
        # Silently return fake success (don't tip off the bot)
        lang = get_language() or 'en'
        if _is_ajax(request):
            return JsonResponse({'success': True, 'message': form_def.get_success_message(lang)})
        messages.success(request, form_def.get_success_message(lang))
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))
    else:
        data.pop(HONEYPOT_FIELD, None)

    # Rate limit: max 5 submissions per IP per form per hour
    rate_key = f'form_rate_{slug}_{ip}'
    submission_count = cache.get(rate_key, 0)
    if submission_count >= 5:
        msg = 'Too many submissions. Please try again later.'
        if _is_ajax(request):
            return JsonResponse({'success': False, 'message': msg}, status=429)
        messages.error(request, msg)
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))

    # Validate
    errors = form_def.validate_submission(data)
    if errors:
        if _is_ajax(request):
            return JsonResponse({'success': False, 'errors': errors}, status=400)
        for field, msg in errors.items():
            messages.error(request, msg)
        referer = request.META.get('HTTP_REFERER', '/')
        return HttpResponseRedirect(referer)

    # Determine source page from referer
    source_page = None
    referer = request.META.get('HTTP_REFERER', '')
    if referer:
        from urllib.parse import urlparse
        path = urlparse(referer).path.strip('/')
        # Strip language prefix
        parts = path.split('/', 1)
        page_slug = parts[1] if len(parts) > 1 else parts[0]
        if page_slug:
            lang = get_language() or 'en'
            source_page = Page.get_by_slug(page_slug, lang)

    process_submission(form_def, data, get_language() or '', ip, request.META.get('HTTP_USER_AGENT', ''),
                       source_page=source_page)

    # Increment rate limit counter
    cache.set(rate_key, submission_count + 1, 3600)

    if _is_ajax(request):
        lang = get_language() or 'en'
        return JsonResponse({
            'success': True,
            'message': form_def.get_success_message(lang),
        })

    lang = get_language() or 'en'
    messages.success(request, form_def.get_success_message(lang))
    referer = request.META.get('HTTP_REFERER', '/')
    return HttpResponseRedirect(referer)


def _is_ajax(request):
    return (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or 'application/json' in request.headers.get('Accept', '')
    )


@require_POST
def set_language(request):
    """
    Custom language switcher that redirects to the correct URL in the target
    language, handling both language prefixes and per-language page slugs.

    Django's built-in set_language redirects to `next` as-is, but that URL
    contains the OLD language prefix and slug — so the middleware re-activates
    the old language and the switch never takes effect.
    """
    target_lang = request.POST.get('language', '')
    available = [code for code, _ in settings.LANGUAGES]
    if target_lang not in available:
        return HttpResponseRedirect('/')

    next_url = request.POST.get('next', request.META.get('HTTP_REFERER', '/'))

    # Strip existing language prefix from the URL: /en/about/ → /about/
    lang_prefix_re = re.compile(r'^/(' + '|'.join(re.escape(c) for c in available) + r')(/|$)')
    match = lang_prefix_re.match(next_url)
    source_lang = match.group(1) if match else None
    stripped_path = lang_prefix_re.sub('/', next_url) if match else next_url
    slug = stripped_path.strip('/')

    # A CMS page's address is data, so only the database knows its slug in the
    # other language. Try that first.
    redirect_url = None
    target_slug = slug
    if slug:
        check_lang = source_lang or translation.get_language()
        page = Page.get_by_slug(slug, check_lang)
        if page:
            target_slug = page.get_slug(target_lang) or slug
            redirect_url = f'/{target_lang}/{target_slug}/'
        else:
            # Not a page: it belongs to a decoupled app, whose prefix lives in
            # the URLconf as a lazily translated string — `path(_('shop/'), …)`.
            # Only resolving and reversing turns `/en/shop/` into `/pt/loja/`,
            # and the resolving half works only while the SOURCE language is
            # active: under any other language that path is not in the URLconf
            # at all, and translate_url quietly hands back what it was given.
            with translation.override(check_lang):
                translated = translate_url(next_url, target_lang)
            if translated != next_url:
                redirect_url = translated

    # Neither a known page nor a reversible route. Land the visitor in the
    # language they asked for and let the usual 404 handling take it from there.
    if redirect_url is None:
        redirect_url = f'/{target_lang}/{target_slug}/' if target_slug else f'/{target_lang}/'

    # Activate the target language and set cookie
    translation.activate(target_lang)

    response = HttpResponseRedirect(redirect_url)
    response.set_cookie(
        settings.LANGUAGE_COOKIE_NAME,
        target_lang,
        max_age=settings.LANGUAGE_COOKIE_AGE or 365 * 24 * 60 * 60,
        path=settings.LANGUAGE_COOKIE_PATH or '/',
        domain=settings.LANGUAGE_COOKIE_DOMAIN,
        secure=settings.LANGUAGE_COOKIE_SECURE,
        httponly=settings.LANGUAGE_COOKIE_HTTPONLY,
        samesite=settings.LANGUAGE_COOKIE_SAMESITE or 'Lax',
    )
    return response
