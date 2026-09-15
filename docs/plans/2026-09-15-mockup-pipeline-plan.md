# Mockup Pipeline (Level A2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an OpenAI image-generation layer (`gpt-image-2.5-sunburst` by default, `gpt-image-2.5-flare` as an explicit cheap option) with three management commands, two new skills (`mockup-site`, `extract-design`), and the changes to `create-briefing` and `generate-site` that make an approved master mockup and an extracted design system mandatory before any build. The briefing is final before any image; the master and each section are generated one at a time with a check after each.

**Architecture:** A dependency-free helper module wraps the OpenAI Images API (generations for masters, edits with reference images for sections) and reports token usage and cost. Thin management commands expose it to skills one image per call. Skills compose the commands, write every prompt to disk first, and keep the rule "facts from the briefing, form from the image". `generate-site` gains a hard gate on `docs/mockups/00-master.png` and `docs/design-system.md`, plus a rebuild entry point for sites that already have pages.

**Tech Stack:** Django 6 management commands, `openai` SDK ≥ 2.36 (`client.images.generate` / `client.images.edit`), Pillow, Django test runner from a child site venv, Markdown skills.

**Spec:** `docs/plans/2026-09-15-mockup-pipeline-design.md`

## Global Constraints

- **Repo:** `/Users/antoniomarante/Documents/djangopress-sites/djangopress`, work on branch `feature/mockup-pipeline` created from `main` (same checkout, no worktree — child sites depend on this path).
- **Tests run from a child site with an editable install:** `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py test djangopress.ai.tests.<module> -v 1`. Tests never call the network: every test injects a fake client.
- **Only two image models:** `gpt-image-2.5-flare` (alias `flare`) and `gpt-image-2.5-sunburst` (alias `sunburst`). No other model id appears anywhere.
- **Size rules, enforced before any call:** `WIDTHxHEIGHT`; both multiples of 16; aspect ratio between 1:3 and 3:1 inclusive; no edge above 3840; total pixels between 655,360 and 8,294,400.
- **Quality values:** `low`, `medium`, `high`, `xhigh`, `max`, `auto`.
- **Prices (USD per million tokens):** text input 5.00, image input 8.00, image output 30.00.
- **Reference images:** at most 16 per edit call; `input_fidelity` is `high` unless told otherwise.
- **Master size:** `1280x3840`. Every render (master, sections, regenerations) uses `sunburst`, `high` unless the operator passes `flare`. One master at a time; the operator approves one (`approve <n>` copies it to `00-master.png`, no API call).
- **Section size table:** hero/cta/band/inverted → `1920x1088`; editorial split → `1536x1024`; gallery/menu/pricing/grid → `1536x1536`; testimonials/trust bar → `1920x832`; header/footer → `1920x640`. A `ratio:` line in the section's briefing entry overrides.
- **Files:** prompts under `docs/mockups/prompts/`, crops under `docs/mockups/crops/`, images `docs/mockups/master-v<n>.png`, `docs/mockups/00-master.png`, `docs/mockups/NN-<name>.png`, section list `docs/mockups/sections.json`, costs `docs/mockups/costs.json`, design system `docs/design-system.md`. PNGs are git-ignored via `docs/mockups/.gitignore`; prompts, costs and design system are committed.
- **Facts from the briefing, form from the image.** Skills never copy text, prices, addresses or names seen in an image.
- **Skills are live on save** (symlinks into this checkout): write a whole skill file in one `Write`; edit existing skills with precise `Edit` calls.
- **Commit messages must not contain `Co-Authored-By`.** Commit only the files named in each task. `briefings/lalitana.md` stays untracked.
- **Do not touch `/Users/antoniomarante/Documents/djangopress-sites/o-marisco/` before Task 8.** Task 8 is the guided real-API test on that site and is the only task allowed there.
- **Existing accessor for env:** `from djangopress.ai.utils.llm_config import get_env` (returns `None` when unset).

---

### Task 1: `openai_images` helper module

**Files:**
- Create: `src/djangopress/ai/utils/openai_images.py`
- Create: `src/djangopress/ai/tests/__init__.py` (empty)
- Test: `src/djangopress/ai/tests/test_openai_images.py`

**Interfaces:**
- Produces: `MODELS`, `QUALITIES`, `PRICE_PER_M`, `MAX_REFERENCES`, `ImageGenerationError(message, retryable=False)`, `Usage(text_in, image_in, image_out)`, `ImageResult(png_bytes, usage, cost_usd, model, size, quality, elapsed_s)`, `validate_size(size) -> (w, h)`, `resolve_model(name) -> str`, `usage_from_response(response) -> Usage`, `cost_usd(usage) -> float`, `is_retryable(exc) -> bool`, `get_client()`, `generate(prompt, *, size, quality='high', model='sunburst', client=None) -> ImageResult`, `edit(prompt, *, references, size, quality='high', model='sunburst', input_fidelity='high', client=None) -> ImageResult`.

- [ ] **Step 1: Write the failing tests**

Create `src/djangopress/ai/tests/__init__.py` (empty) and `src/djangopress/ai/tests/test_openai_images.py`:

