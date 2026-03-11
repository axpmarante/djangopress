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

1. **Decoupled** — the app should NOT import from other apps except `djangopress.core` (for `SiteSettings`, `SiteImage`, `I18nModelMixin`)
2. **Multi-language** — all models use `I18nModelMixin` from `core/mixins.py` with `_i18n` JSON fields
3. **Per-language HTML** — content models store HTML in `html_content_i18n` (same pattern as `Page.html_content_i18n`)
4. **Tailwind CSS** — templates extend `base.html`, use Tailwind classes
5. **URL registration** — public-facing URLs MUST be inside `i18n_patterns()` BEFORE `core.urls` (catch-all)

## Step 1: Create the App

```bash
python manage.py startapp <app_name>
```

Add the app to `INSTALLED_APPS` in `config/settings.py`. Since the settings import from `djangopress.settings`, append to the existing list:

```python
# In config/settings.py, after the djangopress import:
INSTALLED_APPS += ['<app_name>']
```

## Step 2: Create Models

Ask the user what fields their main content model needs. Then create models following the news app pattern. Every app needs at minimum:

### Main Content Model

```python
from djangopress.core.mixins import I18nModelMixin
from djangopress.core.models import SiteImage

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
        from djangopress.core.models import SiteSettings
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

Since `config/urls.py` imports from `djangopress.urls`, you need to replace it with a custom version that includes your app's URLs before the core catch-all:

```python
# config/urls.py
from djangopress.urls import urlpatterns as _base_patterns
from django.conf.urls.i18n import i18n_patterns
from django.urls import path, include

# Start with all non-i18n patterns from djangopress
urlpatterns = [p for p in _base_patterns if not hasattr(p, 'url_patterns') or not any(
    hasattr(sub, 'app_name') and sub.app_name == 'core' for sub in getattr(p, 'url_patterns', [])
)]

# Add i18n patterns with your app BEFORE core catch-all
urlpatterns += i18n_patterns(
    path('', include('<app_name>.urls')),    # Your app
    path('', include('djangopress.core.urls')),  # catch-all last
    prefix_default_language=True,
)
```

Alternatively, copy the full `urlpatterns` from `djangopress/urls.py` and add your app's include before `core.urls`.

## Step 7: Create Template Tags

Create `<app_name>/templatetags/__init__.py` and `<app_name>/templatetags/<app_name>_tags.py` with tags for embedding records in CMS pages:

- `{% latest_<items> N as var %}` — N most recent published items
- `{% <items>_by_category "slug" N as var %}` — N items from a category
- `{% <app>_categories as var %}` — all active categories

Reference: `news/templatetags/news_tags.py`

> **Note:** With the pip package architecture, `backoffice/` files live in the djangopress package. For custom apps, keep backoffice views in your app directory and register the URLs in your custom `config/urls.py`.

## Step 8: Create Backoffice Views and Forms

### Forms (`<app_name>/forms.py`)

```python
from django import forms
from .models import <Item>, <Category>
from djangopress.core.models import SiteImage

class <Item>Form(forms.ModelForm):
    """Form for creating and updating items (i18n version)"""

    gallery_images = forms.ModelMultipleChoiceField(
        queryset=SiteImage.objects.filter(is_active=True).order_by('-id'),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Gallery Images',
        help_text='Select images to add to the gallery'
    )

    class Meta:
        model = <Item>
        fields = [
            'title_i18n', 'slug_i18n', 'featured_image', 'excerpt_i18n',
            'html_content_i18n', 'category', 'is_published', 'published_date',
            'meta_description_i18n',
        ]
        widgets = {
            'is_published': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-blue-600 border-gray-300 rounded focus:ring-2 focus:ring-blue-500'
            }),
            'published_date': forms.DateTimeInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'type': 'datetime-local'
            }),
            'featured_image': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['published_date'].required = False
        self.fields['featured_image'].queryset = SiteImage.objects.filter(is_active=True).order_by('-id')
        if self.instance and self.instance.pk:
            self.fields['gallery_images'].initial = self.instance.gallery_images.all()


