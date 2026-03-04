# News App — Reference Template Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade the news app into a fully-featured reference template that other decoupled apps can copy, with public views, template tags, AI generation, inline editing, and categories.

**Architecture:** The news app becomes a self-contained decoupled app with its own `urls.py`, public views, template tags, and layout storage. It follows the same `html_content_i18n` pattern as the Page model (per-language HTML). A shared `I18nModelMixin` in core eliminates hardcoded language defaults. The AI pipeline is extended with news-specific endpoints that reuse `ContentGenerationService`.

**Tech Stack:** Django 6.0, Tailwind CSS (CDN), Alpine.js, BeautifulSoup, existing AI pipeline (Gemini/OpenAI/Anthropic)

**Design Doc:** `docs/plans/2026-03-04-news-app-reference-template-design.md`

---

## Task 1: I18nModelMixin in core

Create a shared mixin that all app models will use instead of per-model getter methods with hardcoded `'pt'` defaults.

**Files:**
- Create: `core/mixins.py`
- Test: manual — used by subsequent tasks

**Step 1: Create the mixin**

```python
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
```

**Step 2: Commit**

```bash
git add core/mixins.py
git commit -m "feat: add I18nModelMixin for shared language-aware field resolution"
```

---

## Task 2: NewsCategory model

Add the category model for organizing posts.

**Files:**
- Modify: `news/models.py`
- Create: migration via `makemigrations`

**Step 1: Add NewsCategory model to news/models.py**

Add before the `NewsPost` class (after imports):

```python
from core.mixins import I18nModelMixin


class NewsCategory(I18nModelMixin, models.Model):
    """Category for organizing news posts."""
    name_i18n = models.JSONField(
        'Name (All Languages)',
        default=dict,
        blank=True,
        help_text='{"pt": "Tecnologia", "en": "Technology"}'
    )
    slug_i18n = models.JSONField(
        'Slug (All Languages)',
        default=dict,
        blank=True,
        help_text='{"pt": "tecnologia", "en": "technology"}'
    )
    description_i18n = models.JSONField(
        'Description (All Languages)',
        default=dict,
        blank=True,
    )
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['order', 'pk']
        verbose_name = _("News Category")
        verbose_name_plural = _("News Categories")

    def __str__(self):
        return self.get_i18n_field('name') or f'Category #{self.pk}'

    def get_absolute_url(self, lang=None):
        from django.urls import reverse
        from django.utils.translation import get_language
        lang = lang or get_language()
        slug = (self.slug_i18n or {}).get(lang, '')
        if not slug:
            from core.models import SiteSettings
            settings = SiteSettings.load()
            default = settings.get_default_language() if settings else 'pt'
            slug = (self.slug_i18n or {}).get(default, '')
        return reverse('news:category', kwargs={'slug': slug}) if slug else '#'

    def save(self, *args, **kwargs):
        # Auto-generate slugs from name_i18n if empty
        if self.name_i18n and not self.slug_i18n:
            from django.utils.text import slugify
            self.slug_i18n = {
                lang: slugify(name) for lang, name in self.name_i18n.items() if name
            }
        super().save(*args, **kwargs)
```

**Step 2: Create and run migration**

```bash
python manage.py makemigrations news --name add_news_category
python manage.py migrate
```

**Step 3: Commit**

```bash
git add news/models.py news/migrations/
git commit -m "feat: add NewsCategory model with i18n fields"
```

---

## Task 3: Upgrade NewsPost model

Replace old fields, add `slug_i18n`, `html_content_i18n`, category FK, and use `I18nModelMixin`.

**Files:**
- Modify: `news/models.py`
- Create: migrations (schema + data + removal)

**Step 1: Add new fields to NewsPost**

In `news/models.py`, update the `NewsPost` class:

1. Add `I18nModelMixin` to class bases
2. Add `slug_i18n` field (after `meta_description_i18n`)
3. Add `html_content_i18n` field (after `slug_i18n`)
4. Add `category` FK (after `html_content_i18n`)
5. Keep old fields for now (migration removes them later)

