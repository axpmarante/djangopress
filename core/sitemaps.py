from django.contrib.sitemaps import Sitemap
from .models import Page


class PageSitemap(Sitemap):
    changefreq = 'weekly'
    priority = 0.7

    def items(self):
        return Page.objects.filter(is_active=True)

    def location(self, obj):
        return obj.get_absolute_url()

    def lastmod(self, obj):
        return obj.updated_at
