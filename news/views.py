import re

from django.views.generic import ListView, CreateView, UpdateView, DeleteView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.http import JsonResponse
from core.decorators import SuperuserRequiredMixin
from .models import NewsPost, NewsGalleryImage, NewsCategory, NewsLayout
from .forms import NewsPostForm, NewsCategoryForm
from core.models import SiteImage, SiteSettings


# ─── News Posts ───────────────────────────────────────────────────────────────


class NewsListView(LoginRequiredMixin, ListView):
    """List all news posts"""
    model = NewsPost
    template_name = 'backoffice/news_list.html'
    context_object_name = 'news_posts'
    paginate_by = 20

    def get_queryset(self):
        return NewsPost.objects.select_related('category').order_by('-created_at')


class NewsCreateView(LoginRequiredMixin, CreateView):
    """Create new news post"""
    model = NewsPost
    form_class = NewsPostForm
    template_name = 'backoffice/news_form.html'

    def get_success_url(self):
        return reverse_lazy('backoffice:news_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = 'Create New News Post'
        context['submit_text'] = 'Create Post'
        return context

    def form_valid(self, form):
        response = super().form_valid(form)

        # Handle gallery images
        gallery_images = form.cleaned_data.get('gallery_images')
        if gallery_images:
            # Clear existing gallery items
            self.object.gallery_items.all().delete()

            # Add selected images with order
            for idx, site_image in enumerate(gallery_images):
                NewsGalleryImage.objects.create(
                    news_post=self.object,
                    site_image=site_image,
                    order=idx + 1
                )

        messages.success(
            self.request,
            f'News post "{self.object}" created successfully!'
        )
        return response


class NewsUpdateView(LoginRequiredMixin, UpdateView):
    """Update existing news post"""
    model = NewsPost
    form_class = NewsPostForm
    template_name = 'backoffice/news_form.html'

    def get_success_url(self):
        return reverse_lazy('backoffice:news_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = f'Edit News Post: {self.object}'
        context['submit_text'] = 'Update Post'
        return context

    def form_valid(self, form):
        response = super().form_valid(form)

        # Handle gallery images
        gallery_images = form.cleaned_data.get('gallery_images')
        if gallery_images is not None:  # Check if field was in the form
            # Clear existing gallery items
            self.object.gallery_items.all().delete()

            # Add selected images with order
            for idx, site_image in enumerate(gallery_images):
                NewsGalleryImage.objects.create(
                    news_post=self.object,
                    site_image=site_image,
                    order=idx + 1
                )

        messages.success(
            self.request,
            f'News post "{self.object}" updated successfully!'
        )
        return response


class NewsDeleteView(LoginRequiredMixin, DeleteView):
    """Delete news post"""
    model = NewsPost
    template_name = 'backoffice/news_confirm_delete.html'
    success_url = reverse_lazy('backoffice:news_list')

    def delete(self, request, *args, **kwargs):
        messages.success(
            request,
            f'News post "{self.get_object()}" deleted successfully!'
        )
        return super().delete(request, *args, **kwargs)


class NewsGalleryView(LoginRequiredMixin, TemplateView):
    """Manage news post gallery - select from existing images"""
    template_name = 'backoffice/news_gallery.html'

    def dispatch(self, request, *args, **kwargs):
        self.news_post = get_object_or_404(NewsPost, pk=kwargs.get('pk'))
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['news_post'] = self.news_post
        context['gallery_items'] = self.news_post.gallery_items.all()

        # Get all available images from SiteImage
        context['site_images'] = SiteImage.objects.filter(is_active=True).order_by('-id')

        return context

    def post(self, request, *args, **kwargs):
        """Handle adding/removing images from gallery"""
        action = request.POST.get('action')

        if action == 'add_site_image':
            image_id = request.POST.get('image_id')
            site_image = get_object_or_404(SiteImage, pk=image_id)

            # Get current max order
            max_order = NewsGalleryImage.objects.filter(
                news_post=self.news_post
            ).count()

            # Create gallery item if it doesn't exist
            gallery_item, created = NewsGalleryImage.objects.get_or_create(
                news_post=self.news_post,
                site_image=site_image,
                defaults={'order': max_order + 1}
            )

            if created:
                messages.success(request, f'Image "{site_image.title}" added to gallery!')
            else:
                messages.info(request, f'Image "{site_image.title}" is already in the gallery.')

        elif action == 'remove':
            item_id = request.POST.get('item_id')
            gallery_item = get_object_or_404(
                NewsGalleryImage,
                pk=item_id,
                news_post=self.news_post
            )
            image_title = gallery_item.site_image.title
            gallery_item.delete()
            messages.success(request, f'Image "{image_title}" removed from gallery!')

        elif action == 'reorder':
            # Handle reordering via AJAX
            item_id = request.POST.get('item_id')
            new_order = request.POST.get('order')

            gallery_item = get_object_or_404(
                NewsGalleryImage,
                pk=item_id,
                news_post=self.news_post
            )
            gallery_item.order = int(new_order)
            gallery_item.save()

            return JsonResponse({'success': True})

        return redirect('backoffice:news_gallery', pk=self.news_post.pk)


# ─── News Categories ─────────────────────────────────────────────────────────


class CategoryListView(LoginRequiredMixin, ListView):
    """List all news categories"""
    model = NewsCategory
    template_name = 'backoffice/news_categories.html'
    context_object_name = 'categories'

    def get_queryset(self):
        return NewsCategory.objects.order_by('order', 'pk')


class CategoryCreateView(LoginRequiredMixin, CreateView):
    """Create a new news category"""
    model = NewsCategory
    form_class = NewsCategoryForm
    template_name = 'backoffice/news_category_form.html'
    success_url = reverse_lazy('backoffice:news_categories')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = 'Create New Category'
        context['submit_text'] = 'Create Category'
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'Category "{self.object}" created successfully!')
        return response


class CategoryUpdateView(LoginRequiredMixin, UpdateView):
    """Edit an existing news category"""
    model = NewsCategory
    form_class = NewsCategoryForm
    template_name = 'backoffice/news_category_form.html'
    success_url = reverse_lazy('backoffice:news_categories')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = f'Edit Category: {self.object}'
        context['submit_text'] = 'Update Category'
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'Category "{self.object}" updated successfully!')
        return response


