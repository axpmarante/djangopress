# Site Assistant v2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor the site assistant with a service layer, router pattern (gemini-lite), native Gemini function calling, and restructured prompts — eliminating duplicate business logic and improving cost/quality.

**Architecture:** A service layer (`core/services/`) centralizes all business logic. The assistant uses a two-phase approach: Phase 1 (Router, gemini-lite) classifies intent and can respond directly to greetings; Phase 2 (Executor, gemini-flash) uses native Gemini function calling with only the relevant tool subset. Tools become thin adapters to services.

**Tech Stack:** Django 6.0, Google GenAI SDK (`google.genai`), BeautifulSoup4, SQLite

**Design doc:** `docs/plans/2026-03-04-site-assistant-v2-design.md`

---

## Task 1: Service Layer — i18n Helper

**Files:**
- Create: `core/services/__init__.py`
- Create: `core/services/i18n.py`
- Test: `python manage.py test core.tests.test_services_i18n`
- Create: `core/tests/__init__.py` (if missing)
- Create: `core/tests/test_services_i18n.py`

**Step 1: Create the package**

```bash
mkdir -p core/services
touch core/services/__init__.py
mkdir -p core/tests
touch core/tests/__init__.py
```

**Step 2: Write the test**

Create `core/tests/test_services_i18n.py`:

```python
"""Tests for core.services.i18n — auto-translation helper."""

from unittest.mock import patch
from django.test import TestCase, override_settings
from core.services.i18n import build_i18n_field, auto_generate_slugs


class BuildI18nFieldTest(TestCase):
    """Test build_i18n_field() which builds complete i18n dicts."""

    def setUp(self):
        # Ensure SiteSettings exists with pt (default) + en
        from core.models import SiteSettings
        self.settings = SiteSettings.load()
        self.settings.enabled_languages = [
            {'code': 'pt', 'name': 'Português'},
            {'code': 'en', 'name': 'English'},
        ]
        self.settings.default_language = 'pt'
        self.settings.save()

    def test_explicit_i18n_all_langs_returns_as_is(self):
        """When value_i18n has all enabled languages, return it unchanged."""
        i18n = {'pt': 'Sobre Nós', 'en': 'About Us'}
        result = build_i18n_field(value_i18n=i18n)
        self.assertEqual(result, i18n)

    def test_single_value_fills_default_lang(self):
        """When value is a string, it goes into the default language."""
        result = build_i18n_field(value='Sobre Nós')
        self.assertEqual(result['pt'], 'Sobre Nós')
        # 'en' should also be populated (translated)
        self.assertIn('en', result)
        self.assertTrue(len(result['en']) > 0)

    def test_partial_i18n_fills_missing(self):
        """When value_i18n is partial, missing languages get translated."""
        result = build_i18n_field(value_i18n={'pt': 'Sobre Nós'})
        self.assertIn('en', result)
        self.assertEqual(result['pt'], 'Sobre Nós')

    def test_no_value_raises(self):
        """When neither value nor value_i18n, raise ValueError."""
        with self.assertRaises(ValueError):
            build_i18n_field()

    @patch('core.services.i18n._translate_text')
    def test_translation_called_for_missing_langs(self, mock_translate):
        """Translation is called for each missing language."""
        mock_translate.return_value = 'About Us'
        result = build_i18n_field(value='Sobre Nós')
        mock_translate.assert_called_once_with('Sobre Nós', 'pt', 'en')
        self.assertEqual(result['en'], 'About Us')

    @patch('core.services.i18n._translate_text')
    def test_skip_translation_when_all_present(self, mock_translate):
        """No translation call when all languages are provided."""
        build_i18n_field(value_i18n={'pt': 'Sobre', 'en': 'About'})
        mock_translate.assert_not_called()


class AutoGenerateSlugsTest(TestCase):
    """Test auto_generate_slugs() which builds slug_i18n from title_i18n."""

    def test_generates_slugs_from_titles(self):
        titles = {'pt': 'Sobre Nós', 'en': 'About Us'}
        result = auto_generate_slugs(titles)
        self.assertEqual(result['pt'], 'sobre-nos')
        self.assertEqual(result['en'], 'about-us')

    def test_explicit_slug_overrides_default_lang(self):
        titles = {'pt': 'Sobre Nós', 'en': 'About Us'}
        result = auto_generate_slugs(titles, slug='sobre')
        self.assertEqual(result['pt'], 'sobre')
        self.assertEqual(result['en'], 'about-us')
```

**Step 3: Run test to verify it fails**

```bash
python manage.py test core.tests.test_services_i18n -v 2
```

Expected: `ModuleNotFoundError: No module named 'core.services.i18n'`

**Step 4: Implement `core/services/i18n.py`**

