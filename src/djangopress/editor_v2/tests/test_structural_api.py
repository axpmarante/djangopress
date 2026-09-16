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

    def post(self, url_name, body, referer='http://testserver/pt/?edit=v2'):
        body = {'page_id': self.page.id, **body}
        return self.client.post(
            reverse(f'editor_v2:{url_name}'), data=json.dumps(body),
            content_type='application/json', HTTP_REFERER=referer,
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
        self.assertTrue(
            PageVersion.objects.filter(page=self.page, change_summary__contains='Duplicated element').exists()
        )
        self.assertGreaterEqual(PageVersion.objects.filter(page=self.page).count(), 1)

    def test_two_versions_have_distinct_labels(self):
        # The pre-change snapshot and the post-save auto-snapshot must not
        # share the exact same change_summary, or version history can't tell
        # "before" from "after".
        self.post('api_duplicate_element', {'selector': CARD_1})
        summaries = list(
            PageVersion.objects.filter(page=self.page).order_by('version_number').values_list('change_summary', flat=True)
        )
        self.assertEqual(len(summaries), 2)
        self.assertNotEqual(summaries[0], summaries[1])
        self.assertEqual(summaries[0], 'Before: Duplicated element')
        self.assertEqual(summaries[1], 'Duplicated element')

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

    def test_validates_against_the_edited_language_not_the_default(self):
        # PT (default) lacks a third card that EN has; editing from /en/?edit=v2
        # must validate/apply against EN, not fall back to PT.
        en_only_card = 'section[data-section="services"] > div:nth-child(1) > div:nth-child(3)'
        self.page.html_content_i18n['en'] = self.page.html_content_i18n['en'].replace(
            '<div class="card"><h3>Two</h3><p>B</p></div>',
            '<div class="card"><h3>Two</h3><p>B</p></div><div class="card"><h3>Three</h3><p>C</p></div>',
        )
        self.page.save()
        res = self.post(
            'api_duplicate_element', {'selector': en_only_card},
            referer='http://testserver/en/?edit=v2',
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['skipped_languages'], ['pt'])
        self.assertEqual(self.html('en').count('<h3>Three</h3>'), 2)
        self.assertEqual(self.html('pt').count('<h3>Um</h3>'), 1)


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
        self.assertEqual(data['page_id'], self.page.id)
        self.assertEqual(PageVersion.objects.count(), 0)

    def test_bad_direction_is_400(self):
        res = self.post('api_move_element', {'selector': CARD_1, 'direction': 'left'})
        self.assertEqual(res.status_code, 400)


class InsertElementTest(StructuralApiTestCase):
    def test_inserts_identical_snippet_in_all_languages(self):
        res = self.post('api_insert_element', {'selector': CARD_2, 'position': 'after', 'html': '<p class="lead">New</p>'})
        data = res.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['selector'], CARD_2.replace('div:nth-child(2)', 'p:nth-child(3)'))
        self.assertIn('<p class="lead">New</p>', self.html('pt'))
        self.assertIn('<p class="lead">New</p>', self.html('en'))

    def test_invalid_snippet_is_400(self):
        res = self.post('api_insert_element', {'selector': CARD_2, 'position': 'after', 'html': '<script>x</script>'})
        self.assertEqual(res.status_code, 400)
        self.assertIn('script', res.json()['error'])
        self.assertEqual(PageVersion.objects.count(), 0)

    def test_bad_position_is_400(self):
        res = self.post('api_insert_element', {'selector': CARD_2, 'position': 'inside', 'html': '<p>x</p>'})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(PageVersion.objects.count(), 0)


class DuplicateSectionTest(StructuralApiTestCase):
    def test_duplicate_section_in_all_languages(self):
        res = self.post('api_duplicate_section', {'section_name': 'services'})
        data = res.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['section_name'], 'services-2')
        for lang in ('pt', 'en'):
            self.assertIn('data-section="services-2"', self.html(lang))
            self.assertIn('id="services-2"', self.html(lang))
        self.assertTrue(
            PageVersion.objects.filter(page=self.page, change_summary__contains='Duplicated section').exists()
        )

    def test_second_duplicate_gets_next_suffix(self):
        self.post('api_duplicate_section', {'section_name': 'services'})
        res = self.post('api_duplicate_section', {'section_name': 'services'})
        self.assertEqual(res.json()['section_name'], 'services-3')

    def test_missing_section_is_400(self):
        res = self.post('api_duplicate_section', {'section_name': 'nope'})
        self.assertEqual(res.status_code, 400)

    def test_next_free_name_is_unique_across_all_language_copies(self):
        # EN has already drifted ahead with a "services-2" section (e.g. from a
        # previous duplicate that skipped PT). Duplicating from PT must not
        # collide with it.
        self.page.html_content_i18n['en'] = self.page.html_content_i18n['en'].replace(
            '</section><section data-section="cta"',
            '</section><section data-section="services-2" id="services-2"></section>'
            '<section data-section="cta"',
        )
        self.page.save()
        res = self.post('api_duplicate_section', {'section_name': 'services'})
        data = res.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['section_name'], 'services-3')
        self.assertIn('data-section="services-3"', self.html('pt'))
        self.assertIn('data-section="services-3"', self.html('en'))

    def test_language_without_the_section_is_skipped(self):
        self.page.html_content_i18n['en'] = '<section data-section="cta" id="cta"><a href="#services">See</a></section>'
        self.page.save()
        res = self.post('api_duplicate_section', {'section_name': 'services'})
        data = res.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['skipped_languages'], ['en'])
        self.assertIn('data-section="services-2"', self.html('pt'))


class MoveSectionTest(StructuralApiTestCase):
    def test_move_section_down(self):
        res = self.post('api_move_section', {'section_name': 'services', 'direction': 'down'})
        self.assertTrue(res.json()['moved'])
        for lang in ('pt', 'en'):
            html = self.html(lang)
            self.assertLess(html.index('data-section="cta"'), html.index('data-section="services"'))

    def test_move_section_at_edge_is_noop(self):
        res = self.post('api_move_section', {'section_name': 'services', 'direction': 'up'})
        self.assertTrue(res.json()['success'])
        self.assertFalse(res.json()['moved'])
        self.assertEqual(res.json()['page_id'], self.page.id)
        self.assertEqual(PageVersion.objects.count(), 0)

    def test_bad_direction_is_400(self):
        res = self.post('api_move_section', {'section_name': 'services', 'direction': 'left'})
        self.assertEqual(res.status_code, 400)
