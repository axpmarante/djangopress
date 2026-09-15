"""
check_site management command — verify site content against DjangoPress
conventions. The single verification gate used by the generate-site and
edit-site skills.

Usage:
    python manage.py check_site                 # human output, exit 1 on failures
    python manage.py check_site --json          # machine output
    python manage.py check_site --only sections,links

Checks: settings, page-html, forbidden-tag, sections, images, anchors,
links, meta, home, dom-parity, global-section, menu, seo.
"""

import json
import re

from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand, CommandError

from djangopress.core.middleware import NON_I18N_PATHS
from djangopress.core.models import GlobalSection, MenuItem, Page, SiteSettings


CHECK_NAMES = (
    'settings', 'page-html', 'forbidden-tag', 'sections', 'images', 'anchors',
    'links', 'meta', 'home', 'dom-parity', 'global-section', 'menu', 'seo',
)

FORBIDDEN_TAGS = ('html', 'head', 'body', 'header', 'nav', 'footer')
SECTION_NAME_RE = re.compile(r'^[a-z][a-z0-9-]*$')

TEMPLATE_DEFAULT_COLORS = {
    'primary_color': '#1e3a8a',
    'secondary_color': '#64748b',
    'background_color': '#ffffff',
    'text_color': '#1f2937',
}

# Internal paths that legitimately have no language prefix — same list the
# LocaleMiddleware uses to skip its language-prefix redirect (NON_I18N_PATHS:
# /django-admin/, /backoffice/, /ai/, /editor-v2/, /site-assistant/, /i18n/,
# /set-language/, /forms/, /sitemap.xml, /media/, /static/, /robots.txt).
UNPREFIXED_ALLOWED = NON_I18N_PATHS

JSONLD_REQUIRED = {
    'Restaurant': (
        'name', 'telephone', 'address', 'geo',
        'openingHoursSpecification', 'servesCuisine', 'priceRange',
    ),
    'LocalBusiness': ('name', 'telephone', 'address'),
    'Organization': ('name', 'url'),
}

JSONLD_BLOCK_RE = re.compile(
    r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', re.S,
)


def soup_of(html):
    return BeautifulSoup(html or '', 'html.parser')


def structural_signature(html):
    """Depth, tag, classes, id and data-section for every element; no text.

    id and data-section are included because data-section is the section's
    address in editor v2; a divergent name between languages is exactly the
    invisible DOM break this check exists to catch.
    """
    parts = []
    for el in soup_of(html).find_all(True):
        classes = ' '.join(el.get('class', []))
        parts.append(
            f"{len(list(el.parents))}:{el.name}:{classes}:"
            f"{el.get('id', '') or ''}:{el.get('data-section', '') or ''}"
        )
    return parts