```python
"""i18n helpers for the service layer.

Builds complete i18n dicts from single-language values by auto-translating
to other enabled languages. Uses gemini-flash for translation (same pipeline
as page translation).
"""

from django.utils.text import slugify


def _get_language_config():
    """Get enabled languages and default language from SiteSettings."""
    from core.models import SiteSettings
    settings = SiteSettings.load()
    default_lang = settings.get_default_language() if settings else 'pt'
    all_langs = settings.get_language_codes() if settings else [default_lang]
    return default_lang, all_langs


def _translate_text(text, source_lang, target_lang):
    """Translate text using the LLM translation pipeline.

    Uses gemini-flash (same model as page translation in ai/services.py).
    Falls back to the original text if translation fails.
    """
    try:
        from ai.utils.llm_config import LLMBase
        llm = LLMBase()
        messages = [
            {'role': 'system', 'content': (
                f'Translate the following text from {source_lang} to {target_lang}. '
                f'Return ONLY the translated text, nothing else.'
            )},
            {'role': 'user', 'content': text},
        ]
        response = llm.get_completion(messages, tool_name='gemini-lite')
        translated = response.choices[0].message.content.strip()
        return translated if translated else text
    except Exception:
        return text


def build_i18n_field(value=None, value_i18n=None):
    """Build a complete i18n dict from a single-language value or partial dict.

    Args:
        value: Text in the default language (auto-translated to others).
        value_i18n: Explicit per-language dict. If all languages present, used as-is.
                    If partial, missing languages are auto-translated.

    Returns:
        Dict with a key for every enabled language: {"pt": "...", "en": "..."}.

    Raises:
        ValueError: If neither value nor value_i18n provided.
    """
    if not value and not value_i18n:
        raise ValueError('Provide value or value_i18n')

    default_lang, all_langs = _get_language_config()

    # Start with explicit i18n if provided
    result = dict(value_i18n or {})

    # Fill default language from single value
    if value and default_lang not in result:
        result[default_lang] = value

    # If all languages present, return as-is
    if all(lang in result and result[lang] for lang in all_langs):
        return result

    # Find a source language to translate from
    source_lang = default_lang if default_lang in result else next(iter(result))
    source_text = result[source_lang]

    # Translate missing languages
    for lang in all_langs:
        if lang not in result or not result[lang]:
            result[lang] = _translate_text(source_text, source_lang, lang)

    return result


def auto_generate_slugs(title_i18n, slug=None, slug_i18n=None):
    """Generate slug_i18n from title_i18n.

    Args:
        title_i18n: Complete title dict {"pt": "...", "en": "..."}.
        slug: Optional explicit slug for the default language.
        slug_i18n: Optional explicit slugs (overrides everything if complete).

    Returns:
        Dict with a slug for every language in title_i18n.
    """
    if slug_i18n and len(slug_i18n) >= len(title_i18n):
        return slug_i18n

    default_lang, _ = _get_language_config()
    result = dict(slug_i18n or {})

    for lang, title in title_i18n.items():
        if lang not in result:
            result[lang] = slugify(title)

    # Override default lang with explicit slug
    if slug:
        result[default_lang] = slug

    return result
```

**Step 5: Update `core/services/__init__.py`**

```python
from .i18n import build_i18n_field, auto_generate_slugs
```

**Step 6: Run tests**

```bash
python manage.py test core.tests.test_services_i18n -v 2
```

Expected: All pass.

**Step 7: Commit**

```bash
git add core/services/ core/tests/
git commit -m "feat: add core/services/ package with i18n auto-translation helper"
```

---

## Task 2: Service Layer — PageService

**Files:**
- Create: `core/services/pages.py`
- Modify: `core/services/__init__.py`
- Test: `core/tests/test_services_pages.py`
- Reference: `editor_v2/api_views.py:126-146` (`_apply_structural_change_to_all_langs`)
- Reference: `backoffice/api_views.py:638-693` (`update_page_settings` for slug dedup)

**Step 1: Write the test**

Create `core/tests/test_services_pages.py`:

