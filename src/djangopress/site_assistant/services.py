"""AssistantService — two-phase executor with native Gemini function calling.

Phase 1: Router classifies intents (gemini-lite)
Phase 2: Executor runs native FC loop (gemini-flash)
"""

import logging

from djangopress.ai.utils.llm_config import LLMBase, get_ai_model
from .prompts import build_router_snapshot, build_executor_prompt, build_active_page_context
from .router import Router
from .tool_declarations import build_tool_declarations
from .tools import ToolRegistry

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 8

# Tools that mutate page context — refresh system instruction after these
PAGE_CONTEXT_MUTATIONS = {
    'set_active_page', 'create_page',
    'refine_section', 'refine_page',
    'remove_section', 'reorder_sections',
    'update_element_styles', 'update_element_attribute',
    'refine_header', 'refine_footer',
}


class AssistantService:

    def __init__(self, session):
        self.session = session
        self.llm = LLMBase()

    def handle_message(self, message, user=None, reference_images=None, run_id=None):
        """Run one turn and attach its change log (for Undo) to the reply."""
        from djangopress.site_assistant.changes import TurnChanges
        self._changes = TurnChanges(message, user)
        result = self._handle_message(message, user=user, reference_images=reference_images, run_id=run_id)
        items = self._changes.finish()
        if items:
            self.session.refresh_from_db()
            for index in range(len(self.session.messages) - 1, -1, -1):
                if self.session.messages[index].get('role') == 'assistant':
                    self.session.messages[index]['changes'] = items
                    self.session.save(update_fields=['messages', 'updated_at'])
                    result['message_index'] = index
                    break
        result['changes'] = [{'label': i['label'], 'kind': i['kind']} for i in items]
        return result

    def _handle_message(self, message, user=None, reference_images=None, run_id=None):
        """Process a user message through the two-phase flow.

        Phase 1: Router classifies intents or returns a direct response.
        Phase 2: Executor runs native FC loop with tool declarations.

        Returns dict with:
            - response: str (assistant's message)
            - actions: list of {tool, params, result} dicts
            - steps: list of {iteration, actions} dicts
            - set_active_page: int or None
        """
        # Store user message
        self.session.add_message('user', message)
        self._run_id = run_id
        if self._stop_requested():
            return self._stopped([], [], None)

        # Build snapshot for router
        snapshot = build_router_snapshot(self.session)

        # Phase 1: Router classification
        history = self.session.get_history_for_prompt()
        try:
            router_result = Router.classify(message, snapshot, history=history)
        except Exception as e:
            logger.exception('Router classification failed')
            router_result = {
                'intents': ['pages', 'navigation', 'settings'],
                'needs_active_page': False,
                'direct_response': None,
            }

        if self._stop_requested():
            return self._stopped([], [], None)

        # Direct response — no tools needed
        if router_result.get('direct_response'):
            response_text = router_result['direct_response']
            self.session.add_message('assistant', response_text)
            self._auto_title(message)
            return {
                'response': response_text,
                'actions': [],
                'steps': [],
                'set_active_page': None,
            }

        # Phase 2: Executor with native FC
        intents = router_result.get('intents', [])

        # If router says we need active page but none is set, add 'pages' intent
        # so set_active_page tool is available
        if router_result.get('needs_active_page') and not self.session.active_page:
            if 'pages' not in intents:
                intents.append('pages')

        # Always include 'pages' so set_active_page is available
        if 'pages' not in intents:
            intents.append('pages')

        return self._execute_phase2(message, intents, snapshot, user=user, reference_images=reference_images)

    # Tools that only read; they don't count as "done" in the summary.
    READ_ONLY_TOOLS = {'request_additional_tools', 'get_page_info', 'list_pages', 'get_settings', 'list_images',
                       'set_active_page', 'list_menu_items', 'list_forms', 'list_news'}

    @staticmethod
    def _plain(action):
        return f"{action.get('tool', '').replace('_', ' ')}: {action.get('message', '')}".strip()

    def _not_done_note(self, actions):
        """Failed steps are always reported, whatever the model wrote."""
        failed = list(dict.fromkeys(self._plain(a) for a in actions if not a.get('success')))
        if not failed:
            return ''
        return '\n\nNot done:\n' + '\n'.join(f'- {line}' for line in failed)

    def _report(self, actions):
        done = [a for a in actions if a.get('success') and a.get('tool') not in self.READ_ONLY_TOOLS]
        text = ''
        if done:
            text += '\n\nDone:\n' + '\n'.join(f'- {line}' for line in dict.fromkeys(self._plain(a) for a in done))
        text += self._not_done_note(actions)
        return text or '\n\nNothing was changed.'

    def _stop_requested(self):
        from djangopress.site_assistant import cancel
        return cancel.is_cancelled(getattr(self, '_run_id', None))

    def _stopped(self, actions, steps, set_active_page):
        from djangopress.site_assistant import cancel
        cancel.clear(getattr(self, '_run_id', None))
        changed = [a for a in actions if a.get('success') and a.get('tool') not in self.READ_ONLY_TOOLS]
        text = ('Stopped. Changes made before you stopped are kept.' + self._report(actions)) if changed \
            else 'Stopped. Nothing was changed.'
        self.session.add_message('assistant', text, actions=actions or None)
        return {'response': text, 'actions': actions, 'steps': steps,
                'set_active_page': set_active_page, 'stopped': True}

    def _execute_phase2(self, message, intents, snapshot, user=None, reference_images=None):
        """Execute the native Gemini FC loop.

        Builds the executor prompt, assembles tool declarations from intents,
        calls the LLM, executes tool calls, feeds results back, and loops
        until the LLM returns text (no more function calls) or max iterations.

        Returns the same shape dict as handle_message().
        """
        from google.genai import types

        # Build system instruction and tools
        system_instruction = build_executor_prompt(
            self.session, snapshot, has_reference_images=bool(reference_images)
        )
        tools = build_tool_declarations(intents)

        # Build contents (conversation history + current message)
        contents = self._build_contents(message, reference_images)

        context = {
            'session': self.session,
            'changes': getattr(self, '_changes', None),
            'user': user,
            'active_page': self.session.active_page,
            'model': get_ai_model('assistant_executor'),
            'reference_images': reference_images,
        }

        all_executed_actions = []
        steps = []
        set_active_page = None
        iteration = 0
        current_intents = set(intents)

        while iteration < MAX_TOOL_ITERATIONS:
            if self._stop_requested():
                return self._stopped(all_executed_actions, steps, set_active_page)
            # Call LLM with native FC
            try:
                response = self.llm.get_completion_with_tools(
                    contents=contents,
                    system_instruction=system_instruction,
                    tools=tools,
                    tool_name=get_ai_model('assistant_executor'),
                )
            except Exception as e:
                logger.exception('LLM FC call failed at iteration %d', iteration)
                error_msg = f'Sorry, I encountered an error: {str(e)}'
                self.session.add_message('assistant', error_msg)
                return {
                    'response': error_msg,
                    'actions': all_executed_actions,
                    'steps': steps,
                    'set_active_page': set_active_page,
                }

            # Extract the model's content
            if not response.candidates:
                error_msg = 'No response from the model.'
                self.session.add_message('assistant', error_msg)
                return {
                    'response': error_msg,
                    'actions': all_executed_actions,
                    'steps': steps,
                    'set_active_page': set_active_page,
                }

            model_content = response.candidates[0].content

            # Check what the response contains
            function_calls = []
            text_parts = []
            for part in (model_content.parts or []):
                if part.function_call:
                    function_calls.append(part.function_call)
                elif part.text:
                    text_parts.append(part.text)

            # No function calls — we have a final text response
            if not function_calls:
                response_text = '\n'.join(text_parts) if text_parts else ''
                if not response_text:
                    response_text = 'Done.'
                response_text += self._not_done_note(all_executed_actions)

                self.session.add_message('assistant', response_text, actions=all_executed_actions or None)
                self._auto_title(message)
                return {
                    'response': response_text,
                    'actions': all_executed_actions,
                    'steps': steps,
                    'set_active_page': set_active_page,
                }

            # Execute function calls
            function_response_parts = []
            iteration_actions = []
            needs_context_refresh = False

            if self._stop_requested():   # Stop clicked while the model was thinking: skip its tool calls
                return self._stopped(all_executed_actions, steps, set_active_page)

            for fc in function_calls:
                fc_name = fc.name
                fc_args = dict(fc.args) if fc.args else {}

                # Handle meta-tool: request_additional_tools
                if fc_name == 'request_additional_tools':
                    categories = fc_args.get('categories', [])
                    new_categories = [c for c in categories if c not in current_intents]
                    current_intents.update(categories)
                    tools = build_tool_declarations(list(current_intents))
                    result = {
                        'success': True,
                        'message': f'Added tool categories: {", ".join(new_categories)}' if new_categories else 'All requested categories already available.',
                    }
                    function_response_parts.append(
                        types.Part.from_function_response(name=fc_name, response=result)
                    )
                    iteration_actions.append({
                        'tool': fc_name,
                        'params': fc_args,
                        'success': True,
                        'message': result['message'],
                    })
                    continue

                # Execute the tool
                result = ToolRegistry.execute(fc_name, fc_args, context)

                action_record = {
                    'tool': fc_name,
                    'params': fc_args,
                    'success': result.get('success', False),
                    'message': result.get('message', ''),
                }
                # Include query result data for the frontend
                for key in ('pages', 'page', 'menu_items', 'settings', 'images', 'sources', 'answer',
                            'stats', 'page_id', 'menu_item_id', 'form_id',
                            'forms', 'submissions', 'posts', 'post', 'categories'):
                    if key in result:
                        action_record[key] = result[key]

                iteration_actions.append(action_record)

                # Track page switches
                if result.get('set_active_page'):
                    set_active_page = result['set_active_page']
                    self._refresh_context(context, set_active_page)

                # Check if context refresh is needed
                if fc_name in PAGE_CONTEXT_MUTATIONS and result.get('success', False):
                    needs_context_refresh = True

                # Build function response part
                function_response_parts.append(
                    types.Part.from_function_response(name=fc_name, response=result)
                )

            all_executed_actions.extend(iteration_actions)
            steps.append({
                'iteration': iteration + 1,
                'actions': iteration_actions,
            })

            # Append model's response content and function results to contents
            contents.append(model_content)
            contents.append(types.Content(role='user', parts=function_response_parts))

            # Refresh system instruction if page context changed
            if needs_context_refresh:
                # Refresh session's active page from DB
                self.session.refresh_from_db()
                snapshot = build_router_snapshot(self.session)
                system_instruction = build_executor_prompt(
                    self.session, snapshot, has_reference_images=bool(reference_images)
                )
                # Rebuild tools with updated declarations (need to pass new system_instruction)
                tools = build_tool_declarations(list(current_intents))

            iteration += 1

        # Max iterations reached — force a text response
        logger.warning('Max FC iterations reached (%d)', MAX_TOOL_ITERATIONS)
        response_text = 'I ran out of steps before finishing.' + self._report(all_executed_actions)
        self.session.add_message('assistant', response_text, actions=all_executed_actions or None)
        self._auto_title(message)
        return {
            'response': response_text,
            'actions': all_executed_actions,
            'steps': steps,
            'set_active_page': set_active_page,
        }

    def _build_contents(self, message, reference_images=None):
        """Convert session history to Gemini contents format.

        Returns a list of Content objects with role user/model,
        plus the current message as the final user content.
        """
        from google.genai import types

        contents = []
        # Get history messages (excluding the just-added current message)
        messages = self.session.messages[:-1]  # The last one is the current user message we just added

        for msg in messages:
            role = msg.get('role', '')
            content = msg.get('content', '')
            if not content:
                continue

            if role == 'user':
                contents.append(
                    types.Content(role='user', parts=[types.Part.from_text(text=content)])
                )
            elif role == 'assistant':
                contents.append(
                    types.Content(role='model', parts=[types.Part.from_text(text=content)])
                )

        # Add current message, with any attached images/PDFs so the model can see them
        parts = [types.Part.from_text(text=message)]
        for ref in reference_images or []:
            if ref.get('bytes') and ref.get('mime_type'):
                parts.append(types.Part.from_bytes(data=ref['bytes'], mime_type=ref['mime_type']))
        contents.append(types.Content(role='user', parts=parts))

        return contents

    def _refresh_context(self, context, page_id):
        """Refresh active_page in context after a page switch."""
        from djangopress.core.models import Page
        try:
            page = Page.objects.get(pk=page_id)
            context['active_page'] = page
            self.session.set_active_page(page)
        except Page.DoesNotExist:
            pass

    def _auto_title(self, message):
        """Auto-title session on first exchange."""
        if len(self.session.messages) == 2 and not self.session.title:
            self.session.title = message[:100]
            self.session.save(update_fields=['title'])
