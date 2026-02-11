"""Prompt builder for the Site Assistant."""

from bs4 import BeautifulSoup
from core.models import SiteSettings


TOOL_DEFINITIONS = """
## Available Tools

### Site-Wide Tools (always available)

- `list_pages` — List all pages. No params.
- `get_page_info` — Get page details + section names. Params: `{"page_id": int}` OR `{"title": "search string"}` (case-insensitive title search across all languages)
- `create_page` — Create a new page. Params: `{"title_i18n": {"pt": "...", "en": "..."}, "slug_i18n": {"pt": "...", "en": "..."}}`. Auto-sets as active page.
- `update_page_meta` — Update page metadata. Params: `{"page_id": int, "title_i18n": {...}, "slug_i18n": {...}, "is_active": bool, "sort_order": int}` (all optional except page_id)
- `delete_page` — Delete a page. Params: `{"page_id": int}`. DESTRUCTIVE — requires confirmation.
- `reorder_pages` — Set page sort order. Params: `{"order": [{"page_id": int, "sort_order": int}, ...]}`
- `list_menu_items` — List navigation items with hierarchy. No params.
- `create_menu_item` — Create nav item. Params: `{"label_i18n": {"pt": "...", "en": "..."}, "page_id": int, "url": "...", "parent_id": int, "sort_order": int}` (page_id or url required)
- `update_menu_item` — Update nav item. Params: `{"menu_item_id": int, ...fields to update}`
- `delete_menu_item` — Delete nav item. Params: `{"menu_item_id": int}`. DESTRUCTIVE — requires confirmation.
- `get_settings` — Read site settings. Params: `{"fields": ["field1", "field2"]}` (optional, returns all if omitted)
- `update_settings` — Update settings. Params: `{"updates": {"field": "value"}}`. Allowed fields: contact_email, contact_phone, site_name_i18n, site_description_i18n, contact_address_i18n, facebook_url, instagram_url, linkedin_url, twitter_url, youtube_url, google_maps_embed_url, maintenance_mode.
- `list_images` — Browse media library. Params: `{"search": "...", "limit": int}` (optional)
- `list_contacts` — Recent contact form submissions. Params: `{"limit": int}` (optional)
- `get_stats` — Page/image/contact counts. No params.
- `set_active_page` — Switch focus to a specific page. Params: `{"page_id": int}`

### Page-Level Tools (require active page)

- `update_translations` — Change text content directly. Params: `{"updates": {"en": {"hero_title": "New Title"}, "pt": {"hero_title": "Novo Título"}}}`. Fastest way to change text — no AI call needed.
- `update_element_styles` — Change CSS classes. Params: `{"element_id": "...", "new_classes": "text-4xl font-bold text-blue-600"}` or `{"section_name": "...", "new_classes": "..."}`.
- `update_element_attribute` — Change href, src, etc. Params: `{"element_id": "...", "attribute": "href", "value": "/new-url/"}`.
- `remove_section` — Delete a section. Params: `{"section_name": "..."}`.
- `reorder_sections` — Reorder sections. Params: `{"order": ["hero", "features", "cta"]}`.
- `refine_section` — AI-regenerate ONE section. Params: `{"section_name": "...", "instructions": "..."}`. Uses AI — slower and costlier. Use only when structural changes are needed.
- `refine_page` — AI-regenerate entire page. Params: `{"instructions": "..."}`. Most expensive. Use only for major redesigns.
"""

RESPONSE_PROTOCOL = """
## Response Format

You can respond in two modes:

### Mode 1 — Tool call (when you need to see results first):
Output ONLY <actions> with NO <response> tag. The tools will execute and you'll see the results before responding.

<actions>
[{"tool": "tool_name", "params": {...}}]
</actions>

### Mode 2 — Final response (when you have your answer):
Output <response> with optional <actions>.

<response>
Your message to the user.
</response>

<actions>
[{"tool": "tool_name", "params": {...}}]
</actions>

### Destructive actions (delete_page, delete_menu_item):
Output <response> with <pending_confirmation>. No <actions> tag.

<response>
Are you sure you want to delete "Page Name"? This cannot be undone.
</response>

<pending_confirmation>
{"tool": "delete_page", "params": {"page_id": 5}}
</pending_confirmation>

RULES:
- When you need data (list_pages, get_page_info, get_settings, get_stats, list_menu_items, list_images, list_contacts), use Mode 1 FIRST to see results, then respond with Mode 2.
- When you can act without needing to see results first (update_translations, create_page with known params, etc.), use Mode 2 directly with <response> and <actions>.
- You can chain multiple tool calls: Mode 1 → see results → Mode 1 again → see results → Mode 2.
- Maximum 8 tool-call rounds before you must give a final <response>.
- Multiple actions can be in one <actions> list — they execute sequentially.
- Use the LIGHTEST tool possible. For text changes, use `update_translations` (free, instant). Only use `refine_section` or `refine_page` when structural/design changes are needed.
- For destructive operations (delete_page, delete_menu_item), ALWAYS use <pending_confirmation> instead of <actions>.
- Provide all i18n fields in ALL enabled languages when creating/updating content.
- When you execute a write action, you MUST include the tool call in <actions>. Never claim you performed an action without actually calling the tool.
"""


