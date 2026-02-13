from django.db import models
from django.core.cache import cache
from django.conf import settings as django_settings
from django.db.models import Max


# Google Fonts choices - Popular fonts for web design
GOOGLE_FONTS_CHOICES = [
    # Sans-serif fonts
    ('Roboto', 'Roboto (Modern Sans-serif)'),
    ('Open Sans', 'Open Sans (Clean Sans-serif)'),
    ('Lato', 'Lato (Professional Sans-serif)'),
    ('Montserrat', 'Montserrat (Geometric Sans-serif)'),
    ('Poppins', 'Poppins (Modern Sans-serif)'),
    ('Inter', 'Inter (UI Sans-serif)'),
    ('Raleway', 'Raleway (Elegant Sans-serif)'),
    ('Nunito', 'Nunito (Rounded Sans-serif)'),
    ('Nunito Sans', 'Nunito Sans (Clean Rounded Sans-serif)'),
    ('Work Sans', 'Work Sans (Contemporary Sans-serif)'),
    ('Rubik', 'Rubik (Friendly Sans-serif)'),
    ('Oswald', 'Oswald (Bold Sans-serif)'),
    ('Source Sans 3', 'Source Sans 3 (Professional Sans-serif)'),
    ('DM Sans', 'DM Sans (Geometric Sans-serif)'),
    ('Manrope', 'Manrope (Modern Geometric Sans-serif)'),
    ('Plus Jakarta Sans', 'Plus Jakarta Sans (Contemporary Sans-serif)'),
    ('Space Grotesk', 'Space Grotesk (Proportional Sans-serif)'),
    ('Outfit', 'Outfit (Minimal Sans-serif)'),
    ('Figtree', 'Figtree (Friendly Sans-serif)'),
    ('Lexend', 'Lexend (Readability Sans-serif)'),
    ('Barlow', 'Barlow (Slightly Condensed Sans-serif)'),
    ('Barlow Condensed', 'Barlow Condensed (Condensed Sans-serif)'),
    ('Mukta', 'Mukta (Clean Sans-serif)'),
    ('Quicksand', 'Quicksand (Rounded Sans-serif)'),
    ('Cabin', 'Cabin (Humanist Sans-serif)'),
    ('Karla', 'Karla (Grotesque Sans-serif)'),
    ('Exo 2', 'Exo 2 (Futuristic Sans-serif)'),
    ('Mulish', 'Mulish (Minimalist Sans-serif)'),
    ('Josefin Sans', 'Josefin Sans (Elegant Sans-serif)'),
    ('Titillium Web', 'Titillium Web (Technical Sans-serif)'),
    ('Archivo', 'Archivo (Strong Sans-serif)'),
    ('Sora', 'Sora (Modern Sans-serif)'),
    ('Red Hat Display', 'Red Hat Display (Bold Sans-serif)'),

    # Serif fonts
    ('Playfair Display', 'Playfair Display (Elegant Serif)'),
    ('Merriweather', 'Merriweather (Readable Serif)'),
    ('Lora', 'Lora (Beautiful Serif)'),
    ('Crimson Text', 'Crimson Text (Classic Serif)'),
    ('EB Garamond', 'EB Garamond (Traditional Serif)'),
    ('Cormorant Garamond', 'Cormorant Garamond (Refined Serif)'),
    ('Libre Baskerville', 'Libre Baskerville (Classic Serif)'),
    ('DM Serif Display', 'DM Serif Display (Bold Serif)'),
    ('DM Serif Text', 'DM Serif Text (Readable Serif)'),
    ('Bitter', 'Bitter (Slab Serif)'),
    ('Roboto Slab', 'Roboto Slab (Modern Slab Serif)'),
    ('Noto Serif', 'Noto Serif (Universal Serif)'),
    ('PT Serif', 'PT Serif (Professional Serif)'),
    ('Vollkorn', 'Vollkorn (Traditional Serif)'),
    ('Spectral', 'Spectral (Reading Serif)'),
    ('Cardo', 'Cardo (Scholarly Serif)'),
    ('Fraunces', 'Fraunces (Old-style Soft Serif)'),
    ('Instrument Serif', 'Instrument Serif (Editorial Serif)'),

    # Display/Decorative fonts
    ('Bebas Neue', 'Bebas Neue (Display/Headers)'),
    ('Pacifico', 'Pacifico (Handwritten)'),
    ('Dancing Script', 'Dancing Script (Script/Cursive)'),
    ('Righteous', 'Righteous (Bold Display)'),
    ('Abril Fatface', 'Abril Fatface (Display Serif)'),
    ('Alfa Slab One', 'Alfa Slab One (Heavy Display)'),
    ('Permanent Marker', 'Permanent Marker (Marker/Handwritten)'),
    ('Satisfy', 'Satisfy (Cursive Script)'),
    ('Lobster', 'Lobster (Bold Script)'),
    ('Caveat', 'Caveat (Casual Handwritten)'),
    ('Great Vibes', 'Great Vibes (Calligraphy)'),
    ('Cormorant', 'Cormorant (Light Display Serif)'),
    ('Staatliches', 'Staatliches (Condensed Display)'),
    ('Big Shoulders Display', 'Big Shoulders Display (Bold Condensed)'),
    ('Fascinate', 'Fascinate (Decorative Display)'),
    ('Monoton', 'Monoton (Retro Outline)'),

    # Monospace fonts
    ('Roboto Mono', 'Roboto Mono (Monospace)'),
    ('Source Code Pro', 'Source Code Pro (Code Font)'),
    ('JetBrains Mono', 'JetBrains Mono (Modern Monospace)'),
    ('Fira Code', 'Fira Code (Ligature Monospace)'),
    ('IBM Plex Mono', 'IBM Plex Mono (Corporate Monospace)'),
    ('Space Mono', 'Space Mono (Retro Monospace)'),

    # System fonts fallback
    ('system-ui', 'System Default (No Google Font)'),
]


