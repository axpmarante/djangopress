"""
API views for the inline editor.
These endpoints allow staff users to edit page content directly from the frontend.
"""

import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.csrf import csrf_exempt
from core.models import Page, SiteImage
from bs4 import BeautifulSoup


@staff_member_required
@require_http_methods(["POST"])
def update_page_content(request):
    """
    Update a Page's content JSON field (translations).

    Expected POST data:
    {
        "page_id": 1,
        "field_key": "hero_title",
        "language": "pt",
        "value": "New Title"
    }
    """
    try:
        data = json.loads(request.body)
        page_id = data.get('page_id')
        field_key = data.get('field_key')
        language = data.get('language', 'pt')
        value = data.get('value', '').strip() if isinstance(data.get('value'), str) else data.get('value')

        if not page_id or not field_key:
            return JsonResponse({
                'success': False,
                'error': 'Missing page_id or field_key'
            }, status=400)

        try:
            page = Page.objects.get(pk=page_id)
        except Page.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Page not found'
            }, status=404)

        # Update content translations
        content = page.content or {}
        if 'translations' not in content:
            content['translations'] = {}
        if language not in content['translations']:
            content['translations'][language] = {}

        content['translations'][language][field_key] = value
        page.content = content
        page.save()

        return JsonResponse({
            'success': True,
            'message': f'Page content updated: {field_key} ({language})',
            'page_id': page.id,
            'field_key': field_key,
            'language': language,
            'new_value': value
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@staff_member_required
@require_http_methods(["POST"])
def update_page_element_classes(request):
    """
    Update an element's CSS classes directly in the Page's html_content.
    Uses BeautifulSoup to parse HTML and update specific elements by data-element-id.

    Expected POST data:
    {
        "page_id": 1,
        "element_id": "title",
        "new_classes": "text-5xl font-black text-white"
    }
    """
    try:
        data = json.loads(request.body)
        page_id = data.get('page_id')
        element_id = data.get('element_id')
        new_classes = data.get('new_classes', '').strip()

        if not page_id or not element_id:
            return JsonResponse({
                'success': False,
                'error': 'Missing page_id or element_id'
            }, status=400)

        try:
            page = Page.objects.get(pk=page_id)
        except Page.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Page not found'
            }, status=404)

        if not page.html_content or page.html_content.strip() == '':
            return JsonResponse({
                'success': False,
                'error': 'Page has no HTML content'
            }, status=400)

        # Parse HTML with BeautifulSoup
        soup = BeautifulSoup(page.html_content, 'html.parser')

        # Find element by data-element-id
        element = soup.find(attrs={'data-element-id': element_id})

        if not element:
            return JsonResponse({
                'success': False,
                'error': f'Element with data-element-id="{element_id}" not found'
            }, status=404)

        # Store old classes
        old_classes = ' '.join(element.get('class', []))

        # Update classes
        if new_classes:
            element['class'] = new_classes.split()
        else:
            if 'class' in element.attrs:
                del element['class']

        # Convert back to HTML string
        new_html = str(soup)
        if new_html.startswith('<html><body>'):
            new_html = new_html[12:-14]

        page.html_content = new_html
        page.save()

        return JsonResponse({
            'success': True,
            'message': f'Element "{element_id}" classes updated',
            'page_id': page.id,
            'element_id': element_id,
            'old_classes': old_classes,
            'new_classes': new_classes,
            'element_tag': element.name
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@staff_member_required
@require_http_methods(["POST"])
def update_page_element_attribute(request):
    """
    Update any attribute of an element in the Page's html_content.
    Useful for updating href, src, or other attributes.

    Expected POST data:
    {
        "page_id": 1,
        "element_id": "button_primary",
        "attribute": "href",
        "value": "/new-page/"
    }
    """
    try:
        data = json.loads(request.body)
        page_id = data.get('page_id')
        element_id = data.get('element_id')
        attribute = data.get('attribute')
        value = data.get('value', '')

        if not page_id or not element_id or not attribute:
            return JsonResponse({
                'success': False,
                'error': 'Missing required parameters: page_id, element_id, attribute'
            }, status=400)

        try:
            page = Page.objects.get(pk=page_id)
        except Page.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Page not found'
            }, status=404)

        # Parse HTML
        soup = BeautifulSoup(page.html_content, 'html.parser')

        # Find element
        element = soup.find(attrs={'data-element-id': element_id})

        if not element:
            return JsonResponse({
                'success': False,
                'error': f'Element with data-element-id="{element_id}" not found'
            }, status=404)

        # Store old value
        old_value = element.get(attribute, '')

        # Update attribute
        if value:
            element[attribute] = value
        else:
            if attribute in element.attrs:
                del element[attribute]

        # Save
        new_html = str(soup)
        if new_html.startswith('<html><body>'):
            new_html = new_html[12:-14]

        page.html_content = new_html
        page.save()

        return JsonResponse({
            'success': True,
            'message': f'Element "{element_id}" attribute "{attribute}" updated',
            'page_id': page.id,
            'element_id': element_id,
            'attribute': attribute,
            'old_value': old_value,
            'new_value': value
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@staff_member_required
@require_http_methods(["GET"])
def get_media_library(request):
    """
    Get list of all active SiteImages for the media picker modal.

    Query parameters:
    - category: Filter by image category (optional)
    - search: Search in title and tags (optional)
    """
    try:
        images = SiteImage.objects.filter(is_active=True).order_by('-uploaded_at')

        # Filter by category
        category = request.GET.get('category')
        if category and category != 'all':
            images = images.filter(category=category)

        # Search
        search = request.GET.get('search')
        if search:
            images = images.filter(
                title__icontains=search
            ) | images.filter(
                tags__icontains=search
            )

        images_data = []
        for img in images:
            images_data.append({
                'id': img.id,
                'key': img.key,
                'title': img.title,
                'url': img.image.url,
                'alt_text': img.alt_text,
                'category': img.category,
                'tags': img.get_tags_list()
            })

        return JsonResponse({
            'success': True,
            'count': len(images_data),
            'images': images_data
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@staff_member_required
@require_http_methods(["GET"])
def get_images(request):
    """Get all available images for the image modal."""
    images = SiteImage.objects.filter(is_active=True).order_by('-uploaded_at')

    image_list = []
    for img in images:
        alt_text = img.get_alt_text('pt') or img.get_alt_text('en') or img.get_title('pt') or img.get_title('en')
        image_list.append({
            'id': img.id,
            'url': img.image.url if img.image else '',
            'title': img.get_title('pt') or img.get_title('en'),
            'alt_text': alt_text,
            'category': img.category,
            'tags': img.tags or '',
        })

    return JsonResponse({'success': True, 'images': image_list})


@csrf_exempt
@staff_member_required
@require_http_methods(["POST"])
def upload_image(request):
    """Upload a new image to the media library."""
    if 'image' not in request.FILES:
        return JsonResponse({'success': False, 'error': 'No image file provided'}, status=400)

    image_file = request.FILES['image']
    title = request.POST.get('title', image_file.name)
    alt_text = request.POST.get('alt_text', '')
    category = request.POST.get('category', 'other')

    if image_file.size > 10 * 1024 * 1024:
        return JsonResponse({'success': False, 'error': 'File size exceeds 10MB limit'}, status=400)

    allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
    if image_file.content_type not in allowed_types:
        return JsonResponse({'success': False, 'error': 'Invalid file type. Only JPEG, PNG, GIF, and WebP are allowed'}, status=400)

    try:
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
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
