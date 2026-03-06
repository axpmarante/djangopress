"""Tests for core.services.pages — PageService."""

from unittest.mock import patch
from django.test import TestCase
from djangopress.core.models import Page, SiteSettings
from djangopress.core.services.pages import PageService


class PageServiceListTest(TestCase):

    def setUp(self):
        # Clear any pages created by migrations (e.g. 0021_create_homepage_clone)
        Page.objects.all().delete()
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

    def test_list_ordered_by_sort_order(self):
        result = PageService.list()
        pages = result['pages']
        self.assertEqual(pages[0].sort_order, 0)
        self.assertEqual(pages[1].sort_order, 1)
        self.assertEqual(pages[2].sort_order, 2)


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

    def test_get_by_title_case_insensitive(self):
        result = PageService.get(title='contacto')
        self.assertTrue(result['success'])
        self.assertEqual(result['page'].id, self.page.id)

    def test_get_by_title_partial_match(self):
        result = PageService.get(title='Contac')
        self.assertTrue(result['success'])
        self.assertEqual(result['page'].id, self.page.id)

    def test_get_not_found(self):
        result = PageService.get(page_id=99999)
        self.assertFalse(result['success'])

    def test_get_no_params(self):
        result = PageService.get()
        self.assertFalse(result['success'])


class PageServiceGetInfoTest(TestCase):

    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        self.page = Page.objects.create(
            title_i18n={'pt': 'Test', 'en': 'Test'},
            slug_i18n={'pt': 'test', 'en': 'test'},
            html_content_i18n={
                'pt': '<section data-section="hero" id="hero"><h1>Olá Mundo</h1></section><section data-section="about" id="about"><p>Sobre nós</p></section>',
                'en': '<section data-section="hero" id="hero"><h1>Hello World</h1></section><section data-section="about" id="about"><p>About us</p></section>',
            },
        )

    def test_get_info_returns_sections(self):
        result = PageService.get_info(self.page.id)
        self.assertTrue(result['success'])
        self.assertEqual(len(result['sections']), 2)
        self.assertEqual(result['sections'][0]['name'], 'hero')
        self.assertEqual(result['sections'][1]['name'], 'about')

    def test_get_info_section_preview(self):
        result = PageService.get_info(self.page.id)
        # Preview is from default language (pt)
        self.assertIn('Olá', result['sections'][0]['preview'])

    def test_get_info_languages(self):
        result = PageService.get_info(self.page.id)
        self.assertIn('pt', result['languages'])
        self.assertIn('en', result['languages'])

    def test_get_info_not_found(self):
        result = PageService.get_info(99999)
        self.assertFalse(result['success'])


class PageServiceCreateTest(TestCase):

    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()

    @patch('djangopress.core.services.i18n._translate_text', return_value='About Us')
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

    def test_create_with_html_content(self):
        html = {
            'pt': '<section data-section="hero" id="hero"><h1>Olá</h1></section>',
            'en': '<section data-section="hero" id="hero"><h1>Hello</h1></section>',
        }
        result = PageService.create(
            title_i18n={'pt': 'Test', 'en': 'Test'},
            slug_i18n={'pt': 'test', 'en': 'test'},
            html_content_i18n=html,
        )
        self.assertTrue(result['success'])
        self.assertEqual(result['page'].html_content_i18n, html)

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

    def test_create_inactive(self):
        result = PageService.create(
            title_i18n={'pt': 'Draft', 'en': 'Draft'},
            slug_i18n={'pt': 'draft', 'en': 'draft'},
            is_active=False,
        )
        self.assertTrue(result['success'])
        self.assertFalse(result['page'].is_active)


class PageServiceUpdateMetaTest(TestCase):

    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        self.page = Page.objects.create(
            title_i18n={'pt': 'Original', 'en': 'Original'},
            slug_i18n={'pt': 'original', 'en': 'original'},
            is_active=True,
            sort_order=0,
        )

    def test_update_title(self):
        result = PageService.update_meta(
            self.page.id, title_i18n={'pt': 'Novo', 'en': 'New'},
        )
        self.assertTrue(result['success'])
        self.page.refresh_from_db()
        self.assertEqual(self.page.title_i18n['pt'], 'Novo')

    def test_update_slug(self):
        result = PageService.update_meta(
            self.page.id, slug_i18n={'pt': 'novo', 'en': 'new'},
        )
        self.assertTrue(result['success'])
        self.page.refresh_from_db()
        self.assertEqual(self.page.slug_i18n['pt'], 'novo')

    def test_update_slug_duplicate_fails(self):
        Page.objects.create(
            title_i18n={'pt': 'Other', 'en': 'Other'},
            slug_i18n={'pt': 'other', 'en': 'other'},
        )
        result = PageService.update_meta(
            self.page.id, slug_i18n={'pt': 'other', 'en': 'other'},
        )
        self.assertFalse(result['success'])
        self.assertIn('slug', result['error'].lower())

    def test_update_is_active(self):
        result = PageService.update_meta(self.page.id, is_active=False)
        self.assertTrue(result['success'])
        self.page.refresh_from_db()
        self.assertFalse(self.page.is_active)

    def test_update_sort_order(self):
        result = PageService.update_meta(self.page.id, sort_order=5)
        self.assertTrue(result['success'])
        self.page.refresh_from_db()
        self.assertEqual(self.page.sort_order, 5)

    def test_update_not_found(self):
        result = PageService.update_meta(99999, title_i18n={'pt': 'X'})
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


