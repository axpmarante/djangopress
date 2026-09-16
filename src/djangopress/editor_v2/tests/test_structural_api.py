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
        # Page has a post_save signal that auto-snapshots a version on every
        # save, including this creation. Clear it so version-count
        # assertions below start from a clean slate.
        PageVersion.objects.filter(page=self.page).delete()
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


class DuplicateElementTest(StructuralApiTestCase):
    def test_duplicates_in_all_languages_and_returns_new_selector(self):
        res = self.post('api_duplicate_element', {'selector': CARD_1})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['selector'], CARD_2)
        self.assertEqual(data['skipped_languages'], [])
        self.assertEqual(self.html('pt').count('<h3>Um</h3>'), 2)
        self.assertEqual(self.html('en').count('<h3>One</h3>'), 2)
        self.assertEqual(PageVersion.objects.filter(page=self.page).count(), 1)
        self.assertIn('Duplicated element', PageVersion.objects.get().change_summary)

    def test_language_without_the_element_is_skipped_and_reported(self):
        self.page.html_content_i18n['en'] = '<section data-section="services" id="services"><p>x</p></section>'
        self.page.save()
        res = self.post('api_duplicate_element', {'selector': CARD_1})
        self.assertTrue(res.json()['success'])
        self.assertEqual(res.json()['skipped_languages'], ['en'])
        self.assertEqual(self.html('pt').count('<h3>Um</h3>'), 2)

    def test_missing_selector_is_400(self):
        res = self.post('api_duplicate_element', {'selector': CARD_1.replace('(1)', '(9)')})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(PageVersion.objects.count(), 0)


class MoveElementTest(StructuralApiTestCase):
    def test_move_down_swaps_in_all_languages(self):
        res = self.post('api_move_element', {'selector': CARD_1, 'direction': 'down'})
        data = res.json()
        self.assertTrue(data['success'])
        self.assertTrue(data['moved'])
        self.assertEqual(data['selector'], CARD_2)
        self.assertLess(self.html('pt').index('Dois'), self.html('pt').index('Um'))
        self.assertLess(self.html('en').index('Two'), self.html('en').index('One'))

    def test_move_at_edge_is_noop(self):
        res = self.post('api_move_element', {'selector': CARD_1, 'direction': 'up'})
        data = res.json()
        self.assertTrue(data['success'])
        self.assertFalse(data['moved'])
        self.assertEqual(PageVersion.objects.count(), 0)

    def test_bad_direction_is_400(self):
        res = self.post('api_move_element', {'selector': CARD_1, 'direction': 'left'})
        self.assertEqual(res.status_code, 400)
