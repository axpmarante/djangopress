"""
AI Content Generation Services
Main service layer for generating and refining pages and global sections (header/footer)
"""
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Any, Optional, Union
from .utils.llm_config import LLMBase, MODEL_CONFIG
from .utils.prompts import PromptTemplates
from .utils.components import ComponentRegistry
from .models import log_ai_call


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
                tool_name='gemini-flash'
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

    def _detemplatize_html(self, html: str, translations: dict, language: str) -> str:
        """
        Replace {{ trans.xxx }} variables in HTML with actual text from translations.

        Args:
            html: HTML string with {{ trans.xxx }} template variables
            translations: Dict like {"pt": {"hero_title": "Título", ...}, "en": {...}}
            language: Language code to use for substitution

        Returns:
            Clean HTML with real text instead of template variables
        """
        lang_translations = translations.get(language, {})

        def replace_var(match):
            var_name = match.group(1)
            return lang_translations.get(var_name, match.group(0))

        return re.sub(r'\{\{\s*trans\.(\w+)\s*\}\}', replace_var, html)

    @staticmethod
    def _strip_legacy_attrs(html: str) -> str:
        """Strip legacy data-element-id attributes from HTML to save tokens."""
        return re.sub(r'\s+data-element-id="[^"]*"', '', html)


    @staticmethod
    def _extract_text_from_html(html: str) -> list:
        """
        Extract translatable text strings from HTML using BeautifulSoup.

        Walks all NavigableString nodes, filters out non-translatable content,
        and generates variable names based on section context and element role.

        Args:
            html: HTML string (with Django tags already protected as comments)

        Returns:
            List of dicts: [{"var": "hero_title", "original": "Welcome"}, ...]
        """
        from bs4 import BeautifulSoup, NavigableString, Comment

        soup = BeautifulSoup(html, 'html.parser')

        # Tags whose text content should never be extracted
        skip_tags = {'script', 'style', 'svg', 'code', 'pre', 'noscript'}

        # Map parent tag to a role suffix for variable naming
        tag_role_map = {
            'h1': 'title', 'h2': 'heading', 'h3': 'heading', 'h4': 'heading',
            'h5': 'heading', 'h6': 'heading',
            'p': 'text', 'a': 'link', 'button': 'button', 'span': 'label',
            'li': 'item', 'th': 'header', 'td': 'cell', 'label': 'label',
            'figcaption': 'caption', 'blockquote': 'quote', 'cite': 'cite',
            'dt': 'term', 'dd': 'definition', 'legend': 'legend',
            'option': 'option', 'summary': 'summary', 'strong': 'text',
            'em': 'text', 'b': 'text', 'i': 'text', 'small': 'text',
        }

        results = []
        # Track counters per base name to avoid duplicates
        name_counters = {}

        for text_node in soup.descendants:
            # Only process text nodes
            if not isinstance(text_node, NavigableString):
                continue
            # Skip comments and CDATA
            if isinstance(text_node, Comment):
                continue

            text = text_node.strip()
            if not text or len(text) < 2:
                continue

            # Skip protected Django tag placeholders
            if 'PROTECTED_DJANGO_TAG' in text:
                continue

            # Skip if inside a skip tag
            parent = text_node.parent
            if parent is None:
                continue
            in_skip_tag = False
            for ancestor in [parent] + list(parent.parents):
                if ancestor.name in skip_tags:
                    in_skip_tag = True
                    break
            if in_skip_tag:
                continue

            # Find nearest <section data-section="X"> ancestor for section prefix
            section_name = None
            for ancestor in [parent] + list(parent.parents):
                if ancestor.name == 'section' and ancestor.get('data-section'):
                    section_name = ancestor['data-section']
                    break

            # Determine role from parent tag
            role = tag_role_map.get(parent.name, 'text')

            # Build base variable name
            if section_name:
                # Sanitize section name to snake_case
                section_prefix = re.sub(r'[^a-zA-Z0-9]', '_', section_name).strip('_').lower()
                base_name = f"{section_prefix}_{role}"
            else:
                base_name = role

            # Handle duplicate names with counters
            if base_name not in name_counters:
                name_counters[base_name] = 0
            name_counters[base_name] += 1

            if name_counters[base_name] == 1:
                var_name = base_name
            else:
                var_name = f"{base_name}_{name_counters[base_name]}"

            results.append({
                'var': var_name,
                'original': text,
            })

        return results

    def _templatize_and_translate(self, html: str, languages: list, default_language: str, model: str) -> Dict:
        """
        Step 2: Python-based text extraction + translation-only LLM call.

        Extracts text in Python with BeautifulSoup and only sends the text strings
        for translation. ~10x fewer tokens than sending full HTML to the LLM.

        Args:
            html: Clean HTML with real text in the default language
            languages: List of language codes
            default_language: The language the HTML text is written in
            model: LLM model name to use

        Returns:
            Dict with 'html_content' (templatized) and 'content' (with translations)

        Raises:
            ValueError: If templatization fails
        """
        print(f"\n--- Step 2 (v2): Python Extract + Translate ---")

        # Always use gemini-flash for translation
        model = 'gemini-flash'

        # --- Phase A: Protect Django template tags ---
        protected_tags = {}
        protected_html = html

        # Normalize double-brace template tags that LLMs sometimes generate
        protected_html = re.sub(r'\{\{(%.*?%)\}\}', r'{\1}', protected_html)
        protected_html = re.sub(r'\{\{\{\{(.*?)\}\}\}\}', r'{{\1}}', protected_html)

        def protect_tag(match):
            placeholder = f'<!-- PROTECTED_DJANGO_TAG_{len(protected_tags)} -->'
            protected_tags[placeholder] = match.group(0)
            return placeholder

        # Protect {% ... %} tags
        protected_html = re.sub(r'\{%.*?%\}', protect_tag, protected_html, flags=re.DOTALL)
        # Protect {{ ... }} context variables
        protected_html = re.sub(r'\{\{.*?\}\}', protect_tag, protected_html, flags=re.DOTALL)

        if protected_tags:
            print(f"Protected {len(protected_tags)} Django template tags from templatization")

        # --- Phase B: Python text extraction ---
        extracted = self._extract_text_from_html(protected_html)

        if not extracted:
            print("No translatable text found — returning HTML as-is with empty translations")
            final_html = protected_html
            for placeholder, original_tag in protected_tags.items():
                final_html = final_html.replace(placeholder, original_tag)
            return {
                'html_content': final_html,
                'content': {'translations': {lang: {} for lang in languages}},
            }

        print(f"Extracted {len(extracted)} text strings from HTML")

        # Build the text dict for the LLM: {var_name: "original text"}
        text_dict = {item['var']: item['original'] for item in extracted}

        # --- Phase C: Send ONLY text strings to LLM for translation ---
        system_prompt, user_prompt = PromptTemplates.get_translate_only_prompt(
            text_dict=text_dict,
            languages=languages,
            default_language=default_language
        )

        # Debug output
        system_token_estimate = len(system_prompt.split()) * 1.3
        user_token_estimate = len(user_prompt.split()) * 1.3
        total_token_estimate = system_token_estimate + user_token_estimate
        print(f"TRANSLATE PROMPT (≈{int(total_token_estimate)} tokens)")

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ]

        actual_model, provider = self._get_model_info(model)
        t0 = time.time()
        try:
            response = self.llm.get_completion(messages, tool_name=model)
            usage = self._extract_usage(response)
            log_ai_call(
                action='templatize_v2', model_name=actual_model, provider=provider,
                system_prompt=system_prompt, user_prompt=user_prompt,
                response_text=response.choices[0].message.content,
                duration_ms=int((time.time() - t0) * 1000), **usage,
            )
        except Exception as e:
            log_ai_call(
                action='templatize_v2', model_name=actual_model, provider=provider,
                system_prompt=system_prompt, user_prompt=user_prompt,
                duration_ms=int((time.time() - t0) * 1000),
                success=False, error_message=str(e),
            )
            raise

        content = response.choices[0].message.content
        translations_response = self._extract_json_from_response(content)

        # The LLM returns {lang_code: {var: text, ...}, ...}
        if not isinstance(translations_response, dict):
            raise ValueError("Translation step returned invalid data (expected a dict)")

        # Build translations dict — ensure all vars are present for all languages
        translations = {lang: {} for lang in languages}
        for lang in languages:
            lang_trans = translations_response.get(lang, {})
            for item in extracted:
                var = item['var']
                if lang == default_language:
                    # Default language always uses the original text
                    translations[lang][var] = item['original']
                elif var in lang_trans:
                    translations[lang][var] = lang_trans[var]
                else:
                    # Fallback to original if translation missing
                    translations[lang][var] = item['original']
                    print(f"  WARNING: Missing {lang.upper()} translation for '{var}', using original")

        # --- Phase D: HTML replacement + validation ---
        templatized_html = protected_html

        # Sort by length of original text (longest first) to avoid partial replacements
        sorted_extracted = sorted(extracted, key=lambda m: len(m['original']), reverse=True)

        replaced_count = 0
        for item in sorted_extracted:
            var_name = item['var']
            original_text = item['original']
            template_var = '{{ trans.' + var_name + ' }}'
            if original_text in templatized_html:
                templatized_html = templatized_html.replace(original_text, template_var, 1)
                replaced_count += 1

        print(f"Replaced {replaced_count}/{len(extracted)} text strings with template variables")

        # Validate translations completeness
        trans_vars = set(re.findall(r'\{\{\s*trans\.(\w+)\s*\}\}', templatized_html))
        if trans_vars:
            missing_vars = {}
            for lang in languages:
                lang_trans = translations.get(lang, {})
                missing_in_lang = trans_vars - set(lang_trans.keys())
                if missing_in_lang:
                    missing_vars[lang] = list(missing_in_lang)
            if missing_vars:
                print(f"WARNING: Missing translations after templatization:")
                for lang, vars_list in missing_vars.items():
                    print(f"  - {lang.upper()}: {', '.join(vars_list)}")

        print(f"Templatized HTML with {len(trans_vars)} translation variables")

        # Restore protected Django template tags
        if protected_tags:
            restored_count = 0
            for placeholder, original_tag in protected_tags.items():
                if placeholder in templatized_html:
                    templatized_html = templatized_html.replace(placeholder, original_tag)
                    restored_count += 1
                else:
                    print(f"WARNING: Placeholder {placeholder} was consumed during templatization — re-inserting is not possible")
                    print(f"  Original tag was: {original_tag}")
            print(f"Restored {restored_count}/{len(protected_tags)} protected Django template tags")

        # Validate template syntax before returning
        from django.template import Template, TemplateSyntaxError
        try:
            Template(templatized_html)
        except TemplateSyntaxError as e:
            print(f"ERROR: Templatized HTML has broken template syntax: {e}")
            print("Attempting auto-fix of broken template tags...")
            templatized_html = re.sub(
                r'\{\{\s*trans\.(\w+)\s+\{\{[^}]*\}\}\s*\}\}',
                r'{{ trans.\1 }}',
                templatized_html
            )
            try:
                Template(templatized_html)
                print("Auto-fix successful")
            except TemplateSyntaxError as e2:
                raise ValueError(f"Templatized HTML has invalid template syntax that could not be auto-fixed: {e2}")

        return {
            'html_content': templatized_html,
            'content': {
                'translations': translations
            }
        }

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

        # Always use gemini-lite for metadata — title/slug generation is a trivial task
        model = 'gemini-lite'

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
            Dictionary with 'html_content_i18n', 'html_content' (backward compat),
            'content' (backward compat), 'title_i18n', 'slug_i18n'

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
        from core.models import SiteSettings, Page
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
            # Backward compat during transition
            'html_content': raw_html,
            'content': {'translations': {default_lang: {}}},
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
            from core.models import GlobalSection
            from django.utils.translation import get_language
            section = GlobalSection.objects.get(key=section_key)
        except GlobalSection.DoesNotExist:
            raise ValueError(f"GlobalSection with key '{section_key}' not found")

        # Convert to dict — read from html_template_i18n with fallback
        from core.models import SiteSettings, Page
        site_settings = SiteSettings.objects.first()
        default_language = site_settings.get_default_language() if site_settings else 'pt'
        current_lang = get_language() or default_language
        template_i18n = section.html_template_i18n or {}
        current_template = template_i18n.get(current_lang) or template_i18n.get(default_language) or section.html_template
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
        from core.models import MenuItem
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
        page_id: int,
        instructions: str,
        section_name: str = None,
        language: str = 'pt',
        model_override: str = None,
        reference_images: list = None,
        conversation_history: str = None,
        handle_images: bool = False,
        on_progress=None
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

        # Get page
        notify("prepare", "running")
        from core.models import Page, SiteSettings
        from django.utils.translation import get_language
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
        current_lang = get_language() or default_language
        html_i18n = page.html_content_i18n or {}
        clean_html = html_i18n.get(current_lang) or html_i18n.get(default_language) or page.html_content or ''
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
        result_html_i18n = dict(page.html_content_i18n or {})
        result_html_i18n[current_lang] = refined_html

        print(f"Successfully refined page")
        notify("complete", "done")
        return {
            'html_content_i18n': result_html_i18n,
            'html_content': refined_html,  # backward compat
            'content': page.content or {},  # backward compat
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

        from core.models import Page, SiteSettings
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
        current_lang = get_language() or default_language
        html_i18n = page.html_content_i18n or {}
        clean_html = html_i18n.get(current_lang) or html_i18n.get(default_language) or page.html_content or ''
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
        )

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ]

        notify("refine_html", "running", model=model)
        stream_cb = self._make_stream_callback(on_progress, 'refine_html')
        actual_model, provider_str = self._get_model_info(model)
        t0 = time.time()
        try:
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
        from core.models import Page, SiteSettings
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
        current_lang = get_language() or default_language
        html_i18n = page.html_content_i18n or {}
        clean_html = html_i18n.get(current_lang) or html_i18n.get(default_language) or page.html_content or ''
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

        from core.models import Page, SiteSettings
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
        current_lang = get_language() or default_language
        html_i18n = page.html_content_i18n or {}
        clean_html = html_i18n.get(current_lang) or html_i18n.get(default_language) or page.html_content or ''
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
        from core.models import Page, SiteImage, SiteSettings
        from .utils.llm_config import optimize_generated_image, LLMService
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
        current_lang = get_language() or default_language
        html_i18n = page.html_content_i18n or {}
        html = html_i18n.get(current_lang) or html_i18n.get(default_language) or page.html_content or ''
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
            from .utils.llm_config import LLMService, optimize_generated_image
            from core.models import SiteImage
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

        # Save updated HTML to html_content_i18n and backward compat field
        result_html_i18n = dict(page.html_content_i18n or {})
        result_html_i18n[current_lang] = html
        page.html_content_i18n = result_html_i18n
        page.html_content = html  # backward compat
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

        Translates the content['translations'] values using gemini-flash.
        Does NOT re-templatize — the HTML already has {{ trans.xxx }} variables.

        Args:
            target_lang: Language code to translate into (e.g. 'es')
            source_lang: Source language code (defaults to SiteSettings default)

        Returns:
            Dict with 'translated_pages', 'translated_sections', 'errors'
        """
        from core.models import Page, GlobalSection, SiteSettings
        from django.utils.text import slugify

        site_settings = SiteSettings.objects.first()
        if not source_lang:
            source_lang = site_settings.get_default_language() if site_settings else 'pt'

        # Get language names for prompt
        lang_names = {code: name for code, name in (site_settings.get_enabled_languages() if site_settings else [])}
        source_name = lang_names.get(source_lang, source_lang)
        target_name = lang_names.get(target_lang, target_lang)

        translated_pages = 0
        translated_sections = 0
        errors = []

        # Translate Pages
        for page in Page.objects.filter(is_active=True):
            try:
                translations = (page.content or {}).get('translations', {})
                source_trans = translations.get(source_lang, {})

                if not source_trans:
                    continue

                # Skip if target translations already exist with same number of keys
                existing_target = translations.get(target_lang, {})
                if existing_target and len(existing_target) >= len(source_trans):
                    continue

                # Translate content translations
                translated = self._translate_key_value_pairs(
                    source_trans, source_name, target_name
                )
                if translated:
                    if not page.content:
                        page.content = {}
                    if 'translations' not in page.content:
                        page.content['translations'] = {}
                    page.content['translations'][target_lang] = translated

                # Translate title
                source_title = (page.title_i18n or {}).get(source_lang, '')
                if source_title and not (page.title_i18n or {}).get(target_lang):
                    title_result = self._translate_key_value_pairs(
                        {'title': source_title}, source_name, target_name
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
                translations = (section.content or {}).get('translations', {})
                source_trans = translations.get(source_lang, {})

                if not source_trans:
                    continue

                existing_target = translations.get(target_lang, {})
                if existing_target and len(existing_target) >= len(source_trans):
                    continue

                translated = self._translate_key_value_pairs(
                    source_trans, source_name, target_name
                )
                if translated:
                    if not section.content:
                        section.content = {}
                    if 'translations' not in section.content:
                        section.content['translations'] = {}
                    section.content['translations'][target_lang] = translated
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

        actual_model, provider = self._get_model_info('gemini-flash')
        t0 = time.time()
        try:
            response = self.llm.get_completion(messages, tool_name='gemini-flash')
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
        model = model or 'gemini-flash'

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

    @staticmethod
    def _build_library_catalog(default_language: str = 'pt') -> List[Dict]:
        """Build a metadata-only catalog of all active library images."""
        from core.models import SiteImage

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

        actual_model, provider = self._get_model_info('gemini-flash')
        t0 = time.time()
        try:
            response = self.llm.get_completion(messages, tool_name='gemini-flash')
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
        from core.models import Page, SiteSettings, SiteImage

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
        current_lang = get_language() or default_language
        html_i18n = page.html_content_i18n or {}
        clean_html = html_i18n.get(current_lang) or html_i18n.get(default_language) or page.html_content or ''
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

        # Always use gemini-flash for image analysis — fast and sufficient for prompt suggestions
        model = 'gemini-flash'
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
        from core.models import SiteImage, SiteSettings
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

                # Call Gemini Flash vision
                actual_model, provider_str = self._get_model_info('gemini-flash')
                t0 = time.time()
                response = self.llm.get_vision_completion(
                    prompt=prompt,
                    file_bytes=image_bytes,
                    file_mime_type=mime_type,
                    tool_name='gemini-flash',
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
