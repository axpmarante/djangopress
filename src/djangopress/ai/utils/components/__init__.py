"""
Component Skills Registry for DjangoPress CMS.

Auto-discovers component modules in this package and provides:
- get_index()            -> compact listing for LLM pass 1 (component selection)
- get_references(names)  -> full reference docs for LLM pass 2 (HTML generation)
- get_all_names()        -> sorted list of registered component names
- select_components()    -> LLM-powered pass 1: pick which components a request needs
"""

import importlib
import logging
import pkgutil
import re
import time

logger = logging.getLogger(__name__)


class ComponentRegistry:
    """Registry that auto-discovers component skill modules and serves their docs."""

    _components = {}
    _discovered = False

    @classmethod
    def _discover(cls):
        """Scan this package for component modules and register them."""
        if cls._discovered:
            return

        package_path = __path__
        package_name = __name__

        for finder, name, is_pkg in pkgutil.iter_modules(package_path):
            if name.startswith('_'):
                continue
            try:
                module = importlib.import_module(f'.{name}', package=package_name)
                component_name = getattr(module, 'NAME', None)
                if component_name:
                    cls._components[component_name] = module
                else:
                    logger.warning(
                        "Component module '%s' has no NAME attribute, skipping.", name
                    )
            except Exception:
                logger.exception("Failed to import component module '%s'.", name)

        cls._discovered = True

    @classmethod
    def get_index(cls):
        """Return a compact index string listing all components with their INDEX_ENTRY."""
        cls._discover()

        if not cls._components:
            return ""

        lines = [
            "## Available Interactive Components",
            "The following interactive components are available. "
            "Request the ones you need by name.",
            "",
        ]
        for name in sorted(cls._components):
            module = cls._components[name]
            index_entry = getattr(module, 'INDEX_ENTRY', name)
            lines.append(f"- **{name}**: {index_entry}")

        return "\n".join(lines)

    @classmethod
    def get_references(cls, names):
        """Return concatenated FULL_REFERENCE strings for the requested component names."""
        cls._discover()

        parts = []
        for name in names:
            module = cls._components.get(name)
            if module is None:
                logger.warning("Requested component '%s' not found in registry.", name)
                continue
            full_ref = getattr(module, 'FULL_REFERENCE', None)
            if full_ref:
                parts.append(full_ref)

        return "\n\n".join(parts)

    @classmethod
    def get_all_names(cls):
        """Return a sorted list of all registered component names."""
        cls._discover()
        return sorted(cls._components.keys())

    @classmethod
    def select_components(cls, user_request, existing_html, llm):
        """
        Pass 1 of the two-pass flow: ask an LLM which components are needed.

        Args:
            user_request: The user's refinement/generation request text.
            existing_html: The current page HTML (may be empty for new pages).
            llm: An LLMBase instance.

        Returns:
            A list of component name strings that the LLM selected,
            or [] on failure (graceful degradation).
        """
        cls._discover()

        if not cls._components:
            return []

        index = cls.get_index()

        system_prompt = (
            "You are a component selector for a CMS. Given a user's request and "
            "(optionally) the existing page HTML, decide which interactive components "
            "are needed.\n\n"
            f"{index}\n\n"
            "Return a JSON array of component names that are needed for this request. "
            "Examples:\n"
            '- User wants a carousel/slider: ["splide"]\n'
            '- User wants a gallery with lightbox: ["lightbox"]\n'
            '- User wants tabs and an accordion: ["alpine-tabs", "alpine-accordion"]\n\n'
            "Return [] (empty array) when NO interactive components are needed. "
            "This includes:\n"
            "- Simple text edits (rewrite copy, fix typos, change headings)\n"
            "- Layout changes (reorder sections, change grid columns)\n"
            "- Color/style changes (backgrounds, fonts, spacing)\n"
            "- Adding static content (paragraphs, images, lists, cards)\n"
            "- SEO or accessibility improvements\n\n"
            "Respond with ONLY the JSON array, no explanation."
        )

        # Truncate existing HTML to keep pass 1 cheap
        html_preview = ""
        if existing_html:
            html_preview = existing_html[:3000]
            if len(existing_html) > 3000:
                html_preview += "\n<!-- ... truncated ... -->"

        user_prompt_parts = [f"User request: {user_request}"]
        if html_preview:
            user_prompt_parts.append(f"\nExisting page HTML:\n{html_preview}")
        user_prompt = "\n".join(user_prompt_parts)

        from ai.utils.llm_config import MODEL_CONFIG
        config = MODEL_CONFIG.get('gemini-lite')
        model_name = config.model_name if config else 'gemini-lite'

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]

        start_ms = int(time.time() * 1000)
        try:
            response = llm.get_completion(messages, tool_name='gemini-lite')

            response_text = response.choices[0].message.content
            prompt_tokens = getattr(response.usage, 'prompt_tokens', 0)
            completion_tokens = getattr(response.usage, 'completion_tokens', 0)
            total_tokens = getattr(response.usage, 'total_tokens', 0)
            duration_ms = int(time.time() * 1000) - start_ms

            # Extract JSON array from response
            match = re.search(r'\[.*?\]', response_text, re.DOTALL)
            if not match:
                logger.warning(
                    "select_components: no JSON array found in response: %s",
                    response_text[:200],
                )
                from ai.models import log_ai_call
                log_ai_call(
                    action='select_components',
                    model_name=model_name,
                    provider='google',
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_text=response_text,
                    duration_ms=duration_ms,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                )
                return []

            import json
            try:
                names = json.loads(match.group(0))
            except json.JSONDecodeError:
                logger.warning(
                    "select_components: invalid JSON in response: %s",
                    match.group(0),
                )
                from ai.models import log_ai_call
                log_ai_call(
                    action='select_components',
                    model_name=model_name,
                    provider='google',
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_text=response_text,
                    duration_ms=duration_ms,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                )
                return []

            # Validate that all names exist in the registry
            valid_names = [n for n in names if n in cls._components]
            invalid = set(names) - set(valid_names)
            if invalid:
                logger.warning(
                    "select_components: LLM returned unknown components: %s", invalid
                )

            from ai.models import log_ai_call
            log_ai_call(
                action='select_components',
                model_name=model_name,
                provider='google',
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_text=response_text,
                duration_ms=duration_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            )

            return valid_names

        except Exception:
            duration_ms = int(time.time() * 1000) - start_ms
            logger.exception("select_components: LLM call failed")
            try:
                from ai.models import log_ai_call
                log_ai_call(
                    action='select_components',
                    model_name=model_name,
                    provider='google',
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_text='',
                    duration_ms=duration_ms,
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                    success=False,
                    error_message=str(Exception),
                )
            except Exception:
                logger.exception("select_components: failed to log error")
            return []
