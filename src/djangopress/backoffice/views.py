import json

from django.views.generic import TemplateView, ListView, CreateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from djangopress.core.decorators import SuperuserRequiredMixin
from django.http import HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse_lazy

from django.conf.global_settings import LANGUAGES as ALL_LANGUAGES
from djangopress.core.models import SiteSettings, SiteImage, Page, GOOGLE_FONTS_CHOICES, GlobalSection, Blueprint, BlueprintPage, DynamicForm, FormSubmission
from djangopress.core.utils import resize_and_compress_image
from django.utils.text import slugify
from djangopress.news.models import NewsPost


class MediaDetailView(LoginRequiredMixin, TemplateView):
    """Media image detail/edit view"""
    template_name = 'backoffice/media_detail.html'

    def get_context_data(self, **kwargs):
        from PIL import Image as PILImage
        from django.db.models import Q
        import os

        context = super().get_context_data(**kwargs)
        pk = kwargs.get('pk')

        try:
            image = SiteImage.objects.get(pk=pk)
        except SiteImage.DoesNotExist:
            context['image'] = None
            return context

        context['image'] = image

        # Languages
        site_settings = SiteSettings.load()
        context['languages'] = site_settings.get_enabled_languages()

        # File info
        try:
            if image.is_pdf and image.file and image.file.storage.exists(image.file.name):
                context['file_size'] = image.file.size
                context['dimensions'] = None
            elif image.image and image.image.storage.exists(image.image.name):
                context['file_size'] = image.image.size
                try:
                    img = PILImage.open(image.image)
                    context['dimensions'] = f"{img.width} x {img.height}"
                    img.close()
                except Exception:
                    context['dimensions'] = 'Unknown'
            else:
                context['file_size'] = 0
                context['dimensions'] = 'Unknown'
        except Exception:
            context['file_size'] = 0
            context['dimensions'] = 'Unknown'

        # Usage count: scan pages for this media URL
        usage_count = 0
        media_url = image.url
        if media_url:
            for page in Page.objects.all():
                html_i18n = page.html_content_i18n or {}
                found = any(
                    lang_html and media_url in lang_html
                    for lang_html in html_i18n.values()
                )
                if found:
                    usage_count += 1
        context['usage_count'] = usage_count

        # Prev/next navigation (same -id ordering as list view)
        all_ids = list(SiteImage.objects.order_by('-id').values_list('id', flat=True))
        try:
            idx = all_ids.index(pk)
            context['prev_image'] = SiteImage.objects.get(pk=all_ids[idx - 1]) if idx > 0 else None
            context['next_image'] = SiteImage.objects.get(pk=all_ids[idx + 1]) if idx < len(all_ids) - 1 else None
        except (ValueError, SiteImage.DoesNotExist):
            context['prev_image'] = None
            context['next_image'] = None

        return context

    def post(self, request, *args, **kwargs):
        from django.db import IntegrityError

        pk = kwargs.get('pk')
        try:
            image = SiteImage.objects.get(pk=pk)
        except SiteImage.DoesNotExist:
            messages.error(request, 'Image not found.')
            return redirect('backoffice:media')

        action = request.POST.get('action')

        if action == 'delete':
            title = str(image)
            image.delete()
            messages.success(request, f'Image "{title}" deleted.')
            return redirect('backoffice:media')

        # Update fields
        site_settings = SiteSettings.load()
        lang_codes = site_settings.get_language_codes()

        title_i18n = {}
        alt_text_i18n = {}
        for lang in lang_codes:
            t = request.POST.get(f'title_{lang}', '').strip()
            a = request.POST.get(f'alt_text_{lang}', '').strip()
            if t:
                title_i18n[lang] = t
            if a:
                alt_text_i18n[lang] = a

        image.title_i18n = title_i18n
        image.alt_text_i18n = alt_text_i18n
        image.key = request.POST.get('key', '').strip()
        image.tags = request.POST.get('tags', '').strip()
        image.description = request.POST.get('description', '').strip()
        image.is_active = 'is_active' in request.POST

        # Replace file
        if 'file' in request.FILES:
            image.file = request.FILES['file']
        elif 'image' in request.FILES:
            image.image = request.FILES['image']

        try:
            image.save()
            messages.success(request, f'Image "{image}" updated successfully!')
        except IntegrityError:
            messages.error(request, f'An image with key "{image.key}" already exists. Please choose a different key.')
            return redirect('backoffice:media_detail', pk=pk)

        return redirect('backoffice:media_detail', pk=pk)


class DashboardView(LoginRequiredMixin, TemplateView):
    """Main dashboard view"""
    template_name = 'backoffice/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get statistics
        context['total_images'] = SiteImage.objects.count()
        context['active_images'] = SiteImage.objects.filter(is_active=True).count()

        # Page statistics
        context['total_pages'] = Page.objects.count()
        context['active_pages'] = Page.objects.filter(is_active=True).count()

        # News statistics
        context['total_news_posts'] = NewsPost.objects.count()
        context['published_news_posts'] = NewsPost.objects.filter(is_published=True).count()

        # Recent activity
        recent_images = list(SiteImage.objects.order_by('-uploaded_at')[:3])

        # Create activity log
        activity_log = []

        for image in recent_images:
            activity_log.append({
                'type': 'image',
                'title': image.title,
                'action': 'uploaded',
                'date': image.uploaded_at,
                'url': '/backoffice/media/',
                'icon': 'image'
            })

        # Sort by date and limit to 10
        activity_log.sort(key=lambda x: x['date'], reverse=True)
        context['activity_log'] = activity_log[:10]

        return context


class MediaView(LoginRequiredMixin, ListView):
    """Media library management - list all site media (images and documents)"""
    model = SiteImage
    template_name = 'backoffice/media.html'
    context_object_name = 'images'
    paginate_by = 24

    def get_queryset(self):
        qs = SiteImage.objects.order_by('-id')
        file_type = self.request.GET.get('type')
        if file_type == 'images':
            qs = qs.filter(file_type='image')
        elif file_type == 'documents':
            qs = qs.filter(file_type='document')
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_type'] = self.request.GET.get('type', 'all')
        return context


class MediaUploadView(LoginRequiredMixin, CreateView):
    """Upload new media/site image"""
    model = SiteImage
    template_name = 'backoffice/media_upload.html'
    fields = ['title', 'key', 'image', 'alt_text', 'is_active']

    def get_success_url(self):
        return reverse_lazy('backoffice:media')

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            f'Image "{self.object.title}" uploaded successfully!'
        )
        return response


class MediaBulkUploadView(LoginRequiredMixin, TemplateView):
    """Bulk upload multiple files (images and PDFs) to media library"""
    template_name = 'backoffice/media_bulk_upload.html'

    ALLOWED_PDF_TYPES = ['application/pdf']
    ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
    MAX_PDF_SIZE = 20 * 1024 * 1024  # 20MB

    def post(self, request, *args, **kwargs):
        files = request.FILES.getlist('images')

        if not files:
            messages.error(request, 'No files were uploaded. Please try again.')
            return redirect('backoffice:media_bulk_upload')

        uploaded_count = 0
        optimized_count = 0
        skipped_count = 0
        lang_codes = SiteSettings.load().get_language_codes()

        for uploaded_file in files:
            try:
                content_type = uploaded_file.content_type
                is_pdf = content_type in self.ALLOWED_PDF_TYPES
                is_image = content_type in self.ALLOWED_IMAGE_TYPES

                if not is_pdf and not is_image:
                    messages.error(request, f"Skipped {uploaded_file.name}: unsupported file type ({content_type})")
                    continue

                if is_pdf and uploaded_file.size > self.MAX_PDF_SIZE:
                    messages.error(request, f"Skipped {uploaded_file.name}: exceeds 20MB limit")
                    continue

                # Auto-generate title and key from filename
                filename_without_ext = uploaded_file.name.rsplit('.', 1)[0]
                title = filename_without_ext.replace('_', ' ').replace('-', ' ').title()
                base_key = slugify(filename_without_ext)

                # Ensure unique key
                key = base_key
                counter = 1
                while SiteImage.objects.filter(key=key).exists():
                    key = f"{base_key}-{counter}"
                    counter += 1

                site_image = SiteImage(
                    title_i18n={lang: title for lang in lang_codes},
                    alt_text_i18n={lang: title for lang in lang_codes},
                    key=key,
                    is_active=True,
                    file_type='document' if is_pdf else 'image',
                )

                if is_pdf:
                    site_image.file.save(uploaded_file.name, uploaded_file, save=False)
                    skipped_count += 1
                else:
                    image_size_kb = uploaded_file.size / 1024
                    if image_size_kb > 400:
                        processed = resize_and_compress_image(uploaded_file)
                        optimized_count += 1
                    else:
                        processed = uploaded_file
                        skipped_count += 1
                    site_image.image.save(uploaded_file.name, processed, save=False)

                site_image.save()
                uploaded_count += 1

            except Exception as e:
                messages.error(request, f"Error uploading {uploaded_file.name}: {str(e)}")

        # Success message with details
        if uploaded_count > 0:
            details = []
            if optimized_count > 0:
                details.append(f"{optimized_count} optimized")
            if skipped_count > 0:
                details.append(f"{skipped_count} kept original")

            detail_text = f" ({', '.join(details)})" if details else ""
            messages.success(request, f"Successfully uploaded {uploaded_count} file(s){detail_text}!")
        else:
            messages.error(request, "No files were uploaded. Please try again.")

        return redirect('backoffice:media')


