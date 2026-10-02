"""Generating a new page or news post uses the latest pipeline: the site's design
context (the home page for a page, the latest post for news), the design check
and the Flash model. The bulk news planner runs on Flash too."""
import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from djangopress.ai import directions
from djangopress.core.models import Page, SiteSettings
from djangopress.news.models import NewsPost

HOME = ('<section data-section="hero" id="hero"><h2 class="text-[44px] font-light">Olá</h2></section>'
        '<section data-section="sobre" id="sobre"><h2 class="text-[44px] font-light">Sobre nós</h2></section>')
POST = '<section data-section="artigo-corpo" id="artigo-corpo"><h2 class="text-[32px] font-normal">Notícia</h2></section>'
OUT = ('<section data-section="servicos" id="servicos">'
       '<h2 class="text-[60px] font-bold bg-blue-600">Serviços</h2></section>')
SERVICE = 'djangopress.ai.services.ContentGenerationService'
GENERATED = {'html_content_i18n': {'pt': OUT}, 'title_i18n': {'pt': 'Serviços'}, 'slug_i18n': {'pt': 'servicos'}}


class Base(TestCase):
    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}]
        s.default_language = 'pt'
        s.primary_color = '#C42014'
        s.save()
        self.home = Page.objects.create(title_i18n={'pt': 'Início'}, slug_i18n={'pt': 'inicio'}, is_active=True,
                                        html_content_i18n={'pt': HOME})
        s.homepage = self.home
        s.save()
        self.user = get_user_model().objects.create_superuser('a', 'a@x.com', 'pw')

    def generate(self, **kwargs):
        with mock.patch(f'{SERVICE}.generate_page', return_value=json.loads(json.dumps(GENERATED))) as gen, \
                mock.patch(f'{SERVICE}.__init__', return_value=None) as init:
            result = directions.generate_page_in_style('Uma página de serviços', language='pt', **kwargs)
        return result, gen, init


class PageGenerationTest(Base):
    def test_a_new_page_gets_the_site_context_from_the_home_page(self):
        _result, gen, _init = self.generate()
        context = gen.call_args.kwargs['design_context']
        self.assertIn('## Site design', context)
        self.assertIn('Sobre nós', context)
        self.assertIn('h2: font-light', context)

    def test_a_new_page_runs_on_flash(self):
        _result, gen, init = self.generate()
        self.assertEqual(init.call_args.kwargs['model_name'], 'gemini-flash')
        self.assertEqual(gen.call_args.kwargs['model_override'], 'gemini-flash')

    def test_the_generated_page_goes_through_the_design_check(self):
        result, _gen, _init = self.generate()
        self.assertIn('<h2 class="text-[44px] font-light bg-[#C42014]">Serviços</h2>', result['html_content_i18n']['pt'])
        self.assertTrue(result['notes'])
        self.assertEqual(result['title_i18n'], {'pt': 'Serviços'})

    def test_the_brief_outline_and_images_reach_the_generator(self):
        outline = [{'id': 'servicos', 'title': 'Serviços'}]
        _result, gen, _init = self.generate(outline=outline, reference_images=[{'bytes': b'x', 'mime_type': 'image/png'}])
        self.assertEqual(gen.call_args.kwargs['brief'], 'Uma página de serviços')
        self.assertEqual(gen.call_args.kwargs['outline'], outline)
        self.assertEqual(len(gen.call_args.kwargs['reference_images']), 1)


class NewsGenerationTest(Base):
    def test_a_news_post_follows_the_latest_post(self):
        NewsPost.objects.create(title_i18n={'pt': 'Antiga'}, slug_i18n={'pt': 'antiga'}, html_content_i18n={'pt': POST})
        _result, gen, _init = self.generate(kind='news')
        context = gen.call_args.kwargs['design_context']
        self.assertIn('Artigo Corpo', context)
        self.assertIn('h2: font-normal', context)

    def test_the_first_news_post_follows_the_home_page(self):
        _result, gen, _init = self.generate(kind='news')
        self.assertIn('Sobre nós', gen.call_args.kwargs['design_context'])


