"""Site-wide tools — thin adapters to core services."""

from djangopress.core.services import (
    PageService, MenuService, SettingsService, FormService, MediaService,
)


def undo_last_change(params, context):
    """Undo the last assistant turn that changed something ("desfaz isso")."""
    from djangopress.site_assistant import changes
    session = context.get('session')
    index = changes.last_turn_with_changes(session) if session else None
    if index is None:
        return {'success': False, 'message': 'There is no change of mine to undo.'}
    force = bool(params.get('force'))
    if force:
        from djangopress.site_assistant.tools import _has_recent_confirmation
        if not _has_recent_confirmation(context):
            return {'success': False, 'message': ('BLOCKED: undoing over later edits needs the user to confirm. Tell them '
                                                  'what would be lost and ask; call again with force=true only after they confirm.')}
    result = changes.undo_turn(session, index, context.get('user'), force=force)
    if result.get('conflicts'):
        return {'success': False, 'message': 'Changed again since then: ' + ', '.join(result['conflicts'])
                + '. Ask the user to confirm, then call undo_last_change with force=true.'}
    if result.get('error'):
        return {'success': False, 'message': result['error']}
    notes = ''.join(f' Note: {n}.' for n in result.get('notes') or [])
    return {'success': True, 'message': 'Undone: ' + ', '.join(result['undone']) + '.' + notes}


def web_search(params, context):
    """Look facts up on the web (Google Search). Returns the answer and its sources."""
    query = (params.get('query') or '').strip()
    if not query:
        return {'success': False, 'message': 'Missing query'}
    from djangopress.ai.utils.llm_config import LLMBase
    try:
        found = LLMBase().web_search(query)
    except Exception as e:
        return {'success': False, 'message': f'Web search failed: {e}'}
    if not found['sources']:
        return {'success': True, 'message': 'Nothing reliable found on the web.', 'answer': found['text'], 'sources': []}
    return {'success': True, 'message': f'Web search: {query}', 'answer': found['text'], 'sources': found['sources']}


def read_document(params, context):
    """Read a PDF or image of this site: the executor sees it next, and it rides along to the
    design model on refine_section / refine_page / insert_section for the rest of the turn."""
    from djangopress.site_assistant import documents
    try:
        doc = documents.load(file_id=params.get('file_id'), url=params.get('url'))
    except ValueError as e:
        return {'success': False, 'message': str(e)}
    attachment = {'bytes': doc['bytes'], 'mime_type': doc['mime_type']}
    context['reference_images'] = [*(context.get('reference_images') or []), attachment]
    context['new_attachments'] = [*(context.get('new_attachments') or []), attachment]
    return {'success': True, 'message': (
        f'Read "{doc["title"]}" ({doc["mime_type"]}); it is attached below. It is also sent to the design model '
        f'on refine_section / refine_page / insert_section in this reply.')}


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
            'meta_title': page.meta_title_i18n or {},
            'meta_description': page.meta_description_i18n or {},
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
        meta_title_i18n=params.get('meta_title_i18n'),
        meta_description_i18n=params.get('meta_description_i18n'),
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


def validate_forms(params, context):
    """Scan all pages and GlobalSections for form-related issues."""
    import re
    from djangopress.core.models import Page, GlobalSection, DynamicForm, SiteSettings

    site_settings = SiteSettings.objects.first()
    default_lang = site_settings.get_default_language() if site_settings else 'pt'

    # Build registry of existing forms
    existing_forms = {}
    for form in DynamicForm.objects.filter(is_active=True):
        schema_names = {f['name'] for f in form.schema_fields()}
        existing_forms[form.slug] = {
            'name': form.name,
            'field_names': schema_names,
        }

    issues = []
    pages_checked = 0

    # Check pages
    for page in Page.objects.filter(is_active=True):
        html = (page.html_content_i18n or {}).get(default_lang, '')
        if not html:
            continue
        pages_checked += 1
        page_label = page.default_title or f'Page {page.id}'
        _check_html_for_form_issues(html, page_label, existing_forms, issues)

    # Check GlobalSections
    for section in GlobalSection.objects.filter(is_active=True):
        html = (section.html_template_i18n or {}).get(default_lang, '')
        if not html:
            continue
        section_label = f'GlobalSection: {section.name or section.key}'
        _check_html_for_form_issues(html, section_label, existing_forms, issues)

    if not issues:
        return {
            'success': True,
            'message': f'All forms OK. Checked {pages_checked} pages.',
            'issues': [],
        }

    return {
        'success': True,
        'message': f'Found {len(issues)} issue(s) across {pages_checked} pages.',
        'issues': issues,
    }


