"""
API views for inline editing functionality.
These endpoints allow staff users to update content directly from the frontend.
"""

import base64
import hmac
import json
import logging
import os
import re
import signal
import subprocess
import sys
import tempfile
from django.http import JsonResponse
from django.template import Template, Context
from django.views.decorators.http import require_http_methods
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache
from django.core.serializers import deserialize
from django.utils.text import slugify
from django.db import connection
from bs4 import BeautifulSoup
from core.models import SiteSettings, SiteImage, Page, MenuItem, Blueprint, BlueprintPage

logger = logging.getLogger(__name__)
from core.utils import resize_and_compress_image
from core.decorators import superuser_required


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
                'url': img.url,
                'alt_text': img.alt_text,
                'file_type': img.file_type,
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
    Upload multiple files (images and PDFs) to the media library.

    Expected POST data:
    - Multiple files with key 'images'

    Returns:
    {
        "success": true,
        "uploaded_count": 3,
        "optimized_count": 2,
        "skipped_count": 1,
        "uploaded_images": [
            {"id": 1, "title": "Image 1", "url": "/media/site_images/image1.jpg", "file_type": "image"},
            ...
        ]
    }
    """
    ALLOWED_PDF_TYPES = ['application/pdf']
    ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
    MAX_PDF_SIZE = 20 * 1024 * 1024  # 20MB

    try:
        files = request.FILES.getlist('images')

        if not files:
            return JsonResponse({
                'success': False,
                'error': 'No files provided'
            }, status=400)

        uploaded_count = 0
        optimized_count = 0
        skipped_count = 0
        uploaded_images = []
        lang_codes = SiteSettings.load().get_language_codes()

        for uploaded_file in files:
            try:
                content_type = uploaded_file.content_type
                is_pdf = content_type in ALLOWED_PDF_TYPES
                is_image = content_type in ALLOWED_IMAGE_TYPES

                if not is_pdf and not is_image:
                    continue

                if is_pdf and uploaded_file.size > MAX_PDF_SIZE:
                    continue

                # Auto-generate title and key from filename
                filename_without_ext = uploaded_file.name.rsplit('.', 1)[0]
                title = filename_without_ext.replace('_', ' ').replace('-', ' ').title()
                base_key = slugify(filename_without_ext)

                # Ensure unique key
                key = base_key
                counter = 1
                while SiteImage.objects.filter(key=key).exists():
                    key = f"{base_key}-{counter}"
                    counter += 1

                site_image = SiteImage(
                    title_i18n={lang: title for lang in lang_codes},
                    alt_text_i18n={lang: title for lang in lang_codes},
                    key=key,
                    is_active=True,
                    file_type='document' if is_pdf else 'image',
                )

                if is_pdf:
                    site_image.file.save(uploaded_file.name, uploaded_file, save=False)
                    skipped_count += 1
                else:
                    image_size_kb = uploaded_file.size / 1024
                    if image_size_kb > 400:
                        processed = resize_and_compress_image(uploaded_file)
                        optimized_count += 1
                    else:
                        processed = uploaded_file
                        skipped_count += 1
                    site_image.image.save(uploaded_file.name, processed, save=False)

                site_image.save()

                uploaded_images.append({
                    'id': site_image.id,
                    'title': title,
                    'url': site_image.url,
                    'key': site_image.key,
                    'file_type': site_image.file_type,
                })

                uploaded_count += 1

            except Exception as e:
                print(f"Error uploading {uploaded_file.name}: {str(e)}")
                continue

        if uploaded_count == 0:
            return JsonResponse({
                'success': False,
                'error': 'Failed to upload any files'
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
    Get page content (per-language HTML).

    GET /backoffice/api/page-content/<page_id>/

    Returns: {
        "success": true,
        "page": {"id": 1, "title": "Home", "slug": "home"},
        "html_content_i18n": {"pt": "...", "en": "..."}
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
            'html_content_i18n': page.html_content_i18n or {},
        })

    except Page.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': f'Page with id {page_id} not found'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@staff_member_required
@require_http_methods(["GET"])
def get_page_sections(request, page_id):
    """
    Get page metadata and ordered list of sections parsed from html_content_i18n.

    GET /backoffice/api/page-sections/<page_id>/

    Returns: {
        "success": true,
        "page": {"id", "title", "title_i18n", "slug_i18n", "is_active", "meta_title_i18n", "meta_description_i18n", "updated_at"},
        "sections": [{"name": "hero", "html": "<section ...>...</section>"}, ...]
    }
    """
    try:
        page = Page.objects.get(id=page_id)
        sections = []

        html_i18n = page.html_content_i18n or {}
        html_for_parse = next(iter(html_i18n.values()), '') if html_i18n else ''

        if html_for_parse:
            soup = BeautifulSoup(html_for_parse, 'html.parser')
            for section_el in soup.find_all('section', attrs={'data-section': True}):
                sections.append({
                    'name': section_el.get('data-section', ''),
                    'html': str(section_el),
                })

        return JsonResponse({
            'success': True,
            'page': {
                'id': page.id,
                'title': page.default_title,
                'title_i18n': page.title_i18n or {},
                'slug_i18n': page.slug_i18n or {},
                'is_active': page.is_active,
                'meta_title_i18n': page.meta_title_i18n or {},
                'meta_description_i18n': page.meta_description_i18n or {},
                'updated_at': page.updated_at.isoformat(),
            },
            'sections': sections,
            'html_content_i18n': page.html_content_i18n or {},
        })

    except Page.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': f'Page with id {page_id} not found'
        }, status=404)


@staff_member_required
@require_http_methods(["GET"])
def get_page_section_screenshots(request, page_id):
    """
    Capture screenshots of each section on a page using Playwright.

    GET /backoffice/api/page-screenshots/<page_id>/

    Returns: {
        "success": true,
        "sections": [{"name": "hero", "image": "data:image/png;base64,..."}, ...]
    }
    """
    try:
        page = Page.objects.get(id=page_id)
    except Page.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Page not found'}, status=404)

    # Prefer html_content_i18n over legacy html_content
    html_i18n = page.html_content_i18n or {}
    site_settings = SiteSettings.load()
    default_lang = 'pt'
    if site_settings:
        langs = site_settings.get_enabled_languages()
        if langs:
            default_lang = langs[0][0]

    # Get the best available HTML: default lang from i18n, or any lang from i18n
    page_html = html_i18n.get(default_lang) or next(iter(html_i18n.values()), '')

    if not page_html:
        return JsonResponse({'success': True, 'sections': []})

    # Check cache (keyed by page id + updated_at)
    cache_key = f'page_screenshots_{page_id}_{page.updated_at.isoformat()}'
    cached = cache.get(cache_key)
    if cached:
        return JsonResponse({'success': True, 'sections': cached})

    # Render HTML as Django template (for {% url %} tags, etc.)
    try:
        template = Template(page_html)
        rendered_html = template.render(Context({
            'LANGUAGE_CODE': default_lang,
            'page': page,
            'SITE_NAME': site_settings.site_name_i18n.get(default_lang, '') if site_settings else '',
        }))
    except Exception:
        rendered_html = page_html

    # Build full HTML page for Playwright
    full_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body {{ margin: 0; padding: 0; }}
        img {{ max-width: 100%; height: auto; }}
    </style>
</head>
<body>
{rendered_html}
</body>
</html>"""

    # Write to temp file and capture screenshots with Playwright
    sections_data = []
    tmp_path = None
    try:
        from playwright.sync_api import sync_playwright

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(full_html)
            tmp_path = f.name

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(viewport={'width': 1280, 'height': 800})
            pg = ctx.new_page()
            pg.goto(f'file://{tmp_path}', wait_until='networkidle')

            # Wait for Tailwind to process
            pg.wait_for_timeout(1500)

            section_elements = pg.query_selector_all('section[data-section]')
            for el in section_elements:
                name = el.get_attribute('data-section') or ''
                try:
                    screenshot_bytes = el.screenshot(type='png')
                    b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
                    sections_data.append({
                        'name': name,
                        'image': f'data:image/png;base64,{b64}',
                    })
                except Exception as e:
                    logger.warning(f'Screenshot failed for section "{name}": {e}')
                    sections_data.append({'name': name, 'image': ''})

            browser.close()

        # Cache for 10 minutes
        cache.set(cache_key, sections_data, 600)

    except ImportError:
        return JsonResponse({
            'success': False,
            'error': 'Playwright is not installed. Run: pip install playwright && playwright install chromium'
        }, status=500)
    except Exception as e:
        logger.error(f'Playwright screenshot error for page {page_id}: {e}')
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    return JsonResponse({'success': True, 'sections': sections_data})


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
def update_page_settings(request, page_id):
    """
    Update page settings (title, slug, status, SEO) inline from the explorer.

    Expected POST data:
    {
        "title_i18n": {"pt": "...", "en": "..."},
        "slug_i18n": {"pt": "...", "en": "..."},
        "is_active": true,
        "meta_title_i18n": {"pt": "...", "en": "..."},
        "meta_description_i18n": {"pt": "...", "en": "..."}
    }
    """
    try:
        page = Page.objects.get(id=page_id)
    except Page.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Page not found'}, status=404)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    # Validate slugs are unique
    slug_i18n = data.get('slug_i18n')
    if slug_i18n:
        for lang, slug_val in slug_i18n.items():
            if not slug_val:
                continue
            conflict = Page.objects.filter(
                slug_i18n__contains={lang: slug_val}
            ).exclude(id=page_id).first()
            if conflict:
                return JsonResponse({
                    'success': False,
                    'error': f'Slug "{slug_val}" ({lang}) is already used by "{conflict.default_title}"'
                }, status=400)

    # Update fields
    if 'title_i18n' in data:
        page.title_i18n = data['title_i18n']
    if 'slug_i18n' in data:
        page.slug_i18n = data['slug_i18n']
    if 'is_active' in data:
        page.is_active = data['is_active']
    if 'meta_title_i18n' in data:
        page.meta_title_i18n = data['meta_title_i18n']
    if 'meta_description_i18n' in data:
        page.meta_description_i18n = data['meta_description_i18n']

    page._snapshot_user = request.user.get_username()
    page.save()

    return JsonResponse({
        'success': True,
        'message': f'Page "{page.default_title}" updated.',
        'updated_at': page.updated_at.isoformat(),
    })