```python
"""Tests for core.services.pages — PageService."""

from unittest.mock import patch
from django.test import TestCase
from core.models import Page, SiteSettings
from core.services.pages import PageService


class PageServiceListTest(TestCase):

    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        Page.objects.create(title_i18n={'pt': 'Home', 'en': 'Home'}, slug_i18n={'pt': 'home', 'en': 'home'}, is_active=True, sort_order=0)
        Page.objects.create(title_i18n={'pt': 'Sobre', 'en': 'About'}, slug_i18n={'pt': 'sobre', 'en': 'about'}, is_active=True, sort_order=1)
        Page.objects.create(title_i18n={'pt': 'Rascunho', 'en': 'Draft'}, slug_i18n={'pt': 'rascunho', 'en': 'draft'}, is_active=False, sort_order=2)

    def test_list_all(self):
        result = PageService.list()
        self.assertTrue(result['success'])
        self.assertEqual(len(result['pages']), 3)

    def test_list_active_only(self):
        result = PageService.list(active_only=True)
        self.assertTrue(result['success'])
        self.assertEqual(len(result['pages']), 2)


class PageServiceGetTest(TestCase):

    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        self.page = Page.objects.create(
            title_i18n={'pt': 'Contacto', 'en': 'Contact'},
            slug_i18n={'pt': 'contacto', 'en': 'contact'},
        )

    def test_get_by_id(self):
        result = PageService.get(page_id=self.page.id)
        self.assertTrue(result['success'])
        self.assertEqual(result['page'].id, self.page.id)

    def test_get_by_title(self):
        result = PageService.get(title='Contact')
        self.assertTrue(result['success'])
        self.assertEqual(result['page'].id, self.page.id)

    def test_get_not_found(self):
        result = PageService.get(page_id=99999)
        self.assertFalse(result['success'])


class PageServiceCreateTest(TestCase):

    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()

    @patch('core.services.i18n._translate_text', return_value='About Us')
    def test_create_with_single_value(self, mock_translate):
        result = PageService.create(title='Sobre Nós')
        self.assertTrue(result['success'])
        page = result['page']
        self.assertEqual(page.title_i18n['pt'], 'Sobre Nós')
        self.assertEqual(page.title_i18n['en'], 'About Us')
        self.assertIn('pt', page.slug_i18n)
        self.assertIn('en', page.slug_i18n)

    def test_create_with_explicit_i18n(self):
        result = PageService.create(
            title_i18n={'pt': 'Serviços', 'en': 'Services'},
            slug_i18n={'pt': 'servicos', 'en': 'services'},
        )
        self.assertTrue(result['success'])
        self.assertEqual(result['page'].title_i18n['en'], 'Services')

    def test_create_duplicate_slug_fails(self):
        Page.objects.create(
            title_i18n={'pt': 'Sobre', 'en': 'About'},
            slug_i18n={'pt': 'sobre', 'en': 'about'},
        )
        result = PageService.create(
            title_i18n={'pt': 'Sobre Nós', 'en': 'About Us'},
            slug_i18n={'pt': 'sobre', 'en': 'about-us'},
        )
        self.assertFalse(result['success'])
        self.assertIn('slug', result['error'].lower())

    def test_create_missing_title_fails(self):
        result = PageService.create()
        self.assertFalse(result['success'])


class PageServiceDeleteTest(TestCase):

    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}]
        s.default_language = 'pt'
        s.save()
        self.page = Page.objects.create(
            title_i18n={'pt': 'Temp'}, slug_i18n={'pt': 'temp'},
        )

    def test_delete_existing(self):
        result = PageService.delete(self.page.id)
        self.assertTrue(result['success'])
        self.assertFalse(Page.objects.filter(pk=self.page.id).exists())

    def test_delete_not_found(self):
        result = PageService.delete(99999)
        self.assertFalse(result['success'])


class PageServiceElementStylesTest(TestCase):

    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        self.page = Page.objects.create(
            title_i18n={'pt': 'Test', 'en': 'Test'},
            slug_i18n={'pt': 'test', 'en': 'test'},
            html_content_i18n={
                'pt': '<section data-section="hero" id="hero"><h1 class="text-2xl">Olá</h1></section>',
                'en': '<section data-section="hero" id="hero"><h1 class="text-2xl">Hello</h1></section>',
            },
        )

    def test_update_styles_applies_to_all_langs(self):
        result = PageService.update_element_styles(
            self.page, selector='section[data-section="hero"] h1',
            new_classes='text-4xl font-bold',
        )
        self.assertTrue(result['success'])
        self.page.refresh_from_db()
        # Check BOTH languages got updated
        for lang in ['pt', 'en']:
            self.assertIn('text-4xl', self.page.html_content_i18n[lang])
            self.assertIn('font-bold', self.page.html_content_i18n[lang])
            self.assertNotIn('text-2xl', self.page.html_content_i18n[lang])


class PageServiceRemoveSectionTest(TestCase):

    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        self.page = Page.objects.create(
            title_i18n={'pt': 'Test', 'en': 'Test'},
            slug_i18n={'pt': 'test', 'en': 'test'},
            html_content_i18n={
                'pt': '<section data-section="hero" id="hero"><h1>Olá</h1></section><section data-section="cta" id="cta"><p>CTA</p></section>',
                'en': '<section data-section="hero" id="hero"><h1>Hello</h1></section><section data-section="cta" id="cta"><p>CTA</p></section>',
            },
        )

    def test_remove_section_from_all_langs(self):
        result = PageService.remove_section(self.page, 'cta')
        self.assertTrue(result['success'])
        self.page.refresh_from_db()
        for lang in ['pt', 'en']:
            self.assertNotIn('data-section="cta"', self.page.html_content_i18n[lang])
            self.assertIn('data-section="hero"', self.page.html_content_i18n[lang])
```

**Step 2: Run test to verify it fails**

```bash
python manage.py test core.tests.test_services_pages -v 2
```

Expected: `ModuleNotFoundError: No module named 'core.services.pages'`

**Step 3: Implement `core/services/pages.py`**