```python
class NewsPost(I18nModelMixin, models.Model):
    """Model for news posts"""

    # NEW: JSON Translation Fields
    title_i18n = models.JSONField(
        'Title (All Languages)',
        default=dict,
        blank=True,
        help_text='{"pt": "Título PT", "en": "Title EN"}'
    )
    slug_i18n = models.JSONField(
        'Slug (All Languages)',
        default=dict,
        blank=True,
        help_text='{"pt": "meu-artigo", "en": "my-article"}'
    )
    excerpt_i18n = models.JSONField(
        'Excerpt (All Languages)',
        default=dict,
        blank=True,
        help_text='{"pt": "Resumo PT", "en": "Excerpt EN"}'
    )
    html_content_i18n = models.JSONField(
        'HTML Content (All Languages)',
        default=dict,
        blank=True,
        help_text='Per-language HTML, same as Page model'
    )
    meta_description_i18n = models.JSONField(
        'Meta Description (All Languages)',
        default=dict,
        blank=True,
        help_text='{"pt": "Meta descrição PT", "en": "Meta description EN"}'
    )

    # Relations
    category = models.ForeignKey(
        NewsCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='posts',
        verbose_name=_("Category")
    )
    featured_image = models.ImageField(_("Featured Image"), upload_to='news/', blank=True, null=True)
    gallery_images = models.ManyToManyField(
        SiteImage,
        through='NewsGalleryImage',
        related_name='news_posts',
        blank=True,
        verbose_name=_("Gallery Images")
    )

    # Publishing
    is_published = models.BooleanField(_("Published"), default=False)
    published_date = models.DateTimeField(_("Published Date"), blank=True, null=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    class Meta:
        ordering = ['-published_date', '-created_at']
        verbose_name = _("News Post")
        verbose_name_plural = _("News Posts")

    def __str__(self):
        return self.get_i18n_field('title') or f'News Post #{self.pk}'

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
        return reverse('news:detail', kwargs={'slug': slug}) if slug else '#'

    def save(self, *args, **kwargs):
        # Auto-generate slugs from title_i18n if slug_i18n is empty
        if self.title_i18n and not self.slug_i18n:
            self.slug_i18n = {
                lang: slugify(title) for lang, title in self.title_i18n.items() if title
            }
        super().save(*args, **kwargs)
```

**Step 2: Create schema migration (add new fields)**

```bash
python manage.py makemigrations news --name add_slug_i18n_html_content_i18n_category
python manage.py migrate
```

**Step 3: Create data migration**

```bash
python manage.py makemigrations news --empty --name migrate_to_new_fields
```

Edit the migration:

```python
from django.db import migrations


def migrate_data_forward(apps, schema_editor):
    NewsPost = apps.get_model('news', 'NewsPost')
    SiteSettings = apps.get_model('core', 'SiteSettings')

    # Get enabled languages
    try:
        settings = SiteSettings.objects.first()
        if settings and settings.languages:
            enabled_langs = [l['code'] for l in settings.languages if l.get('enabled')]
        else:
            enabled_langs = ['pt', 'en']
    except Exception:
        enabled_langs = ['pt', 'en']

    for post in NewsPost.objects.all():
        # slug → slug_i18n (copy single slug to all enabled languages)
        if post.slug and not post.slug_i18n:
            post.slug_i18n = {lang: post.slug for lang in enabled_langs}

        # content_i18n → html_content_i18n (wrap text in basic HTML)
        if post.content_i18n and not post.html_content_i18n:
            html_i18n = {}
            for lang, text in post.content_i18n.items():
                if text:
                    html_i18n[lang] = f'<section data-section="post-body" id="post-body"><div class="max-w-4xl mx-auto px-4 py-12 prose prose-lg">{text}</div></section>'
            if html_i18n:
                post.html_content_i18n = html_i18n

        post.save()


class Migration(migrations.Migration):
    dependencies = [
        ('news', 'PREVIOUS_MIGRATION_NAME'),  # Update to actual name
        ('core', '__latest__'),
    ]

    operations = [
        migrations.RunPython(migrate_data_forward, migrations.RunPython.noop),
    ]
```

**Step 4: Run data migration**

```bash
python manage.py migrate
```

**Step 5: Remove old fields migration**

```bash
python manage.py makemigrations news --name remove_old_fields
```

This should auto-detect the removal of `title`, `content`, `excerpt`, `meta_description`, `slug`, `content_i18n` from the model. If not, manually create the migration to remove these fields.

```bash
python manage.py migrate
```

**Step 6: Commit**

```bash
git add news/models.py news/migrations/
git commit -m "feat: upgrade NewsPost with slug_i18n, html_content_i18n, category FK

Data migration converts existing slug and content_i18n to new fields.
Old single-language fields removed."
```

---

## Task 4: NewsLayout model

Add the layout model for storing AI-generated list/detail page templates.

**Files:**
- Modify: `news/models.py`
- Create: migration

**Step 1: Add NewsLayout model**

Add after `NewsCategory` in `news/models.py`:

```python
class NewsLayout(models.Model):
    """Layout templates for news public pages (list, detail, category).

    Stores AI-generated HTML per language that wraps dynamic data.
    The HTML uses Django template syntax with app-specific context variables.
    """
    key = models.SlugField(
        max_length=50,
        unique=True,
        help_text='Layout identifier: list, detail, category'
    )
    html_content_i18n = models.JSONField(
        'HTML Layout (All Languages)',
        default=dict,
        blank=True,
        help_text='Per-language HTML layout with Django template syntax'
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("News Layout")
        verbose_name_plural = _("News Layouts")

    def __str__(self):
        return f"NewsLayout: {self.key}"
```

