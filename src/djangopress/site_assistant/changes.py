"""
Every change the site assistant makes can be undone per turn.

A TurnChanges tracker lives in the tool context for one assistant turn:
- pages get ONE labelled `kind='checkpoint'` PageVersion before their first change
  (the editor's one-click Undo stops at it);
- header/footer get a GlobalSectionVersion before their first change;
- objects without versions (SiteSettings, menu items, forms, news, page meta)
  get a JSON snapshot before their first change, or are noted as created.

At the end of the turn `finish()` returns the change log, stored on the
assistant's message. `undo_turn()` restores everything from it, refusing to
overwrite later edits unless forced.
"""
import datetime
import decimal
import hashlib
import json
import logging
import uuid

from django.apps import apps
from django.db import transaction

logger = logging.getLogger(__name__)


def _model_key(obj):
    return obj._meta.label_lower


def _json_value(value):
    if isinstance(value, (datetime.date, datetime.datetime, datetime.time)):
        return value.isoformat()
    if isinstance(value, (decimal.Decimal, uuid.UUID)):
        return str(value)
    if hasattr(value, 'name') and hasattr(value, 'storage'):   # FieldFile
        return value.name or ''
    return value


def _fields(obj):
    """Concrete field values (FKs as *_id), JSON-safe."""
    data = {}
    for field in obj._meta.concrete_fields:
        if field.primary_key or getattr(field, 'auto_now', False) or getattr(field, 'auto_now_add', False):
            continue
        data[field.attname] = _json_value(getattr(obj, field.attname))
    return data


