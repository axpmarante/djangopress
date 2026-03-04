"""Site-wide tools — always available regardless of active page."""

from core.models import Page, SiteSettings, MenuItem, SiteImage, DynamicForm, FormSubmission


def list_pages(params, context):
    pages = Page.objects.all().order_by('sort_order', 'created_at')
    data = []
    for p in pages:
        data.append({
            'id': p.id,
            'title': p.title_i18n,
            'slug': p.slug_i18n,
            'is_active': p.is_active,
            'sort_order': p.sort_order,
        })
    return {'success': True, 'pages': data, 'message': f'{len(data)} pages found'}


def get_page_info(params, context):
    from bs4 import BeautifulSoup

    page_id = params.get('page_id')
    title = params.get('title')

    if not page_id and not title:
        return {'success': False, 'message': 'Provide page_id or title'}

    page = None
    if page_id:
        try:
            page = Page.objects.get(pk=page_id)
        except Page.DoesNotExist:
            return {'success': False, 'message': f'Page {page_id} not found'}
    else:
        # Search by title across all languages in the JSON field
        for p in Page.objects.all():
            if p.title_i18n and isinstance(p.title_i18n, dict):
                for lang, t in p.title_i18n.items():
                    if t and title.lower() in t.lower():
                        page = p
                        break
            if page:
                break
        if not page:
            return {'success': False, 'message': f'No page found matching "{title}"'}

    sections = []
    # Read from html_content_i18n with fallback to html_content
    from django.utils.translation import get_language
    from core.models import SiteSettings
    site_settings = SiteSettings.objects.first()
    default_lang = site_settings.get_default_language() if site_settings else 'pt'
    current_lang = get_language() or default_lang
    html_i18n = page.html_content_i18n or {}
    page_html = html_i18n.get(current_lang) or html_i18n.get(default_lang) or page.html_content or ''
    if page_html:
        soup = BeautifulSoup(page_html, 'html.parser')
        for sec in soup.find_all('section', attrs={'data-section': True}):
            sections.append(sec['data-section'])

    return {
        'success': True,
        'page': {
            'id': page.id,
            'title': page.title_i18n,
            'slug': page.slug_i18n,
            'is_active': page.is_active,
            'sort_order': page.sort_order,
            'sections': sections,
        },
        'message': f'Page "{page.default_title}" with {len(sections)} sections',
    }


def create_page(params, context):
    title_i18n = params.get('title_i18n', {})
    slug_i18n = params.get('slug_i18n', {})

    if not title_i18n:
        return {'success': False, 'message': 'Missing title_i18n'}

    # Auto-generate slug from title if not provided
    if not slug_i18n:
        from django.utils.text import slugify
        slug_i18n = {lang: slugify(title) for lang, title in title_i18n.items()}

    page = Page.objects.create(
        title_i18n=title_i18n,
        slug_i18n=slug_i18n,
        html_content='',
        content={'translations': {}},
        is_active=params.get('is_active', True),
    )

    # Auto-set active page on session
    session = context.get('session')
    if session:
        session.set_active_page(page)

    return {
        'success': True,
        'page_id': page.id,
        'message': f'Created page "{page.default_title}" (ID: {page.id})',
        'set_active_page': page.id,
    }


def update_page_meta(params, context):
    page_id = params.get('page_id')
    if not page_id:
        return {'success': False, 'message': 'Missing page_id'}

    try:
        page = Page.objects.get(pk=page_id)
    except Page.DoesNotExist:
        return {'success': False, 'message': f'Page {page_id} not found'}

    updated = []
    if 'title_i18n' in params:
        page.title_i18n = params['title_i18n']
        updated.append('title')
    if 'slug_i18n' in params:
        page.slug_i18n = params['slug_i18n']
        updated.append('slug')
    if 'is_active' in params:
        page.is_active = params['is_active']
        updated.append('is_active')
    if 'sort_order' in params:
        page.sort_order = params['sort_order']
        updated.append('sort_order')

    if updated:
        page.save()

    return {
        'success': True,
        'message': f'Updated page {page_id}: {", ".join(updated)}',
    }


def delete_page(params, context):
    page_id = params.get('page_id')
    if not page_id:
        return {'success': False, 'message': 'Missing page_id'}

    try:
        page = Page.objects.get(pk=page_id)
    except Page.DoesNotExist:
        return {'success': False, 'message': f'Page {page_id} not found'}

    title = page.default_title
    page.delete()

    # Clear active page if it was the deleted one
    session = context.get('session')
    if session and session.active_page_id == page_id:
        session.set_active_page(None)

    return {'success': True, 'message': f'Deleted page "{title}" (ID: {page_id})'}


