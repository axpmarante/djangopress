from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from core.mixins import I18nModelMixin
from core.models import SiteImage


class NewsCategory(I18nModelMixin, models.Model):
    """Category for organizing news posts."""
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
            from core.models import SiteSettings
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


class NewsPost(models.Model):
    """Model for news posts"""

    # OLD FIELDS (will be removed after migration)
    title = models.CharField(_("Title (OLD)"), max_length=200, null=True, blank=True)
    content = models.TextField(_("Content (OLD)"), blank=True, null=True)
    excerpt = models.TextField(_("Excerpt (OLD)"), max_length=300, blank=True, null=True)
    meta_description = models.CharField(_("Meta Description (OLD)"), max_length=160, blank=True, null=True)

    # NEW: JSON Translation Fields
    title_i18n = models.JSONField(
        'Title (All Languages)',
        default=dict,
        blank=True,
        help_text='{"pt": "Título PT", "en": "Title EN"}'
    )
    content_i18n = models.JSONField(
        'Content (All Languages)',
        default=dict,
        blank=True,
        help_text='{"pt": "Conteúdo PT", "en": "Content EN"}'
    )
    excerpt_i18n = models.JSONField(
        'Excerpt (All Languages)',
        default=dict,
        blank=True,
        help_text='{"pt": "Resumo PT", "en": "Excerpt EN"}'
    )
    meta_description_i18n = models.JSONField(
        'Meta Description (All Languages)',
        default=dict,
        blank=True,
        help_text='{"pt": "Meta descrição PT", "en": "Meta description EN"}'
    )

    slug = models.SlugField(_("Slug"), max_length=200, unique=True, blank=True)
    featured_image = models.ImageField(_("Featured Image"), upload_to='news/', blank=True, null=True)

    # Gallery - many-to-many relationship with SiteImage
    gallery_images = models.ManyToManyField(
        SiteImage,
        through='NewsGalleryImage',
        related_name='news_posts',
        blank=True,
        verbose_name=_("Gallery Images")
    )

    # Metadata
    is_published = models.BooleanField(_("Published"), default=False)
    published_date = models.DateTimeField(_("Published Date"), blank=True, null=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    class Meta:
        ordering = ['-published_date', '-created_at']
        verbose_name = _("News Post")
        verbose_name_plural = _("News Posts")

    def __str__(self):
        # Try new JSON field first, fall back to old field
        if self.title_i18n and isinstance(self.title_i18n, dict):
            return self.title_i18n.get('pt', self.title_i18n.get('en', self.slug or 'News Post'))
        return self.title or self.slug or 'News Post'

    def get_title(self, lang='pt'):
        """Get title in specified language"""
        if self.title_i18n and isinstance(self.title_i18n, dict):
            return self.title_i18n.get(lang, self.title_i18n.get('pt', ''))
        return self.title or ''

    def get_content(self, lang='pt'):
        """Get content in specified language"""
        if self.content_i18n and isinstance(self.content_i18n, dict):
            return self.content_i18n.get(lang, self.content_i18n.get('pt', ''))
        return self.content or ''

    def get_excerpt(self, lang='pt'):
        """Get excerpt in specified language"""
        if self.excerpt_i18n and isinstance(self.excerpt_i18n, dict):
            return self.excerpt_i18n.get(lang, self.excerpt_i18n.get('pt', ''))
        return self.excerpt or ''

    def get_meta_description(self, lang='pt'):
        """Get meta description in specified language"""
        if self.meta_description_i18n and isinstance(self.meta_description_i18n, dict):
            return self.meta_description_i18n.get(lang, self.meta_description_i18n.get('pt', ''))
        return self.meta_description or ''

    def save(self, *args, **kwargs):
        if not self.slug:
            # Generate slug from JSON title if available, otherwise from old title
            if self.title_i18n and isinstance(self.title_i18n, dict):
                title_for_slug = self.title_i18n.get('pt', self.title_i18n.get('en', ''))
            else:
                title_for_slug = self.title or ''
            self.slug = slugify(title_for_slug) if title_for_slug else ''
        super().save(*args, **kwargs)


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
        return f"{self.news_post.title} - {self.site_image.title}"