def validate_contacts(params, context):
    """Check phones, emails, WhatsApp and the map across settings and content. Read-only."""
    from djangopress.site_assistant import contacts
    result = contacts.check(check_web=bool(params.get('check_web')))
    issues = result['issues']
    counts = {level: sum(1 for i in issues if i['level'] == level) for level in ('wrong', 'inconsistent', 'cant_verify')}
    lines = []
    for issue in issues[:25]:
        w = issue['where']
        place = ', '.join(filter(None, [w.get('source'), w.get('section') and f'section "{w["section"]}"',
                                        w.get('lang') and w['lang'].upper()]))
        lines.append(f'[{issue["level"]}] {issue["what"]} ({place})')
    if not issues:
        message = 'Contacts look right: phones, emails, WhatsApp and the map agree with Settings.'
    else:
        message = (f'{counts["wrong"]} wrong, {counts["inconsistent"]} inconsistent, '
                   f'{counts["cant_verify"]} could not be verified. ' + ' | '.join(lines))
    if result['web_answer']:
        message += f' Web search said: {result["web_answer"][:600]}'
    elif not params.get('check_web'):
        message += (' The details were not compared with the web (check_web was off): do not say the web or '
                    'any official site confirms them.')
    message += ' Nothing was changed.'
    return {'success': True, 'issues': issues, 'sources': result['sources'], 'message': message}


FORM_ACTION_RE = r'action="(?:/[a-z]{2})?/forms/([^/"]+)/submit/"'


def _test_value(field, operator_email):
    kind, name = field['type'], field['name'].lower()
    if field['choices']:
        return field['choices'][0]
    if kind == 'email':
        return operator_email
    if kind == 'tel':
        return '+351 912 345 678'
    if kind == 'date':
        import datetime
        return (datetime.date.today() + datetime.timedelta(days=7)).isoformat()
    if kind == 'time':
        return '20:00'
    if kind == 'number':
        return '2'
    if kind == 'checkbox':
        return True
    if kind == 'url':
        return 'https://example.com'
    if kind == 'textarea':
        return 'Mensagem de teste enviada pelo assistente do site. Pode ignorar.'
    if any(w in name for w in ('name', 'nome')):
        return 'Teste Assistente'
    return 'Teste'


def _operator_email(context):
    from django.conf import settings
    user = (context or {}).get('user')
    return getattr(settings, 'PWD_SUPERADMIN_EMAIL', '') or getattr(user, 'email', '') or ''


def test_form(params, context):
    """Submit a form for real (validate, save, emails) with every email going to
    the operator with [TESTE] in the subject; the test submission is deleted."""
    import re
    from djangopress.core.models import DynamicForm, GlobalSection, Page
    from djangopress.core.services.forms import process_submission

    operator = _operator_email(context)
    if not operator:
        return {'success': False, 'message': 'No operator email to send the test to (set PWD_SUPERADMIN_EMAIL)'}
    slug = (params.get('slug') or '').strip()
    if slug:
        forms = list(DynamicForm.objects.filter(slug=slug))
        if not forms:
            return {'success': False, 'message': f'No form with slug "{slug}"'}
    else:
        used = []
        sources = [*(p.html_content_i18n or {} for p in Page.objects.filter(is_active=True)),
                   *(g.html_template_i18n or {} for g in GlobalSection.objects.filter(is_active=True))]
        for copies in sources:
            for html in copies.values():
                used += re.findall(FORM_ACTION_RE, html or '')
        forms = [f for f in DynamicForm.objects.filter(slug__in=set(used))]
        if not forms:
            return {'success': True, 'checks': [], 'message': 'No forms are used on the site pages.'}

    from djangopress.core.models import SiteSettings
    settings = SiteSettings.load()
    lang = settings.get_default_language() if settings else 'pt'
    checks = []
    for form in forms:
        data = {f['name']: _test_value(f, operator) for f in form.schema_fields(lang)}
        check = {'form': form.slug, 'active': form.is_active, 'valid': False, 'saved': False,
                 'notification_sent': False, 'confirmation_sent': None, 'sent_to': operator, 'errors': {}}
        result = process_submission(form, data, lang, None, 'DjangoPress site assistant (test)',
                                    notify_to=operator, subject_prefix='[TESTE] ')
        check['errors'] = result['errors']
        check['valid'] = not result['errors']
        if result['submission'] is not None:
            check['saved'] = True
            check['notification_sent'] = result['notification_sent']
            if form.send_confirmation_email:
                check['confirmation_sent'] = result['confirmation_sent']
            result['submission'].delete()
        checks.append(check)

    lines = []
    for c in checks:
        if not c['valid']:
            lines.append(f'{c["form"]}: test data rejected ({"; ".join(c["errors"].values())})')
            continue
        line = f'{c["form"]}: saved, notification ' + ('sent' if c['notification_sent'] else 'NOT sent')
        if c['confirmation_sent'] is not None:
            line += ', confirmation ' + ('sent' if c['confirmation_sent'] else 'NOT sent')
        if not c['active']:
            line += ' (the form is inactive: visitors can\'t submit it)'
        lines.append(line)
    any_failed = any(not c['valid'] or not c['notification_sent'] for c in checks)
    message = (f'Tested {len(checks)} form(s); emails went only to {operator} with [TESTE] in the subject; '
               f'test submissions deleted. ' + ' | '.join(lines))
    if any_failed:
        message += ' — some emails were not sent or the data was rejected; check the email settings and the form.'
    return {'success': True, 'checks': checks, 'message': message}


