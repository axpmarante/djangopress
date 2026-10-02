"""Three design directions, each its own generation call with the site's design
context; a follow-up can start from an option that was never applied; news
posts work as well as pages."""
import threading
from unittest import mock

from django.test import TestCase

from djangopress.ai import directions
from djangopress.ai.models import AICallLog
from djangopress.ai.services import ContentGenerationService
from djangopress.ai.utils.llm_config import StandardizedLLMResponse
from djangopress.ai.utils.prompts import PromptTemplates
from djangopress.core.models import Page, SiteSettings

CTX = {'colors': [{'name': 'Primary', 'value': '#C42014'}], 'fonts': [{'role': 'Headings', 'family': 'Fraunces'}],
       'design_guide': '', 'references': [], 'vocabulary': [], 'images': []}
STORED = '<section data-section="sala" id="sala"><h2>Sala antiga</h2><p>texto guardado</p></section>'
BASE = '<section data-section="sala" id="sala"><h2>Sala nova</h2><p>opção B por aplicar</p></section>'


def reply(text):
    return StandardizedLLMResponse(content=text, usage={'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2},
                                   finish_reason='STOP')


def section_prompt(**kw):
    args = dict(site_name='S', site_description='', project_briefing='', default_language='pt',
                full_page_html=STORED, section_name='sala', user_request='Mais elegante')
    args.update(kw)
    return PromptTemplates.get_section_refinement_prompt(**args)


class PromptTest(TestCase):
    def test_direction_and_design_context_reach_the_prompt(self):
        system, user = section_prompt(direction={'name': 'Bolder', 'brief': 'Stronger contrast.'},
                                      design_context='## Site design\nPALETTE-MARK')
        both = system + user
        self.assertIn('## Direction', both)
        self.assertIn('Stronger contrast.', both)
        self.assertIn('<!-- WHY:', both)
        self.assertIn('PALETTE-MARK', user)
        self.assertNotIn('Keep output concise', both)
        self.assertNotIn('OPTION_1', both)

    def test_without_direction_the_three_option_prompt_is_unchanged(self):
        system, _user = section_prompt(multi_option=True)
        self.assertIn('OPTION_1', system)
        self.assertNotIn('## Direction', system)

    def test_element_prompt_takes_both_too(self):
        system, user = PromptTemplates.get_element_refinement_prompt(
            site_name='S', site_description='', project_briefing='', default_language='pt', section_html=STORED,
            section_name='sala', element_html='<h2 data-target="true">x</h2>', user_request='r',
            direction={'name': 'Close to current', 'brief': 'Raise the craft.'}, design_context='## Site design\nX')
        self.assertIn('Raise the craft.', system + user)
        self.assertIn('## Site design', user)


class ServiceTest(TestCase):
    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}]
        s.default_language = 'pt'
        s.save()
        self.page = Page.objects.create(title_i18n={'pt': 'Casa'}, slug_i18n={'pt': 'casa'}, is_active=True,
                                        html_content_i18n={'pt': STORED})

    def run_section(self, page, **kw):
        service = ContentGenerationService(model_name='gemini-flash')
        with mock.patch.object(service.llm, 'get_completion', return_value=reply(BASE)) as call:
            result = service.refine_section_only(page_id=getattr(page, 'pk', None), section_name='sala',
                                                 instructions='Fundo escuro', lang='pt', page=page,
                                                 skip_component_selection=True, **kw)
        return result, call.call_args.args[0][1]['content']

    def test_base_html_replaces_the_stored_section_in_the_prompt(self):
        _result, user_prompt = self.run_section(self.page, base_html=BASE)
        self.assertIn('opção B por aplicar', user_prompt)
        self.assertNotIn('texto guardado', user_prompt)

    def test_a_news_post_is_used_as_given_and_logged_without_a_page(self):
        from djangopress.news.models import NewsPost
        post = NewsPost.objects.create(title_i18n={'pt': 'Notícia'}, slug_i18n={'pt': 'noticia'},
                                       html_content_i18n={'pt': STORED})
        with mock.patch.object(Page.objects, 'get', side_effect=AssertionError('no Page lookup')):
            result, _prompt = self.run_section(post)
        self.assertIn('Sala nova', result['options'][0]['html'])
        log = AICallLog.objects.filter(action='refine_section').latest('created_at')
        self.assertIsNone(log.page)

    def test_element_base_html_replaces_the_element(self):
        service = ContentGenerationService(model_name='gemini-flash')
        with mock.patch.object(service.llm, 'get_completion',
                               return_value=reply('<h2 data-target="true">Novo</h2>')) as call:
            service.refine_element_only(page_id=self.page.pk, selector='section[data-section="sala"] > h2',
                                        instructions='r', lang='pt', page=self.page, skip_component_selection=True,
                                        base_html='<h2 class="text-5xl">Ainda não aplicado</h2>')
        prompt = call.call_args.args[0][1]['content']
        self.assertIn('Ainda não aplicado', prompt)
        self.assertNotIn('Sala antiga', prompt)


