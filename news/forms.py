from django import forms
from .models import NewsPost
from core.models import SiteImage


class NewsPostForm(forms.ModelForm):
    """Form for creating and updating news posts"""

    gallery_images = forms.ModelMultipleChoiceField(
        queryset=SiteImage.objects.filter(is_active=True).order_by('-id'),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Gallery Images',
        help_text='Select images to add to the gallery'
    )

    class Meta:
        model = NewsPost
        fields = ['title', 'slug', 'featured_image', 'excerpt', 'content', 'is_published', 'published_date', 'meta_description']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'placeholder': 'News Post Title'
            }),
            'slug': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'placeholder': 'news-post-slug'
            }),
            'featured_image': forms.FileInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'accept': 'image/*'
            }),
            'excerpt': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'rows': 3,
                'placeholder': 'Short summary of the news post...'
            }),
            'content': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'rows': 15,
                'placeholder': 'Full content of the news post...'
            }),
            'is_published': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-blue-600 border-gray-300 rounded focus:ring-2 focus:ring-blue-500'
            }),
            'published_date': forms.DateTimeInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'type': 'datetime-local'
            }),
            'meta_description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'rows': 2,
                'placeholder': 'SEO meta description...'
            }),
        }
        help_texts = {
            'slug': 'URL-friendly identifier (leave blank to auto-generate from title)',
            'excerpt': 'Short summary shown in listings (max 300 characters)',
            'is_published': 'Check to make this post visible on the site',
            'published_date': 'Date and time when this post will be published',
            'meta_description': 'SEO description for search engines (max 160 characters)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make slug optional for creation (it will auto-generate)
        self.fields['slug'].required = False
        self.fields['published_date'].required = False

        # Load existing gallery images if editing
        if self.instance and self.instance.pk:
            self.fields['gallery_images'].initial = self.instance.gallery_images.all()

    def clean_slug(self):
        """Auto-generate slug if not provided"""
        slug = self.cleaned_data.get('slug')
        if not slug and self.cleaned_data.get('title'):
            from django.utils.text import slugify
            slug = slugify(self.cleaned_data['title'])

        # Check for duplicate slugs (excluding current instance if updating)
        if slug:
            queryset = NewsPost.objects.filter(slug=slug)
            if self.instance and self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                raise forms.ValidationError('A news post with this slug already exists.')

        return slug
