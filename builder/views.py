"""
Builder views for frontend editing
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from core.models import SiteImage
import json


@require_http_methods(["GET"])
def get_images(request):
    """
    Get all available images for selection
    """
    images = SiteImage.objects.filter(is_active=True).order_by('-uploaded_at')

    image_list = []
    for img in images:
        # Get alt text using the helper method with fallback to title
        alt_text = img.get_alt_text('pt') or img.get_alt_text('en') or img.get_title('pt') or img.get_title('en')

        image_list.append({
            'id': img.id,
            'url': img.image.url if img.image else '',
            'title': img.get_title('pt') or img.get_title('en'),
            'alt_text': alt_text,
            'category': img.category,
            'tags': img.tags or '',
        })

    return JsonResponse({
        'success': True,
        'images': image_list
    })


@csrf_exempt
@require_http_methods(["POST"])
def upload_image(request):
    """
    Upload a new image to the media library
    """
    if 'image' not in request.FILES:
        return JsonResponse({
            'success': False,
            'error': 'No image file provided'
        }, status=400)

    image_file = request.FILES['image']
    title = request.POST.get('title', image_file.name)
    alt_text = request.POST.get('alt_text', '')
    category = request.POST.get('category', 'other')

    # Validate file size (10MB max)
    if image_file.size > 10 * 1024 * 1024:
        return JsonResponse({
            'success': False,
            'error': 'File size exceeds 10MB limit'
        }, status=400)

    # Validate file type
    allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
    if image_file.content_type not in allowed_types:
        return JsonResponse({
            'success': False,
            'error': 'Invalid file type. Only JPEG, PNG, GIF, and WebP are allowed'
        }, status=400)

    try:
        # Create SiteImage instance with i18n fields
        site_image = SiteImage.objects.create(
            image=image_file,
            title_i18n={'pt': title, 'en': title},
            alt_text_i18n={'pt': alt_text, 'en': alt_text},
            category=category,
            is_active=True
        )

        return JsonResponse({
            'success': True,
            'image': {
                'id': site_image.id,
                'url': site_image.image.url,
                'title': site_image.get_title('pt') or site_image.get_title('en'),
                'alt_text': site_image.get_alt_text('pt') or site_image.get_alt_text('en'),
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
