"""Image references the assistant passes around: "lib:<id>" (media library),
a bare library id, or "unsplash:<id>" (downloaded into the library first)."""
from djangopress.core.models import SiteImage


def resolve_image(ref):
    """The SiteImage a ref points at. Raises ValueError with a message for the model."""
    text = str(ref or '').strip()
    if text.startswith('lib:'):
        text = text[4:]
    if text.isdigit():
        image = SiteImage.objects.filter(pk=int(text), is_active=True).first()
        if image is None or not image.image:
            raise ValueError(f'No library image with id {text}')
        return image
    raise ValueError(f'Unknown image reference "{ref}". Use lib:<id> from list_images or find_photos.')


def image_payload(image, lang):
    """The {id, url, alt} shape the editor's component operations take."""
    alt = (image.alt_text_i18n or {}).get(lang) or (image.title_i18n or {}).get(lang) or ''
    return {'id': str(image.pk), 'url': image.image.url, 'alt': alt}
