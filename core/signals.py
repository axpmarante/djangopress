from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import Page, PageVersion


@receiver(post_save, sender=Page)
def create_page_version(sender, instance: Page, created, raw=False, **kwargs):
    """Create a new PageVersion snapshot on every save."""
    if raw:
        return
    try:
        user = getattr(instance, '_snapshot_user', None)
        change_summary = getattr(instance, '_change_summary', '')
        version_number = PageVersion.next_version_number_for(instance)
        PageVersion.objects.create(
            page=instance,
            version_number=version_number,
            title_i18n=instance.title_i18n,
            slug_i18n=instance.slug_i18n,
            html_content=instance.html_content,
            content=instance.content if instance.content else {},
            is_active=instance.is_active,
            created_by=user,
            change_summary=change_summary or ('Initial create' if created else ''),
        )
    except Exception:
        # Avoid breaking saves due to versioning issues
        pass


@receiver(post_save, sender=Page)
def invalidate_slug_index_on_save(sender, **kwargs):
    """Invalidate slug lookup index when a page is saved."""
    Page.invalidate_slug_index()


@receiver(post_delete, sender=Page)
def invalidate_slug_index_on_delete(sender, **kwargs):
    """Invalidate slug lookup index when a page is deleted."""
    Page.invalidate_slug_index()
