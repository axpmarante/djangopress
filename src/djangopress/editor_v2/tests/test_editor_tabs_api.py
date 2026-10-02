"""Server side of the refreshed editor tabs: links localised per language,
heading level (retag), drag a section to a place, link targets, page copies."""
import json

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from djangopress.core.models import Page, PageVersion, SiteSettings

PT = ('<section data-section="hero" id="hero"><h2 class="text-4xl font-serif" id="t">Olá <b>mundo</b></h2>'
      '<a class="btn" href="/pt/">Início</a></section>'
      '<section data-section="sobre" id="sobre"><p>PT sobre</p></section>'
      '<section data-section="contactos" id="contactos"><p>PT contactos</p></section>')
EN = PT.replace('Olá', 'Hello').replace('Início', 'Home').replace('href="/pt/"', 'href="/en/"').replace('PT ', 'EN ')
H2 = 'section[data-section="hero"] > h2:nth-child(1)'
A = 'section[data-section="hero"] > a:nth-child(2)'


class Base(TestCase):
    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        Page.objects.all().delete()
        self.page = Page.objects.create(title_i18n={'pt': 'Início', 'en': 'Home'}, slug_i18n={'pt': 'inicio', 'en': 'home'},
                                        is_active=True, html_content_i18n={'pt': PT, 'en': EN})
        self.book = Page.objects.create(title_i18n={'pt': 'Reservas', 'en': 'Book'},
                                        slug_i18n={'pt': 'reservas', 'en': 'book-a-table'}, is_active=True,
                                        html_content_i18n={'pt': '<section data-section="grupos" id="grupos"></section>'})
        Page.objects.create(title_i18n={'pt': 'Rascunho'}, slug_i18n={'pt': 'rascunho'}, is_active=False,
                            html_content_i18n={'pt': '<section data-section="x"></section>'})
        PageVersion.objects.all().delete()
        self.user = get_user_model().objects.create_superuser('a', 'a@x.com', 'pw')
        self.client.force_login(self.user)

    def post(self, url, body, lang='pt'):
        return self.client.post(url, data=json.dumps({'page_id': self.page.id, **body}), content_type='application/json',
                                HTTP_REFERER=f'http://testserver/{lang}/?edit=v2')

    def html(self, lang):
        self.page.refresh_from_db()
        return self.page.html_content_i18n[lang]


class HrefTest(Base):
    def test_an_internal_link_is_localised_in_every_language(self):
        res = self.post('/editor-v2/api/update-page-attribute/', {'selector': A, 'attribute': 'href', 'value': '/pt/reservas/'})
        self.assertTrue(res.json()['success'], res.content)
        self.assertIn('href="/pt/reservas/"', self.html('pt'))
        self.assertIn('href="/en/book-a-table/"', self.html('en'))

    def test_saved_from_english_it_is_localised_back(self):
        self.post('/editor-v2/api/update-page-attribute/', {'selector': A, 'attribute': 'href', 'value': '/en/book-a-table/#grupos'}, lang='en')
        self.assertIn('href="/pt/reservas/#grupos"', self.html('pt'))
        self.assertIn('href="/en/book-a-table/#grupos"', self.html('en'))

    def test_a_page_path_without_language_is_read_as_the_editing_language(self):
        self.post('/editor-v2/api/update-page-attribute/', {'selector': A, 'attribute': 'href', 'value': '/reservas/'})
        self.assertIn('href="/pt/reservas/"', self.html('pt'))
        self.assertIn('href="/en/book-a-table/"', self.html('en'))

    def test_other_site_paths_are_left_alone(self):
        self.post('/editor-v2/api/update-page-attribute/', {'selector': A, 'attribute': 'href', 'value': '/media/menu.pdf'})
        self.assertIn('href="/media/menu.pdf"', self.html('pt'))
        self.assertIn('href="/media/menu.pdf"', self.html('en'))

    def test_phone_and_external_links_are_the_same_everywhere(self):
        for value in ('tel:+351968070776', 'https://wa.me/351968070776?text=Ol%C3%A1', '#contactos'):
            self.post('/editor-v2/api/update-page-attribute/', {'selector': A, 'attribute': 'href', 'value': value})
            self.assertIn(f'href="{value}"', self.html('pt'))
            self.assertIn(f'href="{value}"', self.html('en'))


class RetagTest(Base):
    def test_h2_to_h3_in_every_language_keeping_attributes_and_children(self):
        res = self.post('/editor-v2/api/retag-element/', {'selector': H2, 'tag': 'h3'})
        self.assertTrue(res.json()['success'], res.content)
        self.assertIn('<h3 class="text-4xl font-serif" id="t">Olá <b>mundo</b></h3>', self.html('pt'))
        self.assertIn('<h3 class="text-4xl font-serif" id="t">Hello <b>mundo</b></h3>', self.html('en'))
        self.assertEqual(PageVersion.objects.filter(page=self.page, kind='checkpoint').count(), 1)
        self.assertEqual(res.json()['selector'], 'section[data-section="hero"] > h3:nth-child(1)')

    def test_to_a_paragraph(self):
        self.post('/editor-v2/api/retag-element/', {'selector': H2, 'tag': 'p'})
        self.assertIn('<p class="text-4xl font-serif" id="t">', self.html('en'))

    def test_only_headings_and_paragraphs(self):
        res = self.post('/editor-v2/api/retag-element/', {'selector': H2, 'tag': 'div'})
        self.assertEqual(res.status_code, 400)
        self.assertIn('<h2', self.html('pt'))

    def test_only_text_elements_can_be_retagged(self):
        res = self.post('/editor-v2/api/retag-element/', {'selector': A, 'tag': 'h2'})
        self.assertEqual(res.status_code, 400)