**Step 2: Create and run migration**

```bash
python manage.py makemigrations news --name add_news_layout
python manage.py migrate
```

**Step 3: Commit**

```bash
git add news/models.py news/migrations/
git commit -m "feat: add NewsLayout model for AI-generated list/detail page templates"
```

---

## Task 5: Template tags ("records on page" pattern)

Create the template tags that let CMS pages embed news posts.

**Files:**
- Create: `news/templatetags/__init__.py`
- Create: `news/templatetags/news_tags.py`

**Step 1: Create the template tags module**

```bash
mkdir -p news/templatetags
touch news/templatetags/__init__.py
```

**Step 2: Create news_tags.py**

```python
# news/templatetags/news_tags.py
from django import template
from django.utils.translation import get_language
from core.models import SiteSettings

register = template.Library()


def _resolve_post_fields(post, lang, default_lang):
    """Attach language-resolved properties to a post for template use."""
    post._resolved_title = (post.title_i18n or {}).get(lang) or (post.title_i18n or {}).get(default_lang) or ''
    post._resolved_excerpt = (post.excerpt_i18n or {}).get(lang) or (post.excerpt_i18n or {}).get(default_lang) or ''
    post._resolved_slug = (post.slug_i18n or {}).get(lang) or (post.slug_i18n or {}).get(default_lang) or ''
    return post


class LatestPostsNode(template.Node):
    def __init__(self, count, var_name):
        self.count = count
        self.var_name = var_name

    def render(self, context):
        from news.models import NewsPost
        lang = get_language()
        settings = SiteSettings.load()
        default_lang = settings.get_default_language() if settings else 'pt'

        posts = list(NewsPost.objects.filter(is_published=True)[:self.count])
        for post in posts:
            _resolve_post_fields(post, lang, default_lang)
            # Convenience aliases for template access
            post.title = post._resolved_title
            post.excerpt = post._resolved_excerpt
            post.url = post.get_absolute_url(lang)
            if post.category:
                post.category_name = post.category.get_i18n_field('name', lang)

        context[self.var_name] = posts
        return ''


@register.tag('latest_posts')
def do_latest_posts(parser, token):
    """Get latest published news posts.

    Usage: {% latest_posts 3 as posts %}
    """
    bits = token.split_contents()
    if len(bits) != 4 or bits[2] != 'as':
        raise template.TemplateSyntaxError(
            "Usage: {% latest_posts <count> as <variable> %}"
        )
    count = int(bits[1])
    var_name = bits[3]
    return LatestPostsNode(count, var_name)


class PostsByCategoryNode(template.Node):
    def __init__(self, category_slug, count, var_name):
        self.category_slug = category_slug
        self.count = count
        self.var_name = var_name

    def render(self, context):
        from news.models import NewsPost, NewsCategory
        lang = get_language()
        settings = SiteSettings.load()
        default_lang = settings.get_default_language() if settings else 'pt'

        # Find category by slug in any language
        slug = self.category_slug
        categories = NewsCategory.objects.filter(is_active=True)
        category = None
        for cat in categories:
            slugs = cat.slug_i18n or {}
            if slug in slugs.values():
                category = cat
                break

        if not category:
            context[self.var_name] = []
            return ''

        posts = list(
            NewsPost.objects.filter(is_published=True, category=category)[:self.count]
        )
        for post in posts:
            _resolve_post_fields(post, lang, default_lang)
            post.title = post._resolved_title
            post.excerpt = post._resolved_excerpt
            post.url = post.get_absolute_url(lang)

        context[self.var_name] = posts
        return ''


@register.tag('posts_by_category')
def do_posts_by_category(parser, token):
    """Get posts filtered by category slug.

    Usage: {% posts_by_category "technology" 4 as tech_posts %}
    """
    bits = token.split_contents()
    if len(bits) != 5 or bits[3] != 'as':
        raise template.TemplateSyntaxError(
            'Usage: {% posts_by_category "slug" <count> as <variable> %}'
        )
    category_slug = bits[1].strip('"').strip("'")
    count = int(bits[2])
    var_name = bits[4]
    return PostsByCategoryNode(category_slug, count, var_name)


class NewsCategoriesNode(template.Node):
    def __init__(self, var_name):
        self.var_name = var_name

    def render(self, context):
        from news.models import NewsCategory
        lang = get_language()
        settings = SiteSettings.load()
        default_lang = settings.get_default_language() if settings else 'pt'

        categories = list(NewsCategory.objects.filter(is_active=True))
        for cat in categories:
            cat.name = cat.get_i18n_field('name', lang)
            cat.url = cat.get_absolute_url(lang)

        context[self.var_name] = categories
        return ''


@register.tag('news_categories')
def do_news_categories(parser, token):
    """Get all active news categories.

    Usage: {% news_categories as categories %}
    """
    bits = token.split_contents()
    if len(bits) != 3 or bits[1] != 'as':
        raise template.TemplateSyntaxError(
            "Usage: {% news_categories as <variable> %}"
        )
    var_name = bits[2]
    return NewsCategoriesNode(var_name)
```

