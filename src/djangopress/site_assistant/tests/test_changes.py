"""Every assistant change can be undone per turn (pages, header/footer, settings,
menu items, forms), with one labelled checkpoint per page per turn."""
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from djangopress.core.models import GlobalSection, MenuItem, Page, PageVersion, SiteSettings
from djangopress.editor_v2 import history
from djangopress.site_assistant import changes
from djangopress.site_assistant.models import AssistantSession
from djangopress.site_assistant.services import AssistantService
from djangopress.site_assistant.tools import ToolRegistry

ROUTER = 'djangopress.site_assistant.services.Router.classify'
HTML = '<section data-section="hero" id="hero"><h1 class="a">Olá</h1></section>'


def fc(name, **args):
    part = SimpleNamespace(function_call=SimpleNamespace(name=name, args=args), text=None)
    return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(role='model', parts=[part]))])


def text(t):
    part = SimpleNamespace(function_call=None, text=t)
    return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(role='model', parts=[part]))])


class ChangesTestCase(TestCase):
    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}]
        s.default_language = 'pt'
        s.contact_phone = '+351 289 000 000'
        s.save()
        self.page = Page.objects.create(title_i18n={'pt': 'Início'}, slug_i18n={'pt': 'inicio'}, is_active=True,
                                        html_content_i18n={'pt': HTML})
        PageVersion.objects.filter(page=self.page).delete()
        self.user = get_user_model().objects.create_superuser('a', 'a@x.com', 'pw')
        self.session = AssistantSession.objects.create(created_by=self.user, active_page=self.page)
        self.tracker = changes.TurnChanges('Muda o título e o telefone', self.user)
        self.context = {'session': self.session, 'user': self.user, 'active_page': self.page, 'changes': self.tracker}

    def run_tool(self, name, **params):
        return ToolRegistry.execute(name, params, self.context)

    def record_turn(self):
        """Store the tracker's change log on an assistant message, like the service does."""
        self.session.add_message('user', 'pedido')
        self.session.add_message('assistant', 'feito')
        msg = self.session.messages[-1]
        msg['changes'] = self.tracker.finish()
        self.session.save()
        return len(self.session.messages) - 1


class CheckpointTest(ChangesTestCase):
    def test_one_labelled_checkpoint_per_page_per_turn(self):
        self.run_tool('update_element_styles', selector='section[data-section="hero"] > h1:nth-child(1)', new_classes='b')
        self.run_tool('update_element_styles', selector='section[data-section="hero"] > h1:nth-child(1)', new_classes='c')
        checkpoints = PageVersion.objects.filter(page=self.page, kind='checkpoint')
        self.assertEqual(checkpoints.count(), 1)
        self.assertTrue(checkpoints.first().change_summary.startswith('Assistant: Muda o título'))
        self.assertIn('Assistant:', history.history_state(self.page)['undo']['label'])


class UndoTurnTest(ChangesTestCase):
    def test_undo_restores_page_settings_menu_and_header(self):
        header = GlobalSection.objects.create(key='main-header', name='Header', section_type='header',
                                              html_template_i18n={'pt': '<header>Velho</header>'})
        self.run_tool('update_element_styles', selector='section[data-section="hero"] > h1:nth-child(1)', new_classes='novo')
        self.run_tool('update_settings', updates={'contact_phone': '+351 912 345 678'})
        created = self.run_tool('create_menu_item', label='Livro', url='/pt/livro/')
        changes.global_section_checkpoint(self.context, header)     # what refine_header does first
        header.html_template_i18n = {'pt': '<header>Novo</header>'}
        header.save()
        index = self.record_turn()

        result = changes.undo_turn(self.session, index, self.user)
        self.assertFalse(result['conflicts'])
        self.page.refresh_from_db()
        self.assertIn('class="a"', self.page.html_content_i18n['pt'])
        self.assertEqual(SiteSettings.load().contact_phone, '+351 289 000 000')
        self.assertFalse(MenuItem.objects.filter(pk=created['menu_item_id']).exists())
        header.refresh_from_db()
        self.assertEqual(header.html_template_i18n['pt'], '<header>Velho</header>')
        self.assertTrue(PageVersion.objects.filter(page=self.page, kind='undo').exists())
        self.session.refresh_from_db()
        self.assertTrue(self.session.messages[index].get('undone'))

    def test_later_edit_is_a_conflict_until_forced(self):
        self.run_tool('update_element_styles', selector='section[data-section="hero"] > h1:nth-child(1)', new_classes='novo')
        index = self.record_turn()
        self.page.refresh_from_db()
        self.page.html_content_i18n = {'pt': self.page.html_content_i18n['pt'].replace('Olá', 'Olá editado')}
        self.page.save()                       # an editor change after the turn

        result = changes.undo_turn(self.session, index, self.user)
        self.assertTrue(result['conflicts'])
        self.page.refresh_from_db()
        self.assertIn('editado', self.page.html_content_i18n['pt'])

        result = changes.undo_turn(self.session, index, self.user, force=True)
        self.assertFalse(result['conflicts'])
        self.page.refresh_from_db()
        self.assertIn('class="a"', self.page.html_content_i18n['pt'])

    def test_deleted_menu_item_comes_back(self):
        item = MenuItem.objects.create(label_i18n={'pt': 'Sobre'}, url='/pt/sobre/', sort_order=3)
        self.run_tool('delete_menu_item', menu_item_id=item.pk)
        index = self.record_turn()
        changes.undo_turn(self.session, index, self.user)
        self.assertTrue(MenuItem.objects.filter(pk=item.pk, url='/pt/sobre/').exists())


