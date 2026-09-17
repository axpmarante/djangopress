"""Tests for the briefing parser (docs/plans/2026-09-16-fast-site-generation-plan.md, Task 1)."""

from django.test import SimpleTestCase

from djangopress.core.build.briefing import parse_briefing, _parse_content_line


SAMPLE = """# CHECKin Faro — Site Briefing

> Redesign of https://checkinfaro.pt

## Business

Cozinha de autor algarvia, à carta, para partilhar. Chef Leonel Pereira.

Segundo parágrafo.

## Languages
- Default: pt (Português)
- Additional: en (English)

## Contact
- Email: geral@checkinfaro.pt
- Phone: +351 289 000 000
- Address: Rua do Castelo 1, Faro
- Google Maps: https://maps.google.com/?q=37.0146,-7.9350

### Opening hours
- Terça a Sábado: 19:00–23:00
- Domingo e Segunda: encerrado

## Social Media
- Instagram: https://instagram.com/checkinfaro
- Facebook: https://facebook.com/checkinfaro

## Pages
- **Home**: the one-page site
- **Reservas**: form (reuse the template's `contact` DynamicForm)

## Content

### Home
- (required) Message: Cozinha de autor algarvia, à carta, para partilhar — keywords: autor, algarvia, partilhar
- (required) CTA: Reservar mesa → /reservas/
- (required) Proof: Guia Michelin 2024
- (required) Menu: every item name and price from briefings/checkin-faro-menu.json
- Story: o chef, a sala, os produtores

## Header
logo left, 5 links, one CTA, language switcher

## Footer
contact, hours, social icons, privacy link, copyright

## Design Constraints
- **Brand colors**: #C51B17 red, #40308A plum
- **Logo / brand assets**: none
- **Direction**: Sólido e de confiança, claro, fotografia real em destaque
- **Avoid**: orange accents; photo carousel hero
- **References**: https://example.com/a, https://example.com/b
- **Image constraints**: dishes 2048px, interiors 1600px

## Images
- **Strategy**: reuse existing
- **Sources**: old site gallery
- **Constraints**: dishes 2048px, space 1600px

## Domain
checkin-faro

## Additional Notes
jsonld: Restaurant
cuisine: Algarvia
price range: €€€
"""


