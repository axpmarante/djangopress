from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Page, PageVersion


@receiver(post_save, sender=Page)
def create_page_version(sender, instance: Page, created, **kwargs):
    """Create a new PageVersion snapshot on every save."""
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
