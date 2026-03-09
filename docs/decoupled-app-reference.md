# Building Decoupled Apps in DjangoPress

> Reference guide based on the **news** app. Copy this pattern for properties, athletes, products, or any content type.

---

## Quick Start

To create a new app (e.g. `properties`):

1. `python manage.py startapp properties`
2. Add to `INSTALLED_APPS` in `config/settings.py`
3. Copy the patterns below, renaming `news` → `properties`, `NewsPost` → `Property`, etc.
4. Register URLs in `config/urls.py` **before** `core.urls`
5. Run `python manage.py makemigrations properties && python manage.py migrate`

Or use the `/add-app properties` Claude Code skill to scaffold automatically.

---

## Directory Structure

```
myapp/
├── __init__.py
├── apps.py
├── models.py              # Data models (Item, Category, Layout)
├── forms.py               # Django forms for backoffice CRUD
├── admin.py               # Django admin registration
├── urls.py                # Public-facing URL patterns
├── public_views.py        # Public views (list, detail, category)
├── views.py               # Backoffice views (CRUD + AI tools)
├── templatetags/
│   ├── __init__.py
│   └── myapp_tags.py      # Template tags for "records on page"
├── templates/
│   └── myapp/
│       └── base_myapp.html  # Master template for public pages
└── migrations/
```

---

## 1. Models

### Base Mixin

All models use `I18nModelMixin` from `djangopress.core.mixins`:

```python
from djangopress.core.mixins import I18nModelMixin

class Property(I18nModelMixin, models.Model):
    ...
```

This gives you `get_i18n_field(field_name, lang=None)` and `get_i18n_dict(field_name)` for language-aware field resolution with automatic fallback to the default language.

### Required Fields

Every content model needs these i18n JSON fields:

```python
title_i18n = models.JSONField('Title', default=dict, blank=True)
slug_i18n = models.JSONField('Slug', default=dict, blank=True)
excerpt_i18n = models.JSONField('Excerpt', default=dict, blank=True)
html_content_i18n = models.JSONField('HTML Content', default=dict, blank=True)
meta_description_i18n = models.JSONField('Meta Description', default=dict, blank=True)
```

The JSON format is always `{"pt": "value", "en": "value"}`.

`html_content_i18n` stores per-language full HTML (same pattern as `Page.html_content_i18n`). This is what the editor v2 reads/writes.

### Auto-Slug Generation

```python
def save(self, *args, **kwargs):
    if self.title_i18n and not self.slug_i18n:
        self.slug_i18n = {
            lang: slugify(title) for lang, title in self.title_i18n.items() if title
        }
    super().save(*args, **kwargs)
```

### get_absolute_url

```python
def get_absolute_url(self, lang=None):
    from django.urls import reverse
    from django.utils.translation import get_language
    from djangopress.core.models import SiteSettings
    lang = lang or get_language()
    slug = (self.slug_i18n or {}).get(lang, '')
    if not slug:
        settings = SiteSettings.load()
        default = settings.get_default_language() if settings else 'pt'
        slug = (self.slug_i18n or {}).get(default, '')
    try:
        return reverse('myapp:detail', kwargs={'slug': slug}) if slug else '#'
    except Exception:
        return '#'
```

### Category Model

Optional but recommended. Same i18n pattern:

```python
class PropertyCategory(I18nModelMixin, models.Model):
    name_i18n = models.JSONField(default=dict, blank=True)
    slug_i18n = models.JSONField(default=dict, blank=True)
    description_i18n = models.JSONField(default=dict, blank=True)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['order', 'pk']
```

### Layout Model

Stores AI-generated HTML templates for list/detail pages:

```python
class PropertyLayout(models.Model):
    key = models.SlugField(max_length=50, unique=True)  # 'list', 'detail', 'category'
    html_content_i18n = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
```

Public views load layouts from this model and render dynamic data through them using Django's template engine.

---

## 2. Public Views

Three views in `public_views.py`, all extending `TemplateView`:

### Pattern

```python
class MyListView(TemplateView):
    template_name = 'myapp/base_myapp.html'

    def get_context_data(self, **kwargs):
        lang, default_lang = _get_lang_and_default()

        # Query records
        posts = MyModel.objects.filter(is_published=True).order_by('-published_date')

        # Resolve i18n fields for template
        for post in posts:
            post.title = post.get_i18n_field('title', lang) or post.get_i18n_field('title', default_lang)
            post.url = post.get_absolute_url(lang)
            # ... etc

        # Load layout HTML from DB (or fallback)
        layout_html = _get_layout_html('list', lang, default_lang)

        # Render layout as Django template with context
        from django.template import Template, RequestContext
        tpl = Template(layout_html)
        ctx = RequestContext(self.request, {'posts': posts, ...})
        rendered = tpl.render(ctx)

        context = super().get_context_data(**kwargs)
        context['page_content'] = rendered
        return context
```

### Edit Mode Detection (Detail View)

The detail view must support `?edit=v2` for inline editing:

