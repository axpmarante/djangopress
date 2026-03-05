"""PageService — single source of truth for page operations.

Consolidates business logic from:
- backoffice/views.py (PagesView, PageEditView)
- backoffice/api_views.py (update_page_settings, update_page_order)
- editor_v2/api_views.py (_apply_structural_change_to_all_langs)
- site_assistant/tools/site_tools.py (create_page, delete_page, etc.)
"""

import logging
from bs4 import BeautifulSoup
from core.models import Page
from .i18n import build_i18n_field, auto_generate_slugs

logger = logging.getLogger(__name__)


def _apply_to_all_langs(page, change_fn):
    """Apply a structural HTML change to all language copies of a page.

    Moved from editor_v2/api_views.py._apply_structural_change_to_all_langs.

    Args:
        page: Model with html_content_i18n field (modified in-place, NOT saved).
        change_fn: Function(soup) that modifies soup in-place, returns True on success.
    """
    html_i18n = dict(getattr(page, 'html_content_i18n', None) or {})
    for lang, html in html_i18n.items():
        if not html:
            continue
        soup = BeautifulSoup(html, 'html.parser')
        if change_fn(soup):
            new_html = str(soup)
            if new_html.startswith('<html><body>'):
                new_html = new_html[12:-14]
            html_i18n[lang] = new_html
    page.html_content_i18n = html_i18n


def _check_slug_uniqueness(slug_i18n, exclude_page_id=None):
    """Check if any slug in slug_i18n conflicts with existing pages.

    Uses slug_i18n__contains JSON lookup on PostgreSQL, falls back to
    Python-level iteration on SQLite (which doesn't support __contains).
    Returns None if unique, or an error string if duplicate found.
    """
    from django.db import connection
    use_json_contains = connection.vendor != 'sqlite'

    for lang, slug_val in slug_i18n.items():
        if not slug_val:
            continue

        if use_json_contains:
            qs = Page.objects.filter(slug_i18n__contains={lang: slug_val})
            if exclude_page_id:
                qs = qs.exclude(pk=exclude_page_id)
            if qs.exists():
                return f'Slug "{slug_val}" already exists for language "{lang}"'
        else:
            # SQLite fallback: iterate pages and check in Python
            qs = Page.objects.all()
            if exclude_page_id:
                qs = qs.exclude(pk=exclude_page_id)
            for page in qs:
                if page.slug_i18n and isinstance(page.slug_i18n, dict):
                    if page.slug_i18n.get(lang) == slug_val:
                        return f'Slug "{slug_val}" already exists for language "{lang}"'
    return None


