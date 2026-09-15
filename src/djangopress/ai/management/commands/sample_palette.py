"""
sample_palette — dominant colors of a mockup, by k-means on a downscaled copy.

Usage:
    python manage.py sample_palette docs/mockups/00-master.png --k 6
    python manage.py sample_palette docs/mockups/00-master.png --k 6 --json

Used by the extract-design skill so palette values in the design system are
sampled from the approved image rather than guessed.
"""

import json
import random
import sys
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from PIL import Image

MAX_SIDE = 160  # downscale so k-means runs on <= ~25k pixels in pure Python
CHROMATIC_MIN = 12
CHROMATIC_MAX = 243
CHROMATIC_FLOOR = 0.15  # below this share of chromatic pixels, fall back to clustering everything


def luminance(rgb):
    r, g, b = rgb
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def kmeans_palette(pixels, k, iterations=12, seed=7):
    """Return [((r, g, b), share), ...] sorted by share descending."""
    if not pixels:
        return []
    k = min(k, len(set(pixels)))
    rng = random.Random(seed)
    centers = [tuple(map(float, c)) for c in rng.sample(sorted(set(pixels)), k)]
    assignment = [0] * len(pixels)
    for _ in range(iterations):
        for i, p in enumerate(pixels):
            best, best_d = 0, None
            for ci, c in enumerate(centers):
                d = (p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2 + (p[2] - c[2]) ** 2
                if best_d is None or d < best_d:
                    best, best_d = ci, d
            assignment[i] = best
        sums = [[0.0, 0.0, 0.0, 0] for _ in centers]
        for p, a in zip(pixels, assignment):
            s = sums[a]
            s[0] += p[0]; s[1] += p[1]; s[2] += p[2]; s[3] += 1
        new_centers = []
        for c, s in zip(centers, sums):
            new_centers.append((s[0] / s[3], s[1] / s[3], s[2] / s[3]) if s[3] else c)
        if new_centers == centers:
            break
        centers = new_centers
    counts = [0] * len(centers)
    for a in assignment:
        counts[a] += 1
    total = len(pixels)
    result = [
        ((round(c[0]), round(c[1]), round(c[2])), counts[i] / total)
        for i, c in enumerate(centers) if counts[i]
    ]
    return sorted(result, key=lambda item: item[1], reverse=True)


def to_hex(rgb):
    return '#%02x%02x%02x' % rgb


class Command(BaseCommand):
    help = 'Print the dominant colors of an image (k-means), as text or JSON.'

    def add_arguments(self, parser):
        parser.add_argument('src')
        parser.add_argument('--k', type=int, default=6)
        parser.add_argument('--json', action='store_true')

    def handle(self, *args, **options):
        if options['k'] < 1:
            raise CommandError('--k must be at least 1')
        src = Path(options['src'])
        if not src.is_file():
            self.stderr.write(self.style.ERROR(f'image not found: {src}'))
            sys.exit(1)
        with Image.open(src) as im:
            im = im.convert('RGB')
            im.thumbnail((MAX_SIDE, MAX_SIDE))
            pixels = list(im.getdata())

        total = len(pixels)
        chromatic, excluded = [], []
        for p in pixels:
            (chromatic if CHROMATIC_MIN <= luminance(p) <= CHROMATIC_MAX else excluded).append(p)

        entries = []  # [(rgb, share, hint), ...]
        if total and len(chromatic) < CHROMATIC_FLOOR * total:
            # Near-white/near-black dominates the image: fall back to clustering everything.
            for c, s in kmeans_palette(pixels, k=options['k']):
                entries.append((c, s, None))
        else:
            cluster_source = chromatic
            for c, s in kmeans_palette(cluster_source, k=options['k']):
                entries.append((c, s * len(cluster_source) / total, None))
            light = [p for p in excluded if luminance(p) > CHROMATIC_MAX]
            dark = [p for p in excluded if luminance(p) < CHROMATIC_MIN]
            if light:
                mean = tuple(round(sum(ch) / len(light)) for ch in zip(*light))
                entries.append((mean, len(light) / total, 'light'))
            if dark:
                mean = tuple(round(sum(ch) / len(dark)) for ch in zip(*dark))
                entries.append((mean, len(dark) / total, 'dark'))

        if options['json']:
            self.stdout.write(json.dumps([
                {'hex': to_hex(c), 'share': round(s, 4), 'hint': hint or '-'} for c, s, hint in entries
            ]))
        else:
            for c, s, hint in entries:
                self.stdout.write(f'{to_hex(c)}  {s * 100:.1f}%  {hint or "-"}')