@staff_member_required
@require_http_methods(["POST"])
def update_menu_order(request):
    """
    Bulk update menu item sort_order.

    Expected POST data:
    {
        "items": [{"id": 1, "sort_order": 0}, {"id": 2, "sort_order": 1}]
    }
    """
    try:
        data = json.loads(request.body)
        items_data = data.get('items', [])

        if not items_data:
            return JsonResponse({
                'success': False,
                'error': 'No items provided'
            }, status=400)

        for item_data in items_data:
            MenuItem.objects.filter(id=item_data['id']).update(
                sort_order=item_data['sort_order']
            )

        return JsonResponse({
            'success': True,
            'message': f'Updated order for {len(items_data)} item(s)'
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
def update_menu_parent(request):
    """
    Update a menu item's parent (indent/outdent).

    Expected POST data:
    {
        "item_id": 5,
        "parent_id": 3    // null to make top-level (outdent)
    }
    """
    try:
        data = json.loads(request.body)
        item_id = data.get('item_id')
        parent_id = data.get('parent_id')

        if not item_id:
            return JsonResponse({
                'success': False,
                'error': 'item_id is required'
            }, status=400)

        try:
            item = MenuItem.objects.get(pk=item_id)
        except MenuItem.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Menu item not found'
            }, status=400)

        if parent_id:
            if int(parent_id) == item.id:
                return JsonResponse({
                    'success': False,
                    'error': 'An item cannot be its own parent'
                }, status=400)

            try:
                parent = MenuItem.objects.get(pk=parent_id)
            except MenuItem.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Parent item not found'
                }, status=400)

            if parent.parent_id is not None:
                return JsonResponse({
                    'success': False,
                    'error': 'Cannot nest more than one level deep'
                }, status=400)

            item.parent = parent
        else:
            item.parent = None

        item.save()

        return JsonResponse({
            'success': True,
            'message': 'Menu item parent updated'
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


# === Blueprint API ===

@staff_member_required
@require_http_methods(["POST"])
def save_blueprint_page(request):
    """
    Create or update a BlueprintPage.

    POST data: {
        "blueprint_id": 1,
        "page_id": null,  // BlueprintPage id, null to create new
        "title": "About Us",
        "slug": "about-us",
        "description": "Company info...",
        "sections": [{"id": "hero", "title": "Hero", "content": "...", "order": 0}]
    }
    """
    try:
        data = json.loads(request.body)
        blueprint_id = data.get('blueprint_id')
        bp_page_id = data.get('page_id')
        title = data.get('title', '').strip()
        slug_val = data.get('slug', '').strip()
        description = data.get('description', '').strip()
        sections = data.get('sections', [])

        if not blueprint_id or not title:
            return JsonResponse({
                'success': False,
                'error': 'blueprint_id and title are required'
            }, status=400)

        # Validate unique section IDs
        if sections:
            section_ids = [s.get('id', '') for s in sections if s.get('id')]
            if len(section_ids) != len(set(section_ids)):
                dupes = [sid for sid in section_ids if section_ids.count(sid) > 1]
                return JsonResponse({
                    'success': False,
                    'error': f'Duplicate section IDs: {", ".join(set(dupes))}'
                }, status=400)

        blueprint = Blueprint.objects.get(pk=blueprint_id)

        if bp_page_id:
            bp_page = BlueprintPage.objects.get(pk=bp_page_id, blueprint=blueprint)
            bp_page.title = title
            bp_page.slug = slug_val
            bp_page.description = description
            bp_page.sections = sections
            bp_page.save()
        else:
            from django.db.models import Max
            max_order = blueprint.blueprint_pages.aggregate(
                m=Max('sort_order'))['m'] or 0
            bp_page = BlueprintPage.objects.create(
                blueprint=blueprint,
                title=title,
                slug=slug_val,
                description=description,
                sections=sections,
                sort_order=max_order + 1,
            )

        return JsonResponse({
            'success': True,
            'page': {
                'id': bp_page.id,
                'title': bp_page.title,
                'slug': bp_page.slug,
                'description': bp_page.description,
                'sections': bp_page.sections,
                'sort_order': bp_page.sort_order,
                'linked_page_id': bp_page.page_id,
            }
        })

    except Blueprint.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Blueprint not found'}, status=400)
    except BlueprintPage.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Blueprint page not found'}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@staff_member_required
@require_http_methods(["POST"])
def delete_blueprint_page(request):
    """Delete a BlueprintPage. POST data: {"page_id": 5}"""
    try:
        data = json.loads(request.body)
        bp_page_id = data.get('page_id')
        if not bp_page_id:
            return JsonResponse({'success': False, 'error': 'page_id is required'}, status=400)

        bp_page = BlueprintPage.objects.get(pk=bp_page_id)
        bp_page.delete()
        return JsonResponse({'success': True})

    except BlueprintPage.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Blueprint page not found'}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@staff_member_required
@require_http_methods(["POST"])
def reorder_blueprint_pages(request):
    """
    Bulk reorder BlueprintPages.
    POST data: {"pages": [{"id": 1, "sort_order": 0}, {"id": 2, "sort_order": 1}]}
    """
    try:
        data = json.loads(request.body)
        pages_data = data.get('pages', [])

        if not pages_data:
            return JsonResponse({'success': False, 'error': 'No pages provided'}, status=400)

        for item in pages_data:
            BlueprintPage.objects.filter(id=item['id']).update(sort_order=item['sort_order'])

        return JsonResponse({
            'success': True,
            'message': f'Updated order for {len(pages_data)} page(s)'
        })

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@staff_member_required
@require_http_methods(["POST"])
def save_blueprint_sections(request):
    """
    Update sections JSON for a single BlueprintPage.
    POST data: {"blueprint_page_id": 3, "sections": [...]}
    """
    try:
        data = json.loads(request.body)
        bp_page_id = data.get('blueprint_page_id')
        sections = data.get('sections', [])

        if not bp_page_id:
            return JsonResponse({'success': False, 'error': 'blueprint_page_id is required'}, status=400)

        # Validate unique section IDs
        if sections:
            section_ids = [s.get('id', '') for s in sections if s.get('id')]
            if len(section_ids) != len(set(section_ids)):
                dupes = [sid for sid in section_ids if section_ids.count(sid) > 1]
                return JsonResponse({
                    'success': False,
                    'error': f'Duplicate section IDs: {", ".join(set(dupes))}'
                }, status=400)

        bp_page = BlueprintPage.objects.get(pk=bp_page_id)
        bp_page.sections = sections
        bp_page.save()

        return JsonResponse({'success': True, 'sections': bp_page.sections})

    except BlueprintPage.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Blueprint page not found'}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@staff_member_required
@require_http_methods(["POST"])
def create_pages_from_blueprint(request):
    """
    Create actual Page objects from a Blueprint.
    For each BlueprintPage without a linked Page, creates a Page with matching title/slug.
    POST data: {"blueprint_id": 1}
    """
    try:
        data = json.loads(request.body)
        blueprint_id = data.get('blueprint_id')

        if not blueprint_id:
            return JsonResponse({'success': False, 'error': 'blueprint_id is required'}, status=400)

        blueprint = Blueprint.objects.get(pk=blueprint_id)

        site_settings = SiteSettings.objects.first()
        lang_codes = site_settings.get_language_codes() if site_settings else ['pt', 'en']

        created = []
        skipped = []

        for bp_page in blueprint.blueprint_pages.all():
            if bp_page.page_id:
                skipped.append(bp_page.title)
                continue

            title_i18n = {lang: bp_page.title for lang in lang_codes}
            slug_val = bp_page.slug or slugify(bp_page.title)
            slug_i18n = {lang: slug_val for lang in lang_codes}

            # Check for duplicate slugs
            duplicate = False
            for lang, s in slug_i18n.items():
                for existing in Page.objects.all():
                    if existing.get_slug(lang) == s:
                        skipped.append(f'{bp_page.title} (slug "{s}" exists)')
                        duplicate = True
                        break
                if duplicate:
                    break
            if duplicate:
                continue

            page = Page.objects.create(
                title_i18n=title_i18n,
                slug_i18n=slug_i18n,
                is_active=True
            )
            bp_page.page = page
            bp_page.save()
            created.append(bp_page.title)

        return JsonResponse({
            'success': True,
            'created': created,
            'skipped': skipped,
            'message': f'Created {len(created)} page(s), skipped {len(skipped)}'
        })

    except Blueprint.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Blueprint not found'}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# === Benchmark API ===

# Module-level state for the single benchmark subprocess
_benchmark_process = None
_benchmark_output_file = None


@superuser_required
@require_http_methods(["POST"])
def run_benchmark(request):
    """
    Start a benchmark as a subprocess.

    POST data: {"model": "gemini-pro", "briefing": "briefings/benchmark.md", "skip_images": true}
    Returns: {"success": true, "pid": 12345}
    """
    global _benchmark_process, _benchmark_output_file

    if _benchmark_process and _benchmark_process.poll() is None:
        return JsonResponse({
            'success': False,
            'error': 'A benchmark is already running',
            'pid': _benchmark_process.pid,
        }, status=409)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        data = {}

    model = data.get('model', 'gemini-pro')
    briefing = data.get('briefing', 'benchmark.md')
    skip_images = data.get('skip_images', True)

    # Build command
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script_path = os.path.join(project_root, 'scripts', 'benchmark_generate.py')
    briefing_path = os.path.join(project_root, 'briefings', briefing)

    if not os.path.isfile(script_path):
        return JsonResponse({'success': False, 'error': 'Benchmark script not found'}, status=400)
    if not os.path.isfile(briefing_path):
        return JsonResponse({'success': False, 'error': f'Briefing file not found: {briefing}'}, status=400)

    cmd = [sys.executable, script_path, os.path.join('briefings', briefing), '--model', model, '--delay', '0']
    if not skip_images:
        cmd.append('--with-images')

    # Open a temp file for combined stdout/stderr
    import tempfile
    _benchmark_output_file = tempfile.NamedTemporaryFile(
        mode='w', prefix='bench_', suffix='.log', delete=False
    )

    _benchmark_process = subprocess.Popen(
        cmd,
        stdout=_benchmark_output_file,
        stderr=subprocess.STDOUT,
        cwd=project_root,
    )

    return JsonResponse({
        'success': True,
        'pid': _benchmark_process.pid,
    })


@superuser_required
@require_http_methods(["GET"])
def benchmark_status(request):
    """
    Check the status of the running benchmark.

    Returns: {"running": true/false, "pid": ..., "exit_code": ..., "output_tail": "..."}
    """
    global _benchmark_process, _benchmark_output_file

    if _benchmark_process is None:
        return JsonResponse({'running': False, 'pid': None, 'exit_code': None, 'output_tail': ''})

    poll = _benchmark_process.poll()
    running = poll is None

    # Read tail of output file
    output_tail = ''
    if _benchmark_output_file and os.path.isfile(_benchmark_output_file.name):
        try:
            with open(_benchmark_output_file.name, 'r') as f:
                lines = f.readlines()
                output_tail = ''.join(lines[-30:])  # last 30 lines
        except Exception:
            pass

    result = {
        'running': running,
        'pid': _benchmark_process.pid,
        'exit_code': poll,
        'output_tail': output_tail,
    }

    # Clean up if process finished
    if not running:
        if _benchmark_output_file:
            try:
                _benchmark_output_file.close()
                os.unlink(_benchmark_output_file.name)
            except Exception:
                pass
            _benchmark_output_file = None

    return JsonResponse(result)


@superuser_required
@require_http_methods(["POST"])
def cancel_benchmark(request):
    """
    Cancel the running benchmark subprocess.
    """
    global _benchmark_process, _benchmark_output_file

    if _benchmark_process is None or _benchmark_process.poll() is not None:
        return JsonResponse({'success': False, 'error': 'No benchmark running'}, status=400)

    try:
        _benchmark_process.send_signal(signal.SIGTERM)
        _benchmark_process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        _benchmark_process.kill()
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

    if _benchmark_output_file:
        try:
            _benchmark_output_file.close()
            os.unlink(_benchmark_output_file.name)
        except Exception:
            pass
        _benchmark_output_file = None
    _benchmark_process = None

    return JsonResponse({'success': True, 'message': 'Benchmark cancelled'})


# === Data Sync API ===

def _check_sync_auth(request):
    """Validate Bearer token against SYNC_SECRET. Returns error response or None."""
    sync_secret = os.environ.get('SYNC_SECRET', '')
    if not sync_secret:
        return JsonResponse(
            {'success': False, 'error': 'SYNC_SECRET is not configured on the server'},
            status=500,
        )
    auth = request.META.get('HTTP_AUTHORIZATION', '')
    if not auth.startswith('Bearer '):
        return JsonResponse(
            {'success': False, 'error': 'Missing Authorization header'},
            status=401,
        )
    token = auth[7:]
    if not hmac.compare_digest(token, sync_secret):
        return JsonResponse(
            {'success': False, 'error': 'Invalid SYNC_SECRET'},
            status=403,
        )
    return None


def _truncate_sync_tables():
    """Delete all rows from sync tables in FK-safe order."""
    from core.management.commands.push_data import SYNC_TABLES_ORDERED

    is_sqlite = connection.vendor == 'sqlite'
    with connection.cursor() as cursor:
        if is_sqlite:
            cursor.execute('PRAGMA foreign_keys = OFF')
        try:
            for table in SYNC_TABLES_ORDERED:
                cursor.execute(f'DELETE FROM "{table}"')
        finally:
            if is_sqlite:
                cursor.execute('PRAGMA foreign_keys = ON')

    # Reset PostgreSQL sequences
    if connection.vendor == 'postgresql':
        with connection.cursor() as cursor:
            for table in SYNC_TABLES_ORDERED:
                cursor.execute(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), 1, false)"
                )


