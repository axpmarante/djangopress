"""Generated HTML is validated per scope (a section is not compared with the whole
page), real truncation comes from the model's finish reason, and generators work
on the language being edited."""
from unittest import mock

from django.test import SimpleTestCase, TestCase

from djangopress.ai.services import ContentGenerationService, validate_html_structure
from djangopress.ai.utils.llm_config import StandardizedLLMResponse
from djangopress.core.models import Page, SiteSettings

SECTION = '<section data-section="hero" id="hero"><div><h1>Olá</h1><p>' + 'texto ' * 600 + '</p></div></section>'
PAGE = SECTION + ''.join(f'<section data-section="s{i}" id="s{i}"><p>{"x" * 4000}</p></section>' for i in range(10))


class ValidationScopeTest(SimpleTestCase):
    def test_section_much_smaller_than_page_is_fine_for_section_scope(self):
        self.assertEqual(validate_html_structure(SECTION, PAGE, scope='section'), [])

    def test_page_scope_still_catches_a_short_page(self):
        errors = validate_html_structure(SECTION, PAGE, scope='page')
        self.assertTrue(any('possible truncation' in e for e in errors))

    def test_unclosed_section_fails(self):
        errors = validate_html_structure('<section data-section="hero"><div><p>a</p></div>', scope='section')
        self.assertTrue(errors)

    def test_max_tokens_is_reported_as_cut_off(self):
        service = ContentGenerationService.__new__(ContentGenerationService)
        with self.assertRaisesRegex(ValueError, 'cut off'):
            service._extract_html_from_response(SECTION, scope='section', finish_reason='MAX_TOKENS')


class ValidateOptionsTest(SimpleTestCase):
    def setUp(self):
        self.service = ContentGenerationService.__new__(ContentGenerationService)

    def test_wrong_section_name_is_corrected(self):
        options = self.service._validate_options(['<section data-section="other" id="other"><p>a</p></section>'],
                                                 scope='section', section_name='hero')
        self.assertIn('data-section="hero"', options[0]['html'])
        self.assertIn('id="hero"', options[0]['html'])

    def test_an_incomplete_option_fails_the_request(self):
        with self.assertRaisesRegex(ValueError, 'Option 2'):
            self.service._validate_options(['<section data-section="hero"><p>a</p></section>', '<p>no section</p>'],
                                           scope='section', section_name='hero')

    def test_element_scope_needs_the_marked_target(self):
        good = self.service._validate_options(['<section><a data-target="true" class="btn">Go</a></section>'], scope='element')
        self.assertEqual(good[0]['html'], '<a class="btn">Go</a>')
        with self.assertRaisesRegex(ValueError, 'Option 1'):
            self.service._validate_options(['<section><a class="btn">Go</a></section>'], scope='element')


def llm_returning(html):
    return StandardizedLLMResponse(content=html, usage={'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2},
                                   finish_reason='STOP')


class GeneratorLanguageTest(TestCase):
    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        self.page = Page.objects.create(
            title_i18n={'pt': 'Início', 'en': 'Home'}, slug_i18n={'pt': 'inicio', 'en': 'home'}, is_active=True,
            html_content_i18n={'pt': '<section data-section="hero" id="hero"><h1>Olá mundo</h1></section>',
                               'en': '<section data-section="hero" id="hero"><h1>Hello world</h1></section>'},
        )

    def run_refine(self, lang):
        service = ContentGenerationService()
        reply = llm_returning('<section data-section="hero" id="hero"><h1>New</h1></section>')
        with mock.patch.object(service.llm, 'get_completion', return_value=reply) as call:
            service.refine_section_only(page_id=self.page.id, section_name='hero', instructions='Bigger title',
                                        skip_component_selection=True, lang=lang)
        return ' '.join(m['content'] for m in call.call_args.args[0])

    def test_refine_reads_the_editing_language(self):
        prompt = self.run_refine('en')
        self.assertIn('Hello world', prompt)
        self.assertNotIn('Olá mundo', prompt)

    def test_empty_copy_falls_back_to_default_language(self):
        self.page.html_content_i18n = {'pt': self.page.html_content_i18n['pt'], 'en': ''}
        self.page.save()
        self.assertIn('Olá mundo', self.run_refine('en'))
