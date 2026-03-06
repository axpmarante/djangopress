"""Public-facing news views."""

from django.views.generic import TemplateView
from django.http import Http404
from django.template import Template, RequestContext
from django.utils.translation import get_language
from djangopress.core.models import SiteSettings


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
  {{ post.html_content|safe }}
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
    from djangopress.news.models import NewsLayout
    try:
        layout = NewsLayout.objects.get(key=key)
        html_i18n = layout.html_content_i18n or {}
        html = html_i18n.get(lang) or html_i18n.get(default_lang) or ''
        if html:
            return html
    except NewsLayout.DoesNotExist:
        pass

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
        from djangopress.news.models import NewsPost
        from django.core.paginator import Paginator

        context = super().get_context_data(**kwargs)
        lang, default_lang = _get_lang_and_default()

        posts_qs = NewsPost.objects.filter(is_published=True).select_related('category', 'featured_image')
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
            **context,
        })
        context['page_content'] = template.render(render_context)
        context['page_title'] = 'News'
        context['seo_title'] = 'News'
        return context


class NewsDetailView(TemplateView):
    template_name = 'news/base_news.html'

    def get_context_data(self, **kwargs):
        from djangopress.news.models import NewsPost

        context = super().get_context_data(**kwargs)
        lang, default_lang = _get_lang_and_default()
        slug = self.kwargs['slug']

        # Find post by slug_i18n (cached index)
        post = NewsPost.get_by_slug(slug, lang) or NewsPost.get_by_slug(slug, default_lang)

        if not post:
            raise Http404("News post not found")

        _resolve_post(post, lang, default_lang)
        layout_html = _get_layout_html('detail', lang, default_lang)

        template = Template(layout_html)
        render_context = RequestContext(self.request, {
            'post': post,
            'news_post': post,
            **context,
        })
        context['page_content'] = template.render(render_context)
        context['page_title'] = post.title
        context['news_post'] = post

        # SEO
        context['seo_title'] = post.title
        meta_desc = (post.meta_description_i18n or {}).get(lang) or (post.meta_description_i18n or {}).get(default_lang) or post.excerpt or ''
        context['seo_description'] = meta_desc
        context['og_type'] = 'article'
        if post.featured_image:
            context['og_image_url'] = self.request.build_absolute_uri(post.featured_image.url)
        context['canonical_url'] = self.request.build_absolute_uri(post.get_absolute_url(lang))

        # Enable edit mode for staff users with ?edit=true or ?edit=v2
        edit_param = self.request.GET.get('edit')
        if self.request.user.is_staff and edit_param in ('true', 'v2'):
            context['edit_mode'] = 'v2'
            from django.contrib.contenttypes.models import ContentType
            ct = ContentType.objects.get_for_model(post)
            context['editable_content_type_id'] = ct.id
            context['editable_object_id'] = post.pk
        else:
            context['edit_mode'] = False

        return context


class NewsCategoryView(TemplateView):
    template_name = 'news/base_news.html'
    paginate_by = 12

    def get_context_data(self, **kwargs):
        from djangopress.news.models import NewsPost, NewsCategory
        from django.core.paginator import Paginator

        context = super().get_context_data(**kwargs)
        lang, default_lang = _get_lang_and_default()
        slug = self.kwargs['slug']

        # Find category by slug_i18n (cached index)
        category = NewsCategory.get_by_slug(slug, lang) or NewsCategory.get_by_slug(slug, default_lang)

        if not category:
            raise Http404("Category not found")

        posts_qs = NewsPost.objects.filter(
            is_published=True, category=category
        ).select_related('category', 'featured_image')
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
        cat_name = category.get_i18n_field('name', lang)
        context['page_title'] = cat_name
        context['seo_title'] = f'News — {cat_name}'
        cat_desc = (category.description_i18n or {}).get(lang) or (category.description_i18n or {}).get(default_lang) or ''
        if cat_desc:
            context['seo_description'] = cat_desc
        return context
