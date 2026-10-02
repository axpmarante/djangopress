"""The design check snaps generated HTML back onto the site's palette and fonts
and reads the model's one-line rationale."""
from django.test import SimpleTestCase

from djangopress.ai.design_check import check_and_fix

COLORS = [{'name': 'Primary', 'value': '#C42014'}, {'name': 'Gold', 'value': '#E3A11C'},
          {'name': 'Cream', 'value': '#FBF7F0'}, {'name': 'Ink', 'value': '#14171B'},
          {'name': 'White', 'value': '#FFFFFF'}, {'name': 'Black', 'value': '#000000'}]
FONTS = [{'role': 'Headings', 'family': 'Fraunces'}, {'role': 'Body', 'family': 'Inter Tight'}]


def run(html, colors=COLORS, fonts=FONTS):
    return check_and_fix(html, colors, fonts)


class DesignCheckTest(SimpleTestCase):
    def test_a_generic_blue_becomes_the_nearest_brand_colour(self):
        out = run('<section><a class="px-4 bg-blue-600 text-white">x</a></section>')
        self.assertIn('class="px-4 bg-[#C42014] text-white"', out['html'])
        self.assertTrue(any('bg-blue-600' in n for n in out['notes']))

    def test_yellow_goes_to_gold_and_variants_and_opacity_are_kept(self):
        out = run('<div class="md:hover:bg-amber-500/80 text-yellow-400">x</div>')
        self.assertIn('md:hover:bg-[#E3A11C]/80', out['html'])
        self.assertIn('text-[#E3A11C]', out['html'])

    def test_greys_stay_when_the_site_has_no_near_neutral(self):
        out = run('<p class="text-gray-500">x</p>', colors=[{'name': 'Primary', 'value': '#C42014'}])
        self.assertIn('text-gray-500', out['html'])

    def test_greys_snap_to_a_near_site_neutral(self):
        out = run('<p class="text-slate-900">x</p>')
        self.assertIn('text-[#14171B]', out['html'])

    def test_near_hex_snaps_far_hex_is_noted(self):
        out = run('<div class="bg-[#C5221A] text-[#1E90FF]">x</div>')
        self.assertIn('bg-[#C42014]', out['html'])
        self.assertIn('text-[#1E90FF]', out['html'])
        self.assertIn('off-palette colour #1E90FF', out['notes'])

    def test_site_hex_in_any_case_is_untouched(self):
        out = run('<div class="bg-[#c42014]">x</div>')
        self.assertIn('bg-[#c42014]', out['html'])
        self.assertEqual(out['notes'], [])

    def test_foreign_fonts_become_the_site_fonts_by_role(self):
        out = run("<section><h2 class=\"font-['Playfair_Display'] text-4xl\">T<span class=\"font-[Lora]\">x</span></h2>"
                  "<p class=\"font-['Roboto']\">b</p><p class=\"font-['Inter_Tight']\">ok</p></section>")
        self.assertIn("font-['Fraunces'] text-4xl", out['html'])
        self.assertIn('<span class="font-[\'Fraunces\']">', out['html'])
        self.assertIn("<p class=\"font-['Inter_Tight']\">b</p>", out['html'])
        self.assertIn("font Playfair Display → Fraunces", out['notes'])
        self.assertEqual(sum('→' in n for n in out['notes']), 3)

    def test_font_weight_classes_are_not_fonts(self):
        out = run('<p class="font-semibold font-light">x</p>')
        self.assertIn('font-semibold font-light', out['html'])

    def test_why_is_read_and_removed(self):
        out = run('<section data-section="a"><!-- WHY: Reuses the gold divider from the hero. --><h2>x</h2></section>')
        self.assertEqual(out['why'], 'Reuses the gold divider from the hero.')
        self.assertNotIn('WHY', out['html'])
        self.assertTrue(out['html'].startswith('<section data-section="a"><h2>'))

    def test_no_why(self):
        self.assertEqual(run('<div>x</div>')['why'], '')

    def test_placeholders_are_counted(self):
        out = run('<div><img src="https://placehold.co/600x400?text=A"><img src="https://placehold.co/1x1"></div>')
        self.assertIn('2 placeholder image(s)', out['notes'])

    def test_untouched_markup_is_kept(self):
        html = '<section data-section="x" class="py-24"><p class="text-[#C42014]">Olá &amp; adeus</p></section>'
        self.assertEqual(run(html)['html'], html)
