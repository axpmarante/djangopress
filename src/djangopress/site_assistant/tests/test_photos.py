"""find_photos (library + Unsplash), Unsplash import into the library, and
set_section_background in every language."""
import io
import shutil
import tempfile
from unittest import mock

from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from djangopress.core.models import Page, PageVersion, SiteImage, SiteSettings
from djangopress.site_assistant import changes, photos
from djangopress.site_assistant.tools import ToolRegistry

UNSPLASH = 'djangopress.ai.utils.unsplash'
GRADIENT = 'linear-gradient(rgba(0, 0, 0, 0.5), rgba(0, 0, 0, 0.5))'


def jpeg_bytes():
    from PIL import Image
    out = io.BytesIO()
    Image.new('RGB', (40, 30), 'navy').save(out, 'JPEG')
    return out.getvalue()


def library(title, tags='', description='', alt=None):
    slug = title.lower().replace(' ', '-')
    image = SiteImage.objects.create(key=slug, title_i18n={'pt': title}, alt_text_i18n=alt or {'pt': title},
                                     tags=tags, description=description)
    image.image.name = f'site_images/{slug}.jpg'
    image.save()
    return image


class PhotosTestCase(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, True)
        # Local files only: the demo's default storage is the real GCS bucket.
        override = override_settings(MEDIA_ROOT=self.media, MEDIA_URL='/media/', STORAGES={
            'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
        })
        override.enable()
        self.addCleanup(override.disable)
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()


class FindPhotosTest(PhotosTestCase):
    def setUp(self):
        super().setUp()
        self.terrace = library('Terraço', tags='terraço, mar, pôr do sol', description='Terraço com vista mar')
        self.room = library('Sala', tags='interior, mesas')
        self.dish = library('Prato de peixe', description='peixe grelhado junto ao mar')

    def test_library_is_ranked_by_overlap_and_unrelated_left_out(self):
        with mock.patch(f'{UNSPLASH}.is_configured', return_value=False):
            found, note = photos.find_photos('terraço mar', source='library')
        refs = [p['ref'] for p in found]
        self.assertEqual(refs[0], f'lib:{self.terrace.id}')
        self.assertIn(f'lib:{self.dish.id}', refs)
        self.assertNotIn(f'lib:{self.room.id}', refs)
        self.assertEqual(found[0]['thumb_url'], self.terrace.image.url)

    def test_unsplash_off_still_returns_the_library_and_says_so(self):
        with mock.patch(f'{UNSPLASH}.is_configured', return_value=False):
            out = ToolRegistry.execute('find_photos', {'query': 'terraço'}, {})
        self.assertTrue(out['success'], out)
        self.assertEqual(out['photos'][0]['source'], 'library')
        self.assertIn('Unsplash', out['message'])

    def test_unsplash_results_carry_ref_and_credit(self):
        hit = {'id': 'abc123', 'thumb_url': 'https://images.unsplash.com/t', 'regular_url': 'https://images.unsplash.com/r',
               'alt_description': 'sunset terrace', 'photographer': 'Ana Lima', 'photographer_url': 'https://unsplash.com/@ana'}
        with mock.patch(f'{UNSPLASH}.is_configured', return_value=True), \
                mock.patch(f'{UNSPLASH}.search_photos', return_value=[hit]) as search:
            found, note = photos.find_photos('terrace sunset', source='unsplash', orientation='landscape')
        self.assertEqual(search.call_args.kwargs.get('orientation'), 'landscape')
        self.assertEqual(found, [{'ref': 'unsplash:abc123', 'source': 'unsplash', 'title': 'sunset terrace',
                                  'thumb_url': 'https://images.unsplash.com/t', 'credit': 'Photo by Ana Lima on Unsplash'}])


