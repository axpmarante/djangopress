"""One save path for AI output: checkpoint, edited language, translated others,
localized internal links, unique section names."""
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from djangopress.core.models import Page, PageVersion, SiteSettings
from djangopress.editor_v2 import ai_apply

TRANSLATE = 'djangopress.editor_v2.ai_apply.translate_snippet'


def fake_translate(html, source, target):
    return html.replace('PT:', f'{target.upper()}:')


class AIApplyTestCase(TestCase):
    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        Page.objects.create(title_i18n={'pt': 'Reservas', 'en': 'Book'},
                            slug_i18n={'pt': 'reservas', 'en': 'book-a-table'}, is_active=True,
                            html_content_i18n={'pt': '<section data-section="r" id="r"></section>'})
        self.page = Page.objects.create(
            title_i18n={'pt': 'Início', 'en': 'Home'}, slug_i18n={'pt': 'inicio', 'en': 'home'}, is_active=True,
            html_content_i18n={
                'pt': '<section data-section="hero" id="hero"><h1>PT: Olá</h1></section>'
                      '<section data-section="conceito" id="conceito"><p>PT: Conceito</p></section>',
                'en': '<section data-section="hero" id="hero"><h1>EN: Hello</h1></section>'
                      '<section data-section="conceito" id="conceito"><p>EN: Concept</p></section>',
            },
        )
        PageVersion.objects.filter(page=self.page).delete()
        self.user = get_user_model().objects.create_superuser('a', 'a@x.com', 'pw')

    def html(self, lang):
        self.page.refresh_from_db()
        return self.page.html_content_i18n[lang]


class LinksTest(AIApplyTestCase):
    def test_localize_internal_links(self):
        html = ('<a href="/pt/reservas/#x">a</a><a href="/pt/">b</a><a href="/pt/zzz/">c</a>'
                '<a href="https://x.com/pt/">d</a><a href="/pt/reservas/?q=1">e</a><a href="#top">f</a>')
        out = ai_apply.localize_internal_links(html, 'pt', 'en')
        for expected in ('href="/en/book-a-table/#x"', 'href="/en/"', 'href="/en/zzz/"',
                         'href="https://x.com/pt/"', 'href="/en/book-a-table/?q=1"', 'href="#top"'):
            self.assertIn(expected, out)


class SectionTest(AIApplyTestCase):
    def test_replace_writes_every_language_with_a_checkpoint(self):
        new = '<section data-section="hero" id="hero"><h1>PT: Novo</h1><a href="/pt/reservas/">r</a></section>'
        with mock.patch(TRANSLATE, side_effect=fake_translate):
            result = ai_apply.apply_section_html(self.page, new, 'pt', section_name='hero', user=self.user)
        self.assertIn('PT: Novo', self.html('pt'))
        self.assertIn('EN: Novo', self.html('en'))
        self.assertIn('href="/en/book-a-table/"', self.html('en'))
        self.assertIn('href="/pt/reservas/"', self.html('pt'))
        self.assertIn('EN: Concept', self.html('en'))          # other sections untouched
        self.assertEqual(result['translated_languages'], ['en'])
        self.assertTrue(PageVersion.objects.filter(page=self.page, kind='checkpoint').exists())

    def test_insert_renames_a_duplicate_section_everywhere(self):
        new = '<section data-section="conceito" id="conceito"><a href="#conceito">PT: topo</a></section>'
        with mock.patch(TRANSLATE, side_effect=fake_translate):
            result = ai_apply.apply_section_html(self.page, new, 'pt', mode='insert', insert_after='hero', user=self.user)
        self.assertEqual(result['section_name'], 'conceito-2')
        for lang in ('pt', 'en'):
            html = self.html(lang)
            self.assertIn('data-section="conceito-2"', html)
            self.assertIn('href="#conceito-2"', html)
            self.assertLess(html.index('conceito-2'), html.index('data-section="conceito"'))   # after hero, before old

    def test_translation_failure_keeps_source_text(self):
        new = '<section data-section="hero" id="hero"><h1>PT: Novo</h1></section>'
        with mock.patch(TRANSLATE, side_effect=RuntimeError('no key')):
            result = ai_apply.apply_section_html(self.page, new, 'pt', section_name='hero')
        self.assertIn('PT: Novo', self.html('en'))
        self.assertEqual(result['untranslated_languages'], ['en'])

    def test_empty_language_copy_stays_empty(self):
        self.page.html_content_i18n = {'pt': self.page.html_content_i18n['pt'], 'en': ''}
        self.page.save()
        new = '<section data-section="hero" id="hero"><h1>PT: Novo</h1></section>'
        with mock.patch(TRANSLATE, side_effect=fake_translate) as tr:
            ai_apply.apply_section_html(self.page, new, 'pt', section_name='hero')
        tr.assert_not_called()
        self.assertEqual(self.html('en'), '')

    def test_editing_an_empty_copy_writes_the_default(self):
        self.page.html_content_i18n = {'pt': self.page.html_content_i18n['pt'], 'en': ''}
        self.page.save()
        new = '<section data-section="hero" id="hero"><h1>PT: Novo</h1></section>'
        with mock.patch(TRANSLATE, side_effect=fake_translate):
            ai_apply.apply_section_html(self.page, new, 'en', section_name='hero')
        self.assertIn('PT: Novo', self.html('pt'))
        self.assertEqual(self.html('en'), '')

    def test_output_without_a_section_is_refused(self):
        with self.assertRaises(ValueError):
            ai_apply.apply_section_html(self.page, '<div>no</div>', 'pt', section_name='hero')