```python
"""Tests for ai.utils.openai_images — no network; a fake client stands in for the SDK."""

import base64
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase


PNG_1PX = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='
)


def fake_response(text_in=97, image_in=0, image_out=1760):
    return SimpleNamespace(
        data=[SimpleNamespace(b64_json=base64.b64encode(PNG_1PX).decode())],
        usage=SimpleNamespace(
            input_tokens=text_in + image_in,
            input_tokens_details=SimpleNamespace(text_tokens=text_in, image_tokens=image_in),
            output_tokens=image_out,
            total_tokens=text_in + image_in + image_out,
        ),
    )


class FakeImages:
    def __init__(self, responses=None, raises=None):
        self.calls = []
        self.responses = list(responses or [fake_response()])
        self.raises = list(raises or [])

    def _next(self, kind, kwargs):
        self.calls.append((kind, kwargs))
        if self.raises:
            exc = self.raises.pop(0)
            if exc is not None:
                raise exc
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]

    def generate(self, **kwargs):
        return self._next('generate', kwargs)

    def edit(self, **kwargs):
        return self._next('edit', kwargs)


class FakeClient:
    def __init__(self, **kw):
        self.images = FakeImages(**kw)


class ValidateSizeTest(SimpleTestCase):
    def test_accepts_standard_and_custom_sizes(self):
        from djangopress.ai.utils.openai_images import validate_size
        self.assertEqual(validate_size('1024x1024'), (1024, 1024))
        self.assertEqual(validate_size('1280x3840'), (1280, 3840))
        self.assertEqual(validate_size('1920x1088'), (1920, 1088))

    def test_rejects_bad_format(self):
        from djangopress.ai.utils.openai_images import validate_size
        with self.assertRaisesRegex(ValueError, 'WIDTHxHEIGHT'):
            validate_size('big')

    def test_rejects_non_multiple_of_16(self):
        from djangopress.ai.utils.openai_images import validate_size
        with self.assertRaisesRegex(ValueError, 'multiples of 16'):
            validate_size('1920x1080')

    def test_rejects_edge_over_3840(self):
        from djangopress.ai.utils.openai_images import validate_size
        with self.assertRaisesRegex(ValueError, '3840'):
            validate_size('4096x1024')

    def test_rejects_aspect_ratio_outside_bounds(self):
        from djangopress.ai.utils.openai_images import validate_size
        with self.assertRaisesRegex(ValueError, '1:3'):
            validate_size('1024x3840')

    def test_rejects_pixel_count_outside_bounds(self):
        from djangopress.ai.utils.openai_images import validate_size
        with self.assertRaisesRegex(ValueError, '655360'):
            validate_size('512x512')
        with self.assertRaisesRegex(ValueError, '8294400'):
            validate_size('3840x3840')


class ModelAndCostTest(SimpleTestCase):
    def test_resolve_model_aliases_and_ids(self):
        from djangopress.ai.utils.openai_images import resolve_model
        self.assertEqual(resolve_model('flare'), 'gpt-image-2.5-flare')
        self.assertEqual(resolve_model('sunburst'), 'gpt-image-2.5-sunburst')
        self.assertEqual(resolve_model('gpt-image-2.5-flare'), 'gpt-image-2.5-flare')
        with self.assertRaises(ValueError):
            resolve_model('gpt-image-2')

    def test_cost_from_usage(self):
        from djangopress.ai.utils.openai_images import Usage, cost_usd
        # 97 text in, 1000 image in, 1760 image out
        self.assertAlmostEqual(cost_usd(Usage(97, 1000, 1760)), (97 * 5 + 1000 * 8 + 1760 * 30) / 1e6, places=8)

    def test_usage_from_response_handles_missing_usage(self):
        from djangopress.ai.utils.openai_images import usage_from_response, Usage
        self.assertEqual(usage_from_response(SimpleNamespace()), Usage(0, 0, 0))
        u = usage_from_response(fake_response(text_in=10, image_in=20, image_out=30))
        self.assertEqual((u.text_in, u.image_in, u.image_out), (10, 20, 30))

    def test_is_retryable(self):
        from djangopress.ai.utils.openai_images import is_retryable
        RateLimitError = type('RateLimitError', (Exception,), {})
        APIStatusError = type('APIStatusError', (Exception,), {})
        five = APIStatusError('boom'); five.status_code = 503
        four = APIStatusError('nope'); four.status_code = 400
        self.assertTrue(is_retryable(RateLimitError('slow down')))
        self.assertTrue(is_retryable(five))
        self.assertFalse(is_retryable(four))
        self.assertFalse(is_retryable(ValueError('x')))


class GenerateTest(SimpleTestCase):
    def test_generate_calls_generations_with_expected_args(self):
        from djangopress.ai.utils.openai_images import generate
        client = FakeClient()
        result = generate('a hero', size='1920x1088', quality='medium', model='flare', client=client)
        kind, kwargs = client.images.calls[0]
        self.assertEqual(kind, 'generate')
        self.assertEqual(kwargs['model'], 'gpt-image-2.5-flare')
        self.assertEqual(kwargs['size'], '1920x1088')
        self.assertEqual(kwargs['quality'], 'medium')
        self.assertEqual(kwargs['n'], 1)
        self.assertEqual(kwargs['output_format'], 'png')
        self.assertEqual(result.png_bytes, PNG_1PX)
        self.assertEqual(result.usage.image_out, 1760)
        self.assertAlmostEqual(result.cost_usd, (97 * 5 + 1760 * 30) / 1e6, places=8)
        self.assertEqual(result.model, 'gpt-image-2.5-flare')

    def test_generate_validates_size_before_calling(self):
        from djangopress.ai.utils.openai_images import generate
        client = FakeClient()
        with self.assertRaises(ValueError):
            generate('x', size='1920x1080', client=client)
        self.assertEqual(client.images.calls, [])

    def test_generate_rejects_unknown_quality(self):
        from djangopress.ai.utils.openai_images import generate
        with self.assertRaises(ValueError):
            generate('x', size='1024x1024', quality='ultra', client=FakeClient())

    def test_retries_once_on_retryable_then_succeeds(self):
        from djangopress.ai.utils.openai_images import generate
        RateLimitError = type('RateLimitError', (Exception,), {})
        client = FakeClient(raises=[RateLimitError('429'), None])
        with patch('djangopress.ai.utils.openai_images.time.sleep'):
            result = generate('x', size='1024x1024', client=client)
        self.assertEqual(len(client.images.calls), 2)
        self.assertEqual(result.png_bytes, PNG_1PX)

    def test_non_retryable_error_is_wrapped(self):
        from djangopress.ai.utils.openai_images import generate, ImageGenerationError
        APIStatusError = type('APIStatusError', (Exception,), {})
        err = APIStatusError('content policy'); err.status_code = 400
        client = FakeClient(raises=[err])
        with self.assertRaises(ImageGenerationError) as ctx:
            generate('x', size='1024x1024', client=client)
        self.assertFalse(ctx.exception.retryable)
        self.assertEqual(len(client.images.calls), 1)

    def test_gives_up_after_three_retryable_failures(self):
        from djangopress.ai.utils.openai_images import generate, ImageGenerationError
        RateLimitError = type('RateLimitError', (Exception,), {})
        client = FakeClient(raises=[RateLimitError('1'), RateLimitError('2'), RateLimitError('3')])
        with patch('djangopress.ai.utils.openai_images.time.sleep'):
            with self.assertRaises(ImageGenerationError) as ctx:
                generate('x', size='1024x1024', client=client)
        self.assertTrue(ctx.exception.retryable)
        self.assertEqual(len(client.images.calls), 3)


class EditTest(SimpleTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.refs = []
        for name in ('master.png', 'crop.png'):
            p = Path(self.tmp.name) / name
            p.write_bytes(PNG_1PX)
            self.refs.append(p)

    def tearDown(self):
        self.tmp.cleanup()

    def test_edit_sends_reference_files_and_fidelity(self):
        from djangopress.ai.utils.openai_images import edit
        client = FakeClient(responses=[fake_response(image_in=1200)])
        result = edit('the hero', references=self.refs, size='1920x1088', client=client)
        kind, kwargs = client.images.calls[0]
        self.assertEqual(kind, 'edit')
        self.assertEqual(kwargs['model'], 'gpt-image-2.5-sunburst')
        self.assertEqual(len(kwargs['image']), 2)
        self.assertEqual(kwargs['input_fidelity'], 'high')
        self.assertEqual(kwargs['size'], '1920x1088')
        self.assertEqual(kwargs['quality'], 'high')
        self.assertEqual(result.usage.image_in, 1200)
        for f in kwargs['image']:
            self.assertTrue(f.closed)

    def test_edit_requires_at_least_one_and_at_most_16_references(self):
        from djangopress.ai.utils.openai_images import edit
        with self.assertRaises(ValueError):
            edit('x', references=[], size='1024x1024', client=FakeClient())
        with self.assertRaises(ValueError):
            edit('x', references=self.refs * 9, size='1024x1024', client=FakeClient())

    def test_edit_missing_reference_file(self):
        from djangopress.ai.utils.openai_images import edit
        with self.assertRaises(FileNotFoundError):
            edit('x', references=[Path(self.tmp.name) / 'nope.png'], size='1024x1024', client=FakeClient())


class GetClientTest(SimpleTestCase):
    def test_get_client_requires_key(self):
        from djangopress.ai.utils import openai_images
        with patch.object(openai_images, 'get_env', return_value=None):
            with self.assertRaises(openai_images.ImageGenerationError):
                openai_images.get_client()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py test djangopress.ai.tests.test_openai_images -v 1 2>&1 | grep -E "^(Ran|OK|FAILED|ERROR|ModuleNotFoundError)"`
Expected: errors mentioning `No module named 'djangopress.ai.utils.openai_images'`.

- [ ] **Step 3: Write the module**

Create `src/djangopress/ai/utils/openai_images.py`:

```python
"""
OpenAI image generation for site mockups.

Only two models are used: gpt-image-2.5-flare (fast, for master variants)
and gpt-image-2.5-sunburst (precise across edits, for the promoted master
and every section). Masters use the generations endpoint; sections use the
edits endpoint with the master (and optionally a crop) as reference images.

Every result carries token usage and the cost computed from OpenAI's
published per-million-token prices, so skills can log what a site costs.
"""

import base64
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

from djangopress.ai.utils.llm_config import get_env


MODELS = {
    'flare': 'gpt-image-2.5-flare',
    'sunburst': 'gpt-image-2.5-sunburst',
}
QUALITIES = ('low', 'medium', 'high', 'xhigh', 'max', 'auto')
PRICE_PER_M = {'text_in': 5.0, 'image_in': 8.0, 'image_out': 30.0}

MIN_PIXELS = 655_360
MAX_PIXELS = 8_294_400
MAX_EDGE = 3840
MAX_REFERENCES = 16

RETRY_DELAYS = (2, 5)  # seconds between attempts; three attempts total


class ImageGenerationError(Exception):
    def __init__(self, message, retryable=False):
        super().__init__(message)
        self.retryable = retryable


@dataclass
class Usage:
    text_in: int = 0
    image_in: int = 0
    image_out: int = 0


@dataclass
class ImageResult:
    png_bytes: bytes
    usage: Usage
    cost_usd: float
    model: str
    size: str
    quality: str
    elapsed_s: float


def validate_size(size: str):
    """Return (width, height) or raise ValueError naming the violated rule."""
    try:
        w_s, h_s = size.lower().split('x')
        w, h = int(w_s), int(h_s)
    except (ValueError, AttributeError):
        raise ValueError(f"size must be WIDTHxHEIGHT, got {size!r}")
    if w % 16 or h % 16:
        raise ValueError(f"{size}: width and height must be multiples of 16")
    if w > MAX_EDGE or h > MAX_EDGE:
        raise ValueError(f"{size}: no edge may exceed {MAX_EDGE}")
    ratio = w / h
    if ratio < 1 / 3 or ratio > 3:
        raise ValueError(f"{size}: aspect ratio must be between 1:3 and 3:1")
    px = w * h
    if px < MIN_PIXELS or px > MAX_PIXELS:
        raise ValueError(f"{size}: total pixels must be between {MIN_PIXELS} and {MAX_PIXELS}")
    return w, h


def resolve_model(name: str) -> str:
    if name in MODELS:
        return MODELS[name]
    if name in MODELS.values():
        return name
    raise ValueError(f"model must be one of {', '.join(MODELS)} (or their full ids), got {name!r}")


def validate_quality(quality: str) -> str:
    if quality not in QUALITIES:
        raise ValueError(f"quality must be one of {', '.join(QUALITIES)}, got {quality!r}")
    return quality


def usage_from_response(response) -> Usage:
    u = getattr(response, 'usage', None)
    if not u:
        return Usage()
    details = getattr(u, 'input_tokens_details', None)
    return Usage(
        text_in=int(getattr(details, 'text_tokens', 0) or 0) if details else 0,
        image_in=int(getattr(details, 'image_tokens', 0) or 0) if details else 0,
        image_out=int(getattr(u, 'output_tokens', 0) or 0),
    )


def cost_usd(usage: Usage) -> float:
    return round(
        (usage.text_in * PRICE_PER_M['text_in']
         + usage.image_in * PRICE_PER_M['image_in']
         + usage.image_out * PRICE_PER_M['image_out']) / 1_000_000,
        6,
    )


def is_retryable(exc: Exception) -> bool:
    name = exc.__class__.__name__
    if name in ('RateLimitError', 'APIConnectionError', 'APITimeoutError'):
        return True
    status = getattr(exc, 'status_code', None)
    return isinstance(status, int) and status >= 500


def get_client():
    key = get_env('OPENAI_API_KEY')
    if not key:
        raise ImageGenerationError('OPENAI_API_KEY is not set in the site .env')
    from openai import OpenAI
    return OpenAI(api_key=key)


def _call_with_retries(fn, **kwargs):
    attempts = len(RETRY_DELAYS) + 1
    for attempt in range(attempts):
        try:
            return fn(**kwargs)
        except Exception as exc:  # the SDK raises many classes; classify, don't enumerate
            if is_retryable(exc) and attempt < attempts - 1:
                time.sleep(RETRY_DELAYS[attempt])
                continue
            raise ImageGenerationError(f'{exc.__class__.__name__}: {exc}', retryable=is_retryable(exc))


def _decode(response) -> bytes:
    data = getattr(response, 'data', None) or []
    if not data or not getattr(data[0], 'b64_json', None):
        raise ImageGenerationError('the API returned no image data', retryable=False)
    return base64.b64decode(data[0].b64_json)


def _result(response, *, model, size, quality, started) -> ImageResult:
    usage = usage_from_response(response)
    return ImageResult(
        png_bytes=_decode(response),
        usage=usage,
        cost_usd=cost_usd(usage),
        model=model,
        size=size,
        quality=quality,
        elapsed_s=round(time.time() - started, 2),
    )


def generate(prompt: str, *, size: str, quality: str = 'high', model: str = 'sunburst', client=None) -> ImageResult:
    validate_size(size)
    validate_quality(quality)
    model_id = resolve_model(model)
    client = client or get_client()
    started = time.time()
    response = _call_with_retries(
        client.images.generate,
        model=model_id, prompt=prompt, size=size, quality=quality, n=1, output_format='png',
    )
    return _result(response, model=model_id, size=size, quality=quality, started=started)


def edit(prompt: str, *, references: Sequence[Path], size: str, quality: str = 'high',
         model: str = 'sunburst', input_fidelity: str = 'high', client=None) -> ImageResult:
    validate_size(size)
    validate_quality(quality)
    if not references:
        raise ValueError('edit needs at least one reference image')
    if len(references) > MAX_REFERENCES:
        raise ValueError(f'at most {MAX_REFERENCES} reference images, got {len(references)}')
    paths = [Path(p) for p in references]
    for p in paths:
        if not p.is_file():
            raise FileNotFoundError(str(p))
    model_id = resolve_model(model)
    client = client or get_client()
    files = [open(p, 'rb') for p in paths]
    started = time.time()
    try:
        response = _call_with_retries(
            client.images.edit,
            model=model_id, image=files, prompt=prompt, size=size, quality=quality,
            input_fidelity=input_fidelity, n=1,
        )
    finally:
        for f in files:
            f.close()
    return _result(response, model=model_id, size=size, quality=quality, started=started)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py test djangopress.ai.tests.test_openai_images -v 1 2>&1 | grep -E "^(Ran|OK|FAILED|ERROR)"`
Expected: `Ran 20 tests` then `OK`.

If `test_edit_sends_reference_files_and_fidelity` fails on `f.closed`, the `finally` block is not closing the files — fix the module, not the test.

- [ ] **Step 5: Commit**

```bash
git add src/djangopress/ai/utils/openai_images.py src/djangopress/ai/tests/__init__.py src/djangopress/ai/tests/test_openai_images.py
git commit -m "feat(ai): openai_images helper for gpt-image-2.5 mockups with usage and cost"
```

---

### Task 2: `generate_mockup` command

**Files:**
- Create: `src/djangopress/ai/management/commands/generate_mockup.py`
- Test: `src/djangopress/ai/tests/test_generate_mockup.py`

