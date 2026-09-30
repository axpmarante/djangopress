from pathlib import Path

from bs4 import BeautifulSoup
from django.test import SimpleTestCase

from djangopress.editor_v2 import components

FIXTURES = Path(__file__).parent / 'fixtures' / 'components'


def load(name):
    return BeautifulSoup((FIXTURES / f'{name}.html').read_text(), 'html.parser')


class FixtureRecognitionTest(SimpleTestCase):
    """Every fixture declares what the editor must recognise (shared with the JS harness)."""

    def test_fixtures(self):
        names = sorted(p.stem for p in FIXTURES.glob('*.html'))
        self.assertGreaterEqual(len(names), 9)
        for name in names:
            with self.subTest(fixture=name):
                soup = load(name)
                section = soup.find('section')
                found = components.find_for(soup.select_one('[data-probe]'))
                expect = section['data-expect-kind']
                if expect == 'none':
                    self.assertIsNone(found)
                    continue
                root, kind = found
                self.assertEqual(kind, expect)
                its = components.items(root, kind)
                self.assertEqual(len(its), int(section['data-expect-count']))
                leaves = components.text_leaves(its[0])
                self.assertEqual(len(leaves), int(section['data-expect-texts']))
                self.assertEqual(sum(components.is_editable_leaf(l) for l in leaves), int(section['data-expect-editable']))
                self.assertEqual(1 if components.image_of(its[0]) else 0, int(section['data-expect-image']))


class TextTest(SimpleTestCase):
    def test_read_text_collapses_source_whitespace_and_keeps_br(self):
        el = BeautifulSoup('<p>\n  Linha   um<br/>linha\n dois </p>', 'html.parser').p
        self.assertEqual(components.read_text(el), 'Linha um\nlinha dois')

    def test_write_text_turns_newlines_into_br(self):
        soup = BeautifulSoup('<p>old <br/>text</p>', 'html.parser')
        components.write_text(soup.p, 'Novo\ntexto')
        self.assertEqual(str(soup.p), '<p>Novo<br/>texto</p>')


class FindComponentTest(SimpleTestCase):
    def test_find_component_checks_kind(self):
        soup = load('hero_fade')
        sel = 'section[data-section="foto"] > div:nth-child(1)'
        self.assertIsNotNone(components.find_component(soup, sel, 'slider'))
        self.assertIsNone(components.find_component(soup, sel, 'gallery'))
        self.assertIsNone(components.find_component(soup, 'section[data-section="nope"] > div:nth-child(1)', 'slider'))

    def test_min_items(self):
        soup = load('gallery_grid')
        grid = soup.select_one('.grid')
        self.assertEqual(components.min_items(grid, 'gallery'), 2)
        hinted = load('gallery_hint').select_one('[data-media-collection]')
        self.assertEqual(components.min_items(hinted, 'gallery'), 1)
        self.assertEqual(components.min_items(load('hero_fade').select_one('.splide'), 'slider'), 1)

    def test_runtime_class_re(self):
        for c in ('is-active', 'is-visible', 'is-prev', 'is-next', 'splide--fade', 'splide__slide--clone', 'ev2-selected'):
            self.assertTrue(components.RUNTIME_CLASS_RE.match(c), c)
        for c in ('splide', 'splide__slide', 'is-large', 'pb-12'):
            self.assertFalse(components.RUNTIME_CLASS_RE.match(c), c)


import json as _json


def comp(name):
    soup = load(name)
    root, kind = components.find_for(soup.select_one('[data-probe]'))
    return soup, root, kind


def srcs(root, kind):
    return [components.image_of(i)['src'].rsplit('/', 1)[-1] for i in components.items(root, kind)]


