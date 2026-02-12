from django.contrib import admin
from django import forms
from django.conf import settings as django_settings
from .models import SiteSettings, DynamicForm, FormSubmission, SiteImage, Page, PageVersion, GlobalSection, MenuItem


# ===================================
# Custom Widgets for JSON Translations
# ===================================

class LanguageManagementWidget(forms.Widget):
    """
    Custom widget for managing site languages.
    Allows adding/removing languages dynamically.
    """

    def render(self, name, value, attrs=None, renderer=None):
        if value is None or not isinstance(value, list):
            value = []

        html_parts = ['<div class="language-management-widget" style="margin-bottom: 20px;">']

        # Add styles and JavaScript
        html_parts.append('''
        <style>
            .language-item {
                display: flex;
                gap: 10px;
                align-items: center;
                margin-bottom: 10px;
                padding: 12px;
                background: #f8f9fa;
                border-left: 3px solid #007bff;
                border-radius: 4px;
            }
            .language-item input {
                padding: 6px 10px;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
            .language-item .lang-code {
                width: 80px;
                font-weight: bold;
            }
            .language-item .lang-name {
                flex: 1;
            }
            .remove-lang-btn {
                padding: 6px 12px;
                background: #dc3545;
                color: white;
                border: none;
                border-radius: 4px;
                cursor: pointer;
            }
            .remove-lang-btn:hover {
                background: #c82333;
            }
            .add-lang-btn {
                padding: 8px 16px;
                background: #28a745;
                color: white;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                margin-top: 10px;
            }
            .add-lang-btn:hover {
                background: #218838;
            }
        </style>
        ''')

        # Render existing languages
        html_parts.append('<div id="languages-container">')
        for idx, lang in enumerate(value):
            code = lang.get('code', '') if isinstance(lang, dict) else ''
            lang_name = lang.get('name', '') if isinstance(lang, dict) else ''
            html_parts.append(f'''
            <div class="language-item" data-index="{idx}">
                <input type="text" class="lang-code" name="{name}_code_{idx}" value="{code}" placeholder="Code (e.g., pt)" required>
                <input type="text" class="lang-name" name="{name}_name_{idx}" value="{lang_name}" placeholder="Name (e.g., Portuguese)" required>
                <button type="button" class="remove-lang-btn" onclick="removeLanguage(this)">Remove</button>
            </div>
            ''')
        html_parts.append('</div>')

        # Add language button
        html_parts.append(f'''
        <button type="button" class="add-lang-btn" onclick="addLanguage('{name}')">+ Add Language</button>

        <script>
        let langIndex = {len(value)};

        function addLanguage(fieldName) {{
            const container = document.getElementById('languages-container');
            const div = document.createElement('div');
            div.className = 'language-item';
            div.setAttribute('data-index', langIndex);
            div.innerHTML = `
                <input type="text" class="lang-code" name="${{fieldName}}_code_${{langIndex}}" placeholder="Code (e.g., es)" required>
                <input type="text" class="lang-name" name="${{fieldName}}_name_${{langIndex}}" placeholder="Name (e.g., Spanish)" required>
                <button type="button" class="remove-lang-btn" onclick="removeLanguage(this)">Remove</button>
            `;
            container.appendChild(div);
            langIndex++;
        }}

        function removeLanguage(btn) {{
            const item = btn.closest('.language-item');
            if (document.querySelectorAll('.language-item').length > 1) {{
                item.remove();
            }} else {{
                alert('You must have at least one language enabled.');
            }}
        }}
        </script>
        ''')

        html_parts.append('</div>')
        return ''.join(html_parts)

    def value_from_datadict(self, data, files, name):
        """Extract languages list from form data"""
        languages = []
        idx = 0
        while True:
            code_key = f"{name}_code_{idx}"
            name_key = f"{name}_name_{idx}"

            if code_key not in data:
                break

            code = data.get(code_key, '').strip()
            lang_name = data.get(name_key, '').strip()

            if code and lang_name:
                languages.append({
                    'code': code,
                    'name': lang_name
                })

            idx += 1

        return languages if languages else [{'code': 'pt', 'name': 'Portuguese'}]


