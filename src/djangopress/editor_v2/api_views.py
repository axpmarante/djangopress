"""
API views for the inline editor.
These endpoints allow staff users to edit page content directly from the frontend.
"""

import json
import re
import queue
import threading
from django.http import JsonResponse
from django.utils.translation import get_language
from django.views.decorators.http import require_http_methods
from django.contrib.admin.views.decorators import staff_member_required
from djangopress.core.decorators import superuser_required
from django.views.decorators.csrf import csrf_exempt
from djangopress.core.models import Page, PageVersion, SiteImage, SiteSettings
from djangopress.ai.models import RefinementSession
from djangopress.ai.utils.llm_config import get_ai_model
from djangopress.ai.utils.sse import sse_event, sse_response
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Per-language HTML helpers
# ---------------------------------------------------------------------------

def _get_default_language():
    """Get the default language from SiteSettings."""
    settings = SiteSettings.load()
    return settings.get_default_language() if settings else 'pt'


def _detect_language_from_request(request, data=None):
    """Detect the current page language from the request context.

    Priority:
    1. Explicit 'language' field in POST data
    2. Language prefix from Referer URL (e.g., /pt/page?edit=v2 → 'pt')
    3. Default language from SiteSettings

    We intentionally skip get_language() because editor API endpoints are
    outside i18n_patterns, so it returns the browser's Accept-Language
    (usually 'en') rather than the actual page language.
    """
    import re as _re
    from urllib.parse import urlparse

    default_lang = _get_default_language()
    settings = SiteSettings.load()
    enabled_langs = settings.get_language_codes() if settings else ['pt', 'en']

    # 1. Explicit language in POST data
    if data and data.get('language'):
        return data['language']

    # 2. Extract from Referer URL
    referer = request.META.get('HTTP_REFERER', '')
    if referer:
        parsed = urlparse(referer)
        path = parsed.path  # e.g., /pt/?edit=v2 or /en/about/?edit=v2
        match = _re.match(r'^/([a-z]{2})(?:/|$)', path)
        if match and match.group(1) in enabled_langs:
            return match.group(1)

    # 3. Default language from SiteSettings
    # NOTE: We skip get_language() here because editor API endpoints are
    # outside i18n_patterns, so it returns the browser's Accept-Language
    # (usually 'en') rather than the page language the user is viewing.
    return default_lang


def _get_editable_object(data):
    """Get the editable object — either a Page or a generic model instance.

    If content_type_id and object_id are present, looks up via ContentType.
    Otherwise falls back to Page.objects.get(pk=page_id).
    Returns the model instance, or raises DoesNotExist.
    """
    content_type_id = data.get('content_type_id')
    object_id = data.get('object_id')

    if content_type_id and object_id:
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get(pk=content_type_id)
        return ct.get_object_for_this_type(pk=object_id)

    page_id = data.get('page_id')
    if not page_id:
        return None
    return Page.objects.get(pk=page_id)


def _get_page_html(page, lang=None):
    """Read page HTML from html_content_i18n.

    Args:
        page: Page or any model with html_content_i18n field
        lang: Language code (defaults to current language or default lang)

    Returns:
        tuple: (html_string, resolved_lang)
    """
    default_lang = _get_default_language()
    lang = lang or default_lang
    html_i18n = getattr(page, 'html_content_i18n', None) or {}
    html = html_i18n.get(lang) or html_i18n.get(default_lang) or ''
    return html, lang


def _save_page_html(page, html, lang, all_langs=False):
    """Save HTML to html_content_i18n.

    Args:
        page: Page or any model with html_content_i18n field (will be modified but NOT saved)
        html: The new HTML string
        lang: Language code to save for
        all_langs: If True, save the same HTML to ALL existing language copies
    """
    html_i18n = dict(getattr(page, 'html_content_i18n', None) or {})
    if all_langs:
        for existing_lang in list(html_i18n.keys()):
            html_i18n[existing_lang] = html
    html_i18n[lang] = html
    page.html_content_i18n = html_i18n


def _apply_structural_change_to_all_langs(page, change_fn):
    """Apply a structural HTML change (classes, attributes, video) to all language copies.

    Args:
        page: Page or any model with html_content_i18n field (will be modified but NOT saved)
        change_fn: A function(soup) that modifies the soup in-place and returns True on success.
                   If it returns False, that language copy is skipped.
    """
    html_i18n = dict(getattr(page, 'html_content_i18n', None) or {})

    for existing_lang, existing_html in html_i18n.items():
        if not existing_html:
            continue
        soup = BeautifulSoup(existing_html, 'html.parser')
        if change_fn(soup):
            new_html = str(soup)
            if new_html.startswith('<html><body>'):
                new_html = new_html[12:-14]
            html_i18n[existing_lang] = new_html

    page.html_content_i18n = html_i18n


# ---------------------------------------------------------------------------
# Lookup tools for instruction enrichment
# ---------------------------------------------------------------------------

def _lookup_list_pages(params):
    """List all pages with IDs, titles, slugs."""
    pages = Page.objects.all().order_by('sort_order', 'created_at')
    data = [{'id': p.id, 'title': p.title_i18n, 'slug': p.slug_i18n, 'is_active': p.is_active} for p in pages]
    return {'success': True, 'pages': data, 'message': f'{len(data)} pages found'}


def _lookup_get_page_info(params):
    """Get page metadata + list of section names."""
    page_id = params.get('page_id')
    title = params.get('title')

    if not page_id and not title:
        return {'success': False, 'message': 'Provide page_id or title'}

    page = None
    if page_id:
        try:
            page = Page.objects.get(pk=page_id)
        except Page.DoesNotExist:
            return {'success': False, 'message': f'Page {page_id} not found'}
    else:
        for p in Page.objects.all():
            if p.title_i18n and isinstance(p.title_i18n, dict):
                for lang, t in p.title_i18n.items():
                    if t and title.lower() in t.lower():
                        page = p
                        break
            if page:
                break
        if not page:
            return {'success': False, 'message': f'No page found matching "{title}"'}

    sections = []
    html, _ = _get_page_html(page)
    if html:
        soup = BeautifulSoup(html, 'html.parser')
        for sec in soup.find_all('section', attrs={'data-section': True}):
            sections.append(sec['data-section'])

    return {
        'success': True,
        'page': {
            'id': page.id,
            'title': page.title_i18n,
            'slug': page.slug_i18n,
            'sections': sections,
        },
        'message': f'Page "{page.default_title}" with {len(sections)} sections',
    }