def reorder_pages(params, context):
    order = params.get('order', [])
    if not order:
        return {'success': False, 'message': 'Missing order list'}

    for item in order:
        Page.objects.filter(pk=item['page_id']).update(sort_order=item['sort_order'])

    return {'success': True, 'message': f'Reordered {len(order)} pages'}


def list_menu_items(params, context):
    items = MenuItem.objects.filter(parent__isnull=True).order_by('sort_order')
    data = []
    for item in items:
        entry = {
            'id': item.id,
            'label': item.label_i18n,
            'page_id': item.page_id,
            'url': item.url,
            'sort_order': item.sort_order,
            'is_active': item.is_active,
            'children': [],
        }
        for child in item.children.order_by('sort_order'):
            entry['children'].append({
                'id': child.id,
                'label': child.label_i18n,
                'page_id': child.page_id,
                'url': child.url,
                'sort_order': child.sort_order,
                'is_active': child.is_active,
            })
        data.append(entry)
    return {'success': True, 'menu_items': data, 'message': f'{len(data)} top-level menu items'}


def create_menu_item(params, context):
    label_i18n = params.get('label_i18n', {})
    if not label_i18n:
        return {'success': False, 'message': 'Missing label_i18n'}

    kwargs = {
        'label_i18n': label_i18n,
        'sort_order': params.get('sort_order', 0),
        'is_active': params.get('is_active', True),
        'open_in_new_tab': params.get('open_in_new_tab', False),
    }

    page_id = params.get('page_id')
    if page_id:
        try:
            kwargs['page'] = Page.objects.get(pk=page_id)
        except Page.DoesNotExist:
            return {'success': False, 'message': f'Page {page_id} not found'}

    url = params.get('url')
    if url:
        kwargs['url'] = url

    parent_id = params.get('parent_id')
    if parent_id:
        try:
            kwargs['parent'] = MenuItem.objects.get(pk=parent_id)
        except MenuItem.DoesNotExist:
            return {'success': False, 'message': f'Parent menu item {parent_id} not found'}

    item = MenuItem.objects.create(**kwargs)
    return {
        'success': True,
        'menu_item_id': item.id,
        'message': f'Created menu item (ID: {item.id})',
    }


def update_menu_item(params, context):
    item_id = params.get('menu_item_id')
    if not item_id:
        return {'success': False, 'message': 'Missing menu_item_id'}

    try:
        item = MenuItem.objects.get(pk=item_id)
    except MenuItem.DoesNotExist:
        return {'success': False, 'message': f'Menu item {item_id} not found'}

    updated = []
    if 'label_i18n' in params:
        item.label_i18n = params['label_i18n']
        updated.append('label')
    if 'page_id' in params:
        if params['page_id']:
            item.page = Page.objects.get(pk=params['page_id'])
        else:
            item.page = None
        updated.append('page')
    if 'url' in params:
        item.url = params['url']
        updated.append('url')
    if 'sort_order' in params:
        item.sort_order = params['sort_order']
        updated.append('sort_order')
    if 'is_active' in params:
        item.is_active = params['is_active']
        updated.append('is_active')
    if 'parent_id' in params:
        if params['parent_id']:
            item.parent = MenuItem.objects.get(pk=params['parent_id'])
        else:
            item.parent = None
        updated.append('parent')

    if updated:
        item.save()

    return {'success': True, 'message': f'Updated menu item {item_id}: {", ".join(updated)}'}


def delete_menu_item(params, context):
    item_id = params.get('menu_item_id')
    if not item_id:
        return {'success': False, 'message': 'Missing menu_item_id'}

    try:
        item = MenuItem.objects.get(pk=item_id)
    except MenuItem.DoesNotExist:
        return {'success': False, 'message': f'Menu item {item_id} not found'}

    label = item.label_i18n
    item.delete()
    return {'success': True, 'message': f'Deleted menu item "{label}" (ID: {item_id})'}