**Step 3: Commit**

```bash
git add news/templatetags/
git commit -m "feat: add news template tags for records-on-page pattern

Tags: latest_posts, posts_by_category, news_categories.
Language-aware with fallback to default language."
```

---

## Task 6: Public views and URL routing

Create the public-facing news views and register them in `i18n_patterns`.

**Files:**
- Create: `news/urls.py`
- Create: `news/public_views.py`
- Modify: `config/urls.py` (line 49-52 — add news before core catch-all)

**Step 1: Create news/public_views.py**

```python
"""Public-facing news views."""

from django.views.generic import TemplateView
from django.http import Http404
from django.template import Template, RequestContext
from django.utils.translation import get_language
from core.models import SiteSettings


# Minimal fallback layouts when no NewsLayout exists
FALLBACK_LIST = """
<section data-section="news-list" id="news-list">
<div class="max-w-7xl mx-auto px-4 py-16">
  <h1 class="text-3xl font-bold mb-8">News</h1>
  <div class="grid md:grid-cols-3 gap-8">
    {% for post in posts %}
    <article class="bg-white rounded-lg shadow p-6">
      {% if post.featured_image %}<img src="{{ post.featured_image.url }}" alt="{{ post.title }}" class="w-full h-48 object-cover rounded mb-4">{% endif %}
      <h2 class="text-xl font-semibold mb-2"><a href="{{ post.url }}">{{ post.title }}</a></h2>
      <p class="text-gray-600">{{ post.excerpt }}</p>
    </article>
    {% endfor %}
  </div>
  {% if page_obj.has_other_pages %}
  <nav class="flex justify-center mt-12 gap-4">
    {% if page_obj.has_previous %}<a href="?page={{ page_obj.previous_page_number }}" class="px-4 py-2 bg-gray-200 rounded">&larr; Previous</a>{% endif %}
    {% if page_obj.has_next %}<a href="?page={{ page_obj.next_page_number }}" class="px-4 py-2 bg-gray-200 rounded">Next &rarr;</a>{% endif %}
  </nav>
  {% endif %}
</div>
</section>
"""

FALLBACK_DETAIL = """
<section data-section="post-header" id="post-header">
<div class="max-w-4xl mx-auto px-4 py-16">
  {% if post.featured_image %}<img src="{{ post.featured_image.url }}" alt="{{ post.title }}" class="w-full h-64 object-cover rounded-lg mb-8">{% endif %}
  <h1 class="text-4xl font-bold mb-4">{{ post.title }}</h1>
  {% if post.published_date %}<time class="text-gray-500">{{ post.published_date|date:"F j, Y" }}</time>{% endif %}
</div>
</section>
<section data-section="post-content" id="post-content">
<div class="max-w-4xl mx-auto px-4 pb-16 prose prose-lg">
  {{ post.html_content }}
</div>
</section>
"""


def _get_lang_and_default():
    lang = get_language()
    settings = SiteSettings.load()
    default_lang = settings.get_default_language() if settings else 'pt'
    return lang, default_lang


def _get_layout_html(key, lang, default_lang):
    """Load layout HTML from NewsLayout, with fallback."""
    from news.models import NewsLayout
    try:
        layout = NewsLayout.objects.get(key=key)
        html_i18n = layout.html_content_i18n or {}
        html = html_i18n.get(lang) or html_i18n.get(default_lang) or ''
        if html:
            return html
    except NewsLayout.DoesNotExist:
        pass

    # Fallback
    if key == 'detail':
        return FALLBACK_DETAIL
    return FALLBACK_LIST


def _resolve_post(post, lang, default_lang):
    """Attach language-resolved convenience properties to a post."""
    post.title = (post.title_i18n or {}).get(lang) or (post.title_i18n or {}).get(default_lang) or ''
    post.excerpt = (post.excerpt_i18n or {}).get(lang) or (post.excerpt_i18n or {}).get(default_lang) or ''

    html_i18n = post.html_content_i18n or {}
    post.html_content = html_i18n.get(lang) or html_i18n.get(default_lang) or ''

    post.url = post.get_absolute_url(lang)

    if post.category:
        post.category_name = post.category.get_i18n_field('name', lang)
        post.category_url = post.category.get_absolute_url(lang)
    return post


class NewsListView(TemplateView):
    template_name = 'news/base_news.html'
    paginate_by = 12

    def get_context_data(self, **kwargs):
        from news.models import NewsPost
        from django.core.paginator import Paginator

        context = super().get_context_data(**kwargs)
        lang, default_lang = _get_lang_and_default()

        posts_qs = NewsPost.objects.filter(is_published=True).select_related('category')
        paginator = Paginator(posts_qs, self.paginate_by)
        page_number = self.request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        posts = []
        for post in page_obj:
            _resolve_post(post, lang, default_lang)
            posts.append(post)

        layout_html = _get_layout_html('list', lang, default_lang)

        # Render the layout as a Django template
        template = Template(layout_html)
        render_context = RequestContext(self.request, {
            'posts': posts,
            'page_obj': page_obj,
            'paginator': paginator,
            **context,
        })
        context['page_content'] = template.render(render_context)
        context['page_title'] = 'News'
        return context


class NewsDetailView(TemplateView):
    template_name = 'news/base_news.html'

    def get_context_data(self, **kwargs):
        from news.models import NewsPost

        context = super().get_context_data(**kwargs)
        lang, default_lang = _get_lang_and_default()
        slug = self.kwargs['slug']

        # Find post by slug_i18n
        post = None
        for p in NewsPost.objects.filter(is_published=True).select_related('category'):
            slugs = p.slug_i18n or {}
            if slugs.get(lang) == slug or slugs.get(default_lang) == slug or slug in slugs.values():
                post = p
                break

        if not post:
            raise Http404("News post not found")

        _resolve_post(post, lang, default_lang)
        layout_html = _get_layout_html('detail', lang, default_lang)

        template = Template(layout_html)
        render_context = RequestContext(self.request, {
            'post': post,
            'news_post': post,  # For editor_v2 to identify the object
            **context,
        })
        context['page_content'] = template.render(render_context)
        context['page_title'] = post.title
        context['news_post'] = post  # For editor/toolbar
        return context


class NewsCategoryView(TemplateView):
    template_name = 'news/base_news.html'
    paginate_by = 12

    def get_context_data(self, **kwargs):
        from news.models import NewsPost, NewsCategory
        from django.core.paginator import Paginator

        context = super().get_context_data(**kwargs)
        lang, default_lang = _get_lang_and_default()
        slug = self.kwargs['slug']

        # Find category by slug_i18n
        category = None
        for cat in NewsCategory.objects.filter(is_active=True):
            slugs = cat.slug_i18n or {}
            if slugs.get(lang) == slug or slugs.get(default_lang) == slug or slug in slugs.values():
                category = cat
                break

        if not category:
            raise Http404("Category not found")

        posts_qs = NewsPost.objects.filter(
            is_published=True, category=category
        ).select_related('category')
        paginator = Paginator(posts_qs, self.paginate_by)
        page_number = self.request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        posts = []
        for post in page_obj:
            _resolve_post(post, lang, default_lang)
            posts.append(post)

        layout_html = _get_layout_html('list', lang, default_lang)

        template = Template(layout_html)
        render_context = RequestContext(self.request, {
            'posts': posts,
            'page_obj': page_obj,
            'paginator': paginator,
            'category': category,
            'category_name': category.get_i18n_field('name', lang),
            **context,
        })
        context['page_content'] = template.render(render_context)
        context['page_title'] = category.get_i18n_field('name', lang)
        return context
```

