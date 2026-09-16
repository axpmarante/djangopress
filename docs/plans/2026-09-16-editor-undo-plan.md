# Editor v2 One-Click Undo / Redo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every operation the editor commits (structural verb, saved text/class/attribute edits, AI apply, version restore) can be undone and redone with one click by any staff user, across all languages, with a visible label of what will be undone; plus trim the editor to the verbs the user asked for.

**Architecture:** Undo is built on the existing `PageVersion` history. A new `kind` field classifies snapshots: `auto` (the `post_save` signal), `checkpoint` (state BEFORE a user-level operation, labelled with the operation), `undo` (state before an undo ran, i.e. the redo point), `redo` (state before a redo ran). A pure function walks the version list newest-first to find the undo target (the latest checkpoint not consumed by an undo) and the redo target (the latest `undo` snapshot not cancelled by a redo or invalidated by a newer checkpoint). Undo/redo restore `html_content_i18n` only (all languages at once) and record their own snapshots, so nothing is ever lost. The frontend gets Undo/Redo buttons in the topbar, Ctrl+Z routing, a toast after each verb, and the Versions "Restore" uses a staff-level endpoint that restores the whole snapshot.

**Tech Stack:** Django 6 (model field + migration), BeautifulSoup unchanged, Django `TestCase`, vanilla ES modules, Tailwind CDN.

**Spec:** Design approved in chat on 2026-09-16 (recorded in `docs/plans/2026-09-16-editor-add-elements-design.md`, "Direction update"). Branch: `feature/editor-structural-verbs` (continue on it).

## Global Constraints

