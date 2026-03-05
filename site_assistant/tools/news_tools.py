"""News app tools — thin adapters to NewsService."""


def list_news_posts(params, context):
    from news.services import NewsService
    return NewsService.list(
        limit=params.get('limit', 20),
        published_only=params.get('published_only', False),
        category_id=params.get('category_id'),
    )


def get_news_post(params, context):
    from news.services import NewsService
    post_id = params.get('post_id')
    title = params.get('title')
    if not post_id and not title:
        return {'success': False, 'message': 'Provide post_id or title'}
    result = NewsService.get(post_id=post_id, title=title)
    if not result['success']:
        return {'success': False, 'message': result['error']}
    # Serialize the post for LLM
    post = result['post']
    return {
        'success': True,
        'post': {
            'id': post.id,
            'title': post.title_i18n,
            'slug': post.slug_i18n,
            'excerpt': post.excerpt_i18n,
            'is_published': post.is_published,
            'published_date': post.published_date.isoformat() if post.published_date else None,
            'category': str(post.category) if post.category else None,
            'category_id': post.category_id,
            'featured_image_id': post.featured_image_id,
        },
        'message': f'News post "{post}" found',
    }


def create_news_post(params, context):
    from news.services import NewsService
    result = NewsService.create(
        title=params.get('title'),
        title_i18n=params.get('title_i18n'),
        slug_i18n=params.get('slug_i18n'),
        excerpt_i18n=params.get('excerpt_i18n'),
        category_id=params.get('category_id'),
        featured_image_id=params.get('featured_image_id'),
        is_published=params.get('is_published', False),
        published_date=params.get('published_date'),
    )
    if not result['success']:
        return {'success': False, 'message': result['error']}
    return {'success': True, 'post_id': result['post'].id, 'message': result['message']}


def update_news_post(params, context):
    from news.services import NewsService
    post_id = params.get('post_id')
    if not post_id:
        return {'success': False, 'message': 'Missing post_id'}
    # Pass all possible update fields
    kwargs = {}
    for field in ('title_i18n', 'slug_i18n', 'excerpt_i18n', 'html_content_i18n',
                  'meta_description_i18n', 'is_published', 'category_id',
                  'featured_image_id', 'published_date'):
        if field in params:
            kwargs[field] = params[field]
    result = NewsService.update(post_id, **kwargs)
    if not result['success']:
        return {'success': False, 'message': result['error']}
    return {'success': True, 'message': result['message']}


def list_news_categories(params, context):
    from news.services import NewsService
    return NewsService.list_categories()


NEWS_TOOLS = {
    'list_news_posts': list_news_posts,
    'get_news_post': get_news_post,
    'create_news_post': create_news_post,
    'update_news_post': update_news_post,
    'list_news_categories': list_news_categories,
}