class ElementTest(AIApplyTestCase):
    SELECTOR = 'section[data-section="hero"] > h1:nth-child(1)'

    def test_element_replaced_in_every_language(self):
        with mock.patch(TRANSLATE, side_effect=fake_translate):
            ai_apply.apply_element_html(self.page, self.SELECTOR, '<h1 class="big">PT: Grande</h1>', 'pt')
        self.assertIn('<h1 class="big">PT: Grande</h1>', self.html('pt'))
        self.assertIn('<h1 class="big">EN: Grande</h1>', self.html('en'))

    def test_section_root_is_refused_for_an_element(self):
        with self.assertRaises(ValueError):
            ai_apply.apply_element_html(self.page, self.SELECTOR, '<section data-section="hero"><h1>x</h1></section>', 'pt')


class PageTest(AIApplyTestCase):
    def test_page_written_and_translated(self):
        new = '<section data-section="hero" id="hero"><h1>PT: Página</h1><a href="/pt/reservas/">r</a></section>'
        with mock.patch(TRANSLATE, side_effect=fake_translate):
            ai_apply.apply_page_html(self.page, new, 'pt', user=self.user)
        self.assertEqual(self.html('pt'), new)
        self.assertIn('EN: Página', self.html('en'))
        self.assertIn('href="/en/book-a-table/"', self.html('en'))


class ParallelTranslationTest(AIApplyTestCase):
    def test_languages_are_translated_in_parallel(self):
        import time
        s = SiteSettings.load()
        s.enabled_languages = [{'code': c, 'name': c} for c in ('pt', 'en', 'es', 'fr')]
        s.save()
        self.page.html_content_i18n = {c: self.page.html_content_i18n['pt'] for c in ('pt', 'en', 'es', 'fr')}
        self.page.save()

        def slow(html, source, target):
            time.sleep(0.4)
            return fake_translate(html, source, target)
        t0 = time.time()
        with mock.patch(TRANSLATE, side_effect=slow):
            result = ai_apply.apply_page_html(self.page, '<section data-section="hero" id="hero"><h1>PT: P</h1></section>', 'pt')
        self.assertLess(time.time() - t0, 1.0)          # 3 languages x 0.4 s would be 1.2 s in series
        self.assertEqual(sorted(result['translated_languages']), ['en', 'es', 'fr'])
        self.assertIn('FR: P', self.html('fr'))


