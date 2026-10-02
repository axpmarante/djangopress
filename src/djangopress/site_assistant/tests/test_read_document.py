"""read_document: the assistant reads a PDF (or image) that is already on the site."""
from types import SimpleNamespace
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings

from djangopress.core.models import Page, SiteImage, SiteSettings
from djangopress.site_assistant import changes
from djangopress.site_assistant.models import AssistantSession
from djangopress.site_assistant.services import AssistantService
from djangopress.site_assistant.tool_declarations import build_tool_declarations
from djangopress.site_assistant.tools import ToolRegistry

ROUTER = 'djangopress.site_assistant.services.Router.classify'
PDF = b'%PDF-1.4\n% menu\n' + b'0' * 64
IN_MEMORY = {**settings.STORAGES, 'default': {'BACKEND': 'django.core.files.storage.InMemoryStorage'}}


def fc_response(name, args):
    part = SimpleNamespace(function_call=SimpleNamespace(name=name, args=args), text=None)
    return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(role='model', parts=[part]))])


def text_response(text):
    part = SimpleNamespace(function_call=None, text=text)
    return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(role='model', parts=[part]))])


@override_settings(STORAGES=IN_MEMORY)
class ReadDocumentToolTest(TestCase):
    def setUp(self):
        SiteSettings.load()
        self.doc = SiteImage(title_i18n={'pt': 'Menu PT'}, key='menu-pdf-pt', file_type='document')
        self.doc.file.save('menu-pt.pdf', ContentFile(PDF), save=True)
        self.context = {'reference_images': None}

    def read(self, **params):
        return ToolRegistry.execute('read_document', params, self.context)

    def test_by_id_attaches_the_file(self):
        out = self.read(file_id=self.doc.pk)
        self.assertTrue(out['success'], out)
        self.assertEqual(self.context['reference_images'], [{'bytes': PDF, 'mime_type': 'application/pdf'}])
        self.assertEqual(self.context['new_attachments'], self.context['reference_images'])
        self.assertNotIn('bytes', str(out))

    def test_by_its_url(self):
        out = self.read(url=self.doc.url + '?v=2')
        self.assertTrue(out['success'], out)
        self.assertEqual(self.context['reference_images'][0]['bytes'], PDF)

    def test_a_file_in_storage_but_not_in_the_library(self):
        name = default_storage.save('site_files/lista.pdf', ContentFile(PDF))
        out = self.read(url=default_storage.url(name))
        self.assertTrue(out['success'], out)

    def test_a_url_outside_the_site_is_refused_without_fetching(self):
        with mock.patch('urllib.request.urlopen') as urlopen:
            out = self.read(url='https://example.com/menu.pdf')
        self.assertFalse(out['success'])
        self.assertIn('attach', out['message'])
        urlopen.assert_not_called()
        self.assertIsNone(self.context['reference_images'])

    def test_unknown_id(self):
        self.assertFalse(self.read(file_id=999)['success'])

    def test_too_big(self):
        with mock.patch('djangopress.site_assistant.documents.MAX_BYTES', 10):
            out = self.read(file_id=self.doc.pk)
        self.assertFalse(out['success'])
        self.assertIn('MB', out['message'])

    def test_a_library_row_whose_file_is_gone(self):
        default_storage.delete(self.doc.file.name)
        out = self.read(file_id=self.doc.pk)
        self.assertFalse(out['success'])
        self.assertIn('attach', out['message'])

    def test_other_file_types_are_refused(self):
        name = default_storage.save('site_files/tabela.xlsx', ContentFile(b'PK'))
        self.assertFalse(self.read(url=default_storage.url(name))['success'])

    def test_keeps_files_already_attached(self):
        self.context['reference_images'] = [{'bytes': b'png', 'mime_type': 'image/png'}]
        self.read(file_id=self.doc.pk)
        self.assertEqual(len(self.context['reference_images']), 2)
        self.assertEqual(len(self.context['new_attachments']), 1)

    def test_list_images_says_which_are_documents(self):
        out = ToolRegistry.execute('list_images', {}, {})
        self.assertEqual(out['images'][0]['file_type'], 'document')

    def test_always_available(self):
        names = [d.name for d in build_tool_declarations(['pages'])[0].function_declarations]
        self.assertIn('read_document', names)


@override_settings(STORAGES=IN_MEMORY)
class ReadDocumentLoopTest(TestCase):
    def setUp(self):
        SiteSettings.load()
        self.user = get_user_model().objects.create_superuser('a', 'a@x.com', 'pw')
        self.session = AssistantSession.objects.create(created_by=self.user)
        self.doc = SiteImage(title_i18n={'pt': 'Menu PT'}, key='menu-pdf-pt', file_type='document')
        self.doc.file.save('menu-pt.pdf', ContentFile(PDF), save=True)

    def test_the_model_sees_the_document_after_reading_it(self):
        service = AssistantService(self.session)
        router = {'intents': ['media'], 'needs_active_page': False, 'direct_response': None}
        replies = [fc_response('read_document', {'file_id': self.doc.pk}), text_response('Li o menu.')]
        with mock.patch(ROUTER, return_value=router), \
                mock.patch.object(service.llm, 'get_completion_with_tools', side_effect=replies) as llm:
            service.handle_message('Lê o menu em PDF', user=self.user)
        tool_turn = llm.call_args.kwargs['contents'][-1]
        kinds = ['call' if getattr(p, 'function_response', None) else
                 'file' if getattr(p, 'inline_data', None) else 'text' for p in tool_turn.parts]
        self.assertEqual(kinds, ['call', 'file'])
        self.assertEqual(tool_turn.parts[1].inline_data.mime_type, 'application/pdf')
        self.assertIn('read_document', llm.call_args.kwargs['system_instruction'])


class InsertSectionGetsTheDocumentTest(TestCase):
    def test_attachments_reach_the_new_section_model(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}]
        s.default_language = 'pt'
        s.save()
        page = Page.objects.create(title_i18n={'pt': 'Menu'}, slug_i18n={'pt': 'menu'}, is_active=True,
                                   html_content_i18n={'pt': ''})
        user = get_user_model().objects.create_superuser('a', 'a@x.com', 'pw')
        files = [{'bytes': PDF, 'mime_type': 'application/pdf'}]
        context = {'session': mock.Mock(active_page_id=page.id), 'user': user, 'active_page': page,
                   'changes': changes.TurnChanges('Cria o menu', user), 'reference_images': files}
        new = '<section data-section="menu" id="menu"><h2>Entradas</h2></section>'
        with mock.patch('djangopress.ai.services.ContentGenerationService.generate_section',
                        return_value={'options': [{'html': new}], 'assistant_message': ''}) as gen:
            out = ToolRegistry.execute('insert_section', {'instructions': 'O menu inteiro'}, context)
        self.assertTrue(out['success'], out)
        self.assertEqual(gen.call_args.kwargs['reference_images'], files)


class SectionPromptMentionsDocumentsTest(TestCase):
    def test_generate_section_prompt_uses_document_content(self):
        from djangopress.ai.utils.prompts import PromptTemplates
        system, _ = PromptTemplates.get_section_generation_prompt(
            site_name='X', site_description='', project_briefing='', default_language='pt', full_page_html='',
            insert_after=None, user_request='menu', has_reference_images=True)
        self.assertIn('every item', system)
