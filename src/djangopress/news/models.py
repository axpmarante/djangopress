from django.core.cache import cache
from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from djangopress.core.mixins import I18nModelMixin, VersionableMixin
from djangopress.core.models import SiteImage


class NewsCategory(I18nModelMixin, models.Model):
    """Category for organizing news posts."""
    SLUG_CACHE_KEY = 'news_category_slug_index'

    name_i18n = models.JSONField(
        'Name (All Languages)',
        default=dict,
        blank=True,
        help_text='{"pt": "Tecnologia", "en": "Technology"}'
    )
    slug_i18n = models.JSONField(
        'Slug (All Languages)',
        default=dict,
        blank=True,
        help_text='{"pt": "tecnologia", "en": "technology"}'
    )
    description_i18n = models.JSONField(
        'Description (All Languages)',
        default=dict,
        blank=True,
    )
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['order', 'pk']
        verbose_name = _("News Category")
        verbose_name_plural = _("News Categories")

    def __str__(self):
        return self.get_i18n_field('name') or f'Category #{self.pk}'

    def get_absolute_url(self, lang=None):
        from django.urls import reverse
        from django.utils.translation import get_language
        lang = lang or get_language()
        slug = (self.slug_i18n or {}).get(lang, '')
        if not slug:
            from djangopress.core.models import SiteSettings
            settings = SiteSettings.load()
            default = settings.get_default_language() if settings else 'pt'
            slug = (self.slug_i18n or {}).get(default, '')
        return reverse('news:category', kwargs={'slug': slug}) if slug else '#'

    def save(self, *args, **kwargs):
        # Auto-generate slugs from name_i18n if empty
        if self.name_i18n and not self.slug_i18n:
            self.slug_i18n = {
                lang: slugify(name) for lang, name in self.name_i18n.items() if name
            }
        super().save(*args, **kwargs)

    @classmethod
    def get_by_slug(cls, slug, lang=None):
        """Look up an active category by slug using a cached index."""
        index = cache.get(cls.SLUG_CACHE_KEY)
        if index is None:
            index = cls._build_slug_index()

        key = f'{lang}:{slug}' if lang else None
        cat_id = index.get(key) if key else None

        # Fallback: check all languages
        if cat_id is None:
            for k, v in index.items():
                if k.endswith(f':{slug}'):
                    cat_id = v
                    break

        if cat_id is not None:
            try:
                cat = cls.objects.get(pk=cat_id)
                if cat.is_active:
                    return cat
            except cls.DoesNotExist:
                pass

        return None

    @classmethod
    def _build_slug_index(cls):
        """Build {lang:slug -> id} index for all active categories."""
        index = {}
        for cat in cls.objects.filter(is_active=True):
            for lang, slug in (cat.slug_i18n or {}).items():
                if slug:
                    index[f'{lang}:{slug}'] = cat.pk
        cache.set(cls.SLUG_CACHE_KEY, index, 3600)
        return index

    @classmethod
    def invalidate_slug_index(cls):
        """Clear the slug lookup index from cache."""
        cache.delete(cls.SLUG_CACHE_KEY)