class DirectionsTest(TestCase):
    def setUp(self):
        self.page = Page.objects.create(title_i18n={'pt': 'Casa'}, slug_i18n={'pt': 'casa'}, is_active=True,
                                        html_content_i18n={'pt': STORED})

    def run_directions(self, side_effect, **kw):
        with mock.patch.object(directions, 'ContentGenerationService') as cls:
            cls.return_value.refine_section_only.side_effect = side_effect
            got = []
            result = directions.generate_directions(self.page, 'section', 'sala', 'Mais elegante', lang='pt',
                                                    context=CTX, on_option=got.append, **kw)
        return result, got, cls.return_value.refine_section_only

    def test_three_calls_one_per_direction_with_the_same_context(self):
        def gen(**kw):
            return {'options': [{'html': f'<section data-section="sala"><!-- WHY: {kw["direction"]["name"]} fits. -->'
                                         f'<a class="bg-blue-600">x</a></section>'}]}
        result, got, call = self.run_directions(gen)
        self.assertEqual(call.call_count, 3)
        briefs = {c.kwargs['direction']['brief'] for c in call.call_args_list}
        self.assertEqual(len(briefs), 3)
        self.assertEqual({c.kwargs['design_context'] for c in call.call_args_list},
                         {directions.render_design_context(CTX)})
        self.assertEqual([r['key'] for r in result], ['refined', 'bold', 'layout'])
        self.assertEqual(len(got), 3)
        self.assertEqual(result[1]['why'], 'Bolder fits.')
        self.assertIn('bg-[#C42014]', result[1]['html'])          # design check applied
        self.assertNotIn('WHY', result[1]['html'])

    def test_one_failure_keeps_the_other_two(self):
        def gen(**kw):
            if kw['direction']['name'] == 'Bolder':
                raise ValueError('bad html')
            return {'options': [{'html': '<section data-section="sala"><p>ok</p></section>'}]}
        result, got, _call = self.run_directions(gen)
        self.assertEqual(result[1], {'key': 'bold', 'name': 'Bolder', 'error': 'bad html'})
        self.assertIn('ok', result[0]['html'])
        self.assertIn('ok', result[2]['html'])
        self.assertEqual(len(got), 3)

    def test_base_html_and_images_are_passed(self):
        images = [{'bytes': b'x', 'mime_type': 'image/png'}]
        _r, _g, call = self.run_directions(lambda **kw: {'options': [{'html': '<section><p>x</p></section>'}]},
                                           base_html=BASE, images=images)
        self.assertTrue(all(c.kwargs['base_html'] == BASE for c in call.call_args_list))
        self.assertTrue(all(c.kwargs['reference_images'] == images for c in call.call_args_list))
        self.assertTrue(all(c.kwargs['page'] is self.page for c in call.call_args_list))

    def test_cancel_stops_further_options(self):
        first_done = threading.Event()
        cancelled = {'v': False}

        def gen(**kw):
            if kw['direction']['name'] != 'Close to current':
                first_done.wait(2)
            return {'options': [{'html': '<section><p>x</p></section>'}]}

        def on_option(item):
            got.append(item)
            cancelled['v'] = True
            first_done.set()

        got = []
        with mock.patch.object(directions, 'ContentGenerationService') as cls:
            cls.return_value.refine_section_only.side_effect = gen
            result = directions.generate_directions(self.page, 'section', 'sala', 'x', lang='pt', context=CTX,
                                                    on_option=on_option, is_cancelled=lambda: cancelled['v'])
        self.assertEqual(len(got), 1)
        self.assertEqual(len([r for r in result if 'html' in r]), 1)

    def test_only_some_keys(self):
        _r, _g, call = self.run_directions(lambda **kw: {'options': [{'html': '<section><p>x</p></section>'}]},
                                           keys=['bold'])
        self.assertEqual(call.call_count, 1)

    def test_element_scope_uses_the_element_service(self):
        with mock.patch.object(directions, 'ContentGenerationService') as cls:
            cls.return_value.refine_element_only.return_value = {'options': [{'html': '<a>x</a>'}]}
            result = directions.generate_directions(self.page, 'element', 'section > a', 'x', lang='pt', context=CTX)
        self.assertEqual(cls.return_value.refine_element_only.call_count, 3)
        self.assertEqual(cls.return_value.refine_element_only.call_args.kwargs['selector'], 'section > a')
        self.assertEqual(result[0]['html'], '<a>x</a>')


class DeadlineTest(TestCase):
    def setUp(self):
        self.page = Page.objects.create(title_i18n={'pt': 'Casa'}, slug_i18n={'pt': 'casa'}, is_active=True,
                                        html_content_i18n={'pt': STORED})

    def test_directions_still_running_at_the_deadline_are_reported_and_the_rest_kept(self):
        release = threading.Event()

        def gen(**kw):
            if kw['direction']['name'] == 'Bolder':
                release.wait(5)
            return {'options': [{'html': '<section data-section="sala"><p>ok</p></section>'}]}

        got = []
        with mock.patch.object(directions, 'ContentGenerationService') as cls, \
                mock.patch.object(directions, 'DEADLINE_SECONDS', 0.6):
            cls.return_value.refine_section_only.side_effect = gen
            result = directions.generate_directions(self.page, 'section', 'sala', 'x', lang='pt', context=CTX,
                                                    on_option=got.append)
        release.set()
        self.assertEqual([r['key'] for r in result], ['refined', 'bold', 'layout'])
        self.assertIn('too long', result[1]['error'])
        self.assertIn('html', result[0])
        self.assertEqual(len(got), 3)