class <Category>Form(forms.ModelForm):
    class Meta:
        model = <Category>
        fields = ['name_i18n', 'slug_i18n', 'description_i18n', 'order', 'is_active']
        widgets = {
            'name_i18n': forms.Textarea(attrs={
                'rows': 2, 'class': 'w-full px-3 py-2 border border-gray-300 rounded-md text-sm font-mono',
                'placeholder': '{"pt": "Categoria", "en": "Category"}'
            }),
            'slug_i18n': forms.Textarea(attrs={
                'rows': 2, 'class': 'w-full px-3 py-2 border border-gray-300 rounded-md text-sm font-mono',
            }),
            'description_i18n': forms.Textarea(attrs={
                'rows': 3, 'class': 'w-full px-3 py-2 border border-gray-300 rounded-md text-sm font-mono',
            }),
            'order': forms.NumberInput(attrs={
                'class': 'w-24 px-3 py-2 border border-gray-300 rounded-md text-sm',
            }),
        }
```

### Views (`<app_name>/views.py`)

Create views with these patterns:

- CRUD views for the main model (List, Create, Update, Delete)
- Category CRUD views
- Layout list/edit views
- AI tool views (Generate, Bulk, Refine, Images) — use `SuperuserRequiredMixin`

**Critical: Create/Update views must pass language context and handle gallery images:**

```python
from djangopress.core.models import SiteSettings

class <Item>CreateView(LoginRequiredMixin, CreateView):
    model = <Item>
    form_class = <Item>Form
    template_name = 'backoffice/<app>_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = 'Create New <Item>'
        context['submit_text'] = 'Create <Item>'
        # Language context for i18n tabs
        site_settings = SiteSettings.objects.first()
        if site_settings:
            context['languages'] = site_settings.get_enabled_languages()
            context['default_language'] = site_settings.get_default_language()
        else:
            context['languages'] = [('pt', 'Portuguese')]
            context['default_language'] = 'pt'
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        # Handle gallery images
        gallery_images = form.cleaned_data.get('gallery_images')
        if gallery_images:
            self.object.gallery_items.all().delete()
            for idx, site_image in enumerate(gallery_images):
                <Item>GalleryImage.objects.create(
                    parent=self.object, site_image=site_image, order=idx + 1
                )
        return response
```

Same pattern for `<Item>UpdateView` — identical `get_context_data` and `form_valid`.

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

### Form Template Pattern (`<app>_form.html`)

The form template uses **language tabs** for i18n fields and **modal-based image selection**. This is the canonical pattern — copy from `news_form.html`.

**Key architecture:**
1. **Language tab bar** — switches all i18n fields at once, non-i18n fields always visible
2. **Hidden JSON fields** — populated on submit by JS (`assembleI18nJson()`)
3. **`json_script` for initial values** — safe JSON encoding (handles HTML with quotes)
4. **Image modals** — reuse existing `image_selection_modals.html` partial + `image_selection.js`

```html
{% extends 'backoffice/base.html' %}
{% load static %}

{% block title %}{{ form_title }}{% endblock %}

