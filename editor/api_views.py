"""
API views for the inline editor.
These endpoints allow staff users to edit page content directly from the frontend.
"""

import json
import re
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.admin.views.decorators import staff_member_required
from core.decorators import superuser_required
from django.views.decorators.csrf import csrf_exempt
from core.models import Page, SiteImage
from ai.models import RefinementSession
from bs4 import BeautifulSoup


def _sanitize_trans_vars(html):
    """Fix hyphenated {{ trans.xxx-yyy }} → {{ trans.xxx_yyy }} in HTML.
    Django templates don't allow hyphens in variable names."""
    def _fix(m):
        return m.group(1) + m.group(2).replace('-', '_') + m.group(3)
    return re.sub(
        r'(\{\{\s*trans\.)([a-z0-9_-]+)(\s*(?:\|[a-z]+)?\s*\}\})',
        _fix, html
    )


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
    print(f'[API] update_page_content called: {request.method} {request.path}')
    try:
        data = json.loads(request.body)
        page_id = data.get('page_id')
        field_key = data.get('field_key')
        language = data.get('language', 'pt')

        # Normalize field_key: hyphens → underscores (Django templates use {{ trans.xxx_yyy }})
        if field_key:
            field_key = field_key.replace('-', '_')

        print(f'[API] update_page_content data: page_id={page_id}, field_key={field_key}, lang={language}')
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
            }, status=400)

        # Update content translations
        content = page.content or {}
        if 'translations' not in content:
            content['translations'] = {}
        if language not in content['translations']:
            content['translations'][language] = {}

        content['translations'][language][field_key] = value
        page.content = content

        # Also ensure the HTML template uses {{ trans.field_key }} instead of
        # hardcoded text. Elements generated before templatization (or where it
        # was missed) have raw text that ignores the JSON translations.
        element_id = data.get('element_id') or field_key.replace('_', '-')
        if page.html_content:
            soup = BeautifulSoup(page.html_content, 'html.parser')
            element = soup.find(attrs={'data-element-id': element_id})
            if element:
                trans_var = '{{ trans.' + field_key + ' }}'
                element_html = str(element)
                has_var = trans_var in element_html
                if not has_var:
                    element.clear()
                    element.append(trans_var)
                    new_html = str(soup)
                    if new_html.startswith('<html><body>'):
                        new_html = new_html[12:-14]
                    page.html_content = new_html

            # Sanitize any remaining hyphenated trans vars in the full HTML
            page.html_content = _sanitize_trans_vars(page.html_content)

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
    print(f'[API] update_page_element_classes called: {request.method} {request.path}')
    try:
        data = json.loads(request.body)
        print(f'[API] update_page_element_classes data: page_id={data.get("page_id")}, element_id={data.get("element_id")}')
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
            }, status=400)

        if not page.html_content or page.html_content.strip() == '':
            return JsonResponse({
                'success': False,
                'error': 'Page has no HTML content'
            }, status=400)

        # Parse HTML with BeautifulSoup
        soup = BeautifulSoup(page.html_content, 'html.parser')

        # Find element by data-element-id (or id fallback for sections)
        element = soup.find(attrs={'data-element-id': element_id})
        if not element:
            element = soup.find(attrs={'id': element_id})

        if not element:
            return JsonResponse({
                'success': False,
                'error': f'Element with data-element-id="{element_id}" not found'
            }, status=400)

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

        page.html_content = _sanitize_trans_vars(new_html)
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
        "element_id": "button_primary",   (or null with old_value fallback)
        "attribute": "href",
        "value": "/new-page/",
        "old_value": "...",               (optional, fallback when element_id missing)
        "tag_name": "img"                 (optional, fallback when element_id missing)
    }
    """
    print(f'[API] update_page_element_attribute called: {request.method} {request.path}')
    try:
        data = json.loads(request.body)
        print(f'[API] update_page_element_attribute data: page_id={data.get("page_id")}, element_id={data.get("element_id")}, attr={data.get("attribute")}')
        page_id = data.get('page_id')
        element_id = data.get('element_id')
        attribute = data.get('attribute')
        value = data.get('value', '')
        old_value = data.get('old_value')
        tag_name = data.get('tag_name')

        if not page_id or not attribute:
            return JsonResponse({
                'success': False,
                'error': 'Missing required parameters: page_id, attribute'
            }, status=400)

        if not element_id and not old_value:
            return JsonResponse({
                'success': False,
                'error': 'Missing element_id and no old_value fallback'
            }, status=400)

        try:
            page = Page.objects.get(pk=page_id)
        except Page.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Page not found'
            }, status=400)

        # Parse HTML
        soup = BeautifulSoup(page.html_content, 'html.parser')

        # Find element by data-element-id
        element = None
        if element_id:
            element = soup.find(attrs={'data-element-id': element_id})
            # Also try matching by id attribute (sections use id but not data-element-id)
            if not element:
                element = soup.find(attrs={'id': element_id})

        # Fallback: find by old attribute value + tag name
        if not element and old_value and tag_name:
            element = soup.find(tag_name, attrs={attribute: old_value})

        if not element:
            return JsonResponse({
                'success': False,
                'error': f'Element not found (element_id={element_id}, tag={tag_name})'
            }, status=400)

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

        page.html_content = _sanitize_trans_vars(new_html)
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
    - search: Search in title and tags (optional)
    """
    try:
        images = SiteImage.objects.filter(is_active=True).order_by('-uploaded_at')

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
            'tags': img.tags or '',
        })

    return JsonResponse({'success': True, 'images': image_list})