class PagesView(LoginRequiredMixin, TemplateView):
    """Pages management - list of pages using new Page model"""
    template_name = 'backoffice/pages.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get all pages (uses model default ordering: sort_order, created_at)
        pages = Page.objects.all()
        context['total_pages'] = pages.count()
        context['active_pages'] = pages.filter(is_active=True).count()

        # Get enabled languages for create form and translation status
        site_settings = SiteSettings.objects.first()
        if site_settings:
            context['languages'] = site_settings.get_enabled_languages()
            language_codes = site_settings.get_language_codes()
        else:
            context['languages'] = [('pt', 'Portuguese'), ('en', 'English')]
            language_codes = ['pt', 'en']

        # Annotate pages with translation status
        for page in pages:
            html_i18n = page.html_content_i18n or {}
            page.lang_status = [
                (lang, bool(html_i18n.get(lang)))
                for lang in language_codes
            ]
            page.has_any_content = bool(html_i18n)

        context['pages'] = pages
        context['language_codes'] = language_codes

        return context

    def post(self, request, *args, **kwargs):
        """Handle page creation"""
        action = request.POST.get('action')

        if action == 'bulk_create':
            # Get enabled languages
            site_settings = SiteSettings.objects.first()
            if site_settings:
                lang_codes = site_settings.get_language_codes()
            else:
                lang_codes = ['pt', 'en']

            # Collect per-language title/slug lists
            lang_titles = {}
            lang_slugs = {}
            for code in lang_codes:
                lang_titles[code] = request.POST.getlist(f'title_{code}[]')
                lang_slugs[code] = request.POST.getlist(f'slug_{code}[]')

            # Determine number of pages from first language's title list
            num_pages = len(lang_titles.get(lang_codes[0], []))

            created_pages = []
            skipped_pages = []

            for i in range(num_pages):
                title_i18n = {}
                slug_i18n = {}
                for code in lang_codes:
                    t = lang_titles[code][i].strip() if i < len(lang_titles[code]) else ''
                    s = lang_slugs[code][i].strip() if i < len(lang_slugs[code]) else ''
                    if t:
                        title_i18n[code] = t
                    if s:
                        slug_i18n[code] = s

                if not title_i18n or not slug_i18n:
                    continue

                # Check for duplicate slugs
                duplicate = False
                for code, slug_val in slug_i18n.items():
                    for existing_page in Page.objects.all():
                        if existing_page.get_slug(code) == slug_val:
                            display_title = title_i18n.get(lang_codes[0], list(title_i18n.values())[0])
                            skipped_pages.append(f'{display_title} (slug "{slug_val}" already exists for {code})')
                            duplicate = True
                            break
                    if duplicate:
                        break
                if duplicate:
                    continue

                page = Page.objects.create(
                    title_i18n=title_i18n,
                    slug_i18n=slug_i18n,
                    is_active=True
                )
                created_pages.append(page.default_title)

            if created_pages:
                messages.success(request, f'Successfully created {len(created_pages)} page(s): {", ".join(created_pages)}')
            if skipped_pages:
                messages.warning(request, f'Skipped {len(skipped_pages)} page(s): {", ".join(skipped_pages)}')
            if not created_pages and not skipped_pages:
                messages.error(request, 'No valid pages to create.')

        elif action == 'delete':
            page_id = request.POST.get('page_id')
            try:
                page = Page.objects.get(pk=page_id)
                page_title = page.default_title
                page.delete()
                messages.success(request, f'Page "{page_title}" deleted successfully!')
            except Page.DoesNotExist:
                messages.error(request, 'Page not found.')

        return redirect('backoffice:pages')


class PagesExplorerView(LoginRequiredMixin, TemplateView):
    """Pages explorer - sidebar + detail panel view"""
    template_name = 'backoffice/pages_explorer.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        pages = Page.objects.all()
        context['pages'] = pages
        context['total_pages'] = pages.count()
        context['active_pages'] = pages.filter(is_active=True).count()

        site_settings = SiteSettings.objects.first()
        if site_settings:
            context['languages'] = site_settings.get_enabled_languages()
        else:
            context['languages'] = [('pt', 'Portuguese'), ('en', 'English')]

        return context


class PageEditView(LoginRequiredMixin, TemplateView):
    """Edit page details (slug, title, active status)"""
    template_name = 'backoffice/page_edit.html'

    def get_context_data(self, **kwargs):
        from djangopress.core.models import PageVersion, SiteSettings
        context = super().get_context_data(**kwargs)
        page_id = kwargs.get('page_id')

        try:
            page = Page.objects.get(pk=page_id)
            context['page'] = page

            # Get version history
            context['versions'] = PageVersion.objects.filter(page=page).order_by('-version_number')[:10]

            # Get enabled languages for the form
            site_settings = SiteSettings.objects.first()
            context['languages'] = site_settings.get_enabled_languages() if site_settings else [('pt', 'Portuguese'), ('en', 'English')]

            context['all_pages'] = Page.objects.all()

            # AI REFINE MODAL DATA
            # Build reference pages list (exclude current page and pages with no HTML content)
            reference_pages = []
            for ref_page in Page.objects.all().order_by('-created_at'):
                # Skip current page
                if ref_page.id == page_id:
                    continue

                ref_html_i18n = ref_page.html_content_i18n or {}
                has_content = bool(ref_html_i18n)
                if has_content:
                    reference_pages.append({
                        'id': ref_page.id,
                        'title': ref_page.default_title,
                        'slug': ref_page.default_slug,
                    })
            context['reference_pages'] = reference_pages

            # Default language for AI form
            context['default_language'] = site_settings.get_default_language() if site_settings else 'pt'

            # Translation status for this page
            html_i18n = page.html_content_i18n or {}
            lang_codes = site_settings.get_language_codes() if site_settings else ['pt']
            lang_status = [
                (lang, bool(html_i18n.get(lang)))
                for lang in lang_codes
            ]
            context['lang_status'] = lang_status
            context['has_missing_translations'] = any(not has for _, has in lang_status)

            # Get AI configuration
            try:
                from djangopress.ai.utils.llm_config import LLMConfig
                config = LLMConfig()
                context['ai_models'] = config.get_available_models()
                context['default_model'] = config.default_model
            except Exception:
                context['ai_models'] = []
                context['default_model'] = None

        except Page.DoesNotExist:
            context['page'] = None
            context['versions'] = []
            context['languages'] = [('pt', 'Portuguese'), ('en', 'English')]
            context['all_pages'] = []
            context['reference_pages'] = []
            context['ai_models'] = []
            context['default_model'] = None

        return context

    def post(self, request, *args, **kwargs):
        """Handle page update"""
        from djangopress.core.models import SiteSettings
        page_id = kwargs.get('page_id')

        try:
            page = Page.objects.get(pk=page_id)

            # Get enabled languages
            site_settings = SiteSettings.objects.first()
            languages = site_settings.get_language_codes() if site_settings else ['pt', 'en']

            # Get form data for i18n fields
            title_i18n = {}
            slug_i18n = {}

            for lang in languages:
                title = request.POST.get(f'title_{lang}', '').strip()
                slug = request.POST.get(f'slug_{lang}', '').strip()

                if title:
                    title_i18n[lang] = title
                if slug:
                    slug_i18n[lang] = slug

            is_active = 'is_active' in request.POST

            # Validation
            if not title_i18n or not slug_i18n:
                messages.error(request, 'Title and slug are required for at least one language.')
                return redirect('backoffice:page_edit', page_id=page_id)

            # Check for duplicate slugs across all languages
            for lang, slug in slug_i18n.items():
                for other_page in Page.objects.exclude(pk=page_id):
                    if other_page.get_slug(lang) == slug:
                        messages.error(request, f'Page with slug "{slug}" already exists for language "{lang}".')
                        return redirect('backoffice:page_edit', page_id=page_id)

            # Update SEO fields
            meta_title_i18n = {}
            meta_description_i18n = {}
            for lang in languages:
                mt = request.POST.get(f'meta_title_{lang}', '').strip()
                md = request.POST.get(f'meta_description_{lang}', '').strip()
                if mt:
                    meta_title_i18n[lang] = mt
                if md:
                    meta_description_i18n[lang] = md

            # Update OG image
            if 'og_image' in request.FILES:
                page.og_image = request.FILES['og_image']

            # Update page
            page.title_i18n = title_i18n
            page.slug_i18n = slug_i18n
            page.meta_title_i18n = meta_title_i18n
            page.meta_description_i18n = meta_description_i18n
            page.is_active = is_active

            # Set user for version tracking
            if request.user.is_authenticated:
                page._snapshot_user = request.user

            # Set change summary if provided
            change_summary = request.POST.get('change_summary', '')
            if change_summary:
                page._change_summary = change_summary

            page.save()

            messages.success(request, f'Page "{page.get_title()}" updated successfully!')
            return redirect('backoffice:pages')

        except Page.DoesNotExist:
            messages.error(request, 'Page not found.')
            return redirect('backoffice:pages')


