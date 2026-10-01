"""Sliders and galleries from the chat: the assistant's tools run the editor's
component operations (every language, one checkpoint per page per turn)."""
from unittest import mock

from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from django.test import TestCase

from djangopress.core.models import Page, PageVersion, SiteImage, SiteSettings
from djangopress.editor_v2 import components
from djangopress.editor_v2.tests.test_component_api import EN, GALLERY, PT, SLIDER
from djangopress.site_assistant import changes
from djangopress.site_assistant.tools import ToolRegistry

TRANSLATE = 'djangopress.editor_v2.component_ops.translate_texts'


class ComponentToolsTest(TestCase):
    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        self.page = Page.objects.create(title_i18n={'pt': 'Início', 'en': 'Home'},
                                        slug_i18n={'pt': 'inicio', 'en': 'home'}, is_active=True,
                                        html_content_i18n={'pt': PT, 'en': EN})
        PageVersion.objects.filter(page=self.page).delete()
        user = get_user_model().objects.create_superuser('a', 'a@x.com', 'pw')
        self.context = {'session': mock.Mock(active_page_id=self.page.id), 'user': user, 'active_page': self.page,
                        'changes': changes.TurnChanges('Muda a galeria', user)}
        self.photo = SiteImage.objects.create(title_i18n={'pt': 'Sala'},
                                              alt_text_i18n={'pt': 'Sala cheia', 'en': 'Full room'})
        self.photo.image.name = 'site_images/sala.jpg'
        self.photo.save()

    def run_tool(self, name, **params):
        with mock.patch(TRANSLATE, return_value=None):
            return ToolRegistry.execute(name, params, self.context)

    def items(self, lang, root, kind):
        self.page.refresh_from_db()
        soup = BeautifulSoup(self.page.html_content_i18n[lang], 'html.parser')
        return components.items(soup.select_one(root), kind)

    def srcs(self, lang):
        return [components.image_of(i)['src'] for i in self.items(lang, GALLERY, 'gallery')]

    def test_list_components(self):
        out = self.run_tool('list_components')
        self.assertTrue(out['success'], out)
        found = {(c['section'], c['kind']): c for c in out['components']}
        self.assertEqual(found[('g', 'gallery')]['items'], ['a', 'b', 'c'])
        self.assertTrue(found[('t', 'text-slider')]['items'][0].startswith('“Uma refeição'))

    def test_reorder_items_in_every_language(self):
        out = self.run_tool('reorder_items', section='g', order=[3, 1, 2])
        self.assertTrue(out['success'], out)
        for lang in ('pt', 'en'):
            self.assertEqual(self.srcs(lang), ['/media/c.jpg', '/media/a.jpg', '/media/b.jpg'])
        self.assertEqual(PageVersion.objects.filter(page=self.page, kind='checkpoint').count(), 1)

    def test_replace_item_image_from_the_library_with_alt_per_language(self):
        out = self.run_tool('replace_item_image', section='g', index=2, image=f'lib:{self.photo.id}')
        self.assertTrue(out['success'], out)
        for lang, alt in (('pt', 'Sala cheia'), ('en', 'Full room')):
            img = components.image_of(self.items(lang, GALLERY, 'gallery')[1])
            self.assertEqual(img['src'], self.photo.image.url)
            self.assertEqual(img['alt'], alt)

    def test_add_item_images_after_an_item(self):
        out = self.run_tool('add_item_images', section='g', after=3, images=[str(self.photo.id)])
        self.assertTrue(out['success'], out)
        self.assertEqual(self.srcs('en')[-1], self.photo.image.url)
        self.assertEqual(len(self.srcs('pt')), 4)

    def test_remove_item_from_the_text_slider(self):
        out = self.run_tool('remove_item', section='t', index=1)
        self.assertTrue(out['success'], out)
        for lang in ('pt', 'en'):
            self.assertEqual(len(self.items(lang, SLIDER, 'text-slider')), 1)

    def test_bad_index_changes_nothing(self):
        out = self.run_tool('remove_item', section='g', index=9)
        self.assertFalse(out['success'])
        self.assertEqual(len(self.srcs('pt')), 3)

    def test_section_without_a_component_lists_the_ones_that_have(self):
        Page.objects.filter(pk=self.page.pk).update(html_content_i18n={'pt': PT + '<section data-section="x"><p>x</p></section>',
                                                                       'en': EN})
        out = self.run_tool('reorder_items', section='x', order=[1])
        self.assertFalse(out['success'])
        self.assertIn('"g"', out['message'])

    def test_unknown_image_ref(self):
        out = self.run_tool('replace_item_image', section='g', index=1, image='lib:99999')
        self.assertFalse(out['success'])
        self.assertEqual(self.srcs('pt')[0], '/media/a.jpg')
