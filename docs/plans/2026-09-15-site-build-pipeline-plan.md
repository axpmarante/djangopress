# Site Build Pipeline (Level A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a generic `manage.py check_site` verification command, record the rulings every site hits in the HTML reference, and rewrite `create-briefing` (research first, one block of questions) and `generate-site` (unattended, self-verifying build) so several sites can be produced in parallel.

**Architecture:** Everything lands in the djangopress engine (`src/djangopress/`). Skills are Markdown files symlinked into every child site from the editable install, so a saved skill is live everywhere immediately. The verification command is a Django management command in `core`, tested with Django `TestCase`. No changes to the manager's code; one documentation edit there.

**Tech Stack:** Django 6 management commands, `beautifulsoup4` (already a dependency), Django test runner run from a child site's venv, Markdown skills for Claude Code.

**Spec:** `docs/plans/2026-09-15-site-build-pipeline-design.md`

## Global Constraints

Every task's requirements implicitly include this section.

- **Repo:** `/Users/antoniomarante/Documents/djangopress-sites/djangopress`, branch `main`. Work directly on `main`; no worktree (child sites depend on this checkout's path).
- **Run tests from a child site with an editable install.** The engine has no `manage.py`. Use:
  `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py test djangopress.core.tests.<module> -v 1`
  The test runner uses a separate test database; the site's `db.sqlite3` is not touched.
- **Do not touch `o-marisco/`.** A build is running there from its own plan.
- **Skill names stay `create-briefing` and `generate-site`.** The manager and every child `CLAUDE.md` reference them.
- **Skills are live on save.** Write the whole new file in one `Write` call, never leave a half-written skill on disk between steps.
- **Commit messages must not contain `Co-Authored-By` lines** (rule in `CLAUDE.md`).
- **Commit only the files named in each task.** The repo has an untracked `briefings/lalitana.md` that stays untracked.
- **Template default colors** (the "never configured" signature): `primary_color` `#1e3a8a`, `secondary_color` `#64748b`, `background_color` `#ffffff`, `text_color` `#1f2937`. Compare case-insensitively.
- **Language prefix rule:** `Page.get_absolute_url(lang)` returns `/{lang}/{slug}/` for every language including the default. Internal links in page HTML are literal and carry the prefix.
- **`BriefingParser`** (`src/djangopress/ai/site_generator.py`) splits on `## ` headers into a lowercase dict. Existing section names are kept; new sections are safe.

---

### Task 0: Baseline commit of pending engine changes

**Files:**
- Modify (already modified, uncommitted): `docs/plans/2026-03-17-litestream-default-architecture.md`, `site_template/scripts/entrypoint.sh`, `site_template/scripts/pull-from-prod.sh`, `site_template/scripts/sync-to-prod.sh`, `src/djangopress/core/utils.py`, `src/djangopress/editor_v2/static/editor_v2/js/lib/dom.js`, `src/djangopress/skills/create-briefing/SKILL.md`, `src/djangopress/skills/deploy-site-railway/SKILL.md`, `src/djangopress/skills/djangopress-html-reference/SKILL.md`, `src/djangopress/skills/edit-site/SKILL.md`, `src/djangopress/skills/generate-site/SKILL.md`, `src/djangopress/skills/migrate-to-litestream/SKILL.md`, `src/djangopress/templates/base.html`, `src/djangopress/urls.py`
- Add (untracked): `src/djangopress/skills/analyze-site/`, `src/djangopress/skills/improve-site/`, `docs/plans/2026-04-11-schema-org-automation-design.md`, `docs/plans/2026-05-07-editor-v2-image-discovery-design.md`, `docs/plans/2026-05-07-editor-v2-image-discovery-plan.md`

**Interfaces:**
- Produces: a clean `git status` except `briefings/lalitana.md`, so every later diff is reviewable on its own.

- [ ] **Step 1: Confirm the pending set is what the spec describes**

Run: `git status --short`
Expected: the 14 modified files and 5 untracked paths listed above, plus `?? briefings/lalitana.md`. If anything else appears, stop and report it; do not commit unknown files.

- [ ] **Step 2: Commit modified files and the untracked skills and docs**

```bash
git add -u
git add src/djangopress/skills/analyze-site src/djangopress/skills/improve-site \
        docs/plans/2026-04-11-schema-org-automation-design.md \
        docs/plans/2026-05-07-editor-v2-image-discovery-design.md \
        docs/plans/2026-05-07-editor-v2-image-discovery-plan.md
git commit -m "chore: baseline of pending skill, template and editor changes

Includes the design-first/translate-last principle in generate-site,
the marquee pattern in the HTML reference, create_version() in edit-site,
and the analyze-site and improve-site skills."
```

- [ ] **Step 3: Verify**

Run: `git status --short`
Expected: only `?? briefings/lalitana.md`.

---

### Task 1: `check_site` command — page-level checks

**Files:**
- Create: `src/djangopress/core/management/commands/check_site.py`
- Test: `src/djangopress/core/tests/test_check_site.py`

**Interfaces:**
- Produces: `SiteChecker(only=None)` with `.run() -> list[dict]` where each dict is `{'check': str, 'message': str}`; module constants `CHECK_NAMES` (tuple of all check names), `FORBIDDEN_TAGS`, `SECTION_NAME_RE`, `TEMPLATE_DEFAULT_COLORS`; helper `structural_signature(html) -> list[str]`. Task 2 adds more methods to the same class and the CLI options.
- Consumes: `SiteSettings.load()`, `SiteSettings.get_default_language()`, `SiteSettings.get_language_codes()`, `Page.html_content_i18n`, `Page.is_active`.

- [ ] **Step 1: Write the failing tests**

Create `src/djangopress/core/tests/test_check_site.py`:

```python
"""Tests for the check_site management command."""

import json

from django.test import TestCase

from djangopress.core.models import GlobalSection, MenuItem, Page, SiteSettings


VALID_HOME_HTML = """
<section data-section="hero" id="hero">
  <h1>Bem-vindo</h1>
  <a href="#contact">Contactos</a>
  <a href="/pt/sobre/">Sobre</a>
  <img src="/media/site_images/hero.jpg" alt="Sala">
</section>
<section data-section="contact" id="contact">
  <p>Ligue-nos</p>
</section>
"""

VALID_JSONLD = (
    '<script type="application/ld+json">'
    '{"@context": "https://schema.org", "@type": "LocalBusiness", '
    '"name": "Casa", "telephone": "+351 289 000 000", "address": "Rua Um, Faro"}'
    '</script>'
)


def make_valid_site():
    """Build the smallest site that passes every check. Returns the home page."""
    Page.objects.all().delete()
    MenuItem.objects.all().delete()
    s = SiteSettings.load()
    s.enabled_languages = [{'code': 'pt', 'name': 'Português'}]
    s.default_language = 'pt'
    s.gcs_folder = 'test-site'
    s.site_name_i18n = {'pt': 'Casa de Teste'}
    s.primary_color = '#c05b3e'
    s.secondary_color = '#3e6b73'
    s.background_color = '#f5f0e8'
    s.text_color = '#2b2520'
    s.custom_head_code = VALID_JSONLD
    home = Page.objects.create(
        title_i18n={'pt': 'Início'},
        slug_i18n={'pt': 'home'},
        html_content_i18n={'pt': VALID_HOME_HTML},
        meta_title_i18n={'pt': 'Casa de Teste'},
        meta_description_i18n={'pt': 'Descrição'},
        is_active=True,
        sort_order=0,
    )
    s.homepage = home
    s.save()
    for key, name, section_type in (
        ('main-header', 'Main Header', 'header'),
        ('main-footer', 'Main Footer', 'footer'),
    ):
        gs, _ = GlobalSection.objects.get_or_create(
            key=key, defaults={'name': name, 'section_type': section_type},
        )
        gs.html_template_i18n = {'pt': '<header><nav>x</nav></header>'}
        gs.is_active = True
        gs.save()
    MenuItem.objects.create(label_i18n={'pt': 'Início'}, page=home, is_active=True)
    return home


def run_checks(only=None):
    from djangopress.core.management.commands.check_site import SiteChecker
    return SiteChecker(only=only).run()


def check_names(failures):
    return sorted({f['check'] for f in failures})


class ValidSiteTest(TestCase):
    def test_valid_site_has_no_failures(self):
        make_valid_site()
        self.assertEqual(run_checks(), [])


class SettingsCheckTest(TestCase):
    def setUp(self):
        self.home = make_valid_site()

    def test_missing_homepage(self):
        s = SiteSettings.load()
        s.homepage = None
        s.save()
        self.assertIn('settings', check_names(run_checks(only=['settings'])))

    def test_template_default_colors(self):
        s = SiteSettings.load()
        s.primary_color = '#1E3A8A'
        s.secondary_color = '#64748B'
        s.background_color = '#FFFFFF'
        s.text_color = '#1F2937'
        s.save()
        failures = run_checks(only=['settings'])
        self.assertTrue(any('template default' in f['message'] for f in failures))

    def test_default_site_name(self):
        s = SiteSettings.load()
        s.site_name_i18n = {'pt': 'DjangoPress'}
        s.save()
        self.assertIn('settings', check_names(run_checks(only=['settings'])))


class PageHtmlCheckTest(TestCase):
    def setUp(self):
        self.home = make_valid_site()

    def _set_html(self, html):
        self.home.html_content_i18n = {'pt': html}
        self.home.save()

    def test_empty_html(self):
        self._set_html('')
        self.assertIn('page-html', check_names(run_checks()))

    def test_forbidden_tag(self):
        self._set_html('<section data-section="hero" id="hero"><nav>x</nav></section>')
        self.assertIn('forbidden-tag', check_names(run_checks()))

    def test_section_without_data_section(self):
        self._set_html('<section id="hero"><p>x</p></section>')
        self.assertIn('sections', check_names(run_checks()))

    def test_section_id_mismatch(self):
        self._set_html('<section data-section="hero" id="top"><p>x</p></section>')
        self.assertIn('sections', check_names(run_checks()))

    def test_duplicate_section(self):
        self._set_html(
            '<section data-section="hero" id="hero"><p>x</p></section>'
            '<section data-section="hero" id="hero"><p>y</p></section>'
        )
        self.assertIn('sections', check_names(run_checks()))

    def test_placeholder_image(self):
        self._set_html(
            '<section data-section="hero" id="hero">'
            '<img src="https://placehold.co/600x400" alt="x"></section>'
        )
        self.assertIn('images', check_names(run_checks()))

    def test_image_without_alt(self):
        self._set_html(
            '<section data-section="hero" id="hero"><img src="/media/a.jpg"></section>'
        )
        self.assertIn('images', check_names(run_checks()))

    def test_aria_hidden_image_with_alt(self):
        self._set_html(
            '<section data-section="hero" id="hero">'
            '<img src="/media/a.jpg" alt="dup" aria-hidden="true"></section>'
        )
        self.assertIn('images', check_names(run_checks()))

    def test_dangling_anchor(self):
        self._set_html(
            '<section data-section="hero" id="hero"><a href="#nowhere">x</a></section>'
        )
        self.assertIn('anchors', check_names(run_checks()))

    def test_inactive_page_is_skipped(self):
        Page.objects.create(
            title_i18n={'pt': 'Rascunho'}, slug_i18n={'pt': 'rascunho'},
            html_content_i18n={'pt': '<nav>bad</nav>'}, is_active=False,
        )
        self.assertNotIn('forbidden-tag', check_names(run_checks()))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py test djangopress.core.tests.test_check_site -v 1 2>&1 | grep -E "^(Ran|OK|FAILED|ERROR|ModuleNotFoundError)"`
Expected: errors mentioning `No module named 'djangopress.core.management.commands.check_site'`.

- [ ] **Step 3: Write the command with the page-level checks**

Create `src/djangopress/core/management/commands/check_site.py`:

```python
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

# Internal paths that legitimately have no language prefix.
UNPREFIXED_ALLOWED = ('/media/', '/static/', '/backoffice/', '/admin/')

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
                    self._check_internal_link(label, href)

    def _check_internal_link(self, label, href):
        if not href.startswith('/') or href.startswith('//') or href == '/':
            return
        if href.startswith(UNPREFIXED_ALLOWED):
            return
        for code in self.lang_codes:
            if href == f'/{code}' or href.startswith(f'/{code}/'):
                return
        self.fail('links', f'{label}: href {href!r} is missing the language prefix (expected /{self.default_lang}/...)')

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
            objects = data if isinstance(data, list) else data.get('@graph', [data])
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py test djangopress.core.tests.test_check_site -v 1 2>&1 | grep -E "^(Ran|OK|FAILED|ERROR)"`
Expected: `Ran 14 tests` then `OK`.

If `test_valid_site_has_no_failures` fails, print the failures list in the test to see which check the fixture trips, and fix the fixture (not the check) unless the check is wrong against the spec table.

- [ ] **Step 5: Run the command against a real site**

Run: `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py check_site; echo "exit=$?"`
Expected: either `OK — all checks passed` with `exit=0`, or `FAIL — N problem(s):` followed by bracketed lines and `exit=1`. No traceback. Record the output in the task report; it is information about that site, not a defect in the command.

- [ ] **Step 6: Commit**

```bash
git add src/djangopress/core/management/commands/check_site.py src/djangopress/core/tests/test_check_site.py
git commit -m "feat: check_site management command with page-level checks

Generic form of the O Marisco verification harness: settings, page HTML
conventions, images, anchors, internal-link language prefix, meta, home
slug, cross-language DOM parity, global sections, menu and JSON-LD."
```

---

### Task 2: `check_site` — remaining check tests and CLI options

**Files:**
- Modify: `src/djangopress/core/tests/test_check_site.py` (append)
- Modify: `src/djangopress/core/management/commands/check_site.py` (only if a test exposes a defect)

**Interfaces:**
- Consumes: `SiteChecker`, `structural_signature` from Task 1.
- Produces: verified `--json` and `--only` behaviour that the skills in Tasks 5 and 6 rely on:
  `python manage.py check_site --json` → `{"ok": bool, "failures": [{"check": str, "message": str}]}`;
  `--only a,b` runs only those checks; unknown names raise `CommandError`.

- [ ] **Step 1: Append the tests**

Append to `src/djangopress/core/tests/test_check_site.py`:

```python
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError


class LinksCheckTest(TestCase):
    def setUp(self):
        self.home = make_valid_site()

    def _set_html(self, html):
        self.home.html_content_i18n = {'pt': html}
        self.home.save()

    def test_unprefixed_internal_link_fails(self):
        self._set_html('<section data-section="hero" id="hero"><a href="/reservas/">x</a></section>')
        failures = run_checks(only=['links'])
        self.assertEqual(check_names(failures), ['links'])
        self.assertIn('/reservas/', failures[0]['message'])

    def test_prefixed_link_passes(self):
        self._set_html('<section data-section="hero" id="hero"><a href="/pt/reservas/">x</a><a href="/pt/#hero">y</a></section>')
        self.assertEqual(run_checks(only=['links']), [])

    def test_media_static_and_external_links_pass(self):
        self._set_html(
            '<section data-section="hero" id="hero">'
            '<a href="/media/menu.pdf">m</a><a href="/static/x.css">s</a>'
            '<a href="https://example.com/">e</a><a href="/">root</a></section>'
        )
        self.assertEqual(run_checks(only=['links']), [])


class HomeCheckTest(TestCase):
    def setUp(self):
        self.home = make_valid_site()

    def test_home_slug_must_be_home_in_every_language(self):
        self.home.slug_i18n = {'pt': 'home', 'en': 'inicio'}
        self.home.save()
        failures = run_checks(only=['home'])
        self.assertEqual(check_names(failures), ['home'])
        self.assertIn("'inicio'", failures[0]['message'])

    def test_homepage_fk_must_point_at_home(self):
        other = Page.objects.create(
            title_i18n={'pt': 'Outra'}, slug_i18n={'pt': 'outra'},
            html_content_i18n={'pt': VALID_HOME_HTML},
            meta_title_i18n={'pt': 'x'}, meta_description_i18n={'pt': 'y'}, is_active=True,
        )
        s = SiteSettings.load()
        s.homepage = other
        s.save()
        self.assertIn('home', check_names(run_checks(only=['home'])))

    def test_no_home_page(self):
        self.home.slug_i18n = {'pt': 'inicio'}
        self.home.save()
        self.assertIn('home', check_names(run_checks(only=['home'])))


class MetaCheckTest(TestCase):
    def test_missing_meta_description(self):
        home = make_valid_site()
        home.meta_description_i18n = {}
        home.save()
        self.assertEqual(check_names(run_checks(only=['meta'])), ['meta'])


class DomParityCheckTest(TestCase):
    def setUp(self):
        self.home = make_valid_site()

    def test_identical_structure_passes(self):
        en = VALID_HOME_HTML.replace('Bem-vindo', 'Welcome').replace('/pt/sobre/', '/en/about/')
        self.home.html_content_i18n = {'pt': VALID_HOME_HTML, 'en': en}
        self.home.save()
        self.assertEqual(run_checks(only=['dom-parity']), [])

    def test_extra_element_fails(self):
        en = VALID_HOME_HTML.replace('<p>Ligue-nos</p>', '<p>Call us</p><p>extra</p>')
        self.home.html_content_i18n = {'pt': VALID_HOME_HTML, 'en': en}
        self.home.save()
        failures = run_checks(only=['dom-parity'])
        self.assertEqual(check_names(failures), ['dom-parity'])
        self.assertIn('elements', failures[0]['message'])

    def test_changed_class_fails(self):
        en = VALID_HOME_HTML.replace('<h1>', '<h1 class="text-xl">')
        self.home.html_content_i18n = {'pt': VALID_HOME_HTML, 'en': en}
        self.home.save()
        self.assertEqual(check_names(run_checks(only=['dom-parity'])), ['dom-parity'])


class GlobalSectionCheckTest(TestCase):
    def test_inactive_footer_fails(self):
        make_valid_site()
        gs = GlobalSection.objects.get(key='main-footer')
        gs.is_active = False
        gs.save()
        failures = run_checks(only=['global-section'])
        self.assertEqual(check_names(failures), ['global-section'])
        self.assertIn('main-footer', failures[0]['message'])


class MenuCheckTest(TestCase):
    def test_no_menu_items_fails(self):
        make_valid_site()
        MenuItem.objects.all().delete()
        self.assertEqual(check_names(run_checks(only=['menu'])), ['menu'])

    def test_item_linking_inactive_page_fails(self):
        home = make_valid_site()
        home.is_active = False
        home.save()
        failures = run_checks(only=['menu'])
        self.assertEqual(check_names(failures), ['menu'])


class SeoCheckTest(TestCase):
    def setUp(self):
        make_valid_site()

    def _set_head(self, code):
        s = SiteSettings.load()
        s.custom_head_code = code
        s.save()

    def test_missing_jsonld_fails(self):
        self._set_head('')
        self.assertEqual(check_names(run_checks(only=['seo'])), ['seo'])

    def test_unparseable_jsonld_fails(self):
        self._set_head('<script type="application/ld+json">{not json</script>')
        failures = run_checks(only=['seo'])
        self.assertIn('does not parse', failures[0]['message'])

    def test_restaurant_missing_required_keys(self):
        self._set_head('<script type="application/ld+json">{"@type": "Restaurant", "name": "X"}</script>')
        failures = run_checks(only=['seo'])
        missing = {f['message'].split("'")[1] for f in failures}
        self.assertEqual(missing, {'telephone', 'address', 'geo', 'openingHoursSpecification', 'servesCuisine', 'priceRange'})

    def test_unknown_type_only_needs_to_parse(self):
        self._set_head('<script type="application/ld+json">{"@type": "WebSite", "name": "X"}</script>')
        self.assertEqual(run_checks(only=['seo']), [])


class CommandInterfaceTest(TestCase):
    def test_json_output_ok(self):
        make_valid_site()
        out = StringIO()
        call_command('check_site', '--json', stdout=out)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload, {'ok': True, 'failures': []})

    def test_failure_exits_1_with_named_lines(self):
        make_valid_site()
        MenuItem.objects.all().delete()
        out = StringIO()
        with self.assertRaises(SystemExit) as ctx:
            call_command('check_site', stdout=out)
        self.assertEqual(ctx.exception.code, 1)
        text = out.getvalue()
        self.assertIn('FAIL — 1 problem(s):', text)
        self.assertIn('[menu] no active MenuItems', text)

    def test_only_restricts_checks(self):
        make_valid_site()
        MenuItem.objects.all().delete()
        out = StringIO()
        call_command('check_site', '--only', 'settings,seo', '--json', stdout=out)
        self.assertTrue(json.loads(out.getvalue())['ok'])

    def test_unknown_check_name(self):
        make_valid_site()
        with self.assertRaises(CommandError):
            call_command('check_site', '--only', 'nope')
```

- [ ] **Step 2: Run the tests**

Run: `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py test djangopress.core.tests.test_check_site -v 1 2>&1 | grep -E "^(Ran|OK|FAILED|ERROR|FAIL:|AssertionError)"`
Expected: `Ran 35 tests` then `OK`.

If a test fails, the check is wrong, not the test, unless the test contradicts the spec table. Fix the check in `check_site.py` and re-run. Two known traps: `SiteSettings.homepage` is a `ForeignKey`, so compare `homepage_id`; and `call_command` with `SystemExit` needs the `assertRaises(SystemExit)` block, not `CommandError`.

- [ ] **Step 3: Run the whole core test package to make sure nothing else broke**

Run: `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py test djangopress.core.tests -v 1 2>&1 | grep -E "^(Ran|OK|FAILED)"`
Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add src/djangopress/core/tests/test_check_site.py src/djangopress/core/management/commands/check_site.py
git commit -m "test: cover links, home, meta, dom-parity, menu, seo and CLI options of check_site"
```

---

### Task 3: Rulings in `djangopress-html-reference`

**Files:**
- Modify: `src/djangopress/skills/djangopress-html-reference/SKILL.md` (insert a new `## ` section before `## Database Structure`, currently line 143; append one paragraph to `## Temporary File Pattern`, currently ending at line 393)

**Interfaces:**
- Produces: the section heading `## Rulings Every Site Hits`, referenced by name from the `generate-site` and `create-briefing` skills in Tasks 5 and 6.

- [ ] **Step 1: Insert the rulings section**

Insert the following block immediately before the line `## Database Structure`:

```markdown
## Rulings Every Site Hits

Verified once, paid for once. Each of these was rediscovered inside a site session before it was written down here. Do not re-derive them.

**1. Internal links carry the language prefix — including the default language.**
`i18n_patterns` prefixes every language, so `Page.get_absolute_url('pt')` is `/pt/sobre/` and the site root `/` redirects to `/pt/`. Page HTML is raw, with no `{% url %}`, so links are literal:

```html
<!-- wrong -->            <!-- right -->
<a href="/reservas/">     <a href="/pt/reservas/">
<a href="/#menu">         <a href="/pt/#menu">
```

In the English copy of the page the same link is `/en/reservations/`. Header and footer are Django templates and keep using `{% url 'core:page' slug='...' %}`. `manage.py check_site` reports violations under `[links]`.

**2. Version before you mutate, with the model's own method.**
`page.create_version(change_summary='...')` and `section.create_version(change_summary='...')` both exist. Never create `ContentVersion` or `PageVersion` rows by hand.

**3. `SiteImage.key` must be ASCII.**
`django.utils.text.slugify` keeps accented letters, so "Caril de Camarão" becomes `dish-caril-de-camarão` and later lookups by the ASCII form miss. Fold first:

```python
import unicodedata
from django.utils.text import slugify
ascii_name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode()
key = f'dish-{slugify(ascii_name)}'
```

**4. Print HTML to PDF with the bundled Chromium, not `require('playwright')`.**
`require('playwright')` does not resolve from a temp directory (the npx cache is not on the module path). Use the binary Playwright already installed:

```bash
CHROME=$(ls -d ~/Library/Caches/ms-playwright/chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium | tail -1)
"$CHROME" --headless --disable-gpu --no-pdf-header-footer --virtual-time-budget=10000 \
  --print-to-pdf=/tmp/out.pdf /tmp/in.html
```

`--virtual-time-budget` lets Google Fonts load before the PDF is written; without it the PDF prints in a fallback font.

**5. Always the site's own venv.**
`.venv/bin/python manage.py ...`. A script under `scripts/` run directly needs the repo root on `sys.path`, so either run it with `PYTHONPATH=.` or put this at the top:

```python
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

**6. No git worktrees for site work.**
`.env` and `.venv` are git-ignored, so a fresh worktree cannot run `manage.py`. Work on a branch in the existing checkout.

**7. Verification is `python manage.py check_site`.**
It encodes every convention on this page as a named check (`sections`, `links`, `images`, `dom-parity`, `home`, `seo`, ...). Run it after every save with `--only <checks relevant to what you changed>` and in full before declaring a site done. Do not write per-site verification scripts.

```

- [ ] **Step 2: Append to the Temporary File Pattern section**

Append this paragraph at the end of the file, after the line `Same pattern for GlobalSections using \`GlobalSection.html_template_i18n\`.`:

```markdown

After every save, verify what you touched:

```bash
python manage.py check_site --only sections,images,anchors,links,forbidden-tag   # after a page save
python manage.py check_site --only global-section                                # after a header/footer save
python manage.py check_site                                                      # before saying a site is done
```
```

- [ ] **Step 3: Verify the Markdown structure**

Run: `grep -n "^## " src/djangopress/skills/djangopress-html-reference/SKILL.md`
Expected: `## Rulings Every Site Hits` appears immediately before `## Database Structure`, and the other headings are unchanged.

- [ ] **Step 4: Commit**

```bash
git add src/djangopress/skills/djangopress-html-reference/SKILL.md
git commit -m "docs(skills): record the rulings every site hits in the HTML reference"
```

---

### Task 4: Briefing template

**Files:**
- Modify: `briefings/TEMPLATE.md`
- Modify: `site_template/briefings/TEMPLATE.md` (identical copy)

**Interfaces:**
- Produces: section names `## Open Questions`, `## Existing Site`, `## Integrations`, `## To Confirm With Client`, and the structured `## Design Preferences` bullets. Tasks 5 and 6 refer to these names verbatim.
- Constraint: `BriefingParser` keys on `business`, `languages`, `contact`, `social media`, `pages`, `header`, `footer`, `design preferences`, `images`, `domain`, `additional notes`. These names do not change.

- [ ] **Step 1: Write the template**

Replace the whole content of `briefings/TEMPLATE.md` with:

```markdown
# [Business Name] — Site Briefing

> One line: what this is (new site / redesign of <url>) and the one-sentence brief.

## Open Questions

Working section written by `/create-briefing` after research and removed when the
briefing is finalized. Five to eight questions only the operator or the client can
answer, each with the proposed default so the build can proceed without an answer.

1. **[Topic].** [Question]? *Proposed: [default].*

## Business

[2-5 paragraphs: what they do, history, target audience, tone of voice, unique
selling points, competitive positioning, reputation (ratings, awards, press).
This becomes `project_briefing` and drives all generation. Polished prose, not bullets.]

## Languages
- Default: [code] ([name])
- Additional: [code] ([name]), ...

## Contact
- Email:
- Phone:
- Address: [single line, or per language as `- pt: ...` / `- en: ...`]
- Google Maps: [embed URL if available]

### Opening hours
[Table or list. Mark "to confirm" if taken from an old site.]

## Social Media
- Instagram:
- Facebook:
- [others: LinkedIn, YouTube, TikTok, Pinterest, WhatsApp, Twitter/X, TripAdvisor]

## Existing Site

[Redesigns only. One row per page of the current site.]

| Current page | Decision | Reason |
|---|---|---|
| / | keep / merge into X / drop | ... |

## Integrations

[Third-party systems to keep, one per line: what, URL, how it is embedded.]

- Reservations: [system] — [URL] — [iframe on /reservas/ | link | none]
- Menu: [PicklyMenu / PDF hosted on site / HTML page]

## Pages

[One entry per page. Describe the sections in order, with the content each holds
and the CTA. "The home page" is not a description.]

- **Home**: 1. Hero — [message, CTAs]. 2. [Section] — [content]. 3. ...
- **About**: ...
- **Contact**: form (reuse the template's `contact` DynamicForm), map, hours.

## Header
[Navigation style, logo placement, CTA button, language switcher, mobile menu.
If omitted, the template's default header is refined, not replaced.]

## Footer
[Columns, links, contact, social icons, copyright.
If omitted, the template's default footer is refined, not replaced.]

## Design Preferences

Required. This section is what keeps the site from looking like a template.

- **Palette** (hex, with roles):
  - Background:
  - Surface (cards, blocks):
  - Text:
  - Accent (CTAs, prices, highlights):
  - Secondary (links, supporting):
  - Dark block (one inverted section):
- **Type pair** (Google Fonts): headings — [font]; body — [font]
- **Corner radius**: [e.g. 4px, 12px, pill]
- **Layout signature**: [one sentence: the recurring compositional idea, e.g.
  "12-column grid with text in 5 columns and image in 6, vertically offset"]
- **Motif**: [one decorative device used consistently, or "none"]
- **Avoid**: [what the local competition does that this site will not]
- **References**: [up to three URLs]

## Images

- **Strategy**: reuse existing | unsplash | ai | mix | skip
- **Sources**: [where existing photos come from: old site, Facebook, PicklyMenu API,
  client folder. See `briefings/<slug>-audit.md` for the inventory.]
- **Constraints**: [largest usable width per group, e.g. "dishes 680px, space 2560px
  (2013)". Decides whether full-bleed photography is allowed.]

## Domain

[GCS folder identifier, lowercase with hyphens, e.g. `o-marisco`. Already set by
`new_site.sh` to the project slug; do not change once media has been uploaded.]

## Additional Notes

[SEO focus keywords, JSON-LD type, legal requirements, seasonal content,
anything out of scope.]

## To Confirm With Client

[Facts the build assumed and the client must confirm before launch.]

- 
```

- [ ] **Step 2: Copy to the site template**

Run: `cp briefings/TEMPLATE.md site_template/briefings/TEMPLATE.md && diff -q briefings/TEMPLATE.md site_template/briefings/TEMPLATE.md && echo identical`
Expected: `identical`.

- [ ] **Step 3: Verify the parser still reads the required sections**

Run from a child site:

```bash
cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python -c "
from djangopress.ai.site_generator import BriefingParser
text = open('/Users/antoniomarante/Documents/djangopress-sites/djangopress/briefings/TEMPLATE.md').read()
parsed = BriefingParser.parse(text)
keys = sorted(parsed['sections'])
print(keys)
for k in ['business','languages','contact','social media','pages','header','footer','design preferences','images','domain','additional notes']:
    assert k in keys, k
print('parser OK')
"
```

Expected: the key list printed and `parser OK`. Note the parser lowercases `## Open Questions` to `open questions`; it is simply an extra key.

- [ ] **Step 4: Commit**

```bash
git add briefings/TEMPLATE.md site_template/briefings/TEMPLATE.md
git commit -m "docs(briefing): structured, required design direction; open questions, existing site, integrations sections"
```

---

### Task 5: `create-briefing` as intake

**Files:**
- Modify: `src/djangopress/skills/create-briefing/SKILL.md` (full rewrite, single `Write`)

**Interfaces:**
- Consumes: `briefings/TEMPLATE.md` section names from Task 4.
- Produces: `briefings/<slug>.md` (final briefing) and `briefings/<slug>-audit.md` (research, with an image inventory table). The build skill (Task 6) reads both.

- [ ] **Step 1: Write the skill**

Replace the whole content of `src/djangopress/skills/create-briefing/SKILL.md` with:

````markdown
---
name: create-briefing
description: Intake for a new site or a redesign. Researches the client (existing site, socials, reviews, integrations, image inventory) without asking anything, writes a complete draft briefing plus a short list of questions only the operator can answer, then finalizes the briefing from the answers. Use when starting any site, with a URL, a client document, or both.
argument-hint: [url] [path/to/document] — any combination, or nothing
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, AskUserQuestion, WebFetch, WebSearch
---

# Site Intake → Briefing

You produce `briefings/<slug>.md` in the format of `briefings/TEMPLATE.md`, good enough to build from as is, plus `briefings/<slug>-audit.md` with everything you found. The argument is: `$ARGUMENTS`

**Two rules shape this skill.** Research never asks questions. Questions come once, in a block, at the end, each with a proposed default. This is what lets several intakes run in parallel while the operator is away, and makes a single intake faster too.

---

## Phase 0: Detect the mode

Parse `$ARGUMENTS`:

- A token containing `http`, `www.` or ending in a TLD (`.pt`, `.com`, ...) is the **URL** of the existing site.
- A token that is an existing file path (`.md`, `.txt`, `.pdf`, `.docx`, `.html`) is the **document** from the client or the operator.
- Anything else is the business name.

| Inputs | Mode | What the draft proposes | What the questions target |
|---|---|---|---|
| URL only | Redesign | Keep the current structure, refresh design | What changes: pages to merge or drop, content to update, design direction |
| Document only | New site | Structure from the document, filling gaps by industry convention | Gaps in the document, design direction |
| URL + document | Redesign with brief | Crawl as facts, document as intent | Conflicts between the two |
| Nothing | Ask once | — | — |

With nothing, use one `AskUserQuestion`: "Business name, and a URL or document if there is one?" Then continue in the resulting mode. Running non-interactively (the tool is unavailable), print the same question and stop; the next message will carry the answer.

Compute `<slug>` from the business name: lowercase, ASCII-folded, hyphens (`"O Marisco"` → `o-marisco`). If the project directory name already looks like a slug of this business, use the directory name so it matches `SiteSettings.gcs_folder`.

Read the site's current state so the draft does not propose what already exists:

```bash
python manage.py shell -c "
from djangopress.core.models import SiteSettings, Page, GlobalSection, DynamicForm
s = SiteSettings.load()
print('gcs_folder:', s.gcs_folder); print('languages:', s.get_language_codes())
print('pages:', [(p.id, p.slug_i18n) for p in Page.objects.all()])
print('sections:', list(GlobalSection.objects.values_list('key', flat=True)))
print('forms:', list(DynamicForm.objects.values_list('slug', flat=True)))
"
```

---

## Phase 1: Research — no questions

Do all of it before writing anything for the operator. A fetch that fails is noted in the audit and skipped; never stop on a failed fetch, never ask for help with one.

### 1a. Crawl the existing site (URL modes)

1. `WebFetch` the homepage. Extract business name, tagline, what they do, contact, social links, hours, awards, visual style.
2. Collect every internal link from the navigation (including dropdowns), hero CTAs and footer. Drop anchors, `mailto:`, `tel:`, files. Deduplicate.
3. `WebFetch` every internal page, in parallel. Per page record: title, URL, sections in order with a one-line content summary, forms, galleries, testimonials, prices.
4. Record the header and footer structure.

### 1b. Integrations

Any link to a reservation system (ResDiary, TheFork, OpenTable, Bookeo), a menu service (PicklyMenu), a booking engine, or a payment/ticketing provider is an **integration to keep**. Record the exact URL and how it is embedded today (link, iframe, widget script). For PicklyMenu, note whether the menu can be extracted (the API returns JSON with dishes, prices and photo URLs) and, if so, extract it to `briefings/<slug>-menu.json`.

### 1c. Socials and reputation

`WebFetch` the Facebook and Instagram pages found. `WebSearch` for `"<business name>" <city>`: Google rating and review count, TripAdvisor rating and rank, awards (PME Líder, Michelin, press), Google Maps listing.

### 1d. Image inventory

List every image found on the site and socials with URL and pixel dimensions. Fetch dimensions with:

```bash
python -c "
import sys, urllib.request, io
from PIL import Image
for url in sys.argv[1:]:
    try:
        data = urllib.request.urlopen(url, timeout=15).read()
        im = Image.open(io.BytesIO(data)); print(url, im.size[0], im.size[1])
    except Exception as e: print(url, 'ERR', e)
" <url1> <url2> ...
```

Group by subject (dishes, space, exterior, team, products). For each group record the count and the largest width. This decides whether the build may use full-bleed photography: under ~1600px wide, it may not.

### 1e. The document (document modes)

Read it completely. Map every statement onto a template section. Statements that fit nowhere go to `## Additional Notes`. Where the document and the crawl disagree, the document is intent and the crawl is fact; record both and make it a question.

### 1f. Write the audit

Write `briefings/<slug>-audit.md`:

```markdown
# <Business> — Site Audit

> From <URL and/or document> on <date>

## Business Overview
## Contact Information
## Social Media and Reputation
## Integrations
## Site Map
### Navigation
### Pages
#### <Page> (<path>)
**Sections:** 1. ... 2. ...
**Forms / galleries / prices:** ...
### Footer
## Image Inventory
| Group | Count | Largest width | Source | Example URL |
|---|---|---|---|---|
## Design Observations
## Fetch failures
```

---

## Phase 2: Draft briefing and the question list

Read `briefings/TEMPLATE.md`. Write `briefings/<slug>.md` following it exactly, **every section filled with a concrete proposal** — no placeholders, no "TBD". The build skill must be able to run from this draft unchanged.

Rules for the draft:

- **Business** is the most important section: three to five paragraphs of polished prose from the audit and the document. Reputation with numbers. Tone of voice stated. Competitive positioning named.
- **Existing Site** (URL modes): one row per current page with keep / merge / drop and a reason.
- **Integrations**: from 1b, with the embed method proposed.
- **Pages**: sections in order per page, with the CTA. For a one-pager, list the anchor sections.
- **Design Preferences**: a full proposal. Derive the palette from the business and the place, not from the old site's colors unless they are a brand asset. Name the type pair. State the layout signature in one sentence. Fill **Avoid** with what the direct competition does (look at two or three competitors' sites in the same street, marina or niche).
- **Images**: strategy from the inventory. State the constraints line from the largest widths.
- **Additional Notes**: SEO focus phrases (two or three, in the default language and in English), the JSON-LD `@type`.
- **Domain**: the current `gcs_folder`. Never propose changing it.