```python
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

    Uses the efficient slug_i18n__contains JSON lookup.
    Returns None if unique, or an error string if duplicate found.
    """
    for lang, slug_val in slug_i18n.items():
        if not slug_val:
            continue
        qs = Page.objects.filter(slug_i18n__contains={lang: slug_val})
        if exclude_page_id:
            qs = qs.exclude(pk=exclude_page_id)
        if qs.exists():
            return f'Slug "{slug_val}" already exists for language "{lang}"'
    return None


class PageService:

    @staticmethod
    def list(active_only=False):
        qs = Page.objects.all().order_by('sort_order', 'created_at')
        if active_only:
            qs = qs.filter(is_active=True)
        return {'success': True, 'pages': list(qs), 'message': f'{qs.count()} pages found'}

    @staticmethod
    def get(page_id=None, title=None):
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
        """Get page with parsed section info from HTML."""
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
        try:
            page = Page.objects.get(pk=page_id)
        except Page.DoesNotExist:
            return {'success': False, 'error': f'Page {page_id} not found'}
        title = page.default_title
        page.delete()
        return {'success': True, 'message': f'Deleted page "{title}" (ID: {page_id})'}

    @staticmethod
    def reorder(order):
        """order = [{"page_id": int, "sort_order": int}, ...]"""
        if not order:
            return {'success': False, 'error': 'Empty order list'}
        for item in order:
            Page.objects.filter(pk=item['page_id']).update(sort_order=item['sort_order'])
        return {'success': True, 'message': f'Reordered {len(order)} pages'}

    @staticmethod
    def update_element_styles(page, selector=None, section_name=None,
                               new_classes='', user=None):
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
        if not order:
            return {'success': False, 'error': 'Empty order list'}

        if user:
            page.create_version(user=user, change_summary='Reorder sections')

        # Apply to default language only (section order is structural)
        from core.models import SiteSettings
        settings = SiteSettings.load()
        default_lang = settings.get_default_language() if settings else 'pt'

        html_i18n = dict(page.html_content_i18n or {})
        for lang in html_i18n:
            html = html_i18n[lang]
            if not html:
                continue
            soup = BeautifulSoup(html, 'html.parser')
            sections = {}
            for sec in soup.find_all('section', attrs={'data-section': True}):
                sections[sec['data-section']] = sec.extract()
            for name in order:
                if name in sections:
                    soup.append(sections[name])
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
        """Replace a single section's HTML in one language."""
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
```

**Step 4: Update `core/services/__init__.py`**

```python
from .i18n import build_i18n_field, auto_generate_slugs
from .pages import PageService
```

**Step 5: Run tests**

```bash
python manage.py test core.tests.test_services_pages -v 2
```

**Step 6: Commit**

```bash
git add core/services/pages.py core/tests/test_services_pages.py core/services/__init__.py
git commit -m "feat: add PageService with CRUD, slug dedup, and all-language propagation"
```

---

## Task 3: Service Layer — MenuService, SettingsService, FormService, MediaService

**Files:**
- Create: `core/services/menu.py`
- Create: `core/services/settings.py`
- Create: `core/services/forms.py`
- Create: `core/services/media.py`
- Create: `core/tests/test_services_menu.py`
- Create: `core/tests/test_services_settings.py`
- Modify: `core/services/__init__.py`

These follow the same pattern as PageService. Implementation is straightforward CRUD wrapping the existing ORM operations.

**Step 1: Write tests for MenuService**

Create `core/tests/test_services_menu.py` — test create (with auto-translate), update, delete, list, reorder. Test nesting depth validation (max 1 level).

**Step 2: Implement MenuService** in `core/services/menu.py`

Key methods: `list()`, `create()`, `update()`, `delete()`, `reorder()`.
- `create()` uses `build_i18n_field` for `label_i18n`
- Validates parent exists and nesting depth <= 1

**Step 3: Write tests for SettingsService**

Create `core/tests/test_services_settings.py` — test get, update with allowlist, update with blocked field, get_snapshot.

**Step 4: Implement SettingsService** in `core/services/settings.py`

Key methods: `get()`, `update()`, `get_snapshot()`.
- `get_snapshot()` is new — returns compact site state for the router/executor. Queries pages, menu items, images, stats in one call.

**Step 5: Implement FormService** in `core/services/forms.py`

Key methods: `list()`, `create()`, `update()`, `delete()`, `list_submissions()`.
- `create()` validates slug uniqueness.

**Step 6: Implement MediaService** in `core/services/media.py`

Key methods: `list()`, `get()`.

**Step 7: Update `core/services/__init__.py`**

```python
from .i18n import build_i18n_field, auto_generate_slugs
from .pages import PageService
from .menu import MenuService
from .settings import SettingsService
from .forms import FormService
from .media import MediaService
```

**Step 8: Run all tests**

```bash
python manage.py test core.tests -v 2
```

**Step 9: Commit**

```bash
git add core/services/ core/tests/
git commit -m "feat: add MenuService, SettingsService, FormService, MediaService"
```

---

## Task 4: Service Layer — GlobalSectionService and NewsService

**Files:**
- Create: `core/services/global_sections.py`
- Create: `news/services.py`
- Create: `core/tests/test_services_global_sections.py`
- Modify: `core/services/__init__.py`

**Step 1: Implement GlobalSectionService** in `core/services/global_sections.py`

