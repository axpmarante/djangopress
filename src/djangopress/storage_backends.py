"""
Custom storage backends for Google Cloud Storage with domain-based folder organization.

Each site/domain gets its own folder in the GCS bucket for isolated storage.
"""

from storages.backends.gcloud import GoogleCloudStorage
from django.conf import settings


class DomainBasedStorage(GoogleCloudStorage):
    """
    Storage backend that uses SiteSettings.domain as the folder name.

    This allows multiple sites to share a single GCS bucket while keeping
    their files organized in separate folders.

    The folder is always derived from SiteSettings.domain (the configured
    project identifier), NOT from the request hostname. This ensures files
    are stored consistently regardless of whether the site is accessed via
    localhost, a staging domain, or production.
    """
    def __init__(self, *args, **kwargs):
        # Always use SiteSettings.domain as the canonical folder name
        domain = 'default'
        try:
            from djangopress.core.models import SiteSettings
            site_settings = SiteSettings.objects.first()
            if site_settings and site_settings.domain:
                domain = site_settings.domain
        except Exception:
            domain = 'default'

        # Clean the domain for use as folder name
        # Replace dots with dashes and remove port numbers
        folder_name = domain.replace('.', '-').replace(':', '-')

        # Set the location (folder) in the bucket
        kwargs['location'] = folder_name

        super().__init__(*args, **kwargs)
