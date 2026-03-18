"""
Custom storage backends for Google Cloud Storage with folder organization.

Each site gets its own folder in the GCS bucket for isolated storage.
The folder name is determined by SiteSettings.gcs_folder (project slug).
"""

from storages.backends.gcloud import GoogleCloudStorage
from django.conf import settings


class DomainBasedStorage(GoogleCloudStorage):
    """
    Storage backend that uses SiteSettings.gcs_folder as the folder name.

    This allows multiple sites to share a single GCS bucket while keeping
    their files organized in separate folders.

    The folder is derived from SiteSettings.gcs_folder (the project slug),
    falling back to SiteSettings.domain for backwards compatibility.
    """
    def __init__(self, *args, **kwargs):
        folder_name = 'default'
        try:
            from djangopress.core.models import SiteSettings
            site_settings = SiteSettings.objects.first()
            if site_settings:
                if site_settings.gcs_folder:
                    folder_name = site_settings.gcs_folder
                elif site_settings.domain:
                    # Backwards compatibility: use domain if gcs_folder not set
                    folder_name = site_settings.domain.replace('.', '-').replace(':', '-')
        except Exception:
            folder_name = 'default'

        kwargs['location'] = folder_name
        super().__init__(*args, **kwargs)
