"""Tests for the content contract (Task 7)."""

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
