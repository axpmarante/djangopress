"""Prompt builders for the Site Assistant.

build_router_snapshot() — site state dict for Phase 1 router
build_executor_prompt() — system instruction for Phase 2 executor
build_active_page_context() — active page section summary
"""

import re

from bs4 import BeautifulSoup
from django.apps import apps
from django.urls import reverse, NoReverseMatch
from core.models import SiteSettings
from core.services import SettingsService


def build_active_page_context(page):
    """Build a compact page context for the LLM (sections with text previews).

    Returns a multi-line string describing the active page's sections and
    available languages. Used in the executor system instruction.
    """
    html_i18n = page.html_content_i18n or {} if page else {}
    html = next(iter(html_i18n.values()), '') if html_i18n else ''

    if not page or not html:
        return "Page has no content yet."

    soup = BeautifulSoup(html, 'html.parser')
    lines = []

    sections = soup.find_all('section', attrs={'data-section': True})
    if not sections:
        return "Page has content but no structured sections found."

    for sec in sections:
        name = sec['data-section']
        text = sec.get_text(strip=True)[:80]
        lines.append(f"- `{name}`: {text}...")

    if html_i18n:
        lines.append(f"\nLanguages: {', '.join(html_i18n.keys())}")

    return '\n'.join(lines)


def _discover_decoupled_apps():
    """Detect installed decoupled apps that have public-facing URLs.

    Returns a list of dicts:
        [{"name": "news", "label": "News", "list_url": "/news/",
          "item_count": 3, "published_count": 2}, ...]
    """
    SKIP_APPS = {'core', 'backoffice', 'editor_v2', 'ai', 'site_assistant', 'config'}
    discovered = []

    for app_config in apps.get_app_configs():
        name = app_config.name
        if name in SKIP_APPS or '.' in name:
            continue

        try:
            list_url = reverse(f'{name}:list')
            list_url = re.sub(r'^/[a-z]{2}/', '/', list_url)
        except NoReverseMatch:
            continue

        item_count = None
        published = None
        for model in app_config.get_models():
            if hasattr(model, 'is_published') and hasattr(model, 'title_i18n'):
                item_count = model.objects.count()
                published = model.objects.filter(is_published=True).count()
                break

        discovered.append({
            'name': name,
            'label': app_config.verbose_name or name.title(),
            'list_url': list_url,
            'item_count': item_count,
            'published_count': published if item_count is not None else None,
        })

    return discovered


def build_router_snapshot(session):
    """Build the compact site state dict for the Phase 1 router.

    Wraps SettingsService.get_snapshot() and adds active_page info
    and installed_apps list.

    Returns:
        Dict with 'snapshot' key containing the full state, or
        a minimal fallback if settings are not configured.
    """
    result = SettingsService.get_snapshot()
    if not result.get('success'):
        return {
            'site_name': 'Website',
            'default_language': 'pt',
            'languages': ['pt'],
            'pages': [],
            'menu_items': [],
            'stats': {},
            'active_page': 'none selected',
            'installed_apps': [],
        }

    snapshot = result['snapshot']

    # Add active page info
    page = session.active_page
    if page:
        title = ''
        if page.title_i18n and isinstance(page.title_i18n, dict):
            default_lang = snapshot.get('default_language', 'pt')
            title = page.title_i18n.get(default_lang, next(iter(page.title_i18n.values()), ''))
        snapshot['active_page'] = f'#{page.id} {title}'
    else:
        snapshot['active_page'] = 'none selected'

    # Add installed apps
    apps_list = _discover_decoupled_apps()
    snapshot['installed_apps'] = [a['name'] for a in apps_list]
    snapshot['installed_apps_detail'] = apps_list

    return snapshot


def build_executor_prompt(session, snapshot):
    """Build the system instruction for the Phase 2 executor.

    This is a focused prompt (~800-1000 tokens) split into:
    - Identity
    - Site Context (pages, menu, languages, installed apps)
    - Active Page Context (sections with previews)
    - Behavior Rules
    - What You Cannot Do

    Args:
        session: AssistantSession instance.
        snapshot: Dict from build_router_snapshot().

    Returns:
        System instruction string.
    """
    default_lang = snapshot.get('default_language', 'pt')
    site_name = snapshot.get('site_name', 'Website')
    languages = snapshot.get('languages', [default_lang])

    parts = []

    # --- Identity ---
    parts.append(
        f'You are the Site Assistant for "{site_name}". '
        f'Always respond in {default_lang}. '
        f'Enabled languages: {", ".join(languages)}. '
        f'When creating/updating multilingual content, provide values for ALL enabled languages.'
    )

    # --- Site Context ---
    pages = snapshot.get('pages', [])
    page_summary = ', '.join(
        f'#{p["id"]} {p["title"]}{"" if p["is_active"] else " (inactive)"}'
        for p in pages[:25]
    ) if pages else 'none'

    menu_items = snapshot.get('menu_items', [])
    menu_summary = ', '.join(
        f'{m["label"]}' + (f' (+{m["children_count"]} sub)' if m.get('children_count') else '')
        for m in menu_items[:15]
    ) if menu_items else 'none'

    stats = snapshot.get('stats', {})
    parts.append(
        f'\nSite: {stats.get("total_pages", 0)} pages '
        f'({stats.get("active_pages", 0)} active), '
        f'{stats.get("total_images", 0)} images, '
        f'{stats.get("total_menu_items", 0)} menu items, '
        f'{stats.get("total_submissions", 0)} form submissions.'
        f'\nPages: {page_summary}'
        f'\nMenu: {menu_summary}'
    )

    # Installed apps
    apps_detail = snapshot.get('installed_apps_detail', [])
    if apps_detail:
        app_lines = []
        for app in apps_detail:
            count_info = ''
            if app['item_count'] is not None:
                count_info = f' ({app["published_count"]} published, {app["item_count"]} total)'
            app_lines.append(f'- {app["label"]}: list at {app["list_url"]}{count_info}')
        parts.append('\nInstalled apps:\n' + '\n'.join(app_lines))

    # --- Active Page Context ---
    page = session.active_page
    if page:
        parts.append(f'\nActive Page: "{page.default_title}" (ID: {page.id})')
        parts.append(build_active_page_context(page))
    else:
        parts.append(
            '\nNo Active Page. Use set_active_page to work on a specific page. '
            'Page-level tools are NOT available until a page is active.'
        )

    # --- Behavior Rules ---
    parts.append("""
Rules:
- Use the LIGHTEST tool. For CSS changes use update_element_styles (instant). Only use refine_section/refine_page for structural/design changes (AI call, slower).
- NEVER call delete tools directly. Always ask the user for confirmation FIRST, then call the delete tool only after they confirm.
- Be concise. State what you did, not how.
- When you need data (list_pages, get_settings, etc.), call the tool first, then respond based on results.
- Provide all i18n fields in ALL enabled languages when creating/updating content.""")

    # --- What You Cannot Do ---
    parts.append("""
What you cannot do (direct users to these URLs):
- Generate page HTML from scratch: /backoffice/ai/
- Upload/manage images: /backoffice/media/
- Edit header/footer visually: /backoffice/settings/header/ or /backoffice/settings/footer/""")

    return '\n'.join(parts)
