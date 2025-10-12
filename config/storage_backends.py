"""
Custom storage backends for Google Cloud Storage with domain-based folder organization.

Each site/domain gets its own folder in the GCS bucket for isolated storage.
"""

from storages.backends.gcs import GoogleCloudStorage
from django.conf import settings


class DomainBasedStorage(GoogleCloudStorage):
    """
    Storage backend that uses the current domain as the folder name.

    This allows multiple sites to share a single GCS bucket while keeping
    their files organized in separate folders.

    Examples:
    - example.com → example-com/
    - blog.example.com → blog-example-com/
    - mysite.org → mysite-org/
    - localhost:8000 → localhost/
    """
    def __init__(self, *args, **kwargs):
        # Get domain from settings (set by DomainMiddleware during request)
        domain = getattr(settings, 'CURRENT_DOMAIN', 'default')

        # Clean the domain for use as folder name
        # Replace dots with dashes and remove port numbers
        folder_name = domain.replace('.', '-').replace(':', '-')

        # Set the location (folder) in the bucket
        kwargs['location'] = folder_name

        super().__init__(*args, **kwargs)
