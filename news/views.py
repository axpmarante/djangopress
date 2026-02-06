from django.views.generic import ListView, CreateView, UpdateView, DeleteView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.http import JsonResponse
from .models import NewsPost, NewsGalleryImage
from .forms import NewsPostForm
from core.models import SiteImage


class NewsListView(LoginRequiredMixin, ListView):
    """List all news posts"""
    model = NewsPost
    template_name = 'backoffice/news_list.html'
    context_object_name = 'news_posts'
    paginate_by = 20

    def get_queryset(self):
        return NewsPost.objects.order_by('-created_at')


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
            f'News post "{self.object.title}" created successfully!'
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
        context['form_title'] = f'Edit News Post: {self.object.title}'
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
            f'News post "{self.object.title}" updated successfully!'
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
            f'News post "{self.get_object().title}" deleted successfully!'
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
