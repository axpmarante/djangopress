"""RefinementAgent — lightweight agentic router for editor refinements."""

import json
import re
import time
import logging

from ai.utils.llm_config import LLMBase
from . import tools as agent_tools
from .prompts import build_system_prompt, build_user_prompt

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 3


class RefinementAgent:
    """
    Agentic router that analyzes refinement requests and picks the fastest
    execution path: direct CSS/text edit (instant) or AI pipeline delegation.

    Uses gemini-flash for reasoning (~200ms per iteration).
    Returns the same {options: [...], assistant_message: str} format as the
    existing refinement pipeline.
    """

    def __init__(self):
        self.llm = LLMBase()

    def handle(self, instruction, scope, target_name, page,
               conversation_history=None, multi_option=False,
               mode='refine', insert_after=None):
        """
        Main entry point. Analyze instruction and execute via tools.

        Args:
            instruction: User's refinement request
            scope: 'section' or 'element'
            target_name: data-section value or CSS selector
            page: Page model instance
            conversation_history: List of {role, content} dicts
            multi_option: Whether to return 3 variations
            mode: 'refine' or 'create'
            insert_after: For mode='create', section to insert after

        Returns:
            Dict with 'options' (list of {'html': str}) and 'assistant_message'
        """
        from core.models import SiteSettings
        from ai.services import ContentGenerationService

        t0 = time.time()

        # Prepare de-templatized target HTML
        site_settings = SiteSettings.objects.first()
        default_language = site_settings.get_default_language() if site_settings else 'pt'

        target_html = self._get_target_html(page, scope, target_name, default_language)

        # Build conversation history string
        history_text = ''
        if conversation_history:
            for msg in conversation_history:
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                if role == 'user':
                    history_text += f"\nUser: {content}"
                elif role == 'assistant':
                    history_text += f"\nAssistant: {content}"

        # Build context for tools
        context = {
            'page': page,
            'scope': scope,
            'target_name': target_name,
            'target_html': target_html,
            'site_settings': site_settings,
            'instructions': instruction,
            'conversation_history': conversation_history or [],
            'multi_option': multi_option,
            'default_language': default_language,
        }

        # Build prompts
        system_prompt = build_system_prompt(
            scope=scope,
            target_name=target_name,
            target_html=target_html,
            conversation_history=history_text,
        )
        user_prompt = build_user_prompt(instruction, multi_option=multi_option)

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]

        # Agent loop
        iteration = 0
        while iteration < MAX_ITERATIONS:
            try:
                response = self.llm.get_completion(messages, tool_name='gemini-flash')
                raw_content = response.choices[0].message.content
            except Exception as e:
                logger.exception('Agent LLM call failed at iteration %d', iteration)
                print(f"Agent: LLM error at iteration {iteration}: {e}")
                break  # Fall through to fallback

            parsed = self._parse_response(raw_content)
            has_response = parsed['has_response']
            response_text = parsed['response']
            actions_data = parsed['actions']

            print(f"Agent iteration {iteration + 1}: has_response={has_response}, actions={[a.get('tool') for a in actions_data]}")

            if not actions_data and has_response:
                # Agent responded without any tool call — treat as needing AI delegation
                print(f"Agent: response only, no tools — falling back to AI delegation")
                break

            # Execute tools
            results = []
            final_result = None

            for action in actions_data:
                tool_name = action.get('tool', '')
                params = action.get('params', {})

                print(f"Agent: executing {tool_name}({json.dumps(params, default=str)[:200]})")

                result = agent_tools.execute(tool_name, params, context)
                results.append({'tool': tool_name, 'result': result})

                # Check for delegation result
                if result.get('_is_delegation'):
                    routing_ms = int((time.time() - t0) * 1000)
                    tier = f"ai_{params.get('model', 'gemini-flash').split('-')[-1]}"
                    print(f"Agent: delegated to AI pipeline ({tier}) after {routing_ms}ms routing")
                    delegated = result['result']
                    delegated['routing_tier'] = tier
                    delegated['routing_ms'] = routing_ms
                    if response_text:
                        delegated['assistant_message'] = response_text
                    return delegated

                # Check for direct edit result
                if result.get('success') and tool_name in agent_tools.DIRECT_EDIT_TOOLS:
                    final_result = result

            # If we have a final response and a direct edit was performed, return it
            if has_response and final_result:
                routing_ms = int((time.time() - t0) * 1000)
                print(f"Agent: direct edit complete in {routing_ms}ms")
                return {
                    'options': [{'html': context['target_html']}],
                    'assistant_message': response_text or 'Applied the change directly.',
                    'routing_tier': 'direct_edit',
                    'routing_ms': routing_ms,
                }

            # If we have a final response but no edit was done, break to fallback
            if has_response:
                print(f"Agent: has response but no edit — falling back")
                break

            # Tool call mode — feed results back and loop
            messages.append({'role': 'assistant', 'content': raw_content})
            tool_results_text = self._format_tool_results(results)
            messages.append({'role': 'user', 'content': tool_results_text})

            # Rebuild system prompt with potentially updated HTML
            messages[0] = {
                'role': 'system',
                'content': build_system_prompt(
                    scope=scope,
                    target_name=target_name,
                    target_html=context['target_html'],
                    conversation_history=history_text,
                ),
            }

            iteration += 1

        # Fallback: delegate to full AI pipeline with all context
        routing_ms = int((time.time() - t0) * 1000)
        print(f"Agent: fallback to full AI pipeline after {routing_ms}ms ({iteration} iterations)")

        service = ContentGenerationService(model_name='gemini-pro')

        if mode == 'create':
            result = service.generate_section(
                page_id=page.id,
                insert_after=insert_after,
                instructions=instruction,
                conversation_history=conversation_history,
            )
        elif scope == 'element':
            result = service.refine_element_only(
                page_id=page.id,
                selector=target_name,
                instructions=instruction,
                conversation_history=conversation_history,
                multi_option=multi_option,
            )
        else:
            result = service.refine_section_only(
                page_id=page.id,
                section_name=target_name,
                instructions=instruction,
                conversation_history=conversation_history,
                multi_option=multi_option,
            )

        result['routing_tier'] = 'fallback'
        result['routing_ms'] = routing_ms
        return result

    def _get_target_html(self, page, scope, target_name, default_language):
        """Extract clean HTML for the target section/element from html_content_i18n."""
        from bs4 import BeautifulSoup

        # Use default_language directly — get_language() is unreliable in AJAX context
        # (editor API endpoints are outside i18n_patterns)
        html_i18n = page.html_content_i18n or {}
        clean_html = html_i18n.get(default_language) or ''

        soup = BeautifulSoup(clean_html, 'html.parser')

        if scope == 'element':
            element = soup.select_one(target_name)
            if element:
                section = element.find_parent('section', attrs={'data-section': True})
                return str(section) if section else str(element)
            return clean_html[:2000]

        # Section scope
        section = soup.find('section', attrs={'data-section': target_name})
        if section:
            return str(section)
        return clean_html[:2000]

    def _parse_response(self, raw):
        """Parse XML-tagged LLM response into components."""
        result = {
            'response': '',
            'has_response': False,
            'actions': [],
        }

        # Extract <response>
        response_match = re.search(r'<response>(.*?)</response>', raw, re.DOTALL)
        if response_match:
            result['response'] = response_match.group(1).strip()
            result['has_response'] = True

        # Extract <actions>
        actions_match = re.search(r'<actions>(.*?)</actions>', raw, re.DOTALL)
        if actions_match:
            try:
                result['actions'] = json.loads(actions_match.group(1).strip())
                if not isinstance(result['actions'], list):
                    result['actions'] = []
            except json.JSONDecodeError:
                logger.warning('Failed to parse actions JSON from agent')
                result['actions'] = []

        return result

    def _format_tool_results(self, results):
        """Format tool results as text for injection back to LLM."""
        parts = ['Tool results:\n']
        for r in results:
            tool = r['tool']
            result = r['result']
            status = 'Success' if result.get('success') else 'Failed'
            message = result.get('message', '')
            parts.append(f'### {tool} → {status}')
            if message:
                parts.append(message)
            if result.get('html'):
                parts.append(f'\nUpdated HTML:\n```html\n{result["html"][:2000]}\n```')
            parts.append('')
        return '\n'.join(parts)
