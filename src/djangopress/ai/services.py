"""
AI Content Generation Services
Main service layer for generating and refining pages and global sections (header/footer)
"""
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Any, Optional, Union
from .utils.llm_config import LLMBase, MODEL_CONFIG, get_ai_model
from .utils.prompts import PromptTemplates
from .utils.components import ComponentRegistry
from .models import log_ai_call


class ContentGenerationService:
    """Service for generating CMS content using LLM"""

    def __init__(self, model_name=None):
        """
        Initialize the content generation service

        Args:
            model_name: Name of the LLM model to use (from MODEL_CONFIG)
                       Options: 'gpt-5', 'gpt-5-mini', 'claude', 'gemini-pro', 'gemini-flash', 'gemini-lite'
                       Default: 'gemini-pro' (high quality, balanced speed)
        """
        self.llm = LLMBase()
        self.model_name = model_name or get_ai_model('refinement_section')

    @staticmethod
    def _get_model_info(tool_name: str) -> tuple:
        """Return (actual_model_name, provider_string) for a tool_name key."""
        config = MODEL_CONFIG.get(tool_name)
        if config:
            return config.model_name, config.provider.value
        return tool_name, 'unknown'

    @staticmethod
    def _extract_usage(response) -> dict:
        """Extract token usage from a StandardizedLLMResponse."""
        usage = getattr(response, 'usage', None)
        if usage is None:
            return {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}
        return {
            'prompt_tokens': getattr(usage, 'prompt_tokens', 0) or 0,
            'completion_tokens': getattr(usage, 'completion_tokens', 0) or 0,
            'total_tokens': getattr(usage, 'total_tokens', 0) or 0,
        }

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
            # Use a fast model for fixing — never the expensive pro model
            messages = [{"role": "user", "content": fix_prompt}]
            response = self.llm.get_completion(
                messages=messages,
                tool_name=get_ai_model('refinement_section')
            )

            if response and hasattr(response, 'choices') and len(response.choices) > 0:
                fixed_json = response.choices[0].message.content
                print(f"LLM attempted to fix the JSON")
                return fixed_json

        except Exception as e:
            print(f"Error asking LLM to fix JSON: {e}")

        return None

    def _make_stream_callback(self, on_progress, step_name, throttle_chars=500):
        """Create an on_stream callback that sends progress events during LLM streaming."""
        last_update = [0]
        start_time = [time.time()]

        def on_stream(accumulated_text, char_count):
            if char_count - last_update[0] >= throttle_chars:
                last_update[0] = char_count
                elapsed = time.time() - start_time[0]
                if on_progress:
                    try:
                        on_progress({
                            "step": step_name,
                            "status": "streaming",
                            "chars": char_count,
                            "elapsed": round(elapsed, 1),
                        })
                    except Exception:
                        pass
        return on_stream

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

    def _split_multi_options(self, html: str) -> list:
        """
        Split already-extracted HTML containing multiple options separated by
        <!-- OPTION_N --> markers into a list of HTML strings.

        Args:
            html: HTML string (already extracted from LLM response)

        Returns:
            List of HTML strings (1-3 items). Falls back to [html]
            if no markers found.
        """
        # Split on <!-- OPTION_N --> markers
        parts = re.split(r'<!--\s*OPTION_\d+\s*-->', html)

        # Filter out empty/whitespace-only parts
        options = [p.strip() for p in parts if p.strip()]

        if not options:
            return [html]

        return options[:3]  # Cap at 3

    @staticmethod
    def _strip_legacy_attrs(html: str) -> str:
        """Strip legacy data-element-id attributes from HTML to save tokens."""
        return re.sub(r'\s+data-element-id="[^"]*"', '', html)


    def _generate_page_metadata(self, brief: str, languages: list, model: str) -> Dict:
        """
        Ask LLM to suggest title_i18n and slug_i18n from the page brief.

        Args:
            brief: User's page description
            languages: List of language codes
            model: LLM model name to use

        Returns:
            Dict with 'title_i18n' and 'slug_i18n'
        """
        print(f"\n--- Generating page metadata (title/slug) ---")

        # Always use a lightweight model for metadata — title/slug generation is a trivial task
        model = get_ai_model('metadata')

        system_prompt, user_prompt = PromptTemplates.get_page_metadata_prompt(
            brief=brief,
            languages=languages
        )

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ]

        actual_model, provider = self._get_model_info(model)
        t0 = time.time()
        try:
            response = self.llm.get_completion(messages, tool_name=model)
            usage = self._extract_usage(response)
            content = response.choices[0].message.content
            log_ai_call(
                action='generate_metadata', model_name=actual_model, provider=provider,
                system_prompt=system_prompt, user_prompt=user_prompt,
                response_text=content,
                duration_ms=int((time.time() - t0) * 1000), **usage,
            )
            metadata = self._extract_json_from_response(content)

            title_i18n = metadata.get('title_i18n', {})
            slug_i18n = metadata.get('slug_i18n', {})

            # Sanitize slugs
            for lang in languages:
                if lang in slug_i18n:
                    slug = slug_i18n[lang].lower().strip()
                    slug = re.sub(r'[^a-z0-9-]', '', slug)
                    slug = re.sub(r'-+', '-', slug).strip('-')
                    slug_i18n[lang] = slug

            print(f"Suggested titles: {title_i18n}")
            print(f"Suggested slugs: {slug_i18n}")
            return {'title_i18n': title_i18n, 'slug_i18n': slug_i18n}

        except Exception as e:
            log_ai_call(
                action='generate_metadata', model_name=actual_model, provider=provider,
                system_prompt=system_prompt, user_prompt=user_prompt,
                duration_ms=int((time.time() - t0) * 1000),
                success=False, error_message=str(e),
            )
            print(f"WARNING: Metadata generation failed: {e}")
            return {'title_i18n': {}, 'slug_i18n': {}}

    def generate_page(
        self,
        brief: str,
        language: str = 'pt',
        model_override: str = None,
        reference_images: list = None,
        outline: list = None,
        on_progress=None
    ) -> Dict:
        """
        Generate a page as HTML in the default language.

        Step 1: LLM generates clean HTML with real text in the default language.
        Step 2: Generate page metadata (title_i18n, slug_i18n).

        No templatize/translate step — HTML is stored per-language in html_content_i18n.

        Args:
            brief: User's description of the desired page
            language: Primary language for content (default: 'pt')
            model_override: Override the default model for this request

        Returns:
            Dictionary with 'html_content_i18n', 'title_i18n', 'slug_i18n'

        Raises:
            ValueError: If generation fails or returns invalid data
        """
        def notify(step, status, **extra):
            if on_progress:
                try:
                    on_progress({"step": step, "status": status, **extra})
                except Exception:
                    pass

        print(f"\n=== Generating Page (HTML + Metadata) ===")
        print(f"Brief: {brief}")
        print(f"Language: {language}")

        # Get site context
        from djangopress.core.models import SiteSettings, Page
        site_settings = SiteSettings.objects.first()
        default_language = site_settings.get_default_language() if site_settings else 'pt'
        site_name = site_settings.get_site_name(default_language) if site_settings else 'Website'
        site_description = site_settings.get_site_description(default_language) if site_settings else ''
        project_briefing = site_settings.get_project_briefing() if site_settings else ''
        languages = site_settings.get_language_codes() if site_settings else ['pt', 'en']
        model = model_override or self.model_name

        # --- Step 1: Generate clean HTML with real text ---
        print(f"\n--- Step 1: Generate HTML in {default_language.upper()} ---")

        design_guide = site_settings.design_guide if site_settings else ''

        # Build available pages list for inter-page linking
        pages_data = []
        for p in Page.objects.filter(is_active=True).order_by('id'):
            pages_data.append({'title': p.title_i18n or {}, 'slug': p.slug_i18n or {}})

        # Pass 1: Select relevant component skills
        notify("component_selection", "running")
        selected_components = ComponentRegistry.select_components(
            user_request=brief,
            existing_html="",
            llm=self.llm,
        )
        component_references = ComponentRegistry.get_references(selected_components)
        notify("component_selection", "done")

        system_prompt, user_prompt = PromptTemplates.get_page_generation_html_prompt(
            site_name=site_name,
            site_description=site_description,
            project_briefing=project_briefing,
            default_language=default_language,
            brief=brief,
            has_reference_images=bool(reference_images),
            design_guide=design_guide,
            pages=pages_data,
            languages=languages,
            outline=outline,
            component_references=component_references,
        )

        # Debug output
        system_token_estimate = len(system_prompt.split()) * 1.3
        user_token_estimate = len(user_prompt.split()) * 1.3
        total_token_estimate = system_token_estimate + user_token_estimate

        print(f"GENERATION PROMPT (≈{int(total_token_estimate)} tokens)")

        notify("html_generation", "running", model=model)
        actual_model, provider = self._get_model_info(model)
        t0 = time.time()
        try:
            if reference_images:
                # Use vision call with images — combine system + user prompt
                print(f"Using vision call with {len(reference_images)} reference image(s)")
                combined_prompt = system_prompt + "\n\n" + user_prompt
                response = self.llm.get_vision_completion(
                    prompt=combined_prompt,
                    images=reference_images,
                    tool_name=model
                )
            else:
                messages = [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt}
                ]
                stream_cb = self._make_stream_callback(on_progress, 'html_generation')
                response = self.llm.get_completion(messages, tool_name=model, on_stream=stream_cb)

            usage = self._extract_usage(response)
            log_ai_call(
                action='generate_page', model_name=actual_model, provider=provider,
                system_prompt=system_prompt, user_prompt=user_prompt,
                response_text=response.choices[0].message.content,
                duration_ms=int((time.time() - t0) * 1000), **usage,
            )
        except Exception as e:
            log_ai_call(
                action='generate_page', model_name=actual_model, provider=provider,
                system_prompt=system_prompt, user_prompt=user_prompt,
                duration_ms=int((time.time() - t0) * 1000),
                success=False, error_message=str(e),
            )
            raise

        raw_html = self._extract_html_from_response(response.choices[0].message.content)

        if not raw_html or len(raw_html.strip()) < 50:
            raise ValueError("Step 1 returned empty or too-short HTML")

        print(f"Step 1 produced {len(raw_html)} chars of HTML")
        notify("html_generation", "done", chars=len(raw_html))

        # --- Step 2: Generate metadata only (templatize/translate removed) ---
        notify("metadata_generation", "running")
        print(f"\nRunning Step 2 (metadata) only — templatize/translate removed")
        metadata = self._generate_page_metadata(brief, languages, model)
        notify("metadata_generation", "done")

        default_lang = default_language
        page_data = {
            'html_content_i18n': {default_lang: raw_html},
        }
        page_data['title_i18n'] = metadata.get('title_i18n', {})
        page_data['slug_i18n'] = metadata.get('slug_i18n', {})

        print(f"Successfully generated page")
        notify("complete", "done")
        return page_data

    def refine_global_section(
        self,
        section_key: str,
        refinement_instructions: str,
        model_override: str = None,
        prompt_version: str = 'v2',
        on_progress=None
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
        def notify(step, status, **extra):
            if on_progress:
                try:
                    on_progress({"step": step, "status": status, **extra})
                except Exception:
                    pass

        print(f"\n=== Refining Global Section ===")
        print(f"Section Key: {section_key}")
        print(f"Instructions: {refinement_instructions}")

        # Get existing GlobalSection
        notify("load_section", "running")
        try:
            from djangopress.core.models import GlobalSection
            from django.utils.translation import get_language
            section = GlobalSection.objects.get(key=section_key)
        except GlobalSection.DoesNotExist:
            raise ValueError(f"GlobalSection with key '{section_key}' not found")

        # Convert to dict — read from html_template_i18n with fallback
        from djangopress.core.models import SiteSettings, Page
        site_settings = SiteSettings.objects.first()
        default_language = site_settings.get_default_language() if site_settings else 'pt'
        current_lang = default_language  # get_language() unreliable in AJAX context
        template_i18n = section.html_template_i18n or {}
        current_template = template_i18n.get(current_lang) or template_i18n.get(default_language) or ''
        print(f"Reading html_template from html_template_i18n[{current_lang}] ({len(current_template or '')} chars)")

        existing_data = {
            'key': section.key,
            'section_type': section.section_type,
            'html_template': current_template,
            'content': section.content,
            'name': section.name,
        }
        notify("load_section", "done")

        # Get site context
        language = site_settings.default_language if site_settings else 'pt'
        site_name = site_settings.get_site_name(language) if site_settings else 'Website'
        site_description = site_settings.get_site_description(language) if site_settings else ''
        project_briefing = site_settings.get_project_briefing() if site_settings else ''
        languages = site_settings.get_language_codes() if site_settings else ['pt', 'en']

        # Get all pages with their slugs in all languages
        pages_data = []
        for page in Page.objects.filter(is_active=True).order_by('id'):
            page_info = {
                'title': page.title_i18n or {},
                'slug': page.slug_i18n or {},
            }
            pages_data.append(page_info)

        design_guide = site_settings.design_guide if site_settings else ''

        # Get menu items for header/footer context (top-level with children)
        from djangopress.core.models import MenuItem
        menu_items_data = []
        for item in MenuItem.objects.filter(is_active=True, parent__isnull=True).select_related('page').prefetch_related('children', 'children__page').order_by('sort_order', 'id'):
            item_data = {
                'label_i18n': item.label_i18n or {},
                'url': item.url,
                'page_slug': item.page.slug_i18n if item.page else {},
                'children': [],
            }
            for child in item.children.filter(is_active=True).order_by('sort_order', 'id'):
                item_data['children'].append({
                    'label_i18n': child.label_i18n or {},
                    'url': child.url,
                    'page_slug': child.page.slug_i18n if child.page else {},
                })
            menu_items_data.append(item_data)

        # Build prompt for global section
        notify("build_prompt", "running")
        system_prompt, user_prompt = PromptTemplates.get_global_section_refinement_prompt(
            site_name=site_name,
            site_description=site_description,
            project_briefing=project_briefing,
            languages=languages,
            pages=pages_data,
            existing_section=existing_data,
            user_request=refinement_instructions,
            section_type=section.section_type,
            design_guide=design_guide,
            menu_items=menu_items_data
        )
        notify("build_prompt", "done")

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
        notify("refine_html", "running", model=model)

        from .utils.llm_config import ModelProvider
        config = MODEL_CONFIG.get(model)
        actual_model, provider = self._get_model_info(model)
        action = 'refine_header' if section_key == 'main-header' else 'refine_footer'
        stream_cb = self._make_stream_callback(on_progress, 'refine_html')
        t0 = time.time()
        try:
            if config and config.provider == ModelProvider.GOOGLE:
                response = self.llm.get_completion(
                    messages,
                    tool_name=model,
                    on_stream=stream_cb,
                    max_output_tokens=16384
                )
            else:
                response = self.llm.get_completion(
                    messages,
                    tool_name=model,
                    on_stream=stream_cb,
                    max_tokens=16384
                )
            usage = self._extract_usage(response)
            log_ai_call(
                action=action, model_name=actual_model, provider=provider,
                system_prompt=system_prompt, user_prompt=user_prompt,
                response_text=response.choices[0].message.content,
                duration_ms=int((time.time() - t0) * 1000), **usage,
            )
        except Exception as e:
            log_ai_call(
                action=action, model_name=actual_model, provider=provider,
                system_prompt=system_prompt, user_prompt=user_prompt,
                duration_ms=int((time.time() - t0) * 1000),
                success=False, error_message=str(e),
            )
            raise
        notify("refine_html", "done")

        # Extract and parse response
        notify("templatize_translate", "running")
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
        notify("templatize_translate", "done")

        # Add html_template_i18n to the result for the current language
        result_template_i18n = dict(section.html_template_i18n or {})
        result_template_i18n[current_lang] = refined_data.get('html_template', '')
        refined_data['html_template_i18n'] = result_template_i18n

        print(f"Successfully refined global section: {section_key}")
        notify("complete", "done")
        return refined_data

    def refine_page_with_html(
        self,
        page_id: int = None,
        instructions: str = '',
        section_name: str = None,
        language: str = 'pt',
        model_override: str = None,
        reference_images: list = None,
        conversation_history: str = None,
        handle_images: bool = False,
        on_progress=None,
        content_override: dict = None,
    ) -> Dict:
        """
        Refine a page's HTML content based on user instructions.

        Sends the page's HTML to the LLM for refinement.
        If section_name is provided, the LLM focuses on that specific section.

        Args:
            page_id: ID of the page being refined (optional if content_override provided)
            instructions: User's refinement instructions
            section_name: Optional data-section name to target specific section
            language: Primary language for content (default: 'pt')
            model_override: Override the default model for this request
            content_override: Optional dict with 'html_content_i18n', 'title', 'slug'
                to bypass Page lookup. Used for non-Page content like NewsPost.

        Returns:
            Dictionary with 'html_content_i18n'

        Raises:
            ValueError: If refinement fails
        """
        def notify(step, status, **extra):
            if on_progress:
                try:
                    on_progress({"step": step, "status": status, **extra})
                except Exception:
                    pass

        print(f"\n=== Refining Page ===")
        print(f"Page ID: {page_id}")
        print(f"Instructions: {instructions}")
        print(f"Section: {section_name or 'entire page'}")
        print(f"Language: {language}")

        # Get page or use content_override
        notify("prepare", "running")
        from djangopress.core.models import Page, SiteSettings
        from django.utils.translation import get_language

        page = None
        if content_override:
            # Use provided content instead of loading a Page from DB
            page_title = content_override.get('title', 'Untitled')
            page_slug = content_override.get('slug', '')
            override_html_i18n = content_override.get('html_content_i18n', {})
        else:
            if not page_id:
                raise ValueError("Either page_id or content_override is required")
            try:
                page = Page.objects.get(id=page_id)
            except Page.DoesNotExist:
                raise ValueError(f"Page with ID {page_id} not found")
            page_title = page.default_title
            page_slug = page.default_slug

        # Get site context
        site_settings = SiteSettings.objects.first()
        default_language = site_settings.get_default_language() if site_settings else 'pt'
        site_name = site_settings.get_site_name(default_language) if site_settings else 'Website'
        site_description = site_settings.get_site_description(default_language) if site_settings else ''
        project_briefing = site_settings.get_project_briefing() if site_settings else ''
        languages = site_settings.get_language_codes() if site_settings else ['pt', 'en']
        model = model_override or self.model_name

        design_guide = site_settings.design_guide if site_settings else ''

        # Build available pages list for inter-page linking
        pages_data = []
        for p in Page.objects.filter(is_active=True).order_by('id'):
            pages_data.append({'title': p.title_i18n or {}, 'slug': p.slug_i18n or {}})

        # Prepare the refinement instructions with section targeting
        targeted_instructions = instructions
        if section_name:
            targeted_instructions = f"Focus on the <section data-section=\"{section_name}\"> section. {instructions}"

        # --- Read current HTML from html_content_i18n with fallback ---
        current_lang = default_language  # get_language() unreliable in AJAX context
        if content_override:
            html_i18n = override_html_i18n
            clean_html = html_i18n.get(current_lang) or html_i18n.get(default_language) or ''
        else:
            html_i18n = page.html_content_i18n or {}
            clean_html = html_i18n.get(current_lang) or html_i18n.get(default_language) or ''
        print(f"Reading HTML from html_content_i18n[{current_lang}] ({len(clean_html)} chars)")
        notify("prepare", "done")

        # --- Step 1: Refine the clean HTML ---
        print(f"\n--- Step 1: Refine HTML in {default_language.upper()} ---")

        # Pass 1: Select relevant component skills
        notify("component_selection", "running")
        selected_components = ComponentRegistry.select_components(
            user_request=targeted_instructions,
            existing_html=clean_html,
            llm=self.llm,
        )
        component_references = ComponentRegistry.get_references(selected_components)
        notify("component_selection", "done")

        if conversation_history:
            system_prompt, user_prompt = PromptTemplates.get_chat_refinement_html_prompt(
                site_name=site_name,
                site_description=site_description,
                project_briefing=project_briefing,
                default_language=default_language,
                page_html=clean_html,
                user_request=targeted_instructions,
                page_title=page_title,
                page_slug=page_slug,
                design_guide=design_guide,
                has_reference_images=bool(reference_images),
                conversation_history=conversation_history,
                handle_images=handle_images,
                pages=pages_data,
                languages=languages,
                component_references=component_references,
            )
        else:
            system_prompt, user_prompt = PromptTemplates.get_page_refinement_html_prompt(
                site_name=site_name,
                site_description=site_description,
                project_briefing=project_briefing,
                default_language=default_language,
                page_html=clean_html,
                user_request=targeted_instructions,
                page_title=page_title,
                page_slug=page_slug,
                design_guide=design_guide,
                has_reference_images=bool(reference_images),
                handle_images=handle_images,
                pages=pages_data,
                languages=languages,
                component_references=component_references,
            )

        # Debug output
        system_token_estimate = len(system_prompt.split()) * 1.3
        user_token_estimate = len(user_prompt.split()) * 1.3
        total_token_estimate = system_token_estimate + user_token_estimate

        print(f"REFINEMENT PROMPT (≈{int(total_token_estimate)} tokens)")

        notify("refine_html", "running", model=model)
        actual_model, provider_str = self._get_model_info(model)
        log_action = 'chat_refine' if conversation_history else 'refine_page'
        t0 = time.time()
        try:
            if reference_images:
                # Use vision call with images — combine system + user prompt
                print(f"Using vision call with {len(reference_images)} reference image(s)")
                combined_prompt = system_prompt + "\n\n" + user_prompt
                response = self.llm.get_vision_completion(
                    prompt=combined_prompt,
                    images=reference_images,
                    tool_name=model
                )
            else:
                messages = [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt}
                ]
                stream_cb = self._make_stream_callback(on_progress, 'refine_html')
                response = self.llm.get_completion(messages, tool_name=model, on_stream=stream_cb)

            usage = self._extract_usage(response)
            log_ai_call(
                action=log_action, model_name=actual_model, provider=provider_str,
                system_prompt=system_prompt, user_prompt=user_prompt,
                response_text=response.choices[0].message.content,
                duration_ms=int((time.time() - t0) * 1000),
                page=page, section_name=section_name or '', **usage,
            )
        except Exception as e:
            log_ai_call(
                action=log_action, model_name=actual_model, provider=provider_str,
                system_prompt=system_prompt, user_prompt=user_prompt,
                duration_ms=int((time.time() - t0) * 1000),
                page=page, section_name=section_name or '',
                success=False, error_message=str(e),
            )
            raise

        refined_html = self._extract_html_from_response(response.choices[0].message.content)

        if not refined_html or len(refined_html.strip()) < 50:
            raise ValueError("Step 1 returned empty or too-short HTML")

        print(f"Step 1 produced {len(refined_html)} chars of refined HTML")
        notify("refine_html", "done", chars=len(refined_html))

        # Save refined HTML to html_content_i18n for current language
        if content_override:
            result_html_i18n = dict(override_html_i18n)
        else:
            result_html_i18n = dict(page.html_content_i18n or {})
        result_html_i18n[current_lang] = refined_html

        print(f"Successfully refined page")
        notify("complete", "done")
        return {
            'html_content_i18n': result_html_i18n,
        }

    def refine_section_only(
        self,
        page_id: int,
        section_name: str,
        instructions: str,
        conversation_history: list = None,
        multi_option: bool = False,
        model_override: str = None,
        skip_component_selection: bool = False,
        skip_briefing: bool = False,
        skip_pages_list: bool = False,
        skip_design_guide: bool = False,
        reference_images: list = None,
        on_progress=None,
    ) -> Dict:
        """
        Refine a single section without saving to DB.
        Returns the section's html_template and content (translations).

        Args:
            page_id: ID of the page
            section_name: data-section attribute value
            instructions: User's refinement instructions
            conversation_history: List of {role, content} dicts for chat context
            model_override: Override the default model
            on_progress: Optional callback for progress events

        Returns:
            Dict with 'html_template', 'content', and 'assistant_message'
        """
        def notify(step, status, **extra):
            if on_progress:
                try:
                    on_progress({"step": step, "status": status, **extra})
                except Exception:
                    pass

        from djangopress.core.models import Page, SiteSettings
        from django.utils.translation import get_language
        from bs4 import BeautifulSoup

        print(f"\n=== Refining Section Only ===")
        print(f"Page ID: {page_id}, Section: {section_name}")
        print(f"Instructions: {instructions}")

        notify("prepare", "running")
        try:
            page = Page.objects.get(id=page_id)
        except Page.DoesNotExist:
            raise ValueError(f"Page with ID {page_id} not found")

        site_settings = SiteSettings.objects.first()
        default_language = site_settings.get_default_language() if site_settings else 'pt'
        site_name = site_settings.get_site_name(default_language) if site_settings else 'Website'
        site_description = site_settings.get_site_description(default_language) if site_settings else ''
        project_briefing = '' if skip_briefing else (site_settings.get_project_briefing() if site_settings else '')
        languages = site_settings.get_language_codes() if site_settings else ['pt', 'en']
        design_guide = '' if skip_design_guide else (site_settings.design_guide if site_settings else '')
        model = model_override or self.model_name

        page_title = page.default_title
        page_slug = page.default_slug

        # Build pages list for inter-page linking context
        pages_data = []
        if not skip_pages_list:
            for p in Page.objects.filter(is_active=True).order_by('id'):
                pages_data.append({'title': p.title_i18n or {}, 'slug': p.slug_i18n or {}})

        # Read current HTML from html_content_i18n with fallback
        current_lang = default_language  # get_language() unreliable in AJAX context
        html_i18n = page.html_content_i18n or {}
        clean_html = html_i18n.get(current_lang) or html_i18n.get(default_language) or ''
        clean_html = self._strip_legacy_attrs(clean_html)
        print(f"Reading HTML from html_content_i18n[{current_lang}] ({len(clean_html)} chars)")
        notify("prepare", "done")

        # Build conversation history string for prompt
        history_text = ''
        if conversation_history:
            for msg in conversation_history:
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                if role == 'user':
                    history_text += f"\nUser: {content}"
                elif role == 'assistant':
                    history_text += f"\nAssistant: {content}"

        # Step 1: Refine section HTML (section-only prompt — LLM returns just the target section)
        print(f"\n--- Step 1: Refine section '{section_name}' in {default_language.upper()} ---")

        # Pass 1: Select relevant component skills
        notify("component_selection", "running")
        component_references = ''
        if not skip_component_selection:
            selected_components = ComponentRegistry.select_components(
                user_request=instructions,
                existing_html=clean_html,
                llm=self.llm,
            )
            component_references = ComponentRegistry.get_references(selected_components)
        notify("component_selection", "done")

        system_prompt, user_prompt = PromptTemplates.get_section_refinement_prompt(
            site_name=site_name,
            site_description=site_description,
            project_briefing=project_briefing,
            default_language=default_language,
            full_page_html=clean_html,
            section_name=section_name,
            user_request=instructions,
            page_title=page_title,
            page_slug=page_slug,
            design_guide=design_guide,
            conversation_history=history_text,
            pages=pages_data,
            languages=languages,
            multi_option=multi_option,
            component_references=component_references,
            include_component_index=not skip_component_selection,
            has_reference_images=bool(reference_images),
        )

        notify("refine_html", "running", model=model)
        actual_model, provider_str = self._get_model_info(model)
        t0 = time.time()
        try:
            if reference_images:
                print(f"Using vision call with {len(reference_images)} reference image(s)")
                combined_prompt = system_prompt + "\n\n" + user_prompt
                response = self.llm.get_vision_completion(
                    prompt=combined_prompt,
                    images=reference_images,
                    tool_name=model
                )
            else:
                messages = [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt}
                ]
                stream_cb = self._make_stream_callback(on_progress, 'refine_html')
                response = self.llm.get_completion(messages, tool_name=model, on_stream=stream_cb)
            usage = self._extract_usage(response)
            log_ai_call(
                action='refine_section', model_name=actual_model, provider=provider_str,
                system_prompt=system_prompt, user_prompt=user_prompt,
                response_text=response.choices[0].message.content,
                duration_ms=int((time.time() - t0) * 1000),
                page=page, section_name=section_name, **usage,
            )
        except Exception as e:
            log_ai_call(
                action='refine_section', model_name=actual_model, provider=provider_str,
                system_prompt=system_prompt, user_prompt=user_prompt,
                duration_ms=int((time.time() - t0) * 1000),
                page=page, section_name=section_name,
                success=False, error_message=str(e),
            )
            raise

        refined_html = self._extract_html_from_response(response.choices[0].message.content)

        if not refined_html or len(refined_html.strip()) < 50:
            raise ValueError("Step 1 returned empty or too-short HTML")

        print(f"Step 1 produced {len(refined_html)} chars of refined section HTML")
        notify("refine_html", "done", chars=len(refined_html))

        if multi_option:
            # Multi-option: split into options, skip templatize, return raw HTML
            notify("processing_options", "running")
            options = self._split_multi_options(refined_html)
            validated = []
            for i, opt_html in enumerate(options):
                opt_soup = BeautifulSoup(opt_html, 'html.parser')
                opt_section = opt_soup.find('section', attrs={'data-section': section_name})
                if opt_section:
                    validated.append({'html': str(opt_section)})
                elif opt_soup.find('section'):
                    validated.append({'html': str(opt_soup.find('section'))})
                else:
                    validated.append({'html': opt_html})
                print(f"  Option {i+1}: {len(validated[-1]['html'])} chars")

            notify("processing_options", "done")
            notify("complete", "done")
            assistant_message = f"Here are {len(validated)} variations for the {section_name} section."
            return {
                'options': validated,
                'assistant_message': assistant_message,
            }

        # Single option — validate and return as 1-element options list
        # (templatize happens in apply-option, keeping the flow consistent)
        soup = BeautifulSoup(refined_html, 'html.parser')
        section_el = soup.find('section', attrs={'data-section': section_name})

        if section_el:
            section_html = str(section_el)
        else:
            all_sections = soup.find_all('section')
            if len(all_sections) == 1:
                section_html = str(all_sections[0])
            elif len(all_sections) > 1:
                print(f"WARNING: LLM returned {len(all_sections)} sections, extracting target")
                target = soup.find('section', attrs={'data-section': section_name})
                if target:
                    section_html = str(target)
                else:
                    raise ValueError(f"Section '{section_name}' not found in AI response with {len(all_sections)} sections")
            else:
                section_html = refined_html

        print(f"Section '{section_name}': {len(section_html)} chars")

        notify("complete", "done")
        return {
            'options': [{'html': section_html}],
            'assistant_message': f"Here is the refined {section_name} section.",
        }

    def generate_section(
        self,
        page_id: int,
        insert_after: str,
        instructions: str,
        conversation_history: list = None,
        model_override: str = None
    ) -> Dict:
        """
        Generate a brand new section (3 variations) to insert into a page.
        Returns raw HTML options (no templatization — that happens when the user picks one).

        Args:
            page_id: ID of the page to add the section to
            insert_after: data-section value of the section to insert after (empty/None = top of page)
            instructions: User's description of what the new section should be
            conversation_history: List of {role, content} dicts for chat context
            model_override: Override the default model

        Returns:
            Dict with 'options' (list of {'html': str}) and 'assistant_message'
        """
        from djangopress.core.models import Page, SiteSettings
        from django.utils.translation import get_language
        from bs4 import BeautifulSoup

        print(f"\n=== Generating New Section ===")
        print(f"Page ID: {page_id}, Insert after: {insert_after or '(top of page)'}")
        print(f"Instructions: {instructions}")

        try:
            page = Page.objects.get(id=page_id)
        except Page.DoesNotExist:
            raise ValueError(f"Page with ID {page_id} not found")

        site_settings = SiteSettings.objects.first()
        default_language = site_settings.get_default_language() if site_settings else 'pt'
        site_name = site_settings.get_site_name(default_language) if site_settings else 'Website'
        site_description = site_settings.get_site_description(default_language) if site_settings else ''
        project_briefing = site_settings.get_project_briefing() if site_settings else ''
        languages = site_settings.get_language_codes() if site_settings else ['pt', 'en']
        design_guide = site_settings.design_guide if site_settings else ''
        model = model_override or self.model_name

        page_title = page.default_title
        page_slug = page.default_slug

        # Build pages list for inter-page linking context
        pages_data = []
        for p in Page.objects.filter(is_active=True).order_by('id'):
            pages_data.append({'title': p.title_i18n or {}, 'slug': p.slug_i18n or {}})

        # Read current HTML from html_content_i18n with fallback
        current_lang = default_language  # get_language() unreliable in AJAX context
        html_i18n = page.html_content_i18n or {}
        clean_html = html_i18n.get(current_lang) or html_i18n.get(default_language) or ''
        clean_html = self._strip_legacy_attrs(clean_html)
        print(f"Reading HTML from html_content_i18n[{current_lang}] ({len(clean_html)} chars)")

        # Build conversation history string for prompt
        history_text = ''
        if conversation_history:
            for msg in conversation_history:
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                if role == 'user':
                    history_text += f"\nUser: {content}"
                elif role == 'assistant':
                    history_text += f"\nAssistant: {content}"

        # Generate new section HTML (3 variations)
        print(f"\n--- Generating new section (insert after '{insert_after or 'top'}') in {default_language.upper()} ---")

        # Pass 1: Select relevant component skills
        selected_components = ComponentRegistry.select_components(
            user_request=instructions,
            existing_html=clean_html,
            llm=self.llm,
        )
        component_references = ComponentRegistry.get_references(selected_components)

        system_prompt, user_prompt = PromptTemplates.get_section_generation_prompt(
            site_name=site_name,
            site_description=site_description,
            project_briefing=project_briefing,
            default_language=default_language,
            full_page_html=clean_html,
            insert_after=insert_after,
            user_request=instructions,
            page_title=page_title,
            page_slug=page_slug,
            design_guide=design_guide,
            conversation_history=history_text,
            pages=pages_data,
            languages=languages,
            component_references=component_references,
        )

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ]

        actual_model, provider_str = self._get_model_info(model)
        t0 = time.time()
        try:
            response = self.llm.get_completion(messages, tool_name=model)
            usage = self._extract_usage(response)
            log_ai_call(
                action='generate_section', model_name=actual_model, provider=provider_str,
                system_prompt=system_prompt, user_prompt=user_prompt,
                response_text=response.choices[0].message.content,
                duration_ms=int((time.time() - t0) * 1000),
                page=page, section_name=f'new_after_{insert_after or "top"}', **usage,
            )
        except Exception as e:
            log_ai_call(
                action='generate_section', model_name=actual_model, provider=provider_str,
                system_prompt=system_prompt, user_prompt=user_prompt,
                duration_ms=int((time.time() - t0) * 1000),
                page=page, section_name=f'new_after_{insert_after or "top"}',
                success=False, error_message=str(e),
            )
            raise

        generated_html = self._extract_html_from_response(response.choices[0].message.content)

        if not generated_html or len(generated_html.strip()) < 50:
            raise ValueError("AI returned empty or too-short HTML for new section")

        print(f"AI produced {len(generated_html)} chars of new section HTML")

        # Split into options and validate each one
        options = self._split_multi_options(generated_html)
        validated = []
        for i, opt_html in enumerate(options):
            opt_soup = BeautifulSoup(opt_html, 'html.parser')
            # Don't filter by specific data-section name — the LLM creates the name
            section_tag = opt_soup.find('section')
            if section_tag:
                validated.append({'html': str(section_tag)})
            else:
                validated.append({'html': opt_html})
            print(f"  Option {i+1}: {len(validated[-1]['html'])} chars")

        assistant_message = f"Here are {len(validated)} design options for the new section."
        return {
            'options': validated,
            'assistant_message': assistant_message,
        }

    def refine_element_only(
        self,
        page_id: int,
        selector: str,
        instructions: str,
        conversation_history: list = None,
        multi_option: bool = False,
        model_override: str = None,
        skip_component_selection: bool = False,
        skip_briefing: bool = False,
        skip_pages_list: bool = False,
        skip_design_guide: bool = False,
        on_progress=None,
    ) -> Dict:
        """
        Refine a single element within a section without saving to DB.
        Returns the element's html_template and content (translations).
        """
        def notify(step, status, **extra):
            if on_progress:
                try:
                    on_progress({"step": step, "status": status, **extra})
                except Exception:
                    pass

        from djangopress.core.models import Page, SiteSettings
        from django.utils.translation import get_language
        from bs4 import BeautifulSoup

        print(f"\n=== Refining Element Only ===")
        print(f"Page ID: {page_id}, Selector: {selector}")
        print(f"Instructions: {instructions}")

        notify("prepare", "running")
        try:
            page = Page.objects.get(id=page_id)
        except Page.DoesNotExist:
            raise ValueError(f"Page with ID {page_id} not found")

        site_settings = SiteSettings.objects.first()
        default_language = site_settings.get_default_language() if site_settings else 'pt'
        site_name = site_settings.get_site_name(default_language) if site_settings else 'Website'
        site_description = site_settings.get_site_description(default_language) if site_settings else ''
        project_briefing = '' if skip_briefing else (site_settings.get_project_briefing() if site_settings else '')
        languages = site_settings.get_language_codes() if site_settings else ['pt', 'en']
        design_guide = '' if skip_design_guide else (site_settings.design_guide if site_settings else '')
        model = model_override or self.model_name

        # Read current HTML from html_content_i18n with fallback
        current_lang = default_language  # get_language() unreliable in AJAX context
        html_i18n = page.html_content_i18n or {}
        clean_html = html_i18n.get(current_lang) or html_i18n.get(default_language) or ''
        clean_html = self._strip_legacy_attrs(clean_html)
        print(f"Reading HTML from html_content_i18n[{current_lang}] ({len(clean_html)} chars)")
        notify("prepare", "done")

        # Find the target element by CSS selector
        soup = BeautifulSoup(clean_html, 'html.parser')
        element_el = soup.select_one(selector)
        if not element_el:
            raise ValueError(f"Element not found for selector: {selector}")

        # Extract parent section for context
        section_el = element_el.find_parent('section', attrs={'data-section': True})
        if not section_el:
            raise ValueError("Element is not inside a data-section")
        section_name = section_el['data-section']

        # Mark the target element for the LLM, then extract HTML
        element_el['data-target'] = 'true'
        section_html = str(section_el)
        element_html = str(element_el)
        del element_el['data-target']  # clean up the soup

        # Build conversation history string for prompt
        history_text = ''
        if conversation_history:
            for msg in conversation_history:
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                if role == 'user':
                    history_text += f"\nUser: {content}"
                elif role == 'assistant':
                    history_text += f"\nAssistant: {content}"

        # Step 1: Refine element HTML
        print(f"\n--- Step 1: Refine element in {default_language.upper()} ---")

        # Pass 1: Select relevant component skills
        notify("component_selection", "running")
        component_references = ''
        if not skip_component_selection:
            selected_components = ComponentRegistry.select_components(
                user_request=instructions,
                existing_html=clean_html,
                llm=self.llm,
            )
            component_references = ComponentRegistry.get_references(selected_components)
        notify("component_selection", "done")

        system_prompt, user_prompt = PromptTemplates.get_element_refinement_prompt(
            site_name=site_name,
            site_description=site_description,
            project_briefing=project_briefing,
            default_language=default_language,
            section_html=section_html,
            section_name=section_name,
            element_html=element_html,
            user_request=instructions,
            design_guide=design_guide,
            conversation_history=history_text,
            multi_option=multi_option,
            component_references=component_references,
            include_component_index=not skip_component_selection,
        )

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ]

        notify("refine_html", "running", model=model)
        actual_model, provider_str = self._get_model_info(model)
        t0 = time.time()
        try:
            response = self.llm.get_completion(messages, tool_name=model)
            usage = self._extract_usage(response)
            log_ai_call(
                action='refine_element', model_name=actual_model, provider=provider_str,
                system_prompt=system_prompt, user_prompt=user_prompt,
                response_text=response.choices[0].message.content,
                duration_ms=int((time.time() - t0) * 1000),
                page=page, section_name=section_name, **usage,
            )
        except Exception as e:
            log_ai_call(
                action='refine_element', model_name=actual_model, provider=provider_str,
                system_prompt=system_prompt, user_prompt=user_prompt,
                duration_ms=int((time.time() - t0) * 1000),
                page=page, section_name=section_name,
                success=False, error_message=str(e),
            )
            raise

        refined_html = self._extract_html_from_response(response.choices[0].message.content)

        if not refined_html or len(refined_html.strip()) < 10:
            raise ValueError("Step 1 returned empty or too-short HTML")

        print(f"Step 1 produced {len(refined_html)} chars of refined element HTML")
        notify("refine_html", "done", chars=len(refined_html))

        if multi_option:
            # Multi-option: split into options, skip templatize, return raw HTML
            notify("processing_options", "running")
            options = self._split_multi_options(refined_html)
            validated = []
            for i, opt_html in enumerate(options):
                opt_soup = BeautifulSoup(opt_html, 'html.parser')
                opt_el = opt_soup.find(attrs={'data-target': 'true'})
                if opt_el:
                    del opt_el['data-target']
                    validated.append({'html': str(opt_el)})
                else:
                    validated.append({'html': opt_html})
                print(f"  Option {i+1}: {len(validated[-1]['html'])} chars")

            notify("processing_options", "done")
            notify("complete", "done")
            assistant_message = f"Here are {len(validated)} variations."
            return {
                'options': validated,
                'assistant_message': assistant_message,
            }

        # Single option — validate and return as 1-element options list
        # (templatize happens in apply-option, keeping the flow consistent)
        result_soup = BeautifulSoup(refined_html, 'html.parser')
        target_el = result_soup.find(attrs={'data-target': 'true'})

        if target_el:
            del target_el['data-target']
            element_result_html = str(target_el)
        else:
            print("WARNING: data-target not found in response, using full response")
            element_result_html = refined_html

        print(f"Refined element: {len(element_result_html)} chars")

        notify("complete", "done")
        return {
            'options': [{'html': element_result_html}],
            'assistant_message': "Here is the refined element.",
        }

    def process_page_images(
        self,
        page_id: int,
        image_decisions: List[Dict],
        languages: List[str] = None,
    ) -> Dict:
        """
        Phase 2: Process image placeholders on a page.

        For each image decision, either pick an existing SiteImage from the
        media library or generate a new one via the LLM, then replace the
        placeholder src in the page HTML and remove the data-image-* attributes.

        Image generation is parallelized (up to 3 concurrent) for performance.

        Args:
            page_id: ID of the page to process
            image_decisions: List of dicts, each containing:
                - image_name: value of data-image-name attribute
                - action: 'library' or 'generate'
                - library_image_id: SiteImage id (when action='library')
                - prompt: generation prompt (when action='generate')
                - aspect_ratio: e.g. '16:9' (when action='generate', optional)
            languages: Language codes for SiteImage i18n fields

        Returns:
            Dict with 'processed', 'failed', and 'report' keys
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from djangopress.core.models import Page, SiteImage, SiteSettings
        from .utils.llm_config import optimize_generated_image, LLMBase as LLMService
        from django.core.files.base import ContentFile
        from django.utils.text import slugify

        print(f"\n=== Processing Page Images ===")
        print(f"Page ID: {page_id}")
        print(f"Decisions: {len(image_decisions)}")

        try:
            page = Page.objects.get(id=page_id)
        except Page.DoesNotExist:
            raise ValueError(f"Page with ID {page_id} not found")

        if not languages:
            site_settings = SiteSettings.objects.first()
            languages = site_settings.get_language_codes() if site_settings else ['pt', 'en']
        else:
            site_settings = SiteSettings.objects.first()

        # Read current HTML from html_content_i18n with fallback
        from django.utils.translation import get_language
        default_language = site_settings.get_default_language() if site_settings else 'pt'
        current_lang = default_language  # get_language() unreliable in AJAX context
        html_i18n = page.html_content_i18n or {}
        html = html_i18n.get(current_lang) or html_i18n.get(default_language) or ''
        print(f"Reading HTML from html_content_i18n[{current_lang}] ({len(html)} chars)")
        processed = []
        failed = []

        # --- Phase 1: Resolve all images (parallel for 'generate' actions) ---
        # Each entry will hold: (decision, new_url) or (decision, error)
        resolved = []

        # Separate decisions by type for optimal parallelism
        generate_decisions = []
        other_decisions = []
        for decision in image_decisions:
            image_name = decision.get('image_name', '')
            image_src = decision.get('image_src', '')
            action = decision.get('action', '')

            if not action or (not image_name and not image_src):
                failed.append({'image_name': image_name or image_src, 'error': 'Missing identifier or action'})
                continue

            if action == 'generate':
                generate_decisions.append(decision)
            else:
                other_decisions.append(decision)

        def _generate_single_image(decision):
            """Generate a single image in a thread — returns (decision, url) or (decision, None, error)."""
            from .utils.llm_config import LLMBase as LLMService, optimize_generated_image
            from djangopress.core.models import SiteImage
            from django.core.files.base import ContentFile
            from django.utils.text import slugify

            image_name = decision.get('image_name', '')
            image_src = decision.get('image_src', '')
            prompt = decision.get('prompt', '')
            aspect_ratio = decision.get('aspect_ratio', '16:9')

            if not prompt:
                return (decision, None, 'Missing prompt')

            image_label = image_name or image_src.split('/')[-1] or 'image'
            print(f"Generating image for '{image_label}': {prompt[:80]}...")

            thread_llm = LLMService()
            result = thread_llm.generate_image(prompt=prompt, aspect_ratio=aspect_ratio)

            if not result.success:
                return (decision, None, result.error or 'Generation failed')

            optimized_bytes = optimize_generated_image(result.image_bytes, max_width=1200, quality=85)

            file_slug = slugify(image_name or image_src.split('/')[-1]) or 'ai-image'
            base_key = f"ai-{file_slug}"
            key = base_key
            counter = 1
            while SiteImage.objects.filter(key=key).exists():
                key = f"{base_key}-{counter}"
                counter += 1

            title_text = (image_name or file_slug).replace('-', ' ').replace('_', ' ').title()
            site_image = SiteImage(
                key=key,
                title_i18n={lang: title_text for lang in languages},
                alt_text_i18n={lang: prompt[:200] for lang in languages},
                tags='ai-generated',
                is_active=True,
            )
            filename = f"{file_slug}.jpg"
            site_image.image.save(filename, ContentFile(optimized_bytes), save=True)
            print(f"Saved generated image: {key} -> {site_image.image.url}")
            return (decision, site_image.image.url, None)

        # Process 'generate' decisions in parallel
        if generate_decisions:
            print(f"Generating {len(generate_decisions)} images in parallel (max 3 workers)...")
            with ThreadPoolExecutor(max_workers=3) as pool:
                futures = {pool.submit(_generate_single_image, d): d for d in generate_decisions}
                for future in as_completed(futures):
                    decision, new_url, error = future.result()
                    if error:
                        failed.append({'image_name': decision.get('image_name', ''), 'error': error})
                    else:
                        resolved.append((decision, new_url))

        # Process non-generate decisions sequentially (library, unsplash — usually fast)
        for decision in other_decisions:
            image_name = decision.get('image_name', '')
            image_src = decision.get('image_src', '')
            action = decision.get('action', '')

            try:
                new_url = None

                if action == 'library':
                    library_image_id = decision.get('library_image_id')
                    if not library_image_id:
                        print(f"Auto-matching library image for '{image_name or image_src}'...")
                        site_settings_obj = SiteSettings.objects.first()
                        default_lang = site_settings_obj.get_default_language() if site_settings_obj else 'pt'
                        library_catalog = self._build_library_catalog(default_lang)
                        if not library_catalog:
                            failed.append({'image_name': image_name, 'error': 'Library is empty — cannot auto-match'})
                            continue
                        # html is already clean (read from html_content_i18n)
                        page_context = html
                        image_context = {
                            'name': image_name,
                            'alt': decision.get('alt', ''),
                            'src': image_src,
                            'prompt': decision.get('prompt', ''),
                        }
                        library_image_id = self._auto_match_library_image(
                            image_context=image_context,
                            library_catalog=library_catalog,
                            page_html=page_context,
                        )
                        if not library_image_id:
                            failed.append({'image_name': image_name, 'error': 'Auto-match found no suitable library image'})
                            continue
                        print(f"Auto-matched to library image ID {library_image_id}")
                    site_image = SiteImage.objects.get(id=library_image_id)
                    new_url = site_image.image.url

                elif action == 'unsplash':
                    from .utils.unsplash import download_photo

                    unsplash_photo_id = decision.get('unsplash_photo_id', '')
                    unsplash_url = decision.get('unsplash_url', '')
                    photographer = decision.get('photographer', '')

                    if not unsplash_photo_id or not unsplash_url:
                        failed.append({'image_name': image_name, 'error': 'Missing Unsplash photo data'})
                        continue

                    print(f"Downloading Unsplash photo '{unsplash_photo_id}' by {photographer}...")
                    image_bytes = download_photo(unsplash_photo_id, unsplash_url)

                    if not image_bytes:
                        failed.append({'image_name': image_name, 'error': 'Failed to download Unsplash photo'})
                        continue

                    optimized_bytes = optimize_generated_image(image_bytes, max_width=1200, quality=85)

                    file_slug = slugify(image_name or image_src.split('/')[-1]) or 'unsplash-image'
                    base_key = f"unsplash-{file_slug}"
                    key = base_key
                    counter = 1
                    while SiteImage.objects.filter(key=key).exists():
                        key = f"{base_key}-{counter}"
                        counter += 1

                    title_text = (image_name or file_slug).replace('-', ' ').replace('_', ' ').title()
                    photographer_tag = f'Photo by {photographer}' if photographer else ''
                    tags = ', '.join(filter(None, ['unsplash', photographer_tag]))

                    site_image = SiteImage(
                        key=key,
                        title_i18n={lang: title_text for lang in languages},
                        alt_text_i18n={lang: title_text for lang in languages},
                        tags=tags,
                        is_active=True,
                    )
                    filename = f"{file_slug}.jpg"
                    site_image.image.save(filename, ContentFile(optimized_bytes), save=True)
                    new_url = site_image.image.url
                    print(f"Saved Unsplash image: {key} -> {new_url}")

                else:
                    failed.append({'image_name': image_name, 'error': f'Unknown action: {action}'})
                    continue

                if new_url:
                    resolved.append((decision, new_url))

            except SiteImage.DoesNotExist:
                failed.append({'image_name': image_name, 'error': 'Library image not found'})
            except Exception as e:
                failed.append({'image_name': image_name, 'error': str(e)})

        # --- Phase 2: Apply all HTML replacements sequentially ---
        for decision, new_url in resolved:
            image_name = decision.get('image_name', '')
            image_src = decision.get('image_src', '')
            action = decision.get('action', '')

            match = None
            if image_name:
                pattern = re.compile(
                    r'(<img\b[^>]*?\bdata-image-name="' + re.escape(image_name) + r'"[^>]*?)(/?>)',
                    re.DOTALL
                )
                match = pattern.search(html)

            if not match and image_src:
                pattern2 = re.compile(
                    r'(<img\b[^>]*?\bsrc="' + re.escape(image_src) + r'"[^>]*?)(/?>)',
                    re.DOTALL
                )
                match = pattern2.search(html)

            if match:
                tag_content = match.group(1)
                tag_close = match.group(2)

                tag_content = re.sub(r'\bsrc="[^"]*"', f'src="{new_url}"', tag_content)
                tag_content = re.sub(r'\s*data-image-prompt="[^"]*"', '', tag_content)
                tag_content = re.sub(r'\s*data-image-name="[^"]*"', '', tag_content)

                html = html[:match.start()] + tag_content + tag_close + html[match.end():]
                processed.append({'image_name': image_name, 'new_url': new_url, 'action': action})
            else:
                failed.append({'image_name': image_name, 'error': 'Image tag not found in HTML'})

            if new_url and image_src:
                bg_pattern = re.compile(
                    r'(background-image\s*:\s*[^;]*?)url\(\s*["\']?' + re.escape(image_src) + r'["\']?\s*\)',
                    re.DOTALL
                )
                html = bg_pattern.sub(
                    lambda m: m.group(1) + f'url("{new_url}")',
                    html
                )

        # Save updated HTML to html_content_i18n
        result_html_i18n = dict(page.html_content_i18n or {})
        result_html_i18n[current_lang] = html
        page.html_content_i18n = result_html_i18n
        page.save()

        print(f"Processed {len(processed)} images, {len(failed)} failed")
        return {
            'processed': processed,
            'failed': failed,
            'report': f"Processed {len(processed)} image(s), {len(failed)} failed"
        }

    def translate_content_to_language(
        self,
        target_lang: str,
        source_lang: str = None,
    ) -> Dict:
        """
        Bulk-translate all existing Pages and GlobalSections to a new language.

        Uses translate_html to translate per-language HTML directly.

        Args:
            target_lang: Language code to translate into (e.g. 'es')
            source_lang: Source language code (defaults to SiteSettings default)

        Returns:
            Dict with 'translated_pages', 'translated_sections', 'errors'
        """
        from djangopress.core.models import Page, GlobalSection, SiteSettings
        from django.utils.text import slugify

        site_settings = SiteSettings.objects.first()
        if not source_lang:
            source_lang = site_settings.get_default_language() if site_settings else 'pt'

        translated_pages = 0
        translated_sections = 0
        errors = []

        # Translate Pages
        for page in Page.objects.filter(is_active=True):
            try:
                html_i18n = page.html_content_i18n or {}
                source_html = html_i18n.get(source_lang, '')

                if not source_html:
                    continue

                # Skip if target HTML already exists
                if html_i18n.get(target_lang):
                    continue

                translated_html = self.translate_html(source_html, source_lang, target_lang)
                if not page.html_content_i18n:
                    page.html_content_i18n = {}
                page.html_content_i18n[target_lang] = translated_html

                # Translate title
                source_title = (page.title_i18n or {}).get(source_lang, '')
                if source_title and not (page.title_i18n or {}).get(target_lang):
                    title_result = self._translate_key_value_pairs(
                        {'title': source_title}, source_lang, target_lang
                    )
                    if title_result and 'title' in title_result:
                        if not page.title_i18n:
                            page.title_i18n = {}
                        page.title_i18n[target_lang] = title_result['title']

                # Generate slug from translated title
                if not (page.slug_i18n or {}).get(target_lang):
                    source_slug = (page.slug_i18n or {}).get(source_lang, '')
                    if not page.slug_i18n:
                        page.slug_i18n = {}
                    if source_slug == 'home':
                        page.slug_i18n[target_lang] = 'home'
                    elif page.title_i18n.get(target_lang):
                        page.slug_i18n[target_lang] = slugify(page.title_i18n[target_lang])
                    else:
                        page.slug_i18n[target_lang] = source_slug

                page.save()
                translated_pages += 1

            except Exception as e:
                page_title = page.default_title or f'Page {page.id}'
                errors.append(f'Page "{page_title}": {str(e)}')

        # Translate GlobalSections
        for section in GlobalSection.objects.filter(is_active=True):
            try:
                html_i18n = section.html_template_i18n or {}
                source_html = html_i18n.get(source_lang, '')

                if not source_html:
                    continue

                if html_i18n.get(target_lang):
                    continue

                translated_html = self.translate_html(source_html, source_lang, target_lang)
                if not section.html_template_i18n:
                    section.html_template_i18n = {}
                section.html_template_i18n[target_lang] = translated_html
                section.save()
                translated_sections += 1

            except Exception as e:
                errors.append(f'Section "{section.key}": {str(e)}')

        return {
            'translated_pages': translated_pages,
            'translated_sections': translated_sections,
            'errors': errors,
        }

    def _translate_key_value_pairs(
        self,
        source_dict: Dict[str, str],
        source_name: str,
        target_name: str,
    ) -> Optional[Dict[str, str]]:
        """
        Translate a dict of key-value pairs from one language to another using gemini-flash.

        Args:
            source_dict: Dict like {"hero_title": "Welcome", ...}
            source_name: Human-readable source language name
            target_name: Human-readable target language name

        Returns:
            Translated dict with same keys, or None on failure
        """
        prompt = f"""Translate these UI text strings from {source_name} to {target_name}.