- Repo: `~/Documents/djangopress-sites/djangopress`. Tests: `cd ~/Documents/djangopress-sites/o-marisco && .venv/bin/python manage.py test djangopress.editor_v2` (plus `djangopress.core` when models change; full `djangopress` once at the end). The `timeout` binary does not exist on macOS.
- Commit messages: no `Co-Authored-By` lines, no `Claude-Session` trailers.
- Undo/redo/restore write only `html_content_i18n` (never title/slug/is_active), so a backoffice title change made meanwhile survives an undo.
- Snapshots are page-level; `GlobalSection` (header/footer) editable objects are out of scope: history endpoints return `{undo: null, redo: null}` for them, and `kind` is only passed to `Page.create_version`.
- Every pre-mutation snapshot in `api_views.py` becomes `kind='checkpoint'` with a short user-facing label (no "Before:" prefix). The automatic post-save snapshot stays `kind='auto'`.
- `Page.create_version` default `max_versions` rises from 20 to 60; `list_page_versions` returns all of them (no `[:10]`).
- All new endpoints are `editor_required`. No LLM calls.
- Cache-busters when done: `editor.js?v=35` → `?v=36`, `editor.css?v=21` → `?v=22`.
- Browser verification on the disposable site `http://127.0.0.1:8123` (`ev2staff`/`ev2staff-pass`, `ev2super`/`ev2super-pass`); never on a real site DB.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/djangopress/core/models.py` | `PageVersion.kind` field; `Page.create_version(kind=...)`; `max_versions=60`. |
| `src/djangopress/core/migrations/0047_pageversion_kind.py` | Migration. |
| `src/djangopress/editor_v2/history.py` (new) | Pure undo/redo target resolution over an ordered version list; `history_state(page)`. |
| `src/djangopress/editor_v2/api_views.py` | Checkpoint labelling of existing pre-snapshots; `checkpoint`, `history_state`, `undo`, `redo`, `restore_version` views; `list_page_versions` returns all versions with `kind`. |
| `src/djangopress/editor_v2/urls.py` | Routes. |
| `src/djangopress/editor_v2/tests/test_history.py` (new) | Unit tests for `history.py` and API tests for the endpoints. |
| `editor_v2/static/editor_v2/js/modules/history.js` (new) | Topbar Undo/Redo buttons, state load, toast, Ctrl+Z routing. |
| `editor_v2/static/editor_v2/js/modules/changes.js` | Checkpoint before save; in-memory undo falls through to server undo when nothing is pending. |
| `editor_v2/static/editor_v2/js/lib/structural.js` | After-reload state carries the verb label for the toast. |
| `editor_v2/static/editor_v2/js/modules/versions.js` | Restore through `/restore-version/`; label shows total. |
| `editor_v2/static/editor_v2/js/modules/context-menu.js`, `js/lib/snippets.js` (delete) | Remove the four "Add … After" primitives. |
| `editor_v2/templates/editor_v2/partials/editor.html`, `css/editor.css` | Buttons and toast markup/styles. |
| `src/djangopress/templates/base.html` | Cache-busters. |
| `skills/djangopress-architecture/SKILL.md`, `CLAUDE.md` | Docs. |

---

## Task 1: `PageVersion.kind` and labelled checkpoints

**Files:**
- Modify: `src/djangopress/core/models.py` (`Page.create_version` ~line 978, `PageVersion` ~line 1176, `Page.restore_to_version` ~line 1031)
- Create: `src/djangopress/core/migrations/0047_pageversion_kind.py` (via `makemigrations`)
- Modify: `src/djangopress/editor_v2/api_views.py` (every `page.create_version(` call: lines ~878, 1073, 1324, 1730, 1796, 1957, 2018, 2079, 2354 at the time of writing)
- Test: `src/djangopress/editor_v2/tests/test_history.py` (new), `tests/test_structural_api.py` (adjust the I5 label test)

**Interfaces:**
- Produces: `PageVersion.kind` (`CharField(max_length=12, default='auto', db_index=True)`, choices `auto|checkpoint|undo|redo`), `Page.create_version(user=None, change_summary='', max_versions=60, kind='auto')`.
- Checkpoint labels (exact): structural verbs keep their `change_summary` (`Duplicated element`, `Moved element up`, `Inserted element (after)`, `Duplicated section "x" as "x-2"`, `Moved section "x" down`); `remove_section` → `Removed section "x"`; `remove_element` → `Removed element`; AI applies keep their existing summaries; `restore_to_version` → `Restore to v{n}`.

- [ ] **Step 1: Write the failing tests**

```python
# src/djangopress/editor_v2/tests/test_history.py
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from djangopress.core.models import Page, PageVersion, SiteSettings

User = get_user_model()

PT = ('<section data-section="services" id="services"><div class="grid">'
      '<div class="card"><h3>Um</h3></div><div class="card"><h3>Dois</h3></div></div></section>')
EN = PT.replace('Um', 'One').replace('Dois', 'Two')
CARD_1 = 'section[data-section="services"] > div:nth-child(1) > div:nth-child(1)'


class HistoryTestCase(TestCase):
    def setUp(self):
        Page.objects.all().delete()
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        self.page = Page.objects.create(title_i18n={'pt': 'Home', 'en': 'Home'},
                                        slug_i18n={'pt': 'home', 'en': 'home'},
                                        is_active=True, html_content_i18n={'pt': PT, 'en': EN})
        PageVersion.objects.filter(page=self.page).delete()
        self.staff = User.objects.create_user('staff', 's@example.com', 'pw', is_staff=True)
        self.client.force_login(self.staff)

    def post(self, name, body, referer='http://testserver/pt/?edit=v2'):
        return self.client.post(reverse(f'editor_v2:{name}'), data=json.dumps({'page_id': self.page.id, **body}),
                                content_type='application/json', HTTP_REFERER=referer)

    def html(self, lang='pt'):
        self.page.refresh_from_db()
        return self.page.html_content_i18n[lang]

    def kinds(self):
        return list(PageVersion.objects.filter(page=self.page).order_by('version_number').values_list('kind', 'change_summary'))


class KindFieldTest(HistoryTestCase):
    def test_default_kind_is_auto_and_signal_snapshots_are_auto(self):
        self.page.html_content_i18n = {'pt': PT + '<!-- x -->', 'en': EN}
        self.page.save()
        self.assertEqual(self.kinds(), [('auto', '')])

    def test_create_version_accepts_kind(self):
        self.page.create_version(user=self.staff, change_summary='Duplicated element', kind='checkpoint')
        self.assertEqual(self.kinds(), [('checkpoint', 'Duplicated element')])

    def test_structural_verb_writes_checkpoint_then_auto(self):
        res = self.post('api_duplicate_element', {'selector': CARD_1})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.kinds(), [('checkpoint', 'Duplicated element'), ('auto', 'Duplicated element')])

    def test_remove_verbs_write_checkpoints(self):
        self.post('api_remove_element', {'selector': CARD_1})
        self.post('api_remove_section', {'section_name': 'services'})
        self.assertEqual([k for k, _ in self.kinds()], ['checkpoint', 'auto', 'checkpoint', 'auto'])
        self.assertEqual(self.kinds()[0][1], 'Removed element')
        self.assertEqual(self.kinds()[2][1], 'Removed section "services"')

    def test_max_versions_is_60(self):
        for i in range(65):
            self.page.create_version(change_summary=f'v{i}', kind='checkpoint')
        self.assertEqual(PageVersion.objects.filter(page=self.page).count(), 60)
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/Documents/djangopress-sites/o-marisco && .venv/bin/python manage.py test djangopress.editor_v2.tests.test_history 2>&1 | tail -4`
Expected: errors mentioning `kind` (`TypeError: ... unexpected keyword argument 'kind'` / `FieldError`).

- [ ] **Step 3: Model + migration**

In `core/models.py`:
- `PageVersion`: add after `change_summary`:
```python
    KIND_CHOICES = [('auto', 'Auto'), ('checkpoint', 'Checkpoint'), ('undo', 'Undo'), ('redo', 'Redo')]
    kind = models.CharField('Kind', max_length=12, default='auto', choices=KIND_CHOICES, db_index=True,
                            help_text='auto = post-save snapshot; checkpoint = state before a user operation; undo/redo = state before an undo/redo ran')
