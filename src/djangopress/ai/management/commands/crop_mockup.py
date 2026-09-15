"""
crop_mockup — cut a horizontal band out of a mockup by height fractions.

Usage:
    python manage.py crop_mockup docs/mockups/00-master.png docs/mockups/crops/01-hero.png --top 0.00 --bottom 0.17

The crop is the second reference image when a section is rendered: the
master gives the design system, the crop gives the local composition.
"""

import sys
from pathlib import Path

from django.core.management.base import BaseCommand
from PIL import Image


class Command(BaseCommand):
    help = 'Crop a band out of a mockup image by height fractions (0..1).'

    def add_arguments(self, parser):
        parser.add_argument('src')
        parser.add_argument('out')
        parser.add_argument('--top', type=float, required=True, help='Top edge as a fraction of the height')
        parser.add_argument('--bottom', type=float, required=True, help='Bottom edge as a fraction of the height')

    def fail(self, message):
        self.stderr.write(self.style.ERROR(message))
        sys.exit(1)

    def handle(self, *args, **options):
        src, out = Path(options['src']), Path(options['out'])
        top, bottom = options['top'], options['bottom']
        if not src.is_file():
            self.fail(f'source image not found: {src}')
        if not (0.0 <= top < bottom <= 1.0):
            self.fail(f'fractions must satisfy 0 <= top < bottom <= 1, got top={top} bottom={bottom}')
        with Image.open(src) as im:
            w, h = im.size
            box = (0, round(h * top), w, round(h * bottom))
            crop = im.crop(box)
            out.parent.mkdir(parents=True, exist_ok=True)
            crop.save(out, format='PNG')
            cw, ch = crop.size
        self.stdout.write(f'wrote {out} {cw}x{ch}')
