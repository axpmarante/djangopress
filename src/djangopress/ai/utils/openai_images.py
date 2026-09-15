"""
OpenAI image generation for site mockups.

Two models are available: gpt-image-2.5-sunburst is used for every master
and every section, one at a time, and gpt-image-2.5-flare is an explicit
cheap option an operator can opt into per call. Masters use the generations
endpoint; sections use the edits endpoint with the master (and optionally a
crop) as reference images.

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
    exc_str = str(exc).lower()
    if 'insufficient_quota' in exc_str or 'credit_balance_exhausted' in exc_str:
        return False
    status = getattr(exc, 'status_code', None)
    if status == 429:
        return True
    name = exc.__class__.__name__
    if name in ('RateLimitError', 'APIConnectionError', 'APITimeoutError'):
        return True
    return isinstance(status, int) and status >= 500


def get_client():
    key = get_env('OPENAI_API_KEY')
    if not key:
        raise ImageGenerationError('OPENAI_API_KEY is not set — put it in the DjangoPress Manager .env (it is injected into site processes) or export it in this shell')
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
         model: str = 'sunburst', client=None) -> ImageResult:
    """Reference-guided render via the edits endpoint.

    gpt-image-2.5 rejects `input_fidelity` (verified against the live API), so it is
    never sent; the models weigh reference images on their own.
    """
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
    files = []
    started = time.time()
    try:
        for p in paths:
            files.append(open(p, 'rb'))
        response = _call_with_retries(
            client.images.edit,
            model=model_id, image=files, prompt=prompt, size=size, quality=quality,
            n=1, output_format='png',
        )
    finally:
        for f in files:
            f.close()
    return _result(response, model=model_id, size=size, quality=quality, started=started)
