"""MenuService — navigation management."""

import logging
from core.models import MenuItem, Page
from .i18n import build_i18n_field

logger = logging.getLogger(__name__)


class MenuService:

    @staticmethod
    def list():
        """List menu items with hierarchy (top-level + children)."""
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

    @staticmethod
    def create(label=None, label_i18n=None, page_id=None, url=None,
               parent_id=None, sort_order=0, is_active=True, open_in_new_tab=False):
        """Create a menu item with auto-translation support."""
        if not label and not label_i18n:
            return {'success': False, 'error': 'Provide label or label_i18n'}

        try:
            label_i18n = build_i18n_field(value=label, value_i18n=label_i18n)
        except ValueError as e:
            return {'success': False, 'error': str(e)}

        kwargs = {
            'label_i18n': label_i18n,
            'sort_order': sort_order,
            'is_active': is_active,
            'open_in_new_tab': open_in_new_tab,
        }

        if page_id:
            try:
                kwargs['page'] = Page.objects.get(pk=page_id)
            except Page.DoesNotExist:
                return {'success': False, 'error': f'Page {page_id} not found'}

        if url:
            kwargs['url'] = url

        if not page_id and not url:
            return {'success': False, 'error': 'Provide page_id or url'}

        if parent_id:
            try:
                parent = MenuItem.objects.get(pk=parent_id)
                # Validate nesting depth <= 1
                if parent.parent_id:
                    return {'success': False, 'error': 'Maximum nesting depth is 1 level'}
                kwargs['parent'] = parent
            except MenuItem.DoesNotExist:
                return {'success': False, 'error': f'Parent menu item {parent_id} not found'}

        item = MenuItem.objects.create(**kwargs)
        return {
            'success': True,
            'menu_item': item,
            'message': f'Created menu item (ID: {item.id})',
        }

    @staticmethod
    def update(menu_item_id, label_i18n=None, page_id=None, url=None,
               parent_id=None, sort_order=None, is_active=None, open_in_new_tab=None):
        """Update a menu item."""
        try:
            item = MenuItem.objects.get(pk=menu_item_id)
        except MenuItem.DoesNotExist:
            return {'success': False, 'error': f'Menu item {menu_item_id} not found'}

        updated = []
        if label_i18n is not None:
            item.label_i18n = label_i18n
            updated.append('label')
        if page_id is not None:
            if page_id:
                try:
                    item.page = Page.objects.get(pk=page_id)
                except Page.DoesNotExist:
                    return {'success': False, 'error': f'Page {page_id} not found'}
            else:
                item.page = None
            updated.append('page')
        if url is not None:
            item.url = url
            updated.append('url')
        if sort_order is not None:
            item.sort_order = sort_order
            updated.append('sort_order')
        if is_active is not None:
            item.is_active = is_active
            updated.append('is_active')
        if open_in_new_tab is not None:
            item.open_in_new_tab = open_in_new_tab
            updated.append('open_in_new_tab')
        if parent_id is not None:
            if parent_id:
                try:
                    parent = MenuItem.objects.get(pk=parent_id)
                    if parent.parent_id:
                        return {'success': False, 'error': 'Maximum nesting depth is 1 level'}
                    item.parent = parent
                except MenuItem.DoesNotExist:
                    return {'success': False, 'error': f'Parent menu item {parent_id} not found'}
            else:
                item.parent = None
            updated.append('parent')

        if updated:
            item.save()

        return {'success': True, 'menu_item': item, 'message': f'Updated menu item {menu_item_id}: {", ".join(updated)}'}

    @staticmethod
    def delete(menu_item_id):
        """Delete a menu item."""
        try:
            item = MenuItem.objects.get(pk=menu_item_id)
        except MenuItem.DoesNotExist:
            return {'success': False, 'error': f'Menu item {menu_item_id} not found'}

        item.delete()
        return {'success': True, 'message': f'Deleted menu item (ID: {menu_item_id})'}

    @staticmethod
    def reorder(order):
        """order = [{"menu_item_id": int, "sort_order": int}, ...]"""
        if not order:
            return {'success': False, 'error': 'Empty order list'}
        for item in order:
            MenuItem.objects.filter(pk=item['menu_item_id']).update(sort_order=item['sort_order'])
        return {'success': True, 'message': f'Reordered {len(order)} menu items'}
