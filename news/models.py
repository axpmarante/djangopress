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


class NewsPost(I18nModelMixin, models.Model):
    """Model for news posts"""

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
    featured_image = models.ImageField(_("Featured Image"), upload_to='news/', blank=True, null=True)
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
        from core.models import SiteSettings
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