class NewsPost(VersionableMixin, I18nModelMixin, models.Model):
    """Model for news posts"""
    SLUG_CACHE_KEY = 'news_post_slug_index'
    VERSIONED_FIELDS = [
        'title_i18n', 'slug_i18n', 'excerpt_i18n',
        'html_content_i18n', 'meta_description_i18n', 'is_published',
    ]

    # JSON Translation Fields
    title_i18n = models.JSONField(
        'Title (All Languages)',
        default=dict,
        blank=True,
        help_text='{"pt": "Título PT", "en": "Title EN"}'
    )
    slug_i18n = models.JSONField(
        'Slug (All Languages)',
        default=dict,
        blank=True,
        help_text='{"pt": "meu-artigo", "en": "my-article"}'
    )
    excerpt_i18n = models.JSONField(
        'Excerpt (All Languages)',
        default=dict,
        blank=True,
        help_text='{"pt": "Resumo PT", "en": "Excerpt EN"}'
    )
    html_content_i18n = models.JSONField(
        'HTML Content (All Languages)',
        default=dict,
        blank=True,
        help_text='Per-language HTML, same as Page model'
    )
    meta_description_i18n = models.JSONField(
        'Meta Description (All Languages)',
        default=dict,
        blank=True,
        help_text='{"pt": "Meta descrição PT", "en": "Meta description EN"}'
    )

    # Relations
    category = models.ForeignKey(
        NewsCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='posts',
        verbose_name=_("Category")
    )
    featured_image = models.ForeignKey(
        SiteImage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='news_featured_posts',
        verbose_name=_("Featured Image"),
    )
    gallery_images = models.ManyToManyField(
        SiteImage,
        through='NewsGalleryImage',
        related_name='news_posts',
        blank=True,
        verbose_name=_("Gallery Images")
    )

    # Publishing
    is_published = models.BooleanField(_("Published"), default=False)
    published_date = models.DateTimeField(_("Published Date"), blank=True, null=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    class Meta:
        ordering = ['-published_date', '-created_at']
        verbose_name = _("News Post")
        verbose_name_plural = _("News Posts")

    def __str__(self):
        return self.get_i18n_field('title') or f'News Post #{self.pk}'

    def get_absolute_url(self, lang=None):
        from django.urls import reverse
        from django.utils.translation import get_language
        from djangopress.core.models import SiteSettings
        lang = lang or get_language()
        slug = (self.slug_i18n or {}).get(lang, '')
        if not slug:
            settings = SiteSettings.load()
            default = settings.get_default_language() if settings else 'pt'
            slug = (self.slug_i18n or {}).get(default, '')
        try:
            return reverse('news:detail', kwargs={'slug': slug}) if slug else '#'
        except Exception:
            return '#'

    def save(self, *args, **kwargs):
        if self.title_i18n and not self.slug_i18n:
            self.slug_i18n = {
                lang: slugify(title) for lang, title in self.title_i18n.items() if title
            }
        super().save(*args, **kwargs)

    @classmethod
    def get_by_slug(cls, slug, lang=None):
        """Look up a published post by slug using a cached index."""
        index = cache.get(cls.SLUG_CACHE_KEY)
        if index is None:
            index = cls._build_slug_index()

        key = f'{lang}:{slug}' if lang else None
        post_id = index.get(key) if key else None

        # Fallback: check all languages
        if post_id is None:
            for k, v in index.items():
                if k.endswith(f':{slug}'):
                    post_id = v
                    break

        if post_id is not None:
            try:
                return cls.objects.select_related('category').get(pk=post_id, is_published=True)
            except cls.DoesNotExist:
                pass

        return None

    @classmethod
    def _build_slug_index(cls):
        """Build {lang:slug -> id} index for all published posts."""
        index = {}
        for post in cls.objects.filter(is_published=True):
            for lang, slug in (post.slug_i18n or {}).items():
                if slug:
                    index[f'{lang}:{slug}'] = post.pk
        cache.set(cls.SLUG_CACHE_KEY, index, 3600)
        return index

    @classmethod
    def invalidate_slug_index(cls):
        """Clear the slug lookup index from cache."""
        cache.delete(cls.SLUG_CACHE_KEY)


class NewsLayout(models.Model):
    """Layout templates for news public pages (list, detail, category).

    Stores AI-generated HTML per language that wraps dynamic data.
    The HTML uses Django template syntax with app-specific context variables.
    """
    key = models.SlugField(
        max_length=50,
        unique=True,
        help_text='Layout identifier: list, detail, category'
    )
    html_content_i18n = models.JSONField(
        'HTML Layout (All Languages)',
        default=dict,
        blank=True,
        help_text='Per-language HTML layout with Django template syntax'
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("News Layout")
        verbose_name_plural = _("News Layouts")

    def __str__(self):
        return f"NewsLayout: {self.key}"


class NewsGalleryImage(models.Model):
    """Through model for NewsPost gallery images with ordering"""

    news_post = models.ForeignKey(
        NewsPost,
        on_delete=models.CASCADE,
        related_name='gallery_items',
        verbose_name=_("News Post")
    )
    site_image = models.ForeignKey(
        SiteImage,
        on_delete=models.CASCADE,
        related_name='news_gallery_items',
        verbose_name=_("Site Image")
    )
    order = models.PositiveIntegerField(_("Order"), default=0, help_text="Display order in gallery")
    added_at = models.DateTimeField(_("Added At"), auto_now_add=True)

    class Meta:
        ordering = ['order', 'added_at']
        verbose_name = _("News Gallery Image")
        verbose_name_plural = _("News Gallery Images")
        unique_together = [['news_post', 'site_image']]

    def __str__(self):
        post_title = self.news_post.get_i18n_field('title') if hasattr(self.news_post, 'get_i18n_field') else str(self.news_post)
        image_title = str(self.site_image)
        return f"{post_title} - {image_title}"
