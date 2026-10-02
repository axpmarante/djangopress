"""Paste a section copied from another DjangoPress site: read the clip, clean it, point its form
at one of this site's forms, flag links to pages this site lacks, and copy its images into this
site's library when it is added."""
import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.conf import settings
from django.test import TestCase, override_settings

from djangopress.core.models import DynamicForm, Page, SiteImage, SiteSettings
from djangopress.editor_v2 import paste

META = '<!-- djangopress:section {"site": "Adega Serra", "section": "visitas", "lang": "pt", "origin": "https://adega.example"} -->'
SECTION = ('<section data-section="visitas" id="visitas" class="py-10 ev2-selected" onclick="x()">'
           '<h2>Visitas</h2><img src="https://cdn.example/site_images/vinha.jpg" alt="Vinha">'
           '<img src="/media/site_images/adega.jpg" alt="">'
           '<div style="background-image: url(\'https://cdn.example/site_images/fundo.jpg\')"></div>'
           '<img src="https://placehold.co/600x400?text=x" alt="">'
           '<a href="/pt/visitas/">Ver</a><a href="/pt/sobre/">Sobre</a><a href="https://wa.me/1">WA</a>'
           '<form action="/forms/marcacoes/submit/" method="post"><input name="nome"></form>'
           '<script>alert(1)</script></section>')
CLIP = META + '\n' + SECTION


# Never write test images to the site's real storage (a bucket in development).
@override_settings(STORAGES={**settings.STORAGES, 'default': {'BACKEND': 'django.core.files.storage.InMemoryStorage'}})
class Base(TestCase):
    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        self.page = Page.objects.create(title_i18n={'pt': 'Início'}, slug_i18n={'pt': 'inicio'}, is_active=True,
                                        html_content_i18n={'pt': '<section data-section="visitas" id="visitas"><h2>Já existe</h2></section>'})
        Page.objects.create(title_i18n={'pt': 'Sobre'}, slug_i18n={'pt': 'sobre', 'en': 'about'}, is_active=True,
                            html_content_i18n={'pt': '<section data-section="a"></section>'})
        DynamicForm.objects.all().delete()
        DynamicForm.objects.create(name='Reserva', slug='reserva')


class ReadClipTest(Base):
    def test_the_marker_gives_the_source(self):
        html, meta = paste.read_clip(CLIP)
        self.assertEqual(meta['site'], 'Adega Serra')
        self.assertTrue(html.startswith('<section'))

    def test_plain_section_html_works_too(self):
        html, meta = paste.read_clip('<section data-section="x"><p>Olá</p></section>')
        self.assertEqual(meta, {})
        self.assertIn('Olá', html)

    def test_loose_html_is_wrapped_in_a_section(self):
        html, _meta = paste.read_clip('<div><p>Olá</p></div>')
        self.assertTrue(html.startswith('<section data-section="pasted"'))

    def test_nothing_to_paste(self):
        with self.assertRaises(ValueError):
            paste.read_clip('   ')


class InspectTest(Base):
    def inspect(self, clip=CLIP):
        return paste.inspect(self.page, clip, 'pt')

    def test_scripts_handlers_and_editor_state_are_removed(self):
        html = self.inspect()['html']
        for gone in ('<script', 'onclick', 'ev2-selected'):
            self.assertNotIn(gone, html)

    def test_the_name_does_not_clash_with_this_page(self):
        self.assertEqual(self.inspect()['name'], 'visitas-2')

    def test_relative_media_becomes_an_address_on_the_source_site(self):
        self.assertIn('src="https://adega.example/media/site_images/adega.jpg"', self.inspect()['html'])

    def test_a_form_this_site_lacks_posts_to_one_it_has(self):
        result = self.inspect()
        self.assertIn('action="/forms/reserva/submit/"', result['html'])
        self.assertIn('Reserva', ' '.join(c['text'] for c in result['checks']))

    def test_links_to_missing_pages_are_flagged(self):
        texts = ' '.join(c['text'] for c in self.inspect()['checks'])
        self.assertIn('/pt/visitas/', texts)
        self.assertNotIn('/pt/sobre/', texts)

    def test_images_to_copy_are_counted(self):
        result = self.inspect()
        self.assertEqual(result['images'], 3)          # placeholder skipped
        self.assertIn("3 images will be copied to this site's library", [c['text'] for c in result['checks']])

    def test_no_forms_here_says_so(self):
        DynamicForm.objects.all().delete()
        texts = ' '.join(c['text'] for c in self.inspect()['checks'])
        self.assertIn('This site has no forms', texts)


class CopyImagesTest(Base):
    def test_external_images_land_in_the_library_and_the_html_points_at_them(self):
        png = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4'
               b'\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82')
        html = paste.inspect(self.page, CLIP, 'pt')['html']
        with mock.patch('djangopress.editor_v2.paste.fetch_image', side_effect=lambda u: (png, 'image/png')):
            out = paste.copy_images(html)
        self.assertEqual(out['copied'], 3)
        self.assertEqual(SiteImage.objects.count(), 3)
        self.assertNotIn('cdn.example', out['html'])
        self.assertNotIn('adega.example', out['html'])
        self.assertEqual(SiteImage.objects.filter(alt_text_i18n__pt='Vinha').count(), 1)

    def test_an_image_that_cannot_be_read_stays_linked(self):
        html = paste.inspect(self.page, CLIP, 'pt')['html']
        with mock.patch('djangopress.editor_v2.paste.fetch_image', side_effect=ValueError('no')):
            out = paste.copy_images(html)
        self.assertEqual((out['copied'], out['kept']), (0, 3))
        self.assertIn('cdn.example/site_images/vinha.jpg', out['html'])