class SettingsView(LoginRequiredMixin, TemplateView):
    """Site settings hub — cards linking to child pages"""
    template_name = 'backoffice/settings.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        site_settings, _ = SiteSettings.objects.get_or_create(pk=1)
        context['settings'] = site_settings

        # Integrations summary for hub card
        from djangopress.ai.utils.llm_config import get_env
        integrations = [
            bool(get_env('GEMINI_API_KEY')),
            bool(get_env('OPENAI_API_KEY')),
            bool(get_env('ANTHROPIC_API_KEY')),
            bool(get_env('MAILGUN_API_KEY')),
            bool(get_env('GS_BUCKET_NAME')),
        ]
        context['integrations_configured'] = sum(integrations)
        context['integrations_total'] = len(integrations)

        return context


class SettingsGeneralView(LoginRequiredMixin, TemplateView):
    """General settings: site name, description, briefing, logos, domain"""
    template_name = 'backoffice/settings/general.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        site_settings, _ = SiteSettings.objects.get_or_create(pk=1)
        context['settings'] = site_settings
        context['site_name_i18n_json'] = json.dumps(site_settings.site_name_i18n or {})
        context['site_description_i18n_json'] = json.dumps(site_settings.site_description_i18n or {})
        context['pages'] = Page.objects.filter(is_active=True).order_by('sort_order', 'pk')
        return context

    def post(self, request, *args, **kwargs):
        settings, _ = SiteSettings.objects.get_or_create(pk=1)

        for i18n_field in ('site_name_i18n', 'site_description_i18n'):
            raw = request.POST.get(i18n_field, '')
            if raw:
                try:
                    setattr(settings, i18n_field, json.loads(raw))
                except (ValueError, TypeError):
                    pass

        settings.project_briefing = request.POST.get('project_briefing', '')
        settings.domain = request.POST.get('domain', settings.domain)
        settings.maintenance_mode = 'maintenance_mode' in request.POST

        # Homepage
        homepage_id = request.POST.get('homepage', '')
        if homepage_id:
            settings.homepage_id = int(homepage_id)
        else:
            settings.homepage_id = None

        if 'logo' in request.FILES:
            settings.logo = request.FILES['logo']
        if 'logo_dark_bg' in request.FILES:
            settings.logo_dark_bg = request.FILES['logo_dark_bg']
        if 'favicon' in request.FILES:
            settings.favicon = request.FILES['favicon']

        settings.save()
        messages.success(request, 'General settings updated successfully!')
        return redirect('backoffice:settings_general')


class SettingsLanguagesView(LoginRequiredMixin, TemplateView):
    """Language settings — AJAX save via existing API endpoint"""
    template_name = 'backoffice/settings/languages.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        site_settings, _ = SiteSettings.objects.get_or_create(pk=1)
        context['settings'] = site_settings
        context['available_languages'] = ALL_LANGUAGES
        return context


class SettingsContactView(LoginRequiredMixin, TemplateView):
    """Contact info and social media links"""
    template_name = 'backoffice/settings/contact.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        site_settings, _ = SiteSettings.objects.get_or_create(pk=1)
        context['settings'] = site_settings
        context['contact_address_i18n_json'] = json.dumps(site_settings.contact_address_i18n or {})
        return context

    def post(self, request, *args, **kwargs):
        settings, _ = SiteSettings.objects.get_or_create(pk=1)

        raw = request.POST.get('contact_address_i18n', '')
        if raw:
            try:
                settings.contact_address_i18n = json.loads(raw)
            except (ValueError, TypeError):
                pass

        settings.contact_email = request.POST.get('contact_email', settings.contact_email)
        settings.contact_phone = request.POST.get('contact_phone', '')
        settings.facebook_url = request.POST.get('facebook_url', '')
        settings.instagram_url = request.POST.get('instagram_url', '')
        settings.linkedin_url = request.POST.get('linkedin_url', '')
        settings.twitter_url = request.POST.get('twitter_url', '')
        settings.youtube_url = request.POST.get('youtube_url', '')
        settings.google_maps_embed_url = request.POST.get('google_maps_embed_url', '')
        settings.whatsapp_number = request.POST.get('whatsapp_number', '')
        settings.tiktok_url = request.POST.get('tiktok_url', '')
        settings.pinterest_url = request.POST.get('pinterest_url', '')

        settings.save()
        messages.success(request, 'Contact & social settings updated successfully!')
        return redirect('backoffice:settings_contact')


class SettingsSEOView(LoginRequiredMixin, TemplateView):
    """SEO, analytics, code injection, and Open Graph defaults"""
    template_name = 'backoffice/settings/seo.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        site_settings, _ = SiteSettings.objects.get_or_create(pk=1)
        context['settings'] = site_settings
        context['default_og_description_i18n_json'] = json.dumps(site_settings.default_og_description_i18n or {})
        return context

    def post(self, request, *args, **kwargs):
        settings, _ = SiteSettings.objects.get_or_create(pk=1)

        settings.meta_keywords = request.POST.get('meta_keywords', '')
        settings.google_analytics_id = request.POST.get('google_analytics_id', '')

        # Code injection
        settings.custom_head_code = request.POST.get('custom_head_code', '')
        settings.custom_body_code = request.POST.get('custom_body_code', '')

        # Open Graph defaults
        if 'og_image' in request.FILES:
            settings.og_image = request.FILES['og_image']
        if request.POST.get('og_image_clear') == '1':
            settings.og_image = None

        raw = request.POST.get('default_og_description_i18n', '')
        if raw:
            try:
                settings.default_og_description_i18n = json.loads(raw)
            except (ValueError, TypeError):
                pass

        settings.save()
        messages.success(request, 'SEO & Code settings updated successfully!')
        return redirect('backoffice:settings_seo')


class SettingsDesignSystemView(LoginRequiredMixin, TemplateView):
    """Design — guide, colors, typography, layout, buttons"""
    template_name = 'backoffice/settings/design_system.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        site_settings, _ = SiteSettings.objects.get_or_create(pk=1)
        context['settings'] = site_settings
        context['google_fonts'] = GOOGLE_FONTS_CHOICES

        # Design guide: pages + AI models
        all_active_pages = Page.objects.filter(is_active=True).order_by('id')
        context['pages_with_content'] = [
            p for p in all_active_pages
            if p.html_content_i18n and any(p.html_content_i18n.values())
        ]

        try:
            from djangopress.ai.utils.llm_config import LLMConfig
            config = LLMConfig()
            context['ai_models'] = config.get_available_models()
            context['default_model'] = config.default_model
        except Exception:
            context['ai_models'] = []
            from djangopress.ai.utils.llm_config import get_ai_model
            context['default_model'] = get_ai_model('generation')

        # Color fields
        context['color_fields'] = [
            {'name': 'primary_color', 'label': 'Primary Color', 'value': site_settings.primary_color},
            {'name': 'primary_color_hover', 'label': 'Primary Hover', 'value': site_settings.primary_color_hover},
            {'name': 'secondary_color', 'label': 'Secondary Color', 'value': site_settings.secondary_color},
            {'name': 'accent_color', 'label': 'Accent Color', 'value': site_settings.accent_color},
            {'name': 'background_color', 'label': 'Background Color', 'value': site_settings.background_color},
            {'name': 'text_color', 'label': 'Text Color', 'value': site_settings.text_color},
            {'name': 'heading_color', 'label': 'Heading Color', 'value': site_settings.heading_color},
        ]

        # Heading levels for template loop
        context['heading_levels'] = [
            {'prefix': 'h1', 'label': 'H1', 'font_value': site_settings.h1_font, 'size_value': site_settings.h1_size},
            {'prefix': 'h2', 'label': 'H2', 'font_value': site_settings.h2_font, 'size_value': site_settings.h2_size},
            {'prefix': 'h3', 'label': 'H3', 'font_value': site_settings.h3_font, 'size_value': site_settings.h3_size},
            {'prefix': 'h4', 'label': 'H4', 'font_value': site_settings.h4_font, 'size_value': site_settings.h4_size},
            {'prefix': 'h5', 'label': 'H5', 'font_value': site_settings.h5_font, 'size_value': site_settings.h5_size},
            {'prefix': 'h6', 'label': 'H6', 'font_value': site_settings.h6_font, 'size_value': site_settings.h6_size},
        ]

        context['tailwind_sizes'] = [
            'text-xs', 'text-sm', 'text-base', 'text-lg', 'text-xl',
            'text-2xl', 'text-3xl', 'text-4xl', 'text-5xl', 'text-6xl',
            'text-7xl', 'text-8xl', 'text-9xl',
        ]

        # Layout choices from model field
        context['container_width_choices'] = SiteSettings._meta.get_field('container_width').choices
        context['border_radius_choices'] = SiteSettings._meta.get_field('border_radius_preset').choices
        context['spacing_scale_choices'] = SiteSettings._meta.get_field('spacing_scale').choices
        context['shadow_preset_choices'] = SiteSettings._meta.get_field('shadow_preset').choices

        # Button choices from model field
        context['button_style_choices'] = SiteSettings._meta.get_field('button_style').choices
        context['button_size_choices'] = SiteSettings._meta.get_field('button_size').choices
        context['button_border_width_choices'] = SiteSettings._meta.get_field('button_border_width').choices

        # Button color fields
        context['primary_button_colors'] = [
            {'name': 'primary_button_bg', 'label': 'Background', 'value': site_settings.primary_button_bg},
            {'name': 'primary_button_text', 'label': 'Text', 'value': site_settings.primary_button_text},
            {'name': 'primary_button_border', 'label': 'Border', 'value': site_settings.primary_button_border},
            {'name': 'primary_button_hover', 'label': 'Hover', 'value': site_settings.primary_button_hover},
        ]
        context['secondary_button_colors'] = [
            {'name': 'secondary_button_bg', 'label': 'Background', 'value': site_settings.secondary_button_bg},
            {'name': 'secondary_button_text', 'label': 'Text', 'value': site_settings.secondary_button_text},
            {'name': 'secondary_button_border', 'label': 'Border', 'value': site_settings.secondary_button_border},
            {'name': 'secondary_button_hover', 'label': 'Hover', 'value': site_settings.secondary_button_hover},
        ]

        return context

    def post(self, request, *args, **kwargs):
        settings, _ = SiteSettings.objects.get_or_create(pk=1)

        # Design guide
        settings.design_guide = request.POST.get('design_guide', settings.design_guide)

        # Colors
        settings.primary_color = request.POST.get('primary_color', settings.primary_color)
        settings.primary_color_hover = request.POST.get('primary_color_hover', settings.primary_color_hover)
        settings.secondary_color = request.POST.get('secondary_color', settings.secondary_color)
        settings.accent_color = request.POST.get('accent_color', settings.accent_color)
        settings.background_color = request.POST.get('background_color', settings.background_color)
        settings.text_color = request.POST.get('text_color', settings.text_color)
        settings.heading_color = request.POST.get('heading_color', settings.heading_color)

        # Typography
        settings.heading_font = request.POST.get('heading_font', settings.heading_font)
        settings.body_font = request.POST.get('body_font', settings.body_font)
        for i in range(1, 7):
            setattr(settings, f'h{i}_font', request.POST.get(f'h{i}_font', getattr(settings, f'h{i}_font')))
            setattr(settings, f'h{i}_size', request.POST.get(f'h{i}_size', getattr(settings, f'h{i}_size')))

        # Layout
        settings.container_width = request.POST.get('container_width', settings.container_width)
        settings.border_radius_preset = request.POST.get('border_radius_preset', settings.border_radius_preset)
        settings.spacing_scale = request.POST.get('spacing_scale', settings.spacing_scale)
        settings.shadow_preset = request.POST.get('shadow_preset', settings.shadow_preset)

        # Buttons
        settings.button_style = request.POST.get('button_style', settings.button_style)
        settings.button_size = request.POST.get('button_size', settings.button_size)
        settings.button_border_width = request.POST.get('button_border_width', settings.button_border_width)

        for prefix in ('primary_button', 'secondary_button'):
            for suffix in ('bg', 'text', 'border', 'hover'):
                field = f'{prefix}_{suffix}'
                setattr(settings, field, request.POST.get(field, getattr(settings, field)))

        settings.save()
        messages.success(request, 'Design settings updated successfully!')
        return redirect('backoffice:settings_design')