class SiteSettings(models.Model):
    """Singleton model for storing website settings"""

    # OLD FIELDS (will be removed after migration)
    site_name = models.CharField("Site Name (OLD)", max_length=100, default="DjangoPress", null=True, blank=True)
    site_description = models.CharField("Site Description (OLD)", max_length=255, blank=True, null=True)
    project_briefing = models.TextField("Project Briefing", blank=True, default='', help_text='Detailed description of the project/business for AI context.')
    contact_address = models.TextField("Address (OLD)", blank=True, default='', null=True)

    # NEW: JSON Translation Fields
    site_name_i18n = models.JSONField(
        'Site Name (All Languages)',
        default=dict,
        blank=True,
        help_text='{"pt": "Nome do Site", "en": "Site Name"}'
    )
    site_description_i18n = models.JSONField(
        'Site Description (All Languages)',
        default=dict,
        blank=True,
        help_text='{"pt": "Descrição PT", "en": "Description EN"}'
    )
    contact_address_i18n = models.JSONField(
        'Contact Address (All Languages)',
        default=dict,
        blank=True,
        help_text='{"pt": "Morada PT", "en": "Address EN"}'
    )

    # Site Domain (used for GCS folder organization)
    domain = models.CharField(
        "Site Domain",
        max_length=255,
        blank=True,
        default='',
        help_text="e.g. get-algarve-com — used as the storage folder name in Google Cloud Storage"
    )

    logo = models.ImageField("Logo (Light Backgrounds)", upload_to='site_images/', blank=True, null=True, help_text="Main logo for light backgrounds")
    logo_dark_bg = models.ImageField("Logo (Dark Backgrounds)", upload_to='site_images/', blank=True, null=True, help_text="Alternative logo for dark backgrounds (typically white/light version)")
    favicon = models.ImageField("Favicon", upload_to='site_images/', blank=True, null=True, help_text="Site favicon (recommended: 32x32 or 48x48 PNG)")

    # Contact Information
    contact_email = models.EmailField("Contact Email", default="admin@example.com")
    contact_phone = models.CharField("Contact Phone", max_length=20, default="")

    # Google Maps
    google_maps_embed_url = models.TextField("Google Maps Embed URL", blank=True, help_text="Full Google Maps embed iframe URL")

    # Social Media Links
    facebook_url = models.URLField("Facebook URL", blank=True, default="")
    instagram_url = models.URLField("Instagram URL", blank=True, default="")
    linkedin_url = models.URLField("LinkedIn URL", blank=True, default="")
    youtube_url = models.URLField("YouTube URL", blank=True, default="")
    twitter_url = models.URLField("Twitter URL", blank=True, default="")
    whatsapp_number = models.CharField("WhatsApp Number", max_length=20, blank=True, default="", help_text="International format, e.g. +351912345678")
    tiktok_url = models.URLField("TikTok URL", blank=True, default="")
    pinterest_url = models.URLField("Pinterest URL", blank=True, default="")

    # SEO Fields
    meta_keywords = models.CharField("Meta Keywords", max_length=255, blank=True)
    google_analytics_id = models.CharField("Google Analytics ID", max_length=50, blank=True)

    # Custom Code Injection
    custom_head_code = models.TextField("Custom Head Code", blank=True, default="", help_text="Code injected before </head> (e.g. Facebook Pixel, Hotjar, custom CSS)")
    custom_body_code = models.TextField("Custom Body Code", blank=True, default="", help_text="Code injected before </body> (e.g. chat widgets, cookie consent)")

    # Open Graph Defaults
    og_image = models.ImageField("Default OG Image", upload_to='site_images/', blank=True, null=True, help_text="Fallback image for social media sharing when a page has no OG image")
    default_og_description_i18n = models.JSONField(
        'Default OG Description (All Languages)',
        default=dict,
        blank=True,
        help_text='Fallback OG description: {"pt": "Descrição PT", "en": "Description EN"}'
    )

    # Design System Settings
    # Colors
    primary_color = models.CharField("Primary Color", max_length=7, default="#1e3a8a", help_text="Hex color code (e.g., #1e3a8a for navy blue)")
    primary_color_hover = models.CharField("Primary Color Hover", max_length=7, default="#1e40af", help_text="Hover state for primary color")
    secondary_color = models.CharField("Secondary Color", max_length=7, default="#64748b", help_text="Secondary/accent color")
    accent_color = models.CharField("Accent Color", max_length=7, default="#f59e0b", help_text="Accent/highlight color")
    background_color = models.CharField("Background Color", max_length=7, default="#ffffff", help_text="Main background color")
    text_color = models.CharField("Text Color", max_length=7, default="#1f2937", help_text="Main text color")
    heading_color = models.CharField("Heading Color", max_length=7, default="#111827", help_text="Headings color")

    # Fonts - General
    heading_font = models.CharField(
        "Heading Font",
        max_length=100,
        default="Montserrat",
        choices=GOOGLE_FONTS_CHOICES,
        help_text="Font family for headings"
    )
    body_font = models.CharField(
        "Body Font",
        max_length=100,
        default="Open Sans",
        choices=GOOGLE_FONTS_CHOICES,
        help_text="Font family for body text"
    )

    # Typography - Individual Heading Fonts
    h1_font = models.CharField(
        "H1 Font",
        max_length=100,
        default="Montserrat",
        choices=GOOGLE_FONTS_CHOICES,
        help_text="Font family for H1 headings"
    )
    h2_font = models.CharField(
        "H2 Font",
        max_length=100,
        default="Montserrat",
        choices=GOOGLE_FONTS_CHOICES,
        help_text="Font family for H2 headings"
    )
    h3_font = models.CharField(
        "H3 Font",
        max_length=100,
        default="Montserrat",
        choices=GOOGLE_FONTS_CHOICES,
        help_text="Font family for H3 headings"
    )
    h4_font = models.CharField(
        "H4 Font",
        max_length=100,
        default="Montserrat",
        choices=GOOGLE_FONTS_CHOICES,
        help_text="Font family for H4 headings"
    )
    h5_font = models.CharField(
        "H5 Font",
        max_length=100,
        default="Montserrat",
        choices=GOOGLE_FONTS_CHOICES,
        help_text="Font family for H5 headings"
    )
    h6_font = models.CharField(
        "H6 Font",
        max_length=100,
        default="Montserrat",
        choices=GOOGLE_FONTS_CHOICES,
        help_text="Font family for H6 headings"
    )

    # Typography - Heading Sizes (Tailwind classes)
    h1_size = models.CharField("H1 Size", max_length=20, default="text-5xl", help_text="Tailwind text size class (e.g., text-5xl)")
    h2_size = models.CharField("H2 Size", max_length=20, default="text-4xl", help_text="Tailwind text size class (e.g., text-4xl)")
    h3_size = models.CharField("H3 Size", max_length=20, default="text-3xl", help_text="Tailwind text size class (e.g., text-3xl)")
    h4_size = models.CharField("H4 Size", max_length=20, default="text-2xl", help_text="Tailwind text size class (e.g., text-2xl)")
    h5_size = models.CharField("H5 Size", max_length=20, default="text-xl", help_text="Tailwind text size class (e.g., text-xl)")
    h6_size = models.CharField("H6 Size", max_length=20, default="text-lg", help_text="Tailwind text size class (e.g., text-lg)")

    # Layout Settings
    container_width = models.CharField("Container Width", max_length=20, default="7xl", choices=[
        ('full', 'Full Width'),
        ('xs', 'Extra Small (20rem)'),
        ('sm', 'Small (24rem)'),
        ('md', 'Medium (28rem)'),
        ('lg', 'Large (32rem)'),
        ('xl', 'Extra Large (36rem)'),
        ('2xl', '2XL (42rem)'),
        ('3xl', '3XL (48rem)'),
        ('4xl', '4XL (56rem)'),
        ('5xl', '5XL (64rem)'),
        ('6xl', '6XL (72rem)'),
        ('7xl', '7XL (80rem)'),
    ], help_text="Maximum width for main content container")

    border_radius_preset = models.CharField("Border Radius", max_length=20, default="lg", choices=[
        ('none', 'None (0px)'),
        ('sm', 'Small (0.125rem)'),
        ('md', 'Medium (0.375rem)'),
        ('lg', 'Large (0.5rem)'),
        ('xl', 'Extra Large (0.75rem)'),
        ('2xl', '2XL (1rem)'),
        ('3xl', '3XL (1.5rem)'),
        ('full', 'Full (9999px)'),
    ], help_text="Default border radius for cards, images, etc.")

    spacing_scale = models.CharField("Spacing Scale", max_length=20, default="normal", choices=[
        ('tight', 'Tight (smaller gaps)'),
        ('normal', 'Normal'),
        ('relaxed', 'Relaxed (larger gaps)'),
        ('loose', 'Loose (largest gaps)'),
    ], help_text="Spacing between sections and elements")

    shadow_preset = models.CharField("Shadow Preset", max_length=20, default="md", choices=[
        ('none', 'None'),
        ('sm', 'Small'),
        ('md', 'Medium'),
        ('lg', 'Large'),
        ('xl', 'Extra Large'),
        ('2xl', '2XL'),
    ], help_text="Default shadow style for cards and elevated elements")

    # Button Settings - Style & Size
    button_style = models.CharField("Button Style", max_length=20, default="rounded", choices=[
        ('rounded', 'Rounded'),
        ('square', 'Square'),
        ('pill', 'Pill (Full rounded)'),
    ])
    button_size = models.CharField("Button Size", max_length=20, default="medium", choices=[
        ('small', 'Small'),
        ('medium', 'Medium'),
        ('large', 'Large'),
    ])

    # Button Settings - Primary Button Colors
    primary_button_bg = models.CharField("Primary Button Background", max_length=7, default="#1e3a8a", help_text="Background color for primary buttons")
    primary_button_text = models.CharField("Primary Button Text", max_length=7, default="#ffffff", help_text="Text color for primary buttons")
    primary_button_border = models.CharField("Primary Button Border", max_length=7, default="#1e3a8a", help_text="Border color for primary buttons")
    primary_button_hover = models.CharField("Primary Button Hover", max_length=7, default="#1e40af", help_text="Hover background color for primary buttons")

    # Button Settings - Secondary Button Colors
    secondary_button_bg = models.CharField("Secondary Button Background", max_length=7, default="#64748b", help_text="Background color for secondary buttons")
    secondary_button_text = models.CharField("Secondary Button Text", max_length=7, default="#ffffff", help_text="Text color for secondary buttons")
    secondary_button_border = models.CharField("Secondary Button Border", max_length=7, default="#64748b", help_text="Border color for secondary buttons")
    secondary_button_hover = models.CharField("Secondary Button Hover", max_length=7, default="#475569", help_text="Hover background color for secondary buttons")

    # Button Settings - Border Width
    button_border_width = models.CharField("Button Border Width", max_length=10, default="0", choices=[
        ('0', 'None'),
        ('1', '1px'),
        ('2', '2px'),
        ('4', '4px'),
    ], help_text="Border width for buttons")

    # Design Guide (freeform markdown for AI context)
    design_guide = models.TextField(
        'Design Guide',
        blank=True,
        default='',
        help_text='Markdown document describing UI patterns, component styles, and design rules for AI generation.'
    )

    # Language Settings
    default_language = models.CharField(
        "Default Language",
        max_length=10,
        default='pt',
        help_text="Default language code (e.g., 'pt', 'en', 'es')"
    )
    enabled_languages = models.JSONField(
        'Enabled Languages',
        default=list,
        blank=True,
        help_text='List of enabled languages: [{"code": "pt", "name": "Portuguese"}, {"code": "en", "name": "English"}]'
    )

    # Misc
    maintenance_mode = models.BooleanField("Maintenance Mode", default=False)

    class Meta:
        verbose_name = "Site Settings"
        verbose_name_plural = "Site Settings"

    def __str__(self):
        # Try new JSON field first, fall back to old field
        if self.site_name_i18n and isinstance(self.site_name_i18n, dict):
            return self.site_name_i18n.get('pt', self.site_name_i18n.get('en', 'Site'))
        return self.site_name or 'Site Settings'

    # Helper methods for accessing translations
    def get_site_name(self, lang='pt'):
        """Get site name in specified language"""
        if self.site_name_i18n and isinstance(self.site_name_i18n, dict) and self.site_name_i18n:
            name = self.site_name_i18n.get(lang, self.site_name_i18n.get('pt', ''))
            if name:
                return name
        # Fallback to old field if new field is empty
        return self.site_name or ''

    def get_site_description(self, lang='pt'):
        """Get site description in specified language"""
        if self.site_description_i18n and isinstance(self.site_description_i18n, dict) and self.site_description_i18n:
            desc = self.site_description_i18n.get(lang, self.site_description_i18n.get('pt', ''))
            if desc:
                return desc
        # Fallback to old field if new field is empty
        return self.site_description or ''

    def get_project_briefing(self):
        """Get project briefing for AI context"""
        return self.project_briefing or ''

    def get_contact_address(self, lang='pt'):
        """Get contact address in specified language"""
        if self.contact_address_i18n and isinstance(self.contact_address_i18n, dict):
            return self.contact_address_i18n.get(lang, self.contact_address_i18n.get('pt', ''))
        return self.contact_address or ''

    def get_enabled_languages(self):
        """
        Get list of enabled languages.
        Returns list of tuples: [(code, name), ...]
        Falls back to Django settings if not configured.
        """
        if self.enabled_languages and isinstance(self.enabled_languages, list) and len(self.enabled_languages) > 0:
            return [(lang.get('code', 'pt'), lang.get('name', 'Portuguese')) for lang in self.enabled_languages]
        # Fallback to Django settings
        return list(django_settings.LANGUAGES)

    def get_default_language(self):
        """Get default language code"""
        if self.default_language:
            return self.default_language
        # Fallback to Django settings
        return django_settings.LANGUAGE_CODE

    def get_language_codes(self):
        """Get list of enabled language codes only"""
        return [code for code, name in self.get_enabled_languages()]

    def get_google_fonts_url(self):
        """
        Generate Google Fonts URL for all selected fonts.
        Returns URL string or empty string if only system fonts are used.
        """
        # Collect all unique fonts being used
        fonts_used = set()
        font_fields = [
            self.heading_font, self.body_font,
            self.h1_font, self.h2_font, self.h3_font,
            self.h4_font, self.h5_font, self.h6_font
        ]

        # System font patterns to skip
        system_fonts = ['system-ui', 'system', '-apple-system', 'sans-serif', 'serif', 'monospace']

        for font in font_fields:
            if not font:
                continue

            # Extract the first font from comma-separated list (for backward compatibility)
            # e.g., "Poppins, sans-serif" -> "Poppins"
            first_font = font.split(',')[0].strip()

            # Skip system fonts
            if first_font.lower() in [s.lower() for s in system_fonts]:
                continue

            # Skip if it looks like a generic font family
            if first_font.lower() in ['sans-serif', 'serif', 'monospace', 'cursive', 'fantasy']:
                continue

            fonts_used.add(first_font)

        if not fonts_used:
            return ''

        # Build Google Fonts URL
        # Format: https://fonts.googleapis.com/css2?family=Font+Name:wght@400;700&family=Another+Font:wght@400;700&display=swap
        font_params = []
        for font in sorted(fonts_used):
            # Replace spaces with + for URL
            font_name = font.replace(' ', '+')
            # Include common weights: 300 (light), 400 (normal), 500 (medium), 600 (semibold), 700 (bold), 800 (extra bold)
            font_params.append(f'family={font_name}:wght@300;400;500;600;700;800')

        if font_params:
            return f'https://fonts.googleapis.com/css2?{"&".join(font_params)}&display=swap'

        return ''

    @classmethod
    def load(cls):
        """Load site settings from cache or database"""
        obj = cache.get('site_settings')
        if obj is None:
            obj, created = cls.objects.get_or_create(pk=1)
            cache.set('site_settings', obj, 60 * 60)  # Cache for 1 hour
        return obj

    def save(self, *args, **kwargs):
        """Override save to clear cache and ensure site name is consistent across all languages"""

        # Site name should be the same in all languages (it's a brand name, not translated content)
        if self.site_name_i18n and isinstance(self.site_name_i18n, dict):
            # Get the first non-empty site name value
            site_name_value = None
            for lang_code, name in self.site_name_i18n.items():
                if name and name.strip():
                    site_name_value = name.strip()
                    break

            # If we found a site name, replicate it to all enabled languages
            if site_name_value:
                languages = self.get_language_codes()
                self.site_name_i18n = {lang: site_name_value for lang in languages}

        # Fallback: if site_name_i18n is empty but old site_name has a value, populate i18n field
        elif self.site_name and not self.site_name_i18n:
            languages = self.get_language_codes()
            self.site_name_i18n = {lang: self.site_name for lang in languages}

        super().save(*args, **kwargs)

        # Clear caches
        cache.delete('site_settings')
        cache.delete('default_language_code')  # Clear language cache for middleware