class PlaceSectionTest(Base):
    def order(self, lang):
        import re
        return re.findall(r'data-section="([^"]+)"', self.html(lang))

    def test_place_before_another_section(self):
        res = self.post('/editor-v2/api/move-section/', {'section_name': 'contactos', 'before': 'hero'})
        self.assertTrue(res.json()['success'], res.content)
        self.assertEqual(self.order('pt'), ['contactos', 'hero', 'sobre'])
        self.assertEqual(self.order('en'), ['contactos', 'hero', 'sobre'])
        self.assertEqual(PageVersion.objects.filter(page=self.page, kind='checkpoint').count(), 1)

    def test_place_at_the_end(self):
        self.post('/editor-v2/api/move-section/', {'section_name': 'hero', 'before': None})
        self.assertEqual(self.order('en'), ['sobre', 'contactos', 'hero'])

    def test_same_place_is_a_no_op(self):
        res = self.post('/editor-v2/api/move-section/', {'section_name': 'hero', 'before': 'sobre'})
        self.assertFalse(res.json()['moved'])
        self.assertEqual(PageVersion.objects.count(), 0)

    def test_up_and_down_still_work(self):
        self.post('/editor-v2/api/move-section/', {'section_name': 'sobre', 'direction': 'up'})
        self.assertEqual(self.order('pt'), ['sobre', 'hero', 'contactos'])


class ReadEndpointsTest(Base):
    def test_link_targets_in_the_editing_language(self):
        res = self.client.get('/editor-v2/api/link-targets/', HTTP_REFERER='http://testserver/en/?edit=v2')
        pages = res.json()['pages']
        self.assertEqual([p['title'] for p in pages], ['Home', 'Book'])
        book = pages[1]
        self.assertEqual(book['url'], '/en/book-a-table/')
        self.assertEqual(book['sections'], [{'name': 'grupos', 'label': 'Grupos'}])
        self.assertEqual(pages[0]['url'], '/en/')

    def test_link_targets_always_carry_the_language(self):
        pages = self.client.get('/editor-v2/api/link-targets/', HTTP_REFERER='http://testserver/pt/?edit=v2').json()['pages']
        self.assertEqual([p['url'] for p in pages], ['/pt/', '/pt/reservas/'])

    def test_page_copies(self):
        res = self.client.get('/editor-v2/api/page-copies/', {'page_id': self.page.id})
        self.assertEqual(set(res.json()['copies']), {'pt', 'en'})
        self.assertIn('Hello', res.json()['copies']['en'])

    def test_page_copies_for_a_news_post(self):
        from djangopress.news.models import NewsPost
        post = NewsPost.objects.create(title_i18n={'pt': 'N'}, slug_i18n={'pt': 'n'}, html_content_i18n={'pt': '<p>a</p>', 'en': '<p>b</p>'})
        ct = ContentType.objects.get_for_model(post)
        res = self.client.get('/editor-v2/api/page-copies/', {'content_type_id': ct.id, 'object_id': post.pk})
        self.assertEqual(res.json()['copies'], {'pt': '<p>a</p>', 'en': '<p>b</p>'})


class RenameSectionTest(Base):
    def setUp(self):
        super().setUp()
        self.page.html_content_i18n = {
            'pt': PT.replace('<a class="btn" href="/pt/">', '<a class="btn" href="#sobre">'),
            'en': EN.replace('<a class="btn" href="/en/">', '<a class="btn" href="#sobre">'),
        }
        self.page.save()

    def test_rename_in_every_language_with_its_anchors(self):
        res = self.post('/editor-v2/api/rename-section/', {'section_name': 'sobre', 'new_name': 'Quem Somos'})
        self.assertTrue(res.json()['success'], res.content)
        self.assertEqual(res.json()['section_name'], 'quem-somos')
        for lang in ('pt', 'en'):
            html = self.html(lang)
            self.assertIn('<section data-section="quem-somos" id="quem-somos">', html)
            self.assertIn('href="#quem-somos"', html)
            self.assertNotIn('"sobre"', html)
        self.assertEqual(PageVersion.objects.filter(page=self.page, kind='checkpoint').count(), 1)

    def test_a_taken_or_empty_name_is_refused(self):
        self.assertEqual(self.post('/editor-v2/api/rename-section/', {'section_name': 'sobre', 'new_name': 'Hero'}).status_code, 400)
        self.assertEqual(self.post('/editor-v2/api/rename-section/', {'section_name': 'sobre', 'new_name': '  '}).status_code, 400)
        self.assertIn('data-section="sobre"', self.html('pt'))