```python
# In get_context_data:
edit_param = self.request.GET.get('edit')
if self.request.user.is_staff and edit_param in ('true', 'v2'):
    context['edit_mode'] = 'v2'
    from django.contrib.contenttypes.models import ContentType
    ct = ContentType.objects.get_for_model(post)
    context['editable_content_type_id'] = ct.id
    context['editable_object_id'] = post.pk
```

### Fallback Layouts

Define minimal fallback HTML constants for when no Layout exists in DB:

```python
FALLBACK_LIST = '''
<section data-section="posts-list" id="posts-list" class="py-16 px-4">
  <div class="max-w-6xl mx-auto">
    <h1 class="text-3xl font-bold mb-8">Latest Posts</h1>
    <div class="grid md:grid-cols-3 gap-6">
      {% for post in posts %}
      <a href="{{ post.url }}" class="block bg-white rounded-lg shadow p-6 hover:shadow-lg">
        <h2 class="text-xl font-semibold">{{ post.title }}</h2>
        <p class="text-gray-600 mt-2">{{ post.excerpt }}</p>
      </a>
      {% endfor %}
    </div>
  </div>
</section>
'''
```

---

## 3. URL Registration

### Public URLs (`myapp/urls.py`)

```python
from django.urls import path
from . import public_views

app_name = 'myapp'

urlpatterns = [
    path('properties/', public_views.ListView.as_view(), name='list'),
    path('properties/category/<slug:slug>/', public_views.CategoryView.as_view(), name='category'),
    path('properties/<slug:slug>/', public_views.DetailView.as_view(), name='detail'),
]
```

**Important**: Put category URL before detail to avoid slug conflicts.

### Register in `config/urls.py`

```python
urlpatterns += i18n_patterns(
    path('', include('myapp.urls')),    # ← BEFORE core.urls
    path('', include('djangopress.core.urls')),     # catch-all for CMS pages
    prefix_default_language=True,
)
```

---

## 4. Template Tags ("Records on Page")

This is the Elementor "posts element" equivalent. CMS pages embed app data via template tags.

### `myapp/templatetags/myapp_tags.py`

```python
from django import template
from django.utils.translation import get_language
from myapp.models import MyModel, MyCategory

register = template.Library()

class LatestItemsNode(template.Node):
    def __init__(self, count, var_name):
        self.count = count
        self.var_name = var_name

    def render(self, context):
        lang = get_language()
        items = MyModel.objects.filter(is_published=True)[:self.count]
        resolved = []
        for item in items:
            item.title = item.get_i18n_field('title', lang)
            item.excerpt = item.get_i18n_field('excerpt', lang)
            item.url = item.get_absolute_url(lang)
            resolved.append(item)
        context[self.var_name] = resolved
        return ''

@register.tag('latest_items')
def do_latest_items(parser, token):
    # Usage: {% latest_items 3 as my_items %}
    bits = token.split_contents()
    return LatestItemsNode(int(bits[1]), bits[3])
```

### Usage in CMS Page HTML

Since `html_content_i18n` is rendered as a Django template, these tags work directly:

```html
{% load myapp_tags %}

<section data-section="featured-items" id="featured-items">
  {% latest_items 3 as items %}
  <div class="grid md:grid-cols-3 gap-6">
    {% for item in items %}
    <a href="{{ item.url }}" class="block bg-white rounded-lg shadow p-6">
      <h3>{{ item.title }}</h3>
      <p>{{ item.excerpt }}</p>
    </a>
    {% endfor %}
  </div>
</section>
```

---

## 5. Master Template

### `myapp/templates/myapp/base_myapp.html`

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

The `extra_js` block injects `contentTypeId` and `objectId` into the editor config. This is what makes inline editing work for non-Page content — the editor JS modules send these fields with every API call, and the backend resolves the correct model via `_get_editable_object()`.

---

## 6. Editor v2 Integration

**No JS changes needed.** The editor JS modules already support generic content via `content_type_id`/`object_id`. Your app just needs to:

1. Set `EDITOR_CONFIG.contentTypeId` and `EDITOR_CONFIG.objectId` in the template (see above)
2. Have `html_content_i18n` on your model

The following editor features work automatically:
- Inline text editing
- CSS class editing
- Attribute editing (href, src, etc.)
- Section/element removal
- Background video set/remove
- AI refinement (via refine-multi/apply-option)
- Process images

Version history is Page-only (uses `PageVersion` model). If your app needs versioning, create a similar version model.

---

## 7. AI Integration

### AI API Endpoints

Create endpoints in `ai/views.py` (or your own `myapp/api_views.py`):

```python
# Required endpoints:
POST /ai/api/generate-myitem/          # Generate a new item
POST /ai/api/generate-myitem/stream/   # SSE streaming version
POST /ai/api/chat-refine-myitem/       # Chat-based refinement
POST /ai/api/chat-refine-myitem/stream/
POST /ai/api/save-myitem/             # Save generated item to DB
GET  /ai/api/myitem-sessions/<id>/    # Load chat session history
```

These follow the same pattern as the news endpoints. They use `ContentGenerationService` from `ai/services.py` for the actual LLM calls, and `RefinementSession` with a generic FK for chat history:

