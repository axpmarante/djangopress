"""
Component panel endpoint — one POST for every slider / gallery operation.
Runs editor_v2.components operations through _run_structural_verb, so each
change is checkpointed (undoable) and applied to every language copy.
"""
import json

from bs4 import BeautifulSoup
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from djangopress.core.decorators import editor_required
from djangopress.core.models import SiteImage
from djangopress.editor_v2 import components
from djangopress.editor_v2.api_views import (
    _detect_language_from_request, _edit_lang, _get_editable_object, _get_page_html, _run_structural_verb,
)
from djangopress.editor_v2.component_translate import translate_texts

LABELS = {
    'reorder': 'Reordered items',
    'remove': 'Removed an item',
    'set_settings': 'Changed slider settings',
    'replace_image': 'Replaced an image',
    'add_images': 'Added images',
    'add_text_item': 'Added a slide',
    'update_item': 'Edited an item',
}


def _error(message, status=400):
    return JsonResponse({'success': False, 'error': message}, status=status)


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _alts_by_lang(images, lang, langs, notes):
    """{lang: [alt per image]}: library alt_text_i18n first, else the current-language alt translated."""
    ids = [i for i in (_as_int(img.get('id')) for img in images) if i is not None]
    library = {s.id: s for s in SiteImage.objects.filter(id__in=ids)}
    codes = list(dict.fromkeys([lang, *langs]))
    result = {code: [] for code in codes}
    missing = {}
    for n, image in enumerate(images):
        source = (image.get('alt') or '').strip()
        site_image = library.get(_as_int(image.get('id')))
        i18n = (site_image.alt_text_i18n or {}) if site_image else {}
        for code in codes:
            value = (i18n.get(code) or '').strip()
            if not value and code == lang:
                value = source
            result[code].append(value)
    for code in codes:
        if code == lang:
            continue
        idxs = [n for n, v in enumerate(result[code]) if not v and result[lang][n]]
        if idxs:
            missing[code] = idxs
    for code, idxs in missing.items():
        out = translate_texts([result[lang][n] for n in idxs], lang, code)
        if out is None:
            notes['untranslated'].append(code)
            out = [result[lang][n] for n in idxs]
        else:
            notes['translated'].append(code)
        for n, text in zip(idxs, out):
            result[code][n] = text
    return result


def _texts_by_lang(texts, lang, langs, notes):
    keys = list(texts)
    values = [texts[k].strip() for k in keys]
    result = {lang: dict(zip(keys, values))}
    for code in langs:
        if code == lang:
            continue
        out = translate_texts(values, lang, code)
        if out is None:
            notes['untranslated'].append(code)
            out = values
        else:
            notes['translated'].append(code)
        result[code] = dict(zip(keys, out))
    return result


def _build_op(op, kind, args, lang, langs, notes):
    """fn(root, lang_code) -> focus index, with per-language values resolved up front."""
    if op == 'reorder':
        return lambda root, code: components.reorder(root, kind, args.get('order'))
    if op == 'remove':
        return lambda root, code: components.remove(root, kind, args.get('index'))
    if op == 'set_settings':
        return lambda root, code: components.set_settings(root, args.get('settings'))
    if op == 'update_item':
        return lambda root, code: components.update_item(
            root, kind, args.get('index'), alt=args.get('alt'), caption=args.get('caption'), texts=args.get('texts'))
    if op in ('replace_image', 'add_images'):
        images = [args.get('image')] if op == 'replace_image' else args.get('images')
        if not isinstance(images, list) or not images or not all(isinstance(i, dict) and i.get('url') for i in images):
            raise ValueError('Pick at least one image')
        alts = _alts_by_lang(images, lang, langs, notes)
        urls = [i['url'] for i in images]
        if op == 'replace_image':
            return lambda root, code: components.replace_image(
                root, kind, args.get('index'), urls[0], alts.get(code, alts[lang])[0])
        return lambda root, code: components.add_images(
            root, kind, args.get('after'), list(zip(urls, alts.get(code, alts[lang]))))
    if op == 'add_text_item':
        texts = args.get('texts')
        if not isinstance(texts, dict) or not texts or not all(isinstance(v, str) and v.strip() for v in texts.values()):
            raise ValueError('Fill in every field')
        per_lang = _texts_by_lang(texts, lang, langs, notes)
        return lambda root, code: components.add_text_item(
            root, kind, args.get('after'), per_lang.get(code, per_lang[lang]))
    raise ValueError(f'Unknown operation: {op}')


@editor_required
@require_http_methods(["POST"])
def component_op(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return _error('Invalid JSON')
    root_sel, kind, op = data.get('root'), data.get('kind'), data.get('op')
    count, args = data.get('count'), data.get('args') or {}
    if not root_sel or kind not in components.KINDS or op not in LABELS \
            or not isinstance(count, int) or not isinstance(args, dict):
        return _error('Missing or invalid root / kind / op / count / args')
    try:
        page = _get_editable_object(data)
    except Exception:
        page = None
    if not page:
        return _error('Page or editable object not found')

    lang = _detect_language_from_request(request, data)
    langs = [code for code, html in (getattr(page, 'html_content_i18n', None) or {}).items() if html]
    notes = {'translated': [], 'untranslated': []}
    try:
        op_fn = _build_op(op, kind, args, lang, langs, notes)
    except ValueError as e:
        return _error(str(e))

    edit_lang = _edit_lang(page, lang)

    def apply(soup, code):
        root = components.find_component(soup, root_sel, kind)
        if root is None or len(components.items(root, kind)) != count:
            return None
        try:
            return op_fn(root, code)
        except ValueError:
            # Bad input is reported for the copy being edited; another language
            # whose markup drifted (same count, different shape) is skipped.
            if code in (lang, edit_lang):
                raise
            return None

    try:
        outcome = _run_structural_verb(
            request, data, LABELS[op], apply,
            pass_lang=True, only_lang=edit_lang if op == 'update_item' else None,
        )
    except ValueError as e:
        return _error(str(e))
    if isinstance(outcome, JsonResponse):
        return outcome
    page, focus, skipped = outcome
    if focus is None:
        return _error('This part of the page changed. Reload the page and try again.', status=409)

    html, _lang = _get_page_html(page, lang)
    fresh = components.find_component(BeautifulSoup(html or '', 'html.parser'), root_sel, kind)
    return JsonResponse({
        'success': True,
        'index': focus,
        'html': str(fresh) if fresh is not None else None,
        'skipped_languages': skipped,
        'translated_languages': notes['translated'],
        'untranslated_languages': notes['untranslated'],
        'label': LABELS[op],
        'page_id': page.id,
    })
