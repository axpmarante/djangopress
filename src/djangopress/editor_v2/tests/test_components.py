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
