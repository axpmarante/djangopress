from bs4 import BeautifulSoup
from django.test import SimpleTestCase

from djangopress.editor_v2.structure import (
    signature_of, find_repeat_groups,
)


def soup(html):
    return BeautifulSoup(html, 'html.parser')


CARDS = '''
<section data-section="services" id="services">
  <div class="container">
    <h2 class="title">Services</h2>
    <div class="grid">
      <div class="card"><h3>A</h3><p>a</p></div>
      <div class="card"><h3>B</h3><p>b</p></div>
      <div class="card"><h3>C</h3><p>c</p></div>
    </div>
  </div>
</section>'''

TWO_COLUMNS = '''
<section data-section="about" id="about">
  <div class="grid">
    <div class="col"><img src="x.jpg" alt=""></div>
    <div class="col"><h2>About</h2><p>text</p></div>
  </div>
</section>'''

NESTED = '''
<section data-section="faq" id="faq">
  <ul class="list">
    <li class="item"><h3>Q1</h3><ul class="tags"><li class="tag">a</li><li class="tag">b</li></ul></li>
    <li class="item"><h3>Q2</h3><ul class="tags"><li class="tag">c</li><li class="tag">d</li></ul></li>
  </ul>
</section>'''


class SignatureTest(SimpleTestCase):
    def test_signature_is_tag_plus_sorted_classes(self):
        t = soup('<div class="b a">x</div>').div
        self.assertEqual(signature_of(t), 'div|a b')

    def test_signature_ignores_editor_classes(self):
        t = soup('<div class="card ev2-selected">x</div>').div
        self.assertEqual(signature_of(t), 'div|card')


class FindRepeatGroupsTest(SimpleTestCase):
    def test_finds_card_grid(self):
        groups = find_repeat_groups(soup(CARDS).section)
        self.assertEqual(len(groups), 1)
        g = groups[0]
        self.assertEqual(g['size'], 3)
        self.assertEqual(g['signature'], 'div|card')
        self.assertEqual(g['container_path'], 'div:nth-child(1) > div:nth-child(2)')
        self.assertEqual(g['ambiguous'], '')
        self.assertFalse(g['nested'])

    def test_two_columns_with_different_children_are_ambiguous(self):
        groups = find_repeat_groups(soup(TWO_COLUMNS).section)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]['ambiguous'], 'pair-with-different-children')

    def test_nested_groups_are_flagged(self):
        groups = find_repeat_groups(soup(NESTED).section)
        items = [g for g in groups if g['signature'] == 'li|item']
        tags = [g for g in groups if g['signature'] == 'li|tag']
        self.assertEqual(len(items), 1)
        self.assertFalse(items[0]['nested'])
        # each <ul class="tags"> is its own container, so two nested groups of two
        self.assertEqual(len(tags), 2)
        self.assertTrue(all(g['nested'] for g in tags))
        self.assertEqual([g['size'] for g in tags], [2, 2])

    def test_single_child_is_not_a_group(self):
        groups = find_repeat_groups(soup('<section data-section="x"><div><p class="a">1</p></div></section>').section)
        self.assertEqual(groups, [])
