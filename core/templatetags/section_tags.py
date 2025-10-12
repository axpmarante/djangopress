from django import template
from django.urls import reverse

register = template.Library()


@register.inclusion_tag('partials/global_sections/cta.html')
def cta_section(title=None, text=None, button_text=None, button_url=None):
    """Render a call-to-action section"""
    return {
        'section_title': title,
        'section_text': text,
        'button_text': button_text,
        'button_url': button_url or reverse('core:contact'),
    }


@register.simple_tag
def site_image(key, default=None, css_class=None):
    """Render an image by its key with optional fallback and CSS class"""
    from core.models import SiteImage
    from django.utils.safestring import mark_safe

    try:
        image = SiteImage.objects.get(key=key, is_active=True)
        img_url = image.image.url
        alt_text = image.alt_text or image.title
    except SiteImage.DoesNotExist:
        if default:
            img_url = default
            alt_text = key.replace('_', ' ').title()
        else:
            return ''

    class_attr = f' class="{css_class}"' if css_class else ''
    return mark_safe(f'<img src="{img_url}" alt="{alt_text}"{class_attr}>')