{% block content %}
<div class="max-w-4xl mx-auto">
    <div class="mb-6">
        <h2 class="text-3xl font-bold text-gray-900">{{ form_title }}</h2>
    </div>

    <div class="bg-white rounded-lg shadow p-6">
        <form id="<app>-form" method="post" enctype="multipart/form-data" class="space-y-6">
            {% csrf_token %}

            {% if form.non_field_errors %}
            <div class="bg-red-50 border-l-4 border-red-500 p-4">
                <p class="text-sm text-red-700">{{ form.non_field_errors.0 }}</p>
            </div>
            {% endif %}

            <!-- Language Tabs -->
            <div class="border-b border-gray-200">
                <nav class="flex space-x-4" id="lang-tabs">
                    {% for code, name in languages %}
                    <button type="button"
                            class="lang-tab px-4 py-2 text-sm font-medium transition-colors {% if code == default_language %}border-b-2 border-blue-500 text-blue-600{% else %}text-gray-500 hover:text-gray-700{% endif %}"
                            data-lang="{{ code }}"
                            onclick="switchLanguageTab('{{ code }}')">
                        {{ name }}
                    </button>
                    {% endfor %}
                </nav>
            </div>

            <!-- Hidden JSON fields (populated on submit by JS) -->
            <input type="hidden" name="title_i18n" id="title_i18n_json">
            <input type="hidden" name="slug_i18n" id="slug_i18n_json">
            <input type="hidden" name="excerpt_i18n" id="excerpt_i18n_json">
            <input type="hidden" name="html_content_i18n" id="html_content_i18n_json">
            <input type="hidden" name="meta_description_i18n" id="meta_description_i18n_json">

            <!-- Initial values for JS to parse (safe JSON encoding via json_script) -->
            {{ form.title_i18n.value|default_if_none:"{}"|json_script:"title_i18n_initial" }}
            {{ form.slug_i18n.value|default_if_none:"{}"|json_script:"slug_i18n_initial" }}
            {{ form.excerpt_i18n.value|default_if_none:"{}"|json_script:"excerpt_i18n_initial" }}
            {{ form.html_content_i18n.value|default_if_none:"{}"|json_script:"html_content_i18n_initial" }}
            {{ form.meta_description_i18n.value|default_if_none:"{}"|json_script:"meta_description_i18n_initial" }}

            <!-- Per-language panels (one per language, toggled by JS) -->
            {% for code, name in languages %}
            <div class="lang-panel space-y-6 {% if code != default_language %}hidden{% endif %}" data-lang="{{ code }}">
                <!-- Title -->
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-2">Title ({{ name }}) *</label>
                    <input type="text" class="i18n-field w-full px-4 py-3 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                           data-field="title_i18n" data-lang="{{ code }}" placeholder="Title in {{ name }}">
                </div>

                <!-- Slug -->
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-2">Slug ({{ name }})</label>
                    <input type="text" class="i18n-field w-full px-4 py-3 border border-gray-300 rounded-md font-mono text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                           data-field="slug_i18n" data-lang="{{ code }}" placeholder="url-slug-in-{{ code }}">
                    <p class="mt-1 text-xs text-gray-500">Leave empty to auto-generate from title</p>
                </div>

                <!-- Excerpt -->
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-2">Excerpt ({{ name }})</label>
                    <textarea class="i18n-field w-full px-4 py-3 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                              data-field="excerpt_i18n" data-lang="{{ code }}" rows="3" placeholder="Short summary in {{ name }}"></textarea>
                </div>

                <!-- HTML Content -->
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-2">HTML Content ({{ name }})</label>
                    <textarea class="i18n-field w-full px-4 py-3 border border-gray-300 rounded-md font-mono text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                              data-field="html_content_i18n" data-lang="{{ code }}" rows="15" placeholder="<p>Content in {{ name }}...</p>"></textarea>
                </div>

                <!-- Meta Description -->
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-2">Meta Description ({{ name }})</label>
                    <textarea class="i18n-field w-full px-4 py-3 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                              data-field="meta_description_i18n" data-lang="{{ code }}" rows="2" placeholder="SEO description in {{ name }}"></textarea>
                </div>
            </div>
            {% endfor %}

            <!-- Category (always visible, outside language panels) -->
            <div>
                <label class="block text-sm font-medium text-gray-700 mb-2">Category</label>
                <select name="category" class="w-full px-4 py-3 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent">
                    <option value="">---------</option>
                    {% for choice in form.category.field.queryset %}
                    <option value="{{ choice.pk }}" {% if form.category.value|stringformat:"s" == choice.pk|stringformat:"s" %}selected{% endif %}>{{ choice }}</option>
                    {% endfor %}
                </select>
            </div>

            <!-- Featured Image (modal-based) -->
            <div>
                <label class="block text-sm font-medium text-gray-700 mb-2">Featured Image</label>
                <select name="featured_image" class="hidden" id="id_featured_image">
                    <option value="">---------</option>
                    {% for image in form.featured_image.field.queryset %}
                    <option value="{{ image.pk }}" {% if form.featured_image.value|stringformat:"s" == image.pk|stringformat:"s" %}selected{% endif %}>{{ image }}</option>
                    {% endfor %}
                </select>
                <div id="featured-image-display"></div>
                <div class="mt-3 flex space-x-3">
                    <button type="button" onclick="openFeaturedImageModal()" class="px-4 py-2 text-sm font-medium text-blue-600 bg-blue-50 rounded-lg hover:bg-blue-100 transition-colors">
                        Select from Library
                    </button>
                    <button type="button" onclick="openFeaturedUploadModal()" class="px-4 py-2 text-sm font-medium text-gray-600 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors">
                        Upload New
                    </button>
                </div>
            </div>

            <!-- Publication Settings -->
            <div class="border-t pt-6">
                <h3 class="text-lg font-semibold text-gray-900 mb-4">Publication Settings</h3>
                <div class="space-y-4">
                    <div class="flex items-center">
                        {{ form.is_published }}
                        <label for="{{ form.is_published.id_for_label }}" class="ml-2 block text-sm text-gray-700">
                            {{ form.is_published.help_text }}
                        </label>
                    </div>
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-2">Published Date</label>
                        {{ form.published_date }}
                    </div>
                </div>
            </div>

            <!-- Gallery Images (modal-based) -->
            <div class="border-t pt-6">
                <h3 class="text-lg font-semibold text-gray-900 mb-4">Gallery Images</h3>
                <div id="gallery-checkboxes-container" class="hidden">
                    {% for image in form.gallery_images.field.queryset %}
                    <input type="checkbox" name="gallery_images" value="{{ image.id }}"
                           {% if image in form.gallery_images.initial %}checked{% endif %}>
                    {% endfor %}
                </div>
                <div id="selected-gallery-display"></div>
                <div class="mt-3 flex space-x-3">
                    <button type="button" onclick="openGalleryModal()" class="px-4 py-2 text-sm font-medium text-green-600 bg-green-50 rounded-lg hover:bg-green-100 transition-colors">
                        Select from Library
                    </button>
                    <button type="button" onclick="openUploadModal()" class="px-4 py-2 text-sm font-medium text-gray-600 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors">
                        Upload New
                    </button>
                </div>
            </div>

            <!-- Form Actions -->
            <div class="flex items-center justify-between pt-6 border-t border-gray-200">
                <a href="{% url 'backoffice:<app>_list' %}" class="px-4 py-2 text-sm font-medium text-gray-700 hover:text-gray-900">Cancel</a>
                <button type="submit" class="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors">{{ submit_text }}</button>
            </div>
        </form>
    </div>
