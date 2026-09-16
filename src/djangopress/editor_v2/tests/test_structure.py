from bs4 import BeautifulSoup
from django.test import SimpleTestCase

from djangopress.editor_v2.structure import (
    signature_of, find_repeat_groups, path_from_section,
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

    def test_decorative_pairs_are_not_groups(self):
        html = ('<section data-section="x" id="x"><p class="lead">Line one<br class="hidden lg:inline">'
                'Line two<br class="hidden lg:inline">Line three</p>'
                '<svg viewBox="0 0 24 24"><path d="M1 1"/><path d="M2 2"/></svg></section>')
        self.assertEqual(find_repeat_groups(soup(html).section), [])

    def test_identical_siblings_get_distinct_paths(self):
        # Two unedited copies of the same card: bs4 Tag equality is structural,
        # so positions must be computed by identity, not ==.
        html = ('<section data-section="s" id="s"><div class="grid">'
                '<div class="card"><h3>Same</h3></div><div class="card"><h3>Same</h3></div>'
                '</div></section>')
        groups = find_repeat_groups(soup(html).section)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]['size'], 2)
        self.assertEqual(groups[0]['container_path'], 'div:nth-child(1)')
        self.assertFalse(groups[0]['nested'])
        # path of the second identical card must be nth-child(2)
        section = soup(html).section
        second = find_repeat_groups(section)[0]['items'][1]
        self.assertEqual(path_from_section(second, section), 'div:nth-child(1) > div:nth-child(2)')


from djangopress.editor_v2.structure import (
    shift_last_index, duplicate_node, move_node,
)

GRID = ('<section data-section="s" id="s"><div class="grid">'
        '<div class="card" id="c1"><h3 id="t1">A</h3></div>'
        '<div class="card"><h3>B</h3></div>'
        '</div></section>')
C1 = 'section[data-section="s"] > div:nth-child(1) > div:nth-child(1)'
C2 = 'section[data-section="s"] > div:nth-child(1) > div:nth-child(2)'
C3 = 'section[data-section="s"] > div:nth-child(1) > div:nth-child(3)'


class SelectorArithmeticTest(SimpleTestCase):
    def test_shift_last_index(self):
        self.assertEqual(shift_last_index(C1, 1), C2)
        self.assertEqual(shift_last_index(C2, -1), C1)

    def test_shift_section_selector_is_unchanged(self):
        self.assertEqual(shift_last_index('section[data-section="s"]', 1), 'section[data-section="s"]')


class DuplicateNodeTest(SimpleTestCase):
    def test_clone_is_inserted_after_and_ids_stripped(self):
        s = soup(GRID)
        new_sel = duplicate_node(s, C1)
        self.assertEqual(new_sel, C2)
        cards = s.select('section > div > div')
        self.assertEqual(len(cards), 3)
        self.assertEqual(cards[1].h3.get_text(), 'A')
        self.assertIsNone(cards[1].get('id'))
        self.assertIsNone(cards[1].h3.get('id'))
        self.assertEqual(cards[0].get('id'), 'c1')

    def test_missing_selector_returns_none(self):
        self.assertIsNone(duplicate_node(soup(GRID), C3))


class MoveNodeTest(SimpleTestCase):
    def test_move_down(self):
        s = soup(GRID)
        self.assertEqual(move_node(s, C1, 'down'), C2)
        self.assertEqual([c.h3.get_text() for c in s.select('section > div > div')], ['B', 'A'])

    def test_move_up(self):
        s = soup(GRID)
        self.assertEqual(move_node(s, C2, 'up'), C1)
        self.assertEqual([c.h3.get_text() for c in s.select('section > div > div')], ['B', 'A'])

    def test_move_at_edge_returns_none_and_changes_nothing(self):
        s = soup(GRID)
        self.assertIsNone(move_node(s, C1, 'up'))
        self.assertEqual([c.h3.get_text() for c in s.select('section > div > div')], ['A', 'B'])

    def test_whitespace_between_siblings_is_ignored(self):
        s = soup(GRID.replace('</div><div class="card">', '</div>\n  <div class="card">'))
        self.assertEqual(move_node(s, C2, 'up'), C1)