class CategoryDeleteView(LoginRequiredMixin, DeleteView):
    """Delete a news category"""
    model = NewsCategory
    template_name = 'backoffice/news_category_confirm_delete.html'
    success_url = reverse_lazy('backoffice:news_categories')

    def delete(self, request, *args, **kwargs):
        messages.success(
            request,
            f'Category "{self.get_object()}" deleted successfully!'
        )
        return super().delete(request, *args, **kwargs)


# ─── News Layouts ─────────────────────────────────────────────────────────────


class LayoutListView(LoginRequiredMixin, ListView):
    """List all news layout templates"""
    model = NewsLayout
    template_name = 'backoffice/news_layouts.html'
    context_object_name = 'layouts'

    def get_queryset(self):
        return NewsLayout.objects.order_by('key')


class LayoutUpdateView(LoginRequiredMixin, UpdateView):
    """Edit a news layout template"""
    model = NewsLayout
    template_name = 'backoffice/news_layout_form.html'
    fields = ['html_content_i18n']
    success_url = reverse_lazy('backoffice:news_layouts')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = f'Edit Layout: {self.object.key}'
        context['submit_text'] = 'Update Layout'
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'Layout "{self.object.key}" updated successfully!')
        return response


# ─── AI Tools ────────────────────────────────────────────────────────────────


class NewsGenerateView(SuperuserRequiredMixin, TemplateView):
    """AI generation page for news posts"""
    template_name = 'backoffice/ai_generate_news.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_posts'] = NewsPost.objects.count()
        context['categories'] = NewsCategory.objects.filter(is_active=True).order_by('order')

        try:
            from ai.utils.llm_config import LLMConfig
            config = LLMConfig()
            context['ai_models'] = config.get_available_models()
            context['default_model'] = config.default_model
        except Exception:
            context['ai_models'] = []
            context['default_model'] = None

        return context