class OperationsTest(SimpleTestCase):
    def test_reorder_is_a_permutation_by_slot(self):
        soup, root, kind = comp('loop_carousel')
        components.reorder(root, kind, [3, 0, 1, 2])
        self.assertEqual(srcs(root, kind), ['4.jpg', '1.jpg', '2.jpg', '3.jpg'])
        # the pre-baked clone keeps its place, first in the list
        self.assertIn('splide__slide--clone', soup.select('.splide__list > li')[0]['class'])

    def test_reorder_rejects_non_permutation(self):
        _, root, kind = comp('hero_fade')
        for bad in ([0, 1], [0, 0, 1], [0, 1, 5], 'x', [True, 0, 1]):
            with self.assertRaises(ValueError):
                components.reorder(root, kind, bad)

    def test_reorder_gallery_keeps_non_items_in_place(self):
        soup = BeautifulSoup('<section data-section="s"><div class="g"><h3>T</h3>'
                             '<a href="/1.jpg" data-lightbox="g"><img src="/1.jpg"/></a>'
                             '<a href="/2.jpg" data-lightbox="g"><img src="/2.jpg"/></a></div></section>', 'html.parser')
        root = soup.select_one('.g')
        components.reorder(root, 'gallery', [1, 0])
        self.assertEqual([c.name for c in root.find_all(True, recursive=False)], ['h3', 'a', 'a'])
        self.assertEqual(root.select('a')[0]['href'], '/2.jpg')

    def test_remove_and_focus(self):
        _, root, kind = comp('hero_fade')
        self.assertEqual(components.remove(root, kind, 2), 1)
        self.assertEqual(srcs(root, kind), ['a.jpg', 'b.jpg'])

    def test_remove_refuses_below_minimum(self):
        _, root, kind = comp('hero_fade')
        components.remove(root, kind, 0)
        components.remove(root, kind, 0)
        with self.assertRaises(ValueError):
            components.remove(root, kind, 0)
        soup = BeautifulSoup('<section data-section="s"><div class="g">'
                             '<a href="/1.jpg" data-lightbox="g"><img src="/1.jpg"/></a>'
                             '<a href="/2.jpg" data-lightbox="g"><img src="/2.jpg"/></a></div></section>', 'html.parser')
        with self.assertRaises(ValueError):
            components.remove(soup.select_one('.g'), 'gallery', 0)

    def test_remove_rejects_bad_index(self):
        _, root, kind = comp('hero_fade')
        for bad in (-1, 3, '1', None, True):
            with self.assertRaises(ValueError):
                components.remove(root, kind, bad)

    def test_set_settings_merges_and_deletes(self):
        _, root, kind = comp('hero_fade')
        components.set_settings(root, {'type': 'loop', 'rewind': None, 'interval': 3000})
        opts = _json.loads(root['data-splide'])
        self.assertEqual(opts['type'], 'loop')
        self.assertNotIn('rewind', opts)
        self.assertEqual(opts['interval'], 3000)
        self.assertEqual(opts['arrowPath'], 'M15 6 L29 20 L15 34')   # unknown key preserved

    def test_set_settings_validates(self):
        _, root, kind = comp('hero_fade')
        for bad in ({'type': 'cube'}, {'autoplay': 'yes'}, {'interval': 10}, {'perPage': 0},
                    {'arrowPath': 'x'}, {'breakpoints': []}, 'nope'):
            with self.assertRaises(ValueError):
                components.set_settings(root, bad)

    def test_set_settings_refuses_invalid_json(self):
        _, root, kind = comp('hero_fade')
        root['data-splide'] = '{type: fade'
        with self.assertRaises(ValueError):
            components.set_settings(root, {'autoplay': False})
        self.assertEqual(root['data-splide'], '{type: fade')

    def test_set_settings_only_on_sliders(self):
        _, root, kind = comp('gallery_grid')
        with self.assertRaises(ValueError):
            components.set_settings(root, {'autoplay': False})

    def test_replace_image_syncs_lightbox_and_drops_srcset(self):
        _, root, kind = comp('gallery_grid')
        item = components.items(root, kind)[1]
        components.image_of(item)['srcset'] = 'x 1x'
        components.replace_image(root, kind, 1, 'https://example.com/new.jpg', 'Novo')
        img = components.image_of(item)
        self.assertEqual((img['src'], img['alt']), ('https://example.com/new.jpg', 'Novo'))
        self.assertNotIn('srcset', img.attrs)
        self.assertEqual(item['href'], 'https://example.com/new.jpg')
        self.assertEqual(item['data-alt'], 'Novo')

    def test_replace_image_rejects_unsafe_url(self):
        _, root, kind = comp('hero_fade')
        for bad in ('javascript:alert(1)', 'data:text/html,x', ''):
            with self.assertRaises(ValueError):
                components.replace_image(root, kind, 0, bad, 'x')

    def test_add_images_clones_the_anchor_item(self):
        _, root, kind = comp('loop_carousel')
        first_new = components.add_images(root, kind, 1, [('/n1.jpg', 'N1'), ('/n2.jpg', 'N2')])
        self.assertEqual(first_new, 2)
        self.assertEqual(srcs(root, kind), ['1.jpg', '2.jpg', 'n1.jpg', 'n2.jpg', '3.jpg', '4.jpg'])
        new = components.items(root, kind)[2]
        self.assertEqual(new['class'], ['splide__slide'])
        self.assertEqual(components.image_of(new)['alt'], 'N1')

    def test_add_text_item_writes_leaves(self):
        _, root, kind = comp('testimonials')
        idx = components.add_text_item(root, kind, 0, {'0': '“Excelente.”', '1': 'Rui · Google'})
        self.assertEqual(idx, 1)
        leaves = components.text_leaves(components.items(root, kind)[1])
        self.assertEqual([components.read_text(l) for l in leaves], ['“Excelente.”', 'Rui · Google'])
        self.assertEqual(leaves[0]['class'], ['text-2xl'])

    def test_add_text_item_refuses_empty_and_formatted(self):
        _, root, kind = comp('testimonials')
        with self.assertRaises(ValueError):
            components.add_text_item(root, kind, 0, {'0': '   '})
        _, root, kind = comp('card_carousel')
        with self.assertRaises(ValueError):   # leaf 1 has <strong>: not editable
            components.add_text_item(root, kind, 0, {'1': 'x'})

    def test_update_item(self):
        _, root, kind = comp('gallery_grid')
        components.update_item(root, kind, 0, alt='Sala grande', caption='A sala')
        item = components.items(root, kind)[0]
        self.assertEqual(components.image_of(item)['alt'], 'Sala grande')
        self.assertEqual(item['data-alt'], 'A sala')
        _, root, kind = comp('testimonials')
        components.update_item(root, kind, 2, texts={'1': 'Ana M. · Google'})
        self.assertEqual(components.read_text(components.text_leaves(components.items(root, kind)[2])[1]), 'Ana M. · Google')

    def test_update_item_rejects_missing_targets(self):
        _, root, kind = comp('testimonials')
        with self.assertRaises(ValueError):
            components.update_item(root, kind, 0, alt='x')        # no image
        with self.assertRaises(ValueError):
            components.update_item(root, kind, 0, caption='x')    # no lightbox link
        with self.assertRaises(ValueError):
            components.update_item(root, kind, 0, texts={'7': 'x'})