```python
"""GlobalSectionService — header/footer management."""

from core.models import GlobalSection


class GlobalSectionService:

    @staticmethod
    def get(key):
        try:
            section = GlobalSection.objects.get(key=key)
            return {'success': True, 'section': section}
        except GlobalSection.DoesNotExist:
            return {'success': False, 'error': f'GlobalSection "{key}" not found'}

    @staticmethod
    def get_html(key, lang=None):
        result = GlobalSectionService.get(key)
        if not result['success']:
            return result
        section = result['section']
        from core.models import SiteSettings
        settings = SiteSettings.load()
        lang = lang or (settings.get_default_language() if settings else 'pt')
        html_i18n = section.html_template_i18n or {}
        html = html_i18n.get(lang) or next(iter(html_i18n.values()), '')
        return {'success': True, 'html': html, 'language': lang}

    @staticmethod
    def refine(key, instructions, model='gemini-pro', user=None):
        """AI-refine a GlobalSection. Delegates to ContentGenerationService."""
        result = GlobalSectionService.get(key)
        if not result['success']:
            return result

        from ai.services import ContentGenerationService
        service = ContentGenerationService(model_name=model)
        ai_result = service.refine_global_section(
            section_key=key,
            instructions=instructions,
            model_override=model,
        )

        # Save the refined HTML
        section = GlobalSection.objects.get(key=key)
        from core.models import SiteSettings
        settings = SiteSettings.load()
        default_lang = settings.get_default_language() if settings else 'pt'

        html_i18n = dict(section.html_template_i18n or {})
        refined_html = ai_result.get('options', [{}])[0].get('html_template', '')
        if refined_html:
            html_i18n[default_lang] = refined_html
            section.html_template_i18n = html_i18n
            section.save()

        return {
            'success': True,
            'message': f'Refined {key} with AI',
            'assistant_message': ai_result.get('assistant_message', ''),
        }
```

**Step 2: Implement NewsService** in `news/services.py`

Follow the same pattern as PageService. Key methods: `list()`, `get()`, `create()`, `update()`, `list_categories()`. Uses `build_i18n_field` for title/slug/excerpt.

**Step 3: Update `core/services/__init__.py`**

```python
from .i18n import build_i18n_field, auto_generate_slugs
from .pages import PageService
from .menu import MenuService
from .settings import SettingsService
from .forms import FormService
from .media import MediaService
from .global_sections import GlobalSectionService
```

**Step 4: Run tests and commit**

```bash
python manage.py test core.tests -v 2
git add core/services/ news/services.py core/tests/
git commit -m "feat: add GlobalSectionService and NewsService"
```

---

## Task 5: LLM Native Function Calling Support

**Files:**
- Modify: `ai/utils/llm_config.py`
- Test: `core/tests/test_llm_function_calling.py`

**Step 1: Write the test**

Create `core/tests/test_llm_function_calling.py`:

```python
"""Test that LLMBase.get_completion_with_tools() builds correct Gemini FC requests."""

from unittest.mock import patch, MagicMock
from django.test import TestCase


class LLMFunctionCallingTest(TestCase):

    @patch('ai.utils.llm_config.GOOGLE_AVAILABLE', True)
    def test_get_completion_with_tools_builds_config(self):
        """Verify tools are passed to Gemini's GenerateContentConfig."""
        from google.genai import types
        from ai.utils.llm_config import LLMBase

        tool_declarations = [
            types.Tool(function_declarations=[
                types.FunctionDeclaration(
                    name='list_pages',
                    description='List all pages',
                    parameters=types.Schema(type='OBJECT', properties={}),
                ),
            ])
        ]

        # We're testing the method builds the right config, not the actual API call
        llm = LLMBase()
        # Mock the Google client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = 'Hello!'
        mock_response.candidates = [MagicMock()]
        mock_response.candidates[0].content.parts = [MagicMock(function_call=None)]
        mock_client.models.generate_content.return_value = mock_response
        llm._clients['google'] = mock_client

        result = llm.get_completion_with_tools(
            contents=[{'role': 'user', 'parts': ['hello']}],
            system_instruction='You are an assistant.',
            tools=tool_declarations,
            tool_name='gemini-flash',
        )

        # Verify generate_content was called with tools in config
        call_kwargs = mock_client.models.generate_content.call_args
        self.assertIsNotNone(call_kwargs)
```

**Step 2: Implement `get_completion_with_tools()`**

Add to `LLMBase` in `ai/utils/llm_config.py`:

```python
def get_completion_with_tools(self, contents, system_instruction, tools,
                               tool_name='gemini-flash'):
    """Call Gemini with native function calling.

    Args:
        contents: List of Gemini Content objects (conversation history).
        system_instruction: System instruction string.
        tools: List of types.Tool objects with FunctionDeclarations.
        tool_name: Model config key (e.g. 'gemini-flash').

    Returns:
        The raw Gemini GenerateContentResponse.
    """
    config_entry = MODEL_CONFIG.get(tool_name)
    if not config_entry or config_entry.provider != ModelProvider.GOOGLE:
        raise ValueError(f'Native FC only supported for Google models, got: {tool_name}')

    client = self._clients.get(ModelProvider.GOOGLE)
    if not client:
        raise RuntimeError('Google client not initialized')

    from google.genai import types

    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        tools=tools,
        temperature=config_entry.temperature,
        max_output_tokens=config_entry.max_output_tokens,
        top_p=config_entry.provider_params.get('generation_config', {}).get('top_p', 0.95),
        top_k=config_entry.provider_params.get('generation_config', {}).get('top_k', 40),
    )

    response = client.models.generate_content(
        model=config_entry.model_name,
        contents=contents,
        config=config,
    )

    return response
```

**Step 3: Run tests and commit**

```bash
python manage.py test core.tests.test_llm_function_calling -v 2
git add ai/utils/llm_config.py core/tests/test_llm_function_calling.py
git commit -m "feat: add get_completion_with_tools() for native Gemini function calling"
```

