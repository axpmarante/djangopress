"""Tests for the language switcher.

The switcher has to cope with two kinds of address, and they need two different
mechanisms:

* A CMS page's address comes from data — `Page.slug_i18n` — so only a database
  lookup turns `/en/our-wines/` into `/pt/vinhos/`.
* A decoupled app's address comes from the URLconf, where the prefix is a
  lazily translated string, so only resolving and reversing turns `/en/shop/`
  into `/pt/loja/`.

Before this was fixed the switcher only did the first. On any site with a
decoupled app, changing language from one of that app's pages kept the
source-language segment and sent the visitor to a 404.

The app-URL cases are asserted against `translate_url` being consulted rather
than against a particular translated prefix: which prefixes exist is a property
of each site's catalogue, not of the engine, so a test that hard-coded one
would pass or fail for reasons that have nothing to do with this view.
"""

from unittest.mock import patch

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from djangopress.core.models import Page


@override_settings(LANGUAGES=[('en', 'English'), ('pt', 'Português')])
class SetLanguageTests(TestCase):
    def setUp(self):
        self.url = reverse('set_language')

    def _switch(self, to, from_url):
        return self.client.post(self.url, {'language': to, 'next': from_url})

    def test_a_cms_page_switches_to_its_translated_slug(self):
        Page.objects.create(
            title_i18n={'en': 'About', 'pt': 'Sobre Nós'},
            slug_i18n={'en': 'about', 'pt': 'sobre-nos'},
            is_active=True,
        )
        self.assertEqual(self._switch('pt', '/en/about/')['Location'], '/pt/sobre-nos/')

    def test_a_cms_page_does_not_consult_the_urlconf(self):
        """A page's slug is data. Reversing would only ever get it wrong."""
        Page.objects.create(
            title_i18n={'en': 'About', 'pt': 'Sobre Nós'},
            slug_i18n={'en': 'about', 'pt': 'sobre-nos'},
            is_active=True,
        )
        with patch('djangopress.core.views.translate_url') as translate:
            response = self._switch('pt', '/en/about/')
        translate.assert_not_called()
        self.assertEqual(response['Location'], '/pt/sobre-nos/')

    def test_the_bare_language_root_switches(self):
        self.assertEqual(self._switch('pt', '/en/')['Location'], '/pt/')

    def test_an_unknown_language_is_refused(self):
        self.assertEqual(self._switch('de', '/en/about/')['Location'], '/')

    def test_the_cookie_is_set_to_the_target_language(self):
        response = self._switch('pt', '/en/')
        self.assertEqual(response.cookies[settings.LANGUAGE_COOKIE_NAME].value, 'pt')


@override_settings(LANGUAGES=[('en', 'English'), ('pt', 'Português')])
class SetLanguageAppUrlTests(TestCase):
    """What happens when the path is not a CMS page."""

    def setUp(self):
        self.url = reverse('set_language')

    def _switch(self, to, from_url):
        return self.client.post(self.url, {'language': to, 'next': from_url})

    def test_a_non_page_url_is_translated_through_the_urlconf(self):
        with patch('djangopress.core.views.translate_url',
                   return_value='/pt/loja/') as translate:
            response = self._switch('pt', '/en/shop/')
        translate.assert_called_once()
        self.assertEqual(translate.call_args.args[1], 'pt')
        self.assertEqual(response['Location'], '/pt/loja/')

    def test_resolution_happens_with_the_source_language_active(self):
        """`/en/shop/` only resolves while English is active.

        Under any other language the English prefix is not in the URLconf, so
        `translate_url` would quietly hand back what it was given.
        """
        from django.utils import translation

        seen = {}

        def record(url, lang):
            seen['active'] = translation.get_language()
            return '/pt/loja/'

        with patch('djangopress.core.views.translate_url', side_effect=record):
            self._switch('pt', '/en/shop/')
        self.assertEqual(seen['active'], 'en')

    def test_an_untranslatable_path_still_lands_in_the_target_language(self):
        """No page, and nothing the URLconf can reverse: fall back cleanly."""
        with patch('djangopress.core.views.translate_url',
                   side_effect=lambda url, lang: url):
            response = self._switch('pt', '/en/nothing-here/')
        self.assertTrue(response['Location'].startswith('/pt/'))
        self.assertNotIn('/en/', response['Location'])
