# News Form Improvements — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rewrite the news form template with language tabs for i18n fields and modal-based image selection (reusing existing partials).

**Architecture:** Template + JS rewrite of `news_form.html`. Views get a small context update to pass `languages`. No model or form class changes. The form still submits the same JSON fields.

**Tech Stack:** Django templates, Tailwind CSS, vanilla JS, existing `image_selection_modals.html` partial + `image_selection.js`

---

### Task 1: Update views to pass language context

**Files:**
- Modify: `src/djangopress/news/views.py:73-125`

**Step 1: Add languages to NewsCreateView and NewsUpdateView context**

Both views need `languages` and `default_language` in context so the template can build tabs.

In `NewsCreateView.get_context_data()` (line 82), add after `context['submit_text']`:

```python
def get_context_data(self, **kwargs):
    context = super().get_context_data(**kwargs)
    context['form_title'] = 'Create New News Post'
    context['submit_text'] = 'Create Post'
    from djangopress.core.models import SiteSettings
    site_settings = SiteSettings.objects.first()
    if site_settings:
        context['languages'] = site_settings.get_enabled_languages()
        context['default_language'] = site_settings.get_default_language()
    else:
        context['languages'] = [('pt', 'Portuguese')]
        context['default_language'] = 'pt'
    return context
```

Same pattern for `NewsUpdateView.get_context_data()` (line 121).

**Step 2: Verify**

Run: `cd /path/to/child-project && python manage.py shell -c "from djangopress.news.views import NewsCreateView; print('OK')"`

**Step 3: Commit**

```bash
git add src/djangopress/news/views.py
git commit -m "feat: pass language context to news form views"
```

---

### Task 2: Rewrite news_form.html template

**Files:**
- Modify: `src/djangopress/backoffice/templates/backoffice/news_form.html`

**Step 1: Rewrite the template**

The new template structure:

```
{% extends 'backoffice/base.html' %}
{% block title %}{{ form_title }}{% endblock %}

{% block content %}
<div class="max-w-4xl mx-auto">
    <!-- Header -->
    <div class="mb-6">
        <h2 class="text-3xl font-bold text-gray-900">{{ form_title }}</h2>
        <p class="text-gray-600 mt-1">...</p>
    </div>

    <div class="bg-white rounded-lg shadow p-6">
        <form method="post" enctype="multipart/form-data" id="news-form" class="space-y-6">
            {% csrf_token %}

            <!-- Non-field errors -->
            ...

            <!-- Language Tabs -->
            <div class="border-b border-gray-200">
                <nav class="flex space-x-4" id="lang-tabs">
                    {% for code, name in languages %}
                    <button type="button"
                            class="lang-tab px-4 py-2 text-sm font-medium rounded-t-lg transition-colors
                                   {% if code == default_language %}border-b-2 border-blue-500 text-blue-600{% else %}text-gray-500 hover:text-gray-700{% endif %}"
                            data-lang="{{ code }}"
                            onclick="switchLanguageTab('{{ code }}')">
                        {{ name }}
                    </button>
                    {% endfor %}
                </nav>
            </div>

            <!-- Hidden JSON fields (populated on submit) -->
            <input type="hidden" name="title_i18n" id="title_i18n_json">
            <input type="hidden" name="slug_i18n" id="slug_i18n_json">
            <input type="hidden" name="excerpt_i18n" id="excerpt_i18n_json">
            <input type="hidden" name="html_content_i18n" id="html_content_i18n_json">
            <input type="hidden" name="meta_description_i18n" id="meta_description_i18n_json">

            <!-- Per-language i18n fields (title, slug, excerpt, html_content) -->
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
            </div>
            {% endfor %}

            <!-- Category (always visible) -->
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
                <div id="featured-image-display">
                    <!-- JS populates this on load -->
                </div>
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
                        <p class="mt-1 text-xs text-gray-500">{{ form.published_date.help_text }}</p>
                    </div>
                </div>
            </div>

            <!-- Gallery Images (modal-based) -->
            <div class="border-t pt-6">
                <h3 class="text-lg font-semibold text-gray-900 mb-4">Gallery Images</h3>
                <p class="text-sm text-gray-600 mb-4">Select images from your media library</p>

                <!-- Hidden checkboxes container -->
                <div id="gallery-checkboxes-container" class="hidden">
                    {% for image in form.gallery_images.field.queryset %}
                    <input type="checkbox" name="gallery_images" value="{{ image.id }}"
                           {% if image in form.gallery_images.initial %}checked{% endif %}>
                    {% endfor %}
                </div>

                <!-- Visual display of selected gallery images -->
                <div id="selected-gallery-display">
                    <!-- JS populates on load -->
                </div>

                <div class="mt-3 flex space-x-3">
                    <button type="button" onclick="openGalleryModal()" class="px-4 py-2 text-sm font-medium text-green-600 bg-green-50 rounded-lg hover:bg-green-100 transition-colors">
                        Select from Library
                    </button>
                    <button type="button" onclick="openUploadModal()" class="px-4 py-2 text-sm font-medium text-gray-600 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors">
                        Upload New
                    </button>
                </div>
            </div>

            <!-- SEO Settings (per-language, inside lang panels already covered above) -->
            <!-- Wait — meta_description needs to be in the lang panels too -->
            <!-- Add meta_description to each lang-panel above -->

            <!-- Form Actions -->
            <div class="flex items-center justify-between pt-6 border-t border-gray-200">
                <a href="{% url 'backoffice:news_list' %}" class="px-4 py-2 text-sm font-medium text-gray-700 hover:text-gray-900">Cancel</a>
                <button type="submit" class="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors">{{ submit_text }}</button>
            </div>
        </form>
    </div>
</div>

<!-- Include image selection modals -->
{% include 'backoffice/partials/image_selection_modals.html' with form=form %}

<!-- Include image selection JS -->
<script src="{% static 'backoffice/js/image_selection.js' %}"></script>
{% endblock %}
```

