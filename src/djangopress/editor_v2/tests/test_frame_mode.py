"""?ev2_frame=1 renders the page for the editor's true-width device preview:
no editor UI, no admin toolbar, plus the bridge script — editors only."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from djangopress.core.models import Page, SiteSettings

HTML = '<section data-section="hero" id="hero"><h1>Olá</h1></section>'


class FrameModeTest(TestCase):
    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}]
        s.default_language = 'pt'
        s.save()
        Page.objects.all().delete()
        self.page = Page.objects.create(title_i18n={'pt': 'Reservas'}, slug_i18n={'pt': 'reservas'}, is_active=True,
                                        html_content_i18n={'pt': HTML})
        self.staff = get_user_model().objects.create_user('ed', 'ed@x.com', 'pw', is_staff=True)
        self.url = self.page.get_absolute_url()

    def get(self, query):
        return self.client.get(self.url + query, follow=True).content.decode()

    def test_editor_gets_the_bridge_and_no_editor_ui(self):
        self.client.force_login(self.staff)
        html = self.get('?ev2_frame=1')
        self.assertIn('editor_v2/js/frame-bridge.js', html)
        self.assertNotIn('editor-v2-content', html)
        self.assertNotIn('editor_v2/js/editor.js', html)
        self.assertIn('Olá', html)

    def test_anonymous_gets_the_normal_page(self):
        html = self.get('?ev2_frame=1')
        self.assertNotIn('frame-bridge.js', html)

    def test_non_staff_user_gets_the_normal_page(self):
        user = get_user_model().objects.create_user('v', 'v@x.com', 'pw')
        self.client.force_login(user)
        self.assertNotIn('frame-bridge.js', self.get('?ev2_frame=1'))

    def test_normal_editor_page_has_no_bridge(self):
        self.client.force_login(self.staff)
        html = self.get('?edit=v2')
        self.assertNotIn('frame-bridge.js', html)
        self.assertIn('editor-v2-content', html)

    def test_frame_mode_may_be_framed_by_the_editor_only(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.url + '?ev2_frame=1')['X-Frame-Options'], 'SAMEORIGIN')
        self.assertEqual(self.client.get(self.url)['X-Frame-Options'], 'DENY')
