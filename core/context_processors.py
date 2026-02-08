from .models import SiteSettings, SiteImage, MenuItem


def site_settings(request):
    """Make site settings available in all templates"""
    settings = SiteSettings.load()

    social_media = {
        'facebook': settings.facebook_url,
        'instagram': settings.instagram_url,
        'linkedin': settings.linkedin_url,
        'twitter': settings.twitter_url,
    }

    # Button classes based on settings
    button_radius = {
        'rounded': 'rounded-md',
        'square': 'rounded-none',
        'pill': 'rounded-full',
    }.get(settings.button_style, 'rounded-md')

    button_padding = {
        'small': 'px-6 py-2 text-sm',
        'medium': 'px-8 py-3',
        'large': 'px-10 py-4 text-lg',
    }.get(settings.button_size, 'px-8 py-3')

    # Container width class mapping
    container_width_class = f"max-w-{settings.container_width}" if settings.container_width != 'full' else "w-full"

    # Border radius class mapping
    border_radius_class = f"rounded-{settings.border_radius_preset}" if settings.border_radius_preset != 'none' else "rounded-none"

    # Shadow class mapping
    shadow_class = f"shadow-{settings.shadow_preset}" if settings.shadow_preset != 'none' else "shadow-none"

    # Spacing scale mapping (for section padding)
    spacing_scale_map = {
        'tight': 'py-8 px-4',
        'normal': 'py-12 px-6',
        'relaxed': 'py-16 px-8',
        'loose': 'py-20 px-10',
    }
    spacing_class = spacing_scale_map.get(settings.spacing_scale, 'py-12 px-6')

    # Button border width mapping
    button_border_class = f"border-{settings.button_border_width}" if settings.button_border_width != '0' else "border-0"

    # Menu items (top-level with children prefetched)
    menu_items = MenuItem.objects.filter(
        is_active=True, parent__isnull=True
    ).select_related('page').prefetch_related('children')

    return {
        'FAVICON': settings.favicon if settings.favicon else None,
        'MENU_ITEMS': menu_items,

        # OLD: Backward compatible (using modeltranslation, will be removed later)
        'SITE_NAME': settings.site_name,
        'SITE_DESCRIPTION': settings.site_description,
        'CONTACT_ADDRESS': settings.contact_address,
        'PROJECT_BRIEFING': settings.project_briefing,

        # NEW: JSON translation fields (use with get_translation filter)
        'SITE_NAME_I18N': settings.site_name_i18n,
        'SITE_DESCRIPTION_I18N': settings.site_description_i18n,
        'CONTACT_ADDRESS_I18N': settings.contact_address_i18n,

        # Pass entire settings object for helper methods
        'site_settings': settings,

        # Non-translatable fields
        'LOGO': settings.logo if settings.logo else None,
        'SITE_LOGO': settings.logo if settings.logo else None,  # Keep for backwards compatibility
        'LOGO_DARK_BG': settings.logo_dark_bg if settings.logo_dark_bg else None,
        'SITE_LOGO_DARK_BG': settings.logo_dark_bg if settings.logo_dark_bg else None,
        'CONTACT_EMAIL': settings.contact_email,
        'CONTACT_PHONE': settings.contact_phone,
        'SOCIAL_MEDIA': social_media,
        'META_KEYWORDS': settings.meta_keywords,
        'GOOGLE_ANALYTICS_ID': settings.google_analytics_id,
        'GOOGLE_MAPS_EMBED_URL': settings.google_maps_embed_url,
        'GOOGLE_FONTS_URL': settings.get_google_fonts_url(),

        # Social Media URLs (individual)
        'FACEBOOK_URL': settings.facebook_url,
        'INSTAGRAM_URL': settings.instagram_url,
        'LINKEDIN_URL': settings.linkedin_url,
        'YOUTUBE_URL': settings.youtube_url,
        'TWITTER_URL': settings.twitter_url,

        # Design System
        'THEME': {
            # Colors
            'primary_color': settings.primary_color,
            'primary_color_hover': settings.primary_color_hover,
            'secondary_color': settings.secondary_color,
            'accent_color': settings.accent_color,
            'background_color': settings.background_color,
            'text_color': settings.text_color,
            'heading_color': settings.heading_color,

            # Typography - General
            'heading_font': settings.heading_font,
            'body_font': settings.body_font,

            # Typography - Individual Headings
            'h1_font': settings.h1_font,
            'h1_size': settings.h1_size,
            'h2_font': settings.h2_font,
            'h2_size': settings.h2_size,
            'h3_font': settings.h3_font,
            'h3_size': settings.h3_size,
            'h4_font': settings.h4_font,
            'h4_size': settings.h4_size,
            'h5_font': settings.h5_font,
            'h5_size': settings.h5_size,
            'h6_font': settings.h6_font,
            'h6_size': settings.h6_size,

            # Layout
            'container_width': settings.container_width,
            'container_width_class': container_width_class,
            'border_radius_preset': settings.border_radius_preset,
            'border_radius_class': border_radius_class,
            'spacing_scale': settings.spacing_scale,
            'spacing_class': spacing_class,
            'shadow_preset': settings.shadow_preset,
            'shadow_class': shadow_class,

            # Buttons - Style & Size
            'button_style': settings.button_style,
            'button_size': settings.button_size,
            'button_radius': button_radius,
            'button_padding': button_padding,
            'button_border_width': settings.button_border_width,
            'button_border_class': button_border_class,

            # Buttons - Primary Colors
            'primary_button_bg': settings.primary_button_bg,
            'primary_button_text': settings.primary_button_text,
            'primary_button_border': settings.primary_button_border,
            'primary_button_hover': settings.primary_button_hover,

            # Buttons - Secondary Colors
            'secondary_button_bg': settings.secondary_button_bg,
            'secondary_button_text': settings.secondary_button_text,
            'secondary_button_border': settings.secondary_button_border,
            'secondary_button_hover': settings.secondary_button_hover,
        },

        # Language Settings (Dynamic)
        'SITE_LANGUAGES': settings.get_enabled_languages(),
        'DEFAULT_LANGUAGE': settings.get_default_language(),
        'LANGUAGE_CODES': settings.get_language_codes(),
    }
