"""
Conversation Title Service

Uses a lightweight LLM (gemini-lite) to generate and update conversation titles
based on the conversation content.
"""
from typing import Optional
from .models import Conversation, Message

# How often to update the title (every N user messages)
TITLE_UPDATE_INTERVAL = 5

# Model to use for title generation (lightweight model)
TITLE_MODEL = 'gemini-lite'

# Debug flag
DEBUG_TITLE_SERVICE = True


def debug_print(message: str):
    """Print debug info if enabled"""
    if DEBUG_TITLE_SERVICE:
        print(f"[TITLE] {message}")


class TitleService:
    """
    Service for generating and updating conversation titles.

    Uses gemini-lite for fast, cheap title generation.
    Updates title on first message and every TITLE_UPDATE_INTERVAL user messages.
    """

    def __init__(self, conversation: Conversation):
        self.conversation = conversation

    def should_update_title(self) -> bool:
        """
        Determine if the title should be updated.

        Returns True if:
        - This is the first user message (message count <= 2)
        - User message count is a multiple of TITLE_UPDATE_INTERVAL
        """
        # Count user messages
        user_message_count = self.conversation.messages.filter(role='user').count()

        debug_print(f"User message count: {user_message_count}")

        # Update on first message
        if user_message_count == 1:
            debug_print("First message - should update title")
            return True

        # Update every TITLE_UPDATE_INTERVAL messages
        if user_message_count > 0 and user_message_count % TITLE_UPDATE_INTERVAL == 0:
            debug_print(f"Message count {user_message_count} is multiple of {TITLE_UPDATE_INTERVAL} - should update title")
            return True

        return False

    def generate_title(self) -> Optional[str]:
        """
        Generate a title for the conversation using LLM.

        Returns:
            Generated title string, or None if generation fails
        """
        debug_print("Generating title...")

        try:
            from ai_assistant.llm_config import LLMBase

            # Get recent messages for context (last 10 messages max)
            messages = list(self.conversation.messages.order_by('created_at')[:10])

            if not messages:
                debug_print("No messages to generate title from")
                return None

            # Build context from messages
            context_lines = []
            for msg in messages:
                if msg.role == 'user':
                    context_lines.append(f"User: {msg.content[:500]}")
                elif msg.role == 'assistant':
                    # Only include first part of assistant response
                    content = msg.content[:300]
                    if '---' in content:
                        content = content.split('---')[0]
                    context_lines.append(f"Assistant: {content}")

            conversation_context = "\n".join(context_lines)

            # Build prompt for title generation
            prompt = f"""Generate a short, descriptive title for this conversation (max 50 characters).
The title should capture the main topic or intent of the conversation.
Do not use quotes or special characters. Just output the title text.

Conversation:
{conversation_context}

Title:"""

            debug_print(f"Calling LLM with {len(messages)} messages of context")

            # Call LLM
            llm = LLMBase()
            response = llm.get_completion(
                messages=[
                    {"role": "user", "content": prompt}
                ],
                tool_name=TITLE_MODEL,
            )

            # Extract and clean title
            title = response.choices[0].message.content.strip()

            # Remove quotes if present
            title = title.strip('"\'')

            # Truncate if too long
            if len(title) > 60:
                title = title[:57] + "..."

            debug_print(f"Generated title: {title}")
            return title

        except Exception as e:
            debug_print(f"Error generating title: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    def update_title_if_needed(self) -> bool:
        """
        Check if title should be updated and update it if so.

        Returns:
            True if title was updated, False otherwise
        """
        if not self.should_update_title():
            return False

        new_title = self.generate_title()

        if new_title:
            old_title = self.conversation.title
            self.conversation.title = new_title
            self.conversation.save(update_fields=['title'])
            debug_print(f"Title updated: '{old_title}' -> '{new_title}'")
            return True

        return False


def update_conversation_title(conversation: Conversation) -> bool:
    """
    Convenience function to update a conversation's title if needed.

    Args:
        conversation: The conversation to update

    Returns:
        True if title was updated, False otherwise
    """
    service = TitleService(conversation)
    return service.update_title_if_needed()