Then write `## Open Questions` right after the title. Five to eight questions. Each is something only the operator or the client can answer, carries the proposed default, and would change the build if answered differently. Never ask what the research already answered. Typical questions:

- Pages to merge or drop (redesigns)
- Integration to keep vs. replace (PicklyMenu vs. PDF, reservation widget)
- Languages beyond the default
- Contact email when none is published
- Whether the old photos are acceptable or a shoot is planned
- A design direction choice when two are plausible (offer both, propose one)
- Anything the document and the crawl disagree on

Print the questions in the console, numbered, with the proposed defaults, and end the turn:

```
Draft briefing: briefings/<slug>.md
Audit: briefings/<slug>-audit.md

Open questions (reply with the numbers you want to change; unanswered ones keep the proposal):
1. ...
```

**When `AskUserQuestion` is available** and the operator is present, ask them there instead, in batches of up to four per call, each with the proposed default as the first option. Then continue to Phase 3 in the same turn.

---

## Phase 3: Apply answers and finalize

For each answer, edit the relevant section of the briefing. Questions left unanswered keep the proposal. Anything that still depends on the client moves to `## To Confirm With Client`. Delete the `## Open Questions` section.

Re-read the whole file once. Check: every `## ` section from the template is present; Design Preferences has every bullet filled; Pages describe sections, not pages; Domain equals `gcs_folder`.

