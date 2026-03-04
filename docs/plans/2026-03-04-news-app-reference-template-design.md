# News App — Reference Template for Decoupled Apps

**Date:** 2026-03-04
**Status:** Approved
**Motivation:** Upgrade the news app into a fully-featured reference template that other decoupled apps (properties, athletes, products, events) can copy. Establish the "records on page" pattern, public views, AI generation, and inline editing for app content.

---

## Summary

The news app becomes the canonical example of a DjangoPress decoupled app. It demonstrates: public list/detail views with localized URLs, template tags for embedding records in CMS pages, per-app layout storage with AI generation, full AI workflow (generate, chat refine, bulk, image processing), inline editing via editor_v2, and a category model for organizing content.

All patterns are designed to be directly copiable to any app (properties, athletes, etc.) — only the model fields and business logic change.

---

## 1. Data Model

### NewsCategory (new)

```python
class NewsCategory(models.Model):
    name_i18n = JSONField(default=dict)         # {"pt": "Tecnologia", "en": "Technology"}
    slug_i18n = JSONField(default=dict)         # {"pt": "tecnologia", "en": "technology"}
    description_i18n = JSONField(default=dict)  # Optional
    order = PositiveIntegerField(default=0)
    is_active = BooleanField(default=True)
```

### NewsPost (upgraded)

```python
class NewsPost(models.Model):
    # Content — same pattern as Page
    title_i18n = JSONField(default=dict)
    slug_i18n = JSONField(default=dict)            # Replaces single slug — localized URLs
    excerpt_i18n = JSONField(default=dict)
    html_content_i18n = JSONField(default=dict)    # Full HTML per language, like Page
    meta_description_i18n = JSONField(default=dict)

    # Relations
    category = ForeignKey(NewsCategory, null=True, blank=True)
    featured_image = ImageField(upload_to='news/')
    gallery_images = M2M(SiteImage, through=NewsGalleryImage)

    # Publishing
    is_published = BooleanField(default=False)
    published_date = DateTimeField(null=True, blank=True)
    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)
```

**Removed fields:** `title`, `content`, `excerpt`, `meta_description` (old single-language), `slug` (single), `content_i18n` (replaced by `html_content_i18n`).

### NewsLayout (new — per-app layout storage)

```python
class NewsLayout(models.Model):
    key = SlugField(unique=True)                # 'list', 'detail', 'category'
    html_content_i18n = JSONField(default=dict) # Full HTML per language
```

Layout HTML uses Django template syntax with app-specific context variables (`posts`, `post`, `page_obj`, `category`, etc.) plus all site context (THEME, LOGO, CONTACT, etc.).

### NewsGalleryImage (unchanged)

Through model for ordered gallery relationship. No changes needed.

### I18n Mixin (new, in core)

```python
# core/mixins.py
class I18nModelMixin:
    def get_i18n_field(self, field_name, lang=None):
        lang = lang or get_language()
        default = SiteSettings.load().default_language
        data = getattr(self, f'{field_name}_i18n', {}) or {}
        return data.get(lang) or data.get(default) or ''
```

All app models inherit this — no more per-model getter methods with hardcoded `'pt'` defaults.

---

## 2. URL Structure & Public Views

### Registration

```python
# config/urls.py — news before core catch-all
urlpatterns += i18n_patterns(
    path('', include('news.urls')),
    path('', include('core.urls')),
    prefix_default_language=True,
)
```

### Public URLs (`news/urls.py`)

```python
app_name = 'news'
urlpatterns = [
    path('news/',                      NewsListView,     name='list'),
    path('news/<slug:slug>/',          NewsDetailView,   name='detail'),
    path('news/category/<slug:slug>/', NewsCategoryView, name='category'),
]
```

Fixed `news/` prefix in all languages. Slugs after the prefix are localized via `slug_i18n`.

### Rendering Pipeline

**NewsListView:**
1. Query published posts (paginated, optionally filtered by category)
2. Load `NewsLayout(key='list').html_content_i18n[lang]` (fallback to default_lang)
3. Resolve language-aware properties on each post (title, excerpt, url, category)
4. Render layout as Django Template with `posts`, `page_obj`, and full site context
5. Inject into `base.html` via `{% block content %}`

**NewsDetailView:**
1. Look up post by `slug_i18n[lang]`
2. Load `NewsLayout(key='detail').html_content_i18n[lang]`
3. Resolve post's `html_content_i18n[lang]` for the body content
4. Render layout with `post` context + full site context
5. Supports `?edit=v2` for inline editing

**NewsCategoryView:**
Same as list, filtered by category slug. Uses the `list` layout.

### Fallback

If no `NewsLayout` exists (fresh install), views use a minimal built-in default — enough to render posts unstyled. AI generation creates proper layouts.

---

## 3. Template Tags ("Records on Page" Pattern)

### `news/templatetags/news_tags.py`

```python
{% load news_tags %}

# Latest posts
{% latest_posts 3 as posts %}
{% for post in posts %}
    <img src="{{ post.featured_image.url }}">
    <h3>{{ post.title }}</h3>
    <p>{{ post.excerpt }}</p>
    <a href="{{ post.url }}">Read more</a>
{% endfor %}

# Posts by category
{% posts_by_category "technology" 4 as tech_posts %}

# All categories
{% news_categories as categories %}
```

### Internal Behavior

Each tag:
1. Calls `get_language()` for current language
2. Loads `SiteSettings.load().default_language` for fallback
3. Queries published posts ordered by date
4. Attaches resolved language-aware properties: `.title`, `.excerpt`, `.url`, `.category`
5. Returns via `{% as variable %}` assignment pattern

### AI Awareness