class PageServiceReorderTest(TestCase):

    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}]
        s.default_language = 'pt'
        s.save()
        self.p1 = Page.objects.create(title_i18n={'pt': 'A'}, slug_i18n={'pt': 'a'}, sort_order=0)
        self.p2 = Page.objects.create(title_i18n={'pt': 'B'}, slug_i18n={'pt': 'b'}, sort_order=1)
        self.p3 = Page.objects.create(title_i18n={'pt': 'C'}, slug_i18n={'pt': 'c'}, sort_order=2)

    def test_reorder(self):
        result = PageService.reorder([
            {'page_id': self.p3.id, 'sort_order': 0},
            {'page_id': self.p1.id, 'sort_order': 1},
            {'page_id': self.p2.id, 'sort_order': 2},
        ])
        self.assertTrue(result['success'])
        self.p1.refresh_from_db()
        self.p2.refresh_from_db()
        self.p3.refresh_from_db()
        self.assertEqual(self.p3.sort_order, 0)
        self.assertEqual(self.p1.sort_order, 1)
        self.assertEqual(self.p2.sort_order, 2)

    def test_reorder_empty_fails(self):
        result = PageService.reorder([])
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
        for lang in ['pt', 'en']:
            self.assertIn('text-4xl', self.page.html_content_i18n[lang])
            self.assertIn('font-bold', self.page.html_content_i18n[lang])
            self.assertNotIn('text-2xl', self.page.html_content_i18n[lang])

    def test_update_styles_by_section_name(self):
        result = PageService.update_element_styles(
            self.page, section_name='hero',
            new_classes='bg-blue-500 p-8',
        )
        self.assertTrue(result['success'])
        self.page.refresh_from_db()
        for lang in ['pt', 'en']:
            self.assertIn('bg-blue-500', self.page.html_content_i18n[lang])

    def test_update_styles_remove_classes(self):
        result = PageService.update_element_styles(
            self.page, selector='section[data-section="hero"] h1',
            new_classes='',
        )
        self.assertTrue(result['success'])
        self.page.refresh_from_db()
        for lang in ['pt', 'en']:
            self.assertNotIn('text-2xl', self.page.html_content_i18n[lang])

    def test_update_styles_no_selector_fails(self):
        result = PageService.update_element_styles(self.page)
        self.assertFalse(result['success'])


class PageServiceUpdateAttributeTest(TestCase):

    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        self.page = Page.objects.create(
            title_i18n={'pt': 'Test', 'en': 'Test'},
            slug_i18n={'pt': 'test', 'en': 'test'},
            html_content_i18n={
                'pt': '<section data-section="hero" id="hero"><a href="/old" class="btn">Link</a></section>',
                'en': '<section data-section="hero" id="hero"><a href="/old" class="btn">Link</a></section>',
            },
        )

    def test_update_attribute_applies_to_all_langs(self):
        result = PageService.update_element_attribute(
            self.page, selector='section[data-section="hero"] a',
            attribute='href', value='/new',
        )
        self.assertTrue(result['success'])
        self.page.refresh_from_db()
        for lang in ['pt', 'en']:
            self.assertIn('href="/new"', self.page.html_content_i18n[lang])
            self.assertNotIn('href="/old"', self.page.html_content_i18n[lang])

    def test_update_attribute_remove(self):
        result = PageService.update_element_attribute(
            self.page, selector='section[data-section="hero"] a',
            attribute='href', value='',
        )
        self.assertTrue(result['success'])
        self.page.refresh_from_db()
        for lang in ['pt', 'en']:
            self.assertNotIn('href=', self.page.html_content_i18n[lang])

    def test_update_attribute_missing_params(self):
        result = PageService.update_element_attribute(self.page, selector='', attribute='')
        self.assertFalse(result['success'])


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

    def test_remove_section_missing_name(self):
        result = PageService.remove_section(self.page, '')
        self.assertFalse(result['success'])


