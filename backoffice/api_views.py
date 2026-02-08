"""
API views for inline editing functionality.
These endpoints allow staff users to update content directly from the frontend.
"""

import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache
from django.utils.text import slugify
from core.models import SiteSettings, SiteImage, Page
from core.utils import resize_and_compress_image


@staff_member_required
@require_http_methods(["POST"])
def update_site_settings(request):
    """
    Update a SiteSettings field via AJAX.

    Expected POST data:
    {
        "field": "site_name",
        "value": "New Site Name",
        "language": "en"  # or "pt", optional for non-translated fields
    }
    """
    try:
        data = json.loads(request.body)
        field = data.get('field')
        value = data.get('value')
        language = data.get('language')

        if not all([field, value is not None]):
            return JsonResponse({
                'success': False,
                'error': 'Missing required fields: field, value'
            }, status=400)

        settings = SiteSettings.load()

        # Check if this is a translatable field
        if language and hasattr(settings, f"{field}_{language}"):
            field_name = f"{field}_{language}"
        else:
            field_name = field

        if not hasattr(settings, field_name):
            return JsonResponse({
                'success': False,
                'error': f'Field "{field_name}" does not exist'
            }, status=400)

        setattr(settings, field_name, value)
        settings.save()

        # Clear cache
        cache.delete('site_settings')

        return JsonResponse({
            'success': True,
            'message': f'Updated site settings: {field_name}',
            'data': {
                'field': field_name,
                'value': value
            }
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
    """
    try:
        images = SiteImage.objects.filter(is_active=True).order_by('-id')

        images_data = []
        for img in images:
            images_data.append({
                'id': img.id,
                'key': img.key,
                'title': img.title,
                'url': img.image.url,
                'alt_text': img.alt_text,
            })

        return JsonResponse({
            'success': True,
            'images': images_data
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@staff_member_required
@require_http_methods(["POST"])
def upload_images(request):
    """
    Upload multiple images to the media library.

    Expected POST data:
    - Multiple files with key 'images'

    Returns:
    {
        "success": true,
        "uploaded_count": 3,
        "optimized_count": 2,
        "skipped_count": 1,
        "uploaded_images": [
            {"id": 1, "title": "Image 1", "url": "/media/site_images/image1.jpg"},
            ...
        ]
    }
    """
    try:
        images = request.FILES.getlist('images')

        if not images:
            return JsonResponse({
                'success': False,
                'error': 'No images provided'
            }, status=400)

        uploaded_count = 0
        optimized_count = 0
        skipped_count = 0
        uploaded_images = []

        for image in images:
            try:
                # Get file size in KB
                image_size_kb = image.size / 1024

                # Auto-generate title and key from filename
                filename_without_ext = image.name.rsplit('.', 1)[0]
                title = filename_without_ext.replace('_', ' ').replace('-', ' ').title()
                base_key = slugify(filename_without_ext)

                # Ensure unique key
                key = base_key
                counter = 1
                while SiteImage.objects.filter(key=key).exists():
                    key = f"{base_key}-{counter}"
                    counter += 1

                # Check if image needs optimization (larger than 400KB)
                if image_size_kb > 400:
                    processed_image = resize_and_compress_image(image)
                    optimized_count += 1
                else:
                    processed_image = image
                    skipped_count += 1

                # Create SiteImage object with 'project' category
                site_image = SiteImage(
                    title=title,
                    key=key,
                    alt_text=title,
                    category='project',
                    is_active=True
                )
                site_image.image.save(image.name, processed_image, save=False)
                site_image.save()

                uploaded_images.append({
                    'id': site_image.id,
                    'title': site_image.title,
                    'url': site_image.image.url,
                    'key': site_image.key
                })

                uploaded_count += 1

            except Exception as e:
                print(f"❌ Error uploading {image.name}: {str(e)}")
                continue

        if uploaded_count == 0:
            return JsonResponse({
                'success': False,
                'error': 'Failed to upload any images'
            }, status=500)

        return JsonResponse({
            'success': True,
            'uploaded_count': uploaded_count,
            'optimized_count': optimized_count,
            'skipped_count': skipped_count,
            'uploaded_images': uploaded_images
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@staff_member_required
@require_http_methods(["GET"])
def get_page_content(request, page_id):
    """
    Get page content (HTML and translations).

    GET /backoffice/api/page-content/<page_id>/

    Returns: {
        "success": true,
        "page": {"id": 1, "title": "Home", "slug": "home"},
        "html_content": "...",
        "content": {"translations": {...}}
    }
    """
    try:
        page = Page.objects.get(id=page_id)

        return JsonResponse({
            'success': True,
            'page': {
                'id': page.id,
                'title': page.default_title,
                'slug': page.default_slug
            },
            'html_content': page.html_content or '',
            'content': page.content or {}
        })

    except Page.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': f'Page with id {page_id} not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@staff_member_required
@require_http_methods(["GET"])
def get_site_settings(request):
    """
    Get site settings including enabled languages.

    GET /backoffice/api/get-site-settings/

    Returns: {
        "success": true,
        "settings": {
            "site_name": "...",
            "enabled_languages": [{"code": "pt", "name": "Portuguese"}, ...],
            "default_language": "pt"
        }
    }
    """
    try:
        settings = SiteSettings.load()

        enabled_languages = getattr(settings, 'enabled_languages', None)
        if not enabled_languages:
            enabled_languages = [{'code': 'pt', 'name': 'Portuguese'}, {'code': 'en', 'name': 'English'}]

        default_language = getattr(settings, 'default_language', 'pt')

        return JsonResponse({
            'success': True,
            'settings': {
                'site_name': settings.site_name or '',
                'enabled_languages': enabled_languages,
                'default_language': default_language,
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@staff_member_required
@require_http_methods(["POST"])
def generate_design_guide(request):
    """
    Generate a starter design guide markdown document from current SiteSettings values.
    Pure Python — no LLM call. Returns markdown text the user can customize.
    """
    try:
        settings = SiteSettings.load()

        lines = ["# Design Guide\n"]

        # Colors
        lines.append("## Colors\n")
        lines.append(f"- **Primary:** `{settings.primary_color}` (hover: `{settings.primary_color_hover}`)")
        lines.append(f"- **Secondary:** `{settings.secondary_color}`")
        lines.append(f"- **Accent:** `{settings.accent_color}`")
        lines.append(f"- **Background:** `{settings.background_color}`")
        lines.append(f"- **Text:** `{settings.text_color}`")
        lines.append(f"- **Headings:** `{settings.heading_color}`")
        lines.append("")

        # Typography
        lines.append("## Typography\n")
        lines.append(f"- **Body font:** {settings.body_font}")
        lines.append(f"- **Heading font:** {settings.heading_font}")
        lines.append(f"- H1: {settings.h1_font} / {settings.h1_size}")
        lines.append(f"- H2: {settings.h2_font} / {settings.h2_size}")
        lines.append(f"- H3: {settings.h3_font} / {settings.h3_size}")
        lines.append(f"- H4: {settings.h4_font} / {settings.h4_size}")
        lines.append(f"- H5: {settings.h5_font} / {settings.h5_size}")
        lines.append(f"- H6: {settings.h6_font} / {settings.h6_size}")
        lines.append("")

        # Layout
        lines.append("## Layout\n")
        lines.append(f"- **Container width:** max-w-{settings.container_width}")
        lines.append(f"- **Border radius:** rounded-{settings.border_radius_preset}")
        lines.append(f"- **Spacing scale:** {settings.spacing_scale}")
        lines.append(f"- **Shadow preset:** shadow-{settings.shadow_preset}")
        lines.append("")

        # Buttons
        lines.append("## Buttons\n")
        lines.append(f"- **Style:** {settings.button_style}")
        lines.append(f"- **Size:** {settings.button_size}")
        lines.append(f"- **Border width:** {settings.button_border_width}px")
        lines.append(f"- **Primary button:** bg `{settings.primary_button_bg}`, text `{settings.primary_button_text}`, border `{settings.primary_button_border}`, hover `{settings.primary_button_hover}`")
        lines.append(f"- **Secondary button:** bg `{settings.secondary_button_bg}`, text `{settings.secondary_button_text}`, border `{settings.secondary_button_border}`, hover `{settings.secondary_button_hover}`")
        lines.append("")

        # Component patterns (starter suggestions)
        lines.append("## Component Patterns\n")
        lines.append("### Cards")
        lines.append(f"- Use `rounded-{settings.border_radius_preset}` corners with `shadow-{settings.shadow_preset}`")
        lines.append(f"- Background: white with `{settings.text_color}` text")
        lines.append("")
        lines.append("### Sections")
        spacing_map = {'tight': 'py-12 md:py-16', 'normal': 'py-16 md:py-24', 'relaxed': 'py-20 md:py-28', 'loose': 'py-24 md:py-32'}
        section_padding = spacing_map.get(settings.spacing_scale, 'py-16 md:py-24')
        lines.append(f"- Default section padding: `{section_padding}`")
        lines.append(f"- Container: `max-w-{settings.container_width} mx-auto px-6`")
        lines.append("- Alternate between white and light gray (`bg-gray-50`) backgrounds")
        lines.append("")
        lines.append("### Hero Sections")
        lines.append(f"- Use primary color `{settings.primary_color}` as background with white text, or use a background image with dark overlay")
        lines.append("- Hero padding should be larger: `py-24 md:py-32`")
        lines.append("")
        lines.append("## Visual Rules\n")
        lines.append("- Maintain consistent spacing between elements within sections")
        lines.append("- Use the accent color sparingly for highlights and CTAs")
        lines.append("- Ensure sufficient color contrast for accessibility")

        markdown = "\n".join(lines)

        return JsonResponse({
            'success': True,
            'design_guide': markdown,
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@staff_member_required
@require_http_methods(["POST"])
def update_page_order(request):
    """
    Bulk update page sort_order.

    Expected POST data:
    {
        "pages": [{"id": 1, "sort_order": 0}, {"id": 2, "sort_order": 1}]
    }
    """
    try:
        data = json.loads(request.body)
        pages_data = data.get('pages', [])

        if not pages_data:
            return JsonResponse({
                'success': False,
                'error': 'No pages provided'
            }, status=400)

        for page_data in pages_data:
            Page.objects.filter(id=page_data['id']).update(
                sort_order=page_data['sort_order']
            )

        return JsonResponse({
            'success': True,
            'message': f'Updated order for {len(pages_data)} page(s)'
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
def update_languages(request):
    """
    Update site language settings.

    Expected POST data:
    {
        "default_language": "pt",
        "enabled_languages": [
            {"code": "pt", "name": "Portuguese"},
            {"code": "en", "name": "English"}
        ]
    }
    """
    try:
        data = json.loads(request.body)
        default_language = data.get('default_language')
        enabled_languages = data.get('enabled_languages')

        if not default_language or not enabled_languages:
            return JsonResponse({
                'success': False,
                'error': 'Missing required fields: default_language, enabled_languages'
            }, status=400)

        # Validate that enabled_languages is a list
        if not isinstance(enabled_languages, list) or len(enabled_languages) == 0:
            return JsonResponse({
                'success': False,
                'error': 'enabled_languages must be a non-empty list'
            }, status=400)

        # Validate each language has code and name
        for lang in enabled_languages:
            if not isinstance(lang, dict) or 'code' not in lang or 'name' not in lang:
                return JsonResponse({
                    'success': False,
                    'error': 'Each language must have "code" and "name" fields'
                }, status=400)

        # Validate that default_language is in enabled_languages
        enabled_codes = [lang['code'] for lang in enabled_languages]
        if default_language not in enabled_codes:
            return JsonResponse({
                'success': False,
                'error': 'default_language must be one of the enabled languages'
            }, status=400)

        settings = SiteSettings.load()
        settings.default_language = default_language
        settings.enabled_languages = enabled_languages
        settings.save()

        # Clear cache
        cache.delete('site_settings')

        return JsonResponse({
            'success': True,
            'message': 'Language settings updated successfully',
            'data': {
                'default_language': default_language,
                'enabled_languages': enabled_languages
            }
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
