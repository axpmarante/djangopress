from unittest import mock

from django.test import SimpleTestCase

from djangopress.editor_v2.component_translate import translate_texts

SERVICE = 'djangopress.ai.services.ContentGenerationService'


class TranslateTextsTest(SimpleTestCase):
    def test_round_trip_keeps_order_and_line_breaks(self):
        with mock.patch(SERVICE) as svc:
            svc.return_value.translate_html.return_value = (
                '<p data-i="0">Great<br>food</p><p data-i="1">Rui &amp; Ana</p>')
            out = translate_texts(['Ótima\ncomida', 'Rui & Ana'], 'pt', 'en')
        self.assertEqual(out, ['Great\nfood', 'Rui & Ana'])
        snippet = svc.return_value.translate_html.call_args[0][0]
        self.assertIn('<p data-i="0">Ótima<br>comida</p>', snippet)
        self.assertIn('Rui &amp; Ana', snippet)

    def test_failure_returns_none(self):
        with mock.patch(SERVICE) as svc:
            svc.return_value.translate_html.side_effect = RuntimeError('no key')
            self.assertIsNone(translate_texts(['Olá'], 'pt', 'en'))

    def test_missing_or_empty_output_returns_none(self):
        with mock.patch(SERVICE) as svc:
            svc.return_value.translate_html.return_value = '<p data-i="0"> </p>'
            self.assertIsNone(translate_texts(['Olá'], 'pt', 'en'))
            svc.return_value.translate_html.return_value = 'Hello'
            self.assertIsNone(translate_texts(['Olá'], 'pt', 'en'))

    def test_empty_input(self):
        self.assertEqual(translate_texts([], 'pt', 'en'), [])
