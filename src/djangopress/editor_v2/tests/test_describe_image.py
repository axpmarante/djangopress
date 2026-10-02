"""Describe the photo: alt text in every language from the image itself."""
import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from django.test import TestCase, override_settings

from djangopress.core.models import Page, SiteImage, SiteSettings

DESCRIBE = 'djangopress.ai.services.ContentGenerationService.describe_image_alt'
FETCH = 'djangopress.editor_v2.api_views._fetch_image_bytes'
IMG = 'section[data-section="sala"] > img:nth-child(1)'


def html(src, alt):
    return f'<section data-section="sala" id="sala"><img src="{src}" alt="{alt}"></section>'


@override_settings(STORAGES={**settings.STORAGES, 'default': {'BACKEND': 'django.core.files.storage.InMemoryStorage'}})
class DescribeImageTest(TestCase):
    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        self.lib = SiteImage.objects.create(title_i18n={'pt': 'Sala'}, key='sala',
                                            image=SimpleUploadedFile('sala.jpg', b'\xff\xd8JPEGDATA', content_type='image/jpeg'))
        src = self.lib.image.url
        self.page = Page.objects.create(title_i18n={'pt': 'Início'}, slug_i18n={'pt': 'inicio'}, is_active=True,
                                        html_content_i18n={'pt': html(src, ''), 'en': html(src, '')})
        self.user = get_user_model().objects.create_superuser('a', 'a@x.com', 'pw')
        self.client.force_login(self.user)

    def post(self, body=None):
        return self.client.post('/editor-v2/api/describe-image/', data=json.dumps({'page_id': self.page.id, 'selector': IMG, **(body or {})}),
                                content_type='application/json', HTTP_REFERER='http://testserver/pt/?edit=v2')

    def test_library_image_bytes_and_other_languages_written(self):
        with mock.patch(DESCRIBE, return_value={'pt': 'Mesas postas na sala', 'en': 'Set tables in the room'}) as d:
            res = self.post()
        self.assertTrue(res.json()['success'], res.content)
        self.assertEqual(d.call_args.args[0], b'\xff\xd8JPEGDATA')
        self.assertEqual(res.json()['current'], 'Mesas postas na sala')
        self.page.refresh_from_db()
        self.assertIn('alt="Set tables in the room"', self.page.html_content_i18n['en'])
        self.assertIn('alt=""', self.page.html_content_i18n['pt'])        # the field holds it as an unsaved change

    def test_an_image_outside_the_library_is_fetched_when_it_is_on_the_page(self):
        src = 'https://storage.googleapis.com/bucket/x.jpg'
        self.page.html_content_i18n = {'pt': html(src, ''), 'en': html(src, '')}
        self.page.save()
        with mock.patch(FETCH, return_value=(b'IMG', 'image/jpeg')) as f, \
                mock.patch(DESCRIBE, return_value={'pt': 'a', 'en': 'b'}):
            res = self.post()
        self.assertTrue(res.json()['success'], res.content)
        self.assertEqual(f.call_args.args[0], src)

    def test_a_library_row_whose_file_is_missing_falls_back_to_the_url(self):
        SiteImage.objects.create(title_i18n={'pt': 'x'}, key='gone', image='site_images/gone.jpg')
        src = 'https://storage.googleapis.com/bucket/site/site_images/gone.jpg'
        self.page.html_content_i18n = {'pt': html(src, ''), 'en': html(src, '')}
        self.page.save()
        with mock.patch(FETCH, return_value=(b'IMG', 'image/jpeg')) as f, \
                mock.patch(DESCRIBE, return_value={'pt': 'a', 'en': 'b'}):
            res = self.post()
        self.assertTrue(res.json()['success'], res.content)
        f.assert_called_once()

    def test_a_replaced_photo_not_saved_yet_is_refused(self):
        with mock.patch(DESCRIBE) as d:
            res = self.post({'src': 'https://example.com/new-photo.jpg'})
        self.assertEqual(res.status_code, 409)
        self.assertIn('Save', res.json()['error'])
        d.assert_not_called()

    def test_a_save_made_during_the_ai_call_is_kept(self):
        def concurrent_save(*args, **kwargs):
            page = Page.objects.get(pk=self.page.pk)
            copies = dict(page.html_content_i18n)
            copies['pt'] = copies['pt'].replace('</section>', '<p>Novo texto</p></section>')
            page.html_content_i18n = copies
            page.save()
            return {'pt': 'a', 'en': 'Room'}
        with mock.patch(DESCRIBE, side_effect=concurrent_save):
            self.post()
        self.page.refresh_from_db()
        self.assertIn('Novo texto', self.page.html_content_i18n['pt'])
        self.assertIn('alt="Room"', self.page.html_content_i18n['en'])

    def test_missing_element_is_refused_without_a_fetch(self):
        with mock.patch(FETCH) as f, mock.patch(DESCRIBE) as d:
            res = self.post({'selector': 'section[data-section="sala"] > img:nth-child(5)'})
        self.assertEqual(res.status_code, 400)
        f.assert_not_called()
        d.assert_not_called()

    def test_editors_without_ai_access_are_refused(self):
        editor = get_user_model().objects.create_user('e', 'e@x.com', 'pw', is_staff=True)
        self.client.force_login(editor)
        res = self.post()
        self.assertIn(res.status_code, (302, 403))


class DescribeServiceTest(TestCase):
    def test_parses_one_alt_per_language(self):
        from djangopress.ai.services import ContentGenerationService
        from djangopress.ai.utils.llm_config import StandardizedLLMResponse
        service = ContentGenerationService(model_name='gemini-flash')
        reply = StandardizedLLMResponse(content='```json\n{"pt": "Mesas", "en": "Tables", "fr": "x"}\n```',
                                        usage={'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}, finish_reason='STOP')
        with mock.patch.object(service.llm, 'get_vision_completion', return_value=reply) as v:
            out = service.describe_image_alt(b'IMG', 'image/jpeg', ['pt', 'en'])
        self.assertEqual(out, {'pt': 'Mesas', 'en': 'Tables'})
        self.assertEqual(v.call_args.kwargs['file_bytes'], b'IMG')


class FetchGuardTest(TestCase):
    def test_internal_addresses_are_refused(self):
        from djangopress.editor_v2.api_views import _fetch_image_bytes
        for url in ('http://127.0.0.1/admin/', 'http://localhost:8000/x.jpg', 'http://169.254.169.254/latest/',
                    'http://10.0.0.5/a.jpg', 'ftp://example.com/a.jpg'):
            with self.assertRaises(ValueError, msg=url):
                _fetch_image_bytes(url)

    def test_only_images_are_read(self):
        from djangopress.editor_v2 import api_views
        response = mock.MagicMock()
        response.headers.get_content_type.return_value = 'text/html'
        response.read.return_value = b'<html>secret</html>'
        opener = mock.MagicMock()
        opener.open.return_value.__enter__.return_value = response
        with mock.patch.object(api_views, '_public_host', return_value=True), \
                mock.patch('urllib.request.build_opener', return_value=opener):
            with self.assertRaises(ValueError):
                api_views._fetch_image_bytes('https://example.com/page')
