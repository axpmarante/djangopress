"""MediaService — media library management."""

import logging
from django.db.models import Q
from djangopress.core.models import SiteImage

logger = logging.getLogger(__name__)


class MediaService:

    @staticmethod
    def list(search='', limit=20):
        """Browse media library with optional search."""
        images = SiteImage.objects.filter(is_active=True).order_by('-uploaded_at')

        if search:
            images = images.filter(
                Q(title_i18n__icontains=search) | Q(tags__icontains=search)
            )

        images = images[:limit]
        data = []
        for img in images:
            data.append({
                'id': img.id,
                'title': img.title_i18n,
                'url': img.url,
                'tags': img.tags or '',
            })
        return {'success': True, 'images': data, 'message': f'{len(data)} images found'}

    @staticmethod
    def get(image_id):
        """Get a single image by ID."""
        try:
            img = SiteImage.objects.get(pk=image_id)
            return {
                'success': True,
                'image': {
                    'id': img.id,
                    'title': img.title_i18n,
                    'alt_text': img.alt_text_i18n,
                    'url': img.url,
                    'tags': img.tags or '',
                    'description': img.description,
                },
            }
        except SiteImage.DoesNotExist:
            return {'success': False, 'error': f'Image {image_id} not found'}
