"""Files already on the site (a PDF menu, a brochure, an image) that the assistant can read.

Only the site's own storage is read, never an outside URL: a link to another site has to be
downloaded and attached to the chat by the user.
"""
import mimetypes
from urllib.parse import unquote, urlsplit

from django.core.files.storage import default_storage

MAX_BYTES = 20 * 1024 * 1024   # Gemini's inline limit is ~20 MB per request


def _is_readable(mime_type):
    return mime_type == 'application/pdf' or (mime_type or '').startswith('image/')


def _library_file(item):
    """(storage name, title) of a media library row, or None when it has no file."""
    field = item.file if item.file else item.image
    if not field:
        return None
    return field.name, str(item)


def _from_url(url):
    """(storage name, title) for a URL that points into this site's storage."""
    from djangopress.core.models import SiteImage
    path = unquote(urlsplit(url.strip()).path)
    for item in SiteImage.objects.all():
        found = _library_file(item)
        if found and path.endswith('/' + found[0]):
            return found
    base = unquote(urlsplit(default_storage.url('')).path)
    if base and base != '/' and path.startswith(base):
        name = path[len(base):]
        if name and default_storage.exists(name):
            return name, name.rsplit('/', 1)[-1]
    return None


def load(file_id=None, url=None):
    """{'bytes', 'mime_type', 'title', 'name'} for a file of this site; ValueError with a reason otherwise."""
    from djangopress.core.models import SiteImage
    if file_id not in (None, ''):
        item = SiteImage.objects.filter(pk=file_id).first()
        found = _library_file(item) if item else None
        if not found:
            raise ValueError(f'No file with id {file_id} in the media library (see list_images).')
    elif url:
        found = _from_url(url)
        if not found:
            raise ValueError('That link is not a file of this site. Ask the user to download it and attach it '
                             'to the chat (the paperclip), or to upload it in /backoffice/media/.')
    else:
        raise ValueError('Pass file_id (from list_images) or url.')

    name, title = found
    mime_type = mimetypes.guess_type(name)[0] or ''
    if not _is_readable(mime_type):
        raise ValueError(f'"{name}" is not a PDF or an image; only those can be read.')
    try:
        size = default_storage.size(name)
        if size > MAX_BYTES:
            raise ValueError(f'"{name}" is {size / 1024 / 1024:.0f} MB; the limit is {MAX_BYTES // 1024 // 1024} MB.')
        with default_storage.open(name, 'rb') as fh:
            data = fh.read()
    except ValueError:
        raise
    except Exception as e:   # missing in storage, network error
        raise ValueError(f'Could not open "{name}" from the site\'s storage ({e.__class__.__name__}). '
                         f'Ask the user to attach the file to the chat.')
    return {'bytes': data, 'mime_type': mime_type, 'title': title, 'name': name}
