---
name: add-app
description: Scaffold a new decoupled app for a DjangoPress site. Creates the app, models, views, templates, URLs, and registers it correctly in i18n_patterns before the catch-all.
argument-hint: [app-name]
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, AskUserQuestion
---

# Add a Decoupled App to DjangoPress

Create a new decoupled feature app for this DjangoPress site. The app name is: **$ARGUMENTS**

If no app name was provided, ask the user what the app should be called.

> **Reference:** Read `docs/decoupled-app-reference.md` first — it contains the full pattern with code examples based on the **news** app. The news app (`news/`) is the canonical template to copy from.

## DjangoPress App Rules

1. **Decoupled** — the app should NOT import from other apps except `core` (for `SiteSettings`, `SiteImage`, `I18nModelMixin`)
2. **Multi-language** — all models use `I18nModelMixin` from `core/mixins.py` with `_i18n` JSON fields
3. **Per-language HTML** — content models store HTML in `html_content_i18n` (same pattern as `Page.html_content_i18n`)
4. **Tailwind CSS** — templates extend `base.html`, use Tailwind classes
5. **URL registration** — public-facing URLs MUST be inside `i18n_patterns()` BEFORE `core.urls` (catch-all)

## Step 1: Create the App

```bash
python manage.py startapp <app_name>
```

Add `'<app_name>'` to `INSTALLED_APPS` in `config/settings.py`.

## Step 2: Create Models

Ask the user what fields their main content model needs. Then create models following the news app pattern. Every app needs at minimum:

### Main Content Model

```python
from core.mixins import I18nModelMixin
from core.models import SiteImage

class <Item>(I18nModelMixin, models.Model):
    # Required i18n fields
    title_i18n = models.JSONField('Title', default=dict, blank=True)
    slug_i18n = models.JSONField('Slug', default=dict, blank=True)
    excerpt_i18n = models.JSONField('Excerpt', default=dict, blank=True)
    html_content_i18n = models.JSONField('HTML Content', default=dict, blank=True)
    meta_description_i18n = models.JSONField('Meta Description', default=dict, blank=True)

    # Relations (add as needed)
    category = models.ForeignKey('<Category>', on_delete=models.SET_NULL, null=True, blank=True, related_name='items')
    featured_image = models.ImageField(upload_to='<app>/', blank=True, null=True)

    # Publishing
    is_published = models.BooleanField(default=False)
    published_date = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-published_date', '-created_at']

    def __str__(self):
        return self.get_i18n_field('title') or f'<Item> #{self.pk}'

    def get_absolute_url(self, lang=None):
        from django.urls import reverse
        from django.utils.translation import get_language
        from core.models import SiteSettings
        lang = lang or get_language()
        slug = (self.slug_i18n or {}).get(lang, '')
        if not slug:
            settings = SiteSettings.load()
            default = settings.get_default_language() if settings else 'pt'
            slug = (self.slug_i18n or {}).get(default, '')
        try:
            return reverse('<app>:detail', kwargs={'slug': slug}) if slug else '#'
        except Exception:
            return '#'

    def save(self, *args, **kwargs):
        if self.title_i18n and not self.slug_i18n:
            from django.utils.text import slugify
            self.slug_i18n = {
                lang: slugify(title) for lang, title in self.title_i18n.items() if title
            }
        super().save(*args, **kwargs)
```

### Category Model

```python
class <Category>(I18nModelMixin, models.Model):
    name_i18n = models.JSONField(default=dict, blank=True)
    slug_i18n = models.JSONField(default=dict, blank=True)
    description_i18n = models.JSONField(default=dict, blank=True)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['order', 'pk']

    def save(self, *args, **kwargs):
        if self.name_i18n and not self.slug_i18n:
            from django.utils.text import slugify
            self.slug_i18n = {lang: slugify(name) for lang, name in self.name_i18n.items() if name}
        super().save(*args, **kwargs)
```

### Layout Model

```python
class <App>Layout(models.Model):
    key = models.SlugField(max_length=50, unique=True)  # 'list', 'detail', 'category'
    html_content_i18n = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
```

### Gallery Through Model (if needed)

```python
class <Item>GalleryImage(models.Model):
    parent = models.ForeignKey('<Item>', on_delete=models.CASCADE, related_name='gallery_items')
    site_image = models.ForeignKey(SiteImage, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'added_at']
        unique_together = [['parent', 'site_image']]
```

