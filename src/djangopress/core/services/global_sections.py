"""GlobalSectionService — header/footer and global section management."""

from djangopress.core.models import GlobalSection


class GlobalSectionService:

    @staticmethod
    def get(key):
        """Get a GlobalSection by key.

        Args:
            key: Unique slug key (e.g. 'main-header', 'main-footer').

        Returns:
            dict with 'success', 'section' (GlobalSection instance), or 'error'.
        """
        try:
            section = GlobalSection.objects.get(key=key)
            return {'success': True, 'section': section}
        except GlobalSection.DoesNotExist:
            return {'success': False, 'error': f'GlobalSection "{key}" not found'}

    @staticmethod
    def list(active_only=False, section_type=None):
        """List GlobalSections with optional filters.

        Args:
            active_only: If True, only return active sections.
            section_type: Filter by section type ('header', 'footer', etc.).

        Returns:
            dict with 'success', 'sections' (list of GlobalSection), 'message'.
        """
        qs = GlobalSection.objects.all().order_by('order', 'pk')
        if active_only:
            qs = qs.filter(is_active=True)
        if section_type:
            qs = qs.filter(section_type=section_type)
        sections = list(qs)
        return {
            'success': True,
            'sections': sections,
            'message': f'{len(sections)} global sections found',
        }

    @staticmethod
    def get_html(key, lang=None):
        """Get the HTML for a GlobalSection in a specific language.

        Falls back to the first available language if the requested
        language is not present in html_template_i18n.

        Args:
            key: Section key.
            lang: Language code. Defaults to site's default language.

        Returns:
            dict with 'success', 'html', 'language', or 'error'.
        """
        result = GlobalSectionService.get(key)
        if not result['success']:
            return result

        section = result['section']
        from djangopress.core.models import SiteSettings
        settings = SiteSettings.load()
        lang = lang or (settings.get_default_language() if settings else 'pt')

        html_i18n = section.html_template_i18n or {}
        html = html_i18n.get(lang) or next(iter(html_i18n.values()), '')

        return {'success': True, 'html': html, 'language': lang}

    @staticmethod
    def update_html(key, html, lang=None):
        """Update the HTML for a GlobalSection in a specific language.

        Args:
            key: Section key.
            html: New HTML content.
            lang: Language code. Defaults to site's default language.

        Returns:
            dict with 'success', 'message', or 'error'.
        """
        result = GlobalSectionService.get(key)
        if not result['success']:
            return result

        section = result['section']
        from djangopress.core.models import SiteSettings
        settings = SiteSettings.load()
        lang = lang or (settings.get_default_language() if settings else 'pt')

        html_i18n = dict(section.html_template_i18n or {})
        html_i18n[lang] = html
        section.html_template_i18n = html_i18n
        section.save()

        return {
            'success': True,
            'message': f'Updated "{key}" HTML for language "{lang}"',
        }

    @staticmethod
    def refine(key, instructions, model=None, user=None):
        """AI-refine a GlobalSection. Delegates to ContentGenerationService.

        Args:
            key: Section key.
            instructions: Refinement instructions for the AI.
            model: LLM model name. Defaults to configured header_footer model.
            user: User requesting the refinement (for audit).

        Returns:
            dict with 'success', 'message', 'assistant_message', or 'error'.
        """
        from djangopress.ai.utils.llm_config import get_ai_model
        model = model or get_ai_model('header_footer')

        result = GlobalSectionService.get(key)
        if not result['success']:
            return result

        from djangopress.ai.services import ContentGenerationService
        service = ContentGenerationService(model_name=model)
        ai_result = service.refine_global_section(
            section_key=key,
            refinement_instructions=instructions,
            model_override=model,
        )

        # Save the refined HTML
        section = GlobalSection.objects.get(key=key)
        section.html_template_i18n = ai_result.get('html_template_i18n', section.html_template_i18n or {})
        if ai_result.get('html_template'):
            section.html_template = ai_result['html_template']
        if ai_result.get('content'):
            section.content = ai_result['content']
        section.save()

        return {
            'success': True,
            'message': f'Refined {key} with AI',
            'assistant_message': ai_result.get('assistant_message', ''),
        }
