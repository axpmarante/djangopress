"""Image editor for the media library: rotate, flip, crop and resize.

The browser sends the list of steps the user kept (after undo/redo); the steps
are replayed here with Pillow on the stored file, so the result is full
quality and keeps the original format. The edited image is written as a new
file (production storage never overwrites, and a new URL can't be served from
a stale cache) and every page, global section, news post and news layout that
used the old file is pointed at the new one. The first original is remembered
on SiteImage.original_image so "Restore original" can put it back.
"""

import io
import logging
import os
import re

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

EDITABLE_FORMATS = {'JPEG', 'PNG', 'WEBP'}
EDITABLE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
MAX_OPERATIONS = 200
MAX_DIMENSION = 10000

_EDITED_SUFFIX = re.compile(r'-edited-\d+$')


class ImageEditError(ValueError):
    """A request the editor can't carry out; the message is shown to the user."""


def is_editable(site_image):
    """True when the media item is a raster image the editor can save back."""
    if site_image.is_pdf or not site_image.image:
        return False
    return os.path.splitext(site_image.image.name)[1].lower() in EDITABLE_EXTENSIONS


def _int(value, name):
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        raise ImageEditError(f'Invalid {name}.')


def apply_operations(img, operations):
    """Replay the editor's steps on a PIL image and return the result."""
    if not isinstance(operations, list):
        raise ImageEditError('Invalid list of edits.')
    if len(operations) > MAX_OPERATIONS:
        raise ImageEditError('Too many edits in one save.')

    for op in operations:
        if not isinstance(op, dict):
            raise ImageEditError('Invalid edit.')
        kind = op.get('op')
        if kind == 'rotate':
            deg = _int(op.get('deg'), 'rotation') % 360
            if deg == 90:
                img = img.transpose(Image.Transpose.ROTATE_270)  # Pillow rotates counterclockwise
            elif deg == 180:
                img = img.transpose(Image.Transpose.ROTATE_180)
            elif deg == 270:
                img = img.transpose(Image.Transpose.ROTATE_90)
            elif deg != 0:
                raise ImageEditError('Images can only be rotated in steps of 90°.')
        elif kind == 'flip':
            axis = op.get('axis')
            if axis == 'h':
                img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            elif axis == 'v':
                img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            else:
                raise ImageEditError('Invalid flip direction.')
        elif kind == 'crop':
            x, y = _int(op.get('x'), 'crop'), _int(op.get('y'), 'crop')
            w, h = _int(op.get('width'), 'crop'), _int(op.get('height'), 'crop')
            left, top = max(0, x), max(0, y)
            right, bottom = min(img.width, x + w), min(img.height, y + h)
            if right - left < 1 or bottom - top < 1:
                raise ImageEditError('The crop area is outside the image.')
            img = img.crop((left, top, right, bottom))
        elif kind == 'resize':
            w, h = _int(op.get('width'), 'width'), _int(op.get('height'), 'height')
            if not (1 <= w <= MAX_DIMENSION and 1 <= h <= MAX_DIMENSION):
                raise ImageEditError(f'Width and height must be between 1 and {MAX_DIMENSION} pixels.')
            img = img.resize((w, h), Image.Resampling.LANCZOS)
        else:
            raise ImageEditError(f'Unknown edit "{kind}".')
    return img


def _encode(img, fmt, icc_profile=None):
    buf = io.BytesIO()
    params = {}
    if icc_profile:
        params['icc_profile'] = icc_profile
    if fmt == 'JPEG':
        if img.mode not in ('RGB', 'L', 'CMYK'):
            img = img.convert('RGB')
        params.update(quality=90, optimize=True)
    elif fmt == 'PNG':
        params.update(optimize=True)
    elif fmt == 'WEBP':
        params.update(quality=90)
    img.save(buf, fmt, **params)
    return buf.getvalue()


def _edited_name(current_name, original_name):
    base = original_name or current_name
    stem, ext = os.path.splitext(os.path.basename(base))
    stem = _EDITED_SUFFIX.sub('', stem)
    folder = os.path.dirname(current_name) or 'site_images'
    stamp = timezone.now().strftime('%Y%m%d%H%M%S')
    return f'{folder}/{stem}-edited-{stamp}{ext.lower()}'


def _replace_in_i18n(value, pattern, new_name):
    """Return (new_dict, changed) with the file name swapped in every language."""
    if not isinstance(value, dict):
        return value, False
    out, changed = {}, False
    for lang, html in value.items():
        if isinstance(html, str):
            new_html = pattern.sub(new_name, html)
            changed = changed or new_html != html
            out[lang] = new_html
        else:
            out[lang] = html
    return out, changed