class SiteChecker:
    """Runs every enabled check and collects failures as {'check', 'message'}."""

    def __init__(self, only=None):
        self.only = set(only) if only else None
        self.failures = []
        self.settings = SiteSettings.load()
        self.default_lang = self.settings.get_default_language()
        self.lang_codes = self.settings.get_language_codes() or [self.default_lang]

    # -- plumbing ---------------------------------------------------------

    def enabled(self, check):
        return self.only is None or check in self.only

    def fail(self, check, message):
        self.failures.append({'check': check, 'message': message})

    def run(self):
        self.check_settings()
        self.check_pages()
        self.check_dom_parity()
        self.check_global_sections()
        self.check_menu()
        self.check_seo()
        return self.failures

    # -- settings ---------------------------------------------------------

    def check_settings(self):
        if not self.enabled('settings'):
            return
        s = self.settings
        if not s.homepage_id:
            self.fail('settings', 'SiteSettings.homepage is not set — site root will be empty')
        if not s.enabled_languages:
            self.fail('settings', 'SiteSettings.enabled_languages is empty')
        elif self.default_lang not in self.lang_codes:
            self.fail('settings', f'default_language {self.default_lang!r} is not in enabled_languages')
        if not s.gcs_folder:
            self.fail('settings', 'SiteSettings.gcs_folder is empty — media would land in default/')
        name = (s.site_name_i18n or {}).get(self.default_lang)
        if name in (None, '', 'DjangoPress'):
            self.fail('settings', f"site_name_i18n[{self.default_lang!r}] is still the template default")
        if all(
            (getattr(s, field) or '').lower() == default
            for field, default in TEMPLATE_DEFAULT_COLORS.items()
        ):
            self.fail('settings', 'design colors are still the template defaults — SiteSettings was never configured')

    # -- pages ------------------------------------------------------------

    def check_pages(self):
        page_checks = ('page-html', 'forbidden-tag', 'sections', 'images', 'anchors', 'links', 'meta', 'home')
        if not any(self.enabled(c) for c in page_checks):
            return
        home_pages = []
        for page in Page.objects.filter(is_active=True).order_by('sort_order', 'id'):
            content = page.html_content_i18n or {}
            if (page.slug_i18n or {}).get(self.default_lang) == 'home':
                home_pages.append(page)
            self._check_meta(page)
            html = content.get(self.default_lang)
            if not html:
                if self.enabled('page-html'):
                    self.fail('page-html', f'page {page.id} [{self.default_lang}]: html_content is missing or empty')
                continue
            for lang, lang_html in content.items():
                if not lang_html:
                    continue
                self._check_page_html(page, lang, lang_html)
        self._check_home(home_pages)

    def _check_meta(self, page):
        if not self.enabled('meta'):
            return
        if not (page.meta_title_i18n or {}).get(self.default_lang):
            self.fail('meta', f'page {page.id}: meta_title_i18n[{self.default_lang!r}] is empty')
        if not (page.meta_description_i18n or {}).get(self.default_lang):
            self.fail('meta', f'page {page.id}: meta_description_i18n[{self.default_lang!r}] is empty')

    def _check_home(self, home_pages):
        if not self.enabled('home'):
            return
        if len(home_pages) != 1:
            self.fail('home', f"expected exactly one active page with slug 'home' in {self.default_lang!r}, found {len(home_pages)}")
            return
        home = home_pages[0]
        if self.settings.homepage_id != home.id:
            self.fail('home', f'SiteSettings.homepage is {self.settings.homepage_id!r}, but the home page is id {home.id}')
        for lang, slug in (home.slug_i18n or {}).items():
            if slug != 'home':
                self.fail('home', f"home page slug in {lang!r} is {slug!r}, must be 'home' in every language")

    def _check_page_html(self, page, lang, html):
        label = f'page {page.id} [{lang}]'
        soup = soup_of(html)

        if self.enabled('forbidden-tag'):
            for tag in FORBIDDEN_TAGS:
                if soup.find(tag):
                    self.fail('forbidden-tag', f'{label}: contains <{tag}>')

        if self.enabled('sections'):
            sections = soup.find_all('section', recursive=False)
            if not sections:
                self.fail('sections', f'{label}: no top-level <section> elements')
            seen = set()
            for sec in sections:
                name = sec.get('data-section')
                sid = sec.get('id')
                if not name:
                    self.fail('sections', f'{label}: <section> without data-section')
                    continue
                if name != sid:
                    self.fail('sections', f'{label}: data-section={name!r} but id={sid!r}')
                if not SECTION_NAME_RE.match(name):
                    self.fail('sections', f'{label}: bad section name {name!r}')
                if name in seen:
                    self.fail('sections', f'{label}: duplicate section {name!r}')
                seen.add(name)

        if self.enabled('images'):
            for img in soup.find_all('img'):
                src = img.get('src', '')
                if 'placehold.co' in src:
                    self.fail('images', f'{label}: unresolved placeholder {src}')
                if img.get('data-image-prompt') or img.get('data-image-name'):
                    self.fail('images', f'{label}: leftover data-image-* attribute on {src[:60]}')
                if img.get('aria-hidden') == 'true':
                    if img.get('alt'):
                        self.fail('images', f'{label}: aria-hidden img must have empty alt ({src[:60]})')
                elif not img.get('alt'):
                    self.fail('images', f'{label}: <img> without alt ({src[:60]})')

        if self.enabled('anchors') or self.enabled('links'):
            for a in soup.find_all('a', href=True):
                href = a['href']
                if href.startswith('#'):
                    if self.enabled('anchors') and len(href) > 1 and not soup.find(id=href[1:]):
                        self.fail('anchors', f'{label}: {href} has no matching id')
                elif self.enabled('links'):
                    self._check_internal_link(label, lang, href)

    def _check_internal_link(self, label, lang, href):
        if not href.startswith('/') or href.startswith('//') or href == '/':
            return
        if href.startswith(UNPREFIXED_ALLOWED):
            return
        for code in self.lang_codes:
            if href == f'/{code}' or href.startswith(f'/{code}/'):
                return
        self.fail('links', f'{label}: href {href!r} is missing the language prefix (expected /{lang}/...)')

    # -- cross-language ---------------------------------------------------

    def check_dom_parity(self):
        if not self.enabled('dom-parity'):
            return
        for page in Page.objects.filter(is_active=True):
            content = {k: v for k, v in (page.html_content_i18n or {}).items() if v}
            if len(content) < 2:
                continue
            base_lang = self.default_lang if self.default_lang in content else sorted(content)[0]
            base = structural_signature(content[base_lang])
            for lang in sorted(content):
                if lang == base_lang:
                    continue
                other = structural_signature(content[lang])
                if len(base) != len(other):
                    self.fail('dom-parity', f'page {page.id}: {base_lang} has {len(base)} elements, {lang} has {len(other)} — editor nth-child will break')
                    continue
                for i, (a, b) in enumerate(zip(base, other)):
                    if a != b:
                        self.fail('dom-parity', f'page {page.id}: element {i} differs — {base_lang}={a!r} vs {lang}={b!r}')
                        break

    # -- global sections, menu, seo ---------------------------------------

    def check_global_sections(self):
        if not self.enabled('global-section'):
            return
        for key in ('main-header', 'main-footer'):
            section = GlobalSection.objects.filter(key=key, is_active=True).first()
            if not section:
                self.fail('global-section', f'{key} missing or inactive')
                continue
            if not (section.html_template_i18n or {}).get(self.default_lang):
                self.fail('global-section', f'{key} has no {self.default_lang!r} template')

    def check_menu(self):
        if not self.enabled('menu'):
            return
        items = MenuItem.objects.filter(is_active=True).select_related('page')
        if not items.exists():
            self.fail('menu', 'no active MenuItems')
            return
        for item in items:
            if item.page_id and not item.page.is_active:
                self.fail('menu', f'MenuItem {item.id} links to inactive page {item.page_id}')

    def check_seo(self):
        if not self.enabled('seo'):
            return
        blocks = JSONLD_BLOCK_RE.findall(self.settings.custom_head_code or '')
        if not blocks:
            self.fail('seo', 'no JSON-LD block in SiteSettings.custom_head_code')
            return
        for raw in blocks:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                self.fail('seo', f'JSON-LD does not parse: {exc}')
                continue
            # A block may hold one object, a list of objects, or an @graph.
            if isinstance(data, list):
                objects = data
            elif isinstance(data, dict):
                graph = data.get('@graph')
                if graph is None:
                    objects = [data]
                elif isinstance(graph, list):
                    objects = graph
                else:
                    objects = [graph]
            else:
                self.fail('seo', f'JSON-LD block is {type(data).__name__}, expected an object or a list')
                continue
            for obj in objects:
                if not isinstance(obj, dict):
                    continue
                types = obj.get('@type')
                types = types if isinstance(types, list) else [types]
                for t in types:
                    for required in JSONLD_REQUIRED.get(t, ()):
                        if required not in obj:
                            self.fail('seo', f'{t} JSON-LD missing {required!r}')


class Command(BaseCommand):
    help = 'Verify site content against DjangoPress conventions. Exit 1 on failures.'

    def add_arguments(self, parser):
        parser.add_argument('--json', action='store_true', help='Machine-readable output')
        parser.add_argument('--only', default='', help='Comma-separated subset of checks to run')

    def handle(self, *args, **options):
        only = [c.strip() for c in options['only'].split(',') if c.strip()]
        unknown = [c for c in only if c not in CHECK_NAMES]
        if unknown:
            raise CommandError(f"Unknown check(s): {', '.join(unknown)}. Known: {', '.join(CHECK_NAMES)}")

        failures = SiteChecker(only=only or None).run()

        if options['json']:
            self.stdout.write(json.dumps({'ok': not failures, 'failures': failures}, ensure_ascii=False))
        elif failures:
            self.stdout.write(f'FAIL — {len(failures)} problem(s):\n')
            for f in failures:
                self.stdout.write(f"  [{f['check']}] {f['message']}")
        else:
            self.stdout.write('OK — all checks passed')

        if failures:
            raise SystemExit(1)