```python
from django.contrib.contenttypes.models import ContentType

ct = ContentType.objects.get_for_model(my_item)
session = RefinementSession(
    content_type=ct,
    object_id=my_item.pk,
    title=f'Refinement: {instructions[:60]}',
    model_used='gemini-pro',
    created_by=request.user,
)
```

### Image Processing

The existing `/ai/api/analyze-page-images/` and `/ai/api/process-page-images/` endpoints work with any model — they operate on HTML content by `page_id`. For non-Page content, the editor's process-images module sends `content_type_id`/`object_id` automatically.

---

## 8. Backoffice Integration

### Views (`myapp/views.py`)

Standard Django CBVs with `LoginRequiredMixin`:

- **ListView** — list all items with pagination
- **CreateView / UpdateView** — CRUD with `ModelForm`
- **DeleteView** — delete confirmation
- **CategoryListView / CategoryCreateView / CategoryUpdateView / CategoryDeleteView**
- **LayoutListView / LayoutUpdateView** — edit layout templates
- **GenerateView / BulkView / RefineView / ImagesView** — AI tool pages (SuperuserRequiredMixin)

### Backoffice URLs (`backoffice/urls.py`)

```python
# CRUD
path('properties/', views.PropertyListView.as_view(), name='property_list'),
path('properties/create/', views.PropertyCreateView.as_view(), name='property_create'),
path('properties/<int:pk>/edit/', views.PropertyUpdateView.as_view(), name='property_edit'),
path('properties/<int:pk>/delete/', views.PropertyDeleteView.as_view(), name='property_delete'),

# Categories
path('properties/categories/', views.CategoryListView.as_view(), name='property_categories'),
path('properties/categories/create/', ...),
path('properties/categories/<int:pk>/edit/', ...),
path('properties/categories/<int:pk>/delete/', ...),

# Layouts
path('properties/layouts/', views.LayoutListView.as_view(), name='property_layouts'),
path('properties/layouts/<int:pk>/edit/', ...),

# AI Tools
path('properties/ai/generate/', views.GenerateView.as_view(), name='property_ai_generate'),
path('properties/ai/bulk/', views.BulkView.as_view(), name='property_ai_bulk'),
path('properties/ai/chat/refine/<int:pk>/', views.RefineView.as_view(), name='property_ai_refine'),
path('properties/<int:pk>/images/', views.ImagesView.as_view(), name='property_images'),
```

### Sidebar Navigation

Add a collapsible section to `backoffice/templates/backoffice/includes/sidebar.html`:

```html
<div class="nav-section">
  <a href="{% url 'backoffice:property_list' %}" class="nav-section-header">
    Properties
  </a>
  <div class="nav-section-items">
    <a href="{% url 'backoffice:property_list' %}">All Properties</a>
    <a href="{% url 'backoffice:property_categories' %}">Categories</a>
    <a href="{% url 'backoffice:property_layouts' %}">Layouts</a>
    <a href="{% url 'backoffice:property_ai_generate' %}">AI Generate</a>
    <a href="{% url 'backoffice:property_ai_bulk' %}">AI Bulk Create</a>
  </div>
</div>
```

### Dashboard Stats

Add counts to `backoffice/views.py` `DashboardView`:

```python
from myapp.models import Property
context['property_count'] = Property.objects.count()
context['published_property_count'] = Property.objects.filter(is_published=True).count()
```

---

## 9. Checklist

When creating a new decoupled app, verify:

- [ ] Models use `I18nModelMixin` and `_i18n` JSON fields
- [ ] `html_content_i18n` field exists on the main content model
- [ ] Auto-slug generation in `save()`
- [ ] `get_absolute_url()` with language fallback
- [ ] Public views load from `Layout` model with fallback HTML
- [ ] Detail view supports `?edit=v2` with ContentType injection
- [ ] Template (`base_myapp.html`) extends `base.html` and injects editor config
- [ ] URLs registered in `i18n_patterns` **before** `core.urls`
- [ ] Category URL comes before detail URL (avoid slug conflicts)
- [ ] Template tags created for "records on page" pattern
- [ ] Backoffice CRUD views + templates
- [ ] Sidebar navigation added
- [ ] AI endpoints created (generate, refine, save, sessions)
- [ ] AI endpoints use `RefinementSession` with generic FK
- [ ] Dashboard stats added
- [ ] Admin registered

---

## Reference Files (news app)

| File | Purpose |
|------|---------|
| `news/models.py` | 4 models: NewsPost, NewsCategory, NewsLayout, NewsGalleryImage |
| `news/public_views.py` | 3 public views with layout rendering + edit mode |
| `news/urls.py` | Public URL patterns (3 routes) |
| `news/views.py` | Backoffice views (CRUD + AI tools, ~15 views) |
| `news/forms.py` | NewsPostForm, NewsCategoryForm |
| `news/admin.py` | Admin registration with i18n widgets |
| `news/templatetags/news_tags.py` | 3 template tags for "records on page" |
| `news/templates/news/base_news.html` | Master template with editor config |
| `core/mixins.py` | I18nModelMixin (shared across all apps) |
| `editor_v2/api_views.py` | `_get_editable_object()` handles any model |