class SettingsIntegrationsView(LoginRequiredMixin, TemplateView):
    """Integrations status — read-only"""
    template_name = 'backoffice/settings/integrations.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from djangopress.ai.utils.llm_config import get_env
        context['integrations'] = [
            {'name': 'Google Gemini', 'configured': bool(get_env('GEMINI_API_KEY')), 'description': 'AI generation (Gemini models)'},
            {'name': 'OpenAI', 'configured': bool(get_env('OPENAI_API_KEY')), 'description': 'AI generation (GPT models)'},
            {'name': 'Anthropic', 'configured': bool(get_env('ANTHROPIC_API_KEY')), 'description': 'AI generation (Claude models)'},
            {'name': 'Mailgun', 'configured': bool(get_env('MAILGUN_API_KEY')), 'description': 'Email delivery'},
            {'name': 'Google Cloud Storage', 'configured': bool(get_env('GS_BUCKET_NAME')), 'description': 'Media file storage'},
        ]
        return context


class SettingsAIModelsView(LoginRequiredMixin, SuperuserRequiredMixin, TemplateView):
    """AI model configuration — superuser only."""
    template_name = 'backoffice/settings/ai_models.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        site_settings, _ = SiteSettings.objects.get_or_create(pk=1)
        context['settings'] = site_settings

        from djangopress.ai.utils.llm_config import MODEL_CONFIG, AI_MODEL_DEFAULTS
        context['available_models'] = [
            {'key': k, 'name': f"{k} ({v.provider.value})", 'provider': v.provider.value}
            for k, v in MODEL_CONFIG.items()
        ]
        context['task_groups'] = [
            {
                'title': 'Content Generation',
                'tasks': [
                    {'key': 'generation', 'label': 'Page Generation', 'description': 'Creating new pages, site generation, bulk pages'},
                    {'key': 'refinement_page', 'label': 'Page Refinement', 'description': 'Full-page refinement and chat-based editing'},
                    {'key': 'refinement_section', 'label': 'Section Refinement', 'description': 'Individual section refinement in the editor'},
                    {'key': 'refinement_element', 'label': 'Element Refinement', 'description': 'Single element text/style refinement'},
                    {'key': 'header_footer', 'label': 'Header & Footer', 'description': 'Header and footer generation and refinement'},
                ],
            },
            {
                'title': 'Processing',
                'tasks': [
                    {'key': 'translation', 'label': 'Translation', 'description': 'HTML and text translation between languages'},
                    {'key': 'metadata', 'label': 'Metadata', 'description': 'Page titles, slugs, and metadata generation'},
                    {'key': 'image_analysis', 'label': 'Image Analysis', 'description': 'Image prompt suggestions, descriptions, and vision analysis'},
                    {'key': 'consistency', 'label': 'Design Consistency', 'description': 'Analyze and fix design inconsistencies across pages'},
                ],
            },
            {
                'title': 'Site Assistant',
                'tasks': [
                    {'key': 'assistant_router', 'label': 'Intent Router', 'description': 'Classifies user intents (lightweight)'},
                    {'key': 'assistant_executor', 'label': 'Executor', 'description': 'Executes tools and generates responses'},
                ],
            },
        ]
        context['defaults'] = AI_MODEL_DEFAULTS
        context['current_config'] = site_settings.ai_model_config or {}
        context['defaults_json'] = json.dumps(AI_MODEL_DEFAULTS)
        context['current_config_json'] = json.dumps(site_settings.ai_model_config or {})
        return context

    def post(self, request, *args, **kwargs):
        settings, _ = SiteSettings.objects.get_or_create(pk=1)
        from djangopress.ai.utils.llm_config import MODEL_CONFIG, AI_MODEL_DEFAULTS

        config = {}
        for task_key in AI_MODEL_DEFAULTS:
            model = request.POST.get(f'model_{task_key}', '')
            if model and model in MODEL_CONFIG:
                config[task_key] = model

        settings.ai_model_config = config
        settings.save(update_fields=['ai_model_config'])
        messages.success(request, 'AI model configuration updated!')
        return redirect('backoffice:settings_ai_models')


from django.http import JsonResponse
from djangopress.core.models import MenuItem


