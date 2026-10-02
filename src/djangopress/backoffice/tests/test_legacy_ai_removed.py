"""The old AI workflows the visual editor replaces are gone (page Chat Refine, the
page/news image screens, news AI Refine, dead endpoints and files), and nothing
that linked to them breaks. AI features without a replacement stay."""
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from djangopress.core.models import Page, SiteSettings

REMOVED = [
    ('backoffice:ai_chat_refine', {'page_id': 1}), ('backoffice:ai_refine_page', {}),
    ('backoffice:ai_refine_page_with_slug', {'page_slug': 'x'}), ('backoffice:process_images', {'page_id': 1}),
    ('backoffice:ai_bulk_pages', {}), ('backoffice:news_ai_refine', {'pk': 1}), ('backoffice:news_images', {'pk': 1}),
    ('ai:generate_page', {}), ('ai:refine_page_with_html', {}), ('ai:refine_header', {}), ('ai:refine_footer', {}),
    ('ai:chat_refine_page', {}), ('ai:chat_refine_page_stream', {}), ('ai:get_refinement_session', {'session_id': 1}),
    ('ai:list_refinement_sessions', {'page_id': 1}), ('ai:propagate_translation', {}), ('ai:generate_news_post', {}),
    ('ai:chat_refine_news', {}), ('ai:chat_refine_news_stream', {}), ('ai:list_news_refinement_sessions', {'post_id': 1}),
]
KEPT = [
    ('backoffice:ai_generate_page', {}), ('backoffice:news_ai_generate', {}), ('backoffice:news_ai_bulk', {}),
    ('backoffice:ai_bulk_translate', {}), ('ai:generate_page_stream', {}), ('ai:save_page', {}),
    ('ai:refine_header_stream', {}), ('ai:refine_footer_stream', {}), ('ai:enhance_prompt', {}),
    ('ai:analyze_page_images', {}), ('ai:process_page_images', {}), ('ai:search_unsplash', {}),
    ('ai:translate_to_language', {}), ('ai:bulk_translate', {}), ('ai:describe_images', {}),
    ('ai:generate_design_guide_ai', {}), ('ai:sync_settings_from_guide', {}), ('ai:suggest_page_sections', {}),
    ('ai:fill_section_content', {}), ('ai:analyze_consistency_stream', {}), ('ai:fix_consistency_stream', {}),
    ('ai:generate_news_post_stream', {}), ('ai:save_news_post', {}), ('ai:analyze_bulk_pages', {}),
]
DEAD_FILES = ['backoffice/templates/backoffice/ai_management.html', 'backoffice/templates/backoffice/ai_settings.html',
              'backoffice/templates/backoffice/includes/ai_assistant_modal.html',
              'backoffice/static/backoffice/js/ai_assistant.js', 'backoffice/templates/backoffice/ai_bulk_pages.html',
              'backoffice/templates/backoffice/ai_chat_refine.html', 'backoffice/templates/backoffice/ai_refine_page.html',
              'backoffice/templates/backoffice/process_images.html', 'backoffice/templates/backoffice/news_images.html']


class LegacyAIRemovedTest(TestCase):
    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        self.page = Page.objects.create(title_i18n={'pt': 'Início'}, slug_i18n={'pt': 'inicio'}, is_active=True,
                                        html_content_i18n={'pt': '<section data-section="hero"><h1>Olá</h1></section>'})
        from djangopress.news.models import NewsPost
        self.post = NewsPost.objects.create(title_i18n={'pt': 'Notícia'}, slug_i18n={'pt': 'noticia'},
                                            html_content_i18n={'pt': '<p>x</p>'}, is_published=True)
        self.client.force_login(get_user_model().objects.create_superuser('a', 'a@x.com', 'pw'))

    def test_the_replaced_routes_are_gone(self):
        for name, kwargs in REMOVED:
            with self.assertRaises(NoReverseMatch, msg=name):
                reverse(name, kwargs=kwargs)

    def test_the_features_without_a_replacement_stay(self):
        for name, kwargs in KEPT:
            reverse(name, kwargs=kwargs)

    def test_dead_files_are_gone(self):
        root = Path(__file__).resolve().parents[2]
        self.assertEqual([f for f in DEAD_FILES if (root / f).exists()], [])

    def test_the_screens_that_linked_to_them_still_open(self):
        for url in (reverse('backoffice:page_edit', kwargs={'page_id': self.page.pk}), reverse('backoffice:pages'),
                    reverse('backoffice:news_list'), reverse('backoffice:blueprint'), '/backoffice/'):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_news_rows_open_the_post_in_the_editor(self):
        html = self.client.get(reverse('backoffice:news_list')).content.decode()
        self.assertIn(f'{self.post.get_absolute_url()}?edit=v2', html)
        self.assertNotIn('Process Images', html)
