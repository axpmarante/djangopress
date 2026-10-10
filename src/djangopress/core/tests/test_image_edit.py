"""Tests for core.services.image_edit — the backoffice image editor."""

import io

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from PIL import Image

from djangopress.core.models import GlobalSection, Page, PageVersion, SiteImage, SiteSettings
from djangopress.core.services.image_edit import (
    ImageEditError, apply_operations, restore_original, save_edited,
)
from djangopress.news.models import NewsPost


def _png(size=(40, 20), color=(255, 0, 0, 255), mode='RGBA'):
    buf = io.BytesIO()
    Image.new(mode, size, color).save(buf, 'PNG')
    return buf.getvalue()


def _jpeg(size=(40, 20)):
    buf = io.BytesIO()
    Image.new('RGB', size, (0, 128, 255)).save(buf, 'JPEG')
    return buf.getvalue()


class ApplyOperationsTest(TestCase):

    def setUp(self):
        # 4x2 image: left half red, right half blue, so orientation is observable
        self.img = Image.new('RGB', (4, 2), (255, 0, 0))
        for x in (2, 3):
            for y in (0, 1):
                self.img.putpixel((x, y), (0, 0, 255))

    def test_rotate_clockwise(self):
        out = apply_operations(self.img, [{'op': 'rotate', 'deg': 90}])
        self.assertEqual(out.size, (2, 4))
        # clockwise: the left (red) half ends up on top
        self.assertEqual(out.getpixel((0, 0)), (255, 0, 0))
        self.assertEqual(out.getpixel((0, 3)), (0, 0, 255))

    def test_rotate_counterclockwise(self):
        out = apply_operations(self.img, [{'op': 'rotate', 'deg': -90}])
        self.assertEqual(out.size, (2, 4))
        self.assertEqual(out.getpixel((0, 0)), (0, 0, 255))

    def test_rotate_180(self):
        out = apply_operations(self.img, [{'op': 'rotate', 'deg': 180}])
        self.assertEqual(out.size, (4, 2))
        self.assertEqual(out.getpixel((0, 0)), (0, 0, 255))

    def test_flip_horizontal_and_vertical(self):
        out = apply_operations(self.img, [{'op': 'flip', 'axis': 'h'}])
        self.assertEqual(out.getpixel((0, 0)), (0, 0, 255))
        out = apply_operations(self.img, [{'op': 'flip', 'axis': 'v'}])
        self.assertEqual(out.getpixel((0, 0)), (255, 0, 0))

    def test_crop(self):
        out = apply_operations(self.img, [{'op': 'crop', 'x': 2, 'y': 0, 'width': 2, 'height': 2}])
        self.assertEqual(out.size, (2, 2))
        self.assertEqual(out.getpixel((0, 0)), (0, 0, 255))

    def test_crop_is_clamped_to_the_image(self):
        out = apply_operations(self.img, [{'op': 'crop', 'x': -5, 'y': 1, 'width': 100, 'height': 100}])
        self.assertEqual(out.size, (4, 1))

    def test_resize(self):
        out = apply_operations(self.img, [{'op': 'resize', 'width': 8, 'height': 4}])
        self.assertEqual(out.size, (8, 4))

    def test_operations_apply_in_order(self):
        # rotate first, then crop in the rotated image's coordinates
        out = apply_operations(self.img, [
            {'op': 'rotate', 'deg': 90},
            {'op': 'crop', 'x': 0, 'y': 2, 'width': 2, 'height': 2},
        ])
        self.assertEqual(out.size, (2, 2))
        self.assertEqual(out.getpixel((0, 0)), (0, 0, 255))

    def test_unknown_or_bad_operations_are_refused(self):
        for ops in (
            [{'op': 'blur'}],
            [{'op': 'rotate', 'deg': 45}],
            [{'op': 'flip', 'axis': 'z'}],
            [{'op': 'crop', 'x': 10, 'y': 10, 'width': 1, 'height': 1}],  # entirely outside
            [{'op': 'resize', 'width': 0, 'height': 10}],
            [{'op': 'resize', 'width': 99999, 'height': 10}],
            'rotate',
        ):
            with self.assertRaises(ImageEditError, msg=ops):
                apply_operations(self.img, ops)

    def test_too_many_operations_are_refused(self):
        with self.assertRaises(ImageEditError):
            apply_operations(self.img, [{'op': 'flip', 'axis': 'h'}] * 201)