class MenuView(LoginRequiredMixin, TemplateView):
    """Navigation menu management"""
    template_name = 'backoffice/menu.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        all_items = list(MenuItem.objects.select_related('page', 'parent').all())
        context['pages'] = Page.objects.filter(is_active=True)

        # Get enabled languages
        site_settings = SiteSettings.objects.first()
        context['languages'] = site_settings.get_enabled_languages() if site_settings else [('pt', 'Portuguese'), ('en', 'English')]

        # Build tree-ordered list: top-level items interleaved with their children
        top_level = [i for i in all_items if i.parent_id is None]
        children_by_parent = {}
        for i in all_items:
            if i.parent_id is not None:
                children_by_parent.setdefault(i.parent_id, []).append(i)

        ordered_items = []
        prev_top_level_id = None
        for item in top_level:
            has_children = item.id in children_by_parent
            item.can_indent = prev_top_level_id is not None and not has_children
            item.can_outdent = False
            item.indent_parent_id = prev_top_level_id
            item.is_child = False
            ordered_items.append(item)
            for child in children_by_parent.get(item.id, []):
                child.can_indent = False
                child.can_outdent = True
                child.indent_parent_id = None
                child.is_child = True
                ordered_items.append(child)
            prev_top_level_id = item.id

        context['menu_items'] = ordered_items
        context['total_items'] = len(all_items)
        context['active_items'] = sum(1 for i in all_items if i.is_active)
        context['top_level_items'] = len(top_level)
        return context

    def post(self, request, *args, **kwargs):
        action = request.POST.get('action')

        if action == 'create':
            # Get enabled languages
            site_settings = SiteSettings.objects.first()
            lang_codes = site_settings.get_language_codes() if site_settings else ['pt', 'en']

            label_i18n = {}
            for lang in lang_codes:
                label = request.POST.get(f'label_{lang}', '').strip()
                if label:
                    label_i18n[lang] = label

            page_id = request.POST.get('page_id')
            url = request.POST.get('url', '').strip()
            parent_id = request.POST.get('parent_id')
            sort_order = int(request.POST.get('sort_order', 0))
            open_in_new_tab = 'open_in_new_tab' in request.POST
            css_class = request.POST.get('css_class', '').strip()

            if not label_i18n:
                messages.error(request, 'Label is required for at least one language.')
                return redirect('backoffice:menu')

            MenuItem.objects.create(
                label_i18n=label_i18n,
                page_id=int(page_id) if page_id else None,
                url=url,
                parent_id=int(parent_id) if parent_id else None,
                sort_order=sort_order,
                open_in_new_tab=open_in_new_tab,
                css_class=css_class,
            )

            messages.success(request, 'Menu item created.')

        elif action == 'update':
            item_id = request.POST.get('item_id')
            try:
                item = MenuItem.objects.get(pk=item_id)

                site_settings = SiteSettings.objects.first()
                lang_codes = site_settings.get_language_codes() if site_settings else ['pt', 'en']

                label_i18n = {}
                for lang in lang_codes:
                    label = request.POST.get(f'label_{lang}', '').strip()
                    if label:
                        label_i18n[lang] = label

                page_id = request.POST.get('page_id')
                item.label_i18n = label_i18n
                item.page_id = int(page_id) if page_id else None
                item.url = request.POST.get('url', '').strip()
                parent_id = request.POST.get('parent_id')
                item.parent_id = int(parent_id) if parent_id else None
                item.sort_order = int(request.POST.get('sort_order', 0))
                item.is_active = 'is_active' in request.POST
                item.open_in_new_tab = 'open_in_new_tab' in request.POST
                item.css_class = request.POST.get('css_class', '').strip()
                item.save()
    
                messages.success(request, 'Menu item updated.')
            except MenuItem.DoesNotExist:
                messages.error(request, 'Menu item not found.')

        elif action == 'delete':
            item_id = request.POST.get('item_id')
            try:
                item = MenuItem.objects.get(pk=item_id)
                item.delete()
    
                messages.success(request, 'Menu item deleted.')
            except MenuItem.DoesNotExist:
                messages.error(request, 'Menu item not found.')

        return redirect('backoffice:menu')



class AIGeneratePageView(SuperuserRequiredMixin, TemplateView):
    """AI Content Studio - Generate Page"""
    template_name = 'backoffice/ai_generate_page.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['total_pages'] = Page.objects.count()

        # Get AI configuration (if available)
        try:
            from djangopress.ai.utils.llm_config import LLMConfig
            config = LLMConfig()
            context['ai_models'] = config.get_available_models()
            context['default_model'] = config.default_model
        except:
            context['ai_models'] = []
            context['default_model'] = None

        # Load blueprint page data if provided
        blueprint_page_id = self.request.GET.get('blueprint_page_id')
        if blueprint_page_id:
            try:
                from djangopress.core.models import BlueprintPage
                bp_page = BlueprintPage.objects.get(pk=int(blueprint_page_id))
                context['blueprint_page'] = bp_page
                context['blueprint_page_id'] = bp_page.pk
                context['blueprint_title'] = bp_page.title
                context['blueprint_slug'] = bp_page.slug

                # Build brief from description + sections
                parts = []
                if bp_page.description:
                    parts.append(bp_page.description)
                if bp_page.sections:
                    parts.append('\nSections:')
                    for section in bp_page.sections:
                        title = section.get('title', '')
                        content = section.get('content', '')
                        if title:
                            parts.append(f'\n## {title}')
                        if content:
                            parts.append(content)
                context['blueprint_brief'] = '\n'.join(parts)
            except (BlueprintPage.DoesNotExist, ValueError, TypeError):
                pass

        return context


class AIBulkPagesView(SuperuserRequiredMixin, TemplateView):
    """AI Content Studio - Bulk Create Pages"""
    template_name = 'backoffice/ai_bulk_pages.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['total_pages'] = Page.objects.count()

        # Get AI configuration (if available)
        try:
            from djangopress.ai.utils.llm_config import LLMConfig
            config = LLMConfig()
            context['ai_models'] = config.get_available_models()
            context['default_model'] = config.default_model
        except:
            context['ai_models'] = []
            context['default_model'] = None

        return context


class AIBulkTranslateView(SuperuserRequiredMixin, TemplateView):
    """AI Content Studio - Bulk Translate Pages"""
    template_name = 'backoffice/ai_bulk_translate.html'

    def get_context_data(self, **kwargs):
        from djangopress.core.models import GlobalSection
        context = super().get_context_data(**kwargs)

        site_settings = SiteSettings.load()
        languages = site_settings.get_language_codes() if site_settings else ['pt']
        default_lang = site_settings.get_default_language() if site_settings else 'pt'
        language_names = dict(site_settings.get_enabled_languages()) if site_settings else {}

        pages = Page.objects.filter(is_active=True).order_by('sort_order', 'id')
        pages_data = []
        for page in pages:
            html_i18n = page.html_content_i18n or {}
            pages_data.append({
                'id': page.id,
                'title': page.get_title(default_lang),
                'lang_status': [(lang, bool(html_i18n.get(lang))) for lang in languages],
            })

        sections = GlobalSection.objects.filter(is_active=True)
        sections_data = []
        for section in sections:
            html_i18n = section.html_template_i18n or {}
            sections_data.append({
                'id': section.id,
                'key': section.key,
                'name': section.name or section.key,
                'lang_status': [(lang, bool(html_i18n.get(lang))) for lang in languages],
            })

        # Language list with names for sidebar (excluding default)
        target_languages = [
            (code, language_names.get(code, code))
            for code in languages if code != default_lang
        ]

        context['pages_data'] = pages_data
        context['sections_data'] = sections_data
        context['languages'] = languages
        context['language_names'] = language_names
        context['target_languages'] = target_languages
        context['default_language'] = default_lang
        context['pages_data_json'] = json.dumps(pages_data, default=str)
        context['sections_data_json'] = json.dumps(sections_data, default=str)

        # Get AI configuration
        try:
            from djangopress.ai.utils.llm_config import LLMConfig
            config = LLMConfig()
            context['ai_models'] = config.get_available_models()
            context['default_model'] = config.default_model
        except Exception:
            context['ai_models'] = []
            context['default_model'] = None

        return context


class DesignConsistencyView(SuperuserRequiredMixin, TemplateView):
    """Design Consistency Analyzer — analyze and fix design inconsistencies across pages."""
    template_name = 'backoffice/design_consistency.html'

    def get_context_data(self, **kwargs):
        from djangopress.core.models import GlobalSection
        context = super().get_context_data(**kwargs)

        site_settings = SiteSettings.load()
        default_lang = site_settings.get_default_language() if site_settings else 'pt'

        pages = Page.objects.filter(is_active=True).order_by('sort_order', 'id')
        pages_data = []
        for page in pages:
            html_i18n = page.html_content_i18n or {}
            has_html = bool(html_i18n.get(default_lang))
            if has_html:
                pages_data.append({
                    'id': page.id,
                    'title': page.get_title(default_lang) or page.default_title or f'Page {page.id}',
                    'slug': page.get_slug(default_lang) or '',
                })

        sections = GlobalSection.objects.filter(is_active=True)
        sections_data = []
        for section in sections:
            html_i18n = section.html_template_i18n or {}
            has_html = bool(html_i18n.get(default_lang))
            if has_html:
                sections_data.append({
                    'key': section.key,
                    'name': section.name or section.key,
                })

        context['pages_data'] = pages_data
        context['sections_data'] = sections_data
        context['total_scannable'] = len(pages_data) + len(sections_data)
        context['design_guide_preview'] = (site_settings.design_guide or '')[:200] if site_settings else ''
        context['default_language'] = default_lang
        return context


class AIRefinePageView(SuperuserRequiredMixin, TemplateView):
    """AI Content Studio - Refine Page"""
    template_name = 'backoffice/ai_refine_page.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get all pages for dropdown options (sorted by created_at)
        all_pages = Page.objects.all().order_by('-created_at')
        context['pages'] = all_pages
        context['total_pages'] = all_pages.count()

        # Pre-populate page if page_slug is in URL
        page_slug = kwargs.get('page_slug')
        selected_page_obj = None
        selected_page_id = None
        if page_slug:
            try:
                # Find page by slug_i18n (check all languages)
                page_obj = None
                for page in all_pages:
                    if page.slug_i18n and isinstance(page.slug_i18n, dict):
                        if page_slug in page.slug_i18n.values():
                            page_obj = page
                            break

                if page_obj:
                    selected_page_obj = page_obj
                    selected_page_id = page_obj.id
                    context['selected_page'] = page_obj
                    context['selected_page_slug'] = page_slug
            except Page.DoesNotExist:
                pass

        # Build reference pages list (exclude current page and pages with no HTML content)
        reference_pages = []
        for page in all_pages:
            # Skip current page
            if selected_page_id and page.id == selected_page_id:
                continue

            ref_html_i18n = page.html_content_i18n or {}
            has_content = bool(ref_html_i18n)
            if has_content:
                reference_pages.append({
                    'id': page.id,
                    'title': page.default_title,
                    'slug': page.default_slug,
                })
        context['reference_pages'] = reference_pages

        # Get AI configuration (if available)
        try:
            from djangopress.ai.utils.llm_config import LLMConfig
            config = LLMConfig()
            context['ai_models'] = config.get_available_models()
            context['default_model'] = config.default_model
        except:
            context['ai_models'] = []
            context['default_model'] = None

        return context