```
- `Page.create_version(self, user=None, change_summary='', max_versions=60, kind='auto')`: pass `kind=kind` to `PageVersion.objects.create(...)`.
- `Page.restore_to_version`: `self.create_version(user, f'Restore to v{version_number}', kind='checkpoint')`.
- `core/signals.py`: unchanged (creates `kind='auto'` by default).

Run: `cd ~/Documents/djangopress-sites/o-marisco && .venv/bin/python manage.py makemigrations core -n pageversion_kind` and confirm the file `src/djangopress/core/migrations/0047_pageversion_kind.py` is created inside the engine package (the app's migrations dir), then `manage.py migrate` on the o-marisco venv's test run is automatic.

- [ ] **Step 4: Label the checkpoints in `api_views.py`**

- `_run_structural_verb`: `page.create_version(user=request.user, change_summary=change_summary, kind='checkpoint')` (drop the `Before: ` prefix); keep `page._change_summary = change_summary` before `save()`.
- `remove_section`: `create_version(user=request.user, change_summary=f'Removed section "{section_name}"', kind='checkpoint')` and set `page._change_summary = f'Removed section "{section_name}"'`, `page._snapshot_user = request.user` before its `page.save()`. Same for `remove_element` with `'Removed element'`.
- Every other `page.create_version(` in the file (AI section/element/page saves, `apply_option`, streams): add `kind='checkpoint'` and keep their summaries. Guard: these calls already sit behind `hasattr(page, 'create_version')`; `GlobalSection.create_version` has no `kind` — wrap as `if isinstance(page, Page): page.create_version(..., kind='checkpoint') else: page.create_version(change_summary=...)` where needed (check each call site's guard).
- In `tests/test_structural_api.py`, change `test_two_versions_have_distinct_labels` to assert `[('checkpoint', 'Duplicated element'), ('auto', 'Duplicated element')]` on `(kind, change_summary)`.

- [ ] **Step 5: Run tests**

Run: `cd ~/Documents/djangopress-sites/o-marisco && .venv/bin/python manage.py test djangopress.editor_v2 djangopress.core 2>&1 | grep -E "^Ran|OK|FAIL|ERROR"`
Expected: OK.

- [ ] **Step 6: Commit**

```bash
git add src/djangopress/core/models.py src/djangopress/core/migrations/0047_pageversion_kind.py src/djangopress/editor_v2/api_views.py src/djangopress/editor_v2/tests/
git commit -m "feat(editor): PageVersion.kind and labelled checkpoints before every editor operation"
```

---

## Task 2: Undo/redo target resolution (`history.py`)

**Files:**
- Create: `src/djangopress/editor_v2/history.py`
- Test: `src/djangopress/editor_v2/tests/test_history.py`

**Interfaces:**
- Produces: `find_undo_target(versions)` and `find_redo_target(versions)` where `versions` is any iterable of objects with `.kind`, `.change_summary`, `.version_number`, `.html_content_i18n`, ordered NEWEST FIRST; return the matching version object or `None`. `history_state(page)` → `{'undo': {'version_number', 'label'} | None, 'redo': {...} | None}`.

- [ ] **Step 1: Write the failing tests**

```python
from types import SimpleNamespace as V
from djangopress.editor_v2.history import find_undo_target, find_redo_target


def seq(*items):
    """items: (kind, label) oldest→newest; returns newest-first list with version numbers."""
    out = [V(kind=k, change_summary=l, version_number=i + 1, html_content_i18n={}) for i, (k, l) in enumerate(items)]
    return list(reversed(out))


class UndoTargetTest(TestCase):
    def test_latest_checkpoint_is_the_target(self):
        vs = seq(('checkpoint', 'op1'), ('auto', ''), ('checkpoint', 'op2'), ('auto', ''))
        self.assertEqual(find_undo_target(vs).change_summary, 'op2')

    def test_auto_only_has_no_target(self):
        self.assertIsNone(find_undo_target(seq(('auto', ''), ('auto', ''))))

    def test_undo_consumes_one_checkpoint(self):
        vs = seq(('checkpoint', 'op1'), ('auto', ''), ('checkpoint', 'op2'), ('auto', ''), ('undo', 'op2'), ('auto', ''))
        self.assertEqual(find_undo_target(vs).change_summary, 'op1')

    def test_redo_cancels_an_undo(self):
        vs = seq(('checkpoint', 'op1'), ('auto', ''), ('checkpoint', 'op2'), ('auto', ''),
                 ('undo', 'op2'), ('auto', ''), ('redo', 'op2'), ('auto', ''))
        self.assertEqual(find_undo_target(vs).change_summary, 'op2')

    def test_two_undos_walk_back_twice(self):
        vs = seq(('checkpoint', 'op1'), ('auto', ''), ('checkpoint', 'op2'), ('auto', ''), ('checkpoint', 'op3'), ('auto', ''),
                 ('undo', 'op3'), ('auto', ''), ('undo', 'op2'), ('auto', ''))
        self.assertEqual(find_undo_target(vs).change_summary, 'op1')


class RedoTargetTest(TestCase):
    def test_latest_undo_is_the_redo_target(self):
        vs = seq(('checkpoint', 'op1'), ('auto', ''), ('undo', 'op1'), ('auto', ''))
        self.assertEqual(find_redo_target(vs).kind, 'undo')

    def test_redo_consumes_the_undo(self):
        vs = seq(('checkpoint', 'op1'), ('auto', ''), ('undo', 'op1'), ('auto', ''), ('redo', 'op1'), ('auto', ''))
        self.assertIsNone(find_redo_target(vs))

    def test_new_checkpoint_invalidates_redo(self):
        vs = seq(('checkpoint', 'op1'), ('auto', ''), ('undo', 'op1'), ('auto', ''), ('checkpoint', 'op2'), ('auto', ''))
        self.assertIsNone(find_redo_target(vs))

    def test_two_undos_two_redos(self):
        vs = seq(('checkpoint', 'op1'), ('auto', ''), ('checkpoint', 'op2'), ('auto', ''),
                 ('undo', 'op2'), ('auto', ''), ('undo', 'op1'), ('auto', ''), ('redo', 'op1'), ('auto', ''))
        self.assertEqual(find_redo_target(vs).change_summary, 'op2')
```

- [ ] **Step 2: Run to verify failure** — `ModuleNotFoundError: djangopress.editor_v2.history`.

- [ ] **Step 3: Implement**

```python
# src/djangopress/editor_v2/history.py
"""
One-click undo/redo over PageVersion snapshots.

Kinds (PageVersion.kind):
  auto        post-save snapshot written by core/signals.py (ignored here)
  checkpoint  state BEFORE a user operation, labelled with that operation
  undo        state BEFORE an undo ran (= the redo point), labelled like the undone op
  redo        state BEFORE a redo ran, labelled like the redone op

Undo target: walking newest→oldest, `undo` adds one pending undo, `redo` removes
one, and a `checkpoint` is either consumed by a pending undo or is the target.
Redo target: walking newest→oldest, `redo` adds one pending redo, `undo` is either
consumed by a pending redo or is the target, and a `checkpoint` (a new operation)
ends the search — there is nothing to redo any more.
"""


def find_undo_target(versions):
    pending_undos = 0
    for v in versions:
        if v.kind == 'undo':
            pending_undos += 1
        elif v.kind == 'redo':
            pending_undos = max(0, pending_undos - 1)
        elif v.kind == 'checkpoint':
            if pending_undos > 0:
                pending_undos -= 1
            else:
                return v
    return None


def find_redo_target(versions):
    pending_redos = 0
    for v in versions:
        if v.kind == 'redo':
            pending_redos += 1
        elif v.kind == 'undo':
            if pending_redos > 0:
                pending_redos -= 1
            else:
                return v
        elif v.kind == 'checkpoint':
            return None
    return None


def _entry(v):
    return {'version_number': v.version_number, 'label': v.change_summary} if v else None


def history_state(page):
    """{'undo': {...}|None, 'redo': {...}|None} for a Page; empty for other editables."""
    versions_rel = getattr(page, 'versions', None)
    if versions_rel is None or not hasattr(page, 'html_content_i18n'):
        return {'undo': None, 'redo': None}
    versions = list(versions_rel.order_by('-version_number').only('kind', 'change_summary', 'version_number'))
    return {'undo': _entry(find_undo_target(versions)), 'redo': _entry(find_redo_target(versions))}
```

(`only()` may not include `html_content_i18n`; the endpoints re-fetch the target by `version_number` when they need its HTML.)

- [ ] **Step 4: Run tests** — expected OK.
- [ ] **Step 5: Commit** — `feat(editor): undo/redo target resolution over version kinds`.

---

## Task 3: Endpoints — checkpoint, history state, undo, redo, restore-version

**Files:**
- Modify: `src/djangopress/editor_v2/api_views.py`, `urls.py`
- Test: `src/djangopress/editor_v2/tests/test_history.py`

**Interfaces:**
- `POST api/checkpoint/` `{page_id, label}` → `{success, version_number}`; creates `kind='checkpoint'` with `change_summary=label[:255]`. 400 on empty label. Non-Page editables → `{success: true, version_number: null}`.
- `GET api/history/<page_id>/` → `{success, undo, redo}` (from `history_state`).
- `POST api/undo/` `{page_id}` → `{success, label, undone_version}`; 400 `Nothing to undo` when no target.
- `POST api/redo/` `{page_id}` → `{success, label}`; 400 `Nothing to redo`.
- `POST api/restore-version/` `{page_id, version_number}` → `{success}`; restores `html_content_i18n` of that version after a checkpoint `Restore to v{n}`.
- `list_page_versions` returns ALL versions and adds `kind` to each entry.

- [ ] **Step 1: Write the failing tests**

```python
class HistoryApiTest(HistoryTestCase):
    def state(self):
        return self.client.get(reverse('editor_v2:api_history', args=[self.page.id])).json()

    def test_state_empty(self):
        self.assertEqual(self.state(), {'success': True, 'undo': None, 'redo': None})

    def test_undo_reverts_a_verb_in_all_languages(self):
        self.post('api_duplicate_element', {'selector': CARD_1})
        self.assertEqual(self.html('pt').count('<h3>Um</h3>'), 2)
        st = self.state()
        self.assertEqual(st['undo']['label'], 'Duplicated element')
        self.assertIsNone(st['redo'])
        res = self.post('api_undo', {})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['label'], 'Duplicated element')
        self.assertEqual(self.html('pt'), PT)
        self.assertEqual(self.html('en'), EN)
        st = self.state()
        self.assertIsNone(st['undo'])
        self.assertEqual(st['redo']['label'], 'Duplicated element')

    def test_redo_reapplies(self):
        self.post('api_duplicate_element', {'selector': CARD_1})
        self.post('api_undo', {})
        res = self.post('api_redo', {})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.html('pt').count('<h3>Um</h3>'), 2)
        self.assertEqual(self.html('en').count('<h3>One</h3>'), 2)
        self.assertEqual(self.state()['undo']['label'], 'Duplicated element')
        self.assertIsNone(self.state()['redo'])

    def test_new_operation_after_undo_clears_redo(self):
        self.post('api_duplicate_element', {'selector': CARD_1})
        self.post('api_undo', {})
        self.post('api_remove_element', {'selector': CARD_1})
        self.assertIsNone(self.state()['redo'])
        self.assertEqual(self.state()['undo']['label'], 'Removed element')

    def test_undo_twice_walks_back_twice(self):
        self.post('api_duplicate_element', {'selector': CARD_1})
        self.post('api_remove_element', {'selector': CARD_1})
        self.post('api_undo', {})
        self.post('api_undo', {})
        self.assertEqual(self.html('pt'), PT)
        self.assertIsNone(self.state()['undo'])

    def test_undo_with_nothing_is_400(self):
        self.assertEqual(self.post('api_undo', {}).status_code, 400)

    def test_undo_keeps_title(self):
        self.post('api_duplicate_element', {'selector': CARD_1})
        self.page.refresh_from_db(); self.page.title_i18n = {'pt': 'Novo', 'en': 'New'}; self.page.save()
        self.post('api_undo', {})
        self.page.refresh_from_db()
        self.assertEqual(self.page.title_i18n['pt'], 'Novo')

    def test_checkpoint_then_manual_edit_is_undoable(self):
        self.post('api_checkpoint', {'label': 'Edits (1)'})
        self.client.post(reverse('editor_v2:api_update_page_content'), data=json.dumps({
            'page_id': self.page.id, 'selector': CARD_1 + ' > h3:nth-child(1)', 'language': 'pt', 'value': 'Alterado'}),
            content_type='application/json')
        self.assertIn('Alterado', self.html('pt'))
        self.post('api_undo', {})
        self.assertNotIn('Alterado', self.html('pt'))

    def test_restore_version_restores_all_languages_and_is_undoable(self):
        self.post('api_duplicate_element', {'selector': CARD_1})
        first = PageVersion.objects.filter(page=self.page, kind='checkpoint').order_by('version_number').first()
        res = self.post('api_restore_version', {'version_number': first.version_number})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.html('pt'), PT)
        self.assertEqual(self.html('en'), EN)
        self.assertEqual(self.state()['undo']['label'], f'Restore to v{first.version_number}')

    def test_list_versions_returns_all_with_kind(self):
        for i in range(12):
            self.post('api_checkpoint', {'label': f'c{i}'})
        res = self.client.get(reverse('editor_v2:api_list_versions', args=[self.page.id])).json()
        self.assertEqual(len(res['versions']), 12)
        self.assertEqual(res['versions'][0]['kind'], 'checkpoint')

    def test_non_staff_cannot_undo(self):
        self.client.force_login(User.objects.create_user('plain', 'p@example.com', 'pw'))
        self.assertEqual(self.post('api_undo', {}).status_code, 302)
