"""
Fix html_content_i18n / html_template_i18n fields that still contain
{{ trans.xxx }} variables from incomplete data migration.

Re-applies regex replacement from translations JSON, then strips any
remaining {{ trans.xxx }} patterns (replacing with empty string).

Usage:
    python manage.py fix_i18n_html          # Fix all pages + global sections
    python manage.py fix_i18n_html --dry-run  # Preview changes without saving
"""

import re

from django.core.management.base import BaseCommand

from djangopress.core.models import Page, GlobalSection, PageVersion, SiteSettings

TRANS_PATTERN = re.compile(r'\{\{\s*trans\.\w+\s*\}\}')


def _replace_trans_vars(html, trans_dict):
    """Replace {{ trans.key }} with values from trans_dict."""
    result = html
    for key, value in trans_dict.items():
        pattern = r'\{\{\s*trans\.' + re.escape(key) + r'\s*\}\}'
        result = re.sub(pattern, str(value), result)
    return result


def _strip_remaining_trans(html):
    """Remove any {{ trans.xxx }} patterns that weren't resolved."""
    return TRANS_PATTERN.sub('', html)


class Command(BaseCommand):
    help = 'Fix html_content_i18n fields that still contain {{ trans.xxx }} variables'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Preview changes without saving')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — no changes will be saved\n'))

        self._fix_pages(dry_run)
        self._fix_global_sections(dry_run)
        self._fix_page_versions(dry_run)

    def _fix_pages(self, dry_run):
        fixed = skipped = 0
        for page in Page.objects.all():
            html_i18n = page.html_content_i18n or {}
            if not html_i18n:
                skipped += 1
                continue

            translations = (page.content or {}).get('translations', {})
            changed = False

            for lang, html in html_i18n.items():
                if not TRANS_PATTERN.search(html):
                    continue

                # Re-apply translations for this language
                trans_dict = translations.get(lang, {})
                new_html = _replace_trans_vars(html, trans_dict)

                # Strip any remaining unresolved {{ trans.xxx }}
                remaining = TRANS_PATTERN.findall(new_html)
                new_html = _strip_remaining_trans(new_html)

                if new_html != html:
                    html_i18n[lang] = new_html
                    changed = True
                    if remaining:
                        self.stdout.write(
                            f'  Page {page.id} [{lang}]: stripped {len(remaining)} '
                            f'unresolved trans vars: {remaining[:5]}'
                        )

            if changed:
                fixed += 1
                if not dry_run:
                    page.html_content_i18n = html_i18n
                    page.save(update_fields=['html_content_i18n'])

            else:
                skipped += 1

        self.stdout.write(f'Pages: {fixed} fixed, {skipped} clean')

    def _fix_global_sections(self, dry_run):
        fixed = skipped = 0
        for section in GlobalSection.objects.all():
            html_i18n = section.html_template_i18n or {}
            if not html_i18n:
                skipped += 1
                continue

            translations = (section.content or {}).get('translations', {})
            changed = False

            for lang, html in html_i18n.items():
                if not TRANS_PATTERN.search(html):
                    continue

                trans_dict = translations.get(lang, {})
                new_html = _replace_trans_vars(html, trans_dict)
                remaining = TRANS_PATTERN.findall(new_html)
                new_html = _strip_remaining_trans(new_html)

                if new_html != html:
                    html_i18n[lang] = new_html
                    changed = True
                    if remaining:
                        self.stdout.write(
                            f'  GlobalSection {section.key} [{lang}]: stripped {len(remaining)} '
                            f'unresolved trans vars: {remaining[:5]}'
                        )

            if changed:
                fixed += 1
                if not dry_run:
                    section.html_template_i18n = html_i18n
                    section.save(update_fields=['html_template_i18n'])
            else:
                skipped += 1

        self.stdout.write(f'GlobalSections: {fixed} fixed, {skipped} clean')

    def _fix_page_versions(self, dry_run):
        fixed = skipped = 0
        for version in PageVersion.objects.all():
            html_i18n = version.html_content_i18n or {}
            if not html_i18n:
                skipped += 1
                continue

            translations = (version.content or {}).get('translations', {})
            changed = False

            for lang, html in html_i18n.items():
                if not TRANS_PATTERN.search(html):
                    continue

                trans_dict = translations.get(lang, {})
                new_html = _replace_trans_vars(html, trans_dict)
                remaining = TRANS_PATTERN.findall(new_html)
                new_html = _strip_remaining_trans(new_html)

                if new_html != html:
                    html_i18n[lang] = new_html
                    changed = True

            if changed:
                fixed += 1
                if not dry_run:
                    version.html_content_i18n = html_i18n
                    version.save(update_fields=['html_content_i18n'])
            else:
                skipped += 1

        self.stdout.write(f'PageVersions: {fixed} fixed, {skipped} clean')
