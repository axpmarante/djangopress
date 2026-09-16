import json
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from djangopress.core.models import Page, SiteSettings


HTML = ('<section data-section="services" id="services"><div class="grid">'
        '<div class="card"><h3>A</h3></div><div class="card"><h3>B</h3></div></div></section>'
        '<section data-section="hero" id="hero"><h1>Hi</h1></section>')


class AuditRepeatGroupsTest(TestCase):
    def setUp(self):
        Page.objects.all().delete()
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}]
        s.default_language = 'pt'
        s.save()
        Page.objects.create(title_i18n={'pt': 'Home'}, slug_i18n={'pt': 'home'},
                            is_active=True, html_content_i18n={'pt': HTML})

    def test_json_output_lists_groups_per_section(self):
        out = StringIO()
        call_command('audit_repeat_groups', '--json', stdout=out)
        data = json.loads(out.getvalue())
        self.assertEqual(data['pages'][0]['slug'], 'home')
        sections = {s['name']: s for s in data['pages'][0]['sections']}
        self.assertEqual(sections['services']['groups'][0]['size'], 2)
        self.assertEqual(sections['services']['groups'][0]['signature'], 'div|card')
        self.assertEqual(sections['hero']['groups'], [])

    def test_markdown_output_has_a_table(self):
        out = StringIO()
        call_command('audit_repeat_groups', stdout=out)
        text = out.getvalue()
        self.assertIn('| services |', text)
        self.assertIn('div|card', text)
