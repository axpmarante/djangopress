# Fast Site Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Take a one-page DjangoPress site from a content-only briefing to a live Railway link in 7–9 minutes unattended, by building three complete HTML concepts in parallel, importing the chosen one through a deterministic adapter, verifying with a browser probe, and publishing with a database push plus a container restart.

**Architecture:** A `djangopress.core.build` package holds pure, testable units — briefing parser, packet builder, concept adapter, importer, content contract, Playwright probe, DNA ledger, prompt filler. Six thin management commands expose them one step per call. A new `build-site` skill composes the commands in ~12 model turns and dispatches one builder agent per concept. The legacy `mockup-site` / `extract-design` / `generate-site` path is untouched and stays available.

**Tech Stack:** Django 6 management commands, `beautifulsoup4` (already a dependency), `playwright` (new optional extra `[build]`), Django test runner from a child site venv, Markdown skills and prompt templates, Railway CLI (`railway redeploy -y`), Litestream (`scripts/sync-to-prod.sh`).

**Spec:** `/Users/antoniomarante/Documents/djangopress-sites/djangopress-manager/docs/superpowers/specs/2026-09-16-fast-site-generation-design.md` (canonical copy, committed in the manager repo at `9cb71df`). Section numbers below (§7, §8.2, …) refer to it.

