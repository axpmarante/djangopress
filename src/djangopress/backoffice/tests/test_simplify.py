"""Simplified backoffice: pages open in the editor, a short menu, and a Home
that is an assistant for superusers and shortcuts for staff."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from djangopress.core.models import Page, SiteSettings

User = get_user_model()

# Tools kept in code (reachable by URL) but no longer in the menu.
HIDDEN_TOOLS = ('blueprint', 'ai_call_logs', 'benchmarks', 'consistency_reports', 'overview')


class BackofficeTestCase(TestCase):
    def setUp(self):
        Page.objects.all().delete()
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        self.live = Page.objects.create(
            title_i18n={'pt': 'Sobre', 'en': 'About'}, slug_i18n={'pt': 'sobre', 'en': 'about'},
            is_active=True, html_content_i18n={'pt': '<section data-section="a"></section>'},
        )
        self.draft = Page.objects.create(
            title_i18n={'pt': 'Rascunho', 'en': 'Draft'}, slug_i18n={'pt': 'rascunho', 'en': 'draft'},
            is_active=False, html_content_i18n={'pt': '<section data-section="b"></section>'},
        )
        self.admin = User.objects.create_superuser('admin', 'a@example.com', 'pw')
        self.staff = User.objects.create_user('staff', 's@example.com', 'pw', is_staff=True)

    def get(self, url, user):
        self.client.force_login(user)
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200, url)
        return res.content.decode()


class PagesListTest(BackofficeTestCase):
    def test_edit_opens_the_page_in_the_editor(self):
        html = self.get(reverse('backoffice:pages'), self.admin)
        self.assertIn(f'{self.live.get_absolute_url()}?edit=v2', html)

    def test_edit_on_a_draft_uses_preview(self):
        html = self.get(reverse('backoffice:pages'), self.admin)
        self.assertIn(f'{self.draft.get_absolute_url()}?preview=true&amp;edit=v2', html)

    def test_settings_link_goes_to_page_settings(self):
        html = self.get(reverse('backoffice:pages'), self.admin)
        self.assertIn(reverse('backoffice:page_edit', args=[self.live.id]), html)
        self.assertIn('>Settings<', html)

    def test_page_settings_screen_is_named_page_settings(self):
        html = self.get(reverse('backoffice:page_edit', args=[self.live.id]), self.admin)
        self.assertIn('Page settings', html)


class SidebarTest(BackofficeTestCase):
    def test_menu_keeps_the_daily_tools(self):
        html = self.get(reverse('backoffice:pages'), self.admin)
        for name in ('pages', 'media', 'forms', 'menu', 'settings', 'ai_bulk_translate'):
            self.assertIn(f'href="{reverse(f"backoffice:{name}")}"', html, name)
        self.assertIn('>Home<', html)

    def test_unused_tools_leave_the_menu(self):
        html = self.get(reverse('backoffice:pages'), self.admin)
        for name in HIDDEN_TOOLS:
            self.assertNotIn(f'href="{reverse(f"backoffice:{name}")}"', html, name)
        self.assertNotIn('href="/site-assistant/"', html)

    def test_unused_tools_still_open_by_url(self):
        self.client.force_login(self.admin)
        for name in HIDDEN_TOOLS:
            self.assertEqual(self.client.get(reverse(f'backoffice:{name}')).status_code, 200, name)

    def test_staff_do_not_see_translate(self):
        html = self.get(reverse('backoffice:pages'), self.staff)
        self.assertNotIn(f'href="{reverse("backoffice:ai_bulk_translate")}"', html)


class HomeTest(BackofficeTestCase):
    def test_superuser_home_is_the_assistant(self):
        html = self.get(reverse('backoffice:dashboard'), self.admin)
        self.assertIn('id="bo-home-assistant"', html)
        self.assertIn(reverse('site_assistant:chat_api'), html)

    def test_staff_home_is_shortcuts_without_chat(self):
        html = self.get(reverse('backoffice:dashboard'), self.staff)
        self.assertNotIn('id="bo-home-assistant"', html)
        self.assertNotIn(reverse('site_assistant:chat_api'), html)
        self.assertIn('id="bo-home-shortcuts"', html)
        for name in ('pages', 'media', 'forms'):
            self.assertIn(f'href="{reverse(f"backoffice:{name}")}"', html, name)

    def test_assistant_api_stays_superuser_only(self):
        self.client.force_login(self.staff)
        res = self.client.post(reverse('site_assistant:chat_api'), data='{"message": "x"}', content_type='application/json')
        self.assertNotEqual(res.status_code, 200)

    def test_old_dashboard_lives_on_as_overview(self):
        html = self.get(reverse('backoffice:overview'), self.admin)
        self.assertIn('Overview', html)


class PageSettingsTest(BackofficeTestCase):
    def test_page_settings_links_to_the_editor(self):
        html = self.get(reverse('backoffice:page_edit', args=[self.draft.id]), self.admin)
        self.assertIn(f'{self.draft.get_absolute_url()}?preview=true&amp;edit=v2', html)


class ChromeTest(BackofficeTestCase):
    def test_no_template_comment_leaks_into_the_menu(self):
        html = self.get(reverse('backoffice:pages'), self.admin)
        self.assertNotIn('{#', html)
        self.assertNotIn('Tools kept in code', html)

    def test_header_does_not_claim_every_page_is_the_dashboard(self):
        import re
        for name in ('dashboard', 'pages', 'media'):
            html = self.get(reverse(f'backoffice:{name}'), self.admin)
            self.assertIsNone(re.search(r'<h1[^>]*>\s*Dashboard', html), name)

    def test_home_has_no_second_chat_bubble(self):
        self.assertNotIn('chatWidget()', self.get(reverse('backoffice:dashboard'), self.admin))
        self.assertIn('chatWidget()', self.get(reverse('backoffice:pages'), self.admin))
