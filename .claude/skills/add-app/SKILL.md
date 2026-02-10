---
name: add-app
description: Scaffold a new decoupled app for a DjangoPress site. Creates the app, models, views, templates, URLs, and registers it correctly in i18n_patterns before the catch-all.
argument-hint: [app-name]
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, AskUserQuestion
---

# Add a Decoupled App to DjangoPress

Create a new decoupled feature app for this DjangoPress site. The app name is: **$ARGUMENTS**

If no app name was provided, ask the user what the app should be called.

## DjangoPress App Rules

1. **Decoupled** — the app should NOT import from other apps except `core` (for `SiteSettings`, `SiteImage`)
2. **Multi-language** — use JSON fields (`JSONField`) for all user-facing text, following the `{"pt": "...", "en": "..."}` pattern
3. **Tailwind CSS** — templates extend `base.html`, use Tailwind classes, no custom CSS unless absolutely necessary
4. **URL registration** — public-facing URLs MUST be inside `i18n_patterns()` BEFORE `core.urls` (which is a catch-all)

## Step 1: Create the App

```bash
python manage.py startapp <app_name>
```

## Step 2: Add to INSTALLED_APPS

Edit `config/settings.py` — add `'<app_name>'` to `INSTALLED_APPS`.

## Step 3: Create Models

Ask the user what the app's main model should contain. Follow these conventions:

- Use `title_i18n = models.JSONField('Title', default=dict, blank=True)` for translated text
- Use `slug_i18n = models.JSONField('Slug', default=dict, blank=True)` for translated slugs
- Add `is_active`, `created_at`, `updated_at` fields
- Add `sort_order` if items need manual ordering
- For image galleries, use a through model linking to `core.SiteImage`:

```python
class <Model>Image(models.Model):
    parent = models.ForeignKey('<Model>', on_delete=models.CASCADE, related_name='gallery_items')
    site_image = models.ForeignKey('core.SiteImage', on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']
        unique_together = ('parent', 'site_image')
```

- Add helper methods: `get_title(lang)`, `get_slug(lang)`, `get_absolute_url(lang)` following the `Page` model pattern
- For `get_absolute_url(lang)`, follow the same default-language-no-prefix pattern as `Page`:

```python
def get_absolute_url(self, lang=None):
    from core.models import SiteSettings
    try:
        site_settings = SiteSettings.objects.first()
        default_lang = site_settings.get_default_language() if site_settings else 'pt'
    except Exception:
        default_lang = 'pt'
    if lang is None:
        lang = default_lang
    slug = self.get_slug(lang)
    if lang == default_lang:
        return f'/<app_prefix>/{slug}/'
    return f'/{lang}/<app_prefix>/{slug}/'
```

## Step 4: Create URLs

Create `<app_name>/urls.py`:

```python
from django.urls import path
from . import views

app_name = '<app_name>'

urlpatterns = [
    path('<app_prefix>/', views.<List>View.as_view(), name='list'),
    path('<app_prefix>/<slug:slug>/', views.<Detail>View.as_view(), name='detail'),
]
```

## Step 5: Register URLs in config/urls.py

**CRITICAL:** The app's URLs must be included inside `i18n_patterns()` BEFORE `core.urls`:

```python
urlpatterns += i18n_patterns(
    path('', include('<app_name>.urls')),    # <-- BEFORE core
    path('', include('core.urls')),          # <-- catch-all last
    prefix_default_language=True,
)
```

Read the current `config/urls.py` and modify the existing `i18n_patterns` block. Do NOT create a second one.

## Step 6: Create Views

- Use class-based views (ListView, DetailView)
- Get the current language from the request: `lang = getattr(request, 'LANGUAGE_CODE', 'pt')`
- Get SiteSettings for language info: `SiteSettings.objects.first()`
- For list views, resolve translated slugs in the queryset
- For detail views, look up by slug in the current language

## Step 7: Create Templates

Create templates in `<app_name>/templates/<app_name>/`:

- `list.html` — extends `base.html`, lists items with cards
- `detail.html` — extends `base.html`, shows full item

Templates should:
- Extend `{% extends 'base.html' %}`
- Use `{% block content %}...{% endblock %}`
- Use Tailwind CSS classes for all styling
- Use the design system context variables: `{{ THEME.primary_color }}`, etc.
- Support the lightbox for image galleries (use `data-lightbox="gallery-name"`)

## Step 8: Run Migrations

```bash
python manage.py makemigrations <app_name>
python manage.py migrate
```

## Step 9: Add Backoffice Management (Optional)

Ask the user if they want backoffice CRUD views for managing this app's content. If yes:

1. Add views to `backoffice/views.py` or create `<app_name>/backoffice_views.py`
2. Add URL patterns in `backoffice/urls.py`
3. Add a link in the backoffice sidebar template
4. Include per-language input fields for all i18n JSON fields (same pattern as the settings page)

## Checklist Before Done

- [ ] App created and added to INSTALLED_APPS
- [ ] Models have i18n JSON fields, not plain CharField for user text
- [ ] URLs registered in i18n_patterns BEFORE core.urls
- [ ] Migrations created and applied
- [ ] Templates extend base.html and use Tailwind
- [ ] Dev server starts without errors: `python manage.py runserver 8000`