# Never write test images to the site's real storage (a bucket in development).
@override_settings(STORAGES={**settings.STORAGES, 'default': {'BACKEND': 'django.core.files.storage.InMemoryStorage'}})
class SaveEditedTest(TestCase):

    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        self.user = get_user_model().objects.create_superuser('admin', 'a@example.com', 'x')
        self.image = SiteImage(title_i18n={'pt': 'Foto'}, key='foto')
        self.image.image.save('photo.png', ContentFile(_png()), save=True)
        self.old_url = self.image.image.url
        self.page = Page.objects.create(
            title_i18n={'pt': 'Início'}, slug_i18n={'pt': 'inicio'}, is_active=True,
            html_content_i18n={
                'pt': f'<img src="{self.old_url}"><img src="{self.old_url}">',
                'en': f'<div style="background-image:url({self.old_url})"></div>',
            })
        self.other_page = Page.objects.create(
            title_i18n={'pt': 'Outra'}, slug_i18n={'pt': 'outra'}, is_active=True,
            html_content_i18n={'pt': '<p>no images</p>'})
        self.header = GlobalSection.objects.create(
            key='main-header', section_type='header',
            html_template_i18n={'pt': f'<img src="{self.old_url}">'})
        self.post = NewsPost.objects.create(
            title_i18n={'pt': 'Notícia'}, slug_i18n={'pt': 'noticia'},
            html_content_i18n={'pt': f'<img src="{self.old_url}">'})

    def test_saves_a_new_file_and_keeps_the_original(self):
        original_name = self.image.image.name
        result = save_edited(self.image, [{'op': 'rotate', 'deg': 90}], user=self.user)

        self.image.refresh_from_db()
        self.assertNotEqual(self.image.image.name, original_name)
        self.assertIn('-edited-', self.image.image.name)
        self.assertTrue(self.image.image.name.endswith('.png'))
        self.assertEqual(self.image.original_image, original_name)
        self.assertTrue(self.image.image.storage.exists(original_name))
        with self.image.image.open('rb') as f:
            self.assertEqual(Image.open(f).size, (20, 40))
        self.assertEqual(result['url'], self.image.image.url)

    def test_png_keeps_transparency(self):
        self.image.image.save('alpha.png', ContentFile(_png(color=(255, 0, 0, 0))), save=True)
        save_edited(self.image, [{'op': 'flip', 'axis': 'h'}], user=self.user)
        self.image.refresh_from_db()
        with self.image.image.open('rb') as f:
            out = Image.open(f)
            self.assertEqual(out.mode, 'RGBA')
            self.assertEqual(out.getpixel((0, 0))[3], 0)

    def test_jpeg_stays_jpeg(self):
        self.image.image.save('photo.jpg', ContentFile(_jpeg()), save=True)
        save_edited(self.image, [{'op': 'crop', 'x': 0, 'y': 0, 'width': 10, 'height': 10}], user=self.user)
        self.image.refresh_from_db()
        self.assertTrue(self.image.image.name.endswith('.jpg'))
        with self.image.image.open('rb') as f:
            out = Image.open(f)
            self.assertEqual(out.format, 'JPEG')
            self.assertEqual(out.size, (10, 10))

    def test_rewrites_every_reference(self):
        result = save_edited(self.image, [{'op': 'rotate', 'deg': 90}], user=self.user)
        new_url = self.image.image.url

        self.page.refresh_from_db()
        self.header.refresh_from_db()
        self.post.refresh_from_db()
        for html in (*self.page.html_content_i18n.values(),
                     self.header.html_template_i18n['pt'], self.post.html_content_i18n['pt']):
            self.assertNotIn(self.old_url, html)
            self.assertIn(new_url, html)
        self.assertEqual(self.page.html_content_i18n['pt'].count(new_url), 2)
        self.assertEqual(result['pages'], ['Início'])
        self.assertEqual(result['sections'], ['main-header'])
        self.assertEqual(result['news'], ['Notícia'])

    def test_rewritten_pages_get_a_checkpoint(self):
        save_edited(self.image, [{'op': 'rotate', 'deg': 90}], user=self.user)
        version = PageVersion.objects.filter(page=self.page, kind='checkpoint').first()
        self.assertIsNotNone(version)
        self.assertIn(self.old_url, version.html_content_i18n['pt'])
        self.assertFalse(PageVersion.objects.filter(page=self.other_page, kind='checkpoint').exists())

    def test_a_longer_name_that_starts_with_the_same_name_is_left_alone(self):
        similar = self.old_url.replace('.png', '.png.webp')
        self.page.html_content_i18n = {'pt': f'<img src="{similar}">'}
        self.page.save()
        save_edited(self.image, [{'op': 'rotate', 'deg': 90}], user=self.user)
        self.page.refresh_from_db()
        self.assertEqual(self.page.html_content_i18n['pt'], f'<img src="{similar}">')

    def test_editing_twice_keeps_the_first_original(self):
        original_name = self.image.image.name
        save_edited(self.image, [{'op': 'rotate', 'deg': 90}], user=self.user)
        save_edited(self.image, [{'op': 'flip', 'axis': 'h'}], user=self.user)
        self.image.refresh_from_db()
        self.assertEqual(self.image.original_image, original_name)
        self.assertEqual(self.image.image.name.count('-edited-'), 1)

    def test_restore_original_puts_it_back_everywhere(self):
        original_name = self.image.image.name
        save_edited(self.image, [{'op': 'rotate', 'deg': 90}], user=self.user)
        result = restore_original(self.image, user=self.user)

        self.image.refresh_from_db()
        self.assertEqual(self.image.image.name, original_name)
        self.assertEqual(self.image.original_image, '')
        self.page.refresh_from_db()
        self.assertEqual(self.page.html_content_i18n['pt'].count(self.old_url), 2)
        self.assertEqual(result['pages'], ['Início'])

    def test_restore_without_an_original_is_refused(self):
        with self.assertRaises(ImageEditError):
            restore_original(self.image, user=self.user)

    def test_documents_and_unsupported_formats_are_refused(self):
        gif = io.BytesIO()
        Image.new('RGB', (4, 4)).save(gif, 'GIF')
        self.image.image.save('anim.gif', ContentFile(gif.getvalue()), save=True)
        with self.assertRaises(ImageEditError):
            save_edited(self.image, [{'op': 'rotate', 'deg': 90}], user=self.user)

        doc = SiteImage.objects.create(file_type='document', key='doc')
        with self.assertRaises(ImageEditError):
            save_edited(doc, [{'op': 'rotate', 'deg': 90}], user=self.user)

    def test_no_operations_is_refused(self):
        with self.assertRaises(ImageEditError):
            save_edited(self.image, [], user=self.user)