Show a short summary (pages, languages, design direction in one line, integrations) and offer the next step:

```
AskUserQuestion:
Question: "Briefing finalizado. Avançar com o build?"
Options:
- "Sim — /generate-site briefings/<slug>.md" (Recommended)
- "Não — fico por aqui"
```

If yes, invoke the `generate-site` skill with `briefings/<slug>.md`. Non-interactively, print the command and stop.

---

## Key principles

- **Research first, ask last, ask once.** The operator's time is the scarce resource.
- **Every question carries its default.** A briefing with open questions is still buildable.
- **The draft is complete.** If you would leave a section blank, propose something and make it a question instead.
- **Facts vs. intent.** Crawl is fact, document is intent, operator answer wins over both.
- **Output must parse.** `## ` section names exactly as in `briefings/TEMPLATE.md`.
````

- [ ] **Step 2: Verify the frontmatter and headings**

Run: `head -6 src/djangopress/skills/create-briefing/SKILL.md && grep -c "^## Phase" src/djangopress/skills/create-briefing/SKILL.md`
Expected: frontmatter with `name: create-briefing`, and `4` phase headings.

- [ ] **Step 3: Check the symlink still resolves in a child site**

Run: `ls -la /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa/.claude/skills/create-briefing && head -3 /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa/.claude/skills/create-briefing/SKILL.md`
Expected: a symlink into the engine, and the new frontmatter.