class AIChatRefineView(SuperuserRequiredMixin, TemplateView):
    """AI Content Studio - Chat-based Page Refinement"""
    template_name = 'backoffice/ai_chat_refine.html'

    def get_context_data(self, **kwargs):
        from djangopress.core.models import PageVersion
        from djangopress.ai.models import RefinementSession
        import re

        context = super().get_context_data(**kwargs)
        page_id = kwargs.get('page_id')

        try:
            page = Page.objects.get(pk=page_id)
        except Page.DoesNotExist:
            context['page'] = None
            return context

        context['page'] = page

        # Parse section names from HTML
        html_i18n = page.html_content_i18n or {}
        html = next(iter(html_i18n.values()), '') if html_i18n else ''
        section_matches = re.findall(r'data-section="([^"]+)"', html)
        context['page_sections'] = section_matches

        # Version count
        context['version_count'] = PageVersion.objects.filter(page=page).count()

        # Sessions for this page (last 20)
        sessions = RefinementSession.objects.filter(page=page)[:20]
        context['sessions'] = sessions

        # Active session from query param
        active_session_id = self.request.GET.get('session')
        if active_session_id:
            try:
                active_session = RefinementSession.objects.get(id=active_session_id, page=page)
                context['active_session'] = active_session
                context['active_session_messages'] = active_session.messages
            except RefinementSession.DoesNotExist:
                pass

        # AI models
        try:
            from djangopress.ai.utils.llm_config import LLMConfig
            config = LLMConfig()
            context['ai_models'] = config.get_available_models()
            context['default_model'] = config.default_model
        except Exception:
            context['ai_models'] = []
            from djangopress.ai.utils.llm_config import get_ai_model
            context['default_model'] = get_ai_model('generation')

        # Language info for translation propagation
        from djangopress.core.models import SiteSettings
        site_settings = SiteSettings.objects.first()
        if site_settings:
            default_lang = site_settings.get_default_language()
            enabled_langs = site_settings.get_enabled_languages()
            context['default_language'] = default_lang
            context['enabled_languages'] = enabled_langs
            # Other languages (exclude default) for propagation targets
            context['other_languages'] = [
                (code, name) for code, name in enabled_langs if code != default_lang
            ]
            # Languages that already have HTML content
            html_i18n = page.html_content_i18n or {}
            context['languages_with_html'] = list(html_i18n.keys())
        else:
            context['default_language'] = 'pt'
            context['enabled_languages'] = []
            context['other_languages'] = []
            context['languages_with_html'] = []

        return context


@login_required
@require_http_methods(["POST"])
def restore_page_version(request, version_id):
    """Restore a page to a specific version"""
    from djangopress.core.models import PageVersion

    try:
        version = PageVersion.objects.get(pk=version_id)
        page = version.page

        # Set user for version tracking
        if request.user.is_authenticated:
            page._snapshot_user = request.user
        page._change_summary = f'Restored to version {version.version_number}'

        # Restore the version
        version.restore()

        messages.success(request, f'Page "{page.slug}" restored to version {version.version_number}!')
        return redirect('backoffice:page_edit', page_id=page.id)

    except PageVersion.DoesNotExist:
        messages.error(request, 'Version not found.')
        return redirect('backoffice:pages')
    except Exception as e:
        messages.error(request, f'Error restoring version: {str(e)}')
        return redirect('backoffice:pages')


# === AI GENERATION CONTEXT MANAGEMENT ===
# AI Generation Settings have been removed.
# All AI context is now managed through the Project Briefing field in SiteSettings.
# Users should edit the Project Briefing in Django Admin > Site Settings.


class ProcessImagesView(SuperuserRequiredMixin, TemplateView):
    """Full page for processing images on a page"""
    template_name = 'backoffice/process_images.html'

    def get_context_data(self, **kwargs):
        from django.conf import settings as django_settings

        context = super().get_context_data(**kwargs)
        page_id = kwargs.get('page_id')

        try:
            page = Page.objects.get(pk=page_id)
            context['page'] = page

            # Get AI configuration
            try:
                from djangopress.ai.utils.llm_config import LLMConfig
                config = LLMConfig()
                context['ai_models'] = config.get_available_models()
                context['default_model'] = config.default_model
            except Exception:
                context['ai_models'] = []
                context['default_model'] = None

            # Unsplash availability
            context['unsplash_configured'] = bool(getattr(django_settings, 'UNSPLASH_ACCESS_KEY', ''))

        except Page.DoesNotExist:
            context['page'] = None
            context['ai_models'] = []
            context['default_model'] = None
            context['unsplash_configured'] = False

        return context


class HeaderEditView(LoginRequiredMixin, TemplateView):
    """Header editing page"""
    template_name = 'backoffice/header_edit.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Get or create header global section
        header, created = GlobalSection.objects.get_or_create(
            key='main-header',
            defaults={
                'section_type': 'header',
                'name': 'Main Header',
                'html_template': '',
                'fallback_template': 'partials/header.html',
                'cache_duration': 3600,
                'is_active': True
            }
        )
        context['header'] = header
        context['section'] = header  # For consistency with other templates

        # Add AI configuration
        try:
            from djangopress.ai.utils.llm_config import LLMConfig
            config = LLMConfig()
            context['ai_models'] = config.get_available_models()
            context['default_model'] = config.default_model
        except:
            context['ai_models'] = []
            from djangopress.ai.utils.llm_config import get_ai_model
            context['default_model'] = get_ai_model('generation')

        return context

    def post(self, request, *args, **kwargs):
        """Handle header update"""
        header, _ = GlobalSection.objects.get_or_create(
            key='main-header',
            defaults={
                'section_type': 'header',
                'name': 'Main Header',
                'fallback_template': 'partials/header.html',
            }
        )

        # Update header HTML template
        header.html_template = request.POST.get('html_template', '')
        header.name = request.POST.get('name', 'Main Header')
        header.cache_duration = int(request.POST.get('cache_duration', 3600))
        header.is_active = 'is_active' in request.POST
        header.fallback_template = request.POST.get('fallback_template', 'partials/header.html')
        
        header.save()  # This will auto-clear cache
        
        messages.success(request, 'Header updated successfully!')
        return redirect('backoffice:header_edit')


class FooterEditView(LoginRequiredMixin, TemplateView):
    """Footer editing page"""
    template_name = 'backoffice/footer_edit.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Get or create footer global section
        footer, created = GlobalSection.objects.get_or_create(
            key='main-footer',
            defaults={
                'section_type': 'footer',
                'name': 'Main Footer',
                'html_template': '',
                'fallback_template': 'partials/footer.html',
                'cache_duration': 3600,
                'is_active': True
            }
        )
        context['footer'] = footer
        context['section'] = footer  # For consistency with other templates

        # Add AI configuration
        try:
            from djangopress.ai.utils.llm_config import LLMConfig
            config = LLMConfig()
            context['ai_models'] = config.get_available_models()
            context['default_model'] = config.default_model
        except:
            context['ai_models'] = []
            from djangopress.ai.utils.llm_config import get_ai_model
            context['default_model'] = get_ai_model('generation')

        return context

    def post(self, request, *args, **kwargs):
        """Handle footer update"""
        footer, _ = GlobalSection.objects.get_or_create(
            key='main-footer',
            defaults={
                'section_type': 'footer',
                'name': 'Main Footer',
                'fallback_template': 'partials/footer.html',
            }
        )

        # Update footer HTML template
        footer.html_template = request.POST.get('html_template', '')
        footer.name = request.POST.get('name', 'Main Footer')
        footer.cache_duration = int(request.POST.get('cache_duration', 3600))
        footer.is_active = 'is_active' in request.POST
        footer.fallback_template = request.POST.get('fallback_template', 'partials/footer.html')
        
        footer.save()  # This will auto-clear cache
        
        messages.success(request, 'Footer updated successfully!')
        return redirect('backoffice:footer_edit')


class BlueprintView(SuperuserRequiredMixin, TemplateView):
    """Blueprint — site-level content plan"""
    template_name = 'backoffice/blueprint.html'

    def get_context_data(self, **kwargs):
        import json as json_mod
        context = super().get_context_data(**kwargs)

        # Auto-create default blueprint
        blueprint, _ = Blueprint.objects.get_or_create(
            name='Main Blueprint',
            defaults={'description': '', 'is_active': True}
        )
        context['blueprint'] = blueprint

        # Serialize pages for JS
        bp_pages = list(blueprint.blueprint_pages.all().values(
            'id', 'title', 'slug', 'description', 'sections', 'sort_order', 'page_id'
        ))
        context['pages_json'] = json_mod.dumps(bp_pages)

        # Active Page objects for "link to page" dropdown
        context['site_pages'] = Page.objects.filter(is_active=True)

        # AI models
        try:
            from djangopress.ai.utils.llm_config import LLMConfig
            config = LLMConfig()
            context['ai_models'] = config.get_available_models()
            context['default_model'] = config.default_model
        except Exception:
            context['ai_models'] = []
            from djangopress.ai.utils.llm_config import get_ai_model
            context['default_model'] = get_ai_model('generation')

        return context