def get_settings(params, context):
    settings = SiteSettings.load()
    if not settings:
        return {'success': False, 'message': 'No site settings configured'}

    fields = params.get('fields')
    data = {
        'site_name': settings.site_name_i18n,
        'site_description': settings.site_description_i18n,
        'contact_email': settings.contact_email,
        'contact_phone': settings.contact_phone,
        'contact_address': settings.contact_address_i18n,
        'facebook_url': settings.facebook_url,
        'instagram_url': settings.instagram_url,
        'linkedin_url': settings.linkedin_url,
        'twitter_url': settings.twitter_url,
        'youtube_url': settings.youtube_url,
        'google_maps_embed_url': settings.google_maps_embed_url,
        'maintenance_mode': settings.maintenance_mode,
        'domain': settings.domain,
        'default_language': settings.get_default_language(),
        'enabled_languages': settings.get_language_codes(),
        # Design system
        'primary_color': settings.primary_color,
        'primary_color_hover': settings.primary_color_hover,
        'secondary_color': settings.secondary_color,
        'accent_color': settings.accent_color,
        'background_color': settings.background_color,
        'text_color': settings.text_color,
        'heading_color': settings.heading_color,
        'heading_font': settings.heading_font,
        'body_font': settings.body_font,
        'container_width': settings.container_width,
        'border_radius_preset': settings.border_radius_preset,
        'button_style': settings.button_style,
        'button_size': settings.button_size,
        'primary_button_bg': settings.primary_button_bg,
        'primary_button_text': settings.primary_button_text,
        'primary_button_border': settings.primary_button_border,
        'primary_button_hover': settings.primary_button_hover,
        'secondary_button_bg': settings.secondary_button_bg,
        'secondary_button_text': settings.secondary_button_text,
        'secondary_button_border': settings.secondary_button_border,
        'secondary_button_hover': settings.secondary_button_hover,
        # Content
        'design_guide': settings.design_guide,
        'project_briefing': settings.project_briefing,
    }

    if fields:
        data = {k: v for k, v in data.items() if k in fields}

    return {'success': True, 'settings': data, 'message': 'Site settings retrieved'}


SETTINGS_ALLOWLIST = {
    'contact_email', 'contact_phone', 'site_name_i18n', 'site_description_i18n',
    'contact_address_i18n', 'facebook_url', 'instagram_url', 'linkedin_url',
    'twitter_url', 'youtube_url', 'google_maps_embed_url', 'maintenance_mode',
    # Design system
    'primary_color', 'primary_color_hover', 'secondary_color', 'accent_color',
    'background_color', 'text_color', 'heading_color',
    'heading_font', 'body_font',
    'container_width', 'border_radius_preset',
    'button_style', 'button_size',
    'primary_button_bg', 'primary_button_text', 'primary_button_border', 'primary_button_hover',
    'secondary_button_bg', 'secondary_button_text', 'secondary_button_border', 'secondary_button_hover',
    # Content
    'design_guide', 'project_briefing',
}


def update_settings(params, context):
    settings = SiteSettings.load()
    if not settings:
        return {'success': False, 'message': 'No site settings configured'}

    updates = params.get('updates', {})
    if not updates:
        return {'success': False, 'message': 'No updates provided'}

    blocked = [k for k in updates if k not in SETTINGS_ALLOWLIST]
    if blocked:
        return {
            'success': False,
            'message': f'Cannot update protected fields: {", ".join(blocked)}',
        }

    updated = []
    for key, value in updates.items():
        setattr(settings, key, value)
        updated.append(key)

    if updated:
        settings.save()

    return {'success': True, 'message': f'Updated settings: {", ".join(updated)}'}


def list_images(params, context):
    limit = params.get('limit', 20)
    search = params.get('search', '')
    images = SiteImage.objects.filter(is_active=True).order_by('-uploaded_at')

    if search:
        from django.db.models import Q
        images = images.filter(
            Q(title_i18n__icontains=search) | Q(title__icontains=search) | Q(tags__icontains=search)
        )

    images = images[:limit]
    data = []
    for img in images:
        data.append({
            'id': img.id,
            'title': img.title_i18n,
            'url': img.image.url if img.image else '',
            'tags': img.tags or '',
        })
    return {'success': True, 'images': data, 'message': f'{len(data)} images found'}


def list_forms(params, context):
    forms = DynamicForm.objects.all()
    data = []
    for f in forms:
        data.append({
            'id': f.id,
            'name': f.name,
            'slug': f.slug,
            'notification_email': f.notification_email,
            'is_active': f.is_active,
            'submission_count': f.submissions.count(),
        })
    return {'success': True, 'forms': data, 'message': f'{len(data)} forms found'}