class PageService:

    @staticmethod
    def list(active_only=False):
        """List pages ordered by sort_order, created_at.

        Args:
            active_only: If True, only return active pages.

        Returns:
            dict with 'success', 'pages' (list of Page), 'message'.
        """
        qs = Page.objects.all().order_by('sort_order', 'created_at')
        if active_only:
            qs = qs.filter(is_active=True)
        return {'success': True, 'pages': list(qs), 'message': f'{qs.count()} pages found'}

    @staticmethod
    def get(page_id=None, title=None):
        """Get a page by ID or case-insensitive title search across all languages.

        Args:
            page_id: Page primary key.
            title: Search string matched case-insensitively against all language titles.

        Returns:
            dict with 'success', 'page' (if found), or 'error'.
        """
        if not page_id and not title:
            return {'success': False, 'error': 'Provide page_id or title'}

        if page_id:
            try:
                return {'success': True, 'page': Page.objects.get(pk=page_id)}
            except Page.DoesNotExist:
                return {'success': False, 'error': f'Page {page_id} not found'}

        # Search by title across all languages
        for page in Page.objects.all():
            if page.title_i18n and isinstance(page.title_i18n, dict):
                for lang, t in page.title_i18n.items():
                    if t and title.lower() in t.lower():
                        return {'success': True, 'page': page}
        return {'success': False, 'error': f'No page found matching "{title}"'}

    @staticmethod
    def get_info(page_id):
        """Get page with parsed section info from HTML.

        Parses the default language HTML to extract section names and previews.

        Args:
            page_id: Page primary key.

        Returns:
            dict with 'success', 'page', 'sections' (list of dicts), 'languages'.
        """
        try:
            page = Page.objects.get(pk=page_id)
        except Page.DoesNotExist:
            return {'success': False, 'error': f'Page {page_id} not found'}

        from core.models import SiteSettings
        settings = SiteSettings.load()
        default_lang = settings.get_default_language() if settings else 'pt'

        html_i18n = page.html_content_i18n or {}
        html = html_i18n.get(default_lang) or next(iter(html_i18n.values()), '')

        sections = []
        if html:
            soup = BeautifulSoup(html, 'html.parser')
            for sec in soup.find_all('section', attrs={'data-section': True}):
                text_preview = sec.get_text(strip=True)[:80]
                sections.append({
                    'name': sec['data-section'],
                    'preview': text_preview,
                })

        return {
            'success': True,
            'page': page,
            'sections': sections,
            'languages': list(html_i18n.keys()),
        }

    @staticmethod
    def create(title=None, slug=None, title_i18n=None, slug_i18n=None,
               html_content_i18n=None, is_active=True, user=None):
        """Create a page with auto i18n and slug deduplication.

        Provide either `title` (single language, auto-translated) or `title_i18n`
        (explicit per-language dict). Slugs are auto-generated from titles if not
        provided.

        Args:
            title: Title in default language (auto-translated to others).
            slug: Optional explicit slug for default language.
            title_i18n: Explicit per-language title dict.
            slug_i18n: Explicit per-language slug dict.
            html_content_i18n: Per-language HTML content dict.
            is_active: Whether the page is active (default True).
            user: User creating the page (for audit trail).

        Returns:
            dict with 'success', 'page' (if created), 'message' or 'error'.
        """
        if not title and not title_i18n:
            return {'success': False, 'error': 'Provide title or title_i18n'}

        try:
            title_i18n = build_i18n_field(value=title, value_i18n=title_i18n)
        except ValueError as e:
            return {'success': False, 'error': str(e)}

        slug_i18n = auto_generate_slugs(title_i18n, slug=slug, slug_i18n=slug_i18n)

        # Check slug uniqueness
        error = _check_slug_uniqueness(slug_i18n)
        if error:
            return {'success': False, 'error': error}

        page = Page.objects.create(
            title_i18n=title_i18n,
            slug_i18n=slug_i18n,
            html_content_i18n=html_content_i18n or {},
            is_active=is_active,
        )
        return {
            'success': True,
            'page': page,
            'message': f'Created page "{page.default_title}" (ID: {page.id})',
        }

    @staticmethod
    def update_meta(page_id, title_i18n=None, slug_i18n=None,
                    is_active=None, sort_order=None):
        """Update page metadata (title, slug, active status, sort order).

        Args:
            page_id: Page primary key.
            title_i18n: New per-language title dict.
            slug_i18n: New per-language slug dict (checked for uniqueness).
            is_active: New active status.
            sort_order: New sort order.

        Returns:
            dict with 'success', 'page' (if updated), 'message' or 'error'.
        """
        try:
            page = Page.objects.get(pk=page_id)
        except Page.DoesNotExist:
            return {'success': False, 'error': f'Page {page_id} not found'}

        updated = []
        if title_i18n is not None:
            page.title_i18n = title_i18n
            updated.append('title')
        if slug_i18n is not None:
            error = _check_slug_uniqueness(slug_i18n, exclude_page_id=page_id)
            if error:
                return {'success': False, 'error': error}
            page.slug_i18n = slug_i18n
            updated.append('slug')
        if is_active is not None:
            page.is_active = is_active
            updated.append('is_active')
        if sort_order is not None:
            page.sort_order = sort_order
            updated.append('sort_order')

        if updated:
            page.save()

        return {'success': True, 'page': page, 'message': f'Updated: {", ".join(updated)}'}

    @staticmethod
    def delete(page_id):
        """Delete a page.

        Args:
            page_id: Page primary key.

        Returns:
            dict with 'success', 'message' or 'error'.
        """
        try:
            page = Page.objects.get(pk=page_id)
        except Page.DoesNotExist:
            return {'success': False, 'error': f'Page {page_id} not found'}
        title = page.default_title
        page.delete()
        return {'success': True, 'message': f'Deleted page "{title}" (ID: {page_id})'}

    @staticmethod
    def reorder(order):
        """Set page sort order from a list of dicts.

        Args:
            order: List of dicts like [{"page_id": int, "sort_order": int}, ...].

        Returns:
            dict with 'success', 'message' or 'error'.
        """
        if not order:
            return {'success': False, 'error': 'Empty order list'}
        for item in order:
            Page.objects.filter(pk=item['page_id']).update(sort_order=item['sort_order'])
        return {'success': True, 'message': f'Reordered {len(order)} pages'}

    @staticmethod
    def update_element_styles(page, selector=None, section_name=None,
                               new_classes='', user=None):
        """Update CSS classes on an element across ALL language copies.

        Args:
            page: Page instance.
            selector: CSS selector to find the element.
            section_name: Alternative to selector — finds section by data-section attr.
            new_classes: Space-separated class string. Empty string removes all classes.
            user: User making the change (for version creation).

        Returns:
            dict with 'success', 'message' or 'error'.
        """
        if not selector and not section_name:
            return {'success': False, 'error': 'Provide selector or section_name'}

        if user:
            page.create_version(user=user, change_summary='Update element styles')

        def apply_classes(soup):
            if selector:
                el = soup.select_one(selector)
            else:
                el = soup.find('section', attrs={'data-section': section_name})
            if not el:
                return False
            if new_classes:
                el['class'] = new_classes.split()
            elif 'class' in el.attrs:
                del el['class']
            return True

        _apply_to_all_langs(page, apply_classes)
        page.save()
        return {'success': True, 'message': 'Updated element classes'}

    @staticmethod
    def update_element_attribute(page, selector, attribute, value='', user=None):
        """Update an attribute on an element across ALL language copies.

        Args:
            page: Page instance.
            selector: CSS selector to find the element.
            attribute: Attribute name to set or remove.
            value: Attribute value. Empty string removes the attribute.
            user: User making the change (for version creation).

        Returns:
            dict with 'success', 'message' or 'error'.
        """
        if not selector or not attribute:
            return {'success': False, 'error': 'Missing selector or attribute'}

        if user:
            page.create_version(user=user, change_summary='Update element attribute')

        def apply_attr(soup):
            el = soup.select_one(selector)
            if not el:
                return False
            if value:
                el[attribute] = value
            elif attribute in el.attrs:
                del el[attribute]
            return True

        _apply_to_all_langs(page, apply_attr)
        page.save()
        return {'success': True, 'message': f'Updated {attribute} on element'}

    @staticmethod
    def remove_section(page, section_name, user=None):
        """Remove a section from ALL language copies.

        Args:
            page: Page instance.
            section_name: Value of data-section attribute to match.
            user: User making the change (for version creation).

        Returns:
            dict with 'success', 'message' or 'error'.
        """
        if not section_name:
            return {'success': False, 'error': 'Missing section_name'}

        if user:
            page.create_version(user=user, change_summary=f'Remove section "{section_name}"')

        def remove_sect(soup):
            sec = soup.find('section', attrs={'data-section': section_name})
            if not sec:
                return False
            sec.decompose()
            return True

        _apply_to_all_langs(page, remove_sect)
        page.save()
        return {'success': True, 'message': f'Removed section "{section_name}"'}

    @staticmethod
    def reorder_sections(page, order, user=None):
        """Reorder sections in ALL language copies.

        Args:
            page: Page instance.
            order: List of section names (data-section values) in desired order.
            user: User making the change (for version creation).

        Returns:
            dict with 'success', 'message' or 'error'.
        """
        if not order:
            return {'success': False, 'error': 'Empty order list'}

        if user:
            page.create_version(user=user, change_summary='Reorder sections')

        html_i18n = dict(page.html_content_i18n or {})
        for lang in html_i18n:
            html = html_i18n[lang]
            if not html:
                continue
            soup = BeautifulSoup(html, 'html.parser')
            sections = {}
            for sec in soup.find_all('section', attrs={'data-section': True}):
                sections[sec['data-section']] = sec.extract()
            # Add sections back in the specified order
            for name in order:
                if name in sections:
                    soup.append(sections[name])
            # Append any sections not in the order list (preserve them)
            for name, sec in sections.items():
                if name not in order:
                    soup.append(sec)
            new_html = str(soup)
            if new_html.startswith('<html><body>'):
                new_html = new_html[12:-14]
            html_i18n[lang] = new_html

        page.html_content_i18n = html_i18n
        page.save()
        return {'success': True, 'message': f'Reordered {len(order)} sections'}

    @staticmethod
    def save_section_html(page, section_name, new_html, lang=None, user=None):
        """Replace a single section's HTML in one language.

        If the section doesn't exist, it is appended to the page.

        Args:
            page: Page instance.
            section_name: Value of data-section attribute to match.
            new_html: Full section HTML to replace with.
            lang: Target language code. Defaults to site's default language.
            user: User making the change (for version creation).

        Returns:
            dict with 'success', 'message' or 'error'.
        """
        from core.models import SiteSettings
        settings = SiteSettings.load()
        lang = lang or (settings.get_default_language() if settings else 'pt')

        if user:
            page.create_version(user=user, change_summary=f'Update section "{section_name}"')

        html_i18n = dict(page.html_content_i18n or {})
        page_html = html_i18n.get(lang, '')

        soup = BeautifulSoup(page_html, 'html.parser')
        old_section = soup.find('section', attrs={'data-section': section_name})

        new_soup = BeautifulSoup(new_html, 'html.parser')
        new_section = new_soup.find('section') or new_soup

        if old_section:
            old_section.replace_with(new_section)
        else:
            soup.append(new_section)

        result_html = str(soup)
        if result_html.startswith('<html><body>'):
            result_html = result_html[12:-14]
        html_i18n[lang] = result_html
        page.html_content_i18n = html_i18n
        page.save()

        return {'success': True, 'message': f'Updated section "{section_name}"'}