The system prompt for page generation includes available template tags:
```
Available template tags:
- {% load news_tags %}{% latest_posts N as posts %} — latest N published posts
- {% posts_by_category "slug" N as posts %} — posts in a category
Each post has: .title, .excerpt, .featured_image.url, .url, .published_date, .category
```

### Reusability

Any app copies this pattern — only the model, fields, and filters change:
- `{% load properties_tags %}{% featured_properties 6 as props %}`
- `{% load athletes_tags %}{% athletes_by_position "forward" 4 as players %}`

---

## 4. AI Integration (Full Workflow)

### Generate Post

**View:** `/backoffice/news/ai/generate/`
**API:** `/ai/api/generate-news-post/`

Same flow as page generation:
- User writes post brief (topic, key points, tone)
- Selects AI model, optional image placeholders
- AI generates `html_content_i18n[default_lang]`
- Second call generates `title_i18n` and `slug_i18n`
- User previews, sets category, saves

Reuses `ContentGenerationService` with news-specific prompts (article structure emphasis).

### Chat Refine

**View:** `/backoffice/news/ai/chat/refine/<post_id>/`

Same as page chat refine: conversational editing with session history, reference images, image placeholders. Post's `html_content_i18n[lang]` sent as context.

### Bulk Generate

**View:** `/backoffice/news/ai/bulk/`

User describes multiple posts. AI extracts structure, generates each one. Same flow as bulk pages.

### Process Images

**View:** `/backoffice/news/<post_id>/images/`

Identical to page image processing: scan `<img>` tags, AI suggest prompts, process with AI/library/Unsplash.

### Inline Editor Refinement

Staff visits `/en/news/my-article/?edit=v2` — section/element/page refinement works same as CMS pages. Editor JS sends `content_type` + `object_id` to identify what's being edited.

### RefinementSession Extension

```python
class RefinementSession(models.Model):
    page = ForeignKey(Page, null=True, blank=True, ...)  # Keep for backward compat
    content_type = ForeignKey(ContentType, null=True, blank=True)
    object_id = PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')
```

Generic FK lets any app (news, properties, athletes) have chat refinement sessions.

---

## 5. Backoffice Integration

### Views

**Existing (cleaned up):**
- `/backoffice/news/` — list with status/category filters, search
- `/backoffice/news/create/` — form with i18n JSON editor widgets
- `/backoffice/news/<id>/edit/` — edit form
- `/backoffice/news/<id>/delete/` — confirmation
- `/backoffice/news/<id>/gallery/` — gallery management
- `/backoffice/news/<id>/images/` — process images

**New:**
- `/backoffice/news/categories/` — category CRUD
- `/backoffice/news/ai/generate/` — generate post
- `/backoffice/news/ai/bulk/` — bulk generate
- `/backoffice/news/ai/chat/refine/<id>/` — chat refinement
- `/backoffice/news/layouts/` — layout management with AI edit

### Sidebar

```
Apps
  └─ News
       ├─ All Posts
       ├─ Categories
       └─ Layouts
```

### Dashboard

`DashboardView` provides:
- `total_news_posts`, `published_news_posts` — for stats cards
- `recent_news_posts` — latest 5 for activity feed

---

## 6. Editor v2 Extension

### How It Works

When staff visits a news detail page with `?edit=v2`:
- The page renders with `data-editable-type="news_post"` and `data-editable-id="42"` on the content container
- Editor JS detects these attributes and sends the right identifiers to API endpoints
- Save endpoints accept `content_type` + `object_id` alongside existing `page_id`
- Section/element/page refinement all work

### API Changes

Editor API views gain optional `content_type`/`object_id` parameters:
- If present → load the app model instance (NewsPost, etc.)
- If absent → load Page (backward compatible)
- Save changes to the model's `html_content_i18n[lang]`

---

## 7. Migration & Cleanup

### Data Migration

```python
for post in NewsPost.objects.all():
    # slug → slug_i18n
    if post.slug and not post.slug_i18n:
        post.slug_i18n = {lang: post.slug for lang in enabled_languages}

    # content_i18n → html_content_i18n (wrap plain text in basic HTML)
    if post.content_i18n and not post.html_content_i18n:
        for lang, text in post.content_i18n.items():
            post.html_content_i18n[lang] = f'<div class="prose prose-lg">{text}</div>'

    post.save()
```

### Migration Order

1. Add new fields (`slug_i18n`, `html_content_i18n`) + new models (`NewsCategory`, `NewsLayout`)
2. Run data migration (copy existing data to new fields)
3. Remove old fields (`slug`, `title`, `content`, `excerpt`, `meta_description`, `content_i18n`)
4. Add `category` FK to NewsPost

### What Gets Removed

- Old single-language fields on NewsPost
- `content_i18n` field (replaced by `html_content_i18n`)
- Old form using single-language fields
- Per-model getter methods (`get_title(lang='pt')`) — replaced by `I18nModelMixin`

---

## 8. Reusability — How Other Apps Copy This

When building a new app (e.g. properties for real estate), the developer:

1. **Copies the model pattern:** `_i18n` JSON fields, `slug_i18n`, `html_content_i18n`, `I18nModelMixin`, category model
2. **Copies `urls.py`:** Public list/detail/category views registered in `i18n_patterns` before `core.urls`
3. **Copies template tags:** `{% load properties_tags %}{% featured_properties 6 as props %}` — same machinery, different model
4. **Copies `AppLayout` model:** `PropertyLayout(key='list')`, `PropertyLayout(key='detail')` — AI-generated layouts
5. **Copies AI endpoints:** Generate, chat refine, bulk, process images — same `ContentGenerationService`, different prompts
6. **Copies backoffice views:** List, create, edit, delete, gallery, categories, layouts, AI tools
7. **Copies editor integration:** `data-editable-type="property"` + generic FK on RefinementSession

The news app IS the blueprint. Every other app follows the exact same structure.