def _load_fixture(fixture_data):
    """Deserialize a JSON fixture list into the database. Returns count of objects loaded."""
    json_str = json.dumps(fixture_data)
    objects = list(deserialize('json', json_str))
    count = 0
    for obj in objects:
        obj.save()
        count += 1
    return count


@csrf_exempt
@require_http_methods(["POST"])
def data_sync_receive(request):
    """
    Receive a pushed fixture from push_data and load it into the database.

    POST /backoffice/api/data-sync/
    Authorization: Bearer <SYNC_SECRET>
    Body: JSON array of serialized Django objects
    """
    auth_err = _check_sync_auth(request)
    if auth_err:
        return auth_err

    try:
        fixture = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    if not isinstance(fixture, list):
        return JsonResponse({'success': False, 'error': 'Expected a JSON array'}, status=400)

    try:
        _truncate_sync_tables()
        count = _load_fixture(fixture)
        cache.clear()
        return JsonResponse({'success': True, 'loaded': count})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def data_sync_export(request):
    """
    Export database content as a JSON fixture for pull_data.

    GET /backoffice/api/data-sync-export/
    Authorization: Bearer <SYNC_SECRET>
    """
    auth_err = _check_sync_auth(request)
    if auth_err:
        return auth_err

    try:
        from core.management.commands.push_data import build_fixture
        fixture = build_fixture()
        return JsonResponse(fixture, safe=False)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