@superuser_required
@require_http_methods(["POST"])
def refine_section(request):
    """
    Refine a single section using AI without saving to DB.
    Returns the section's html_template and content for client-side preview.

    Expected POST data:
    {
        "page_id": 1,
        "section_name": "hero",
        "instructions": "Make the title bolder",
        "conversation_history": [{"role": "user", "content": "..."}, ...],
        "model": "gemini-pro"
    }
    """
    try:
        data = json.loads(request.body)
        page_id = data.get('page_id')
        section_name = data.get('section_name')
        instructions = data.get('instructions', '').strip()
        conversation_history = data.get('conversation_history', [])
        model = data.get('model', 'gemini-flash')
        session_id = data.get('session_id')

        if not page_id or not section_name:
            return JsonResponse({
                'success': False,
                'error': 'Missing page_id or section_name'
            }, status=400)

        if not instructions:
            return JsonResponse({
                'success': False,
                'error': 'Missing instructions'
            }, status=400)

        page = Page.objects.get(pk=page_id)

        # Load or create RefinementSession
        session = None
        if session_id:
            try:
                session = RefinementSession.objects.get(id=session_id, page=page)
            except RefinementSession.DoesNotExist:
                session = None

        if not session:
            session = RefinementSession(
                page=page,
                title=f'[{section_name}] {instructions[:60]}',
                model_used=model,
                created_by=request.user if request.user.is_authenticated else None,
            )
            session.save()

        # Add user message to session
        session.add_user_message(instructions)

        from ai.services import ContentGenerationService
        service = ContentGenerationService(model_name=model)
        result = service.refine_section_only(
            page_id=page_id,
            section_name=section_name,
            instructions=instructions,
            conversation_history=conversation_history,
            model_override=model,
        )

        # Add assistant message to session
        assistant_msg = result.get('assistant_message', 'Changes applied.')
        session.add_assistant_message(assistant_msg, [section_name])
        session.save()

        return JsonResponse({
            'success': True,
            'section': {
                'html_template': result['html_template'],
                'content': result['content'],
            },
            'assistant_message': assistant_msg,
            'session_id': session.id,
        })

    except Page.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Page not found'
        }, status=400)
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