def _lookup_get_section_html(params):
    """Get a section's de-templatized HTML from a page."""
    page_id = params.get('page_id')
    section_name = params.get('section_name')

    if not page_id or not section_name:
        return {'success': False, 'message': 'Provide page_id and section_name'}

    try:
        page = Page.objects.get(pk=page_id)
    except Page.DoesNotExist:
        return {'success': False, 'message': f'Page {page_id} not found'}

    page_html, resolved_lang = _get_page_html(page)
    if not page_html:
        return {'success': False, 'message': 'Page has no HTML content'}

    soup = BeautifulSoup(page_html, 'html.parser')
    section = soup.find('section', attrs={'data-section': section_name})
    if not section:
        return {'success': False, 'message': f'Section "{section_name}" not found in page'}

    html = str(section)

    # Truncate to avoid blowing up context
    if len(html) > 3000:
        html = html[:3000] + '\n<!-- truncated -->'

    return {'success': True, 'html': html, 'message': f'Section "{section_name}" HTML ({len(html)} chars)'}


_LOOKUP_TOOLS = {
    'list_pages': _lookup_list_pages,
    'get_page_info': _lookup_get_page_info,
    'get_section_html': _lookup_get_section_html,
}


# ---------------------------------------------------------------------------
# Instruction enrichment via tool-calling pre-processor
# ---------------------------------------------------------------------------

def _parse_enrichment_response(raw):
    """Parse LLM response for <refined_instructions> or <actions> tags."""
    match = re.search(r'<refined_instructions>(.*?)</refined_instructions>', raw, re.DOTALL)
    if match:
        return {'done': True, 'instructions': match.group(1).strip()}
    actions_match = re.search(r'<actions>(.*?)</actions>', raw, re.DOTALL)
    if actions_match:
        try:
            actions = json.loads(actions_match.group(1).strip())
            return {'done': False, 'actions': actions}
        except json.JSONDecodeError:
            pass
    return {'done': True, 'instructions': raw.strip()}


def _format_lookup_results(tool_name, result):
    """Format tool results compactly for feeding back to the LLM."""
    if tool_name == 'list_pages':
        pages = result.get('pages', [])
        lines = [f"ID:{p['id']} | {p.get('title', {})}" for p in pages]
        return f"Pages:\n" + "\n".join(lines)
    elif tool_name == 'get_page_info':
        page = result.get('page', {})
        sections = ', '.join(page.get('sections', []))
        return f"Page: {page.get('title', {})} (ID:{page.get('id')}), Sections: {sections}"
    elif tool_name == 'get_section_html':
        html = result.get('html', '')
        return f"```html\n{html}\n```"
    else:
        return json.dumps(result, default=str)


def _enrich_instructions(instructions, page):
    """
    Pre-process user instructions with lookup tools.
    If the instruction references other pages/sections, uses an LLM
    to look them up and produce an enriched instruction for the refinement LLM.
    Returns the original or enriched instruction string.
    """
    # Quick check: skip enrichment for simple instructions that don't reference other pages
    reference_keywords = [
        'like the', 'like on', 'match the', 'same as', 'copy from', 'similar to',
        'from the', 'on the', 'other page', 'another page', 'about page',
        'home page', 'services page', 'contact page',
    ]
    lower_inst = instructions.lower()
    if not any(kw in lower_inst for kw in reference_keywords):
        return instructions

    try:
        from djangopress.ai.utils.llm_config import LLMBase

        # Build page title for context
        page_title = page.default_title if hasattr(page, 'default_title') else str(page.title_i18n)

        system_prompt = (
            "You are a pre-processor for a website page editor. The user wants to refine part of a page.\n"
            "If the instruction references another page, section, or style you don't have context for, "
            "use the available tools to look it up. Then output the final enriched instruction inside "
            "<refined_instructions> tags with all the context the refinement LLM will need.\n\n"
            "If no lookups are needed, output the instruction unchanged in <refined_instructions> tags.\n\n"
            "Available tools (call via <actions> JSON array):\n"
            '- `list_pages` — List all pages with IDs and titles. No params needed.\n'
            '- `get_page_info` — Get page sections. Params: {"page_id": int} OR {"title": "search"}\n'
            '- `get_section_html` — Get a section\'s HTML. Params: {"page_id": int, "section_name": "hero"}\n\n'
            "To call tools, output:\n"
            '<actions>[{"tool": "tool_name", "params": {...}}]</actions>\n\n'
            "After receiving tool results, output:\n"
            "<refined_instructions>enriched instruction with full context</refined_instructions>\n\n"
            f'Current page: "{page_title}" (ID: {page.id})'
        )

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': instructions},
        ]

        llm = LLMBase()

        for iteration in range(3):
            response = llm.get_completion(messages, tool_name=get_ai_model('refinement_section'))
            raw = response.choices[0].message.content

            parsed = _parse_enrichment_response(raw)

            if parsed['done']:
                enriched = parsed['instructions']
                print(f"[Enrich] Done after {iteration} tool calls. Enriched: {enriched[:200]}...")
                return enriched

            # Execute tool calls
            actions = parsed['actions']
            results_text = []
            for action in actions:
                tool_name = action.get('tool', '')
                params = action.get('params', {})
                tool_fn = _LOOKUP_TOOLS.get(tool_name)
                if tool_fn:
                    result = tool_fn(params)
                    formatted = _format_lookup_results(tool_name, result)
                    results_text.append(f"[{tool_name}] {formatted}")
                else:
                    results_text.append(f"[{tool_name}] Unknown tool")

            # Feed results back to the LLM
            messages.append({'role': 'assistant', 'content': raw})
            messages.append({'role': 'user', 'content': "Tool results:\n" + "\n\n".join(results_text)})

        # All 3 tool iterations used — one final LLM call to get the enriched instruction
        messages.append({'role': 'user', 'content': 'Now output the final enriched instruction in <refined_instructions> tags.'})
        response = llm.get_completion(messages, tool_name=get_ai_model('refinement_section'))
        raw = response.choices[0].message.content
        parsed = _parse_enrichment_response(raw)
        if parsed['done']:
            enriched = parsed['instructions']
            print(f"[Enrich] Done after final call. Enriched: {enriched[:200]}...")
            return enriched

        # True fallback
        print("[Enrich] Could not extract enriched instructions, using original")
        return instructions

    except Exception as e:
        print(f"[Enrich] Error during enrichment: {e}")
        return instructions


