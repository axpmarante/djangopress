# Editor v2 Structural Verbs (Phases 0–2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the inline editor deterministic verbs to duplicate, move and insert elements and sections (no LLM), open them to staff users, and make them discoverable through insertion bars, a floating toolbar and the sidebar.

**Architecture:** HTML per language stays the single source of truth. Every verb is "insert / move / remove a node at an anchor", implemented as a pure BeautifulSoup function in a new `editor_v2/structure.py`, wrapped by an API view that validates on the current language, snapshots a version, applies the change to every language copy with the existing `_apply_structural_change_to_all_langs`, and returns the selector of the affected node. The frontend calls the endpoint, stores the returned selector in `sessionStorage`, reloads, and re-selects. Repeat-group detection (for "Add another") is heuristic and client-side, measured first by a Phase 0 audit command.

**Tech Stack:** Django 6, BeautifulSoup 4 (soupsieve selectors), Django `TestCase`, vanilla ES modules (no build step), Tailwind CDN. No JS test runner exists; JS is verified in the browser with the `playwright-cli` skill.

**Spec:** `docs/plans/2026-09-16-editor-add-elements-design.md` (Phases 0, 1, 2 only; Phases 3–6 get their own plans).

## Global Constraints

- Repo: `~/Documents/djangopress-sites/djangopress` (engine). Work on a feature branch off `main` named `feature/editor-structural-verbs`.
- Tests run from any child site whose venv has the engine installed editable. Use: `cd ~/Documents/djangopress-sites/o-marisco && .venv/bin/python manage.py test djangopress.editor_v2` (Django creates a throwaway test DB; the site's data is untouched). Existing suites: `python manage.py test djangopress.core djangopress.ai` must stay green.
- No LLM calls in any verb. Endpoints added here are `editor_required` (`is_active and is_staff`). AI endpoints stay `superuser_required`.
- Commit messages: no `Co-Authored-By` lines (repo rule). Conventional prefixes: `feat(editor):`, `fix(editor):`, `test(editor):`, `docs:`.
- Selectors follow the existing shape `section[data-section="x"] > div:nth-child(2) > h3:nth-child(1)`; `nth-child` counts element siblings only.
- New JS uses the existing patterns: `events` bus, `api.post`, `withEditableId`-style body building, `init()/destroy()` exports, `ev2-` CSS prefix, `esc()` for any interpolated text.
- When `templates/base.html` script/CSS cache-busters must change: `editor.js?v=34` → `?v=35`, `editor.css?v=20` → `?v=21` (Task 15 only).

---

## File Structure

| File | Responsibility |
|---|---|
| `src/djangopress/editor_v2/structure.py` (new) | Pure BeautifulSoup helpers: signatures, repeat-group audit, duplicate/move/insert/section helpers, selector arithmetic. No Django imports. |
| `src/djangopress/core/management/commands/audit_repeat_groups.py` (new) | Phase 0 report over a site's pages. |
| `src/djangopress/core/decorators.py` | Add `editor_required`. |
| `src/djangopress/editor_v2/api_views.py` | Five new views; permission change on remove/versions views. |
| `src/djangopress/editor_v2/urls.py` | Five new routes. |
| `src/djangopress/editor_v2/tests/__init__.py`, `test_structure.py`, `test_structural_api.py`, `test_audit_command.py` (new) | Tests. |
| `editor_v2/static/editor_v2/js/lib/structural.js` (new) | Client wrappers for the verbs, confirm dialogs, reload-and-reselect. |
| `editor_v2/static/editor_v2/js/lib/snippets.js` (new) | Primitive snippets (paragraph, heading, button, image) with class copying. |
| `editor_v2/static/editor_v2/js/lib/dom.js` | `signatureOf`, `findRepeatGroup`; export `isRuntimeInjected`. |
| `editor_v2/static/editor_v2/js/modules/context-menu.js` | New items, `disabled` support, delegate removes to `structural.js`. |
| `editor_v2/static/editor_v2/js/modules/sidebar.js` | Repeat-group panel in Content tab; arrows and `+` in Structure tab; fix listener leak. |
| `editor_v2/static/editor_v2/js/modules/section-inserter.js` | Insertion bars between sections. |
| `editor_v2/static/editor_v2/js/modules/section-modal.js` | Non-superuser message. |
| `editor_v2/static/editor_v2/js/modules/element-toolbar.js` (new) | Floating toolbar on the selected element. |
| `editor_v2/static/editor_v2/js/modules/command-palette.js` | Entries for the verbs. |
| `editor_v2/static/editor_v2/js/editor.js` | Init new modules; call `restoreSelection()`. |
| `editor_v2/static/editor_v2/css/editor.css` | Styles for disabled menu items, repeat panel, tree actions, insertion bars, element toolbar. |
| `src/djangopress/templates/base.html` | Cache-busters. |
| `src/djangopress/skills/djangopress-architecture/SKILL.md`, `CLAUDE.md` | Endpoint list and editor notes. |

---

## Task 0: Branch and test scaffolding

**Files:**
- Create: `src/djangopress/editor_v2/tests/__init__.py` (empty)

- [ ] **Step 1: Create the branch**

```bash
cd ~/Documents/djangopress-sites/djangopress
git checkout main && git pull
git checkout -b feature/editor-structural-verbs
```

- [ ] **Step 2: Create the tests package**

```bash
mkdir -p src/djangopress/editor_v2/tests
touch src/djangopress/editor_v2/tests/__init__.py
```

- [ ] **Step 3: Confirm discovery works (0 tests)**

Run: `cd ~/Documents/djangopress-sites/o-marisco && .venv/bin/python manage.py test djangopress.editor_v2 2>&1 | grep -E "^Ran|OK|Error"`
Expected: `Ran 0 tests` and `OK`

- [ ] **Step 4: Commit**

```bash
cd ~/Documents/djangopress-sites/djangopress
git add src/djangopress/editor_v2/tests/__init__.py docs/plans/2026-09-16-editor-add-elements-design.md docs/plans/2026-09-16-editor-add-elements-plan.md
git commit -m "docs(editor): design and plan for structural verbs; test package"
```

---

## Task 1: Signatures and repeat-group detection (Python)

**Files:**
- Create: `src/djangopress/editor_v2/structure.py`
- Test: `src/djangopress/editor_v2/tests/test_structure.py`

**Interfaces:**
- Produces: `signature_of(tag) -> str`, `child_signature_of(tag) -> str`, `find_repeat_groups(section_tag) -> list[dict]` with keys `container` (Tag), `items` (list[Tag]), `signature` (str), `size` (int), `nested` (bool), `ambiguous` (str or ''), `container_path` (str selector-like path from the section).

- [ ] **Step 1: Write the failing tests**

```python
# src/djangopress/editor_v2/tests/test_structure.py
from bs4 import BeautifulSoup
from django.test import SimpleTestCase

from djangopress.editor_v2.structure import (
    signature_of, find_repeat_groups,
)


def soup(html):
    return BeautifulSoup(html, 'html.parser')


CARDS = '''
<section data-section="services" id="services">
  <div class="container">
    <h2 class="title">Services</h2>
    <div class="grid">
      <div class="card"><h3>A</h3><p>a</p></div>
      <div class="card"><h3>B</h3><p>b</p></div>
      <div class="card"><h3>C</h3><p>c</p></div>
    </div>
  </div>
</section>'''

TWO_COLUMNS = '''
<section data-section="about" id="about">
  <div class="grid">
    <div class="col"><img src="x.jpg" alt=""></div>
    <div class="col"><h2>About</h2><p>text</p></div>
  </div>
</section>'''

NESTED = '''
<section data-section="faq" id="faq">
  <ul class="list">
    <li class="item"><h3>Q1</h3><ul class="tags"><li class="tag">a</li><li class="tag">b</li></ul></li>
    <li class="item"><h3>Q2</h3><ul class="tags"><li class="tag">c</li><li class="tag">d</li></ul></li>
  </ul>
</section>'''


class SignatureTest(SimpleTestCase):
    def test_signature_is_tag_plus_sorted_classes(self):
        t = soup('<div class="b a">x</div>').div
        self.assertEqual(signature_of(t), 'div|a b')

    def test_signature_ignores_editor_classes(self):
        t = soup('<div class="card ev2-selected">x</div>').div
        self.assertEqual(signature_of(t), 'div|card')


class FindRepeatGroupsTest(SimpleTestCase):
    def test_finds_card_grid(self):
        groups = find_repeat_groups(soup(CARDS).section)
        self.assertEqual(len(groups), 1)
        g = groups[0]
        self.assertEqual(g['size'], 3)
        self.assertEqual(g['signature'], 'div|card')
        self.assertEqual(g['container_path'], 'div:nth-child(1) > div:nth-child(2)')
        self.assertEqual(g['ambiguous'], '')
        self.assertFalse(g['nested'])

    def test_two_columns_with_different_children_are_ambiguous(self):
        groups = find_repeat_groups(soup(TWO_COLUMNS).section)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]['ambiguous'], 'pair-with-different-children')

    def test_nested_groups_are_flagged(self):
        groups = find_repeat_groups(soup(NESTED).section)
        items = [g for g in groups if g['signature'] == 'li|item']
        tags = [g for g in groups if g['signature'] == 'li|tag']
        self.assertEqual(len(items), 1)
        self.assertFalse(items[0]['nested'])
        # each <ul class="tags"> is its own container, so two nested groups of two
        self.assertEqual(len(tags), 2)
        self.assertTrue(all(g['nested'] for g in tags))
        self.assertEqual([g['size'] for g in tags], [2, 2])

    def test_single_child_is_not_a_group(self):
        groups = find_repeat_groups(soup('<section data-section="x"><div><p class="a">1</p></div></section>').section)
        self.assertEqual(groups, [])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Documents/djangopress-sites/o-marisco && .venv/bin/python manage.py test djangopress.editor_v2.tests.test_structure 2>&1 | tail -3`
Expected: `ModuleNotFoundError: No module named 'djangopress.editor_v2.structure'`

- [ ] **Step 3: Implement**

```python
# src/djangopress/editor_v2/structure.py
"""
Pure BeautifulSoup helpers for structural editing (no Django imports).

Selectors follow the editor's shape:
    section[data-section="x"] > div:nth-child(2) > h3:nth-child(1)
`nth-child` counts element siblings only, which is what soupsieve does too.
"""
import copy
import re

from bs4 import BeautifulSoup, Tag

EDITOR_CLASS_PREFIX = 'ev2-'
NTH_RE = re.compile(r'^(?P<tag>[a-z0-9]+):nth-child\((?P<n>\d+)\)$')


# ---------------------------------------------------------------------------
# Signatures and repeat groups (Phase 0 heuristic, mirrored in lib/dom.js)
# ---------------------------------------------------------------------------

def element_children(tag):
    return [c for c in tag.children if isinstance(c, Tag)]


def signature_of(tag):
    classes = sorted(c for c in (tag.get('class') or []) if not c.startswith(EDITOR_CLASS_PREFIX))
    return f"{tag.name}|{' '.join(classes)}"


def child_signature_of(tag):
    return ','.join(signature_of(c) for c in element_children(tag))


def path_from_section(tag, section):
    """Selector path of `tag` relative to `section` (without the section prefix)."""
    parts = []
    current = tag
    while current is not None and current is not section:
        parent = current.parent
        if parent is None:
            break
        index = element_children(parent).index(current) + 1
        parts.insert(0, f'{current.name}:nth-child({index})')
        current = parent
    return ' > '.join(parts)


def find_repeat_groups(section):
    """
    Return every sibling group inside `section` whose members share a signature.

    A group is a dict: container, items, signature, size, nested, ambiguous,
    container_path. Groups of exactly two whose members have different child
    signatures are marked ambiguous ('pair-with-different-children'): they are
    usually two columns, not two cards.
    """
    groups = []
    for container in [section] + section.find_all(True):
        children = element_children(container)
        by_sig = {}
        for child in children:
            by_sig.setdefault(signature_of(child), []).append(child)
        for sig, items in by_sig.items():
            if len(items) < 2:
                continue
            ambiguous = ''
            if len(items) == 2 and child_signature_of(items[0]) != child_signature_of(items[1]):
                ambiguous = 'pair-with-different-children'
            groups.append({
                'container': container,
                'items': items,
                'signature': sig,
                'size': len(items),
                'nested': False,
                'ambiguous': ambiguous,
                'container_path': path_from_section(container, section),
            })
    # Mark nested groups: container lives inside an item of another group.
    for g in groups:
        for other in groups:
            if other is g:
                continue
            if any(item in g['container'].parents or item is g['container'] for item in other['items']):
                g['nested'] = True
                break
    return groups
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/Documents/djangopress-sites/o-marisco && .venv/bin/python manage.py test djangopress.editor_v2.tests.test_structure 2>&1 | grep -E "^Ran|OK|FAIL"`
Expected: `Ran 6 tests` … `OK`

- [ ] **Step 5: Commit**

```bash
cd ~/Documents/djangopress-sites/djangopress
git add src/djangopress/editor_v2/structure.py src/djangopress/editor_v2/tests/test_structure.py
git commit -m "feat(editor): repeat-group detection helpers"
```

---

## Task 2: Phase 0 audit command and measurement

**Files:**
- Create: `src/djangopress/core/management/commands/audit_repeat_groups.py`
- Test: `src/djangopress/editor_v2/tests/test_audit_command.py`
- Modify: `docs/plans/2026-09-16-editor-add-elements-design.md` (record results under Phase 0)

**Interfaces:**
- Consumes: `find_repeat_groups` from Task 1.
- Produces: `python manage.py audit_repeat_groups [--json] [--lang pt]`.

- [ ] **Step 1: Write the failing test**

```python
# src/djangopress/editor_v2/tests/test_audit_command.py
import json
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from djangopress.core.models import Page, SiteSettings


HTML = ('<section data-section="services" id="services"><div class="grid">'
        '<div class="card"><h3>A</h3></div><div class="card"><h3>B</h3></div></div></section>'
        '<section data-section="hero" id="hero"><h1>Hi</h1></section>')


class AuditRepeatGroupsTest(TestCase):
    def setUp(self):
        Page.objects.all().delete()
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}]
        s.default_language = 'pt'
        s.save()
        Page.objects.create(title_i18n={'pt': 'Home'}, slug_i18n={'pt': 'home'},
                            is_active=True, html_content_i18n={'pt': HTML})

    def test_json_output_lists_groups_per_section(self):
        out = StringIO()
        call_command('audit_repeat_groups', '--json', stdout=out)
        data = json.loads(out.getvalue())
        self.assertEqual(data['pages'][0]['slug'], 'home')
        sections = {s['name']: s for s in data['pages'][0]['sections']}
        self.assertEqual(sections['services']['groups'][0]['size'], 2)
        self.assertEqual(sections['services']['groups'][0]['signature'], 'div|card')
        self.assertEqual(sections['hero']['groups'], [])

    def test_markdown_output_has_a_table(self):
        out = StringIO()
        call_command('audit_repeat_groups', stdout=out)
        text = out.getvalue()
        self.assertIn('| services |', text)
        self.assertIn('div|card', text)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/Documents/djangopress-sites/o-marisco && .venv/bin/python manage.py test djangopress.editor_v2.tests.test_audit_command 2>&1 | tail -3`
Expected: `CommandError: Unknown command: 'audit_repeat_groups'`

- [ ] **Step 3: Implement the command**

```python
# src/djangopress/core/management/commands/audit_repeat_groups.py
"""
audit_repeat_groups — Phase 0 measurement for the editor's "Add another" verb.

For every active page (default language unless --lang), lists the sibling
groups the repeat-group heuristic finds per section, with size and
ambiguity flags. Read-only.

Usage:
    python manage.py audit_repeat_groups           # markdown table
    python manage.py audit_repeat_groups --json
    python manage.py audit_repeat_groups --lang en
"""
import json

from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand

from djangopress.core.models import Page, SiteSettings
from djangopress.editor_v2.structure import find_repeat_groups


class Command(BaseCommand):
    help = 'Report repeat groups found by the editor heuristic, per page and section.'

    def add_arguments(self, parser):
        parser.add_argument('--json', action='store_true', dest='as_json')
        parser.add_argument('--lang', default=None)

    def handle(self, *args, **options):
        settings = SiteSettings.load()
        lang = options['lang'] or settings.get_default_language()
        report = {'language': lang, 'pages': []}

        for page in Page.objects.filter(is_active=True).order_by('sort_order', 'id'):
            html = (page.html_content_i18n or {}).get(lang) or ''
            soup = BeautifulSoup(html, 'html.parser')
            page_entry = {'slug': (page.slug_i18n or {}).get(lang, str(page.id)), 'sections': []}
            for section in soup.find_all('section', attrs={'data-section': True}):
                groups = find_repeat_groups(section)
                page_entry['sections'].append({
                    'name': section.get('data-section'),
                    'groups': [{
                        'signature': g['signature'],
                        'size': g['size'],
                        'nested': g['nested'],
                        'ambiguous': g['ambiguous'],
                        'container_path': g['container_path'],
                    } for g in groups],
                })
            report['pages'].append(page_entry)

        if options['as_json']:
            self.stdout.write(json.dumps(report, indent=2, ensure_ascii=False))
            return

        self.stdout.write(f'# Repeat groups ({lang})\n')
        self.stdout.write('| page | section | signature | size | nested | ambiguous |')
        self.stdout.write('|---|---|---|---|---|---|')
        for p in report['pages']:
            for s in p['sections']:
                if not s['groups']:
                    self.stdout.write(f"| {p['slug']} | {s['name']} | (none) | | | |")
                for g in s['groups']:
                    self.stdout.write(
                        f"| {p['slug']} | {s['name']} | {g['signature']} | {g['size']} | "
                        f"{'yes' if g['nested'] else ''} | {g['ambiguous']} |"
                    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/Documents/djangopress-sites/o-marisco && .venv/bin/python manage.py test djangopress.editor_v2 2>&1 | grep -E "^Ran|OK|FAIL"`
Expected: `Ran 8 tests` … `OK`

- [ ] **Step 5: Run the audit on every real site**

```bash
cd ~/Documents/djangopress-sites
for d in */; do
  [ -x "$d/.venv/bin/python" ] || continue
  [ -f "$d/manage.py" ] || continue
  echo "## $d"; (cd "$d" && .venv/bin/python manage.py audit_repeat_groups 2>/dev/null | grep -E "^\|" | grep -v "(none)")
done > /tmp/repeat-groups-audit.md
grep -c "pair-with-different-children" /tmp/repeat-groups-audit.md
grep -c "| yes |" /tmp/repeat-groups-audit.md
```

Expected: a markdown table per site. Read through and note: (a) sections where the *outermost non-ambiguous* group is not the visually obvious card list, (b) ambiguous pairs that are in fact two cards (false negatives).

- [ ] **Step 6: Record the results in the design doc**

Append under **Phase 0** in `docs/plans/2026-09-16-editor-add-elements-design.md` a short "Results (2026-09-16)" block: number of sites audited, number of sections, number of groups, count of ambiguous pairs, and the list of sections where the heuristic misplaced the group (site/page/section). End with one line: "Phase 6 needed: yes/no".

- [ ] **Step 7: Commit**

```bash
cd ~/Documents/djangopress-sites/djangopress
git add src/djangopress/core/management/commands/audit_repeat_groups.py src/djangopress/editor_v2/tests/test_audit_command.py docs/plans/2026-09-16-editor-add-elements-design.md
git commit -m "feat(editor): audit_repeat_groups command and Phase 0 results"
```

---

## Task 3: `editor_required` and permission change on existing endpoints

**Files:**
- Modify: `src/djangopress/core/decorators.py`
- Modify: `src/djangopress/editor_v2/api_views.py` (decorators on `remove_section`, `remove_element`, `list_page_versions`, `get_page_version`)
- Test: `src/djangopress/editor_v2/tests/test_structural_api.py` (new; shared fixtures for all API tasks)

**Interfaces:**
- Produces: `editor_required` decorator in `djangopress.core.decorators`; test base class `StructuralApiTestCase` with `self.page`, `self.staff`, `self.post(url_name, body)`, `self.html(lang)`, constants `PT_HTML`, `EN_HTML`.

- [ ] **Step 1: Write the failing tests**

```python
# src/djangopress/editor_v2/tests/test_structural_api.py
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from djangopress.core.models import Page, PageVersion, SiteSettings

User = get_user_model()

PT_HTML = (
    '<section data-section="services" id="services">'
    '<div class="grid">'
    '<div class="card"><h3>Um</h3><p>A</p></div>'
    '<div class="card"><h3>Dois</h3><p>B</p></div>'
    '</div>'
    '</section>'
    '<section data-section="cta" id="cta"><a href="#services">Ver</a></section>'
)
EN_HTML = (
    '<section data-section="services" id="services">'
    '<div class="grid">'
    '<div class="card"><h3>One</h3><p>A</p></div>'
    '<div class="card"><h3>Two</h3><p>B</p></div>'
    '</div>'
    '</section>'
    '<section data-section="cta" id="cta"><a href="#services">See</a></section>'
)
CARD_1 = 'section[data-section="services"] > div:nth-child(1) > div:nth-child(1)'
CARD_2 = 'section[data-section="services"] > div:nth-child(1) > div:nth-child(2)'


class StructuralApiTestCase(TestCase):
    def setUp(self):
        Page.objects.all().delete()
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        self.page = Page.objects.create(
            title_i18n={'pt': 'Home', 'en': 'Home'}, slug_i18n={'pt': 'home', 'en': 'home'},
            is_active=True, html_content_i18n={'pt': PT_HTML, 'en': EN_HTML},
        )
        self.staff = User.objects.create_user('staff', 'staff@example.com', 'pw', is_staff=True)
        self.client.force_login(self.staff)

    def post(self, url_name, body):
        body = {'page_id': self.page.id, **body}
        return self.client.post(
            reverse(f'editor_v2:{url_name}'), data=json.dumps(body),
            content_type='application/json', HTTP_REFERER='http://testserver/pt/?edit=v2',
        )

    def html(self, lang):
        self.page.refresh_from_db()
        return self.page.html_content_i18n[lang]


class PermissionsTest(StructuralApiTestCase):
    def test_staff_can_remove_element(self):
        res = self.post('api_remove_element', {'selector': CARD_2})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['success'])
        self.assertNotIn('Dois', self.html('pt'))
        self.assertNotIn('Two', self.html('en'))

    def test_staff_can_list_versions(self):
        self.page.create_version(user=self.staff, change_summary='x')
        res = self.client.get(reverse('editor_v2:api_list_versions', args=[self.page.id]))
        self.assertEqual(res.status_code, 200)

    def test_non_staff_is_redirected(self):
        plain = User.objects.create_user('plain', 'p@example.com', 'pw')
        self.client.force_login(plain)
        res = self.post('api_remove_element', {'selector': CARD_2})
        self.assertEqual(res.status_code, 302)
        self.assertIn('Dois', self.html('pt'))

    def test_anonymous_is_redirected(self):
        self.client.logout()
        res = self.post('api_remove_section', {'section_name': 'cta'})
        self.assertEqual(res.status_code, 302)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Documents/djangopress-sites/o-marisco && .venv/bin/python manage.py test djangopress.editor_v2.tests.test_structural_api 2>&1 | grep -E "^Ran|OK|FAIL|Error"`
Expected: `test_staff_can_remove_element` and `test_staff_can_list_versions` FAIL (302 instead of 200); the two redirect tests pass.

- [ ] **Step 3: Add the decorator**

Append to `src/djangopress/core/decorators.py`:

```python
def editor_required(view_func=None, redirect_field_name=REDIRECT_FIELD_NAME, login_url=None):
    """Decorator for inline-editor endpoints: active staff user (not necessarily superuser)."""
    actual_decorator = user_passes_test(
        lambda u: u.is_active and u.is_staff,
        login_url=login_url,
        redirect_field_name=redirect_field_name,
    )
    if view_func:
        return actual_decorator(view_func)
    return actual_decorator
```

- [ ] **Step 4: Switch the four views**

In `src/djangopress/editor_v2/api_views.py`:

- change the import line `from djangopress.core.decorators import superuser_required` to `from djangopress.core.decorators import superuser_required, editor_required`
- replace `@superuser_required` with `@editor_required` immediately above `def list_page_versions`, `def get_page_version`, `def remove_section`, `def remove_element`. Leave every other view untouched.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd ~/Documents/djangopress-sites/o-marisco && .venv/bin/python manage.py test djangopress.editor_v2 2>&1 | grep -E "^Ran|OK|FAIL"`
Expected: `Ran 12 tests` … `OK`

- [ ] **Step 6: Commit**

```bash
cd ~/Documents/djangopress-sites/djangopress
git add src/djangopress/core/decorators.py src/djangopress/editor_v2/api_views.py src/djangopress/editor_v2/tests/test_structural_api.py
git commit -m "feat(editor): editor_required; open remove and versions endpoints to staff"
```

---

## Task 4: Structural helpers — duplicate, move, selector arithmetic

**Files:**
- Modify: `src/djangopress/editor_v2/structure.py`
- Test: `src/djangopress/editor_v2/tests/test_structure.py`

**Interfaces:**
- Produces: `shift_last_index(selector, delta) -> str`, `strip_ids(tag) -> None`, `duplicate_node(soup, selector) -> str|None` (selector of the clone), `move_node(soup, selector, direction) -> str|None` (new selector; `None` when not found or at the edge), `adjacent_sibling(tag, direction) -> Tag|None`.

- [ ] **Step 1: Write the failing tests**

Append to `src/djangopress/editor_v2/tests/test_structure.py`:

```python
from djangopress.editor_v2.structure import (
    shift_last_index, duplicate_node, move_node,
)

GRID = ('<section data-section="s" id="s"><div class="grid">'
        '<div class="card" id="c1"><h3 id="t1">A</h3></div>'
        '<div class="card"><h3>B</h3></div>'
        '</div></section>')
C1 = 'section[data-section="s"] > div:nth-child(1) > div:nth-child(1)'
C2 = 'section[data-section="s"] > div:nth-child(1) > div:nth-child(2)'
C3 = 'section[data-section="s"] > div:nth-child(1) > div:nth-child(3)'


class SelectorArithmeticTest(SimpleTestCase):
    def test_shift_last_index(self):
        self.assertEqual(shift_last_index(C1, 1), C2)
        self.assertEqual(shift_last_index(C2, -1), C1)

    def test_shift_section_selector_is_unchanged(self):
        self.assertEqual(shift_last_index('section[data-section="s"]', 1), 'section[data-section="s"]')


class DuplicateNodeTest(SimpleTestCase):
    def test_clone_is_inserted_after_and_ids_stripped(self):
        s = soup(GRID)
        new_sel = duplicate_node(s, C1)
        self.assertEqual(new_sel, C2)
        cards = s.select('section > div > div')
        self.assertEqual(len(cards), 3)
        self.assertEqual(cards[1].h3.get_text(), 'A')
        self.assertIsNone(cards[1].get('id'))
        self.assertIsNone(cards[1].h3.get('id'))
        self.assertEqual(cards[0].get('id'), 'c1')

    def test_missing_selector_returns_none(self):
        self.assertIsNone(duplicate_node(soup(GRID), C3))


class MoveNodeTest(SimpleTestCase):
    def test_move_down(self):
        s = soup(GRID)
        self.assertEqual(move_node(s, C1, 'down'), C2)
        self.assertEqual([c.h3.get_text() for c in s.select('section > div > div')], ['B', 'A'])

    def test_move_up(self):
        s = soup(GRID)
        self.assertEqual(move_node(s, C2, 'up'), C1)
        self.assertEqual([c.h3.get_text() for c in s.select('section > div > div')], ['B', 'A'])

    def test_move_at_edge_returns_none_and_changes_nothing(self):
        s = soup(GRID)
        self.assertIsNone(move_node(s, C1, 'up'))
        self.assertEqual([c.h3.get_text() for c in s.select('section > div > div')], ['A', 'B'])

    def test_whitespace_between_siblings_is_ignored(self):
        s = soup(GRID.replace('</div><div class="card">', '</div>\n  <div class="card">'))
        self.assertEqual(move_node(s, C2, 'up'), C1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Documents/djangopress-sites/o-marisco && .venv/bin/python manage.py test djangopress.editor_v2.tests.test_structure 2>&1 | tail -3`
Expected: `ImportError: cannot import name 'shift_last_index'`

- [ ] **Step 3: Implement**

Append to `src/djangopress/editor_v2/structure.py`:

```python
# ---------------------------------------------------------------------------
# Selector arithmetic
# ---------------------------------------------------------------------------

def split_last(selector):
    """('head', 'tag', n) for a selector ending in `tag:nth-child(n)`, else None."""
    head, _sep, last = selector.rpartition(' > ')
    m = NTH_RE.match(last)
    if not m:
        return None
    return head, m.group('tag'), int(m.group('n'))


def with_last(selector, tag, n):
    """Rebuild `selector` with a new last part `tag:nth-child(n)`."""
    parts = split_last(selector)
    head = parts[0] if parts else selector
    return f'{head} > {tag}:nth-child({n})'


def shift_last_index(selector, delta):
    """Return `selector` with the last `:nth-child(n)` moved by `delta` (same tag)."""
    parts = split_last(selector)
    if not parts:
        return selector
    head, tag, n = parts
    return with_last(selector, tag, max(1, n + delta))


def adjacent_sibling(tag, direction):
    """Previous/next element sibling, or None."""
    if direction == 'up':
        return tag.find_previous_sibling(True)
    if direction == 'down':
        return tag.find_next_sibling(True)
    raise ValueError(f'direction must be "up" or "down", got {direction!r}')


def strip_ids(tag):
    """Remove `id` from `tag` and every descendant (ids must stay unique)."""
    if tag.has_attr('id'):
        del tag['id']
    for t in tag.find_all(id=True):
        del t['id']


# ---------------------------------------------------------------------------
# Element verbs
# ---------------------------------------------------------------------------

def duplicate_node(soup, selector):
    """Clone the node at `selector` right after itself. Returns the clone's selector."""
    node = soup.select_one(selector)
    if node is None:
        return None
    clone = copy.copy(node)
    strip_ids(clone)
    node.insert_after(clone)
    return shift_last_index(selector, 1)


def move_node(soup, selector, direction):
    """Swap the node with its previous/next element sibling. Returns the new selector, or None."""
    node = soup.select_one(selector)
    if node is None:
        return None
    other = adjacent_sibling(node, direction)
    if other is None:
        return None
    node = node.extract()
    if direction == 'up':
        other.insert_before(node)
        return shift_last_index(selector, -1)
    other.insert_after(node)
    return shift_last_index(selector, 1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/Documents/djangopress-sites/o-marisco && .venv/bin/python manage.py test djangopress.editor_v2.tests.test_structure 2>&1 | grep -E "^Ran|OK|FAIL"`
Expected: `Ran 14 tests` … `OK`

- [ ] **Step 5: Commit**

```bash
cd ~/Documents/djangopress-sites/djangopress
git add src/djangopress/editor_v2/structure.py src/djangopress/editor_v2/tests/test_structure.py
git commit -m "feat(editor): duplicate_node and move_node helpers"
```

---

## Task 5: Endpoints `duplicate-element` and `move-element`

**Files:**
- Modify: `src/djangopress/editor_v2/api_views.py` (append after `remove_element`)
- Modify: `src/djangopress/editor_v2/urls.py`
- Test: `src/djangopress/editor_v2/tests/test_structural_api.py`

**Interfaces:**
- Consumes: `duplicate_node`, `move_node` (Task 4); `editor_required` (Task 3); `_get_editable_object`, `_get_page_html`, `_apply_structural_change_to_all_langs` (existing).
- Produces: `POST /editor-v2/api/duplicate-element/` body `{page_id, selector}` → `{success, selector, skipped_languages}`; `POST /editor-v2/api/move-element/` body `{page_id, selector, direction}` → `{success, moved, selector, skipped_languages}`. URL names `api_duplicate_element`, `api_move_element`.

- [ ] **Step 1: Write the failing tests**

Append to `test_structural_api.py`:

```python
class DuplicateElementTest(StructuralApiTestCase):
    def test_duplicates_in_all_languages_and_returns_new_selector(self):
        res = self.post('api_duplicate_element', {'selector': CARD_1})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['selector'], CARD_2)
        self.assertEqual(data['skipped_languages'], [])
        self.assertEqual(self.html('pt').count('<h3>Um</h3>'), 2)
        self.assertEqual(self.html('en').count('<h3>One</h3>'), 2)
        self.assertEqual(PageVersion.objects.filter(page=self.page).count(), 1)
        self.assertIn('Duplicated element', PageVersion.objects.get().change_summary)

    def test_language_without_the_element_is_skipped_and_reported(self):
        self.page.html_content_i18n['en'] = '<section data-section="services" id="services"><p>x</p></section>'
        self.page.save()
        res = self.post('api_duplicate_element', {'selector': CARD_1})
        self.assertTrue(res.json()['success'])
        self.assertEqual(res.json()['skipped_languages'], ['en'])
        self.assertEqual(self.html('pt').count('<h3>Um</h3>'), 2)

    def test_missing_selector_is_400(self):
        res = self.post('api_duplicate_element', {'selector': CARD_1.replace('(1)', '(9)')})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(PageVersion.objects.count(), 0)


class MoveElementTest(StructuralApiTestCase):
    def test_move_down_swaps_in_all_languages(self):
        res = self.post('api_move_element', {'selector': CARD_1, 'direction': 'down'})
        data = res.json()
        self.assertTrue(data['success'])
        self.assertTrue(data['moved'])
        self.assertEqual(data['selector'], CARD_2)
        self.assertLess(self.html('pt').index('Dois'), self.html('pt').index('Um'))
        self.assertLess(self.html('en').index('Two'), self.html('en').index('One'))

    def test_move_at_edge_is_noop(self):
        res = self.post('api_move_element', {'selector': CARD_1, 'direction': 'up'})
        data = res.json()
        self.assertTrue(data['success'])
        self.assertFalse(data['moved'])
        self.assertEqual(PageVersion.objects.count(), 0)

    def test_bad_direction_is_400(self):
        res = self.post('api_move_element', {'selector': CARD_1, 'direction': 'left'})
        self.assertEqual(res.status_code, 400)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Documents/djangopress-sites/o-marisco && .venv/bin/python manage.py test djangopress.editor_v2.tests.test_structural_api 2>&1 | tail -3`
Expected: `NoReverseMatch: Reverse for 'api_duplicate_element' not found`

- [ ] **Step 3: Add a shared helper and the two views**

In `api_views.py`, add the import near the top (after the `bs4` import):

```python
from djangopress.editor_v2 import structure
```

Append after `remove_element`:

```python
# ---------------------------------------------------------------------------
# Structural verbs (no LLM): duplicate / move / insert
# ---------------------------------------------------------------------------

def _run_structural_verb(request, data, change_summary, apply_fn):
    """
    Shared driver for structural endpoints.

    `apply_fn(soup)` mutates a soup and returns a result (truthy on success,
    None when the target was not found or the verb was a no-op). It is run
    once on the current-language HTML for validation and to get the result,
    then on every language copy through _apply_structural_change_to_all_langs.

    Returns a JsonResponse on a request error, otherwise the tuple
    (page, result, skipped_languages); `result` is None when the target
    was not found in the current language (nothing was changed or saved).
    """
    try:
        page = _get_editable_object(data)
    except Exception:
        page = None
    if not page:
        return JsonResponse({'success': False, 'error': 'Page or editable object not found'}, status=400)

    current_html, _lang = _get_page_html(page)
    result = apply_fn(BeautifulSoup(current_html or '', 'html.parser'))
    if result is None:
        return page, None, []

    if hasattr(page, 'create_version'):
        page.create_version(user=request.user, change_summary=change_summary)

    skipped = []
    html_i18n = dict(getattr(page, 'html_content_i18n', None) or {})
    for lang_code, lang_html in html_i18n.items():
        if not lang_html:
            continue
        soup = BeautifulSoup(lang_html, 'html.parser')
        if apply_fn(soup) is None:
            skipped.append(lang_code)
            continue
        new_html = str(soup)
        if new_html.startswith('<html><body>'):
            new_html = new_html[12:-14]
        html_i18n[lang_code] = new_html
    page.html_content_i18n = html_i18n
    page.save()
    return page, result, skipped


@editor_required
@require_http_methods(["POST"])
def duplicate_element(request):
    """Clone the element at `selector` right after itself, in every language copy."""
    try:
        data = json.loads(request.body)
        selector = data.get('selector')
        if not selector:
            return JsonResponse({'success': False, 'error': 'Missing selector'}, status=400)

        outcome = _run_structural_verb(
            request, data, 'Duplicated element',
            lambda soup: structure.duplicate_node(soup, selector),
        )
        if isinstance(outcome, JsonResponse):
            return outcome
        page, new_selector, skipped = outcome
        if new_selector is None:
            return JsonResponse({'success': False, 'error': 'Element not found for selector'}, status=400)
        return JsonResponse({'success': True, 'selector': new_selector, 'skipped_languages': skipped, 'page_id': page.id})
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@editor_required
@require_http_methods(["POST"])
def move_element(request):
    """Swap the element at `selector` with its previous ('up') or next ('down') sibling."""
    try:
        data = json.loads(request.body)
        selector = data.get('selector')
        direction = data.get('direction')
        if not selector:
            return JsonResponse({'success': False, 'error': 'Missing selector'}, status=400)
        if direction not in ('up', 'down'):
            return JsonResponse({'success': False, 'error': 'direction must be "up" or "down"'}, status=400)

        # Distinguish "not found" (400) from "at the edge" (no-op) before running the verb.
        page = _get_editable_object(data)
        current_html, _lang = _get_page_html(page)
        probe = BeautifulSoup(current_html or '', 'html.parser')
        node = probe.select_one(selector)
        if node is None:
            return JsonResponse({'success': False, 'error': 'Element not found for selector'}, status=400)
        if structure.adjacent_sibling(node, direction) is None:
            return JsonResponse({'success': True, 'moved': False, 'selector': selector, 'skipped_languages': []})

        outcome = _run_structural_verb(
            request, data, f'Moved element {direction}',
            lambda soup: structure.move_node(soup, selector, direction),
        )
        if isinstance(outcome, JsonResponse):
            return outcome
        page, new_selector, skipped = outcome
        return JsonResponse({'success': True, 'moved': True, 'selector': new_selector, 'skipped_languages': skipped, 'page_id': page.id})
    except Page.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Page not found'}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
```

Note on `_run_structural_verb`: callers first check `isinstance(outcome, JsonResponse)`, then unpack `page, result, skipped`; `result is None` means "not found in the current language" and nothing was saved.

- [ ] **Step 4: Add the routes**

In `urls.py`, after the `remove-element` route:

```python
    # Structural verbs (no LLM)
    path('api/duplicate-element/', api_views.duplicate_element, name='api_duplicate_element'),
    path('api/move-element/', api_views.move_element, name='api_move_element'),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd ~/Documents/djangopress-sites/o-marisco && .venv/bin/python manage.py test djangopress.editor_v2 2>&1 | grep -E "^Ran|OK|FAIL"`
Expected: `Ran 26 tests` … `OK`

- [ ] **Step 6: Commit**

```bash
cd ~/Documents/djangopress-sites/djangopress
git add src/djangopress/editor_v2/api_views.py src/djangopress/editor_v2/urls.py src/djangopress/editor_v2/tests/test_structural_api.py
git commit -m "feat(editor): duplicate-element and move-element endpoints"
```

---

## Task 6: `insert-element` with snippet validation

**Files:**
- Modify: `src/djangopress/editor_v2/structure.py`, `api_views.py`, `urls.py`
- Test: `test_structure.py`, `test_structural_api.py`

**Interfaces:**
- Produces: `validate_snippet(html) -> Tag` (raises `ValueError` with a message), `insert_snippet(soup, selector, position, snippet_html) -> str|None` (selector of the inserted node); `POST /editor-v2/api/insert-element/` body `{page_id, selector, position: 'before'|'after'|'append', html}` → `{success, selector, skipped_languages}`; URL name `api_insert_element`.

- [ ] **Step 1: Write the failing tests**

Append to `test_structure.py`:

```python
from djangopress.editor_v2.structure import validate_snippet, insert_snippet


class ValidateSnippetTest(SimpleTestCase):
    def test_single_element_ok(self):
        self.assertEqual(validate_snippet('<p class="a">x</p>').name, 'p')

    def test_surrounding_whitespace_ok(self):
        self.assertEqual(validate_snippet('\n  <p>x</p>\n').name, 'p')

    def test_two_roots_rejected(self):
        with self.assertRaises(ValueError):
            validate_snippet('<p>a</p><p>b</p>')

    def test_text_only_rejected(self):
        with self.assertRaises(ValueError):
            validate_snippet('just text')

    def test_script_and_section_rejected(self):
        with self.assertRaises(ValueError):
            validate_snippet('<script>1</script>')
        with self.assertRaises(ValueError):
            validate_snippet('<div><script>1</script></div>')
        with self.assertRaises(ValueError):
            validate_snippet('<section data-section="x"></section>')


class InsertSnippetTest(SimpleTestCase):
    P2 = 'section[data-section="s"] > div:nth-child(1) > p:nth-child(2)'

    def test_after(self):
        s = soup(GRID)
        self.assertEqual(insert_snippet(s, C1, 'after', '<p class="new">n</p>'), self.P2)
        self.assertEqual([c.name for c in s.select('section > div > *')], ['div', 'p', 'div'])
        self.assertEqual(s.select_one(self.P2).get_text(), 'n')

    def test_before(self):
        s = soup(GRID)
        self.assertEqual(insert_snippet(s, C2, 'before', '<p class="new">n</p>'), self.P2)
        self.assertEqual([c.name for c in s.select('section > div > *')], ['div', 'p', 'div'])

    def test_append(self):
        s = soup(GRID)
        sel = insert_snippet(s, C1, 'append', '<p class="new">n</p>')
        self.assertEqual(sel, C1 + ' > p:nth-child(2)')
        self.assertEqual(s.select_one(sel).get_text(), 'n')

    def test_missing_anchor_returns_none(self):
        self.assertIsNone(insert_snippet(soup(GRID), C3, 'after', '<p>n</p>'))
```

Append to `test_structural_api.py`:

```python
class InsertElementTest(StructuralApiTestCase):
    def test_inserts_identical_snippet_in_all_languages(self):
        res = self.post('api_insert_element', {'selector': CARD_2, 'position': 'after', 'html': '<p class="lead">New</p>'})
        data = res.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['selector'], CARD_2.replace('div:nth-child(2)', 'p:nth-child(3)'))
        self.assertIn('<p class="lead">New</p>', self.html('pt'))
        self.assertIn('<p class="lead">New</p>', self.html('en'))

    def test_invalid_snippet_is_400(self):
        res = self.post('api_insert_element', {'selector': CARD_2, 'position': 'after', 'html': '<script>x</script>'})
        self.assertEqual(res.status_code, 400)
        self.assertIn('script', res.json()['error'])
        self.assertEqual(PageVersion.objects.count(), 0)

    def test_bad_position_is_400(self):
        res = self.post('api_insert_element', {'selector': CARD_2, 'position': 'inside', 'html': '<p>x</p>'})
        self.assertEqual(res.status_code, 400)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Documents/djangopress-sites/o-marisco && .venv/bin/python manage.py test djangopress.editor_v2 2>&1 | tail -3`
Expected: `ImportError: cannot import name 'validate_snippet'`

- [ ] **Step 3: Implement the helpers**

Append to `structure.py`:

```python
FORBIDDEN_SNIPPET_TAGS = ('script', 'style', 'section', 'html', 'head', 'body', 'iframe')


def validate_snippet(html):
    """Parse a snippet and return its single root Tag; raise ValueError otherwise."""
    parsed = BeautifulSoup(html or '', 'html.parser')
    roots = [c for c in parsed.contents if isinstance(c, Tag)]
    stray_text = [c for c in parsed.contents if not isinstance(c, Tag) and str(c).strip()]
    if len(roots) != 1 or stray_text:
        raise ValueError('Snippet must contain exactly one top-level element')
    root = roots[0]
    for name in FORBIDDEN_SNIPPET_TAGS:
        if root.name == name or root.find(name):
            raise ValueError(f'Snippet may not contain <{name}>')
    return root


def insert_snippet(soup, selector, position, snippet_html):
    """
    Insert a validated snippet relative to the node at `selector`.
    position: 'before' | 'after' | 'append' (as last child).
    Returns the selector of the inserted node, or None if the anchor is missing.
    """
    anchor = soup.select_one(selector)
    if anchor is None:
        return None
    node = validate_snippet(snippet_html)
    parts = split_last(selector)          # None when the anchor is the section itself
    if position == 'before':
        anchor.insert_before(node)
        return with_last(selector, node.name, parts[2]) if parts else None
    if position == 'after':
        anchor.insert_after(node)
        return with_last(selector, node.name, parts[2] + 1) if parts else None
    if position == 'append':
        anchor.append(node)
        return f'{selector} > {node.name}:nth-child({len(element_children(anchor))})'
    raise ValueError('position must be "before", "after" or "append"')
```

Note: when the anchor is the section itself (`section[data-section="x"]`, no `nth-child` part), only `append` is meaningful; `before`/`after` still insert but return `None`, which the view reports as an error. Client code never sends a bare section selector with `before`/`after`.

- [ ] **Step 4: Implement the view and route**

Append to `api_views.py`:

```python
@editor_required
@require_http_methods(["POST"])
def insert_element(request):
    """Insert a small HTML snippet before/after/inside the element at `selector`, in every language."""
    try:
        data = json.loads(request.body)
        selector = data.get('selector')
        position = data.get('position', 'after')
        html = (data.get('html') or '').strip()
        if not selector:
            return JsonResponse({'success': False, 'error': 'Missing selector'}, status=400)
        if position not in ('before', 'after', 'append'):
            return JsonResponse({'success': False, 'error': 'position must be "before", "after" or "append"'}, status=400)
        try:
            structure.validate_snippet(html)
        except ValueError as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)

        outcome = _run_structural_verb(
            request, data, f'Inserted element ({position})',
            lambda soup: structure.insert_snippet(soup, selector, position, html),
        )
        if isinstance(outcome, JsonResponse):
            return outcome
        page, new_selector, skipped = outcome
        if new_selector is None:
            return JsonResponse({'success': False, 'error': 'Element not found for selector'}, status=400)
        return JsonResponse({'success': True, 'selector': new_selector, 'skipped_languages': skipped, 'page_id': page.id})
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
```

In `urls.py`, after `move-element`:

```python
    path('api/insert-element/', api_views.insert_element, name='api_insert_element'),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd ~/Documents/djangopress-sites/o-marisco && .venv/bin/python manage.py test djangopress.editor_v2 2>&1 | grep -E "^Ran|OK|FAIL"`
Expected: `Ran 38 tests` … `OK`

- [ ] **Step 6: Commit**

```bash
cd ~/Documents/djangopress-sites/djangopress
git add src/djangopress/editor_v2/structure.py src/djangopress/editor_v2/api_views.py src/djangopress/editor_v2/urls.py src/djangopress/editor_v2/tests/
git commit -m "feat(editor): insert-element endpoint with snippet validation"
```

---

## Task 7: Section verbs — `duplicate-section` and `move-section`

**Files:**
- Modify: `structure.py`, `api_views.py`, `urls.py`
- Test: `test_structure.py`, `test_structural_api.py`
- Modify (docs): `src/djangopress/skills/djangopress-architecture/SKILL.md` (endpoint list), `CLAUDE.md` root (editor notes)

**Interfaces:**
- Produces: `next_free_section_name(soup, base) -> str`, `duplicate_section(soup, name, new_name) -> bool`, `move_section(soup, name, direction) -> bool`; `POST /editor-v2/api/duplicate-section/` `{page_id, section_name}` → `{success, section_name, skipped_languages}`; `POST /editor-v2/api/move-section/` `{page_id, section_name, direction}` → `{success, moved, skipped_languages}`. URL names `api_duplicate_section`, `api_move_section`.

- [ ] **Step 1: Write the failing tests**

Append to `test_structure.py`:

```python
from djangopress.editor_v2.structure import next_free_section_name, duplicate_section, move_section

