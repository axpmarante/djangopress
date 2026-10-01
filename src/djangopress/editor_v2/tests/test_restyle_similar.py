"""Apply to all similar: elements with the same tag and the same class list, on
every active page (and header/footer when asked), in every language; one
checkpoint per changed page."""
import json

from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from djangopress.core.models import GlobalSection, Page, PageVersion, SiteSettings

BTN = 'inline-flex px-6 py-3 bg-[#C42014] text-white'


def html(prefix, extra=''):
    return (f'<section data-section="a" id="a"><a class="{BTN}" href="/r/">{prefix} Reservar</a>'
            f'<a class="{BTN} w-full" href="/c/">{prefix} Carta</a>{extra}</section>')


class RestyleSimilarTest(TestCase):
    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        Page.objects.all().delete()
        self.a = Page.objects.create(title_i18n={'pt': 'Início'}, slug_i18n={'pt': 'inicio'}, is_active=True,
                                     html_content_i18n={'pt': html('PT'), 'en': html('EN')})
        self.b = Page.objects.create(title_i18n={'pt': 'Reservas'}, slug_i18n={'pt': 'reservas'}, is_active=True,
                                     html_content_i18n={'pt': html('PT'), 'en': html('EN')})
        self.header = GlobalSection.objects.create(key='main-header', name='Header', section_type='header',
                                                   html_template_i18n={'pt': f'<header><a class="{BTN}">R</a></header>'})
        PageVersion.objects.all().delete()
        staff = get_user_model().objects.create_user('ed', 'ed@x.com', 'pw', is_staff=True)
        self.client.force_login(staff)

    def post(self, **body):
        body.setdefault('tag', 'a')
        body.setdefault('classes', BTN.split())
        return self.client.post(reverse('editor_v2:api_restyle_similar'), data=json.dumps(body),
                                content_type='application/json')

    def classes(self, page, lang, text):
        page.refresh_from_db()
        soup = BeautifulSoup(page.html_content_i18n[lang], 'html.parser')
        return [a for a in soup.find_all('a') if text in a.get_text()][0].get('class')

    def test_count(self):
        res = self.client.get(reverse('editor_v2:api_restyle_similar'), {'tag': 'a', 'classes': BTN})
        self.assertEqual(res.json(), {'success': True, 'count': 2, 'pages': 2, 'globals': 1})

    def test_same_class_list_changes_on_every_page_and_language(self):
        res = self.post(add=['bg-[#E3A11C]'], remove=['bg-[#C42014]'])
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()['total'], 2)   # elements (one per page), each changed in both languages
        for page in (self.a, self.b):
            for lang, prefix in (('pt', 'PT'), ('en', 'EN')):
                self.assertIn('bg-[#E3A11C]', self.classes(page, lang, f'{prefix} Reservar'))
                self.assertNotIn('bg-[#C42014]', self.classes(page, lang, f'{prefix} Reservar'))
                self.assertIn('bg-[#C42014]', self.classes(page, lang, f'{prefix} Carta'))   # one extra class: not similar
        self.header.refresh_from_db()
        self.assertIn('bg-[#C42014]', self.header.html_template_i18n['pt'])

    def test_header_and_footer_when_asked(self):
        self.post(add=['rounded-full'], include_globals=True)
        self.header.refresh_from_db()
        self.assertIn('rounded-full', self.header.html_template_i18n['pt'])

    def test_one_checkpoint_per_changed_page(self):
        self.post(add=['rounded-full'])
        self.assertEqual(PageVersion.objects.filter(kind='checkpoint').count(), 2)
        self.assertTrue(PageVersion.objects.filter(page=self.a, change_summary='Apply to all similar').exists())

    def test_order_of_classes_does_not_matter_and_runtime_classes_are_ignored(self):
        res = self.post(classes=list(reversed(BTN.split())) + ['ev2-selected'], add=['rounded-full'])
        self.assertEqual(res.json()['total'], 2)   # elements (one per page), each changed in both languages

    def test_staff_only(self):
        self.client.logout()
        self.assertNotEqual(self.post(add=['x']).status_code, 200)

    def test_says_whether_the_current_page_changed(self):
        res = self.post(add=['rounded-full'], page_id=self.a.pk)
        self.assertIs(res.json()['current_page_changed'], True)
        other = Page.objects.create(title_i18n={'pt': 'Vazia'}, slug_i18n={'pt': 'vazia'}, is_active=True,
                                    html_content_i18n={'pt': '<section data-section="x" id="x"><p>x</p></section>'})
        res = self.post(add=['shadow-lg'], page_id=other.pk)
        self.assertIs(res.json()['current_page_changed'], False)