def replace_references(old_name, new_name, user=None):
    """Point every page, global section, news post and news layout at new_name.

    Matches the storage name after a '/', so both absolute bucket URLs and
    /media/ URLs are caught, and a longer name that merely starts with the
    same characters (photo.png.webp) is left alone. Pages, sections and posts
    get a version first so the change shows (and can be undone) in history.
    """
    from djangopress.core.models import GlobalSection, Page
    from djangopress.news.models import NewsLayout, NewsPost

    pattern = re.compile(r'(?<=/)' + re.escape(old_name) + r'(?![\w.\-])')
    summary = f'Image replaced by the image editor ({os.path.basename(new_name)})'
    lang = _default_language()
    result = {'pages': [], 'sections': [], 'news': [], 'layouts': []}

    for page in Page.objects.all():
        new_value, changed = _replace_in_i18n(page.html_content_i18n, pattern, new_name)
        if changed:
            page.create_version(user=user, change_summary=summary, kind='checkpoint')
            page.html_content_i18n = new_value
            page.save()
            result['pages'].append((page.title_i18n or {}).get(lang) or str(page))

    for section in GlobalSection.objects.all():
        new_value, changed = _replace_in_i18n(section.html_template_i18n, pattern, new_name)
        if changed:
            section.create_version(change_summary=summary)
            section.html_template_i18n = new_value
            section.save()
            result['sections'].append(section.key)

    for post in NewsPost.objects.all():
        new_value, changed = _replace_in_i18n(post.html_content_i18n, pattern, new_name)
        if changed:
            post.create_version(user=user, change_summary=summary)
            post.html_content_i18n = new_value
            post.save()
            result['news'].append((post.title_i18n or {}).get(lang) or str(post))

    for layout in NewsLayout.objects.all():
        new_value, changed = _replace_in_i18n(layout.html_content_i18n, pattern, new_name)
        if changed:
            layout.html_content_i18n = new_value
            layout.save()
            result['layouts'].append(layout.key)

    return result


def _default_language():
    from djangopress.core.models import SiteSettings
    try:
        return SiteSettings.load().get_default_language()
    except Exception:
        return 'pt'


def save_edited(site_image, operations, user=None):
    """Apply the steps, store the result as a new file and swap every reference."""
    if not is_editable(site_image):
        raise ImageEditError('Only JPEG, PNG and WebP images can be edited.')
    if not operations:
        raise ImageEditError('There are no edits to save.')

    field = site_image.image
    storage = field.storage
    with field.open('rb') as fh:
        src = Image.open(fh)
        fmt = src.format
        if fmt not in EDITABLE_FORMATS:
            raise ImageEditError('Only JPEG, PNG and WebP images can be edited.')
        if getattr(src, 'is_animated', False):
            raise ImageEditError('Animated images can\'t be edited.')
        icc_profile = src.info.get('icc_profile')
        src.load()
    # Browsers draw a photo upright from its EXIF orientation; do the same so
    # the steps the user saw are the steps applied here.
    img = ImageOps.exif_transpose(src)

    edited = apply_operations(img, operations)
    data = _encode(edited, fmt, icc_profile)

    old_name = field.name
    new_name = storage.save(_edited_name(old_name, site_image.original_image), ContentFile(data))

    with transaction.atomic():
        if not site_image.original_image:
            site_image.original_image = old_name
        site_image.image.name = new_name
        site_image.save(update_fields=['image', 'original_image', 'updated_at'])
        result = replace_references(old_name, new_name, user=user)

    logger.info('Image %s edited: %s -> %s', site_image.pk, old_name, new_name)
    result['url'] = site_image.image.url
    result['width'], result['height'] = edited.size
    return result


def restore_original(site_image, user=None):
    """Put the file from before the first edit back, everywhere it was used."""
    original = site_image.original_image
    if not original:
        raise ImageEditError('This image has no original to restore.')
    if not site_image.image.storage.exists(original):
        raise ImageEditError('The original file is no longer in storage.')

    old_name = site_image.image.name
    with transaction.atomic():
        site_image.image.name = original
        site_image.original_image = ''
        site_image.save(update_fields=['image', 'original_image', 'updated_at'])
        result = replace_references(old_name, original, user=user)

    logger.info('Image %s restored to %s', site_image.pk, original)
    result['url'] = site_image.image.url
    return result


def describe_changes(result):
    """One short sentence for the backoffice message, e.g. 'updated in 2 pages and the header'."""
    parts = []
    pages = result.get('pages') or []
    if pages:
        parts.append(f'{len(pages)} page{"s" if len(pages) != 1 else ""}')
    parts.extend(result.get('sections') or [])
    news = result.get('news') or []
    if news:
        parts.append(f'{len(news)} news post{"s" if len(news) != 1 else ""}')
    layouts = result.get('layouts') or []
    if layouts:
        parts.append(f'{len(layouts)} news layout{"s" if len(layouts) != 1 else ""}')
    if not parts:
        return 'not used on any page yet'
    if len(parts) == 1:
        return f'updated in {parts[0]}'
    return f'updated in {", ".join(parts[:-1])} and {parts[-1]}'
