"""Site-wide restyles: find_elements groups matching elements by their classes
across every page (and header/footer); restyle_elements changes them all in
one call, in every language, with one Undo."""
from unittest import mock

from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from django.test import TestCase

from djangopress.core.models import GlobalSection, Page, PageVersion, SiteSettings
from djangopress.site_assistant import changes
from djangopress.site_assistant.models import AssistantSession
from djangopress.site_assistant.tools import ToolRegistry

BTN = 'inline-flex px-6 py-3 bg-[#6B1712] text-white'
GHOST = 'inline-flex px-6 py-3 border border-black'


def page_html(prefix):
    return (f'<section data-section="hero" id="hero"><h1>{prefix} Olá</h1><a class="{BTN}" href="/r/">{prefix} Reservar</a>'
            f'<a class="{GHOST}" href="/c/">{prefix} Carta</a></section>'
            f'<section data-section="contactos" id="contactos"><button class="{BTN}">{prefix} Enviar</button></section>')


class SiteStylesTest(TestCase):
    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        Page.objects.all().delete()
        self.a = Page.objects.create(title_i18n={'pt': 'Início'}, slug_i18n={'pt': 'inicio'}, is_active=True,
                                     html_content_i18n={'pt': page_html('PT'), 'en': page_html('EN')})
        self.b = Page.objects.create(title_i18n={'pt': 'Reservas'}, slug_i18n={'pt': 'reservas'}, is_active=True,
                                     html_content_i18n={'pt': page_html('PT'), 'en': page_html('EN')})
        self.header = GlobalSection.objects.create(key='main-header', name='Header', section_type='header',
                                                   html_template_i18n={'pt': f'<header><a class="{BTN}">Reservar</a></header>'})
        PageVersion.objects.all().delete()
        self.user = get_user_model().objects.create_superuser('a', 'a@x.com', 'pw')
        self.session = AssistantSession.objects.create(created_by=self.user)
        self.tracker = changes.TurnChanges('Botões a dourado', self.user)
        self.context = {'session': self.session, 'user': self.user, 'active_page': None, 'changes': self.tracker}

    def run_tool(self, name, **params):
        return ToolRegistry.execute(name, params, self.context)

    def classes(self, page, lang, text):
        page.refresh_from_db()
        soup = BeautifulSoup(page.html_content_i18n[lang], 'html.parser')
        return [el for el in soup.find_all(['a', 'button']) if text in el.get_text()][0].get('class')

    def test_find_elements_groups_by_classes_with_counts_and_places(self):
        out = self.run_tool('find_elements', tags='a,button')
        self.assertTrue(out['success'], out)
        groups = {g['classes']: g for g in out['groups']}
        self.assertEqual(groups[BTN]['count'], 5)            # 2 per page + header
        self.assertEqual(groups[GHOST]['count'], 2)
        self.assertIn('Início › hero', groups[BTN]['where'])
        self.assertIn('Header', groups[BTN]['where'])

    def test_restyle_everywhere_in_every_language_keeping_other_classes(self):
        out = self.run_tool('restyle_elements', tags='a,button', has_classes='bg-[#6B1712]',
                            add_classes='bg-[#C9A961] text-black', remove_classes='bg-[#6B1712] text-white')
        self.assertTrue(out['success'], out)
        for page in (self.a, self.b):
            for lang, prefix in (('pt', 'PT'), ('en', 'EN')):
                self.assertEqual(self.classes(page, lang, f'{prefix} Reservar'),
                                 ['inline-flex', 'px-6', 'py-3', 'bg-[#C9A961]', 'text-black'])
                self.assertEqual(self.classes(page, lang, f'{prefix} Carta'), GHOST.split())
        self.header.refresh_from_db()
        self.assertIn('bg-[#6B1712]', self.header.html_template_i18n['pt'])     # header only when asked

    def test_header_and_footer_when_asked(self):
        self.run_tool('restyle_elements', tags='a', has_classes='bg-[#6B1712]', add_classes='bg-[#C9A961]',
                      remove_classes='bg-[#6B1712]', include_header_footer=True)
        self.header.refresh_from_db()
        self.assertIn('bg-[#C9A961]', self.header.html_template_i18n['pt'])

    def test_limited_to_some_pages(self):
        self.run_tool('restyle_elements', tags='a', has_classes='bg-[#6B1712]', add_classes='rounded-full',
                      pages=['Reservas'])
        self.assertIn('rounded-full', self.classes(self.b, 'pt', 'PT Reservar'))
        self.assertNotIn('rounded-full', self.classes(self.a, 'pt', 'PT Reservar'))

    def test_nothing_matches(self):
        out = self.run_tool('restyle_elements', tags='a', has_classes='bg-nope', add_classes='x')
        self.assertFalse(out['success'])

    def test_one_undo_restores_every_page_and_the_header(self):
        self.run_tool('restyle_elements', tags='a,button', has_classes='bg-[#6B1712]', add_classes='bg-[#C9A961]',
                      remove_classes='bg-[#6B1712]', include_header_footer=True)
        self.session.add_message('user', 'botões')
        self.session.add_message('assistant', 'feito')
        self.session.messages[-1]['changes'] = self.tracker.finish()
        self.session.save()
        self.assertEqual(sorted(i['label'] for i in self.session.messages[-1]['changes']), ['Header', 'Início', 'Reservas'])
        result = changes.undo_turn(self.session, len(self.session.messages) - 1, self.user)
        self.assertFalse(result['conflicts'])
        self.assertEqual(self.classes(self.a, 'en', 'EN Enviar'), BTN.split())
        self.header.refresh_from_db()
        self.assertIn('bg-[#6B1712]', self.header.html_template_i18n['pt'])
