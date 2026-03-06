"""
Unsplash API client — lightweight wrapper using urllib (no extra dependencies).
"""
import json
import urllib.request
import urllib.parse
import urllib.error
from django.conf import settings


def is_configured():
    """Return True if the Unsplash API key is set."""
    return bool(getattr(settings, 'UNSPLASH_ACCESS_KEY', ''))


def search_photos(query, per_page=9, orientation=None):
    """
    Search Unsplash photos.

    Args:
        query: Search term (e.g. "modern office interior")
        per_page: Number of results (max 30, default 9)
        orientation: Optional filter — 'landscape', 'portrait', or 'squarish'

    Returns:
        List of dicts: {id, thumb_url, regular_url, alt_description, photographer, photographer_url}
        Empty list if not configured or on error.
    """
    if not is_configured():
        return []

    params = {
        'query': query,
        'per_page': str(min(per_page, 30)),
    }
    if orientation:
        params['orientation'] = orientation

    url = 'https://api.unsplash.com/search/photos?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        'Authorization': f'Client-ID {settings.UNSPLASH_ACCESS_KEY}',
        'Accept-Version': 'v1',
    })

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as e:
        print(f'Unsplash search error: {e}')
        return []

    results = []
    for photo in data.get('results', []):
        urls = photo.get('urls', {})
        user = photo.get('user', {})
        results.append({
            'id': photo.get('id', ''),
            'thumb_url': urls.get('thumb', ''),
            'regular_url': urls.get('regular', ''),
            'alt_description': photo.get('alt_description') or photo.get('description') or '',
            'photographer': user.get('name', ''),
            'photographer_url': user.get('links', {}).get('html', ''),
        })

    return results


def download_photo(photo_id, regular_url):
    """
    Download a photo from Unsplash.

    1. Triggers the Unsplash download tracking endpoint (required by API guidelines).
    2. Fetches the image bytes from the regular_url.

    Args:
        photo_id: Unsplash photo ID (for download tracking)
        regular_url: The regular-size URL to fetch image bytes from

    Returns:
        Image bytes, or None on error.
    """
    if not is_configured():
        return None

    # 1. Trigger download tracking (Unsplash API requirement)
    track_url = f'https://api.unsplash.com/photos/{photo_id}/download'
    track_req = urllib.request.Request(track_url, headers={
        'Authorization': f'Client-ID {settings.UNSPLASH_ACCESS_KEY}',
        'Accept-Version': 'v1',
    })
    try:
        with urllib.request.urlopen(track_req, timeout=10):
            pass
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        print(f'Unsplash download tracking error: {e}')

    # 2. Fetch image bytes from regular_url
    try:
        img_req = urllib.request.Request(regular_url, headers={
            'User-Agent': 'DjangoPress CMS',
        })
        with urllib.request.urlopen(img_req, timeout=30) as resp:
            return resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        print(f'Unsplash image download error: {e}')
        return None
