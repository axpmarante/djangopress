"""Site-wide tools — thin adapters to core services."""

from djangopress.core.services import (
    PageService, MenuService, SettingsService, FormService, MediaService,
)


def list_pages(params, context):
    result = PageService.list()
    pages_data = [{'id': p.id, 'title': p.title_i18n, 'slug': p.slug_i18n,
                   'is_active': p.is_active, 'sort_order': p.sort_order}
                  for p in result['pages']]
    return {'success': True, 'pages': pages_data, 'message': result['message']}


def get_page_info(params, context):
    page_id = params.get('page_id')
    title = params.get('title')

    if page_id:
        result = PageService.get_info(page_id)
    elif title:
        # First find by title, then get info
        find = PageService.get(title=title)
        if not find['success']:
            return {'success': False, 'message': find['error']}
        result = PageService.get_info(find['page'].id)
    else:
        return {'success': False, 'message': 'Provide page_id or title'}

    if not result['success']:
        return {'success': False, 'message': result['error']}

    page = result['page']
    return {
        'success': True,
        'page': {
            'id': page.id,
            'title': page.title_i18n,
            'slug': page.slug_i18n,
            'is_active': page.is_active,
            'sort_order': page.sort_order,
            'sections': [s['name'] for s in result['sections']],
        },
        'message': f'Page "{page.default_title}" with {len(result["sections"])} sections',
    }


def create_page(params, context):
    result = PageService.create(
        title=params.get('title'),
        slug=params.get('slug'),
        title_i18n=params.get('title_i18n'),
        slug_i18n=params.get('slug_i18n'),
        user=context.get('user'),
    )
    if not result['success']:
        return {'success': False, 'message': result['error']}

    page = result['page']
    session = context.get('session')
    if session:
        session.set_active_page(page)
    return {
        'success': True, 'page_id': page.id,
        'message': result['message'], 'set_active_page': page.id,
    }


def update_page_meta(params, context):
    page_id = params.get('page_id')
    if not page_id:
        return {'success': False, 'message': 'Missing page_id'}
    result = PageService.update_meta(
        page_id=page_id,
        title_i18n=params.get('title_i18n'),
        slug_i18n=params.get('slug_i18n'),
        is_active=params.get('is_active'),
        sort_order=params.get('sort_order'),
    )
    if not result['success']:
        return {'success': False, 'message': result['error']}
    return {'success': True, 'message': result['message']}


def delete_page(params, context):
    page_id = params.get('page_id')
    if not page_id:
        return {'success': False, 'message': 'Missing page_id'}
    result = PageService.delete(page_id)
    if not result['success']:
        return {'success': False, 'message': result['error']}
    session = context.get('session')
    if session and session.active_page_id == page_id:
        session.set_active_page(None)
    return {'success': True, 'message': result['message']}


def reorder_pages(params, context):
    order = params.get('order', [])
    result = PageService.reorder(order)
    if not result['success']:
        return {'success': False, 'message': result['error']}
    return {'success': True, 'message': result['message']}


def set_active_page(params, context):
    page_id = params.get('page_id')
    if not page_id:
        return {'success': False, 'message': 'Missing page_id'}
    result = PageService.get(page_id=page_id)
    if not result['success']:
        return {'success': False, 'message': result['error']}
    page = result['page']
    session = context.get('session')
    if session:
        session.set_active_page(page)
    return {
        'success': True,
        'message': f'Switched to page "{page.default_title}" (ID: {page.id})',
        'set_active_page': page.id,
    }


def list_menu_items(params, context):
    return MenuService.list()


def create_menu_item(params, context):
    result = MenuService.create(
        label=params.get('label'),
        label_i18n=params.get('label_i18n'),
        page_id=params.get('page_id'),
        url=params.get('url'),
        parent_id=params.get('parent_id'),
        sort_order=params.get('sort_order', 0),
        is_active=params.get('is_active', True),
        open_in_new_tab=params.get('open_in_new_tab', False),
    )
    if not result['success']:
        return {'success': False, 'message': result['error']}
    return {'success': True, 'menu_item_id': result['menu_item'].id, 'message': result['message']}


