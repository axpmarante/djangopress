"""AssistantService — orchestrates LLM calls and tool execution."""

import json
import re
import logging

from ai.utils.llm_config import LLMBase
from .prompts import build_system_prompt, build_user_prompt
from .tools import ToolRegistry

logger = logging.getLogger(__name__)

# Tools that require user confirmation before executing
DESTRUCTIVE_TOOLS = {'delete_page', 'delete_menu_item'}

# Tools that perform write/mutation operations
WRITE_TOOLS = {
    'create_page', 'update_page_meta', 'delete_page', 'reorder_pages',
    'create_menu_item', 'update_menu_item', 'delete_menu_item',
    'update_settings', 'update_translations', 'update_element_styles',
    'update_element_attribute', 'remove_section', 'reorder_sections',
    'refine_section', 'refine_page',
}

# Keywords in response text that indicate the LLM claims a write action
WRITE_CLAIM_KEYWORDS = {
    'created', 'updated', 'changed', 'modified', 'deleted', 'removed',
    'added', 'renamed', 'reordered', 'set up', 'configured',
}

MAX_TOOL_ITERATIONS = 8
MAX_VERIFICATION_RETRIES = 1


class AssistantService:

    def __init__(self, session):
        self.session = session
        self.llm = LLMBase()

    def handle_message(self, message, user=None):
        """
        Process a user message through a tool loop: call LLM, parse response,
        execute tools. If the LLM outputs only <actions> (no <response>),
        feed tool results back and loop. When <response> appears, return.

        Returns dict with:
            - response: str (assistant's message)
            - actions: list of {tool, params, result} (all actions across iterations)
            - steps: list of {iteration, actions} (intermediate tool-call rounds)
            - pending_confirmation: dict or None
            - set_active_page: int or None
        """
        model = self.session.model_used or 'gemini-flash'

        # Build initial messages
        system_prompt = build_system_prompt(self.session)
        history = self.session.get_history_for_prompt()
        user_prompt = build_user_prompt(message, history)

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]

        # Store user message
        self.session.add_message('user', message)

        context = {
            'session': self.session,
            'user': user,
            'active_page': self.session.active_page,
            'model': model,
        }

        all_executed_actions = []
        steps = []
        set_active_page = None
        iteration = 0

        while iteration <= MAX_TOOL_ITERATIONS:
            # Call LLM
            try:
                response = self.llm.get_completion(messages, tool_name=model)
                raw_content = response.choices[0].message.content
            except Exception as e:
                logger.exception('LLM call failed at iteration %d', iteration)
                return {
                    'response': f'Sorry, I encountered an error: {str(e)}',
                    'actions': all_executed_actions,
                    'steps': steps,
                    'pending_confirmation': None,
                    'set_active_page': set_active_page,
                }

            # Parse
            parsed = self._parse_response(raw_content)
            has_response = parsed['has_response']
            response_text = parsed['response']
            actions_data = parsed['actions']
            pending = parsed['pending_confirmation']

            # --- Exit conditions ---

            # Destructive confirmation — return immediately
            if pending:
                self.session.add_message('assistant', response_text, actions=[{
                    'tool': pending['tool'],
                    'status': 'pending_confirmation',
                }])
                return {
                    'response': response_text,
                    'actions': all_executed_actions,
                    'steps': steps,
                    'pending_confirmation': pending,
                    'set_active_page': set_active_page,
                }

            # Final response or max iterations reached
            if has_response or iteration == MAX_TOOL_ITERATIONS:
                if not has_response and iteration == MAX_TOOL_ITERATIONS:
                    logger.warning('Max tool iterations reached, forcing response')

                # Execute any final actions
                final_actions, page_switch = self._execute_actions(
                    actions_data, context
                )
                all_executed_actions.extend(final_actions)
                if page_switch:
                    set_active_page = page_switch
                    self._refresh_context(context, page_switch)

                # Verify actions match claims
                response_text, needs_retry = self._verify_actions(
                    response_text, all_executed_actions
                )

                if needs_retry:
                    # Retry once with correction prompt
                    messages.append({'role': 'assistant', 'content': raw_content})
                    messages.append({'role': 'user', 'content': (
                        'Your response claims you performed an action, but no tool '
                        'was executed. You MUST include the tool call in <actions> '
                        'to actually perform it. Try again.'
                    )})

                    retry_result = self._retry_for_verification(
                        messages, model, context, all_executed_actions, steps,
                        set_active_page
                    )
                    if retry_result:
                        return retry_result

                    # Retry also failed — append warning
                    response_text += (
                        '\n\nNote: The requested action could not be completed. '
                        'Please try again with a more specific request.'
                    )

                # Save and return
                self.session.add_message(
                    'assistant', response_text, actions=all_executed_actions
                )
                self._auto_title(message)

                return {
                    'response': response_text,
                    'actions': all_executed_actions,
                    'steps': steps,
                    'pending_confirmation': None,
                    'set_active_page': set_active_page,
                }

            # --- Tool call mode (no <response>) — execute and loop ---
            logger.info(
                'Tool loop iteration %d: %d actions',
                iteration + 1, len(actions_data)
            )

            executed, page_switch = self._execute_actions(actions_data, context)
            all_executed_actions.extend(executed)
            if page_switch:
                set_active_page = page_switch
                self._refresh_context(context, page_switch)

            # Record step
            steps.append({
                'iteration': iteration + 1,
                'actions': executed,
            })

            # Append assistant output + tool results to messages
            messages.append({'role': 'assistant', 'content': raw_content})
            tool_results_text = self._format_tool_results(executed)
            messages.append({'role': 'user', 'content': tool_results_text})

            # Rebuild system prompt (page context may have changed)
            messages[0] = {
                'role': 'system',
                'content': build_system_prompt(self.session),
            }

            iteration += 1

        # Should not reach here, but safety return
        return {
            'response': 'I was unable to complete the request within the allowed number of steps.',
            'actions': all_executed_actions,
            'steps': steps,
            'pending_confirmation': None,
            'set_active_page': set_active_page,
        }

    def execute_confirmed_action(self, tool_name, params, user=None):
        """Execute a previously confirmed destructive action."""
        context = {
            'session': self.session,
            'user': user,
            'active_page': self.session.active_page,
            'model': self.session.model_used or 'gemini-flash',
        }

        result = ToolRegistry.execute(tool_name, params, context)

        action_record = {
            'tool': tool_name,
            'params': params,
            'success': result.get('success', False),
            'message': result.get('message', ''),
        }
        self.session.add_message(
            'assistant', result.get('message', 'Action executed.'),
            actions=[action_record]
        )

        return {
            'response': result.get('message', ''),
            'actions': [action_record],
            'set_active_page': result.get('set_active_page'),
        }

    def _execute_actions(self, actions_data, context):
        """Execute a list of tool actions. Returns (executed_actions, set_active_page)."""
        executed = []
        set_active_page = None

        for action in actions_data:
            tool_name = action.get('tool')
            params = action.get('params', {})

            result = ToolRegistry.execute(tool_name, params, context)
            action_record = {
                'tool': tool_name,
                'params': params,
                'success': result.get('success', False),
                'message': result.get('message', ''),
            }
            # Include query result data for the frontend
            for key in ('pages', 'page', 'menu_items', 'settings', 'images',
                        'contacts', 'stats', 'page_id', 'menu_item_id'):
                if key in result:
                    action_record[key] = result[key]
            executed.append(action_record)

            # Track page switches
            if result.get('set_active_page'):
                set_active_page = result['set_active_page']
                self._refresh_context(context, set_active_page)

        return executed, set_active_page

    def _refresh_context(self, context, page_id):
        """Refresh active_page in context after a page switch."""
        from core.models import Page
        try:
            context['active_page'] = Page.objects.get(pk=page_id)
        except Page.DoesNotExist:
            pass

    def _format_tool_results(self, executed_actions):
        """Format tool results as compact text for injection back to LLM."""
        if not executed_actions:
            return 'Tool results:\nNo actions were executed.'

        parts = ['Tool results:\n']
        for action in executed_actions:
            tool = action.get('tool', 'unknown')
            success = action.get('success', False)
            status = 'Success' if success else 'Failed'
            message = action.get('message', '')

            parts.append(f'### {tool} → {status}')
            if message:
                parts.append(message)

            # Include key data so the LLM can reference it
            if action.get('pages'):
                lines = []
                for p in action['pages']:
                    title = p.get('title', {})
                    if isinstance(title, dict):
                        title_str = title.get('en') or title.get('pt') or str(title)
                    else:
                        title_str = str(title)
                    active = 'Yes' if p.get('is_active') else 'No'
                    lines.append(f"  ID:{p['id']} | {title_str} | Active:{active}")
                parts.append('\n'.join(lines))

            if action.get('page'):
                p = action['page']
                title = p.get('title', {})
                if isinstance(title, dict):
                    title_str = title.get('en') or title.get('pt') or str(title)
                else:
                    title_str = str(title)
                parts.append(f"Page: \"{title_str}\" (ID: {p.get('id', '?')})")
                if p.get('sections'):
                    parts.append(f"Sections: {', '.join(p['sections'])}")
                if p.get('translations'):
                    for lang, trans in p['translations'].items():
                        sample = list(trans.items())[:5]
                        sample_str = ', '.join(
                            f'{k}="{v[:40]}"' for k, v in sample
                        )
                        extra = f' (+{len(trans)-5} more)' if len(trans) > 5 else ''
                        parts.append(f"  {lang}: {sample_str}{extra}")

            if action.get('menu_items'):
                for m in action['menu_items']:
                    label = m.get('label', {})
                    if isinstance(label, dict):
                        label_str = label.get('en') or label.get('pt') or str(label)
                    else:
                        label_str = str(label)
                    parts.append(f"  #{m['id']}: {label_str}")
                    for c in m.get('children', []):
                        cl = c.get('label', {})
                        if isinstance(cl, dict):
                            cl_str = cl.get('en') or cl.get('pt') or str(cl)
                        else:
                            cl_str = str(cl)
                        parts.append(f"    └ #{c['id']}: {cl_str}")

            if action.get('stats'):
                for k, v in action['stats'].items():
                    parts.append(f"  {k}: {v}")

            if action.get('settings'):
                for k, v in action['settings'].items():
                    val = json.dumps(v) if isinstance(v, (dict, list)) else str(v)
                    parts.append(f"  {k}: {val[:80]}")

            if action.get('page_id'):
                parts.append(f"Created page ID: {action['page_id']}")

            if action.get('menu_item_id'):
                parts.append(f"Created menu item ID: {action['menu_item_id']}")

            parts.append('')  # blank line between actions

        return '\n'.join(parts)

    def _verify_actions(self, response_text, all_executed_actions):
        """
        Check if response claims match actual tool executions.
        Returns (possibly_modified_response_text, needs_retry).
        """
        response_lower = response_text.lower()

        # Does the response claim a write action?
        claims_write = any(kw in response_lower for kw in WRITE_CLAIM_KEYWORDS)
        if not claims_write:
            return response_text, False

        # Were any write tools actually executed successfully?
        successful_writes = [
            a for a in all_executed_actions
            if a.get('tool') in WRITE_TOOLS and a.get('success')
        ]

        if successful_writes:
            # Check for partial failures
            failed = [a for a in all_executed_actions if not a.get('success')]
            if failed:
                failures = ', '.join(
                    f"{a['tool']}: {a['message']}" for a in failed
                )
                response_text += f'\n\nSome actions failed: {failures}'
            return response_text, False

        # Hallucination: claims write but no write tools executed
        return response_text, True

    def _retry_for_verification(self, messages, model, context,
                                 all_executed_actions, steps, set_active_page):
        """
        Retry LLM call after hallucination detection.
        Returns a complete result dict if retry succeeds, None otherwise.
        """
        try:
            response = self.llm.get_completion(messages, tool_name=model)
            raw_content = response.choices[0].message.content
        except Exception as e:
            logger.exception('Verification retry LLM call failed')
            return None

        parsed = self._parse_response(raw_content)
        if not parsed['has_response']:
            # Retry produced another tool-only call — execute it
            executed, page_switch = self._execute_actions(
                parsed['actions'], context
            )
            all_executed_actions.extend(executed)
            if page_switch:
                set_active_page = page_switch

            # Check if write tools ran this time
            successful_writes = [
                a for a in executed
                if a.get('tool') in WRITE_TOOLS and a.get('success')
            ]
            if successful_writes:
                response_text = 'Action completed.'
                self.session.add_message(
                    'assistant', response_text, actions=all_executed_actions
                )
                return {
                    'response': response_text,
                    'actions': all_executed_actions,
                    'steps': steps,
                    'pending_confirmation': None,
                    'set_active_page': set_active_page,
                }
            return None

        # Retry produced a response — execute any actions
        response_text = parsed['response']
        executed, page_switch = self._execute_actions(
            parsed['actions'], context
        )
        all_executed_actions.extend(executed)
        if page_switch:
            set_active_page = page_switch

        # Check if write tools ran
        successful_writes = [
            a for a in executed
            if a.get('tool') in WRITE_TOOLS and a.get('success')
        ]
        if successful_writes:
            self.session.add_message(
                'assistant', response_text, actions=all_executed_actions
            )
            self._auto_title_from_session()
            return {
                'response': response_text,
                'actions': all_executed_actions,
                'steps': steps,
                'pending_confirmation': None,
                'set_active_page': set_active_page,
            }

        return None

    def _auto_title(self, message):
        """Auto-title session on first exchange."""
        if len(self.session.messages) == 2 and not self.session.title:
            self.session.title = message[:100]
            self.session.save(update_fields=['title'])

    def _auto_title_from_session(self):
        """Auto-title from first user message in session."""
        if not self.session.title and self.session.messages:
            for msg in self.session.messages:
                if msg.get('role') == 'user':
                    self.session.title = msg['content'][:100]
                    self.session.save(update_fields=['title'])
                    break

    def _parse_response(self, raw):
        """Parse XML-tagged LLM response into components."""
        result = {
            'response': '',
            'has_response': False,
            'actions': [],
            'pending_confirmation': None,
        }

        # Extract <response>
        response_match = re.search(r'<response>(.*?)</response>', raw, re.DOTALL)
        if response_match:
            result['response'] = response_match.group(1).strip()
            result['has_response'] = True
        else:
            # No <response> tag — check if there's non-tag text (fallback)
            stripped = re.sub(
                r'<(?:actions|pending_confirmation)>.*?</(?:actions|pending_confirmation)>',
                '', raw, flags=re.DOTALL
            ).strip()
            if stripped:
                result['response'] = stripped
                # Don't set has_response — this is fallback text, not an explicit response

        # Extract <pending_confirmation>
        pending_match = re.search(
            r'<pending_confirmation>(.*?)</pending_confirmation>', raw, re.DOTALL
        )
        if pending_match:
            try:
                result['pending_confirmation'] = json.loads(
                    pending_match.group(1).strip()
                )
                result['has_response'] = True  # Confirmation always ends the loop
            except json.JSONDecodeError:
                logger.warning('Failed to parse pending_confirmation JSON')

        # Extract <actions>
        actions_match = re.search(r'<actions>(.*?)</actions>', raw, re.DOTALL)
        if actions_match:
            try:
                result['actions'] = json.loads(actions_match.group(1).strip())
                if not isinstance(result['actions'], list):
                    result['actions'] = []
            except json.JSONDecodeError:
                logger.warning('Failed to parse actions JSON')
                result['actions'] = []

        return result
