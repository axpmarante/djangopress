"""SettingsService — site settings management."""

import logging
from core.models import SiteSettings, Page, SiteImage, MenuItem, FormSubmission

logger = logging.getLogger(__name__)

SETTINGS_ALLOWLIST = {
    'contact_email', 'contact_phone', 'site_name_i18n', 'site_description_i18n',
    'contact_address_i18n', 'facebook_url', 'instagram_url', 'linkedin_url',
    'twitter_url', 'youtube_url', 'google_maps_embed_url', 'maintenance_mode',
    'primary_color', 'primary_color_hover', 'secondary_color', 'accent_color',
    'background_color', 'text_color', 'heading_color',
    'heading_font', 'body_font',
    'container_width', 'border_radius_preset',
    'button_style', 'button_size',
    'primary_button_bg', 'primary_button_text', 'primary_button_border', 'primary_button_hover',
    'secondary_button_bg', 'secondary_button_text', 'secondary_button_border', 'secondary_button_hover',
    'design_guide', 'project_briefing',
}


class SettingsService:

    @staticmethod
    def get(fields=None):
        """Get site settings, optionally filtered by field names."""
        settings = SiteSettings.load()
        if not settings:
            return {'success': False, 'error': 'No site settings configured'}

        data = {
            'site_name': settings.site_name_i18n,
            'site_description': settings.site_description_i18n,
            'contact_email': settings.contact_email,
            'contact_phone': settings.contact_phone,
            'contact_address': settings.contact_address_i18n,
            'facebook_url': settings.facebook_url,
            'instagram_url': settings.instagram_url,
            'linkedin_url': settings.linkedin_url,
            'twitter_url': settings.twitter_url,
            'youtube_url': settings.youtube_url,
            'google_maps_embed_url': settings.google_maps_embed_url,
            'maintenance_mode': settings.maintenance_mode,
            'domain': settings.domain,
            'default_language': settings.get_default_language(),
            'enabled_languages': settings.get_language_codes(),
            'primary_color': settings.primary_color,
            'primary_color_hover': settings.primary_color_hover,
            'secondary_color': settings.secondary_color,
            'accent_color': settings.accent_color,
            'background_color': settings.background_color,
            'text_color': settings.text_color,
            'heading_color': settings.heading_color,
            'heading_font': settings.heading_font,
            'body_font': settings.body_font,
            'container_width': settings.container_width,
            'border_radius_preset': settings.border_radius_preset,
            'button_style': settings.button_style,
            'button_size': settings.button_size,
            'primary_button_bg': settings.primary_button_bg,
            'primary_button_text': settings.primary_button_text,
            'primary_button_border': settings.primary_button_border,
            'primary_button_hover': settings.primary_button_hover,
            'secondary_button_bg': settings.secondary_button_bg,
            'secondary_button_text': settings.secondary_button_text,
            'secondary_button_border': settings.secondary_button_border,
            'secondary_button_hover': settings.secondary_button_hover,
            'design_guide': settings.design_guide,
            'project_briefing': settings.project_briefing,
        }

        if fields:
            data = {k: v for k, v in data.items() if k in fields}

        return {'success': True, 'settings': data, 'message': 'Site settings retrieved'}

    @staticmethod
    def update(updates):
        """Update site settings with allowlist protection."""
        settings = SiteSettings.load()
        if not settings:
            return {'success': False, 'error': 'No site settings configured'}

        if not updates:
            return {'success': False, 'error': 'No updates provided'}

        blocked = [k for k in updates if k not in SETTINGS_ALLOWLIST]
        if blocked:
            return {'success': False, 'error': f'Cannot update protected fields: {", ".join(blocked)}'}

        updated = []
        for key, value in updates.items():
            setattr(settings, key, value)
            updated.append(key)

        if updated:
            settings.save()

        return {'success': True, 'message': f'Updated settings: {", ".join(updated)}'}

    @staticmethod
    def get_snapshot():
        """Return compact site state for the router/executor prompt.

        Queries pages, menu items, images, stats in one call.
        """
        settings = SiteSettings.load()
        if not settings:
            return {'success': False, 'error': 'No site settings configured'}

        default_lang = settings.get_default_language()

        pages = Page.objects.all().order_by('sort_order', 'created_at')
        page_list = []
        for p in pages:
            title = ''
            if p.title_i18n and isinstance(p.title_i18n, dict):
                title = p.title_i18n.get(default_lang, next(iter(p.title_i18n.values()), ''))
            page_list.append({
                'id': p.id,
                'title': title,
                'is_active': p.is_active,
            })

        menu_items = MenuItem.objects.filter(parent__isnull=True).order_by('sort_order')
        menu_list = []
        for m in menu_items:
            label = ''
            if m.label_i18n and isinstance(m.label_i18n, dict):
                label = m.label_i18n.get(default_lang, next(iter(m.label_i18n.values()), ''))
            menu_list.append({
                'id': m.id,
                'label': label,
                'children_count': m.children.count(),
            })

        return {
            'success': True,
            'snapshot': {
                'site_name': settings.site_name_i18n.get(default_lang, '') if settings.site_name_i18n else '',
                'languages': settings.get_language_codes(),
                'default_language': default_lang,
                'pages': page_list,
                'menu_items': menu_list,
                'stats': {
                    'total_pages': len(page_list),
                    'active_pages': sum(1 for p in page_list if p['is_active']),
                    'total_images': SiteImage.objects.filter(is_active=True).count(),
                    'total_submissions': FormSubmission.objects.count(),
                    'total_menu_items': MenuItem.objects.count(),
                },
            },
        }
