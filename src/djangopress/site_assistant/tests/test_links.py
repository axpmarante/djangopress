"""Each assistant reply carries buttons: the pages it worked on or talks about
(view / edit) and the backoffice screens it sends the user to."""
import json
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from djangopress.core.models import DynamicForm, Page, SiteSettings
from djangopress.site_assistant import links
from djangopress.site_assistant.models import AssistantSession

ROUTER = 'djangopress.site_assistant.services.Router.classify'
HTML = '<section data-section="hero" id="hero"><h1 class="a">Olá</h1></section><section data-section="livro" id="livro"></section>'


def fc(name, **args):
    part = SimpleNamespace(function_call=SimpleNamespace(name=name, args=args), text=None)
    return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(role='model', parts=[part]))])


def text(t):
    part = SimpleNamespace(function_call=None, text=t)
    return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(role='model', parts=[part]))])


class LinksTest(TestCase):
    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        Page.objects.all().delete()
        self.home = Page.objects.create(title_i18n={'pt': 'Início', 'en': 'Home'}, slug_i18n={'pt': 'inicio', 'en': 'home'},
                                        is_active=True, html_content_i18n={'pt': HTML, 'en': HTML})
        self.book = Page.objects.create(title_i18n={'pt': 'Reservas', 'en': 'Bookings'},
                                        slug_i18n={'pt': 'reservas', 'en': 'bookings'}, is_active=False,
                                        html_content_i18n={'pt': HTML})
        self.user = get_user_model().objects.create_superuser('a', 'a@x.com', 'pw')
        self.session = AssistantSession.objects.create(created_by=self.user, active_page=self.home)

    def by_label(self, out):
        return {l['label']: l['url'] for l in out}

    def test_a_page_the_turn_changed_gets_view_at_the_section_and_edit(self):
        out = self.by_label(links.build_links('Feito.', [], touched={self.home.pk: 'livro'}))
        view = out['View Início']
        self.assertTrue(view.endswith('#livro'), view)
        self.assertIn('edit=v2', out['Edit Início'])

    def test_an_inactive_page_links_to_its_preview(self):
        out = self.by_label(links.build_links('Feito.', [], touched={self.book.pk: None}))
        self.assertIn('preview=true', out['View Reservas'])

    def test_a_page_named_in_bold_or_after_pagina_gets_buttons(self):
        out = self.by_label(links.build_links('A secção ficou na página Reservas e também na **Início**.', []))
        self.assertIn('View Reservas', out)
        self.assertIn('View Início', out)

    def test_a_page_title_in_plain_text_is_not_enough(self):
        out = self.by_label(links.build_links('As reservas de grupos têm FAQ.', []))
        self.assertEqual(out, {})

    def test_pages_the_tools_looked_at(self):
        actions = [{'tool': 'get_page_info', 'success': True, 'params': {'page_id': self.book.pk}}]
        self.assertIn('View Reservas', self.by_label(links.build_links('Tem 2 secções.', actions)))

    def test_backoffice_paths_become_named_buttons_and_unknown_ones_are_ignored(self):
        out = self.by_label(links.build_links(
            'Carregue a imagem em /backoffice/media/ e reveja /backoffice/settings/header/. Ignore /backoffice/nada/.', []))
        self.assertEqual(out['Media library'], '/backoffice/media/')
        self.assertEqual(out['Edit header'], '/backoffice/settings/header/')
        self.assertEqual(len(out), 2)

    def test_form_tools_link_the_form_and_its_submissions(self):
        DynamicForm.objects.all().delete()
        form = DynamicForm.objects.create(name='Reserva', slug='reserva', fields_schema=[])
        actions = [{'tool': 'test_form', 'success': True, 'params': {'slug': 'reserva'}}]
        out = self.by_label(links.build_links('Testado.', actions))
        self.assertEqual(out['Form Reserva'], f'/backoffice/forms/{form.pk}/edit/')
        self.assertEqual(out['Reserva submissions'], f'/backoffice/forms/{form.pk}/submissions/')

    def test_contacts_check_links_the_contact_settings(self):
        actions = [{'tool': 'validate_contacts', 'success': True, 'params': {}}]
        self.assertIn('Contact settings', self.by_label(links.build_links('1 inconsistência.', actions)))

    def test_no_duplicates(self):
        actions = [{'tool': 'get_page_info', 'success': True, 'params': {'page_id': self.home.pk}}]
        out = links.build_links('Na página **Início**. Veja /backoffice/media/ e /backoffice/media/.', actions,
                                touched={self.home.pk: 'hero'})
        labels = [l['label'] for l in out]
        self.assertEqual(len(labels), len(set(labels)))

    def test_chat_reply_carries_and_stores_the_links(self):
        router = {'intents': ['page_edit'], 'needs_active_page': True, 'direct_response': None}
        self.client.force_login(self.user)
        with mock.patch(ROUTER, return_value=router), \
                mock.patch('djangopress.site_assistant.services.LLMBase.get_completion_with_tools',
                           side_effect=[fc('update_element_styles', section_name='livro', add_classes='py-24'),
                                        text('Pronto. Para a capa, carregue a imagem em /backoffice/media/.')]):
            res = self.client.post('/site-assistant/api/chat/', data=json.dumps(
                {'message': 'Mais espaço no livro', 'session_id': self.session.id}), content_type='application/json')
        data = res.json()
        labels = {l['label']: l['url'] for l in data['links']}
        self.assertTrue(labels['View Início'].endswith('#livro'), labels)
        self.assertIn('Media library', labels)
        self.session.refresh_from_db()
        self.assertEqual(self.session.messages[-1]['links'], data['links'])

    def test_older_replies_get_links_when_the_conversation_is_opened(self):
        self.session.add_message('user', 'onde carrego imagens?')
        self.session.add_message('assistant', 'Na página **Reservas**, carregue em /backoffice/media/.')
        self.client.force_login(self.user)
        data = self.client.get(f'/site-assistant/api/sessions/{self.session.id}/').json()
        labels = [l['label'] for l in data['session']['messages'][-1]['links']]
        self.assertEqual(labels, ['View Reservas', 'Edit Reservas', 'Media library'])
        self.session.refresh_from_db()
        self.assertNotIn('links', self.session.messages[-1])        # computed on read, not stored

    def test_prompt_says_page_html_is_one_language(self):
        from djangopress.site_assistant import prompts
        prompt = prompts.build_executor_prompt(self.session, prompts.build_router_snapshot(self.session))
        self.assertNotIn('provide values for ALL enabled languages', prompt)
        self.assertIn('ONE language', prompt)
