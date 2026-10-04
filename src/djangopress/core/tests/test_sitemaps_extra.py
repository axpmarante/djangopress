from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from djangopress.core.sitemaps import PageSitemap
from djangopress.urls import build_sitemaps


class SitemapsExtraTests(SimpleTestCase):
    def test_pages_only_by_default(self):
        self.assertEqual(build_sitemaps({}), {'pages': PageSitemap})

    def test_extra_entries_are_imported(self):
        self.assertEqual(build_sitemaps({'more': 'djangopress.core.sitemaps.PageSitemap'}),
                         {'pages': PageSitemap, 'more': PageSitemap})

    def test_a_wrong_path_names_the_entry(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "SITEMAPS_EXTRA['shop']"):
            build_sitemaps({'shop': 'nope.Missing'})