---

## Task 6: Tool Declarations (Native FC Schemas)

**Files:**
- Create: `site_assistant/tool_declarations.py`

**Step 1: Create `site_assistant/tool_declarations.py`**

Define all `FunctionDeclaration` objects organized by category. Use `google.genai.types`. Each tool has `name`, `description`, and `parameters` schema.

Key categories and their tools:

```python
"""Native Gemini FunctionDeclaration schemas for the Site Assistant."""

from google.genai import types

# ---- PAGES ----
PAGES_TOOLS = [
    types.FunctionDeclaration(
        name='list_pages',
        description='List all pages on the site with IDs and active status.',
        parameters=types.Schema(type='OBJECT', properties={}),
    ),
    types.FunctionDeclaration(
        name='get_page_info',
        description='Get page details including section names. Search by ID or title.',
        parameters=types.Schema(type='OBJECT', properties={
            'page_id': types.Schema(type='INTEGER', description='Page ID'),
            'title': types.Schema(type='STRING', description='Search by title (case-insensitive)'),
        }),
    ),
    types.FunctionDeclaration(
        name='create_page',
        description='Create a new page. Provide title in default language; other languages are auto-translated.',
        parameters=types.Schema(type='OBJECT', properties={
            'title': types.Schema(type='STRING', description='Page title in default language'),
            'slug': types.Schema(type='STRING', description='URL slug (auto-generated if omitted)'),
            'title_i18n': types.Schema(type='OBJECT', description='Explicit per-language titles (optional override)'),
            'slug_i18n': types.Schema(type='OBJECT', description='Explicit per-language slugs (optional override)'),
        }, required=['title']),
    ),
    # ... update_page_meta, delete_page, reorder_pages, set_active_page
]

# ---- PAGE EDITING ----
PAGE_EDIT_TOOLS = [
    types.FunctionDeclaration(
        name='refine_section',
        description='AI-regenerate ONE section. Use for structural/design changes. Slower and costlier than style changes.',
        parameters=types.Schema(type='OBJECT', properties={
            'section_name': types.Schema(type='STRING', description='The data-section name to refine'),
            'instructions': types.Schema(type='STRING', description='What to change about this section'),
        }, required=['section_name', 'instructions']),
    ),
    # ... refine_page, update_element_styles, update_element_attribute, remove_section, reorder_sections
]

# ---- NAVIGATION ----
NAVIGATION_TOOLS = [...]

# ---- SETTINGS ----
SETTINGS_TOOLS = [...]

# ---- HEADER/FOOTER ----
HEADER_FOOTER_TOOLS = [
    types.FunctionDeclaration(
        name='refine_header',
        description='AI-regenerate the site header. Use for navigation layout, logo placement, style changes.',
        parameters=types.Schema(type='OBJECT', properties={
            'instructions': types.Schema(type='STRING', description='What to change'),
        }, required=['instructions']),
    ),
    types.FunctionDeclaration(
        name='refine_footer',
        description='AI-regenerate the site footer. Use for footer layout, links, contact info.',
        parameters=types.Schema(type='OBJECT', properties={
            'instructions': types.Schema(type='STRING', description='What to change'),
        }, required=['instructions']),
    ),
]

# ---- FORMS ----
FORMS_TOOLS = [...]

# ---- MEDIA ----
MEDIA_TOOLS = [...]

# ---- NEWS ----
NEWS_TOOLS = [...]

# ---- STATS ----
STATS_TOOLS = [...]

# ---- META (always included) ----
REQUEST_TOOLS_DECLARATION = types.FunctionDeclaration(
    name='request_additional_tools',
    description='Request tools from another category if you need them mid-task.',
    parameters=types.Schema(type='OBJECT', properties={
        'categories': types.Schema(
            type='ARRAY', items=types.Schema(type='STRING'),
            description='Category names: pages, page_edit, navigation, settings, header_footer, forms, media, news, stats',
        ),
    }, required=['categories']),
)

# Category registry
TOOL_CATEGORIES = {
    'pages': PAGES_TOOLS,
    'page_edit': PAGE_EDIT_TOOLS,
    'navigation': NAVIGATION_TOOLS,
    'settings': SETTINGS_TOOLS,
    'header_footer': HEADER_FOOTER_TOOLS,
    'forms': FORMS_TOOLS,
    'media': MEDIA_TOOLS,
    'news': NEWS_TOOLS,
    'stats': STATS_TOOLS,
}


def build_tool_declarations(intents):
    """Build a types.Tool list from router intents."""
    declarations = []
    for intent in intents:
        if intent in TOOL_CATEGORIES:
            declarations.extend(TOOL_CATEGORIES[intent])
    declarations.append(REQUEST_TOOLS_DECLARATION)
    return [types.Tool(function_declarations=declarations)]
```

Complete ALL tool declarations in this file — refer to the existing tool functions in `site_assistant/tools/site_tools.py`, `page_tools.py`, and `news_tools.py` for the exact parameter names and types. Remove `update_translations` (dead code).

**Step 2: Commit**

```bash
git add site_assistant/tool_declarations.py
git commit -m "feat: add native Gemini FunctionDeclaration schemas for all tools"
```

---

