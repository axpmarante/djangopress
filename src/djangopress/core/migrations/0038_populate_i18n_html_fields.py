"""
Data migration: populate html_content_i18n / html_template_i18n from
existing templatized HTML + translation JSON.

Uses regex string replacement for ALL models (Pages, GlobalSections,
PageVersions) to replace {{ trans.xxx }} with translated text while
preserving other Django template tags ({% csrf_token %}, {% url %},
{% load %}, etc.) that will be rendered at request time with a proper
RequestContext.

Idempotent: skips any record that already has a non-empty *_i18n dict.
"""

import re

from django.db import migrations


def _replace_trans_vars(html, trans_dict):
    """Replace {{ trans.key }} patterns with values from trans_dict.

    Only touches {{ trans.xxx }} variables — all other Django template
    syntax ({% tags %}, {{ other.vars }}, filters, etc.) is left intact.
    """
    result = html
    for key, value in trans_dict.items():
        pattern = r'\{\{\s*trans\.' + re.escape(key) + r'\s*\}\}'
        result = re.sub(pattern, str(value), result)
    return result


def _get_default_language(SiteSettings):
    """Read the default language from SiteSettings, fallback to 'pt'."""
    try:
        ss = SiteSettings.objects.first()
        if ss and ss.default_language:
            return ss.default_language
    except Exception:
        pass
    return 'pt'


def populate_page_i18n(apps, schema_editor):
    """Replace {{ trans.xxx }} in html_content for every Page."""
    Page = apps.get_model('core', 'Page')
    SiteSettings = apps.get_model('core', 'SiteSettings')
    default_lang = _get_default_language(SiteSettings)

    migrated = skipped = 0

    for page in Page.objects.all():
        # Idempotent: skip if already populated
        if page.html_content_i18n:
            skipped += 1
            continue

        html = page.html_content or ''
        if not html.strip():
            skipped += 1
            continue

        content = page.content or {}
        translations = content.get('translations', {})
        html_i18n = {}

        if translations:
            for lang, trans_dict in translations.items():
                html_i18n[lang] = _replace_trans_vars(html, trans_dict)
        else:
            # No translations — store raw HTML under default language
            html_i18n[default_lang] = html

        page.html_content_i18n = html_i18n
        page.save(update_fields=['html_content_i18n'])
        migrated += 1

    print(f"  Pages: {migrated} migrated, {skipped} skipped")


def populate_globalsection_i18n(apps, schema_editor):
    """Replace {{ trans.xxx }} in html_template for every GlobalSection."""
    GlobalSection = apps.get_model('core', 'GlobalSection')
    SiteSettings = apps.get_model('core', 'SiteSettings')
    default_lang = _get_default_language(SiteSettings)

    migrated = skipped = 0

    for section in GlobalSection.objects.all():
        if section.html_template_i18n:
            skipped += 1
            continue

        html = section.html_template or ''
        if not html.strip():
            skipped += 1
            continue

        content = section.content or {}
        translations = content.get('translations', {})
        html_i18n = {}

        if translations:
            for lang, trans_dict in translations.items():
                html_i18n[lang] = _replace_trans_vars(html, trans_dict)
        else:
            html_i18n[default_lang] = html

        section.html_template_i18n = html_i18n
        section.save(update_fields=['html_template_i18n'])
        migrated += 1

    print(f"  GlobalSections: {migrated} migrated, {skipped} skipped")


def populate_pageversion_i18n(apps, schema_editor):
    """Replace {{ trans.xxx }} in html_content for every PageVersion."""
    PageVersion = apps.get_model('core', 'PageVersion')
    SiteSettings = apps.get_model('core', 'SiteSettings')
    default_lang = _get_default_language(SiteSettings)

    migrated = skipped = 0

    for version in PageVersion.objects.all():
        if version.html_content_i18n:
            skipped += 1
            continue

        html = version.html_content or ''
        if not html.strip():
            skipped += 1
            continue

        content = version.content or {}
        translations = content.get('translations', {})
        html_i18n = {}

        if translations:
            for lang, trans_dict in translations.items():
                html_i18n[lang] = _replace_trans_vars(html, trans_dict)
        else:
            html_i18n[default_lang] = html

        version.html_content_i18n = html_i18n
        version.save(update_fields=['html_content_i18n'])
        migrated += 1

    print(f"  PageVersions: {migrated} migrated, {skipped} skipped")


def forward(apps, schema_editor):
    print("\n  Migrating existing content to *_i18n fields...")
    populate_page_i18n(apps, schema_editor)
    populate_globalsection_i18n(apps, schema_editor)
    populate_pageversion_i18n(apps, schema_editor)
    print("  Done.\n")


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0037_globalsection_html_template_i18n_and_more'),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
