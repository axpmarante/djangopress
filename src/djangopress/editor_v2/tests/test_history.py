import json
from types import SimpleNamespace as V

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from djangopress.core.models import Page, PageVersion, SiteSettings
from djangopress.editor_v2.history import find_undo_target, find_redo_target

User = get_user_model()

PT = ('<section data-section="services" id="services"><div class="grid">'
      '<div class="card"><h3>Um</h3></div><div class="card"><h3>Dois</h3></div></div></section>')
EN = PT.replace('Um', 'One').replace('Dois', 'Two')
CARD_1 = 'section[data-section="services"] > div:nth-child(1) > div:nth-child(1)'


class HistoryTestCase(TestCase):
    def setUp(self):
        Page.objects.all().delete()
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        self.page = Page.objects.create(title_i18n={'pt': 'Home', 'en': 'Home'},
                                        slug_i18n={'pt': 'home', 'en': 'home'},
                                        is_active=True, html_content_i18n={'pt': PT, 'en': EN})
        PageVersion.objects.filter(page=self.page).delete()
        self.staff = User.objects.create_user('staff', 's@example.com', 'pw', is_staff=True)
        self.client.force_login(self.staff)

    def post(self, name, body, referer='http://testserver/pt/?edit=v2'):
        return self.client.post(reverse(f'editor_v2:{name}'), data=json.dumps({'page_id': self.page.id, **body}),
                                content_type='application/json', HTTP_REFERER=referer)

    def html(self, lang='pt'):
        self.page.refresh_from_db()
        return self.page.html_content_i18n[lang]

    def kinds(self):
        return list(PageVersion.objects.filter(page=self.page).order_by('version_number').values_list('kind', 'change_summary'))


class KindFieldTest(HistoryTestCase):
    def test_default_kind_is_auto_and_signal_snapshots_are_auto(self):
        self.page.html_content_i18n = {'pt': PT + '<!-- x -->', 'en': EN}
        self.page.save()
        self.assertEqual(self.kinds(), [('auto', '')])

    def test_create_version_accepts_kind(self):
        self.page.create_version(user=self.staff, change_summary='Duplicated element', kind='checkpoint')
        self.assertEqual(self.kinds(), [('checkpoint', 'Duplicated element')])

    def test_structural_verb_writes_checkpoint_then_auto(self):
        res = self.post('api_duplicate_element', {'selector': CARD_1})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.kinds(), [('checkpoint', 'Duplicated element'), ('auto', 'Duplicated element')])

    def test_remove_verbs_write_checkpoints(self):
        self.post('api_remove_element', {'selector': CARD_1})
        self.post('api_remove_section', {'section_name': 'services'})
        self.assertEqual([k for k, _ in self.kinds()], ['checkpoint', 'auto', 'checkpoint', 'auto'])
        self.assertEqual(self.kinds()[0][1], 'Removed element')
        self.assertEqual(self.kinds()[2][1], 'Removed section "services"')

    def test_max_versions_is_60(self):
        for i in range(65):
            self.page.create_version(change_summary=f'v{i}', kind='checkpoint')
        self.assertEqual(PageVersion.objects.filter(page=self.page).count(), 60)


def seq(*items):
    """items: (kind, label) oldest→newest; returns newest-first list with version numbers."""
    out = [V(kind=k, change_summary=l, version_number=i + 1, html_content_i18n={}) for i, (k, l) in enumerate(items)]
    return list(reversed(out))


class UndoTargetTest(TestCase):
    def test_latest_checkpoint_is_the_target(self):
        vs = seq(('checkpoint', 'op1'), ('auto', ''), ('checkpoint', 'op2'), ('auto', ''))
        self.assertEqual(find_undo_target(vs).change_summary, 'op2')

    def test_auto_only_has_no_target(self):
        self.assertIsNone(find_undo_target(seq(('auto', ''), ('auto', ''))))

    def test_undo_consumes_one_checkpoint(self):
        vs = seq(('checkpoint', 'op1'), ('auto', ''), ('checkpoint', 'op2'), ('auto', ''), ('undo', 'op2'), ('auto', ''))
        self.assertEqual(find_undo_target(vs).change_summary, 'op1')

    def test_redo_cancels_an_undo(self):
        vs = seq(('checkpoint', 'op1'), ('auto', ''), ('checkpoint', 'op2'), ('auto', ''),
                 ('undo', 'op2'), ('auto', ''), ('redo', 'op2'), ('auto', ''))
        self.assertEqual(find_undo_target(vs).change_summary, 'op2')

    def test_two_undos_walk_back_twice(self):
        vs = seq(('checkpoint', 'op1'), ('auto', ''), ('checkpoint', 'op2'), ('auto', ''), ('checkpoint', 'op3'), ('auto', ''),
                 ('undo', 'op3'), ('auto', ''), ('undo', 'op2'), ('auto', ''))
        self.assertEqual(find_undo_target(vs).change_summary, 'op1')


class RedoTargetTest(TestCase):
    def test_latest_undo_is_the_redo_target(self):
        vs = seq(('checkpoint', 'op1'), ('auto', ''), ('undo', 'op1'), ('auto', ''))
        self.assertEqual(find_redo_target(vs).kind, 'undo')

    def test_redo_consumes_the_undo(self):
        vs = seq(('checkpoint', 'op1'), ('auto', ''), ('undo', 'op1'), ('auto', ''), ('redo', 'op1'), ('auto', ''))
        self.assertIsNone(find_redo_target(vs))

    def test_new_checkpoint_invalidates_redo(self):
        vs = seq(('checkpoint', 'op1'), ('auto', ''), ('undo', 'op1'), ('auto', ''), ('checkpoint', 'op2'), ('auto', ''))
        self.assertIsNone(find_redo_target(vs))

    def test_two_undos_two_redos(self):
        vs = seq(('checkpoint', 'op1'), ('auto', ''), ('checkpoint', 'op2'), ('auto', ''),
                 ('undo', 'op2'), ('auto', ''), ('undo', 'op1'), ('auto', ''), ('redo', 'op1'), ('auto', ''))
        self.assertEqual(find_redo_target(vs).change_summary, 'op2')
