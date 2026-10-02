"""A new section can start from a given version: refining one of the three options
(it used to be dropped, so "refine" made a new section from scratch), and fitting a
section pasted from another site to this site's design."""
from unittest import mock

from django.test import TestCase

from djangopress.ai import directions
from djangopress.ai.utils.prompts import PromptTemplates
from djangopress.core.models import Page, SiteSettings
from djangopress.editor_v2 import chat

BASE = '<section data-section="visitas" id="visitas"><h2 class="font-[\'Cormorant\'] text-[#2F5D3A]">Visitas</h2></section>'
SERVICE = 'djangopress.ai.services.ContentGenerationService'


def prompt(**kwargs):
    return PromptTemplates.get_section_generation_prompt(
        site_name='S', site_description='', project_briefing='', default_language='pt', full_page_html='<section></section>',
        insert_after='hero', user_request='x', direction={'name': 'D', 'brief': 'b'}, **kwargs)


class PromptTest(TestCase):
    def test_the_version_to_work_on_is_in_the_prompt(self):
        _system, user = prompt(base_html=BASE)
        self.assertIn(BASE, user)
        self.assertLess(user.index(BASE), user.index('# USER REQUEST'))

    def test_without_a_version_the_prompt_is_unchanged(self):
        self.assertEqual(prompt(), prompt(base_html=None))

    def test_a_pasted_section_keeps_its_image_addresses(self):
        system, _user = prompt(base_html=BASE)
        self.assertIn('Keep every image', system)


class Base(TestCase):
    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}]
        s.default_language = 'pt'
        s.save()
        self.page = Page.objects.create(title_i18n={'pt': 'Início'}, slug_i18n={'pt': 'inicio'}, is_active=True,
                                        html_content_i18n={'pt': '<section data-section="hero" id="hero"><h2>Olá</h2></section>'})


class DirectionsTest(Base):
    def test_a_new_section_refine_gets_its_version(self):
        with mock.patch(f'{SERVICE}.generate_section', return_value={'options': [{'html': BASE}]}) as gen, \
                mock.patch(f'{SERVICE}.__init__', return_value=None):
            directions.generate_directions(self.page, 'new', 'hero', 'mais escuro', lang='pt', base_html=BASE,
                                           directions=[directions.REFINED], context={})
        self.assertEqual(gen.call_args.kwargs['base_html'], BASE)


class FitTurnTest(Base):
    def test_fit_mode_runs_the_fit_direction_on_the_pasted_html(self):
        events = []
        with mock.patch.object(chat, 'generate_directions', return_value=[{'key': 'fit', 'name': 'x', 'html': BASE}]) as gen, \
                mock.patch.object(chat, 'build_design_context', return_value={}), \
                mock.patch.object(chat, 'matches_summary', return_value={}):
            result = chat.run_turn(self.page, scope='new', target='hero', instructions='Fit this section to this site',
                                   mode='fit', lang='pt', base_html=BASE, emit=lambda e, d: events.append((e, d)))
        self.assertEqual(gen.call_args.kwargs['directions'], [directions.FIT])
        self.assertEqual(gen.call_args.kwargs['base_html'], BASE)
        self.assertEqual(result['mode'], 'fit')
        self.assertIn(('step', {'key': 'fit', 'label': "Fitting it to this site's design", 'state': 'running'}), events)
