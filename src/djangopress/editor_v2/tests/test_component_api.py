import json
from unittest import mock

from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from djangopress.core.models import Page, PageVersion, SiteImage, SiteSettings
from djangopress.editor_v2 import components

User = get_user_model()
TRANSLATE = 'djangopress.editor_v2.component_views.translate_texts'


def slider(texts):
    slides = ''.join(
        f'<li class="splide__slide"><blockquote>{q}</blockquote><p>{a}</p></li>' for q, a in texts)
    return (f'<section data-section="t" id="t"><div class="splide" data-splide=\'{{"type":"fade","rewind":true}}\'>'
            f'<div class="splide__track"><ul class="splide__list">{slides}</ul></div></div></section>')


def gallery(names):
    links = ''.join(f'<a href="/media/{n}.jpg" data-lightbox="g" data-alt="{n}"><img src="/media/{n}.jpg" alt="{n}"/></a>'
                    for n in names)
    return f'<section data-section="g" id="g"><div class="grid">{links}</div></section>'


PT = slider([('“Uma refeição inesquecível, cheia de sabor e bom serviço.”', 'Ana'),
             ('“O melhor restaurante de Faro, sem qualquer dúvida possível.”', 'Rui')]) + gallery(['a', 'b', 'c'])
EN = slider([('“An unforgettable meal, full of flavour and good service.”', 'Ana'),
             ('“The best restaurant in Faro, without any possible doubt.”', 'Rui')]) + gallery(['a', 'b', 'c'])
SLIDER = 'section[data-section="t"] > div:nth-child(1)'
GALLERY = 'section[data-section="g"] > div:nth-child(1)'


class ComponentApiTest(TestCase):
    def setUp(self):
        Page.objects.all().delete()
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        self.page = Page.objects.create(
            title_i18n={'pt': 'Home', 'en': 'Home'}, slug_i18n={'pt': 'home', 'en': 'home'},
            is_active=True, html_content_i18n={'pt': PT, 'en': EN},
        )
        PageVersion.objects.filter(page=self.page).delete()
        self.staff = User.objects.create_user('staff', 'staff@example.com', 'pw', is_staff=True)
        self.client.force_login(self.staff)

    def post(self, root, kind, count, op, args, language='pt'):
        body = {'page_id': self.page.id, 'language': language, 'root': root, 'kind': kind,
                'count': count, 'op': op, 'args': args}
        return self.client.post(reverse('editor_v2:api_component_op'), data=json.dumps(body),
                                content_type='application/json')

    def comp(self, lang, root, kind):
        self.page.refresh_from_db()
        soup = BeautifulSoup(self.page.html_content_i18n[lang], 'html.parser')
        c = components.find_component(soup, root, kind)
        return components.items(c, kind)

    def texts(self, lang, i):
        leaves = components.text_leaves(self.comp(lang, SLIDER, 'text-slider')[i])
        return [components.read_text(l) for l in leaves]

    def test_reorder_applies_to_all_languages_with_checkpoint(self):
        res = self.post(SLIDER, 'text-slider', 2, 'reorder', {'order': [1, 0]})
        self.assertEqual(res.status_code, 200, res.content)
        body = res.json()
        self.assertEqual(body['skipped_languages'], [])
        self.assertEqual(self.texts('pt', 0)[1], 'Rui')
        self.assertEqual(self.texts('en', 0)[1], 'Rui')
        self.assertTrue(PageVersion.objects.filter(page=self.page, kind='checkpoint').exists())
        self.assertIn('splide__slide', body['html'])
        self.assertTrue(body['html'].startswith('<div class="splide"'))

    def test_update_item_touches_current_language_only(self):
        res = self.post(SLIDER, 'text-slider', 2, 'update_item', {'index': 1, 'texts': {'1': 'Rui M.'}})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(self.texts('pt', 1)[1], 'Rui M.')
        self.assertEqual(self.texts('en', 1)[1], 'Rui')

    def test_add_text_item_translates_other_languages(self):
        with mock.patch(TRANSLATE, return_value=['“Great.”', 'Zé']) as tr:
            res = self.post(SLIDER, 'text-slider', 2, 'add_text_item',
                            {'after': 1, 'texts': {'0': '“Ótimo.”', '1': 'Zé'}})
        self.assertEqual(res.status_code, 200, res.content)
        body = res.json()
        tr.assert_called_once_with(['“Ótimo.”', 'Zé'], 'pt', 'en')
        self.assertEqual(body['index'], 2)
        self.assertEqual(body['translated_languages'], ['en'])
        self.assertEqual(self.texts('pt', 2), ['“Ótimo.”', 'Zé'])
        self.assertEqual(self.texts('en', 2), ['“Great.”', 'Zé'])

    def test_add_text_item_translation_failure_keeps_source(self):
        with mock.patch(TRANSLATE, return_value=None):
            res = self.post(SLIDER, 'text-slider', 2, 'add_text_item',
                            {'after': 0, 'texts': {'0': '“Ótimo.”', '1': 'Zé'}})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()['untranslated_languages'], ['en'])
        self.assertEqual(self.texts('en', 1), ['“Ótimo.”', 'Zé'])

    def test_add_images_uses_library_alt_per_language(self):
        img = SiteImage.objects.create(title_i18n={'pt': 'Sala'}, alt_text_i18n={'pt': 'Sala cheia', 'en': 'Full room'})
        with mock.patch(TRANSLATE) as tr:
            res = self.post(GALLERY, 'gallery', 3, 'add_images',
                            {'after': 2, 'images': [{'id': str(img.id), 'url': '/media/new.jpg', 'alt': 'Sala cheia'}]})
        self.assertEqual(res.status_code, 200, res.content)
        tr.assert_not_called()
        self.assertEqual(components.image_of(self.comp('pt', GALLERY, 'gallery')[3])['alt'], 'Sala cheia')
        self.assertEqual(components.image_of(self.comp('en', GALLERY, 'gallery')[3])['alt'], 'Full room')
        self.assertEqual(self.comp('en', GALLERY, 'gallery')[3]['href'], '/media/new.jpg')

    def test_replace_image_translates_missing_alt(self):
        with mock.patch(TRANSLATE, return_value=['Terrace']) as tr:
            res = self.post(GALLERY, 'gallery', 3, 'replace_image',
                            {'index': 0, 'image': {'url': '/media/t.jpg', 'alt': 'Esplanada'}})
        self.assertEqual(res.status_code, 200, res.content)
        tr.assert_called_once_with(['Esplanada'], 'pt', 'en')
        self.assertEqual(components.image_of(self.comp('en', GALLERY, 'gallery')[0])['alt'], 'Terrace')

    def test_set_settings(self):
        res = self.post(SLIDER, 'text-slider', 2, 'set_settings', {'settings': {'autoplay': True, 'interval': 4000}})
        self.assertEqual(res.status_code, 200, res.content)
        self.page.refresh_from_db()
        for lang in ('pt', 'en'):
            root = BeautifulSoup(self.page.html_content_i18n[lang], 'html.parser').select_one(SLIDER)
            self.assertEqual(json.loads(root['data-splide'])['interval'], 4000)

    def test_drifted_language_is_skipped(self):
        link_c = '<a href="/media/c.jpg" data-lightbox="g" data-alt="c"><img src="/media/c.jpg" alt="c"/></a>'
        self.page.html_content_i18n = {'pt': PT, 'en': EN.replace(link_c, '')}
        self.page.save()
        res = self.post(GALLERY, 'gallery', 3, 'remove', {'index': 0})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()['skipped_languages'], ['en'])
        self.assertEqual(len(self.comp('pt', GALLERY, 'gallery')), 2)
        self.assertEqual(len(self.comp('en', GALLERY, 'gallery')), 2)   # untouched: it already had 2

    def test_stale_count_in_current_language_is_409(self):
        res = self.post(GALLERY, 'gallery', 5, 'remove', {'index': 0})
        self.assertEqual(res.status_code, 409)
        self.assertFalse(res.json()['success'])

    def test_bad_arguments_are_400_and_change_nothing(self):
        before = dict(self.page.html_content_i18n)
        for op, args in (('reorder', {'order': [0, 0]}), ('remove', {'index': 9}), ('explode', {}),
                         ('set_settings', {'settings': {'type': 'cube'}}),
                         ('add_text_item', {'after': 0, 'texts': {'0': ' '}})):
            with self.subTest(op=op), mock.patch(TRANSLATE, return_value=['x']):
                res = self.post(SLIDER, 'text-slider', 2, op, args)
                self.assertEqual(res.status_code, 400, res.content)
        self.page.refresh_from_db()
        self.assertEqual(self.page.html_content_i18n, before)

    def test_non_staff_is_redirected(self):
        self.client.force_login(User.objects.create_user('plain', 'p@example.com', 'pw'))
        res = self.post(SLIDER, 'text-slider', 2, 'remove', {'index': 0})
        self.assertEqual(res.status_code, 302)


