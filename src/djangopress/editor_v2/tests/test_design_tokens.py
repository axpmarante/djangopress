"""The Design panel's swatches and fonts come from the site: SiteSettings first,
then the colours and fonts the pages actually use."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from djangopress.core.models import GlobalSection, Page, SiteSettings
from djangopress.editor_v2.design_tokens import collect_tokens

PAGE = ('<section data-section="a" id="a" class="bg-[#FBF7F0]"><h1 class="font-[\'Fraunces\'] text-[#c42014]">A</h1>'
        '<p class="text-[#14171B]">b</p><a class="bg-[#C42014] text-white">c</a><span class="text-[#3D3F44]">d</span></section>')


class DesignTokensTest(TestCase):
    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}]
        s.default_language = 'pt'
        s.primary_color = '#c42014'
        s.primary_color_hover = '#9C190F'
        s.secondary_color = '#E3A11C'
        s.accent_color = '#E3A11C'          # duplicate of secondary
        s.background_color = '#FBF7F0'
        s.text_color = '#14171B'
        s.heading_color = '#14171B'
        s.heading_font = 'Fraunces'
        s.body_font = 'Inter Tight'
        for n in range(1, 7):
            setattr(s, f'h{n}_font', 'Fraunces')
        s.save()
        Page.objects.all().delete()
        Page.objects.create(title_i18n={'pt': 'A'}, slug_i18n={'pt': 'a'}, is_active=True, html_content_i18n={'pt': PAGE})
        GlobalSection.objects.create(key='main-footer', name='Footer', section_type='footer',
                                     html_template_i18n={'pt': '<footer class="bg-[#0F1418] font-[\'Inter_Tight\']">x</footer>'})

    def test_named_colours_first_without_duplicates(self):
        colours = collect_tokens()['colors']
        names = [c['name'] for c in colours[:5]]
        self.assertEqual(names, ['Primary', 'Primary hover', 'Secondary', 'Background', 'Text'])
        self.assertEqual(colours[0]['value'], '#C42014')
        values = [c['value'] for c in colours]
        self.assertEqual(len(values), len(set(values)))

    def test_colours_used_on_the_site_follow_and_white_black_are_there(self):
        values = [c['value'] for c in collect_tokens()['colors']]
        self.assertIn('#3D3F44', values)            # used in a page, not in settings
        self.assertIn('#0F1418', values)            # used in the footer
        self.assertIn('#FFFFFF', values)
        self.assertIn('#000000', values)
        site = [c for c in collect_tokens()['colors'] if c['value'] == '#3D3F44'][0]
        self.assertEqual(site['name'], '#3D3F44')

    def test_fonts_from_settings_and_pages(self):
        fonts = collect_tokens()['fonts']
        self.assertEqual(fonts[:2], [{'role': 'Headings', 'family': 'Fraunces'}, {'role': 'Body', 'family': 'Inter Tight'}])
        self.assertEqual(len(fonts), 2)               # page fonts are the same two

    def test_presets(self):
        tokens = collect_tokens()
        self.assertEqual(tokens['spacing'], {'S': 40, 'M': 64, 'L': 104, 'XL': 152})
        self.assertEqual(tokens['buttonSizes']['M'], [14, 28, 15])

    def test_endpoint_is_for_editors(self):
        url = reverse('editor_v2:api_design_tokens')
        self.assertNotEqual(self.client.get(url).status_code, 200)
        staff = get_user_model().objects.create_user('ed', 'ed@x.com', 'pw', is_staff=True)
        self.client.force_login(staff)
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['success'])
        self.assertTrue(res.json()['colors'])
