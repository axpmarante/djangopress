"""Router — Phase 1 of the site assistant.

Lightweight intent classifier using gemini-lite. Determines which tool
categories the executor needs, or responds directly for greetings/questions.
"""

import json
import logging
from djangopress.ai.utils.llm_config import LLMBase, get_ai_model

logger = logging.getLogger(__name__)

ROUTER_PROMPT = """You classify site management requests for {site_name}.
Respond ONLY with valid JSON, no other text.

Site: {page_count} pages, {menu_count} menu items, {image_count} images
Pages: {page_names}
Active page: {active_page}
Apps: {apps}
Default language: {default_lang}

Categories:
- greeting: Greetings, thanks, general chat
- question: Questions answerable from the snapshot above
- pages: Create, list, find, delete, reorder pages
- page_edit: Modify sections/styles/text on the active page
- navigation: Menu items, links, navigation structure
- settings: Site config, contact info, design system colors/fonts, briefing
- header_footer: Regenerate or edit header/footer with AI
- forms: Dynamic forms and submissions
- media: Browse/search image library
- news: Blog/news posts and categories
- properties: Rental properties — list, search, update, embed property cards in pages
- stats: Detailed site statistics

Rules:
- If greeting or answerable from snapshot, write answer in direct_response (in {default_lang}).
- If it needs tools, set direct_response to null.
- A request can need multiple categories.
- "delete" requests need the relevant category.

Output JSON:
{{"intents": ["category1", ...], "needs_active_page": bool, "direct_response": "text or null"}}

{history_section}"""


class Router:

    @staticmethod
    def classify(message, snapshot, history=''):
        """Classify a user message into intents.

        Args:
            message: User's message text.
            snapshot: Dict from SettingsService.get_snapshot()['snapshot'].
            history: Compact conversation history string.

        Returns:
            Dict with 'intents' (list), 'needs_active_page' (bool),
            'direct_response' (str or None).
        """
        default_lang = snapshot.get('default_language', 'pt')
        site_name = snapshot.get('site_name', 'Website')

        # Format page names compactly
        pages = snapshot.get('pages', [])
        page_names = ', '.join(
            f"#{p['id']} {p['title']}" for p in pages[:20]
        ) if pages else 'none'

        history_section = f'Conversation context:\n{history}' if history else ''

        prompt = ROUTER_PROMPT.format(
            site_name=site_name,
            page_count=len(pages),
            menu_count=snapshot.get('stats', {}).get('total_menu_items', 0),
            image_count=snapshot.get('stats', {}).get('total_images', 0),
            page_names=page_names,
            active_page=snapshot.get('active_page', 'none selected'),
            apps=', '.join(snapshot.get('installed_apps', [])) or 'none',
            default_lang=default_lang,
            history_section=history_section,
        )

        llm = LLMBase()
        messages = [
            {'role': 'system', 'content': prompt},
            {'role': 'user', 'content': message},
        ]

        try:
            response = llm.get_completion(messages, tool_name=get_ai_model('assistant_router'))
            raw = response.choices[0].message.content.strip()

            # Parse JSON from response (handle markdown code blocks)
            if raw.startswith('```'):
                raw = raw.split('\n', 1)[1].rsplit('```', 1)[0]
            result = json.loads(raw)

            return {
                'intents': result.get('intents', []),
                'needs_active_page': result.get('needs_active_page', False),
                'direct_response': result.get('direct_response'),
            }
        except (json.JSONDecodeError, Exception) as e:
            logger.warning('Router classification failed: %s', e)
            # Fallback: assume it needs all tools
            return {
                'intents': ['pages', 'navigation', 'settings'],
                'needs_active_page': False,
                'direct_response': None,
            }
