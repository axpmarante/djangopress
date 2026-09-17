"""Save an AdaptResult into the site: Page, GlobalSections, SiteSettings, MenuItems, JSON-LD."""

import json
from pathlib import Path

from djangopress.core.build.jsonld import build_jsonld
from djangopress.core.models import GlobalSection, MenuItem, Page, SiteSettings

TOKEN_FIELDS = ('heading_font', 'body_font', 'background_color', 'text_color', 'heading_color', 'primary_color',
                'primary_button_bg', 'primary_button_text', 'secondary_color', 'accent_color',
                'container_width', 'border_radius_preset', 'shadow_preset')


def cta_texts_from(packet):
    return [i['text'] for page in packet['content'].values() for i in page['required'] if i.get('href')]


def mark_concept_status(concepts_json_path, key, status):
    """Update docs/concepts/concepts.json in place: set `key`'s status; when the new status is
    'shipped', demote every other 'shipped' entry to 'rejected' (a concept import always
    replaces whatever was shipped before). No-op when the file doesn't exist."""
    path = Path(concepts_json_path)
    if not path.exists():
        return
    index = json.loads(path.read_text())
    for entry in index:
        if entry['key'] == key:
            entry['status'] = status
        elif status == 'shipped' and entry.get('status') == 'shipped':
            entry['status'] = 'rejected'
    path.write_text(json.dumps(index, ensure_ascii=False, indent=2))


def _jsonld_block(data):
    return '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False) + '</script>'


def import_result(result, *, packet, set_home=True, change_summary='Import concept'):
    lang = packet['site']['default_language']
    warnings = list(result.warnings)
    s = SiteSettings.load()

    home = next((p for p in Page.objects.all() if (p.slug_i18n or {}).get(lang) == 'home'), None)
    new_home_fields = {
        'title_i18n': {lang: packet['site']['name']},
        'slug_i18n': {lang: 'home'},
        'html_content_i18n': {lang: result.page_html},
        'meta_title_i18n': {lang: result.meta_title or packet['site']['name']},
        'meta_description_i18n': {lang: result.meta_description or packet['business']['positioning']},
    }
    if home is None:
        home = Page(sort_order=0, is_active=True, **new_home_fields)
        home.save()
    else:
        # Page auto-versions on every save() (signals.create_page_version reads
        # instance._change_summary), unlike GlobalSection which has no such signal —
        # so never call home.create_version() here, that would double the version on
        # every genuine change. Only touch (and thus version) the page when its
        # content actually changed, or a byte-identical reimport would pile up a
        # redundant version too.
        changed = not home.is_active or any(getattr(home, f) != v for f, v in new_home_fields.items())
        if changed:
            for field, value in new_home_fields.items():
                setattr(home, field, value)
            home.is_active = True
            home._change_summary = change_summary
            home.save()

    ids = {}
    for key, name, stype, html in (('main-header', 'Main Header', 'header', result.header_html),
                                   ('main-footer', 'Main Footer', 'footer', result.footer_html)):
        section = GlobalSection.objects.filter(key=key).first()
        if section is None:
            section = GlobalSection(key=key, name=name, section_type=stype)
        else:
            section.create_version(change_summary=change_summary)
        section.html_template_i18n = {lang: html}
        section.is_active = True
        section.save()
        ids[key] = section.id

    MenuItem.objects.all().delete()
    for i, item in enumerate(result.menu):
        MenuItem.objects.create(label_i18n={lang: item['label']}, url=item['href'], sort_order=i, is_active=True)

    for field in TOKEN_FIELDS:
        if result.settings.get(field):
            setattr(s, field, result.settings[field])
    jsonld_data = build_jsonld(packet)
    s.custom_head_code = result.head_code + '\n' + _jsonld_block(jsonld_data)
    if 'geo' not in jsonld_data:
        warnings.append('JSON-LD has no geo: add coordinates to the Google Maps link in the briefing')
    if set_home:
        s.homepage = home
    s.save()

    return {'page_id': home.id, 'header_id': ids['main-header'], 'footer_id': ids['main-footer'],
            'menu_items': len(result.menu), 'warnings': warnings}


def _fonts_link(settings):
    families = [f for f in (settings.get('heading_font'), settings.get('body_font')) if f]
    if not families:
        return ''
    query = '&'.join(f"family={f.replace(' ', '+')}:wght@400;500;600;700" for f in dict.fromkeys(families))
    return f'<link href="https://fonts.googleapis.com/css2?{query}&display=swap" rel="stylesheet">'


def import_as_page(result, *, packet, slug, change_summary='Import concept as page'):
    """A non-shipped concept as an extra page: its sections plus page-scoped fonts, config and CSS.

    Header, footer, menu, settings and the homepage are untouched — the page renders inside the
    shipped concept's header and footer. `{{`, `{%` and `{#` are broken up so a raw page never
    holds template syntax.
    """
    lang = packet['site']['default_language']
    page = next((p for p in Page.objects.all() if (p.slug_i18n or {}).get(lang) == slug), None)
    scoped = (_fonts_link(result.settings) + '\n' + result.head_code).replace('{{', '{ {').replace('{%', '{ %').replace('{#', '{ #')
    new_page_fields = {
        'title_i18n': {lang: f"{packet['site']['name']} — {slug}"},
        'slug_i18n': {lang: slug},
        'html_content_i18n': {lang: result.page_html + '\n' + scoped},
        'meta_title_i18n': {lang: result.meta_title or packet['site']['name']},
        'meta_description_i18n': {lang: result.meta_description or packet['business']['positioning']},
    }
    if page is None:
        page = Page(sort_order=500, is_active=True, **new_page_fields)
        page.save()
    else:
        # Same reasoning as import_result: Page auto-versions on every save(), so
        # never call page.create_version() here, and only save when content changed.
        changed = not page.is_active or any(getattr(page, f) != v for f, v in new_page_fields.items())
        if changed:
            for field, value in new_page_fields.items():
                setattr(page, field, value)
            page.is_active = True
            page._change_summary = change_summary
            page.save()
    return {'page_id': page.id, 'slug': slug, 'warnings': list(result.warnings)}
