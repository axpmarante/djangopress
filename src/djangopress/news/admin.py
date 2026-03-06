from django.contrib import admin
from core.admin import TranslationJSONField  # Import custom widget from core
from .models import NewsPost, NewsGalleryImage, NewsCategory, NewsLayout


class NewsGalleryImageInline(admin.TabularInline):
    model = NewsGalleryImage
    extra = 0
    fields = ('site_image', 'order')
    ordering = ('order',)


@admin.register(NewsCategory)
class NewsCategoryAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'order', 'is_active', 'post_count')
    list_filter = ('is_active',)
    list_editable = ('order', 'is_active')
    ordering = ('order', 'pk')

    fieldsets = (
        (None, {
            'fields': ('name_i18n', 'slug_i18n', 'description_i18n', 'order', 'is_active'),
        }),
    )

    def post_count(self, obj):
        return obj.posts.count()
    post_count.short_description = 'Posts'

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        for field_name in ('name_i18n', 'slug_i18n', 'description_i18n'):
            if field_name in form.base_fields:
                widget_type = 'textarea' if 'description' in field_name else 'text'
                form.base_fields[field_name] = TranslationJSONField(
                    label=field_name.replace('_i18n', '').replace('_', ' ').title(),
                    widget_type=widget_type,
                    required=False,
                )
        return form


@admin.register(NewsPost)
class NewsPostAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'category', 'is_published', 'published_date', 'created_at', 'gallery_count')
    list_filter = ('is_published', 'category', 'published_date', 'created_at')
    search_fields = ('title_i18n',)
    date_hierarchy = 'published_date'
    ordering = ('-published_date', '-created_at')
    inlines = [NewsGalleryImageInline]

    fieldsets = (
        ('Content (Translations)', {
            'fields': ('title_i18n', 'slug_i18n', 'featured_image', 'excerpt_i18n', 'html_content_i18n', 'category'),
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

        json_fields = {
            'title_i18n': ('Title', 'text'),
            'slug_i18n': ('Slug', 'text'),
            'excerpt_i18n': ('Excerpt', 'textarea'),
            'html_content_i18n': ('HTML Content', 'textarea'),
            'meta_description_i18n': ('Meta Description', 'text'),
        }

        for field_name, (label, widget_type) in json_fields.items():
            if field_name in form.base_fields:
                form.base_fields[field_name] = TranslationJSONField(
                    label=label,
                    widget_type=widget_type,
                    required=False,
                )

        return form


@admin.register(NewsLayout)
class NewsLayoutAdmin(admin.ModelAdmin):
    list_display = ('key', 'updated_at')
    readonly_fields = ('updated_at',)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if 'html_content_i18n' in form.base_fields:
            form.base_fields['html_content_i18n'] = TranslationJSONField(
                label='HTML Content',
                widget_type='textarea',
                required=False,
            )
        return form


@admin.register(NewsGalleryImage)
class NewsGalleryImageAdmin(admin.ModelAdmin):
    list_display = ('news_post', 'site_image', 'order', 'added_at')
    list_filter = ('news_post', 'added_at')
    ordering = ('news_post', 'order')