@staff_member_required
@require_http_methods(["POST"])
def update_page_content(request):
    """
    Update a Page's per-language HTML for an inline text edit.

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

        print(f'[API] update_page_content data: page_id={page_id}, field_key={field_key}, lang={language}')
        value = data.get('value', '').strip() if isinstance(data.get('value'), str) else data.get('value')

        selector = data.get('selector')

        try:
            page = _get_editable_object(data)
        except Exception:
            page = None
        if not page:
            return JsonResponse({
                'success': False,
                'error': 'Page or editable object not found'
            }, status=400)

        if not field_key and not selector:
            return JsonResponse({
                'success': False,
                'error': 'Missing field_key or selector'
            }, status=400)

        # --- Update per-language HTML in html_content_i18n ---
        html_i18n = dict(getattr(page, 'html_content_i18n', None) or {})
        lang_html = html_i18n.get(language, '')

        if lang_html and selector:
            soup = BeautifulSoup(lang_html, 'html.parser')
            element = soup.select_one(selector)
            if element:
                element.clear()
                element.append(value)

                new_html = str(soup)
                if new_html.startswith('<html><body>'):
                    new_html = new_html[12:-14]
                html_i18n[language] = new_html

        page.html_content_i18n = html_i18n
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
    Uses BeautifulSoup to parse HTML and update specific elements by CSS selector.

    Expected POST data:
    {
        "page_id": 1,
        "selector": "section[data-section='hero'] > div > h1",
        "new_classes": "text-5xl font-black text-white"
    }
    """
    print(f'[API] update_page_element_classes called: {request.method} {request.path}')
    try:
        data = json.loads(request.body)
        print(f'[API] update_page_element_classes data: page_id={data.get("page_id")}, selector={data.get("selector")}')
        page_id = data.get('page_id')
        selector = data.get('selector')
        new_classes = data.get('new_classes', '').strip()

        if not selector:
            return JsonResponse({
                'success': False,
                'error': 'Missing selector'
            }, status=400)

        try:
            page = _get_editable_object(data)
        except Exception:
            page = None
        if not page:
            return JsonResponse({
                'success': False,
                'error': 'Page or editable object not found'
            }, status=400)

        # Read HTML from current language for validation
        current_html, resolved_lang = _get_page_html(page)
        if not current_html or current_html.strip() == '':
            return JsonResponse({
                'success': False,
                'error': 'Page has no HTML content'
            }, status=400)

        # Validate element exists in current language
        soup = BeautifulSoup(current_html, 'html.parser')
        element = soup.select_one(selector)

        if not element:
            return JsonResponse({
                'success': False,
                'error': f'Element not found for selector'
            }, status=400)

        # Store old classes
        old_classes = ' '.join(element.get('class', []))

        # Apply structural change to ALL language copies (+ legacy fallback)
        def apply_classes(s):
            el = s.select_one(selector)
            if not el:
                return False
            if new_classes:
                el['class'] = new_classes.split()
            else:
                if 'class' in el.attrs:
                    del el['class']
            return True

        _apply_structural_change_to_all_langs(page, apply_classes)
        page.save()

        return JsonResponse({
            'success': True,
            'message': 'Element classes updated',
            'page_id': page.id,
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
        "selector": "section[data-section='hero'] > div > a",   (or null with old_value fallback)
        "attribute": "href",
        "value": "/new-page/",
        "old_value": "...",               (optional, fallback when selector missing)
        "tag_name": "img"                 (optional, fallback when selector missing)
    }
    """
    print(f'[API] update_page_element_attribute called: {request.method} {request.path}')
    try:
        data = json.loads(request.body)
        print(f'[API] update_page_element_attribute data: page_id={data.get("page_id")}, selector={data.get("selector")}, attr={data.get("attribute")}')
        page_id = data.get('page_id')
        selector = data.get('selector')
        attribute = data.get('attribute')
        value = data.get('value', '')
        old_value = data.get('old_value')
        tag_name = data.get('tag_name')

        if not attribute:
            return JsonResponse({
                'success': False,
                'error': 'Missing required parameter: attribute'
            }, status=400)

        if not selector and not old_value:
            return JsonResponse({
                'success': False,
                'error': 'Missing selector and no old_value fallback'
            }, status=400)

        try:
            page = _get_editable_object(data)
        except Exception:
            page = None
        if not page:
            return JsonResponse({
                'success': False,
                'error': 'Page or editable object not found'
            }, status=400)

        # Read HTML from current language for validation
        current_html, resolved_lang = _get_page_html(page)

        # Parse HTML
        soup = BeautifulSoup(current_html, 'html.parser')

        # Find element by CSS selector
        element = None
        if selector:
            element = soup.select_one(selector)

        # Fallback: find by old attribute value + tag name
        if not element and old_value and tag_name:
            element = soup.find(tag_name, attrs={attribute: old_value})

        if not element:
            return JsonResponse({
                'success': False,
                'error': f'Element not found (selector={selector}, tag={tag_name})'
            }, status=400)

        # Store old value
        old_value = element.get(attribute, '')

        # Apply structural change to ALL language copies (+ legacy fallback)
        def apply_attribute(s):
            el = None
            if selector:
                el = s.select_one(selector)
            if not el and old_value and tag_name:
                el = s.find(tag_name, attrs={attribute: old_value})
            if not el:
                return False
            if value:
                el[attribute] = value
            else:
                if attribute in el.attrs:
                    del el[attribute]
            return True

        _apply_structural_change_to_all_langs(page, apply_attribute)
        page.save()

        return JsonResponse({
            'success': True,
            'message': f'Element attribute "{attribute}" updated',
            'page_id': page.id,
            'selector': selector,
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
        model = data.get('model') or get_ai_model('refinement_section')
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

        # Enrich instructions with cross-page context if needed
        instructions = _enrich_instructions(instructions, page)

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

        from djangopress.ai.services import ContentGenerationService
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

        # Service returns {'options': [{'html': ...}], 'assistant_message': ...}
        options = result.get('options', [])
        page = Page.objects.get(id=page_id)
        html_i18n = page.html_content_i18n or {}
        available_languages = [lang for lang in html_i18n.keys()] if len(html_i18n) > 1 else []

        return JsonResponse({
            'success': True,
            'options': options,
            'assistant_message': assistant_msg,
            'session_id': session.id,
            'available_languages': available_languages,
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
    Replaces only the target section in html_content_i18n for the current language.

    Expected POST data:
    {
        "page_id": 1,
        "section_name": "hero",
        "html_template": "<section data-section='hero'>...</section>"
    }
    """
    try:
        data = json.loads(request.body)
        page_id = data.get('page_id')
        section_name = data.get('section_name')
        html_template = data.get('html_template', '')

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

        # Determine current language
        lang = _detect_language_from_request(request, data)

        # Read HTML for the current language
        current_html, resolved_lang = _get_page_html(page, lang)

        # Parse current page HTML and replace the target section
        soup = BeautifulSoup(current_html, 'html.parser')
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

        # Save updated HTML to html_content_i18n for current language
        new_html = str(soup)
        if new_html.startswith('<html><body>'):
            new_html = new_html[12:-14]
        _save_page_html(page, new_html, lang)
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
        "selector": "section[data-section='hero'] > div > a.btn",
        "instructions": "Make it larger with a gradient background",
        "conversation_history": [{"role": "user", "content": "..."}, ...],
        "session_id": null,
        "model": "gemini-flash"
    }
    """
    try:
        data = json.loads(request.body)
        page_id = data.get('page_id')
        selector = data.get('selector')
        instructions = data.get('instructions', '').strip()
        conversation_history = data.get('conversation_history', [])
        model = data.get('model') or get_ai_model('refinement_element')
        session_id = data.get('session_id')

        if not page_id or not selector:
            return JsonResponse({
                'success': False,
                'error': 'Missing page_id or selector'
            }, status=400)

        if not instructions:
            return JsonResponse({
                'success': False,
                'error': 'Missing instructions'
            }, status=400)

        page = Page.objects.get(pk=page_id)

        # Enrich instructions with cross-page context if needed
        instructions = _enrich_instructions(instructions, page)

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
                title=f'[element] {instructions[:60]}',
                model_used=model,
                created_by=request.user if request.user.is_authenticated else None,
            )
            session.save()

        session.add_user_message(instructions)

        from djangopress.ai.services import ContentGenerationService
        service = ContentGenerationService(model_name=model)
        result = service.refine_element_only(
            page_id=page_id,
            selector=selector,
            instructions=instructions,
            conversation_history=conversation_history,
            model_override=model,
        )

        assistant_msg = result.get('assistant_message', 'Changes applied.')
        session.add_assistant_message(assistant_msg, ['element'])
        session.save()

        # Service returns {'options': [{'html': ...}], 'assistant_message': ...}
        options = result.get('options', [])
        page = Page.objects.get(id=page_id)
        html_i18n = page.html_content_i18n or {}
        available_languages = [lang for lang in html_i18n.keys()] if len(html_i18n) > 1 else []

        return JsonResponse({
            'success': True,
            'options': options,
            'assistant_message': assistant_msg,
            'session_id': session.id,
            'available_languages': available_languages,
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
    Finds the element by CSS selector and replaces it.

    Expected POST data:
    {
        "page_id": 1,
        "selector": "section[data-section='hero'] > div > a.btn",
        "html_template": "<a ...>...</a>"
    }
    """
    try:
        data = json.loads(request.body)
        page_id = data.get('page_id')
        section_name = data.get('section_name', '')
        selector = data.get('selector')
        html_template = data.get('html_template', '')

        if not page_id or not selector or not html_template:
            return JsonResponse({
                'success': False,
                'error': 'Missing page_id, selector, or html_template'
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
            change_summary=f'AI refined element'
        )

        # Determine current language
        lang = _detect_language_from_request(request, data)

        # Read HTML for the current language
        current_html, resolved_lang = _get_page_html(page, lang)

        # Parse current page HTML and find the target element
        soup = BeautifulSoup(current_html, 'html.parser')
        old_element = soup.select_one(selector)

        if not old_element:
            return JsonResponse({
                'success': False,
                'error': 'Element not found for selector'
            }, status=400)

        # Parse the new element HTML — find by data-target marker or use first child
        new_element_soup = BeautifulSoup(html_template, 'html.parser')
        new_element = new_element_soup.find(attrs={'data-target': 'true'})
        if new_element:
            del new_element['data-target']
        if not new_element:
            children = list(new_element_soup.children)
            new_element = children[0] if children else new_element_soup

        old_element.replace_with(new_element)

        # Save updated HTML to html_content_i18n for current language
        new_html = str(soup)
        if new_html.startswith('<html><body>'):
            new_html = new_html[12:-14]
        _save_page_html(page, new_html, lang)
        page.save()

        return JsonResponse({
            'success': True,
            'message': 'Element saved successfully',
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
def refine_multi(request):
    """
    Refine a section or element, returning 3 variations for the user to pick from.
    No templatize step — returns raw HTML with real text.
    """
    try:
        data = json.loads(request.body)
        page_id = data.get('page_id')
        scope = data.get('scope', 'section')
        section_name = data.get('section_name')
        selector = data.get('selector')
        instructions = data.get('instructions', '').strip()
        conversation_history = data.get('conversation_history', [])
        session_id = data.get('session_id')
        mode = data.get('mode', 'refine')
        insert_after = data.get('insert_after')
        multi_option = data.get('multi_option', True)

        if not instructions:
            return JsonResponse({'success': False, 'error': 'Missing instructions'}, status=400)

        if mode != 'create':
            if scope == 'element' and not selector:
                return JsonResponse({'success': False, 'error': 'Missing selector for element scope'}, status=400)
            if scope == 'section' and not section_name:
                return JsonResponse({'success': False, 'error': 'Missing section_name for section scope'}, status=400)

        try:
            page = _get_editable_object(data)
        except Exception:
            page = None
        if not page:
            return JsonResponse({'success': False, 'error': 'Page or editable object not found'}, status=400)

        # Load or create RefinementSession
        is_page = isinstance(page, Page)
        session = None
        if session_id:
            try:
                if is_page:
                    session = RefinementSession.objects.get(id=session_id, page=page)
                else:
                    from django.contrib.contenttypes.models import ContentType
                    ct = ContentType.objects.get_for_model(page)
                    session = RefinementSession.objects.get(id=session_id, content_type=ct, object_id=page.pk)
            except RefinementSession.DoesNotExist:
                session = None

        if not session:
            if mode == 'create':
                prefix = '[new section]'
            elif scope == 'element':
                prefix = '[element]'
            else:
                prefix = f'[{section_name}]'
            session_kwargs = {
                'title': f'{prefix} {instructions[:60]}',
                'model_used': get_ai_model('refinement_section'),
                'created_by': request.user if request.user.is_authenticated else None,
            }
            if is_page:
                session_kwargs['page'] = page
            else:
                from django.contrib.contenttypes.models import ContentType
                ct = ContentType.objects.get_for_model(page)
                session_kwargs['content_type'] = ct
                session_kwargs['object_id'] = page.pk
            session = RefinementSession(**session_kwargs)
            session.save()

        session.add_user_message(instructions)

        # Route through refinement agent if enabled
        from django.conf import settings as django_settings
        use_agent = getattr(django_settings, 'USE_REFINEMENT_AGENT', True)

        if use_agent and mode != 'create':
            try:
                from djangopress.ai.refinement_agent.agent import RefinementAgent
                agent = RefinementAgent()
                result = agent.handle(
                    instruction=instructions,
                    scope=scope,
                    target_name=section_name if scope == 'section' else selector,
                    page=page,
                    conversation_history=conversation_history,
                    multi_option=multi_option,
                    mode=mode,
                    insert_after=insert_after,
                )
            except Exception as e:
                # Agent failed — fall back to direct pipeline
                print(f"Agent error, falling back to direct pipeline: {e}")
                import traceback
                traceback.print_exc()
                use_agent = False

        if not use_agent or mode == 'create':
            from djangopress.ai.services import ContentGenerationService
            service = ContentGenerationService(model_name=get_ai_model('generation'))

            if mode == 'create':
                result = service.generate_section(
                    page_id=page_id,
                    insert_after=insert_after,
                    instructions=instructions,
                    conversation_history=conversation_history,
                )
            elif scope == 'element':
                result = service.refine_element_only(
                    page_id=page_id,
                    selector=selector,
                    instructions=instructions,
                    conversation_history=conversation_history,
                    multi_option=multi_option,
                )
            else:
                result = service.refine_section_only(
                    page_id=page_id,
                    section_name=section_name,
                    instructions=instructions,
                    conversation_history=conversation_history,
                    multi_option=multi_option,
                )

        assistant_msg = result.get('assistant_message', 'Here are 3 variations.')
        if mode == 'create':
            target = f'new_after_{insert_after or "top"}'
        else:
            target = 'element' if scope == 'element' else section_name
        session.add_assistant_message(assistant_msg, [target])
        session.save()

        return JsonResponse({
            'success': True,
            'options': result.get('options', []),
            'assistant_message': assistant_msg,
            'session_id': session.id,
        })

    except Page.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Page not found'}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@superuser_required
@require_http_methods(["POST"])
def apply_option(request):
    """
    Save the chosen option's clean HTML directly to html_content_i18n[lang].
    No templatize step — the HTML already contains real text in the target language.
    """
    try:
        data = json.loads(request.body)
        page_id = data.get('page_id')
        scope = data.get('scope', 'section')
        section_name = data.get('section_name')
        selector = data.get('selector')
        html = data.get('html', '').strip()
        mode = data.get('mode', 'replace')
        insert_after = data.get('insert_after')

        if not html:
            return JsonResponse({'success': False, 'error': 'Missing html'}, status=400)

        try:
            page = _get_editable_object(data)
        except Exception:
            page = None
        if not page:
            return JsonResponse({'success': False, 'error': 'Page or editable object not found'}, status=400)

        # Detect language from request context (Referer URL, not get_language())
        lang = _detect_language_from_request(request, data)

        print(f"\n=== apply_option ===")
        print(f"Page ID: {page_id}, Scope: {scope}, Section: {section_name}")
        print(f"Language detected: {lang} (from Referer: {request.META.get('HTTP_REFERER', 'none')})")
        print(f"get_language(): {get_language()}")
        print(f"HTML to save: {len(html)} chars")
        html_i18n_keys = list((getattr(page, 'html_content_i18n', None) or {}).keys())
        print(f"html_content_i18n keys: {html_i18n_keys}")

        # Read current HTML for this language
        current_html, resolved_lang = _get_page_html(page, lang)
        print(f"Current HTML for [{lang}]: {len(current_html)} chars (resolved from [{resolved_lang}])")

        # Create version for rollback BEFORE modifying (only if model supports it)
        if hasattr(page, 'create_version'):
            page.create_version(
                user=request.user,
                change_summary=f'AI {"new section" if mode == "insert" else "multi-option"} applied'
            )

        if mode == 'insert':
            # Insert new section into page
            soup = BeautifulSoup(current_html or '', 'html.parser')
            new_soup = BeautifulSoup(html, 'html.parser')
            new_section = new_soup.find('section')
            if not new_section:
                return JsonResponse({'success': False, 'error': 'No section found in generated HTML'}, status=400)

            if insert_after:
                anchor = soup.find('section', attrs={'data-section': insert_after})
                if anchor:
                    anchor.insert_after(new_section)
                else:
                    soup.append(new_section)
            else:
                first_section = soup.find('section')
                if first_section:
                    first_section.insert_before(new_section)
                else:
                    soup.append(new_section)

            new_html = str(soup)
            if new_html.startswith('<html><body>'):
                new_html = new_html[12:-14]
            _save_page_html(page, new_html, lang)

        elif scope == 'element' and selector:
            # Surgical element replacement
            soup = BeautifulSoup(current_html, 'html.parser')
            old_element = soup.select_one(selector)
            if not old_element:
                return JsonResponse({'success': False, 'error': 'Element not found for selector'}, status=400)

            new_soup = BeautifulSoup(html, 'html.parser')
            children = list(new_soup.children)
            new_element = children[0] if children else new_soup

            old_element.replace_with(new_element)
            new_html = str(soup)
            if new_html.startswith('<html><body>'):
                new_html = new_html[12:-14]
            _save_page_html(page, new_html, lang)

        else:
            # Surgical section replacement
            soup = BeautifulSoup(current_html, 'html.parser')
            old_section = soup.find('section', attrs={'data-section': section_name})
            if not old_section:
                return JsonResponse({'success': False, 'error': f'Section "{section_name}" not found'}, status=400)

            new_soup = BeautifulSoup(html, 'html.parser')
            new_section = new_soup.find('section', attrs={'data-section': section_name})
            if not new_section:
                new_section = new_soup.find('section')
            if not new_section:
                return JsonResponse({'success': False, 'error': 'No section found in generated HTML'}, status=400)

            old_section.replace_with(new_section)
            new_html = str(soup)
            if new_html.startswith('<html><body>'):
                new_html = new_html[12:-14]
            _save_page_html(page, new_html, lang)

        page.save()

        # Auto-translate ONLY the changed section/element to other languages
        site_settings = SiteSettings.objects.first()
        default_language = site_settings.get_default_language() if site_settings else 'pt'
        all_languages = site_settings.get_language_codes() if site_settings else [default_language]
        other_languages = [l for l in all_languages if l != lang]
        translated_langs = []

        if other_languages:
            html_i18n = dict(page.html_content_i18n or {})
            print(f"Auto-translating {scope} to {other_languages} ({len(html)} chars)...")

            from djangopress.ai.services import ContentGenerationService
            service = ContentGenerationService(model_name=get_ai_model('translation'))

            for target_lang in other_languages:
                try:
                    # Translate only the changed snippet
                    translated_snippet = service.translate_html(html, lang, target_lang)
                    print(f"  Translated snippet [{lang}] → [{target_lang}]: {len(translated_snippet)} chars")

                    # Surgically insert/replace in the target language's full page HTML
                    target_html = html_i18n.get(target_lang) or html_i18n.get(default_language) or ''
                    target_soup = BeautifulSoup(target_html, 'html.parser')
                    snippet_soup = BeautifulSoup(translated_snippet, 'html.parser')

                    if mode == 'insert':
                        new_section = snippet_soup.find('section')
                        if new_section:
                            if insert_after:
                                anchor = target_soup.find('section', attrs={'data-section': insert_after})
                                if anchor:
                                    anchor.insert_after(new_section)
                                else:
                                    target_soup.append(new_section)
                            else:
                                first_section = target_soup.find('section')
                                if first_section:
                                    first_section.insert_before(new_section)
                                else:
                                    target_soup.append(new_section)

                    elif scope == 'element' and selector:
                        old_el = target_soup.select_one(selector)
                        if old_el:
                            children = list(snippet_soup.children)
                            new_el = children[0] if children else snippet_soup
                            old_el.replace_with(new_el)

                    else:
                        # Section replacement — match by data-section
                        new_sec = snippet_soup.find('section', attrs={'data-section': section_name})
                        if not new_sec:
                            new_sec = snippet_soup.find('section')
                        old_sec = target_soup.find('section', attrs={'data-section': section_name})
                        if old_sec and new_sec:
                            old_sec.replace_with(new_sec)

                    result_html = str(target_soup)
                    if result_html.startswith('<html><body>'):
                        result_html = result_html[12:-14]
                    html_i18n[target_lang] = result_html
                    translated_langs.append(target_lang)

                except Exception as e:
                    print(f"  Translation [{lang}] → [{target_lang}] failed: {e}")
                    translated_langs.append(f"{target_lang}(failed)")

            page.html_content_i18n = html_i18n
            page.save(update_fields=['html_content_i18n'])
            print(f"  Auto-translation complete")

        # Debug: verify save
        page.refresh_from_db()
        saved_i18n = getattr(page, 'html_content_i18n', None) or {}
        print(f"After save — html_content_i18n keys: {list(saved_i18n.keys())}")
        for k, v in saved_i18n.items():
            print(f"  [{k}]: {len(v)} chars")
        print(f"=== apply_option done ===\n")

        msg = f'{scope.capitalize()} saved successfully'
        if translated_langs:
            msg += f' (translated to {", ".join(translated_langs)})'

        return JsonResponse({
            'success': True,
            'message': msg,
            'page_id': page.id,
        })

    except Page.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Page not found'}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


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

        if not section_id:
            return JsonResponse({
                'success': False,
                'error': 'Missing section_id'
            }, status=400)

        try:
            page = _get_editable_object(data)
        except Exception:
            page = None
        if not page:
            return JsonResponse({
                'success': False,
                'error': 'Page or editable object not found'
            }, status=400)

        # Validate section exists in current language HTML
        current_html, resolved_lang = _get_page_html(page)
        soup = BeautifulSoup(current_html, 'html.parser')
        section = (
            soup.find('section', attrs={'data-section': section_id})
            or soup.find('section', attrs={'id': section_id})
        )

        if not section:
            return JsonResponse({
                'success': False,
                'error': f'Section "{section_id}" not found'
            }, status=400)

        # Apply video change to ALL language copies (structural change)
        def apply_video(s):
            sec = (
                s.find('section', attrs={'data-section': section_id})
                or s.find('section', attrs={'id': section_id})
            )
            if not sec:
                return False

            # Remove existing background video/iframe
            old_vid = sec.find('video', recursive=False)
            old_ifr = None
            for ifr in sec.find_all('iframe', recursive=False):
                if ifr.get('src', '') and 'youtube' in ifr.get('src', ''):
                    old_ifr = ifr
                    break
            if old_vid:
                old_vid.decompose()
            if old_ifr:
                old_ifr.decompose()

            if video_url:
                yt_match = re.search(
                    r'(?:youtube\.com/watch\?.*v=|youtube\.com/embed/|youtu\.be/)([a-zA-Z0-9_-]{11})',
                    video_url
                )
                if yt_match:
                    yt_id = yt_match.group(1)
                    embed_url = (
                        f'https://www.youtube.com/embed/{yt_id}'
                        f'?autoplay=1&mute=1&loop=1&controls=0&showinfo=0'
                        f'&playlist={yt_id}&playsinline=1'
                    )
                    new_el = s.new_tag(
                        'iframe',
                        src=embed_url,
                        frameborder='0',
                        allow='autoplay; encrypted-media',
                        allowfullscreen='',
                        **{'class': 'absolute inset-0 w-full h-full pointer-events-none'}
                    )
                    new_el['style'] = (
                        'position:absolute;top:50%;left:50%;'
                        'width:100vw;height:56.25vw;'
                        'min-height:100%;min-width:177.77vh;'
                        'transform:translate(-50%,-50%);'
                    )
                else:
                    new_el = s.new_tag(
                        'video',
                        autoplay='',
                        muted='',
                        loop='',
                        playsinline='',
                        **{'class': 'absolute inset-0 w-full h-full object-cover'}
                    )
                    source_tag = s.new_tag('source', src=video_url, type='video/mp4')
                    new_el.append(source_tag)

                sec.insert(0, new_el)
            return True

        _apply_structural_change_to_all_langs(page, apply_video)
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

        # Enrich instructions with cross-page context if needed
        instructions = _enrich_instructions(instructions, page)

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
                model_used=get_ai_model('refinement_page'),
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

        # Call AI — full page refinement
        from djangopress.ai.services import ContentGenerationService
        service = ContentGenerationService()
        result = service.refine_page_with_html(
            page_id=page_id,
            instructions=instructions,
            model_override=get_ai_model('refinement_page'),
            conversation_history=history or None,
        )

        assistant_msg = "I've refined the page based on your instructions."
        session.add_assistant_message(assistant_msg, ['full-page'])
        session.save()

        html_i18n = page.html_content_i18n or {}
        available_languages = [lang for lang in html_i18n.keys()] if len(html_i18n) > 1 else []

        return JsonResponse({
            'success': True,
            'page': {
                'html_content_i18n': result.get('html_content_i18n', {}),
            },
            'assistant_message': assistant_msg,
            'session_id': session.id,
            'available_languages': available_languages,
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
        "html_template": "<section ...>...</section>..."
    }
    """
    try:
        data = json.loads(request.body)
        page_id = data.get('page_id')
        html_template = data.get('html_template', '').strip()

        if not html_template:
            return JsonResponse({'success': False, 'error': 'Missing html_template'}, status=400)

        try:
            page = _get_editable_object(data)
        except Exception:
            page = None
        if not page:
            return JsonResponse({'success': False, 'error': 'Page or editable object not found'}, status=404)

        if hasattr(page, 'create_version'):
            page.create_version(
                user=request.user,
                change_summary='Before save-ai-page (full page replacement)'
            )

        # Determine current language
        lang = _detect_language_from_request(request, data)

        # Save to html_content_i18n for current language
        _save_page_html(page, html_template, lang)
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


@superuser_required
@require_http_methods(["GET"])
def list_page_versions(request, page_id):
    """
    List all versions for a page (newest first, max 10).

    GET /editor-v2/api/versions/<page_id>/
    """
    try:
        page = Page.objects.get(pk=page_id)
    except Page.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Page not found'}, status=404)

    versions = page.versions.order_by('-version_number')[:10]
    return JsonResponse({
        'success': True,
        'versions': [{
            'id': v.id,
            'version_number': v.version_number,
            'change_summary': v.change_summary,
            'created_at': v.created_at.isoformat(),
            'created_by': str(v.created_by) if v.created_by else 'System',
        } for v in versions],
        'current_version': versions[0].version_number if versions else 0,
    })


@superuser_required
@require_http_methods(["GET"])
def get_page_version(request, page_id, version_number):
    """
    Get a specific version's content.

    GET /editor-v2/api/versions/<page_id>/<version_number>/
    """
    try:
        version = PageVersion.objects.get(page_id=page_id, version_number=version_number)
    except PageVersion.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Version not found'}, status=404)

    return JsonResponse({
        'success': True,
        'version': {
            'version_number': version.version_number,
            'html_content_i18n': version.html_content_i18n or {},
            'change_summary': version.change_summary,
            'created_at': version.created_at.isoformat(),
        }
    })


@superuser_required
@require_http_methods(["POST"])
def remove_section(request):
    """
    Remove a section from a page by its data-section name.
    Creates a version snapshot before modifying.
    """
    try:
        data = json.loads(request.body)
        page_id = data.get('page_id')
        section_name = data.get('section_name')

        if not section_name:
            return JsonResponse({'success': False, 'error': 'Missing section_name'}, status=400)

        try:
            page = _get_editable_object(data)
        except Exception:
            page = None
        if not page:
            return JsonResponse({'success': False, 'error': 'Page or editable object not found'}, status=400)

        # Validate section exists in current language HTML
        current_html, resolved_lang = _get_page_html(page)
        soup = BeautifulSoup(current_html or '', 'html.parser')
        section = soup.find('section', attrs={'data-section': section_name})
        if not section:
            return JsonResponse({'success': False, 'error': f'Section "{section_name}" not found'}, status=400)

        # Create version for rollback (only if model supports it)
        if hasattr(page, 'create_version'):
            page.create_version(
                user=request.user,
                change_summary=f'Removed section "{section_name}"'
            )

        # Remove section from ALL language copies
        def remove_sect(s):
            sec = s.find('section', attrs={'data-section': section_name})
            if not sec:
                return False
            sec.decompose()
            return True

        _apply_structural_change_to_all_langs(page, remove_sect)
        page.save()

        return JsonResponse({
            'success': True,
            'message': f'Section "{section_name}" removed',
            'page_id': page.id,
        })

    except Page.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Page not found'}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@superuser_required
@require_http_methods(["POST"])
def remove_element(request):
    """
    Remove an element from a page by CSS selector.
    Creates a version snapshot before modifying.
    """
    try:
        data = json.loads(request.body)
        page_id = data.get('page_id')
        selector = data.get('selector')

        if not selector:
            return JsonResponse({'success': False, 'error': 'Missing selector'}, status=400)

        try:
            page = _get_editable_object(data)
        except Exception:
            page = None
        if not page:
            return JsonResponse({'success': False, 'error': 'Page or editable object not found'}, status=400)

        # Validate element exists in current language HTML
        current_html, resolved_lang = _get_page_html(page)
        soup = BeautifulSoup(current_html or '', 'html.parser')
        element = soup.select_one(selector)
        if not element:
            return JsonResponse({'success': False, 'error': 'Element not found for selector'}, status=400)

        # Create version for rollback (only if model supports it)
        if hasattr(page, 'create_version'):
            page.create_version(
                user=request.user,
                change_summary='Removed element'
            )

        # Remove element from ALL language copies
        def remove_el(s):
            el = s.select_one(selector)
            if not el:
                return False
            el.decompose()
            return True

        _apply_structural_change_to_all_langs(page, remove_el)
        page.save()

        return JsonResponse({
            'success': True,
            'message': 'Element removed',
            'page_id': page.id,
        })

    except Page.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Page not found'}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ---------------------------------------------------------------------------
# SSE streaming endpoints for editor AI refinement
# ---------------------------------------------------------------------------

@superuser_required
@require_http_methods(["POST"])
def refine_page_stream(request):
    """
    SSE streaming endpoint for full-page refinement in the editor.

    POST /editor-v2/api/refine-page/stream/
    Same inputs as refine_page. Returns SSE events with progress updates
    followed by the final result.
    """
    try:
        data = json.loads(request.body)
        page_id = data.get('page_id')
        instructions = data.get('instructions', '').strip()
        conversation_history = data.get('conversation_history', [])
        session_id = data.get('session_id')

        if not page_id:
            return sse_response(iter([
                sse_event({'error': 'Missing page_id'}, event='error')
            ]))
        if not instructions:
            return sse_response(iter([
                sse_event({'error': 'Missing instructions'}, event='error')
            ]))

        try:
            page = Page.objects.get(id=page_id)
        except Page.DoesNotExist:
            return sse_response(iter([
                sse_event({'error': f'Page {page_id} not found'}, event='error')
            ]))

        # Enrich instructions with cross-page context if needed
        instructions = _enrich_instructions(instructions, page)

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
                model_used=get_ai_model('refinement_page'),
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

        q = queue.Queue()
        sentinel = object()

        def on_progress(event_data):
            q.put(('progress', event_data))

        def worker():
            try:
                from djangopress.ai.services import ContentGenerationService
                service = ContentGenerationService()
                result = service.refine_page_with_html(
                    page_id=page_id,
                    instructions=instructions,
                    model_override=get_ai_model('refinement_page'),
                    conversation_history=history or None,
                    on_progress=on_progress,
                )

                assistant_msg = "I've refined the page based on your instructions."
                session.add_assistant_message(assistant_msg, ['full-page'])
                session.save()

                q.put(('complete', {
                    'success': True,
                    'page': {
                        'html_content_i18n': result.get('html_content_i18n', {}),
                    },
                    'assistant_message': assistant_msg,
                    'session_id': session.id,
                }))
            except Exception as e:
                q.put(('error', str(e)))
            finally:
                q.put(sentinel)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        def generate():
            while True:
                try:
                    item = q.get(timeout=300)
                except queue.Empty:
                    yield sse_event({'error': 'Refinement timed out'}, event='error')
                    return

                if item is sentinel:
                    return

                event_type, payload = item
                if event_type == 'progress':
                    yield sse_event(payload, event='progress')
                elif event_type == 'complete':
                    yield sse_event(payload, event='complete')
                elif event_type == 'error':
                    yield sse_event({'error': payload}, event='error')

        return sse_response(generate())

    except Exception as e:
        import traceback
        traceback.print_exc()
        return sse_response(iter([
            sse_event({'error': str(e)}, event='error')
        ]))


@superuser_required
@require_http_methods(["POST"])
def refine_multi_stream(request):
    """
    SSE streaming endpoint for section/element refinement in the editor.

    POST /editor-v2/api/refine-multi/stream/
    Same inputs as refine_multi. Returns SSE events with progress updates
    followed by the final result with options.
    """
    try:
        data = json.loads(request.body)
        page_id = data.get('page_id')
        scope = data.get('scope', 'section')
        section_name = data.get('section_name')
        selector = data.get('selector')
        instructions = data.get('instructions', '').strip()
        conversation_history = data.get('conversation_history', [])
        session_id = data.get('session_id')
        mode = data.get('mode', 'refine')
        insert_after = data.get('insert_after')
        multi_option = data.get('multi_option', True)

        if not page_id or not instructions:
            return sse_response(iter([
                sse_event({'error': 'Missing page_id or instructions'}, event='error')
            ]))

        if mode != 'create':
            if scope == 'element' and not selector:
                return sse_response(iter([
                    sse_event({'error': 'Missing selector for element scope'}, event='error')
                ]))
            if scope == 'section' and not section_name:
                return sse_response(iter([
                    sse_event({'error': 'Missing section_name for section scope'}, event='error')
                ]))

        try:
            page = Page.objects.get(pk=page_id)
        except Page.DoesNotExist:
            return sse_response(iter([
                sse_event({'error': 'Page not found'}, event='error')
            ]))

        # Load or create RefinementSession
        session = None
        if session_id:
            try:
                session = RefinementSession.objects.get(id=session_id, page=page)
            except RefinementSession.DoesNotExist:
                session = None

        if not session:
            if mode == 'create':
                prefix = '[new section]'
            elif scope == 'element':
                prefix = '[element]'
            else:
                prefix = f'[{section_name}]'
            session = RefinementSession(
                page=page,
                title=f'{prefix} {instructions[:60]}',
                model_used=get_ai_model('refinement_section'),
                created_by=request.user if request.user.is_authenticated else None,
            )
            session.save()

        session.add_user_message(instructions)

        q = queue.Queue()
        sentinel = object()

        def on_progress(event_data):
            q.put(('progress', event_data))

        def worker():
            try:
                # Route through refinement agent if enabled
                from django.conf import settings as django_settings
                use_agent = getattr(django_settings, 'USE_REFINEMENT_AGENT', True)
                result = None

                if use_agent and mode != 'create':
                    try:
                        from djangopress.ai.refinement_agent.agent import RefinementAgent
                        agent = RefinementAgent()
                        result = agent.handle(
                            instruction=instructions,
                            scope=scope,
                            target_name=section_name if scope == 'section' else selector,
                            page=page,
                            conversation_history=conversation_history,
                            multi_option=multi_option,
                            mode=mode,
                            insert_after=insert_after,
                        )
                    except Exception as e:
                        print(f"Agent error, falling back to direct pipeline: {e}")
                        import traceback
                        traceback.print_exc()
                        use_agent = False

                if result is None:
                    from djangopress.ai.services import ContentGenerationService
                    service = ContentGenerationService(model_name=get_ai_model('refinement_section'))

                    if mode == 'create':
                        result = service.generate_section(
                            page_id=page_id,
                            insert_after=insert_after,
                            instructions=instructions,
                            conversation_history=conversation_history,
                        )
                    elif scope == 'element':
                        result = service.refine_element_only(
                            page_id=page_id,
                            selector=selector,
                            instructions=instructions,
                            conversation_history=conversation_history,
                            multi_option=multi_option,
                            on_progress=on_progress,
                        )
                    else:
                        result = service.refine_section_only(
                            page_id=page_id,
                            section_name=section_name,
                            instructions=instructions,
                            conversation_history=conversation_history,
                            multi_option=multi_option,
                            on_progress=on_progress,
                        )

                assistant_msg = result.get('assistant_message', 'Here are the variations.')
                if mode == 'create':
                    target = f'new_after_{insert_after or "top"}'
                else:
                    target = 'element' if scope == 'element' else section_name
                session.add_assistant_message(assistant_msg, [target])
                session.save()

                q.put(('complete', {
                    'success': True,
                    'options': result.get('options', []),
                    'assistant_message': assistant_msg,
                    'session_id': session.id,
                }))
            except Exception as e:
                q.put(('error', str(e)))
            finally:
                q.put(sentinel)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        def generate():
            while True:
                try:
                    item = q.get(timeout=300)
                except queue.Empty:
                    yield sse_event({'error': 'Refinement timed out'}, event='error')
                    return

                if item is sentinel:
                    return

                event_type, payload = item
                if event_type == 'progress':
                    yield sse_event(payload, event='progress')
                elif event_type == 'complete':
                    yield sse_event(payload, event='complete')
                elif event_type == 'error':
                    yield sse_event({'error': payload}, event='error')

        return sse_response(generate())

    except json.JSONDecodeError:
        return sse_response(iter([
            sse_event({'error': 'Invalid JSON'}, event='error')
        ]))
    except Exception as e:
        return sse_response(iter([
            sse_event({'error': str(e)}, event='error')
        ]))