</div>

<!-- Image Selection Modals (reusable partial) -->
{% include 'backoffice/partials/image_selection_modals.html' with form=form %}

<script src="{% static 'backoffice/js/image_selection.js' %}"></script>

<script>
// === Language Tab Management ===
const I18N_FIELDS = ['title_i18n', 'slug_i18n', 'excerpt_i18n', 'html_content_i18n', 'meta_description_i18n'];

function initI18nFields() {
    I18N_FIELDS.forEach(fieldName => {
        let data = {};
        try {
            const el = document.getElementById(fieldName + '_initial');
            if (el) {
                const raw = el.textContent;
                if (raw) {
                    const parsed = JSON.parse(raw);
                    // json_script double-encodes: parse again if we got a string
                    data = (typeof parsed === 'string') ? JSON.parse(parsed) : parsed;
                }
            }
        } catch (e) {
            console.warn('Failed to parse i18n initial data for', fieldName, e);
        }
        document.querySelectorAll(`.i18n-field[data-field="${fieldName}"]`).forEach(input => {
            const lang = input.dataset.lang;
            if (data[lang] !== undefined) input.value = data[lang];
        });
    });
}

function assembleI18nJson() {
    I18N_FIELDS.forEach(fieldName => {
        const data = {};
        document.querySelectorAll(`.i18n-field[data-field="${fieldName}"]`).forEach(input => {
            const val = input.value;
            if (val) data[input.dataset.lang] = val;
        });
        document.getElementById(fieldName + '_json').value = JSON.stringify(data);
    });
}

function switchLanguageTab(lang) {
    document.querySelectorAll('.lang-tab').forEach(tab => {
        if (tab.dataset.lang === lang) {
            tab.classList.add('border-b-2', 'border-blue-500', 'text-blue-600');
            tab.classList.remove('text-gray-500');
        } else {
            tab.classList.remove('border-b-2', 'border-blue-500', 'text-blue-600');
            tab.classList.add('text-gray-500');
        }
    });
    document.querySelectorAll('.lang-panel').forEach(panel => {
        panel.classList.toggle('hidden', panel.dataset.lang !== lang);
    });
}

