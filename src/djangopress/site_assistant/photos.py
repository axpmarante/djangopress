"""Image references the assistant passes around: "lib:<id>" (media library),
a bare library id, or "unsplash:<id>" (downloaded into the library first)."""
import re
import unicodedata

from django.core.files.base import ContentFile

from djangopress.ai.utils import unsplash
from djangopress.core.models import SiteImage

MAX_RESULTS = 8


def _tokens(text):
    plain = unicodedata.normalize('NFKD', str(text or '').lower())
    plain = ''.join(c for c in plain if not unicodedata.combining(c))
    return {w for w in re.findall(r'[a-z0-9]+', plain) if len(w) >= 3}


def _matches(word, haystack):
    return word in haystack or any(len(h) >= 4 and (h.startswith(word) or word.startswith(h)) for h in haystack)


def _library(query, limit):
    words = _tokens(query)
    scored = []
    for image in SiteImage.objects.filter(is_active=True).exclude(image=''):
        text = ' '.join([*(image.title_i18n or {}).values(), *(image.alt_text_i18n or {}).values(),
                         image.tags or '', image.description or '', image.key or ''])
        haystack = _tokens(text)
        score = sum(1 for w in words if _matches(w, haystack))
        if score:
            scored.append((score, image.pk, image))
    scored.sort(key=lambda t: (-t[0], -t[1]))
    return [{'ref': f'lib:{image.pk}', 'source': 'library',
             'title': next(iter((image.title_i18n or {}).values()), '') or image.key,
             'thumb_url': image.image.url, 'credit': ''} for _s, _pk, image in scored[:limit]]


def find_photos(query, source='both', orientation=None):
    """Up to 8 candidates [{ref, source, title, thumb_url, credit}] and a note for the model."""
    notes = []
    found = []
    want_unsplash = source in ('both', 'unsplash')
    if want_unsplash and not unsplash.is_configured():
        notes.append('Unsplash is not configured on this site, so only the media library was searched.')
        want_unsplash = False
        source = 'library'
    if source in ('both', 'library'):
        found = _library(query, MAX_RESULTS // 2 if want_unsplash else MAX_RESULTS)
    if want_unsplash:
        for hit in unsplash.search_photos(query, per_page=MAX_RESULTS - len(found), orientation=orientation or None):
            found.append({'ref': f'unsplash:{hit["id"]}', 'source': 'unsplash', 'title': hit.get('alt_description', ''),
                          'thumb_url': hit.get('thumb_url', ''),
                          'credit': f'Photo by {hit.get("photographer") or "unknown"} on Unsplash'})
    if not found:
        notes.append('No photos found; try other words (English works best for Unsplash).')
    return found[:MAX_RESULTS], ' '.join(notes)


def ensure_library_image(ref):
    """The SiteImage for a ref, downloading an Unsplash photo into the library once."""
    text = str(ref or '').strip()
    if not text.startswith('unsplash:'):
        return resolve_image(text)
    photo_id = text.split(':', 1)[1]
    key = 'unsplash-' + re.sub(r'[^a-z0-9-]', '', photo_id.lower())[:40]
    existing = SiteImage.objects.filter(key=key).first()
    if existing is not None and existing.image:
        return existing
    if not unsplash.is_configured():
        raise ValueError('Unsplash is not configured on this site')
    info = unsplash.get_photo(photo_id)
    if not info or not info.get('regular_url'):
        raise ValueError(f'Unsplash photo {photo_id} not found')
    data = unsplash.download_photo(photo_id, info['regular_url'])
    if not data:
        raise ValueError(f'Could not download Unsplash photo {photo_id}')
    from djangopress.ai.utils.llm_config import optimize_generated_image
    data = optimize_generated_image(data, max_width=1600, quality=85)

    from djangopress.core.models import SiteSettings
    settings = SiteSettings.load()
    codes = [lang['code'] if isinstance(lang, dict) else lang for lang in (settings.enabled_languages or [])] or ['pt']
    title = (info.get('alt_description') or 'Unsplash photo').strip()[:100]
    credit = f'Photo by {info.get("photographer") or "unknown"} on Unsplash'
    image = existing or SiteImage(key=key)
    image.title_i18n = {code: title for code in codes}
    image.alt_text_i18n = {code: title for code in codes}
    image.tags = ', '.join(filter(None, ['unsplash', f'Photo by {info.get("photographer")}' if info.get('photographer') else '']))
    image.description = f'{title}. {credit} ({info.get("photographer_url") or "https://unsplash.com"}).'
    image.is_active = True
    image.image.save(f'{key}.jpg', ContentFile(data), save=True)
    return image


def resolve_image(ref):
    """The SiteImage a ref points at. Raises ValueError with a message for the model."""
    text = str(ref or '').strip()
    if text.startswith('unsplash:'):
        return ensure_library_image(text)
    if text.startswith('lib:'):
        text = text[4:]
    if text.isdigit():
        image = SiteImage.objects.filter(pk=int(text), is_active=True).first()
        if image is None or not image.image:
            raise ValueError(f'No library image with id {text}')
        return image
    raise ValueError(f'Unknown image reference "{ref}". Use lib:<id> or unsplash:<id> from find_photos.')


def image_payload(image, lang):
    """The {id, url, alt} shape the editor's component operations take."""
    alt = (image.alt_text_i18n or {}).get(lang) or (image.title_i18n or {}).get(lang) or ''
    return {'id': str(image.pk), 'url': image.image.url, 'alt': alt}