## Task 7: Rewrite Tools as Thin Service Adapters

**Files:**
- Rewrite: `site_assistant/tools/site_tools.py`
- Rewrite: `site_assistant/tools/page_tools.py`
- Rewrite: `site_assistant/tools/news_tools.py`
- Modify: `site_assistant/tools/__init__.py`

**Step 1: Rewrite `site_assistant/tools/site_tools.py`**

Every tool becomes a thin adapter:

```python
"""Site-wide tools — thin adapters to core services."""

from core.services import PageService, MenuService, SettingsService, FormService, MediaService


def list_pages(params, context):
    result = PageService.list()
    pages_data = [{'id': p.id, 'title': p.title_i18n, 'slug': p.slug_i18n,
                   'is_active': p.is_active, 'sort_order': p.sort_order}
                  for p in result['pages']]
    return {'success': True, 'pages': pages_data, 'message': result['message']}


def create_page(params, context):
    result = PageService.create(
        title=params.get('title'),
        slug=params.get('slug'),
        title_i18n=params.get('title_i18n'),
        slug_i18n=params.get('slug_i18n'),
        user=context.get('user'),
    )
    if not result['success']:
        return {'success': False, 'message': result['error']}

    page = result['page']
    session = context.get('session')
    if session:
        session.set_active_page(page)
    return {
        'success': True, 'page_id': page.id,
        'message': result['message'], 'set_active_page': page.id,
    }

# ... same pattern for all other tools
```

**Step 2: Rewrite `page_tools.py`** — adapters to `PageService` and `ContentGenerationService`.

Remove `update_translations` (dead code). `refine_section` and `refine_page` use `ContentGenerationService` directly (already a service).

**Step 3: Rewrite `news_tools.py`** — adapters to `NewsService`.

**Step 4: Add new tools** `refine_header` and `refine_footer` — adapters to `GlobalSectionService.refine()`.

**Step 5: Simplify `__init__.py`** — update `ALL_TOOLS` dict, add `delete_form` to `DESTRUCTIVE_TOOLS`.

**Step 6: Run the server, test tool execution manually**

```bash
python manage.py runserver 8002
# Visit /site-assistant/ and test a few tool calls
```

**Step 7: Commit**

```bash
git add site_assistant/tools/
git commit -m "refactor: rewrite assistant tools as thin adapters to service layer"
```

---

## Task 8: Router Implementation

**Files:**
- Create: `site_assistant/router.py`
- Test: `core/tests/test_assistant_router.py`

**Step 1: Write the test**

```python
"""Tests for site_assistant.router — intent classification."""

from unittest.mock import patch, MagicMock
from django.test import TestCase
from site_assistant.router import Router


class RouterClassifyTest(TestCase):

    def setUp(self):
        from core.models import SiteSettings
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}]
        s.default_language = 'pt'
        s.save()

    @patch('site_assistant.router.LLMBase')
    def test_greeting_returns_direct_response(self, MockLLM):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"intents":["greeting"],"needs_active_page":false,"direct_response":"Olá!"}'
        MockLLM.return_value.get_completion.return_value = mock_response

        result = Router.classify('hi', snapshot={}, history='')
        self.assertEqual(result['direct_response'], 'Olá!')

    @patch('site_assistant.router.LLMBase')
    def test_page_edit_returns_intents(self, MockLLM):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"intents":["page_edit"],"needs_active_page":true,"direct_response":null}'
        MockLLM.return_value.get_completion.return_value = mock_response

        result = Router.classify('change the hero title', snapshot={}, history='')
        self.assertIn('page_edit', result['intents'])
        self.assertIsNone(result['direct_response'])
```

**Step 2: Implement `site_assistant/router.py`**

```python
"""Router — Phase 1 of the site assistant.

Lightweight intent classifier using gemini-lite. Determines which tool
categories the executor needs, or responds directly for greetings/questions.
"""

import json
import logging
from ai.utils.llm_config import LLMBase

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
- stats: Detailed site statistics

Rules:
- If greeting or answerable from snapshot, write answer in direct_response (in {default_lang}).
- If it needs tools, set direct_response to null.
- A request can need multiple categories.
- "delete" requests need the relevant category.

{history_section}"""


class Router:

    @staticmethod
    def classify(message, snapshot, history=''):
        """Classify a user message into intents.

        Args:
            message: User's message text.
            snapshot: Dict from SettingsService.get_snapshot().
            history: Compact conversation history string.

        Returns:
            Dict with 'intents' (list), 'needs_active_page' (bool),
            'direct_response' (str or None).
        """
        default_lang = snapshot.get('default_lang', 'pt')
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
            menu_count=snapshot.get('menu_count', 0),
            image_count=snapshot.get('image_count', 0),
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
            response = llm.get_completion(messages, tool_name='gemini-lite')
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
```

**Step 3: Run tests and commit**

```bash
python manage.py test core.tests.test_assistant_router -v 2
git add site_assistant/router.py core/tests/test_assistant_router.py
git commit -m "feat: add Router for gemini-lite intent classification"
```

---

## Task 9: Executor Rewrite + Prompt Restructuring

**Files:**
- Rewrite: `site_assistant/services.py`
- Rewrite: `site_assistant/prompts.py`

This is the main rewrite. The executor uses native Gemini function calling.