Return ONLY a JSON object with the exact same keys and translated values.
Keep the translations natural and fluent — these are website UI strings.

{json.dumps(source_dict, ensure_ascii=False, indent=2)}"""

        messages = [{'role': 'user', 'content': prompt}]

        actual_model, provider = self._get_model_info(get_ai_model('translation'))
        t0 = time.time()
        try:
            response = self.llm.get_completion(messages, tool_name=get_ai_model('translation'))
            usage = self._extract_usage(response)
            content = response.choices[0].message.content
            log_ai_call(
                action='bulk_translate', model_name=actual_model, provider=provider,
                user_prompt=prompt, response_text=content,
                duration_ms=int((time.time() - t0) * 1000), **usage,
            )
            result = self._extract_json_from_response(content)
            if isinstance(result, dict):
                return result
            return None
        except Exception as e:
            log_ai_call(
                action='bulk_translate', model_name=actual_model, provider=provider,
                user_prompt=prompt,
                duration_ms=int((time.time() - t0) * 1000),
                success=False, error_message=str(e),
            )
            raise

    def translate_html(self, html: str, source_lang: str, target_lang: str, model: str = None) -> str:
        """
        Translate HTML content from one language to another.
        LLM only outputs clean HTML -- no JSON, no template variables.

        Args:
            html: The HTML string to translate
            source_lang: Source language code (e.g. 'pt')
            target_lang: Target language code (e.g. 'en')
            model: LLM model to use (default: 'gemini-flash')

        Returns:
            Translated HTML string
        """
        prompt = PromptTemplates.get_html_translation_prompt(
            html=html,
            source_lang=source_lang,
            target_lang=target_lang,
        )
        model = model or get_ai_model('translation')

        messages = [
            {'role': 'user', 'content': prompt}
        ]

        actual_model, provider = self._get_model_info(model)
        t0 = time.time()
        try:
            response = self.llm.get_completion(messages, tool_name=model)
            usage = self._extract_usage(response)
            content = response.choices[0].message.content
            log_ai_call(
                action='translate_html', model_name=actual_model, provider=provider,
                user_prompt=prompt, response_text=content,
                duration_ms=int((time.time() - t0) * 1000), **usage,
            )
            translated_html = self._extract_html_from_response(content)
            return translated_html or content
        except Exception as e:
            log_ai_call(
                action='translate_html', model_name=actual_model, provider=provider,
                user_prompt=prompt,
                duration_ms=int((time.time() - t0) * 1000),
                success=False, error_message=str(e),
            )
            raise

    def bulk_translate_page(self, page, target_languages, model=None):
        """
        Translate a page's per-language HTML to multiple languages.
        Uses the default language HTML as source.

        Args:
            page: Page instance
            target_languages: List of language codes to translate into
            model: LLM model name (defaults to gemini-flash)

        Returns:
            Dict mapping language code -> translated HTML string
        """
        from djangopress.core.models import SiteSettings

        site_settings = SiteSettings.objects.first()
        default_lang = site_settings.get_default_language() if site_settings else 'pt'

        source_html = (page.html_content_i18n or {}).get(default_lang, '')
        if not source_html:
            raise ValueError("No source HTML in default language")

        results = {}
        for lang in target_languages:
            if lang == default_lang:
                continue
            translated = self.translate_html(source_html, default_lang, lang, model=model)
            results[lang] = translated

        return results

    def bulk_translate_section(self, section, target_languages, model=None):
        """
        Translate a GlobalSection's per-language HTML to multiple languages.
        Uses the default language HTML as source.

        Args:
            section: GlobalSection instance
            target_languages: List of language codes to translate into
            model: LLM model name (defaults to gemini-flash)

        Returns:
            Dict mapping language code -> translated HTML string
        """
        from djangopress.core.models import SiteSettings

        site_settings = SiteSettings.objects.first()
        default_lang = site_settings.get_default_language() if site_settings else 'pt'

        source_html = (section.html_template_i18n or {}).get(default_lang, '')
        if not source_html:
            raise ValueError("No source HTML in default language")

        results = {}
        for lang in target_languages:
            if lang == default_lang:
                continue
            translated = self.translate_html(source_html, default_lang, lang, model=model)
            results[lang] = translated

        return results

    @staticmethod
    def _build_library_catalog(default_language: str = 'pt') -> List[Dict]:
        """Build a metadata-only catalog of all active library images."""
        from djangopress.core.models import SiteImage

        catalog = []
        for img in SiteImage.objects.filter(is_active=True).order_by('-id'):
            title = img.title if isinstance(img.title, str) else (img.title_i18n or {}).get(default_language, img.title_i18n.get(list(img.title_i18n.keys())[0], '')) if img.title_i18n else ''
            alt_text = img.alt_text if isinstance(img.alt_text, str) else (img.alt_text_i18n or {}).get(default_language, '') if hasattr(img, 'alt_text_i18n') and img.alt_text_i18n else ''
            catalog.append({
                'id': img.id,
                'title': title,
                'alt_text': alt_text,
                'key': img.key or '',
                'tags': img.tags or '',
                'description': img.description or '',
            })
        return catalog

    def _auto_match_library_image(
        self,
        image_context: Dict,
        library_catalog: List[Dict],
        page_html: str = '',
    ) -> Optional[int]:
        """
        Use Gemini Flash to pick the best library image for a given image slot.

        Args:
            image_context: Dict with name, alt, src, prompt
            library_catalog: Library catalog from _build_library_catalog()
            page_html: De-templatized page HTML for context

        Returns:
            SiteImage ID of the best match, or None if no match
        """
        if not library_catalog:
            return None

        system_prompt, user_prompt = PromptTemplates.get_library_auto_match_prompt(
            image_context=image_context,
            library_catalog=library_catalog,
            page_context=page_html,
        )

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]

        actual_model, provider = self._get_model_info(get_ai_model('image_analysis'))
        t0 = time.time()
        try:
            response = self.llm.get_completion(messages, tool_name=get_ai_model('image_analysis'))
            usage = self._extract_usage(response)
            content = response.choices[0].message.content
            log_ai_call(
                action='auto_match_library', model_name=actual_model, provider=provider,
                system_prompt=system_prompt, user_prompt=user_prompt,
                response_text=content,
                duration_ms=int((time.time() - t0) * 1000), **usage,
            )
            result = self._extract_json_from_response(content)
            if isinstance(result, dict):
                image_id = result.get('image_id')
                if image_id is not None:
                    return int(image_id)
            return None
        except Exception as e:
            log_ai_call(
                action='auto_match_library', model_name=actual_model, provider=provider,
                system_prompt=system_prompt, user_prompt=user_prompt,
                duration_ms=int((time.time() - t0) * 1000),
                success=False, error_message=str(e),
            )
            print(f"Auto-match failed: {e}")
            return None

    def analyze_page_images(
        self,
        page_id: int,
        images: List[Dict],
        model_override: str = None
    ) -> List[Dict]:
        """
        Analyze page images and suggest generation prompts + library matches.

        Args:
            page_id: ID of the page
            images: List of dicts with index, src, alt, name
            model_override: Override the default model

        Returns:
            List of suggestion dicts with index, prompt, aspect_ratio, library_matches
        """
        from djangopress.core.models import Page, SiteSettings, SiteImage

        print(f"\n=== Analyzing Page Images ===")
        print(f"Page ID: {page_id}")
        print(f"Images: {len(images)}")

        try:
            page = Page.objects.get(id=page_id)
        except Page.DoesNotExist:
            raise ValueError(f"Page with ID {page_id} not found")

        site_settings = SiteSettings.objects.first()
        default_language = site_settings.get_default_language() if site_settings else 'pt'
        site_name = site_settings.get_site_name(default_language) if site_settings else 'Website'
        project_briefing = site_settings.get_project_briefing() if site_settings else ''
        design_guide = site_settings.design_guide if site_settings else ''

        # Read current HTML from html_content_i18n with fallback
        from django.utils.translation import get_language
        current_lang = default_language  # get_language() unreliable in AJAX context
        html_i18n = page.html_content_i18n or {}
        clean_html = html_i18n.get(current_lang) or html_i18n.get(default_language) or ''
        clean_html = self._strip_legacy_attrs(clean_html)
        print(f"Reading HTML from html_content_i18n[{current_lang}] ({len(clean_html)} chars)")

        # Build library catalog (metadata only, no URLs)
        library_catalog = self._build_library_catalog(default_language)

        page_title = page.default_title or page.default_slug or 'Untitled'

        # Build prompt
        system_prompt, user_prompt = PromptTemplates.get_image_analysis_prompt(
            site_name=site_name,
            project_briefing=project_briefing,
            design_guide=design_guide,
            page_title=page_title,
            page_html=clean_html,
            images=images,
            library_catalog=library_catalog,
        )

        # Always use a fast model for image analysis — sufficient for prompt suggestions
        model = get_ai_model('image_analysis')
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ]

        actual_model, provider_str = self._get_model_info(model)
        t0 = time.time()
        try:
            response = self.llm.get_completion(messages, tool_name=model)
            usage = self._extract_usage(response)
            log_ai_call(
                action='analyze_images', model_name=actual_model, provider=provider_str,
                system_prompt=system_prompt, user_prompt=user_prompt,
                response_text=response.choices[0].message.content,
                duration_ms=int((time.time() - t0) * 1000), page=page, **usage,
            )
        except Exception as e:
            log_ai_call(
                action='analyze_images', model_name=actual_model, provider=provider_str,
                system_prompt=system_prompt, user_prompt=user_prompt,
                duration_ms=int((time.time() - t0) * 1000), page=page,
                success=False, error_message=str(e),
            )
            raise

        content = response.choices[0].message.content
        suggestions = self._extract_json_from_response(content)

        # Ensure it's a list
        if isinstance(suggestions, dict):
            for key in ('suggestions', 'images', 'results'):
                if key in suggestions and isinstance(suggestions[key], list):
                    suggestions = suggestions[key]
                    break
            else:
                suggestions = [suggestions]

        # Validate library IDs
        valid_ids = set(SiteImage.objects.filter(is_active=True).values_list('id', flat=True))
        for suggestion in suggestions:
            matches = suggestion.get('library_matches', [])
            suggestion['library_matches'] = [mid for mid in matches if mid in valid_ids]

        print(f"Generated {len(suggestions)} image suggestions")
        return suggestions

    def describe_images(self, image_ids: List[int], languages: List[str] = None) -> List[Dict]:
        """
        Use Gemini Flash vision to generate descriptions for media library images.
        Also suggests title and alt_text if they're empty.

        Args:
            image_ids: List of SiteImage IDs to describe
            languages: List of language codes for title/alt_text suggestions

        Returns:
            List of result dicts with id, description, title_i18n, alt_text_i18n, status
        """
        from djangopress.core.models import SiteImage, SiteSettings
        import mimetypes

        site_settings = SiteSettings.objects.first()
        if not languages:
            languages = [lang[0] for lang in (site_settings.get_enabled_languages() if site_settings else [('en', 'English')])]

        default_language = site_settings.get_default_language() if site_settings else 'en'
        site_context = ''
        if site_settings:
            site_name = site_settings.get_site_name(default_language)
            briefing = site_settings.get_project_briefing() or ''
            if site_name:
                site_context = f"This image belongs to the website: {site_name}."
            if briefing:
                site_context += f"\nSite context: {briefing[:500]}"

        images = SiteImage.objects.filter(id__in=image_ids)
        results = []

        for img in images:
            try:
                # Read image bytes
                img.image.open('rb')
                image_bytes = img.image.read()
                img.image.close()

                # Determine MIME type
                mime_type = mimetypes.guess_type(img.image.name)[0] or 'image/jpeg'

                # Check which fields need filling
                has_title = bool(img.title_i18n and any(v for v in img.title_i18n.values()))
                has_alt = bool(img.alt_text_i18n and any(v for v in img.alt_text_i18n.values()))

                lang_list = ', '.join(languages)
                prompt_parts = [
                    "Analyze this image and provide:",
                    "",
                    "1. **description**: A rich semantic description (2-3 sentences) covering: subject matter, visual style, mood/atmosphere, colors, and what type of website section it would suit (hero, about, team, services, gallery, testimonial, contact, etc.).",
                ]
                if not has_title:
                    prompt_parts.append(f"2. **titles**: A short, descriptive title (3-6 words) for each language: {lang_list}")
                if not has_alt:
                    prompt_parts.append(f"3. **alt_texts**: Accessible alt text (1 sentence) for each language: {lang_list}")

                if site_context:
                    prompt_parts.append(f"\nContext: {site_context}")

                prompt_parts.append("\nRespond in valid JSON only, no markdown fences:")

                json_example = '{"description": "..."'
                if not has_title:
                    json_example += ', "titles": {"' + '": "...", "'.join(languages) + '": "..."}'
                if not has_alt:
                    json_example += ', "alt_texts": {"' + '": "...", "'.join(languages) + '": "..."}'
                json_example += '}'
                prompt_parts.append(json_example)

                prompt = '\n'.join(prompt_parts)

                # Call vision model for image description
                actual_model, provider_str = self._get_model_info(get_ai_model('image_analysis'))
                t0 = time.time()
                response = self.llm.get_vision_completion(
                    prompt=prompt,
                    file_bytes=image_bytes,
                    file_mime_type=mime_type,
                    tool_name=get_ai_model('image_analysis'),
                )

                # Parse response
                content = response.content if hasattr(response, 'content') else response.choices[0].message.content
                log_ai_call(
                    action='describe_image', model_name=actual_model, provider=provider_str,
                    system_prompt='', user_prompt=prompt,
                    response_text=content,
                    duration_ms=int((time.time() - t0) * 1000),
                    prompt_tokens=getattr(getattr(response, 'usage', None), 'prompt_tokens', 0) or 0,
                    completion_tokens=getattr(getattr(response, 'usage', None), 'completion_tokens', 0) or 0,
                    total_tokens=getattr(getattr(response, 'usage', None), 'total_tokens', 0) or 0,
                )
                data = self._extract_json_from_response(content)

                description = data.get('description', '') if isinstance(data, dict) else ''

                # Save description
                img.description = description

                # Fill empty titles
                if not has_title and isinstance(data.get('titles'), dict):
                    title_i18n = img.title_i18n if isinstance(img.title_i18n, dict) else {}
                    for lang_code in languages:
                        if lang_code not in title_i18n or not title_i18n[lang_code]:
                            title_i18n[lang_code] = data['titles'].get(lang_code, '')
                    img.title_i18n = title_i18n

                # Fill empty alt texts
                if not has_alt and isinstance(data.get('alt_texts'), dict):
                    alt_i18n = img.alt_text_i18n if isinstance(img.alt_text_i18n, dict) else {}
                    for lang_code in languages:
                        if lang_code not in alt_i18n or not alt_i18n[lang_code]:
                            alt_i18n[lang_code] = data['alt_texts'].get(lang_code, '')
                    img.alt_text_i18n = alt_i18n

                img.save()

                result = {
                    'id': img.id,
                    'description': description,
                    'title_i18n': img.title_i18n,
                    'alt_text_i18n': img.alt_text_i18n,
                    'status': 'ok',
                }
                results.append(result)
                print(f"  Described image #{img.id}: {description[:80]}...")

            except Exception as e:
                print(f"  Error describing image #{img.id}: {e}")
                results.append({
                    'id': img.id,
                    'status': 'error',
                    'error': str(e),
                })

        return results

    @staticmethod
    def _build_design_system_dict(site_settings) -> Dict:
        """Build a dict of design tokens from SiteSettings for consistency analysis."""
        ds = {}
        if not site_settings:
            return ds

        ds['colors'] = {
            'primary': getattr(site_settings, 'primary_color', '') or '',
            'secondary': getattr(site_settings, 'secondary_color', '') or '',
            'accent': getattr(site_settings, 'accent_color', '') or '',
            'background': getattr(site_settings, 'background_color', '') or '',
            'text': getattr(site_settings, 'text_color', '') or '',
            'heading': getattr(site_settings, 'heading_color', '') or '',
        }

        ds['typography'] = {
            'heading_font': getattr(site_settings, 'heading_font', '') or '',
            'body_font': getattr(site_settings, 'body_font', '') or '',
        }
        for level in range(1, 7):
            font = getattr(site_settings, f'h{level}_font', '') or ''
            size = getattr(site_settings, f'h{level}_size', '') or ''
            if font or size:
                ds['typography'][f'h{level}'] = {'font': font, 'size': size}

        ds['layout'] = {
            'container_width': getattr(site_settings, 'container_width', '') or '',
            'border_radius': getattr(site_settings, 'border_radius_preset', '') or '',
            'spacing': getattr(site_settings, 'spacing_scale', '') or '',
            'shadow': getattr(site_settings, 'shadow_preset', '') or '',
        }

        ds['buttons'] = {
            'style': getattr(site_settings, 'button_style', '') or '',
            'size': getattr(site_settings, 'button_size', '') or '',
            'primary': {
                'bg': getattr(site_settings, 'primary_button_bg', '') or '',
                'text': getattr(site_settings, 'primary_button_text', '') or '',
                'hover': getattr(site_settings, 'primary_button_hover', '') or '',
                'border': getattr(site_settings, 'primary_button_border', '') or '',
            },
            'secondary': {
                'bg': getattr(site_settings, 'secondary_button_bg', '') or '',
                'text': getattr(site_settings, 'secondary_button_text', '') or '',
                'hover': getattr(site_settings, 'secondary_button_hover', '') or '',
                'border': getattr(site_settings, 'secondary_button_border', '') or '',
            },
        }

        return ds

    def analyze_design_consistency(
        self,
        custom_rules: str = '',
        model_override: str = None,
        on_progress=None,
    ) -> List[Dict]:
        """
        Analyze all pages and GlobalSections for design inconsistencies.

        Args:
            custom_rules: Optional user-defined rules
            model_override: Override the default model
            on_progress: Progress callback

        Returns:
            List of page/section analysis dicts with issues
        """
        def notify(step, status, **extra):
            if on_progress:
                try:
                    on_progress({"step": step, "status": status, **extra})
                except Exception:
                    pass

        from djangopress.core.models import SiteSettings, Page, GlobalSection

        notify("analyzing", "running")

        site_settings = SiteSettings.objects.first()
        default_lang = site_settings.get_default_language() if site_settings else 'pt'

        # Build design system dict
        design_system = self._build_design_system_dict(site_settings)
        design_guide = site_settings.design_guide if site_settings else ''

        # Collect pages HTML
        pages_html = []
        for page in Page.objects.filter(is_active=True).order_by('sort_order', 'id'):
            html_i18n = page.html_content_i18n or {}
            html = html_i18n.get(default_lang, '')
            if html:
                pages_html.append({
                    'id': page.id,
                    'title': page.get_title(default_lang) or page.default_title or f'Page {page.id}',
                    'html': html,
                })

        # Collect GlobalSections HTML
        sections_html = []
        for section in GlobalSection.objects.filter(is_active=True):
            html_i18n = section.html_template_i18n or {}
            html = html_i18n.get(default_lang, '')
            if html:
                sections_html.append({
                    'key': section.key,
                    'name': section.name or section.key,
                    'html': html,
                })

        if not pages_html and not sections_html:
            notify("analyzing", "done")
            return []

        notify("analyzing", "running", pages=len(pages_html), sections=len(sections_html))

        # Build prompt
        system_prompt, user_prompt = PromptTemplates.get_consistency_analysis_prompt(
            design_system=design_system,
            design_guide=design_guide,
            pages_html=pages_html,
            sections_html=sections_html,
            custom_rules=custom_rules,
        )

        model = model_override or get_ai_model('consistency')
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]

        actual_model, provider = self._get_model_info(model)
        stream_cb = self._make_stream_callback(on_progress, 'analyzing')
        t0 = time.time()
        try:
            response = self.llm.get_completion(messages, tool_name=model, on_stream=stream_cb)
            usage = self._extract_usage(response)
            content = response.choices[0].message.content
            log_ai_call(
                action='consistency_analysis', model_name=actual_model, provider=provider,
                system_prompt=system_prompt, user_prompt=user_prompt,
                response_text=content,
                duration_ms=int((time.time() - t0) * 1000), **usage,
            )
        except Exception as e:
            log_ai_call(
                action='consistency_analysis', model_name=actual_model, provider=provider,
                system_prompt=system_prompt, user_prompt=user_prompt,
                duration_ms=int((time.time() - t0) * 1000),
                success=False, error_message=str(e),
            )
            raise

        report = self._extract_json_from_response(content)

        # Ensure it's a list
        if isinstance(report, dict):
            for key in ('pages', 'results', 'report'):
                if key in report and isinstance(report[key], list):
                    report = report[key]
                    break
            else:
                report = [report]

        notify("analyzing", "done", total_issues=sum(len(p.get('issues', [])) for p in report))
        return report

    def fix_design_consistency(
        self,
        page_id: int = None,
        section_key: str = None,
        issues: list = None,
        custom_rules: str = '',
        model_override: str = None,
        on_progress=None,
    ) -> Dict:
        """
        Fix design inconsistencies on a single page or GlobalSection.

        Args:
            page_id: Page ID to fix (mutually exclusive with section_key)
            section_key: GlobalSection key to fix
            issues: List of issue dicts to fix
            custom_rules: Optional user-defined rules
            model_override: Override the default model
            on_progress: Progress callback

        Returns:
            Dict with 'html' containing the fixed HTML
        """
        def notify(step, status, **extra):
            if on_progress:
                try:
                    on_progress({"step": step, "status": status, **extra})
                except Exception:
                    pass

        from djangopress.core.models import SiteSettings, Page, GlobalSection

        site_settings = SiteSettings.objects.first()
        default_lang = site_settings.get_default_language() if site_settings else 'pt'
        design_system = self._build_design_system_dict(site_settings)
        design_guide = site_settings.design_guide if site_settings else ''

        # Load HTML
        if page_id:
            page = Page.objects.get(id=page_id)
            html_i18n = page.html_content_i18n or {}
            html = html_i18n.get(default_lang, '')
            label = page.get_title(default_lang) or f'Page {page_id}'
        elif section_key:
            section = GlobalSection.objects.get(key=section_key)
            html_i18n = section.html_template_i18n or {}
            html = html_i18n.get(default_lang, '')
            label = section.name or section_key
        else:
            raise ValueError("Either page_id or section_key is required")

        if not html:
            raise ValueError(f"No HTML found for {label}")

        notify("fixing", "running", label=label)

        system_prompt, user_prompt = PromptTemplates.get_consistency_fix_prompt(
            design_system=design_system,
            design_guide=design_guide,
            page_html=html,
            issues=issues or [],
            custom_rules=custom_rules,
        )

        model = model_override or get_ai_model('consistency')
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]

        actual_model, provider = self._get_model_info(model)
        stream_cb = self._make_stream_callback(on_progress, 'fixing')
        t0 = time.time()
        try:
            response = self.llm.get_completion(messages, tool_name=model, on_stream=stream_cb)
            usage = self._extract_usage(response)
            content = response.choices[0].message.content
            log_ai_call(
                action='consistency_fix', model_name=actual_model, provider=provider,
                system_prompt=system_prompt, user_prompt=user_prompt,
                response_text=content,
                duration_ms=int((time.time() - t0) * 1000), **usage,
            )
        except Exception as e:
            log_ai_call(
                action='consistency_fix', model_name=actual_model, provider=provider,
                system_prompt=system_prompt, user_prompt=user_prompt,
                duration_ms=int((time.time() - t0) * 1000),
                success=False, error_message=str(e),
            )
            raise

        fixed_html = self._extract_html_from_response(content)

        if not fixed_html or len(fixed_html.strip()) < 50:
            raise ValueError("Fix returned empty or too-short HTML")

        notify("fixing", "done", label=label)
        return {'html': fixed_html}
