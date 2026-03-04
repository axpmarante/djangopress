from django import forms
from .models import NewsPost, NewsCategory
from core.models import SiteImage


class NewsPostForm(forms.ModelForm):
    """Form for creating and updating news posts (i18n version)"""

    gallery_images = forms.ModelMultipleChoiceField(
        queryset=SiteImage.objects.filter(is_active=True).order_by('-id'),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Gallery Images',
        help_text='Select images to add to the gallery'
    )

    class Meta:
        model = NewsPost
        fields = [
            'title_i18n', 'slug_i18n', 'featured_image', 'excerpt_i18n',
            'html_content_i18n', 'category', 'is_published', 'published_date',
            'meta_description_i18n',
        ]
        widgets = {
            'is_published': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-blue-600 border-gray-300 rounded focus:ring-2 focus:ring-blue-500'
            }),
            'published_date': forms.DateTimeInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'type': 'datetime-local'
            }),
            'featured_image': forms.FileInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'accept': 'image/*'
            }),
        }
        help_texts = {
            'slug_i18n': 'URL-friendly identifiers per language (auto-generated from title if empty)',
            'excerpt_i18n': 'Short summary shown in listings',
            'is_published': 'Check to make this post visible on the site',
            'published_date': 'Date and time when this post will be published',
            'meta_description_i18n': 'SEO description for search engines per language',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['published_date'].required = False

        # Load existing gallery images if editing
        if self.instance and self.instance.pk:
            self.fields['gallery_images'].initial = self.instance.gallery_images.all()


class NewsCategoryForm(forms.ModelForm):
    """Form for creating and updating news categories"""

    class Meta:
        model = NewsCategory
        fields = ['name_i18n', 'slug_i18n', 'description_i18n', 'order', 'is_active']
        widgets = {
            'name_i18n': forms.Textarea(attrs={
                'rows': 2, 'class': 'w-full px-3 py-2 border border-gray-300 rounded-md text-sm font-mono',
                'placeholder': '{"pt": "Tecnologia", "en": "Technology"}'
            }),
            'slug_i18n': forms.Textarea(attrs={
                'rows': 2, 'class': 'w-full px-3 py-2 border border-gray-300 rounded-md text-sm font-mono',
                'placeholder': '{"pt": "tecnologia", "en": "technology"} (auto-generated if empty)'
            }),
            'description_i18n': forms.Textarea(attrs={
                'rows': 3, 'class': 'w-full px-3 py-2 border border-gray-300 rounded-md text-sm font-mono',
            }),
            'order': forms.NumberInput(attrs={
                'class': 'w-24 px-3 py-2 border border-gray-300 rounded-md text-sm',
            }),
        }