class PageServiceReorderSectionsTest(TestCase):

    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        self.page = Page.objects.create(
            title_i18n={'pt': 'Test', 'en': 'Test'},
            slug_i18n={'pt': 'test', 'en': 'test'},
            html_content_i18n={
                'pt': '<section data-section="hero" id="hero"><h1>Hero</h1></section><section data-section="about" id="about"><p>About</p></section><section data-section="cta" id="cta"><p>CTA</p></section>',
                'en': '<section data-section="hero" id="hero"><h1>Hero</h1></section><section data-section="about" id="about"><p>About</p></section><section data-section="cta" id="cta"><p>CTA</p></section>',
            },
        )

    def test_reorder_sections(self):
        result = PageService.reorder_sections(self.page, ['cta', 'hero', 'about'])
        self.assertTrue(result['success'])
        self.page.refresh_from_db()
        from bs4 import BeautifulSoup
        for lang in ['pt', 'en']:
            soup = BeautifulSoup(self.page.html_content_i18n[lang], 'html.parser')
            sections = soup.find_all('section', attrs={'data-section': True})
            self.assertEqual(sections[0]['data-section'], 'cta')
            self.assertEqual(sections[1]['data-section'], 'hero')
            self.assertEqual(sections[2]['data-section'], 'about')

    def test_reorder_empty_fails(self):
        result = PageService.reorder_sections(self.page, [])
        self.assertFalse(result['success'])


class PageServiceSaveSectionHtmlTest(TestCase):

    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        self.page = Page.objects.create(
            title_i18n={'pt': 'Test', 'en': 'Test'},
            slug_i18n={'pt': 'test', 'en': 'test'},
            html_content_i18n={
                'pt': '<section data-section="hero" id="hero"><h1>Olá</h1></section>',
                'en': '<section data-section="hero" id="hero"><h1>Hello</h1></section>',
            },
        )

    def test_save_section_replaces_in_target_lang(self):
        new_html = '<section data-section="hero" id="hero"><h1>Novo título</h1><p>Descrição</p></section>'
        result = PageService.save_section_html(self.page, 'hero', new_html, lang='pt')
        self.assertTrue(result['success'])
        self.page.refresh_from_db()
        self.assertIn('Novo título', self.page.html_content_i18n['pt'])
        self.assertIn('Descrição', self.page.html_content_i18n['pt'])
        # English should remain unchanged
        self.assertIn('Hello', self.page.html_content_i18n['en'])
        self.assertNotIn('Novo título', self.page.html_content_i18n['en'])

    def test_save_section_defaults_to_default_lang(self):
        new_html = '<section data-section="hero" id="hero"><h1>Default lang</h1></section>'
        result = PageService.save_section_html(self.page, 'hero', new_html)
        self.assertTrue(result['success'])
        self.page.refresh_from_db()
        self.assertIn('Default lang', self.page.html_content_i18n['pt'])

    def test_save_section_appends_if_not_found(self):
        new_html = '<section data-section="new-section" id="new-section"><p>New</p></section>'
        result = PageService.save_section_html(self.page, 'new-section', new_html, lang='pt')
        self.assertTrue(result['success'])
        self.page.refresh_from_db()
        self.assertIn('data-section="new-section"', self.page.html_content_i18n['pt'])
        self.assertIn('data-section="hero"', self.page.html_content_i18n['pt'])


class PageServiceSlugUniquenessTest(TestCase):
    """Test the internal _check_slug_uniqueness helper."""

    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        self.page = Page.objects.create(
            title_i18n={'pt': 'Existing', 'en': 'Existing'},
            slug_i18n={'pt': 'existing', 'en': 'existing'},
        )

    def test_unique_slugs_pass(self):
        from djangopress.core.services.pages import _check_slug_uniqueness
        error = _check_slug_uniqueness({'pt': 'new-page', 'en': 'new-page'})
        self.assertIsNone(error)

    def test_duplicate_slug_detected(self):
        from djangopress.core.services.pages import _check_slug_uniqueness
        error = _check_slug_uniqueness({'pt': 'existing', 'en': 'different'})
        self.assertIsNotNone(error)
        self.assertIn('existing', error)

    def test_exclude_self_allows_update(self):
        from djangopress.core.services.pages import _check_slug_uniqueness
        error = _check_slug_uniqueness(
            {'pt': 'existing', 'en': 'existing'},
            exclude_page_id=self.page.id,
        )
        self.assertIsNone(error)