class ServiceAndToolTest(ChangesTestCase):
    def test_assistant_reply_stores_its_changes_and_undo_last_change_reverts(self):
        service = AssistantService(self.session)
        router = {'intents': ['settings'], 'needs_active_page': False, 'direct_response': None}
        with mock.patch(ROUTER, return_value=router), \
                mock.patch.object(service.llm, 'get_completion_with_tools',
                                  side_effect=[fc('update_settings', updates={'contact_phone': '+351 999 999 999'}), text('Feito.')]):
            result = service.handle_message('Muda o telefone', user=self.user)
        self.assertEqual(SiteSettings.load().contact_phone, '+351 999 999 999', result['actions'])
        self.assertTrue(result['changes'])
        self.session.refresh_from_db()
        self.assertTrue(self.session.messages[-1]['changes'])

        out = ToolRegistry.execute('undo_last_change', {}, {'session': self.session, 'user': self.user})
        self.assertTrue(out['success'], out)
        self.assertEqual(SiteSettings.load().contact_phone, '+351 289 000 000')

    def test_undo_endpoint(self):
        import json
        self.run_tool('update_settings', updates={'contact_phone': '+351 111 111 111'})
        index = self.record_turn()
        self.client.force_login(self.user)
        res = self.client.post(f'/site-assistant/api/sessions/{self.session.id}/undo/',
                               data=json.dumps({'message_index': index}), content_type='application/json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(SiteSettings.load().contact_phone, '+351 289 000 000')


class ChangeLogShapeTest(ChangesTestCase):
    def test_page_log_keeps_a_fingerprint_not_the_html(self):
        self.run_tool('update_element_styles', selector='section[data-section="hero"] > h1:nth-child(1)', new_classes='novo')
        item = self.tracker.finish()[0]
        self.assertNotIn('Olá', str(item))

    def test_chat_api_returns_changes_and_message_index(self):
        router = {'intents': ['settings'], 'needs_active_page': False, 'direct_response': None}
        self.client.force_login(self.user)
        with mock.patch(ROUTER, return_value=router), \
                mock.patch('djangopress.site_assistant.services.LLMBase.get_completion_with_tools',
                           side_effect=[fc('update_settings', updates={'contact_phone': '+351 222 222 222'}), text('Feito.')]):
            res = self.client.post('/site-assistant/api/chat/', data={'message': 'Muda o telefone',
                                                                       'session_id': self.session.id})
        data = res.json()
        self.assertEqual(data['changes'][0]['kind'], 'object', data)
        self.session.refresh_from_db()
        self.assertTrue(self.session.messages[data['message_index']]['changes'])


class ReviewFixesTest(ChangesTestCase):
    """Findings of the final branch review."""

    def test_reorder_pages_works_inside_a_turn_and_undoes(self):
        other = Page.objects.create(title_i18n={'pt': 'Outra'}, slug_i18n={'pt': 'outra'}, is_active=True, sort_order=5)
        out = self.run_tool('reorder_pages', order=[{'page_id': other.pk, 'sort_order': 0},
                                                   {'page_id': self.page.pk, 'sort_order': 1}])
        self.assertTrue(out['success'], out)
        other.refresh_from_db()
        self.assertEqual(other.sort_order, 0)
        changes.undo_turn(self.session, self.record_turn(), self.user)
        other.refresh_from_db()
        self.assertEqual(other.sort_order, 5)

    def test_missing_checkpoint_is_an_error_not_a_silent_skip(self):
        self.run_tool('update_element_styles', selector='section[data-section="hero"] > h1:nth-child(1)', new_classes='novo')
        index = self.record_turn()
        PageVersion.objects.filter(page=self.page, kind='checkpoint').delete()      # pruned by the version cap
        result = changes.undo_turn(self.session, index, self.user, force=True)
        self.assertIn('too old', result.get('error', ''))
        self.session.refresh_from_db()
        self.assertFalse(self.session.messages[index].get('undone'))

    def test_settings_undo_only_touches_the_fields_the_turn_changed(self):
        self.run_tool('update_settings', updates={'contact_phone': '+351 912 000 000'})
        index = self.record_turn()
        s = SiteSettings.load()
        s.contact_email = 'novo@restaurante.pt'          # an unrelated edit made later
        s.save()
        result = changes.undo_turn(self.session, index, self.user)
        self.assertFalse(result['conflicts'], result)
        s = SiteSettings.objects.get()
        self.assertEqual((s.contact_phone, s.contact_email), ('+351 289 000 000', 'novo@restaurante.pt'))

    def test_settings_snapshot_reads_the_database_not_a_cached_copy(self):
        SiteSettings.load()                                # cache it
        SiteSettings.objects.update(contact_phone='+351 222 000 000')
        self.run_tool('update_settings', updates={'contact_phone': '+351 912 000 000'})
        changes.undo_turn(self.session, self.record_turn(), self.user)
        self.assertEqual(SiteSettings.objects.get().contact_phone, '+351 222 000 000')

    def test_forced_chat_undo_needs_the_user_to_confirm(self):
        self.run_tool('update_settings', updates={'contact_phone': '+351 912 000 000'})
        self.record_turn()
        self.session.add_message('user', 'desfaz isso')
        out = ToolRegistry.execute('undo_last_change', {'force': True}, {'session': self.session, 'user': self.user})
        self.assertFalse(out['success'])
        self.assertIn('confirm', out['message'].lower())
        self.assertEqual(SiteSettings.objects.get().contact_phone, '+351 912 000 000')
        self.session.add_message('user', 'sim, confirmo')
        out = ToolRegistry.execute('undo_last_change', {'force': True}, {'session': self.session, 'user': self.user})
        self.assertTrue(out['success'], out)

    def test_editing_the_last_message_undoes_its_changes_first(self):
        import json
        self.run_tool('update_settings', updates={'contact_phone': '+351 912 000 000'})
        self.record_turn()
        self.client.force_login(self.user)
        router = {'intents': [], 'needs_active_page': False, 'direct_response': 'Ok.'}
        with mock.patch(ROUTER, return_value=router):
            res = self.client.post('/site-assistant/api/chat/', data=json.dumps(
                {'message': 'outra coisa', 'session_id': self.session.id, 'replace_last': True}),
                content_type='application/json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(SiteSettings.objects.get().contact_phone, '+351 289 000 000')

    def test_editing_is_refused_when_its_changes_were_edited_since(self):
        import json
        self.run_tool('update_settings', updates={'contact_phone': '+351 912 000 000'})
        self.record_turn()
        SiteSettings.objects.update(contact_phone='+351 933 000 000')
        self.client.force_login(self.user)
        res = self.client.post('/site-assistant/api/chat/', data=json.dumps(
            {'message': 'outra coisa', 'session_id': self.session.id, 'replace_last': True}),
            content_type='application/json')
        self.assertEqual(res.status_code, 409)
        self.assertEqual(SiteSettings.objects.get().contact_phone, '+351 933 000 000')

    def test_undoing_a_page_delete_restores_its_menu_links(self):
        item = MenuItem.objects.create(label_i18n={'pt': 'Início'}, page=self.page, sort_order=1)
        self.session.add_message('user', 'sim')
        out = self.run_tool('delete_page', page_id=self.page.pk)
        self.assertTrue(out['success'], out)
        result = changes.undo_turn(self.session, self.record_turn(), self.user)
        self.assertTrue(Page.objects.filter(pk=self.page.pk).exists())
        item.refresh_from_db()
        self.assertEqual(item.page_id, self.page.pk)
        self.assertTrue(any('history' in n for n in result['notes']), result)

    def test_undoing_a_form_delete_says_submissions_are_gone(self):
        from djangopress.core.models import DynamicForm, FormSubmission
        DynamicForm.objects.all().delete()
        form = DynamicForm.objects.create(name='Contacto', slug='contacto', fields_schema=[])
        FormSubmission.objects.create(form=form, data={'a': 1})
        self.session.add_message('user', 'sim')
        self.run_tool('delete_form', slug='contacto')
        result = changes.undo_turn(self.session, self.record_turn(), self.user)
        self.assertTrue(DynamicForm.objects.filter(pk=form.pk).exists())
        self.assertTrue(any('submission' in n for n in result['notes']), result)