Reference: `news/models.py`

## Step 3: Create Public Views

Create `<app_name>/public_views.py` with three views following the news pattern:

- **ListView** — paginated list, loads Layout with key `'list'`
- **DetailView** — single item, loads Layout with key `'detail'`, supports `?edit=v2`
- **CategoryView** — filtered list by category, loads Layout with key `'list'`

All views:
1. Extend `TemplateView` with `template_name = '<app>/base_<app>.html'`
2. Load layout HTML from `<App>Layout` model (with fallback constants)
3. Render layout as Django Template with `RequestContext`
4. Put rendered HTML in `context['page_content']`

**Critical for editor v2:** The detail view must detect edit mode and inject ContentType:

```python
edit_param = self.request.GET.get('edit')
if self.request.user.is_staff and edit_param in ('true', 'v2'):
    context['edit_mode'] = 'v2'
    from django.contrib.contenttypes.models import ContentType
    ct = ContentType.objects.get_for_model(item)
    context['editable_content_type_id'] = ct.id
    context['editable_object_id'] = item.pk
```

Reference: `news/public_views.py`

## Step 4: Create Template

Create `<app_name>/templates/<app_name>/base_<app_name>.html`:

```html
{% extends "base.html" %}

{% block content %}
{{ page_content }}
{% endblock %}

{% block extra_js %}
{% if edit_mode == 'v2' and editable_content_type_id %}
<script>
  window.EDITOR_CONFIG.contentTypeId = {{ editable_content_type_id }};
  window.EDITOR_CONFIG.objectId = {{ editable_object_id }};
</script>
{% endif %}
{% endblock %}
```

This enables inline editing — no JS changes needed.

## Step 5: Create URLs

Create `<app_name>/urls.py`:

```python
from django.urls import path
from . import public_views

app_name = '<app_name>'

urlpatterns = [
    path('<prefix>/', public_views.ListView.as_view(), name='list'),
    path('<prefix>/category/<slug:slug>/', public_views.CategoryView.as_view(), name='category'),
    path('<prefix>/<slug:slug>/', public_views.DetailView.as_view(), name='detail'),
]
```

**Important:** Category URL before detail URL to avoid slug conflicts.

## Step 6: Register URLs in config/urls.py

Read the current `config/urls.py` and add the app inside the existing `i18n_patterns` block, **before** `core.urls`:

```python
urlpatterns += i18n_patterns(
    path('', include('<app_name>.urls')),    # ← BEFORE core
    path('', include('core.urls')),          # catch-all last
    prefix_default_language=True,
)
```

Do NOT create a second `i18n_patterns` block.

## Step 7: Create Template Tags

Create `<app_name>/templatetags/__init__.py` and `<app_name>/templatetags/<app_name>_tags.py` with tags for embedding records in CMS pages:

- `{% latest_<items> N as var %}` — N most recent published items
- `{% <items>_by_category "slug" N as var %}` — N items from a category
- `{% <app>_categories as var %}` — all active categories

Reference: `news/templatetags/news_tags.py`

## Step 8: Create Backoffice Views

Create views in `<app_name>/views.py` (or add to `backoffice/views.py`):

- CRUD views for the main model (List, Create, Update, Delete)
- Category CRUD views
- Layout list/edit views
- AI tool views (Generate, Bulk, Refine, Images) — use `SuperuserRequiredMixin`

Create forms in `<app_name>/forms.py` with `ModelForm` for the content model and category.

Reference: `news/views.py`, `news/forms.py`

## Step 9: Add Backoffice URLs

Add URL patterns in `backoffice/urls.py` for all CRUD + AI views:

```python
# CRUD
path('<app>/', views.ListView.as_view(), name='<app>_list'),
path('<app>/create/', views.CreateView.as_view(), name='<app>_create'),
path('<app>/<int:pk>/edit/', views.UpdateView.as_view(), name='<app>_edit'),
path('<app>/<int:pk>/delete/', views.DeleteView.as_view(), name='<app>_delete'),
# Categories, Layouts, AI tools...
```

Reference: `backoffice/urls.py` (search for `news`)

## Step 10: Add Sidebar Navigation

