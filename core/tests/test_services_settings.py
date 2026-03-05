"""Tests for core.services.settings — SettingsService."""

from django.test import TestCase
from core.models import Page, SiteSettings, MenuItem, SiteImage, DynamicForm, FormSubmission
from core.services.settings import SettingsService


class SettingsServiceGetTest(TestCase):

    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.site_name_i18n = {'pt': 'Test Site', 'en': 'Test Site'}
        s.contact_email = 'test@example.com'
        s.primary_color = '#ff0000'
        s.save()

    def test_get_all(self):
        result = SettingsService.get()
        self.assertTrue(result['success'])
        settings = result['settings']
        self.assertEqual(settings['contact_email'], 'test@example.com')
        self.assertEqual(settings['primary_color'], '#ff0000')
        self.assertIn('site_name', settings)
        self.assertIn('default_language', settings)
        self.assertIn('enabled_languages', settings)
        self.assertIn('design_guide', settings)

    def test_get_filtered(self):
        result = SettingsService.get(fields=['contact_email', 'primary_color'])
        self.assertTrue(result['success'])
        settings = result['settings']
        self.assertEqual(len(settings), 2)
        self.assertIn('contact_email', settings)
        self.assertIn('primary_color', settings)
        self.assertNotIn('site_name', settings)


class SettingsServiceUpdateTest(TestCase):

    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()

    def test_update_allowed_field(self):
        result = SettingsService.update({'contact_email': 'new@example.com'})
        self.assertTrue(result['success'])
        s = SiteSettings.load()
        self.assertEqual(s.contact_email, 'new@example.com')

    def test_update_multiple_allowed_fields(self):
        result = SettingsService.update({
            'contact_email': 'multi@example.com',
            'primary_color': '#00ff00',
        })
        self.assertTrue(result['success'])
        s = SiteSettings.load()
        self.assertEqual(s.contact_email, 'multi@example.com')
        self.assertEqual(s.primary_color, '#00ff00')

    def test_update_blocked_field(self):
        result = SettingsService.update({'domain': 'hacked'})
        self.assertFalse(result['success'])
        self.assertIn('protected', result['error'].lower())
        self.assertIn('domain', result['error'])

    def test_update_empty_fails(self):
        result = SettingsService.update({})
        self.assertFalse(result['success'])

    def test_update_mixed_allowed_and_blocked_fails(self):
        """If any field is blocked, the entire update is rejected."""
        result = SettingsService.update({
            'contact_email': 'ok@example.com',
            'domain': 'bad',
        })
        self.assertFalse(result['success'])
        self.assertIn('domain', result['error'])


class SettingsServiceSnapshotTest(TestCase):

    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.site_name_i18n = {'pt': 'Snapshot Site', 'en': 'Snapshot Site'}
        s.save()
        # Clean slate
        Page.objects.all().delete()
        MenuItem.objects.all().delete()

    def test_get_snapshot(self):
        # Create some data
        p1 = Page.objects.create(
            title_i18n={'pt': 'Home', 'en': 'Home'},
            slug_i18n={'pt': 'home', 'en': 'home'},
            is_active=True,
        )
        p2 = Page.objects.create(
            title_i18n={'pt': 'Sobre', 'en': 'About'},
            slug_i18n={'pt': 'sobre', 'en': 'about'},
            is_active=False,
        )
        m1 = MenuItem.objects.create(
            label_i18n={'pt': 'Home', 'en': 'Home'},
            page=p1,
            sort_order=0,
        )
        MenuItem.objects.create(
            label_i18n={'pt': 'Sub', 'en': 'Sub'},
            url='/sub',
            parent=m1,
            sort_order=0,
        )

        result = SettingsService.get_snapshot()
        self.assertTrue(result['success'])
        snap = result['snapshot']
        self.assertEqual(snap['site_name'], 'Snapshot Site')
        self.assertEqual(snap['default_language'], 'pt')
        self.assertIn('pt', snap['languages'])
        self.assertIn('en', snap['languages'])
        self.assertEqual(len(snap['pages']), 2)
        self.assertEqual(snap['stats']['total_pages'], 2)
        self.assertEqual(snap['stats']['active_pages'], 1)
        self.assertEqual(len(snap['menu_items']), 1)
        self.assertEqual(snap['menu_items'][0]['children_count'], 1)
        self.assertEqual(snap['stats']['total_menu_items'], 2)

    def test_get_snapshot_empty_site(self):
        result = SettingsService.get_snapshot()
        self.assertTrue(result['success'])
        snap = result['snapshot']
        self.assertEqual(snap['stats']['total_pages'], 0)
        self.assertEqual(snap['stats']['total_menu_items'], 0)