def _fingerprint(content):
    """A short hash of page/header HTML: enough to detect later edits without
    copying the HTML into the session log."""
    raw = json.dumps(content or {}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


class TurnChanges:
    def __init__(self, request_text, user=None):
        self.label = ' '.join((request_text or '').split())[:60]
        self.user = user
        self.items = []
        self._seen = set()

    # --- before a change -------------------------------------------------
    def page_checkpoint(self, page):
        key = ('page', page.pk)
        if key in self._seen:
            return
        self._seen.add(key)
        page.create_version(user=self.user, change_summary=f'Assistant: {self.label}', kind='checkpoint')
        version = page.versions.order_by('-version_number').first()
        self.items.append({'kind': 'page', 'model': _model_key(page), 'id': page.pk,
                           'label': page.default_title, 'version': version.version_number if version else None})

    def global_section_checkpoint(self, section):
        key = ('global_section', section.pk)
        if key in self._seen:
            return
        self._seen.add(key)
        section.create_version(change_summary=f'Assistant: {self.label}')
        version = section.versions.order_by('-version_number').first() if hasattr(section, 'versions') else None
        from djangopress.core.models import GlobalSectionVersion
        version = version or GlobalSectionVersion.objects.filter(section=section).order_by('-version_number').first()
        self.items.append({'kind': 'global_section', 'model': _model_key(section), 'id': section.pk,
                           'label': section.name or section.key, 'version': version.version_number if version else None})

    def snapshot(self, obj, label=''):
        key = (_model_key(obj), obj.pk)
        if key in self._seen:
            return
        self._seen.add(key)
        self.items.append({'kind': 'object', 'model': _model_key(obj), 'id': obj.pk,
                           'label': label or str(obj), 'before': _fields(obj)})

    # --- after a change --------------------------------------------------
    def created(self, obj, label=''):
        key = (_model_key(obj), obj.pk)
        self._seen.add(key)
        self.items.append({'kind': 'created', 'model': _model_key(obj), 'id': obj.pk, 'label': label or str(obj)})

    def finish(self):
        """The change log, with the 'after' state used to detect later edits."""
        for item in self.items:
            obj = _get(item)
            if item['kind'] == 'page' and obj is not None:
                latest = obj.versions.order_by('-version_number').first()
                item['after_version'] = latest.version_number if latest else None
                item['after'] = _fingerprint(obj.html_content_i18n)
            elif item['kind'] == 'global_section' and obj is not None:
                item['after'] = _fingerprint(obj.html_template_i18n)
            elif item['kind'] in ('object', 'created'):
                item['after'] = _fields(obj) if obj is not None else None
        return self.items


def _get(item):
    try:
        model = apps.get_model(item['model'])
    except LookupError:
        return None
    return model.objects.filter(pk=item['id']).first()


# --- helpers for tools (fall back to the old behaviour without a tracker) --------

def page_checkpoint(context, page):
    tracker = (context or {}).get('changes')
    if tracker:
        tracker.page_checkpoint(page)
    else:
        page.create_version(user=(context or {}).get('user'), change_summary='Site Assistant edit', kind='checkpoint')


def global_section_checkpoint(context, section):
    tracker = (context or {}).get('changes')
    if tracker:
        tracker.global_section_checkpoint(section)
    else:
        section.create_version(change_summary='Site Assistant edit')


def snapshot(context, obj, label=''):
    tracker = (context or {}).get('changes')
    if tracker and obj is not None:
        tracker.snapshot(obj, label)


def created(context, obj, label=''):
    tracker = (context or {}).get('changes')
    if tracker and obj is not None:
        tracker.created(obj, label)


# --- undo -------------------------------------------------------------------------

def _conflict(item):
    """Was this object changed again after the turn?"""
    obj = _get(item)
    if item['kind'] == 'page':
        return obj is not None and _fingerprint(obj.html_content_i18n) != item.get('after')
    if item['kind'] == 'global_section':
        return obj is not None and _fingerprint(obj.html_template_i18n) != item.get('after')
    if item['kind'] in ('object', 'created'):
        if obj is None:
            return item['kind'] == 'object' and item.get('after') is not None
        return _fields(obj) != item.get('after')
    return False


def _restore(item, user):
    obj = _get(item)
    kind = item['kind']
    if kind == 'page' and obj is not None and item.get('version'):
        from djangopress.editor_v2.api_views import _apply_snapshot_html
        version = obj.versions.filter(version_number=item['version']).first()
        if version is not None:
            _apply_snapshot_html(obj, version, f'Undo assistant: {item["label"]}', 'undo', user)
    elif kind == 'global_section' and obj is not None and item.get('version'):
        from djangopress.core.models import GlobalSectionVersion
        version = GlobalSectionVersion.objects.filter(section=obj, version_number=item['version']).first()
        if version is not None:
            obj.create_version(change_summary=f'Before undo: {item["label"]}')
            version.restore()
    elif kind == 'object':
        model = apps.get_model(item['model'])
        if obj is None:                      # deleted during the turn: recreate with the same id
            obj = model(pk=item['id'])
        for name, value in item['before'].items():
            setattr(obj, name, value)
        obj.save()
    elif kind == 'created' and obj is not None:
        obj.delete()


def undo_turn(session, message_index, user, force=False):
    """Restore everything one assistant turn changed. Returns {'undone', 'conflicts'}."""
    try:
        message = session.messages[message_index]
    except (IndexError, TypeError):
        return {'undone': [], 'conflicts': [], 'error': 'Message not found'}
    items = message.get('changes') or []
    if not items:
        return {'undone': [], 'conflicts': [], 'error': 'That reply changed nothing'}
    if message.get('undone'):
        return {'undone': [], 'conflicts': [], 'error': 'Already undone'}

    conflicts = [item['label'] for item in items if _conflict(item)]
    if conflicts and not force:
        return {'undone': [], 'conflicts': conflicts}

    with transaction.atomic():
        for item in reversed(items):
            _restore(item, user)
        message['undone'] = True
        session.messages[message_index] = message
        labels = list(dict.fromkeys(item['label'] for item in items))
        session.add_message('assistant', 'Undone: ' + ', '.join(labels))
    return {'undone': labels, 'conflicts': []}


def last_turn_with_changes(session):
    for index in range(len(session.messages) - 1, -1, -1):
        msg = session.messages[index]
        if msg.get('role') == 'assistant' and msg.get('changes') and not msg.get('undone'):
            return index
    return None
