from django.contrib import admin
from core.admin import TranslationJSONField  # Import custom widget from core
from .models import NewsPost, NewsGalleryImage


class NewsGalleryImageInline(admin.TabularInline):
    model = NewsGalleryImage
    extra = 0
    fields = ('site_image', 'order')
    ordering = ('order',)


@admin.register(NewsPost)
class NewsPostAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'is_published', 'published_date', 'created_at', 'gallery_count')
    list_filter = ('is_published', 'published_date', 'created_at')
    search_fields = ('slug',)
    date_hierarchy = 'published_date'
    ordering = ('-published_date', '-created_at')
    inlines = [NewsGalleryImageInline]

    fieldsets = (
        ('Content (Translations)', {
            'fields': ('title_i18n', 'slug', 'featured_image', 'excerpt_i18n', 'content_i18n'),
            'description': 'News post content in all languages. Edit each language separately below.'
        }),
        ('Publication', {
            'fields': ('is_published', 'published_date')
        }),
        ('SEO (Translations)', {
            'fields': ('meta_description_i18n',),
            'classes': ('collapse',)
        }),
    )

    def gallery_count(self, obj):
        return obj.gallery_items.count()
    gallery_count.short_description = 'Gallery Images'

    def get_form(self, request, obj=None, **kwargs):
        """Customize form to use custom widgets for JSON translation fields"""
        form = super().get_form(request, obj, **kwargs)

        # Use custom widget for JSON translation fields
        if 'title_i18n' in form.base_fields:
            form.base_fields['title_i18n'] = TranslationJSONField(
                label='Title',
                widget_type='text',
                required=False
            )

        if 'content_i18n' in form.base_fields:
            form.base_fields['content_i18n'] = TranslationJSONField(
                label='Content',
                widget_type='textarea',
                required=False
            )

        if 'excerpt_i18n' in form.base_fields:
            form.base_fields['excerpt_i18n'] = TranslationJSONField(
                label='Excerpt',
                widget_type='textarea',
                required=False
            )

        if 'meta_description_i18n' in form.base_fields:
            form.base_fields['meta_description_i18n'] = TranslationJSONField(
                label='Meta Description',
                widget_type='text',
                required=False
            )

        return form


@admin.register(NewsGalleryImage)
class NewsGalleryImageAdmin(admin.ModelAdmin):
    list_display = ('news_post', 'site_image', 'order', 'added_at')
    list_filter = ('news_post', 'added_at')
    search_fields = ('news_post__title', 'site_image__title')
    ordering = ('news_post', 'order')
