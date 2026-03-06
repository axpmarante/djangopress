"""NewsService — single source of truth for news post operations.

Consolidates business logic from:
- site_assistant/tools/news_tools.py (list, get, create, update, categories)
- news/views.py (backoffice CRUD)
"""

import logging
from django.utils.text import slugify

logger = logging.getLogger(__name__)


class NewsService:

    @staticmethod
    def list(limit=20, published_only=False, category_id=None):
        """List news posts with optional filters.

        Args:
            limit: Maximum number of posts to return (default 20).
            published_only: If True, only return published posts.
            category_id: Filter by category ID.

        Returns:
            dict with 'success', 'posts' (list of dicts), 'message'.
        """
        from news.models import NewsPost
        qs = NewsPost.objects.select_related(
            'category', 'featured_image',
        ).order_by('-published_date', '-created_at')

        if published_only:
            qs = qs.filter(is_published=True)
        if category_id:
            qs = qs.filter(category_id=category_id)

        posts = qs[:limit]
        data = []
        for p in posts:
            data.append({
                'id': p.id,
                'title': p.title_i18n,
                'slug': p.slug_i18n,
                'is_published': p.is_published,
                'published_date': p.published_date.isoformat() if p.published_date else None,
                'category': str(p.category) if p.category else None,
                'category_id': p.category_id,
                'has_featured_image': p.featured_image_id is not None,
            })
        return {'success': True, 'posts': data, 'message': f'{len(data)} news posts found'}

    @staticmethod
    def get(post_id=None, title=None):
        """Get a news post by ID or case-insensitive title search.

        Args:
            post_id: Post primary key.
            title: Search string matched case-insensitively against all language titles.

        Returns:
            dict with 'success', 'post' (NewsPost instance), or 'error'.
        """
        from news.models import NewsPost

        if not post_id and not title:
            return {'success': False, 'error': 'Provide post_id or title'}

        if post_id:
            try:
                post = NewsPost.objects.select_related(
                    'category', 'featured_image',
                ).get(pk=post_id)
                return {'success': True, 'post': post}
            except NewsPost.DoesNotExist:
                return {'success': False, 'error': f'News post {post_id} not found'}

        # Search by title across all languages
        for post in NewsPost.objects.select_related('category', 'featured_image').all():
            if post.title_i18n and isinstance(post.title_i18n, dict):
                for lang, t in post.title_i18n.items():
                    if t and title.lower() in t.lower():
                        return {'success': True, 'post': post}

        return {'success': False, 'error': f'No news post found matching "{title}"'}

    @staticmethod
    def create(title=None, title_i18n=None, slug_i18n=None,
               excerpt=None, excerpt_i18n=None,
               html_content_i18n=None, meta_description_i18n=None,
               category_id=None, featured_image_id=None,
               is_published=False, published_date=None):
        """Create a news post with auto i18n.

        Provide either `title` (single language, auto-translated) or `title_i18n`
        (explicit per-language dict). Slugs are auto-generated from titles if not
        provided.

        Args:
            title: Title in default language (auto-translated to others).
            title_i18n: Explicit per-language title dict.
            slug_i18n: Explicit per-language slug dict.
            excerpt: Excerpt in default language (auto-translated).
            excerpt_i18n: Explicit per-language excerpt dict.
            html_content_i18n: Per-language HTML content dict.
            meta_description_i18n: Per-language meta description dict.
            category_id: Category primary key.
            featured_image_id: SiteImage primary key for featured image.
            is_published: Whether the post is published (default False).
            published_date: Published datetime string (ISO format) or datetime.

        Returns:
            dict with 'success', 'post' (NewsPost instance), 'message', or 'error'.
        """
        from news.models import NewsPost, NewsCategory

        if not title and not title_i18n:
            return {'success': False, 'error': 'Provide title or title_i18n'}

        from core.services.i18n import build_i18n_field, auto_generate_slugs

        try:
            title_i18n = build_i18n_field(value=title, value_i18n=title_i18n)
        except ValueError as e:
            return {'success': False, 'error': str(e)}

        slug_i18n = auto_generate_slugs(title_i18n, slug_i18n=slug_i18n)

        # Build excerpt i18n if provided
        final_excerpt_i18n = excerpt_i18n or {}
        if excerpt and not final_excerpt_i18n:
            try:
                final_excerpt_i18n = build_i18n_field(value=excerpt)
            except ValueError:
                final_excerpt_i18n = {}

        post = NewsPost(
            title_i18n=title_i18n,
            slug_i18n=slug_i18n,
            excerpt_i18n=final_excerpt_i18n,
            html_content_i18n=html_content_i18n or {},
            meta_description_i18n=meta_description_i18n or {},
            is_published=is_published,
        )

        # Set category
        if category_id:
            try:
                post.category = NewsCategory.objects.get(pk=category_id)
            except NewsCategory.DoesNotExist:
                return {'success': False, 'error': f'Category {category_id} not found'}

        # Set featured image
        if featured_image_id:
            from core.models import SiteImage
            try:
                post.featured_image = SiteImage.objects.get(pk=featured_image_id)
            except SiteImage.DoesNotExist:
                pass  # Silently ignore invalid image ID

        # Set published date
        if published_date:
            if isinstance(published_date, str):
                from django.utils.dateparse import parse_datetime
                post.published_date = parse_datetime(published_date)
            else:
                post.published_date = published_date

        post.save()
        return {
            'success': True,
            'post': post,
            'message': f'Created news post "{post}" (ID: {post.id})',
        }

    @staticmethod
    def update(post_id, **kwargs):
        """Update fields on a news post.

        Args:
            post_id: Post primary key.
            **kwargs: Fields to update. Supported: title_i18n, slug_i18n,
                excerpt_i18n, html_content_i18n, meta_description_i18n,
                is_published, category_id, featured_image_id, published_date.

        Returns:
            dict with 'success', 'post' (NewsPost instance), 'message', or 'error'.
        """
        from news.models import NewsPost, NewsCategory

        if not post_id:
            return {'success': False, 'error': 'Missing post_id'}

        try:
            post = NewsPost.objects.get(pk=post_id)
        except NewsPost.DoesNotExist:
            return {'success': False, 'error': f'News post {post_id} not found'}

        updated = []

        # Simple JSON fields
        for field in ('title_i18n', 'slug_i18n', 'excerpt_i18n',
                      'html_content_i18n', 'meta_description_i18n'):
            if field in kwargs:
                setattr(post, field, kwargs[field])
                updated.append(field.replace('_i18n', ''))

        # Boolean field
        if 'is_published' in kwargs:
            post.is_published = kwargs['is_published']
            updated.append('is_published')

        # Category FK
        if 'category_id' in kwargs:
            if kwargs['category_id']:
                try:
                    post.category = NewsCategory.objects.get(pk=kwargs['category_id'])
                except NewsCategory.DoesNotExist:
                    return {'success': False, 'error': f'Category {kwargs["category_id"]} not found'}
            else:
                post.category = None
            updated.append('category')

        # Featured image FK
        if 'featured_image_id' in kwargs:
            if kwargs['featured_image_id']:
                from core.models import SiteImage
                try:
                    post.featured_image = SiteImage.objects.get(pk=kwargs['featured_image_id'])
                except SiteImage.DoesNotExist:
                    pass
            else:
                post.featured_image = None
            updated.append('featured_image')

        # Published date
        if 'published_date' in kwargs:
            if kwargs['published_date']:
                if isinstance(kwargs['published_date'], str):
                    from django.utils.dateparse import parse_datetime
                    post.published_date = parse_datetime(kwargs['published_date'])
                else:
                    post.published_date = kwargs['published_date']
            else:
                post.published_date = None
            updated.append('published_date')

        if updated:
            post.save()

        return {
            'success': True,
            'post': post,
            'message': f'Updated news post {post_id}: {", ".join(updated)}',
        }

    @staticmethod
    def delete(post_id):
        """Delete a news post.

        Args:
            post_id: Post primary key.

        Returns:
            dict with 'success', 'message', or 'error'.
        """
        from news.models import NewsPost

        try:
            post = NewsPost.objects.get(pk=post_id)
        except NewsPost.DoesNotExist:
            return {'success': False, 'error': f'News post {post_id} not found'}

        title = str(post)
        post.delete()
        return {'success': True, 'message': f'Deleted news post "{title}" (ID: {post_id})'}

    @staticmethod
    def list_categories():
        """List all news categories with post counts.

        Returns:
            dict with 'success', 'categories' (list of dicts), 'message'.
        """
        from news.models import NewsCategory
        categories = NewsCategory.objects.all().order_by('order', 'pk')
        data = []
        for cat in categories:
            data.append({
                'id': cat.id,
                'name': cat.name_i18n,
                'slug': cat.slug_i18n,
                'is_active': cat.is_active,
                'order': cat.order,
                'post_count': cat.posts.count(),
            })
        return {
            'success': True,
            'categories': data,
            'message': f'{len(data)} news categories found',
        }