class DynamicForm(models.Model):
    """A configurable form definition (contact, quote request, booking, etc.)"""

    name = models.CharField("Name", max_length=200)
    slug = models.SlugField("Slug", max_length=100, unique=True)
    notification_email = models.EmailField(
        "Notification Email", blank=True,
        help_text="Where to send submissions. Falls back to SiteSettings.contact_email."
    )
    fields_schema = models.JSONField(
        "Fields Schema", default=list, blank=True,
        help_text='[{"name": "email", "type": "email", "label": "Email", "required": true}]'
    )
    success_message_i18n = models.JSONField(
        "Success Message", default=dict, blank=True,
        help_text='{"pt": "Obrigado!", "en": "Thank you!"}'
    )
    send_confirmation_email = models.BooleanField("Send Confirmation Email", default=False)
    confirmation_subject_i18n = models.JSONField(
        "Confirmation Subject", default=dict, blank=True,
        help_text='Auto-reply subject per language'
    )
    confirmation_body_i18n = models.JSONField(
        "Confirmation Body", default=dict, blank=True,
        help_text='Auto-reply body per language'
    )
    is_active = models.BooleanField("Active", default=True)
    created_at = models.DateTimeField("Created At", auto_now_add=True)
    updated_at = models.DateTimeField("Updated At", auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Dynamic Form"
        verbose_name_plural = "Dynamic Forms"

    def __str__(self):
        return self.name

    def get_notification_email(self):
        if self.notification_email:
            return self.notification_email
        settings = SiteSettings.load()
        return settings.contact_email if settings else ''

    def get_success_message(self, lang='en'):
        if self.success_message_i18n and isinstance(self.success_message_i18n, dict):
            return self.success_message_i18n.get(lang, self.success_message_i18n.get('en', 'Thank you!'))
        return 'Thank you!'

    def get_field_label(self, name):
        if self.fields_schema and isinstance(self.fields_schema, list):
            for field in self.fields_schema:
                if field.get('name') == name:
                    return field.get('label', name)
        return name.replace('_', ' ').title()

    def get_reply_to_field(self):
        if self.fields_schema and isinstance(self.fields_schema, list):
            for field in self.fields_schema:
                if field.get('type') == 'email':
                    return field.get('name')
        return 'email'

    def validate_submission(self, data):
        errors = {}
        if not self.fields_schema or not isinstance(self.fields_schema, list):
            return errors
        for field in self.fields_schema:
            name = field.get('name', '')
            required = field.get('required', False)
            field_type = field.get('type', 'text')
            value = data.get(name, '')
            if required and not value:
                errors[name] = f'{field.get("label", name)} is required.'
            if value and field_type == 'email':
                import re
                if not re.match(r'^[^@]+@[^@]+\.[^@]+$', value):
                    errors[name] = f'{field.get("label", name)} must be a valid email.'
        return errors


class FormSubmission(models.Model):
    """A submission to a DynamicForm"""

    form = models.ForeignKey(DynamicForm, on_delete=models.CASCADE, related_name='submissions')
    data = models.JSONField("Submitted Data", default=dict)
    source_page = models.ForeignKey('Page', on_delete=models.SET_NULL, null=True, blank=True)
    language = models.CharField("Language", max_length=10, blank=True, default='')
    ip_address = models.GenericIPAddressField("IP Address", null=True, blank=True)
    user_agent = models.TextField("User Agent", blank=True, default='')
    is_read = models.BooleanField("Read", default=False)
    notification_sent = models.BooleanField("Notification Sent", default=False)
    created_at = models.DateTimeField("Created At", auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Form Submission"
        verbose_name_plural = "Form Submissions"

    def __str__(self):
        return f"{self.form.name} - {self.created_at:%Y-%m-%d %H:%M}"

    def get_display_fields(self):
        result = []
        for key, value in self.data.items():
            label = self.form.get_field_label(key)
            result.append({'name': key, 'label': label, 'value': value})
        return result


class SiteImage(models.Model):
    """Model for managing all images across the site"""

    # OLD FIELDS (will be removed after migration)
    title = models.CharField('Title (OLD)', max_length=100, null=True, blank=True)
    alt_text = models.CharField('Alt text (OLD)', max_length=200, blank=True, null=True)

    # NEW: JSON Translation Fields
    title_i18n = models.JSONField(
        'Title (All Languages)',
        default=dict,
        blank=True,
        help_text='{"pt": "Título PT", "en": "Title EN"}'
    )
    alt_text_i18n = models.JSONField(
        'Alt Text (All Languages)',
        default=dict,
        blank=True,
        help_text='{"pt": "Texto alternativo PT", "en": "Alt text EN"}'
    )

    key = models.SlugField('Key', unique=True, blank=True, help_text='Optional unique identifier to reference this image in templates')
    image = models.ImageField('Image', upload_to='site_images/')
    tags = models.CharField('Tags', max_length=200, blank=True, default='', help_text='Comma-separated tags for filtering (e.g., construction, villa, pool)')
    description = models.TextField('AI Description', blank=True, default='', help_text='AI-generated semantic description for intelligent image matching')
    is_active = models.BooleanField('Active', default=True)
    uploaded_at = models.DateTimeField('Uploaded At', auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField('Updated At', auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = 'Site Image'
        verbose_name_plural = 'Site Images'
        ordering = ['-uploaded_at']

    def __str__(self):
        # Try new JSON field first, fall back to old field
        if self.title_i18n and isinstance(self.title_i18n, dict):
            return self.title_i18n.get('pt', self.title_i18n.get('en', self.key or 'Image'))
        return self.title or self.key or 'Image'

    def get_title(self, lang='pt'):
        """Get title in specified language"""
        if self.title_i18n and isinstance(self.title_i18n, dict):
            return self.title_i18n.get(lang, self.title_i18n.get('pt', ''))
        return self.title or ''

    def get_alt_text(self, lang='pt'):
        """Get alt text in specified language"""
        if self.alt_text_i18n and isinstance(self.alt_text_i18n, dict):
            return self.alt_text_i18n.get(lang, self.alt_text_i18n.get('pt', ''))
        return self.alt_text or self.get_title(lang)  # Fall back to title

    def get_tags_list(self):
        """Return tags as a list"""
        if self.tags:
            return [tag.strip() for tag in self.tags.split(',')]
        return []


class Page(models.Model):
    """Represents a website page"""

    SLUG_CACHE_KEY = 'page_slug_index'

    # OLD FIELD (for backward compatibility, will be removed later)
    slug = models.SlugField('Slug (OLD)', max_length=50, null=True, blank=True)

    # OLD FIELD (will be removed after migration)
    title = models.CharField('Title (OLD)', max_length=200, null=True, blank=True)

    # NEW: JSON Translation Fields
    title_i18n = models.JSONField(
        'Title (All Languages)',
        default=dict,
        blank=True,
        help_text='{"pt": "Título PT", "en": "Title EN"}'
    )
    slug_i18n = models.JSONField(
        'Slug (All Languages)',
        default=dict,
        blank=True,
        help_text='{"pt": "sobre", "en": "about"} - URL-friendly slugs for each language'
    )

    html_content = models.TextField(
        'HTML Content',
        blank=True,
        default='',
        help_text='Full page HTML with Tailwind CSS. Use {{trans.field}} for translatable content. Use data-section="name" on <section> tags for LLM reference.'
    )
    content = models.JSONField(
        'Translations',
        default=dict,
        blank=True,
        help_text='{"translations": {"pt": {"field": "valor"}, "en": {"field": "value"}}}'
    )

    # SEO Fields
    meta_title_i18n = models.JSONField('Meta Title', default=dict, blank=True,
        help_text='{"pt": "Título SEO", "en": "SEO Title"} - Override the page title in search results')
    meta_description_i18n = models.JSONField('Meta Description', default=dict, blank=True,
        help_text='{"pt": "Descrição SEO", "en": "SEO Description"} - Description shown in search results')
    og_image = models.ImageField('OG Image', upload_to='site_images/', blank=True, null=True,
        help_text='Image shown when page is shared on social media')

    # Ordering
    sort_order = models.IntegerField('Sort Order', default=0)

    is_active = models.BooleanField('Active', default=True)
    created_at = models.DateTimeField('Created At', auto_now_add=True)
    updated_at = models.DateTimeField('Updated At', auto_now=True)

    class Meta:
        verbose_name = 'Page'
        verbose_name_plural = 'Pages'
        ordering = ['sort_order', 'created_at']

    def __str__(self):
        # Try new JSON field first, fall back to old field
        if self.title_i18n and isinstance(self.title_i18n, dict):
            return self.title_i18n.get('pt', self.title_i18n.get('en', self.slug))
        return self.title or self.slug

    def get_title(self, lang='pt'):
        """Get title in specified language"""
        if self.title_i18n and isinstance(self.title_i18n, dict):
            return self.title_i18n.get(lang, self.title_i18n.get('pt', ''))
        return self.title or ''

    @property
    def default_title(self):
        """Get title in the default language from site settings"""
        try:
            site_settings = SiteSettings.objects.first()
            default_lang = site_settings.get_default_language() if site_settings else 'pt'

            # Normalize language code (eng -> en)
            if default_lang == 'eng':
                default_lang = 'en'

            title = self.get_title(default_lang)

            # If not found, try to get first available title
            if not title and self.title_i18n:
                # Get first available title from any language
                for lang_code, lang_title in self.title_i18n.items():
                    if lang_title:
                        return lang_title

            return title
        except:
            return self.get_title('pt')

    @property
    def default_slug(self):
        """Get slug in the default language from site settings"""
        try:
            site_settings = SiteSettings.objects.first()
            default_lang = site_settings.get_default_language() if site_settings else 'pt'

            # Normalize language code (eng -> en)
            if default_lang == 'eng':
                default_lang = 'en'

            slug = self.get_slug(default_lang)

            # If not found, try to get first available slug
            if not slug and self.slug_i18n:
                # Get first available slug from any language
                for lang_code, lang_slug in self.slug_i18n.items():
                    if lang_slug:
                        return lang_slug

            return slug
        except:
            return self.get_slug('pt')

    @property
    def slug_i18n_json(self):
        """Return slug_i18n as a JSON string for use in templates"""
        import json
        return json.dumps(self.slug_i18n or {})

    def get_slug(self, lang='pt'):
        """
        Get slug in specified language.
        Falls back to default slug if language-specific slug not found.
        """
        if self.slug_i18n and isinstance(self.slug_i18n, dict):
            return self.slug_i18n.get(lang, self.slug_i18n.get('pt', self.slug))
        return self.slug or ''

    @classmethod
    def get_by_slug(cls, slug, lang, include_inactive=False):
        """
        Look up a page by its language-specific slug using a cached index.
        Falls back to rebuilding the index on cache miss.

        Args:
            slug: The URL slug to look up
            lang: Language code (e.g. 'en', 'pt')
            include_inactive: If True, also search inactive pages

        Returns:
            Page instance or None
        """
        index = cache.get(cls.SLUG_CACHE_KEY)
        if index is None:
            index = cls._build_slug_index()

        key = f'{lang}:{slug}'
        page_id = index.get(key)

        if page_id is not None:
            try:
                page = cls.objects.get(pk=page_id)
                if page.is_active or include_inactive:
                    return page
            except cls.DoesNotExist:
                pass

        # If include_inactive, also check inactive pages not in the index
        if include_inactive:
            for page in cls.objects.filter(is_active=False):
                if page.get_slug(lang) == slug:
                    return page

        return None

    @classmethod
    def _build_slug_index(cls):
        """
        Build a {lang:slug -> page_id} index from all pages and cache it.

        Returns:
            Dict mapping 'lang:slug' strings to page IDs
        """
        index = {}
        for page in cls.objects.all():
            slug_i18n = page.slug_i18n or {}
            for lang, slug in slug_i18n.items():
                if slug:
                    index[f'{lang}:{slug}'] = page.pk
            # Also index the legacy slug field
            if page.slug:
                index[f'_legacy:{page.slug}'] = page.pk
        cache.set(cls.SLUG_CACHE_KEY, index, 3600)  # Cache for 1 hour
        return index

    @classmethod
    def invalidate_slug_index(cls):
        """Clear the slug lookup index from cache."""
        cache.delete(cls.SLUG_CACHE_KEY)

    def get_meta_title(self, lang='pt'):
        """Get meta title in specified language, falls back to page title"""
        if self.meta_title_i18n and isinstance(self.meta_title_i18n, dict):
            val = self.meta_title_i18n.get(lang, self.meta_title_i18n.get('pt', ''))
            if val:
                return val
        return self.get_title(lang)

    def get_meta_description(self, lang='pt'):
        """Get meta description in specified language"""
        if self.meta_description_i18n and isinstance(self.meta_description_i18n, dict):
            return self.meta_description_i18n.get(lang, self.meta_description_i18n.get('pt', ''))
        return ''

    def get_absolute_url(self, lang=None):
        """
        Get the absolute URL for this page in specified language.
        If lang is None, uses default language WITHOUT prefix.
        Non-default languages include the language prefix.

        The middleware (DynamicLanguageMiddleware) handles unprefixed URLs
        by internally routing them to the correct language in i18n_patterns.
        """
        # Get default language from SiteSettings
        try:
            site_settings = SiteSettings.objects.first()
            default_lang = site_settings.get_default_language() if site_settings else 'pt'
        except:
            default_lang = 'pt'

        # If no language specified, use default language
        if lang is None:
            lang = default_lang

        # Get slug for the specified language
        slug = self.get_slug(lang)

        # Default language: no prefix
        if lang == default_lang:
            if slug == 'home':
                return '/'
            return f'/{slug}/'

        # Non-default language: include prefix
        if slug == 'home':
            return f'/{lang}/'
        return f'/{lang}/{slug}/'

    def create_version(self, user=None, change_summary='', max_versions=10):
        """
        Create a version snapshot of current page state.
        Automatically deletes old versions to keep only the most recent ones.

        Args:
            user: User making the change (optional)
            change_summary: Description of the change (optional)
            max_versions: Maximum number of versions to keep (default: 10)

        Returns:
            PageVersion: The created version object
        """
        version_number = PageVersion.next_version_number_for(self)

        version = PageVersion.objects.create(
            page=self,
            version_number=version_number,
            title_i18n=self.title_i18n if self.title_i18n else {},
            slug_i18n=self.slug_i18n if self.slug_i18n else {},
            html_content=self.html_content,
            content=self.content if self.content else {},
            is_active=self.is_active,
            created_by=user,
            change_summary=change_summary
        )

        # Clean up old versions
        self._cleanup_old_versions(max_versions)

        return version

    def _cleanup_old_versions(self, max_versions=10):
        """Delete old page versions, keeping only the most recent max_versions."""
        all_versions = self.versions.order_by('-version_number')
        total_versions = all_versions.count()

        if total_versions > max_versions:
            versions_to_keep = all_versions[:max_versions].values_list('id', flat=True)
            deleted_count = self.versions.exclude(id__in=versions_to_keep).delete()[0]

            if deleted_count > 0:
                print(f"🗑️  Cleaned up {deleted_count} old version(s) for page {self.id}")

        return total_versions - max_versions if total_versions > max_versions else 0

    def get_latest_version(self):
        """Get the most recent version of this page."""
        return self.versions.order_by('-version_number').first()

    def get_version_count(self):
        """Get total number of versions for this page."""
        return self.versions.count()

    def restore_to_version(self, version_number, user=None):
        """
        Restore page to a specific version.
        Creates a version of current state before restoring.
        """
        version = self.versions.get(version_number=version_number)
        self.create_version(user, f'Before restore to v{version_number}')
        return version.restore()


class GlobalSection(models.Model):
    """
    Global sections that appear site-wide (header, footer, announcement bars).
    Separate from Page sections for better performance and caching.
    """

    SECTION_TYPES = [
        ('header', 'Header'),
        ('footer', 'Footer'),
        ('announcement', 'Announcement Bar'),
        ('sidebar', 'Sidebar'),
        ('custom', 'Custom Global Section'),
    ]

    key = models.SlugField(
        'Key',
        max_length=100,
        unique=True,
        help_text='Unique identifier (e.g., "main-header", "footer")'
    )
    section_type = models.CharField(
        'Section Type',
        max_length=50,
        choices=SECTION_TYPES,
        default='custom'
    )
    name = models.CharField(
        'Name',
        max_length=200,
        help_text='Display name for admin (e.g., "Main Header", "Footer")'
    )

    html_template = models.TextField(
        'HTML Template',
        help_text='HTML template with Django template syntax. Use {{trans.field}} for translatable content.'
    )

    # JSON content for translations
    content = models.JSONField(
        'Content',
        default=dict,
        blank=True,
        help_text='Translatable content: {"translations": {"pt": {...}, "en": {...}}}'
    )

    is_active = models.BooleanField('Active', default=True)

    # Caching
    cache_duration = models.IntegerField(
        'Cache Duration (seconds)',
        default=3600,
        help_text='How long to cache this section (default: 3600 = 1 hour)'
    )

    # Fallback
    fallback_template = models.CharField(
        'Fallback Template Path',
        max_length=255,
        blank=True,
        help_text='Optional: Path to template file as fallback (e.g., "partials/header.html")'
    )

    order = models.IntegerField('Display Order', default=0)
    created_at = models.DateTimeField('Created At', auto_now_add=True)
    updated_at = models.DateTimeField('Updated At', auto_now=True)

    class Meta:
        verbose_name = 'Global Section'
        verbose_name_plural = 'Global Sections'
        ordering = ['order', 'key']

    def __str__(self):
        return f"{self.name} ({self.key})"



class PageVersion(models.Model):
    """Immutable snapshot of a Page at a point in time."""
    page = models.ForeignKey('Page', on_delete=models.CASCADE, related_name='versions')
    version_number = models.IntegerField()

    # OLD FIELDS (kept for backward compatibility, nullable)
    title = models.CharField('Title (OLD)', max_length=200, null=True, blank=True)
    slug = models.SlugField('Slug (OLD)', max_length=50, null=True, blank=True)

    # NEW: JSON Translation Fields
    title_i18n = models.JSONField(
        'Title (All Languages)',
        default=dict,
        blank=True,
        help_text='{"pt": "Título PT", "en": "Title EN"}'
    )
    slug_i18n = models.JSONField(
        'Slug (All Languages)',
        default=dict,
        blank=True,
        help_text='{"pt": "sobre", "en": "about"}'
    )

    html_content = models.TextField('HTML Content', blank=True, default='')
    content = models.JSONField('Translations', default=dict, blank=True)

    is_active = models.BooleanField('Active', default=True)
    created_at = models.DateTimeField('Created At', auto_now_add=True)
    created_by = models.ForeignKey(django_settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    change_summary = models.CharField('Change Summary', max_length=255, blank=True, default='')

    class Meta:
        verbose_name = 'Page Version'
        verbose_name_plural = 'Page Versions'
        ordering = ['-created_at']
        unique_together = ('page', 'version_number')

    def __str__(self):
        page_slug = self.page.default_slug if self.page else 'unknown'
        return f"{page_slug} v{self.version_number} @ {self.created_at:%Y-%m-%d %H:%M}"

    @classmethod
    def next_version_number_for(cls, page):
        current = cls.objects.filter(page=page).aggregate(Max('version_number'))['version_number__max'] or 0
        return current + 1

    def restore(self):
        """Restore the associated Page to this version's data."""
        p = self.page
        p.title_i18n = self.title_i18n if self.title_i18n else {}
        p.slug_i18n = self.slug_i18n if self.slug_i18n else {}
        p.html_content = self.html_content
        p.content = self.content if self.content else {}
        p.is_active = self.is_active
        setattr(p, '_change_summary', f'Restore to version {self.version_number}')
        p.save()
        return p


class MenuItem(models.Model):
    """Navigation menu item, supports hierarchy via parent FK."""

    label_i18n = models.JSONField('Label', default=dict, blank=True,
        help_text='{"pt": "Início", "en": "Home"}')
    page = models.ForeignKey('Page', on_delete=models.SET_NULL, null=True, blank=True,
        help_text='Link to an internal page')
    url = models.CharField('Custom URL', max_length=500, blank=True, default='',
        help_text='External or custom URL (used when no page is selected)')
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True,
        related_name='children')
    sort_order = models.IntegerField('Sort Order', default=0)
    is_active = models.BooleanField('Active', default=True)
    open_in_new_tab = models.BooleanField('Open in New Tab', default=False)
    css_class = models.CharField('CSS Class', max_length=100, blank=True, default='')

    class Meta:
        ordering = ['sort_order', 'id']
        verbose_name = 'Menu Item'
        verbose_name_plural = 'Menu Items'

    def __str__(self):
        if self.label_i18n and isinstance(self.label_i18n, dict):
            return self.label_i18n.get('pt', self.label_i18n.get('en', f'MenuItem {self.id}'))
        return f'MenuItem {self.id}'

    def get_label(self, lang='pt'):
        """Get label in specified language"""
        if self.label_i18n and isinstance(self.label_i18n, dict):
            return self.label_i18n.get(lang, self.label_i18n.get('pt', ''))
        return ''

    def get_url(self, lang='pt'):
        """Get URL: page URL if linked, otherwise custom URL with language prefix"""
        if self.page:
            return self.page.get_absolute_url(lang)
        url = self.url or '#'
        # Add language prefix for relative URLs when not the default language
        if url.startswith('/') and url != '/':
            try:
                site_settings = SiteSettings.objects.first()
                default_lang = site_settings.get_default_language() if site_settings else 'pt'
            except Exception:
                default_lang = 'pt'
            if lang != default_lang:
                return f'/{lang}{url}'
        return url


class Blueprint(models.Model):
    """Site-level content plan / wireframe"""
    name = models.CharField(max_length=200, default='Main Blueprint')
    description = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return self.name


class BlueprintPage(models.Model):
    """A page within a blueprint"""
    blueprint = models.ForeignKey(Blueprint, on_delete=models.CASCADE, related_name='blueprint_pages')
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, blank=True)
    description = models.TextField(blank=True, default='')
    sections = models.JSONField(default=list, blank=True)
    sort_order = models.IntegerField(default=0)
    page = models.ForeignKey('Page', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='blueprint_source')

    class Meta:
        ordering = ['sort_order', 'id']

    def __str__(self):
        return self.title


