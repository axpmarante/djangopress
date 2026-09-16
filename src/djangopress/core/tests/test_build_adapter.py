"""Tests for the concept adapter (Tasks 4 and 5)."""

from pathlib import Path

from django.test import SimpleTestCase

from djangopress.core.build import adapter
from djangopress.core.build.adapter import (
    check_complete, extract_colors, extract_fonts, fix_body_rules, infer_layout, lift_head, soup_of, split_document,
)

FIXTURES = Path(__file__).parent / 'fixtures'
MINIMAL = (FIXTURES / 'concept-minimal.html').read_text()
CHECKIN = (FIXTURES / 'concept-checkin-faro.html').read_text()


class CompletenessTest(SimpleTestCase):

    def test_complete_document_has_no_errors(self):
        self.assertEqual(check_complete(MINIMAL), [])

    def test_truncated_document(self):
        cut = MINIMAL[: MINIMAL.index('<footer')]
        errors = check_complete(cut)
        self.assertTrue(any('truncated' in e for e in errors))
        self.assertTrue(any('<footer' in e for e in errors))


class SplitTest(SimpleTestCase):

    def test_split_minimal(self):
        header, main, footer, trailing = split_document(soup_of(MINIMAL))
        self.assertEqual(header.name, 'header')
        self.assertEqual(main.name, 'main')
        self.assertEqual(footer.name, 'footer')
        self.assertEqual(len(trailing), 1)
        self.assertIn("console.log('ready')", trailing[0].get_text())

    def test_split_checkin(self):
        header, main, footer, trailing = split_document(soup_of(CHECKIN))
        # NOTE: the brief's plan said 10; the real fixture has 11 top-level
        # <section> children of <main> (verified via find_all(recursive=False)).
        self.assertEqual(len(main.find_all('section', recursive=False)), 11)
        self.assertIn('lucide.createIcons', trailing[0].get_text())


class LiftHeadTest(SimpleTestCase):

    def test_minimal(self):
        soup = soup_of(MINIMAL)
        head = lift_head(soup)
        self.assertIn('tailwind.config', head['config_js'])
        self.assertIn('.grain', head['css'])
        self.assertEqual(head['meta_title'], 'Casa Teste — Início')
        self.assertEqual(head['meta_description'], 'Descrição de teste.')
        self.assertEqual(head['google_families'], ['Lora', 'Inter'])
        self.assertEqual(head['removed']['tailwind-cdn'], 1)
        self.assertEqual(head['removed']['google-fonts-link'], 2)
        self.assertNotIn('cdn.tailwindcss.com', head['head_code'])
        self.assertNotIn('fonts.googleapis', head['head_code'])
        self.assertIn('<script>', head['head_code'])
        self.assertIn('<style>', head['head_code'])

    def test_checkin_keeps_lucide(self):
        head = lift_head(soup_of(CHECKIN))
        self.assertIn('unpkg.com/lucide', head['head_code'])
        self.assertIn('.boarding-ticket', head['css'])


class BodyRuleTest(SimpleTestCase):

    def test_rewrites_body_selector_only(self):
        css, n = fix_body_rules('html { scroll-behavior: smooth; }\nbody { background:#F7F1E8; }\n.body-copy { color: red }\nhtml, body { margin: 0 }')
        self.assertEqual(n, 2)
        self.assertIn('body.bg-white { background:#F7F1E8; }', css)
        self.assertIn('html, body.bg-white { margin: 0 }', css)
        self.assertIn('.body-copy { color: red }', css)


class TokensTest(SimpleTestCase):

    def test_fonts_from_config(self):
        head = lift_head(soup_of(MINIMAL))
        self.assertEqual(extract_fonts(head['config_js'], head['google_families']), ('Lora', 'Inter'))

    def test_fonts_from_google_link_when_no_config(self):
        self.assertEqual(extract_fonts('', ['Playfair Display', 'Inter Tight']), ('Playfair Display', 'Inter Tight'))

    def test_colors_minimal(self):
        soup = soup_of(MINIMAL)
        head = lift_head(soup)
        colors = extract_colors(head['config_js'], head['css'], soup, cta_texts=['Reservar mesa'])
        self.assertEqual(colors['background_color'], '#f5f0e8')
        self.assertEqual(colors['text_color'], '#2b2520')
        self.assertEqual(colors['heading_color'], '#2b2520')
        self.assertEqual(colors['primary_color'], '#c05b3e')
        self.assertEqual(colors['primary_button_bg'], '#c05b3e')
        self.assertEqual(colors['primary_button_text'], '#ffffff')
        self.assertIn(colors['secondary_color'], ('#3e6b73', '#2b2520', '#f5f0e8'))

    def test_colors_checkin(self):
        soup = soup_of(CHECKIN)
        head = lift_head(soup)
        colors = extract_colors(head['config_js'], head['css'], soup, cta_texts=['Reservar'])
        self.assertEqual(colors['background_color'], '#f7f1e8')
        self.assertEqual(colors['text_color'], '#141313')
        self.assertRegex(colors['primary_color'], r'^#[0-9a-f]{6}$')

    def test_layout_minimal(self):
        layout = infer_layout(soup_of(MINIMAL))
        self.assertEqual(layout['container_width'], '6xl')
        self.assertEqual(layout['border_radius_preset'], 'lg')
        self.assertEqual(layout['shadow_preset'], 'lg')

    def test_layout_defaults_when_nothing_found(self):
        layout = infer_layout(soup_of('<html><body><main><section><p>x</p></section></main></body></html>'))
        self.assertEqual(layout, {'container_width': '7xl', 'border_radius_preset': 'none', 'shadow_preset': 'none'})