@superuser_required
@require_http_methods(["POST"])
def save_ai_section(request):
    """
    Save an AI-refined section to the page in DB.
    Replaces only the target section in html_content and merges translations.

    Expected POST data:
    {
        "page_id": 1,
        "section_name": "hero",
        "html_template": "<section data-section='hero'>...</section>",
        "content": {"translations": {"pt": {...}, "en": {...}}}
    }
    """
    try:
        data = json.loads(request.body)
        page_id = data.get('page_id')
        section_name = data.get('section_name')
        html_template = data.get('html_template', '')
        content = data.get('content', {})

        if not page_id or not section_name or not html_template:
            return JsonResponse({
                'success': False,
                'error': 'Missing page_id, section_name, or html_template'
            }, status=400)

        try:
            page = Page.objects.get(pk=page_id)
        except Page.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Page not found'
            }, status=400)

        # Create version for rollback
        page.create_version(user=request.user, change_summary=f'AI refined section: {section_name}')

        # Parse current page HTML and replace the target section
        soup = BeautifulSoup(page.html_content, 'html.parser')
        old_section = soup.find('section', attrs={'data-section': section_name})

        if not old_section:
            return JsonResponse({
                'success': False,
                'error': f'Section "{section_name}" not found in page HTML'
            }, status=400)

        # Parse the new section HTML
        new_section_soup = BeautifulSoup(html_template, 'html.parser')
        new_section = new_section_soup.find('section')
        if not new_section:
            # If the html_template is a full section tag, the parser might put it at top level
            new_section = new_section_soup

        old_section.replace_with(new_section)

        # Save updated HTML
        new_html = str(soup)
        if new_html.startswith('<html><body>'):
            new_html = new_html[12:-14]
        page.html_content = new_html

        # Merge translations (don't overwrite other sections' translations)
        new_translations = content.get('translations', {})
        page_content = page.content or {}
        if 'translations' not in page_content:
            page_content['translations'] = {}

        for lang_code, lang_trans in new_translations.items():
            if lang_code not in page_content['translations']:
                page_content['translations'][lang_code] = {}
            page_content['translations'][lang_code].update(lang_trans)

        page.content = page_content
        page.save()

        return JsonResponse({
            'success': True,
            'message': f'Section "{section_name}" saved successfully',
            'page_id': page.id,
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


@superuser_required
@require_http_methods(["POST"])
def refine_element(request):
    """
    Refine a single element using AI without saving to DB.
    Returns the element's html_template and content for client-side preview.

    Expected POST data:
    {
        "page_id": 1,
        "section_name": "hero",
        "element_id": "hero_cta_button",
        "instructions": "Make it larger with a gradient background",
        "conversation_history": [{"role": "user", "content": "..."}, ...],
        "session_id": null,
        "model": "gemini-flash"
    }
    """
    try:
        data = json.loads(request.body)
        page_id = data.get('page_id')
        section_name = data.get('section_name')
        element_id = data.get('element_id')
        instructions = data.get('instructions', '').strip()
        conversation_history = data.get('conversation_history', [])
        model = data.get('model', 'gemini-flash')
        session_id = data.get('session_id')

        if not page_id or not section_name or not element_id:
            return JsonResponse({
                'success': False,
                'error': 'Missing page_id, section_name, or element_id'
            }, status=400)

        if not instructions:
            return JsonResponse({
                'success': False,
                'error': 'Missing instructions'
            }, status=400)

        page = Page.objects.get(pk=page_id)

        # Load or create RefinementSession
        session = None
        if session_id:
            try:
                session = RefinementSession.objects.get(id=session_id, page=page)
            except RefinementSession.DoesNotExist:
                session = None

        if not session:
            session = RefinementSession(
                page=page,
                title=f'[{element_id}] {instructions[:60]}',
                model_used=model,
                created_by=request.user if request.user.is_authenticated else None,
            )
            session.save()

        session.add_user_message(instructions)

        from ai.services import ContentGenerationService
        service = ContentGenerationService(model_name=model)
        result = service.refine_element_only(
            page_id=page_id,
            section_name=section_name,
            element_id=element_id,
            instructions=instructions,
            conversation_history=conversation_history,
            model_override=model,
        )

        assistant_msg = result.get('assistant_message', 'Changes applied.')
        session.add_assistant_message(assistant_msg, [f'{section_name}/{element_id}'])
        session.save()

        return JsonResponse({
            'success': True,
            'element': {
                'html_template': result['html_template'],
                'content': result['content'],
            },
            'assistant_message': assistant_msg,
            'session_id': session.id,
        })

    except Page.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Page not found'
        }, status=400)
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


