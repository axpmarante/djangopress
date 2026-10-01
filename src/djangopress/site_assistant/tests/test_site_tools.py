from django.test import TestCase

from djangopress.core.models import Page, SiteSettings
from djangopress.site_assistant.tools.site_tools import get_page_info


class GetPageInfoTest(TestCase):
    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        self.page = Page.objects.create(
            title_i18n={'pt': 'Reservas', 'en': 'Book a table'}, slug_i18n={'pt': 'reservas', 'en': 'book-a-table'},
            meta_title_i18n={'pt': 'Reservar mesa — Casa', 'en': 'Book a table — Casa'},
            meta_description_i18n={'pt': 'Reserve online.', 'en': 'Book online.'},
            is_active=True, html_content_i18n={'pt': '<section data-section="hero" id="hero"></section>'},
        )

    def test_includes_seo_fields(self):
        """Without them the assistant guesses the SEO title instead of reading it."""
        result = get_page_info({'page_id': self.page.id}, {})
        self.assertTrue(result['success'])
        self.assertEqual(result['page']['meta_title'], {'pt': 'Reservar mesa — Casa', 'en': 'Book a table — Casa'})
        self.assertEqual(result['page']['meta_description'], {'pt': 'Reserve online.', 'en': 'Book online.'})


class UpdatePageMetaTest(GetPageInfoTest):
    def test_seo_fields_are_updated_and_merged_per_language(self):
        from djangopress.site_assistant.tools.site_tools import update_page_meta
        result = update_page_meta({'page_id': self.page.id, 'meta_title_i18n': {'pt': 'Novo título SEO'},
                                   'meta_description_i18n': {'en': 'New description.'}}, {})
        self.assertTrue(result['success'], result)
        self.page.refresh_from_db()
        self.assertEqual(self.page.meta_title_i18n, {'pt': 'Novo título SEO', 'en': 'Book a table — Casa'})
        self.assertEqual(self.page.meta_description_i18n, {'pt': 'Reserve online.', 'en': 'New description.'})
        self.assertEqual(self.page.title_i18n, {'pt': 'Reservas', 'en': 'Book a table'})   # page name untouched

    def test_partial_title_and_slug_keep_other_languages(self):
        from djangopress.site_assistant.tools.site_tools import update_page_meta
        update_page_meta({'page_id': self.page.id, 'title_i18n': {'pt': 'Reservar'}, 'slug_i18n': {'pt': 'reservar'}}, {})
        self.page.refresh_from_db()
        self.assertEqual(self.page.title_i18n, {'pt': 'Reservar', 'en': 'Book a table'})
        self.assertEqual(self.page.slug_i18n, {'pt': 'reservar', 'en': 'book-a-table'})

    def test_declaration_tells_the_model_where_seo_lives(self):
        from djangopress.site_assistant.tool_declarations import UPDATE_PAGE_META
        props = UPDATE_PAGE_META.parameters.properties
        self.assertIn('meta_title_i18n', props)
        self.assertIn('meta_description_i18n', props)
        self.assertIn('SEO', UPDATE_PAGE_META.description)
