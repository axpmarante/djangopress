"""validate_contacts: wrong / inconsistent / can't-verify contact details across
settings, pages and header/footer, in every language. Read-only."""
from unittest import mock

from django.test import TestCase

from djangopress.core.models import GlobalSection, Page, SiteSettings
from djangopress.site_assistant import contacts
from djangopress.site_assistant.tools import ToolRegistry

DOMAIN = 'djangopress.site_assistant.contacts.mail_domain_status'
FOOTER = ('<footer><a href="tel:+351289000000">+351 289 000 000</a> '
          '<a href="mailto:geral@restaurante.pt">geral@restaurante.pt</a></footer>')


class ContactsTest(TestCase):
    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.site_name_i18n = {'pt': 'Restaurante Mar', 'en': 'Restaurante Mar'}
        s.contact_phone = '+351 289 000 000'
        s.contact_email = 'geral@restaurante.pt'
        s.whatsapp_number = '+351912345678'
        s.contact_address_i18n = {'pt': 'Rua do Mar 1, Faro'}
        s.google_maps_embed_url = 'https://www.google.com/maps/embed?pb=!1m18'
        s.save()
        GlobalSection.objects.create(key='main-footer', name='Footer', section_type='footer',
                                     html_template_i18n={'pt': FOOTER, 'en': FOOTER})

    def page(self, pt, en=None, title='Contactos'):
        return Page.objects.create(title_i18n={'pt': title}, slug_i18n={'pt': title.lower()}, is_active=True,
                                   html_content_i18n={'pt': pt, 'en': en if en is not None else pt})

    def check(self, **params):
        with mock.patch(DOMAIN, return_value='ok'):
            return ToolRegistry.execute('validate_contacts', params, {})

    def levels(self, out, level):
        return [i for i in out['issues'] if i['level'] == level]

    def test_all_consistent(self):
        self.page('<section data-section="c"><p>Ligue <a href="tel:289000000">289 000 000</a></p>'
                  '<a href="https://wa.me/351912345678">WhatsApp</a></section>')
        out = self.check()
        self.assertTrue(out['success'], out)
        self.assertEqual(out['issues'], [], out['issues'])

    def test_tel_link_that_dials_another_number(self):
        self.page('<section data-section="c"><a href="tel:+351289000001">+351 289 000 000</a></section>')
        wrong = self.levels(self.check(), 'wrong')
        self.assertTrue(any('dials' in i['what'] for i in wrong), wrong)
        self.assertEqual(wrong[0]['where']['section'], 'c')

    def test_a_different_phone_on_one_page_in_one_language(self):
        self.page('<section data-section="c"><p>Tel. 289 000 000</p></section>',
                  en='<section data-section="c"><p>Phone 289 111 222</p></section>')
        inconsistent = self.levels(self.check(), 'inconsistent')
        self.assertEqual(len(inconsistent), 1, inconsistent)
        self.assertEqual(inconsistent[0]['where']['lang'], 'en')
        self.assertIn('289 111 222', inconsistent[0]['what'])

    def test_bad_email_and_bad_phone(self):
        self.page('<section data-section="c"><a href="mailto:geral@restaurante">escreva-nos</a></section>')
        s = SiteSettings.load()
        s.contact_phone = '12345'
        s.save()
        wrong = [i['what'] for i in self.levels(self.check(), 'wrong')]
        self.assertTrue(any('geral@restaurante' in w for w in wrong), wrong)
        self.assertTrue(any('12345' in w for w in wrong), wrong)

    def test_email_domain_without_mail_server(self):
        with mock.patch(DOMAIN, side_effect=lambda d: 'no_mx' if d == 'restaurante.pt' else 'ok'):
            out = ToolRegistry.execute('validate_contacts', {}, {})
        self.assertTrue(any('restaurante.pt' in i['what'] for i in self.levels(out, 'wrong')), out['issues'])

    def test_offline_domain_check_is_cant_verify(self):
        with mock.patch(DOMAIN, return_value='unknown'):
            out = ToolRegistry.execute('validate_contacts', {}, {})
        self.assertTrue(self.levels(out, 'cant_verify'))
        self.assertFalse(self.levels(out, 'wrong'))

    def test_maps_url_that_is_not_an_embed(self):
        s = SiteSettings.load()
        s.google_maps_embed_url = 'https://maps.app.goo.gl/abc'
        s.save()
        self.assertTrue(any('Maps' in i['what'] for i in self.levels(self.check(), 'wrong')))

    def test_web_check_compares_and_cites(self):
        found = {'text': 'Restaurante Mar, Rua do Mar 1, Faro. Telefone 289 999 999.',
                 'sources': [{'title': 'Guia', 'url': 'https://guia.pt/mar'}], 'queries': []}
        with mock.patch(DOMAIN, return_value='ok'), \
                mock.patch('djangopress.ai.utils.llm_config.LLMBase.web_search', return_value=found):
            out = ToolRegistry.execute('validate_contacts', {'check_web': True}, {})
        web = [i for i in out['issues'] if i.get('sources')]
        self.assertTrue(web, out['issues'])
        self.assertIn('289 999 999', web[0]['what'])
        self.assertEqual(out['sources'][0]['url'], 'https://guia.pt/mar')

    def test_template_variables_are_not_errors(self):
        GlobalSection.objects.filter(key='main-footer').update(html_template_i18n={
            'pt': '<footer><a href="mailto:{{ CONTACT_EMAIL }}">{{ CONTACT_EMAIL }}</a> {{ CONTACT_PHONE }}</footer>'})
        self.assertEqual(self.check()['issues'], [])

    def test_one_issue_per_differing_number_listing_the_places(self):
        self.page('<section data-section="c"><p>Fixo 289 824 178</p></section>', title='Contactos')
        self.page('<section data-section="r"><p>Fixo 289 824 178</p></section>', title='Reservas')
        inconsistent = self.levels(self.check(), 'inconsistent')
        self.assertEqual(len(inconsistent), 1, inconsistent)
        self.assertEqual(len(inconsistent[0]['places']), 4)
        self.assertIn('Contactos', inconsistent[0]['what'])
        self.assertIn('Reservas', inconsistent[0]['what'])

    def test_without_web_check_the_result_says_the_web_was_not_checked(self):
        out = self.check()
        self.assertIn('not compared with the web', out['message'])
        self.assertEqual(out['sources'], [])

    def test_phone_normalisation(self):
        self.assertEqual(contacts.normalise_phone('289 000 000'), '351289000000')
        self.assertEqual(contacts.normalise_phone('+351 912-345-678'), '351912345678')
        self.assertEqual(contacts.normalise_phone('00351 912345678'), '351912345678')
        self.assertEqual(contacts.normalise_phone('+44 20 7946 0958'), '442079460958')
