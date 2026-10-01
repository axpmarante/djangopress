"""One request, several pages: page tools take a `page`, the prompt carries a
map of every page's sections, and one Undo restores every page touched."""
import re
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from djangopress.core.models import Page, PageVersion, SiteSettings
from djangopress.site_assistant import changes, prompts
from djangopress.site_assistant.models import AssistantSession
from djangopress.site_assistant.services import AssistantService
from djangopress.site_assistant.tool_declarations import build_tool_declarations
from djangopress.site_assistant.tools import ToolRegistry

ROUTER = 'djangopress.site_assistant.services.Router.classify'
GENERATE = 'djangopress.ai.services.ContentGenerationService.generate_section'
TRANSLATE = 'djangopress.editor_v2.ai_apply.translate_snippet'
NEW = '<section data-section="horario" id="horario"><p>PT: horário</p></section>'


def html(names, prefix='PT'):
    return ''.join(f'<section data-section="{n}" id="{n}"><p>{prefix}: {n}</p></section>' for n in names)


def calls(*pairs):
    parts = [SimpleNamespace(function_call=SimpleNamespace(name=n, args=a), text=None) for n, a in pairs]
    return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(role='model', parts=parts))])


def text(t):
    part = SimpleNamespace(function_call=None, text=t)
    return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(role='model', parts=[part]))])


