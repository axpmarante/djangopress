"""Tests for crop_mockup and sample_palette."""

import json
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import SimpleTestCase
from PIL import Image


class CropMockupTest(SimpleTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = Path(self.tmp.name) / 'master.png'
        Image.new('RGB', (100, 400), (200, 200, 200)).save(self.src)
        self.out = Path(self.tmp.name) / 'crops' / 'hero.png'

    def tearDown(self):
        self.tmp.cleanup()

    def test_crops_by_fractions(self):
        out = StringIO()
        call_command('crop_mockup', str(self.src), str(self.out), '--top', '0.25', '--bottom', '0.5', stdout=out)
        with Image.open(self.out) as im:
            self.assertEqual(im.size, (100, 100))
        self.assertIn('wrote', out.getvalue())
        self.assertIn('100x100', out.getvalue())

    def test_rejects_bad_fractions(self):
        for top, bottom in (('0.6', '0.5'), ('-0.1', '0.5'), ('0.2', '1.2')):
            with self.assertRaises(SystemExit):
                call_command('crop_mockup', str(self.src), str(self.out), '--top', top, '--bottom', bottom)

    def test_missing_source(self):
        with self.assertRaises(SystemExit):
            call_command('crop_mockup', str(self.src.with_name('nope.png')), str(self.out), '--top', '0', '--bottom', '0.5')


class SamplePaletteTest(SimpleTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = Path(self.tmp.name) / 'img.png'
        im = Image.new('RGB', (90, 30))
        px = im.load()
        for x in range(90):
            for y in range(30):
                px[x, y] = (245, 240, 232) if x < 45 else ((192, 91, 62) if x < 75 else (62, 107, 115))
        im.save(self.src)

    def tearDown(self):
        self.tmp.cleanup()

    def test_kmeans_finds_three_colors_with_shares(self):
        from djangopress.ai.management.commands.sample_palette import kmeans_palette
        pixels = [(245, 240, 232)] * 50 + [(192, 91, 62)] * 30 + [(62, 107, 115)] * 20
        result = kmeans_palette(pixels, k=3)
        self.assertEqual(len(result), 3)
        colors = [c for c, _ in result]
        shares = [s for _, s in result]
        self.assertEqual(shares, sorted(shares, reverse=True))
        self.assertAlmostEqual(sum(shares), 1.0, places=6)
        for target in ((245, 240, 232), (192, 91, 62), (62, 107, 115)):
            self.assertTrue(any(all(abs(a - b) <= 2 for a, b in zip(c, target)) for c in colors), target)

    def test_json_output(self):
        out = StringIO()
        call_command('sample_palette', str(self.src), '--k', '3', '--json', stdout=out)
        data = json.loads(out.getvalue())
        self.assertEqual(len(data), 3)
        self.assertEqual(data[0]['hex'].lower(), '#f5f0e8')
        self.assertAlmostEqual(data[0]['share'], 0.5, places=1)

    def test_text_output(self):
        out = StringIO()
        call_command('sample_palette', str(self.src), '--k', '3', stdout=out)
        lines = out.getvalue().strip().splitlines()
        self.assertEqual(len(lines), 3)
        self.assertRegex(lines[0], r'^#[0-9a-f]{6}\s+\d+\.\d%$')
