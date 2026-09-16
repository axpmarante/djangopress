import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from djangopress.core.models import Page, PageVersion, SiteSettings

User = get_user_model()

PT_HTML = (
    '<section data-section="services" id="services">'
    '<div class="grid">'
    '<div class="card"><h3>Um</h3><p>A</p></div>'
    '<div class="card"><h3>Dois</h3><p>B</p></div>'
    '</div>'
    '</section>'
    '<section data-section="cta" id="cta"><a href="#services">Ver</a></section>'
)
EN_HTML = (
    '<section data-section="services" id="services">'
    '<div class="grid">'
    '<div class="card"><h3>One</h3><p>A</p></div>'
    '<div class="card"><h3>Two</h3><p>B</p></div>'
    '</div>'
    '</section>'
    '<section data-section="cta" id="cta"><a href="#services">See</a></section>'
)
CARD_1 = 'section[data-section="services"] > div:nth-child(1) > div:nth-child(1)'
CARD_2 = 'section[data-section="services"] > div:nth-child(1) > div:nth-child(2)'


class StructuralApiTestCase(TestCase):
    def setUp(self):
        Page.objects.all().delete()
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        self.page = Page.objects.create(
            title_i18n={'pt': 'Home', 'en': 'Home'}, slug_i18n={'pt': 'home', 'en': 'home'},
            is_active=True, html_content_i18n={'pt': PT_HTML, 'en': EN_HTML},
        )
        self.staff = User.objects.create_user('staff', 'staff@example.com', 'pw', is_staff=True)
        self.client.force_login(self.staff)

    def post(self, url_name, body):
        body = {'page_id': self.page.id, **body}
        return self.client.post(
            reverse(f'editor_v2:{url_name}'), data=json.dumps(body),
            content_type='application/json', HTTP_REFERER='http://testserver/pt/?edit=v2',
        )

    def html(self, lang):
        self.page.refresh_from_db()
        return self.page.html_content_i18n[lang]


class PermissionsTest(StructuralApiTestCase):
    def test_staff_can_remove_element(self):
        res = self.post('api_remove_element', {'selector': CARD_2})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['success'])
        self.assertNotIn('Dois', self.html('pt'))
        self.assertNotIn('Two', self.html('en'))

    def test_staff_can_list_versions(self):
        self.page.create_version(user=self.staff, change_summary='x')
        res = self.client.get(reverse('editor_v2:api_list_versions', args=[self.page.id]))
        self.assertEqual(res.status_code, 200)

    def test_non_staff_is_redirected(self):
        plain = User.objects.create_user('plain', 'p@example.com', 'pw')
        self.client.force_login(plain)
        res = self.post('api_remove_element', {'selector': CARD_2})
        self.assertEqual(res.status_code, 302)
        self.assertIn('Dois', self.html('pt'))

    def test_anonymous_is_redirected(self):
        self.client.logout()
        res = self.post('api_remove_section', {'section_name': 'cta'})
        self.assertEqual(res.status_code, 302)
