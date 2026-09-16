"""Tests for the concept adapter (Tasks 4 and 5)."""

from collections import Counter
from pathlib import Path

from django.test import SimpleTestCase

from djangopress.core.build import adapter
from djangopress.core.build.adapter import (
    apply_editor_contract, check_complete, extract_colors, extract_fonts, fix_body_rules, infer_layout, lift_head,
    soup_of, split_document,
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


from djangopress.core.build.adapter import adapt


class AdaptMinimalTest(SimpleTestCase):

    def setUp(self):
        self.r = adapt(MINIMAL, lang='pt', languages=['pt', 'en'],
                       image_map={'dish-1': {'url': 'https://example.com/dish.jpg'}},
                       cta_texts=['Reservar mesa'], contact_phone='+351 289 000 000')

    def test_no_errors(self):
        self.assertEqual(self.r.errors, [])

    def test_sections_named_and_wrapped(self):
        self.assertEqual(self.r.sections, ['hero', 'menu', 'contact'])
        page = soup_of(self.r.page_html)
        secs = page.find_all('section', recursive=False)
        self.assertEqual([s['data-section'] for s in secs], ['hero', 'menu', 'contact'])
        self.assertEqual([s['id'] for s in secs], ['hero', 'menu', 'contact'])
        self.assertIsNone(page.find('main'))

    def test_links_prefixed(self):
        hrefs = [a['href'] for a in soup_of(self.r.header_html).find_all('a')]
        self.assertEqual(hrefs[:4], ['/pt/', '/pt/#menu', '/pt/#contact', '/pt/reservas/'])
        self.assertIn('/pt/politica-de-privacidade/', self.r.footer_html)
        self.assertIn('href="/pt/reservas/"', self.r.page_html)

    def test_overlay_gets_pointer_events_none_but_img_does_not(self):
        page = soup_of(self.r.page_html)
        overlay = page.select_one('section#hero div.bg-gradient-to-t')
        self.assertIn('pointer-events-none', overlay['class'])
        img = page.select_one('section#hero img')
        self.assertNotIn('pointer-events-none', img.get('class', []))
        self.assertEqual(self.r.changes['pointer-events-none'], 1)

    def test_duplicate_image_marked_decorative(self):
        imgs = soup_of(self.r.page_html).select('section#menu img')
        dup = imgs[1]
        self.assertEqual(dup['aria-hidden'], 'true')
        self.assertEqual(dup['alt'], '')

    def test_foreign_image_becomes_placeholder(self):
        img = soup_of(self.r.page_html).select('section#menu img')[0]
        self.assertIn('placehold.co', img['src'])
        self.assertTrue(img['data-image-name'])
        self.assertTrue(img['data-image-prompt'])
        self.assertTrue(any('unsplash' in w for w in self.r.warnings))

    def test_language_switcher_injected_in_slot(self):
        self.assertIn("{% url 'set_language' %}", self.r.header_html)
        self.assertIn('{% load i18n %}', self.r.header_html)
        self.assertNotIn('data-slot="language-switcher"', self.r.header_html)

    def test_menu_extracted(self):
        self.assertEqual(self.r.menu, [
            {'label': 'Casa Teste', 'href': '/pt/'}, {'label': 'Menu', 'href': '/pt/#menu'},
            {'label': 'Contactos', 'href': '/pt/#contact'}, {'label': 'Reservar mesa', 'href': '/pt/reservas/'},
        ])

    def test_head_code_and_settings(self):
        self.assertIn('body.bg-white { background: #F5F0E8', self.r.head_code)
        self.assertNotIn('cdn.tailwindcss.com', self.r.head_code)
        self.assertEqual(self.r.settings['heading_font'], 'Lora')
        self.assertEqual(self.r.settings['body_font'], 'Inter')
        self.assertEqual(self.r.settings['primary_color'], '#c05b3e')
        self.assertEqual(self.r.settings['container_width'], '6xl')
        self.assertEqual(self.r.meta_title, 'Casa Teste — Início')

    def test_trailing_script_kept_in_page(self):
        self.assertTrue(self.r.page_html.rstrip().endswith("<script>console.log('ready');</script>"))

    def test_single_language_has_no_switcher(self):
        r = adapt(MINIMAL, lang='pt', languages=['pt'], image_map={})
        self.assertNotIn('set_language', r.header_html)
        self.assertNotIn('data-slot', r.header_html)


class AdaptCheckinTest(SimpleTestCase):

    def setUp(self):
        self.r = adapt(CHECKIN, lang='pt', languages=['pt', 'en'], image_map={}, cta_texts=['Reservar'])

    def test_eleven_sections_first_is_hero(self):
        self.assertEqual(len(self.r.sections), 11)   # the fixture has 11 direct children of <main> (Task 4 confirmed)
        self.assertEqual(self.r.sections[0], 'hero')
        self.assertEqual(len(set(self.r.sections)), 11)
        for name in self.r.sections:
            self.assertRegex(name, r'^[a-z][a-z0-9-]*$')
        self.assertIn('carta', self.r.sections)

    def test_no_forbidden_tags_and_no_errors(self):
        page = soup_of(self.r.page_html)
        for tag in ('html', 'head', 'body', 'header', 'nav', 'footer'):
            self.assertIsNone(page.find(tag), tag)
        self.assertEqual(self.r.errors, [])

    def test_switcher_appended_when_no_slot(self):
        self.assertIn("{% url 'set_language' %}", self.r.header_html)

    def test_no_stray_content_outside_sections(self):
        page = soup_of(self.r.page_html)
        for node in page.contents:
            if getattr(node, 'name', None) in ('section', 'script'):
                continue
            text = str(node)
            self.assertEqual(text.strip(), '', f'stray content outside a <section>: {text!r}')


class AdaptErrorsTest(SimpleTestCase):

    def test_truncated(self):
        r = adapt(MINIMAL[: MINIMAL.index('<footer')], lang='pt', languages=['pt'], image_map={})
        self.assertFalse(r.ok)
        self.assertTrue(any('truncated' in e for e in r.errors))

    def test_template_syntax_in_footer(self):
        r = adapt(MINIMAL.replace('© 2026 Casa Teste', '© {{ year }} Casa Teste'), lang='pt', languages=['pt'], image_map={})
        self.assertTrue(any('template syntax' in e and 'footer' in e for e in r.errors))

    def test_style_inside_main(self):
        r = adapt(MINIMAL.replace('<h2 class="font-display text-4xl">A carta</h2>', '<style>.x{}</style><h2>A carta</h2>'), lang='pt', languages=['pt'], image_map={})
        self.assertTrue(any('<style>' in e for e in r.errors))

    def test_nav_inside_main(self):
        r = adapt(MINIMAL.replace('<ul><li>Couvert', '<nav><a href="#x">x</a></nav><ul><li>Couvert'), lang='pt', languages=['pt'], image_map={})
        self.assertTrue(any('<nav>' in e for e in r.errors))


class MenuDedupeAndLogoSkipTest(SimpleTestCase):

    HEADER_WITH_DUPLICATE_NAV = MINIMAL.replace(
        '<div data-slot="language-switcher"></div>\n  </nav>',
        '<div data-slot="language-switcher"></div>\n'
        '    <div class="lg:hidden">\n'
        '      <a href="/">Casa Teste</a>\n'
        '      <a href="#menu">Menu</a>\n'
        '      <a href="/reservas/">Reservar mesa</a>\n'
        '    </div>\n  </nav>',
    )

    def test_menu_dedupes_desktop_and_mobile_links(self):
        r = adapt(self.HEADER_WITH_DUPLICATE_NAV, lang='pt', languages=['pt', 'en'],
                  image_map={'dish-1': {'url': 'https://example.com/dish.jpg'}},
                  cta_texts=['Reservar mesa'], contact_phone='+351 289 000 000')
        self.assertEqual(len(r.menu), 4)
        self.assertEqual([m['href'] for m in r.menu], ['/pt/', '/pt/#menu', '/pt/#contact', '/pt/reservas/'])

    def test_menu_skips_logo_link_to_home(self):
        r = adapt(MINIMAL, lang='pt', languages=['pt', 'en'],
                  image_map={'dish-1': {'url': 'https://example.com/dish.jpg'}},
                  cta_texts=['Reservar mesa'], contact_phone='+351 289 000 000', site_name='Casa Teste')
        self.assertNotIn({'label': 'Casa Teste', 'href': '/pt/'}, r.menu)
        self.assertEqual(len(r.menu), 3)

        r_without_site_name = adapt(MINIMAL, lang='pt', languages=['pt', 'en'],
                                    image_map={'dish-1': {'url': 'https://example.com/dish.jpg'}},
                                    cta_texts=['Reservar mesa'], contact_phone='+351 289 000 000')
        self.assertIn({'label': 'Casa Teste', 'href': '/pt/'}, r_without_site_name.menu)


class EditorContractGuardsTest(SimpleTestCase):

    def test_placeholder_duplicates_not_marked_decorative(self):
        soup = soup_of(
            '<div><img src="https://placehold.co/600x400?text=x">'
            '<img src="https://placehold.co/600x400?text=x"></div>'
        )
        changes = Counter()
        apply_editor_contract(soup, changes)
        imgs = soup.find_all('img')
        self.assertNotIn('aria-hidden', imgs[1].attrs)
        self.assertEqual(changes['duplicate-img-decorative'], 0)

    def test_alpine_backdrop_keeps_pointer_events(self):
        soup = soup_of('<div class="absolute inset-0 bg-black/50" @click="open = false"></div>')
        changes = Counter()
        apply_editor_contract(soup, changes)
        div = soup.find('div')
        self.assertNotIn('pointer-events-none', div.get('class', []))
        self.assertEqual(changes['pointer-events-none'], 0)


class RenamedSectionAnchorTest(SimpleTestCase):

    DOC = (
        '<!DOCTYPE html><html><head><title>T</title></head><body>'
        '<header><nav><a href="#Sobre">Sobre</a></nav></header>'
        '<main><section id="Sobre"><h2>Sobre</h2><p>Texto</p></section></main>'
        '<footer><p>f</p></footer>'
        '</body></html>'
    )

    def test_renamed_section_id_rewrites_anchors(self):
        r = adapt(self.DOC, lang='pt', languages=['pt'], image_map={})
        self.assertEqual(r.errors, [])
        self.assertEqual(r.sections, ['sobre'])
        self.assertIn('href="/pt/#sobre"', r.header_html)