PAGE = ('<section data-section="hero" id="hero"><a href="#hero">top</a></section>'
        '<section data-section="services" id="services"><a href="#services" class="x">s</a></section>')


class SectionNamesTest(SimpleTestCase):
    def test_first_free_suffix(self):
        s = soup(PAGE)
        self.assertEqual(next_free_section_name(s, 'hero'), 'hero-2')
        s.append(soup('<section data-section="hero-2" id="hero-2"></section>').section)
        self.assertEqual(next_free_section_name(s, 'hero'), 'hero-3')


class DuplicateSectionTest(SimpleTestCase):
    def test_clone_renamed_and_anchor_rewritten(self):
        s = soup(PAGE)
        self.assertTrue(duplicate_section(s, 'services', 'services-2'))
        names = [x['data-section'] for x in s.find_all('section')]
        self.assertEqual(names, ['hero', 'services', 'services-2'])
        clone = s.find('section', attrs={'data-section': 'services-2'})
        self.assertEqual(clone['id'], 'services-2')
        self.assertEqual(clone.a['href'], '#services-2')
        original = s.find('section', attrs={'data-section': 'services'})
        self.assertEqual(original.a['href'], '#services')

    def test_missing_section_returns_false(self):
        self.assertFalse(duplicate_section(soup(PAGE), 'nope', 'nope-2'))