def update_menu_item(params, context):
    menu_item_id = params.get('menu_item_id')
    if not menu_item_id:
        return {'success': False, 'message': 'Missing menu_item_id'}
    result = MenuService.update(
        menu_item_id=menu_item_id,
        label_i18n=params.get('label_i18n'),
        page_id=params.get('page_id'),
        url=params.get('url'),
        parent_id=params.get('parent_id'),
        sort_order=params.get('sort_order'),
        is_active=params.get('is_active'),
        open_in_new_tab=params.get('open_in_new_tab'),
    )
    if not result['success']:
        return {'success': False, 'message': result['error']}
    return {'success': True, 'message': result['message']}


def delete_menu_item(params, context):
    menu_item_id = params.get('menu_item_id')
    if not menu_item_id:
        return {'success': False, 'message': 'Missing menu_item_id'}
    result = MenuService.delete(menu_item_id)
    if not result['success']:
        return {'success': False, 'message': result['error']}
    return {'success': True, 'message': result['message']}


def get_settings(params, context):
    return SettingsService.get(fields=params.get('fields'))


def update_settings(params, context):
    result = SettingsService.update(params.get('updates', {}))
    if not result['success']:
        return {'success': False, 'message': result['error']}
    return {'success': True, 'message': result['message']}


def list_images(params, context):
    return MediaService.list(
        search=params.get('search', ''),
        limit=params.get('limit', 20),
    )


def list_forms(params, context):
    return FormService.list()


def create_form(params, context):
    result = FormService.create(
        name=params.get('name', ''),
        slug=params.get('slug', ''),
        notification_email=params.get('notification_email', ''),
        fields_schema=params.get('fields_schema'),
        success_message_i18n=params.get('success_message_i18n'),
        is_active=params.get('is_active', True),
    )
    if not result['success']:
        return {'success': False, 'message': result['error']}
    return {'success': True, 'form_id': result['form'].id, 'message': result['message']}


def update_form(params, context):
    result = FormService.update(
        form_id=params.get('form_id'),
        slug=params.get('slug'),
        name=params.get('name'),
        notification_email=params.get('notification_email'),
        fields_schema=params.get('fields_schema'),
        success_message_i18n=params.get('success_message_i18n'),
        is_active=params.get('is_active'),
    )
    if not result['success']:
        return {'success': False, 'message': result['error']}
    return {'success': True, 'message': result['message']}


def delete_form(params, context):
    result = FormService.delete(
        form_id=params.get('form_id'),
        slug=params.get('slug'),
    )
    if not result['success']:
        return {'success': False, 'message': result['error']}
    return {'success': True, 'message': result['message']}


def list_form_submissions(params, context):
    return FormService.list_submissions(
        form_slug=params.get('form_slug'),
        limit=params.get('limit', 10),
    )


def get_stats(params, context):
    result = SettingsService.get_snapshot()
    if not result['success']:
        return {'success': False, 'message': result['error']}
    stats = result['snapshot']['stats']
    return {'success': True, 'stats': stats, 'message': 'Site statistics retrieved'}


# ---- HEADER/FOOTER (new tools) ----

def refine_header(params, context):
    from djangopress.core.services import GlobalSectionService
    instructions = params.get('instructions', '')
    if not instructions:
        return {'success': False, 'message': 'Missing instructions'}
    result = GlobalSectionService.refine('main-header', instructions, user=context.get('user'))
    if not result['success']:
        return {'success': False, 'message': result['error']}
    return {'success': True, 'message': result['message']}


def refine_footer(params, context):
    from djangopress.core.services import GlobalSectionService
    instructions = params.get('instructions', '')
    if not instructions:
        return {'success': False, 'message': 'Missing instructions'}
    result = GlobalSectionService.refine('main-footer', instructions, user=context.get('user'))
    if not result['success']:
        return {'success': False, 'message': result['error']}
    return {'success': True, 'message': result['message']}


# Registry mapping
SITE_TOOLS = {
    'list_pages': list_pages,
    'get_page_info': get_page_info,
    'create_page': create_page,
    'update_page_meta': update_page_meta,
    'delete_page': delete_page,
    'reorder_pages': reorder_pages,
    'set_active_page': set_active_page,
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
    'refine_header': refine_header,
    'refine_footer': refine_footer,
}