class TranslationJSONWidget(forms.Widget):
    """
    Custom widget to edit JSON translations as separate inputs per language.
    Provides a clean UI for editing translations without dealing with raw JSON.
    """

    def __init__(self, widget_type='text', attrs=None):
        super().__init__(attrs)
        self.widget_type = widget_type  # 'text', 'textarea', or 'richtext'

    def render(self, name, value, attrs=None, renderer=None):
        if value is None or not isinstance(value, dict):
            value = {}

        html_parts = ['<div class="translation-json-widget" style="margin-bottom: 20px;">']

        # Get languages from SiteSettings or fallback to django settings
        from .models import SiteSettings
        try:
            site_settings = SiteSettings.objects.first()
            languages = site_settings.get_enabled_languages() if site_settings else django_settings.LANGUAGES
        except:
            languages = django_settings.LANGUAGES

        for lang_code, lang_name in languages:
            lang_value = value.get(lang_code, '')
            field_id = f"id_{name}_{lang_code}"

            html_parts.append(f'<div style="margin-bottom: 15px; padding: 10px; background: #f8f9fa; border-left: 3px solid #007bff; border-radius: 4px;">')
            html_parts.append(f'<label for="{field_id}" style="display: block; font-weight: bold; margin-bottom: 5px; color: #333;">')
            html_parts.append(f'{lang_name} ({lang_code.upper()})</label>')

            if self.widget_type == 'textarea':
                html_parts.append(f'<textarea id="{field_id}" name="{name}_{lang_code}" rows="6" ')
                html_parts.append('style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; font-family: monospace;">')
                html_parts.append(f'{lang_value}</textarea>')
            else:  # text input
                html_parts.append(f'<input type="text" id="{field_id}" name="{name}_{lang_code}" value="{lang_value}" ')
                html_parts.append('style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px;">')

            html_parts.append('</div>')

        html_parts.append('</div>')
        return ''.join(html_parts)

    def value_from_datadict(self, data, files, name):
        """Extract JSON from form data"""
        result = {}

        # Get languages from SiteSettings or fallback to django settings
        from .models import SiteSettings
        try:
            site_settings = SiteSettings.objects.first()
            languages = site_settings.get_enabled_languages() if site_settings else django_settings.LANGUAGES
        except:
            languages = django_settings.LANGUAGES

        for lang_code, _ in languages:
            field_name = f"{name}_{lang_code}"
            if field_name in data:
                value = data[field_name].strip()
                if value:  # Only include non-empty values
                    result[lang_code] = value
        return result if result else {}