**Step 2: Create the base template for news pages**

Create `news/templates/news/base_news.html`:

```html
{% extends "base.html" %}

{% block content %}
{{ page_content }}
{% endblock %}
```

This injects the rendered layout HTML into the site's master layout (with header/footer).

**Step 3: Create news/urls.py**

```python
from django.urls import path
from news.public_views import NewsListView, NewsDetailView, NewsCategoryView

app_name = 'news'

urlpatterns = [
    path('news/', NewsListView.as_view(), name='list'),
    path('news/category/<slug:slug>/', NewsCategoryView.as_view(), name='category'),
    path('news/<slug:slug>/', NewsDetailView.as_view(), name='detail'),
]
```

Note: category URL comes before detail to avoid slug conflicts.

**Step 4: Register in config/urls.py**

Modify lines 49-52 to add news before core catch-all:

```python
urlpatterns += i18n_patterns(
    path('', include('news.urls')),    # News public routes (before catch-all)
    path('', include('core.urls')),    # Core page catch-all (must be last)
    prefix_default_language=True,
)
```

**Step 5: Verify the server starts**

```bash
python manage.py check
python manage.py runserver 8000
```

Visit `/en/news/` — should show the fallback list layout (empty if no posts).

**Step 6: Commit**

```bash
git add news/public_views.py news/urls.py news/templates/ config/urls.py
git commit -m "feat: add public news views with layout rendering and i18n slug lookup

List, detail, and category views with NewsLayout support.
Fallback to minimal built-in layouts when no NewsLayout exists.
Registered in i18n_patterns before core catch-all."
```

---

## Task 7: Update backoffice — forms, views, sidebar, dashboard

Update the backoffice to work with the new model fields and add category/layout management.