- [ ] **Step 4: Commit**

```bash
git add src/djangopress/skills/create-briefing/SKILL.md
git commit -m "feat(skills): create-briefing as intake — research first, one block of questions with defaults"
```

---

### Task 6: `generate-site` as the unattended build

**Files:**
- Modify: `src/djangopress/skills/generate-site/SKILL.md` (full rewrite, single `Write`)

**Interfaces:**
- Consumes: `briefings/<slug>.md` and `briefings/<slug>-audit.md` from Task 5; `python manage.py check_site [--only ...] [--json]` from Tasks 1–2; the `edit-site` skill's sections `Create Page`, `Edit Header/Footer (GlobalSections)`, `Rebuild menu from pages`, `Use real images from media library`, `Update SEO metadata for a page`, `Translations`; the HTML reference section `Rulings Every Site Hits` from Task 3.
- Produces: `docs/build-report.md`, `docs/screenshots/<page>-<width>.png`, a commit on the site's current branch.

- [ ] **Step 1: Write the skill**

Replace the whole content of `src/djangopress/skills/generate-site/SKILL.md` with:

````markdown
---
name: generate-site
description: Unattended build of a DjangoPress site from a finalized briefing — settings, design guide, pages in the default language, header, footer, menu, SEO, verified by `manage.py check_site` and screenshots, ending in a build report. Also runs the deferred translation pass on an already built site. Never asks questions.
argument-hint: briefings/<slug>.md
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, Agent
---

