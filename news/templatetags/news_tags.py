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

        posts = list(NewsPost.objects.filter(is_published=True).select_related('category')[:self.count])
        for post in posts:
            _resolve_post_fields(post, lang, default_lang)
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
            NewsPost.objects.filter(is_published=True, category=category)
            .select_related('category')[:self.count]
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