Add a collapsible section in `backoffice/templates/backoffice/includes/sidebar.html` with links to:
- All Items, Categories, Layouts, AI Generate, AI Bulk Create

Reference: sidebar.html (search for "News" section)

## Step 11: Create Backoffice Templates

Create templates in `backoffice/templates/backoffice/` following the news pattern:
- `<app>_list.html`, `<app>_form.html`, `<app>_confirm_delete.html`
- `<app>_categories.html`, `<app>_category_form.html`, `<app>_category_confirm_delete.html`
- `<app>_layouts.html`, `<app>_layout_form.html`
- `ai_generate_<app>.html`, `ai_bulk_<app>.html`, `ai_refine_<app>.html`, `<app>_images.html`

Reference: `backoffice/templates/backoffice/` (files prefixed with `news_` or `ai_*_news`)

## Step 12: Add AI Endpoints

Add API endpoints in `ai/views.py` and `ai/urls.py`:

```python
# ai/urls.py
path('api/generate-<item>/', views.generate_<item>_api, name='generate_<item>'),
path('api/generate-<item>/stream/', views.generate_<item>_stream, name='generate_<item>_stream'),
path('api/chat-refine-<item>/', views.chat_refine_<item>_api, name='chat_refine_<item>'),
path('api/chat-refine-<item>/stream/', views.chat_refine_<item>_stream, name='chat_refine_<item>_stream'),
path('api/save-<item>/', views.save_<item>_api, name='save_<item>'),
path('api/<item>-sessions/<int:id>/', views.list_<item>_sessions_api, name='list_<item>_sessions'),
```

Use `RefinementSession` with generic FK for chat history:

```python
from django.contrib.contenttypes.models import ContentType
ct = ContentType.objects.get_for_model(item)
session = RefinementSession(content_type=ct, object_id=item.pk, ...)
```

Reference: `ai/views.py` (search for `news`), `ai/urls.py`

## Step 13: Register Admin

Create `<app_name>/admin.py`:

```python
from django.contrib import admin
from .models import <Item>, <Category>, <Layout>

@admin.register(<Item>)
class <Item>Admin(admin.ModelAdmin):
    list_display = ['__str__', 'is_published', 'published_date']
    list_filter = ['is_published', 'category']

@admin.register(<Category>)
class <Category>Admin(admin.ModelAdmin):
    list_display = ['__str__', 'order', 'is_active']

@admin.register(<Layout>)
class <Layout>Admin(admin.ModelAdmin):
    list_display = ['key', 'updated_at']
```

Reference: `news/admin.py`

## Step 14: Add Dashboard Stats

In `backoffice/views.py` `DashboardView.get_context_data()`, add counts:

```python
from <app_name>.models import <Item>
context['<app>_count'] = <Item>.objects.count()
context['published_<app>_count'] = <Item>.objects.filter(is_published=True).count()
```

## Step 15: Run Migrations

```bash
python manage.py makemigrations <app_name>
python manage.py migrate
```

## Step 16: Verify

```bash
python manage.py check
python manage.py runserver 8000
```

Test:
- Public pages: `/<lang>/<prefix>/`, `/<lang>/<prefix>/<slug>/`
- Backoffice: `/backoffice/<app>/`
- Editor: `/<lang>/<prefix>/<slug>/?edit=v2` (staff user)

## Checklist

- [ ] App created and added to `INSTALLED_APPS`
- [ ] Models use `I18nModelMixin` and `_i18n` JSON fields
- [ ] `html_content_i18n` field on main content model
- [ ] Auto-slug generation in `save()`
- [ ] `get_absolute_url()` with language fallback
- [ ] Category model with i18n fields
- [ ] Layout model (`key` + `html_content_i18n`)
- [ ] Public views load from Layout with fallback HTML
- [ ] Detail view supports `?edit=v2` with ContentType injection
- [ ] Template extends `base.html` and injects editor config
- [ ] URLs in `i18n_patterns` BEFORE `core.urls`
- [ ] Category URL before detail URL
- [ ] Template tags for "records on page"
- [ ] Backoffice CRUD views + templates
- [ ] Sidebar navigation added
- [ ] AI endpoints with generic FK sessions
- [ ] Dashboard stats added
- [ ] Admin registered
- [ ] Migrations created and applied
- [ ] `python manage.py check` passes
