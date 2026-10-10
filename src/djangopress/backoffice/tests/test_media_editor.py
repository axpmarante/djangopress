"""Backoffice endpoints of the media image editor (source, save, restore)."""

import io
import json

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from djangopress.core.models import Page, SiteImage, SiteSettings


def _png(size=(40, 20)):
    buf = io.BytesIO()
    Image.new('RGB', size, (255, 0, 0)).save(buf, 'PNG')
    return buf.getvalue()


# Never write test images to the site's real storage (a bucket in development).
@override_settings(STORAGES={**settings.STORAGES, 'default': {'BACKEND': 'django.core.files.storage.InMemoryStorage'}})
class MediaEditorViewsTest(TestCase):

    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}]
        s.default_language = 'pt'
        s.save()
        self.user = get_user_model().objects.create_superuser('admin', 'a@example.com', 'x')
        self.client.force_login(self.user)
        self.image = SiteImage(title_i18n={'pt': 'Foto'}, key='foto')
        self.image.image.save('photo.png', ContentFile(_png()), save=True)
        self.page = Page.objects.create(
            title_i18n={'pt': 'Início'}, slug_i18n={'pt': 'inicio'}, is_active=True,
            html_content_i18n={'pt': f'<img src="{self.image.image.url}">'})

    def _edit(self, operations):
        return self.client.post(reverse('backoffice:media_edit', args=[self.image.pk]),
                                data=json.dumps({'operations': operations}),
                                content_type='application/json')

    def test_detail_page_offers_the_editor_for_images(self):
        response = self.client.get(reverse('backoffice:media_detail', args=[self.image.pk]))
        self.assertTrue(response.context['editable'])
        self.assertContains(response, 'Edit image')

    def test_detail_page_hides_the_editor_for_documents(self):
        doc = SiteImage(file_type='document', key='doc')
        doc.file.save('doc.pdf', ContentFile(b'%PDF-1.4'), save=True)
        response = self.client.get(reverse('backoffice:media_detail', args=[doc.pk]))
        self.assertFalse(response.context['editable'])
        self.assertNotContains(response, 'Edit image')

    def test_source_streams_the_file_from_this_origin(self):
        response = self.client.get(reverse('backoffice:media_source', args=[self.image.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
        self.assertEqual(b''.join(response.streaming_content), _png())

    def test_source_needs_a_login(self):
        self.client.logout()
        response = self.client.get(reverse('backoffice:media_source', args=[self.image.pk]))
        self.assertEqual(response.status_code, 302)

    def test_edit_saves_and_updates_pages(self):
        response = self._edit([{'op': 'rotate', 'deg': 90}])
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual((data['width'], data['height']), (20, 40))
        self.assertEqual(data['pages'], ['Início'])
        self.page.refresh_from_db()
        self.assertIn(data['url'], self.page.html_content_i18n['pt'])

    def test_edit_reports_bad_steps(self):
        response = self._edit([{'op': 'rotate', 'deg': 45}])
        self.assertEqual(response.status_code, 400)
        self.assertIn('90', response.json()['error'])

    def test_edit_rejects_get_and_bad_json(self):
        url = reverse('backoffice:media_edit', args=[self.image.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        response = self.client.post(url, data='not json', content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_restore_original(self):
        original = self.image.image.name
        self._edit([{'op': 'rotate', 'deg': 90}])
        response = self.client.post(reverse('backoffice:media_restore_original', args=[self.image.pk]))
        self.assertRedirects(response, reverse('backoffice:media_detail', args=[self.image.pk]),
                             fetch_redirect_response=False)
        self.image.refresh_from_db()
        self.assertEqual(self.image.image.name, original)
