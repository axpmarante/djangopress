from django.apps import AppConfig
from django.conf import settings


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'djangopress.core'

    def ready(self):
        import djangopress.core.signals  # noqa

        # Auto-fix: swap Django's LocaleMiddleware with our custom one that
        # skips redirects for non-i18n paths (backoffice, ai, editor, etc.)
        old_django = 'django.middleware.locale.LocaleMiddleware'
        old_unprefixed = 'core.middleware.LocaleMiddleware'
        new = 'djangopress.core.middleware.LocaleMiddleware'
        if old_django in settings.MIDDLEWARE or old_unprefixed in settings.MIDDLEWARE:
            settings.MIDDLEWARE = [
                new if m in (old_django, old_unprefixed) else m
                for m in settings.MIDDLEWARE
            ]