class TranslationJSONField(forms.JSONField):
    """Form field for JSON translations with custom widget"""

    def __init__(self, *args, widget_type='text', **kwargs):
        kwargs['widget'] = TranslationJSONWidget(widget_type=widget_type)
        # Don't require the field - allow empty JSON
        kwargs.setdefault('required', False)
        super().__init__(*args, **kwargs)

    def prepare_value(self, value):
        """Prepare value for display in widget"""
        if value is None:
            return {}
        if isinstance(value, str):
            import json
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return {}
        return value


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    """Admin for site settings"""

    fieldsets = (
        ('Basic Information (Translations)', {
            'fields': ('site_name_i18n', 'site_description_i18n', 'logo', 'logo_dark_bg'),
            'description': 'Site name and description in all languages. Upload both light and dark versions of your logo.',
        }),
        ('Language Settings', {
            'fields': ('default_language', 'enabled_languages'),
            'description': 'Configure which languages are available on your site and set the default language. Changes here will affect the entire site.',
        }),
        ('AI Context - Project Briefing', {
            'fields': ('project_briefing',),
            'description': 'Detailed description of the project/business for AI content generation. Include business type, target audience, brand values, tone of voice, key messaging, and any specific guidelines.',
        }),
        ('Contact Information', {
            'fields': ('contact_email', 'contact_phone', 'contact_address_i18n')
        }),
        ('Google Maps', {
            'fields': ('google_maps_embed_url',),
            'description': 'Google Maps embed URL for the contact page.',
        }),
        ('Social Media', {
            'fields': ('facebook_url', 'instagram_url', 'youtube_url', 'linkedin_url', 'twitter_url')
        }),
        ('Design System - Colors', {
            'fields': ('primary_color', 'primary_color_hover', 'secondary_color', 'text_color', 'heading_color'),
            'description': 'Customize the color scheme of your website. Use hex color codes (e.g., #1e3a8a).',
        }),
        ('Design System - Typography', {
            'fields': (
                ('heading_font', 'body_font'),
                ('h1_font', 'h2_font'),
                ('h3_font', 'h4_font'),
                ('h5_font', 'h6_font'),
            ),
            'description': 'Select Google Fonts for your website. Choose from popular professional fonts. The selected fonts will be automatically loaded from Google Fonts.',
        }),
        ('Design System - Buttons', {
            'fields': ('button_style', 'button_size'),
            'description': 'Customize the appearance of buttons throughout the site.',
        }),
        ('SEO', {
            'fields': ('meta_keywords', 'google_analytics_id')
        }),
        ('Maintenance Mode', {
            'fields': ('maintenance_mode',),
            'description': 'Enable maintenance mode to show a maintenance page to all visitors. Staff users will still have access to the site.',
            'classes': ('collapse',)
        }),
    )

    list_display = ('site_name', 'maintenance_mode_status')
    list_display_links = ('site_name',)

    def maintenance_mode_status(self, obj):
        """Display maintenance mode status with icon"""
        if obj.maintenance_mode:
            return '🔧 Active'
        return '✓ Normal'
    maintenance_mode_status.short_description = 'Status'

    def get_form(self, request, obj=None, **kwargs):
        """Customize form to use custom widgets for JSON translation fields"""
        form = super().get_form(request, obj, **kwargs)

        # Use custom widget for JSON translation fields
        if 'site_name_i18n' in form.base_fields:
            form.base_fields['site_name_i18n'] = TranslationJSONField(
                label='Site Name',
                widget_type='text',
                required=False
            )

        if 'site_description_i18n' in form.base_fields:
            form.base_fields['site_description_i18n'] = TranslationJSONField(
                label='Site Description',
                widget_type='text',
                required=False
            )

        if 'contact_address_i18n' in form.base_fields:
            form.base_fields['contact_address_i18n'] = TranslationJSONField(
                label='Contact Address',
                widget_type='textarea',
                required=False
            )

        # Use custom widget for language management
        if 'enabled_languages' in form.base_fields:
            form.base_fields['enabled_languages'].widget = LanguageManagementWidget()
            form.base_fields['enabled_languages'].required = True
            form.base_fields['enabled_languages'].help_text = 'Manage the languages available on your site. At least one language is required.'

        return form

    def has_add_permission(self, request):
        # Only allow one instance
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        # Don't allow deletion
        return False


