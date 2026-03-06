# core/mixins.py
from django.utils.translation import get_language


class I18nModelMixin:
    """Mixin for models with _i18n JSON fields.

    Provides language-aware field resolution with fallback to default language.
    """

    def get_i18n_field(self, field_name, lang=None):
        from djangopress.core.models import SiteSettings
        lang = lang or get_language()
        settings = SiteSettings.load()
        default = settings.get_default_language() if settings else 'pt'
        data = getattr(self, f'{field_name}_i18n', None) or {}
        return data.get(lang) or data.get(default) or ''

    def get_i18n_dict(self, field_name):
        return getattr(self, f'{field_name}_i18n', None) or {}


class VersionableMixin:
    """Mixin that adds generic version history via ContentVersion.

    Models using this mixin must define:
        VERSIONED_FIELDS = ['field1', 'field2', ...]
    """

    VERSIONED_FIELDS = []

    def create_version(self, user=None, change_summary='', max_versions=20):
        """Create a snapshot of the current state of VERSIONED_FIELDS.

        Returns:
            ContentVersion instance
        """
        from django.contrib.contenttypes.models import ContentType
        from djangopress.core.models import ContentVersion

        ct = ContentType.objects.get_for_model(self.__class__)
        version_number = ContentVersion.next_version_number(ct, self.pk)

        snapshot = {}
        for field in self.VERSIONED_FIELDS:
            snapshot[field] = getattr(self, field, None)

        version = ContentVersion.objects.create(
            content_type=ct,
            object_id=self.pk,
            version_number=version_number,
            snapshot=snapshot,
            created_by=user,
            change_summary=change_summary,
        )

        # Cleanup old versions
        old_versions = ContentVersion.objects.filter(
            content_type=ct, object_id=self.pk
        ).order_by('-version_number')[max_versions:]
        if old_versions.exists():
            ContentVersion.objects.filter(
                pk__in=old_versions.values_list('pk', flat=True)
            ).delete()

        return version

    def get_versions(self):
        """Return all versions for this object, newest first."""
        from django.contrib.contenttypes.models import ContentType
        from djangopress.core.models import ContentVersion

        ct = ContentType.objects.get_for_model(self.__class__)
        return ContentVersion.objects.filter(
            content_type=ct, object_id=self.pk
        ).order_by('-version_number')

    def restore_to_version(self, version_number):
        """Restore this object to a specific version."""
        from django.contrib.contenttypes.models import ContentType
        from djangopress.core.models import ContentVersion

        ct = ContentType.objects.get_for_model(self.__class__)
        try:
            version = ContentVersion.objects.get(
                content_type=ct, object_id=self.pk, version_number=version_number
            )
        except ContentVersion.DoesNotExist:
            return None

        for field, value in version.snapshot.items():
            setattr(self, field, value)
        self.save()
        return version