class MoveSectionTest(SimpleTestCase):
    def test_move_up(self):
        s = soup(PAGE)
        self.assertTrue(move_section(s, 'services', 'up'))
        self.assertEqual([x['data-section'] for x in s.find_all('section')], ['services', 'hero'])

    def test_move_at_edge_is_false(self):
        s = soup(PAGE)
        self.assertFalse(move_section(s, 'hero', 'up'))
        self.assertEqual([x['data-section'] for x in s.find_all('section')], ['hero', 'services'])
```

Append to `test_structural_api.py`:

```python
class DuplicateSectionTest(StructuralApiTestCase):
    def test_duplicate_section_in_all_languages(self):
        res = self.post('api_duplicate_section', {'section_name': 'services'})
        data = res.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['section_name'], 'services-2')
        for lang in ('pt', 'en'):
            self.assertIn('data-section="services-2"', self.html(lang))
            self.assertIn('id="services-2"', self.html(lang))
        self.assertEqual(PageVersion.objects.count(), 1)

    def test_second_duplicate_gets_next_suffix(self):
        self.post('api_duplicate_section', {'section_name': 'services'})
        res = self.post('api_duplicate_section', {'section_name': 'services'})
        self.assertEqual(res.json()['section_name'], 'services-3')

    def test_missing_section_is_400(self):
        res = self.post('api_duplicate_section', {'section_name': 'nope'})
        self.assertEqual(res.status_code, 400)