@superuser_required
@require_http_methods(["POST"])
def save_ai_element(request):
    """
    Save an AI-refined element to the page in DB.
    Finds the element by data-element-id and replaces it.

    Expected POST data:
    {
        "page_id": 1,
        "section_name": "hero",
        "element_id": "hero_cta_button",
        "html_template": "<a data-element-id='hero_cta_button' ...>...</a>",
        "content": {"translations": {"pt": {...}, "en": {...}}}
    }
    """
    try:
        data = json.loads(request.body)
        page_id = data.get('page_id')
        section_name = data.get('section_name', '')
        element_id = data.get('element_id')
        html_template = data.get('html_template', '')
        content = data.get('content', {})

        if not page_id or not element_id or not html_template:
            return JsonResponse({
                'success': False,
                'error': 'Missing page_id, element_id, or html_template'
            }, status=400)

        try:
            page = Page.objects.get(pk=page_id)
        except Page.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Page not found'
            }, status=400)

        # Create version for rollback
        page.create_version(
            user=request.user,
            change_summary=f'AI refined element: {element_id} in {section_name}'
        )

        # Parse current page HTML and find the target element (scoped to section if provided)
        soup = BeautifulSoup(page.html_content, 'html.parser')
        if section_name:
            section_el = soup.find('section', attrs={'data-section': section_name})
            old_element = section_el.find(attrs={'data-element-id': element_id}) if section_el else None
        else:
            old_element = None
        if not old_element:
            old_element = soup.find(attrs={'data-element-id': element_id})

        if not old_element:
            return JsonResponse({
                'success': False,
                'error': f'Element "{element_id}" not found in page HTML'
            }, status=400)

        # Parse the new element HTML
        new_element_soup = BeautifulSoup(html_template, 'html.parser')
        new_element = new_element_soup.find(attrs={'data-element-id': element_id})
        if not new_element:
            children = list(new_element_soup.children)
            new_element = children[0] if children else new_element_soup

        old_element.replace_with(new_element)

        # Save updated HTML
        new_html = str(soup)
        if new_html.startswith('<html><body>'):
            new_html = new_html[12:-14]
        page.html_content = new_html

        # Merge translations
        new_translations = content.get('translations', {})
        page_content = page.content or {}
        if 'translations' not in page_content:
            page_content['translations'] = {}

        for lang_code, lang_trans in new_translations.items():
            if lang_code not in page_content['translations']:
                page_content['translations'][lang_code] = {}
            page_content['translations'][lang_code].update(lang_trans)

        page.content = page_content
        page.save()

        return JsonResponse({
            'success': True,
            'message': f'Element "{element_id}" saved successfully',
            'page_id': page.id,
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
def update_section_video(request):
    """
    Update or remove the background video in a page section.
    Handles both direct video URLs (mp4) and YouTube links.

    Expected POST data:
    {
        "page_id": 1,
        "section_id": "test-bg-video",
        "video_url": "https://youtube.com/watch?v=..."  (or "" to remove)
    }
    """
    try:
        data = json.loads(request.body)
        page_id = data.get('page_id')
        section_id = data.get('section_id')
        video_url = data.get('video_url', '').strip()

        if not page_id or not section_id:
            return JsonResponse({
                'success': False,
                'error': 'Missing page_id or section_id'
            }, status=400)

        try:
            page = Page.objects.get(pk=page_id)
        except Page.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Page not found'
            }, status=400)

        soup = BeautifulSoup(page.html_content, 'html.parser')
        section = (
            soup.find('section', attrs={'data-section': section_id})
            or soup.find('section', attrs={'id': section_id})
        )

        if not section:
            return JsonResponse({
                'success': False,
                'error': f'Section "{section_id}" not found'
            }, status=400)

        # Remove existing background video/iframe
        old_video = section.find('video', recursive=False)
        old_iframe = None
        for iframe in section.find_all('iframe', recursive=False):
            if iframe.get('src', '') and 'youtube' in iframe.get('src', ''):
                old_iframe = iframe
                break

        if old_video:
            old_video.decompose()
        if old_iframe:
            old_iframe.decompose()

        if video_url:
            # Detect YouTube
            yt_match = re.search(
                r'(?:youtube\.com/watch\?.*v=|youtube\.com/embed/|youtu\.be/)([a-zA-Z0-9_-]{11})',
                video_url
            )

            if yt_match:
                # YouTube: insert <iframe> as first child
                yt_id = yt_match.group(1)
                embed_url = (
                    f'https://www.youtube.com/embed/{yt_id}'
                    f'?autoplay=1&mute=1&loop=1&controls=0&showinfo=0'
                    f'&playlist={yt_id}&playsinline=1'
                )
                new_el = soup.new_tag(
                    'iframe',
                    src=embed_url,
                    frameborder='0',
                    allow='autoplay; encrypted-media',
                    allowfullscreen='',
                    **{'class': 'absolute inset-0 w-full h-full pointer-events-none'}
                )
                # Scale iframe to cover section like a video
                new_el['style'] = (
                    'position:absolute;top:50%;left:50%;'
                    'width:100vw;height:56.25vw;'
                    'min-height:100%;min-width:177.77vh;'
                    'transform:translate(-50%,-50%);'
                )
            else:
                # Direct video URL: insert <video> as first child
                new_el = soup.new_tag(
                    'video',
                    autoplay='',
                    muted='',
                    loop='',
                    playsinline='',
                    **{'class': 'absolute inset-0 w-full h-full object-cover'}
                )
                source_tag = soup.new_tag('source', src=video_url, type='video/mp4')
                new_el.append(source_tag)

            # Insert as first child of section
            section.insert(0, new_el)

        # Save
        new_html = str(soup)
        if new_html.startswith('<html><body>'):
            new_html = new_html[12:-14]

        page.html_content = _sanitize_trans_vars(new_html)
        page.save()

        action = 'removed' if not video_url else ('YouTube' if video_url and 'youtu' in video_url else 'video')
        return JsonResponse({
            'success': True,
            'message': f'Background video {action} updated in section "{section_id}"',
            'page_id': page.id,
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


@superuser_required
@require_http_methods(["POST"])
def refine_page(request):
    """
    Refine the full page using AI without saving to DB.
    Returns html_template and content for client-side preview.

    POST /editor-v2/api/refine-page/
    {
        "page_id": 1,
        "instructions": "Make the hero section more impactful",
        "conversation_history": [{"role": "user", "content": "..."}, ...],
        "session_id": null
    }
    """
    try:
        data = json.loads(request.body)
        page_id = data.get('page_id')
        instructions = data.get('instructions', '').strip()
        conversation_history = data.get('conversation_history', [])
        session_id = data.get('session_id')

        if not page_id:
            return JsonResponse({'success': False, 'error': 'Missing page_id'}, status=400)
        if not instructions:
            return JsonResponse({'success': False, 'error': 'Missing instructions'}, status=400)

        try:
            page = Page.objects.get(id=page_id)
        except Page.DoesNotExist:
            return JsonResponse({'success': False, 'error': f'Page {page_id} not found'}, status=404)

        # Load or create session
        if session_id:
            try:
                session = RefinementSession.objects.get(id=session_id, page=page)
            except RefinementSession.DoesNotExist:
                session = None
        else:
            session = None

        if not session:
            session = RefinementSession(
                page=page,
                title=instructions[:80],
                model_used='gemini-pro',
                created_by=request.user if request.user.is_authenticated else None,
            )
            session.save()

        session.add_user_message(instructions)
        history = session.get_history_for_prompt()

        # Create version for rollback
        page.create_version(
            user=request.user,
            change_summary=f'Before editor refine-page: {instructions[:100]}'
        )

        # Call AI — full page refinement (gemini-pro)
        from ai.services import ContentGenerationService
        service = ContentGenerationService()
        result = service.refine_page_with_html(
            page_id=page_id,
            instructions=instructions,
            model_override='gemini-pro',
            conversation_history=history or None,
        )

        assistant_msg = "I've refined the page based on your instructions."
        session.add_assistant_message(assistant_msg, ['full-page'])
        session.save()

        return JsonResponse({
            'success': True,
            'page': {
                'html_template': result.get('html_content', ''),
                'content': result.get('content', {}),
            },
            'assistant_message': assistant_msg,
            'session_id': session.id,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@superuser_required
@require_http_methods(["POST"])
def save_ai_page(request):
    """
    Save full-page AI refinement result.

    POST /editor-v2/api/save-ai-page/
    {
        "page_id": 1,
        "html_template": "<section ...>...</section>...",
        "content": {"translations": {"pt": {...}, "en": {...}}}
    }
    """
    try:
        data = json.loads(request.body)
        page_id = data.get('page_id')
        html_template = data.get('html_template', '').strip()
        content = data.get('content', {})

        if not page_id or not html_template:
            return JsonResponse({'success': False, 'error': 'Missing page_id or html_template'}, status=400)

        try:
            page = Page.objects.get(id=page_id)
        except Page.DoesNotExist:
            return JsonResponse({'success': False, 'error': f'Page {page_id} not found'}, status=404)

        page.create_version(
            user=request.user,
            change_summary='Before save-ai-page (full page replacement)'
        )

        page.html_content = html_template
        if content:
            page.content = content
        page.save()

        return JsonResponse({
            'success': True,
            'message': 'Page saved successfully',
            'page_id': page.id,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@superuser_required
@require_http_methods(["GET"])
def get_editor_session(request, page_id):
    """
    Load sessions for the editor chat panel.

    GET /editor-v2/api/session/<page_id>/
    GET /editor-v2/api/session/<page_id>/?session_id=123

    Returns the requested (or most recent) session's messages,
    plus a list of all sessions for the session switcher dropdown.
    """
    try:
        # All sessions for this page (newest first), limited to recent 20
        all_sessions = RefinementSession.objects.filter(
            page_id=page_id
        ).order_by('-updated_at')[:20]

        sessions_list = [{
            'id': s.id,
            'title': s.title or f'Session {s.id}',
            'updated_at': s.updated_at.isoformat(),
        } for s in all_sessions]

        # Load specific session or most recent
        target_id = request.GET.get('session_id')
        if target_id:
            try:
                session = RefinementSession.objects.get(id=int(target_id), page_id=page_id)
            except RefinementSession.DoesNotExist:
                session = all_sessions.first() if all_sessions else None
        else:
            session = all_sessions.first() if all_sessions else None

        if not session:
            return JsonResponse({
                'success': True,
                'session_id': None,
                'messages': [],
                'sessions': sessions_list,
            })

        return JsonResponse({
            'success': True,
            'session_id': session.id,
            'messages': session.messages or [],
            'sessions': sessions_list,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
