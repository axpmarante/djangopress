"""Tests for the content contract (Task 7)."""

import copy

from django.test import SimpleTestCase

from djangopress.core.build.contract import check_contract, normalise
from djangopress.core.tests.test_build_importer import PACKET

PAGE = """
<section data-section="hero" id="hero"><h1>Cozinha  de AUTOR algarvia</h1>
<a href="/pt/reservas/">Reservar mesa</a></section>
<section data-section="proof" id="proof"><p>Guia Michelin 2024</p></section>
<section data-section="menu" id="menu"><ul><li>Couvert <span>3,30 €</span></li></ul></section>
<section data-section="contact" id="contact"><p>+351 289 000 000 · Rua do Castelo 1, Faro</p>
<p>geral@casateste.pt</p><p>Terça a Sábado 19:00–23:00</p></section>
"""


class NormaliseTest(SimpleTestCase):

    def test_collapses_and_casefolds_keeps_accents(self):
        self.assertEqual(normalise('  Cozinha  de\nAUTOR  '), 'cozinha de autor')
        self.assertEqual(normalise('Terça'), 'terça')


class ContractTest(SimpleTestCase):

    def parts(self, page=PAGE):
        return {'page': page, 'header': '<header><a href="/pt/reservas/">Reservar mesa</a></header>', 'footer': '<footer></footer>'}

    def test_full_page_passes(self):
        self.assertEqual(check_contract(PACKET, self.parts(), 'pt'), [])

    def test_missing_keyword_item(self):
        page = PAGE.replace('Cozinha  de AUTOR algarvia', 'Bem-vindos')
        misses = check_contract(PACKET, self.parts(page), 'pt')
        self.assertEqual([m['id'] for m in misses], ['home-1'])
        self.assertIn('keywords', misses[0]['reason'])

    def test_missing_href(self):
        parts = self.parts(PAGE.replace('/pt/reservas/', '/pt/contactos/'))
        parts['header'] = '<header></header>'
        misses = check_contract(PACKET, parts, 'pt')
        self.assertEqual([m['id'] for m in misses], ['home-2'])
        self.assertIn('/pt/reservas/', misses[0]['reason'])

    def test_missing_exact_and_menu_item(self):
        page = PAGE.replace('Guia Michelin 2024', 'Michelin').replace('Couvert', 'Pão')
        ids = [m['id'] for m in check_contract(PACKET, self.parts(page), 'pt')]
        self.assertEqual(ids, ['home-3', 'home-4'])

    def test_price_accepts_comma_or_dot(self):
        page = PAGE.replace('3,30 €', '3.30€')
        self.assertEqual(check_contract(PACKET, self.parts(page), 'pt'), [])

    def test_missing_fact_phone_and_hours(self):
        page = PAGE.replace('+351 289 000 000', '').replace('19:00–23:00', '')
        reasons = [m['reason'] for m in check_contract(PACKET, self.parts(page), 'pt')]
        self.assertTrue(any('phone' in r for r in reasons))
        self.assertTrue(any('19:00' in r for r in reasons))

    def test_contact_kind_item_is_covered_by_facts(self):
        packet = copy.deepcopy(PACKET)
        packet['content']['home']['required'].append(
            {'id': 'home-9', 'kind': 'Contact', 'text': 'phone, email, address (from ## Contact)'})
        misses = check_contract(packet, self.parts(), 'pt')
        self.assertNotIn('home-9', [m['id'] for m in misses])
        page = PAGE.replace('+351 289 000 000', '')
        misses = check_contract(packet, self.parts(page), 'pt')
        self.assertNotIn('home-9', [m['id'] for m in misses])
        self.assertTrue(any('phone' in m['reason'] for m in misses))

    def test_verbatim_ignores_quotes_and_dashes(self):
        packet = copy.deepcopy(PACKET)
        packet['content']['home']['required'].append(
            {'id': 'home-10', 'kind': 'Testimonial',
             'text': '"Somos um negócio de pessoas, não um negócio de web design." — António Marante'})
        page = PAGE + ('<section><p>«Somos um negócio de pessoas, não um negócio de web design.»</p>'
                        '<p>— António Marante</p></section>')
        misses = check_contract(packet, self.parts(page), 'pt')
        self.assertNotIn('home-10', [m['id'] for m in misses])

    def test_verbatim_segments_may_be_apart(self):
        packet = copy.deepcopy(PACKET)
        packet['content']['home']['required'].append(
            {'id': 'home-11', 'kind': 'Testimonial',
             'text': 'Somos um negócio de pessoas, não um negócio de web design. — António Marante'})
        page = ('<section><blockquote>«Somos um negócio de pessoas, não um negócio de web design.»</blockquote>'
                '</section>' + PAGE + '<section><p>Fundador — António Marante</p></section>')
        misses = check_contract(packet, self.parts(page), 'pt')
        self.assertNotIn('home-11', [m['id'] for m in misses])

    def test_verbatim_segment_missing_is_reported(self):
        packet = copy.deepcopy(PACKET)
        packet['content']['home']['required'].append(
            {'id': 'home-11', 'kind': 'Testimonial',
             'text': 'Somos um negócio de pessoas, não um negócio de web design. — António Marante'})
        page = ('<section><blockquote>«Somos um negócio de pessoas, não um negócio de web design.»</blockquote>'
                '</section>' + PAGE)
        misses = check_contract(packet, self.parts(page), 'pt')
        home_11_misses = [m for m in misses if m['id'] == 'home-11']
        self.assertEqual(len(home_11_misses), 1)
        self.assertIn('António Marante', home_11_misses[0]['reason'])

    def test_price_stays_strict(self):
        page = PAGE.replace('3,30 €', '330 €')
        misses = check_contract(PACKET, self.parts(page), 'pt')
        self.assertEqual([m['id'] for m in misses], ['home-4'])
        self.assertIn('price', misses[0]['reason'])

    def test_anchor_cta_matches_prefixed_anchor(self):
        packet = copy.deepcopy(PACKET)
        packet['content']['home']['required'] = [
            {'id': 'home-2', 'kind': 'CTA', 'text': 'Reservar mesa', 'href': '#contact'},
        ]
        packet['facts'] = {}
        parts = {'page': '<section><a href="/pt/#contact">Reservar mesa</a></section>', 'header': '<header></header>', 'footer': '<footer></footer>'}
        misses = check_contract(packet, parts, 'pt')
        self.assertEqual(misses, [])

    def test_address_with_br_and_commas(self):
        packet = copy.deepcopy(PACKET)
        packet['content']['home']['required'] = []
        packet['facts'] = dict(packet['facts'])
        packet['facts']['address'] = 'Rua do Castelo 1, Faro'
        parts = {'page': '<p>Rua do Castelo 1<br>Faro</p>', 'header': '<header></header>', 'footer': '<footer></footer>'}
        misses = check_contract(packet, parts, 'pt')
        self.assertFalse(any('address' in m['reason'] for m in misses))