class EnsureLibraryImageTest(PhotosTestCase):
    def test_unsplash_photo_is_downloaded_once_with_its_credit(self):
        info = {'id': 'abc123', 'regular_url': 'https://images.unsplash.com/r', 'alt_description': 'sunset terrace',
                'photographer': 'Ana Lima', 'thumb_url': '', 'photographer_url': ''}
        with mock.patch(f'{UNSPLASH}.is_configured', return_value=True), \
                mock.patch(f'{UNSPLASH}.get_photo', return_value=info), \
                mock.patch(f'{UNSPLASH}.download_photo', return_value=jpeg_bytes()) as download:
            first = photos.ensure_library_image('unsplash:abc123')
            again = photos.ensure_library_image('unsplash:abc123')
        self.assertEqual(first.pk, again.pk)
        self.assertEqual(download.call_count, 1)
        self.assertIn('Ana Lima', first.description)
        self.assertTrue(first.image.name)

    def test_unsplash_failure_is_a_clear_error(self):
        with mock.patch(f'{UNSPLASH}.is_configured', return_value=True), \
                mock.patch(f'{UNSPLASH}.get_photo', return_value=None):
            with self.assertRaises(ValueError):
                photos.ensure_library_image('unsplash:nope')


class SectionBackgroundTest(PhotosTestCase):
    def setUp(self):
        super().setUp()
        self.photo = library('Terraço', alt={'pt': 'Terraço ao pôr do sol', 'en': 'Terrace at sunset'})
        self.user = get_user_model().objects.create_superuser('a', 'a@x.com', 'pw')

    def make_page(self, pt, en):
        self.page = Page.objects.create(title_i18n={'pt': 'Início', 'en': 'Home'},
                                        slug_i18n={'pt': 'inicio', 'en': 'home'}, is_active=True,
                                        html_content_i18n={'pt': pt, 'en': en})
        PageVersion.objects.filter(page=self.page).delete()
        self.context = {'session': mock.Mock(active_page_id=self.page.id), 'user': self.user,
                        'active_page': self.page, 'changes': changes.TurnChanges('Fundo novo', self.user)}

    def section(self, lang):
        self.page.refresh_from_db()
        return BeautifulSoup(self.page.html_content_i18n[lang], 'html.parser').find('section')

    def set_bg(self):
        return ToolRegistry.execute('set_section_background',
                                    {'section_name': 'hero', 'image': f'lib:{self.photo.id}'}, self.context)

    def test_inline_background_keeps_the_overlay(self):
        html = (f'<section data-section="hero" style="background-image: {GRADIENT}, url(\'/media/old.jpg\'); '
                f'background-size: cover"><h1>{{}}</h1></section>')
        self.make_page(html.format('Olá'), html.format('Hello'))
        out = self.set_bg()
        self.assertTrue(out['success'], out)
        for lang in ('pt', 'en'):
            style = self.section(lang)['style']
            self.assertIn(GRADIENT, style)
            self.assertIn(self.photo.image.url, style)
            self.assertNotIn('old.jpg', style)
        self.assertEqual(PageVersion.objects.filter(page=self.page, kind='checkpoint').count(), 1)

    def test_inline_background_without_overlay(self):
        html = '<section data-section="hero" style="background-image: url(/media/old.jpg)"><h1>x</h1></section>'
        self.make_page(html, html)
        self.set_bg()
        self.assertIn(self.photo.image.url, self.section('en')['style'])
        self.assertNotIn('gradient', self.section('en')['style'])

    def test_img_layer_gets_new_src_and_alt_per_language(self):
        html = ('<section data-section="hero" class="relative"><a href="/media/old.jpg" data-lightbox="h">'
                '<img class="absolute inset-0 w-full h-full object-cover" src="/media/old.jpg" srcset="x 2x" alt="old"/></a>'
                '<div class="relative"><h1>x</h1></div></section>')
        self.make_page(html, html)
        self.set_bg()
        for lang, alt in (('pt', 'Terraço ao pôr do sol'), ('en', 'Terrace at sunset')):
            img = self.section(lang).find('img')
            self.assertEqual(img['src'], self.photo.image.url)
            self.assertEqual(img['alt'], alt)
            self.assertNotIn('srcset', img.attrs)
            self.assertEqual(img.parent['href'], self.photo.image.url)

    def test_section_without_a_background_gets_one(self):
        html = '<section data-section="hero" class="py-20"><h1>x</h1></section>'
        self.make_page(html, html)
        out = self.set_bg()
        self.assertTrue(out['success'], out)
        style = self.section('pt')['style']
        self.assertIn(self.photo.image.url, style)
        self.assertIn('cover', style)

    def test_unknown_section(self):
        html = '<section data-section="hero"><h1>x</h1></section>'
        self.make_page(html, html)
        out = ToolRegistry.execute('set_section_background', {'section_name': 'nope', 'image': f'lib:{self.photo.id}'},
                                   self.context)
        self.assertFalse(out['success'])
