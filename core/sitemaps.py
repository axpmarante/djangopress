from django.contrib.sitemaps import Sitemap
from django.urls import reverse


class StaticViewSitemap(Sitemap):
    """Sitemap for static pages"""
    priority = 0.5
    changefreq = 'monthly'

    def items(self):
        return ['core:home', 'core:about', 'core:services', 'core:contact']

    def location(self, item):
        return reverse(item)