class MultiPageTest(TestCase):
    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        Page.objects.all().delete()
        self.pages = {}
        for title, slug, names in (('Início', 'inicio', ['hero', 'contactos']),
                                   ('Proposta 1', 'proposta-1', ['hero', 'carta', 'contactos']),
                                   ('Proposta 2', 'proposta-2', ['hero', 'manifesto', 'contactos'])):
            self.pages[slug] = Page.objects.create(
                title_i18n={'pt': title, 'en': title}, slug_i18n={'pt': slug, 'en': slug}, is_active=True,
                html_content_i18n={'pt': html(names), 'en': html(names, 'EN')})
        PageVersion.objects.all().delete()
        self.user = get_user_model().objects.create_superuser('a', 'a@x.com', 'pw')
        self.session = AssistantSession.objects.create(created_by=self.user, active_page=self.pages['inicio'])

    def context(self, active='inicio'):
        return {'session': self.session, 'user': self.user,
                'active_page': self.pages[active] if active else None,
                'changes': changes.TurnChanges('Horário nas propostas', self.user)}

    def names(self, slug, lang='pt'):
        self.pages[slug].refresh_from_db()
        return re.findall(r'data-section="([^"]+)"', self.pages[slug].html_content_i18n[lang])

    def insert(self, context, **params):
        with mock.patch(GENERATE, return_value={'options': [{'html': NEW}]}), \
                mock.patch(TRANSLATE, side_effect=lambda h, s, t: h.replace('PT:', 'EN:')):
            return ToolRegistry.execute('insert_section', {'position': 'before', 'anchor_section': 'contactos',
                                                           'instructions': 'horário', **params}, context)

    def test_page_param_by_title_works_on_that_page_and_makes_it_active(self):
        context = self.context()
        out = self.insert(context, page='Proposta 2')
        self.assertTrue(out['success'], out)
        self.assertEqual(self.names('proposta-2'), ['hero', 'manifesto', 'horario', 'contactos'])
        self.assertEqual(self.names('inicio'), ['hero', 'contactos'])
        self.assertEqual(context['active_page'].pk, self.pages['proposta-2'].pk)
        self.session.refresh_from_db()
        self.assertEqual(self.session.active_page_id, self.pages['proposta-2'].pk)
        self.assertTrue(PageVersion.objects.filter(page=self.pages['proposta-2'], kind='checkpoint').exists())

    def test_page_param_by_slug_or_id_and_without_any_active_page(self):
        self.assertTrue(self.insert(self.context(active=None), page='proposta-1')['success'])
        self.assertIn('horario', self.names('proposta-1'))
        out = ToolRegistry.execute('read_section', {'section_name': 'manifesto', 'page': self.pages['proposta-2'].pk},
                                   self.context(active=None))
        self.assertTrue(out['success'], out)

    def test_unknown_page_lists_the_pages(self):
        out = self.insert(self.context(), page='Proposta 9')
        self.assertFalse(out['success'])
        self.assertIn('Proposta 1', out['message'])
        self.assertEqual(self.names('inicio'), ['hero', 'contactos'])

    def test_component_and_photo_tools_take_a_page_too(self):
        out = ToolRegistry.execute('list_components', {'page': 'Proposta 1'}, self.context())
        self.assertTrue(out['success'], out)
        self.assertEqual(out['components'], [])

    def test_declarations_offer_the_page_param(self):
        decls = {d.name: d for d in build_tool_declarations(['page_edit', 'media'])[0].function_declarations}
        for name in ('insert_section', 'read_section', 'update_element_styles', 'reorder_items',
                     'list_components', 'set_section_background', 'remove_section'):
            self.assertIn('page', decls[name].parameters.properties, name)

    def test_prompt_has_a_map_of_every_page_s_sections(self):
        prompt = prompts.build_executor_prompt(self.session, prompts.build_router_snapshot(self.session))
        self.assertIn('Proposta 1: hero, carta, contactos', prompt)
        self.assertIn('Proposta 2: hero, manifesto, contactos', prompt)

    def test_one_turn_on_three_pages_is_one_undo(self):
        service = AssistantService(self.session)
        router = {'intents': ['page_edit'], 'needs_active_page': False, 'direct_response': None}
        step = calls(*[('insert_section', {'page': t, 'position': 'before', 'anchor_section': 'contactos',
                                           'instructions': 'horário'}) for t in ('Início', 'Proposta 1', 'Proposta 2')])
        with mock.patch(ROUTER, return_value=router), \
                mock.patch.object(service.llm, 'get_completion_with_tools', side_effect=[step, text('Feito.')]), \
                mock.patch(GENERATE, return_value={'options': [{'html': NEW}]}), \
                mock.patch(TRANSLATE, side_effect=lambda h, s, t: h.replace('PT:', 'EN:')):
            result = service.handle_message('Horário antes dos contactos em todas as páginas', user=self.user)
        for slug in self.pages:
            self.assertIn('horario', self.names(slug, 'en'), slug)
        self.assertEqual(sorted(c['label'] for c in result['changes']), ['Início', 'Proposta 1', 'Proposta 2'])
        labels = [l['label'] for l in result['links']]
        self.assertIn('View Proposta 1', labels)
        changes.undo_turn(self.session, result['message_index'], self.user)
        for slug in self.pages:
            self.assertNotIn('horario', self.names(slug), slug)
            self.assertNotIn('horario', self.names(slug, 'en'), slug)

    def test_out_of_steps_still_ends_with_the_model_s_summary(self):
        from djangopress.site_assistant import services
        service = AssistantService(self.session)
        router = {'intents': ['page_edit'], 'needs_active_page': False, 'direct_response': None}
        busy = calls(('read_section', {'section_name': 'hero', 'page': 'Início'}))
        replies = [busy] * services.MAX_TOOL_ITERATIONS + [text('Mudei o que pedi. Resumo: nada ficou por fazer.')]
        with mock.patch(ROUTER, return_value=router), \
                mock.patch.object(service.llm, 'get_completion_with_tools', side_effect=replies) as llm:
            result = service.handle_message('Lê tudo', user=self.user)
        self.assertEqual(result['response'], 'Mudei o que pedi. Resumo: nada ficou por fazer.')
        self.assertIsNone(llm.call_args.kwargs['tools'])          # the last call can't call tools

    def test_out_of_steps_falls_back_to_the_report_when_the_summary_fails(self):
        from djangopress.site_assistant import services
        service = AssistantService(self.session)
        router = {'intents': ['page_edit'], 'needs_active_page': False, 'direct_response': None}
        busy = calls(('read_section', {'section_name': 'hero', 'page': 'Início'}))
        replies = [busy] * services.MAX_TOOL_ITERATIONS + [RuntimeError('quota')]
        with mock.patch(ROUTER, return_value=router), \
                mock.patch.object(service.llm, 'get_completion_with_tools', side_effect=replies):
            result = service.handle_message('Lê tudo', user=self.user)
        self.assertIn('ran out of steps', result['response'])