document.addEventListener('DOMContentLoaded', function() {
    initI18nFields();

    // Initialize featured image display
    const select = document.querySelector('select[name="featured_image"]');
    if (select && select.value) {
        const modalItem = document.querySelector(`.modal-image-item[data-image-id="${select.value}"]`);
        if (modalItem) {
            selectFeaturedImage(parseInt(select.value), modalItem.dataset.imageUrl, modalItem.dataset.imageTitle);
        }
    } else {
        clearFeaturedImage();
    }

    // Initialize gallery display
    updateGalleryDisplay();

    // Assemble JSON on submit
    document.getElementById('<app>-form').addEventListener('submit', function(e) {
        assembleI18nJson();
    });
});
</script>
{% endblock %}
```

**Key elements to customize per app:**
- Form ID (`<app>-form`)
- Cancel link URL (`backoffice:<app>_list`)
- Add any app-specific non-i18n fields (price, location, etc.) in the "always visible" section
- Add/remove i18n fields from `I18N_FIELDS` array as needed

**Image modal requirements:**
- `select[name="featured_image"]` — hidden select for form submission
- `#featured-image-display` — JS populates featured image preview
- `#gallery-checkboxes-container` — hidden checkboxes for gallery selection
- `#selected-gallery-display` — JS populates gallery preview grid
- Include `image_selection_modals.html` partial and `image_selection.js`

Reference: `backoffice/templates/backoffice/news_form.html`

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
- [ ] Gallery through model (if needed)
- [ ] Public views load from Layout with fallback HTML
- [ ] Detail view supports `?edit=v2` with ContentType injection
- [ ] Template extends `base.html` and injects editor config
- [ ] URLs in `i18n_patterns` BEFORE `core.urls`
- [ ] Category URL before detail URL
- [ ] Template tags for "records on page"
- [ ] Backoffice CRUD views + templates
- [ ] Form template has language tabs for i18n fields
- [ ] Form template uses `json_script` for initial values + `assembleI18nJson()` on submit
- [ ] Form template includes `image_selection_modals.html` partial + `image_selection.js`
- [ ] Create/Update views pass `languages` and `default_language` context
- [ ] Create/Update views handle gallery images in `form_valid()`
- [ ] Sidebar navigation added
- [ ] AI endpoints with generic FK sessions
- [ ] Dashboard stats added
- [ ] Admin registered
- [ ] Migrations created and applied
- [ ] `python manage.py check` passes

## Site Assistant Integration (Optional)

To make the app queryable and manageable via the site assistant chat, add tools following the `news_tools` / `properties_tools` pattern. All files are in `djangopress/site_assistant/`.

### 1. Tool Declarations (`tool_declarations.py`)

Add FunctionDeclarations for the app's tools. Typical tools for a content app:

- `list_<app>_items` — list/filter records
- `get_<app>_item` — get details by ID or name search
- `update_<app>_item` — update fields
- `list_<app>_template_tags` — expose available template tags for embedding in CMS pages

Group them in a `<APP>_TOOLS` list and register in `TOOL_CATEGORIES`:

```python
TOOL_CATEGORIES = {
    ...
    '<app>': <APP>_TOOLS,
}
```

Add `<app>` to the `REQUEST_TOOLS_DECLARATION` description strings.

### 2. Tool Implementations (`tools/<app>_tools.py`)

Create thin adapter functions with signature `(params, context) -> dict`. Use lazy imports inside each function so the module can be conditionally imported:

```python
def list_items(params, context):
    from myapp.models import MyModel
    # query, filter, serialize
    return {'success': True, 'items': [...], 'message': '...'}

<APP>_TOOLS = {
    'list_<app>_items': list_items,
    ...
}
```

See `tools/news_tools.py` and `tools/properties_tools.py` for complete examples.

### 3. Registry (`tools/__init__.py`)

Add a conditional import block:

```python
try:
    from .<app>_tools import <APP>_TOOLS
    ALL_TOOLS.update(<APP>_TOOLS)
except ImportError:
    <APP>_TOOLS = {}
```

Add `<APP>_TOOL_NAMES` to `ToolRegistry` and include in `get_available_tools()`.

### 4. Router (`router.py`)

Add the app as a category in `ROUTER_PROMPT`:

```
- <app>: <description of what the app manages>
```

### 5. Template Tags Tool

If the app has template tags for embedding content in CMS pages, expose them via a `list_<app>_template_tags` tool. This returns static metadata (tag name, load statement, usage example, description) so the assistant knows how to inject them using `refine_section`.
