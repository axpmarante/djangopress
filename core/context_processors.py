from .models import SiteSettings, SiteImage


def site_settings(request):
    """Make site settings available in all templates"""
    settings = SiteSettings.load()

    social_media = {
        'facebook': settings.facebook_url,
        'instagram': settings.instagram_url,
        'linkedin': settings.linkedin_url,
        'twitter': settings.twitter_url,
    }

    return {
        'SITE_NAME': settings.site_name,
        'SITE_DESCRIPTION': settings.site_description,
        'SITE_LOGO': settings.logo,
        'CONTACT_EMAIL': settings.contact_email,
        'CONTACT_PHONE': settings.contact_phone,
        'CONTACT_ADDRESS': settings.contact_address,
        'SOCIAL_MEDIA': social_media,
        'META_KEYWORDS': settings.meta_keywords,
        'GOOGLE_ANALYTICS_ID': settings.google_analytics_id,
    }


def site_images(request):
    """Make site images available in all templates"""
    images = {}
    for image in SiteImage.objects.filter(is_active=True):
        images[image.key] = {
            'url': image.image.url,
            'alt': image.alt_text or image.title,
            'title': image.title
        }
    return {'SITE_IMAGES': images}