**Files:**
- Modify: `news/forms.py`
- Modify: `news/views.py`
- Modify: `news/admin.py`
- Modify: `backoffice/urls.py` (lines 35-40)
- Modify: `backoffice/views.py` (DashboardView, lines 150-185)
- Modify: `backoffice/templates/backoffice/includes/sidebar.html` (lines 79-89)
- Create: `backoffice/templates/backoffice/news_categories.html`
- Create: `backoffice/templates/backoffice/news_layouts.html`
- Modify: existing news templates to use new i18n fields

**Step 1: Update news/forms.py**

Replace the form to use the new i18n fields:

```python
from django import forms
from news.models import NewsPost, NewsCategory
from core.models import SiteImage


class NewsPostForm(forms.ModelForm):
    gallery_images = forms.ModelMultipleChoiceField(
        queryset=SiteImage.objects.filter(is_active=True),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = NewsPost
        fields = [
            'title_i18n', 'slug_i18n', 'featured_image', 'excerpt_i18n',
            'html_content_i18n', 'category', 'is_published', 'published_date',
            'meta_description_i18n',
        ]
        widgets = {
            'title_i18n': forms.Textarea(attrs={
                'rows': 2, 'class': 'w-full px-3 py-2 border border-gray-300 rounded-md text-sm font-mono',
                'placeholder': '{"pt": "Título", "en": "Title"}'
            }),
            'slug_i18n': forms.Textarea(attrs={
                'rows': 2, 'class': 'w-full px-3 py-2 border border-gray-300 rounded-md text-sm font-mono',
                'placeholder': '{"pt": "meu-artigo", "en": "my-article"} (auto-generated if empty)'
            }),
            'excerpt_i18n': forms.Textarea(attrs={
                'rows': 3, 'class': 'w-full px-3 py-2 border border-gray-300 rounded-md text-sm',
                'placeholder': '{"pt": "Resumo...", "en": "Summary..."}'
            }),
            'html_content_i18n': forms.Textarea(attrs={
                'rows': 6, 'class': 'w-full px-3 py-2 border border-gray-300 rounded-md text-sm font-mono',
                'placeholder': '{"pt": "<section>...</section>", "en": "<section>...</section>"}'
            }),
            'meta_description_i18n': forms.Textarea(attrs={
                'rows': 2, 'class': 'w-full px-3 py-2 border border-gray-300 rounded-md text-sm font-mono',
                'placeholder': '{"pt": "Meta descrição", "en": "Meta description"}'
            }),
            'category': forms.Select(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-md text-sm'
            }),
            'published_date': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-md text-sm',
            }),
            'is_published': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 text-blue-600 rounded',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['gallery_images'].initial = self.instance.gallery_images.all()


class NewsCategoryForm(forms.ModelForm):
    class Meta:
        model = NewsCategory
        fields = ['name_i18n', 'slug_i18n', 'description_i18n', 'order', 'is_active']
        widgets = {
            'name_i18n': forms.Textarea(attrs={
                'rows': 2, 'class': 'w-full px-3 py-2 border border-gray-300 rounded-md text-sm font-mono',
                'placeholder': '{"pt": "Tecnologia", "en": "Technology"}'
            }),
            'slug_i18n': forms.Textarea(attrs={
                'rows': 2, 'class': 'w-full px-3 py-2 border border-gray-300 rounded-md text-sm font-mono',
                'placeholder': '{"pt": "tecnologia", "en": "technology"} (auto-generated if empty)'
            }),
            'description_i18n': forms.Textarea(attrs={
                'rows': 3, 'class': 'w-full px-3 py-2 border border-gray-300 rounded-md text-sm font-mono',
            }),
            'order': forms.NumberInput(attrs={
                'class': 'w-24 px-3 py-2 border border-gray-300 rounded-md text-sm',
            }),
        }
```

**Step 2: Update news/views.py (backoffice views)**

Update all views to use new model fields. The existing views need to reference the new i18n fields instead of old single-language fields. Also add CategoryListView and LayoutListView.

This is a full rewrite of `news/views.py` — update all view classes to work with the new form and add category/layout management views.

**Step 3: Update backoffice/urls.py**

Add the new routes for categories and layouts alongside existing news routes (lines 35-40):

```python
# News app routes
path('news/', news_views.NewsListView.as_view(), name='news_list'),
path('news/create/', news_views.NewsCreateView.as_view(), name='news_create'),
path('news/<int:pk>/edit/', news_views.NewsUpdateView.as_view(), name='news_edit'),
path('news/<int:pk>/delete/', news_views.NewsDeleteView.as_view(), name='news_delete'),
path('news/<int:pk>/gallery/', news_views.NewsGalleryView.as_view(), name='news_gallery'),
path('news/categories/', news_views.CategoryListView.as_view(), name='news_categories'),
path('news/categories/create/', news_views.CategoryCreateView.as_view(), name='news_category_create'),
path('news/categories/<int:pk>/edit/', news_views.CategoryUpdateView.as_view(), name='news_category_edit'),
path('news/categories/<int:pk>/delete/', news_views.CategoryDeleteView.as_view(), name='news_category_delete'),
path('news/layouts/', news_views.LayoutListView.as_view(), name='news_layouts'),
path('news/layouts/<int:pk>/edit/', news_views.LayoutUpdateView.as_view(), name='news_layout_edit'),
```