## Spike results (2026-09-16)
- Design quality: run on checkin-faro (mechanics) and on the agency's own site pwd-v2 (gate; the operator delegated the pick). Three parallel builders, model fable: 5m41s and 8m06s wall clock, 58–81k tokens each, 7–10 sections, none truncated, no forbidden tags. All three concepts radically distinct (editorial / poster / receipt). Concept C shippable as rendered and picked for home; A and B hid most of their content behind scroll-reveal animations in a static render → visibility rule added to the builder contract and `hidden-content` to the probe. **Gate passed.**
- Publish path: not yet timed — pwd-v2 needs a first-time Railway deploy (cloud resources; operator's call). `entrypoint.sh` restores from GCS unconditionally on every start; Task 13 Step 2 times it if the site is deployed by then.

## Run results (2026-09-16)
- **Supervised** (pwd-v2, fresh agent following the skill): 22:54 → pick at 23:07 (13 min: director 2 min, builders 194/200/469 s, screening 30 s). Three concepts visibly distinct, none hid content behind scroll reveals. Resumed with `pick b` at 23:11 after a tooling fix; import 13 s, verify + one fix round 3 min, report + commit at 23:16. `/pt/homepage-v2/` and `/pt/homepage-v3/` render the other two concepts. Not on Railway → `Not on Railway yet` printed. Commit e228764 in pwd-v2.
- **Unattended** (pwd-v2-unattended): 23:21:41 → 23:34:23 = **12 m 42 s**, zero human input; builders 246/210/272 s, 57–63k tokens each. Rule picked a (b lost `clean` on a verbatim false negative — fixed afterwards by the segment rule; c had a `<footer>` inside a section — fixed by hand per the new Turn 4 rule). Commit e7423ee.
- **Promote**: exercised by the unit test only (`promote_concept` on pwd-v2-unattended not run — the shipped concept was the one the rule picked).
- **Probe available**: yes (Chromium in every site venv via the `[build]` extra).
- **Tooling defects found by the runs and fixed on the branch**: contract `Contact` item never matched (f5f9637); punctuation/segment-insensitive verbatim (f5f9637, +1); relative builder output path (f5f9637); `build_verify` probing another site's dev server on :8000 (db09187); publish line refused by the auto-mode classifier (db09187); page links to non-existent pages (db09187); non-truncation hard errors and semantic tags inside `<main>` (+1).
- **Honest comparison with the target**: 7–9 min was the spec's estimate; measured 12–16 min. The whole gap is builder wall clock (the slowest of three, 3.5–8 min per page). Everything deterministic totals under 3 min. Next lever: shorter builder outputs or a faster builder model, not more automation.

## Global Constraints

- **Repo:** `/Users/antoniomarante/Documents/djangopress-sites/djangopress`. Work on branch `feature/fast-site-generation`, created with `git checkout -b feature/fast-site-generation` from the current HEAD of `feature/editor-structural-verbs` (same checkout, no worktree — every child site's venv is an editable install of this path). The working tree already holds **uncommitted editor changes** (`src/djangopress/ai/views.py`, `src/djangopress/editor_v2/…`, `src/djangopress/skills/djangopress-architecture/SKILL.md`, `briefings/lalitana.md`). Never stage them: `git add` only the files each task names. Never `git stash`, `git checkout -- <file>` or `git reset`.
- **Tests run from a child site with the editable install:** `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py test djangopress.core.tests.<module> -v 1`. Tests never touch the network: `urllib.request.urlopen` and `subprocess` are patched wherever a unit would call them. Tests that need Playwright call `self.skipTest` when `import playwright` fails.
- **Existing helpers to reuse, never re-implement:** `djangopress.core.models.SiteSettings.load()`, `Page.create_version(change_summary=…)`, `GlobalSection.create_version(change_summary=…)`, `djangopress.core.middleware.NON_I18N_PATHS`, `django.utils.text.slugify`, the `make_valid_site()` fixture in `src/djangopress/core/tests/test_check_site.py`.
- **`MenuService.create` and `build_i18n_field` auto-translate through an LLM.** The importer writes `MenuItem` rows with the ORM and `label_i18n={lang: label}` only.
- **Editor-v2 editable tags:** `h1 h2 h3 h4 h5 h6 p span a li td th label button blockquote`.
- **Section names** must match `^[a-z][a-z0-9-]*$` and `data-section == id` (from `check_site.py`).
- **`check_site` acceptable residue on this path:** `[images]` lines reading `unresolved placeholder` or `leftover data-image-* attribute`. Anything else is a failure.
- **Language prefix rule:** `#x` → `/<lang>/#x`; `/x/` → `/<lang>/x/` unless it starts with `/<code>/` for an enabled code or with one of `NON_I18N_PATHS`; `http(s)://`, `mailto:`, `tel:`, `//` untouched.
- **`base.html` facts:** it loads `https://cdn.tailwindcss.com` itself; renders `CUSTOM_HEAD_CODE` late in `<head>`; hardcodes `<body class="bg-white">`; builds the Google Fonts URL from `heading_font`/`body_font`. GlobalSection HTML is rendered through `django.template.Template`, so `{{`, `{%`, `{#` in a header/footer are executed.
- **Files produced in a site:** `docs/build-packet.json`, `docs/concepts/brief-<k>.md`, `docs/concepts/concept-<k>.html`, `docs/concepts/concepts.json`, `docs/concepts/prompts/director.md`, `docs/concepts/prompts/builder-<k>.md`, `docs/concepts/import-<k>.json`, `docs/concepts/screen.json`, `docs/verify.json`, `docs/screenshots/home-390.png`, `docs/build-report.md`. Ledger: `$DJANGOPRESS_SITES_ROOT/.design-dna/ledger.json`, default `Path.cwd().parent / '.design-dna' / 'ledger.json'`.
- **Concept keys** are single lowercase letters `a`–`f`. Order of preference when unattended: `b, a, c, d, e, f`.
- **Visibility rule (from the spike):** builders never hide content behind scroll reveals (`opacity-0` + `x-intersect`/IntersectionObserver); counters carry their final number in the HTML. The probe scrolls the whole page before measuring and reports `hidden-content`; `BLOCKING_KINDS` includes it.
- **Extra pages (operator request):** every concept that is not shipped is imported with `import_concept --as-page homepage-v2` / `homepage-v3`, outside the menu, with its own fonts link + `tailwind.config` + `<style>` appended to its page HTML. Those pages render inside the shipped concept's header and footer.
- **Task 13 runs on `pwd-v2`** (already scaffolded, briefing at `pwd-v2/briefings/pwd-v2.md`), not on a casa-teste scratch site.
- **Commit messages must not contain `Co-Authored-By`.** Commit only the files named in each task.
- **Skills are live on save** (symlinked into every child site): write a whole new skill file in one `Write`; edit existing skills with precise `Edit` calls.
- **Do not run anything against a real client site.** Task 13 is the guided end-to-end run and names the only site it may touch.

---

## File structure

```
src/djangopress/core/build/                 ← new package, pure logic
  __init__.py
  briefing.py        parse_briefing(text) -> Briefing            (Task 1)
  packet.py          build_packet(...), detect_vertical(...)     (Task 2)
  ledger.py          Ledger(path).read/append/mark_shipped       (Task 3)
  adapter.py         adapt(html, ...) -> AdaptResult             (Tasks 4, 5)
  importer.py        import_result(result, packet, ...)          (Task 6)
  jsonld.py          build_jsonld(packet) -> dict                (Task 6)
  contract.py        check_contract(packet, parts, lang)         (Task 7)
  probe.py, probe.js run_probe(url, ...) -> dict                 (Task 8)
  prompts.py         fill_director(...), fill_builder(...)       (Task 10)
src/djangopress/core/management/commands/
  build_prepare.py   (Task 2)     concept_ledger.py  (Task 3)
  import_concept.py  (Task 6)     build_verify.py    (Task 8)
  promote_concept.py (Task 9)     build_prompt.py    (Task 10)
src/djangopress/core/tests/
  fixtures/concept-checkin-faro.html   the operator's 288 KB ChatGPT page (Task 4)
  fixtures/concept-minimal.html        3-section synthetic document (Task 4)
  test_build_briefing.py test_build_packet.py test_build_ledger.py
  test_build_adapter.py test_build_importer.py test_build_contract.py
  test_build_probe.py test_build_prompts.py test_build_promote.py
src/djangopress/skills/build-site/SKILL.md            (Task 11)
src/djangopress/skills/build-site/prompts/director.md (Task 10)
src/djangopress/skills/build-site/prompts/builder.md  (Task 10)
src/djangopress/skills/create-briefing/SKILL.md       (Task 12, edits)
briefings/TEMPLATE.md                                 (Task 1, edits)
pyproject.toml, scripts/new_site.sh                   (Task 8, edits)
```

Commands stay under 60 lines each: argument parsing, one call into `core.build`, JSON out, exit code.

---

### Task 0: Validation spike (operator + main session, no subagent)

This is §14 of the spec. It produces an answer, not code. Nothing from it is committed except the two numbers it records.

**Files:**
- Read: spec §6.1 and §6.2 (the prompt templates)
- Read: `/Users/antoniomarante/Documents/djangopress-sites/checkin-faro/briefings/checkin-faro.md`
- Read: `/Users/antoniomarante/Downloads/checkin-faro-homepage-v2-red-creative.html` (baseline)
- Scratch only: `/private/tmp/…/spike/` (nothing under a site or the engine)

- [ ] **Step 1: Hand-fill the director prompt**

Copy §6.1 into `spike/director.md`. Fill `[VERTICAL_SPECIALIZATION]` = `hospitality, restaurants and premium consumer brands`; BRIEF = the `## Business` prose of `checkin-faro.md` plus its `## Pages` → Home entry rewritten as content items (no section order); DESIGN CONSTRAINTS = brand colors `#C51B17 red, #40308A plum, #F6E500 yellow` (from the audit's logo description), avoid list from `## Design Preferences` → Reference/Avoid lines, image constraint `dish photos up to 2048px; interiors 1600px; no exterior photos`; `[N]` = 3; PREVIOUSLY USED = `none yet`.

- [ ] **Step 2: Run the director, split the output**

Run the prompt in this session (one turn). Save each concept between `===== CONCEPT X =====` delimiters to `spike/brief-a.md`, `brief-b.md`, `brief-c.md`. Record the wall clock.

- [ ] **Step 3: Hand-fill three builder prompts and dispatch three agents in one message**

Copy §6.2 into `spike/builder-<k>.md` ×3 with the matching brief, the content items, the audit's example image URLs as the photo list, and `[OUTPUT_PATH]` = `spike/concept-<k>.html`. Dispatch three `Agent`s (general-purpose) in a single message. Record wall clock from dispatch to the last report, and each agent's token usage from the task notification.

- [ ] **Step 4: Judge**

`open spike/concept-*.html /Users/antoniomarante/Downloads/checkin-faro-homepage-v2-red-creative.html`. Operator answers, per concept: (a) distinct from the other two? (b) shippable as a client's first look? (c) at least as good as the baseline? Also note: did any output stop before `</html>`?

- [ ] **Step 5: Publish path**

On a site that is already on Railway and is not a live client site (the operator names it), change one word in a page via the backoffice, then time:

```bash
bash scripts/sync-to-prod.sh && railway redeploy -y
```

Confirm the word is live. Record seconds.

- [ ] **Step 6: Gate**

Exit criteria: at least two of three concepts shippable; publish live in under 2 minutes with no image build. Write both results as two lines at the top of this plan under a `## Spike results (date)` heading and commit that edit alone:

```bash
cd /Users/antoniomarante/Documents/djangopress-sites/djangopress
git add docs/plans/2026-09-16-fast-site-generation-plan.md
git commit -m "docs: spike results for fast site generation"
```

If the design criterion fails, stop: the spec's §14 says the architecture changes. Do not start Task 1.

---

### Task 1: Briefing parser and the new `TEMPLATE.md` shape

**Files:**
- Create: `src/djangopress/core/build/__init__.py` (empty)
- Create: `src/djangopress/core/build/briefing.py`
- Modify: `briefings/TEMPLATE.md` (sections `## Pages`, new `## Content`, `## Design Preferences` → `## Design Constraints`)
- Test: `src/djangopress/core/tests/test_build_briefing.py`

**Interfaces:**
- Produces: `parse_briefing(text: str) -> Briefing` and the dataclasses `Briefing`, `ContentItem` (fields below). Task 2 consumes `Briefing`; Task 7 consumes `ContentItem`.

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for the briefing parser (docs/plans/2026-09-16-fast-site-generation-plan.md, Task 1)."""

from django.test import SimpleTestCase

from djangopress.core.build.briefing import parse_briefing


SAMPLE = """# CHECKin Faro — Site Briefing

> Redesign of https://checkinfaro.pt

## Business

Cozinha de autor algarvia, à carta, para partilhar. Chef Leonel Pereira.

Segundo parágrafo.

## Languages
- Default: pt (Português)
- Additional: en (English)

## Contact
- Email: geral@checkinfaro.pt
- Phone: +351 289 000 000
- Address: Rua do Castelo 1, Faro
- Google Maps: https://maps.google.com/?q=37.0146,-7.9350

### Opening hours
- Terça a Sábado: 19:00–23:00
- Domingo e Segunda: encerrado

## Social Media
- Instagram: https://instagram.com/checkinfaro
- Facebook: https://facebook.com/checkinfaro

## Pages
- **Home**: the one-page site
- **Reservas**: form (reuse the template's `contact` DynamicForm)

## Content

### Home
- (required) Message: Cozinha de autor algarvia, à carta, para partilhar — keywords: autor, algarvia, partilhar
- (required) CTA: Reservar mesa → /reservas/
- (required) Proof: Guia Michelin 2024
- (required) Menu: every item name and price from briefings/checkin-faro-menu.json
- Story: o chef, a sala, os produtores

## Header
logo left, 5 links, one CTA, language switcher

## Footer
contact, hours, social icons, privacy link, copyright

## Design Constraints
- **Brand colors**: #C51B17 red, #40308A plum
- **Logo / brand assets**: none
- **Avoid**: orange accents; photo carousel hero
- **References**: https://example.com/a, https://example.com/b
- **Image constraints**: dishes 2048px, interiors 1600px

## Images
- **Strategy**: reuse existing
- **Sources**: old site gallery
- **Constraints**: dishes 2048px, space 1600px

## Domain
checkin-faro

## Additional Notes
jsonld: Restaurant
cuisine: Algarvia
price range: €€€
"""


class ParseBriefingTest(SimpleTestCase):

    def setUp(self):
        self.b = parse_briefing(SAMPLE)

    def test_title_and_business(self):
        self.assertEqual(self.b.title, 'CHECKin Faro')
        self.assertTrue(self.b.business.startswith('Cozinha de autor'))
        self.assertIn('Segundo parágrafo.', self.b.business)

    def test_languages(self):
        self.assertEqual(self.b.default_language, 'pt')
        self.assertEqual(self.b.languages, ['pt', 'en'])

    def test_contact_hours_social(self):
        self.assertEqual(self.b.contact['email'], 'geral@checkinfaro.pt')
        self.assertEqual(self.b.contact['phone'], '+351 289 000 000')
        self.assertEqual(self.b.contact['address'], 'Rua do Castelo 1, Faro')
        self.assertEqual(self.b.contact['maps_url'], 'https://maps.google.com/?q=37.0146,-7.9350')
        self.assertEqual(self.b.hours, ['Terça a Sábado: 19:00–23:00', 'Domingo e Segunda: encerrado'])
        self.assertEqual(self.b.social['instagram'], 'https://instagram.com/checkinfaro')

    def test_pages(self):
        self.assertEqual([p['slug'] for p in self.b.pages], ['home', 'reservas'])
        self.assertEqual(self.b.pages[0]['name'], 'Home')

    def test_content_items(self):
        items = self.b.content['home']
        self.assertEqual(len(items), 5)
        first = items[0]
        self.assertEqual(first.id, 'home-1')
        self.assertTrue(first.required)
        self.assertEqual(first.kind, 'Message')
        self.assertEqual(first.text, 'Cozinha de autor algarvia, à carta, para partilhar')
        self.assertEqual(first.keywords, ['autor', 'algarvia', 'partilhar'])
        cta = items[1]
        self.assertEqual(cta.href, '/reservas/')
        self.assertEqual(cta.text, 'Reservar mesa')
        menu = items[3]
        self.assertEqual(menu.menu_json, 'briefings/checkin-faro-menu.json')
        self.assertFalse(items[4].required)

    def test_constraints(self):
        c = self.b.constraints
        self.assertEqual(c['brand_colors'], ['#C51B17', '#40308A'])
        self.assertIsNone(c['logo'])
        self.assertEqual(c['avoid'], ['orange accents', 'photo carousel hero'])
        self.assertEqual(c['references'], ['https://example.com/a', 'https://example.com/b'])
        self.assertEqual(c['image_max_widths'], {'dishes': 2048, 'interiors': 1600})

    def test_notes_and_flags(self):
        self.assertEqual(self.b.notes['jsonld'], 'Restaurant')
        self.assertEqual(self.b.notes['cuisine'], 'Algarvia')
        self.assertEqual(self.b.notes['price range'], '€€€')
        self.assertFalse(self.b.has_open_questions)
        self.assertEqual(self.b.images['strategy'], 'reuse existing')
        self.assertEqual(self.b.header, 'logo left, 5 links, one CTA, language switcher')

    def test_open_questions_detected(self):
        b = parse_briefing(SAMPLE.replace('## Business', '## Open Questions\n1. x?\n\n## Business'))
        self.assertTrue(b.has_open_questions)

    def test_bad_content_line_raises(self):
        bad = SAMPLE.replace('- (required) Proof: Guia Michelin 2024', '- (required) no colon here')
        with self.assertRaises(ValueError) as cm:
            parse_briefing(bad)
        self.assertIn('no colon here', str(cm.exception))
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py test djangopress.core.tests.test_build_briefing -v 1 2>&1 | tail -5`
Expected: `ImportError` / `ModuleNotFoundError: No module named 'djangopress.core.build'`

- [ ] **Step 3: Write the parser**

`src/djangopress/core/build/__init__.py`: empty file.

`src/djangopress/core/build/briefing.py`:

```python
"""Parse a content-only site briefing (briefings/<slug>.md) into a Briefing.

The briefing describes WHAT the site says; design lives in the concepts.
Grammar of a `## Content` line:
    - (required)? <Kind>: <text> [— keywords: a, b, c] [→ <href>]
"""

import re
from dataclasses import dataclass, field

from django.utils.text import slugify

HEADING_RE = re.compile(r'^(#{2,3})\s+(.*?)\s*$')
CONTENT_LINE_RE = re.compile(r'^-\s*(?P<req>\(required\)\s*)?(?P<kind>[^:]+?):\s*(?P<rest>.*)$')
KEYWORDS_SPLIT_RE = re.compile(r'\s+[—-]\s+keywords:\s*', re.I)
HREF_SPLIT_RE = re.compile(r'\s+→\s+|\s+->\s+')
MENU_JSON_RE = re.compile(r'(briefings/[\w.-]+-menu\.json)')
HEX_RE = re.compile(r'#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b')
WIDTH_RE = re.compile(r'([\wÀ-ÿ /]+?)\s+(\d{3,4})\s*px', re.I)
BULLET_RE = re.compile(r'^-\s*(?:\*\*(?P<bkey>[^*]+)\*\*|(?P<key>[^:]+?))\s*:\s*(?P<val>.*)$')
PAGE_RE = re.compile(r'^-\s*\*\*(?P<name>[^*]+)\*\*\s*:\s*(?P<desc>.*)$')
LANG_RE = re.compile(r'([a-z]{2})(?:\s*\(([^)]*)\))?')


@dataclass
class ContentItem:
    id: str
    kind: str
    text: str
    required: bool = False
    keywords: list = field(default_factory=list)
    href: str | None = None
    menu_json: str | None = None


@dataclass
class Briefing:
    title: str = ''
    business: str = ''
    default_language: str = 'pt'
    languages: list = field(default_factory=list)          # codes, default first
    language_names: dict = field(default_factory=dict)     # code -> name
    contact: dict = field(default_factory=dict)            # email, phone, address, maps_url
    hours: list = field(default_factory=list)              # raw lines
    social: dict = field(default_factory=dict)             # instagram -> url
    pages: list = field(default_factory=list)              # [{name, slug, description}]
    content: dict = field(default_factory=dict)            # page slug -> [ContentItem]
    header: str = ''
    footer: str = ''
    constraints: dict = field(default_factory=dict)        # brand_colors, logo, avoid, references, image_max_widths
    images: dict = field(default_factory=dict)             # strategy, sources, constraints
    domain: str = ''
    notes: dict = field(default_factory=dict)              # lowercased "key: value" lines from Additional Notes
    has_open_questions: bool = False


def _sections(text):
    """Split markdown into an ordered list of (level, heading, body_lines)."""
    out = []
    current = None
    for line in text.splitlines():
        m = HEADING_RE.match(line)
        if m:
            current = (len(m.group(1)), m.group(2).strip(), [])
            out.append(current)
        elif current is not None:
            current[2].append(line)
    return out


def _bullets(lines):
    """`- Key: value` and `- **Key**: value` lines -> {key.lower(): value}."""
    result = {}
    for line in lines:
        m = BULLET_RE.match(line.strip())
        if m:
            key = (m.group('bkey') or m.group('key')).strip().lower()
            result[key] = m.group('val').strip()
    return result


def _parse_content_line(line, page_slug, index):
    m = CONTENT_LINE_RE.match(line.strip())
    if not m:
        raise ValueError(f'Malformed content line (expected "- (required) Kind: text"): {line.strip()!r}')
    rest = m.group('rest').strip()
    keywords = []
    parts = KEYWORDS_SPLIT_RE.split(rest, maxsplit=1)
    if len(parts) == 2:
        rest, kw = parts
        keywords = [k.strip() for k in kw.split(',') if k.strip()]
    href = None
    parts = HREF_SPLIT_RE.split(rest, maxsplit=1)
    if len(parts) == 2:
        rest, href = parts[0].strip(), parts[1].strip()
    menu = MENU_JSON_RE.search(rest)
    return ContentItem(
        id=f'{page_slug}-{index}',
        kind=m.group('kind').strip(),
        text=rest.strip(),
        required=bool(m.group('req')),
        keywords=keywords,
        href=href,
        menu_json=menu.group(1) if menu else None,
    )


def _parse_languages(lines):
    b = _bullets(lines)
    default = 'pt'
    names = {}
    codes = []
    m = LANG_RE.match(b.get('default', 'pt'))
    if m:
        default = m.group(1)
        names[default] = (m.group(2) or default).strip()
    codes.append(default)
    for m in LANG_RE.finditer(b.get('additional', '')):
        code = m.group(1)
        if code not in codes:
            codes.append(code)
            names[code] = (m.group(2) or code).strip()
    return default, codes, names


def _parse_constraints(lines):
    b = _bullets(lines)
    colors = HEX_RE.findall(b.get('brand colors', ''))
    logo = b.get('logo / brand assets', b.get('logo', '')).strip()
    widths = {}
    for label, px in WIDTH_RE.findall(b.get('image constraints', '')):
        widths[label.strip().lower().replace(' ', '-')] = int(px)
    return {
        'brand_colors': colors,
        'logo': None if logo.lower() in ('', 'none') else logo,
        'avoid': [a.strip() for a in re.split(r';|\n', b.get('avoid', '')) if a.strip()],
        'references': [r.strip() for r in b.get('references', '').split(',') if r.strip()],
        'image_max_widths': widths,
    }


def parse_briefing(text):
    briefing = Briefing()
    first = next((l for l in text.splitlines() if l.startswith('# ')), '')
    briefing.title = first[2:].split('—')[0].strip()

    current_h2 = ''
    for level, heading, lines in _sections(text):
        key = heading.lower()
        body = '\n'.join(lines).strip()
        if level == 2:
            current_h2 = key
        if level == 2 and key == 'open questions':
            briefing.has_open_questions = bool(body)
        elif level == 2 and key == 'business':
            briefing.business = body
        elif level == 2 and key == 'languages':
            briefing.default_language, briefing.languages, briefing.language_names = _parse_languages(lines)
        elif level == 2 and key == 'contact':
            b = _bullets(lines)
            briefing.contact = {
                'email': b.get('email', ''), 'phone': b.get('phone', ''),
                'address': b.get('address', ''), 'maps_url': b.get('google maps', ''),
            }
        elif level == 3 and key == 'opening hours':
            briefing.hours = [l.strip()[2:].strip() for l in lines if l.strip().startswith('- ')]
        elif level == 2 and key == 'social media':
            briefing.social = {k: v for k, v in _bullets(lines).items() if v}
        elif level == 2 and key == 'pages':
            for line in lines:
                m = PAGE_RE.match(line.strip())
                if m:
                    name = m.group('name').strip()
                    slug = 'home' if name.lower() in ('home', 'início', 'inicio') else slugify(name)
                    briefing.pages.append({'name': name, 'slug': slug, 'description': m.group('desc').strip()})
        elif level == 2 and key == 'content':
            pass
        elif level == 3 and current_h2 == 'content':
            name = heading.strip()
            page_slug = 'home' if name.lower() in ('home', 'início', 'inicio') else slugify(name)
            items = []
            for line in lines:
                if line.strip().startswith('- '):
                    items.append(_parse_content_line(line, page_slug, len(items) + 1))
            briefing.content[page_slug] = items
        elif level == 2 and key == 'header':
            briefing.header = body
        elif level == 2 and key == 'footer':
            briefing.footer = body
        elif level == 2 and key in ('design constraints', 'design preferences'):
            briefing.constraints = _parse_constraints(lines)
        elif level == 2 and key == 'images':
            briefing.images = _bullets(lines)
        elif level == 2 and key == 'domain':
            briefing.domain = body.strip('`').strip()
        elif level == 2 and key == 'additional notes':
            for line in lines:
                if ':' in line and not line.startswith('#'):
                    k, v = line.split(':', 1)
                    briefing.notes[k.strip().lower()] = v.strip()
    return briefing
```

- [ ] **Step 4: Run the tests**

Run: `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py test djangopress.core.tests.test_build_briefing -v 1 2>&1 | tail -5`
Expected: `Ran 9 tests … OK`

- [ ] **Step 5: Update `briefings/TEMPLATE.md`**

Replace the `## Pages` block (from `## Pages` up to but not including `## Header`) with:

```markdown
## Pages

[One entry per page: what the page is for and its meta. Do NOT list sections in order —
the design concept decides how content is grouped and sequenced.]

- **Home**: the one-page site — meta title: [..]; meta description: [..]
- **Reservas**: form (reuse the template's `contact` DynamicForm), map, hours.

## Content

[What each page must communicate, as a flat list. Items marked `(required)` form the
content contract: whichever design concept ships, every required item is verified
present. Grammar: `- (required)? Kind: text [— keywords: a, b, c] [→ /href/]`.
An item with keywords passes when one keyword appears; without keywords the text must
appear verbatim (use this for names, prices, awards, labels). A CTA carries `→ /href/`.]

### Home
- (required) Message: [the one-sentence positioning] — keywords: [3–5 words from it]
- (required) CTA: [label] → /[page]/
- (required) Proof: [award, rating, press — exact wording]
- (required) Contact: phone, address, opening hours (from ## Contact)
- Story: [what the story block should say]
- Gallery: [how many photos, of what]

```

Replace the whole `## Design Preferences` block (up to but not including `## Images`) with:

```markdown
## Design Constraints

[Only what every design concept must respect. Never a design: no palette roles, no font
pair, no layout signature — those are chosen per concept by `/build-site`.]

- **Brand colors**: [hex values only if non-negotiable — an existing logo or identity — or "none"]
- **Logo / brand assets**: [path or URL, or "none"]
- **Avoid**: [what the local competition does that this site will not; anything the client rejected — separated by `;`]
- **References**: [up to three URLs, context for the art director, never models to copy]
- **Image constraints**: [largest usable width per group, e.g. "dishes 680px, space 2560px" — decides whether full-bleed photography is possible]

```

- [ ] **Step 6: Commit**

```bash
cd /Users/antoniomarante/Documents/djangopress-sites/djangopress
git add src/djangopress/core/build/__init__.py src/djangopress/core/build/briefing.py src/djangopress/core/tests/test_build_briefing.py briefings/TEMPLATE.md
git commit -m "feat(build): briefing parser and content-only TEMPLATE.md"
```

---

### Task 2: Build packet and `build_prepare`

**Files:**
- Create: `src/djangopress/core/build/packet.py`
- Create: `src/djangopress/core/management/commands/build_prepare.py`
- Test: `src/djangopress/core/tests/test_build_packet.py`

**Interfaces:**
- Consumes: `parse_briefing`, `Briefing`, `ContentItem` (Task 1).
- Produces: `detect_vertical(briefing) -> str`, `VERTICALS[vertical] -> {specialization, jsonld, families}`, `build_packet(briefing, *, site_slug, image_map, menus) -> dict` with the §4.4 shape, and the command `build_prepare <briefing> [--audit path] [--no-download]` writing `docs/build-packet.json`. Every later task reads the packet dict.

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for build_packet / build_prepare (Task 2)."""

import json
import tempfile
from io import BytesIO, StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from djangopress.core.build.briefing import parse_briefing
from djangopress.core.build.packet import build_packet, detect_vertical
from djangopress.core.models import Page, SiteImage, SiteSettings
from djangopress.core.tests.test_build_briefing import SAMPLE

AUDIT = """# CHECKin Faro — Site Audit

## Image Inventory

| Group | Count | Largest width | Source | Example URL |
|---|---|---|---|---|
| Dishes (pro, 2021) | 6 | 2048 (DSC-7371 2048×1365) | old site | https://example.com/dish.jpg |
| Exterior | 0 | — | — | — |
"""

MENU = {"pt": {"Entradas": [{"title": "Couvert", "desc": "", "price": "3.30", "photo": ""}]}}

# 1x1 PNG
PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89'
       b'\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82')


class DetectVerticalTest(TestCase):

    def test_restaurant_from_business_prose(self):
        self.assertEqual(detect_vertical(parse_briefing(SAMPLE)), 'restaurant')

    def test_default_is_services(self):
        b = parse_briefing(SAMPLE.replace('Cozinha de autor algarvia, à carta, para partilhar. Chef Leonel Pereira.', 'Consultoria.'))
        b.notes = {}
        self.assertEqual(detect_vertical(b), 'services')

    def test_notes_override(self):
        b = parse_briefing(SAMPLE)
        b.notes['vertical'] = 'legal'
        self.assertEqual(detect_vertical(b), 'legal')


class BuildPacketTest(TestCase):

    def test_shape(self):
        b = parse_briefing(SAMPLE)
        packet = build_packet(
            b, site_slug='checkin-faro',
            image_map={'dishes-1': {'url': 'https://s/dish.jpg', 'width': 2048, 'alt': 'Dishes'}},
            menus={'briefings/checkin-faro-menu.json': MENU},
        )
        self.assertEqual(packet['site']['lang_prefix'], '/pt')
        self.assertEqual(packet['site']['languages'], ['pt', 'en'])
        self.assertEqual(packet['business']['type'], 'restaurant')
        self.assertEqual(packet['business']['jsonld_type'], 'Restaurant')
        self.assertEqual(packet['facts']['phone'], '+351 289 000 000')
        req = packet['content']['home']['required']
        self.assertEqual(req[1]['href'], '/reservas/')
        menu_item = next(i for i in req if i['kind'] == 'Menu')
        self.assertEqual(menu_item['items'], [{'name': 'Couvert', 'price': '3.30', 'category': 'Entradas'}])
        self.assertEqual(packet['images']['map']['dishes-1']['width'], 2048)
        self.assertEqual(packet['design_constraints']['brand_colors'], ['#C51B17', '#40308A'])
        self.assertIn('editorial', packet['families'])


class BuildPrepareCommandTest(TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'briefings').mkdir()
        (self.root / 'briefings' / 'checkin-faro.md').write_text(SAMPLE)
        (self.root / 'briefings' / 'checkin-faro-audit.md').write_text(AUDIT)
        (self.root / 'briefings' / 'checkin-faro-menu.json').write_text(json.dumps(MENU))
        Page.objects.all().delete()
        SiteImage.objects.all().delete()

    def tearDown(self):
        self.tmp.cleanup()

    def run_cmd(self, *extra):
        out = StringIO()
        storages = {'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}
        with override_settings(MEDIA_ROOT=str(self.root / 'media'), STORAGES=storages), \
             patch('djangopress.core.build.packet.urlopen', return_value=BytesIO(PNG)), \
             patch('djangopress.core.management.commands.build_prepare.Path.cwd', return_value=self.root):
            call_command('build_prepare', str(self.root / 'briefings' / 'checkin-faro.md'), *extra, stdout=out)
        return json.loads(out.getvalue())

    def test_writes_settings_packet_privacy_and_images(self):
        summary = self.run_cmd()
        s = SiteSettings.load()
        self.assertEqual(s.default_language, 'pt')
        self.assertEqual([l['code'] for l in s.enabled_languages], ['pt', 'en'])
        self.assertEqual(s.site_name_i18n, {'pt': 'CHECKin Faro', 'en': 'CHECKin Faro'})
        self.assertEqual(s.contact_phone, '+351 289 000 000')
        self.assertEqual(s.instagram_url, 'https://instagram.com/checkinfaro')
        self.assertTrue(s.project_briefing.startswith('Cozinha de autor'))
        self.assertTrue(Page.objects.filter(slug_i18n__pt='politica-de-privacidade').exists())
        img = SiteImage.objects.get(key='dishes-pro-2021-1')
        self.assertTrue(img.image.name)
        packet = json.loads((self.root / 'docs' / 'build-packet.json').read_text())
        self.assertEqual(packet['images']['map']['dishes-pro-2021-1']['width'], 2048)
        self.assertEqual(summary['required_items'], 4)

    def test_open_questions_block(self):
        (self.root / 'briefings' / 'checkin-faro.md').write_text(
            SAMPLE.replace('## Business', '## Open Questions\n1. x?\n\n## Business'))
        with self.assertRaises(SystemExit):
            self.run_cmd()

    def test_no_download_skips_images(self):
        self.run_cmd('--no-download')
        self.assertFalse(SiteImage.objects.exists())
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py test djangopress.core.tests.test_build_packet -v 1 2>&1 | tail -5`
Expected: `ModuleNotFoundError: No module named 'djangopress.core.build.packet'`

- [ ] **Step 3: Write `packet.py`**

```python
"""Assemble docs/build-packet.json: every fact the builders and checks need."""

import re
from urllib.request import urlopen  # patched in tests

from django.utils.text import slugify

VERTICALS = {
    'restaurant': {
        'keywords': ['restaurante', 'restaurant', 'cozinha', 'chef', 'menu', 'carta', 'gastron'],
        'specialization': 'hospitality, restaurants and premium consumer brands',
        'jsonld': 'Restaurant',
        'families': ['editorial', 'cinematic hospitality', 'Mediterranean modernism', 'vernacular / regional',
                     'cultural / craft', 'publication / magazine', 'immersive photography', 'expressive typography',
                     'contemporary luxury', 'retro-modern'],
    },
    'hospitality': {
        'keywords': ['hotel', 'alojamento', 'lodging', 'apartamento', 'guest', 'villa', 'resort', 'turismo rural'],
        'specialization': 'hospitality, resorts and boutique lodging',
        'jsonld': 'LodgingBusiness',
        'families': ['resort lifestyle', 'cinematic hospitality', 'Mediterranean modernism', 'artistic minimalism',
                     'immersive photography', 'contemporary luxury', 'editorial', 'narrative / storytelling'],
    },
    'real-estate': {
        'keywords': ['imobili', 'real estate', 'propert', 'moradia', 'apartamentos para venda', 'realtor'],
        'specialization': 'real estate, architecture and premium property brands',
        'jsonld': 'RealEstateAgent',
        'families': ['architectural modernism', 'contemporary luxury', 'gallery / museum', 'editorial',
                     'artistic minimalism', 'product-led', 'publication / magazine'],
    },
    'legal': {
        'keywords': ['advogad', 'law firm', 'legal', 'jurídic', 'juridic', 'solicitor'],
        'specialization': 'professional services, law and finance brands',
        'jsonld': 'LegalService',
        'families': ['architectural modernism', 'contemporary luxury', 'gallery / museum', 'publication / magazine',
                     'artistic minimalism', 'editorial'],
    },
    'retail': {
        'keywords': ['loja', 'shop', 'store', 'retail', 'produtos', 'boutique', 'e-commerce'],
        'specialization': 'retail, product and lifestyle brands',
        'jsonld': 'Store',
        'families': ['product-led', 'graphic-design-led', 'fashion editorial', 'retro-modern', 'postmodern',
                     'editorial', 'neo-brutalism', 'expressive typography'],
    },
    'tourism': {
        'keywords': ['tour', 'passeio', 'boat', 'barco', 'transfer', 'excurs', 'experiênc', 'experience', 'activit'],
        'specialization': 'travel, tours and outdoor experience brands',
        'jsonld': 'TouristInformationCenter',
        'families': ['immersive photography', 'resort lifestyle', 'narrative / storytelling', 'cinematic hospitality',
                     'graphic-design-led', 'vernacular / regional', 'editorial'],
    },
    'services': {
        'keywords': [],
        'specialization': 'service businesses and professional brands',
        'jsonld': 'LocalBusiness',
        'families': ['editorial', 'architectural modernism', 'artistic minimalism', 'graphic-design-led',
                     'contemporary luxury', 'publication / magazine', 'expressive typography'],
    },
}

LANG_NAMES = {'pt': 'Português', 'en': 'English', 'fr': 'Français', 'de': 'Deutsch', 'es': 'Español', 'it': 'Italiano'}
INVENTORY_ROW_RE = re.compile(r'^\|\s*(?P<group>[^|]+?)\s*\|\s*(?P<count>\d+)\s*\|\s*(?P<width>[^|]*?)\s*\|\s*(?P<source>[^|]*?)\s*\|\s*(?P<url>https?://\S+)\s*\|')


def detect_vertical(briefing):
    override = (briefing.notes.get('vertical') or '').strip().lower()
    if override in VERTICALS:
        return override
    haystack = (briefing.business + ' ' + briefing.title).lower()
    for name, spec in VERTICALS.items():
        if any(k in haystack for k in spec['keywords']):
            return name
    return 'services'


def parse_inventory(audit_text):
    """Rows of the audit's `## Image Inventory` table that carry a URL and a count > 0."""
    rows = []
    in_table = False
    for line in audit_text.splitlines():
        if line.startswith('## '):
            in_table = line.strip().lower() == '## image inventory'
            continue
        if not in_table:
            continue
        m = INVENTORY_ROW_RE.match(line.strip())
        if m and int(m.group('count')) > 0:
            width_m = re.match(r'(\d{3,4})', m.group('width'))
            rows.append({
                'group': m.group('group'),
                'key': slugify(m.group('group')) + '-1',
                'width': int(width_m.group(1)) if width_m else None,
                'url': m.group('url').rstrip('|').strip(),
            })
    return rows


def download(url):
    return urlopen(url, timeout=30).read()


def _menu_items(menu, lang):
    items = []
    for category, entries in (menu.get(lang) or next(iter(menu.values()), {})).items():
        for e in entries:
            items.append({'name': e.get('title', ''), 'price': e.get('price', ''), 'category': category})
    return items


def _item_dict(item, menus, lang):
    d = {'id': item.id, 'kind': item.kind, 'text': item.text}
    if item.keywords:
        d['keywords'] = item.keywords
    if item.href:
        d['href'] = item.href
    if item.menu_json and item.menu_json in menus:
        d['items'] = _menu_items(menus[item.menu_json], lang)
    return d


def build_packet(briefing, *, site_slug, image_map, menus):
    vertical = detect_vertical(briefing)
    spec = VERTICALS[vertical]
    lang = briefing.default_language
    content = {}
    for page, items in briefing.content.items():
        content[page] = {
            'required': [_item_dict(i, menus, lang) for i in items if i.required],
            'optional': [_item_dict(i, menus, lang) for i in items if not i.required],
        }
    first_sentence = re.split(r'(?<=[.!?])\s', briefing.business.strip(), maxsplit=1)[0]
    return {
        'site': {
            'slug': site_slug, 'name': briefing.title, 'default_language': lang,
            'default_language_name': briefing.language_names.get(lang, LANG_NAMES.get(lang, lang)),
            'languages': briefing.languages, 'lang_prefix': f'/{lang}',
        },
        'business': {
            'type': vertical,
            'jsonld_type': briefing.notes.get('jsonld') or spec['jsonld'],
            'specialization': spec['specialization'],
            'positioning': first_sentence,
            'prose': briefing.business,
            'cuisine': briefing.notes.get('cuisine', ''),
            'price_range': briefing.notes.get('price range', '€€'),
        },
        'families': spec['families'],
        'facts': {
            'phone': briefing.contact.get('phone', ''), 'email': briefing.contact.get('email', ''),
            'address': briefing.contact.get('address', ''), 'maps_url': briefing.contact.get('maps_url', ''),
            'hours': briefing.hours, 'social': briefing.social,
        },
        'pages': briefing.pages,
        'content': content,
        'images': {
            'strategy': briefing.images.get('strategy', 'skip'),
            'map': image_map,
            'constraints': briefing.constraints.get('image_max_widths', {}),
        },
        'design_constraints': briefing.constraints,
        'header': briefing.header,
        'footer': briefing.footer,
    }
```

- [ ] **Step 4: Write the command**

```python
"""build_prepare — briefing → SiteSettings, privacy page, inventory images, docs/build-packet.json."""

import json
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError

from djangopress.core.build.briefing import parse_briefing
from djangopress.core.build.packet import LANG_NAMES, build_packet, download, parse_inventory
from djangopress.core.models import Page, SiteImage, SiteSettings

SOCIAL_FIELDS = {'instagram': 'instagram_url', 'facebook': 'facebook_url', 'linkedin': 'linkedin_url',
                 'youtube': 'youtube_url', 'tiktok': 'tiktok_url', 'twitter': 'twitter_url', 'twitter/x': 'twitter_url', 'x': 'twitter_url'}
PRIVACY = {'pt': ('politica-de-privacidade', 'Política de Privacidade e Cookies'),
           'en': ('privacy-policy', 'Privacy & Cookies Policy')}


class Command(BaseCommand):
    help = 'Prepare a site build from a content-only briefing.'

    def add_arguments(self, parser):
        parser.add_argument('briefing')
        parser.add_argument('--audit', default='')
        parser.add_argument('--no-download', action='store_true')

    def handle(self, *args, **opts):
        root = Path.cwd()
        briefing_path = Path(opts['briefing'])
        briefing = parse_briefing(briefing_path.read_text())
        if briefing.has_open_questions:
            raise CommandError('Briefing still has ## Open Questions — finish /create-briefing first')
        slug = briefing_path.stem
        lang = briefing.default_language

        s = SiteSettings.load()
        s.default_language = lang
        s.enabled_languages = [{'code': c, 'name': briefing.language_names.get(c, LANG_NAMES.get(c, c))} for c in briefing.languages]
        s.site_name_i18n = {c: briefing.title for c in briefing.languages}
        s.site_description_i18n = {lang: briefing.business.split('\n')[0][:300]}
        s.project_briefing = briefing.business
        if briefing.contact.get('email'):
            s.contact_email = briefing.contact['email']
        s.contact_phone = briefing.contact.get('phone', '')
        for key, url in briefing.social.items():
            if key == 'whatsapp':
                s.whatsapp_number = url.rsplit('/', 1)[-1] if url.startswith('http') else url
            elif key in SOCIAL_FIELDS:
                setattr(s, SOCIAL_FIELDS[key], url)
        s.save()

        if not any('privac' in (p.slug_i18n or {}).get(lang, '') or 'politica' in (p.slug_i18n or {}).get(lang, '')
                   for p in Page.objects.all()):
            pslug, ptitle = PRIVACY.get(lang, PRIVACY['en'])
            Page.objects.create(
                title_i18n={lang: ptitle}, slug_i18n={lang: pslug},
                html_content_i18n={lang: f'<section data-section="privacy" id="privacy"><h1>{ptitle}</h1><p>{briefing.title}</p></section>'},
                meta_title_i18n={lang: ptitle}, meta_description_i18n={lang: ptitle}, is_active=True, sort_order=999)

        image_map = {}
        for img in SiteImage.objects.filter(is_active=True).exclude(key='').exclude(image=''):
            image_map[img.key] = {'url': img.image.url, 'width': None, 'alt': img.get_title(lang) if hasattr(img, 'get_title') else img.key}
        audit_path = Path(opts['audit']) if opts['audit'] else briefing_path.with_name(f'{slug}-audit.md')
        if audit_path.exists() and not opts['no_download']:
            for row in parse_inventory(audit_path.read_text()):
                if row['key'] in image_map:
                    image_map[row['key']]['width'] = row['width']
                    continue
                try:
                    data = download(row['url'])
                except Exception as exc:  # network is best-effort
                    self.stderr.write(f'skip {row["url"]}: {exc}')
                    continue
                img = SiteImage(key=row['key'], title_i18n={lang: row['group']}, alt_text_i18n={lang: row['group']})
                img.image.save(row['url'].rsplit('/', 1)[-1].split('?')[0] or f'{row["key"]}.jpg', ContentFile(data), save=True)
                image_map[row['key']] = {'url': img.image.url, 'width': row['width'], 'alt': row['group']}

        menus = {}
        for items in briefing.content.values():
            for item in items:
                if item.menu_json and (root / item.menu_json).exists():
                    menus[item.menu_json] = json.loads((root / item.menu_json).read_text())

        packet = build_packet(briefing, site_slug=slug, image_map=image_map, menus=menus)
        out = root / 'docs' / 'build-packet.json'
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(packet, ensure_ascii=False, indent=2))
        required = sum(len(v['required']) for v in packet['content'].values())
        self.stdout.write(json.dumps({'packet': str(out), 'required_items': required, 'images': len(image_map),
                                      'languages': briefing.languages, 'vertical': packet['business']['type']}))
```

- [ ] **Step 5: Run the tests**

Run: `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py test djangopress.core.tests.test_build_packet -v 1 2>&1 | tail -5`
Expected: `Ran 7 tests … OK`. If `SiteImage.get_title` does not exist, replace the `alt` expression with `img.key` — the test does not assert it.

- [ ] **Step 6: Commit**

```bash
cd /Users/antoniomarante/Documents/djangopress-sites/djangopress
git add src/djangopress/core/build/packet.py src/djangopress/core/management/commands/build_prepare.py src/djangopress/core/tests/test_build_packet.py
git commit -m "feat(build): build packet and build_prepare command"
```

---

### Task 3: Design DNA ledger and `concept_ledger`

**Files:**
- Create: `src/djangopress/core/build/ledger.py`
- Create: `src/djangopress/core/management/commands/concept_ledger.py`
- Test: `src/djangopress/core/tests/test_build_ledger.py`

**Interfaces:**
- Produces: `parse_brief(text) -> {name, register, premise, dna: {16 keys}}` (also used by Task 10), `Ledger(path)` with `.read(vertical=None, limit=12) -> list`, `.append(entry)`, `.mark_shipped(site, key)`, `format_entries(entries) -> str`, `default_ledger_path() -> Path`. Command `concept_ledger --read --vertical V | --append brief --site S --key K --vertical V [--shipped] | --mark-shipped S K`.

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for the design DNA ledger (Task 3)."""

import json
import os
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase

from djangopress.core.build.ledger import Ledger, format_entries, parse_brief

BRIEF = """CONCEPT NAME: Boarding Pass
REGISTER: distinctive
CREATIVE PREMISE: The restaurant as a departure gate; every section is a stamp on a ticket.
BRAND IDEA: The airport vocabulary of the menu.
DESIGN DNA:
- Movement: graphic-design-led
- Personality: playful, precise
- Layout grammar: ticket-stub modules on a 12-col grid
- Hero: full-bleed red field with a perforated ticket card
- Typography: Instrument Serif + DM Sans
- Color: cream ground, oxblood and plum accents
- Photography: documentary, warm
- Cropping: tight, tilted
- Graphic device: perforation line
- Section transitions: dashed tear lines
- Geometry: rounded stubs
- Density: medium
- Navigation: boarding-strip bar
- CTA: stamp button
- Motion: stamp-in on scroll
- Mobile behaviour: stubs stack
HERO DESCRIPTION: ...
"""


class ParseBriefTest(SimpleTestCase):

    def test_fields(self):
        b = parse_brief(BRIEF)
        self.assertEqual(b['name'], 'Boarding Pass')
        self.assertEqual(b['register'], 'distinctive')
        self.assertTrue(b['premise'].startswith('The restaurant'))
        self.assertEqual(b['dna']['graphic_device'], 'perforation line')
        self.assertEqual(b['dna']['mobile'], 'stubs stack')
        self.assertEqual(len(b['dna']), 16)


class LedgerTest(SimpleTestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / '.design-dna' / 'ledger.json'

    def tearDown(self):
        self.tmp.cleanup()

    def entry(self, site, key, vertical='restaurant', shipped=False, date='2026-09-16'):
        b = parse_brief(BRIEF)
        return {'site': site, 'date': date, 'key': key, 'name': b['name'], 'vertical': vertical,
                'register': b['register'], 'shipped': shipped, 'dna': b['dna']}

    def test_append_read_filter_and_order(self):
        led = Ledger(self.path)
        led.append(self.entry('a-site', 'a', date='2026-09-01'))
        led.append(self.entry('b-site', 'b', shipped=True, date='2026-09-02'))
        led.append(self.entry('c-site', 'c', vertical='legal', date='2026-09-03'))
        rows = led.read(vertical='restaurant')
        self.assertEqual([r['site'] for r in rows], ['b-site', 'a-site'])
        self.assertEqual(len(led.read()), 3)
        self.assertEqual(len(led.read(limit=1)), 1)

    def test_mark_shipped(self):
        led = Ledger(self.path)
        led.append(self.entry('a-site', 'a'))
        led.mark_shipped('a-site', 'a')
        self.assertTrue(led.read()[0]['shipped'])

    def test_format_entries(self):
        text = format_entries([self.entry('a-site', 'a')])
        self.assertIn('Boarding Pass', text)
        self.assertIn('Graphic device: perforation line', text)

    def test_command_roundtrip(self):
        brief = Path(self.tmp.name) / 'brief-b.md'
        brief.write_text(BRIEF)
        with patch.dict(os.environ, {'DJANGOPRESS_SITES_ROOT': self.tmp.name}):
            call_command('concept_ledger', '--append', str(brief), '--site', 'x', '--key', 'b', '--vertical', 'restaurant', '--shipped')
            out = StringIO()
            call_command('concept_ledger', '--read', '--vertical', 'restaurant', stdout=out)
        self.assertIn('Boarding Pass', out.getvalue())
        self.assertTrue(json.loads(self.path.read_text())[0]['shipped'])
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py test djangopress.core.tests.test_build_ledger -v 1 2>&1 | tail -5`
Expected: `ModuleNotFoundError: No module named 'djangopress.core.build.ledger'`

- [ ] **Step 3: Write `ledger.py`**

```python
"""Shared design-DNA ledger: every concept ever generated, across all sites."""

import json
import os
import re
from pathlib import Path

DNA_KEYS = {
    'movement': 'movement', 'personality': 'personality', 'layout grammar': 'layout_grammar', 'hero': 'hero',
    'typography': 'typography', 'color': 'color', 'photography': 'photography', 'cropping': 'cropping',
    'graphic device': 'graphic_device', 'section transitions': 'section_transitions', 'geometry': 'geometry',
    'density': 'density', 'navigation': 'navigation', 'cta': 'cta', 'motion': 'motion', 'mobile behaviour': 'mobile',
}
DNA_LABELS = {v: k.capitalize() for k, v in DNA_KEYS.items()}
FIELD_RE = re.compile(r'^(CONCEPT NAME|REGISTER|CREATIVE PREMISE|BRAND IDEA):\s*(.*)$')
DNA_LINE_RE = re.compile(r'^-\s*([A-Za-z ]+?):\s*(.*)$')


def parse_brief(text):
    out = {'name': '', 'register': '', 'premise': '', 'brand_idea': '', 'dna': {}}
    for line in text.splitlines():
        m = FIELD_RE.match(line.strip())
        if m:
            key = {'CONCEPT NAME': 'name', 'REGISTER': 'register', 'CREATIVE PREMISE': 'premise', 'BRAND IDEA': 'brand_idea'}[m.group(1)]
            out[key] = m.group(2).strip()
            continue
        m = DNA_LINE_RE.match(line.strip())
        if m and m.group(1).strip().lower() in DNA_KEYS:
            out['dna'][DNA_KEYS[m.group(1).strip().lower()]] = m.group(2).strip()
    return out


def default_ledger_path():
    root = os.environ.get('DJANGOPRESS_SITES_ROOT') or str(Path.cwd().parent)
    return Path(root) / '.design-dna' / 'ledger.json'


def format_entries(entries):
    if not entries:
        return 'none yet'
    blocks = []
    for e in entries:
        lines = [f"{e['name']} ({e['site']}, {e['date']}, {'shipped' if e.get('shipped') else 'not shipped'}):"]
        for key in DNA_KEYS.values():
            if e['dna'].get(key):
                lines.append(f"  - {DNA_LABELS[key]}: {e['dna'][key]}")
        blocks.append('\n'.join(lines))
    return '\n\n'.join(blocks)


class Ledger:
    def __init__(self, path=None):
        self.path = Path(path) if path else default_ledger_path()

    def _load(self):
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text() or '[]')

    def _save(self, rows):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(rows, ensure_ascii=False, indent=1))

    def read(self, vertical=None, limit=12):
        rows = [r for r in self._load() if vertical is None or r.get('vertical') == vertical]
        rows.sort(key=lambda r: r.get('date', ''), reverse=True)   # newest first …
        rows.sort(key=lambda r: not r.get('shipped', False))       # … shipped first (stable)
        return rows[:limit]

    def append(self, entry):
        rows = self._load()
        rows = [r for r in rows if not (r['site'] == entry['site'] and r['key'] == entry['key'])]
        rows.append(entry)
        self._save(rows)

    def mark_shipped(self, site, key):
        rows = self._load()
        for r in rows:
            if r['site'] == site:
                r['shipped'] = (r['key'] == key)
        self._save(rows)
```

- [ ] **Step 4: Write the command**

```python
"""concept_ledger — read or update the shared design-DNA ledger."""

import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from djangopress.core.build.ledger import Ledger, format_entries, parse_brief


class Command(BaseCommand):
    help = 'Read/append the cross-site design DNA ledger.'

    def add_arguments(self, parser):
        parser.add_argument('--read', action='store_true')
        parser.add_argument('--append', default='', help='brief-<k>.md to append')
        parser.add_argument('--mark-shipped', nargs=2, metavar=('SITE', 'KEY'))
        parser.add_argument('--site', default='')
        parser.add_argument('--key', default='')
        parser.add_argument('--vertical', default='')
        parser.add_argument('--shipped', action='store_true')
        parser.add_argument('--limit', type=int, default=12)

    def handle(self, *args, **opts):
        ledger = Ledger()
        if opts['read']:
            self.stdout.write(format_entries(ledger.read(vertical=opts['vertical'] or None, limit=opts['limit'])))
        elif opts['append']:
            if not (opts['site'] and opts['key'] and opts['vertical']):
                raise CommandError('--append needs --site, --key and --vertical')
            b = parse_brief(Path(opts['append']).read_text())
            ledger.append({'site': opts['site'], 'date': datetime.date.today().isoformat(), 'key': opts['key'],
                           'name': b['name'], 'vertical': opts['vertical'], 'register': b['register'],
                           'shipped': opts['shipped'], 'dna': b['dna']})
            self.stdout.write(f"appended {b['name']} ({opts['site']}/{opts['key']})")
        elif opts['mark_shipped']:
            ledger.mark_shipped(*opts['mark_shipped'])
            self.stdout.write('ok')
        else:
            raise CommandError('one of --read, --append, --mark-shipped')
```

- [ ] **Step 5: Run the tests**

Run: `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py test djangopress.core.tests.test_build_ledger -v 1 2>&1 | tail -5`
Expected: `Ran 5 tests … OK`

- [ ] **Step 6: Commit**

```bash
cd /Users/antoniomarante/Documents/djangopress-sites/djangopress
git add src/djangopress/core/build/ledger.py src/djangopress/core/management/commands/concept_ledger.py src/djangopress/core/tests/test_build_ledger.py
git commit -m "feat(build): shared design DNA ledger and concept_ledger command"
```

---

### Task 4: Adapter, part 1 — completeness, split, head lifting, tokens

**Files:**
- Create: `src/djangopress/core/tests/fixtures/concept-checkin-faro.html` (copy of `/Users/antoniomarante/Downloads/checkin-faro-homepage-v2-red-creative.html`, byte for byte)
- Create: `src/djangopress/core/tests/fixtures/concept-minimal.html`
- Create: `src/djangopress/core/build/adapter.py`
- Test: `src/djangopress/core/tests/test_build_adapter.py`

**Interfaces:**
- Produces (all in `adapter.py`, consumed by Task 5's `adapt()`): `AdaptResult` dataclass; `soup_of(html) -> BeautifulSoup`; `check_complete(raw) -> list[str]`; `split_document(soup) -> (header, main, footer, trailing_scripts)`; `lift_head(soup) -> dict(head_code, css, config_js, meta_title, meta_description, google_families, removed: Counter)`; `fix_body_rules(css) -> (css, n)`; `extract_fonts(config_js, google_families) -> (heading, body)`; `extract_colors(config_js, css, root, cta_texts) -> dict`; `infer_layout(root) -> dict`.

- [ ] **Step 1: Create the fixtures**

```bash
mkdir -p /Users/antoniomarante/Documents/djangopress-sites/djangopress/src/djangopress/core/tests/fixtures
cp /Users/antoniomarante/Downloads/checkin-faro-homepage-v2-red-creative.html \
   /Users/antoniomarante/Documents/djangopress-sites/djangopress/src/djangopress/core/tests/fixtures/concept-checkin-faro.html
```

Write `src/djangopress/core/tests/fixtures/concept-minimal.html` exactly:

```html
<!DOCTYPE html>
<html lang="pt">
<head>
<meta charset="UTF-8">
<title>Casa Teste — Início</title>
<meta name="description" content="Descrição de teste.">
<script src="https://cdn.tailwindcss.com"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Lora:wght@400;600&family=Inter:wght@400;500&display=swap" rel="stylesheet">
<script>
tailwind.config = { theme: { extend: { colors: { cream: '#F5F0E8', ink: '#2B2520', brick: '#C05B3E', teal: '#3E6B73' }, fontFamily: { sans: ['Inter', 'sans-serif'], display: ['Lora', 'serif'] } } } }
</script>
<style>
body { background: #F5F0E8; color: #2B2520; }
.grain { opacity: .1; }
</style>
</head>
<body>
<header class="absolute inset-x-0 top-0 z-50">
  <nav class="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
    <a href="/" class="font-display text-xl">Casa Teste</a>
    <a href="#menu" class="text-sm uppercase tracking-wide">Menu</a>
    <a href="#contact" class="text-sm uppercase tracking-wide">Contactos</a>
    <a href="/reservas/" class="rounded-lg bg-brick px-4 py-2 text-white">Reservar mesa</a>
    <div data-slot="language-switcher"></div>
  </nav>
</header>
<main>
  <section class="relative min-h-screen bg-ink text-white">
    <img src="https://example.com/dish.jpg" alt="Prato" class="absolute inset-0 h-full w-full object-cover">
    <div class="absolute inset-0 bg-gradient-to-t from-black to-transparent"></div>
    <div class="relative mx-auto max-w-6xl px-6 py-32">
      <h1 class="font-display text-6xl">Cozinha de autor algarvia</h1>
      <p class="mt-4 text-lg">À carta, para partilhar.</p>
      <a href="/reservas/" class="mt-8 inline-block rounded-lg bg-brick px-6 py-3 text-white shadow-lg">Reservar mesa</a>
    </div>
  </section>
  <section id="menu" class="bg-cream py-20">
    <div class="mx-auto max-w-6xl px-6">
      <h2 class="font-display text-4xl">A carta</h2>
      <ul><li>Couvert — 3.30 €</li></ul>
      <div class="flex gap-4">
        <img src="https://images.unsplash.com/photo-1?w=800" alt="Sala" class="rounded-lg">
        <img src="https://example.com/dish.jpg" alt="Prato outra vez" class="rounded-lg">
      </div>
    </div>
  </section>
  <div class="bg-teal py-20 text-white">
    <div class="mx-auto max-w-6xl px-6">
      <h2 class="font-display text-4xl">Contactos</h2>
      <p>+351 289 000 000 · Rua do Castelo 1, Faro</p>
      <p>Guia Michelin 2024</p>
      <form action="/forms/contact/" method="post"><label>Nome</label><input name="name"><button class="rounded-lg bg-brick px-4 py-2 text-white">Enviar</button></form>
    </div>
  </div>
</main>
<footer class="bg-ink py-10 text-white">
  <div class="mx-auto max-w-6xl px-6">
    <a href="/politica-de-privacidade/">Política de Privacidade</a>
    <span>© 2026 Casa Teste</span>
  </div>
</footer>
<script>console.log('ready');</script>
</body>
</html>
```

- [ ] **Step 2: Write the failing tests**

```python
"""Tests for the concept adapter (Tasks 4 and 5)."""

from pathlib import Path

from django.test import SimpleTestCase

from djangopress.core.build import adapter
from djangopress.core.build.adapter import (
    check_complete, extract_colors, extract_fonts, fix_body_rules, infer_layout, lift_head, soup_of, split_document,
)

FIXTURES = Path(__file__).parent / 'fixtures'
MINIMAL = (FIXTURES / 'concept-minimal.html').read_text()
CHECKIN = (FIXTURES / 'concept-checkin-faro.html').read_text()


class CompletenessTest(SimpleTestCase):

    def test_complete_document_has_no_errors(self):
        self.assertEqual(check_complete(MINIMAL), [])

    def test_truncated_document(self):
        cut = MINIMAL[: MINIMAL.index('<footer')]
        errors = check_complete(cut)
        self.assertTrue(any('truncated' in e for e in errors))
        self.assertTrue(any('<footer' in e for e in errors))


class SplitTest(SimpleTestCase):

    def test_split_minimal(self):
        header, main, footer, trailing = split_document(soup_of(MINIMAL))
        self.assertEqual(header.name, 'header')
        self.assertEqual(main.name, 'main')
        self.assertEqual(footer.name, 'footer')
        self.assertEqual(len(trailing), 1)
        self.assertIn("console.log('ready')", trailing[0].get_text())

    def test_split_checkin(self):
        header, main, footer, trailing = split_document(soup_of(CHECKIN))
        self.assertEqual(len(main.find_all('section', recursive=False)), 11)
        self.assertIn('lucide.createIcons', trailing[0].get_text())


class LiftHeadTest(SimpleTestCase):

    def test_minimal(self):
        soup = soup_of(MINIMAL)
        head = lift_head(soup)
        self.assertIn('tailwind.config', head['config_js'])
        self.assertIn('.grain', head['css'])
        self.assertEqual(head['meta_title'], 'Casa Teste — Início')
        self.assertEqual(head['meta_description'], 'Descrição de teste.')
        self.assertEqual(head['google_families'], ['Lora', 'Inter'])
        self.assertEqual(head['removed']['tailwind-cdn'], 1)
        self.assertEqual(head['removed']['google-fonts-link'], 2)
        self.assertNotIn('cdn.tailwindcss.com', head['head_code'])
        self.assertNotIn('fonts.googleapis', head['head_code'])
        self.assertIn('<script>', head['head_code'])
        self.assertIn('<style>', head['head_code'])

    def test_checkin_keeps_lucide(self):
        head = lift_head(soup_of(CHECKIN))
        self.assertIn('unpkg.com/lucide', head['head_code'])
        self.assertIn('.boarding-ticket', head['css'])


class BodyRuleTest(SimpleTestCase):

    def test_rewrites_body_selector_only(self):
        css, n = fix_body_rules('html { scroll-behavior: smooth; }\nbody { background:#F7F1E8; }\n.body-copy { color: red }\nhtml, body { margin: 0 }')
        self.assertEqual(n, 2)
        self.assertIn('body.bg-white { background:#F7F1E8; }', css)
        self.assertIn('html, body.bg-white { margin: 0 }', css)
        self.assertIn('.body-copy { color: red }', css)


class TokensTest(SimpleTestCase):

    def test_fonts_from_config(self):
        head = lift_head(soup_of(MINIMAL))
        self.assertEqual(extract_fonts(head['config_js'], head['google_families']), ('Lora', 'Inter'))

    def test_fonts_from_google_link_when_no_config(self):
        self.assertEqual(extract_fonts('', ['Playfair Display', 'Inter Tight']), ('Playfair Display', 'Inter Tight'))

    def test_colors_minimal(self):
        soup = soup_of(MINIMAL)
        head = lift_head(soup)
        colors = extract_colors(head['config_js'], head['css'], soup, cta_texts=['Reservar mesa'])
        self.assertEqual(colors['background_color'], '#f5f0e8')
        self.assertEqual(colors['text_color'], '#2b2520')
        self.assertEqual(colors['heading_color'], '#2b2520')
        self.assertEqual(colors['primary_color'], '#c05b3e')
        self.assertEqual(colors['primary_button_bg'], '#c05b3e')
        self.assertEqual(colors['primary_button_text'], '#ffffff')
        self.assertIn(colors['secondary_color'], ('#3e6b73', '#2b2520', '#f5f0e8'))

    def test_colors_checkin(self):
        soup = soup_of(CHECKIN)
        head = lift_head(soup)
        colors = extract_colors(head['config_js'], head['css'], soup, cta_texts=['Reservar'])
        self.assertEqual(colors['background_color'], '#f7f1e8')
        self.assertEqual(colors['text_color'], '#141313')
        self.assertRegex(colors['primary_color'], r'^#[0-9a-f]{6}$')

    def test_layout_minimal(self):
        layout = infer_layout(soup_of(MINIMAL))
        self.assertEqual(layout['container_width'], '6xl')
        self.assertEqual(layout['border_radius_preset'], 'lg')
        self.assertEqual(layout['shadow_preset'], 'lg')

    def test_layout_defaults_when_nothing_found(self):
        layout = infer_layout(soup_of('<html><body><main><section><p>x</p></section></main></body></html>'))
        self.assertEqual(layout, {'container_width': '7xl', 'border_radius_preset': 'none', 'shadow_preset': 'none'})
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py test djangopress.core.tests.test_build_adapter -v 1 2>&1 | tail -5`
Expected: `ModuleNotFoundError: No module named 'djangopress.core.build.adapter'`

- [ ] **Step 4: Write `adapter.py` (part 1)**

```python
"""Adapter: one standalone HTML document → DjangoPress-legal parts (spec §7).

Pure functions on BeautifulSoup trees; no database access. `adapt()` (Task 5)
orchestrates them and returns an AdaptResult.
"""

import re
from collections import Counter
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag
from django.utils.text import slugify

from djangopress.core.middleware import NON_I18N_PATHS

EDITABLE_TAGS = {'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'span', 'a', 'li', 'td', 'th', 'label', 'button', 'blockquote'}
FORBIDDEN_IN_PAGE = ('html', 'head', 'body', 'header', 'nav', 'footer')
NON_OVERLAY_TAGS = {'img', 'a', 'button', 'input', 'select', 'textarea', 'form', 'svg', 'video', 'iframe'}
SECTION_NAME_RE = re.compile(r'^[a-z][a-z0-9-]*$')
TEMPLATE_SYNTAX_RE = re.compile(r'{{|{%|{#')
BODY_SELECTOR_RE = re.compile(r'(?<![\w.#\-\[])body(?=\s*[{,])')
HEX_RE = re.compile(r'#[0-9a-fA-F]{6}\b')
CONFIG_COLOR_RE = re.compile(r"""([A-Za-z][\w-]*)\s*:\s*['"](#[0-9a-fA-F]{6})['"]""")
FONT_FAMILY_BLOCK_RE = re.compile(r'fontFamily\s*:\s*\{(.*?)\}', re.S)
FONT_ENTRY_RE = re.compile(r"""([A-Za-z][\w-]*)\s*:\s*\[\s*['"]([^'"]+)['"]""")
GOOGLE_FAMILY_RE = re.compile(r'family=([^:&]+)')
BODY_RULE_RE = re.compile(r'(?<![\w.#-])body(?:\.bg-white)?\s*\{([^}]*)\}')
CSS_BG_RE = re.compile(r'background(?:-color)?\s*:\s*(#[0-9a-fA-F]{6})')
CSS_COLOR_RE = re.compile(r'(?<![-\w])color\s*:\s*(#[0-9a-fA-F]{6})')
MAX_W_RE = re.compile(r'^max-w-(\w+|\[\d+px\])$')
ROUNDED_RE = re.compile(r'^rounded(?:-(\w+))?$')
SHADOW_RE = re.compile(r'^shadow(?:-(\w+))?$')
CONTAINER_CHOICES = {'full', 'xs', 'sm', 'md', 'lg', 'xl', '2xl', '3xl', '4xl', '5xl', '6xl', '7xl'}
RADIUS_MAP = {None: 'md', 'none': 'none', 'sm': 'sm', 'md': 'md', 'lg': 'lg', 'xl': 'xl', '2xl': '2xl', '3xl': '3xl', 'full': 'full'}
SHADOW_MAP = {None: 'md', 'none': 'none', 'sm': 'sm', 'md': 'md', 'lg': 'lg', 'xl': 'xl', '2xl': '2xl'}
PLACEHOLDER_HOST = 'placehold.co'
SWITCHER_TOKEN = '__DP_LANGUAGE_SWITCHER__'


@dataclass
class AdaptResult:
    page_html: str = ''
    header_html: str = ''
    footer_html: str = ''
    head_code: str = ''
    settings: dict = field(default_factory=dict)
    meta_title: str = ''
    meta_description: str = ''
    sections: list = field(default_factory=list)
    menu: list = field(default_factory=list)
    changes: Counter = field(default_factory=Counter)
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    @property
    def ok(self):
        return not self.errors

    def as_report(self):
        return {
            'ok': self.ok, 'errors': self.errors, 'warnings': self.warnings, 'changes': dict(self.changes),
            'sections': self.sections, 'menu': self.menu, 'settings': self.settings,
            'meta_title': self.meta_title, 'meta_description': self.meta_description,
        }


def soup_of(html):
    return BeautifulSoup(html, 'html.parser')


def check_complete(raw):
    """Truncation guard: the builder contract says the document ends with </html>."""
    errors = []
    low = raw.lower()
    if '</html>' not in low.rstrip()[-300:]:
        errors.append('truncated: document does not end with </html>')
    for tag in ('<header', '<main', '<footer'):
        if tag not in low:
            errors.append(f'missing {tag}> element')
    return errors


def split_document(soup):
    header = soup.find('header')
    main = soup.find('main')
    footer = soup.find('footer')
    body = soup.body or soup
    trailing = [s for s in body.find_all('script', recursive=False)]
    return header, main, footer, trailing


def lift_head(soup):
    """Pull tailwind.config, <style>, lucide and meta out of <head>; drop the duplicate CDN and font links."""
    head = soup.head or soup
    removed = Counter()
    config_js, css_blocks, extra = '', [], []
    google_families = []
    for script in head.find_all('script'):
        src = script.get('src', '')
        text = script.get_text()
        if 'cdn.tailwindcss.com' in src:
            removed['tailwind-cdn'] += 1
        elif 'tailwind.config' in text:
            config_js = text.strip()
        elif 'lucide' in src:
            extra.append(f'<script src="{src}"></script>')
        elif src:
            removed['other-script'] += 1
        elif text.strip():
            extra.append(f'<script>{text.strip()}</script>')
    for style in head.find_all('style'):
        css_blocks.append(style.get_text().strip())
    for link in head.find_all('link'):
        href = link.get('href', '')
        if 'fonts.googleapis.com' in href or 'fonts.gstatic.com' in href:
            removed['google-fonts-link'] += 1
            for fam in GOOGLE_FAMILY_RE.findall(href):
                google_families.append(fam.replace('+', ' '))
    title = soup.title.get_text(strip=True) if soup.title else ''
    desc_tag = head.find('meta', attrs={'name': 'description'})
    css = '\n'.join(b for b in css_blocks if b)
    parts = []
    if config_js:
        parts.append(f'<script>\n{config_js}\n</script>')
    if css:
        parts.append(f'<style>\n{css}\n</style>')
    parts.extend(extra)
    return {
        'head_code': '\n'.join(parts), 'css': css, 'config_js': config_js,
        'meta_title': title, 'meta_description': desc_tag.get('content', '').strip() if desc_tag else '',
        'google_families': google_families, 'removed': removed,
    }


def fix_body_rules(css):
    """base.html hardcodes <body class="bg-white">; `body {}` loses to it. Raise specificity."""
    return BODY_SELECTOR_RE.subn('body.bg-white', css)


def extract_fonts(config_js, google_families):
    families = {}
    m = FONT_FAMILY_BLOCK_RE.search(config_js or '')
    if m:
        for name, first in FONT_ENTRY_RE.findall(m.group(1)):
            families[name] = first.strip()
    heading = families.get('display') or families.get('heading') or families.get('serif')
    body = families.get('sans') or families.get('body')
    if not heading:
        others = [v for k, v in families.items() if v != body]
        heading = others[0] if others else None
    if not heading and google_families:
        heading = google_families[0]
    if not body and google_families:
        body = google_families[1] if len(google_families) > 1 else google_families[0]
    return (heading or 'Inter', body or heading or 'Inter')


def _class_tokens(tag):
    return tag.get('class', []) if tag else []


def _color_from_classes(tokens, prefix, config):
    for t in tokens:
        if t.startswith(prefix + '[#') and t.endswith(']'):
            return t[len(prefix) + 1:-1].lower()
        if t.startswith(prefix):
            name = t[len(prefix):]
            if name in config:
                return config[name]
            if name == 'white':
                return '#ffffff'
            if name == 'black':
                return '#000000'
    return None


def extract_colors(config_js, css, root, cta_texts=()):
    config = {k: v.lower() for k, v in CONFIG_COLOR_RE.findall(config_js or '')}
    background = text = None
    m = BODY_RULE_RE.search(css or '')
    if m:
        bg = CSS_BG_RE.search(m.group(1))
        fg = CSS_COLOR_RE.search(m.group(1))
        background = bg.group(1).lower() if bg else None
        text = fg.group(1).lower() if fg else None
    if not background:
        background = _color_from_classes(_class_tokens(root.body), 'bg-', config) or '#ffffff'
    if not text:
        text = _color_from_classes(_class_tokens(root.body), 'text-', config) or '#1f2937'

    wanted = {t.strip().lower() for t in cta_texts if t.strip()}
    button = None
    for tag in root.find_all(['a', 'button']):
        if tag.get_text(' ', strip=True).lower() in wanted and _color_from_classes(_class_tokens(tag), 'bg-', config):
            button = tag
            break
    if button is None:
        header = root.find('header')
        for tag in (header.find_all(['a', 'button']) if header else []):
            if _color_from_classes(_class_tokens(tag), 'bg-', config):
                button = tag
                break
    primary = _color_from_classes(_class_tokens(button), 'bg-', config) if button else None
    if not primary:
        primary = next((v for v in config.values() if v not in (background, text)), '#1e3a8a')
    button_text = (_color_from_classes(_class_tokens(button), 'text-', config) if button else None) or '#ffffff'

    usage = Counter()
    for tag in root.find_all(class_=True):
        for t in tag['class']:
            for prefix in ('bg-', 'text-', 'border-'):
                if t.startswith(prefix) and t[len(prefix):] in config:
                    usage[config[t[len(prefix):]]] += 1
    rest = [c for c, _ in usage.most_common() if c not in (background, text, primary)]
    rest += [c for c in config.values() if c not in rest and c not in (background, text, primary)]
    secondary = rest[0] if rest else text
    accent = rest[1] if len(rest) > 1 else primary
    return {
        'background_color': background, 'text_color': text, 'heading_color': text,
        'primary_color': primary, 'primary_button_bg': primary, 'primary_button_text': button_text,
        'secondary_color': secondary, 'accent_color': accent,
    }


def infer_layout(root):
    widths, radii, shadows = Counter(), Counter(), Counter()
    for tag in root.find_all(class_=True):
        for t in tag['class']:
            m = MAX_W_RE.match(t)
            if m:
                v = m.group(1)
                if v.startswith('['):
                    px = int(v[1:-3])
                    v = '6xl' if px <= 1152 else '7xl' if px <= 1280 else 'full'
                if v in CONTAINER_CHOICES:
                    widths[v] += 1
            m = ROUNDED_RE.match(t)
            if m and m.group(1) in RADIUS_MAP:
                radii[RADIUS_MAP[m.group(1)]] += 1
            m = SHADOW_RE.match(t)
            if m and m.group(1) in SHADOW_MAP:
                shadows[SHADOW_MAP[m.group(1)]] += 1
    return {
        'container_width': widths.most_common(1)[0][0] if widths else '7xl',
        'border_radius_preset': radii.most_common(1)[0][0] if radii else 'none',
        'shadow_preset': shadows.most_common(1)[0][0] if shadows else 'none',
    }
```

- [ ] **Step 5: Run the tests**

Run: `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py test djangopress.core.tests.test_build_adapter -v 1 2>&1 | tail -5`
Expected: `Ran 13 tests … OK`

- [ ] **Step 6: Commit**

```bash
cd /Users/antoniomarante/Documents/djangopress-sites/djangopress
git add src/djangopress/core/build/adapter.py src/djangopress/core/tests/test_build_adapter.py src/djangopress/core/tests/fixtures/concept-checkin-faro.html src/djangopress/core/tests/fixtures/concept-minimal.html
git commit -m "feat(build): concept adapter — completeness, split, head lifting, design tokens"
```

---

### Task 5: Adapter, part 2 — sections, links, switcher, editor contract, images, `adapt()`

**Files:**
- Modify: `src/djangopress/core/build/adapter.py` (append)
- Test: `src/djangopress/core/tests/test_build_adapter.py` (append)

**Interfaces:**
- Produces: `adapt(raw, *, lang, languages, image_map, cta_texts=(), contact_phone='') -> AdaptResult`. Task 6 (importer), Task 8 (screening) and Task 9 consume it. Also `name_sections`, `prefix_links`, `inject_language_switcher`, `apply_editor_contract`, `normalise_images`, `extract_menu`.

- [ ] **Step 1: Append the failing tests**

```python
from djangopress.core.build.adapter import adapt


class AdaptMinimalTest(SimpleTestCase):

    def setUp(self):
        self.r = adapt(MINIMAL, lang='pt', languages=['pt', 'en'],
                       image_map={'dish-1': {'url': 'https://example.com/dish.jpg'}},
                       cta_texts=['Reservar mesa'], contact_phone='+351 289 000 000')

    def test_no_errors(self):
        self.assertEqual(self.r.errors, [])

    def test_sections_named_and_wrapped(self):
        self.assertEqual(self.r.sections, ['hero', 'menu', 'contact'])
        page = soup_of(self.r.page_html)
        secs = page.find_all('section', recursive=False)
        self.assertEqual([s['data-section'] for s in secs], ['hero', 'menu', 'contact'])
        self.assertEqual([s['id'] for s in secs], ['hero', 'menu', 'contact'])
        self.assertIsNone(page.find('main'))

    def test_links_prefixed(self):
        hrefs = [a['href'] for a in soup_of(self.r.header_html).find_all('a')]
        self.assertEqual(hrefs[:4], ['/pt/', '/pt/#menu', '/pt/#contact', '/pt/reservas/'])
        self.assertIn('/pt/politica-de-privacidade/', self.r.footer_html)
        self.assertIn('href="/pt/reservas/"', self.r.page_html)

    def test_overlay_gets_pointer_events_none_but_img_does_not(self):
        page = soup_of(self.r.page_html)
        overlay = page.select_one('section#hero div.bg-gradient-to-t')
        self.assertIn('pointer-events-none', overlay['class'])
        img = page.select_one('section#hero img')
        self.assertNotIn('pointer-events-none', img.get('class', []))
        self.assertEqual(self.r.changes['pointer-events-none'], 1)

    def test_duplicate_image_marked_decorative(self):
        imgs = soup_of(self.r.page_html).select('section#menu img')
        dup = imgs[1]
        self.assertEqual(dup['aria-hidden'], 'true')
        self.assertEqual(dup['alt'], '')

    def test_foreign_image_becomes_placeholder(self):
        img = soup_of(self.r.page_html).select('section#menu img')[0]
        self.assertIn('placehold.co', img['src'])
        self.assertTrue(img['data-image-name'])
        self.assertTrue(img['data-image-prompt'])
        self.assertTrue(any('unsplash' in w for w in self.r.warnings))

    def test_language_switcher_injected_in_slot(self):
        self.assertIn("{% url 'set_language' %}", self.r.header_html)
        self.assertIn('{% load i18n %}', self.r.header_html)
        self.assertNotIn('data-slot="language-switcher"', self.r.header_html)

    def test_menu_extracted(self):
        self.assertEqual(self.r.menu, [
            {'label': 'Casa Teste', 'href': '/pt/'}, {'label': 'Menu', 'href': '/pt/#menu'},
            {'label': 'Contactos', 'href': '/pt/#contact'}, {'label': 'Reservar mesa', 'href': '/pt/reservas/'},
        ])

    def test_head_code_and_settings(self):
        self.assertIn('body.bg-white { background: #F5F0E8', self.r.head_code)
        self.assertNotIn('cdn.tailwindcss.com', self.r.head_code)
        self.assertEqual(self.r.settings['heading_font'], 'Lora')
        self.assertEqual(self.r.settings['body_font'], 'Inter')
        self.assertEqual(self.r.settings['primary_color'], '#c05b3e')
        self.assertEqual(self.r.settings['container_width'], '6xl')
        self.assertEqual(self.r.meta_title, 'Casa Teste — Início')

    def test_trailing_script_kept_in_page(self):
        self.assertTrue(self.r.page_html.rstrip().endswith("<script>console.log('ready');</script>"))

    def test_single_language_has_no_switcher(self):
        r = adapt(MINIMAL, lang='pt', languages=['pt'], image_map={})
        self.assertNotIn('set_language', r.header_html)
        self.assertNotIn('data-slot', r.header_html)


class AdaptCheckinTest(SimpleTestCase):

    def setUp(self):
        self.r = adapt(CHECKIN, lang='pt', languages=['pt', 'en'], image_map={}, cta_texts=['Reservar'])

    def test_eleven_sections_first_is_hero(self):
        self.assertEqual(len(self.r.sections), 11)   # the fixture has 11 direct children of <main> (Task 4 confirmed)
        self.assertEqual(self.r.sections[0], 'hero')
        self.assertEqual(len(set(self.r.sections)), 11)
        for name in self.r.sections:
            self.assertRegex(name, r'^[a-z][a-z0-9-]*$')
        self.assertIn('carta', self.r.sections)

    def test_no_forbidden_tags_and_no_errors(self):
        page = soup_of(self.r.page_html)
        for tag in ('html', 'head', 'body', 'header', 'nav', 'footer'):
            self.assertIsNone(page.find(tag), tag)
        self.assertEqual(self.r.errors, [])

    def test_switcher_appended_when_no_slot(self):
        self.assertIn("{% url 'set_language' %}", self.r.header_html)


class AdaptErrorsTest(SimpleTestCase):

    def test_truncated(self):
        r = adapt(MINIMAL[: MINIMAL.index('<footer')], lang='pt', languages=['pt'], image_map={})
        self.assertFalse(r.ok)
        self.assertTrue(any('truncated' in e for e in r.errors))

    def test_template_syntax_in_footer(self):
        r = adapt(MINIMAL.replace('© 2026 Casa Teste', '© {{ year }} Casa Teste'), lang='pt', languages=['pt'], image_map={})
        self.assertTrue(any('template syntax' in e and 'footer' in e for e in r.errors))

    def test_style_inside_main(self):
        r = adapt(MINIMAL.replace('<h2 class="font-display text-4xl">A carta</h2>', '<style>.x{}</style><h2>A carta</h2>'), lang='pt', languages=['pt'], image_map={})
        self.assertTrue(any('<style>' in e for e in r.errors))

    def test_nav_inside_main(self):
        r = adapt(MINIMAL.replace('<ul><li>Couvert', '<nav><a href="#x">x</a></nav><ul><li>Couvert'), lang='pt', languages=['pt'], image_map={})
        self.assertTrue(any('<nav>' in e for e in r.errors))
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py test djangopress.core.tests.test_build_adapter -v 1 2>&1 | tail -5`
Expected: `ImportError: cannot import name 'adapt'`

- [ ] **Step 3: Append to `adapter.py`**

```python
# --- part 2: structure ------------------------------------------------------

SWITCHER_HTML = (
    '{% load i18n %}<form action="{% url \'set_language\' %}" method="post" class="inline-block">{% csrf_token %}'
    '<input name="next" type="hidden" value="{{ request.path }}">'
    '<select name="language" onchange="this.form.submit()" class="bg-transparent cursor-pointer CLASSES">'
    '{% get_current_language as LANGUAGE_CODE %}{% get_available_languages as LANGUAGES %}'
    '{% for lang_code, lang_name in LANGUAGES %}<option value="{{ lang_code }}" {% if lang_code == LANGUAGE_CODE %}selected{% endif %}>'
    '{{ lang_code|upper }}</option>{% endfor %}</select></form>'
)


def _unique(name, seen):
    base = name if SECTION_NAME_RE.match(name) else 's-' + re.sub(r'[^a-z0-9-]', '', name.lower()) or 's'
    if not SECTION_NAME_RE.match(base):
        base = 'section'
    candidate, n = base, 2
    while candidate in seen:
        candidate, n = f'{base}-{n}', n + 1
    seen.add(candidate)
    return candidate


def name_sections(main, contact_phone=''):
    """Every direct child of <main> becomes a <section data-section=id id=...>; names synthesised when missing."""
    for child in list(main.children):
        if getattr(child, 'name', None) is None:
            if str(child).strip():
                child.wrap(Tag(name='section'))
            continue
        if child.name != 'section':
            child.wrap(Tag(name='section'))
    seen, names = set(), []
    sections = main.find_all('section', recursive=False)
    for i, sec in enumerate(sections):
        name = (sec.get('id') or '').strip().lower()
        if not name:
            if i == 0:
                name = 'hero'
            elif sec.find('form') or (contact_phone and contact_phone in sec.get_text(' ')):
                name = 'contact'
            else:
                heading = sec.find(['h1', 'h2', 'h3'])
                name = slugify(heading.get_text(' ', strip=True)) if heading else 'section'
        name = _unique(name or 'section', seen)
        sec['id'] = name
        sec['data-section'] = name
        names.append(name)
    return names


def prefix_links(root, lang, codes):
    n = 0
    for a in root.find_all('a', href=True):
        href = a['href'].strip()
        new = href
        if href.startswith('#'):
            new = f'/{lang}/{href}'
        elif href == '/':
            new = f'/{lang}/'
        elif href.startswith('/') and not href.startswith('//'):
            if not href.startswith(NON_I18N_PATHS) and not any(href == f'/{c}' or href.startswith(f'/{c}/') for c in codes):
                new = f'/{lang}{href}'
        if new != href:
            a['href'] = new
            n += 1
    return n


def inject_language_switcher(header):
    """Replace <div data-slot="language-switcher"> (or append to <nav>) with a token swapped after serialisation."""
    slot = header.find(attrs={'data-slot': 'language-switcher'})
    nav = header.find('nav') or header
    first_link = nav.find('a')
    classes = ' '.join(c for c in _class_tokens(first_link) if c.startswith(('text-', 'uppercase', 'tracking-', 'font-')))
    if slot is not None:
        slot.replace_with(SWITCHER_TOKEN)
    else:
        nav.append(SWITCHER_TOKEN)
    return SWITCHER_HTML.replace('CLASSES', classes)


def find_template_syntax(html):
    return bool(TEMPLATE_SYNTAX_RE.search(html))


def apply_editor_contract(root, changes):
    for el in root.find_all(class_=True):
        classes = el['class']
        if not ({'absolute', 'fixed'} & set(classes)) or el.name in NON_OVERLAY_TAGS:
            continue
        if el.find(['img', 'svg', 'video', 'input', 'button']):
            continue
        if el.name in EDITABLE_TAGS and el.get_text(strip=True):
            continue
        if any(d.name in EDITABLE_TAGS and d.get_text(strip=True) for d in el.find_all(True)):
            continue
        if 'pointer-events-none' not in classes:
            classes.append('pointer-events-none')
            changes['pointer-events-none'] += 1
    seen = set()
    for img in root.find_all('img'):
        if any(c.startswith('splide') for p in img.parents for c in _class_tokens(p)):
            continue
        src = img.get('src', '')
        if src in seen and img.get('aria-hidden') != 'true':
            img['aria-hidden'] = 'true'
            img['alt'] = ''
            changes['duplicate-img-decorative'] += 1
        seen.add(src)


def normalise_images(root, image_urls, changes, warnings, part):
    counter = 0
    for img in root.find_all('img'):
        src = img.get('src', '').strip()
        section = img.find_parent('section')
        sec_name = section.get('id', part) if section else part
        counter += 1
        if PLACEHOLDER_HOST in src:
            pass
        elif src in image_urls or src.startswith(('/media/', '/static/')):
            if not img.get('alt') and img.get('aria-hidden') != 'true':
                img['alt'] = img.get('data-image-name') or sec_name
                changes['alt-filled'] += 1
            continue
        else:
            warnings.append(f'{part}/{sec_name}: image {src[:80]!r} not in the inventory — replaced by a placeholder')
            img['src'] = f'https://{PLACEHOLDER_HOST}/1200x800?text={sec_name}'
            changes['img-replaced'] += 1
        if not img.get('data-image-name'):
            img['data-image-name'] = f'{sec_name}-img-{counter}'
        if not img.get('data-image-prompt'):
            img['data-image-prompt'] = img.get('alt') or f'photo for {sec_name}'
        if img.get('aria-hidden') == 'true':
            img['alt'] = ''
        elif not img.get('alt'):
            img['alt'] = img['data-image-name']


def extract_menu(header):
    nav = header.find('nav') or header
    items = []
    for a in nav.find_all('a', href=True):
        label = a.get_text(' ', strip=True)
        if label:
            items.append({'label': label, 'href': a['href']})
    return items


def adapt(raw, *, lang, languages, image_map, cta_texts=(), contact_phone=''):
    result = AdaptResult()
    result.errors.extend(check_complete(raw))
    if result.errors:
        return result
    soup = soup_of(raw)
    header, main, footer, trailing = split_document(soup)
    if header is None or main is None or footer is None:
        result.errors.append('document must have one <header>, one <main> and one <footer>')
        return result

    head = lift_head(soup)
    css, n = fix_body_rules(head['css'])
    result.changes['body-rule-rewritten'] = n
    result.changes.update(head['removed'])
    head_code = head['head_code'].replace(head['css'], css) if head['css'] else head['head_code']
    result.head_code = head_code
    result.meta_title, result.meta_description = head['meta_title'], head['meta_description']

    heading_font, body_font = extract_fonts(head['config_js'], head['google_families'])
    result.settings = {'heading_font': heading_font, 'body_font': body_font}
    result.settings.update(extract_colors(head['config_js'], css, soup, cta_texts))
    result.settings.update(infer_layout(soup))

    for part, tag in (('header', header), ('footer', footer)):
        if find_template_syntax(str(tag)):
            result.errors.append(f'{part}: contains Django template syntax ({{{{, {{% or {{#) — not allowed')
    for tag in FORBIDDEN_IN_PAGE:
        if main.find(tag):
            result.errors.append(f'page: contains <{tag}> inside <main> — forbidden in page HTML')
    if main.find('style'):
        result.errors.append('page: <style> inside <main> — CSS belongs in <head>')
    if result.errors:
        return result

    result.sections = name_sections(main, contact_phone)
    codes = list(languages)
    for tag in (header, main, footer):
        result.changes['links-prefixed'] += prefix_links(tag, lang, codes)
    image_urls = {v['url'] for v in image_map.values() if v.get('url')}
    for part, tag in (('header', header), ('page', main), ('footer', footer)):
        apply_editor_contract(tag, result.changes)
        normalise_images(tag, image_urls, result.changes, result.warnings, part)
    if main.find('script'):
        result.warnings.append('page: inline <script> inside a section (kept)')
    result.menu = extract_menu(header)

    switcher = ''
    if len(codes) > 1:
        switcher = inject_language_switcher(header)
    else:
        slot = header.find(attrs={'data-slot': 'language-switcher'})
        if slot is not None:
            slot.decompose()

    result.header_html = str(header).replace(SWITCHER_TOKEN, switcher)
    result.footer_html = str(footer)
    page = ''.join(str(c) for c in main.children).strip()
    if trailing:
        page += '\n' + '\n'.join(str(s) for s in trailing)
    result.page_html = page
    return result
```

- [ ] **Step 4: Run the tests**

Run: `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py test djangopress.core.tests.test_build_adapter -v 1 2>&1 | tail -5`
Expected: `Ran 30 tests … OK` (13 from Task 4 + 17 new). If `test_eleven_sections_first_is_hero` reports a name like `s-` for a section whose heading is all-symbol, that section's heading text is empty — check the fixture's section and adjust `_unique` only if the name is not a legal slug.

- [ ] **Step 5: Commit**

```bash
cd /Users/antoniomarante/Documents/djangopress-sites/djangopress
git add src/djangopress/core/build/adapter.py src/djangopress/core/tests/test_build_adapter.py
git commit -m "feat(build): concept adapter — sections, links, switcher, editor contract, images"
```

---

### Task 6: JSON-LD, importer and `import_concept`

**Files:**
- Create: `src/djangopress/core/build/jsonld.py`
- Create: `src/djangopress/core/build/importer.py`
- Create: `src/djangopress/core/management/commands/import_concept.py`
- Test: `src/djangopress/core/tests/test_build_importer.py`

**Interfaces:**
- Consumes: `adapt` / `AdaptResult` (Task 5); packet dict (Task 2).
- Produces: `build_jsonld(packet) -> dict`, `parse_hours_line(line) -> list[dict]`, `geo_from_maps_url(url) -> dict|None`; `import_result(result, *, packet, set_home=True, change_summary='Import concept') -> dict(page_id, header_id, footer_id, menu_items, warnings)`; `import_as_page(result, *, packet, slug, change_summary=…) -> dict(page_id, slug, warnings)`; `cta_texts_from(packet) -> list[str]`; command `import_concept <file> [--home | --as-page SLUG] [--dry-run] [--packet docs/build-packet.json] [--key k]` (exit 1 on adapter errors, nothing written).

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for JSON-LD, the importer and import_concept (Task 6)."""

import json
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from djangopress.core.build.adapter import adapt
from djangopress.core.build.importer import cta_texts_from, import_as_page, import_result
from djangopress.core.build.jsonld import build_jsonld, geo_from_maps_url, parse_hours_line
from djangopress.core.models import GlobalSection, MenuItem, Page, SiteSettings

FIXTURES = Path(__file__).parent / 'fixtures'
MINIMAL = (FIXTURES / 'concept-minimal.html').read_text()

PACKET = {
    'site': {'slug': 'casa-teste', 'name': 'Casa Teste', 'default_language': 'pt', 'default_language_name': 'Português',
             'languages': ['pt', 'en'], 'lang_prefix': '/pt'},
    'business': {'type': 'restaurant', 'jsonld_type': 'Restaurant', 'specialization': 'x', 'positioning': 'Cozinha de autor algarvia.',
                 'prose': 'Cozinha de autor algarvia.', 'cuisine': 'Algarvia', 'price_range': '€€€'},
    'families': ['editorial'],
    'facts': {'phone': '+351 289 000 000', 'email': 'geral@casateste.pt', 'address': 'Rua do Castelo 1, Faro',
              'maps_url': 'https://www.google.com/maps/place/x/@37.0146,-7.935,17z', 'hours': ['Terça a Sábado: 19:00–23:00', 'Domingo e Segunda: encerrado'],
              'social': {'instagram': 'https://instagram.com/casateste'}},
    'pages': [{'name': 'Home', 'slug': 'home', 'description': ''}],
    'content': {'home': {'required': [
        {'id': 'home-1', 'kind': 'Message', 'text': 'Cozinha de autor algarvia', 'keywords': ['autor', 'algarvia']},
        {'id': 'home-2', 'kind': 'CTA', 'text': 'Reservar mesa', 'href': '/reservas/'},
        {'id': 'home-3', 'kind': 'Proof', 'text': 'Guia Michelin 2024'},
        {'id': 'home-4', 'kind': 'Menu', 'text': 'menu', 'items': [{'name': 'Couvert', 'price': '3.30', 'category': 'Entradas'}]},
    ], 'optional': []}},
    'images': {'strategy': 'reuse existing', 'map': {'dish-1': {'url': 'https://example.com/dish.jpg', 'width': 2048, 'alt': 'Prato'}}, 'constraints': {}},
    'design_constraints': {'brand_colors': [], 'logo': None, 'avoid': [], 'references': [], 'image_max_widths': {}},
    'header': '', 'footer': '',
}


class JsonLdTest(TestCase):

    def test_hours_range(self):
        specs = parse_hours_line('Terça a Sábado: 19:00–23:00')
        self.assertEqual(specs[0]['dayOfWeek'], ['Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'])
        self.assertEqual((specs[0]['opens'], specs[0]['closes']), ('19:00', '23:00'))

    def test_hours_two_ranges_and_list(self):
        specs = parse_hours_line('Seg e Qua: 12h00-15h00, 19h00-23h00')
        self.assertEqual(len(specs), 2)
        self.assertEqual(specs[0]['dayOfWeek'], ['Monday', 'Wednesday'])
        self.assertEqual(specs[1]['opens'], '19:00')

    def test_closed_line_gives_nothing(self):
        self.assertEqual(parse_hours_line('Domingo e Segunda: encerrado'), [])

    def test_unparseable_with_time_keeps_description(self):
        specs = parse_hours_line('Todos os dias exceto feriados: 10:00–18:00')
        self.assertEqual(specs[0]['opens'], '10:00')
        self.assertIn('description', specs[0])

    def test_geo(self):
        self.assertEqual(geo_from_maps_url('https://www.google.com/maps/place/x/@37.0146,-7.935,17z'), {'@type': 'GeoCoordinates', 'latitude': 37.0146, 'longitude': -7.935})
        self.assertEqual(geo_from_maps_url('https://maps.google.com/?q=37.01,-7.93')['latitude'], 37.01)
        self.assertIsNone(geo_from_maps_url('https://goo.gl/maps/abc'))

    def test_restaurant_block(self):
        d = build_jsonld(PACKET)
        self.assertEqual(d['@type'], 'Restaurant')
        self.assertEqual(d['servesCuisine'], 'Algarvia')
        self.assertEqual(d['priceRange'], '€€€')
        self.assertEqual(d['geo']['latitude'], 37.0146)
        self.assertEqual(d['image'], 'https://example.com/dish.jpg')
        self.assertEqual(d['sameAs'], ['https://instagram.com/casateste'])
        self.assertEqual(len(d['openingHoursSpecification']), 1)


class ImportResultTest(TestCase):

    def setUp(self):
        Page.objects.all().delete()
        MenuItem.objects.all().delete()
        GlobalSection.objects.all().delete()
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'Português'}, {'code': 'en', 'name': 'English'}]
        s.default_language = 'pt'
        s.gcs_folder = 'casa-teste'
        s.site_name_i18n = {'pt': 'Casa Teste', 'en': 'Casa Teste'}
        s.save()
        self.result = adapt(MINIMAL, lang='pt', languages=['pt', 'en'], image_map=PACKET['images']['map'],
                            cta_texts=cta_texts_from(PACKET), contact_phone='+351 289 000 000')

    def test_cta_texts(self):
        self.assertEqual(cta_texts_from(PACKET), ['Reservar mesa'])

    def test_import_creates_everything(self):
        out = import_result(self.result, packet=PACKET, set_home=True)
        home = Page.objects.get(slug_i18n__pt='home')
        self.assertEqual(out['page_id'], home.id)
        self.assertIn('data-section="hero"', home.html_content_i18n['pt'])
        self.assertEqual(home.meta_title_i18n['pt'], 'Casa Teste — Início')
        self.assertEqual(list(home.html_content_i18n.keys()), ['pt'])
        s = SiteSettings.load()
        self.assertEqual(s.homepage_id, home.id)
        self.assertIn('tailwind.config', s.custom_head_code)
        self.assertIn('application/ld+json', s.custom_head_code)
        self.assertEqual(s.heading_font, 'Lora')
        self.assertEqual(s.primary_color, '#c05b3e')
        self.assertEqual(s.container_width, '6xl')
        header = GlobalSection.objects.get(key='main-header')
        self.assertTrue(header.is_active)
        self.assertIn("{% url 'set_language' %}", header.html_template_i18n['pt'])
        self.assertEqual(GlobalSection.objects.get(key='main-footer').section_type, 'footer')
        self.assertEqual(MenuItem.objects.count(), 4)
        self.assertEqual(MenuItem.objects.order_by('sort_order').first().label_i18n, {'pt': 'Casa Teste'})

    def test_reimport_versions_and_does_not_duplicate(self):
        import_result(self.result, packet=PACKET)
        import_result(self.result, packet=PACKET, change_summary='again')
        self.assertEqual(Page.objects.filter(slug_i18n__pt='home').count(), 1)
        home = Page.objects.get(slug_i18n__pt='home')
        self.assertEqual(home.versions.count(), 1)
        self.assertEqual(GlobalSection.objects.get(key='main-header').versions.count(), 1)
        self.assertEqual(MenuItem.objects.count(), 4)

    def test_import_as_page_is_scoped(self):
        import_result(self.result, packet=PACKET)
        header_before = GlobalSection.objects.get(key='main-header').html_template_i18n['pt']
        out = import_as_page(self.result, packet=PACKET, slug='homepage-v2')
        page = Page.objects.get(slug_i18n__pt='homepage-v2')
        self.assertEqual(out['page_id'], page.id)
        html = page.html_content_i18n['pt']
        self.assertTrue(html.startswith('<section'))
        self.assertIn('fonts.googleapis.com/css2?family=Lora', html)
        self.assertIn('tailwind.config', html)
        self.assertIn('body.bg-white', html)
        self.assertNotIn('{{', html)
        self.assertEqual(GlobalSection.objects.get(key='main-header').html_template_i18n['pt'], header_before)
        self.assertEqual(SiteSettings.load().homepage_id, Page.objects.get(slug_i18n__pt='home').id)
        self.assertEqual(MenuItem.objects.count(), 4)
        self.assertFalse(MenuItem.objects.filter(url__contains='homepage-v2').exists())

    def test_check_site_residue_is_images_only(self):
        import_result(self.result, packet=PACKET)
        out = StringIO()
        try:
            call_command('check_site', json=True, stdout=out)
        except SystemExit:
            pass
        failures = json.loads(out.getvalue())['failures']
        self.assertEqual({f['check'] for f in failures}, {'images'}, failures)


class ImportConceptCommandTest(TestCase):

    def setUp(self):
        Page.objects.all().delete()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'docs' / 'concepts').mkdir(parents=True)
        (self.root / 'docs' / 'build-packet.json').write_text(json.dumps(PACKET))
        (self.root / 'docs' / 'concepts' / 'concept-b.html').write_text(MINIMAL)
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'Português'}, {'code': 'en', 'name': 'English'}]
        s.default_language = 'pt'
        s.save()

    def tearDown(self):
        self.tmp.cleanup()

    def run_cmd(self, *args):
        out = StringIO()
        call_command('import_concept', str(self.root / 'docs' / 'concepts' / 'concept-b.html'),
                     '--packet', str(self.root / 'docs' / 'build-packet.json'), *args, stdout=out)
        return json.loads(out.getvalue())

    def test_dry_run_writes_nothing(self):
        rep = self.run_cmd('--dry-run')
        self.assertTrue(rep['ok'])
        self.assertEqual(rep['sections'], ['hero', 'menu', 'contact'])
        self.assertFalse(Page.objects.filter(slug_i18n__pt='home').exists())

    def test_import_and_report_file(self):
        rep = self.run_cmd('--home')
        self.assertTrue(rep['ok'])
        self.assertTrue(Page.objects.filter(slug_i18n__pt='home').exists())
        self.assertTrue((self.root / 'docs' / 'concepts' / 'import-b.json').exists())

    def test_as_page_command(self):
        rep = self.run_cmd('--as-page', 'homepage-v3')
        self.assertTrue(rep['ok'])
        self.assertTrue(Page.objects.filter(slug_i18n__pt='homepage-v3').exists())
        self.assertFalse(Page.objects.filter(slug_i18n__pt='home').exists())

    def test_truncated_exits_1(self):
        (self.root / 'docs' / 'concepts' / 'concept-b.html').write_text(MINIMAL[: MINIMAL.index('<footer')])
        with self.assertRaises(SystemExit):
            self.run_cmd('--home')
        self.assertFalse(Page.objects.filter(slug_i18n__pt='home').exists())
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py test djangopress.core.tests.test_build_importer -v 1 2>&1 | tail -5`
Expected: `ModuleNotFoundError: No module named 'djangopress.core.build.importer'`

- [ ] **Step 3: Write `jsonld.py`**

```python
"""JSON-LD for SiteSettings.custom_head_code, built from the packet's facts."""

import re

DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
DAY_TOKENS = {
    'segunda': 0, 'seg': 0, 'monday': 0, 'mon': 0, 'terça': 1, 'terca': 1, 'ter': 1, 'tuesday': 1, 'tue': 1,
    'quarta': 2, 'qua': 2, 'wednesday': 2, 'wed': 2, 'quinta': 3, 'qui': 3, 'thursday': 3, 'thu': 3,
    'sexta': 4, 'sex': 4, 'friday': 4, 'fri': 4, 'sábado': 5, 'sabado': 5, 'sáb': 5, 'sab': 5, 'saturday': 5, 'sat': 5,
    'domingo': 6, 'dom': 6, 'sunday': 6, 'sun': 6,
}
CLOSED_WORDS = ('encerrado', 'fechado', 'closed')
TIME_RANGE_RE = re.compile(r'(\d{1,2})[:h](\d{2})\s*[–\-—a]+\s*(\d{1,2})[:h](\d{2})')
WORD_RE = re.compile(r'[a-záéíóúâêôãõç]+', re.I)
RANGE_WORDS = ('a', 'to', '-', '–', 'até')
GEO_RES = (re.compile(r'@(-?\d+\.\d+),(-?\d+\.\d+)'), re.compile(r'[?&]q=(-?\d+\.\d+),(-?\d+\.\d+)'),
           re.compile(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)'))


def _days_from(text):
    tokens = [w.lower() for w in WORD_RE.findall(text)]
    idx = [(i, DAY_TOKENS[t]) for i, t in enumerate(tokens) if t in DAY_TOKENS]
    if not idx:
        return []
    if len(idx) == 2 and any(t in RANGE_WORDS for t in tokens[idx[0][0] + 1:idx[1][0]]):
        a, b = idx[0][1], idx[1][1]
        return [DAYS[i % 7] for i in range(a, b + 1 if b >= a else b + 8)]
    return [DAYS[d] for _, d in idx]


def parse_hours_line(line):
    if any(w in line.lower() for w in CLOSED_WORDS) and not TIME_RANGE_RE.search(line):
        return []
    head = line.split(':', 1)[0] if re.match(r'^[^\d]*:', line) else line
    days = _days_from(head)
    specs = []
    for o1, o2, c1, c2 in TIME_RANGE_RE.findall(line):
        spec = {'@type': 'OpeningHoursSpecification', 'opens': f'{int(o1):02d}:{o2}', 'closes': f'{int(c1):02d}:{c2}'}
        if days:
            spec['dayOfWeek'] = days
        else:
            spec['description'] = line.strip()
        specs.append(spec)
    return specs


def geo_from_maps_url(url):
    for rx in GEO_RES:
        m = rx.search(url or '')
        if m:
            return {'@type': 'GeoCoordinates', 'latitude': float(m.group(1)), 'longitude': float(m.group(2))}
    return None


def build_jsonld(packet):
    facts, biz, site = packet['facts'], packet['business'], packet['site']
    data = {'@context': 'https://schema.org', '@type': biz['jsonld_type'], 'name': site['name']}
    if facts.get('phone'):
        data['telephone'] = facts['phone']
    if facts.get('email'):
        data['email'] = facts['email']
    if facts.get('address'):
        data['address'] = facts['address']
    geo = geo_from_maps_url(facts.get('maps_url', ''))
    if geo:
        data['geo'] = geo
    hours = [s for line in facts.get('hours', []) for s in parse_hours_line(line)]
    if hours:
        data['openingHoursSpecification'] = hours
    first = next((v['url'] for v in packet['images']['map'].values() if v.get('url')), None)
    if first:
        data['image'] = first
    social = [u for u in facts.get('social', {}).values() if u.startswith('http')]
    if social:
        data['sameAs'] = social
    if biz['jsonld_type'] == 'Restaurant':
        data['servesCuisine'] = biz.get('cuisine') or biz.get('positioning', '')
        data['priceRange'] = biz.get('price_range') or '€€'
    return data
```

- [ ] **Step 4: Write `importer.py`**

```python
"""Save an AdaptResult into the site: Page, GlobalSections, SiteSettings, MenuItems, JSON-LD."""

import json

from djangopress.core.build.jsonld import build_jsonld
from djangopress.core.models import GlobalSection, MenuItem, Page, SiteSettings

TOKEN_FIELDS = ('heading_font', 'body_font', 'background_color', 'text_color', 'heading_color', 'primary_color',
                'primary_button_bg', 'primary_button_text', 'secondary_color', 'accent_color',
                'container_width', 'border_radius_preset', 'shadow_preset')


def cta_texts_from(packet):
    return [i['text'] for page in packet['content'].values() for i in page['required'] if i.get('href')]


def _jsonld_block(packet):
    return '<script type="application/ld+json">' + json.dumps(build_jsonld(packet), ensure_ascii=False) + '</script>'


def import_result(result, *, packet, set_home=True, change_summary='Import concept'):
    lang = packet['site']['default_language']
    warnings = list(result.warnings)
    s = SiteSettings.load()

    home = next((p for p in Page.objects.all() if (p.slug_i18n or {}).get(lang) == 'home'), None)
    if home is None:
        home = Page(sort_order=0, is_active=True)
    else:
        home.create_version(change_summary=change_summary)
    home.title_i18n = {lang: packet['site']['name']}
    home.slug_i18n = {lang: 'home'}
    home.html_content_i18n = {lang: result.page_html}
    home.meta_title_i18n = {lang: result.meta_title or packet['site']['name']}
    home.meta_description_i18n = {lang: result.meta_description or packet['business']['positioning']}
    home.is_active = True
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
    s.custom_head_code = result.head_code + '\n' + _jsonld_block(packet)
    if 'geo' not in build_jsonld(packet):
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
    shipped concept's header and footer. `{{` is broken up so a raw page never holds template syntax.
    """
    lang = packet['site']['default_language']
    page = next((p for p in Page.objects.all() if (p.slug_i18n or {}).get(lang) == slug), None)
    if page is None:
        page = Page(sort_order=500, is_active=True)
    else:
        page.create_version(change_summary=change_summary)
    scoped = (_fonts_link(result.settings) + '\n' + result.head_code).replace('{{', '{ {').replace('{%', '{ %')
    page.title_i18n = {lang: f"{packet['site']['name']} — {slug}"}
    page.slug_i18n = {lang: slug}
    page.html_content_i18n = {lang: result.page_html + '\n' + scoped}
    page.meta_title_i18n = {lang: result.meta_title or packet['site']['name']}
    page.meta_description_i18n = {lang: result.meta_description or packet['business']['positioning']}
    page.is_active = True
    page.save()
    return {'page_id': page.id, 'slug': slug, 'warnings': list(result.warnings)}
```

- [ ] **Step 5: Write the command**

```python
"""import_concept — one standalone concept document → DjangoPress rows (spec §7)."""

import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from djangopress.core.build.adapter import adapt
from djangopress.core.build.importer import cta_texts_from, import_as_page, import_result


def concept_key(path):
    m = re.search(r'concept-([a-z])\.html$', str(path))
    return m.group(1) if m else Path(path).stem


class Command(BaseCommand):
    help = 'Import a standalone concept HTML document as the site home page, header and footer.'

    def add_arguments(self, parser):
        parser.add_argument('file')
        parser.add_argument('--home', action='store_true')
        parser.add_argument('--as-page', default='', metavar='SLUG', help='import as an extra page with this slug (no header/footer/menu changes)')
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--packet', default='docs/build-packet.json')
        parser.add_argument('--key', default='')

    def handle(self, *args, **opts):
        if opts['home'] and opts['as_page']:
            raise CommandError('--home and --as-page are mutually exclusive')
        path = Path(opts['file'])
        packet_path = Path(opts['packet'])
        if not packet_path.exists():
            raise CommandError(f'{packet_path} not found — run build_prepare first')
        packet = json.loads(packet_path.read_text())
        key = opts['key'] or concept_key(path)
        result = adapt(path.read_text(), lang=packet['site']['default_language'], languages=packet['site']['languages'],
                       image_map=packet['images']['map'], cta_texts=cta_texts_from(packet),
                       contact_phone=packet['facts'].get('phone', ''))
        report = result.as_report()
        report['key'] = key
        if result.ok and not opts['dry_run']:
            if opts['as_page']:
                saved = import_as_page(result, packet=packet, slug=opts['as_page'], change_summary=f"Import concept {key} as {opts['as_page']}")
            else:
                saved = import_result(result, packet=packet, set_home=opts['home'], change_summary=f'Import concept {key}')
            report.update(saved)
            out = path.parent / f'import-{key}.json'
            out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
            report['report'] = str(out)
        self.stdout.write(json.dumps(report, ensure_ascii=False))
        if not result.ok:
            raise SystemExit(1)
```

- [ ] **Step 6: Run the tests**

Run: `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py test djangopress.core.tests.test_build_importer -v 1 2>&1 | tail -5`
Expected: `Ran 15 tests … OK`. If `test_check_site_residue_is_images_only` reports `[seo]` lines, print the failures and fix `build_jsonld` (every `JSONLD_REQUIRED['Restaurant']` key must be present); if it reports `[settings] design colors are still the template defaults`, the adapter's colour extraction returned defaults — fix there, not in the test.

- [ ] **Step 7: Commit**

```bash
cd /Users/antoniomarante/Documents/djangopress-sites/djangopress
git add src/djangopress/core/build/jsonld.py src/djangopress/core/build/importer.py src/djangopress/core/management/commands/import_concept.py src/djangopress/core/tests/test_build_importer.py
git commit -m "feat(build): JSON-LD, importer and import_concept command"
```

---

### Task 7: Content contract

**Files:**
- Create: `src/djangopress/core/build/contract.py`
- Test: `src/djangopress/core/tests/test_build_contract.py`

**Interfaces:**
- Consumes: packet dict (Task 2).
- Produces: `check_contract(packet, parts: dict[str, str], lang: str) -> list[dict(id, kind, text, reason)]` and `normalise(text) -> str`. Task 8 consumes.

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for the content contract (Task 7)."""

from django.test import SimpleTestCase

from djangopress.core.build.contract import check_contract, normalise
from djangopress.core.tests.test_build_importer import PACKET

PAGE = """
<section data-section="hero" id="hero"><h1>Cozinha  de AUTOR algarvia</h1>
<a href="/pt/reservas/">Reservar mesa</a></section>
<section data-section="proof" id="proof"><p>Guia Michelin 2024</p></section>
<section data-section="menu" id="menu"><ul><li>Couvert <span>3,30 €</span></li></ul></section>
<section data-section="contact" id="contact"><p>+351 289 000 000 · Rua do Castelo 1, Faro</p>
<p>geral@casateste.pt</p><p>Terça a Sábado 19:00–23:00</p></section>
"""


class NormaliseTest(SimpleTestCase):

    def test_collapses_and_casefolds_keeps_accents(self):
        self.assertEqual(normalise('  Cozinha  de\nAUTOR  '), 'cozinha de autor')
        self.assertEqual(normalise('Terça'), 'terça')


class ContractTest(SimpleTestCase):

    def parts(self, page=PAGE):
        return {'page': page, 'header': '<header><a href="/pt/reservas/">Reservar mesa</a></header>', 'footer': '<footer></footer>'}

    def test_full_page_passes(self):
        self.assertEqual(check_contract(PACKET, self.parts(), 'pt'), [])

    def test_missing_keyword_item(self):
        page = PAGE.replace('Cozinha  de AUTOR algarvia', 'Bem-vindos')
        misses = check_contract(PACKET, self.parts(page), 'pt')
        self.assertEqual([m['id'] for m in misses], ['home-1'])
        self.assertIn('keywords', misses[0]['reason'])

    def test_missing_href(self):
        parts = self.parts(PAGE.replace('/pt/reservas/', '/pt/contactos/'))
        parts['header'] = '<header></header>'
        misses = check_contract(PACKET, parts, 'pt')
        self.assertEqual([m['id'] for m in misses], ['home-2'])
        self.assertIn('/pt/reservas/', misses[0]['reason'])

    def test_missing_exact_and_menu_item(self):
        page = PAGE.replace('Guia Michelin 2024', 'Michelin').replace('Couvert', 'Pão')
        ids = [m['id'] for m in check_contract(PACKET, self.parts(page), 'pt')]
        self.assertEqual(ids, ['home-3', 'home-4'])

    def test_price_accepts_comma_or_dot(self):
        page = PAGE.replace('3,30 €', '3.30€')
        self.assertEqual(check_contract(PACKET, self.parts(page), 'pt'), [])

    def test_missing_fact_phone_and_hours(self):
        page = PAGE.replace('+351 289 000 000', '').replace('19:00–23:00', '')
        reasons = [m['reason'] for m in check_contract(PACKET, self.parts(page), 'pt')]
        self.assertTrue(any('phone' in r for r in reasons))
        self.assertTrue(any('19:00' in r for r in reasons))
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py test djangopress.core.tests.test_build_contract -v 1 2>&1 | tail -5`
Expected: `ModuleNotFoundError: No module named 'djangopress.core.build.contract'`

- [ ] **Step 3: Write `contract.py`**

```python
"""Content contract: every (required) briefing item must be present in the shipped HTML (spec §8.3)."""

import re
import unicodedata

from bs4 import BeautifulSoup

TIME_RE = re.compile(r'\d{1,2}[:h]\d{2}')


def normalise(text):
    text = unicodedata.normalize('NFC', text or '')
    return re.sub(r'\s+', ' ', text).strip().casefold()


def _digits(text):
    return re.sub(r'\D', '', text or '')


def _haystack(parts):
    texts, hrefs, raw = [], [], []
    for html in parts.values():
        soup = BeautifulSoup(html, 'html.parser')
        texts.append(soup.get_text(' '))
        texts.extend(img.get('alt', '') for img in soup.find_all('img'))
        hrefs.extend(a['href'].strip() for a in soup.find_all('a', href=True))
        raw.append(html)
    return normalise(' '.join(texts)), set(hrefs)


def _price_forms(price):
    p = price.strip().replace(',', '.')
    return {p, p.replace('.', ',')}


def check_contract(packet, parts, lang):
    text, hrefs = _haystack(parts)
    misses = []

    def miss(item, reason):
        misses.append({'id': item['id'], 'kind': item['kind'], 'text': item.get('text', ''), 'reason': reason})

    for page in packet['content'].values():
        for item in page['required']:
            if item.get('items'):
                for entry in item['items']:
                    if normalise(entry['name']) not in text:
                        miss(item, f"menu item {entry['name']!r} not found")
                        break
                    if entry.get('price') and not any(f in text for f in _price_forms(entry['price'])):
                        miss(item, f"price {entry['price']!r} for {entry['name']!r} not found")
                        break
            elif item.get('href'):
                href = item['href']
                wanted = f'/{lang}{href}' if href.startswith('/') and not href.startswith(f'/{lang}/') else href
                if wanted not in hrefs:
                    miss(item, f'no link to {wanted}')
                elif normalise(item['text']) not in text:
                    miss(item, f"CTA label {item['text']!r} not found")
            elif item.get('keywords'):
                if not any(normalise(k) in text for k in item['keywords']):
                    miss(item, f"none of the keywords {item['keywords']} found")
            elif normalise(item.get('text', '')) not in text:
                miss(item, f"text {item['text']!r} not found verbatim")

    facts = packet['facts']
    fact_item = {'id': 'facts', 'kind': 'Contact', 'text': ''}
    if facts.get('phone') and _digits(facts['phone']) not in _digits(text):
        miss(fact_item, f"phone {facts['phone']!r} not found")
    if facts.get('email') and normalise(facts['email']) not in text:
        miss(fact_item, f"email {facts['email']!r} not found")
    if facts.get('address') and normalise(facts['address']) not in text:
        miss(fact_item, f"address {facts['address']!r} not found")
    for line in facts.get('hours', []):
        for t in TIME_RE.findall(line):
            canon = t.replace('h', ':')
            if canon not in text and canon.replace(':', 'h') not in text:
                miss(fact_item, f'opening hours {t} (from {line!r}) not found')
                break
    return misses
```

- [ ] **Step 4: Run the tests**

Run: `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py test djangopress.core.tests.test_build_contract -v 1 2>&1 | tail -5`
Expected: `Ran 7 tests … OK`

- [ ] **Step 5: Commit**

```bash
cd /Users/antoniomarante/Documents/djangopress-sites/djangopress
git add src/djangopress/core/build/contract.py src/djangopress/core/tests/test_build_contract.py
git commit -m "feat(build): content contract check"
```

---

### Task 8: Playwright probe, `build_verify`, and the `[build]` extra

**Files:**
- Create: `src/djangopress/core/build/probe.js`
- Create: `src/djangopress/core/build/probe.py`
- Create: `src/djangopress/core/build/verify.py`
- Create: `src/djangopress/core/management/commands/build_verify.py`
- Modify: `pyproject.toml` (add `[project.optional-dependencies]`), `scripts/new_site.sh:143-149`
- Test: `src/djangopress/core/tests/test_build_probe.py`

**Interfaces:**
- Consumes: `adapt`, `cta_texts_from`, `check_contract`, `check_site` (call_command).
- Produces: `run_probe(url, widths=(390, 834, 1440), *, cta_texts=(), fonts=(), screenshot_path=None) -> dict(available, defects[{kind, section, detail, width}])`; `BLOCKING_KINDS`; `screen_file(path, packet, *, probe=None) -> dict`; `verify_live(packet, *, port, probe=None, screenshot=True) -> dict` (a `None` probe resolves to `run_probe` at call time); `is_residue(failure) -> bool`; command `build_verify [--files …] [--widths 390,834,1440] [--port 8000] [--no-screenshot] [--packet …]` (exit 0 clean / 1 defects / 2 probe unavailable).

- [ ] **Step 1: Install Playwright in the test site venv (one-off, the designated test site only)**

```bash
cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/pip install -q playwright && .venv/bin/playwright install chromium 2>&1 | tail -1
```

- [ ] **Step 2: Write the failing tests**

```python
"""Tests for the probe and build_verify (Task 8)."""

import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from djangopress.core.build.adapter import adapt
from djangopress.core.build.importer import cta_texts_from, import_result
from djangopress.core.build.probe import run_probe
from djangopress.core.build.verify import BLOCKING_KINDS, is_residue, screen_file, verify_live
from djangopress.core.models import Page, SiteSettings
from djangopress.core.tests.test_build_importer import MINIMAL, PACKET

BROKEN = """<!DOCTYPE html><html><head><style>body{margin:0}</style></head><body>
<header><a href="#" style="color:#fff">Home</a></header>
<main>
<section data-section="hero" id="hero" style="height:600px;background:#fff"><h1>Hi</h1><div style="width:2000px;height:10px"></div></section>
<section data-section="empty" id="empty"></section>
<section data-section="text" id="text" style="height:300px"><p>Body</p></section>
<section data-section="reveal" id="reveal" style="height:300px"><p style="opacity:0">Hidden until scroll</p></section>
</main>
<footer style="height:200px">footer</footer>
<div style="position:fixed;bottom:0;left:0;right:0;height:80px;background:#000"></div>
</body></html>"""


def playwright_available():
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


class ProbeTest(TestCase):

    def setUp(self):
        if not playwright_available():
            self.skipTest('playwright not installed')

    def test_detects_known_defects(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'broken.html'
            f.write_text(BROKEN)
            try:
                out = run_probe(f.as_uri(), widths=(390,), cta_texts=['Reservar'])
            except Exception as exc:  # chromium missing
                self.skipTest(f'chromium unavailable: {exc}')
        kinds = {d['kind'] for d in out['defects']}
        self.assertTrue(out['available'])
        self.assertIn('overflow', kinds)
        self.assertIn('empty-section', kinds)
        self.assertIn('covered-footer', kinds)
        self.assertIn('cta-below-fold', kinds)
        self.assertIn('header-contrast', kinds)
        self.assertIn('hidden-content', kinds)
        self.assertEqual(next(d for d in out['defects'] if d['kind'] == 'hidden-content')['section'], 'reveal')
        self.assertEqual(next(d for d in out['defects'] if d['kind'] == 'overflow')['section'], 'hero')

    def test_clean_page_and_screenshot(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'ok.html'
            f.write_text(MINIMAL)
            shot = Path(d) / 'home-390.png'
            try:
                out = run_probe(f.as_uri(), widths=(390,), screenshot_path=shot)
            except Exception as exc:
                self.skipTest(f'chromium unavailable: {exc}')
            self.assertTrue(shot.exists())
        blocking = [x for x in out['defects'] if x['kind'] in BLOCKING_KINDS]
        self.assertEqual(blocking, [])


class ResidueTest(TestCase):

    def test_residue(self):
        self.assertTrue(is_residue({'check': 'images', 'message': 'page 1 [pt]: unresolved placeholder https://placehold.co/x'}))
        self.assertTrue(is_residue({'check': 'images', 'message': 'page 1 [pt]: leftover data-image-* attribute on x'}))
        self.assertFalse(is_residue({'check': 'images', 'message': 'page 1 [pt]: <img> without alt (x)'}))
        self.assertFalse(is_residue({'check': 'links', 'message': 'x'}))


FAKE_PROBE_OK = lambda url, **kw: {'available': True, 'defects': []}  # noqa: E731
FAKE_PROBE_BAD = lambda url, **kw: {'available': True, 'defects': [{'kind': 'overflow', 'section': 'menu', 'detail': 'x', 'width': 390}]}  # noqa: E731
FAKE_PROBE_NONE = lambda url, **kw: {'available': False, 'defects': []}  # noqa: E731


class ScreenFileTest(TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.f = Path(self.tmp.name) / 'concept-b.html'
        self.f.write_text(MINIMAL)

    def tearDown(self):
        self.tmp.cleanup()

    def test_clean(self):
        r = screen_file(self.f, PACKET, probe=FAKE_PROBE_OK)
        self.assertEqual(r['key'], 'b')
        self.assertEqual(r['hard_errors'], [])
        self.assertEqual(r['content_missing'], [])
        self.assertTrue(r['clean'])

    def test_blocking_defect(self):
        r = screen_file(self.f, PACKET, probe=FAKE_PROBE_BAD)
        self.assertFalse(r['clean'])

    def test_truncated_is_hard_error(self):
        self.f.write_text(MINIMAL[: MINIMAL.index('<footer')])
        r = screen_file(self.f, PACKET, probe=FAKE_PROBE_OK)
        self.assertTrue(r['hard_errors'])
        self.assertFalse(r['clean'])

    def test_content_missing_blocks(self):
        self.f.write_text(MINIMAL.replace('Guia Michelin 2024', 'x'))
        r = screen_file(self.f, PACKET, probe=FAKE_PROBE_OK)
        self.assertEqual([m['id'] for m in r['content_missing']], ['home-3'])
        self.assertFalse(r['clean'])


class VerifyLiveTest(TestCase):

    def setUp(self):
        Page.objects.all().delete()
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'Português'}, {'code': 'en', 'name': 'English'}]
        s.default_language = 'pt'
        s.gcs_folder = 'casa-teste'
        s.save()
        result = adapt(MINIMAL, lang='pt', languages=['pt', 'en'], image_map=PACKET['images']['map'],
                       cta_texts=cta_texts_from(PACKET), contact_phone='+351 289 000 000')
        import_result(result, packet=PACKET)

    def test_verify_live_clean_with_residue(self):
        with patch('djangopress.core.build.verify.ensure_server', return_value=None):
            r = verify_live(PACKET, port=8999, probe=FAKE_PROBE_OK, screenshot=False)
        self.assertEqual(r['check_site'], [])
        self.assertGreater(r['residue'], 0)
        self.assertEqual(r['content_missing'], [])
        self.assertTrue(r['clean'])

    def test_probe_unavailable_reported(self):
        with patch('djangopress.core.build.verify.ensure_server', return_value=None):
            r = verify_live(PACKET, port=8999, probe=FAKE_PROBE_NONE, screenshot=False)
        self.assertFalse(r['probe']['available'])
        self.assertTrue(r['clean'])


class BuildVerifyCommandTest(TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'docs' / 'concepts').mkdir(parents=True)
        (self.root / 'docs' / 'build-packet.json').write_text(json.dumps(PACKET))
        (self.root / 'docs' / 'concepts' / 'concept-a.html').write_text(MINIMAL)
        (self.root / 'docs' / 'concepts' / 'concept-b.html').write_text(MINIMAL[: MINIMAL.index('<footer')])

    def tearDown(self):
        self.tmp.cleanup()

    def test_files_mode_writes_screen_json_and_exits_1(self):
        out = StringIO()
        with patch('djangopress.core.build.verify.run_probe', FAKE_PROBE_OK), \
             patch('djangopress.core.management.commands.build_verify.Path.cwd', return_value=self.root):
            with self.assertRaises(SystemExit) as cm:
                call_command('build_verify', '--files', str(self.root / 'docs/concepts/concept-a.html'),
                             str(self.root / 'docs/concepts/concept-b.html'),
                             '--packet', str(self.root / 'docs/build-packet.json'), stdout=out)
        self.assertEqual(cm.exception.code, 1)
        screen = json.loads((self.root / 'docs' / 'concepts' / 'screen.json').read_text())
        self.assertEqual([(s['key'], s['clean']) for s in screen], [('a', True), ('b', False)])
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py test djangopress.core.tests.test_build_probe -v 1 2>&1 | tail -5`
Expected: `ModuleNotFoundError: No module named 'djangopress.core.build.probe'`

- [ ] **Step 4: Write `probe.js`**

```javascript
// Layout probe (spec §8.2). Evaluated by Playwright with page.evaluate(PROBE_JS, args).
// Returns [{kind, section, detail}]. args = {ctaTexts: [...], fonts: [...]}
(args) => {
  const defects = [];
  const w = window.innerWidth, h = window.innerHeight;
  const de = document.documentElement;
  const norm = s => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();

  function sectionOf(el) {
    if (!el || !el.closest) return 'page';
    const s = el.closest('[data-section]');
    if (s) return s.dataset.section;
    if (el.closest('header')) return 'header';
    if (el.closest('footer')) return 'footer';
    return 'page';
  }
  function effectiveBg(el) {
    let e = el;
    while (e && e !== de) {
      const bg = getComputedStyle(e).backgroundColor;
      if (bg && bg !== 'transparent' && !/rgba\(\d+, \d+, \d+, 0\)/.test(bg)) return bg;
      e = e.parentElement;
    }
    return getComputedStyle(document.body).backgroundColor || 'rgb(255, 255, 255)';
  }
  function lum(c) {
    const m = (c || '').match(/\d+(\.\d+)?/g);
    if (!m || m.length < 3) return null;
    const [r, g, b] = m.slice(0, 3).map(v => { v = parseFloat(v) / 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  }
  function contrast(a, b) {
    const la = lum(a), lb = lum(b);
    if (la === null || lb === null) return null;
    const hi = Math.max(la, lb), lo = Math.min(la, lb);
    return (hi + 0.05) / (lo + 0.05);
  }

  // Scroll the whole page first so lazy/intersection-driven content has had its chance to appear.
  for (let y = 0; y < de.scrollHeight; y += Math.max(200, h / 2)) window.scrollTo(0, y);
  window.scrollTo(0, de.scrollHeight);
  window.scrollTo(0, 0);

  for (const sec of document.querySelectorAll('[data-section]')) {
    const texts = [...sec.querySelectorAll('h1,h2,h3,h4,p,li,a,span')].filter(e => e.textContent.trim());
    if (!texts.length) continue;
    const hidden = texts.filter(e => { const cs = getComputedStyle(e); return parseFloat(cs.opacity) === 0 || cs.visibility === 'hidden'; });
    if (hidden.length === texts.length) defects.push({ kind: 'hidden-content', section: sec.dataset.section, detail: `${texts.length} text elements at opacity 0 / hidden after scrolling the page` });
  }

  if (de.scrollWidth > w + 1) {
    let culprit = null;
    for (const el of document.querySelectorAll('body *')) {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.right > w + 1) { culprit = el; break; }
    }
    defects.push({ kind: 'overflow', section: sectionOf(culprit), detail: `scrollWidth ${de.scrollWidth} > ${w}` + (culprit ? ` at <${culprit.tagName.toLowerCase()}>` : '') });
  }

  for (const sec of document.querySelectorAll('[data-section]')) {
    const r = sec.getBoundingClientRect();
    if (r.height < 40) defects.push({ kind: 'empty-section', section: sec.dataset.section, detail: `height ${Math.round(r.height)}px` });
  }

  const header = document.querySelector('header');
  if (header) {
    const link = header.querySelector('a');
    if (link) {
      const rect = link.getBoundingClientRect();
      const x = Math.min(w - 1, Math.max(0, rect.left + rect.width / 2));
      const y = Math.max(0, rect.top + rect.height / 2);
      const under = document.elementsFromPoint(x, y).find(e => !header.contains(e));
      const ratio = contrast(getComputedStyle(link).color, under ? effectiveBg(under) : effectiveBg(document.body));
      if (ratio !== null && ratio < 3) defects.push({ kind: 'header-contrast', section: 'header', detail: `ratio ${ratio.toFixed(2)} for first nav link` });
    }
  }

  for (const img of document.images) {
    if (img.src.includes('placehold.co') || !img.complete || !img.naturalWidth) continue;
    if (img.naturalWidth < img.clientWidth * 0.9) defects.push({ kind: 'upscaled-image', section: sectionOf(img), detail: `${img.naturalWidth}px source rendered at ${img.clientWidth}px` });
  }

  if (args.ctaTexts && args.ctaTexts.length) {
    const wanted = args.ctaTexts.map(norm);
    let found = false;
    for (const el of document.querySelectorAll('a, button')) {
      const r = el.getBoundingClientRect();
      if (wanted.includes(norm(el.textContent)) && r.height > 0 && r.top >= 0 && r.top < h) { found = true; break; }
    }
    if (!found) defects.push({ kind: 'cta-below-fold', section: 'hero', detail: 'no primary CTA inside the first viewport' });
  }

  for (const sec of document.querySelectorAll('[data-section]')) {
    const texts = [...sec.querySelectorAll('h1,h2,h3,h4,p')].map(e => ({ e, r: e.getBoundingClientRect() })).filter(t => t.r.height > 0 && t.r.width > 0);
    let reported = false;
    for (let i = 0; i < texts.length && !reported; i++) {
      for (let j = i + 1; j < texts.length; j++) {
        const a = texts[i], b = texts[j];
        if (a.e.contains(b.e) || b.e.contains(a.e)) continue;
        const ox = Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left);
        const oy = Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top);
        if (ox > 8 && oy > 8) { defects.push({ kind: 'overlapping-text', section: sec.dataset.section, detail: `<${a.e.tagName.toLowerCase()}> overlaps <${b.e.tagName.toLowerCase()}>` }); reported = true; break; }
      }
    }
  }

  const footer = document.querySelector('footer');
  if (footer) {
    window.scrollTo(0, de.scrollHeight);
    const fr = footer.getBoundingClientRect();
    for (const el of document.querySelectorAll('body *')) {
      if (footer.contains(el) || getComputedStyle(el).position !== 'fixed') continue;
      const r = el.getBoundingClientRect();
      if (r.width * r.height === 0) continue;
      const ox = Math.min(fr.right, r.right) - Math.max(fr.left, r.left);
      const oy = Math.min(fr.bottom, r.bottom) - Math.max(fr.top, r.top);
      if (ox > 0 && oy > 24) { defects.push({ kind: 'covered-footer', section: 'footer', detail: `fixed <${el.tagName.toLowerCase()}> covers ${Math.round(oy)}px of the footer` }); break; }
    }
    window.scrollTo(0, 0);
  }

  for (const f of (args.fonts || [])) {
    if (f && !document.fonts.check(`16px "${f}"`)) defects.push({ kind: 'font-not-loaded', section: 'head', detail: f });
  }
  return defects;
}
```

- [ ] **Step 5: Write `probe.py`**

```python
"""Run probe.js in Chromium at several widths (spec §8.2). Playwright is optional."""

from pathlib import Path

PROBE_JS = (Path(__file__).with_name('probe.js')).read_text()


def run_probe(url, widths=(390, 834, 1440), *, cta_texts=(), fonts=(), screenshot_path=None, screenshot_width=390):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {'available': False, 'defects': []}
    defects, page_errors = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for w in widths:
                page = browser.new_page(viewport={'width': w, 'height': 900})
                page.on('pageerror', lambda e: page_errors.append(str(e)))
                page.goto(url, wait_until='networkidle', timeout=60000)
                page.evaluate('() => document.fonts.ready')
                for d in page.evaluate(PROBE_JS, {'ctaTexts': list(cta_texts), 'fonts': list(fonts)}):
                    d['width'] = w
                    defects.append(d)
                if screenshot_path and w == screenshot_width:
                    Path(screenshot_path).parent.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(screenshot_path), full_page=True)
                page.close()
        finally:
            browser.close()
    for err in dict.fromkeys(page_errors):
        defects.append({'kind': 'console-error', 'section': 'page', 'detail': err[:200], 'width': 0})
    return {'available': True, 'defects': defects}
```

- [ ] **Step 6: Write `verify.py`**

```python
"""Screening of concept files and live verification of the imported site (spec §8)."""

import json
import re
import socket
import subprocess
import sys
import time
from io import StringIO
from pathlib import Path

from django.core.management import call_command

from djangopress.core.build.adapter import adapt
from djangopress.core.build.contract import check_contract
from djangopress.core.build.importer import cta_texts_from
from djangopress.core.build.probe import run_probe
from djangopress.core.models import GlobalSection, Page

BLOCKING_KINDS = {'overflow', 'empty-section', 'hidden-content', 'console-error'}
RESIDUE_RE = re.compile(r'unresolved placeholder|leftover data-image-\* attribute')


def is_residue(failure):
    return failure.get('check') == 'images' and bool(RESIDUE_RE.search(failure.get('message', '')))


def _adapt(path, packet):
    return adapt(path.read_text(), lang=packet['site']['default_language'], languages=packet['site']['languages'],
                 image_map=packet['images']['map'], cta_texts=cta_texts_from(packet),
                 contact_phone=packet['facts'].get('phone', ''))


def _fonts(settings):
    return [f for f in (settings.get('heading_font'), settings.get('body_font')) if f]


def screen_file(path, packet, *, probe=None, widths=(390, 834, 1440)):
    probe = probe or run_probe   # resolved at call time so tests can patch verify.run_probe
    path = Path(path)
    m = re.search(r'concept-([a-z])\.html$', path.name)
    key = m.group(1) if m else path.stem
    result = _adapt(path, packet)
    lang = packet['site']['default_language']
    missing = check_contract(packet, {'page': result.page_html, 'header': result.header_html, 'footer': result.footer_html}, lang) if result.ok else []
    probe_out = probe(path.resolve().as_uri(), widths=widths, cta_texts=cta_texts_from(packet), fonts=_fonts(result.settings)) if result.ok else {'available': True, 'defects': []}
    blocking = [d for d in probe_out['defects'] if d['kind'] in BLOCKING_KINDS]
    return {
        'key': key, 'file': str(path), 'hard_errors': result.errors, 'warnings': result.warnings,
        'defects': probe_out['defects'], 'content_missing': missing, 'probe_available': probe_out['available'],
        'clean': result.ok and not missing and not blocking,
    }


def run_check_site():
    out = StringIO()
    try:
        call_command('check_site', json=True, stdout=out)
    except SystemExit:
        pass
    failures = json.loads(out.getvalue() or '{"failures": []}')['failures']
    return [f for f in failures if not is_residue(f)], sum(1 for f in failures if is_residue(f))


def _port_open(port):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(('127.0.0.1', port)) == 0


def ensure_server(port):
    """Start `manage.py runserver` if nothing answers on the port. Returns the Popen to stop, or None."""
    if _port_open(port):
        return None
    proc = subprocess.Popen([sys.executable, 'manage.py', 'runserver', f'127.0.0.1:{port}', '--noreload'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        if _port_open(port):
            return proc
        time.sleep(0.5)
    proc.terminate()
    raise RuntimeError(f'dev server did not answer on port {port}')


def verify_live(packet, *, port=8000, probe=None, screenshot=True, widths=(390, 834, 1440)):
    probe = probe or run_probe
    lang = packet['site']['default_language']
    failures, residue = run_check_site()
    home = next((p for p in Page.objects.all() if (p.slug_i18n or {}).get(lang) == 'home'), None)
    parts = {
        'page': (home.html_content_i18n or {}).get(lang, '') if home else '',
        'header': ((GlobalSection.objects.filter(key='main-header').first() or GlobalSection()).html_template_i18n or {}).get(lang, ''),
        'footer': ((GlobalSection.objects.filter(key='main-footer').first() or GlobalSection()).html_template_i18n or {}).get(lang, ''),
    }
    missing = check_contract(packet, parts, lang)
    proc = ensure_server(port)
    try:
        from djangopress.core.models import SiteSettings
        s = SiteSettings.load()
        probe_out = probe(f'http://127.0.0.1:{port}/{lang}/', widths=widths, cta_texts=cta_texts_from(packet),
                          fonts=[s.heading_font.split(',')[0], s.body_font.split(',')[0]],
                          screenshot_path=Path('docs/screenshots/home-390.png') if screenshot else None)
    finally:
        if proc is not None:
            proc.terminate()
    blocking = [d for d in probe_out['defects'] if d['kind'] in BLOCKING_KINDS]
    return {
        'check_site': failures, 'residue': residue, 'content_missing': missing, 'probe': probe_out,
        'screenshot': 'docs/screenshots/home-390.png' if screenshot and probe_out['available'] else None,
        'clean': not failures and not missing and not blocking,
    }
```

- [ ] **Step 7: Write the command**

```python
"""build_verify — screen concept files, or verify the live site (spec §8)."""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from djangopress.core.build.verify import screen_file, verify_live


class Command(BaseCommand):
    help = 'Verify concept files (--files) or the imported site: check_site + probe + content contract.'

    def add_arguments(self, parser):
        parser.add_argument('--files', nargs='*', default=[])
        parser.add_argument('--widths', default='390,834,1440')
        parser.add_argument('--port', type=int, default=8000)
        parser.add_argument('--no-screenshot', action='store_true')
        parser.add_argument('--packet', default='docs/build-packet.json')

    def handle(self, *args, **opts):
        packet_path = Path(opts['packet'])
        if not packet_path.exists():
            raise CommandError(f'{packet_path} not found — run build_prepare first')
        packet = json.loads(packet_path.read_text())
        widths = tuple(int(w) for w in opts['widths'].split(','))
        if opts['files']:
            results = [screen_file(f, packet, widths=widths) for f in opts['files']]
            out = Path.cwd() / 'docs' / 'concepts' / 'screen.json'
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(results, ensure_ascii=False, indent=2))
            self.stdout.write(json.dumps(results, ensure_ascii=False))
            if not all(r['clean'] for r in results):
                raise SystemExit(1)
            if not all(r['probe_available'] for r in results):
                raise SystemExit(2)
            return
        result = verify_live(packet, port=opts['port'], screenshot=not opts['no_screenshot'], widths=widths)
        out = Path.cwd() / 'docs' / 'verify.json'
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        self.stdout.write(json.dumps(result, ensure_ascii=False))
        if not result['clean']:
            raise SystemExit(1)
        if not result['probe']['available']:
            raise SystemExit(2)
```

- [ ] **Step 8: Add the `[build]` extra and install it in `new_site.sh`**

In `pyproject.toml`, after the `dependencies = [...]` list, add:

```toml
[project.optional-dependencies]
build = ["playwright>=1.45"]
```

In `scripts/new_site.sh`, replace the line `pip install -q -e "$SOURCE_DIR"` with:

```bash
pip install -q -e "$SOURCE_DIR[build]"
.venv/bin/playwright install chromium >/dev/null 2>&1 || echo "  (chromium not installed — build_verify will skip the layout probe)"
```

- [ ] **Step 9: Run the tests**

Run: `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py test djangopress.core.tests.test_build_probe -v 1 2>&1 | tail -5`
Expected: `Ran 12 tests … OK` (the two `ProbeTest` cases run for real; if they skip, chromium did not install in Step 1 — rerun it).

- [ ] **Step 10: Commit**

```bash
cd /Users/antoniomarante/Documents/djangopress-sites/djangopress
git add src/djangopress/core/build/probe.js src/djangopress/core/build/probe.py src/djangopress/core/build/verify.py src/djangopress/core/management/commands/build_verify.py src/djangopress/core/tests/test_build_probe.py pyproject.toml scripts/new_site.sh
git commit -m "feat(build): Playwright layout probe and build_verify command"
```

---

### Task 9: `promote_concept`

**Files:**
- Create: `src/djangopress/core/management/commands/promote_concept.py`
- Test: `src/djangopress/core/tests/test_build_promote.py`

**Interfaces:**
- Consumes: `adapt`, `import_result`, `cta_texts_from`, `Ledger`.
- Produces: command `promote_concept <k> [--publish] [--packet …]`: imports `docs/concepts/concept-<k>.html` as home, marks it `shipped` in `concepts.json` (any other `shipped` → `rejected`), `Ledger.mark_shipped(site, k)`, and with `--publish` runs `bash scripts/sync-to-prod.sh && railway redeploy -y` when `railway status` succeeds. Exit 1 on adapter errors.

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for promote_concept (Task 9)."""

import json
import os
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from djangopress.core.models import Page, SiteSettings
from djangopress.core.tests.test_build_importer import MINIMAL, PACKET

INDEX = [
    {'key': 'a', 'name': 'Safe', 'register': 'safe', 'premise': '', 'file': 'concept-a.html', 'status': 'rejected'},
    {'key': 'b', 'name': 'Distinct', 'register': 'distinctive', 'premise': '', 'file': 'concept-b.html', 'status': 'shipped'},
    {'key': 'c', 'name': 'Wild', 'register': 'creative', 'premise': '', 'file': 'concept-c.html', 'status': 'rejected'},
]


class PromoteConceptTest(TestCase):

    def setUp(self):
        Page.objects.all().delete()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'docs' / 'concepts').mkdir(parents=True)
        (self.root / 'docs' / 'build-packet.json').write_text(json.dumps(PACKET))
        (self.root / 'docs' / 'concepts' / 'concepts.json').write_text(json.dumps(INDEX))
        (self.root / 'docs' / 'concepts' / 'concept-c.html').write_text(MINIMAL)
        (self.root / '.design-dna').mkdir()
        (self.root / '.design-dna' / 'ledger.json').write_text(json.dumps([
            {'site': 'casa-teste', 'date': '2026-09-16', 'key': 'b', 'name': 'Distinct', 'vertical': 'restaurant', 'register': 'distinctive', 'shipped': True, 'dna': {}},
            {'site': 'casa-teste', 'date': '2026-09-16', 'key': 'c', 'name': 'Wild', 'vertical': 'restaurant', 'register': 'creative', 'shipped': False, 'dna': {}},
        ]))
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'Português'}, {'code': 'en', 'name': 'English'}]
        s.default_language = 'pt'
        s.save()

    def tearDown(self):
        self.tmp.cleanup()

    def run_cmd(self, *args):
        out = StringIO()
        with patch('djangopress.core.management.commands.promote_concept.Path.cwd', return_value=self.root), \
             patch.dict(os.environ, {'DJANGOPRESS_SITES_ROOT': self.tmp.name}), \
             patch('djangopress.core.management.commands.promote_concept.subprocess.run') as run:
            run.return_value.returncode = 0
            call_command('promote_concept', *args, '--packet', str(self.root / 'docs' / 'build-packet.json'), stdout=out)
        return json.loads(out.getvalue()), run

    def test_promote_swaps_status_and_ledger(self):
        rep, run = self.run_cmd('c')
        self.assertTrue(rep['ok'])
        self.assertTrue(Page.objects.filter(slug_i18n__pt='home').exists())
        index = {e['key']: e['status'] for e in json.loads((self.root / 'docs' / 'concepts' / 'concepts.json').read_text())}
        self.assertEqual(index, {'a': 'rejected', 'b': 'rejected', 'c': 'shipped'})
        ledger = {e['key']: e['shipped'] for e in json.loads((self.root / '.design-dna' / 'ledger.json').read_text())}
        self.assertEqual(ledger, {'b': False, 'c': True})
        run.assert_not_called()

    def test_publish_runs_sync_and_redeploy(self):
        rep, run = self.run_cmd('c', '--publish')
        cmds = [c.args[0] for c in run.call_args_list]
        self.assertEqual(cmds[0], ['railway', 'status'])
        self.assertIn('railway redeploy -y', cmds[1])
        self.assertTrue(rep['published'])
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py test djangopress.core.tests.test_build_promote -v 1 2>&1 | tail -5`
Expected: `Unknown command: 'promote_concept'` (CommandError)

- [ ] **Step 3: Write the command**

```python
"""promote_concept — make another already-built concept the live home page, optionally publish (spec §9, §10)."""

import json
import subprocess
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from djangopress.core.build.adapter import adapt
from djangopress.core.build.importer import cta_texts_from, import_result
from djangopress.core.build.ledger import Ledger

PUBLISH_CMD = 'bash scripts/sync-to-prod.sh && railway redeploy -y'


class Command(BaseCommand):
    help = 'Import docs/concepts/concept-<k>.html as the home page and mark it shipped.'

    def add_arguments(self, parser):
        parser.add_argument('key')
        parser.add_argument('--publish', action='store_true')
        parser.add_argument('--packet', default='docs/build-packet.json')

    def handle(self, *args, **opts):
        root = Path.cwd()
        key = opts['key']
        packet = json.loads(Path(opts['packet']).read_text())
        concepts_dir = root / 'docs' / 'concepts'
        path = concepts_dir / f'concept-{key}.html'
        if not path.exists():
            raise CommandError(f'{path} not found')
        result = adapt(path.read_text(), lang=packet['site']['default_language'], languages=packet['site']['languages'],
                       image_map=packet['images']['map'], cta_texts=cta_texts_from(packet),
                       contact_phone=packet['facts'].get('phone', ''))
        report = result.as_report()
        report['key'] = key
        if not result.ok:
            self.stdout.write(json.dumps(report, ensure_ascii=False))
            raise SystemExit(1)
        report.update(import_result(result, packet=packet, set_home=True, change_summary=f'Promote concept {key}'))

        index_path = concepts_dir / 'concepts.json'
        if index_path.exists():
            index = json.loads(index_path.read_text())
            for entry in index:
                if entry['key'] == key:
                    entry['status'] = 'shipped'
                elif entry.get('status') == 'shipped':
                    entry['status'] = 'rejected'
            index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2))
        Ledger().mark_shipped(packet['site']['slug'], key)

        report['published'] = False
        if opts['publish']:
            if subprocess.run(['railway', 'status'], capture_output=True).returncode == 0:
                subprocess.run(PUBLISH_CMD, shell=True, check=True)
                report['published'] = True
            else:
                report['publish_hint'] = 'site is not linked to Railway — run /deploy-site-railway first'
        self.stdout.write(json.dumps(report, ensure_ascii=False))
```

- [ ] **Step 4: Run the tests**

Run: `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py test djangopress.core.tests.test_build_promote -v 1 2>&1 | tail -5`
Expected: `Ran 2 tests … OK`

- [ ] **Step 5: Commit**

```bash
cd /Users/antoniomarante/Documents/djangopress-sites/djangopress
git add src/djangopress/core/management/commands/promote_concept.py src/djangopress/core/tests/test_build_promote.py
git commit -m "feat(build): promote_concept command"
```

---

### Task 10: Prompt templates and `build_prompt`

**Files:**
- Create: `src/djangopress/skills/build-site/prompts/director.md`
- Create: `src/djangopress/skills/build-site/prompts/builder.md`
- Create: `src/djangopress/core/build/prompts.py`
- Create: `src/djangopress/core/management/commands/build_prompt.py`
- Test: `src/djangopress/core/tests/test_build_prompts.py`

**Interfaces:**
- Consumes: packet, `Ledger`, `format_entries`, `parse_brief`.
- Produces: `registers_for(n) -> list[(label, register)]`, `fill_director(packet, ledger_text, n) -> str`, `fill_builder(packet, brief_text, output_path) -> str`, `upsert_concept_index(index_path, key, brief_text)`; command `build_prompt director [--concepts N]` → `docs/concepts/prompts/director.md`; `build_prompt builder <k>` → `docs/concepts/prompts/builder-<k>.md` and a `concepts.json` entry. Tokens in the templates are `[[NAME]]` (double brackets, so `bg-[#…]` and `[N]` in prose never collide).

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for prompt filling and build_prompt (Task 10)."""

import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from djangopress.core.build.prompts import fill_builder, fill_director, registers_for, upsert_concept_index
from djangopress.core.tests.test_build_importer import PACKET
from djangopress.core.tests.test_build_ledger import BRIEF


class RegistersTest(SimpleTestCase):

    def test_three(self):
        self.assertEqual(registers_for(3), [('A', 'commercially safe'), ('B', 'distinctive contemporary'), ('C', 'strongly creative')])

    def test_six(self):
        self.assertEqual([r for _, r in registers_for(6)],
                         ['commercially safe', 'distinctive contemporary', 'distinctive contemporary',
                          'strongly creative', 'strongly creative', 'experimental'])


class FillTest(SimpleTestCase):

    def test_director(self):
        text = fill_director(PACKET, 'PREVIOUS DNA HERE', 3)
        self.assertIn('hospitality, restaurants and premium consumer brands', text)
        self.assertIn('Generate: 3 concepts', text)
        self.assertIn('A commercially safe', text)
        self.assertIn('PREVIOUS DNA HERE', text)
        self.assertIn('editorial', text)
        self.assertIn('Cozinha de autor algarvia.', text)
        self.assertNotIn('+351 289 000 000', text)   # the director never sees facts
        self.assertNotIn('[[', text)

    def test_builder(self):
        text = fill_builder(PACKET, BRIEF, 'docs/concepts/concept-b.html')
        self.assertIn('docs/concepts/concept-b.html', text)
        self.assertIn('Boarding Pass', text)
        self.assertIn('REQUIRED', text)
        self.assertIn('Reservar mesa → /reservas/', text)
        self.assertIn('Couvert — 3.30', text)
        self.assertIn('https://example.com/dish.jpg', text)
        self.assertIn('+351 289 000 000', text)
        self.assertIn('Português', text)
        self.assertNotIn('[[', text)


class IndexTest(SimpleTestCase):

    def test_upsert(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'concepts.json'
            upsert_concept_index(p, 'b', BRIEF)
            upsert_concept_index(p, 'b', BRIEF)
            upsert_concept_index(p, 'a', BRIEF.replace('Boarding Pass', 'Quiet Room'))
            rows = json.loads(p.read_text())
        self.assertEqual([(r['key'], r['name'], r['status']) for r in rows], [('a', 'Quiet Room', 'pending'), ('b', 'Boarding Pass', 'pending')])
        self.assertEqual(rows[1]['file'], 'concept-b.html')


class CommandTest(TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'docs' / 'concepts').mkdir(parents=True)
        (self.root / 'docs' / 'build-packet.json').write_text(json.dumps(PACKET))
        (self.root / 'docs' / 'concepts' / 'brief-b.md').write_text(BRIEF)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cmd(self, *args):
        out = StringIO()
        with patch('djangopress.core.management.commands.build_prompt.Path.cwd', return_value=self.root), \
             patch('djangopress.core.management.commands.build_prompt.Ledger') as L:
            L.return_value.read.return_value = []
            call_command('build_prompt', *args, '--packet', str(self.root / 'docs' / 'build-packet.json'), stdout=out)
        return json.loads(out.getvalue())

    def test_director_written(self):
        rep = self.run_cmd('director', '--concepts', '3')
        p = self.root / 'docs' / 'concepts' / 'prompts' / 'director.md'
        self.assertEqual(rep['prompt'], str(p))
        self.assertIn('none yet', p.read_text())

    def test_builder_written_and_indexed(self):
        rep = self.run_cmd('builder', 'b')
        p = self.root / 'docs' / 'concepts' / 'prompts' / 'builder-b.md'
        self.assertEqual(rep['prompt'], str(p))
        self.assertEqual(rep['output'], 'docs/concepts/concept-b.html')
        self.assertIn('Boarding Pass', p.read_text())
        rows = json.loads((self.root / 'docs' / 'concepts' / 'concepts.json').read_text())
        self.assertEqual(rows[0]['key'], 'b')
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py test djangopress.core.tests.test_build_prompts -v 1 2>&1 | tail -5`
Expected: `ModuleNotFoundError: No module named 'djangopress.core.build.prompts'`

- [ ] **Step 3: Write `prompts/director.md`**

```markdown
You are a senior creative director specializing in [[SPECIALIZATION]].

Your task is NOT to design the website yet.
Your task is to generate radically distinct ART DIRECTIONS for the same brief.

==================================================
BRIEF
==================================================

[[BRIEF]]

==================================================
DESIGN CONSTRAINTS (every concept must respect these)
==================================================

[[DESIGN_CONSTRAINTS]]

==================================================
NUMBER OF CONCEPTS
==================================================

Generate: [[N]] concepts, labelled [[LABELS]].
Register per label: [[REGISTERS]].
Every concept must still be usable as a real website for this business.

==================================================
CORE OBJECTIVE
==================================================

Every concept must be appropriate for the same business, but must feel as though it was
created by a different high-level creative studio. Do not generate minor variations of the
same aesthetic. Do not simply change colors, fonts or the hero image. The underlying visual
system must change.

==================================================
DESIGN DNA
==================================================

For each concept independently define:
1. DESIGN MOVEMENT  2. VISUAL PERSONALITY  3. LAYOUT GRAMMAR  4. HERO ARCHITECTURE
5. TYPOGRAPHIC SYSTEM  6. COLOR LOGIC  7. PHOTOGRAPHY STYLE  8. IMAGE CROPPING LANGUAGE
9. GRAPHIC DEVICE  10. SECTION TRANSITION LANGUAGE  11. GEOMETRY  12. INFORMATION DENSITY
13. NAVIGATION STYLE  14. PRIMARY CTA STYLE  15. MOTION / INTERACTION PERSONALITY
16. MOBILE DESIGN BEHAVIOUR

==================================================
DIVERSITY REQUIREMENT
==================================================

The concepts must have high visual distance from one another. For every pair of concepts,
change at least 7 of the 16 Design DNA dimensions. Never allow two concepts to share all of:
same hero architecture, same layout grammar, same typography class, same dominant color
logic, same graphic device. If two concepts begin to feel visually similar, redesign one
before returning the result.

==================================================
STYLE FAMILY ROTATION
==================================================

Explore different families where appropriate: [[FAMILIES]].
Do not use all of these. Select combinations that make sense for this business.

==================================================
AVOID GENERIC AI DESIGN
==================================================

Avoid repeating common AI-generated landing page patterns: text left / image right hero,
floating glass card over hero, endless rounded cards, identical 3-column grids,
gradient-heavy backgrounds, generic luxury black + gold, SaaS-style feature cards,
excessive pills, excessive shadows, identical centered headings, repeating alternating
text/image sections. Use these only when clearly justified by the concept.

==================================================
PREVIOUSLY USED DESIGN DNA
==================================================

The following concepts have already been generated for other sites in this vertical:

[[LEDGER]]

Do not recreate them. Avoid their defining hero composition, typography combination,
layout grammar, graphic motif, color logic and section rhythm. A new concept may reuse an
individual element, but not the overall design system.

==================================================
BUSINESS-SPECIFIC THINKING
==================================================

Before creating each concept, identify one specific aspect of the business that becomes
the creative starting point (cuisine, founder, geography, architecture, history,
ingredients, technique, cultural references, format, local environment, customer
experience, …). Do not use the same starting point twice unless the resulting visual
concept is radically different.

==================================================
OUTPUT FORMAT
==================================================

Return exactly [[N]] concepts. Delimit each with a line `===== CONCEPT <LABEL> =====`
and inside it write, in this order:

CONCEPT NAME:
REGISTER: safe | distinctive | creative | experimental
CREATIVE PREMISE: one concise paragraph.
BRAND IDEA: the business characteristic that inspired the concept.
DESIGN DNA:
- Movement:
- Personality:
- Layout grammar:
- Hero:
- Typography:
- Color:
- Photography:
- Cropping:
- Graphic device:
- Section transitions:
- Geometry:
- Density:
- Navigation:
- CTA:
- Motion:
- Mobile behaviour:
HERO DESCRIPTION: exactly how the first viewport looks.
PAGE RHYTHM: how the visual composition evolves down the homepage, and in which order the
required content items appear (name them by their ids from the brief).
SIGNATURE MOMENT: one memorable section or interaction unique to this concept.
WHY IT FITS: maximum 3 sentences.
AVOID: 3 design choices that would weaken this particular concept.

==================================================
FINAL DIVERSITY CHECK
==================================================

Before outputting, compare all concepts internally. If any two could plausibly be variants
of the same template, redesign one. Do not output that internal analysis.
```

- [ ] **Step 4: Write `prompts/builder.md`**

```markdown
You are building the complete home page of a real website as ONE standalone HTML document.
Write it to [[OUTPUT_PATH]] and report only that path.

==================================================
THE DESIGN (follow exactly)
==================================================

[[DESIGN]]

==================================================
THE CONTENT (facts — never invent, never alter)
==================================================

Language of all text: [[LANGUAGE_NAME]].
Site name: [[SITE_NAME]].

[[CONTENT]]

Facts:
[[FACTS]]

Header must provide: [[HEADER]]
Footer must provide: [[FOOTER]]

Every item marked REQUIRED must appear on the page, verbatim where it is a name, price,
number, address, label or link target. You decide where and how; the design decides the
order. Do not invent prices, addresses, awards, reviews, dish names or phone numbers.

==================================================
IMAGES
==================================================

Available photos (use the URL as src; never render wider than the width limit):
[[IMAGES]]

For any image slot without a photo, use
  <img src="https://placehold.co/1200x800?text=Label" data-image-name="<ascii-key>"
       data-image-prompt="<one-line description of the photo needed>" alt="…">
Never use any other external image URL.

==================================================
DOCUMENT CONTRACT (the importer relies on this)
==================================================

- A complete document: <!DOCTYPE html> … </html>. It must be finished; end with </html>.
- <head>: <title>, <meta name="description">, <script src="https://cdn.tailwindcss.com"></script>,
  one <script> that sets tailwind.config, one <style> block, Google Fonts <link> tags.
  Optional: <script src="https://unpkg.com/lucide@latest"></script>.
- <body>: exactly one <header>, one <main>, one <footer>, then at most one <script> block.
- Inside <main>, only <section> elements, each with an English id in lowercase-hyphen form
  (id="hero", id="chefs-table"). Nothing outside a <section>.
- Inside <header>, one <nav>; place <div data-slot="language-switcher"></div> where the
  language switcher goes. Mobile menu with Alpine.js (x-data / x-show / @click).
- Internal links: href="#section-id" for anchors, href="/reservas/" for pages — no language
  prefix, the importer adds it. External links, mailto:, tel: as normal.
- Tailwind utility classes and the tailwind.config theme only; arbitrary values (bg-[#…])
  are fine. No <style> outside <head>. No inline style="" except for background-image.
- Do not use {{ or {% anywhere.
- Decorative overlays with no text (gradients, tints) get class pointer-events-none.
- An image repeated for a marquee/loop: the copies get aria-hidden="true" alt="".
- Editable text lives in h1–h6, p, span, a, li, td, th, label, button, blockquote.
- Mobile-first; every section must work at 390px with no horizontal overflow.
- Real text only, no lorem ipsum, no template variables.
- Everything is visible without JavaScript and without scrolling: never hide content behind a
  scroll reveal (no opacity-0 / translate + x-intersect / IntersectionObserver reveals).
  Motion may move things; it never hides them. Counters show their final number in the HTML.
- Header anchor links point to your own English section ids (href="#services"), whatever the
  label's language.

==================================================
AVOID GENERIC AI DESIGN
==================================================

Avoid repeating common AI-generated landing page patterns: text left / image right hero,
floating glass card over hero, endless rounded cards, identical 3-column grids,
gradient-heavy backgrounds, generic luxury black + gold, SaaS-style feature cards,
excessive pills, excessive shadows, identical centered headings, repeating alternating
text/image sections. Use these only when clearly justified by the concept.
Also avoid the three items under this concept's own AVOID.
```

- [ ] **Step 5: Write `prompts.py`**

```python
"""Fill the director and builder prompt templates from the build packet (spec §6)."""

import json
from pathlib import Path

import djangopress

from djangopress.core.build.ledger import parse_brief

PROMPTS_DIR = Path(djangopress.__file__).parent / 'skills' / 'build-site' / 'prompts'
LABELS = 'ABCDEF'


def registers_for(n):
    if n == 3:
        regs = ['commercially safe', 'distinctive contemporary', 'strongly creative']
    elif n == 6:
        regs = ['commercially safe', 'distinctive contemporary', 'distinctive contemporary',
                'strongly creative', 'strongly creative', 'experimental']
    else:
        regs = ['commercially safe'] + ['distinctive contemporary' if i % 2 else 'strongly creative' for i in range(1, n - 1)]
        regs.append('experimental' if n >= 5 else 'strongly creative')
    return list(zip(LABELS[:n], regs[:n]))


def _fill(template, values):
    text = template
    for key, val in values.items():
        text = text.replace(f'[[{key}]]', str(val))
    return text


def _content_lines(packet):
    lines = []
    for page, groups in packet['content'].items():
        lines.append(f'Page: {page}')
        for flag, items in (('REQUIRED', groups['required']), ('optional', groups['optional'])):
            for item in items:
                line = f"- [{flag}] {item['id']} {item['kind']}: {item['text']}"
                if item.get('keywords'):
                    line += f" (keywords: {', '.join(item['keywords'])})"
                if item.get('href'):
                    line = f"- [{flag}] {item['id']} {item['kind']}: {item['text']} → {item['href']}"
                lines.append(line)
                for entry in item.get('items', []):
                    lines.append(f"    · {entry['name']} — {entry['price']} ({entry['category']})")
    return '\n'.join(lines)


def _facts_lines(packet):
    f = packet['facts']
    lines = [f"- Phone: {f.get('phone', '')}", f"- Email: {f.get('email', '')}", f"- Address: {f.get('address', '')}"]
    if f.get('maps_url'):
        lines.append(f"- Google Maps: {f['maps_url']}")
    for h in f.get('hours', []):
        lines.append(f'- Hours: {h}')
    for k, v in f.get('social', {}).items():
        lines.append(f'- {k.capitalize()}: {v}')
    return '\n'.join(lines)


def _images_lines(packet):
    rows = [f"- {k} — {v['url']} — max width {v.get('width') or 'unknown'}px — {v.get('alt', '')}" for k, v in packet['images']['map'].items()]
    return '\n'.join(rows) if rows else '(none — use placeholders everywhere)'


def _constraints_text(packet):
    c = packet['design_constraints']
    colors = ', '.join(c.get('brand_colors') or []) or 'none — choose freely'
    widths = ', '.join(f'{k} {v}px' for k, v in (c.get('image_max_widths') or {}).items()) or 'none stated'
    return '\n'.join([
        f'Brand colors (must appear, may be used sparingly): {colors}',
        f"Logo: {c.get('logo') or 'none'}",
        f"Avoid: {'; '.join(c.get('avoid') or []) or 'nothing specific'}",
        f"References (context only, never copy): {', '.join(c.get('references') or []) or 'none'}",
        f'Image constraints: {widths}',
    ])


def fill_director(packet, ledger_text, n):
    regs = registers_for(n)
    brief = '\n\n'.join([
        packet['business']['prose'],
        f"Audience and tone: {packet['business'].get('audience', '') or packet['business']['positioning']}",
        'Content the page must carry (ids are referenced in PAGE RHYTHM):',
        '\n'.join(f"- {i['id']} {i['kind']}: {i['text']}" for g in packet['content'].values() for i in g['required']),
        f"Header: {packet.get('header') or 'logo, links, one CTA, language switcher'}",
        f"Footer: {packet.get('footer') or 'contact, hours, social, privacy link, copyright'}",
    ])
    return _fill((PROMPTS_DIR / 'director.md').read_text(), {
        'SPECIALIZATION': packet['business']['specialization'], 'BRIEF': brief,
        'DESIGN_CONSTRAINTS': _constraints_text(packet), 'N': n,
        'LABELS': ', '.join(l for l, _ in regs), 'REGISTERS': ' · '.join(f'{l} {r}' for l, r in regs),
        'FAMILIES': ', '.join(packet['families']), 'LEDGER': ledger_text or 'none yet',
    })


def fill_builder(packet, brief_text, output_path):
    return _fill((PROMPTS_DIR / 'builder.md').read_text(), {
        'OUTPUT_PATH': output_path, 'DESIGN': brief_text.strip(),
        'LANGUAGE_NAME': packet['site']['default_language_name'], 'SITE_NAME': packet['site']['name'],
        'CONTENT': _content_lines(packet), 'FACTS': _facts_lines(packet),
        'HEADER': packet.get('header') or 'logo, links, one CTA, language switcher',
        'FOOTER': packet.get('footer') or 'contact, hours, social, privacy link, copyright',
        'IMAGES': _images_lines(packet),
    })


def upsert_concept_index(index_path, key, brief_text):
    index_path = Path(index_path)
    rows = json.loads(index_path.read_text()) if index_path.exists() else []
    b = parse_brief(brief_text)
    entry = {'key': key, 'name': b['name'], 'register': b['register'], 'premise': b['premise'],
             'file': f'concept-{key}.html', 'status': 'pending'}
    rows = [r for r in rows if r['key'] != key] + [entry]
    rows.sort(key=lambda r: r['key'])
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    return entry
```

- [ ] **Step 6: Write the command**

```python
"""build_prompt — write the filled director or builder prompt to docs/concepts/prompts/."""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from djangopress.core.build.ledger import Ledger, format_entries
from djangopress.core.build.prompts import fill_builder, fill_director, upsert_concept_index


class Command(BaseCommand):
    help = 'Fill a prompt template: build_prompt director [--concepts N] | build_prompt builder <k>'

    def add_arguments(self, parser):
        parser.add_argument('kind', choices=['director', 'builder'])
        parser.add_argument('key', nargs='?', default='')
        parser.add_argument('--concepts', type=int, default=3)
        parser.add_argument('--packet', default='docs/build-packet.json')

    def handle(self, *args, **opts):
        root = Path.cwd()
        packet = json.loads(Path(opts['packet']).read_text())
        prompts = root / 'docs' / 'concepts' / 'prompts'
        prompts.mkdir(parents=True, exist_ok=True)
        if opts['kind'] == 'director':
            n = opts['concepts']
            if not 1 <= n <= 6:
                raise CommandError('--concepts must be between 1 and 6')
            ledger = format_entries(Ledger().read(vertical=packet['business']['type']))
            out = prompts / 'director.md'
            out.write_text(fill_director(packet, ledger, n))
            self.stdout.write(json.dumps({'prompt': str(out), 'concepts': n}))
            return
        key = opts['key']
        if not key:
            raise CommandError('builder needs a concept key')
        brief = root / 'docs' / 'concepts' / f'brief-{key}.md'
        if not brief.exists():
            raise CommandError(f'{brief} not found — write the director output there first')
        output = f'docs/concepts/concept-{key}.html'
        out = prompts / f'builder-{key}.md'
        out.write_text(fill_builder(packet, brief.read_text(), output))
        entry = upsert_concept_index(root / 'docs' / 'concepts' / 'concepts.json', key, brief.read_text())
        self.stdout.write(json.dumps({'prompt': str(out), 'output': output, 'concept': entry}, ensure_ascii=False))
```

- [ ] **Step 7: Run the tests**

Run: `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py test djangopress.core.tests.test_build_prompts -v 1 2>&1 | tail -5`
Expected: `Ran 7 tests … OK`

- [ ] **Step 8: Commit**

```bash
cd /Users/antoniomarante/Documents/djangopress-sites/djangopress
git add src/djangopress/skills/build-site/prompts/director.md src/djangopress/skills/build-site/prompts/builder.md src/djangopress/core/build/prompts.py src/djangopress/core/management/commands/build_prompt.py src/djangopress/core/tests/test_build_prompts.py
git commit -m "feat(build): director and builder prompt templates with build_prompt"
```

---

### Task 11: The `build-site` skill

**Files:**
- Create: `src/djangopress/skills/build-site/SKILL.md`

**Interfaces:**
- Consumes: every command from Tasks 2–10.
- Produces: the operator-facing `/build-site` skill (§11.1). No tests; Task 13 exercises it.

- [ ] **Step 1: Write the skill, in one `Write`**

```markdown
---
name: build-site
description: Fast, unattended build of a one-page DjangoPress site from a content-only briefing — three complete design concepts built in parallel, one imported through the deterministic adapter, verified by check_site + a layout probe + one look at the mobile screenshot, then published. Supervised mode stops once so the operator picks a concept. Never asks questions.
argument-hint: briefings/<slug>.md [supervised] [concepts N] | briefings/<slug>.md pick <k> [notes]
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, Agent
---

# Build a site from three concepts

`$ARGUMENTS` = `<briefing> [supervised] [concepts N]`, or `<briefing> pick <k> [notes]` to resume a
supervised run. Default: unattended, 3 concepts. All commands run through the site venv:
`.venv/bin/python manage.py …`. **Never call `AskUserQuestion`.** Never edit the briefing.

Two rules. **Form from the concept, facts from the briefing**: builders take every name,
price, number and link from the packet, never from imagination. **Deterministic steps are
commands**: you never write settings, pages or menus by hand — `import_concept` does.

Budget: the whole run is ~12 of your turns. Do not add exploratory turns; every step below
names its command.

## Turn 1 — Prepare

```bash
.venv/bin/python manage.py build_prepare <briefing>
```

Stop and print the command's message if it fails (open questions, malformed content line).
Read `docs/build-packet.json` once; you will refer to `site.slug`, `site.default_language`,
`business.type` and `content.home.required` below.

## Turn 2 — Three concept briefs

```bash
.venv/bin/python manage.py build_prompt director --concepts <N>
```

Read `docs/concepts/prompts/director.md` and **answer it yourself in this turn** — you are the
creative director. Split your answer on the `===== CONCEPT <LABEL> =====` lines and write each
block to `docs/concepts/brief-<k>.md` (`k` = label in lowercase: `a`, `b`, `c`, …). Then, for each:

```bash
.venv/bin/python manage.py build_prompt builder <k>
```

## Turn 3 — Three sites in parallel

Dispatch one `Agent` (general-purpose) per concept **in a single message**. Each agent's whole
prompt is the content of `docs/concepts/prompts/builder-<k>.md` plus this line:

> Write the complete document with the Write tool to the OUTPUT path in one call. Do not run
> any command, do not read other files, do not stop before `</html>`. Report only the path.

Wait for all reports.

## Turn 4 — Screen

```bash
.venv/bin/python manage.py build_verify --files docs/concepts/concept-*.html
```

Read `docs/concepts/screen.json`. A concept with `hard_errors` (truncated, malformed) is
rebuilt **once**: dispatch its agent again with the same builder prompt plus
`The previous attempt stopped at <last section id>; the document must be complete and end with </html>.`,
then re-run the screening line. A second failure leaves that concept out.

## Turn 5 — Pick

**Supervised** (`supervised` in `$ARGUMENTS`): print one line per concept —
`<k> · <name> · <register> · <premise> · <clean|defects: n> · docs/concepts/concept-<k>.html` —
then `open docs/concepts/concept-*.html` and stop with:

```
Pick with: /build-site <briefing> pick <k> [what to change]
```

**Resuming with `pick <k> [notes]`**: if notes were given, edit `docs/concepts/concept-<k>.html`
per the notes in one pass (the builder's DOCUMENT CONTRACT still applies; facts unchanged), then
re-run the screening line for that file. Continue with Turn 6.

**Unattended**: `k` = the first concept with `"clean": true` in the order **b, a, c, d, e, f**.
If none is clean, `k = b` and the fix round below is mandatory.

## Turn 6 — Import

```bash
.venv/bin/python manage.py import_concept docs/concepts/concept-<k>.html --home
.venv/bin/python manage.py import_concept docs/concepts/concept-<j>.html --as-page homepage-v2   # every other concept, in key order: v2, v3, …
```

Exit 1 means adapter errors: read the JSON `errors`, fix the file (not the database), re-run. The
extra pages stay out of the menu; they render inside the shipped concept's header and footer.

## Turn 7 — Verify

```bash
.venv/bin/python manage.py build_verify
```

Read `docs/verify.json`: `check_site` (non-residue failures), `content_missing`, `probe.defects`.

## Turn 8 — One fix round

Read `docs/screenshots/home-390.png` with the Read tool. One question only: *does any section
look broken, or outside this concept's direction?* Combine what you see with `docs/verify.json`
and apply every fix by editing `docs/concepts/concept-<k>.html` — never the database — then:

```bash
.venv/bin/python manage.py import_concept docs/concepts/concept-<k>.html --home
.venv/bin/python manage.py build_verify
```

**One round.** Whatever remains goes to the report as open items.

## Turn 9 — Report, ledger, commit

Write `docs/build-report.md`:

```markdown
# <Site> — Build Report (<date>)

## Result
Shipped: concept <k> — <name> (<register>). check_site: <OK | n non-residue failures>. Probe: <n defects>. Content contract: <OK | n missing>.
Other concepts, live on this site: /<lang>/homepage-v2/ — <name> · /<lang>/homepage-v3/ — <name>   (files in docs/concepts/)

## Assumptions
- <where the briefing was silent, one line each>

## Open items
- <every remaining verify.json line and screenshot finding, one per line>
- <placeholder images: count, from check_site residue>

## Timing
prepare <s> · briefs <s> · builds <s> · screen <s> · import+verify <s> · fix <s>

## Next
- Switch concept: .venv/bin/python manage.py promote_concept <k> --publish
- Refine: /edit-site <what to change>
- Translate (after sign-off): /generate-site <briefing>
```

Then, for every concept, and `--shipped` only for `<k>`:

```bash
.venv/bin/python manage.py concept_ledger --append docs/concepts/brief-<k>.md --site <site.slug> --key <k> --vertical <business.type> [--shipped]
git add db.sqlite3 docs/ && git commit -m "Build <site> from concept <k> (<name>)"
```

No `Co-Authored-By` lines.

## Turn 10 — Publish

```bash
railway status >/dev/null 2>&1 && bash scripts/sync-to-prod.sh && railway redeploy -y
```

If `railway status` fails, print `Not on Railway yet: run /deploy-site-railway` instead. Print
the live URL from `railway domain` (or the `.env` `RAILWAY_URL`), the report's Result section,
and stop.

## Error handling

- A command exits non-zero: read its JSON, fix the named file or line, retry once, then record
  the failure under Open items and continue.
- Playwright missing (`build_verify` exit 2): record "layout probe skipped" and continue; the
  `check_site` gate still applies.
- An agent reports without writing its file: dispatch it once more; then continue without that
  concept.
- Anything else: record and continue. The run must end with a report even when incomplete.
```

- [ ] **Step 2: Confirm the skill is visible in a child site**

Run: `cd /Users/antoniomarante/Documents/djangopress-sites/quer-pintar-a-sua-casa && .venv/bin/python manage.py sync_skills --clean 2>&1 | tail -3 && ls -la .claude/skills/ | grep build-site`
Expected: a `build-site` symlink pointing into the engine checkout.

- [ ] **Step 3: Commit**

```bash
cd /Users/antoniomarante/Documents/djangopress-sites/djangopress
git add src/djangopress/skills/build-site/SKILL.md
git commit -m "feat(skills): build-site — three concepts, adapter import, probe verify, publish"
```

---

### Task 12: `create-briefing` writes the new shape; docs point at the fast path

**Files:**
- Modify: `src/djangopress/skills/create-briefing/SKILL.md` (Phase 2 rules, question list, Phase 3)
- Modify: `src/djangopress/skills/generate-site/SKILL.md` (one note under the title)
- Modify: `/Users/antoniomarante/Documents/djangopress-sites/djangopress-manager/CLAUDE.md` (skills table + Typical Workflows) — separate commit in the manager repo

- [ ] **Step 1: Edit `create-briefing/SKILL.md` — Phase 2 draft rules**

Replace the two bullets

```
- **Pages**: sections in order per page, with the CTA. For a one-pager, list the anchor sections.
- **Design Preferences**: a full proposal. Derive the palette from the business and the place, not from the old site's colors unless they are a brand asset. Name the type pair. State the layout signature in one sentence. Fill **Avoid** with what the direct competition does (look at two or three competitors' sites in the same street, marina or niche).
```

with

```
- **Pages**: one entry per page with its purpose and meta title/description. Do **not** list sections in order — the design concept decides grouping and sequence.
- **Content**: per page, a flat list of what must be communicated. Mark every fact, name, price, award, label and CTA `(required)`; give messages 3–5 `keywords:`; give CTAs `→ /href/`. Menu items come from `briefings/<slug>-menu.json` when it exists — reference it in the Menu item. This list is the content contract the build verifies.
- **Design Constraints**: only what every concept must respect. Brand colors **only** if they are a brand asset (logo, existing identity) — otherwise `none`. Fill **Avoid** with what the direct competition does (look at two or three competitors' sites in the same street, marina or niche). References are context, never models. State the image constraints line from the largest widths. Never propose a palette, type pair, layout signature or motif here.
```

- [ ] **Step 2: Edit `create-briefing/SKILL.md` — question list**

Replace `- A design direction choice when two are plausible (offer both, propose one)` with
`- Any non-negotiable colours or fonts (default: none — the concepts choose)`.

- [ ] **Step 3: Edit `create-briefing/SKILL.md` — Phase 3 checks and next step**

Replace `Re-read the whole file once. Check: every `## ` section from the template is present; Design Preferences has every bullet filled; Pages describe sections, not pages; Domain equals `gcs_folder`.` with
`Re-read the whole file once. Check: every `## ` section from the template is present; Design Constraints is filled (brand colors may be `none`); every `## Content` line parses as `- (required)? Kind: text [— keywords: …] [→ /href/]`; Pages do not fix section order; Domain equals `gcs_folder`.`

Replace the block from `Show a short summary (pages, languages, design direction in one line, integrations) and offer the next step:` through `never directly from here.` with:

~~~~
Show a short summary (pages, languages, required content items, integrations) and offer the next step:

```
AskUserQuestion:
Question: "Briefing finalizado. Construir o site?"
Options:
- "Sim, supervisionado — /build-site briefings/<slug>.md supervised" (Recommended)
- "Sim, sem supervisão — /build-site briefings/<slug>.md"
- "Não — fico por aqui"
```

If yes, invoke the `build-site` skill with the chosen arguments. Non-interactively, print
`Next: /build-site briefings/<slug>.md supervised` and stop. The mockup path
(`/mockup-site master` → `/extract-design` → `/generate-site`) remains available for sites
where the client must approve a rendered look before any build.
~~~~

- [ ] **Step 4: Edit `generate-site/SKILL.md`**

After the line `# Site Build`, insert:

```
> **Fast path:** `/build-site briefings/<slug>.md` builds three HTML concepts in parallel and
> publishes one in minutes, without mockups. This skill is the mockup-first path for sites
> where the client approves a rendered look before the build, and it still owns the
> translation pass (Phase 9) for both paths.
```

- [ ] **Step 5: Update the manager's `CLAUDE.md`**

In the "DjangoPress Skills (available in child sites)" table, add a first row:

```
| **build-site** | `/build-site briefings/<slug>.md [supervised] [concepts N]` | Fast path: three HTML concepts in parallel, adapter import, probe verify, publish. Supervised stops once for the pick; `pick <k> [notes]` resumes. | `cd <site.path>` then invoke |
```

Replace the "**New site from scratch:**" list with:

```
**New site from scratch (fast path, default):**
1. `/create-briefing <url and/or document>` → research, one block of questions, content-only briefing
2. `/build-site briefings/<slug>.md supervised` → three concepts, pick one, verify, publish (unattended: drop `supervised`)
3. Review the live link; `manage.py promote_concept <k> --publish` to switch concept
4. `/edit-site` → interactive refinement
5. `/generate-site briefings/<slug>.md` → translation pass once design is signed off

**New site, mockup-first (flagship path):**
1. `/create-briefing …` 2. `/mockup-site master` → approve 3. `/mockup-site section next` 4. `/extract-design` 5. `/generate-site briefings/<slug>.md` 6. `/deploy-site-railway`
```

- [ ] **Step 6: Commit both repos**

```bash
cd /Users/antoniomarante/Documents/djangopress-sites/djangopress
git add src/djangopress/skills/create-briefing/SKILL.md src/djangopress/skills/generate-site/SKILL.md
git commit -m "docs(skills): create-briefing writes content-only briefings; generate-site points at the fast path"
cd /Users/antoniomarante/Documents/djangopress-sites/djangopress-manager
git add CLAUDE.md
git commit -m "docs: build-site fast path in the skills table and workflows"
```

---

### Task 13: Guided end-to-end run (operator present)

The only task that touches a real site directory: **`pwd-v2`**, the agency's own new site (not a client), scaffolded during the spike with its content-only briefing already in place. The operator picked concept C (Orçamento) in the spike; this run rebuilds through the real pipeline.

**Files:**
- Use: `/Users/antoniomarante/Documents/djangopress-sites/pwd-v2/` (exists) and `pwd-v2/briefings/pwd-v2.md` (exists)
- Modify: this plan (append `## Run results`)

- [ ] **Step 1: Reinstall the engine extra in pwd-v2 so the probe and the new skill are available**

```bash
cd /Users/antoniomarante/Documents/djangopress-sites/pwd-v2 && .venv/bin/pip install -q -e "/Users/antoniomarante/Documents/djangopress-sites/djangopress[build]" && .venv/bin/playwright install chromium 2>&1 | tail -1 && .venv/bin/python manage.py sync_skills --clean | tail -1 && .venv/bin/python manage.py build_prepare briefings/pwd-v2.md --no-download | head -c 300
```

- [ ] **Step 2: Supervised run**

In a Claude Code session opened in `pwd-v2/`:

```
/build-site briefings/pwd-v2.md supervised
```

Record: minutes per turn (from the report's Timing line), whether three tabs opened, whether the three concepts are visibly distinct and none hides content behind scroll reveals. Pick one with a note. Confirm the pipeline continues to the report without asking anything, that `/pt/homepage-v2/` and `/pt/homepage-v3/` render the other two concepts, and — if pwd-v2 is on Railway by then — that Turn 10 publishes with `railway redeploy -y` and how long it takes; otherwise confirm it prints `Not on Railway yet`.

- [ ] **Step 3: Unattended run on a fresh copy**

```bash
cd /Users/antoniomarante/Documents/djangopress-sites/djangopress && bash scripts/new_site.sh pwd-v2-unattended >/dev/null 2>&1 && cp pwd-v2/briefings/pwd-v2.md pwd-v2-unattended/briefings/pwd-v2-unattended.md
```

Then `/build-site briefings/pwd-v2-unattended.md` in that directory. Record the total wall clock from invocation to report, and the token usage from the three agent notifications.

- [ ] **Step 4: Promote**

```bash
cd /Users/antoniomarante/Documents/djangopress-sites/pwd-v2-unattended && .venv/bin/python manage.py promote_concept c && .venv/bin/python manage.py build_verify --no-screenshot | head -c 400
```

Confirm `concepts.json` shows `c` shipped and the dev server renders concept C at `http://localhost:8000/pt/`.

- [ ] **Step 6: Record and commit**

Append to this plan:

```markdown
## Run results (<date>)
- Supervised: <min> to the pick, <min> pick → report. Concepts distinct: <yes/no>. Open items: <n>.
- Unattended: <min> total, <tokens> across three builders. Shipped <k>. check_site non-residue failures: <n>.
- Promote: <s>. Probe available: <yes/no>.
```

```bash
cd /Users/antoniomarante/Documents/djangopress-sites/djangopress
git add docs/plans/2026-09-16-fast-site-generation-plan.md
git commit -m "docs: end-to-end run results for build-site"
```

`pwd-v2` is the agency's real new site and stays. `pwd-v2-unattended` is scratch; the operator deletes it when done, never a subagent.

---

## Self-review (done while writing)

**Spec coverage.** §4.1–4.2 briefing shape → Task 1 (+ Task 12 for the skill that writes it). §4.3 concept files → Tasks 10, 11. §4.4 packet → Task 2. §4.5 ledger → Task 3. §5 stage map → Task 11 turn by turn. §6 prompts → Task 10. §7 adapter (16 transforms) → Tasks 4–6 (transform 13 JSON-LD/meta and 14 menu live in Task 6; 15 save in Task 6; 16 report in Tasks 5–6). §8.1–8.4 verification and screening → Tasks 7, 8. §8.5 vision pass and §8.6 pick rule → Task 11 turns 5 and 8. §9 publish → Task 9 (`--publish`) and Task 11 turn 10; `railway redeploy -y` confirmed against the installed CLI. §10 command reference → Tasks 2, 3, 6, 8, 9 plus `build_prompt` (Task 10), an addition to the spec's list that removes fragile prompt-filling from the model. §11.2 `create-briefing` → Task 12. §11.3 legacy path → Task 12 note. §12 testing → every task. §14 spike → Task 0. §15 follow-ups are not in this plan by design.

**Deviations from the spec, deliberate.** (1) A sixth command, `build_prompt`, fills the templates deterministically. (2) The first section keeps the builder's own `id` when present; `hero` is forced only when the id is missing, so anchors written by the builder keep working. (3) `build_verify --files` runs the probe on the raw file and the content contract on the dry-run-adapted HTML, exactly as §8.4 (revised) says. (4) `build_prepare` registers inventory *example* URLs (one per audit group) because the audit table holds only those; the map also carries every pre-existing `SiteImage`.

**Type consistency.** `adapt(raw, *, lang, languages, image_map, cta_texts=(), contact_phone='')` is called with those keyword names in Tasks 6, 8, 9. `import_result(result, *, packet, set_home, change_summary)` is used identically in Tasks 6, 8, 9. `run_probe(url, widths, *, cta_texts, fonts, screenshot_path)` is patched under `djangopress.core.build.verify.run_probe` in Task 8 because `verify.py` imports the name. `Ledger().read(vertical=..., limit=...)` / `.append(entry)` / `.mark_shipped(site, key)` are used the same way in Tasks 3, 9, 10. Packet keys used everywhere: `site.slug/name/default_language/default_language_name/languages/lang_prefix`, `business.type/jsonld_type/specialization/positioning/prose/cuisine/price_range`, `families`, `facts.phone/email/address/maps_url/hours/social`, `content.<page>.required[].id/kind/text/keywords/href/items`, `images.strategy/map/constraints`, `design_constraints.*`, `header`, `footer`.