def _check_html_for_form_issues(html, source_label, existing_forms, issues):
    """Check a piece of HTML for form-related problems."""
    import re

    # Find all form actions
    form_actions = re.findall(
        r'<form[^>]*action="/forms/([^/"]+)/submit/"[^>]*>(.*?)</form>',
        html, re.DOTALL | re.IGNORECASE,
    )

    for slug, form_body in form_actions:
        # Check slug exists
        if slug not in existing_forms:
            issues.append({
                'source': source_label,
                'severity': 'high',
                'issue': f'Form action references non-existent DynamicForm: "{slug}"',
                'fix': f'Create a DynamicForm with slug="{slug}" or update the form action URL.',
            })
            continue

        # Check field name mismatches
        schema_names = existing_forms[slug]['field_names']
        html_names = set(re.findall(r'name="([^"]+)"', form_body))
        # Exclude system fields
        html_names -= {'csrfmiddlewaretoken', 'website_url', 'next', 'language'}

        missing_in_schema = html_names - schema_names
        missing_in_html = {n for n in schema_names if n not in html_names}

        if missing_in_schema:
            issues.append({
                'source': source_label,
                'severity': 'medium',
                'issue': (
                    f'Form "{slug}": HTML has fields not in schema: '
                    f'{", ".join(sorted(missing_in_schema))}'
                ),
                'fix': 'Add these fields to the DynamicForm fields_schema or remove from HTML.',
            })
        if missing_in_html:
            issues.append({
                'source': source_label,
                'severity': 'medium',
                'issue': (
                    f'Form "{slug}": schema requires fields missing from HTML: '
                    f'{", ".join(sorted(missing_in_html))}'
                ),
                'fix': 'Add these fields to the HTML form or remove from schema.',
            })

        # Check honeypot
        if 'website_url' not in re.findall(r'name="([^"]+)"', form_body):
            issues.append({
                'source': source_label,
                'severity': 'low',
                'issue': f'Form "{slug}": missing honeypot field (website_url)',
                'fix': 'Add hidden honeypot field for spam protection.',
            })

    # Check for escaped JS operators (BS4 corruption)
    if '=&gt;' in html or '&amp;&amp;' in html:
        issues.append({
            'source': source_label,
            'severity': 'high',
            'issue': 'HTML contains escaped JS operators (=&gt; or &amp;&amp;) — JavaScript is broken',
            'fix': 'Run sanitize_html_output() or replace =&gt; with => in the stored HTML.',
        })


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
    'validate_contacts': validate_contacts,
    'test_form': test_form,
    'web_search': web_search,
    'read_document': read_document,
    'undo_last_change': undo_last_change,
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
    'validate_forms': validate_forms,
    'get_stats': get_stats,
    'refine_header': refine_header,
    'refine_footer': refine_footer,
}
