"""Tests for core.services.media — MediaService."""

from django.test import TestCase
from core.models import SiteImage
from core.services.media import MediaService


class MediaServiceListTest(TestCase):

    def setUp(self):
        SiteImage.objects.all().delete()

    def test_list_empty(self):
        result = MediaService.list()
        self.assertTrue(result['success'])
        self.assertEqual(result['images'], [])

    def test_list_with_images(self):
        SiteImage.objects.create(
            title_i18n={'pt': 'Logo', 'en': 'Logo'},
            key='logo',
            tags='branding',
            is_active=True,
        )
        SiteImage.objects.create(
            title_i18n={'pt': 'Banner', 'en': 'Banner'},
            key='banner',
            tags='hero',
            is_active=True,
        )
        result = MediaService.list()
        self.assertTrue(result['success'])
        self.assertEqual(len(result['images']), 2)

    def test_list_excludes_inactive(self):
        SiteImage.objects.create(
            title_i18n={'pt': 'Active'},
            key='active',
            is_active=True,
        )
        SiteImage.objects.create(
            title_i18n={'pt': 'Inactive'},
            key='inactive',
            is_active=False,
        )
        result = MediaService.list()
        self.assertEqual(len(result['images']), 1)

    def test_list_search_by_tag(self):
        SiteImage.objects.create(
            title_i18n={'pt': 'Pool'},
            key='pool',
            tags='villa, pool, luxury',
            is_active=True,
        )
        SiteImage.objects.create(
            title_i18n={'pt': 'Beach'},
            key='beach',
            tags='sea, sand',
            is_active=True,
        )
        result = MediaService.list(search='pool')
        self.assertEqual(len(result['images']), 1)
        self.assertEqual(result['images'][0]['title'], {'pt': 'Pool'})

    def test_list_search_by_title(self):
        SiteImage.objects.create(
            title_i18n={'pt': 'Piscina', 'en': 'Pool'},
            key='pool-img',
            is_active=True,
        )
        result = MediaService.list(search='Piscina')
        self.assertEqual(len(result['images']), 1)

    def test_list_limit(self):
        for i in range(5):
            SiteImage.objects.create(
                title_i18n={'pt': f'Img {i}'},
                key=f'img-{i}',
                is_active=True,
            )
        result = MediaService.list(limit=3)
        self.assertEqual(len(result['images']), 3)


class MediaServiceGetTest(TestCase):

    def setUp(self):
        SiteImage.objects.all().delete()
        self.img = SiteImage.objects.create(
            title_i18n={'pt': 'Test Image', 'en': 'Test Image'},
            alt_text_i18n={'pt': 'Alt PT', 'en': 'Alt EN'},
            key='test-img',
            tags='test, sample',
            description='A test image',
            is_active=True,
        )

    def test_get_existing(self):
        result = MediaService.get(self.img.id)
        self.assertTrue(result['success'])
        image = result['image']
        self.assertEqual(image['id'], self.img.id)
        self.assertEqual(image['title'], {'pt': 'Test Image', 'en': 'Test Image'})
        self.assertEqual(image['alt_text'], {'pt': 'Alt PT', 'en': 'Alt EN'})
        self.assertEqual(image['tags'], 'test, sample')
        self.assertEqual(image['description'], 'A test image')

    def test_get_not_found(self):
        result = MediaService.get(99999)
        self.assertFalse(result['success'])
        self.assertIn('not found', result['error'])