class EndpointsTest(Base):
    def setUp(self):
        super().setUp()
        self.client.force_login(get_user_model().objects.create_superuser('a', 'a@x.com', 'pw'))

    def post(self, url, **body):
        return self.client.post(url, json.dumps({'page_id': self.page.pk, **body}), content_type='application/json',
                                HTTP_X_EDITOR_LANGUAGE='pt')

    def test_inspect(self):
        data = self.post('/editor-v2/api/paste-section/inspect/', html=CLIP).json()
        self.assertTrue(data['success'])
        self.assertEqual(data['name'], 'visitas-2')
        self.assertEqual(data['source'], {'site': 'Adega Serra', 'section': 'visitas', 'lang': 'pt'})

    def test_inspect_with_nothing(self):
        self.assertEqual(self.post('/editor-v2/api/paste-section/inspect/', html='').status_code, 400)

    def test_apply_copies_images_and_inserts_after_the_anchor(self):
        html = paste.inspect(self.page, CLIP, 'pt')['html']
        with mock.patch('djangopress.editor_v2.paste.fetch_image', side_effect=ValueError('no')), \
                mock.patch('djangopress.editor_v2.ai_apply._translations', return_value={'en': ('<section>EN</section>', True)}):
            data = self.post('/editor-v2/api/paste-section/apply/', html=html, insert_after='visitas').json()
        self.assertTrue(data['success'], data)
        self.assertEqual(data['section_name'], 'visitas-2')
        self.assertEqual(data['kept_images'], 3)
        self.page.refresh_from_db()
        names = [s for s in ('visitas', 'visitas-2') if f'data-section="{s}"' in self.page.html_content_i18n['pt']]
        self.assertEqual(names, ['visitas', 'visitas-2'])


class ReviewFixesTest(Base):
    def test_a_rendered_csrf_token_goes_back_to_the_tag(self):
        clip = ('<section data-section="c"><form action="/forms/reserva/submit/" method="post">'
                '<input type="hidden" name="csrfmiddlewaretoken" value="SECRET123"></form></section>')
        html = paste.inspect(self.page, clip, 'pt')['html']
        self.assertNotIn('SECRET123', html)
        self.assertIn('{% csrf_token %}', html)

    def test_markup_that_runs_code_is_removed(self):
        clip = ('<section data-section="x"><iframe srcdoc="<script>alert(1)</script>"></iframe>'
                '<object data="x.swf"></object><embed src="x"><link rel="stylesheet" href="x.css">'
                '<meta http-equiv="refresh" content="0"><base href="https://evil.example/">'
                '<a id="j" href="javascript:alert(1)">x</a><button formaction="javascript:alert(1)">b</button>'
                '<iframe data-bg-video="youtube" src="https://www.youtube.com/embed/abc"></iframe>'
                '<img src="data:image/png;base64,AAAA" alt=""><img src="data:text/html,<b>x</b>" alt="">'
                '<a href="/pt/sobre/">ok</a></section>')
        html = paste.inspect(self.page, clip, 'pt')['html']
        for gone in ('srcdoc', '<object', '<embed', '<link', '<meta', '<base', 'javascript:', 'data:text/html'):
            self.assertNotIn(gone, html)
        for kept in ('youtube.com/embed/abc', 'data:image/png;base64,AAAA', 'href="/pt/sobre/"'):
            self.assertIn(kept, html)

    def test_an_image_on_another_sites_folder_with_the_same_name_is_not_ours(self):
        clip = ('<section data-section="x"><img src="https://cdn.example/media/outro/site_images/hero.jpg" alt="">'
                '<img src="https://cdn.example/media/este/site_images/hero.jpg" alt=""></section>')
        with mock.patch('djangopress.editor_v2.paste._media_base', return_value='https://cdn.example/media/este/'):
            self.assertEqual(paste.inspect(self.page, clip, 'pt')['images'], 1)

    def test_local_media_on_this_host_is_ours(self):
        clip = '<section data-section="x"><img src="http://testserver/media/site_images/a.jpg" alt=""></section>'
        with mock.patch('djangopress.editor_v2.paste._media_base', return_value='/media/'):
            self.assertEqual(paste.inspect(self.page, clip, 'pt', own_origin='http://testserver')['images'], 0)
            self.assertEqual(paste.inspect(self.page, clip, 'pt', own_origin='http://other')['images'], 1)


class ApplyFailureTest(EndpointsTest):
    PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4'
           b'\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82')

    def test_a_failed_insert_leaves_no_copied_images(self):
        html = paste.inspect(self.page, CLIP, 'pt')['html']
        with mock.patch('djangopress.editor_v2.paste.fetch_image', side_effect=lambda u: (self.PNG, 'image/png')), \
                mock.patch('djangopress.editor_v2.ai_apply.apply_section_html', side_effect=RuntimeError('boom')):
            res = self.post('/editor-v2/api/paste-section/apply/', html=html, insert_after='visitas')
        self.assertEqual(res.status_code, 500)
        self.assertFalse(res.json()['success'])
        self.assertEqual(SiteImage.objects.count(), 0)