```

- [ ] **Step 2: Run to verify failure** — `NoReverseMatch` for `api_history`.

- [ ] **Step 3: Implement**

Append to `api_views.py` (imports: `from djangopress.editor_v2 import history`):

```python
# ---------------------------------------------------------------------------
# One-click undo / redo over PageVersion kinds (see editor_v2/history.py)
# ---------------------------------------------------------------------------

def _apply_snapshot_html(page, version, summary, kind, user):
    """Record the current state as `kind`, then set the page HTML to `version`'s and save."""
    page.create_version(user=user, change_summary=summary, kind=kind)
    page.html_content_i18n = dict(version.html_content_i18n or {})
    page._change_summary = summary
    page._snapshot_user = user
    page.save()


@editor_required
@require_http_methods(["POST"])
def create_checkpoint(request):
    try:
        data = json.loads(request.body)
        label = (data.get('label') or '').strip()[:255]
        if not label:
            return JsonResponse({'success': False, 'error': 'Missing label'}, status=400)
        page = _get_editable_object(data)
        if not page:
            return JsonResponse({'success': False, 'error': 'Page or editable object not found'}, status=400)
        if not isinstance(page, Page):
            return JsonResponse({'success': True, 'version_number': None})
        v = page.create_version(user=request.user, change_summary=label, kind='checkpoint')
        return JsonResponse({'success': True, 'version_number': v.version_number})
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@editor_required
@require_http_methods(["GET"])
def history_state(request, page_id):
    try:
        page = Page.objects.get(pk=page_id)
    except Page.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Page not found'}, status=404)
    return JsonResponse({'success': True, **history.history_state(page)})