# Site Build

You build a complete DjangoPress site from `$ARGUMENTS` (a briefing file) without asking anything, and you prove it is done with `python manage.py check_site` and screenshots. HTML conventions come from `djangopress-html-reference`; the save recipes come from `edit-site`. Read both before Phase 2.

**Never call `AskUserQuestion`; it is not in your tools.** When the briefing is silent, take the most conventional choice for the business type and record it under "Assumptions" in the build report. The operator reviews assumptions afterwards with `edit-site`.

## Core principle: design first, translate last

Build and iterate in the default language only. Other languages stay absent from every `*_i18n` field until the translation pass (Phase 9), which runs only on an already built site, once design is signed off. Brand names that do not translate (`site_name_i18n`) may be written for all languages at once.

## Two entry points

- **Fresh site** (no page other than the template's privacy page): run Phases 0–8. Stop after Phase 8.
- **Built site, translation requested** (the operator asked for translation, or ran this skill again on a site that already passes `check_site` in the default language): run Phase 9 only.

Decide by reading the state in Phase 0.

---

## Phase 0: Pre-flight

```bash
test -f .env && echo "ENV OK" || echo "ENV MISSING"
.venv/bin/python -c "import djangopress; print('djangopress', djangopress.__version__ if hasattr(djangopress,'__version__') else 'ok')"
.venv/bin/python manage.py migrate --check >/dev/null 2>&1 && echo "MIGRATIONS OK" || echo "MIGRATIONS PENDING"
.venv/bin/python manage.py check_site --json
```

Read the briefing, the audit (`briefings/<slug>-audit.md`) if it exists, and the menu JSON if it exists. Then read the current state:

```bash
.venv/bin/python manage.py shell -c "
from djangopress.core.models import SiteSettings, Page, GlobalSection, MenuItem, DynamicForm, SiteImage
s = SiteSettings.load()
print('gcs_folder:', s.gcs_folder, '| languages:', s.get_language_codes(), '| default:', s.get_default_language())
print('homepage:', s.homepage_id, '| design_guide:', len(s.design_guide or ''))
for p in Page.objects.all(): print('page', p.id, p.slug_i18n, list((p.html_content_i18n or {}).keys()))
print('sections:', list(GlobalSection.objects.values_list('key','is_active')))
print('menu:', MenuItem.objects.count(), '| forms:', list(DynamicForm.objects.values_list('slug', flat=True)), '| images:', SiteImage.objects.count())
"
```

Facts to hold: the template already created a privacy page (`sort_order=999`), `main-header` and `main-footer` with a default layout, and a `contact` DynamicForm. Refine them; never recreate them. `gcs_folder` is already the project slug; never change it.

Create a branch for the build if you are on `main` with a clean tree: `git checkout -b build-$(date +%Y%m%d)`. If the tree is dirty, stay where you are.

---

## Phase 1: Settings

Follow `edit-site` → *Settings* → *Update site identity / contact / social / design system*, in one shell call, from the briefing:

- `enabled_languages` = every language in the briefing (the full set, even though content is default-only for now); `default_language`.
- `site_name_i18n` for all languages (brand), `site_description_i18n` default only.
- `project_briefing` = the Business section verbatim.
- Contact, social URLs, `whatsapp_number` if any.
- Colors from Design Preferences: `background_color`, `text_color`, `primary_color` (accent), `secondary_color`, `accent_color`, `heading_color`; `heading_font`, `body_font`; `border_radius_class`, `container_width_class`, `shadow_class`, button colors from the palette.

Verify: `.venv/bin/python manage.py check_site --only settings` may still report `homepage`; everything else under `[settings]` must be gone.

---

## Phase 2: Design guide

Write `SiteSettings.design_guide` **now, before any page**, from Design Preferences. It is the contract every page follows, including the home page. Markdown, 40–80 lines:

- Palette with roles and the exact Tailwind arbitrary-value classes you will use (`bg-[#F5F0E8]`, `text-[#2B2520]`, ...).
- Type: heading font classes, body font, the size scale for h1/h2/h3 at mobile and desktop.
- Layout signature: the grid pattern and how it collapses on mobile.
- Section rhythm: vertical padding, alternation of backgrounds, where the dark block sits.
- Components: button primary/secondary, card, price line, badge, section eyebrow.
- Motif: how and where the decorative device appears.
- Image rules from the Images constraints (max render width per group, `srcset`, no full-bleed if the inventory forbids it).
- Avoid list, copied.

Save it with the `edit-site` settings pattern (`s.design_guide = open('/tmp/dp-design-guide.md').read()`).

---

## Phase 3: Images from the inventory

Only when the briefing's Images strategy is `reuse existing` or `mix` and the audit has an inventory. Download each usable image and register it as a `SiteImage` with an **ASCII key** (`Rulings Every Site Hits` §3), grouped as in the audit: `space-<n>`, `dish-<slug>`, `exterior-<n>`. Storage goes to GCS under `gcs_folder` automatically. Record the key → URL map in `/tmp/dp-images.json` for the page phases.

With `unsplash`, `ai` or `skip`, pages use `https://placehold.co/WxH?text=Label` placeholders with `data-image-name` and `data-image-prompt` as `djangopress-html-reference` describes; `check_site` will report them under `[images]` and the report lists them as open items.

---

## Phase 4: Home page

Write the home page HTML in the default language to `/tmp/dp-page-new-<lang>.html`, following the design guide and the Pages section of the briefing. Then save it with `edit-site` → *Create Page* (steps 4, 6: create, then set as homepage), including `meta_title_i18n` and `meta_description_i18n`.

Internal links are literal with the language prefix: `/pt/reservas/`, `/pt/#menu` (`Rulings` §1).

Verify and fix until clean:

```bash
.venv/bin/python manage.py check_site --only sections,forbidden-tag,images,anchors,links,meta,home
```

Placeholder images are the only acceptable remaining `[images]` lines, and only under the placeholder strategies.

---

## Phase 5: Remaining pages

For every other page in the briefing, the same as Phase 4, **without** the homepage step. Pages are independent once the design guide and the home page exist, so you may dispatch them in parallel with the `Agent` tool, one agent per page, each given: the briefing path, the design guide (read it from settings), the home page HTML as the style reference, the image map, and the exact `check_site --only` line above. Each agent saves its page and reports the page id and its check result. Run the check yourself afterwards; agents' reports are not evidence.

Sequential is fine for three pages or fewer.

---

## Phase 6: Header, footer, menu

1. Menu: `edit-site` → *Menu Management* → *Rebuild menu from pages*, then adjust order and add anchor items for a one-pager (`/pt/#menu`) and the reservations CTA as a CTA item.
2. Header: refine `main-header` per the briefing's Header section with `edit-site` → *Edit Header/Footer*. Keep `{% url %}` tags; keep the language switcher; make the mobile menu work with Alpine.
3. Footer: same for `main-footer`. Contact, hours, social icons, privacy link, copyright.

```bash
.venv/bin/python manage.py check_site --only global-section,menu
```

---

## Phase 7: SEO

- `meta_title_i18n` and `meta_description_i18n` on every page (Phase 4/5 already did; confirm with `--only meta`).
- JSON-LD in `SiteSettings.custom_head_code`: the `@type` from Additional Notes (`Restaurant`, `LocalBusiness`, ...), with the keys `check_site` requires for that type (see `JSONLD_REQUIRED` in the command), hours from the briefing, `geo` from the Maps link, `image` from the inventory.
- `og_image` on the home page from the best space photo when one exists.

```bash
.venv/bin/python manage.py check_site --only seo,meta
```

---

## Phase 8: Full verification, screenshots, report

### 8a. The gate

```bash
.venv/bin/python manage.py check_site
```

Must print `OK — all checks passed`, except `[images]` placeholder lines under a placeholder strategy. Fix anything else before continuing.

### 8b. Screenshots

Start the dev server if it is not running (`.venv/bin/python manage.py runserver 8000 --noreload &`, wait 3s). Capture every page at three widths:

```bash
mkdir -p docs/screenshots
LANG_CODE=<default>
for W in 390 834 1440; do
  for SLUG in home <other-slugs>; do
    PATH_PART=$([ "$SLUG" = home ] && echo "" || echo "$SLUG/")
    playwright-cli screenshot --full-page --viewport-size="$W,900" \
      "http://localhost:8000/$LANG_CODE/$PATH_PART" "docs/screenshots/$SLUG-$W.png" \
    || npx --yes playwright screenshot --full-page --viewport-size="$W,900" \
      "http://localhost:8000/$LANG_CODE/$PATH_PART" "docs/screenshots/$SLUG-$W.png"
  done
done
```

### 8c. Look at every screenshot

Read each PNG. Check this list, and only this list, per screenshot:

1. No horizontal scrollbar at 390.
2. Header legible over the hero at every width.
3. No section that reads as broken: overlapping text, empty band, unstyled list.
4. No image rendered wider than its source width (softness) when the inventory set a limit.
5. Primary CTA visible above the fold at 390 and 1440.
6. Dark or inverted block reads as intentional.
7. Footer complete and not covered by a fixed element.

Fix what fails (edit the page HTML, save, re-run `check_site --only ...`), re-capture the affected pages, and re-check. At most three rounds. Whatever remains goes to the report as an open item.

### 8d. Build report

Write `docs/build-report.md`:

```markdown
# <Site> — Build Report (<date>)

## Result
check_site: OK | FAIL (<n> remaining, listed below)
Pages: <n> in <lang>. Header, footer, menu: done. JSON-LD: <type>.

## Pages
| Page | URL | Sections |
|---|---|---|

## Assumptions taken
- <each decision made where the briefing was silent, one line>

## Open items for review
- <screenshot findings not fixed, placeholder images, client confirmations>

## Screenshots
docs/screenshots/<slug>-<width>.png ...

## Next
- Review in the browser: http://localhost:8000/<lang>/
- Refine: /edit-site <what to change>
- When design is signed off: /generate-site briefings/<slug>.md  → runs the translation pass
- Then: /deploy-site-railway
```

### 8e. Commit

```bash
rm -f /tmp/dp-*.html /tmp/dp-images.json
git add db.sqlite3 docs/ briefings/
git commit -m "Build <site> in <lang> from briefing"
```

No `Co-Authored-By` lines. Print the report's Result and Next sections and stop.

---

## Phase 9: Translation pass (built sites only)

Run only when the site already passes `check_site` in the default language, more than one language is enabled, and the operator asked for translation (explicitly, or by invoking this skill on a built site). Otherwise stop and say the site is ready for design iteration.

For every `Page`, `MenuItem`, `GlobalSection` and the `SiteSettings` i18n fields, fill each target language by mirroring the default-language value with **DOM preserved exactly** — only text nodes and `alt` change; tags, attributes, classes, `id`, `data-section`, `src`, `href` targets stay identical, except internal links which switch prefix (`/pt/reservas/` → `/en/reservations/`) and page slugs which translate (home stays `home`). Follow `edit-site` → *Translations* for the save recipes, one page at a time, with `page.create_version(change_summary='Translation pass')` first.

After each page:

```bash
.venv/bin/python manage.py check_site --only dom-parity,links,home
```

`[dom-parity]` names the first differing element; fix the translated HTML to match the default, never the other way round. When every page passes, run the full `check_site`, re-capture screenshots for the new language, append a "Translation" section to `docs/build-report.md`, and commit:

```bash
git add db.sqlite3 docs/
git commit -m "Add <lang> translations with DOM parity preserved"
```

---

## Error handling

- A shell save fails: read the traceback, fix the HTML or the field name, retry once. Field names are in `djangopress-html-reference` → Database Structure.
- `check_site` keeps failing on the same line after two fixes: stop fixing, record it under Open items, continue.
- Screenshot tooling missing: record "screenshots skipped: <reason>" in the report and continue; the `check_site` gate still applies.
- Any unexpected error: diagnose, fix if it is in your control, otherwise record and continue with the next phase. The build must end with a report even when incomplete.
````

- [ ] **Step 2: Verify size and structure**

Run: `wc -l src/djangopress/skills/generate-site/SKILL.md && grep -n "^## Phase" src/djangopress/skills/generate-site/SKILL.md && grep -c "AskUserQuestion" src/djangopress/skills/generate-site/SKILL.md`
Expected: under 400 lines; ten phase headings (0–9); the `AskUserQuestion` count is `2` (the frontmatter no longer lists it; the two mentions are the prohibition sentences).

- [ ] **Step 3: Verify every cross-reference resolves**

Run:

```bash
for h in "## Create Page" "## Edit Header/Footer (GlobalSections)" "### Rebuild menu from pages" "### Use real images from media library" "### Update SEO metadata for a page" "## Translations" "## Settings"; do
  grep -q "^$h" src/djangopress/skills/edit-site/SKILL.md && echo "OK  $h" || echo "MISSING  $h"
done
grep -q "^## Rulings Every Site Hits" src/djangopress/skills/djangopress-html-reference/SKILL.md && echo "OK  rulings" || echo "MISSING rulings"
```

Expected: every line `OK`.

- [ ] **Step 4: Commit**

```bash
git add src/djangopress/skills/generate-site/SKILL.md
git commit -m "feat(skills): generate-site as unattended build — design guide first, check_site gates, screenshots, build report"
```

---

### Task 7: Documentation, version bump

**Files:**
- Modify: `CLAUDE.md` (engine) — the skills table rows for `/create-briefing` and `/generate-site`, and the "Typical New Site Flow" block
- Modify: `/Users/antoniomarante/Documents/djangopress-sites/djangopress-manager/CLAUDE.md:202-203`
- Modify: `src/djangopress/VERSION` via `bump_version`

**Interfaces:**
- Consumes: the skill descriptions from Tasks 5 and 6.

- [ ] **Step 1: Engine CLAUDE.md**

Run: `grep -n "create-briefing\|generate-site\|check_site" CLAUDE.md`

Update the two skill rows to:

```markdown
| `/create-briefing` | `/create-briefing https://client.pt docs/brief.pdf` | Intake: researches the client without asking, writes a complete draft briefing plus a short list of questions with defaults, finalizes from the answers. |
| `/generate-site` | `/generate-site briefings/my-client.md` | Unattended build in the default language: settings, design guide, pages, header, footer, menu, SEO, verified by `check_site` and screenshots. Re-run on a built site for the translation pass. |
```

In the "Typical New Site Flow" block, replace the flow with:

```
1. /create-briefing <url and/or document>   ← research, answer the question block, briefing.md
2. /generate-site briefings/my-client.md    ← unattended build, ends with docs/build-report.md
3. /edit-site ...                           ← interactive refinement
4. /generate-site briefings/my-client.md    ← translation pass, once design is signed off
5. /deploy-site-railway my-client           ← deploy to Railway (SQLite + Litestream)
```

In the `## Commands` section (line 179 onward), add this line to the code block, directly after the `bump_version` lines:

```
python manage.py check_site                            # verify site conventions (run inside a child site); exit 1 on failures
```

- [ ] **Step 2: Manager CLAUDE.md**

In `/Users/antoniomarante/Documents/djangopress-sites/djangopress-manager/CLAUDE.md`, replace lines 202–203 with:

```markdown
| **generate-site** | `/generate-site briefings/<slug>.md` | Unattended build in the default language, verified by `check_site` + screenshots; re-run for the translation pass | `cd <site.path>` then invoke |
| **create-briefing** | `/create-briefing <url> [document]` | Research first, then one block of questions with defaults, then the final briefing | `cd <site.path>` then invoke |
```

The manager repo is on branch `feature/backup-system` with uncommitted work. Do **not** commit there; leave the edit in the working tree and say so in the task report.

- [ ] **Step 3: Bump the engine version**

Run: `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py bump_version minor && cat /Users/antoniomarante/Documents/djangopress-sites/djangopress/src/djangopress/VERSION`
Expected: `3.6.0`.

- [ ] **Step 4: Commit the engine**

```bash
cd /Users/antoniomarante/Documents/djangopress-sites/djangopress
git add CLAUDE.md src/djangopress/VERSION
git commit -m "docs: intake/build flow in CLAUDE.md; bump version to 3.6.0"
```

- [ ] **Step 5: Final check**

Run: `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py test djangopress.core.tests -v 1 2>&1 | grep -E "^(Ran|OK|FAILED)" && .venv/bin/python manage.py sync_skills --list | grep -E "create-briefing|generate-site"`
Expected: `OK`, and both skills `[linked]`.

---

## Self-review against the spec

- **Component 1 (`check_site`)** → Tasks 1–2. Every row of the spec's check table has a check and a test. `--json` and `--only` covered in `CommandInterfaceTest`.
- **Component 2 (rulings)** → Task 3. Seven rulings, the temp-file paragraph.
- **Component 3 (intake)** → Task 5. Mode table, research phases 1a–1f including the image inventory, draft with Open Questions, answer block, hand-off.
- **Component 4 (build)** → Task 6. No questions, design guide before pages, image import, home first, parallel pages, header/footer/menu, SEO, verification loop with three rounds, report, commit; Phase 9 translation preserved.
- **Component 5 (template)** → Task 4, both copies, parser check.
- **Component 6 (rollout)** → Task 0 baseline, Task 7 docs and bump; O Marisco untouched by the Global Constraints.
- **Type consistency:** `SiteChecker(only=...)`, `.run()` returning `[{'check','message'}]`, `CHECK_NAMES`, and the `--only` names are the same in Task 1 code, Task 2 tests, Task 3 text and Task 6 commands. Section headings referenced from Task 6 are verified by its Step 3.