class NewsBulkView(SuperuserRequiredMixin, TemplateView):
    """Bulk create news posts via AI"""
    template_name = 'backoffice/ai_bulk_news.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_posts'] = NewsPost.objects.count()
        context['categories'] = NewsCategory.objects.filter(is_active=True).order_by('order')

        try:
            from ai.utils.llm_config import LLMConfig
            config = LLMConfig()
            context['ai_models'] = config.get_available_models()
            context['default_model'] = config.default_model
        except Exception:
            context['ai_models'] = []
            context['default_model'] = None

        return context


class NewsRefineView(SuperuserRequiredMixin, TemplateView):
    """Chat-based news post refinement"""
    template_name = 'backoffice/ai_refine_news.html'

    def get_context_data(self, **kwargs):
        from ai.models import RefinementSession
        from django.contrib.contenttypes.models import ContentType

        context = super().get_context_data(**kwargs)
        post_id = kwargs.get('pk')

        try:
            post = NewsPost.objects.get(pk=post_id)
        except NewsPost.DoesNotExist:
            context['post'] = None
            return context

        context['post'] = post

        # Parse section names from HTML
        html_i18n = post.html_content_i18n or {}
        html = next(iter(html_i18n.values()), '') if html_i18n else ''
        section_matches = re.findall(r'data-section="([^"]+)"', html)
        context['post_sections'] = section_matches

        # Sessions for this post (using generic FK)
        ct = ContentType.objects.get_for_model(NewsPost)
        sessions = RefinementSession.objects.filter(
            content_type=ct, object_id=post_id
        )[:20]
        context['sessions'] = sessions

        # Active session from query param
        active_session_id = self.request.GET.get('session')
        if active_session_id:
            try:
                active_session = RefinementSession.objects.get(
                    id=active_session_id, content_type=ct, object_id=post_id
                )
                context['active_session'] = active_session
                context['active_session_messages'] = active_session.messages
            except RefinementSession.DoesNotExist:
                pass

        # AI models
        try:
            from ai.utils.llm_config import LLMConfig
            config = LLMConfig()
            context['ai_models'] = config.get_available_models()
            context['default_model'] = config.default_model
        except Exception:
            context['ai_models'] = []
            context['default_model'] = 'gemini-pro'

        # Language info
        site_settings = SiteSettings.objects.first()
        if site_settings:
            default_lang = site_settings.get_default_language()
            enabled_langs = site_settings.get_enabled_languages()
            context['default_language'] = default_lang
            context['enabled_languages'] = enabled_langs
            context['other_languages'] = [
                (code, name) for code, name in enabled_langs if code != default_lang
            ]
            html_i18n = post.html_content_i18n or {}
            context['languages_with_html'] = list(html_i18n.keys())
        else:
            context['default_language'] = 'pt'
            context['enabled_languages'] = []
            context['other_languages'] = []
            context['languages_with_html'] = []

        return context


class NewsImagesView(SuperuserRequiredMixin, TemplateView):
    """Process images on a news post"""
    template_name = 'backoffice/news_images.html'

    def get_context_data(self, **kwargs):
        from django.conf import settings as django_settings

        context = super().get_context_data(**kwargs)
        post_id = kwargs.get('pk')

        try:
            post = NewsPost.objects.get(pk=post_id)
            context['post'] = post

            try:
                from ai.utils.llm_config import LLMConfig
                config = LLMConfig()
                context['ai_models'] = config.get_available_models()
                context['default_model'] = config.default_model
            except Exception:
                context['ai_models'] = []
                context['default_model'] = None

            context['unsplash_configured'] = bool(getattr(django_settings, 'UNSPLASH_ACCESS_KEY', ''))
        except NewsPost.DoesNotExist:
            context['post'] = None
            context['ai_models'] = []
            context['default_model'] = None
            context['unsplash_configured'] = False

        return context