class AICallLogsView(SuperuserRequiredMixin, TemplateView):
    """AI Call Logs — browse all LLM API calls."""
    template_name = 'backoffice/ai_call_logs.html'

    def get_context_data(self, **kwargs):
        from djangopress.ai.models import AICallLog, ACTION_CHOICES
        from django.db.models import Sum, Count, Q

        context = super().get_context_data(**kwargs)
        qs = AICallLog.objects.all()

        # Filters
        action = self.request.GET.get('action', '')
        model_name = self.request.GET.get('model', '')
        status = self.request.GET.get('status', '')

        if action:
            qs = qs.filter(action=action)
        if model_name:
            qs = qs.filter(model_name=model_name)
        if status == 'error':
            qs = qs.filter(success=False)
        elif status == 'ok':
            qs = qs.filter(success=True)

        # Summary stats (on filtered qs)
        stats = qs.aggregate(
            total_calls=Count('id'),
            total_tokens=Sum('total_tokens'),
            total_errors=Count('id', filter=Q(success=False)),
        )
        context['stats'] = stats

        # Paginate
        from django.core.paginator import Paginator
        paginator = Paginator(qs, 50)
        page_number = self.request.GET.get('page', 1)
        context['page_obj'] = paginator.get_page(page_number)
        context['logs'] = context['page_obj']

        # Filter options
        context['action_choices'] = ACTION_CHOICES
        context['model_choices'] = (
            AICallLog.objects.values_list('model_name', flat=True)
            .distinct().order_by('model_name')
        )
        context['current_action'] = action
        context['current_model'] = model_name
        context['current_status'] = status

        return context


class FormsView(LoginRequiredMixin, TemplateView):
    """List all dynamic forms with stats."""
    template_name = 'backoffice/forms.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        forms = DynamicForm.objects.all()
        form_data = []
        for f in forms:
            total = f.submissions.count()
            unread = f.submissions.filter(is_read=False).count()
            form_data.append({'form': f, 'total': total, 'unread': unread})
        context['forms'] = form_data
        context['total_forms'] = forms.count()
        context['total_submissions'] = FormSubmission.objects.count()
        context['total_unread'] = FormSubmission.objects.filter(is_read=False).count()
        return context

    def post(self, request, *args, **kwargs):
        action = request.POST.get('action')

        if action == 'create':
            name = request.POST.get('name', '').strip()
            slug = request.POST.get('slug', '').strip()
            notification_email = request.POST.get('notification_email', '').strip()

            if not name or not slug:
                messages.error(request, 'Name and slug are required.')
                return redirect('backoffice:forms')

            if DynamicForm.objects.filter(slug=slug).exists():
                messages.error(request, f'A form with slug "{slug}" already exists.')
                return redirect('backoffice:forms')

            DynamicForm.objects.create(
                name=name,
                slug=slug,
                notification_email=notification_email,
            )
            messages.success(request, f'Form "{name}" created.')

        elif action == 'delete':
            form_id = request.POST.get('form_id')
            try:
                form = DynamicForm.objects.get(pk=form_id)
                form_name = form.name
                form.delete()
                messages.success(request, f'Form "{form_name}" deleted.')
            except DynamicForm.DoesNotExist:
                messages.error(request, 'Form not found.')

        return redirect('backoffice:forms')


class FormEditView(LoginRequiredMixin, TemplateView):
    """Edit a dynamic form definition."""
    template_name = 'backoffice/form_edit.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form_id = kwargs.get('form_id')
        try:
            form = DynamicForm.objects.get(pk=form_id)
            context['form_obj'] = form

            site_settings = SiteSettings.objects.first()
            context['languages'] = site_settings.get_enabled_languages() if site_settings else [('en', 'English')]

            # Serialize i18n dicts for JS population
            context['success_message_json'] = json.dumps(form.success_message_i18n or {})
            context['confirmation_subject_json'] = json.dumps(form.confirmation_subject_i18n or {})
            context['confirmation_body_json'] = json.dumps(form.confirmation_body_i18n or {})
            context['fields_schema_json'] = json.dumps(form.fields_schema or [], indent=2)
        except DynamicForm.DoesNotExist:
            context['form_obj'] = None
            context['languages'] = [('en', 'English')]
        return context

    def post(self, request, *args, **kwargs):
        form_id = kwargs.get('form_id')
        try:
            form = DynamicForm.objects.get(pk=form_id)
        except DynamicForm.DoesNotExist:
            messages.error(request, 'Form not found.')
            return redirect('backoffice:forms')

        form.name = request.POST.get('name', form.name).strip()
        form.slug = request.POST.get('slug', form.slug).strip()
        form.notification_email = request.POST.get('notification_email', '').strip()
        form.is_active = 'is_active' in request.POST
        form.send_confirmation_email = 'send_confirmation_email' in request.POST

        # Fields schema JSON
        fields_schema_raw = request.POST.get('fields_schema', '').strip()
        if fields_schema_raw:
            try:
                form.fields_schema = json.loads(fields_schema_raw)
            except (ValueError, TypeError):
                messages.error(request, 'Invalid JSON in fields schema.')
                return redirect('backoffice:form_edit', form_id=form_id)
        else:
            form.fields_schema = []

        # i18n fields
        site_settings = SiteSettings.objects.first()
        lang_codes = site_settings.get_language_codes() if site_settings else ['en']

        success_msg = {}
        confirm_subject = {}
        confirm_body = {}
        for lang in lang_codes:
            s = request.POST.get(f'success_message_{lang}', '').strip()
            cs = request.POST.get(f'confirmation_subject_{lang}', '').strip()
            cb = request.POST.get(f'confirmation_body_{lang}', '').strip()
            if s:
                success_msg[lang] = s
            if cs:
                confirm_subject[lang] = cs
            if cb:
                confirm_body[lang] = cb

        form.success_message_i18n = success_msg
        form.confirmation_subject_i18n = confirm_subject
        form.confirmation_body_i18n = confirm_body

        form.save()
        messages.success(request, f'Form "{form.name}" updated.')
        return redirect('backoffice:form_edit', form_id=form_id)


class FormSubmissionsView(LoginRequiredMixin, TemplateView):
    """List submissions for a specific form."""
    template_name = 'backoffice/form_submissions.html'

    def get_context_data(self, **kwargs):
        from django.core.paginator import Paginator
        context = super().get_context_data(**kwargs)
        form_id = kwargs.get('form_id')
        try:
            form = DynamicForm.objects.get(pk=form_id)
            context['form_obj'] = form

            qs = form.submissions.all()
            paginator = Paginator(qs, 25)
            page_number = self.request.GET.get('page', 1)
            page_obj = paginator.get_page(page_number)
            context['page_obj'] = page_obj
            context['submissions'] = page_obj
            context['total'] = qs.count()
            context['unread'] = qs.filter(is_read=False).count()
        except DynamicForm.DoesNotExist:
            context['form_obj'] = None
            context['submissions'] = []
        return context

    def post(self, request, *args, **kwargs):
        form_id = kwargs.get('form_id')
        action = request.POST.get('action')
        ids = request.POST.getlist('submission_ids')

        if action == 'mark_read' and ids:
            FormSubmission.objects.filter(pk__in=ids).update(is_read=True)
            messages.success(request, f'{len(ids)} submission(s) marked as read.')
        elif action == 'delete' and ids:
            FormSubmission.objects.filter(pk__in=ids).delete()
            messages.success(request, f'{len(ids)} submission(s) deleted.')

        return redirect('backoffice:form_submissions', form_id=form_id)


class SubmissionDetailView(LoginRequiredMixin, TemplateView):
    """View a single form submission."""
    template_name = 'backoffice/submission_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        submission_id = kwargs.get('submission_id')
        try:
            submission = FormSubmission.objects.select_related('form', 'source_page').get(pk=submission_id)
            if not submission.is_read:
                submission.is_read = True
                submission.save(update_fields=['is_read'])
            context['submission'] = submission
            context['fields'] = submission.get_display_fields()
        except FormSubmission.DoesNotExist:
            context['submission'] = None
            context['fields'] = []
        return context