**Interfaces:**
- Consumes: `openai_images.generate`, `openai_images.edit`, `openai_images.validate_size`, `openai_images.get_client`, `ImageGenerationError`.
- Produces: the CLI `generate_mockup --prompt-file F | --prompt TEXT --out PATH [--model flare|sunburst] [--size WxH] [--quality Q] [--ref PATH ...] [--fidelity high|low] [--budget USD] [--costs-file PATH] [--dry-run]`; the costs file schema `{"total_usd": float, "records": [{"ts", "out", "model", "size", "quality", "refs", "text_in", "image_in", "image_out", "cost_usd", "elapsed_s"}]}`; a helper `load_costs(path) -> dict` and `append_cost(path, record) -> dict` in the same module (imported by Task 3's tests only through the CLI).

- [ ] **Step 1: Write the failing tests**

Create `src/djangopress/ai/tests/test_generate_mockup.py`:

```python
"""Tests for the generate_mockup command — fake client, no network."""

import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase

from .test_openai_images import FakeClient, PNG_1PX, fake_response


class GenerateMockupTest(SimpleTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.prompt = self.root / 'prompt.md'
        self.prompt.write_text('A desktop website hero section.')
        self.out = self.root / 'mockups' / '01-hero.png'
        self.costs = self.root / 'mockups' / 'costs.json'

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, *args, client=None, **kw):
        out = StringIO()
        with patch('djangopress.ai.management.commands.generate_mockup.get_client', return_value=client or FakeClient()):
            call_command('generate_mockup', *args, '--costs-file', str(self.costs), stdout=out, **kw)
        return out.getvalue()

    def test_generates_and_records_cost(self):
        text = self._run('--prompt-file', str(self.prompt), '--out', str(self.out),
                         '--model', 'flare', '--size', '1280x3840', '--quality', 'medium')
        self.assertEqual(self.out.read_bytes(), PNG_1PX)
        data = json.loads(self.costs.read_text())
        self.assertEqual(len(data['records']), 1)
        rec = data['records'][0]
        self.assertEqual(rec['model'], 'gpt-image-2.5-flare')
        self.assertEqual(rec['size'], '1280x3840')
        self.assertEqual(rec['quality'], 'medium')
        self.assertEqual(rec['image_out'], 1760)
        self.assertAlmostEqual(data['total_usd'], rec['cost_usd'], places=8)
        self.assertIn('wrote', text)
        self.assertIn('$', text)

    def test_refs_use_edit_endpoint(self):
        ref = self.root / 'master.png'
        ref.write_bytes(PNG_1PX)
        client = FakeClient()
        self._run('--prompt-file', str(self.prompt), '--out', str(self.out),
                  '--size', '1920x1088', '--ref', str(ref), client=client)
        kind, kwargs = client.images.calls[0]
        self.assertEqual(kind, 'edit')
        self.assertEqual(kwargs['input_fidelity'], 'high')
        rec = json.loads(self.costs.read_text())['records'][0]
        self.assertEqual(rec['refs'], [str(ref)])

    def test_inline_prompt(self):
        client = FakeClient()
        self._run('--prompt', 'inline text', '--out', str(self.out), '--size', '1024x1024', client=client)
        self.assertEqual(client.images.calls[0][1]['prompt'], 'inline text')

    def test_dry_run_makes_no_call_and_writes_nothing(self):
        client = FakeClient()
        text = self._run('--prompt-file', str(self.prompt), '--out', str(self.out),
                         '--size', '1536x1024', '--dry-run', client=client)
        self.assertEqual(client.images.calls, [])
        self.assertFalse(self.out.exists())
        self.assertFalse(self.costs.exists())
        self.assertIn('gpt-image-2.5-sunburst', text)
        self.assertIn('1536x1024', text)

    def test_invalid_size_exits_before_calling(self):
        client = FakeClient()
        with self.assertRaises(SystemExit) as ctx:
            self._run('--prompt-file', str(self.prompt), '--out', str(self.out), '--size', '1920x1080', client=client)
        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(client.images.calls, [])

    def test_budget_refuses_when_total_would_exceed(self):
        # First call records ~$0.053 (97 text + 1760 out at published rates).
        self._run('--prompt-file', str(self.prompt), '--out', str(self.out), '--size', '1024x1024')
        second = self.root / 'mockups' / '02.png'
        client = FakeClient()
        with self.assertRaises(SystemExit):
            self._run('--prompt-file', str(self.prompt), '--out', str(second), '--size', '1024x1024',
                      '--budget', '0.06', client=client)
        self.assertEqual(client.images.calls, [])
        self.assertFalse(second.exists())

    def test_budget_allows_when_under(self):
        second = self.root / 'mockups' / '02.png'
        self._run('--prompt-file', str(self.prompt), '--out', str(second), '--size', '1024x1024', '--budget', '5')
        self.assertTrue(second.exists())

    def test_api_error_exits_1_with_message(self):
        APIStatusError = type('APIStatusError', (Exception,), {})
        err = APIStatusError('safety'); err.status_code = 400
        client = FakeClient(raises=[err])
        with self.assertRaises(SystemExit) as ctx:
            self._run('--prompt-file', str(self.prompt), '--out', str(self.out), '--size', '1024x1024', client=client)
        self.assertEqual(ctx.exception.code, 1)
        self.assertFalse(self.out.exists())
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py test djangopress.ai.tests.test_generate_mockup -v 1 2>&1 | grep -E "^(Ran|OK|FAILED|ERROR|CommandError)"`
Expected: errors — `Unknown command: 'generate_mockup'`.

- [ ] **Step 3: Write the command**

Create `src/djangopress/ai/management/commands/generate_mockup.py`:

```python
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
        except json.JSONDecodeError:
            pass
    return {'total_usd': 0.0, 'records': []}


def append_cost(path: Path, record: dict) -> dict:
    data = load_costs(path)
    data['records'].append(record)
    data['total_usd'] = round(sum(r.get('cost_usd', 0.0) for r in data['records']), 6)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
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

        data = load_costs(costs_path)
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
        data = append_cost(costs_path, record)
        self.stdout.write(
            f"wrote {out}  {result.size}  ${result.cost_usd:.4f}  ({result.elapsed_s}s)  "
            f"site total ${data['total_usd']:.3f}"
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py test djangopress.ai.tests.test_generate_mockup -v 1 2>&1 | grep -E "^(Ran|OK|FAILED|ERROR)"`
Expected: `Ran 8 tests` then `OK`.

Known trap: `self.fail` shadows `TestCase.fail` only inside the command class; it calls `sys.exit(1)`, which `call_command` propagates as `SystemExit` — the tests assert exactly that.

- [ ] **Step 5: Commit**

```bash
git add src/djangopress/ai/management/commands/generate_mockup.py src/djangopress/ai/tests/test_generate_mockup.py
git commit -m "feat(ai): generate_mockup command with reference images, budget and cost log"
```

---

### Task 3: `crop_mockup` and `sample_palette` commands

**Files:**
- Create: `src/djangopress/ai/management/commands/crop_mockup.py`
- Create: `src/djangopress/ai/management/commands/sample_palette.py`
- Test: `src/djangopress/ai/tests/test_mockup_tools.py`

**Interfaces:**
- Produces: `crop_mockup SRC OUT --top F --bottom F` (fractions of height, 0 ≤ top < bottom ≤ 1) writing a PNG and printing `wrote OUT WxH`; `sample_palette SRC [--k N] [--json]` printing either lines `#rrggbb  12.3%` or a JSON list `[{"hex": "#rrggbb", "share": 0.123}, ...]` sorted by share descending; the function `kmeans_palette(pixels, k, iterations=12) -> list[tuple[(r,g,b), share]]` in `sample_palette.py`.

- [ ] **Step 1: Write the failing tests**

Create `src/djangopress/ai/tests/test_mockup_tools.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py test djangopress.ai.tests.test_mockup_tools -v 1 2>&1 | grep -E "^(Ran|OK|FAILED|ERROR)"`
Expected: errors — unknown commands.

- [ ] **Step 3: Write `crop_mockup`**

Create `src/djangopress/ai/management/commands/crop_mockup.py`:

```python
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
```

- [ ] **Step 4: Write `sample_palette`**

Create `src/djangopress/ai/management/commands/sample_palette.py`:

```python
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

from django.core.management.base import BaseCommand
from PIL import Image

MAX_SIDE = 160  # downscale so k-means runs on <= ~25k pixels in pure Python


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
        src = Path(options['src'])
        if not src.is_file():
            self.stderr.write(self.style.ERROR(f'image not found: {src}'))
            sys.exit(1)
        with Image.open(src) as im:
            im = im.convert('RGB')
            im.thumbnail((MAX_SIDE, MAX_SIDE))
            pixels = list(im.getdata())
        palette = kmeans_palette(pixels, k=options['k'])
        if options['json']:
            self.stdout.write(json.dumps([{'hex': to_hex(c), 'share': round(s, 4)} for c, s in palette]))
        else:
            for c, s in palette:
                self.stdout.write(f'{to_hex(c)}  {s * 100:.1f}%')
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py test djangopress.ai.tests.test_mockup_tools -v 1 2>&1 | grep -E "^(Ran|OK|FAILED|ERROR)"`
Expected: `Ran 6 tests` then `OK`.

If `test_json_output` is off by the thumbnail resampling blending colors at the boundaries (a 90×30 image is not resampled because it is under `MAX_SIDE`, so this should not happen), keep the test and check `thumbnail` is not upscaling.

- [ ] **Step 6: Commit**

```bash
git add src/djangopress/ai/management/commands/crop_mockup.py src/djangopress/ai/management/commands/sample_palette.py src/djangopress/ai/tests/test_mockup_tools.py
git commit -m "feat(ai): crop_mockup and sample_palette commands for the mockup pipeline"
```

---

### Task 4: skill `mockup-site`

**Files:**
- Create: `src/djangopress/skills/mockup-site/SKILL.md`

**Interfaces:**
- Consumes: `generate_mockup`, `crop_mockup` CLIs (Tasks 2–3); the final briefing at `briefings/<slug>.md` with sections Business, Pages, Design Preferences, Integrations, Additional Notes; optional `briefings/<slug>-menu.json`.
- Produces: `docs/mockups/prompts/00-master-v<n>.md`, `docs/mockups/master-v<n>.png`, `docs/mockups/00-master.png`, `docs/mockups/sections.json`, `docs/mockups/prompts/NN-<name>.md`, `docs/mockups/crops/NN-<name>.png`, `docs/mockups/NN-<name>.png`, `docs/mockups/costs.json`, `docs/mockups/.gitignore`; the briefing line `- **Reference mockup**: docs/mockups/00-master.png (v<n>)` under Design Preferences; the section list convention `NN-<name>` with `NN` two digits from 01 in page order.

- [ ] **Step 1: Write the skill**

Create `src/djangopress/skills/mockup-site/SKILL.md`:

````markdown
---
name: mockup-site
description: Generate the approved-design mockups for a site with gpt-image-2.5 — one master one-page at a time from the final briefing until the operator approves it, then every section in high resolution from that master, one at a time with a check after each. Runs after the briefing is final and before any build; the build refuses to start without an approved master.
argument-hint: master [note] | approve <n> | section next | section <name> [note] | sections | costs
allowed-tools: Bash, Read, Write, Edit, Grep, Glob
---

# Mockups: one master → high-resolution sections, one at a time

The argument is: `$ARGUMENTS`. First word is the mode.

**Two rules.** Form comes from the image, facts come from the briefing: nothing seen in an image — a price, an address, a name, a menu item — is ever written into the site. And the approved master is the design: sections are never redesigned, only expanded from it.

**Rhythm.** Each mode renders at most one image and stops so the operator can look. The next call continues. The operator is present during this phase by design.

All commands run through the site venv: `.venv/bin/python manage.py …`. Every prompt is written to `docs/mockups/prompts/` before the call so the operator can read, edit and re-run it. Every render uses `--model sunburst --quality high` unless the operator's argument contains the word `flare`.

## Setup (every mode)

```bash
mkdir -p docs/mockups/prompts docs/mockups/crops
[ -f docs/mockups/.gitignore ] || printf '*.png\ncrops/\n' > docs/mockups/.gitignore
```

Read the briefing (`briefings/<slug>.md`, the only `.md` in `briefings/` besides `TEMPLATE.md` and `*-audit.md`). If it still has an `## Open Questions` section, stop: the briefing is not final; the operator finishes `/create-briefing` first. Read `briefings/<slug>-menu.json` if it exists, and `docs/mockups/costs.json` if it exists.

---

## `master [note]`

Renders **one** master one-page. `<n>` is the next free number (`master-v1.png` if none exists).

### Prompt: `docs/mockups/prompts/00-master-v<n>.md`

```
DESKTOP WEBSITE ONE-PAGE MOCKUP, full page from header to footer, rendered at
about 1440px wide, tall vertical layout, sections stacked top to bottom.
Photorealistic UI: real navigation bar, real buttons, real typography, real
photography. No device frame, no browser chrome, no annotations.

BRAND: <site name> — <one-line positioning from Business>.
LANGUAGE OF ALL TEXT: <default language name>. Use short, plausible placeholder
copy; never invent prices, addresses, phone numbers or awards.

AUDIENCE AND TONE: <2 sentences from Business>.

SECTIONS, in this order (one band each):
1. Header: <from Header section, or "logo left, 5 links, one CTA button, language switcher">
2. <section from Pages → Home entry, one line each, with its purpose and main element>
...
N. Footer: <from Footer section>

DESIGN DIRECTION (follow exactly):
- Palette: background <hex>, surface <hex>, text <hex>, accent <hex>, secondary <hex>, one dark block <hex>
- Type: headings <font or classification>, body <font or classification>
- Corner radius: <value>. Layout signature: <sentence>. Motif: <sentence or none>.
- Photography: <from Images: reuse real photos → "documentary, warm, no stock-look"; ai/unsplash → "editorial hospitality photography">
AVOID: <the Avoid list verbatim>.
```

When a previous master `master-v<n-1>.png` exists and a note was given, append:

```
ADJUSTMENT REQUESTED BY THE OPERATOR: <note verbatim>. Keep everything else
exactly as in the reference image: same sections, order, palette, type and
composition.
```

and pass the previous master as reference.

### Render

```bash
.venv/bin/python manage.py generate_mockup --prompt-file docs/mockups/prompts/00-master-v<n>.md \
  --out docs/mockups/master-v<n>.png --model sunburst --size 1280x3840 --quality high \
  [--ref docs/mockups/master-v<n-1>.png]
```

**Long pages.** When the section list has more than 9 entries, render two halves: `--out docs/mockups/master-v<n>-top.png` with sections 1..⌈N/2⌉ and the line `SHOW ONLY THE TOP HALF OF THE PAGE, ending mid-page`, then `master-v<n>-bottom.png` with the remaining sections, `--ref docs/mockups/master-v<n>-top.png`, and the line `CONTINUE THIS EXACT WEBSITE from where the reference ends; the header is NOT repeated; end with the footer`. Both halves keep `1280x3840`.

Print and stop:

```
Master v<n>: docs/mockups/master-v<n>.png   $<cost>   site total $<total>
Approve with: /mockup-site approve <n>
Or ask for another: /mockup-site master <what to change>
```

---

## `approve <n>`

No API call. Copy `master-v<n>.png` to `docs/mockups/00-master.png` (for a two-half master, copy `-top` to `00-master.png` and `-bottom` to `00-master-bottom.png`). In the briefing, under `## Design Preferences`, add or replace the line `- **Reference mockup**: docs/mockups/00-master.png (v<n>)`. Print `Approved master v<n>. Next: /mockup-site section next` and stop.

---

## `section next`

Requires `docs/mockups/00-master.png`; otherwise say so and stop.

### 1. Section list (first call only)

If `docs/mockups/sections.json` does not exist: open `00-master.png` (and `00-master-bottom.png` if present) with the Read tool and write the section sequence you see, top to bottom, with the vertical extent of each as fractions of the image height:

```json
[
  {"nn": "01", "name": "hero", "type": "hero", "top": 0.00, "bottom": 0.16},
  {"nn": "02", "name": "trust-bar", "type": "trust", "top": 0.16, "bottom": 0.19}
]
```

Names: lowercase, hyphens, English. Types: `hero`, `band` (full-width photographic or colored band, CTA), `inverted` (dark block), `editorial` (text + image split), `grid` (3+ cards or items), `gallery`, `menu`, `pricing`, `testimonials`, `trust`, `header`, `footer`. For a bottom-half image, add `"image": "00-master-bottom.png"` to its entries.

Reconcile with the briefing's `## Pages` → Home: a section in the master but absent from the briefing is appended to the briefing's Home entry as `(proposed from mockup)`; a section in the briefing but absent from the master is appended to `sections.json` with `"top": null, "bottom": null` (no crop). Do not drop anything from the briefing.

### 2. Pick the next section

The first entry in `sections.json` whose `docs/mockups/NN-<name>.png` does not exist. If none is left, print `All sections rendered. Next: /extract-design` and stop.

### 3. Prompt: `docs/mockups/prompts/NN-<name>.md`

Five blocks, in this order:

```
MASTER REFERENCE. The first reference image is the approved master design of
this website. Do NOT redesign the brand. Do NOT create a new visual direction.
The new image must look like another screenshot from the exact same website,
rendered at much higher resolution: same typography and hierarchy, same
palette and background colors, same button design, same dividers, same image
grading and photography style, same spacing, content width and grid, same
decorative language. When unsure, prefer consistency with the master over
novelty.
<if a crop exists:> The second reference image is the crop of this section
from the master: keep its composition and element order; reconstruct it as a
polished high-resolution section, do not merely upscale it.

PROJECT: <site name> — <positioning>. Language of all text: <default language>.

SECTION TO CREATE: <NAME> (<type>). Purpose: <one sentence from the briefing>.

CONTENT (use exactly these words; no other text, prices or names):
<headline, subhead, labels, CTAs from the briefing; for menu/pricing sections
the real items from the menu JSON with their real prices; for contact
sections the real phone, address and hours; navigation labels for header>

OUTPUT: only this one section, desktop layout about 1440px wide, no browser
chrome, no annotations, no device frame.
```

### 4. Crop and render

When `top`/`bottom` are set:

```bash
.venv/bin/python manage.py crop_mockup docs/mockups/<image or 00-master.png> docs/mockups/crops/NN-<name>.png --top <top> --bottom <bottom>
```

Size by type (a `ratio:` line in the section's briefing entry overrides):

| type | size |
|---|---|
| hero, band, inverted | 1920x1088 |
| editorial | 1536x1024 |
| grid, gallery, menu, pricing | 1536x1536 |
| testimonials, trust | 1920x832 |
| header, footer | 1920x640 |

```bash
.venv/bin/python manage.py generate_mockup --prompt-file docs/mockups/prompts/NN-<name>.md \
  --out docs/mockups/NN-<name>.png --model sunburst --size <size> --quality high \
  --ref docs/mockups/00-master.png [--ref docs/mockups/crops/NN-<name>.png]
```

### 5. Stop

```
Section NN-<name>: docs/mockups/NN-<name>.png   $<cost>   site total $<total>   (<k> of <N> done)
OK? → /mockup-site section next
Change it → /mockup-site section <name> <what to change>
```

---

## `section <name> [note]`

Regenerates `NN-<name>.png`. Keep the previous file as `docs/mockups/NN-<name>.prev.png`. Append to the prompt file:

```
ADJUSTMENT REQUESTED BY THE OPERATOR: <note verbatim>. Everything else stays as
in the references.
```

Run the same `generate_mockup` line as in `section next`, with the previous render added as a further `--ref` so the change is incremental. Print the new path and the cost, then the same two options as `section next`.

---

## `sections`

Renders every remaining section without stopping between them, with the same prompts and sizes as `section next`. For the operator who already trusts the master. Stop at the first non-retryable failure and report it; print the full list and the site total at the end.

---

## `costs`

Print `docs/mockups/costs.json` as a table (file, model, size, quality, tokens out, cost) and the total. No API calls.

---

## Failure handling

- `OPENAI_API_KEY is not set`: say which `.env` to edit and stop.
- A `budget` refusal: print the total and stop; the operator raises the budget explicitly.
- A non-retryable API error: report the error text and the prompt file, and stop; the operator edits the prompt or changes the note.
- Never delete a rendered PNG except by the `.prev.png` rotation above.
````

- [ ] **Step 2: Verify**

Run: `head -6 src/djangopress/skills/mockup-site/SKILL.md && grep -n "^## " src/djangopress/skills/mockup-site/SKILL.md && grep -c '^````' src/djangopress/skills/mockup-site/SKILL.md && grep -c "flare" src/djangopress/skills/mockup-site/SKILL.md`
Expected: frontmatter with `name: mockup-site`; headings for Setup, `master [note]`, `approve <n>`, `section next`, `section <name> [note]`, `sections`, `costs`, Failure handling; four-backtick count `0`; `flare` appears only in the sentence about the operator's explicit option (count `1`).

- [ ] **Step 3: Commit**

```bash
git add src/djangopress/skills/mockup-site/SKILL.md
git commit -m "feat(skills): mockup-site — one master at a time, approve, sections one at a time, costs"
```

---

### Task 5: skill `extract-design`

**Files:**
- Create: `src/djangopress/skills/extract-design/SKILL.md`

**Interfaces:**
- Consumes: `docs/mockups/00-master.png`, `docs/mockups/NN-<name>.png`, `sample_palette` CLI, the briefing, `check_site --only settings`.
- Produces: `docs/design-system.md` with a `## Tokens` part and a `## Sections` part (one `### NN-<name>` per rendered section); the briefing's `## Design Preferences` and `## Pages` rewritten; `SiteSettings` design fields and `design_guide` set. Task 6's `generate-site` reads exactly these.

- [ ] **Step 1: Write the skill**

Create `src/djangopress/skills/extract-design/SKILL.md`:

````markdown
---
name: extract-design
description: Turn the approved mockups into an executable design system — sampled palette mapped to SiteSettings fields, a concrete Google Fonts pair, type scale, layout tokens, and a per-section UI spec — and write it into docs/design-system.md, the briefing and SiteSettings. Runs after mockup-site sections are approved and before generate-site.
argument-hint:
allowed-tools: Bash, Read, Write, Edit, Grep, Glob
---

# Extract the design system from the mockups

Inputs: `docs/mockups/00-master.png`, every `docs/mockups/NN-<name>.png`, the briefing. If the master or the sections are missing, say which command produces them and stop.

**Rule.** Form from the images, facts from the briefing. Any text, price, address, name, review or menu item you can read in an image is ignored; the briefing already holds the real ones.

## 1. Sample the palette

```bash
.venv/bin/python manage.py sample_palette docs/mockups/00-master.png --k 8 --json
```

Open the master with the Read tool. Assign roles to the sampled colors by where they appear: page background, card/surface, body text, accent (buttons, prices, highlights), secondary (links, supporting), dark block. Use the sampled hex values, rounded to the nearest 4 per channel; keep the briefing's palette only where the image confirms it.

## 2. Classify the typography

From the master and the hero section: heading face (serif / sans / slab / display; contrast; weight), body face. Map to a concrete Google Fonts pair, for example:

| Seen in the image | Google Fonts |
|---|---|
| high-contrast transitional serif headings | Playfair Display |
| low-contrast humanist serif headings | Lora |
| geometric sans headings | Bricolage Grotesque, Manrope |
| grotesk body | Instrument Sans, Inter Tight |
| humanist sans body | Source Sans 3 |

Record the classification next to the choice so a reviewer can disagree with the mapping, not the observation.

## 3. Write `docs/design-system.md`

```markdown
# <Site> — Design System (from docs/mockups/00-master.png, <date>)

## Tokens

### Palette (SiteSettings fields)
| Role | Hex | Field |
|---|---|---|
| background | #… | background_color |
| surface | #… | (Tailwind arbitrary value in HTML) |
| text | #… | text_color |
| headings | #… | heading_color |
| accent | #… | primary_color, primary_button_bg |
| secondary | #… | secondary_color |
| dark block | #… | (Tailwind arbitrary value in HTML) |

### Type
- Heading: <font> (<classification>) — field heading_font
- Body: <font> (<classification>) — field body_font
- Scale (desktop / mobile): h1 <size>/<size>, h2 …, body 16–18px, eyebrow 11–12px uppercase tracked

### Layout
- container_width: <7xl | 6xl | …>  (content width seen ≈ <px>)
- border_radius_preset: <none | sm | md | lg | …>
- shadow_preset: <none | sm | md | …>
- spacing_scale: <tight | normal | relaxed | loose>  (section padding seen ≈ <px>)
- Grid: <e.g. 12 columns, text 5 / image 6 offset>
- Buttons: height ≈ <px>, padding <px>, radius <px>, primary filled accent, secondary outlined
- Dividers and motifs: <what and where>
- Photography: <treatment, warmth, crop style>; max render width per image group from the briefing's Images constraints

## Sections

### 01-hero (docs/mockups/01-hero.png)
- Layout: <grid / split / full-bleed>, image ratio <w:h>, image max width <px>
- Background: <token>
- Elements in order: <eyebrow, h1, lead, primary CTA, secondary CTA, badge…>
- Editable text: <which elements>
- Notes: <anything the build must reproduce, e.g. offset, overlay, divider>

### 02-… (one per rendered section)
```

## 4. Write back to the briefing

- `## Design Preferences`: replace the bullets with the token values (hex, font names, radius, layout signature, motif), keep the `Avoid` and `References` bullets and the `Reference mockup` line.
- `## Pages` → Home: rewrite the section list in the master's order; each entry `N. <name> — <purpose> — spec: docs/design-system.md#NN-<name>`. Facts (dish names, prices, hours, contacts) stay exactly as they were.

## 5. Write SiteSettings

```bash
.venv/bin/python manage.py shell -c "
from djangopress.core.models import SiteSettings
s = SiteSettings.load()
s.background_color = '<hex>'; s.text_color = '<hex>'; s.heading_color = '<hex>'
s.primary_color = '<hex>'; s.secondary_color = '<hex>'; s.accent_color = '<hex>'
s.primary_button_bg = '<hex>'; s.primary_button_text = '<hex>'
s.heading_font = '<font>'; s.body_font = '<font>'
s.container_width = '<value>'; s.border_radius_preset = '<value>'; s.shadow_preset = '<value>'; s.spacing_scale = '<value>'
s.design_guide = open('docs/design-system.md').read().split('## Sections')[0]
s.save(); print('design system written')
"
.venv/bin/python manage.py check_site --only settings || true
```

## 6. Commit and report

```bash
git add docs/design-system.md briefings/ docs/mockups/prompts docs/mockups/costs.json docs/mockups/.gitignore
git commit -m "Design system extracted from approved mockups"
```

Print the token table and the section list, then: `Next: /generate-site briefings/<slug>.md` (add `rebuild` when the site already has pages).
````

- [ ] **Step 2: Verify**

Run: `head -6 src/djangopress/skills/extract-design/SKILL.md && grep -n "^## " src/djangopress/skills/extract-design/SKILL.md && grep -c '^````' src/djangopress/skills/extract-design/SKILL.md && grep -n "container_width\b\|border_radius_preset\|shadow_preset\|spacing_scale" src/djangopress/core/models.py | head -4`
Expected: frontmatter `name: extract-design`; six numbered headings; four-backtick count `0`; the four model fields exist.

- [ ] **Step 3: Commit**

```bash
git add src/djangopress/skills/extract-design/SKILL.md
git commit -m "feat(skills): extract-design — design system and per-section specs from approved mockups"
```

---

### Task 6: `generate-site` gate and section-aware build; `create-briefing` hand-off

**Files:**
- Modify: `src/djangopress/skills/generate-site/SKILL.md` (sections "Two entry points", Phase 0, Phase 2, Phase 4, Phase 5, 8c, 8d)
- Modify: `src/djangopress/skills/create-briefing/SKILL.md` (Phase 3 hand-off only)

**Interfaces:**
- Consumes: `docs/mockups/00-master.png`, `docs/design-system.md` (Task 5 format), `docs/mockups/NN-<name>.png`, `mockup-site` modes `master` / `approve` / `section next` (Task 4).
- Produces: the argument form `/generate-site briefings/<slug>.md [rebuild]`; the build report field "Mockups used".

Use `grep -n` before each edit to find the current line; the anchors below are the exact current sentences.

- [ ] **Step 1: `generate-site` — entry points**

Replace the "Two entry points" section body (from `- **Fresh site**` to `Decide by reading the state in Phase 0.`) with:

```markdown
- **Fresh site** (no pages yet): run Phases 0–8. Stop after Phase 8.
- **Rebuild from mockups** (the site already has pages and `$ARGUMENTS` contains the word `rebuild`): run Phases 0–8, but in Phases 4–6 update the existing page, header and footer rows by slug/key instead of creating new ones. Call `create_version()` before every overwrite. Write only the default-language key and **delete the other language keys** from every `*_i18n` field you rewrite, so stale translations cannot fail `dom-parity`; the report tells the operator to re-run the translation pass.
- **Built site, translation requested** (pages exist, no `rebuild`, the operator asked for translation or the site passes `check_site` in the default language): run Phase 9 only.

Decide by reading the state in Phase 0.
```

- [ ] **Step 2: `generate-site` — Phase 0 gate**

Immediately after the Phase 0 shell block that ends with `check_site --json || true` and its following sentence, insert:

```markdown
### Mandatory mockup gate

```bash
test -f docs/mockups/00-master.png && echo "MASTER OK" || echo "MASTER MISSING"
test -f docs/design-system.md && echo "DESIGN SYSTEM OK" || echo "DESIGN SYSTEM MISSING"
```

If either is missing, stop here and print:

```
This build needs an approved mockup and an extracted design system.
  /mockup-site master         → look → approve <n>, or master <note> for another
  /mockup-site section next   → one section at a time → /extract-design
Then run /generate-site again.
```

There is no flag to bypass this gate. When both exist, read `docs/design-system.md` in full and list `docs/mockups/*.png`; you will open each section image while writing its HTML.
```

- [ ] **Step 3: `generate-site` — Phase 2**

Replace the Phase 2 paragraph that starts `Write \`SiteSettings.design_guide\` **now, before any page**, from Design Preferences.` and its bullet list and the save sentence, with:

```markdown
The design guide is the `## Tokens` part of `docs/design-system.md`, already written to `SiteSettings.design_guide` by `extract-design`. Confirm it is there (`len(s.design_guide) > 0` in the Phase 0 state dump); if it is empty, copy it now:

```bash
.venv/bin/python manage.py shell -c "
from djangopress.core.models import SiteSettings
s = SiteSettings.load()
s.design_guide = open('docs/design-system.md').read().split('## Sections')[0]
s.save(); print(len(s.design_guide), 'chars')
"
```

Do not derive a design guide from prose when a design system exists.
```

- [ ] **Step 4: `generate-site` — Phase 4 and Phase 5**

In Phase 4, after the first sentence (`Write the home page HTML in the default language to …`), insert:

```markdown
Build the page section by section in the order of `## Sections` in `docs/design-system.md`. For each section, open its image `docs/mockups/NN-<name>.png` with the Read tool and its `### NN-<name>` spec, then write that `<section data-section="<name>" id="<name>">` to match the image's layout, palette, type and rhythm — and take every word, number and link from the briefing, never from the image. The section name in the HTML is the `<name>` from the file name.
```

In Phase 5, add to the list of things given to each agent: `the section images and specs for its page (or, for inner pages without mockups, the home page's images as the style reference)`.

- [ ] **Step 5: `generate-site` — 8c and 8d**

In 8c, add an eighth checklist item: `8. Each section reads as the same design as its mockup in docs/mockups/ — same layout, palette, type and rhythm; content differs by design.`

In 8d's report template, under `## Result`, add the line `Mockups used: docs/mockups/00-master.png + <n> section images; design system: docs/design-system.md`.

In the `## Next` block of the report template, when the run was a rebuild, add the line `- Translation is stale: run /generate-site briefings/<slug>.md for the translation pass after review.`

- [ ] **Step 6: `create-briefing` — hand-off to the master, not the build**

Phases 0–2 and the question block are unchanged: the briefing is final before any image exists. In Phase 3, replace the hand-off `AskUserQuestion` block (from `AskUserQuestion:` through `If yes, invoke the \`generate-site\` skill … print the command and stop.`) with:

```markdown
```
AskUserQuestion:
Question: "Briefing finalizado. Gerar o primeiro master one-page?"
Options:
- "Sim — /mockup-site master" (Recommended)
- "Não — fico por aqui"
```

If yes, invoke the `mockup-site` skill with `master`. Non-interactively, print `Next: /mockup-site master` and stop. The build comes only after `/mockup-site approve <n>`, the sections and `/extract-design`, never directly from here.
```

- [ ] **Step 7: `create-briefing` — no other change**

Confirm with `grep -n "masters\|promote" src/djangopress/skills/create-briefing/SKILL.md` that the file contains neither word.

- [ ] **Step 8: Verify**

Run:

```bash
cd /Users/antoniomarante/Documents/djangopress-sites/djangopress
grep -n "Mandatory mockup gate\|Rebuild from mockups\|docs/design-system.md\|Mockups used\|reads as the same design" src/djangopress/skills/generate-site/SKILL.md
grep -n "/mockup-site master\|approve <n>\|generate-site" src/djangopress/skills/create-briefing/SKILL.md
grep -c "AskUserQuestion" src/djangopress/skills/generate-site/SKILL.md
grep -c '^````' src/djangopress/skills/generate-site/SKILL.md src/djangopress/skills/create-briefing/SKILL.md
wc -l src/djangopress/skills/generate-site/SKILL.md
```

Expected: every grep hits; `AskUserQuestion` count in generate-site still `1`; four-backtick counts `0`; generate-site under 320 lines. `create-briefing` must no longer invoke `generate-site` anywhere (the last grep's `generate-site` hits are only in prose saying the build comes later).

- [ ] **Step 9: Commit**

```bash
git add src/djangopress/skills/generate-site/SKILL.md src/djangopress/skills/create-briefing/SKILL.md
git commit -m "feat(skills): mandatory mockup gate and section-aware build; briefing hands off to the master"
```

---

### Task 7: Rollout — dependency pin, env example, docs, version

**Files:**
- Modify: `pyproject.toml` (dependency `"openai"` → `"openai>=2.36"`)
- Modify: `site_template/.env.example:30` (comment)
- Modify: `CLAUDE.md` (engine): skills table rows for `mockup-site` and `extract-design`; "Typical New Site Flow"; Commands block
- Modify: `/Users/antoniomarante/Documents/djangopress-sites/djangopress-manager/CLAUDE.md` (skills table + "New site from scratch" list; not committed)
- Modify: `src/djangopress/VERSION` via `bump_version minor`

- [ ] **Step 1: pyproject and env example**

In `pyproject.toml` change the dependency line `    "openai",` to `    "openai>=2.36",`. In `site_template/.env.example` change line 30 to `# OPENAI_API_KEY=your-openai-api-key   # used for gpt-image-2.5 mockups (mockup-site skill)`.

- [ ] **Step 2: Engine CLAUDE.md**

Add two rows to the skills table after the `/generate-site` row:

```markdown
| `/mockup-site` | `/mockup-site master` | One master one-page at a time from the final briefing (gpt-image-2.5-sunburst); approve one; render sections one at a time with a check after each; regenerate one; report costs. |
| `/extract-design` | `/extract-design` | Sampled palette, font pair, layout tokens and per-section UI specs from the approved mockups → `docs/design-system.md`, briefing, SiteSettings. |
```

Replace the "Typical New Site Flow" block with:

```
1. /create-briefing <url and/or document>   ← research, one block of questions, FINAL briefing.md
2. /mockup-site master                      ← one master one-page; approve <n>, or master <note> for another
3. /mockup-site section next                ← one section at a time from the master; ok → next, or a note
4. /extract-design                          ← design system + per-section specs
5. /generate-site briefings/my-client.md    ← unattended build (gated on the master + design system)
6. /edit-site ...                           ← interactive refinement
7. /generate-site briefings/my-client.md    ← translation pass, once design is signed off
8. /deploy-site-railway my-client           ← deploy to Railway (SQLite + Litestream)
```

In the `## Commands` code block, after the `check_site` line, add:

```
python manage.py generate_mockup --prompt-file F --out P [--ref R ...]   # one gpt-image-2.5 render, cost logged
python manage.py crop_mockup SRC OUT --top 0.0 --bottom 0.2              # crop a band of a mockup
python manage.py sample_palette IMG --k 6 --json                         # dominant colors of a mockup
```

- [ ] **Step 3: Manager CLAUDE.md (edit only, do not commit)**

In the DjangoPress skills table add rows for `mockup-site` and `extract-design` in the same four-column layout with "How to use from manager" = `` `cd <site.path>` then invoke ``. In "Typical Workflows → New site from scratch", insert after step 1: `2. /mockup-site master → one master at a time, approve` , `3. /mockup-site section next → sections one at a time` and `4. /extract-design → design system`, renumbering the rest.

- [ ] **Step 4: Bump version**

Run: `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py bump_version minor && cat /Users/antoniomarante/Documents/djangopress-sites/djangopress/src/djangopress/VERSION`
Expected: `3.7.0`.

- [ ] **Step 5: Full test run and sync**

Run: `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py test djangopress -v 1 2>&1 | grep -E "^(Ran|OK|FAILED)" && .venv/bin/python manage.py sync_skills | tail -3 && ls .claude/skills | grep -E "mockup-site|extract-design"`
Expected: `OK` with 196 + 34 = `Ran 230 tests`; sync reports the two new skills created; both listed.

- [ ] **Step 6: Commit the engine**

```bash
cd /Users/antoniomarante/Documents/djangopress-sites/djangopress
git add pyproject.toml site_template/.env.example CLAUDE.md src/djangopress/VERSION
git commit -m "docs: mockup pipeline in CLAUDE.md; openai>=2.36; bump version to 3.7.0"
```

---

### Task 8: Guided real-API test on O Marisco — first master only

**Files:**
- Create (in the site, not the engine): `/Users/antoniomarante/Documents/djangopress-sites/o-marisco/docs/mockups/prompts/00-master-v1.md`, `…/docs/mockups/master-v1.png`, `…/docs/mockups/costs.json`, `…/docs/mockups/.gitignore`

**Interfaces:**
- Consumes: the `mockup-site` skill via the site's symlink, `OPENAI_API_KEY` in `o-marisco/.env` (verified present), the final briefing `briefings/o-marisco.md`.
- Produces: one master and its measured cost, for the operator to approve or adjust. Nothing after `master` runs in this task — `approve`, `section next`, `extract-design` and the rebuild need the operator and happen interactively afterwards.

- [ ] **Step 1: Sync skills into the site and confirm the key**

```bash
cd /Users/antoniomarante/Documents/djangopress-sites/o-marisco
git branch --show-current            # expected: redesign-2026
.venv/bin/python manage.py sync_skills | tail -3
ls .claude/skills | grep -E "mockup-site|extract-design"
grep -c "^OPENAI_API_KEY=sk" .env    # expected: 1
grep -c "^## Open Questions" briefings/o-marisco.md   # expected: 0 (the briefing is final)
```

- [ ] **Step 2: Dry run**

Write the master prompt as the skill's `master` mode specifies (read `.claude/skills/mockup-site/SKILL.md`, follow its Setup and the prompt template using `briefings/o-marisco.md`), then:

```bash
.venv/bin/python manage.py generate_mockup --prompt-file docs/mockups/prompts/00-master-v1.md \
  --out docs/mockups/master-v1.png --model sunburst --size 1280x3840 --quality high --dry-run
```

Expected: `dry run: generations model=gpt-image-2.5-sunburst size=1280x3840 quality=high refs=0 …` and the first 800 characters of the prompt. Read the prompt back: it must contain the briefing's palette hexes, "Bricolage Grotesque", the Avoid list ("azul-marinho náutico", "tipografia script", "fotografia de barcos", "âncora e leme"), and no prices or addresses.

- [ ] **Step 3: Render the first master (real API, well under $1)**

Run the `generate_mockup` call exactly as the skill's `master` mode specifies, with `--budget 2`. Expected: `wrote docs/mockups/master-v1.png 1280x3840 $… (…s) site total $…`.

- [ ] **Step 4: Look at it**

Open the PNG with the Read tool. Note in the report: does it follow the section order from the briefing; does it respect the Avoid list; is the palette recognisably cal/terracota/azul-maré; is the text legible enough to judge hierarchy. Do not fix anything; this is evidence for the operator.

- [ ] **Step 5: Commit prompt and costs in the site (PNGs stay ignored)**

```bash
git add docs/mockups/.gitignore docs/mockups/prompts docs/mockups/costs.json
git commit -m "Add first master mockup prompt and cost log"
```

- [ ] **Step 6: Report**

Report the path, the cost and elapsed time from `costs.json`, the observations from Step 4, and the two next commands for the operator: `/mockup-site approve 1` or `/mockup-site master <what to change>`.

---

## Self-review against the spec

- **Component 1** → Task 1 (module, 19 tests). **Component 2** → Task 2 (command, 8 tests; `--budget`, `--dry-run`, costs file, edits vs generations). **Component 3** → Task 3 `crop_mockup`. **Component 4** → Task 3 `sample_palette` with `kmeans_palette`. **Component 5** → Task 4 (modes `master`, `approve`, `section next`, `section <name>`, `sections`, `costs`; size table; long-page halves; prompt files; `sections.json`; `.gitignore`). **Component 6** → Task 5. **Component 7** → Task 6 Steps 1–5 (gate with no bypass, design guide from design system, section-by-section build, checklist item, report line) plus the `rebuild` entry point needed for the O Marisco test. **Component 8** → Task 6 Steps 6–7 (hand-off only). **Component 9** → Task 7 (pin, env example, CLAUDE.md, version, sync) and Task 8 (first real run, one master, operator approves or adjusts).
- **Type consistency:** `generate(prompt, *, size, quality, model, client)` / `edit(prompt, *, references, size, quality, model, input_fidelity, client)` are the same in Task 1's module and tests and in Task 2's command; `ImageResult` fields used by the command (`png_bytes`, `usage.text_in/image_in/image_out`, `cost_usd`, `model`, `size`, `quality`, `elapsed_s`) are the ones defined; `get_client` is patched at `djangopress.ai.management.commands.generate_mockup.get_client`, which exists because the command imports it by name; the costs record keys in Task 2 match what the `costs` mode of Task 4 prints; file names `docs/mockups/00-master.png`, `NN-<name>.png`, `docs/design-system.md` and the `### NN-<name>` spec headings are identical across Tasks 4, 5 and 6.
- **Placeholder scan:** none.
