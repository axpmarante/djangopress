"""
Chat Service - Main orchestration for chat functionality

Coordinates between LLM, VEL, and database for chat operations.
"""
import asyncio
import time
import json
from typing import Dict, Any, Optional
from django.utils import timezone

from chat.models import Conversation, Message, ChatVELExecution
from .prompts import build_system_prompt, STRUCTURED_SUMMARY_PROMPT

# Debug flag - set to True to see service details
DEBUG_SERVICE = True


def debug_print(label: str, data: Any = None, separator: bool = False):
    """Print debug info if DEBUG_SERVICE is enabled"""
    if not DEBUG_SERVICE:
        return
    if separator:
        print(f"\n{'='*60}")
        print(f"[SERVICE] {label}")
        print('='*60)
    elif data is not None:
        if isinstance(data, (dict, list)):
            try:
                print(f"[SERVICE] {label}:")
                print(json.dumps(data, indent=2, default=str)[:3000])
            except:
                print(f"[SERVICE] {label}: {str(data)[:1000]}")
        else:
            print(f"[SERVICE] {label}: {data}")
    else:
        print(f"[SERVICE] {label}")


class ChatService:
    """
    Main service for handling chat interactions.
    Coordinates between LLM, VEL, and database.

    Supports internal/public tag system:
    - <internal> tags contain LLM reasoning and VEL commands (hidden from user)
    - <public> tags contain final response for user (shown to user)
    """

    # Maximum iterations for tool loop (prevents runaway costs)
    MAX_TOOL_ITERATIONS = 10

    def __init__(self, user, conversation: Conversation):
        self.user = user
        self.conversation = conversation

    # =========================================================================
    # Internal/Public Tag Processing Methods
    # =========================================================================

    def _extract_internal_content(self, text: str) -> str:
        """Extract content from <internal> tags."""
        import re
        pattern = r'<internal>(.*?)</internal>'
        matches = re.findall(pattern, text, re.DOTALL)
        return '\n'.join(matches).strip()

    def _extract_public_content(self, text: str) -> str:
        """Extract content from <public> tags."""
        import re
        pattern = r'<public>(.*?)</public>'
        matches = re.findall(pattern, text, re.DOTALL)
        return '\n'.join(matches).strip()

    def _has_public_tag(self, text: str) -> bool:
        """Check if response contains a <public> tag."""
        return '<public>' in text and '</public>' in text

    def _has_internal_tag(self, text: str) -> bool:
        """Check if response contains an <internal> tag."""
        return '<internal>' in text and '</internal>' in text

    def _strip_tags(self, text: str) -> str:
        """Remove all internal/public tags from text, keeping content."""
        import re
        # Remove <internal>...</internal> completely (hide reasoning)
        text = re.sub(r'<internal>.*?</internal>', '', text, flags=re.DOTALL)
        # Remove <public> and </public> tags but keep content
        text = re.sub(r'</?public>', '', text)
        return text.strip()

    def _strip_vel_blocks(self, text: str) -> str:
        """Remove VEL command blocks from text (for user-facing content)."""
        import re
        # Remove ```vel ... ``` blocks
        text = re.sub(r'```vel\s*.*?```', '', text, flags=re.DOTALL)
        return text.strip()

    def _has_vel_blocks(self, text: str) -> bool:
        """Check if text contains VEL command blocks."""
        return '```vel' in text

    def send_message(self, user_content: str) -> Dict[str, Any]:
        """
        Process a user message and get AI response with tool loop.

        Flow:
        1. Save user message
        2. Build conversation context
        3. Call LLM
        4. Check for VEL commands in response
        5. If VEL commands found: execute, inject results, loop back to step 3
        6. If no VEL commands: we have final response
        7. Save assistant message
        8. Return formatted response
        """
        debug_print("SEND MESSAGE", separator=True)
        debug_print(f"Conversation ID: {self.conversation.id}")
        debug_print(f"Model: {self.conversation.model_name}")
        debug_print(f"User Content: {user_content[:200]}...")

        # 1. Save user message
        user_message = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content=user_content,
        )
        debug_print(f"User message saved with ID: {user_message.id}")

        try:
            from ai_assistant.llm_config import LLMBase
            from vel.messages import format_many_for_llm
            from vel.schema import ExecutionResult

            llm = LLMBase()

            # Track cumulative tokens across iterations
            total_input_tokens = 0
            total_output_tokens = 0
            total_processing_time = 0

            # Tool loop - continues until <public> tag appears or max iterations
            iteration_count = 0
            messages = self._build_messages()
            has_vel = False
            vel_result = {'has_commands': False}
            all_executions = []  # Collect all executions across iterations

            while iteration_count < self.MAX_TOOL_ITERATIONS:
                iteration_count += 1
                debug_print(f"TOOL LOOP ITERATION {iteration_count}", separator=True)

                debug_print(f"Total messages in conversation: {len(messages)}")
                msg_summary = [{"role": m["role"], "content_length": len(m["content"])} for m in messages]
                debug_print("Message Summary", msg_summary)

                # Call LLM
                debug_print("Calling LLM...", separator=True)
                debug_print(f"Model: {self.conversation.model_name}")
                start_time = time.time()

                response = llm.get_completion(
                    messages=messages,
                    tool_name=self.conversation.model_name,
                )

                processing_time = int((time.time() - start_time) * 1000)
                total_processing_time += processing_time
                assistant_content = response.choices[0].message.content

                debug_print(f"LLM Response Time: {processing_time}ms")
                debug_print(f"Response Length: {len(assistant_content)} chars")
                debug_print("LLM Response Preview (first 500 chars):")
                print("-" * 40)
                print(assistant_content[:500])
                print("-" * 40)

                # Extract token usage
                input_tokens = getattr(response.usage, 'prompt_tokens', 0)
                output_tokens = getattr(response.usage, 'completion_tokens', 0)
                total_input_tokens += input_tokens
                total_output_tokens += output_tokens
                debug_print(f"Input Tokens: {input_tokens}")
                debug_print(f"Output Tokens: {output_tokens}")

                # Check for <public> tag - signals LLM is done with tools
                has_public = self._has_public_tag(assistant_content)
                has_internal = self._has_internal_tag(assistant_content)
                debug_print(f"Has <internal> tag: {has_internal}")
                debug_print(f"Has <public> tag: {has_public}")

                if has_public:
                    debug_print("Found <public> tag, LLM is done - exiting tool loop")
                    break

                # Extract internal content for VEL processing
                # VEL commands should be wrapped in <internal> tags
                content_to_process = assistant_content
                has_raw_vel = self._has_vel_blocks(assistant_content)

                if has_internal:
                    internal_content = self._extract_internal_content(assistant_content)
                    debug_print(f"Extracted internal content ({len(internal_content)} chars)")

                    # Check if VEL blocks are inside or outside internal tags
                    has_vel_in_internal = self._has_vel_blocks(internal_content)

                    if has_vel_in_internal:
                        # VEL is inside internal tags (correct format)
                        content_to_process = internal_content
                    elif has_raw_vel:
                        # VEL blocks are OUTSIDE internal tags (LLM formatting issue)
                        # Use full response for VEL processing
                        debug_print("WARNING: VEL blocks found outside <internal> tags")
                        debug_print("Processing VEL from full response")
                        content_to_process = assistant_content
                    else:
                        content_to_process = internal_content
                elif has_raw_vel:
                    # LLM used old format - VEL without <internal> tags
                    debug_print("WARNING: Raw VEL blocks found without <internal> tags (old format)")
                    debug_print("Processing VEL from full response (backwards compatibility)")

                # Check for VEL commands and execute them
                debug_print("Processing VEL Commands...", separator=True)
                vel_result = self._process_vel_commands(content_to_process)
                debug_print("VEL Result", vel_result)

                has_vel = vel_result.get('has_commands', False)

                # Check for VEL processing errors (exception during processing)
                if vel_result.get('error') and not has_vel:
                    debug_print(f"VEL processing error detected: {vel_result['error']}")
                    # Inject error feedback to LLM so it can retry
                    errors = self._extract_vel_errors(vel_result)
                    if errors:
                        error_feedback = self._format_vel_error_feedback(errors)
                        messages.append({'role': 'assistant', 'content': assistant_content})
                        messages.append({'role': 'user', 'content': error_feedback})
                        debug_print("Injected error feedback, continuing to let LLM retry...")
                        continue

                # If VEL commands were executed, inject results and continue loop
                if has_vel and vel_result.get('executions'):
                    debug_print(f"VEL commands found, injecting results for next iteration...")

                    # Collect executions for final save
                    all_executions.extend(vel_result.get('executions', []))

                    # Check if there are execution errors
                    vel_errors = self._extract_vel_errors(vel_result)
                    if vel_errors:
                        debug_print(f"VEL execution errors found: {vel_errors}")

                    # Add assistant message with VEL commands to context
                    messages.append({'role': 'assistant', 'content': assistant_content})

                    # Convert execution data to ExecutionResult objects for formatter
                    execution_results = []
                    for ex in vel_result['executions']:
                        execution_results.append(ExecutionResult(
                            action=ex['action'],
                            status=ex['status'],
                            audit_id=ex.get('audit_id', ''),
                            executed_at='',
                            result=ex.get('result_data'),
                            error=ex.get('error'),
                        ))

                    # Format results using existing MessageFormatter (includes errors)
                    vel_message = format_many_for_llm(execution_results)
                    messages.append(vel_message.to_dict())

                    debug_print(f"Injected VEL results message, continuing to iteration {iteration_count + 1}...")
                    continue

                # No VEL commands and no <public> tag - unexpected state
                # Fallback: treat entire response as final
                debug_print("WARNING: No VEL commands and no <public> tag - using fallback")
                break

            # Check if we hit max iterations - make final summary call
            if iteration_count >= self.MAX_TOOL_ITERATIONS and has_vel:
                debug_print(f"WARNING: Max tool iterations ({self.MAX_TOOL_ITERATIONS}) reached")
                debug_print("Making final summary call to LLM...")

                # Build summary of executed actions
                actions_summary = []
                for ex in all_executions:
                    status_icon = "✅" if ex.get('status') == 'success' else "❌"
                    actions_summary.append(f"{status_icon} {ex.get('action')}: {ex.get('result_summary', 'completed')[:100]}")

                summary_text = "\n".join(actions_summary) if actions_summary else "No actions completed."

                # Inject summary request
                summary_request = f"""[SYSTEM: Maximum tool iterations ({self.MAX_TOOL_ITERATIONS}) reached]

You have been working on the user's request but haven't completed yet. Here's what you've done so far:

{summary_text}

Please provide a response to the user that:
1. Summarizes what you accomplished
2. Explains what still needs to be done (if anything)
3. Asks for clarification or more specific instructions if needed

Respond directly to the user in a helpful way. Do NOT use VEL commands in this response."""

                messages.append({'role': 'assistant', 'content': assistant_content})
                messages.append({'role': 'user', 'content': summary_request})

                # Make final LLM call
                start_time = time.time()
                response = llm.get_completion(
                    messages=messages,
                    tool_name=self.conversation.model_name,
                )
                processing_time = int((time.time() - start_time) * 1000)
                total_processing_time += processing_time
                assistant_content = response.choices[0].message.content

                # Update token counts
                total_input_tokens += getattr(response.usage, 'prompt_tokens', 0)
                total_output_tokens += getattr(response.usage, 'completion_tokens', 0)

                debug_print(f"Final summary response received ({len(assistant_content)} chars)")

            # Process final response - extract only <public> content for user
            if self._has_public_tag(assistant_content):
                final_content = self._extract_public_content(assistant_content)
                debug_print(f"Extracted <public> content ({len(final_content)} chars)")
            else:
                # Fallback: strip any tags and use remaining content
                final_content = self._strip_tags(assistant_content)
                debug_print("Fallback: stripped tags from response")

            # Safety: always strip any remaining VEL blocks from user-facing content
            if self._has_vel_blocks(final_content):
                debug_print("WARNING: VEL blocks found in final content, stripping them")
                final_content = self._strip_vel_blocks(final_content)

            # If final content is empty after stripping, provide a fallback message
            if not final_content.strip():
                debug_print("WARNING: Final content is empty after stripping")
                # This shouldn't happen if VEL processing works correctly
                # Provide a helpful fallback message
                if has_vel and all_executions:
                    final_content = "I've completed the requested actions. Is there anything else you'd like me to do?"
                else:
                    final_content = "I'm sorry, I couldn't process that request properly. Could you please try rephrasing?"

            vel_session_id = vel_result.get('session_id', '')

            # ================================================================
            # PHASE 2: VEL Gate Validation (ALWAYS runs to catch hallucinations)
            # ================================================================
            # Always validate responses to catch cases where LLM claims success
            # without actually executing VEL commands (hallucination prevention)
            debug_print("VEL GATE VALIDATION", separator=True)
            final_content, gated_result = self._apply_vel_gate(
                final_content=final_content,
                all_executions=all_executions,
                messages=messages,
                assistant_content=assistant_content,
                llm=llm,
                correlation_id=vel_session_id or 'no-vel-session',
            )
            debug_print(f"VEL gate was_overridden: {gated_result.get('was_overridden', False)}")
            debug_print(f"VEL gate receipts_matched: {gated_result.get('receipts_matched', True)}")
            debug_print(f"VEL gate verification_passed: {gated_result.get('verification_passed', True)}")

            # ================================================================
            # RETRY: If VEL Gate detected write hallucination (claimed success but no VEL)
            # ================================================================
            vel_gate_retry_count = 0
            MAX_VEL_GATE_RETRIES = 2

            while (gated_result.get('was_overridden', False) and
                   not gated_result.get('receipts_matched', True) and
                   len(all_executions) == 0 and
                   vel_gate_retry_count < MAX_VEL_GATE_RETRIES):

                vel_gate_retry_count += 1
                debug_print(f"VEL GATE RETRY {vel_gate_retry_count}", separator=True)
                debug_print("LLM claimed success but no VEL was executed - retrying with correction")

                # Write hallucination - LLM claimed to perform an action without executing
                correction_prompt = """Your previous response claimed to perform an action, but NO VEL command was actually executed.

You MUST emit a VEL command inside <internal> tags to perform the action. Do NOT just say you did it - actually do it.

Example of what you MUST do:
<internal>
Executing the action now.
```vel
{"action": "create_task", "params": {"title": "...", ...}}
```
</internal>

Now execute the VEL command for the user's original request."""

                messages.append({'role': 'assistant', 'content': assistant_content})
                messages.append({'role': 'user', 'content': correction_prompt})

                # Re-run tool loop iteration
                debug_print("Re-running LLM with correction...")
                start_time = time.time()
                response = llm.get_completion(
                    messages=messages,
                    tool_name=self.conversation.model_name,
                )
                processing_time = int((time.time() - start_time) * 1000)
                total_processing_time += processing_time
                assistant_content = response.choices[0].message.content

                debug_print(f"Retry LLM Response Time: {processing_time}ms")
                debug_print(f"Retry Response Preview: {assistant_content[:500]}")

                # Update token counts
                input_tokens = getattr(response.usage, 'prompt_tokens', 0)
                output_tokens = getattr(response.usage, 'completion_tokens', 0)
                total_input_tokens += input_tokens
                total_output_tokens += output_tokens

                # Process VEL commands from retry
                content_to_process = assistant_content
                if self._has_internal_tag(assistant_content):
                    internal_content = self._extract_internal_content(assistant_content)
                    if self._has_vel_blocks(internal_content):
                        content_to_process = internal_content
                    elif self._has_vel_blocks(assistant_content):
                        content_to_process = assistant_content
                    else:
                        content_to_process = internal_content

                vel_result = self._process_vel_commands(content_to_process)
                debug_print("Retry VEL Result", vel_result)

                if vel_result.get('has_commands', False):
                    # Collect executions from retry
                    retry_executions = vel_result.get('executions', [])
                    all_executions.extend(retry_executions)
                    has_vel = True

                    # Re-inject VEL results to LLM for final response
                    vel_feedback = self._format_vel_result_feedback(vel_result)
                    messages.append({'role': 'assistant', 'content': assistant_content})
                    messages.append({'role': 'user', 'content': vel_feedback})

                    # Get final response after VEL execution
                    response = llm.get_completion(
                        messages=messages,
                        tool_name=self.conversation.model_name,
                    )
                    assistant_content = response.choices[0].message.content
                    total_input_tokens += getattr(response.usage, 'prompt_tokens', 0)
                    total_output_tokens += getattr(response.usage, 'completion_tokens', 0)

                # Extract final content
                if self._has_public_tag(assistant_content):
                    final_content = self._extract_public_content(assistant_content)
                else:
                    final_content = self._strip_tags(assistant_content)
                final_content = self._strip_vel_blocks(final_content)

                # Update vel_session_id
                vel_session_id = vel_result.get('session_id', '') or vel_session_id

                # Re-run VEL Gate validation
                debug_print("Re-running VEL Gate after retry...")
                final_content, gated_result = self._apply_vel_gate(
                    final_content=final_content,
                    all_executions=all_executions,
                    messages=messages,
                    assistant_content=assistant_content,
                    llm=llm,
                    correlation_id=vel_session_id or 'retry-vel-session',
                )
                debug_print(f"Retry VEL gate was_overridden: {gated_result.get('was_overridden', False)}")
                debug_print(f"Retry VEL gate receipts_matched: {gated_result.get('receipts_matched', True)}")

            if vel_gate_retry_count > 0:
                debug_print(f"VEL Gate retry completed after {vel_gate_retry_count} attempts")

            debug_print(f"Final has_vel: {has_vel}")
            debug_print(f"Total iterations: {iteration_count}")
            if vel_result.get('summary'):
                debug_print(f"Final VEL Summary: {vel_result['summary']}")

            # Don't append execution summary to final response - the LLM should include the data in its response
            # The old behavior appended "Actions Executed: ✅" but now the LLM has the actual data

            # Save final assistant message
            debug_print("Saving assistant message...")
            assistant_message = Message.objects.create(
                conversation=self.conversation,
                role='assistant',
                content=final_content,
                model_used=self.conversation.model_name,
                processing_time_ms=total_processing_time,
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                has_vel_commands=len(all_executions) > 0,
                vel_session_id=vel_session_id,
            )
            debug_print(f"Assistant message saved with ID: {assistant_message.id}")

            # Save all VEL executions from all iterations
            if all_executions:
                debug_print(f"Saving {len(all_executions)} VEL execution records...")
                self._save_vel_executions(assistant_message, all_executions)

            # Update conversation
            self.conversation.last_message_at = timezone.now()
            self.conversation.total_input_tokens += total_input_tokens
            self.conversation.total_output_tokens += total_output_tokens
            self.conversation.save(update_fields=[
                'last_message_at', 'total_input_tokens', 'total_output_tokens'
            ])

            # Update title using AI summarization
            debug_print("Checking if title needs update...")
            from chat.title_service import update_conversation_title
            title_updated = update_conversation_title(self.conversation)
            if title_updated:
                debug_print(f"Title updated to: {self.conversation.title}")

            # Return response
            debug_print("SEND MESSAGE COMPLETE", separator=True)
            debug_print(f"Total Processing Time: {total_processing_time}ms")
            debug_print(f"Total Tokens: {total_input_tokens + total_output_tokens}")
            debug_print(f"Tool Loop Iterations: {iteration_count}")

            return {
                'success': True,
                'message': {
                    'id': assistant_message.id,
                    'role': 'assistant',
                    'content': final_content,
                    'created_at': assistant_message.created_at.isoformat(),
                    'has_vel_commands': len(all_executions) > 0,
                    'processing_time_ms': total_processing_time,
                },
                'token_usage': {
                    'input': total_input_tokens,
                    'output': total_output_tokens,
                    'conversation_total_input': self.conversation.total_input_tokens,
                    'conversation_total_output': self.conversation.total_output_tokens,
                },
                'vel_executions': [
                    {
                        'action': ex.get('action'),
                        'status': ex.get('status'),
                        'link': self._get_execution_link(ex),
                    }
                    for ex in all_executions
                ] if all_executions else [],
                'confirmations_pending': vel_result.get('confirmation_tokens', {}),
                'tool_iterations': iteration_count,
            }

        except Exception as e:
            debug_print(f"ERROR in send_message: {str(e)}")
            import traceback
            traceback.print_exc()
            # Save error message
            error_message = Message.objects.create(
                conversation=self.conversation,
                role='assistant',
                content=f"I apologize, but I encountered an error: {str(e)}",
                is_error=True,
                error_message=str(e),
            )

            return {
                'success': False,
                'error': str(e),
                'message': {
                    'id': error_message.id,
                    'role': 'assistant',
                    'content': error_message.content,
                    'created_at': error_message.created_at.isoformat(),
                    'is_error': True,
                }
            }

    def _extract_vel_errors(self, vel_result: Dict[str, Any]) -> list:
        """Extract error messages from VEL execution results."""
        errors = []
        if not vel_result.get('has_commands'):
            return errors

        for execution in vel_result.get('executions', []):
            if execution.get('status') == 'error':
                action = execution.get('action', 'unknown')
                error_msg = execution.get('result_summary', 'Unknown error')
                errors.append(f"{action}: {error_msg}")

        # Also check for VEL processing errors
        if vel_result.get('error'):
            errors.append(f"VEL Processing: {vel_result['error']}")

        return errors

    def _format_vel_error_feedback(self, errors: list) -> str:
        """Format VEL errors as feedback for the LLM to correct its actions."""
        error_list = '\n'.join(f"- {error}" for error in errors)
        return f"""[SYSTEM ERROR FEEDBACK]

The following VEL action(s) failed:
{error_list}

Please review the error(s) above and try again with corrected action syntax. Common issues:
1. Action name might be misspelled - check the available actions in your system prompt
2. Required parameters might be missing
3. Parameter values might be in wrong format (e.g., string instead of number)
4. The referenced resource (note, project, area, task) might not exist

Please retry your response with corrected VEL commands."""

    def _format_vel_result_feedback(self, vel_result: Dict[str, Any]) -> str:
        """Format VEL execution results as feedback for the LLM to generate final response."""
        executions = vel_result.get('executions', [])
        if not executions:
            return "[VEL Result] No operations were executed."

        results = []
        for ex in executions:
            status = ex.get('status', 'unknown')
            action = ex.get('action', 'unknown')
            result_data = ex.get('result_data', {})

            if status == 'success':
                # Include key info from result_data
                result_id = result_data.get('id', 'N/A')
                title = result_data.get('title', result_data.get('name', ''))
                results.append(f"✅ {action}: SUCCESS (ID: {result_id}, title: '{title}')")
            else:
                error_msg = ex.get('result_summary', 'Unknown error')
                results.append(f"❌ {action}: FAILED - {error_msg}")

        results_text = '\n'.join(results)
        return f"""[VEL Result]
{results_text}

Now provide a <public> response to the user summarizing what was done."""

    def _build_messages(self) -> list:
        """Build message list for LLM including system prompt and history"""
        messages = []

        # System prompt with full context
        system_prompt = build_system_prompt(self.user, self.conversation)
        messages.append({
            'role': 'system',
            'content': system_prompt
        })

        # Add conversation history
        for msg in self.conversation.messages.all():
            # Skip system messages from VEL execution results in history
            if msg.role == 'system':
                continue
            messages.append({
                'role': msg.role,
                'content': msg.content
            })

        return messages

    def _process_vel_commands(self, text: str) -> Dict[str, Any]:
        """
        Process VEL commands from LLM response.

        Uses asyncio to run the async VEL processor.
        """
        debug_print("VEL PROCESSING", separator=True)
        debug_print(f"Checking text for VEL commands ({len(text)} chars)")

        # Check if text contains VEL markers
        if '```vel' in text:
            debug_print("Found ```vel marker in text")
            # Extract and show VEL blocks
            import re
            vel_blocks = re.findall(r'```vel\s*(.*?)\s*```', text, re.DOTALL)
            for i, block in enumerate(vel_blocks):
                debug_print(f"VEL Block {i+1}: {block[:200]}")

        try:
            from vel.chat import VELProcessor

            processor = VELProcessor(
                user=self.user,
                secure=True,
                session_id=f"chat_{self.conversation.id}",
            )

            # Check if there are commands first
            has_commands = processor.check_for_commands(text)
            debug_print(f"VEL check_for_commands result: {has_commands}")

            if not has_commands:
                debug_print("No VEL commands found")
                return {'has_commands': False}

            # Run async processor
            debug_print("Running VEL processor...")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(processor.process(text))
            finally:
                loop.close()

            debug_print(f"VEL processing complete. has_commands: {result.has_commands}")

            if not result.has_commands:
                debug_print("VEL processor returned no commands")
                return {'has_commands': False}

            # Format results
            debug_print(f"Processing {len(result.executions)} VEL executions")
            summary_lines = []
            executions_data = []

            for i, execution in enumerate(result.executions):
                debug_print(f"Execution {i+1}: action={execution.action}, status={execution.status}")
                exec_data = {
                    'action': execution.action,
                    'status': execution.status,
                    'audit_id': execution.audit_id or '',
                    'result_summary': '',
                    'requires_confirmation': False,
                    'confirmation_token': '',
                }

                if execution.status == 'success':
                    summary_lines.append(f"✅ **{execution.action}**: Completed successfully")
                    # Capture full result data for LLM injection
                    exec_data['result_data'] = execution.result
                    if execution.result:
                        exec_data['result_summary'] = str(execution.result)[:500]
                elif execution.status == 'confirmation_required':
                    summary_lines.append(f"⚠️ **{execution.action}**: Requires confirmation")
                    exec_data['requires_confirmation'] = True
                    exec_data['result_data'] = execution.result
                    if execution.result and execution.result.get('token'):
                        exec_data['confirmation_token'] = execution.result['token']
                elif execution.status == 'error':
                    error_msg = 'Unknown error'
                    if execution.error:
                        error_msg = execution.error.get('message', str(execution.error))
                    summary_lines.append(f"❌ **{execution.action}**: Failed - {error_msg}")
                    # Capture full error dict for LLM injection
                    exec_data['error'] = execution.error
                    exec_data['result_summary'] = error_msg
                elif execution.status == 'denied':
                    reason = 'Permission denied'
                    if execution.error:
                        reason = execution.error.get('message', str(execution.error))
                    summary_lines.append(f"🚫 **{execution.action}**: Denied - {reason}")
                    exec_data['error'] = execution.error
                    exec_data['result_summary'] = reason
                else:
                    summary_lines.append(f"ℹ️ **{execution.action}**: {execution.status}")

                executions_data.append(exec_data)

            vel_return = {
                'has_commands': True,
                'session_id': result.session_id,
                'summary': '\n'.join(summary_lines),
                'executions': executions_data,
                'confirmation_tokens': result.confirmation_tokens,
            }
            debug_print("VEL Processing Complete", vel_return)
            return vel_return

        except ImportError as e:
            # VEL not available
            debug_print(f"VEL ImportError: {e}")
            return {'has_commands': False, 'error': str(e)}
        except Exception as e:
            # Log error but don't fail the whole response
            debug_print(f"VEL processing error: {e}")
            import traceback
            traceback.print_exc()
            return {'has_commands': False, 'error': str(e)}

    def _save_vel_executions(self, message: Message, executions: list):
        """Save VEL execution records"""
        for exec_data in executions:
            ChatVELExecution.objects.create(
                message=message,
                audit_id=exec_data.get('audit_id', ''),
                action=exec_data.get('action', ''),
                status=exec_data.get('status', 'error'),
                result_summary=exec_data.get('result_summary', ''),
                result_data=exec_data.get('result_data', {}),
                requires_confirmation=exec_data.get('requires_confirmation', False),
                confirmation_token=exec_data.get('confirmation_token', ''),
            )

    def _get_execution_link(self, exec_data: dict) -> dict | None:
        """Generate link data for an execution's created/affected item."""
        if exec_data.get('status') != 'success':
            return None

        result = exec_data.get('result_data', {})
        if not result:
            return None

        action = exec_data.get('action', '')

        # Map actions to their URL patterns
        action_urls = {
            'create_note': '/notes/{id}/',
            'get_note': '/notes/{id}/',
            'update_note': '/notes/{id}/',
            'move_note': '/notes/{id}/',
            'archive_note': '/notes/{id}/',
            'create_project': '/para/projects/{id}/',
            'get_project': '/para/projects/{id}/',
            'update_project': '/para/projects/{id}/',
            'create_area': '/para/areas/{id}/',
            'get_area': '/para/areas/{id}/',
            'update_area': '/para/areas/{id}/',
            # Task actions - use tasks app URLs
            'create_task': '/tasks/{id}/',
            'get_task': '/tasks/{id}/',
            'update_task': '/tasks/{id}/',
            'move_task': '/tasks/{id}/',
            'complete_task': '/tasks/{id}/',
            'start_task': '/tasks/{id}/',
            'uncomplete_task': '/tasks/{id}/',
        }

        if action in action_urls and result.get('id'):
            return {
                'url': action_urls[action].format(id=result['id']),
                'title': result.get('title', result.get('name', f'Item #{result["id"]}')),
            }
        return None

    def _apply_vel_gate(
        self,
        final_content: str,
        all_executions: list,
        messages: list,
        assistant_content: str,
        llm,
        correlation_id: str,
    ) -> tuple[str, dict]:
        """
        Apply VEL gate validation to the final response.

        This implements Phase 2 of the two-phase approach:
        1. Get structured response from LLM with explicit success claims
        2. Validate claims against actual execution receipts
        3. Override with deterministic message if mismatch detected

        Args:
            final_content: The extracted <public> content from Phase 1
            all_executions: List of VEL execution data from Phase 1
            messages: The conversation messages up to this point
            assistant_content: The full assistant response from Phase 1
            llm: The LLM instance for Phase 2 call
            correlation_id: Session ID for tracing

        Returns:
            Tuple of (validated_content, gate_result_dict)
        """
        try:
            from vel.gate import (
                VELGate,
                StructuredLLMResponse,
                IntentType,
                STRUCTURED_RESPONSE_SCHEMA,
                build_receipts_from_executions,
            )

            debug_print("Phase 2: Getting structured LLM response...")

            # Build Phase 2 messages - include the VEL results context
            phase2_messages = messages.copy()
            phase2_messages.append({'role': 'assistant', 'content': assistant_content})
            phase2_messages.append({'role': 'user', 'content': STRUCTURED_SUMMARY_PROMPT})

            # Call LLM with structured output format
            try:
                response = llm.get_completion(
                    messages=phase2_messages,
                    tool_name=self.conversation.model_name,
                    response_format=STRUCTURED_RESPONSE_SCHEMA,
                )
                structured_json = response.choices[0].message.content
                debug_print(f"Phase 2 LLM response: {structured_json[:500]}")

                # Parse structured response
                structured_data = json.loads(structured_json)
                structured_response = StructuredLLMResponse.from_dict(structured_data)
                debug_print(f"Parsed: references_success={structured_response.references_success}, "
                           f"resource_ids={structured_response.resource_ids_mentioned}")

            except json.JSONDecodeError as e:
                debug_print(f"Phase 2 JSON parse error: {e}")
                # Fallback: create a response that doesn't claim success
                structured_response = StructuredLLMResponse(
                    intent=IntentType.UNKNOWN,
                    requires_confirmation=False,
                    message_to_user=final_content,
                    references_success=False,
                    resource_ids_mentioned=[],
                )
            except Exception as e:
                debug_print(f"Phase 2 LLM call error: {e}")
                # Fallback: use original content with no success claim
                structured_response = StructuredLLMResponse(
                    intent=IntentType.UNKNOWN,
                    requires_confirmation=False,
                    message_to_user=final_content,
                    references_success=False,
                    resource_ids_mentioned=[],
                )

            # Build receipts from executions
            receipts = build_receipts_from_executions(all_executions)
            debug_print(f"Built {len(receipts)} receipts from executions")
            for r in receipts:
                debug_print(f"  Receipt: {r.action} -> {r.status.value}, id={r.resource_id}")

            # Apply VEL gate validation
            vel_gate = VELGate(user=self.user)
            gated = vel_gate.gate(
                structured_response=structured_response,
                receipts=receipts,
                correlation_id=correlation_id or 'unknown',
            )

            debug_print(f"VEL Gate result: was_overridden={gated.was_overridden}, "
                       f"receipts_matched={gated.receipts_matched}, "
                       f"verification_passed={gated.verification_passed}")

            return gated.validated_response, {
                'was_overridden': gated.was_overridden,
                'receipts_matched': gated.receipts_matched,
                'verification_passed': gated.verification_passed,
                'correlation_id': gated.correlation_id,
            }

        except ImportError as e:
            debug_print(f"VEL gate import error: {e}")
            # If gate not available, return original content
            return final_content, {'was_overridden': False, 'error': str(e)}
        except Exception as e:
            debug_print(f"VEL gate error: {e}")
            import traceback
            traceback.print_exc()
            # On error, return original content (fail open for now)
            return final_content, {'was_overridden': False, 'error': str(e)}

    def confirm_action(self, token: str) -> Dict[str, Any]:
        """Confirm a pending VEL action"""
        debug_print("CONFIRM ACTION", separator=True)
        debug_print(f"Confirmation Token: {token}")

        try:
            from vel.chat import VELProcessor

            processor = VELProcessor(
                user=self.user,
                secure=True,
                session_id=f"chat_{self.conversation.id}",
            )

            # Run async confirmation
            debug_print("Running VEL confirmation...")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    processor.process("", confirmation_token=token)
                )
            finally:
                loop.close()

            debug_print(f"Confirmation result: {len(result.executions)} executions")

            # Update execution record
            ChatVELExecution.objects.filter(
                confirmation_token=token,
                message__conversation=self.conversation
            ).update(
                confirmed=True,
                confirmed_at=timezone.now(),
                status='confirmed'
            )

            # Add system message about confirmation
            if result.executions:
                execution = result.executions[0]
                if execution.status == 'success':
                    content = f"✅ Action `{execution.action}` has been confirmed and executed successfully."
                else:
                    error_msg = execution.error.get('message', 'Unknown error') if execution.error else 'Unknown error'
                    content = f"❌ Action `{execution.action}` failed: {error_msg}"

                Message.objects.create(
                    conversation=self.conversation,
                    role='system',
                    content=content,
                )

            confirm_result = {
                'success': True,
                'result': {
                    'action': result.executions[0].action if result.executions else 'unknown',
                    'status': result.executions[0].status if result.executions else 'error',
                }
            }
            debug_print("Confirmation Complete", confirm_result)
            return confirm_result

        except Exception as e:
            debug_print(f"Confirmation Error: {e}")
            return {
                'success': False,
                'error': str(e),
            }

    def cancel_action(self, token: str) -> Dict[str, Any]:
        """Cancel a pending VEL action"""
        debug_print("CANCEL ACTION", separator=True)
        debug_print(f"Cancellation Token: {token}")

        # Update execution record
        updated = ChatVELExecution.objects.filter(
            confirmation_token=token,
            message__conversation=self.conversation,
            confirmed=False
        ).update(status='cancelled')

        debug_print(f"Records updated: {updated}")

        if updated:
            Message.objects.create(
                conversation=self.conversation,
                role='system',
                content="Action cancelled by user.",
            )
            debug_print("Cancellation message added")

        cancel_result = {
            'success': True,
            'cancelled': updated > 0
        }
        debug_print("Cancel Complete", cancel_result)
        return cancel_result


def get_or_create_conversation(user, context_type='general', context_id=None, model_name='gemini-flash') -> Conversation:
    """
    Helper to get or create a conversation.

    Args:
        user: Django user
        context_type: 'general', 'project', or 'area'
        context_id: ID of the project or area (if scoped)
        model_name: LLM model to use

    Returns:
        Conversation instance
    """
    return Conversation.objects.create(
        user=user,
        title="New Conversation",
        context_type=context_type,
        context_id=context_id,
        model_name=model_name,
        last_message_at=timezone.now(),
    )