class BenchmarkListView(SuperuserRequiredMixin, TemplateView):
    template_name = 'backoffice/benchmarks.html'

    def get_context_data(self, **kwargs):
        import os
        from django.conf import settings
        context = super().get_context_data(**kwargs)
        benchmarks_dir = os.path.join(settings.BASE_DIR, 'benchmarks')
        reports = []

        if os.path.isdir(benchmarks_dir):
            for fname in sorted(os.listdir(benchmarks_dir), reverse=True):
                if not fname.endswith('.json'):
                    continue
                filepath = os.path.join(benchmarks_dir, fname)
                try:
                    with open(filepath) as f:
                        data = json.load(f)
                    reports.append({
                        'filename': fname,
                        'meta': data.get('meta', {}),
                        'summary': data.get('summary', {}),
                    })
                except (json.JSONDecodeError, IOError):
                    continue

        # Summary stats
        if reports:
            times = [r['meta'].get('total_time_s', 0) for r in reports if r['meta'].get('total_time_s')]
            context['best_time'] = min(times) if times else 0
            context['avg_page_time'] = round(
                sum(r['summary'].get('avg_page_time_s', 0) for r in reports) / len(reports), 1
            ) if reports else 0
        else:
            context['best_time'] = 0
            context['avg_page_time'] = 0

        context['reports'] = reports

        # Default model for benchmark (from AI settings)
        from djangopress.ai.utils.llm_config import get_ai_model
        context['default_model'] = get_ai_model('generation')

        # Available briefings
        briefings_dir = os.path.join(settings.BASE_DIR, 'briefings')
        context['available_briefings'] = []
        if os.path.isdir(briefings_dir):
            context['available_briefings'] = sorted([
                f for f in os.listdir(briefings_dir) if f.endswith('.md')
            ])

        return context


class BenchmarkDetailView(SuperuserRequiredMixin, TemplateView):
    template_name = 'backoffice/benchmark_detail.html'

    def get_context_data(self, **kwargs):
        import os
        from django.conf import settings
        from django.http import Http404
        context = super().get_context_data(**kwargs)
        filename = kwargs['filename']

        # Security: only allow .json files, no path traversal
        if not filename.endswith('.json') or '/' in filename or '\\' in filename:
            raise Http404

        filepath = os.path.join(settings.BASE_DIR, 'benchmarks', filename)
        if not os.path.exists(filepath):
            raise Http404

        with open(filepath) as f:
            report = json.load(f)

        context['filename'] = filename
        context['report'] = report
        context['meta'] = report.get('meta', {})
        context['summary'] = report.get('summary', {})
        context['llm_calls'] = report.get('llm_calls', [])

        # Pipeline step bars with percentages
        steps = report.get('steps', {})
        total = report['meta'].get('total_time_s', 1) or 1
        step_colors = {
            'plan': 'bg-gray-400',
            'configure_settings': 'bg-blue-500',
            'generate_pages': 'bg-indigo-500',
            'generate_design_guide': 'bg-purple-500',
            'create_menu_items': 'bg-gray-400',
            'generate_header': 'bg-teal-500',
            'generate_footer': 'bg-cyan-500',
            'process_images': 'bg-green-500',
            'ensure_contact_form': 'bg-gray-400',
        }
        context['step_bars'] = [
            {
                'name': name.replace('_', ' ').title(),
                'key': name,
                'time': time_val,
                'pct': round((time_val / total) * 100, 1) if total else 0,
                'color': step_colors.get(name, 'bg-gray-400'),
            }
            for name, time_val in steps.items()
            if time_val > 0.01  # skip near-zero steps
        ]

        # Per-page data with sub-step percentages
        pages = report.get('pages', {})
        page_list = []
        for name, pdata in pages.items():
            page_entry = {
                'name': name,
                'elapsed_s': pdata.get('elapsed_s', 0),
                'llm_calls': pdata.get('llm_calls', 0),
                'llm_time_s': pdata.get('llm_time_s', 0),
                'html_chars': pdata.get('html_chars', 0),
                'error': pdata.get('error'),
                'sub_steps': [],
            }
            sub_steps = pdata.get('sub_steps', {})
            page_total = pdata.get('llm_time_s', 1) or 1
            sub_step_colors = {
                'component_selection': 'bg-blue-400',
                'html_generation': 'bg-indigo-500',
                'metadata': 'bg-gray-400',
                'templatization': 'bg-purple-500',
            }
            for sname, sdata in sub_steps.items():
                page_entry['sub_steps'].append({
                    'name': sname.replace('_', ' ').title(),
                    'key': sname,
                    'elapsed_s': sdata.get('elapsed_s', 0),
                    'model': sdata.get('model', ''),
                    'tokens': sdata.get('tokens', 0),
                    'pct': round((sdata.get('elapsed_s', 0) / page_total) * 100, 1),
                    'color': sub_step_colors.get(sname, 'bg-gray-400'),
                })
            page_list.append(page_entry)
        context['pages'] = page_list

        return context


class BenchmarkCompareView(SuperuserRequiredMixin, TemplateView):
    template_name = 'backoffice/benchmark_compare.html'

    def _load_report(self, filename):
        import os
        from django.conf import settings
        if not filename or not filename.endswith('.json') or '/' in filename:
            return None
        filepath = os.path.join(settings.BASE_DIR, 'benchmarks', filename)
        if not os.path.exists(filepath):
            return None
        try:
            with open(filepath) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    def _delta(self, old, new):
        if old is None or new is None or old == 0:
            return {'diff': 0, 'pct': 0, 'improved': False, 'has_data': False}
        diff = round(new - old, 1)
        pct = round((diff / old) * 100, 1)
        return {'diff': diff, 'pct': pct, 'improved': diff < 0, 'has_data': True}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        file_a = self.request.GET.get('a', '')
        file_b = self.request.GET.get('b', '')

        report_a = self._load_report(file_a)
        report_b = self._load_report(file_b)

        if not report_a or not report_b:
            context['error'] = 'Both reports must be valid JSON files.'
            return context

        context['file_a'] = file_a
        context['file_b'] = file_b
        context['meta_a'] = report_a.get('meta', {})
        context['meta_b'] = report_b.get('meta', {})
        context['summary_a'] = report_a.get('summary', {})
        context['summary_b'] = report_b.get('summary', {})

        # Headline
        ta = report_a['meta'].get('total_time_s', 0)
        tb = report_b['meta'].get('total_time_s', 0)
        if ta and tb:
            context['change_pct'] = round(((tb - ta) / ta) * 100, 1)
            context['is_faster'] = context['change_pct'] < 0
        else:
            context['change_pct'] = 0
            context['is_faster'] = False

        # Step comparison
        all_steps = list(dict.fromkeys(
            list(report_a.get('steps', {}).keys()) + list(report_b.get('steps', {}).keys())
        ))
        step_comparison = []
        for step in all_steps:
            a_val = report_a.get('steps', {}).get(step)
            b_val = report_b.get('steps', {}).get(step)
            step_comparison.append({
                'name': step.replace('_', ' ').title(),
                'a': a_val,
                'b': b_val,
                'delta': self._delta(a_val, b_val),
            })
        context['step_comparison'] = step_comparison

        # Page comparison
        all_pages = list(dict.fromkeys(
            list(report_a.get('pages', {}).keys()) + list(report_b.get('pages', {}).keys())
        ))
        page_comparison = []
        for page in all_pages:
            a_val = report_a.get('pages', {}).get(page, {}).get('elapsed_s')
            b_val = report_b.get('pages', {}).get(page, {}).get('elapsed_s')
            page_comparison.append({
                'name': page,
                'a': a_val,
                'b': b_val,
                'delta': self._delta(a_val, b_val),
            })
        context['page_comparison'] = page_comparison

        # Key metrics comparison
        metrics = [
            ('Total Time', 'total_time_s', 'meta'),
            ('Total LLM Time', 'total_llm_time_s', 'summary'),
            ('Avg Per LLM Call', 'avg_llm_call_s', 'summary'),
            ('Avg Per Page', 'avg_page_time_s', 'summary'),
            ('Text Gen Avg', 'text_llm_avg_s', 'summary'),
            ('Image Gen Avg', 'image_gen_avg_s', 'summary'),
            ('Overhead', 'overhead_time_s', 'summary'),
        ]
        metric_comparison = []
        for label, key, source in metrics:
            if source == 'meta':
                a_val = report_a.get('meta', {}).get(key)
                b_val = report_b.get('meta', {}).get(key)
            else:
                a_val = report_a.get('summary', {}).get(key)
                b_val = report_b.get('summary', {}).get(key)
            if a_val is None and b_val is None:
                continue
            metric_comparison.append({
                'label': label,
                'a': a_val,
                'b': b_val,
                'delta': self._delta(a_val, b_val),
            })
        context['metric_comparison'] = metric_comparison

        # Count metrics
        count_metrics = [
            ('Total LLM Calls', 'total_llm_calls'),
            ('Pages Created', 'pages_created'),
            ('Fallbacks', 'fallback_count'),
            ('Failed Calls', 'failed_count'),
        ]
        count_comparison = []
        for label, key in count_metrics:
            a_val = report_a.get('summary', {}).get(key, 0)
            b_val = report_b.get('summary', {}).get(key, 0)
            diff = b_val - a_val
            count_comparison.append({
                'label': label,
                'a': a_val,
                'b': b_val,
                'diff': diff,
            })
        context['count_comparison'] = count_comparison

        return context


@csrf_exempt
def auto_login(request):
    """Auto-login endpoint for the DjangoPress Manager dashboard."""
    if request.META.get('REMOTE_ADDR') not in ('127.0.0.1', '::1'):
        return HttpResponseForbidden('Local access only')
    if request.method == 'GET':
        if request.user.is_authenticated:
            return redirect('backoffice:dashboard')
        return redirect('backoffice:login')
    username = request.POST.get('username', '')
    password = request.POST.get('password', '')
    user = authenticate(request, username=username, password=password)
    if user:
        login(request, user)
        return redirect('backoffice:dashboard')
    return redirect('backoffice:login')
