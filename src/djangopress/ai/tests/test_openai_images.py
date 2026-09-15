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