class MoveSectionTest(StructuralApiTestCase):
    def test_move_section_down(self):
        res = self.post('api_move_section', {'section_name': 'services', 'direction': 'down'})
        self.assertTrue(res.json()['moved'])
        for lang in ('pt', 'en'):
            html = self.html(lang)
            self.assertLess(html.index('data-section="cta"'), html.index('data-section="services"'))

    def test_move_section_at_edge_is_noop(self):
        res = self.post('api_move_section', {'section_name': 'services', 'direction': 'up'})
        self.assertTrue(res.json()['success'])
        self.assertFalse(res.json()['moved'])
        self.assertEqual(PageVersion.objects.count(), 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Documents/djangopress-sites/o-marisco && .venv/bin/python manage.py test djangopress.editor_v2 2>&1 | tail -3`
Expected: `ImportError: cannot import name 'next_free_section_name'`

- [ ] **Step 3: Implement the helpers**

Append to `structure.py`:

```python
# ---------------------------------------------------------------------------
# Section verbs
# ---------------------------------------------------------------------------

def _find_section(soup, name):
    return soup.find('section', attrs={'data-section': name})


def next_free_section_name(soup, base):
    """`base-2`, `base-3`, … whichever data-section name is not yet used."""
    used = {s.get('data-section') for s in soup.find_all('section')}
    n = 2
    while f'{base}-{n}' in used:
        n += 1
    return f'{base}-{n}'


def duplicate_section(soup, name, new_name):
    """Clone section `name` right after itself as `new_name`; rewrite in-clone `#name` anchors."""
    section = _find_section(soup, name)
    if section is None:
        return False
    clone = copy.copy(section)
    strip_ids(clone)
    clone['data-section'] = new_name
    clone['id'] = new_name
    for a in clone.find_all('a', href=f'#{name}'):
        a['href'] = f'#{new_name}'
    section.insert_after(clone)
    return True


def move_section(soup, name, direction):
    """Swap section `name` with the adjacent <section>. False when missing or at the edge."""
    section = _find_section(soup, name)
    if section is None:
        return False
    other = section.find_previous_sibling('section') if direction == 'up' else section.find_next_sibling('section')
    if other is None:
        return False
    section = section.extract()
    if direction == 'up':
        other.insert_before(section)
    else:
        other.insert_after(section)
    return True
```

- [ ] **Step 4: Implement the views and routes**

Append to `api_views.py`:

```python
@editor_required
@require_http_methods(["POST"])
def duplicate_section(request):
    """Clone a section after itself with a fresh `name-N` in every language copy."""
    try:
        data = json.loads(request.body)
        section_name = data.get('section_name')
        if not section_name:
            return JsonResponse({'success': False, 'error': 'Missing section_name'}, status=400)

        page = _get_editable_object(data)
        current_html, _lang = _get_page_html(page)
        probe = BeautifulSoup(current_html or '', 'html.parser')
        if probe.find('section', attrs={'data-section': section_name}) is None:
            return JsonResponse({'success': False, 'error': f'Section "{section_name}" not found'}, status=400)
        new_name = structure.next_free_section_name(probe, section_name)

        outcome = _run_structural_verb(
            request, data, f'Duplicated section "{section_name}" as "{new_name}"',
            lambda soup: True if structure.duplicate_section(soup, section_name, new_name) else None,
        )
        if isinstance(outcome, JsonResponse):
            return outcome
        page, _ok, skipped = outcome
        return JsonResponse({'success': True, 'section_name': new_name, 'skipped_languages': skipped, 'page_id': page.id})
    except Page.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Page not found'}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@editor_required
@require_http_methods(["POST"])
def move_section(request):
    """Swap a section with the previous ('up') or next ('down') section in every language copy."""
    try:
        data = json.loads(request.body)
        section_name = data.get('section_name')
        direction = data.get('direction')
        if not section_name:
            return JsonResponse({'success': False, 'error': 'Missing section_name'}, status=400)
        if direction not in ('up', 'down'):
            return JsonResponse({'success': False, 'error': 'direction must be "up" or "down"'}, status=400)

        page = _get_editable_object(data)
        current_html, _lang = _get_page_html(page)
        probe = BeautifulSoup(current_html or '', 'html.parser')
        section = probe.find('section', attrs={'data-section': section_name})
        if section is None:
            return JsonResponse({'success': False, 'error': f'Section "{section_name}" not found'}, status=400)
        neighbour = section.find_previous_sibling('section') if direction == 'up' else section.find_next_sibling('section')
        if neighbour is None:
            return JsonResponse({'success': True, 'moved': False, 'skipped_languages': []})

        outcome = _run_structural_verb(
            request, data, f'Moved section "{section_name}" {direction}',
            lambda soup: True if structure.move_section(soup, section_name, direction) else None,
        )
        if isinstance(outcome, JsonResponse):
            return outcome
        page, _ok, skipped = outcome
        return JsonResponse({'success': True, 'moved': True, 'skipped_languages': skipped, 'page_id': page.id})
    except Page.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Page not found'}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
```

In `urls.py`, after `insert-element`:

```python
    path('api/duplicate-section/', api_views.duplicate_section, name='api_duplicate_section'),
    path('api/move-section/', api_views.move_section, name='api_move_section'),
```

- [ ] **Step 5: Run the whole editor suite plus the core suite**

Run: `cd ~/Documents/djangopress-sites/o-marisco && .venv/bin/python manage.py test djangopress.editor_v2 djangopress.core 2>&1 | grep -E "^Ran|OK|FAIL"`
Expected: `OK` with no failures. (editor_v2 alone is 48 tests at this point; the combined run adds the core suite.)

- [ ] **Step 6: Document the endpoints**

In `src/djangopress/skills/djangopress-architecture/SKILL.md`, in the "Editor API Endpoints" list, add after the `remove-element` line (add that line too if absent):

```
- `POST /editor-v2/api/remove-section/`, `remove-element/` — structural removes (staff)
- `POST /editor-v2/api/duplicate-element/`, `move-element/`, `insert-element/` — clone / swap / insert a node at a selector, applied to every language, no LLM (staff)
- `POST /editor-v2/api/duplicate-section/`, `move-section/` — same for whole sections; duplicate renames to `name-2`, `name-3`… (staff)
```

In the same file's "Gotchas" area add one line: `- **Structural verbs are staff-level (`editor_required`); AI endpoints stay superuser-only.**`

In `CLAUDE.md` (engine root) there is no editor section; add under "Key Reminders":

```
- **Editor structural verbs** (duplicate / move / insert element or section) are deterministic BeautifulSoup patches in `editor_v2/structure.py`, applied to every language copy. Never add an LLM call to them.
```

- [ ] **Step 7: Commit**

```bash
cd ~/Documents/djangopress-sites/djangopress
git add src/djangopress/editor_v2/ src/djangopress/skills/djangopress-architecture/SKILL.md CLAUDE.md
git commit -m "feat(editor): duplicate-section and move-section endpoints; docs"
```

---

## Task 8: Client-side repeat-group detection (`dom.js`)

**Files:**
- Modify: `editor_v2/static/editor_v2/js/lib/dom.js`

**Interfaces:**
- Produces: `export function isRuntimeInjected(el)` (existing private function made public), `export function signatureOf(el) -> string`, `export function findRepeatGroup(el) -> {item, items, container, index} | null` (outermost non-ambiguous group between `el` and its section).

- [ ] **Step 1: Export `isRuntimeInjected` and add the helpers**

In `dom.js`, change `function isRuntimeInjected(el) {` to `export function isRuntimeInjected(el) {`. Then append at the end of the file:

```js
/** "tag|sorted classes" (editor classes excluded). Mirrors structure.signature_of. */
export function signatureOf(el) {
    const classes = Array.from(el.classList).filter(c => !c.startsWith('ev2-')).sort();
    return `${el.tagName.toLowerCase()}|${classes.join(' ')}`;
}

function childSignatureOf(el) {
    return Array.from(el.children).filter(c => !isRuntimeInjected(c)).map(signatureOf).join(',');
}

/**
 * Find the repeat group that contains `el`: walking up to the section, the
 * OUTERMOST level where the current node has at least one sibling with the
 * same signature. Pairs whose children differ (two columns, not two cards)
 * are skipped. Returns { item, items, container, index } or null.
 */
export function findRepeatGroup(el) {
    const section = el?.closest?.('[data-section]');
    if (!section || el === section) return null;

    let found = null;
    let current = el;
    while (current && current !== section) {
        const parent = current.parentElement;
        if (!parent) break;
        const siblings = Array.from(parent.children).filter(s => !isRuntimeInjected(s));
        const sig = signatureOf(current);
        const peers = siblings.filter(s => signatureOf(s) === sig);
        const ambiguousPair = peers.length === 2 && childSignatureOf(peers[0]) !== childSignatureOf(peers[1]);
        if (peers.length >= 2 && !ambiguousPair) {
            found = { item: current, items: peers, container: parent, index: peers.indexOf(current) };
        }
        current = parent;
    }
    return found;
}
```

- [ ] **Step 2: Verify in the browser**

Start a site with several card grids (o-marisco): `cd ~/Documents/djangopress-sites/o-marisco && .venv/bin/python manage.py runserver 8123` (leave running). Log in at `http://127.0.0.1:8123/backoffice/login/` as a staff user, then open `http://127.0.0.1:8123/pt/?edit=v2`.

In the browser console:

```js
const m = await import('/static/editor_v2/js/lib/dom.js');
const h3 = document.querySelector('.editor-v2-content section h3');
const g = m.findRepeatGroup(h3);
console.log(g && g.items.length, g && g.item.className);
```

Expected: a number ≥ 2 and the class string of a card (not of the `h3`). Try one more heading in a two-column "about" section: expected `null` or a group whose items are visually cards.

- [ ] **Step 3: Commit**

```bash
cd ~/Documents/djangopress-sites/djangopress
git add src/djangopress/editor_v2/static/editor_v2/js/lib/dom.js
git commit -m "feat(editor): findRepeatGroup client heuristic"
```

---

## Task 9: `lib/structural.js`, reload-and-reselect, context menu verbs

**Files:**
- Create: `editor_v2/static/editor_v2/js/lib/structural.js`
- Modify: `editor_v2/static/editor_v2/js/modules/context-menu.js`
- Modify: `editor_v2/static/editor_v2/js/editor.js`
- Modify: `editor_v2/static/editor_v2/css/editor.css`

**Interfaces:**
- Produces (from `structural.js`): `duplicateElement(selector)`, `moveElement(selector, 'up'|'down')`, `insertElement(selector, position, html, {after: 'inline-edit'|'image-picker'|null})`, `duplicateSection(name)`, `moveSection(name, direction)`, `removeElement(selector)` (with confirm), `removeSection(name)` (with confirm), `canMove(el, direction) -> bool`, `canMoveSection(sectionEl, direction) -> bool`, `restoreSelection()`.
- Context menu supports items with `disabled: true`.

- [ ] **Step 1: Create `structural.js`**

```js
// editor_v2/static/editor_v2/js/lib/structural.js
/**
 * Client wrappers for the structural verbs (duplicate / move / insert /
 * remove). Each verb POSTs, then reloads the page and re-selects the node
 * whose selector the server returned. State survives the reload in
 * sessionStorage under one key.
 */
import { api } from './api.js';
import { events } from './events.js';
import { isRuntimeInjected } from './dom.js';

const AFTER_RELOAD_KEY = 'ev2-after-reload';
const config = () => window.EDITOR_CONFIG || {};

function body(extra) {
    const cfg = config();
    const b = { page_id: cfg.pageId, ...extra };
    if (cfg.contentTypeId && cfg.objectId) {
        b.content_type_id = cfg.contentTypeId;
        b.object_id = cfg.objectId;
    }
    return b;
}

function reloadWith(state) {
    try { sessionStorage.setItem(AFTER_RELOAD_KEY, JSON.stringify(state || {})); } catch (_) {}
    window.location.reload();
}

async function run(endpoint, payload, afterState) {
    try {
        const res = await api.post(endpoint, body(payload));
        if (!res.success) { alert(res.error || 'Operation failed'); return null; }
        if (res.moved === false) return res; // edge no-op: nothing changed
        if (res.skipped_languages && res.skipped_languages.length) {
            alert(`Applied, but not in: ${res.skipped_languages.join(', ')} (element not found there).`);
        }
        reloadWith(afterState ? afterState(res) : null);
        return res;
    } catch (err) {
        alert('Operation failed: ' + (err.message || err));
        return null;
    }
}

export function duplicateElement(selector) {
    return run('/duplicate-element/', { selector }, r => ({ selector: r.selector }));
}

export function moveElement(selector, direction) {
    return run('/move-element/', { selector, direction }, r => ({ selector: r.selector }));
}

export function insertElement(selector, position, html, { after = null } = {}) {
    return run('/insert-element/', { selector, position, html }, r => ({ selector: r.selector, after }));
}

export function duplicateSection(name) {
    return run('/duplicate-section/', { section_name: name },
        r => ({ selector: `section[data-section="${r.section_name}"]` }));
}

export function moveSection(name, direction) {
    return run('/move-section/', { section_name: name, direction },
        () => ({ selector: `section[data-section="${name}"]` }));
}

export function removeElement(selector) {
    if (!confirm('Remove this element? This can be undone via version history.')) return Promise.resolve(null);
    return run('/remove-element/', { selector }, null);
}

export function removeSection(name) {
    if (!confirm(`Remove section "${name}"? This can be undone via version history.`)) return Promise.resolve(null);
    return run('/remove-section/', { section_name: name }, null);
}

/** True when `el` has an element sibling in that direction (ignoring runtime clones). */
export function canMove(el, direction) {
    if (!el?.parentElement) return false;
    const siblings = Array.from(el.parentElement.children).filter(s => !isRuntimeInjected(s));
    const i = siblings.indexOf(el);
    return direction === 'up' ? i > 0 : i >= 0 && i < siblings.length - 1;
}

export function canMoveSection(sectionEl, direction) {
    const sections = Array.from(document.querySelectorAll('.editor-v2-content [data-section]'));
    const i = sections.indexOf(sectionEl);
    return direction === 'up' ? i > 0 : i >= 0 && i < sections.length - 1;
}

/** Called once after all modules are initialised: re-select what a verb just produced. */
export function restoreSelection() {
    let state = null;
    try {
        const raw = sessionStorage.getItem(AFTER_RELOAD_KEY);
        sessionStorage.removeItem(AFTER_RELOAD_KEY);
        state = raw ? JSON.parse(raw) : null;
    } catch (_) { state = null; }
    if (!state?.selector) return;
    const el = document.querySelector(state.selector);
    if (!el) return;
    events.emit('selection:request', el);
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    if (state.after === 'inline-edit') events.emit('inline-edit:trigger', { element: el });
    if (state.after === 'image-picker') events.emit('image-picker:open');
}
```

- [ ] **Step 2: Rewrite the context menu items**

In `context-menu.js`:

- Replace the imports block at the top with:

```js
import { events } from '../lib/events.js';
import { $, getContentWrapper, isTextElement, getCssSelector } from '../lib/dom.js';
import { insertBefore, insertAfterSection } from './section-inserter.js';
import {
  duplicateElement, moveElement, duplicateSection, moveSection,
  removeElement, removeSection, canMove, canMoveSection,
} from '../lib/structural.js';
```

- Delete `api` import, `withEditableId`, `config`, and the four functions `confirmRemoveSection`, `removeSection`, `confirmRemoveElement`, `removeElement` (they now live in `structural.js`). Keep `esc`, `handlers`, `menu`, `getSection`.

- Replace `buildItems` with:

```js
function buildItems(el) {
  const items = [];
  const section = getSection(el);
  const aiEnabled = !!(window.EDITOR_CONFIG || {}).aiEnabled;

  if (isTextElement(el)) {
    items.push({ label: 'Edit Text', icon: '✎', hint: 'Dbl-click', action: () => events.emit('inline-edit:trigger', { element: el }) });
  }
  if (section) {
    const name = section.getAttribute('data-section');
    const selector = getCssSelector(el);
    const isElement = el !== section && !!selector;

    if (aiEnabled) {
      items.push(null);
      if (isElement) items.push({ label: 'AI Refine Element', icon: '✦', action: () => events.emit('context:ai-refine', { section: name, selector }) });
      items.push({ label: 'AI Refine Section', icon: '✦', action: () => events.emit('context:ai-refine', { section: name }) });
    }

    items.push(null);
    items.push({ label: 'Process Section Images', icon: '⬡', action: () => events.emit('process-images:open', { section: name }) });

    // Element verbs
    if (isElement) {
      items.push(null);
      items.push({ label: 'Duplicate Element', icon: '⧉', action: () => duplicateElement(selector) });
      items.push({ label: 'Move Element Up', icon: '↑', disabled: !canMove(el, 'up'), action: () => moveElement(selector, 'up') });
      items.push({ label: 'Move Element Down', icon: '↓', disabled: !canMove(el, 'down'), action: () => moveElement(selector, 'down') });
      items.push({ label: 'Remove Element', icon: '✕', cls: 'danger', action: () => removeElement(selector) });
    }

    // Section verbs
    items.push(null);
    items.push({ label: 'Insert Section Before', icon: '+', action: () => insertBefore(name) });
    items.push({ label: 'Insert Section After', icon: '+', action: () => insertAfterSection(name) });
    items.push({ label: 'Duplicate Section', icon: '⧉', action: () => duplicateSection(name) });
    items.push({ label: 'Move Section Up', icon: '↑', disabled: !canMoveSection(section, 'up'), action: () => moveSection(name, 'up') });
    items.push({ label: 'Move Section Down', icon: '↓', disabled: !canMoveSection(section, 'down'), action: () => moveSection(name, 'down') });
    items.push({ label: 'Remove Section', icon: '✕', cls: 'danger', action: () => removeSection(name) });
  }

  items.push(null);
  items.push({ label: 'Copy Element HTML', icon: '⎘', action: () => navigator.clipboard.writeText(el.outerHTML) });
  if (section && section !== el) {
    items.push({ label: 'Select Section', icon: '▢', action: () => events.emit('selection:request', section) });
  }
  return items;
}
```

- In `renderMenu`, change the class computation and the click binding so disabled items render greyed and do nothing:

```js
function renderMenu(items) {
  menu.innerHTML = items.map(item => {
    if (!item) return '<div class="ev2-context-sep"></div>';
    const hint = item.hint ? `<span class="ev2-command-result-hint">${esc(item.hint)}</span>` : '';
    const cls = (item.cls ? ` ev2-context-item--${item.cls}` : '') + (item.disabled ? ' ev2-context-item--disabled' : '');
    return `<div class="ev2-context-item${cls}" data-idx="${items.indexOf(item)}">
      <span>${item.icon || ''}</span><span style="flex:1">${esc(item.label)}</span>${hint}
    </div>`;
  }).join('');
  return items;
}
```

and in `showMenu` replace the handler attachment with:

```js
  menu.querySelectorAll('.ev2-context-item').forEach(el => {
    const idx = parseInt(el.dataset.idx);
    const item = items[idx];
    if (!item || item.disabled) return;
    el.addEventListener('click', () => { hideMenu(); item.action(); });
  });
```

- [ ] **Step 3: CSS for disabled items**

Append to `editor.css` after `.ev2-context-item--danger:hover { … }`:

```css
.ev2-context-item--disabled {
  opacity: 0.4;
  cursor: default;
  pointer-events: none;
}
```

- [ ] **Step 4: Call `restoreSelection()` from `editor.js`**

Add the import `import { restoreSelection } from './lib/structural.js';` and, inside the `DOMContentLoaded` handler, after `viewport.init();`:

```js
    restoreSelection();
```

- [ ] **Step 5: Verify in the browser**

With the o-marisco dev server still running, hard-reload `http://127.0.0.1:8123/pt/?edit=v2` (Cmd+Shift+R to bypass module cache). Then:

1. Right-click a card in a grid → **Duplicate Element**. Expected: page reloads, a copy of the card appears right after the original and is selected (blue outline, label badge), scrolled into view.
2. Right-click the copy → **Move Element Up**. Expected: it swaps with the original; the moved copy stays selected.
3. Right-click the first card → **Move Element Up** entry is greyed out and not clickable.
4. Right-click any section → **Move Section Down**. Expected: section order changes in the page and the moved section is selected.
5. Switch language (EN button) and confirm the same structure is present there.
6. Open **Versions** (topbar) and step back one version to confirm the snapshot exists; Cancel.
7. Log in as a staff user who is not a superuser: context menu shows no "AI Refine" items but all verbs work.

- [ ] **Step 6: Commit**

```bash
cd ~/Documents/djangopress-sites/djangopress
git add src/djangopress/editor_v2/static/editor_v2/js/lib/structural.js src/djangopress/editor_v2/static/editor_v2/js/modules/context-menu.js src/djangopress/editor_v2/static/editor_v2/js/editor.js src/djangopress/editor_v2/static/editor_v2/css/editor.css
git commit -m "feat(editor): structural verbs in the context menu with reload-and-reselect"
```

---

## Task 10: "Add another" panel in the Content tab

**Files:**
- Modify: `editor_v2/static/editor_v2/js/modules/sidebar.js`
- Modify: `editor_v2/static/editor_v2/css/editor.css`

**Interfaces:**
- Consumes: `findRepeatGroup` (Task 8), `duplicateElement`, `moveElement`, `removeElement`, `canMove` (Task 9).

- [ ] **Step 1: Add the imports**

At the top of `sidebar.js`, extend the `dom.js` import with `findRepeatGroup` and add:

```js
import { duplicateElement, moveElement, removeElement, canMove } from '../lib/structural.js';
```

- [ ] **Step 2: Add the panel renderer**

Insert this function before `prependContentBreadcrumb`:

```js
/**
 * When the selection sits inside a repeated group (cards, slides, FAQ
 * items…), show the group's size and the verbs that act on the item that
 * contains the selection, not on the selection itself.
 */
function prependRepeatPanel(container) {
    if (!selectedEl) return;
    const group = findRepeatGroup(selectedEl);
    if (!group) return;
    const itemSel = getCssSelector(group.item);
    if (!itemSel) return;

    const wrap = document.createElement('div');
    wrap.className = 'ev2-repeat-panel';
    const n = group.items.length;
    const label = group.item.tagName === 'LI' ? 'item' : 'card';
    wrap.innerHTML = `
        <div class="ev2-children-heading">${n} repeated ${label}${n === 1 ? '' : 's'} (this is #${group.index + 1})</div>
        <div class="ev2-repeat-actions">
            <button type="button" class="ev2-btn-sm ev2-btn-sm-primary" data-repeat="add">+ Add another ${esc(label)}</button>
            <button type="button" class="ev2-btn-sm" data-repeat="up" title="Move before" ${canMove(group.item, 'up') ? '' : 'disabled'}>←</button>
            <button type="button" class="ev2-btn-sm" data-repeat="down" title="Move after" ${canMove(group.item, 'down') ? '' : 'disabled'}>→</button>
            <button type="button" class="ev2-btn-sm ev2-btn-sm-danger" data-repeat="remove">Remove this ${esc(label)}</button>
        </div>`;

    wrap.addEventListener('click', (e) => {
        const btn = e.target.closest('[data-repeat]');
        if (!btn || btn.disabled) return;
        const verb = btn.dataset.repeat;
        if (verb === 'add') duplicateElement(itemSel);
        else if (verb === 'up') moveElement(itemSel, 'up');
        else if (verb === 'down') moveElement(itemSel, 'down');
        else if (verb === 'remove') removeElement(itemSel);
    });

    container.insertBefore(wrap, container.firstChild);
}
```

- [ ] **Step 3: Call it from `renderContentTab`**

Change the last line of `renderContentTab` from:

```js
    prependContentBreadcrumb(c);
```

to:

```js
    prependRepeatPanel(c);
    prependContentBreadcrumb(c);
```

(The breadcrumb is prepended last, so it ends up above the repeat panel.)

- [ ] **Step 4: CSS**

Append to `editor.css`:

```css
/* --------------------------------------------------------------------------
   Repeat-group panel (Content tab)
   -------------------------------------------------------------------------- */
.ev2-repeat-panel {
  margin: 0 0 12px;
  padding: 10px;
  border: 1px solid var(--ev2-border);
  border-radius: var(--ev2-radius);
  background: var(--ev2-bg-subtle);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ev2-repeat-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.ev2-repeat-actions .ev2-btn-sm[disabled] {
  opacity: 0.4;
  cursor: default;
}
```

- [ ] **Step 5: Verify in the browser**

Hard-reload the editor. Click an `h3` inside a card of a grid. Expected in the Content tab: above the text field, a panel "3 repeated cards (this is #1)" with **+ Add another card**, ←, →, **Remove this card**. Click **+ Add another card**: a new card appears after this one and is selected. Click a heading in a two-column about section: no panel. Click a section itself: no panel.

- [ ] **Step 6: Commit**

```bash
cd ~/Documents/djangopress-sites/djangopress
git add src/djangopress/editor_v2/static/editor_v2/js/modules/sidebar.js src/djangopress/editor_v2/static/editor_v2/css/editor.css
git commit -m "feat(editor): Add another / move / remove panel for repeated items"
```

---

## Task 11: Primitives — Add Paragraph / Heading / Button / Image

**Files:**
- Create: `editor_v2/static/editor_v2/js/lib/snippets.js`
- Modify: `editor_v2/static/editor_v2/js/modules/context-menu.js`

**Interfaces:**
- Produces: `buildSnippet(kind, anchorEl) -> string` for `kind` in `'paragraph' | 'heading' | 'button' | 'image'`; `PRIMITIVES` array of `{kind, label, after}`.
- Consumes: `insertElement` (Task 9).

- [ ] **Step 1: Create `snippets.js`**

```js
// editor_v2/static/editor_v2/js/lib/snippets.js
/**
 * Minimal HTML snippets for the "Add …" verbs. Classes are copied from the
 * nearest element of the same kind inside the section so the new element
 * matches the site; defaults are used only when nothing similar exists.
 */

const PLACEHOLDER_IMG = 'data:image/svg+xml;utf8,' + encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600" viewBox="0 0 800 600">'
    + '<rect width="800" height="600" fill="#e5e7eb"/>'
    + '<text x="400" y="310" font-family="sans-serif" font-size="28" fill="#6b7280" text-anchor="middle">Choose an image</text>'
    + '</svg>');

const DEFAULTS = {
    paragraph: { tag: 'p',   classes: 'text-base text-gray-600', text: 'New paragraph' },
    heading:   { tag: 'h3',  classes: 'text-2xl font-bold',       text: 'New heading' },
    button:    { tag: 'a',   classes: 'inline-block px-6 py-3 rounded-lg bg-gray-900 text-white font-semibold', text: 'New button', attrs: { href: '#' } },
    image:     { tag: 'img', classes: 'w-full h-auto rounded-lg', attrs: { src: PLACEHOLDER_IMG, alt: '' } },
};

/** What to do once the new element is selected after reload. */
export const PRIMITIVES = [
    { kind: 'paragraph', label: 'Add Paragraph After', after: 'inline-edit' },
    { kind: 'heading',   label: 'Add Heading After',   after: 'inline-edit' },
    { kind: 'button',    label: 'Add Button After',    after: 'inline-edit' },
    { kind: 'image',     label: 'Add Image After',     after: 'image-picker' },
];

function esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function cleanClasses(el) {
    return Array.from(el.classList).filter(c => !c.startsWith('ev2-')).join(' ');
}

function looksLikeButton(a) {
    const cls = a.className || '';
    return /\bbg-/.test(cls) || /\bborder\b|\bborder-/.test(cls);
}

/** Nearest element inside the section to copy classes from, or null. */
function findModel(kind, anchorEl) {
    const section = anchorEl.closest('[data-section]');
    if (!section) return null;
    const d = DEFAULTS[kind];
    const siblings = Array.from(anchorEl.parentElement?.children || []);
    const pool = [...siblings, ...Array.from(section.querySelectorAll(d.tag))];
    for (const el of pool) {
        if (el.tagName.toLowerCase() !== d.tag) continue;
        if (kind === 'button' && !looksLikeButton(el)) continue;
        if (kind === 'heading' && el === anchorEl) continue;
        if (cleanClasses(el)) return el;
    }
    return null;
}

export function buildSnippet(kind, anchorEl) {
    const d = DEFAULTS[kind];
    if (!d) throw new Error(`Unknown primitive: ${kind}`);
    const model = findModel(kind, anchorEl);
    const tag = model ? model.tagName.toLowerCase() : d.tag;
    const classes = model ? cleanClasses(model) : d.classes;
    const attrs = Object.entries(d.attrs || {}).map(([k, v]) => ` ${k}="${esc(v)}"`).join('');
    if (tag === 'img') return `<img class="${esc(classes)}"${attrs}>`;
    return `<${tag} class="${esc(classes)}"${attrs}>${esc(d.text)}</${tag}>`;
}
```

- [ ] **Step 2: Wire the entries into the context menu**

In `context-menu.js` add the imports:

```js
import { insertElement } from '../lib/structural.js';
import { PRIMITIVES, buildSnippet } from '../lib/snippets.js';
```

(merge `insertElement` into the existing `structural.js` import line.) Inside `buildItems`, in the `if (isElement) { … }` block, before `Duplicate Element`, add:

```js
      for (const p of PRIMITIVES) {
        items.push({ label: p.label, icon: '+', action: () => insertElement(selector, 'after', buildSnippet(p.kind, el), { after: p.after }) });
      }
```

- [ ] **Step 3: Verify in the browser**

Hard-reload. Right-click a paragraph inside a card → **Add Paragraph After**. Expected: reload, a new paragraph "New paragraph" with the same classes as the neighbour, selected and already in inline-edit mode (caret visible, floating B/I/link toolbar). Press Escape; the text stays "New paragraph". Right-click a card heading → **Add Image After**: a grey placeholder image appears and the image picker opens; pick an image and confirm it replaces the placeholder. Right-click a hero CTA link → **Add Button After**: a second button with the same classes appears.

- [ ] **Step 4: Commit**

```bash
cd ~/Documents/djangopress-sites/djangopress
git add src/djangopress/editor_v2/static/editor_v2/js/lib/snippets.js src/djangopress/editor_v2/static/editor_v2/js/modules/context-menu.js
git commit -m "feat(editor): add paragraph / heading / button / image primitives"
```

---

## Task 12: Structure tab — section arrows, `+`, and the listener leak

**Files:**
- Modify: `editor_v2/static/editor_v2/js/modules/sidebar.js`
- Modify: `editor_v2/static/editor_v2/css/editor.css`

**Interfaces:**
- Consumes: `moveSection`, `canMoveSection` (Task 9), `insertAfterSection` from `section-inserter.js`.

Background: `renderStructureTab` currently does `container.addEventListener('click', onTreeClick)` on every render, so the same container accumulates listeners and one click fires N times. Harmless for selection, harmful for a move. Fix it by binding once.

- [ ] **Step 1: Imports**

In `sidebar.js` add:

```js
import { moveSection, canMoveSection } from '../lib/structural.js';
import { insertAfterSection } from './section-inserter.js';
```

(merge into the existing `structural.js` import from Task 10.)

- [ ] **Step 2: Render actions on section rows**

In `renderStructureTab`, replace the section row line:

```js
        html += `<strong>${esc(getTagLabel(section))}</strong></div>`;
```

with:

```js
        const name = section.getAttribute('data-section') || '';
        html += `<strong style="flex:1">${esc(getTagLabel(section))}</strong>`;
        html += `<span class="ev2-tree-actions">`;
        html += `<button type="button" data-tree-action="up" data-name="${esc(name)}" title="Move section up" ${canMoveSection(section, 'up') ? '' : 'disabled'}>▲</button>`;
        html += `<button type="button" data-tree-action="down" data-name="${esc(name)}" title="Move section down" ${canMoveSection(section, 'down') ? '' : 'disabled'}>▼</button>`;
        html += `<button type="button" data-tree-action="insert" data-name="${esc(name)}" title="Insert section after">+</button>`;
        html += `</span></div>`;
```

Remove the line `container.addEventListener('click', onTreeClick);` at the end of `renderStructureTab`.

- [ ] **Step 3: Handle actions in one delegated listener**

Replace `onTreeClick` with:

```js
function onTreeClick(e) {
    const actionBtn = e.target.closest('[data-tree-action]');
    if (actionBtn) {
        e.stopPropagation();
        if (actionBtn.disabled) return;
        const name = actionBtn.dataset.name;
        const action = actionBtn.dataset.treeAction;
        if (action === 'up') moveSection(name, 'up');
        else if (action === 'down') moveSection(name, 'down');
        else if (action === 'insert') insertAfterSection(name);
        return;
    }
    const item = e.target.closest('.ev2-tree-item');
    if (!item) return;
    const sel = item.dataset.treeSelector;
    if (!sel) return;
    const el = document.querySelector(sel);
    if (el) {
        events.emit('selection:request', el);
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
}
```

In `init()`, after the other `bindEl(...)` calls, add:

```js
    handlers.treeClick = onTreeClick;
    bindEl('#ev2-tab-content', 'click', handlers.treeClick);
```

and in `destroy()` add `unbindEl('#ev2-tab-content', 'click', handlers.treeClick);`. Because the listener is now on the tab container for every tab, guard the top of `onTreeClick` with `if (activeTab !== 'structure') return;`.

- [ ] **Step 4: CSS**

Append to `editor.css`:

```css
.ev2-tree-actions {
  display: none;
  gap: 2px;
  margin-left: auto;
}
.ev2-tree-item:hover .ev2-tree-actions,
.ev2-tree-item.current .ev2-tree-actions {
  display: inline-flex;
}
.ev2-tree-actions button {
  width: 22px;
  height: 22px;
  border: 1px solid var(--ev2-border);
  border-radius: var(--ev2-radius);
  background: var(--ev2-bg);
  color: var(--ev2-text-secondary);
  font-size: 11px;
  line-height: 1;
  cursor: pointer;
}
.ev2-tree-actions button:hover { background: var(--ev2-bg-hover); }
.ev2-tree-actions button[disabled] { opacity: 0.35; cursor: default; }
```

- [ ] **Step 5: Verify in the browser**

Hard-reload, open the **Structure** tab. Hover a section row: ▲ ▼ + appear. First section: ▲ disabled. Click ▼ on the first section: one reload, the section is now second, and it is selected. Click a plain row: the element is selected exactly once (check the console for a single `selection:changed`, e.g. temporarily `events.on('selection:changed', () => console.count('sel'))` from the console via the imported module).

- [ ] **Step 6: Commit**

```bash
cd ~/Documents/djangopress-sites/djangopress
git add src/djangopress/editor_v2/static/editor_v2/js/modules/sidebar.js src/djangopress/editor_v2/static/editor_v2/css/editor.css
git commit -m "feat(editor): section move arrows and insert in Structure tab; bind tree click once"
```

---

## Task 13: Insertion bars between sections (Phase 2)

**Files:**
- Modify: `editor_v2/static/editor_v2/js/modules/section-inserter.js`
- Modify: `editor_v2/static/editor_v2/js/modules/section-modal.js`
- Modify: `editor_v2/static/editor_v2/css/editor.css`

**Interfaces:**
- Produces: bars with ids `ev2-insert-bar-<i>` (so `isEditable` ignores them) placed before every section and after the last one; clicking calls the existing `insertPlaceholder(afterName)`. Wrapper gets class `ev2-inserting` while a placeholder is active (bars hidden).

- [ ] **Step 1: Render the bars**

In `section-inserter.js` add, after `removePlaceholder`:

```js
// ---------------------------------------------------------------------------
// Insertion bars (hover "+" between sections)
// ---------------------------------------------------------------------------
let bars = [];

function makeBar(index, afterName) {
    const bar = document.createElement('div');
    bar.className = 'ev2-insert-bar';
    bar.id = `ev2-insert-bar-${index}`;
    bar.innerHTML = '<div class="ev2-insert-bar-line"></div><button type="button" class="ev2-insert-bar-btn" title="Insert section here">+</button>';
    bar.querySelector('button').addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        insertPlaceholder(afterName);
    });
    return bar;
}

function renderBars() {
    removeBars();
    const sections = getSections();
    if (sections.length === 0) return;
    sections.forEach((section, i) => {
        const prev = i === 0 ? null : sections[i - 1].getAttribute('data-section');
        const bar = makeBar(i, prev);
        section.parentNode.insertBefore(bar, section);
        bars.push(bar);
    });
    const last = sections[sections.length - 1];
    const tail = makeBar(sections.length, last.getAttribute('data-section'));
    last.parentNode.insertBefore(tail, last.nextSibling);
    bars.push(tail);
}

function removeBars() {
    bars.forEach(b => b.remove());
    bars = [];
}

function setInserting(on) {
    const wrapper = getContentWrapper();
    if (wrapper) wrapper.classList.toggle('ev2-inserting', on);
}
```

In `insertPlaceholder`, right after `removePlaceholder();` add `setInserting(true);`. In `removePlaceholder`, after resetting state add `setInserting(false);`. In `init()` add `renderBars();` and in `destroy()` add `removeBars();`.

Note: bars are siblings of sections, so they never affect `nth-child` paths inside sections, and `getSections()` only matches `[data-section]`.

- [ ] **Step 2: Message for non-superusers in the modal**

In `section-modal.js` `open()`, after `showGeneratePhase();` add:

```js
    if (!(window.EDITOR_CONFIG || {}).aiEnabled) {
        setStatus('Generating a section with AI needs a superuser account. A section catalogue is coming next.', 'error');
        generateBtn.disabled = true;
    } else {
        generateBtn.disabled = false;
    }
```

- [ ] **Step 3: CSS**

Append to `editor.css`:

```css
/* --------------------------------------------------------------------------
   Insertion bars between sections
   -------------------------------------------------------------------------- */
.ev2-insert-bar {
  position: relative;
  height: 0;
  z-index: 9990;
}
.ev2-insert-bar::before {            /* hit area */
  content: '';
  position: absolute;
  left: 0; right: 0;
  top: -12px;
  height: 24px;
}
.ev2-insert-bar-line {
  position: absolute;
  left: 0; right: 0;
  top: -1px;
  height: 2px;
  background: var(--ev2-accent);
  opacity: 0;
  transition: opacity 0.15s;
}
.ev2-insert-bar-btn {
  position: absolute;
  left: 50%;
  top: -14px;
  transform: translateX(-50%);
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: none;
  background: var(--ev2-accent);
  color: #fff;
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s;
  box-shadow: var(--ev2-shadow-md);
}
.ev2-insert-bar:hover .ev2-insert-bar-line,
.ev2-insert-bar:hover .ev2-insert-bar-btn { opacity: 1; }
.editor-v2-content.ev2-inserting .ev2-insert-bar { display: none; }
```

- [ ] **Step 4: Verify in the browser**

Hard-reload. Move the mouse to the seam between two sections: a thin line and a round **+** appear. Click **+**: the dashed placeholder appears at that seam and the modal opens; bars disappear while the placeholder is active; Cancel restores them. As a non-superuser the modal shows the notice and Generate is disabled. Hover the very bottom of the last section: a bar appears there too.

- [ ] **Step 5: Commit**

```bash
cd ~/Documents/djangopress-sites/djangopress
git add src/djangopress/editor_v2/static/editor_v2/js/modules/section-inserter.js src/djangopress/editor_v2/static/editor_v2/js/modules/section-modal.js src/djangopress/editor_v2/static/editor_v2/css/editor.css
git commit -m "feat(editor): hover insertion bars between sections"
```

---

## Task 14: Floating element toolbar (Phase 2)

**Files:**
- Create: `editor_v2/static/editor_v2/js/modules/element-toolbar.js`
- Modify: `editor_v2/static/editor_v2/js/editor.js`
- Modify: `editor_v2/static/editor_v2/css/editor.css`

**Interfaces:**
- Consumes: `selection:changed`, `inline-edit:start`, `inline-edit:end` events; `structural.js` verbs.

- [ ] **Step 1: Create the module**

```js
// editor_v2/static/editor_v2/js/modules/element-toolbar.js
/**
 * Floating toolbar shown above the selected element with the structural
 * verbs. The context menu remains the complete list; this is the
 * discoverable subset.
 */
import { events } from '../lib/events.js';
import { getCssSelector } from '../lib/dom.js';
import {
    duplicateElement, moveElement, removeElement,
    duplicateSection, moveSection, removeSection,
    canMove, canMoveSection,
} from '../lib/structural.js';

let bar = null;
let current = null;
let unsubs = [];
const handlers = {};

const BUTTONS = [
    { verb: 'duplicate', title: 'Duplicate', icon: '⧉' },
    { verb: 'up',        title: 'Move up',   icon: '↑' },
    { verb: 'down',      title: 'Move down', icon: '↓' },
    { verb: 'remove',    title: 'Remove',    icon: '✕', cls: 'danger' },
    { verb: 'ai',        title: 'Refine with AI', icon: '✦' },
];

function build() {
    bar = document.createElement('div');
    bar.id = 'ev2-element-toolbar';
    bar.className = 'ev2-element-toolbar hidden';
    bar.innerHTML = BUTTONS.map(b =>
        `<button type="button" class="ev2-element-toolbar-btn${b.cls ? ' ev2-element-toolbar-btn--' + b.cls : ''}" data-verb="${b.verb}" title="${b.title}">${b.icon}</button>`
    ).join('');
    bar.addEventListener('mousedown', e => e.preventDefault());
    bar.addEventListener('click', onClick);
    document.body.appendChild(bar);
}

function position() {
    if (!current || !bar) return;
    const rect = current.getBoundingClientRect();
    const h = bar.offsetHeight || 32;
    let top = rect.top - h - 30;                // leave room for the label badge
    if (top < 4) top = rect.bottom + 8;
    const left = Math.max(4, Math.min(rect.right - bar.offsetWidth, window.innerWidth - bar.offsetWidth - 4));
    bar.style.top = `${top}px`;
    bar.style.left = `${left}px`;
}

function refresh() {
    if (!bar) return;
    if (!current || !current.closest('[data-section]')) { bar.classList.add('hidden'); return; }
    const isSection = current.hasAttribute('data-section');
    const aiEnabled = !!(window.EDITOR_CONFIG || {}).aiEnabled;
    bar.querySelector('[data-verb="up"]').disabled = isSection ? !canMoveSection(current, 'up') : !canMove(current, 'up');
    bar.querySelector('[data-verb="down"]').disabled = isSection ? !canMoveSection(current, 'down') : !canMove(current, 'down');
    bar.querySelector('[data-verb="ai"]').style.display = aiEnabled ? '' : 'none';
    bar.classList.remove('hidden');
    position();
}

function onClick(e) {
    const btn = e.target.closest('[data-verb]');
    if (!btn || btn.disabled || !current) return;
    e.preventDefault();
    e.stopPropagation();
    const verb = btn.dataset.verb;
    const section = current.closest('[data-section]');
    const name = section?.getAttribute('data-section');
    const isSection = current === section;
    const selector = getCssSelector(current);

    if (verb === 'duplicate') isSection ? duplicateSection(name) : duplicateElement(selector);
    else if (verb === 'up') isSection ? moveSection(name, 'up') : moveElement(selector, 'up');
    else if (verb === 'down') isSection ? moveSection(name, 'down') : moveElement(selector, 'down');
    else if (verb === 'remove') isSection ? removeSection(name) : removeElement(selector);
    else if (verb === 'ai') events.emit('context:ai-refine', isSection ? { section: name } : { section: name, selector });
}

export function init() {
    build();
    unsubs.push(events.on('selection:changed', (el) => { current = el; refresh(); }));
    unsubs.push(events.on('inline-edit:start', () => bar.classList.add('hidden')));
    unsubs.push(events.on('inline-edit:end', () => refresh()));
    handlers.reposition = () => position();
    window.addEventListener('scroll', handlers.reposition, true);
    window.addEventListener('resize', handlers.reposition);
}

export function destroy() {
    unsubs.forEach(u => u());
    unsubs = [];
    window.removeEventListener('scroll', handlers.reposition, true);
    window.removeEventListener('resize', handlers.reposition);
    bar?.remove();
    bar = null;
    current = null;
}
```

- [ ] **Step 2: Init it**

In `editor.js` add `import * as elementToolbar from './modules/element-toolbar.js';` and call `elementToolbar.init();` after `contextMenu.init();`.

- [ ] **Step 3: CSS**

Append to `editor.css`:

```css
/* --------------------------------------------------------------------------
   Floating element toolbar
   -------------------------------------------------------------------------- */
.ev2-element-toolbar {
  position: fixed;
  z-index: 100002;
  display: flex;
  gap: 2px;
  padding: 3px;
  background: var(--ev2-bg);
  border: 1px solid var(--ev2-border);
  border-radius: var(--ev2-radius-lg);
  box-shadow: var(--ev2-shadow-md);
  font-family: var(--ev2-font);
}
.ev2-element-toolbar.hidden { display: none; }
.ev2-element-toolbar-btn {
  width: 28px;
  height: 28px;
  border: none;
  border-radius: var(--ev2-radius);
  background: transparent;
  color: var(--ev2-text-secondary);
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
}
.ev2-element-toolbar-btn:hover { background: var(--ev2-bg-subtle); color: var(--ev2-text); }
.ev2-element-toolbar-btn[disabled] { opacity: 0.35; cursor: default; }
.ev2-element-toolbar-btn--danger:hover { background: #fee2e2; color: #dc2626; }
```

- [ ] **Step 4: Verify in the browser**

Hard-reload. Click a card: the toolbar appears above its top-right corner with ⧉ ↑ ↓ ✕ (and ✦ only for superusers). Scroll: it follows. Double-click a heading to inline-edit: the toolbar hides, the B/I/link toolbar shows; press Escape: it comes back. Click ⧉: the card is duplicated and the copy is selected with the toolbar over it. Click a section (via breadcrumb or "Select Section"): ↑/↓ act on the section.

- [ ] **Step 5: Commit**

```bash
cd ~/Documents/djangopress-sites/djangopress
git add src/djangopress/editor_v2/static/editor_v2/js/modules/element-toolbar.js src/djangopress/editor_v2/static/editor_v2/js/editor.js src/djangopress/editor_v2/static/editor_v2/css/editor.css
git commit -m "feat(editor): floating element toolbar with structural verbs"
```

---

## Task 15: Command palette entries, cache-busters, final checks

**Files:**
- Modify: `editor_v2/static/editor_v2/js/modules/command-palette.js`
- Modify: `src/djangopress/templates/base.html`
- Modify: `src/djangopress/skills/djangopress-architecture/SKILL.md`

- [ ] **Step 1: Palette entries acting on the current selection**

In `command-palette.js` add imports:

```js
import { getSelected } from './selection.js';
import { getCssSelector } from '../lib/dom.js';
import { duplicateElement, moveElement, removeElement } from '../lib/structural.js';
```

and append to the `commands` array:

```js
  { label: 'Duplicate selected element', action: () => { const s = sel(); if (s) duplicateElement(s); } },
  { label: 'Move selected element up',   action: () => { const s = sel(); if (s) moveElement(s, 'up'); } },
  { label: 'Move selected element down', action: () => { const s = sel(); if (s) moveElement(s, 'down'); } },
  { label: 'Remove selected element',    action: () => { const s = sel(); if (s) removeElement(s); } },
```

with this helper defined above the array:

```js
function sel() {
  const el = getSelected();
  const s = el ? getCssSelector(el) : null;
  if (!s) alert('Select an element inside a section first.');
  return s;
}
```

- [ ] **Step 2: Bump cache-busters**

In `src/djangopress/templates/base.html` change `editor.css' %}?v=20` to `?v=21` and `editor.js' %}?v=34` to `?v=35`.

- [ ] **Step 3: Document the UI in the architecture skill**

In `skills/djangopress-architecture/SKILL.md`, in "The Editor (Inline Editor)" section, add a bullet list under a new line **Structural verbs (2026-09):**

```
- Context menu, floating toolbar (⧉ ↑ ↓ ✕), Content-tab "Add another" panel (repeat groups detected by `findRepeatGroup` in `lib/dom.js`, mirrored by `structure.find_repeat_groups`), Structure-tab arrows, hover "+" bars between sections, Ctrl+K entries.
- All verbs reload and re-select via `sessionStorage['ev2-after-reload']` (`lib/structural.js`).
```

- [ ] **Step 4: Full regression**

Run:

```bash
cd ~/Documents/djangopress-sites/o-marisco && .venv/bin/python manage.py test djangopress 2>&1 | grep -E "^Ran|OK|FAIL|ERROR"
cd ~/Documents/djangopress-sites/o-marisco && .venv/bin/python manage.py check_site 2>&1 | tail -3
```

Expected: all tests `OK`; `check_site` result unchanged from before this branch (run it on `main` first if unsure and compare).

Browser: hard-reload the editor, press Ctrl+K, type "dupl", Enter with a card selected: card duplicated. Run through the verification lists of Tasks 9–14 once more on the EN language to confirm parity.

- [ ] **Step 5: Commit**

```bash
cd ~/Documents/djangopress-sites/djangopress
git add src/djangopress/editor_v2/static/editor_v2/js/modules/command-palette.js src/djangopress/templates/base.html src/djangopress/skills/djangopress-architecture/SKILL.md
git commit -m "feat(editor): palette entries for structural verbs; bump asset versions"
```

- [ ] **Step 6: Hand off**

Use `superpowers:finishing-a-development-branch` to merge or open the PR for `feature/editor-structural-verbs`. Phase 3 (section catalogue) gets its own plan after this branch lands.
