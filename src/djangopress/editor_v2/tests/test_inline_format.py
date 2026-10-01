"""Inline text edits keep their formatting: links, bold and italic made with the
floating toolbar are saved, and the HTML is cleaned to inline tags only."""
import json

from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from djangopress.core.models import Page, SiteSettings

PT = '<section data-section="hero" id="hero"><p class="lead">Olá <strong>mundo</strong></p></section>'
EN = '<section data-section="hero" id="hero"><p class="lead">Hello <strong>world</strong></p></section>'
SEL = 'section[data-section="hero"] > p:nth-child(1)'


class InlineFormatTest(TestCase):
    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        self.page = Page.objects.create(title_i18n={'pt': 'Início'}, slug_i18n={'pt': 'inicio'}, is_active=True,
                                        html_content_i18n={'pt': PT, 'en': EN})
        staff = get_user_model().objects.create_user('ed', 'ed@x.com', 'pw', is_staff=True)
        self.client.force_login(staff)

    def save(self, value, fmt=None, language='pt'):
        body = {'page_id': self.page.id, 'selector': SEL, 'language': language, 'value': value, 'field_key': ''}
        if fmt:
            body['format'] = fmt
        res = self.client.post(reverse('editor_v2:api_update_page_content'), data=json.dumps(body),
                               content_type='application/json')
        self.assertEqual(res.status_code, 200, res.content)
        self.page.refresh_from_db()
        return BeautifulSoup(self.page.html_content_i18n[language], 'html.parser').select_one(SEL)

    def test_a_link_and_bold_are_kept(self):
        p = self.save('Veja a <a href="/reservas/">página de reservas</a> e o <b>menu</b>', fmt='html')
        self.assertEqual(p.find('a')['href'], '/reservas/')
        self.assertEqual(p.find('a').get_text(), 'página de reservas')
        self.assertEqual(p.find('b').get_text(), 'menu')
        self.assertEqual(p.get('class'), ['lead'])                       # the element itself is untouched

    def test_only_the_edited_language_changes(self):
        self.save('Novo <em>texto</em>', fmt='html')
        self.assertEqual(self.page.html_content_i18n['en'], EN)

    def test_dangerous_markup_is_removed(self):
        p = self.save('<a href="javascript:alert(1)" onclick="x()">clica</a><script>alert(1)</script>'
                      '<img src=x onerror=alert(1)><div style="color:red">bloco</div> <span class="text-red-600">ok</span>',
                      fmt='html')
        html = str(p)
        self.assertNotIn('javascript', html)
        self.assertNotIn('onclick', html)
        self.assertNotIn('<script', html)
        self.assertNotIn('alert(1)', html)
        self.assertNotIn('<img', html)
        self.assertNotIn('style=', html)
        self.assertIn('clica', html)
        self.assertIn('bloco', html)
        self.assertIn('<span class="text-red-600">ok</span>', html)

    def test_safe_links_keep_their_target(self):
        p = self.save('<a href="https://checkinfaro.pt" target="_blank">site</a> <a href="mailto:a@b.pt">mail</a> '
                      '<a href="tel:+351289000000">tel</a>', fmt='html')
        self.assertEqual([a['href'] for a in p.find_all('a')],
                         ['https://checkinfaro.pt', 'mailto:a@b.pt', 'tel:+351289000000'])
        self.assertEqual(p.find('a').get('rel'), ['noopener'])

    def test_plain_text_edits_still_work_and_escape(self):
        p = self.save('Texto <b>não</b> é HTML')
        self.assertIsNone(p.find('b'))
        self.assertEqual(p.get_text(), 'Texto <b>não</b> é HTML')

    def test_template_variables_are_kept_as_typed(self):
        p = self.save('Escreva para <a href="mailto:{{ CONTACT_EMAIL }}">{{ CONTACT_EMAIL }}</a>', fmt='html')
        self.assertIn('{{ CONTACT_EMAIL }}', p.get_text())
