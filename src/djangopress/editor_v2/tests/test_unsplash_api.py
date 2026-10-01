"""The editor image picker's Unsplash tab: search and import into the library."""
import json
import shutil
import tempfile
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from djangopress.core.models import SiteImage

UNSPLASH = 'djangopress.ai.utils.unsplash'
STORAGES = {'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}


class UnsplashApiTest(TestCase):
    def setUp(self):
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, True)
        override = override_settings(MEDIA_ROOT=media, MEDIA_URL='/media/', STORAGES=STORAGES)
        override.enable()
        self.addCleanup(override.disable)
        staff = get_user_model().objects.create_user('ed', 'ed@x.com', 'pw', is_staff=True)
        self.client.force_login(staff)

    def post(self, name, body):
        return self.client.post(reverse(f'editor_v2:{name}'), data=json.dumps(body), content_type='application/json')

    def test_search_for_staff(self):
        hit = {'id': 'abc', 'thumb_url': 't', 'regular_url': 'r', 'alt_description': 'sea', 'photographer': 'Ana',
               'photographer_url': ''}
        with mock.patch(f'{UNSPLASH}.is_configured', return_value=True), \
                mock.patch(f'{UNSPLASH}.search_photos', return_value=[hit]):
            res = self.post('api_unsplash_search', {'query': 'sea'})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()['results'][0]['id'], 'abc')

    def test_search_when_not_configured(self):
        with mock.patch(f'{UNSPLASH}.is_configured', return_value=False):
            res = self.post('api_unsplash_search', {'query': 'sea'})
        self.assertEqual(res.status_code, 400)

    def test_import_returns_a_library_image(self):
        image = SiteImage(key='unsplash-abc', title_i18n={'pt': 'sea'}, alt_text_i18n={'pt': 'sea'})
        image.image.name = 'site_images/unsplash-abc.jpg'
        image.save()
        with mock.patch('djangopress.site_assistant.photos.ensure_library_image', return_value=image) as ensure:
            res = self.post('api_unsplash_import', {'id': 'abc'})
        self.assertEqual(res.status_code, 200, res.content)
        ensure.assert_called_once_with('unsplash:abc')
        self.assertEqual(res.json()['image'], {'id': image.id, 'url': image.image.url, 'title': 'sea', 'alt_text': 'sea'})

    def test_import_error(self):
        with mock.patch('djangopress.site_assistant.photos.ensure_library_image', side_effect=ValueError('nope')):
            res = self.post('api_unsplash_import', {'id': 'abc'})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()['error'], 'nope')