**Step 4: Update DashboardView**

In `backoffice/views.py`, add news stats to `DashboardView.get_context_data()` (after line 163):

```python
from news.models import NewsPost

# News statistics
context['total_news_posts'] = NewsPost.objects.count()
context['published_news_posts'] = NewsPost.objects.filter(is_published=True).count()
recent_news = list(NewsPost.objects.order_by('-created_at')[:5])
context['recent_news_posts'] = recent_news
```

**Step 5: Update sidebar**

In `backoffice/templates/backoffice/includes/sidebar.html`, expand the News section (lines 82-89) to include sub-links:

```html
<!-- News section with sub-navigation -->
<a href="{% url 'backoffice:news_list' %}" class="...">
    <span>All Posts</span>
</a>
<a href="{% url 'backoffice:news_categories' %}" class="...">
    <span>Categories</span>
</a>
<a href="{% url 'backoffice:news_layouts' %}" class="...">
    <span>Layouts</span>
</a>
```

**Step 6: Create category and layout templates**

Create `backoffice/templates/backoffice/news_categories.html` and `news_layouts.html` following the existing pattern of `news_list.html`.

**Step 7: Update existing news templates**

Update `news_list.html`, `news_form.html`, `news_confirm_delete.html` to use the new i18n fields.

**Step 8: Update news/admin.py**

Add `NewsCategory` admin registration and update `NewsPostAdmin` fieldsets for new fields.

**Step 9: Commit**

```bash
git add news/ backoffice/
git commit -m "feat: update backoffice for new news model fields

Add category CRUD, layout management, dashboard stats.
Update forms and templates for i18n JSON fields.
Expand sidebar with sub-navigation."
```

---

## Task 8: RefinementSession generic FK

Extend `RefinementSession` to support any content type, not just Pages.

**Files:**
- Modify: `ai/models.py` (lines 94-167)
- Create: migration

**Step 1: Add generic FK fields**

Add to `RefinementSession` model (keep existing `page` FK for backward compat):

```python
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

class RefinementSession(models.Model):
    page = models.ForeignKey(
        'core.Page',
        on_delete=models.CASCADE,
        related_name='refinement_sessions',
        null=True, blank=True,  # Make nullable for generic FK usage
    )
    # Generic FK for any content type (NewsPost, PropertyListing, etc.)
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True, blank=True,
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    # ... rest unchanged
```

**Step 2: Create and run migration**

```bash
python manage.py makemigrations ai --name add_generic_fk_to_refinement_session
python manage.py migrate
```

**Step 3: Commit**

```bash
git add ai/models.py ai/migrations/
git commit -m "feat: add generic FK to RefinementSession for multi-app support

Keeps backward-compatible page FK. New content_type/object_id fields
allow refinement sessions for any model (news posts, properties, etc.)."
```

---

## Task 9: AI generation endpoints for news

Add AI generation, chat refinement, bulk generation, and image processing for news posts.

**Files:**
- Modify: `ai/views.py` — add news-specific API endpoints
- Modify: `ai/urls.py` — register new endpoints
- Create: `backoffice/templates/backoffice/ai_generate_news.html`
- Create: `backoffice/templates/backoffice/ai_refine_news.html`
- Create: `backoffice/templates/backoffice/ai_bulk_news.html`
- Create: `backoffice/templates/backoffice/news_images.html`
- Modify: `backoffice/urls.py` — add AI and image processing routes
- Modify: `news/views.py` — add AI tool views

**Step 1: Add news generation API endpoint to ai/views.py**

Add a `generate_news_post_api` function that mirrors `generate_page_api` but with news-specific prompts. The key difference is the prompt context (article structure, category, excerpt) and the save target (`NewsPost.html_content_i18n`).

**Step 2: Add chat refinement API endpoint**

Add `chat_refine_news_api` that mirrors `chat_refine_page_api`. Uses the generic FK `RefinementSession` to store history. Loads the post's `html_content_i18n[lang]` as context.

**Step 3: Add bulk news generation endpoint**

Add `analyze_bulk_news_api` that mirrors `analyze_bulk_pages_api` but extracts post structure (titles, categories, key points) from a description.

**Step 4: Add news image processing endpoints**

Reuse `analyze_page_images` and `process_page_images` endpoints — they already work on arbitrary HTML. The news views just need to pass the right HTML content.

