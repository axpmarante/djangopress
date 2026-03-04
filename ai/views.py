"""
AI Content Generation Views
"""
import json
import queue
import threading
import time
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from core.decorators import superuser_required
from django.views.decorators.csrf import csrf_exempt
from core.models import Page
from .services import ContentGenerationService
from .models import log_ai_call
from .utils.sse import run_with_progress, sse_response, sse_event


def _get_model_info(tool_name):
    """Return (actual_model_name, provider_string) for a tool_name key."""
    from .utils.llm_config import MODEL_CONFIG
    config = MODEL_CONFIG.get(tool_name)
    if config:
        return config.model_name, config.provider.value
    return tool_name, 'unknown'


def _extract_usage(response):
    """Extract token usage from a StandardizedLLMResponse."""
    usage = getattr(response, 'usage', None)
    if usage is None:
        return {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}
    return {
        'prompt_tokens': getattr(usage, 'prompt_tokens', 0) or 0,
        'completion_tokens': getattr(usage, 'completion_tokens', 0) or 0,
        'total_tokens': getattr(usage, 'total_tokens', 0) or 0,
    }


@superuser_required
@require_http_methods(["POST"])
def generate_page_api(request):
    """
    API endpoint to generate a page as HTML in the default language.

    POST /ai/api/generate-page/
    Body: {
        "brief": "User description",
        "language": "pt",  # optional, default: 'pt'
        "model": "gemini-flash"  # optional, default from service
    }

    Returns: {
        "success": true,
        "page_data": {"html_content_i18n": {"pt": "..."}, "html_content": "...", "content": {...}},
        "title_i18n": {...},
        "slug_i18n": {...}
    }
    """
    try:
        # Support both multipart (with images) and JSON body
        if request.content_type and 'multipart' in request.content_type:
            brief = request.POST.get('brief')
            language = request.POST.get('language', 'pt')
            model = request.POST.get('model', 'gemini-pro')
            blueprint_page_id = request.POST.get('blueprint_page_id')
            reference_images = []
            for f in request.FILES.getlist('reference_images'):
                reference_images.append({'bytes': f.read(), 'mime_type': f.content_type})
        else:
            data = json.loads(request.body)
            brief = data.get('brief')
            language = data.get('language', 'pt')
            model = data.get('model', 'gemini-pro')
            blueprint_page_id = data.get('blueprint_page_id')
            reference_images = []

        if not brief:
            return JsonResponse({
                'success': False,
                'error': 'Brief is required'
            }, status=400)

        # Load blueprint outline if provided
        outline = None
        if blueprint_page_id:
            try:
                from core.models import BlueprintPage
                bp_page = BlueprintPage.objects.get(pk=int(blueprint_page_id))
                if bp_page.sections:
                    outline = bp_page.sections
            except (BlueprintPage.DoesNotExist, ValueError):
                pass

        # Generate page
        service = ContentGenerationService()
        page_data = service.generate_page(
            brief=brief,
            language=language,
            model_override=model,
            reference_images=reference_images or None,
            outline=outline
        )

        return JsonResponse({
            'success': True,
            'page_data': page_data,
            'title_i18n': page_data.pop('title_i18n', {}),
            'slug_i18n': page_data.pop('slug_i18n', {}),
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@superuser_required
@require_http_methods(["POST"])
def generate_page_stream(request):
    """
    SSE streaming endpoint for page generation.

    POST /ai/api/generate-page/stream/
    Same inputs as generate_page_api (multipart or JSON).
    Returns Server-Sent Events with progress updates followed by the final result.
    """
    try:
        # Support both multipart (with images) and JSON body
        if request.content_type and 'multipart' in request.content_type:
            brief = request.POST.get('brief')
            language = request.POST.get('language', 'pt')
            model = request.POST.get('model', 'gemini-pro')
            blueprint_page_id = request.POST.get('blueprint_page_id')
            reference_images = []
            for f in request.FILES.getlist('reference_images'):
                reference_images.append({'bytes': f.read(), 'mime_type': f.content_type})
        else:
            data = json.loads(request.body)
            brief = data.get('brief')
            language = data.get('language', 'pt')
            model = data.get('model', 'gemini-pro')
            blueprint_page_id = data.get('blueprint_page_id')
            reference_images = []

        if not brief:
            return sse_response(iter([
                sse_event({'error': 'Brief is required'}, event='error')
            ]))

        # Load blueprint outline if provided
        outline = None
        if blueprint_page_id:
            try:
                from core.models import BlueprintPage
                bp_page = BlueprintPage.objects.get(pk=int(blueprint_page_id))
                if bp_page.sections:
                    outline = bp_page.sections
            except (BlueprintPage.DoesNotExist, ValueError):
                pass

        service = ContentGenerationService()
        kwargs = dict(
            brief=brief,
            language=language,
            model_override=model,
            reference_images=reference_images or None,
            outline=outline,
        )
        return sse_response(run_with_progress(service.generate_page, kwargs))

    except Exception as e:
        return sse_response(iter([
            sse_event({'error': str(e)}, event='error')
        ]))


@superuser_required
@require_http_methods(["POST"])
def refine_header_api(request):
    """
    API endpoint to refine the header GlobalSection

    POST /ai/api/refine-header/
    Body: {
        "instructions": "Add a search icon to the navigation",
        "model": "gemini-pro"  # optional
    }

    Returns: {
        "success": true,
        "section": {...}  # refined GlobalSection data
    }
    """
    try:
        data = json.loads(request.body)
        instructions = data.get('instructions')
        model = data.get('model', 'gemini-pro')

        if not instructions:
            return JsonResponse({
                'success': False,
                'error': 'instructions are required'
            }, status=400)

        # Refine header using GlobalSection
        service = ContentGenerationService()
        section_data = service.refine_global_section(
            section_key='main-header',
            refinement_instructions=instructions,
            model_override=model
        )

        # Save the refined header to the database (html_template_i18n + backward compat)
        from core.models import GlobalSection
        section = GlobalSection.objects.get(key='main-header')
        section.html_template_i18n = section_data.get('html_template_i18n', section.html_template_i18n or {})
        section.html_template = section_data.get('html_template', '')
        section.content = section_data.get('content', {})
        section.save()

        return JsonResponse({
            'success': True,
            'section': section_data
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@superuser_required
@require_http_methods(["POST"])
def refine_footer_api(request):
    """
    API endpoint to refine the footer GlobalSection

    POST /ai/api/refine-footer/
    Body: {
        "instructions": "Add a newsletter subscription form",
        "model": "gemini-pro"  # optional
    }

    Returns: {
        "success": true,
        "section": {...}  # refined GlobalSection data
    }
    """
    try:
        data = json.loads(request.body)
        instructions = data.get('instructions')
        model = data.get('model', 'gemini-pro')

        if not instructions:
            return JsonResponse({
                'success': False,
                'error': 'instructions are required'
            }, status=400)

        # Refine footer using GlobalSection
        service = ContentGenerationService()
        section_data = service.refine_global_section(
            section_key='main-footer',
            refinement_instructions=instructions,
            model_override=model
        )

        # Save the refined footer to the database (html_template_i18n + backward compat)
        from core.models import GlobalSection
        section = GlobalSection.objects.get(key='main-footer')
        section.html_template_i18n = section_data.get('html_template_i18n', section.html_template_i18n or {})
        section.html_template = section_data.get('html_template', '')
        section.content = section_data.get('content', {})
        section.save()

        return JsonResponse({
            'success': True,
            'section': section_data
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@superuser_required
@require_http_methods(["POST"])
def save_generated_page_api(request):
    """
    API endpoint to save generated page to database

    POST /ai/api/save-page/
    Body: {
        "slug": "new-page" or {"pt": "nova-pagina", "en": "new-page"},
        "title": "New Page" or {"pt": "Nova Página", "en": "New Page"},
        "page_data": {
            "html_content_i18n": {"pt": "<html>..."},
            "html_content": "...",
            "content": {"translations": {...}}
        }
    }

    Returns: {
        "success": true,
        "page_id": 123,
        "created": true
    }
    """
    try:
        from core.models import SiteSettings

        data = json.loads(request.body)
        slug = data.get('slug')
        title = data.get('title')
        page_data = data.get('page_data', {})

        if not slug or not title:
            return JsonResponse({
                'success': False,
                'error': 'slug and title are required'
            }, status=400)

        # Get enabled languages from SiteSettings
        site_settings = SiteSettings.objects.first()
        languages = site_settings.get_language_codes() if site_settings else ['pt', 'en']

        # Handle title and slug - can be strings or dicts
        if isinstance(title, dict):
            title_i18n = title
        else:
            title_i18n = {lang: title for lang in languages}

        if isinstance(slug, dict):
            slug_i18n = slug
        else:
            slug_i18n = {lang: slug for lang in languages}

        # Try to find existing page by slug
        existing_page = None
        for page in Page.objects.all():
            for lang in languages:
                provided_slug = slug_i18n.get(lang)
                if provided_slug and page.get_slug(lang) == provided_slug:
                    existing_page = page
                    break
            if existing_page:
                break

        if existing_page:
            page = existing_page
            page.title_i18n = title_i18n
            page.slug_i18n = slug_i18n
            page.html_content_i18n = page_data.get('html_content_i18n', {})
            page.html_content = page_data.get('html_content', '')
            page.content = page_data.get('content', {})
            page.is_active = True
            page.save()
            created = False
        else:
            page = Page.objects.create(
                title_i18n=title_i18n,
                slug_i18n=slug_i18n,
                html_content_i18n=page_data.get('html_content_i18n', {}),
                html_content=page_data.get('html_content', ''),
                content=page_data.get('content', {}),
                is_active=True
            )
            created = True

        # Link BlueprintPage if provided
        blueprint_page_id = data.get('blueprint_page_id')
        if blueprint_page_id:
            try:
                from core.models import BlueprintPage
                bp_page = BlueprintPage.objects.get(pk=int(blueprint_page_id))
                bp_page.page = page
                bp_page.save(update_fields=['page'])
            except (BlueprintPage.DoesNotExist, ValueError, TypeError):
                pass

        # Get default language slug for response
        default_lang = site_settings.get_default_language() if site_settings else 'pt'
        return_slug = slug_i18n.get(default_lang, list(slug_i18n.values())[0] if slug_i18n else 'home')

        return JsonResponse({
            'success': True,
            'page_id': page.id,
            'page_slug': return_slug,
            'title_i18n': title_i18n,
            'slug_i18n': slug_i18n,
            'created': created
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@superuser_required
@require_http_methods(["POST"])
def analyze_bulk_pages_api(request):
    """
    API endpoint to analyze a natural language description and extract page structure

    POST /ai/api/analyze-bulk-pages/
    Body: {
        "description": "User's natural language description of website",
        "language": "pt",  # optional
        "model": "gemini-pro"  # optional
    }

    Returns: {
        "success": true,
        "pages": [...]
    }
    """
    try:
        data = json.loads(request.body)
        description = data.get('description')
        language = data.get('language', 'pt')
        model = data.get('model', 'gemini-pro')

        if not description:
            return JsonResponse({
                'success': False,
                'error': 'Description is required'
            }, status=400)

        from .utils.llm_config import LLMBase
        from .utils.prompts import PromptTemplates

        print(f"\n=== Analyzing Bulk Pages Description ===")
        print(f"Description length: {len(description)} characters")
        print(f"Language: {language}")
        print(f"Model: {model}")

        # Get enabled languages from SiteSettings
        from core.models import SiteSettings
        site_settings = SiteSettings.objects.first()
        site_name = site_settings.get_site_name(language) if site_settings else 'Website'
        site_description = site_settings.get_site_description(language) if site_settings else ''
        project_briefing = site_settings.get_project_briefing() if site_settings else ''
        enabled_languages = site_settings.get_language_codes() if site_settings else ['pt', 'en']

        # Create LLM instance
        llm = LLMBase()

        # Build prompt
        user_prompt = PromptTemplates.get_bulk_page_analysis_prompt(
            site_name=site_name,
            site_description=site_description,
            project_briefing=project_briefing,
            languages=enabled_languages,
            description=description
        )

        messages = [
            {'role': 'user', 'content': user_prompt}
        ]

        # Get LLM completion
        actual_model, provider = _get_model_info(model)
        t0 = time.time()
        try:
            response = llm.get_completion(messages, tool_name=model)
            usage = _extract_usage(response)
            log_ai_call(
                action='analyze_bulk', model_name=actual_model, provider=provider,
                user_prompt=user_prompt,
                response_text=response.choices[0].message.content,
                duration_ms=int((time.time() - t0) * 1000),
                user=request.user, **usage,
            )
        except Exception as e:
            log_ai_call(
                action='analyze_bulk', model_name=actual_model, provider=provider,
                user_prompt=user_prompt,
                duration_ms=int((time.time() - t0) * 1000),
                success=False, error_message=str(e), user=request.user,
            )
            raise

        # Extract and parse response
        content = response.choices[0].message.content

        # Parse JSON from response
        import re
        json_match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', content, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_match = re.search(r'(\[.*\])', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = content

        try:
            pages = json.loads(json_str)
        except json.JSONDecodeError as e:
            return JsonResponse({
                'success': False,
                'error': f'Failed to parse LLM response: {e}'
            }, status=500)

        if not isinstance(pages, list):
            return JsonResponse({
                'success': False,
                'error': 'LLM did not return a list of pages'
            }, status=500)

        # Validate each page
        for i, page in enumerate(pages):
            has_i18n_fields = 'title_i18n' in page and 'slug_i18n' in page
            has_old_fields = 'title' in page and 'slug' in page

            if not has_i18n_fields and not has_old_fields:
                return JsonResponse({
                    'success': False,
                    'error': f'Page at index {i} is missing required fields'
                }, status=500)

            if 'description' not in page:
                return JsonResponse({
                    'success': False,
                    'error': f'Page at index {i} is missing description field'
                }, status=500)

            # Convert old format to new format
            if not has_i18n_fields and has_old_fields:
                page['title_i18n'] = {lang: page['title'] for lang in enabled_languages}
                page['slug_i18n'] = {lang: page['slug'] for lang in enabled_languages}

        print(f"✓ Successfully analyzed description and extracted {len(pages)} pages")

        return JsonResponse({
            'success': True,
            'pages': pages
        })

    except Exception as e:
        print(f"Error in analyze_bulk_pages_api: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@superuser_required
@require_http_methods(["POST"])
def refine_page_with_html_api(request):
    """
    API endpoint to refine a page's HTML content using AI

    POST /ai/api/refine-page-with-html/
    Body: {
        "page_id": 123,
        "instructions": "Make more engaging...",
        "section_name": "hero",  # Optional: target a specific data-section
        "language": "pt",  # optional
        "model": "gemini-pro"  # optional
    }

    Returns: {
        "success": true,
        "page_id": 123,
        "message": "Page updated"
    }
    """
    try:
        from core.models import Page
        from .services import ContentGenerationService

        # Support both multipart (with images) and JSON body
        if request.content_type and 'multipart' in request.content_type:
            page_id = request.POST.get('page_id')
            if page_id:
                page_id = int(page_id)
            instructions = request.POST.get('instructions')
            section_name = request.POST.get('section_name')
            language = request.POST.get('language', 'pt')
            model = request.POST.get('model', 'gemini-pro')
            reference_images = []
            for f in request.FILES.getlist('reference_images'):
                reference_images.append({'bytes': f.read(), 'mime_type': f.content_type})
        else:
            data = json.loads(request.body)
            page_id = data.get('page_id')
            instructions = data.get('instructions')
            section_name = data.get('section_name')
            language = data.get('language', 'pt')
            model = data.get('model', 'gemini-pro')
            reference_images = []

        if not page_id or not instructions:
            return JsonResponse({
                'success': False,
                'error': 'page_id and instructions are required'
            }, status=400)

        # Get the page
        try:
            page = Page.objects.get(id=page_id)
        except Page.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'Page with id {page_id} not found'
            }, status=400)

        # Create a page version before making changes
        page.create_version(
            user=request.user,
            change_summary=f'Before AI edit: {instructions[:100]}'
        )

        # Call AI service to refine the page
        service = ContentGenerationService()
        refined_data = service.refine_page_with_html(
            page_id=page_id,
            instructions=instructions,
            section_name=section_name,
            language=language,
            model_override=model,
            reference_images=reference_images or None
        )

        # Save refined content to page (html_content_i18n + backward compat)
        page.html_content_i18n = refined_data.get('html_content_i18n', page.html_content_i18n or {})
        page.html_content = refined_data.get('html_content', page.html_content)
        page.content = refined_data.get('content', page.content)
        page.save()

        return JsonResponse({
            'success': True,
            'page_id': page.id,
            'message': 'Page updated with AI refinements'
        })

    except Exception as e:
        print(f"Error in refine_page_with_html_api: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@superuser_required
@require_http_methods(["POST"])
def chat_refine_page_api(request):
    """
    Chat-based page refinement endpoint.

    POST /ai/api/chat-refine-page/
    Accepts JSON or multipart (when reference images are included).
    Fields: page_id, message, session_id (optional), model, reference_images
    """
    try:
        from .models import RefinementSession
        from .utils.diff_utils import compute_section_changes, build_change_summary

        # Parse input — dual-mode (same pattern as refine_page_with_html_api)
        if request.content_type and 'multipart' in request.content_type:
            page_id = request.POST.get('page_id')
            if page_id:
                page_id = int(page_id)
            message = request.POST.get('message')
            session_id = request.POST.get('session_id')
            if session_id:
                session_id = int(session_id)
            model = request.POST.get('model', 'gemini-pro')
            handle_images = request.POST.get('handle_images') in ('true', '1', 'on')
            reference_images = []
            for f in request.FILES.getlist('reference_images'):
                reference_images.append({'bytes': f.read(), 'mime_type': f.content_type})
        else:
            data = json.loads(request.body)
            page_id = data.get('page_id')
            message = data.get('message')
            session_id = data.get('session_id')
            model = data.get('model', 'gemini-pro')
            handle_images = bool(data.get('handle_images', False))
            reference_images = []

        if not page_id or not message:
            return JsonResponse({
                'success': False,
                'error': 'page_id and message are required'
            }, status=400)

        # Load the page
        try:
            page = Page.objects.get(id=page_id)
        except Page.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'Page with id {page_id} not found'
            }, status=400)

        # Load or create session
        if session_id:
            try:
                session = RefinementSession.objects.get(id=session_id, page=page)
            except RefinementSession.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': f'Session {session_id} not found'
                }, status=400)
        else:
            session = RefinementSession(
                page=page,
                title=message[:80],
                model_used=model,
                created_by=request.user if request.user.is_authenticated else None,
            )
            session.save()

        # Capture old HTML for diff (from html_content_i18n with fallback)
        from django.utils.translation import get_language
        from core.models import SiteSettings
        site_settings = SiteSettings.objects.first()
        default_lang = site_settings.get_default_language() if site_settings else 'pt'
        current_lang = get_language() or default_lang
        html_i18n = page.html_content_i18n or {}
        old_html = html_i18n.get(current_lang) or html_i18n.get(default_lang) or page.html_content or ''

        # Append user message to session
        session.add_user_message(message, reference_images_count=len(reference_images))

        # Build history from previous completed turns (excludes current message)
        history = session.get_history_for_prompt()

        # Create version snapshot
        page.create_version(
            user=request.user,
            change_summary=f'Before chat refine: {message[:100]}'
        )

        # Call AI service
        service = ContentGenerationService()
        refined_data = service.refine_page_with_html(
            page_id=page_id,
            instructions=message,
            model_override=model,
            reference_images=reference_images or None,
            conversation_history=history or None,
            handle_images=handle_images,
        )

        # Save refined content to page (html_content_i18n + backward compat)
        page.html_content_i18n = refined_data.get('html_content_i18n', page.html_content_i18n or {})
        page.html_content = refined_data.get('html_content', page.html_content)
        page.content = refined_data.get('content', page.content)
        page.save()

        # Compute section changes
        new_html = refined_data.get('html_content', page.html_content) or ''
        added, removed, modified = compute_section_changes(old_html, new_html)
        change_summary = build_change_summary(added, removed, modified)
        sections_changed = added + modified

        # Append assistant message and save session
        session.add_assistant_message(change_summary, sections_changed)
        session.save()

        return JsonResponse({
            'success': True,
            'session_id': session.id,
            'assistant_message': change_summary,
            'sections_changed': sections_changed,
            'page_id': page.id,
        })

    except Exception as e:
        print(f"Error in chat_refine_page_api: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@superuser_required
@require_http_methods(["GET"])
def get_refinement_session_api(request, session_id):
    """Return full session with messages."""
    from .models import RefinementSession

    try:
        session = RefinementSession.objects.get(id=session_id)
    except RefinementSession.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Session not found'}, status=400)

    return JsonResponse({
        'success': True,
        'session': {
            'id': session.id,
            'title': session.title,
            'page_id': session.page_id,
            'model_used': session.model_used,
            'messages': session.messages,
            'created_at': session.created_at.isoformat(),
            'updated_at': session.updated_at.isoformat(),
        }
    })


@superuser_required
@require_http_methods(["GET"])
def list_refinement_sessions_api(request, page_id):
    """Return list of sessions for a given page."""
    from .models import RefinementSession

    sessions = RefinementSession.objects.filter(page_id=page_id)[:20]
    data = []
    for s in sessions:
        data.append({
            'id': s.id,
            'title': s.title,
            'message_count': len(s.messages),
            'updated_at': s.updated_at.isoformat(),
        })

    return JsonResponse({'success': True, 'sessions': data})


@superuser_required
@require_http_methods(["POST"])
def chat_refine_page_stream(request):
    """
    SSE streaming endpoint for chat-based page refinement.

    POST /ai/api/chat-refine-page/stream/
    Same inputs as chat_refine_page_api (multipart or JSON).
    Returns Server-Sent Events with progress updates followed by the final result
    including session_id, assistant_message, sections_changed, html_content, content.
    """
    try:
        from .models import RefinementSession
        from .utils.diff_utils import compute_section_changes, build_change_summary

        # Parse input -- dual-mode (same pattern as chat_refine_page_api)
        if request.content_type and 'multipart' in request.content_type:
            page_id = request.POST.get('page_id')
            if page_id:
                page_id = int(page_id)
            message = request.POST.get('message')
            session_id = request.POST.get('session_id')
            if session_id:
                session_id = int(session_id)
            model = request.POST.get('model', 'gemini-pro')
            handle_images = request.POST.get('handle_images') in ('true', '1', 'on')
            reference_images = []
            for f in request.FILES.getlist('reference_images'):
                reference_images.append({'bytes': f.read(), 'mime_type': f.content_type})
        else:
            data = json.loads(request.body)
            page_id = data.get('page_id')
            message = data.get('message')
            session_id = data.get('session_id')
            model = data.get('model', 'gemini-pro')
            handle_images = bool(data.get('handle_images', False))
            reference_images = []

        if not page_id or not message:
            return sse_response(iter([
                sse_event({'error': 'page_id and message are required'}, event='error')
            ]))

        # Load the page
        try:
            page = Page.objects.get(id=page_id)
        except Page.DoesNotExist:
            return sse_response(iter([
                sse_event({'error': f'Page with id {page_id} not found'}, event='error')
            ]))

        # Load or create session
        if session_id:
            try:
                session = RefinementSession.objects.get(id=session_id, page=page)
            except RefinementSession.DoesNotExist:
                return sse_response(iter([
                    sse_event({'error': f'Session {session_id} not found'}, event='error')
                ]))
        else:
            session = RefinementSession(
                page=page,
                title=message[:80],
                model_used=model,
                created_by=request.user if request.user.is_authenticated else None,
            )
            session.save()

        # Capture old HTML for diff (from html_content_i18n with fallback)
        from django.utils.translation import get_language
        from core.models import SiteSettings
        site_settings = SiteSettings.objects.first()
        default_lang = site_settings.get_default_language() if site_settings else 'pt'
        current_lang = get_language() or default_lang
        html_i18n = page.html_content_i18n or {}
        old_html = html_i18n.get(current_lang) or html_i18n.get(default_lang) or page.html_content or ''

        # Append user message to session
        session.add_user_message(message, reference_images_count=len(reference_images))

        # Build history from previous completed turns (excludes current message)
        history = session.get_history_for_prompt()

        # Create version snapshot
        page.create_version(
            user=request.user,
            change_summary=f'Before chat refine: {message[:100]}'
        )

        # Custom worker thread with post-processing
        q = queue.Queue()
        sentinel = object()

        def on_progress(event_data):
            q.put(('progress', event_data))

        def worker():
            try:
                service = ContentGenerationService()
                refined_data = service.refine_page_with_html(
                    page_id=page_id,
                    instructions=message,
                    model_override=model,
                    reference_images=reference_images or None,
                    conversation_history=history or None,
                    handle_images=handle_images,
                    on_progress=on_progress,
                )

                # Post-processing: save page (html_content_i18n + backward compat)
                page.html_content_i18n = refined_data.get('html_content_i18n', page.html_content_i18n or {})
                page.html_content = refined_data.get('html_content', page.html_content)
                page.content = refined_data.get('content', page.content)
                page.save()

                # Compute section changes
                new_html = refined_data.get('html_content', page.html_content) or ''
                added, removed, modified = compute_section_changes(old_html, new_html)
                change_summary = build_change_summary(added, removed, modified)
                sections_changed = added + modified

                # Append assistant message and save session
                session.add_assistant_message(change_summary, sections_changed)
                session.save()

                q.put(('complete', {
                    'success': True,
                    'session_id': session.id,
                    'assistant_message': change_summary,
                    'sections_changed': sections_changed,
                    'html_content': page.html_content,
                    'content': page.content,
                    'page_id': page.id,
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
        return sse_response(iter([
            sse_event({'error': str(e)}, event='error')
        ]))


@superuser_required
@require_http_methods(["POST"])
def refine_header_stream(request):
    """
    SSE streaming endpoint for header refinement.

    POST /ai/api/refine-header/stream/
    Body: { "instructions": "...", "model": "gemini-pro" }
    Returns Server-Sent Events with progress updates followed by the final result.
    """
    try:
        data = json.loads(request.body)
        instructions = data.get('instructions')
        model = data.get('model', 'gemini-pro')

        if not instructions:
            return sse_response(iter([
                sse_event({'error': 'instructions are required'}, event='error')
            ]))

        # Custom worker thread with post-processing (save to GlobalSection)
        q = queue.Queue()
        sentinel = object()

        def on_progress(event_data):
            q.put(('progress', event_data))

        def worker():
            try:
                service = ContentGenerationService()
                section_data = service.refine_global_section(
                    section_key='main-header',
                    refinement_instructions=instructions,
                    model_override=model,
                    on_progress=on_progress,
                )

                # Save the refined header to the database (html_template_i18n + backward compat)
                from core.models import GlobalSection
                section = GlobalSection.objects.get(key='main-header')
                section.html_template_i18n = section_data.get('html_template_i18n', section.html_template_i18n or {})
                section.html_template = section_data.get('html_template', '')
                section.content = section_data.get('content', {})
                section.save()

                q.put(('complete', {
                    'success': True,
                    'section': section_data,
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
                    yield sse_event({'error': 'Header refinement timed out'}, event='error')
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
        return sse_response(iter([
            sse_event({'error': str(e)}, event='error')
        ]))


@superuser_required
@require_http_methods(["POST"])
def refine_footer_stream(request):
    """
    SSE streaming endpoint for footer refinement.

    POST /ai/api/refine-footer/stream/
    Body: { "instructions": "...", "model": "gemini-pro" }
    Returns Server-Sent Events with progress updates followed by the final result.
    """
    try:
        data = json.loads(request.body)
        instructions = data.get('instructions')
        model = data.get('model', 'gemini-pro')

        if not instructions:
            return sse_response(iter([
                sse_event({'error': 'instructions are required'}, event='error')
            ]))

        # Custom worker thread with post-processing (save to GlobalSection)
        q = queue.Queue()
        sentinel = object()

        def on_progress(event_data):
            q.put(('progress', event_data))

        def worker():
            try:
                service = ContentGenerationService()
                section_data = service.refine_global_section(
                    section_key='main-footer',
                    refinement_instructions=instructions,
                    model_override=model,
                    on_progress=on_progress,
                )

                # Save the refined footer to the database (html_template_i18n + backward compat)
                from core.models import GlobalSection
                section = GlobalSection.objects.get(key='main-footer')
                section.html_template_i18n = section_data.get('html_template_i18n', section.html_template_i18n or {})
                section.html_template = section_data.get('html_template', '')
                section.content = section_data.get('content', {})
                section.save()

                q.put(('complete', {
                    'success': True,
                    'section': section_data,
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
                    yield sse_event({'error': 'Footer refinement timed out'}, event='error')
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
        return sse_response(iter([
            sse_event({'error': str(e)}, event='error')
        ]))


@superuser_required
@require_http_methods(["POST"])
def generate_design_guide_ai_api(request):
    """
    Generate or update a design guide using AI.

    Accepts multipart (when reference images are included) or JSON.
    Fields:
        - page_ids: list of page IDs whose HTML to analyze for patterns
        - reference_images: uploaded design reference images
        - model: LLM model to use
        - existing_guide: current design_guide text (for update mode)

    Returns: { "success": true, "design_guide": "..." }
    """
    try:
        from core.models import SiteSettings, Page
        from .utils.llm_config import LLMBase, MODEL_CONFIG, ModelProvider

        # Parse input
        if request.content_type and 'multipart' in request.content_type:
            page_ids_raw = request.POST.getlist('page_ids')
            page_ids = [int(pid) for pid in page_ids_raw if pid]
            model = request.POST.get('model', 'gemini-pro')
            existing_guide = request.POST.get('existing_guide', '')
            style_instructions = request.POST.get('style_instructions', '')
            reference_images = []
            for f in request.FILES.getlist('reference_images'):
                reference_images.append({'bytes': f.read(), 'mime_type': f.content_type})
        else:
            data = json.loads(request.body)
            page_ids = data.get('page_ids', [])
            model = data.get('model', 'gemini-pro')
            existing_guide = data.get('existing_guide', '')
            style_instructions = data.get('style_instructions', '')
            reference_images = []

        # Load site settings
        site_settings = SiteSettings.objects.first()
        if not site_settings:
            return JsonResponse({
                'success': False,
                'error': 'Site settings not found'
            }, status=400)

        default_language = site_settings.get_default_language()
        site_name = site_settings.get_site_name(default_language)
        project_briefing = site_settings.get_project_briefing()

        # Build current settings summary
        settings_summary = f"""## Current Design System Values

### Colors
- Primary: `{site_settings.primary_color}` (hover: `{site_settings.primary_color_hover}`)
- Secondary: `{site_settings.secondary_color}`
- Accent: `{site_settings.accent_color}`
- Background: `{site_settings.background_color}`
- Text: `{site_settings.text_color}`
- Headings: `{site_settings.heading_color}`

### Typography
- Body font: {site_settings.body_font}
- Heading font: {site_settings.heading_font}
- H1: {site_settings.h1_font} / {site_settings.h1_size}
- H2: {site_settings.h2_font} / {site_settings.h2_size}
- H3: {site_settings.h3_font} / {site_settings.h3_size}
- H4: {site_settings.h4_font} / {site_settings.h4_size}

### Layout
- Container width: max-w-{site_settings.container_width}
- Border radius: rounded-{site_settings.border_radius_preset}
- Spacing scale: {site_settings.spacing_scale}
- Shadow preset: shadow-{site_settings.shadow_preset}

### Buttons
- Style: {site_settings.button_style}, Size: {site_settings.button_size}
- Primary: bg `{site_settings.primary_button_bg}`, text `{site_settings.primary_button_text}`, hover `{site_settings.primary_button_hover}`
- Secondary: bg `{site_settings.secondary_button_bg}`, text `{site_settings.secondary_button_text}`, hover `{site_settings.secondary_button_hover}`
- Border width: {site_settings.button_border_width}px"""

        # Collect page HTML samples (from html_content_i18n with fallback)
        page_samples = ""
        if page_ids:
            pages = Page.objects.filter(id__in=page_ids, is_active=True)
            for page in pages:
                title = page.default_title or page.default_slug
                page_html_i18n = page.html_content_i18n or {}
                html = page_html_i18n.get(default_language) or page.html_content or ''
                if not html:
                    continue
                # Truncate very long pages to keep prompt reasonable
                if len(html) > 8000:
                    html = html[:8000] + "\n<!-- ... truncated ... -->"
                page_samples += f"\n### Page: {title}\n```html\n{html}\n```\n"

        # Build the prompt
        system_prompt = """You are a senior UI/UX designer and design systems expert. Your job is to analyze a website's design settings, existing pages, optional reference images, and the user's style instructions to produce:

1. A comprehensive **design guide** in Markdown
2. **Suggested design system changes** to match the desired look and feel

The design guide will be injected into AI prompts that generate and refine web pages using Tailwind CSS. It must be practical, specific, and focused on producing consistent UI.

## Design Guide — What to Include

1. **Color Usage** — When to use each color (primary for CTAs, secondary for borders, accent for highlights, etc.). Include specific Tailwind style attributes using the hex values with arbitrary value syntax, e.g. `bg-[#1e3a8a]`, `text-[#f59e0b]`.

2. **Typography Rules** — How to use each heading level, font pairing rules, text sizing hierarchy.

3. **Component Patterns** — Describe how to build common components:
   - Cards (padding, shadow, border radius, image treatment)
   - Buttons (primary vs secondary, sizing, hover states)
   - Hero sections (layout, overlay patterns, CTA placement)
   - Content sections (alternating backgrounds, grid patterns)
   - Lists and grids (columns at different breakpoints)
   - Forms (input styling, labels, validation)

4. **Layout Conventions** — Section padding, container width, spacing between elements, responsive breakpoints.

5. **Visual Rules** — Image treatment, icon style, divider patterns, background patterns.

6. **Do's and Don'ts** — Specific things to avoid and things to always do.

## Design System Updates

If the user provided style instructions or reference images that suggest changes to the current design system values, include a `design_updates` object with ONLY the fields that should change. Available fields and their formats:

**Colors** (hex codes like "#1e3a8a"):
primary_color, primary_color_hover, secondary_color, accent_color, background_color, text_color, heading_color, primary_button_bg, primary_button_text, primary_button_border, primary_button_hover, secondary_button_bg, secondary_button_text, secondary_button_border, secondary_button_hover

**Fonts** (Google Fonts names like "Inter", "Playfair Display", "Montserrat"):
heading_font, body_font

**Layout** (preset values):
container_width: full|xs|sm|md|lg|xl|2xl|3xl|4xl|5xl|6xl|7xl
border_radius_preset: none|sm|md|lg|xl|2xl|3xl|full
spacing_scale: tight|normal|relaxed|loose
shadow_preset: none|sm|md|lg|xl|2xl
button_style: rounded|square|pill
button_size: small|medium|large

Only include fields that should CHANGE from their current values. If the current design system already matches the desired style, return an empty object.

## Response Format

Return a JSON object:
```json
{
  "design_guide": "# Design Guide\\n\\n...",
  "design_updates": {
    "primary_color": "#1e3a8a",
    "heading_font": "Playfair Display"
  }
}
```

Return ONLY the JSON. No markdown code blocks wrapping it, no explanations.
Keep the design guide practical — every rule should map to specific Tailwind classes or patterns. Aim for 80-150 lines of concise, actionable markdown.
The design_guide value must have newlines as \\n within the JSON string."""

        user_parts = [f"# Site: {site_name}\n"]

        if project_briefing:
            user_parts.append(f"## Project Briefing\n{project_briefing}\n")

        user_parts.append(settings_summary)

        if page_samples:
            user_parts.append(f"\n## Existing Pages (analyze these for patterns)\n{page_samples}")

        if style_instructions:
            user_parts.append(f"\n## Style Instructions (from the user — this is the most important input)\n{style_instructions}")

        if existing_guide:
            user_parts.append(f"\n## Current Design Guide (update and improve this)\n{existing_guide}")
        else:
            user_parts.append("\n## Task\nGenerate a new design guide from scratch based on the settings, pages, style instructions, and reference images above.")

        if reference_images:
            user_parts.append(f"\n## Reference Images\n{len(reference_images)} design reference image(s) are attached. Analyze their visual style, layout patterns, color usage, typography, and component design. Incorporate these patterns into the design guide.")

        user_prompt = "\n".join(user_parts)

        # Call LLM
        llm = LLMBase()
        actual_model, provider = _get_model_info(model)
        t0 = time.time()

        try:
            if reference_images:
                # Vision call with images
                combined_prompt = system_prompt + "\n\n" + user_prompt
                response = llm.get_vision_completion(
                    prompt=combined_prompt,
                    images=reference_images,
                    tool_name=model
                )
            else:
                messages = [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt}
                ]
                response = llm.get_completion(messages, tool_name=model)

            usage = _extract_usage(response)
            log_ai_call(
                action='generate_design_guide', model_name=actual_model, provider=provider,
                system_prompt=system_prompt, user_prompt=user_prompt,
                response_text=response.choices[0].message.content,
                duration_ms=int((time.time() - t0) * 1000),
                user=request.user, **usage,
            )
        except Exception as e:
            log_ai_call(
                action='generate_design_guide', model_name=actual_model, provider=provider,
                system_prompt=system_prompt, user_prompt=user_prompt,
                duration_ms=int((time.time() - t0) * 1000),
                success=False, error_message=str(e), user=request.user,
            )
            raise

        raw_content = response.choices[0].message.content

        # Try to parse as JSON (new format with design_updates)
        design_guide = ''
        design_updates = {}

        # Strip markdown code block wrapping if present
        content = raw_content.strip()
        if content.startswith('```'):
            lines = content.split('\n')
            if lines[0].startswith('```'):
                lines = lines[1:]
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            content = '\n'.join(lines)

        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict) and 'design_guide' in parsed:
                design_guide = parsed['design_guide']
                design_updates = parsed.get('design_updates', {})
                if not isinstance(design_updates, dict):
                    design_updates = {}
            else:
                # JSON but not the expected format — treat as plain text
                design_guide = content
        except (json.JSONDecodeError, ValueError):
            # Not JSON — treat entire response as the design guide (backward compatible)
            design_guide = content

        # Validate design_updates: only allow known fields
        ALLOWED_UPDATE_FIELDS = {
            'primary_color', 'primary_color_hover', 'secondary_color', 'accent_color',
            'background_color', 'text_color', 'heading_color',
            'heading_font', 'body_font',
            'container_width', 'border_radius_preset', 'spacing_scale', 'shadow_preset',
            'button_style', 'button_size',
            'primary_button_bg', 'primary_button_text', 'primary_button_border', 'primary_button_hover',
            'secondary_button_bg', 'secondary_button_text', 'secondary_button_border', 'secondary_button_hover',
            'button_border_width',
        }
        design_updates = {k: v for k, v in design_updates.items() if k in ALLOWED_UPDATE_FIELDS}

        # Filter out updates that match current values (no change needed)
        if design_updates:
            filtered = {}
            for field, value in design_updates.items():
                current = getattr(site_settings, field, None)
                if current is not None and str(current) != str(value):
                    filtered[field] = value
            design_updates = filtered

        return JsonResponse({
            'success': True,
            'design_guide': design_guide.strip(),
            'design_updates': design_updates,
        })

    except Exception as e:
        print(f"Error in generate_design_guide_ai_api: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@superuser_required
@require_http_methods(["POST"])
def analyze_page_images_api(request):
    """
    Analyze page images and suggest generation prompts + library matches.

    POST /ai/api/analyze-page-images/
    Body: {
        "page_id": 123,
        "images": [{"index": 0, "src": "...", "alt": "...", "name": "..."}],
        "model": "gemini-pro"
    }

    Returns: {
        "success": true,
        "suggestions": [{"index": 0, "prompt": "...", "aspect_ratio": "16:9", "library_matches": [42, 17]}]
    }
    """
    try:
        data = json.loads(request.body)
        page_id = data.get('page_id')
        images = data.get('images', [])
        model = data.get('model', 'gemini-pro')

        if not page_id or not images:
            return JsonResponse({
                'success': False,
                'error': 'page_id and images are required'
            }, status=400)

        service = ContentGenerationService()
        suggestions = service.analyze_page_images(
            page_id=page_id,
            images=images,
            model_override=model,
        )

        return JsonResponse({
            'success': True,
            'suggestions': suggestions,
        })

    except Exception as e:
        print(f"Error in analyze_page_images_api: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@superuser_required
@require_http_methods(["POST"])
def process_page_images_api(request):
    """
    Process image placeholders on a page.

    POST /ai/api/process-page-images/
    Body: {
        "page_id": 123,
        "images": [
            {"image_name": "hero-banner", "action": "library", "library_image_id": 5},
            {"image_name": "team-photo", "action": "generate", "prompt": "...", "aspect_ratio": "16:9"}
        ]
    }

    Returns: {
        "success": true,
        "processed": [...],
        "failed": [...],
        "report": "Processed 2 image(s), 0 failed"
    }
    """
    try:
        data = json.loads(request.body)
        page_id = data.get('page_id')
        images = data.get('images', [])

        if not page_id or not images:
            return JsonResponse({
                'success': False,
                'error': 'page_id and images are required'
            }, status=400)

        # Create version before processing
        try:
            page = Page.objects.get(id=page_id)
        except Page.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'Page with id {page_id} not found'
            }, status=400)

        page.create_version(
            user=request.user,
            change_summary=f'Before image processing: {len(images)} image(s)'
        )

        service = ContentGenerationService()
        result = service.process_page_images(
            page_id=page_id,
            image_decisions=images,
        )

        return JsonResponse({
            'success': True,
            'processed': result['processed'],
            'failed': result['failed'],
            'report': result['report'],
        })

    except Exception as e:
        print(f"Error in process_page_images_api: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@superuser_required
@require_http_methods(["POST"])
def translate_to_language_api(request):
    """
    Bulk-translate all pages and GlobalSections to a new language.

    POST /ai/api/translate-to-language/
    Body: {
        "target_language": "es",
        "source_language": "pt"  // optional, defaults to site default
    }

    Returns: {
        "success": true,
        "translated_pages": 12,
        "translated_sections": 2,
        "errors": []
    }
    """
    try:
        data = json.loads(request.body)
        target_language = data.get('target_language')
        source_language = data.get('source_language')

        if not target_language:
            return JsonResponse({
                'success': False,
                'error': 'target_language is required'
            }, status=400)

        service = ContentGenerationService()
        result = service.translate_content_to_language(
            target_lang=target_language,
            source_lang=source_language,
        )

        return JsonResponse({
            'success': True,
            'translated_pages': result['translated_pages'],
            'translated_sections': result['translated_sections'],
            'errors': result['errors'],
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@superuser_required
@require_http_methods(["POST"])
def bulk_translate_api(request):
    """
    Bulk-translate selected pages and/or GlobalSections to target languages
    using per-language HTML (html_content_i18n / html_template_i18n).

    POST /ai/api/bulk-translate/
    Body: {
        "page_ids": [1, 2, 3],
        "section_ids": [1],
        "target_languages": ["en", "es"],
        "model": "gemini-flash"
    }

    Returns: {
        "success": true,
        "results": {
            "pages": [{"id": 1, "title": "...", "languages": {"en": "ok", "es": "ok"}}],
            "sections": [{"id": 1, "key": "...", "languages": {"en": "ok"}}]
        },
        "errors": []
    }
    """
    try:
        from core.models import Page, GlobalSection, SiteSettings
        from django.utils.text import slugify

        data = json.loads(request.body)
        page_ids = data.get('page_ids', [])
        section_ids = data.get('section_ids', [])
        target_languages = data.get('target_languages', [])
        model = data.get('model', 'gemini-flash')

        if not target_languages:
            return JsonResponse({
                'success': False,
                'error': 'target_languages is required'
            }, status=400)

        if not page_ids and not section_ids:
            return JsonResponse({
                'success': False,
                'error': 'At least one page_id or section_id is required'
            }, status=400)

        site_settings = SiteSettings.objects.first()
        default_lang = site_settings.get_default_language() if site_settings else 'pt'

        service = ContentGenerationService()

        page_results = []
        section_results = []
        errors = []

        # Translate pages
        for page_id in page_ids:
            try:
                page = Page.objects.get(pk=page_id)
                lang_results = {}

                translated = service.bulk_translate_page(
                    page, target_languages, model=model
                )

                # Save translated HTML to html_content_i18n
                if not page.html_content_i18n:
                    page.html_content_i18n = {}

                for lang, html in translated.items():
                    page.html_content_i18n[lang] = html
                    lang_results[lang] = 'ok'

                # Also translate title_i18n and slug_i18n if missing
                source_title = (page.title_i18n or {}).get(default_lang, '')
                if source_title:
                    for lang in target_languages:
                        if lang == default_lang:
                            continue
                        if not (page.title_i18n or {}).get(lang):
                            title_result = service._translate_key_value_pairs(
                                {'title': source_title},
                                default_lang, lang
                            )
                            if title_result and 'title' in title_result:
                                if not page.title_i18n:
                                    page.title_i18n = {}
                                page.title_i18n[lang] = title_result['title']

                        if not (page.slug_i18n or {}).get(lang):
                            if not page.slug_i18n:
                                page.slug_i18n = {}
                            source_slug = (page.slug_i18n or {}).get(default_lang, '')
                            if source_slug == 'home':
                                page.slug_i18n[lang] = 'home'
                            elif page.title_i18n.get(lang):
                                page.slug_i18n[lang] = slugify(page.title_i18n[lang])
                            elif source_slug:
                                page.slug_i18n[lang] = source_slug

                page.save()
                page_results.append({
                    'id': page.id,
                    'title': page.get_title(default_lang),
                    'languages': lang_results,
                })

            except Exception as e:
                errors.append(f'Page {page_id}: {str(e)}')

        # Translate GlobalSections
        for section_id in section_ids:
            try:
                section = GlobalSection.objects.get(pk=section_id)
                lang_results = {}

                translated = service.bulk_translate_section(
                    section, target_languages, model=model
                )

                if not section.html_template_i18n:
                    section.html_template_i18n = {}

                for lang, html in translated.items():
                    section.html_template_i18n[lang] = html
                    lang_results[lang] = 'ok'

                section.save()
                section_results.append({
                    'id': section.id,
                    'key': section.key,
                    'name': section.name or section.key,
                    'languages': lang_results,
                })

            except Exception as e:
                errors.append(f'Section {section_id}: {str(e)}')

        return JsonResponse({
            'success': True,
            'results': {
                'pages': page_results,
                'sections': section_results,
            },
            'errors': errors,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# === Blueprint AI Endpoints ===

@superuser_required
@require_http_methods(["POST"])
def suggest_page_sections_api(request):
    """
    Suggest sections for a blueprint page using AI.

    POST /ai/api/suggest-page-sections/
    Body: {"blueprint_page_id": 3, "model": "gemini-pro"}

    Returns: {"success": true, "sections": [...]}
    """
    try:
        from core.models import SiteSettings, BlueprintPage
        from .utils.llm_config import LLMBase
        from .utils.prompts import PromptTemplates

        data = json.loads(request.body)
        bp_page_id = data.get('blueprint_page_id')
        model = data.get('model', 'gemini-pro')

        if not bp_page_id:
            return JsonResponse({'success': False, 'error': 'blueprint_page_id is required'}, status=400)

        bp_page = BlueprintPage.objects.get(pk=bp_page_id)
        blueprint = bp_page.blueprint

        # Load site context
        site_settings = SiteSettings.objects.first()
        site_name = site_settings.get_site_name() if site_settings else 'Website'
        project_briefing = site_settings.get_project_briefing() if site_settings else ''

        # All pages info for context
        all_pages_info = [
            {'title': p.title, 'slug': p.slug}
            for p in blueprint.blueprint_pages.exclude(pk=bp_page_id)
        ]

        system_prompt, user_prompt = PromptTemplates.get_suggest_sections_prompt(
            site_name=site_name,
            project_briefing=project_briefing,
            page_title=bp_page.title,
            page_description=bp_page.description,
            existing_sections=bp_page.sections or [],
            all_pages_info=all_pages_info,
        )

        llm = LLMBase()
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]
        actual_model, provider = _get_model_info(model)
        t0 = time.time()
        try:
            response = llm.get_completion(messages, tool_name=model)
            usage = _extract_usage(response)
            log_ai_call(
                action='suggest_sections', model_name=actual_model, provider=provider,
                system_prompt=system_prompt, user_prompt=user_prompt,
                response_text=response.choices[0].message.content,
                duration_ms=int((time.time() - t0) * 1000),
                user=request.user, **usage,
            )
        except Exception as e:
            log_ai_call(
                action='suggest_sections', model_name=actual_model, provider=provider,
                system_prompt=system_prompt, user_prompt=user_prompt,
                duration_ms=int((time.time() - t0) * 1000),
                success=False, error_message=str(e), user=request.user,
            )
            raise

        content = response.choices[0].message.content

        # Extract JSON from response
        sections = _extract_json_from_response(content)

        if not isinstance(sections, list):
            return JsonResponse({'success': False, 'error': 'AI did not return a valid sections list'}, status=500)

        return JsonResponse({'success': True, 'sections': sections})

    except BlueprintPage.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Blueprint page not found'}, status=400)
    except Exception as e:
        print(f"Error in suggest_page_sections_api: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@superuser_required
@require_http_methods(["POST"])
def fill_section_content_api(request):
    """
    Fill markdown content for a single blueprint section using AI.

    POST /ai/api/fill-section-content/
    Body: {
        "blueprint_page_id": 3,
        "section_id": "hero",
        "section_title": "Hero Section",
        "other_sections": [{"title": "Services"}],
        "model": "gemini-pro"
    }

    Returns: {"success": true, "content": "...markdown..."}
    """
    try:
        from core.models import SiteSettings, BlueprintPage
        from .utils.llm_config import LLMBase
        from .utils.prompts import PromptTemplates

        data = json.loads(request.body)
        bp_page_id = data.get('blueprint_page_id')
        section_id = data.get('section_id', '')
        section_title = data.get('section_title', '')
        other_sections = data.get('other_sections', [])
        context = data.get('context', '')
        model = data.get('model', 'gemini-pro')

        if not bp_page_id or not section_title:
            return JsonResponse({'success': False, 'error': 'blueprint_page_id and section_title are required'}, status=400)

        bp_page = BlueprintPage.objects.get(pk=bp_page_id)

        site_settings = SiteSettings.objects.first()
        site_name = site_settings.get_site_name() if site_settings else 'Website'
        project_briefing = site_settings.get_project_briefing() if site_settings else ''

        system_prompt, user_prompt = PromptTemplates.get_fill_section_content_prompt(
            site_name=site_name,
            project_briefing=project_briefing,
            page_title=bp_page.title,
            section_title=section_title,
            section_id=section_id,
            other_sections=other_sections,
            context=context,
        )

        llm = LLMBase()
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]
        actual_model, provider = _get_model_info(model)
        t0 = time.time()
        try:
            response = llm.get_completion(messages, tool_name=model)
            usage = _extract_usage(response)
            log_ai_call(
                action='fill_section', model_name=actual_model, provider=provider,
                system_prompt=system_prompt, user_prompt=user_prompt,
                response_text=response.choices[0].message.content,
                duration_ms=int((time.time() - t0) * 1000),
                user=request.user, **usage,
            )
        except Exception as e:
            log_ai_call(
                action='fill_section', model_name=actual_model, provider=provider,
                system_prompt=system_prompt, user_prompt=user_prompt,
                duration_ms=int((time.time() - t0) * 1000),
                success=False, error_message=str(e), user=request.user,
            )
            raise

        content = response.choices[0].message.content

        # Strip code fences if present
        if content.startswith('```'):
            lines = content.split('\n')
            if lines[0].startswith('```'):
                lines = lines[1:]
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            content = '\n'.join(lines)

        return JsonResponse({'success': True, 'content': content.strip()})

    except BlueprintPage.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Blueprint page not found'}, status=400)
    except Exception as e:
        print(f"Error in fill_section_content_api: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@superuser_required
@require_http_methods(["POST"])
def search_unsplash_api(request):
    """
    Search Unsplash photos (proxied to avoid exposing the API key).

    POST /ai/api/search-unsplash/
    Body: {"query": "modern office interior", "per_page": 9}

    Returns: {"success": true, "results": [...]}
    """
    from .utils.unsplash import search_photos, is_configured

    if not is_configured():
        return JsonResponse({
            'success': False,
            'error': 'Unsplash API key not configured'
        }, status=400)

    try:
        data = json.loads(request.body)
        query = data.get('query', '').strip()
        per_page = data.get('per_page', 9)

        if not query:
            return JsonResponse({
                'success': False,
                'error': 'query is required'
            }, status=400)

        results = search_photos(query=query, per_page=per_page)

        return JsonResponse({
            'success': True,
            'results': results,
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def _extract_json_from_response(content):
    """Extract JSON array or object from LLM response text."""
    import re as _re
    # Try code-fenced JSON first
    json_match = _re.search(r'```(?:json)?\s*(\[.*?\]|\{.*?\})\s*```', content, _re.DOTALL)
    if json_match:
        return json.loads(json_match.group(1))
    # Try bare JSON
    json_match = _re.search(r'(\[.*\]|\{.*\})', content, _re.DOTALL)
    if json_match:
        return json.loads(json_match.group(1))
    return json.loads(content)


@superuser_required
@require_http_methods(["POST"])
def describe_images_api(request):
    """
    API endpoint to generate AI descriptions for media library images.

    POST /ai/api/describe-images/
    Body: { "image_ids": [1, 2, 3] }

    Returns: { "results": [...], "success": true }
    """
    try:
        data = json.loads(request.body)
        image_ids = data.get('image_ids', [])

        if not image_ids:
            return JsonResponse({'success': False, 'error': 'No image IDs provided'}, status=400)

        service = ContentGenerationService(model_name='gemini-flash')
        results = service.describe_images(image_ids=image_ids)

        return JsonResponse({
            'success': True,
            'results': results,
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@superuser_required
@require_http_methods(["POST"])
def enhance_prompt_api(request):
    """
    Enhance or suggest a style prompt using AI.

    POST /ai/api/enhance-prompt/
    Body: {
        "text": "make it clean and add a button",
        "section_html": "<section ...>...</section>",  // optional, for suggest mode
        "mode": "enhance" | "suggest"
    }
    """
    try:
        data = json.loads(request.body)
        text = data.get('text', '').strip()
        section_html = data.get('section_html', '').strip()
        mode = data.get('mode', 'enhance')

        if mode == 'suggest' and not section_html:
            return JsonResponse({'success': False, 'error': 'section_html required for suggest mode'}, status=400)

        if mode == 'suggest':
            system_prompt = (
                "You are a web design consultant. Analyze the provided HTML section and suggest "
                "3-5 specific visual and layout improvements. Write as a single instruction paragraph "
                "that a user can send to an AI to refine the section. Be specific about layout changes, "
                "spacing, colors, typography, and visual effects. Reference Tailwind CSS patterns. "
                "Keep it under 150 words. Return ONLY the instruction text, no markdown formatting."
            )
            user_prompt = f"Current instruction draft:\n{text}\n\nHTML section to analyze:\n{section_html}" if text else f"HTML section to analyze:\n{section_html}"
        else:
            if not text:
                return JsonResponse({'success': False, 'error': 'text required for enhance mode'}, status=400)
            system_prompt = (
                "You are a web design prompt specialist. Expand the user's rough design instruction "
                "into a clear, detailed directive for a web designer. Be specific about layout, spacing, "
                "typography, color usage, and visual feel. Reference Tailwind CSS patterns where relevant. "
                "Keep it under 150 words. Return ONLY the enhanced instruction text, no markdown formatting."
            )
            user_prompt = text

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]

        from .utils.llm_config import LLMBase
        llm = LLMBase()
        model = 'gemini-flash'
        actual_model, provider = _get_model_info(model)
        t0 = time.time()

        try:
            response = llm.get_completion(messages, tool_name=model)
            usage = _extract_usage(response)
            log_ai_call(
                action='enhance_prompt', model_name=actual_model, provider=provider,
                system_prompt=system_prompt, user_prompt=user_prompt,
                response_text=response.choices[0].message.content,
                duration_ms=int((time.time() - t0) * 1000),
                user=request.user, **usage,
            )
        except Exception as e:
            log_ai_call(
                action='enhance_prompt', model_name=actual_model, provider=provider,
                system_prompt=system_prompt, user_prompt=user_prompt,
                duration_ms=int((time.time() - t0) * 1000),
                user=request.user, success=False, error_message=str(e),
            )
            raise

        enhanced_text = response.choices[0].message.content.strip()

        return JsonResponse({
            'success': True,
            'text': enhanced_text,
        })

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@superuser_required
@require_http_methods(["POST"])
def propagate_translation_api(request):
    """
    Propagate refined HTML to other languages via translation.

    POST /ai/api/propagate-translation/
    Body: {
        "page_id": 1,
        "source_lang": "pt",
        "target_languages": ["en"],
        "scope": "page",           # "section" or "page"
        "section_id": "hero",      # required if scope == "section"
        "html": "<section>...</section>"  # the HTML to translate
    }
    """
    try:
        data = json.loads(request.body)
        page_id = data.get('page_id')
        source_lang = data.get('source_lang')
        target_languages = data.get('target_languages', [])
        scope = data.get('scope', 'page')
        section_id = data.get('section_id')
        html = data.get('html')

        if not all([page_id, source_lang, target_languages, html]):
            return JsonResponse({'success': False, 'error': 'Missing required fields'}, status=400)

        page = Page.objects.get(id=page_id)
        service = ContentGenerationService()
        results = {}

        for target_lang in target_languages:
            if target_lang == source_lang:
                continue
            try:
                translated_html = service.translate_html(html, source_lang, target_lang)

                # Patch the page's html_content_i18n for this language
                html_i18n = dict(page.html_content_i18n or {})

                if scope == 'section' and section_id:
                    # Replace just the matching section in the target language's HTML
                    from bs4 import BeautifulSoup
                    target_page_html = html_i18n.get(target_lang, '')
                    if target_page_html:
                        soup = BeautifulSoup(target_page_html, 'html.parser')
                        old_section = soup.find('section', {'data-section': section_id})
                        if old_section:
                            new_section = BeautifulSoup(translated_html, 'html.parser')
                            old_section.replace_with(new_section)
                            html_i18n[target_lang] = str(soup)
                        else:
                            html_i18n[target_lang] = translated_html
                    else:
                        html_i18n[target_lang] = translated_html
                else:
                    # Full page replacement
                    html_i18n[target_lang] = translated_html

                page.html_content_i18n = html_i18n
                page.save(update_fields=['html_content_i18n'])
                results[target_lang] = {'success': True}
            except Exception as e:
                results[target_lang] = {'success': False, 'error': str(e)}

        return JsonResponse({'success': True, 'results': results})
    except Page.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Page not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ─── News Post AI Endpoints ─────────────────────────────────────────────────


@superuser_required
@require_http_methods(["POST"])
def generate_news_post_api(request):
    """
    Generate a news post HTML via AI. Same flow as page generation.

    POST /ai/api/generate-news-post/
    Accepts multipart (with images) or JSON body.
    Fields: brief, language, model, reference_images
    """
    try:
        if request.content_type and 'multipart' in request.content_type:
            brief = request.POST.get('brief')
            language = request.POST.get('language', 'pt')
            model = request.POST.get('model', 'gemini-pro')
            reference_images = []
            for f in request.FILES.getlist('reference_images'):
                reference_images.append({'bytes': f.read(), 'mime_type': f.content_type})
        else:
            data = json.loads(request.body)
            brief = data.get('brief')
            language = data.get('language', 'pt')
            model = data.get('model', 'gemini-pro')
            reference_images = []

        if not brief:
            return JsonResponse({'success': False, 'error': 'Brief is required'}, status=400)

        service = ContentGenerationService()
        page_data = service.generate_page(
            brief=brief,
            language=language,
            model_override=model,
            reference_images=reference_images or None,
        )

        return JsonResponse({
            'success': True,
            'page_data': page_data,
            'title_i18n': page_data.pop('title_i18n', {}),
            'slug_i18n': page_data.pop('slug_i18n', {}),
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@superuser_required
@require_http_methods(["POST"])
def generate_news_post_stream(request):
    """
    SSE streaming endpoint for news post generation.

    POST /ai/api/generate-news-post/stream/
    Same inputs as generate_news_post_api (multipart or JSON).
    Returns Server-Sent Events with progress updates followed by the final result.
    """
    try:
        if request.content_type and 'multipart' in request.content_type:
            brief = request.POST.get('brief')
            language = request.POST.get('language', 'pt')
            model = request.POST.get('model', 'gemini-pro')
            reference_images = []
            for f in request.FILES.getlist('reference_images'):
                reference_images.append({'bytes': f.read(), 'mime_type': f.content_type})
        else:
            data = json.loads(request.body)
            brief = data.get('brief')
            language = data.get('language', 'pt')
            model = data.get('model', 'gemini-pro')
            reference_images = []

        if not brief:
            return sse_response(iter([
                sse_event({'error': 'Brief is required'}, event='error')
            ]))

        service = ContentGenerationService()
        kwargs = dict(
            brief=brief,
            language=language,
            model_override=model,
            reference_images=reference_images or None,
        )
        return sse_response(run_with_progress(service.generate_page, kwargs))
    except Exception as e:
        return sse_response(iter([
            sse_event({'error': str(e)}, event='error')
        ]))


@superuser_required
@require_http_methods(["POST"])
def chat_refine_news_api(request):
    """
    Chat-based news post refinement endpoint.

    POST /ai/api/chat-refine-news/
    Accepts JSON or multipart (when reference images are included).
    Fields: post_id, message, session_id (optional), model, handle_images, reference_images
    """
    try:
        from .models import RefinementSession
        from .utils.diff_utils import compute_section_changes, build_change_summary
        from django.contrib.contenttypes.models import ContentType
        from news.models import NewsPost

        # Parse input
        if request.content_type and 'multipart' in request.content_type:
            post_id = request.POST.get('post_id')
            if post_id:
                post_id = int(post_id)
            message = request.POST.get('message')
            session_id = request.POST.get('session_id')
            if session_id:
                session_id = int(session_id)
            model = request.POST.get('model', 'gemini-pro')
            handle_images = request.POST.get('handle_images') in ('true', '1', 'on')
            reference_images = []
            for f in request.FILES.getlist('reference_images'):
                reference_images.append({'bytes': f.read(), 'mime_type': f.content_type})
        else:
            data = json.loads(request.body)
            post_id = data.get('post_id')
            message = data.get('message')
            session_id = data.get('session_id')
            model = data.get('model', 'gemini-pro')
            handle_images = bool(data.get('handle_images', False))
            reference_images = []

        if not post_id or not message:
            return JsonResponse({
                'success': False,
                'error': 'post_id and message are required'
            }, status=400)

        try:
            post = NewsPost.objects.get(id=post_id)
        except NewsPost.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'NewsPost with id {post_id} not found'
            }, status=400)

        ct = ContentType.objects.get_for_model(NewsPost)

        # Load or create session using generic FK
        if session_id:
            try:
                session = RefinementSession.objects.get(
                    id=session_id, content_type=ct, object_id=post_id
                )
            except RefinementSession.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': f'Session {session_id} not found'
                }, status=400)
        else:
            session = RefinementSession(
                content_type=ct,
                object_id=post_id,
                title=message[:80],
                model_used=model,
                created_by=request.user if request.user.is_authenticated else None,
            )
            session.save()

        # Capture old HTML for diff
        from django.utils.translation import get_language
        from core.models import SiteSettings
        site_settings = SiteSettings.objects.first()
        default_lang = site_settings.get_default_language() if site_settings else 'pt'
        current_lang = get_language() or default_lang
        html_i18n = post.html_content_i18n or {}
        old_html = html_i18n.get(current_lang) or html_i18n.get(default_lang) or ''

        # Append user message to session
        session.add_user_message(message, reference_images_count=len(reference_images))
        history = session.get_history_for_prompt()

        # Call AI service using content_override (no Page DB lookup)
        service = ContentGenerationService()
        refined_data = service.refine_page_with_html(
            instructions=message,
            model_override=model,
            reference_images=reference_images or None,
            conversation_history=history or None,
            handle_images=handle_images,
            content_override={
                'html_content_i18n': html_i18n,
                'title': post.get_i18n_field('title') or 'Untitled',
                'slug': post.get_i18n_field('slug') or '',
            },
        )

        # Save refined content to post
        new_html_i18n = refined_data.get('html_content_i18n', html_i18n)
        post.html_content_i18n = new_html_i18n
        post.save()

        # Compute section changes
        new_html = refined_data.get('html_content', '') or ''
        added, removed, modified = compute_section_changes(old_html, new_html)
        change_summary = build_change_summary(added, removed, modified)
        sections_changed = added + modified

        # Append assistant message and save session
        session.add_assistant_message(change_summary, sections_changed)
        session.save()

        return JsonResponse({
            'success': True,
            'session_id': session.id,
            'assistant_message': change_summary,
            'sections_changed': sections_changed,
            'post_id': post.id,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@superuser_required
@require_http_methods(["POST"])
def chat_refine_news_stream(request):
    """
    SSE streaming endpoint for chat-based news post refinement.

    POST /ai/api/chat-refine-news/stream/
    Same inputs as chat_refine_news_api.
    Returns Server-Sent Events with progress updates followed by the final result.
    """
    try:
        from .models import RefinementSession
        from .utils.diff_utils import compute_section_changes, build_change_summary
        from django.contrib.contenttypes.models import ContentType
        from news.models import NewsPost

        # Parse input
        if request.content_type and 'multipart' in request.content_type:
            post_id = request.POST.get('post_id')
            if post_id:
                post_id = int(post_id)
            message = request.POST.get('message')
            session_id = request.POST.get('session_id')
            if session_id:
                session_id = int(session_id)
            model = request.POST.get('model', 'gemini-pro')
            handle_images = request.POST.get('handle_images') in ('true', '1', 'on')
            reference_images = []
            for f in request.FILES.getlist('reference_images'):
                reference_images.append({'bytes': f.read(), 'mime_type': f.content_type})
        else:
            data = json.loads(request.body)
            post_id = data.get('post_id')
            message = data.get('message')
            session_id = data.get('session_id')
            model = data.get('model', 'gemini-pro')
            handle_images = bool(data.get('handle_images', False))
            reference_images = []

        if not post_id or not message:
            return sse_response(iter([
                sse_event({'error': 'post_id and message are required'}, event='error')
            ]))

        try:
            post = NewsPost.objects.get(id=post_id)
        except NewsPost.DoesNotExist:
            return sse_response(iter([
                sse_event({'error': f'NewsPost with id {post_id} not found'}, event='error')
            ]))

        ct = ContentType.objects.get_for_model(NewsPost)

        # Load or create session
        if session_id:
            try:
                session = RefinementSession.objects.get(
                    id=session_id, content_type=ct, object_id=post_id
                )
            except RefinementSession.DoesNotExist:
                return sse_response(iter([
                    sse_event({'error': f'Session {session_id} not found'}, event='error')
                ]))
        else:
            session = RefinementSession(
                content_type=ct,
                object_id=post_id,
                title=message[:80],
                model_used=model,
                created_by=request.user if request.user.is_authenticated else None,
            )
            session.save()

        # Capture old HTML for diff
        from django.utils.translation import get_language
        from core.models import SiteSettings
        site_settings = SiteSettings.objects.first()
        default_lang = site_settings.get_default_language() if site_settings else 'pt'
        current_lang = get_language() or default_lang
        html_i18n = post.html_content_i18n or {}
        old_html = html_i18n.get(current_lang) or html_i18n.get(default_lang) or ''

        session.add_user_message(message, reference_images_count=len(reference_images))
        history = session.get_history_for_prompt()

        # Build worker thread
        q = queue.Queue()
        sentinel = object()

        def on_progress(event_data):
            q.put(('progress', event_data))

        def worker():
            try:
                service = ContentGenerationService()
                refined_data = service.refine_page_with_html(
                    instructions=message,
                    model_override=model,
                    reference_images=reference_images or None,
                    conversation_history=history or None,
                    handle_images=handle_images,
                    on_progress=on_progress,
                    content_override={
                        'html_content_i18n': html_i18n,
                        'title': post.get_i18n_field('title') or 'Untitled',
                        'slug': post.get_i18n_field('slug') or '',
                    },
                )

                # Save refined content to post
                new_html_i18n = refined_data.get('html_content_i18n', html_i18n)
                post.html_content_i18n = new_html_i18n
                post.save()

                new_html = refined_data.get('html_content', '') or ''
                added, removed, modified = compute_section_changes(old_html, new_html)
                change_summary = build_change_summary(added, removed, modified)
                sections_changed = added + modified

                session.add_assistant_message(change_summary, sections_changed)
                session.save()

                q.put(('complete', {
                    'success': True,
                    'session_id': session.id,
                    'assistant_message': change_summary,
                    'sections_changed': sections_changed,
                    'post_id': post.id,
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
        return sse_response(iter([
            sse_event({'error': str(e)}, event='error')
        ]))


@superuser_required
@require_http_methods(["POST"])
def save_news_post_api(request):
    """
    Save a generated news post to the database.

    POST /ai/api/save-news-post/
    Body: {
        "html_content_i18n": {...},
        "title_i18n": {...},
        "slug_i18n": {...},
        "excerpt_i18n": {...},
        "category_id": 1,  // optional
        "is_published": false
    }
    """
    try:
        from news.models import NewsPost, NewsCategory

        data = json.loads(request.body)
        page_data = data.get('page_data', {})
        html_content_i18n = page_data.get('html_content_i18n', data.get('html_content_i18n', {}))
        title_i18n = data.get('title_i18n', data.get('title', {}))
        slug_i18n = data.get('slug_i18n', data.get('slug', {}))
        excerpt_i18n = data.get('excerpt_i18n', {})
        category_id = data.get('category_id')
        is_published = data.get('is_published', False)

        post = NewsPost(
            title_i18n=title_i18n,
            slug_i18n=slug_i18n,
            excerpt_i18n=excerpt_i18n,
            html_content_i18n=html_content_i18n,
            is_published=is_published,
        )

        if category_id:
            try:
                post.category = NewsCategory.objects.get(id=category_id)
            except NewsCategory.DoesNotExist:
                pass

        post.save()

        return JsonResponse({
            'success': True,
            'post_id': post.id,
            'message': f'News post saved: {post}'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@superuser_required
@require_http_methods(["GET"])
def list_news_refinement_sessions_api(request, post_id):
    """Return refinement sessions for a news post."""
    from .models import RefinementSession
    from django.contrib.contenttypes.models import ContentType
    from news.models import NewsPost

    ct = ContentType.objects.get_for_model(NewsPost)
    sessions = RefinementSession.objects.filter(
        content_type=ct, object_id=post_id
    ).order_by('-updated_at')[:20]

    return JsonResponse({
        'success': True,
        'sessions': [
            {
                'id': s.id,
                'title': s.title,
                'message_count': len(s.messages),
                'updated_at': s.updated_at.isoformat(),
            }
            for s in sessions
        ]
    })
