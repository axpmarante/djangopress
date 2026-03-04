# core/mixins.py
from django.utils.translation import get_language


class I18nModelMixin:
    """Mixin for models with _i18n JSON fields.

    Provides language-aware field resolution with fallback to default language.
    """

    def get_i18n_field(self, field_name, lang=None):
        from core.models import SiteSettings
        lang = lang or get_language()
        settings = SiteSettings.load()
        default = settings.get_default_language() if settings else 'pt'
        data = getattr(self, f'{field_name}_i18n', None) or {}
        return data.get(lang) or data.get(default) or ''

    def get_i18n_dict(self, field_name):
        return getattr(self, f'{field_name}_i18n', None) or {}
