"""Tests for core.services.menu — MenuService."""

from unittest.mock import patch
from django.test import TestCase
from djangopress.core.models import Page, SiteSettings, MenuItem
from djangopress.core.services.menu import MenuService


class MenuServiceListTest(TestCase):

    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        MenuItem.objects.all().delete()

    def test_list_empty(self):
        result = MenuService.list()
        self.assertTrue(result['success'])
        self.assertEqual(result['menu_items'], [])
        self.assertIn('0', result['message'])

    def test_list_with_hierarchy(self):
        page = Page.objects.create(
            title_i18n={'pt': 'Home', 'en': 'Home'},
            slug_i18n={'pt': 'home', 'en': 'home'},
        )
        parent = MenuItem.objects.create(
            label_i18n={'pt': 'Inicio', 'en': 'Home'},
            page=page,
            sort_order=0,
        )
        MenuItem.objects.create(
            label_i18n={'pt': 'Sub 1', 'en': 'Sub 1'},
            url='/sub1',
            parent=parent,
            sort_order=0,
        )
        MenuItem.objects.create(
            label_i18n={'pt': 'Sub 2', 'en': 'Sub 2'},
            url='/sub2',
            parent=parent,
            sort_order=1,
        )

        result = MenuService.list()
        self.assertTrue(result['success'])
        self.assertEqual(len(result['menu_items']), 1)
        self.assertEqual(len(result['menu_items'][0]['children']), 2)
        self.assertEqual(result['menu_items'][0]['children'][0]['label'], {'pt': 'Sub 1', 'en': 'Sub 1'})


class MenuServiceCreateTest(TestCase):

    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        MenuItem.objects.all().delete()
        self.page = Page.objects.create(
            title_i18n={'pt': 'Sobre', 'en': 'About'},
            slug_i18n={'pt': 'sobre', 'en': 'about'},
        )

    def test_create_with_page(self):
        result = MenuService.create(
            label_i18n={'pt': 'Sobre', 'en': 'About'},
            page_id=self.page.id,
        )
        self.assertTrue(result['success'])
        self.assertIsNotNone(result['menu_item'])
        item = result['menu_item']
        self.assertEqual(item.page_id, self.page.id)
        self.assertEqual(item.label_i18n, {'pt': 'Sobre', 'en': 'About'})

    def test_create_with_url(self):
        result = MenuService.create(
            label_i18n={'pt': 'Externo', 'en': 'External'},
            url='https://example.com',
        )
        self.assertTrue(result['success'])
        self.assertEqual(result['menu_item'].url, 'https://example.com')

    @patch('djangopress.core.services.i18n._translate_text', return_value='About')
    def test_create_with_single_label(self, mock_translate):
        result = MenuService.create(label='Sobre', page_id=self.page.id)
        self.assertTrue(result['success'])
        item = result['menu_item']
        self.assertEqual(item.label_i18n['pt'], 'Sobre')
        self.assertEqual(item.label_i18n['en'], 'About')

    def test_create_no_label_fails(self):
        result = MenuService.create(page_id=self.page.id)
        self.assertFalse(result['success'])
        self.assertIn('label', result['error'].lower())

    def test_create_no_page_or_url_fails(self):
        result = MenuService.create(label_i18n={'pt': 'Test', 'en': 'Test'})
        self.assertFalse(result['success'])
        self.assertIn('page_id or url', result['error'].lower())

    def test_create_invalid_page_fails(self):
        result = MenuService.create(
            label_i18n={'pt': 'X', 'en': 'X'},
            page_id=99999,
        )
        self.assertFalse(result['success'])
        self.assertIn('not found', result['error'])

    def test_create_nesting_depth_limit(self):
        parent = MenuItem.objects.create(
            label_i18n={'pt': 'P', 'en': 'P'},
            url='/p',
            sort_order=0,
        )
        child = MenuItem.objects.create(
            label_i18n={'pt': 'C', 'en': 'C'},
            url='/c',
            parent=parent,
            sort_order=0,
        )
        # Trying to nest under a child (depth 2) should fail
        result = MenuService.create(
            label_i18n={'pt': 'GC', 'en': 'GC'},
            url='/gc',
            parent_id=child.id,
        )
        self.assertFalse(result['success'])
        self.assertIn('nesting', result['error'].lower())


class MenuServiceUpdateTest(TestCase):

    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        MenuItem.objects.all().delete()
        self.item = MenuItem.objects.create(
            label_i18n={'pt': 'Original', 'en': 'Original'},
            url='/original',
            sort_order=0,
        )

    def test_update_label(self):
        result = MenuService.update(
            self.item.id,
            label_i18n={'pt': 'Novo', 'en': 'New'},
        )
        self.assertTrue(result['success'])
        self.item.refresh_from_db()
        self.assertEqual(self.item.label_i18n, {'pt': 'Novo', 'en': 'New'})
        self.assertIn('label', result['message'])

    def test_update_not_found(self):
        result = MenuService.update(99999, label_i18n={'pt': 'X'})
        self.assertFalse(result['success'])
        self.assertIn('not found', result['error'])

    def test_update_sort_order(self):
        result = MenuService.update(self.item.id, sort_order=5)
        self.assertTrue(result['success'])
        self.item.refresh_from_db()
        self.assertEqual(self.item.sort_order, 5)

    def test_update_is_active(self):
        result = MenuService.update(self.item.id, is_active=False)
        self.assertTrue(result['success'])
        self.item.refresh_from_db()
        self.assertFalse(self.item.is_active)


class MenuServiceDeleteTest(TestCase):

    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}]
        s.default_language = 'pt'
        s.save()
        MenuItem.objects.all().delete()

    def test_delete_existing(self):
        item = MenuItem.objects.create(
            label_i18n={'pt': 'Temp'},
            url='/temp',
        )
        result = MenuService.delete(item.id)
        self.assertTrue(result['success'])
        self.assertFalse(MenuItem.objects.filter(pk=item.id).exists())

    def test_delete_not_found(self):
        result = MenuService.delete(99999)
        self.assertFalse(result['success'])
        self.assertIn('not found', result['error'])


class MenuServiceReorderTest(TestCase):

    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}]
        s.default_language = 'pt'
        s.save()
        MenuItem.objects.all().delete()
        self.m1 = MenuItem.objects.create(label_i18n={'pt': 'A'}, url='/a', sort_order=0)
        self.m2 = MenuItem.objects.create(label_i18n={'pt': 'B'}, url='/b', sort_order=1)
        self.m3 = MenuItem.objects.create(label_i18n={'pt': 'C'}, url='/c', sort_order=2)

    def test_reorder(self):
        result = MenuService.reorder([
            {'menu_item_id': self.m3.id, 'sort_order': 0},
            {'menu_item_id': self.m1.id, 'sort_order': 1},
            {'menu_item_id': self.m2.id, 'sort_order': 2},
        ])
        self.assertTrue(result['success'])
        self.m1.refresh_from_db()
        self.m2.refresh_from_db()
        self.m3.refresh_from_db()
        self.assertEqual(self.m3.sort_order, 0)
        self.assertEqual(self.m1.sort_order, 1)
        self.assertEqual(self.m2.sort_order, 2)

    def test_reorder_empty_fails(self):
        result = MenuService.reorder([])
        self.assertFalse(result['success'])