**Step 5: Register URLs in ai/urls.py**

```python
path('api/generate-news-post/', views.generate_news_post_api, name='generate_news_post'),
path('api/chat-refine-news/', views.chat_refine_news_api, name='chat_refine_news'),
path('api/analyze-bulk-news/', views.analyze_bulk_news_api, name='analyze_bulk_news'),
```

**Step 6: Create backoffice templates**

Create the backoffice templates for AI tools — these closely mirror the page AI templates (`ai_generate_page.html`, `ai_refine_page.html`, `ai_bulk_pages.html`) but target news posts.

**Step 7: Add backoffice views and routes**

In `news/views.py`, add:
- `NewsGenerateView` — renders the AI generate form
- `NewsRefineView` — renders the chat refinement UI
- `NewsBulkView` — renders the bulk generation UI
- `NewsImagesView` — renders the image processing UI

In `backoffice/urls.py`, add:
```python
path('news/ai/generate/', news_views.NewsGenerateView.as_view(), name='news_ai_generate'),
path('news/ai/bulk/', news_views.NewsBulkView.as_view(), name='news_ai_bulk'),
path('news/ai/chat/refine/<int:pk>/', news_views.NewsRefineView.as_view(), name='news_ai_refine'),
path('news/<int:pk>/images/', news_views.NewsImagesView.as_view(), name='news_images'),
```

**Step 8: Commit**

```bash
git add ai/ backoffice/ news/
git commit -m "feat: add full AI workflow for news posts

Generate, chat refine, bulk generate, and image processing.
Reuses ContentGenerationService with news-specific prompts."
```

---

## Task 10: Editor v2 integration for news detail pages

Extend the inline editor to work on news post detail pages.

**Files:**
- Modify: `editor_v2/api_views.py` — add content-type-aware save/load
- Modify: `news/public_views.py` — add editor data attributes to detail view
- Modify: `news/templates/news/base_news.html` — include editor support
- Modify: `editor_v2/static/editor_v2/js/editor.js` — detect news post editing context

**Step 1: Update editor API views**

The key change: editor save/load functions need to accept an optional `content_type` + `object_id` alongside `page_id`. When present, they load/save the app model's `html_content_i18n` instead of `Page.html_content_i18n`.

Add a helper function:

```python
def _get_editable_object(data):
    """Resolve the editable object from request data.

    Returns (obj, lang) where obj has html_content_i18n.
    Supports Page (default) and any model with html_content_i18n via content_type/object_id.
    """
    page_id = data.get('page_id')
    content_type_id = data.get('content_type_id')
    object_id = data.get('object_id')

    if content_type_id and object_id:
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get(id=content_type_id)
        obj = ct.get_object_for_this_type(id=object_id)
        return obj
    elif page_id:
        return Page.objects.get(id=page_id)
    else:
        raise ValueError("No page_id or content_type_id/object_id provided")
```

Update the refine/save endpoints to use this helper.

**Step 2: Update news detail template**

In `news/templates/news/base_news.html`, add data attributes for the editor:

```html
{% extends "base.html" %}

{% block content %}
<div {% if news_post %}data-editable-type="news.newspost" data-editable-id="{{ news_post.pk }}"{% endif %}>
{{ page_content }}
</div>
{% endblock %}
```

**Step 3: Update editor JS**

In `editor_v2/static/editor_v2/js/editor.js`, detect the editable type from data attributes and pass `content_type_id` + `object_id` to API calls when editing non-Page content.

**Step 4: Commit**

```bash
git add editor_v2/ news/
git commit -m "feat: extend inline editor for news post detail pages

Editor detects news_post context via data attributes.
API views resolve editable object via content_type/object_id."
```

---

## Task 11: Verify and test end-to-end

**Step 1: Run all checks**

```bash
python manage.py check
python manage.py migrate --check
python manage.py runserver 8000
```

**Step 2: Manual verification checklist**

- [ ] Visit `/en/news/` — should render (empty or with posts)
- [ ] Create a news post in backoffice with i18n fields
- [ ] Visit `/en/news/<slug>/` — should render the post
- [ ] Visit `/backoffice/news/categories/` — should list categories
- [ ] Visit `/backoffice/news/layouts/` — should list layouts
- [ ] Dashboard shows news stats
- [ ] Sidebar shows expanded news sub-navigation
- [ ] AI generate a news post works
- [ ] Chat refinement on a news post works
- [ ] Inline editor on news detail page works with `?edit=v2`
- [ ] Template tags work in a CMS page: `{% load news_tags %}{% latest_posts 3 as posts %}`

**Step 3: Final commit**

```bash
git add -A
git commit -m "feat: complete news app upgrade to reference template

Public views, template tags, categories, AI workflow, inline editing.
This app serves as the blueprint for all future decoupled apps."
```
