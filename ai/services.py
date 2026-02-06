"""
AI Content Generation Services
Main service layer for generating and refining pages and global sections (header/footer)
"""
import json
import re
from typing import Dict, List, Any, Optional, Union
from .utils.llm_config import LLMBase
from .utils.prompts import PromptTemplates


class ContentGenerationService:
    """Service for generating CMS content using LLM"""

    def __init__(self, model_name: str = 'gemini-pro'):
        """
        Initialize the content generation service

        Args:
            model_name: Name of the LLM model to use (from MODEL_CONFIG)
                       Options: 'gpt-5', 'gpt-5-mini', 'claude', 'gemini-pro', 'gemini-flash', 'gemini-lite'
                       Default: 'gemini-pro' (high quality, balanced speed)
        """
        self.llm = LLMBase()
        self.model_name = model_name

    def _extract_json_from_response(self, content: str, retry_count: int = 0, max_retries: int = 2) -> Union[Dict, List]:
        """
        Extract and parse JSON from LLM response
        Handles cases where the LLM includes markdown code blocks or extra text
        If JSON parsing fails, automatically asks LLM to fix the error

        Args:
            content: Raw response content from LLM
            retry_count: Current retry attempt (internal use)
            max_retries: Maximum number of retry attempts

        Returns:
            Parsed JSON object or array

        Raises:
            ValueError: If no valid JSON found after all retries
        """
        # Try to find JSON in markdown code blocks first
        json_match = re.search(r'```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```', content, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find raw JSON (array or object)
            json_match = re.search(r'(\{.*\}|\[.*\])', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # Last resort: assume entire content is JSON
                json_str = content

        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            error_msg = str(e)
            print(f"Failed to parse JSON (attempt {retry_count + 1}/{max_retries + 1}): {error_msg}")
            print(f"Error location: {e.msg} at line {e.lineno}, column {e.colno}")

            # If we haven't exceeded max retries, ask LLM to fix the error
            if retry_count < max_retries:
                print(f"Asking LLM to fix the JSON error...")
                fixed_content = self._ask_llm_to_fix_json(content, error_msg, e.lineno, e.colno)
                if fixed_content:
                    # Recursively try to parse the fixed JSON
                    return self._extract_json_from_response(fixed_content, retry_count + 1, max_retries)

            # If all retries failed, raise the error
            print(f"Raw content: {content[:500]}...")
            raise ValueError(f"LLM did not return valid JSON after {retry_count + 1} attempts: {e}")

    def _ask_llm_to_fix_json(self, broken_json: str, error_msg: str, line_no: int, col_no: int) -> Optional[str]:
        """
        Ask the LLM to fix broken JSON

        Args:
            broken_json: The broken JSON string
            error_msg: The JSON error message
            line_no: Line number where error occurred
            col_no: Column number where error occurred

        Returns:
            Fixed JSON string, or None if LLM couldn't fix it
        """
        fix_prompt = f"""The previous response contained invalid JSON. Please fix the following JSON syntax error:

**Error**: {error_msg}
**Location**: Line {line_no}, Column {col_no}

**Broken JSON**:
```json
{broken_json}
```

Please return ONLY the corrected JSON, with no additional text, explanations, or markdown code blocks.
Focus on:
1. Fixing the syntax error at the specified location
2. Ensuring all quotes are properly escaped
3. Ensuring all commas are in the right places
4. Ensuring all brackets and braces are properly closed
5. Making sure the JSON is valid and parseable

Return the complete, corrected JSON now:"""

        try:
            # Use a fast model for fixing
            messages = [{"role": "user", "content": fix_prompt}]
            response = self.llm.get_completion(
                messages=messages,
                tool_name=self.model_name
            )

            if response and hasattr(response, 'choices') and len(response.choices) > 0:
                fixed_json = response.choices[0].message.content
                print(f"LLM attempted to fix the JSON")
                return fixed_json

        except Exception as e:
            print(f"Error asking LLM to fix JSON: {e}")

        return None

    def _extract_html_from_response(self, content: str) -> str:
        """
        Extract HTML from LLM response, handling markdown code blocks

        Args:
            content: Raw response content from LLM

        Returns:
            Extracted HTML string
        """
        # Try to find HTML in markdown code blocks first
        html_match = re.search(r'```(?:html)?\s*(.*?)\s*```', content, re.DOTALL)
        if html_match:
            return html_match.group(1).strip()

        # Otherwise return content stripped of leading/trailing whitespace
        return content.strip()

    def generate_page(
        self,
        brief: str,
        page_type: str = 'general',
        language: str = 'pt',
        model_override: str = None
    ) -> Dict:
        """
        Generate a complete page as a single HTML document with translations

        Args:
            brief: User's description of the desired page
            page_type: Type of page (e.g., 'about', 'services', 'home')
            language: Primary language for content (default: 'pt')
            model_override: Override the default model for this request

        Returns:
            Dictionary with 'html_content' and 'content' (translations)

        Raises:
            ValueError: If generation fails or returns invalid data
        """
        print(f"\n=== Generating Page ===")
        print(f"Brief: {brief}")
        print(f"Page Type: {page_type}")
        print(f"Language: {language}")

        # Get site context
        from core.models import SiteSettings
        site_settings = SiteSettings.objects.first()
        site_name = site_settings.get_site_name(language) if site_settings else 'Website'
        site_description = site_settings.get_site_description(language) if site_settings else ''
        project_briefing = site_settings.get_project_briefing(language) if site_settings else ''
        languages = site_settings.get_language_codes() if site_settings else ['pt', 'en']

        # Build prompt
        system_prompt, user_prompt = PromptTemplates.get_page_generation_prompt(
            site_name=site_name,
            site_description=site_description,
            project_briefing=project_briefing,
            languages=languages,
            brief=brief,
            page_type=page_type
        )

        # Print prompts for debugging
        system_token_estimate = len(system_prompt.split()) * 1.3
        user_token_estimate = len(user_prompt.split()) * 1.3
        total_token_estimate = system_token_estimate + user_token_estimate

        print("\n" + "="*80)
        print(f"SYSTEM PROMPT (≈{int(system_token_estimate)} tokens):")
        print("="*80)
        print(system_prompt)
        print("\n" + "="*80)
        print(f"USER PROMPT (≈{int(user_token_estimate)} tokens):")
        print("="*80)
        print(user_prompt)
        print("="*80)
        print(f"TOTAL ESTIMATED TOKENS: ≈{int(total_token_estimate)}")
        print("="*80 + "\n")

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ]

        # Get LLM completion
        model = model_override or self.model_name
        response = self.llm.get_completion(messages, tool_name=model)

        # Extract and parse response
        content = response.choices[0].message.content
        page_data = self._extract_json_from_response(content)

        # Validate the response
        if isinstance(page_data, list):
            raise ValueError("LLM returned a list instead of a page object")

        if 'html_content' not in page_data:
            raise ValueError("Response missing 'html_content' field")

        if 'content' not in page_data:
            page_data['content'] = {}

        # Ensure translations structure exists
        if 'translations' not in page_data.get('content', {}):
            page_data['content']['translations'] = {}

        print(f"✓ Successfully generated page HTML")
        return page_data

    def refine_global_section(
        self,
        section_key: str,
        refinement_instructions: str,
        model_override: str = None,
        prompt_version: str = 'v2'
    ) -> Dict:
        """
        Refine a GlobalSection (header/footer) based on user instructions

        Args:
            section_key: Key of the GlobalSection ('main-header' or 'main-footer')
            refinement_instructions: User's instructions for modifications
            model_override: Override the default model for this request
            prompt_version: Kept for backward compatibility (always uses v2)

        Returns:
            Updated section dictionary with html_template and content

        Raises:
            ValueError: If section not found or generation fails
        """
        print(f"\n=== Refining Global Section ===")
        print(f"Section Key: {section_key}")
        print(f"Instructions: {refinement_instructions}")

        # Get existing GlobalSection
        try:
            from core.models import GlobalSection
            section = GlobalSection.objects.get(key=section_key)
        except GlobalSection.DoesNotExist:
            raise ValueError(f"GlobalSection with key '{section_key}' not found")

        # Convert to dict
        existing_data = {
            'key': section.key,
            'section_type': section.section_type,
            'html_template': section.html_template,
            'content': section.content,
            'name': section.name,
        }

        # Get site context
        from core.models import SiteSettings, Page
        site_settings = SiteSettings.objects.first()
        language = site_settings.default_language if site_settings else 'pt'
        site_name = site_settings.get_site_name(language) if site_settings else 'Website'
        site_description = site_settings.get_site_description(language) if site_settings else ''
        project_briefing = site_settings.get_project_briefing(language) if site_settings else ''
        languages = site_settings.get_language_codes() if site_settings else ['pt', 'en']

        # Get all pages with their slugs in all languages
        pages_data = []
        for page in Page.objects.filter(is_active=True).order_by('id'):
            page_info = {
                'title': page.title_i18n or {},
                'slug': page.slug_i18n or {},
            }
            pages_data.append(page_info)

        # Build prompt for global section
        system_prompt, user_prompt = PromptTemplates.get_global_section_refinement_prompt(
            site_name=site_name,
            site_description=site_description,
            project_briefing=project_briefing,
            languages=languages,
            pages=pages_data,
            existing_section=existing_data,
            user_request=refinement_instructions,
            section_type=section.section_type
        )

        # Print prompts for debugging
        system_token_estimate = len(system_prompt.split()) * 1.3
        user_token_estimate = len(user_prompt.split()) * 1.3
        total_token_estimate = system_token_estimate + user_token_estimate

        print("\n" + "="*80)
        print(f"SYSTEM PROMPT (≈{int(system_token_estimate)} tokens):")
        print("="*80)
        print(system_prompt)
        print("\n" + "="*80)
        print(f"USER PROMPT (≈{int(user_token_estimate)} tokens):")
        print("="*80)
        print(user_prompt)
        print("="*80)
        print(f"TOTAL ESTIMATED TOKENS: ≈{int(total_token_estimate)}")
        print("="*80 + "\n")

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ]

        # Get LLM completion with higher max_tokens for complete HTML templates
        model = model_override or self.model_name

        from .utils.llm_config import MODEL_CONFIG, ModelProvider
        config = MODEL_CONFIG.get(model, None)
        if config and config.provider == ModelProvider.GOOGLE:
            response = self.llm.get_completion(
                messages,
                tool_name=model,
                max_output_tokens=16384
            )
        else:
            response = self.llm.get_completion(
                messages,
                tool_name=model,
                max_tokens=16384
            )

        # Extract and parse response
        content = response.choices[0].message.content
        refined_data = self._extract_json_from_response(content)

        # If response is a list, take first item
        if isinstance(refined_data, list):
            if not refined_data:
                raise ValueError("LLM returned empty list")
            refined_data = refined_data[0]

        # Validate essential fields for GlobalSection
        if 'html_template' not in refined_data:
            raise ValueError("Refined section missing 'html_template' field")

        # Ensure content field exists
        if 'content' not in refined_data:
            refined_data['content'] = {}

        # Validate that all {{trans.xxx}} variables in html_template have translations
        html_template = refined_data.get('html_template', '')
        content = refined_data.get('content', {})
        translations = content.get('translations', {})

        trans_vars = set(re.findall(r'\{\{\s*trans\.(\w+)\s*\}\}', html_template))

        if trans_vars and translations:
            missing_vars = {}
            for lang in languages:
                lang_trans = translations.get(lang, {})
                missing_in_lang = trans_vars - set(lang_trans.keys())
                if missing_in_lang:
                    missing_vars[lang] = list(missing_in_lang)

            if missing_vars:
                print(f"⚠️  WARNING: Missing translations detected!")
                for lang, vars in missing_vars.items():
                    print(f"  - {lang.upper()}: {', '.join(vars)}")
                print(f"  The {section.section_type} may render with blank text for these variables.")

        print(f"✓ Successfully refined global section: {section_key}")
        return refined_data

    def refine_page_with_html(
        self,
        page_id: int,
        instructions: str,
        section_name: str = None,
        language: str = 'pt',
        model_override: str = None
    ) -> Dict:
        """
        Refine a page's HTML content based on user instructions.

        Sends the page's html_content and translations to the LLM for refinement.
        If section_name is provided, the LLM focuses on that specific section.

        Args:
            page_id: ID of the page being refined
            instructions: User's refinement instructions
            section_name: Optional data-section name to target specific section
            language: Primary language for content (default: 'pt')
            model_override: Override the default model for this request

        Returns:
            Dictionary with 'html_content' and 'content' (translations)

        Raises:
            ValueError: If refinement fails
        """
        print(f"\n=== Refining Page (HTML-based) ===")
        print(f"Page ID: {page_id}")
        print(f"Instructions: {instructions}")
        print(f"Section: {section_name or 'entire page'}")
        print(f"Language: {language}")

        # Get page
        from core.models import Page, SiteSettings
        try:
            page = Page.objects.get(id=page_id)
        except Page.DoesNotExist:
            raise ValueError(f"Page with ID {page_id} not found")

        page_title = page.default_title
        page_slug = page.default_slug

        # Get site context
        site_settings = SiteSettings.objects.first()
        site_name = site_settings.get_site_name(language) if site_settings else 'Website'
        site_description = site_settings.get_site_description(language) if site_settings else ''
        project_briefing = site_settings.get_project_briefing(language) if site_settings else ''
        languages = site_settings.get_language_codes() if site_settings else ['pt', 'en']

        # Build design settings
        design_settings = {}
        if site_settings:
            design_settings = {
                'primary_color': site_settings.primary_color or 'bg-blue-600',
                'secondary_color': site_settings.secondary_color or 'bg-gray-600',
                'accent_color': site_settings.accent_color or 'bg-orange-500',
                'background_color': site_settings.background_color or 'bg-white',
                'text_color': site_settings.text_color or 'text-gray-900',
                'heading_color': site_settings.heading_color or 'text-gray-900',
                'body_font': site_settings.body_font or 'Inter',
                'heading_font': site_settings.heading_font or 'Inter',
                'primary_button': f"{site_settings.primary_button_bg or 'bg-blue-600'} {site_settings.primary_button_text or 'text-white'} px-6 py-3 rounded-md hover:{site_settings.primary_button_hover or 'bg-blue-700'} transition-colors",
                'secondary_button': f"{site_settings.secondary_button_bg or 'bg-gray-200'} {site_settings.secondary_button_text or 'text-gray-900'} px-6 py-3 rounded-md hover:{site_settings.secondary_button_hover or 'bg-gray-300'} transition-colors",
                'section_padding': 'py-16 md:py-24',
                'container_width': site_settings.container_width or 'container mx-auto px-6',
                'border_radius': site_settings.border_radius_preset or 'rounded-lg',
            }

        # Prepare the refinement instructions with section targeting
        targeted_instructions = instructions
        if section_name:
            targeted_instructions = f"Focus on the <section data-section=\"{section_name}\"> section. {instructions}"

        # Build prompt
        system_prompt, user_prompt = PromptTemplates.get_page_refinement_prompt(
            site_name=site_name,
            site_description=site_description,
            project_briefing=project_briefing,
            languages=languages,
            page_html=page.html_content or '',
            page_content=page.content or {},
            user_request=targeted_instructions,
            page_title=page_title,
            page_slug=page_slug,
            design_settings=design_settings
        )

        # Print prompts for debugging
        system_token_estimate = len(system_prompt.split()) * 1.3
        user_token_estimate = len(user_prompt.split()) * 1.3
        total_token_estimate = system_token_estimate + user_token_estimate

        print("\n" + "="*80)
        print(f"SYSTEM PROMPT (≈{int(system_token_estimate)} tokens):")
        print("="*80)
        print(system_prompt)
        print("\n" + "="*80)
        print(f"USER PROMPT (≈{int(user_token_estimate)} tokens):")
        print("="*80)
        print(user_prompt)
        print("="*80)
        print(f"TOTAL ESTIMATED TOKENS: ≈{int(total_token_estimate)}")
        print("="*80 + "\n")

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ]

        # Get LLM completion
        model = model_override or self.model_name
        response = self.llm.get_completion(messages, tool_name=model)

        # Extract and parse response
        content = response.choices[0].message.content
        refined_data = self._extract_json_from_response(content)

        # Validate
        if isinstance(refined_data, list):
            raise ValueError("LLM returned a list instead of a page object")

        if 'html_content' not in refined_data:
            raise ValueError("Refined page missing 'html_content' field")

        if 'content' not in refined_data:
            refined_data['content'] = {}

        print(f"✓ Successfully refined page")
        return refined_data
