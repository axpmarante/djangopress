"""The editor's ES modules are loaded through an import map that pins every module
to a version of its content, so a browser never mixes cached and new modules."""
import hashlib
import json
import re
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase

from djangopress.core.models import Page, SiteSettings
from djangopress.editor_v2.templatetags.editor_assets import JS_ROOT, module_map


def importmap(html):
    m = re.search(r'<script type="importmap">(.*?)</script>', html, re.S)
    return json.loads(m.group(1))['imports'] if m else None


class ImportMapTest(TestCase):
    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}]
        s.default_language = 'pt'
        s.save()
        Page.objects.all().delete()
        self.page = Page.objects.create(title_i18n={'pt': 'A'}, slug_i18n={'pt': 'a'}, is_active=True,
                                        html_content_i18n={'pt': '<section data-section="a" id="a"><h1>A</h1></section>'})
        self.staff = get_user_model().objects.create_user('ed', 'ed@x.com', 'pw', is_staff=True)

    def get(self, query):
        return self.client.get(self.page.get_absolute_url() + query, follow=True).content.decode()

    def test_every_module_is_pinned_to_its_content(self):
        imports = module_map()
        files = sorted(JS_ROOT.rglob('*.js'))
        self.assertEqual(len(imports), len(files))
        sidebar = JS_ROOT / 'modules' / 'sidebar.js'
        digest = hashlib.md5(sidebar.read_bytes()).hexdigest()[:10]
        self.assertEqual(imports['/static/editor_v2/js/modules/sidebar.js'], f'/static/editor_v2/js/modules/sidebar.js?v={digest}')

    def test_editor_and_frame_pages_carry_it_before_any_module(self):
        self.client.force_login(self.staff)
        for query in ('?edit=v2', '?ev2_frame=1'):
            html = self.get(query)
            imports = importmap(html)
            self.assertIsNotNone(imports, query)
            self.assertIn('/static/editor_v2/js/lib/dom.js', imports)
            self.assertLess(html.index('type="importmap"'), html.index('type="module"'), query)

    def test_public_pages_have_none(self):
        self.assertIsNone(importmap(self.get('')))