Note: `meta_description_i18n` should be included inside each `lang-panel` div (after html_content), inside a "SEO" sub-header within the language panel.

**Step 2: Add language tab JS**

At the bottom of the template, add the `<script>` block for language tab management:

```javascript
const I18N_FIELDS = ['title_i18n', 'slug_i18n', 'excerpt_i18n', 'html_content_i18n', 'meta_description_i18n'];
const LANGUAGES = [{% for code, name in languages %}'{{ code }}'{% if not forloop.last %}, {% endif %}{% endfor %}];
const DEFAULT_LANG = '{{ default_language }}';

// Parse existing JSON values and populate per-language inputs
function initI18nFields() {
    I18N_FIELDS.forEach(fieldName => {
        const jsonInput = document.getElementById(fieldName + '_json');
        // Read initial value from a data attribute or inline JSON
        let data = {};
        try {
            const raw = document.getElementById(fieldName + '_initial').value;
            if (raw) data = JSON.parse(raw);
        } catch (e) {}

        // Populate per-language inputs
        document.querySelectorAll(`.i18n-field[data-field="${fieldName}"]`).forEach(input => {
            const lang = input.dataset.lang;
            if (data[lang] !== undefined) {
                input.value = data[lang];
            }
        });
    });
}

// Reassemble JSON from per-language inputs before submit
function assembleI18nJson() {
    I18N_FIELDS.forEach(fieldName => {
        const data = {};
        document.querySelectorAll(`.i18n-field[data-field="${fieldName}"]`).forEach(input => {
            const lang = input.dataset.lang;
            const val = input.tagName === 'TEXTAREA' ? input.value : input.value;
            if (val) data[lang] = val;
        });
        document.getElementById(fieldName + '_json').value = JSON.stringify(data);
    });
}

// Switch visible language panel
function switchLanguageTab(lang) {
    // Update tab styles
    document.querySelectorAll('.lang-tab').forEach(tab => {
        if (tab.dataset.lang === lang) {
            tab.classList.add('border-b-2', 'border-blue-500', 'text-blue-600');
            tab.classList.remove('text-gray-500');
        } else {
            tab.classList.remove('border-b-2', 'border-blue-500', 'text-blue-600');
            tab.classList.add('text-gray-500');
        }
    });

    // Show/hide panels
    document.querySelectorAll('.lang-panel').forEach(panel => {
        if (panel.dataset.lang === lang) {
            panel.classList.remove('hidden');
        } else {
            panel.classList.add('hidden');
        }
    });
}

// Initialize on load
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

    // Intercept form submit to assemble JSON
    document.getElementById('news-form').addEventListener('submit', function(e) {
        assembleI18nJson();
    });
});
```

The template also needs hidden inputs to carry the initial JSON values:

```html
<!-- Hidden initial values (for JS to parse on load) -->
<input type="hidden" id="title_i18n_initial" value="{{ form.title_i18n.value|default_if_none:'' }}">
<input type="hidden" id="slug_i18n_initial" value="{{ form.slug_i18n.value|default_if_none:'' }}">
<input type="hidden" id="excerpt_i18n_initial" value="{{ form.excerpt_i18n.value|default_if_none:'' }}">
<input type="hidden" id="html_content_i18n_initial" value="{{ form.html_content_i18n.value|default_if_none:'' }}">
<input type="hidden" id="meta_description_i18n_initial" value="{{ form.meta_description_i18n.value|default_if_none:'' }}">
```

**Step 3: Verify manually**

Start dev server, navigate to `/backoffice/news/create/` and `/backoffice/news/<pk>/edit/`:
- Language tabs switch all i18n fields
- Existing data loads into correct language inputs
- Form submits correctly (JSON assembled)
- Featured image modal opens, selection updates preview
- Gallery modal opens, selection updates display grid
- Upload modals work (drag-and-drop + file picker)

**Step 4: Commit**

```bash
git add src/djangopress/backoffice/templates/backoffice/news_form.html
git commit -m "feat: news form with language tabs and modal-based image selection"
```

---

### Task 3: Test edge cases and polish

**Step 1: Test with single language site**

Ensure form works when only one language is configured (tabs should still show but only one tab).

**Step 2: Test create vs edit**

- Create: all fields empty, JSON assembles correctly
- Edit: existing JSON values parse into correct language inputs

**Step 3: Test form validation**

Submit with missing required fields — errors should display correctly and per-language values should persist (not lost on reload).

For validation persistence, the hidden `_initial` inputs need to use the POST data on validation failure. Django's form re-renders with submitted values in `form.field.value`, so this should work automatically.

**Step 4: Final commit**

```bash
git add -A
git commit -m "fix: news form edge cases and polish"
```