def _undo_or_redo(request, direction):
    try:
        data = json.loads(request.body)
        page = _get_editable_object(data)
        if not page or not isinstance(page, Page):
            return JsonResponse({'success': False, 'error': 'Page not found'}, status=400)
        versions = list(page.versions.order_by('-version_number'))
        target = history.find_undo_target(versions) if direction == 'undo' else history.find_redo_target(versions)
        if target is None:
            return JsonResponse({'success': False, 'error': f'Nothing to {direction}'}, status=400)
        _apply_snapshot_html(page, target, target.change_summary, direction, request.user)
        return JsonResponse({'success': True, 'label': target.change_summary, 'page_id': page.id,
                             ('undone_version' if direction == 'undo' else 'redone_version'): target.version_number})
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@editor_required
@require_http_methods(["POST"])
def undo(request):
    return _undo_or_redo(request, 'undo')


@editor_required
@require_http_methods(["POST"])
def redo(request):
    return _undo_or_redo(request, 'redo')


@editor_required
@require_http_methods(["POST"])
def restore_version(request):
    try:
        data = json.loads(request.body)
        page = _get_editable_object(data)
        if not page or not isinstance(page, Page):
            return JsonResponse({'success': False, 'error': 'Page not found'}, status=400)
        try:
            version = page.versions.get(version_number=int(data.get('version_number')))
        except (PageVersion.DoesNotExist, TypeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Version not found'}, status=404)
        _apply_snapshot_html(page, version, f'Restore to v{version.version_number}', 'checkpoint', request.user)
        return JsonResponse({'success': True, 'page_id': page.id})
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
```

Note the semantics: an undo records the CURRENT state as `kind='undo'` labelled with the undone op (that snapshot is the redo point), then applies the target's HTML; the post-save auto snapshot carries the same label. Redo mirrors it with `kind='redo'`. Restore records a `checkpoint` so it is itself undoable.

`list_page_versions`: remove `[:10]`, add `'kind': v.kind` to each entry.

Routes in `urls.py`:
```python
    # Undo / redo / checkpoints
    path('api/checkpoint/', api_views.create_checkpoint, name='api_checkpoint'),
    path('api/history/<int:page_id>/', api_views.history_state, name='api_history'),
    path('api/undo/', api_views.undo, name='api_undo'),
    path('api/redo/', api_views.redo, name='api_redo'),
    path('api/restore-version/', api_views.restore_version, name='api_restore_version'),
```

- [ ] **Step 4: Run tests** — `manage.py test djangopress.editor_v2` OK.
- [ ] **Step 5: Commit** — `feat(editor): checkpoint, history, undo, redo and restore-version endpoints`.

---

## Task 4: Frontend — Undo/Redo buttons, Ctrl+Z routing, toast, save checkpoint, restore path

**Files:**
- Create: `editor_v2/static/editor_v2/js/modules/history.js`
- Modify: `modules/changes.js`, `lib/structural.js`, `modules/versions.js`, `editor.js`, `templates/editor_v2/partials/editor.html`, `css/editor.css`

**Interfaces:**
- `history.js`: `init()/destroy()`, listens `history:refresh`, `history:undo`, `history:redo`; renders `#ev2-undo-topbar-btn` / `#ev2-redo-topbar-btn` (disabled state + `title` = "Undo: <label>"); shows a toast from `sessionStorage['ev2-after-reload'].label`.
- `changes.js`: `undo()` when `undoStack` is empty emits `history:undo`; `redo()` when `redoStack` empty emits `history:redo`; `save()` POSTs `/checkpoint/` with `label: \`Edits (${changes.length})\`` before the first update call (skip when the POST fails? No: if checkpoint fails, abort the save with the error).
- `structural.js`: `run()` stores `label` from the response (`res.label` if present, else a per-verb label passed by the caller) in the after-reload state; add `label` argument to each verb: `duplicateElement` → 'Duplicated element', `moveElement` → 'Moved element', `insertElement` → 'Inserted element', `duplicateSection` → 'Duplicated section', `moveSection` → 'Moved section', `removeElement` → 'Removed element', `removeSection` → 'Removed section'.
- `versions.js`: `restore()` POSTs `/restore-version/` `{page_id, version_number}`; `updateUI` label stays `v{n} / {total}`.

- [ ] **Step 1: Markup** — in `editor.html` topbar right, before the version nav:

```html
    <button id="ev2-undo-topbar-btn" class="ev2-topbar-btn" title="Undo" disabled>
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 14 4 9 9 4"/><path d="M20 20v-7a4 4 0 0 0-4-4H4"/></svg>
      <span id="ev2-undo-label" class="ev2-history-label">Undo</span>
    </button>
    <button id="ev2-redo-topbar-btn" class="ev2-topbar-btn" title="Redo" disabled>
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 14 20 9 15 4"/><path d="M4 20v-7a4 4 0 0 1 4-4h12"/></svg>
    </button>
    <div class="ev2-topbar-sep"></div>
```
and a toast container before the context menu: `<div id="ev2-toast" class="ev2-toast hidden"><span id="ev2-toast-text"></span><button id="ev2-toast-undo" type="button">Undo</button></div>`.

- [ ] **Step 2: `history.js`**

```js
/**
 * One-click Undo / Redo over server-side version checkpoints.
 * In-memory (unsaved) edits are undone by changes.js; once nothing is pending,
 * Ctrl+Z falls through to `history:undo` handled here.
 */
import { events } from '../lib/events.js';
import { api } from '../lib/api.js';
import { $ } from '../lib/dom.js';

const config = () => window.EDITOR_CONFIG || {};
let state = { undo: null, redo: null };
let unsubs = [];
let toastTimer = null;

async function refresh() {
    const pageId = config().pageId;
    if (!pageId || config().contentTypeId) { render(); return; }
    try {
        const res = await api.get(`/history/${pageId}/`);
        if (res.success) state = { undo: res.undo, redo: res.redo };
    } catch (_) { state = { undo: null, redo: null }; }
    render();
}

function render() {
    const u = $('#ev2-undo-topbar-btn'), r = $('#ev2-redo-topbar-btn'), l = $('#ev2-undo-label');
    if (u) { u.disabled = !state.undo; u.title = state.undo ? `Undo: ${state.undo.label}` : 'Nothing to undo'; }
    if (l) l.textContent = state.undo ? `Undo ${shorten(state.undo.label)}` : 'Undo';
    if (r) { r.disabled = !state.redo; r.title = state.redo ? `Redo: ${state.redo.label}` : 'Nothing to redo'; }
}

function shorten(s) { return s.length > 22 ? s.slice(0, 21) + '…' : s; }

function body() {
    const cfg = config();
    const b = { page_id: cfg.pageId };
    if (cfg.contentTypeId && cfg.objectId) { b.content_type_id = cfg.contentTypeId; b.object_id = cfg.objectId; }
    return b;
}

async function run(direction) {
    if (direction === 'undo' && !state.undo) return;
    if (direction === 'redo' && !state.redo) return;
    try {
        const res = await api.post(`/${direction}/`, body());
        if (!res.success) { alert(res.error || `${direction} failed`); return; }
        try { sessionStorage.setItem('ev2-toast-pending', JSON.stringify({ label: `${direction === 'undo' ? 'Undone' : 'Redone'}: ${res.label}`, noUndoToast: true })); } catch (_) {}
        window.location.reload();
    } catch (err) { alert(`${direction} failed: ` + (err.message || err)); }
}

function showToast(text, withUndo) {
    const t = $('#ev2-toast'), txt = $('#ev2-toast-text'), btn = $('#ev2-toast-undo');
    if (!t) return;
    txt.textContent = text;
    btn.style.display = withUndo ? '' : 'none';
    t.classList.remove('hidden');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.add('hidden'), 6000);
}

function toastFromReload() {
    let st = null;
    try { st = JSON.parse(sessionStorage.getItem('ev2-toast-pending') || 'null'); sessionStorage.removeItem('ev2-toast-pending'); } catch (_) {}
    if (st?.label) showToast(st.label, !st.noUndoToast);
}

export function init() {
    $('#ev2-undo-topbar-btn')?.addEventListener('click', () => run('undo'));
    $('#ev2-redo-topbar-btn')?.addEventListener('click', () => run('redo'));
    $('#ev2-toast-undo')?.addEventListener('click', () => run('undo'));
    unsubs.push(events.on('history:refresh', refresh));
    unsubs.push(events.on('history:undo', () => run('undo')));
    unsubs.push(events.on('history:redo', () => run('redo')));
    unsubs.push(events.on('changes:saved', refresh));
    refresh();
    toastFromReload();
}

export function destroy() { unsubs.forEach(u => u()); unsubs = []; clearTimeout(toastTimer); }
```

Coordination with `structural.js`: `restoreSelection()` already consumes `ev2-after-reload`. To keep one owner per key, `structural.js` writes the toast label to a SEPARATE key `ev2-toast-pending` (`{label}`) in `reloadWith`, and `history.run` writes `{label, noUndoToast: true}` to the same key. `history.js` reads only `ev2-toast-pending`.

- [ ] **Step 3: `structural.js`** — each verb passes a label; `run(endpoint, payload, afterState, label)` sets `sessionStorage['ev2-toast-pending'] = JSON.stringify({label})` inside `reloadWith`. Labels as listed in Interfaces.

- [ ] **Step 4: `changes.js`** — in `undo()`: `if (undoStack.length === 0) { events.emit('history:undo'); return; }`; in `redo()`: `if (redoStack.length === 0) { events.emit('history:redo'); return; }`. In `save()`, before the content loop: `await api.post('/checkpoint/', withEditableId({ page_id: pageId, label: \`Edits (${changes.length})\` }, cfg));` inside the same try (a failure aborts the save with the error shown).

- [ ] **Step 5: `versions.js`** — `restore()`: replace the `/save-ai-page/` call with `await api.post('/restore-version/', withEditableId({ page_id: config().pageId, version_number: previewVersion.version_number }));`; drop the `pickHtmlForLang` guard in `restore()` (keep the function for previews).

- [ ] **Step 6: `editor.js`** — import `history` and call `history.init()` after `versions.init()` and before `restoreSelection()`.

- [ ] **Step 7: CSS** — append:

```css
.ev2-history-label { font-size: 12px; max-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ev2-toast { position: fixed; left: 50%; bottom: 24px; transform: translateX(-50%); z-index: 100003; display: flex; gap: 12px; align-items: center; padding: 10px 14px; background: #111827; color: #fff; border-radius: var(--ev2-radius-lg); box-shadow: var(--ev2-shadow-md); font-family: var(--ev2-font); font-size: 13px; }
.ev2-toast.hidden { display: none; }
.ev2-toast button { background: transparent; border: 1px solid rgba(255,255,255,.4); color: #fff; border-radius: var(--ev2-radius); padding: 4px 10px; cursor: pointer; font-size: 12px; }
.ev2-toast button:hover { background: rgba(255,255,255,.12); }
```

- [ ] **Step 8: Browser verification** (disposable site, `ev2staff`):
1. Right-click a card → Duplicate. After reload: toast "Duplicated element · Undo", topbar Undo enabled with title "Undo: Duplicated element". Click Undo → page reloads, card gone, toast "Undone: Duplicated element", Redo enabled. Click Redo → card back.
2. Edit a heading inline, Save → Undo label "Undo Edits (1)"; click → text reverts. Ctrl+Z with nothing pending triggers the same.
3. Switch to EN: the undo state is the same (server-side) and undoing there reverts both languages.
4. Versions: preview an older version, Restore → works as staff; Undo reverts the restore.
5. Screenshots `task-4-undo-*.png` in the SDD workspace.

- [ ] **Step 9: Commit** — `feat(editor): one-click undo/redo with labelled toast; staff-level restore`.

---

## Task 5: Trim primitives, cache-busters, docs, regression

**Files:**
- Modify: `modules/context-menu.js` (remove the primitives loop and the `snippets.js` import), delete `js/lib/snippets.js`
- Modify: `templates/base.html` (`?v=36`, `?v=22`), `skills/djangopress-architecture/SKILL.md`, root `CLAUDE.md`, `docs/plans/2026-09-16-editor-add-elements-design.md` (one line under "Direction update": primitives removed from the menu; `insert-element` stays for AI/tools)

- [ ] **Step 1:** Remove the four "Add … After" items and the `snippets.js` import from `context-menu.js`; `git rm` `lib/snippets.js`. The backend `insert-element` endpoint and its tests stay.
- [ ] **Step 2:** Bump cache-busters.
- [ ] **Step 3:** Docs: architecture skill "Structural verbs" bullets gain "Undo/Redo: `GET api/history/<id>/`, `POST api/undo|redo|checkpoint|restore-version/`; every operation writes a `checkpoint` PageVersion first; see `editor_v2/history.py`". `CLAUDE.md` Key Reminders: one bullet "Editor operations must create a `kind='checkpoint'` PageVersion before mutating, or they are not undoable."
- [ ] **Step 4:** Regression: `manage.py test djangopress` (full) and `check_site` on o-marisco; browser: context menu no longer shows the Add … items; everything from Task 4's checks still works after a hard reload with the new asset versions.
- [ ] **Step 5: Commit** — `feat(editor): drop menu primitives; docs and asset versions for undo`.