class ComponentApiReviewFixesTest(ComponentApiTest):
    def test_drifted_language_same_count_is_skipped(self):
        en = EN.replace('<p>Rui</p>', '<p><strong>Rui</strong> M.</p>')
        self.page.html_content_i18n = {'pt': PT, 'en': en}
        self.page.save()
        with mock.patch(TRANSLATE, return_value=['“Great.”', 'Zé']):
            res = self.post(SLIDER, 'text-slider', 2, 'add_text_item', {'after': 1, 'texts': {'0': '“Ótimo.”', '1': 'Zé'}})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()['skipped_languages'], ['en'])
        self.assertEqual(len(self.comp('pt', SLIDER, 'text-slider')), 3)
        self.assertEqual(len(self.comp('en', SLIDER, 'text-slider')), 2)

    def test_slider_kind_flip_between_languages(self):
        def hero(caps):
            slides = ''.join(f'<li class="splide__slide"><img src="/media/{i}.jpg" alt="{i}"/><p>{c}</p></li>' for i, c in enumerate(caps))
            return (f'<section data-section="h" id="h"><div class="splide"><div class="splide__track">'
                    f'<ul class="splide__list">{slides}</ul></div></div></section>')
        self.page.html_content_i18n = {'pt': hero(['Sala', 'Bar']),
                                       'en': hero(['A long English caption that is well over forty chars'] * 2)}
        self.page.save()
        root = 'section[data-section="h"] > div:nth-child(1)'
        res = self.post(root, 'slider', 2, 'reorder', {'order': [1, 0]})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()['skipped_languages'], [])
        self.page.refresh_from_db()
        self.assertLess(self.page.html_content_i18n['en'].index('/media/1.jpg'), self.page.html_content_i18n['en'].index('/media/0.jpg'))

    def test_update_item_on_empty_language_copy_edits_the_shown_copy(self):
        self.page.html_content_i18n = {'pt': PT, 'en': ''}
        self.page.save()
        res = self.post(SLIDER, 'text-slider', 2, 'update_item', {'index': 0, 'texts': {'1': 'Ana P.'}}, language='en')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(self.texts('pt', 0)[1], 'Ana P.')

    def test_template_syntax_is_400(self):
        res = self.post(SLIDER, 'text-slider', 2, 'update_item', {'index': 0, 'texts': {'1': 'Ana {% now %}'}})
        self.assertEqual(res.status_code, 400)