**Step 1: Rewrite `site_assistant/prompts.py`**

Replace `TOOL_DEFINITIONS`, `RESPONSE_PROTOCOL` and `build_system_prompt()` with:
- `build_router_snapshot()` — builds the compact site state dict
- `build_executor_prompt()` — builds the system instruction for Phase 2
- `build_active_page_context()` — builds the active page section (extracted from current `build_page_context`)

Remove: `TOOL_DEFINITIONS`, `RESPONSE_PROTOCOL`, `build_user_prompt()`. These are all replaced by native FC.

**Step 2: Rewrite `site_assistant/services.py`**

Replace the entire `AssistantService` class with the two-phase flow:

```python
class AssistantService:

    def handle_message(self, message, user=None):
        # 1. Build snapshot
        snapshot = SettingsService.get_snapshot()

        # 2. Phase 1: Router
        history = self.session.get_history_for_prompt(max_turns=3)
        router_result = Router.classify(message, snapshot, history)

        # 3. If direct response, return immediately
        if router_result['direct_response']:
            self.session.add_message('user', message)
            self.session.add_message('assistant', router_result['direct_response'])
            return {
                'response': router_result['direct_response'],
                'actions': [], 'steps': [], 'pending_confirmation': None,
                'set_active_page': None,
            }

        # 4. Phase 2: Executor with native FC
        return self._execute_phase2(message, router_result['intents'], user, snapshot)

    def _execute_phase2(self, message, intents, user, snapshot):
        # Build system instruction
        system_instruction = build_executor_prompt(self.session, snapshot)

        # Build tool declarations from intents
        tool_decls = build_tool_declarations(intents)

        # Build Gemini contents from conversation history
        contents = self._build_contents(message)

        # Tool execution loop (max 8 iterations)
        # Uses llm.get_completion_with_tools()
        # Feeds back results via Part.from_function_response()
        # Refreshes system_instruction after PAGE_CONTEXT_MUTATIONS
        ...
```

Remove: `_parse_response()`, `_format_tool_results()`, `_verify_actions()`, `_retry_for_verification()`, `WRITE_TOOLS`, `WRITE_CLAIM_KEYWORDS`.

**Step 3: Update `site_assistant/views.py`**

- Remove `confirm_api` view and its URL pattern
- Simplify `chat_api` — the service handles everything

**Step 4: Update `site_assistant/urls.py`**

Remove the confirm URL pattern.

**Step 5: Test end-to-end**

```bash
python manage.py runserver 8002
# Visit /site-assistant/ and test:
# 1. "hi" → should get direct response (0 tool calls)
# 2. "how many pages?" → should get direct response from snapshot
# 3. "list all pages" → should use native FC to call list_pages
# 4. "create a new About page" → should call create_page with auto-translate
# 5. "delete the About page" → should ask for confirmation first
```

**Step 6: Commit**

```bash
git add site_assistant/services.py site_assistant/prompts.py site_assistant/views.py site_assistant/urls.py
git commit -m "feat: rewrite assistant with router pattern and native Gemini function calling"
```

---

## Task 10: Frontend Cleanup + Final Testing

**Files:**
- Modify: `site_assistant/templates/site_assistant/assistant.html`

**Step 1: Update frontend**

The frontend needs minor updates:
- Remove the Confirm/Cancel button handling (confirmation is now conversational)
- The response format is the same (JSON with `response`, `actions`, `steps`)
- Tool result rendering stays the same

**Step 2: Full end-to-end testing**

Test all flows through the UI:
1. Greetings → direct response, no tool calls
2. Page CRUD → create, list, rename, delete (with confirmation)
3. Menu management → create items, reorder
4. Settings → change colors, update briefing
5. Page editing → refine section, update styles
6. Header/footer → refine header, refine footer (new!)
7. News → list posts, create post
8. Multi-step → "create a page and add it to the menu"
9. Mid-execution discovery → request that needs tools from unexpected category

**Step 3: Verify response language**

All responses should be in the site's default language only. No bilingual responses.

**Step 4: Final commit**

```bash
git add site_assistant/templates/
git commit -m "feat: update assistant frontend for v2 (remove confirmation buttons)"
```

---

## Summary

| Task | What | Files |
|------|------|-------|
| 1 | i18n helper | `core/services/i18n.py` |
| 2 | PageService | `core/services/pages.py` |
| 3 | Menu, Settings, Form, Media services | `core/services/menu.py`, `settings.py`, `forms.py`, `media.py` |
| 4 | GlobalSection + News services | `core/services/global_sections.py`, `news/services.py` |
| 5 | LLM native FC support | `ai/utils/llm_config.py` |
| 6 | Tool declarations | `site_assistant/tool_declarations.py` |
| 7 | Tool adapters rewrite | `site_assistant/tools/*.py` |
| 8 | Router | `site_assistant/router.py` |
| 9 | Executor + prompts rewrite | `site_assistant/services.py`, `prompts.py` |
| 10 | Frontend + testing | `site_assistant/templates/...` |

Each task builds on the previous. Tasks 1-4 (service layer) are independent of the assistant and immediately useful for the rest of the codebase. Tasks 5-9 are the assistant-specific changes. Task 10 is integration testing.
