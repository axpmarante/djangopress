from django.apps import AppConfig


class NewsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'djangopress.news'

    def ready(self):
        import djangopress.news.signals  # noqa: F401