@admin.register(DynamicForm)
class DynamicFormAdmin(admin.ModelAdmin):
    """Admin for dynamic form definitions"""

    list_display = ('name', 'slug', 'notification_email', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(FormSubmission)
class FormSubmissionAdmin(admin.ModelAdmin):
    """Admin for form submissions"""

    list_display = ('form', 'is_read', 'language', 'created_at')
    list_filter = ('form', 'is_read', 'created_at')
    readonly_fields = ('form', 'data', 'source_page', 'language', 'ip_address', 'user_agent', 'notification_sent', 'created_at')

    def has_add_permission(self, request):
        return False


@admin.register(SiteImage)
class SiteImageAdmin(admin.ModelAdmin):
    """Admin for site images - Central media library"""

    list_display = ('__str__', 'tags', 'is_active', 'uploaded_at')
    list_filter = ('is_active', 'uploaded_at')
    search_fields = ('key', 'tags')
    readonly_fields = ('uploaded_at', 'updated_at')
    date_hierarchy = 'uploaded_at'
    ordering = ['-uploaded_at']

    fieldsets = (
        ('Image Upload', {
            'fields': ('image', 'title_i18n', 'alt_text_i18n'),
            'description': 'Upload image and provide title and alt text in all languages.'
        }),
        ('Organization', {
            'fields': ('tags', 'key'),
            'description': 'Organize images with tags. The key field is optional and only needed for template references.'
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Metadata', {
            'fields': ('uploaded_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_form(self, request, obj=None, **kwargs):
        """Customize form to use custom widgets for JSON translation fields"""
        form = super().get_form(request, obj, **kwargs)

        # Use custom widget for JSON translation fields
        if 'title_i18n' in form.base_fields:
            form.base_fields['title_i18n'] = TranslationJSONField(
                label='Title',
                widget_type='text',
                required=False
            )

        if 'alt_text_i18n' in form.base_fields:
            form.base_fields['alt_text_i18n'] = TranslationJSONField(
                label='Alt Text',
                widget_type='text',
                required=False
            )

        return form

    def get_search_results(self, request, queryset, search_term):
        """Enhanced search for autocomplete fields"""
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        return queryset, use_distinct


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    """Admin for pages"""

    list_display = ('__str__', 'slug', 'is_active', 'updated_at')
    list_filter = ('is_active', 'updated_at')
    search_fields = ('slug',)
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Page Content (Translations)', {
            'fields': ('title_i18n', 'slug_i18n', 'is_active'),
            'description': 'Page title and slug in all languages. Each language can have its own URL-friendly slug.',
        }),
        ('HTML Content', {
            'fields': ('html_content', 'content'),
            'description': 'Full page HTML and translation JSON. Use {{trans.field}} for translatable content.',
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_form(self, request, obj=None, **kwargs):
        """Customize form to use custom widget for JSON translation fields"""
        form = super().get_form(request, obj, **kwargs)

        # Use custom widget for title_i18n
        if 'title_i18n' in form.base_fields:
            form.base_fields['title_i18n'] = TranslationJSONField(
                label='Page Title',
                widget_type='text',
                required=False
            )

        # Use custom widget for slug_i18n
        if 'slug_i18n' in form.base_fields:
            form.base_fields['slug_i18n'] = TranslationJSONField(
                label='Page Slug (URL)',
                widget_type='text',
                required=False
            )

        return form


@admin.register(PageVersion)
class PageVersionAdmin(admin.ModelAdmin):
    """Admin for Page versions"""
    list_display = ('page', 'version_number', 'title', 'slug', 'is_active', 'created_at', 'created_by')
    list_filter = ('is_active', 'created_at')
    search_fields = ('title', 'slug', 'page__slug')
    readonly_fields = ('page', 'version_number', 'title', 'slug', 'is_active', 'created_at', 'created_by', 'change_summary')
    ordering = ('-created_at',)

    def has_add_permission(self, request):
        """Versions are created automatically, not manually"""
        return False

    def has_change_permission(self, request, obj=None):
        """Versions are immutable"""
        return False


@admin.register(GlobalSection)
class GlobalSectionAdmin(admin.ModelAdmin):
    """Admin for global sections like header and footer"""
    
    list_display = ["key", "name", "section_type", "is_active", "cache_duration", "updated_at"]
    list_filter = ["section_type", "is_active", "created_at"]
    search_fields = ["key", "name", "html_template"]
    
    fieldsets = (
        ("Basic Information", {
            "fields": ("key", "section_type", "name", "is_active", "order")
        }),
        ("Template", {
            "fields": ("html_template",),
            "description": "HTML template with Django template syntax. Use context variables like LOGO, SITE_NAME, etc."
        }),
        ("Translatable Content (JSON)", {
            "fields": ("content",),
            "description": "Optional: Store translatable content as JSON: {\"translations\": {\"pt\": {...}, \"en\": {...}}}"
        }),
        ("Performance", {
            "fields": ("cache_duration", "fallback_template"),
            "description": "Cache settings and fallback template path"
        }),
    )
    
    readonly_fields = ["created_at", "updated_at"]
    
    class Media:
        css = {
            "all": ("admin/css/custom_admin.css",)
        }
        js = ("admin/js/global_section_admin.js",)


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    """Admin for navigation menu items"""
    list_display = ('__str__', 'page', 'url', 'parent', 'sort_order', 'is_active')
    list_filter = ('is_active',)
    list_editable = ('sort_order', 'is_active')
    ordering = ('sort_order', 'id')

