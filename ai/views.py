"""
AI Content Generation Views
"""
import json
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.csrf import csrf_exempt
from core.models import Page
from .services import ContentGenerationService


@staff_member_required
@require_http_methods(["POST"])
def generate_page_api(request):
    """
    API endpoint to generate a complete page as HTML + translations

    POST /ai/api/generate-page/
    Body: {
        "brief": "User description",
        "page_type": "about",  # optional
        "language": "pt",  # optional, default: 'pt'
        "model": "gemini-flash"  # optional, default from service
    }

    Returns: {
        "success": true,
        "page_data": {"html_content": "...", "content": {"translations": {...}}}
    }
    """
    try:
        data = json.loads(request.body)
        brief = data.get('brief')
        page_type = data.get('page_type', 'general')
        language = data.get('language', 'pt')
        model = data.get('model', 'gemini-pro')

        if not brief:
            return JsonResponse({
                'success': False,
                'error': 'Brief is required'
            }, status=400)

        # Generate page
        service = ContentGenerationService()
        page_data = service.generate_page(
            brief=brief,
            page_type=page_type,
            language=language,
            model_override=model
        )

        return JsonResponse({
            'success': True,
            'page_data': page_data
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@staff_member_required
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

        # Save the refined header to the database
        from core.models import GlobalSection
        section = GlobalSection.objects.get(key='main-header')
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


@staff_member_required
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

        # Save the refined footer to the database
        from core.models import GlobalSection
        section = GlobalSection.objects.get(key='main-footer')
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


@staff_member_required
@require_http_methods(["POST"])
def save_generated_page_api(request):
    """
    API endpoint to save generated page to database

    POST /ai/api/save-page/
    Body: {
        "slug": "new-page" or {"pt": "nova-pagina", "en": "new-page"},
        "title": "New Page" or {"pt": "Nova Página", "en": "New Page"},
        "page_data": {"html_content": "...", "content": {"translations": {...}}}
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
            page.html_content = page_data.get('html_content', '')
            page.content = page_data.get('content', {})
            page.is_active = True
            page.save()
            created = False
        else:
            page = Page.objects.create(
                title_i18n=title_i18n,
                slug_i18n=slug_i18n,
                html_content=page_data.get('html_content', ''),
                content=page_data.get('content', {}),
                is_active=True
            )
            created = True

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


@staff_member_required
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
        project_briefing = site_settings.get_project_briefing(language) if site_settings else ''
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
        response = llm.get_completion(messages, tool_name=model)

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


@staff_member_required
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

        data = json.loads(request.body)
        page_id = data.get('page_id')
        instructions = data.get('instructions')
        section_name = data.get('section_name')
        language = data.get('language', 'pt')
        model = data.get('model', 'gemini-pro')

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
            }, status=404)

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
            model_override=model
        )

        # Save refined content to page
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