class PromptTest(TestCase):
    def test_the_generation_prompt_carries_the_design_context(self):
        from djangopress.ai.utils.prompts import PromptTemplates
        _system, user = PromptTemplates.get_page_generation_html_prompt(
            site_name='S', site_description='', project_briefing='', default_language='pt', brief='x',
            design_context='## Site design\nMARK')
        self.assertIn('MARK', user)
        self.assertLess(user.index('MARK'), user.index('# PAGE REQUEST'))

    def test_the_service_passes_the_context_to_the_prompt(self):
        from djangopress.ai.services import ContentGenerationService
        from djangopress.ai.utils.prompts import PromptTemplates
        service = ContentGenerationService.__new__(ContentGenerationService)
        service.model_name = 'gemini-flash'
        with mock.patch.object(PromptTemplates, 'get_page_generation_html_prompt',
                               side_effect=RuntimeError('stop')) as prompt, \
                mock.patch('djangopress.ai.services.ComponentRegistry.select_components', return_value=[]), \
                mock.patch('djangopress.ai.services.ComponentRegistry.get_references', return_value=''):
            service.llm = mock.Mock()
            with self.assertRaises(RuntimeError):
                service.generate_page(brief='x', design_context='CTX')
        self.assertEqual(prompt.call_args.kwargs['design_context'], 'CTX')


class EndpointsTest(Base):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def stream(self, url, kind):
        with mock.patch.object(directions, 'generate_page_in_style', return_value=GENERATED) as helper:
            response = self.client.post(url, {'brief': 'Uma página de serviços'})
            body = b''.join(response.streaming_content).decode()
        self.assertEqual(helper.call_args.kwargs['kind'], kind)
        self.assertEqual(helper.call_args.kwargs['brief'], 'Uma página de serviços')
        self.assertIn('"slug_i18n": {"pt": "servicos"}', body)

    def test_the_page_screen_uses_the_latest_pipeline(self):
        self.stream('/ai/api/generate-page/stream/', 'page')

    def test_the_news_screen_uses_the_latest_pipeline(self):
        self.stream('/ai/api/generate-news-post/stream/', 'news')

    def test_the_bulk_news_planner_runs_on_flash(self):
        reply = mock.Mock()
        reply.choices = [mock.Mock(message=mock.Mock(content='{"pages": []}'))]
        reply.usage = None
        with mock.patch('djangopress.ai.utils.llm_config.LLMBase.get_completion', return_value=reply) as call, \
                mock.patch('djangopress.ai.utils.llm_config.LLMBase.__init__', return_value=None):
            self.client.post('/ai/api/analyze-bulk-pages/', json.dumps({'description': 'Três notícias'}),
                             content_type='application/json')
        self.assertEqual(call.call_args.kwargs['tool_name'], 'gemini-flash')


class FormsInContextTest(TestCase):
    """The component index suggests generic slugs (quote-request, booking); a form posting to one the site lacks
    fails validation and costs the whole generation. The context names the site's real forms."""

    def render(self):
        from djangopress.ai.design_context import build_design_context, render_design_context
        return render_design_context(build_design_context(None, lang='pt'))

    def test_the_context_lists_the_site_forms(self):
        from djangopress.core.models import DynamicForm
        DynamicForm.objects.create(name='Reserva', slug='reserva')
        DynamicForm.objects.create(name='Antigo', slug='antigo', is_active=False)
        text = self.render()
        self.assertIn('/forms/reserva/submit/', text)
        self.assertNotIn('antigo', text)

    def test_a_site_without_forms_says_so(self):
        from djangopress.core.models import DynamicForm
        DynamicForm.objects.all().delete()   # a migration seeds a contact form
        self.assertIn('This site has no forms', self.render())
