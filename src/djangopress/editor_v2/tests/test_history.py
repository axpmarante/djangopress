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


class HistoryApiTest(HistoryTestCase):
    def state(self):
        return self.client.get(reverse('editor_v2:api_history', args=[self.page.id])).json()

    def test_state_empty(self):
        self.assertEqual(self.state(), {'success': True, 'undo': None, 'redo': None})

    def test_undo_reverts_a_verb_in_all_languages(self):
        self.post('api_duplicate_element', {'selector': CARD_1})
        self.assertEqual(self.html('pt').count('<h3>Um</h3>'), 2)
        st = self.state()
        self.assertEqual(st['undo']['label'], 'Duplicated element')
        self.assertIsNone(st['redo'])
        res = self.post('api_undo', {})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['label'], 'Duplicated element')
        self.assertEqual(self.html('pt'), PT)
        self.assertEqual(self.html('en'), EN)
        st = self.state()
        self.assertIsNone(st['undo'])
        self.assertEqual(st['redo']['label'], 'Duplicated element')

    def test_redo_reapplies(self):
        self.post('api_duplicate_element', {'selector': CARD_1})
        self.post('api_undo', {})
        res = self.post('api_redo', {})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.html('pt').count('<h3>Um</h3>'), 2)
        self.assertEqual(self.html('en').count('<h3>One</h3>'), 2)
        self.assertEqual(self.state()['undo']['label'], 'Duplicated element')
        self.assertIsNone(self.state()['redo'])

    def test_new_operation_after_undo_clears_redo(self):
        self.post('api_duplicate_element', {'selector': CARD_1})
        self.post('api_undo', {})
        self.post('api_remove_element', {'selector': CARD_1})
        self.assertIsNone(self.state()['redo'])
        self.assertEqual(self.state()['undo']['label'], 'Removed element')

    def test_undo_twice_walks_back_twice(self):
        self.post('api_duplicate_element', {'selector': CARD_1})
        self.post('api_remove_element', {'selector': CARD_1})
        self.post('api_undo', {})
        self.post('api_undo', {})
        self.assertEqual(self.html('pt'), PT)
        self.assertIsNone(self.state()['undo'])

    def test_undo_with_nothing_is_400(self):
        self.assertEqual(self.post('api_undo', {}).status_code, 400)

    def test_undo_keeps_title(self):
        self.post('api_duplicate_element', {'selector': CARD_1})
        self.page.refresh_from_db(); self.page.title_i18n = {'pt': 'Novo', 'en': 'New'}; self.page.save()
        self.post('api_undo', {})
        self.page.refresh_from_db()
        self.assertEqual(self.page.title_i18n['pt'], 'Novo')

    def test_checkpoint_then_manual_edit_is_undoable(self):
        self.post('api_checkpoint', {'label': 'Edits (1)'})
        self.client.post(reverse('editor_v2:api_update_page_content'), data=json.dumps({
            'page_id': self.page.id, 'selector': CARD_1 + ' > h3:nth-child(1)', 'language': 'pt', 'value': 'Alterado'}),
            content_type='application/json')
        self.assertIn('Alterado', self.html('pt'))
        self.post('api_undo', {})
        self.assertNotIn('Alterado', self.html('pt'))

    def test_restore_version_restores_all_languages_and_is_undoable(self):
        self.post('api_duplicate_element', {'selector': CARD_1})
        first = PageVersion.objects.filter(page=self.page, kind='checkpoint').order_by('version_number').first()
        res = self.post('api_restore_version', {'version_number': first.version_number})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.html('pt'), PT)
        self.assertEqual(self.html('en'), EN)
        self.assertEqual(self.state()['undo']['label'], f'Restore to v{first.version_number}')

    def test_list_versions_returns_all_with_kind(self):
        for i in range(12):
            self.post('api_checkpoint', {'label': f'c{i}'})
        res = self.client.get(reverse('editor_v2:api_list_versions', args=[self.page.id])).json()
        self.assertEqual(len(res['versions']), 12)
        self.assertEqual(res['versions'][0]['kind'], 'checkpoint')

    def test_non_staff_cannot_undo(self):
        self.client.force_login(User.objects.create_user('plain', 'p@example.com', 'pw'))
        self.assertEqual(self.post('api_undo', {}).status_code, 302)

    # -- Final-review fixes --------------------------------------------------

    def test_video_set_checkpoints_and_is_undoable(self):
        res = self.post('api_update_section_video', {'section_id': 'services', 'video_url': 'https://example.com/x.mp4'})
        self.assertEqual(res.status_code, 200)
        self.assertIn('<video', self.html('pt'))
        self.assertIn('<video', self.html('en'))
        self.assertEqual(self.state()['undo']['label'], 'Changed section video')
        undo_res = self.post('api_undo', {})
        self.assertEqual(undo_res.json()['label'], 'Changed section video')
        self.assertNotIn('<video', self.html('pt'))

    def test_video_removed_checkpoints_with_its_own_label(self):
        self.post('api_update_section_video', {'section_id': 'services', 'video_url': 'https://example.com/x.mp4'})
        res = self.post('api_update_section_video', {'section_id': 'services', 'video_url': ''})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.state()['undo']['label'], 'Removed section video')

    def test_undo_keeps_a_language_gained_after_the_checkpoint(self):
        self.post('api_checkpoint', {'label': 'Before add ES'})
        self.page.refresh_from_db()
        html_i18n = dict(self.page.html_content_i18n)
        html_i18n['es'] = PT
        self.page.html_content_i18n = html_i18n
        self.page.save()
        self.assertEqual(self.html('es'), PT)
        self.post('api_undo', {})
        self.assertEqual(self.html('es'), PT)
        self.assertEqual(self.html('pt'), PT)

    def test_restore_of_empty_snapshot_is_400(self):
        empty = PageVersion.objects.create(
            page=self.page,
            version_number=PageVersion.next_version_number_for(self.page),
            html_content_i18n={'pt': '', 'en': ''},
            change_summary='Empty',
            kind='checkpoint',
        )
        res = self.post('api_restore_version', {'version_number': empty.version_number})
        self.assertEqual(res.status_code, 400)
        self.assertIn('no HTML content', res.json()['error'])

    def test_undo_with_stale_expected_version_is_409(self):
        self.post('api_duplicate_element', {'selector': CARD_1})
        target_version = self.state()['undo']['version_number']
        res = self.post('api_undo', {'expected_version': target_version - 1})
        self.assertEqual(res.status_code, 409)
        self.assertIn('changed in another window', res.json()['error'])
        # Nothing was applied: still undoable, HTML untouched.
        self.assertEqual(self.html('pt').count('<h3>Um</h3>'), 2)

    def test_undo_with_matching_expected_version_succeeds(self):
        self.post('api_duplicate_element', {'selector': CARD_1})
        target_version = self.state()['undo']['version_number']
        res = self.post('api_undo', {'expected_version': target_version})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.html('pt'), PT)

    def test_structural_verb_responses_include_label(self):
        self.assertEqual(self.post('api_duplicate_element', {'selector': CARD_1}).json()['label'], 'Duplicated element')
        self.assertEqual(self.post('api_remove_element', {'selector': CARD_1}).json()['label'], 'Removed element')
        self.assertEqual(
            self.post('api_remove_section', {'section_name': 'services'}).json()['label'],
            'Removed section "services"',
        )

    def test_checkpoint_with_missing_page_is_404(self):
        res = self.client.post(reverse('editor_v2:api_checkpoint'),
                                data=json.dumps({'page_id': 999999, 'label': 'x'}),
                                content_type='application/json')
        self.assertEqual(res.status_code, 404)

    def test_undo_with_missing_page_is_404(self):
        res = self.client.post(reverse('editor_v2:api_undo'),
                                data=json.dumps({'page_id': 999999}),
                                content_type='application/json')
        self.assertEqual(res.status_code, 404)

    def test_restore_version_with_missing_page_is_404(self):
        res = self.client.post(reverse('editor_v2:api_restore_version'),
                                data=json.dumps({'page_id': 999999, 'version_number': 1}),
                                content_type='application/json')
        self.assertEqual(res.status_code, 404)