def create_form(params, context):
    name = params.get('name', '')
    slug = params.get('slug', '')
    if not name or not slug:
        return {'success': False, 'message': 'Missing name or slug'}

    if DynamicForm.objects.filter(slug=slug).exists():
        return {'success': False, 'message': f'Form with slug "{slug}" already exists'}

    form = DynamicForm.objects.create(
        name=name,
        slug=slug,
        notification_email=params.get('notification_email', ''),
        fields_schema=params.get('fields_schema', []),
        success_message_i18n=params.get('success_message_i18n', {}),
        is_active=params.get('is_active', True),
    )
    return {
        'success': True,
        'form_id': form.id,
        'message': f'Created form "{name}" (slug: {slug}). Action URL: /forms/{slug}/submit/',
    }


def update_form(params, context):
    form_id = params.get('form_id')
    slug = params.get('slug')
    if not form_id and not slug:
        return {'success': False, 'message': 'Missing form_id or slug'}

    try:
        if form_id:
            form = DynamicForm.objects.get(pk=form_id)
        else:
            form = DynamicForm.objects.get(slug=slug)
    except DynamicForm.DoesNotExist:
        return {'success': False, 'message': f'Form not found'}

    updated = []
    if 'name' in params:
        form.name = params['name']
        updated.append('name')
    if 'notification_email' in params:
        form.notification_email = params['notification_email']
        updated.append('notification_email')
    if 'fields_schema' in params:
        form.fields_schema = params['fields_schema']
        updated.append('fields_schema')
    if 'success_message_i18n' in params:
        form.success_message_i18n = params['success_message_i18n']
        updated.append('success_message')
    if 'is_active' in params:
        form.is_active = params['is_active']
        updated.append('is_active')

    if updated:
        form.save()

    return {'success': True, 'message': f'Updated form "{form.name}": {", ".join(updated)}'}


def delete_form(params, context):
    form_id = params.get('form_id')
    slug = params.get('slug')
    if not form_id and not slug:
        return {'success': False, 'message': 'Missing form_id or slug'}

    try:
        if form_id:
            form = DynamicForm.objects.get(pk=form_id)
        else:
            form = DynamicForm.objects.get(slug=slug)
    except DynamicForm.DoesNotExist:
        return {'success': False, 'message': 'Form not found'}

    name = form.name
    form.delete()
    return {'success': True, 'message': f'Deleted form "{name}" and all its submissions'}


def list_form_submissions(params, context):
    limit = params.get('limit', 10)
    form_slug = params.get('form_slug', '')
    qs = FormSubmission.objects.select_related('form').order_by('-created_at')
    if form_slug:
        qs = qs.filter(form__slug=form_slug)
    submissions = qs[:limit]
    data = []
    for s in submissions:
        data.append({
            'id': s.id,
            'form': s.form.name,
            'data': s.data,
            'is_read': s.is_read,
            'created_at': s.created_at.isoformat(),
        })
    return {'success': True, 'submissions': data, 'message': f'{len(data)} recent submissions'}


def get_stats(params, context):
    return {
        'success': True,
        'stats': {
            'total_pages': Page.objects.count(),
            'active_pages': Page.objects.filter(is_active=True).count(),
            'total_images': SiteImage.objects.filter(is_active=True).count(),
            'total_submissions': FormSubmission.objects.count(),
            'total_menu_items': MenuItem.objects.count(),
        },
        'message': 'Site statistics retrieved',
    }


def set_active_page(params, context):
    page_id = params.get('page_id')
    if not page_id:
        return {'success': False, 'message': 'Missing page_id'}

    try:
        page = Page.objects.get(pk=page_id)
    except Page.DoesNotExist:
        return {'success': False, 'message': f'Page {page_id} not found'}

    session = context.get('session')
    if session:
        session.set_active_page(page)

    return {
        'success': True,
        'message': f'Switched to page "{page.default_title}" (ID: {page.id})',
        'set_active_page': page.id,
    }


# Registry mapping
SITE_TOOLS = {
    'list_pages': list_pages,
    'get_page_info': get_page_info,
    'create_page': create_page,
    'update_page_meta': update_page_meta,
    'delete_page': delete_page,
    'reorder_pages': reorder_pages,
    'list_menu_items': list_menu_items,
    'create_menu_item': create_menu_item,
    'update_menu_item': update_menu_item,
    'delete_menu_item': delete_menu_item,
    'get_settings': get_settings,
    'update_settings': update_settings,
    'list_images': list_images,
    'list_forms': list_forms,
    'create_form': create_form,
    'update_form': update_form,
    'delete_form': delete_form,
    'list_form_submissions': list_form_submissions,
    'get_stats': get_stats,
    'set_active_page': set_active_page,
}
