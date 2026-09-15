"""
generate_mockup — render one mockup image with gpt-image-2.5 and log its cost.

Usage:
    python manage.py generate_mockup --prompt-file docs/mockups/prompts/00-master.md \
        --out docs/mockups/master-v1.png --model flare --size 1280x3840 --quality medium

    python manage.py generate_mockup --prompt-file docs/mockups/prompts/01-hero.md \
        --out docs/mockups/01-hero.png --model sunburst --size 1920x1088 --quality high \
        --ref docs/mockups/00-master.png --ref docs/mockups/crops/01-hero.png

With one or more --ref the edits endpoint is used (reference-guided);
without, the generations endpoint. Every successful call appends a record
to the costs file (default docs/mockups/costs.json) and prints the running
total. --budget refuses a call that would push the total past the limit.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from django.core.management.base import BaseCommand

from djangopress.ai.utils.openai_images import (
    ImageGenerationError,
    edit,
    generate,
    get_client,
    resolve_model,
    validate_quality,
    validate_size,
)

DEFAULT_COSTS_FILE = 'docs/mockups/costs.json'
FALLBACK_ESTIMATE_USD = 0.25  # used for the budget check before any record exists


def load_costs(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise ValueError(f'costs file is not valid JSON: {path} — fix or move it before continuing')
    return {'total_usd': 0.0, 'records': []}


def append_cost(path: Path, record: dict) -> dict:
    data = load_costs(path)
    data['records'].append(record)
    data['total_usd'] = round(sum(r.get('cost_usd', 0.0) for r in data['records']), 6)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    os.replace(tmp, path)
    return data


def estimate_next_cost(data: dict, model: str, size: str, quality: str) -> float:
    for rec in reversed(data['records']):
        if rec.get('model') == model and rec.get('size') == size and rec.get('quality') == quality:
            return float(rec.get('cost_usd', FALLBACK_ESTIMATE_USD))
    return FALLBACK_ESTIMATE_USD


class Command(BaseCommand):
    help = 'Render one mockup image with gpt-image-2.5 (flare/sunburst) and log its cost.'

    def add_arguments(self, parser):
        src = parser.add_mutually_exclusive_group(required=True)
        src.add_argument('--prompt-file', help='File whose whole content is the prompt')
        src.add_argument('--prompt', help='Inline prompt text')
        parser.add_argument('--out', required=True, help='Output PNG path')
        parser.add_argument('--model', default='sunburst', help='flare | sunburst')
        parser.add_argument('--size', default='1536x1024', help='WIDTHxHEIGHT (multiples of 16, 1:3..3:1)')
        parser.add_argument('--quality', default='high', help='low|medium|high|xhigh|max|auto')
        parser.add_argument('--ref', action='append', default=[], help='Reference image (repeatable, max 16)')
        parser.add_argument('--fidelity', default='high', choices=['high', 'low'], help='input_fidelity for edits')
        parser.add_argument('--budget', type=float, default=None, help='Refuse if the site total would exceed this USD amount')
        parser.add_argument('--costs-file', default=DEFAULT_COSTS_FILE)
        parser.add_argument('--dry-run', action='store_true', help='Validate and print the request; no API call')

    def fail(self, message):
        self.stderr.write(self.style.ERROR(message))
        sys.exit(1)

    def handle(self, *args, **options):
        try:
            validate_size(options['size'])
            validate_quality(options['quality'])
            model_id = resolve_model(options['model'])
        except ValueError as exc:
            self.fail(str(exc))

        if options['prompt_file']:
            prompt_path = Path(options['prompt_file'])
            if not prompt_path.is_file():
                self.fail(f'prompt file not found: {prompt_path}')
            prompt = prompt_path.read_text().strip()
        else:
            prompt = options['prompt'].strip()
        if not prompt:
            self.fail('prompt is empty')

        refs = [Path(r) for r in options['ref']]
        for r in refs:
            if not r.is_file():
                self.fail(f'reference image not found: {r}')

        out = Path(options['out'])
        costs_path = Path(options['costs_file'])
        endpoint = 'edits' if refs else 'generations'

        if options['dry_run']:
            self.stdout.write(
                f"dry run: {endpoint} model={model_id} size={options['size']} quality={options['quality']} "
                f"refs={len(refs)} fidelity={options['fidelity']} out={out}\n--- prompt ({len(prompt)} chars) ---\n{prompt[:800]}"
            )
            return

        try:
            data = load_costs(costs_path)
        except ValueError as exc:
            self.fail(str(exc))

        if options['budget'] is not None:
            projected = data['total_usd'] + estimate_next_cost(data, model_id, options['size'], options['quality'])
            if projected > options['budget']:
                self.fail(
                    f"budget: site total ${data['total_usd']:.3f} plus an estimated "
                    f"${projected - data['total_usd']:.3f} would exceed ${options['budget']:.2f}"
                )

        try:
            client = get_client()
            if refs:
                result = edit(prompt, references=refs, size=options['size'], quality=options['quality'],
                              model=model_id, input_fidelity=options['fidelity'], client=client)
            else:
                result = generate(prompt, size=options['size'], quality=options['quality'],
                                  model=model_id, client=client)
        except ImageGenerationError as exc:
            self.fail(f'image generation failed ({"retryable" if exc.retryable else "not retryable"}): {exc}')

        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(result.png_bytes)

        record = {
            'ts': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'out': str(out),
            'model': result.model,
            'size': result.size,
            'quality': result.quality,
            'refs': [str(r) for r in refs],
            'text_in': result.usage.text_in,
            'image_in': result.usage.image_in,
            'image_out': result.usage.image_out,
            'cost_usd': result.cost_usd,
            'elapsed_s': result.elapsed_s,
        }
        try:
            data = append_cost(costs_path, record)
        except ValueError as exc:
            self.fail(f'{exc} (image preserved at {out})')

        self.stdout.write(
            f"wrote {out}  {result.size}  ${result.cost_usd:.4f}  ({result.elapsed_s}s)  "
            f"site total ${data['total_usd']:.3f}"
        )