class ParseBriefingTest(SimpleTestCase):

    def setUp(self):
        self.b = parse_briefing(SAMPLE)

    def test_title_and_business(self):
        self.assertEqual(self.b.title, 'CHECKin Faro')
        self.assertTrue(self.b.business.startswith('Cozinha de autor'))
        self.assertIn('Segundo parágrafo.', self.b.business)

    def test_languages(self):
        self.assertEqual(self.b.default_language, 'pt')
        self.assertEqual(self.b.languages, ['pt', 'en'])

    def test_contact_hours_social(self):
        self.assertEqual(self.b.contact['email'], 'geral@checkinfaro.pt')
        self.assertEqual(self.b.contact['phone'], '+351 289 000 000')
        self.assertEqual(self.b.contact['address'], 'Rua do Castelo 1, Faro')
        self.assertEqual(self.b.contact['maps_url'], 'https://maps.google.com/?q=37.0146,-7.9350')
        self.assertEqual(self.b.hours, ['Terça a Sábado: 19:00–23:00', 'Domingo e Segunda: encerrado'])
        self.assertEqual(self.b.social['instagram'], 'https://instagram.com/checkinfaro')

    def test_pages(self):
        self.assertEqual([p['slug'] for p in self.b.pages], ['home', 'reservas'])
        self.assertEqual(self.b.pages[0]['name'], 'Home')

    def test_content_items(self):
        items = self.b.content['home']
        self.assertEqual(len(items), 5)
        first = items[0]
        self.assertEqual(first.id, 'home-1')
        self.assertTrue(first.required)
        self.assertEqual(first.kind, 'Message')
        self.assertEqual(first.text, 'Cozinha de autor algarvia, à carta, para partilhar')
        self.assertEqual(first.keywords, ['autor', 'algarvia', 'partilhar'])
        cta = items[1]
        self.assertEqual(cta.href, '/reservas/')
        self.assertEqual(cta.text, 'Reservar mesa')
        menu = items[3]
        self.assertEqual(menu.menu_json, 'briefings/checkin-faro-menu.json')
        self.assertFalse(items[4].required)

    def test_constraints(self):
        c = self.b.constraints
        self.assertEqual(c['brand_colors'], ['#C51B17', '#40308A'])
        self.assertIsNone(c['logo'])
        self.assertEqual(c['direction'], 'Sólido e de confiança, claro, fotografia real em destaque')
        self.assertEqual(c['avoid'], ['orange accents', 'photo carousel hero'])
        self.assertEqual(c['references'], ['https://example.com/a', 'https://example.com/b'])
        self.assertEqual(c['image_max_widths'], {'dishes': 2048, 'interiors': 1600})

    def test_mode_defaults_to_conventional(self):
        self.assertEqual(self.b.constraints['mode'], 'conventional')

    def test_mode_bold(self):
        b = parse_briefing(SAMPLE.replace('- **Avoid**: orange accents', '- **Mode**: bold\n- **Avoid**: orange accents'))
        self.assertEqual(b.constraints['mode'], 'bold')

    def test_notes_and_flags(self):
        self.assertEqual(self.b.notes['jsonld'], 'Restaurant')
        self.assertEqual(self.b.notes['cuisine'], 'Algarvia')
        self.assertEqual(self.b.notes['price range'], '€€€')
        self.assertFalse(self.b.has_open_questions)
        self.assertEqual(self.b.images['strategy'], 'reuse existing')
        self.assertEqual(self.b.header, 'logo left, 5 links, one CTA, language switcher')

    def test_notes_accept_bullets(self):
        text = SAMPLE.replace(
            '## Additional Notes\njsonld: Restaurant\ncuisine: Algarvia\nprice range: €€€\n',
            '## Additional Notes\n- jsonld: HomeAndConstructionBusiness\n* cuisine: Algarvia\n')
        b = parse_briefing(text)
        self.assertEqual(b.notes['jsonld'], 'HomeAndConstructionBusiness')
        self.assertEqual(b.notes['cuisine'], 'Algarvia')

    def test_open_questions_detected(self):
        b = parse_briefing(SAMPLE.replace('## Business', '## Open Questions\n1. x?\n\n## Business'))
        self.assertTrue(b.has_open_questions)

    def test_bad_content_line_raises(self):
        bad = SAMPLE.replace('- (required) Proof: Guia Michelin 2024', '- (required) no colon here')
        with self.assertRaises(ValueError) as cm:
            parse_briefing(bad)
        self.assertIn('no colon here', str(cm.exception))

    def test_arrow_inside_prose_is_not_an_href(self):
        line = ('- (required) Gallery: Antes e depois — the 2026 build documented as Início / Meio / Fim '
                '(brick shell → finished house), plus … — keywords: antes e depois, início, fim')
        item = _parse_content_line(line, 'home', 1)
        self.assertIsNone(item.href)
        self.assertEqual(item.text, 'Antes e depois — the 2026 build documented as Início / Meio / Fim '
                                     '(brick shell → finished house), plus …')
        self.assertEqual(item.keywords, ['antes e depois', 'início', 'fim'])

    def test_last_arrow_wins_when_href_like(self):
        line = '- (required) CTA: Falar → agora → #contact'
        item = _parse_content_line(line, 'home', 1)
        self.assertEqual(item.href, '#contact')
        self.assertEqual(item.text, 'Falar → agora')

    def test_contact_annotations_are_stripped(self):
        text = """# Test Co — Site Briefing

## Contact
- Email: geral@remodelacoes24.pt (not published today; the client creates the mailbox)
- Phone: +351 969 240 223 (WhatsApp too)
- Address: Algarve, Portugal (no street address published; the client works multiple sites)
"""
        b = parse_briefing(text)
        self.assertEqual(b.contact['email'], 'geral@remodelacoes24.pt')
        self.assertEqual(b.contact['address'], 'Algarve, Portugal')
        # "(WhatsApp too)" carries no annotation cue (no ";" / "not published" / "the client" / …)
        # so it is real content, not a note to strip.
        self.assertEqual(b.contact['phone'], '+351 969 240 223 (WhatsApp too)')

    def test_address_parenthetical_without_cue_is_kept(self):
        text = SAMPLE.replace('- Address: Rua do Castelo 1, Faro', '- Address: Rua do Castelo 1 (Edifício A, 3º andar)')
        b = parse_briefing(text)
        self.assertEqual(b.contact['address'], 'Rua do Castelo 1 (Edifício A, 3º andar)')

    def test_address_parenthetical_with_cue_is_stripped(self):
        text = SAMPLE.replace(
            '- Address: Rua do Castelo 1, Faro',
            '- Address: Rua do Castelo 1, Faro (not published today; the client will confirm)')
        b = parse_briefing(text)
        self.assertEqual(b.contact['address'], 'Rua do Castelo 1, Faro')

    def test_hash_like_prose_is_not_an_href(self):
        line = '- (required) Proof: o melhor → #1 no ranking'
        item = _parse_content_line(line, 'home', 1)
        self.assertIsNone(item.href)
        self.assertEqual(item.text, 'o melhor → #1 no ranking')