def build_page_context(page):
    """Build a compact page context for the LLM (sections + translations + elements)."""
    if not page or not page.html_content:
        return "Page has no content yet."

    soup = BeautifulSoup(page.html_content, 'html.parser')
    lines = []

    # Sections summary
    sections = soup.find_all('section', attrs={'data-section': True})
    if sections:
        lines.append("### Sections")
        for sec in sections:
            name = sec['data-section']
            # Get a content summary (first ~80 chars of text)
            text = sec.get_text(strip=True)[:80]
            lines.append(f"- `{name}`: {text}...")

    # Translation variables
    translations = (page.content or {}).get('translations', {})
    if translations:
        lines.append("\n### Translation Variables")
        # Show default language fully, others just key count
        for lang, trans in translations.items():
            if trans:
                sample = list(trans.items())[:5]
                sample_str = ', '.join(f'`{k}`: "{v[:40]}..."' if len(str(v)) > 40 else f'`{k}`: "{v}"' for k, v in sample)
                extra = f' (+{len(trans) - 5} more)' if len(trans) > 5 else ''
                lines.append(f"**{lang}**: {sample_str}{extra}")

    # Editable elements
    elements = soup.find_all(attrs={'data-element-id': True})
    if elements:
        lines.append("\n### Editable Elements")
        for el in elements[:20]:
            eid = el['data-element-id']
            classes = ' '.join(el.get('class', []))[:60]
            lines.append(f"- `{eid}` ({el.name}): classes=`{classes}`")
        if len(elements) > 20:
            lines.append(f"  ... and {len(elements) - 20} more elements")

    return '\n'.join(lines) if lines else "Page has content but no structured sections found."


def build_system_prompt(session):
    """Build the full system prompt with tool definitions and page context."""
    settings = SiteSettings.load()
    languages = settings.get_language_codes() if settings else ['pt', 'en']
    default_lang = settings.get_default_language() if settings else 'pt'
    site_name = settings.get_site_name(default_lang) if settings else 'Website'

    parts = [
        f"You are the Site Assistant for **{site_name}**. You help site managers manage their website through natural language.",
        f"\nEnabled languages: {', '.join(languages)} (default: {default_lang})",
        f"When creating or updating multilingual content, always provide values for ALL enabled languages.",
        TOOL_DEFINITIONS,
    ]

    # Page context
    page = session.active_page
    if page:
        parts.append(f"\n## Active Page: \"{page.default_title}\" (ID: {page.id})")
        parts.append(build_page_context(page))
    else:
        parts.append("\n## No Active Page")
        parts.append("No page is currently selected. Use `set_active_page` to work on a specific page, or `create_page` to make a new one.")
        parts.append("Page-level tools (update_translations, update_element_styles, etc.) are NOT available until a page is active.")

    parts.append(RESPONSE_PROTOCOL)

    # Capabilities the assistant should direct users elsewhere for
    parts.append("""
## What You Cannot Do (Direct Users Elsewhere)

- Generate page HTML from scratch → "Use the AI Content Studio at /backoffice/ai/"
- Upload or manage images → "Use the Media Library at /backoffice/media/"
- Change design system (colors, fonts, spacing) → "Use Settings at /backoffice/settings/"
- Edit header/footer → "Use /backoffice/settings/header/ or /backoffice/settings/footer/"
""")

    return '\n'.join(parts)


def build_user_prompt(message, history=''):
    """Build the user prompt with conversation history."""
    parts = []
    if history:
        parts.append(f"## Conversation History\n{history}\n")
    parts.append(f"## Current Request\n{message}")
    return '\n'.join(parts)
