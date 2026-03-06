"""Cache invalidation signals for news models."""

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver


@receiver(post_save, sender='news.NewsPost')
@receiver(post_delete, sender='news.NewsPost')
def invalidate_newspost_slug_index(sender, **kwargs):
    sender.invalidate_slug_index()


@receiver(post_save, sender='news.NewsCategory')
@receiver(post_delete, sender='news.NewsCategory')
def invalidate_newscategory_slug_index(sender, **kwargs):
    sender.invalidate_slug_index()