class ClassOnlyTest(AIApplyTestCase):
    """A change that keeps the visible text reaches the other languages without a translation call."""

    def setUp(self):
        super().setUp()
        self.page.html_content_i18n = {
            'pt': '<section data-section="hero" id="hero" class="py-10"><h1 class="text-4xl">PT: Olá</h1>'
                  '<img src="/m/a.jpg" alt="PT: sala"><a class="btn" href="/pt/">PT: Início</a></section>',
            'en': '<section data-section="hero" id="hero" class="py-10"><h1 class="text-4xl">EN: Hello</h1>'
                  '<img src="/m/a.jpg" alt="EN: room"><a class="btn" href="/en/">EN: Home</a></section>',
        }
        self.page.save()

    def apply(self, new):
        with mock.patch(TRANSLATE, side_effect=fake_translate) as tr:
            result = ai_apply.apply_section_html(self.page, new, 'pt', section_name='hero', user=self.user)
        return result, tr

    def test_classes_are_copied_and_nothing_is_translated(self):
        new = ('<section data-section="hero" id="hero" class="py-24 bg-[#111]"><h1 class="text-6xl text-white">PT: Olá</h1>'
               '<img src="/m/a.jpg" alt="PT: sala"><a class="btn" href="/pt/">PT: Início</a></section>')
        result, tr = self.apply(new)
        tr.assert_not_called()
        en = self.html('en')
        self.assertIn('class="py-24 bg-[#111]"', en)
        self.assertIn('<h1 class="text-6xl text-white">EN: Hello</h1>', en)
        self.assertIn('alt="EN: room"', en)
        self.assertIn('href="/en/"', en)
        self.assertEqual(result['translated_languages'], ['en'])
        self.assertIn('text-6xl', result['html'])
        self.assertIn('PT: Olá', result['html'])

    def test_a_changed_link_is_localised(self):
        new = ('<section data-section="hero" id="hero" class="py-10"><h1 class="text-4xl">PT: Olá</h1>'
               '<img src="/m/a.jpg" alt="PT: sala"><a class="btn" href="/pt/reservas/">PT: Início</a></section>')
        _result, tr = self.apply(new)
        tr.assert_not_called()
        self.assertIn('href="/en/book-a-table/"', self.html('en'))

    def test_a_removed_attribute_is_removed(self):
        new = ('<section data-section="hero" id="hero"><h1 class="text-4xl">PT: Olá</h1>'
               '<img src="/m/a.jpg" alt="PT: sala"><a class="btn" href="/pt/">PT: Início</a></section>')
        self.apply(new)
        self.assertIn('<section data-section="hero" id="hero"><h1', self.html('en'))

    def test_a_text_change_is_translated(self):
        new = ('<section data-section="hero" id="hero" class="py-10"><h1 class="text-4xl">PT: Adeus</h1>'
               '<img src="/m/a.jpg" alt="PT: sala"><a class="btn" href="/pt/">PT: Início</a></section>')
        _result, tr = self.apply(new)
        self.assertEqual(tr.call_count, 1)
        self.assertIn('EN: Adeus', self.html('en'))

    def test_an_alt_change_is_translated(self):
        new = ('<section data-section="hero" id="hero" class="py-10"><h1 class="text-4xl">PT: Olá</h1>'
               '<img src="/m/a.jpg" alt="PT: mesa"><a class="btn" href="/pt/">PT: Início</a></section>')
        _result, tr = self.apply(new)
        self.assertEqual(tr.call_count, 1)

    def test_a_new_structure_is_translated(self):
        new = ('<section data-section="hero" id="hero" class="py-10"><div><h1 class="text-4xl">PT: Olá</h1></div>'
               '<img src="/m/a.jpg" alt="PT: sala"><a class="btn" href="/pt/">PT: Início</a></section>')
        _result, tr = self.apply(new)
        self.assertEqual(tr.call_count, 1)

    def test_element_classes_only(self):
        with mock.patch(TRANSLATE, side_effect=fake_translate) as tr:
            result = ai_apply.apply_element_html(self.page, 'section[data-section="hero"] > h1',
                                                 '<h1 class="text-7xl">PT: Olá</h1>', 'pt', user=self.user)
        tr.assert_not_called()
        self.assertIn('<h1 class="text-7xl">EN: Hello</h1>', self.html('en'))
        self.assertEqual(result['html'], '<h1 class="text-7xl">PT: Olá</h1>')
