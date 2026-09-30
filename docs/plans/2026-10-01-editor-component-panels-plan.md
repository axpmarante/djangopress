# Editor Component Panels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Selecting a slider, text slider or lightbox gallery in editor v2 shows one panel with thumbnails, drag-to-reorder, replace/add/remove, per-item text/alt/caption and slider settings, applied to the stored HTML of every language.

**Architecture:** Structural recognition in two mirrored modules — `editor_v2/components.py` (BeautifulSoup) and `editor_v2/static/editor_v2/js/lib/components.js` (live DOM) — kept in step by shared HTML fixtures. One endpoint `POST /editor-v2/api/component/` runs deterministic operations through the existing `_run_structural_verb` (checkpoint, all languages, drift skipping) and returns the component's new HTML, which the client swaps in place and remounts. New typed text is translated with the engine's `translate_html`.

**Tech Stack:** Django, BeautifulSoup (html.parser), vanilla ES modules (editor v2), Splide v4, playwright-cli for browser checks.

**Spec:** `docs/plans/2026-10-01-editor-component-panels-design.md`

## Global Constraints

- Repo `~/Documents/djangopress-sites/djangopress`, branch `feature/editor-component-panels` (already created, spec committed). Engine code under `src/djangopress/` — paths below are relative to it unless they start with `docs/`.
- Python tests run from a site with the editable engine: `cd ~/Documents/djangopress-sites/checkinfaro-v3 && .venv/bin/python manage.py test djangopress.editor_v2 2>&1 | tail -4`. macOS has no `timeout` binary.
- HTML per language stays the single source of truth. No new required attribute in site HTML; no block model.
- Every component operation goes through `_run_structural_verb` so it writes a `kind='checkpoint'` PageVersion (engine CLAUDE.md: "Editor operations must create a checkpoint … or they are not undoable"). No LLM call in structural operations except the translation of newly typed text / missing alts.
- Commit messages: conventional prefix, no `Co-Authored-By` line (engine CLAUDE.md). End each message with the line `Claude-Session: https://claude.ai/code/session_01WSpzVT1ezgnAA6UbDJmNtS`.
- Asset versions in `templates/base.html`: `editor.js?v=37`, `editor.css?v=23` (were 36 / 22).
- Recognition constants must match between Python and JS: `TEXT_SLIDE_MIN_CHARS = 40`; inline tags `strong em b i br span a small sup sub u mark`; skipped tags `img svg script style picture video iframe source br template`.
- UI copy is English, plain language (the editor's existing language).

## Review Focus

1. **Loop sliders with Splide clones** — the panel must list real slides only, in stored order. Pinned by the `loop_carousel` fixture (contains a pre-baked clone) in Task 1 (Python) and Task 6 (JS harness).
2. **A language whose copy drifted** (different item count) — it must be skipped and reported, never half-edited. Pinned in Task 4 `test_drifted_language_is_skipped`.
3. **Component HTML containing Django template tags** (`{{ }}` / `{% %}`) — the in-place swap would show raw tags; the client must reload instead. Pinned by `canSwapInPlace` in the Task 6 harness.
4. **Removing down to the minimum** (1 slide; 2 gallery items without the hint) — refused with a clear message, component stays recognisable. Pinned in Task 2 `test_remove_refuses_below_minimum` and Task 6 harness `minItems`.
5. **Translation unavailable** (no API key, provider down) — the new item is still added in every language with the source text and the response lists `untranslated_languages`. Pinned in Task 4 `test_add_text_item_translation_failure_keeps_source`.

---

## File Structure

| File | Responsibility |
|---|---|
| `editor_v2/components.py` (new) | Recognition (detect/find/items/fields), text read/write, the seven operations, `audit()` for check_site, `RUNTIME_CLASS_RE` |
| `editor_v2/component_translate.py` (new) | `translate_texts(texts, source, target)` over `ContentGenerationService.translate_html` |
| `editor_v2/component_views.py` (new) | `component_op` endpoint: argument validation, per-language values (alts, translations), response HTML |
| `editor_v2/api_views.py` | `_run_structural_verb` gains `pass_lang` / `only_lang`; per-language `alt`; runtime-class stripping |
| `editor_v2/urls.py` | route `api/component/` |
| `editor_v2/tests/fixtures/components/*.html` (new) | Shared recognition fixtures (Python tests + JS harness) |
| `editor_v2/tests/test_components.py`, `test_component_translate.py`, `test_component_api.py` (new) | Python tests |
| `editor_v2/tests/js/components_test.html` (new) | Browser harness for `components.js` |
| `editor_v2/static/editor_v2/js/lib/components.js` (new) | JS recognition + settings mapping |
| `editor_v2/static/editor_v2/js/modules/component-panel.js` (new) | The card UI and its operations |
| `editor_v2/static/editor_v2/js/lib/dom.js`, `lib/structural.js`, `modules/{sidebar,selection,images-panel,changes,history,image-picker}.js`, `editor.js`, `css/editor.css` | Integration and bug fixes |
| `templates/base.html`, `static/js/lightbox.js` | Keep Splide instances, lightbox edit-mode guard, asset versions |
| `core/management/commands/check_site.py`, `core/tests/test_check_site.py` | `components` check with warnings |
| `ai/utils/components/__init__.py`, skills, `CLAUDE.md` | Docs and prompt fixes |

---

### Task 1: Python recognition + shared fixtures

**Files:**
- Create: `editor_v2/components.py`
- Create: `editor_v2/tests/fixtures/components/{hero_fade,loop_carousel,testimonials,card_carousel,gallery_grid,gallery_wrapped,splide_lightbox,gallery_hint,not_component}.html`
- Test: `editor_v2/tests/test_components.py`

**Interfaces:**
- Produces: `KINDS`, `TEXT_SLIDE_MIN_CHARS`, `RUNTIME_CLASS_RE`, `detect(root) -> str|None`, `find_for(el) -> (root, kind)|None`, `find_component(soup, root_selector, kind) -> Tag|None`, `items(root, kind) -> list[Tag]`, `image_of(item) -> Tag|None`, `lightbox_link_of(el) -> Tag|None`, `text_leaves(item) -> list[Tag]`, `is_editable_leaf(el) -> bool`, `read_text(el) -> str`, `write_text(el, value)`, `min_items(root, kind) -> int`.

- [ ] **Step 1: Write the fixtures.** Each file is one `<section>` with expectations as `data-expect-*` attributes and one element marked `data-probe` (the element a user would click). Create them exactly:

`hero_fade.html`
```html
<section data-section="foto" id="foto" data-expect-kind="slider" data-expect-count="3" data-expect-texts="0" data-expect-editable="0" data-expect-image="1">
<div class="splide" data-splide='{"type":"fade","rewind":true,"autoplay":true,"interval":5000,"speed":1200,"arrows":true,"pagination":true,"arrowPath":"M15 6 L29 20 L15 34"}'>
<div class="splide__track"><ul class="splide__list">
<li class="splide__slide"><img data-probe src="https://example.com/a.jpg" alt="A" class="h-60 w-full"/></li>
<li class="splide__slide"><img src="https://example.com/b.jpg" alt="B" class="h-60 w-full"/></li>
<li class="splide__slide"><img src="https://example.com/c.jpg" alt="C" class="h-60 w-full"/></li>
</ul></div></div>
</section>
```

`loop_carousel.html` (first `li` is a pre-baked Splide clone that must be ignored)
```html
<section data-section="pratos" id="pratos" data-expect-kind="slider" data-expect-count="4" data-expect-texts="1" data-expect-editable="1" data-expect-image="1">
<div class="splide" data-splide='{"type":"loop","perPage":3,"gap":"1rem","breakpoints":{"1024":{"perPage":2},"768":{"perPage":1}}}'>
<div class="splide__track"><ul class="splide__list">
<li class="splide__slide splide__slide--clone"><img src="https://example.com/4.jpg" alt="Quatro"/><p>Quatro</p></li>
<li class="splide__slide"><img src="https://example.com/1.jpg" alt="Um"/><p>Um</p></li>
<li class="splide__slide"><img data-probe src="https://example.com/2.jpg" alt="Dois"/><p>Dois</p></li>
<li class="splide__slide"><img src="https://example.com/3.jpg" alt="Três"/><p>Três</p></li>
<li class="splide__slide"><img src="https://example.com/4.jpg" alt="Quatro"/><p>Quatro</p></li>
</ul></div></div>
</section>
```

`testimonials.html`
```html
<section data-section="testemunhos" id="testemunhos" data-expect-kind="text-slider" data-expect-count="3" data-expect-texts="2" data-expect-editable="2" data-expect-image="0">
<div class="fx-quote splide mt-10" data-splide='{"type":"fade","rewind":true,"autoplay":true,"interval":6000,"speed":900,"arrows":false,"pagination":true}'>
<div class="splide__track"><ul class="splide__list">
<li class="splide__slide pb-12"><blockquote class="text-2xl">“The best meal I have had in the Algarve, without any doubt at all!”</blockquote><p class="mt-6 uppercase">Travelmadame82 · Tripadvisor</p></li>
<li class="splide__slide pb-12"><blockquote data-probe class="text-2xl">“Best restaurant we've been to in Faro. The meal was a symphony.”</blockquote><p class="mt-6 uppercase">travbud1 · Tripadvisor</p></li>
<li class="splide__slide pb-12"><blockquote class="text-2xl">“A wonderful evening, attentive service and remarkable food.”</blockquote><p class="mt-6 uppercase">Ana · Google</p></li>
</ul></div></div>
</section>
```

`card_carousel.html` (image + formatted text: the `p` has a `<strong>`, so it is a read-only leaf)
```html
<section data-section="servicos" id="servicos" data-expect-kind="text-slider" data-expect-count="3" data-expect-texts="2" data-expect-editable="1" data-expect-image="1">
<div class="splide" data-splide='{"type":"slide","perPage":3}'>
<div class="splide__track"><ul class="splide__list">
<li class="splide__slide"><div class="card"><img src="https://example.com/s1.jpg" alt="S1"/><h3 data-probe>Jantares privados</h3><p>Uma sala reservada para <strong>grupos</strong> até vinte pessoas, com menu fechado.</p></div></li>
<li class="splide__slide"><div class="card"><img src="https://example.com/s2.jpg" alt="S2"/><h3>Eventos</h3><p>Casamentos pequenos e <strong>aniversários</strong> com a cozinha da casa e vinhos da região.</p></div></li>
<li class="splide__slide"><div class="card"><img src="https://example.com/s3.jpg" alt="S3"/><h3>Take-away</h3><p>Os pratos da carta para levar, <strong>embalados</strong> em vidro e prontos a aquecer.</p></div></li>
</ul></div></div>
</section>
```

`gallery_grid.html` (caption overlay `div > span` is a read-only leaf)
```html
<section data-section="galeria" id="galeria" data-expect-kind="gallery" data-expect-count="4" data-expect-texts="1" data-expect-editable="0" data-expect-image="1">
<div class="grid grid-cols-2 gap-4">
<a href="https://example.com/g1.jpg" data-lightbox="g" data-alt="Sala"><img data-probe src="https://example.com/g1.jpg" alt="Sala"/><div class="overlay"><span>Ver</span></div></a>
<a href="https://example.com/g2.jpg" data-lightbox="g" data-alt="Esplanada"><img src="https://example.com/g2.jpg" alt="Esplanada"/><div class="overlay"><span>Ver</span></div></a>
<a href="https://example.com/g3.jpg" data-lightbox="g" data-alt="Bar"><img src="https://example.com/g3.jpg" alt="Bar"/><div class="overlay"><span>Ver</span></div></a>
<a href="https://example.com/g4.jpg" data-lightbox="g" data-alt="Cozinha"><img src="https://example.com/g4.jpg" alt="Cozinha"/><div class="overlay"><span>Ver</span></div></a>
</div>
</section>
```

`gallery_wrapped.html`
```html
<section data-section="fotos" id="fotos" data-expect-kind="gallery" data-expect-count="3" data-expect-texts="0" data-expect-editable="0" data-expect-image="1">
<ul class="grid grid-cols-3">
<li><a href="https://example.com/w1.jpg" data-lightbox="w"><img src="https://example.com/w1.jpg" alt="W1"/></a></li>
<li><a data-probe href="https://example.com/w2.jpg" data-lightbox="w"><img src="https://example.com/w2.jpg" alt="W2"/></a></li>
<li><a href="https://example.com/w3.jpg" data-lightbox="w"><img src="https://example.com/w3.jpg" alt="W3"/></a></li>
</ul>
</section>
```

`splide_lightbox.html` (a slider whose slides hold lightbox links: the slider wins)
```html
<section data-section="quartos" id="quartos" data-expect-kind="slider" data-expect-count="3" data-expect-texts="1" data-expect-editable="1" data-expect-image="1">
<div class="splide" data-splide='{"type":"loop","perPage":2}'>
<div class="splide__track"><ul class="splide__list">
<li class="splide__slide"><a href="https://example.com/q1.jpg" data-lightbox="q"><img data-probe src="https://example.com/q1.jpg" alt="Q1"/></a><p>Duplo</p></li>
<li class="splide__slide"><a href="https://example.com/q2.jpg" data-lightbox="q"><img src="https://example.com/q2.jpg" alt="Q2"/></a><p>Suite</p></li>
<li class="splide__slide"><a href="https://example.com/q3.jpg" data-lightbox="q"><img src="https://example.com/q3.jpg" alt="Q3"/></a><p>Twin</p></li>
</ul></div></div>
</section>
```

`gallery_hint.html` (one item, but the hint makes it a gallery)
```html
<section data-section="mapa" id="mapa" data-expect-kind="gallery" data-expect-count="1" data-expect-texts="0" data-expect-editable="0" data-expect-image="1">
<div class="max-w-xl" data-media-collection="lightbox">
<a href="https://example.com/m.jpg" data-lightbox="m"><img data-probe src="https://example.com/m.jpg" alt="Mapa"/></a>
</div>
</section>
```

`not_component.html`
```html
<section data-section="sobre" id="sobre" data-expect-kind="none" data-expect-count="0" data-expect-texts="0" data-expect-editable="0" data-expect-image="0">
<div class="grid grid-cols-2">
<div><a href="https://example.com/x.jpg" data-lightbox="x"><img data-probe src="https://example.com/x.jpg" alt="X"/></a></div>
<div><p>Desde 2014 na baixa de Faro, com cozinha de mercado e vinhos do Algarve.</p></div>
</div>
</section>
```

- [ ] **Step 2: Write the failing tests** — `editor_v2/tests/test_components.py`:

```python
from pathlib import Path

from bs4 import BeautifulSoup
from django.test import SimpleTestCase

from djangopress.editor_v2 import components

FIXTURES = Path(__file__).parent / 'fixtures' / 'components'


def load(name):
    return BeautifulSoup((FIXTURES / f'{name}.html').read_text(), 'html.parser')


class FixtureRecognitionTest(SimpleTestCase):
    """Every fixture declares what the editor must recognise (shared with the JS harness)."""

    def test_fixtures(self):
        names = sorted(p.stem for p in FIXTURES.glob('*.html'))
        self.assertGreaterEqual(len(names), 9)
        for name in names:
            with self.subTest(fixture=name):
                soup = load(name)
                section = soup.find('section')
                found = components.find_for(soup.select_one('[data-probe]'))
                expect = section['data-expect-kind']
                if expect == 'none':
                    self.assertIsNone(found)
                    continue
                root, kind = found
                self.assertEqual(kind, expect)
                its = components.items(root, kind)
                self.assertEqual(len(its), int(section['data-expect-count']))
                leaves = components.text_leaves(its[0])
                self.assertEqual(len(leaves), int(section['data-expect-texts']))
                self.assertEqual(sum(components.is_editable_leaf(l) for l in leaves), int(section['data-expect-editable']))
                self.assertEqual(1 if components.image_of(its[0]) else 0, int(section['data-expect-image']))


class TextTest(SimpleTestCase):
    def test_read_text_collapses_source_whitespace_and_keeps_br(self):
        el = BeautifulSoup('<p>\n  Linha   um<br/>linha\n dois </p>', 'html.parser').p
        self.assertEqual(components.read_text(el), 'Linha um\nlinha dois')

    def test_write_text_turns_newlines_into_br(self):
        soup = BeautifulSoup('<p>old <br/>text</p>', 'html.parser')
        components.write_text(soup.p, 'Novo\ntexto')
        self.assertEqual(str(soup.p), '<p>Novo<br/>texto</p>')


class FindComponentTest(SimpleTestCase):
    def test_find_component_checks_kind(self):
        soup = load('hero_fade')
        sel = 'section[data-section="foto"] > div:nth-child(1)'
        self.assertIsNotNone(components.find_component(soup, sel, 'slider'))
        self.assertIsNone(components.find_component(soup, sel, 'gallery'))
        self.assertIsNone(components.find_component(soup, 'section[data-section="nope"] > div:nth-child(1)', 'slider'))

    def test_min_items(self):
        soup = load('gallery_grid')
        grid = soup.select_one('.grid')
        self.assertEqual(components.min_items(grid, 'gallery'), 2)
        hinted = load('gallery_hint').select_one('[data-media-collection]')
        self.assertEqual(components.min_items(hinted, 'gallery'), 1)
        self.assertEqual(components.min_items(load('hero_fade').select_one('.splide'), 'slider'), 1)

    def test_runtime_class_re(self):
        for c in ('is-active', 'is-visible', 'is-prev', 'is-next', 'splide--fade', 'splide__slide--clone', 'ev2-selected'):
            self.assertTrue(components.RUNTIME_CLASS_RE.match(c), c)
        for c in ('splide', 'splide__slide', 'is-large', 'pb-12'):
            self.assertFalse(components.RUNTIME_CLASS_RE.match(c), c)
```

- [ ] **Step 3: Run to verify failure**

Run: `cd ~/Documents/djangopress-sites/checkinfaro-v3 && .venv/bin/python manage.py test djangopress.editor_v2.tests.test_components 2>&1 | tail -4`
Expected: ERROR — `ImportError: cannot import name 'components'`.

- [ ] **Step 4: Implement** `editor_v2/components.py`:

```python
"""
Editable components — Splide sliders and lightbox galleries — recognised by
structure, and the deterministic operations the editor's component panel runs
on them. Mirror of static/editor_v2/js/lib/components.js: keep the detection
rules in step (shared fixtures in tests/fixtures/components/).
"""
import copy
import json
import re

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from djangopress.editor_v2.structure import strip_ids

KINDS = ('slider', 'text-slider', 'gallery')
TEXT_SLIDE_MIN_CHARS = 40
SKIP_TAGS = {'img', 'svg', 'script', 'style', 'picture', 'video', 'iframe', 'source', 'br', 'template'}
INLINE_TAGS = {'strong', 'em', 'b', 'i', 'br', 'span', 'a', 'small', 'sup', 'sub', 'u', 'mark'}
RUNTIME_INJECTED_CLASSES = {'splide__slide--clone', 'splide__arrows', 'splide__pagination', 'splide__sr'}
# Classes a runtime (Splide, the editor) toggles on live elements; never stored.
RUNTIME_CLASS_RE = re.compile(
    r'^(ev2-|is-(active|visible|prev|next|initialized|rendered|overflow|focus-in)$|splide--|splide__slide--clone$)'
)

_SCRATCH = BeautifulSoup('', 'html.parser')


def _classes(el):
    return el.get('class', []) if isinstance(el, Tag) else []


def _is_runtime(el):
    return bool(RUNTIME_INJECTED_CLASSES & set(_classes(el))) or el.get('data-editor-skip') == 'true'


def _children(el):
    return [c for c in el.find_all(True, recursive=False) if not _is_runtime(c)]


# --- text ------------------------------------------------------------------

def read_text(el):
    """Visible text with source whitespace collapsed; <br> becomes a newline."""
    parts = []

    def walk(node):
        for child in node.children:
            if isinstance(child, Comment):
                continue
            if isinstance(child, NavigableString):
                parts.append(re.sub(r'\s+', ' ', str(child)))
            elif isinstance(child, Tag):
                if child.name == 'br':
                    parts.append('\n')
                elif child.name not in ('script', 'style', 'template'):
                    walk(child)

    walk(el)
    return '\n'.join(line.strip() for line in ''.join(parts).split('\n')).strip()


def write_text(el, value):
    """Replace el's content with plain text; newlines become <br/>."""
    el.clear()
    for i, line in enumerate((value or '').split('\n')):
        if i:
            el.append(_SCRATCH.new_tag('br'))
        el.append(NavigableString(line))


def _is_leafy(el):
    return all(c.name in INLINE_TAGS for c in el.find_all(True, recursive=False))


def is_editable_leaf(el):
    """Only <br> children: the panel can rewrite it without losing formatting."""
    return all(c.name == 'br' for c in el.find_all(True, recursive=False))


def text_leaves(item):
    """Outermost elements holding only inline content and some text, in document order."""
    if _is_leafy(item) and read_text(item):
        return [item]
    out = []

    def walk(node):
        for child in node.find_all(True, recursive=False):
            if _is_runtime(child) or child.name in SKIP_TAGS or child.get('aria-hidden') == 'true':
                continue
            if _is_leafy(child):
                if read_text(child):
                    out.append(child)
            else:
                walk(child)

    walk(item)
    return out


# --- recognition -------------------------------------------------------------

def image_of(item):
    candidates = ([item] if item.name == 'img' else []) + item.find_all('img')
    for img in candidates:
        if img.get('aria-hidden') != 'true':
            return img
    return None


def lightbox_link_of(el):
    if el.name == 'a' and el.has_attr('data-lightbox'):
        return el
    links = el.select('a[data-lightbox]')
    return links[0] if len(links) == 1 else None


def splide_slides(root):
    lst = root.select_one('.splide__list')
    if lst is None:
        return []
    return [c for c in lst.find_all('li', recursive=False)
            if 'splide__slide' in _classes(c) and not _is_runtime(c)]


def gallery_items(root):
    return [c for c in _children(root) if lightbox_link_of(c) is not None]


def _is_image_slide(slide):
    return image_of(slide) is not None and len(read_text(slide)) < TEXT_SLIDE_MIN_CHARS


def detect(root):
    """'slider' | 'text-slider' | 'gallery' | None for a candidate component root."""
    if not isinstance(root, Tag):
        return None
    if 'splide' in _classes(root):
        slides = splide_slides(root)
        if not slides:
            return None
        images = sum(1 for s in slides if _is_image_slide(s))
        return 'slider' if images * 2 > len(slides) else 'text-slider'
    n = len(gallery_items(root))
    if n >= 2 or (n >= 1 and root.get('data-media-collection') == 'lightbox'):
        return 'gallery'
    return None


def find_for(el):
    """(root, kind) of the component containing el, or None. A .splide ancestor wins."""
    section = el if el.has_attr('data-section') else el.find_parent(attrs={'data-section': True})
    if section is None:
        return None
    splide = el if 'splide' in _classes(el) else el.find_parent(class_='splide')
    if splide is not None and splide is not section and any(p is section for p in splide.parents):
        kind = detect(splide)
        return (splide, kind) if kind else None
    node = el
    while node is not None and node is not section:
        if detect(node) == 'gallery':
            return node, 'gallery'
        node = node.parent
    return None


def find_component(soup, root_selector, kind):
    root = soup.select_one(root_selector)
    return root if root is not None and detect(root) == kind else None


def items(root, kind):
    return splide_slides(root) if kind in ('slider', 'text-slider') else gallery_items(root)


def min_items(root, kind):
    if kind == 'gallery' and root.get('data-media-collection') != 'lightbox':
        return 2
    return 1
```

- [ ] **Step 5: Run to verify pass**

Run: `cd ~/Documents/djangopress-sites/checkinfaro-v3 && .venv/bin/python manage.py test djangopress.editor_v2.tests.test_components 2>&1 | tail -4`
Expected: `OK`.

- [ ] **Step 6: Commit**

```bash
cd ~/Documents/djangopress-sites/djangopress
git add src/djangopress/editor_v2/components.py src/djangopress/editor_v2/tests/test_components.py src/djangopress/editor_v2/tests/fixtures
git commit -m "feat(editor): recognise sliders, text sliders and lightbox galleries by structure

Claude-Session: https://claude.ai/code/session_01WSpzVT1ezgnAA6UbDJmNtS"
```

---

### Task 2: Python operations

**Files:**
- Modify: `editor_v2/components.py` (append)
- Test: `editor_v2/tests/test_components.py` (append)

**Interfaces:**
- Consumes: Task 1 functions.
- Produces (all raise `ValueError` on bad arguments; each returns the index the panel should focus, an `int`):
  - `reorder(root, kind, order: list[int]) -> int` — `order[new_position] = old_index`; returns `0`.
  - `remove(root, kind, index) -> int`
  - `set_settings(root, changes: dict) -> int` — `None` value deletes a key; returns `0`.
  - `replace_image(root, kind, index, url, alt) -> int`
  - `add_images(root, kind, after, images: list[tuple[str, str]]) -> int` — index of the first new item.
  - `add_text_item(root, kind, after, texts: dict[str|int, str]) -> int` — keys are text-leaf indices.
  - `update_item(root, kind, index, alt=None, caption=None, texts=None) -> int`
  - `SETTING_KEYS` (frozenset).

- [ ] **Step 1: Write the failing tests** (append to `test_components.py`):

```python
import json as _json


def comp(name):
    soup = load(name)
    root, kind = components.find_for(soup.select_one('[data-probe]'))
    return soup, root, kind


def srcs(root, kind):
    return [components.image_of(i)['src'].rsplit('/', 1)[-1] for i in components.items(root, kind)]


class OperationsTest(SimpleTestCase):
    def test_reorder_is_a_permutation_by_slot(self):
        soup, root, kind = comp('loop_carousel')
        components.reorder(root, kind, [3, 0, 1, 2])
        self.assertEqual(srcs(root, kind), ['4.jpg', '1.jpg', '2.jpg', '3.jpg'])
        # the pre-baked clone keeps its place, first in the list
        self.assertIn('splide__slide--clone', soup.select('.splide__list > li')[0]['class'])

    def test_reorder_rejects_non_permutation(self):
        _, root, kind = comp('hero_fade')
        for bad in ([0, 1], [0, 0, 1], [0, 1, 5], 'x', [True, 0, 1]):
            with self.assertRaises(ValueError):
                components.reorder(root, kind, bad)

    def test_reorder_gallery_keeps_non_items_in_place(self):
        soup = BeautifulSoup('<section data-section="s"><div class="g"><h3>T</h3>'
                             '<a href="/1.jpg" data-lightbox="g"><img src="/1.jpg"/></a>'
                             '<a href="/2.jpg" data-lightbox="g"><img src="/2.jpg"/></a></div></section>', 'html.parser')
        root = soup.select_one('.g')
        components.reorder(root, 'gallery', [1, 0])
        self.assertEqual([c.name for c in root.find_all(True, recursive=False)], ['h3', 'a', 'a'])
        self.assertEqual(root.select('a')[0]['href'], '/2.jpg')

    def test_remove_and_focus(self):
        _, root, kind = comp('hero_fade')
        self.assertEqual(components.remove(root, kind, 2), 1)
        self.assertEqual(srcs(root, kind), ['a.jpg', 'b.jpg'])

    def test_remove_refuses_below_minimum(self):
        _, root, kind = comp('hero_fade')
        components.remove(root, kind, 0)
        components.remove(root, kind, 0)
        with self.assertRaises(ValueError):
            components.remove(root, kind, 0)
        soup = BeautifulSoup('<section data-section="s"><div class="g">'
                             '<a href="/1.jpg" data-lightbox="g"><img src="/1.jpg"/></a>'
                             '<a href="/2.jpg" data-lightbox="g"><img src="/2.jpg"/></a></div></section>', 'html.parser')
        with self.assertRaises(ValueError):
            components.remove(soup.select_one('.g'), 'gallery', 0)

    def test_remove_rejects_bad_index(self):
        _, root, kind = comp('hero_fade')
        for bad in (-1, 3, '1', None, True):
            with self.assertRaises(ValueError):
                components.remove(root, kind, bad)

    def test_set_settings_merges_and_deletes(self):
        _, root, kind = comp('hero_fade')
        components.set_settings(root, {'type': 'loop', 'rewind': None, 'interval': 3000})
        opts = _json.loads(root['data-splide'])
        self.assertEqual(opts['type'], 'loop')
        self.assertNotIn('rewind', opts)
        self.assertEqual(opts['interval'], 3000)
        self.assertEqual(opts['arrowPath'], 'M15 6 L29 20 L15 34')   # unknown key preserved

    def test_set_settings_validates(self):
        _, root, kind = comp('hero_fade')
        for bad in ({'type': 'cube'}, {'autoplay': 'yes'}, {'interval': 10}, {'perPage': 0},
                    {'arrowPath': 'x'}, {'breakpoints': []}, 'nope'):
            with self.assertRaises(ValueError):
                components.set_settings(root, bad)

    def test_set_settings_refuses_invalid_json(self):
        _, root, kind = comp('hero_fade')
        root['data-splide'] = '{type: fade'
        with self.assertRaises(ValueError):
            components.set_settings(root, {'autoplay': False})
        self.assertEqual(root['data-splide'], '{type: fade')

    def test_set_settings_only_on_sliders(self):
        _, root, kind = comp('gallery_grid')
        with self.assertRaises(ValueError):
            components.set_settings(root, {'autoplay': False})

    def test_replace_image_syncs_lightbox_and_drops_srcset(self):
        _, root, kind = comp('gallery_grid')
        item = components.items(root, kind)[1]
        components.image_of(item)['srcset'] = 'x 1x'
        components.replace_image(root, kind, 1, 'https://example.com/new.jpg', 'Novo')
        img = components.image_of(item)
        self.assertEqual((img['src'], img['alt']), ('https://example.com/new.jpg', 'Novo'))
        self.assertNotIn('srcset', img.attrs)
        self.assertEqual(item['href'], 'https://example.com/new.jpg')
        self.assertEqual(item['data-alt'], 'Novo')

    def test_replace_image_rejects_unsafe_url(self):
        _, root, kind = comp('hero_fade')
        for bad in ('javascript:alert(1)', 'data:text/html,x', ''):
            with self.assertRaises(ValueError):
                components.replace_image(root, kind, 0, bad, 'x')

    def test_add_images_clones_the_anchor_item(self):
        _, root, kind = comp('loop_carousel')
        first_new = components.add_images(root, kind, 1, [('/n1.jpg', 'N1'), ('/n2.jpg', 'N2')])
        self.assertEqual(first_new, 2)
        self.assertEqual(srcs(root, kind), ['1.jpg', '2.jpg', 'n1.jpg', 'n2.jpg', '3.jpg', '4.jpg'])
        new = components.items(root, kind)[2]
        self.assertEqual(new['class'], ['splide__slide'])
        self.assertEqual(components.image_of(new)['alt'], 'N1')

    def test_add_text_item_writes_leaves(self):
        _, root, kind = comp('testimonials')
        idx = components.add_text_item(root, kind, 0, {'0': '“Excelente.”', '1': 'Rui · Google'})
        self.assertEqual(idx, 1)
        leaves = components.text_leaves(components.items(root, kind)[1])
        self.assertEqual([components.read_text(l) for l in leaves], ['“Excelente.”', 'Rui · Google'])
        self.assertEqual(leaves[0]['class'], ['text-2xl'])

    def test_add_text_item_refuses_empty_and_formatted(self):
        _, root, kind = comp('testimonials')
        with self.assertRaises(ValueError):
            components.add_text_item(root, kind, 0, {'0': '   '})
        _, root, kind = comp('card_carousel')
        with self.assertRaises(ValueError):   # leaf 1 has <strong>: not editable
            components.add_text_item(root, kind, 0, {'1': 'x'})

    def test_update_item(self):
        _, root, kind = comp('gallery_grid')
        components.update_item(root, kind, 0, alt='Sala grande', caption='A sala')
        item = components.items(root, kind)[0]
        self.assertEqual(components.image_of(item)['alt'], 'Sala grande')
        self.assertEqual(item['data-alt'], 'A sala')
        _, root, kind = comp('testimonials')
        components.update_item(root, kind, 2, texts={'1': 'Ana M. · Google'})
        self.assertEqual(components.read_text(components.text_leaves(components.items(root, kind)[2])[1]), 'Ana M. · Google')

    def test_update_item_rejects_missing_targets(self):
        _, root, kind = comp('testimonials')
        with self.assertRaises(ValueError):
            components.update_item(root, kind, 0, alt='x')        # no image
        with self.assertRaises(ValueError):
            components.update_item(root, kind, 0, caption='x')    # no lightbox link
        with self.assertRaises(ValueError):
            components.update_item(root, kind, 0, texts={'7': 'x'})
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/Documents/djangopress-sites/checkinfaro-v3 && .venv/bin/python manage.py test djangopress.editor_v2.tests.test_components 2>&1 | tail -4`
Expected: FAIL/ERROR — `AttributeError: module ... has no attribute 'reorder'`.

- [ ] **Step 3: Implement** (append to `editor_v2/components.py`):

```python
# --- operations ----------------------------------------------------------------
# Each returns the index the panel should focus and raises ValueError on bad
# arguments. They never look at other languages: the endpoint applies them to
# each language copy in turn.

SETTING_KEYS = frozenset({
    'type', 'rewind', 'autoplay', 'interval', 'speed', 'arrows', 'pagination',
    'pauseOnHover', 'perPage', 'breakpoints',
})
_BOOL_SETTINGS = {'rewind', 'autoplay', 'arrows', 'pagination', 'pauseOnHover'}
_INT_RANGES = {'interval': (1000, 60000), 'speed': (100, 5000), 'perPage': (1, 8)}


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _require_index(its, index):
    if not _is_int(index) or not 0 <= index < len(its):
        raise ValueError('Item not found')


def _safe_url(url):
    if not isinstance(url, str) or not url.strip():
        raise ValueError('Missing image URL')
    if not url.startswith(('http://', 'https://', '/')):
        raise ValueError('Image URL must be http(s) or site-relative')
    return url


def reorder(root, kind, order):
    its = items(root, kind)
    if not isinstance(order, list) or not all(_is_int(i) for i in order) or sorted(order) != list(range(len(its))):
        raise ValueError('order must list every item exactly once')
    markers = []
    for it in its:
        marker = _SCRATCH.new_tag('ev2-slot')
        it.replace_with(marker)
        markers.append(marker)
    for marker, old in zip(markers, order):
        marker.replace_with(its[old])
    return 0


def remove(root, kind, index):
    its = items(root, kind)
    _require_index(its, index)
    if len(its) <= min_items(root, kind):
        raise ValueError("This is the minimum number of items — it can't be removed")
    its[index].decompose()
    return min(index, len(its) - 2)


def _validate_setting(key, value):
    if key not in SETTING_KEYS:
        raise ValueError(f'Unknown setting: {key}')
    if value is None:
        return
    if key == 'type' and value not in ('slide', 'loop', 'fade'):
        raise ValueError('type must be slide, loop or fade')
    if key in _BOOL_SETTINGS and not isinstance(value, bool):
        raise ValueError(f'{key} must be true or false')
    if key in _INT_RANGES:
        lo, hi = _INT_RANGES[key]
        if not _is_int(value) or not lo <= value <= hi:
            raise ValueError(f'{key} must be a whole number between {lo} and {hi}')
    if key == 'breakpoints':
        if not isinstance(value, dict) or not all(str(k).isdigit() and isinstance(v, dict) for k, v in value.items()):
            raise ValueError('breakpoints must map pixel widths to option objects')


def set_settings(root, changes):
    if 'splide' not in _classes(root):
        raise ValueError('Settings apply to sliders only')
    if not isinstance(changes, dict) or not changes:
        raise ValueError('No settings to change')
    for key, value in changes.items():
        _validate_setting(key, value)
    raw = root.get('data-splide')
    try:
        opts = json.loads(raw) if raw else {}
    except ValueError:
        opts = None
    if not isinstance(opts, dict):
        raise ValueError("This slider's settings aren't valid JSON — fix them in the HTML first")
    for key, value in changes.items():
        if value is None:
            opts.pop(key, None)
        else:
            opts[key] = value
    root['data-splide'] = json.dumps(opts, ensure_ascii=False, separators=(',', ':'))
    return 0


def _set_image(item, url, alt):
    img = image_of(item)
    if img is None:
        raise ValueError('This item has no image')
    img['src'] = _safe_url(url)
    for attr in ('srcset', 'sizes'):
        if attr in img.attrs:
            del img[attr]
    if alt is not None:
        img['alt'] = alt
    link = lightbox_link_of(item)
    if link is not None:
        link['href'] = url
        if alt is not None and link.has_attr('data-alt'):
            link['data-alt'] = alt


def replace_image(root, kind, index, url, alt):
    its = items(root, kind)
    _require_index(its, index)
    _set_image(its[index], url, alt)
    return index


def add_images(root, kind, after, images):
    its = items(root, kind)
    _require_index(its, after)
    if not images:
        raise ValueError('No images to add')
    anchor = its[after]
    for url, alt in images:
        clone = copy.copy(its[after])
        strip_ids(clone)
        _set_image(clone, url, alt)
        anchor.insert_after(clone)
        anchor = clone
    return after + 1


def _write_texts(item, texts):
    leaves = text_leaves(item)
    parsed = {}
    for key, value in texts.items():
        try:
            i = int(key)
        except (TypeError, ValueError):
            raise ValueError('Unknown text field')
        if not 0 <= i < len(leaves) or not is_editable_leaf(leaves[i]):
            raise ValueError('This text has formatting — edit it on the page instead')
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Text can't be empty — remove the item instead")
        parsed[i] = value.strip()
    for i, value in parsed.items():
        write_text(leaves[i], value)


def add_text_item(root, kind, after, texts):
    its = items(root, kind)
    _require_index(its, after)
    if not isinstance(texts, dict) or not texts:
        raise ValueError('Fill in the new item')
    clone = copy.copy(its[after])
    strip_ids(clone)
    _write_texts(clone, texts)
    its[after].insert_after(clone)
    return after + 1


def update_item(root, kind, index, alt=None, caption=None, texts=None):
    its = items(root, kind)
    _require_index(its, index)
    item = its[index]
    if alt is not None:
        img = image_of(item)
        if img is None:
            raise ValueError('This item has no image')
        img['alt'] = alt
    if caption is not None:
        link = lightbox_link_of(item)
        if link is None:
            raise ValueError('This item has no lightbox link')
        link['data-alt'] = caption
    if texts:
        _write_texts(item, texts)
    return index
```

- [ ] **Step 4: Run to verify pass**

Run: `cd ~/Documents/djangopress-sites/checkinfaro-v3 && .venv/bin/python manage.py test djangopress.editor_v2.tests.test_components 2>&1 | tail -4`
Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
cd ~/Documents/djangopress-sites/djangopress
git add src/djangopress/editor_v2/components.py src/djangopress/editor_v2/tests/test_components.py
git commit -m "feat(editor): component operations — reorder, remove, settings, replace/add images, text items

Claude-Session: https://claude.ai/code/session_01WSpzVT1ezgnAA6UbDJmNtS"
```

---

### Task 3: Translation helper

**Files:**
- Create: `editor_v2/component_translate.py`
- Test: `editor_v2/tests/test_component_translate.py`

**Interfaces:**
- Consumes: `components.read_text`.
- Produces: `translate_texts(texts: list[str], source_lang: str, target_lang: str) -> list[str] | None` — same order; `None` on any failure or empty output.

- [ ] **Step 1: Write the failing tests**:

```python
from unittest import mock

from django.test import SimpleTestCase

from djangopress.editor_v2.component_translate import translate_texts

SERVICE = 'djangopress.ai.services.ContentGenerationService'


class TranslateTextsTest(SimpleTestCase):
    def test_round_trip_keeps_order_and_line_breaks(self):
        with mock.patch(SERVICE) as svc:
            svc.return_value.translate_html.return_value = (
                '<p data-i="0">Great<br>food</p><p data-i="1">Rui &amp; Ana</p>')
            out = translate_texts(['Ótima\ncomida', 'Rui & Ana'], 'pt', 'en')
        self.assertEqual(out, ['Great\nfood', 'Rui & Ana'])
        snippet = svc.return_value.translate_html.call_args[0][0]
        self.assertIn('<p data-i="0">Ótima<br>comida</p>', snippet)
        self.assertIn('Rui &amp; Ana', snippet)

    def test_failure_returns_none(self):
        with mock.patch(SERVICE) as svc:
            svc.return_value.translate_html.side_effect = RuntimeError('no key')
            self.assertIsNone(translate_texts(['Olá'], 'pt', 'en'))

    def test_missing_or_empty_output_returns_none(self):
        with mock.patch(SERVICE) as svc:
            svc.return_value.translate_html.return_value = '<p data-i="0"> </p>'
            self.assertIsNone(translate_texts(['Olá'], 'pt', 'en'))
            svc.return_value.translate_html.return_value = 'Hello'
            self.assertIsNone(translate_texts(['Olá'], 'pt', 'en'))

    def test_empty_input(self):
        self.assertEqual(translate_texts([], 'pt', 'en'), [])
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/Documents/djangopress-sites/checkinfaro-v3 && .venv/bin/python manage.py test djangopress.editor_v2.tests.test_component_translate 2>&1 | tail -4`
Expected: ERROR — `ModuleNotFoundError: ... component_translate`.

- [ ] **Step 3: Implement** `editor_v2/component_translate.py`:

```python
"""Translate short editor strings (slide text, alt text) with the engine's HTML translator."""
import html
import logging

from bs4 import BeautifulSoup

from djangopress.editor_v2.components import read_text

logger = logging.getLogger(__name__)


def translate_texts(texts, source_lang, target_lang):
    """The texts translated into target_lang, same order; None on any failure."""
    if not texts:
        return []
    snippet = ''.join(
        f'<p data-i="{i}">{html.escape(t, quote=False).replace(chr(10), "<br>")}</p>'
        for i, t in enumerate(texts)
    )
    try:
        from djangopress.ai.services import ContentGenerationService
        translated = ContentGenerationService().translate_html(snippet, source_lang, target_lang)
    except Exception:
        logger.exception('translate_texts %s->%s failed', source_lang, target_lang)
        return None
    soup = BeautifulSoup(translated or '', 'html.parser')
    out = []
    for i in range(len(texts)):
        el = soup.find(attrs={'data-i': str(i)})
        value = read_text(el) if el is not None else ''
        if not value:
            return None
        out.append(value)
    return out
```

- [ ] **Step 4: Run to verify pass** — same command, expected `OK`.

- [ ] **Step 5: Commit**

```bash
cd ~/Documents/djangopress-sites/djangopress
git add src/djangopress/editor_v2/component_translate.py src/djangopress/editor_v2/tests/test_component_translate.py
git commit -m "feat(editor): translate short component texts through translate_html

Claude-Session: https://claude.ai/code/session_01WSpzVT1ezgnAA6UbDJmNtS"
```

---

### Task 4: `POST /editor-v2/api/component/`

**Files:**
- Modify: `editor_v2/api_views.py` — `_run_structural_verb` (around line 2079)
- Create: `editor_v2/component_views.py`
- Modify: `editor_v2/urls.py`
- Test: `editor_v2/tests/test_component_api.py`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: URL name `editor_v2:api_component_op`. Request JSON `{page_id | content_type_id+object_id, language, root, kind, count, op, args}`; `op` ∈ `reorder, remove, set_settings, replace_image, add_images, add_text_item, update_item`. `args`: `reorder {order}`, `remove {index}`, `set_settings {settings}`, `replace_image {index, image:{url, alt, id?}}`, `add_images {after, images:[{url, alt, id?}]}`, `add_text_item {after, texts:{"<leaf index>": str}}`, `update_item {index, alt?, caption?, texts?}`. Response `{success, index, html, skipped_languages, translated_languages, untranslated_languages, label, page_id}`; 400 `{success:false, error}` on bad input; 409 when the component is not found / count differs in the current language.
- `_run_structural_verb(request, data, change_summary, apply_fn, *, pass_lang=False, only_lang=None)` — with `pass_lang=True` it calls `apply_fn(soup, lang_code)`; with `only_lang` it changes only that language copy.

- [ ] **Step 1: Write the failing tests** — `editor_v2/tests/test_component_api.py`:

```python
import json
from unittest import mock

from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from djangopress.core.models import Page, PageVersion, SiteImage, SiteSettings
from djangopress.editor_v2 import components

User = get_user_model()
TRANSLATE = 'djangopress.editor_v2.component_views.translate_texts'


def slider(texts):
    slides = ''.join(
        f'<li class="splide__slide"><blockquote>{q}</blockquote><p>{a}</p></li>' for q, a in texts)
    return (f'<section data-section="t" id="t"><div class="splide" data-splide=\'{{"type":"fade","rewind":true}}\'>'
            f'<div class="splide__track"><ul class="splide__list">{slides}</ul></div></div></section>')


def gallery(names):
    links = ''.join(f'<a href="/media/{n}.jpg" data-lightbox="g" data-alt="{n}"><img src="/media/{n}.jpg" alt="{n}"/></a>'
                    for n in names)
    return f'<section data-section="g" id="g"><div class="grid">{links}</div></section>'


PT = slider([('“Uma refeição inesquecível, cheia de sabor e bom serviço.”', 'Ana'),
             ('“O melhor restaurante de Faro, sem qualquer dúvida possível.”', 'Rui')]) + gallery(['a', 'b', 'c'])
EN = slider([('“An unforgettable meal, full of flavour and good service.”', 'Ana'),
             ('“The best restaurant in Faro, without any possible doubt.”', 'Rui')]) + gallery(['a', 'b', 'c'])
SLIDER = 'section[data-section="t"] > div:nth-child(1)'
GALLERY = 'section[data-section="g"] > div:nth-child(1)'


class ComponentApiTest(TestCase):
    def setUp(self):
        Page.objects.all().delete()
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        self.page = Page.objects.create(
            title_i18n={'pt': 'Home', 'en': 'Home'}, slug_i18n={'pt': 'home', 'en': 'home'},
            is_active=True, html_content_i18n={'pt': PT, 'en': EN},
        )
        PageVersion.objects.filter(page=self.page).delete()
        self.staff = User.objects.create_user('staff', 'staff@example.com', 'pw', is_staff=True)
        self.client.force_login(self.staff)

    def post(self, root, kind, count, op, args, language='pt'):
        body = {'page_id': self.page.id, 'language': language, 'root': root, 'kind': kind,
                'count': count, 'op': op, 'args': args}
        return self.client.post(reverse('editor_v2:api_component_op'), data=json.dumps(body),
                                content_type='application/json')

    def comp(self, lang, root, kind):
        self.page.refresh_from_db()
        soup = BeautifulSoup(self.page.html_content_i18n[lang], 'html.parser')
        c = components.find_component(soup, root, kind)
        return components.items(c, kind)

    def texts(self, lang, i):
        leaves = components.text_leaves(self.comp(lang, SLIDER, 'text-slider')[i])
        return [components.read_text(l) for l in leaves]

    def test_reorder_applies_to_all_languages_with_checkpoint(self):
        res = self.post(SLIDER, 'text-slider', 2, 'reorder', {'order': [1, 0]})
        self.assertEqual(res.status_code, 200, res.content)
        body = res.json()
        self.assertEqual(body['skipped_languages'], [])
        self.assertEqual(self.texts('pt', 0)[1], 'Rui')
        self.assertEqual(self.texts('en', 0)[1], 'Rui')
        self.assertTrue(PageVersion.objects.filter(page=self.page, kind='checkpoint').exists())
        self.assertIn('splide__slide', body['html'])
        self.assertTrue(body['html'].startswith('<div class="splide"'))

    def test_update_item_touches_current_language_only(self):
        res = self.post(SLIDER, 'text-slider', 2, 'update_item', {'index': 1, 'texts': {'1': 'Rui M.'}})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(self.texts('pt', 1)[1], 'Rui M.')
        self.assertEqual(self.texts('en', 1)[1], 'Rui')

    def test_add_text_item_translates_other_languages(self):
        with mock.patch(TRANSLATE, return_value=['“Great.”', 'Zé']) as tr:
            res = self.post(SLIDER, 'text-slider', 2, 'add_text_item',
                            {'after': 1, 'texts': {'0': '“Ótimo.”', '1': 'Zé'}})
        self.assertEqual(res.status_code, 200, res.content)
        body = res.json()
        tr.assert_called_once_with(['“Ótimo.”', 'Zé'], 'pt', 'en')
        self.assertEqual(body['index'], 2)
        self.assertEqual(body['translated_languages'], ['en'])
        self.assertEqual(self.texts('pt', 2), ['“Ótimo.”', 'Zé'])
        self.assertEqual(self.texts('en', 2), ['“Great.”', 'Zé'])

    def test_add_text_item_translation_failure_keeps_source(self):
        with mock.patch(TRANSLATE, return_value=None):
            res = self.post(SLIDER, 'text-slider', 2, 'add_text_item',
                            {'after': 0, 'texts': {'0': '“Ótimo.”', '1': 'Zé'}})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()['untranslated_languages'], ['en'])
        self.assertEqual(self.texts('en', 1), ['“Ótimo.”', 'Zé'])

    def test_add_images_uses_library_alt_per_language(self):
        img = SiteImage.objects.create(title_i18n={'pt': 'Sala'}, alt_text_i18n={'pt': 'Sala cheia', 'en': 'Full room'})
        with mock.patch(TRANSLATE) as tr:
            res = self.post(GALLERY, 'gallery', 3, 'add_images',
                            {'after': 2, 'images': [{'id': str(img.id), 'url': '/media/new.jpg', 'alt': 'Sala cheia'}]})
        self.assertEqual(res.status_code, 200, res.content)
        tr.assert_not_called()
        self.assertEqual(components.image_of(self.comp('pt', GALLERY, 'gallery')[3])['alt'], 'Sala cheia')
        self.assertEqual(components.image_of(self.comp('en', GALLERY, 'gallery')[3])['alt'], 'Full room')
        self.assertEqual(self.comp('en', GALLERY, 'gallery')[3]['href'], '/media/new.jpg')

    def test_replace_image_translates_missing_alt(self):
        with mock.patch(TRANSLATE, return_value=['Terrace']) as tr:
            res = self.post(GALLERY, 'gallery', 3, 'replace_image',
                            {'index': 0, 'image': {'url': '/media/t.jpg', 'alt': 'Esplanada'}})
        self.assertEqual(res.status_code, 200, res.content)
        tr.assert_called_once_with(['Esplanada'], 'pt', 'en')
        self.assertEqual(components.image_of(self.comp('en', GALLERY, 'gallery')[0])['alt'], 'Terrace')

    def test_set_settings(self):
        res = self.post(SLIDER, 'text-slider', 2, 'set_settings', {'settings': {'autoplay': True, 'interval': 4000}})
        self.assertEqual(res.status_code, 200, res.content)
        self.page.refresh_from_db()
        for lang in ('pt', 'en'):
            root = BeautifulSoup(self.page.html_content_i18n[lang], 'html.parser').select_one(SLIDER)
            self.assertEqual(json.loads(root['data-splide'])['interval'], 4000)

    def test_drifted_language_is_skipped(self):
        link_c = '<a href="/media/c.jpg" data-lightbox="g" data-alt="c"><img src="/media/c.jpg" alt="c"/></a>'
        self.page.html_content_i18n = {'pt': PT, 'en': EN.replace(link_c, '')}
        self.page.save()
        res = self.post(GALLERY, 'gallery', 3, 'remove', {'index': 0})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()['skipped_languages'], ['en'])
        self.assertEqual(len(self.comp('pt', GALLERY, 'gallery')), 2)
        self.assertEqual(len(self.comp('en', GALLERY, 'gallery')), 2)   # untouched: it already had 2

    def test_stale_count_in_current_language_is_409(self):
        res = self.post(GALLERY, 'gallery', 5, 'remove', {'index': 0})
        self.assertEqual(res.status_code, 409)
        self.assertFalse(res.json()['success'])

    def test_bad_arguments_are_400_and_change_nothing(self):
        before = dict(self.page.html_content_i18n)
        for op, args in (('reorder', {'order': [0, 0]}), ('remove', {'index': 9}), ('explode', {}),
                         ('set_settings', {'settings': {'type': 'cube'}}),
                         ('add_text_item', {'after': 0, 'texts': {'0': ' '}})):
            with self.subTest(op=op), mock.patch(TRANSLATE, return_value=['x']):
                res = self.post(SLIDER, 'text-slider', 2, op, args)
                self.assertEqual(res.status_code, 400, res.content)
        self.page.refresh_from_db()
        self.assertEqual(self.page.html_content_i18n, before)

    def test_non_staff_is_redirected(self):
        self.client.force_login(User.objects.create_user('plain', 'p@example.com', 'pw'))
        res = self.post(SLIDER, 'text-slider', 2, 'remove', {'index': 0})
        self.assertEqual(res.status_code, 302)
```

(`test_drifted_language_is_skipped`: EN has only two gallery links, so the `count=3` guard skips EN.)

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/Documents/djangopress-sites/checkinfaro-v3 && .venv/bin/python manage.py test djangopress.editor_v2.tests.test_component_api 2>&1 | tail -4`
Expected: ERROR — `NoReverseMatch: 'api_component_op'`.

- [ ] **Step 3: Extend `_run_structural_verb`** in `editor_v2/api_views.py`. Change the signature and the two `apply_fn` calls; everything else stays:

```python
def _run_structural_verb(request, data, change_summary, apply_fn, *, pass_lang=False, only_lang=None):
    """
    Shared driver for structural endpoints.

    `apply_fn(soup)` — or `apply_fn(soup, lang_code)` when `pass_lang` — mutates
    a soup and returns a result (truthy or an int on success, None when the
    target was not found or the verb was a no-op). It is run once on the
    current-language HTML for validation and to get the result, then on every
    language copy (only `only_lang` when given).
    ...(keep the rest of the docstring)
    """
```

Replace `result = apply_fn(BeautifulSoup(current_html or '', 'html.parser'))` with:

```python
    call = (lambda soup, code: apply_fn(soup, code)) if pass_lang else (lambda soup, code: apply_fn(soup))
    result = call(BeautifulSoup(current_html or '', 'html.parser'), lang)
```

and in the language loop replace `if apply_fn(soup) is None:` with:

```python
        if only_lang and lang_code != only_lang:
            continue
        soup = BeautifulSoup(lang_html, 'html.parser')
        if call(soup, lang_code) is None:
```

(the existing `soup = BeautifulSoup(lang_html, 'html.parser')` line moves below the `only_lang` check).

- [ ] **Step 4: Create** `editor_v2/component_views.py`:

```python
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
    _detect_language_from_request, _get_editable_object, _get_page_html, _run_structural_verb,
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

    def apply(soup, code):
        root = components.find_component(soup, root_sel, kind)
        if root is None or len(components.items(root, kind)) != count:
            return None
        return op_fn(root, code)

    try:
        outcome = _run_structural_verb(
            request, data, LABELS[op], apply,
            pass_lang=True, only_lang=lang if op == 'update_item' else None,
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
```

Note: `_run_structural_verb` writes the checkpoint only after the current-language validation call succeeds, so a `ValueError` there leaves the page untouched. A `ValueError` raised for another language happens before `page.save()`, so nothing is written either.

- [ ] **Step 5: Route it** — in `editor_v2/urls.py`, import and add under "Structural verbs (no LLM)":

```python
from . import api_views, component_views
...
    path('api/component/', component_views.component_op, name='api_component_op'),
```

- [ ] **Step 6: Run to verify pass**

Run: `cd ~/Documents/djangopress-sites/checkinfaro-v3 && .venv/bin/python manage.py test djangopress.editor_v2 2>&1 | tail -4`
Expected: `OK` (the existing 96 + the new ones).

- [ ] **Step 7: Commit**

```bash
cd ~/Documents/djangopress-sites/djangopress
git add src/djangopress/editor_v2/api_views.py src/djangopress/editor_v2/component_views.py src/djangopress/editor_v2/urls.py src/djangopress/editor_v2/tests/test_component_api.py
git commit -m "feat(editor): POST /editor-v2/api/component/ — checkpointed component operations in every language

Claude-Session: https://claude.ai/code/session_01WSpzVT1ezgnAA6UbDJmNtS"
```

---

### Task 5: Server bug fixes — per-language alt, runtime classes

**Files:**
- Modify: `editor_v2/api_views.py` — `update_page_element_classes` (~line 465), `update_page_element_attribute` (~line 560), helper next to `_apply_structural_change_to_all_langs` (~line 133)
- Test: `editor_v2/tests/test_structural_api.py` (append a class)

**Interfaces:**
- Consumes: `components.RUNTIME_CLASS_RE`.
- Produces: `update-page-attribute` accepts optional `language` and `image_id`. For `alt`, `title`, `aria-label`, `data-alt`, `placeholder` it writes only the current language, except `alt` with `image_id`, which also writes each other language that has `SiteImage.alt_text_i18n[lang]`. `update-page-classes` drops runtime classes.

- [ ] **Step 1: Write the failing tests** (append to `test_structural_api.py`):

```python
from djangopress.core.models import SiteImage

IMG_PT = '<section data-section="s" id="s"><img src="/a.jpg" alt="Sala"/><p class="x">T</p></section>'
IMG_EN = '<section data-section="s" id="s"><img src="/a.jpg" alt="Room"/><p class="x">T</p></section>'
IMG = 'section[data-section="s"] > img:nth-child(1)'
P = 'section[data-section="s"] > p:nth-child(2)'


class AttributeLanguageTest(StructuralApiTestCase):
    def setUp(self):
        super().setUp()
        self.page.html_content_i18n = {'pt': IMG_PT, 'en': IMG_EN}
        self.page.save()

    def test_typed_alt_changes_current_language_only(self):
        res = self.post('api_update_page_attribute', {'selector': IMG, 'attribute': 'alt', 'value': 'Sala grande', 'language': 'pt'})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertIn('alt="Sala grande"', self.html('pt'))
        self.assertIn('alt="Room"', self.html('en'))

    def test_src_still_changes_every_language(self):
        self.post('api_update_page_attribute', {'selector': IMG, 'attribute': 'src', 'value': '/b.jpg', 'language': 'pt'})
        self.assertIn('src="/b.jpg"', self.html('en'))

    def test_library_alt_fills_other_languages(self):
        img = SiteImage.objects.create(alt_text_i18n={'pt': 'Esplanada', 'en': 'Terrace'})
        self.post('api_update_page_attribute', {'selector': IMG, 'attribute': 'alt', 'value': 'Esplanada',
                                                'language': 'pt', 'image_id': img.id})
        self.assertIn('alt="Esplanada"', self.html('pt'))
        self.assertIn('alt="Terrace"', self.html('en'))

    def test_runtime_classes_are_not_stored(self):
        self.post('api_update_page_classes', {'selector': P, 'new_classes': 'x is-active is-visible splide--fade mt-4'})
        self.assertIn('class="x mt-4"', self.html('pt'))
        self.assertIn('class="x mt-4"', self.html('en'))
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/Documents/djangopress-sites/checkinfaro-v3 && .venv/bin/python manage.py test djangopress.editor_v2.tests.test_structural_api 2>&1 | tail -4`
Expected: FAIL in `test_typed_alt_changes_current_language_only`, `test_library_alt_fills_other_languages`, `test_runtime_classes_are_not_stored`.

- [ ] **Step 3: Implement.**

(a) Next to `_apply_structural_change_to_all_langs` add:

```python
def _apply_change_to_lang(page, lang, change_fn):
    """Apply change_fn(soup) to one language copy (no-op when that copy is empty or change_fn returns False)."""
    html_i18n = dict(getattr(page, 'html_content_i18n', None) or {})
    existing_html = html_i18n.get(lang)
    if not existing_html:
        return
    soup = BeautifulSoup(existing_html, 'html.parser')
    if change_fn(soup):
        new_html = str(soup)
        if new_html.startswith('<html><body>'):
            new_html = new_html[12:-14]
        html_i18n[lang] = new_html
    page.html_content_i18n = html_i18n


# Attributes whose value is text in the page's language: an edit in PT must not
# overwrite the EN copy.
PER_LANGUAGE_ATTRIBUTES = ('alt', 'title', 'aria-label', 'data-alt', 'placeholder')
```

(b) In `update_page_element_classes`, right after `new_classes = data.get('new_classes', '').strip()` add:

```python
        # Splide / editor runtime state classes must never reach the database.
        new_classes = ' '.join(c for c in new_classes.split() if not components.RUNTIME_CLASS_RE.match(c))
```

and add `from djangopress.editor_v2 import components` to the imports at the top (next to `structure`).

(c) In `update_page_element_attribute`:
- after `tag_name = data.get('tag_name')` add `lang = _detect_language_from_request(request, data)`;
- change `current_html, resolved_lang = _get_page_html(page)` to `current_html, resolved_lang = _get_page_html(page, lang)`;
- change `def apply_attribute(s):` to `def apply_attribute(s, value=value):` (body unchanged — it already uses `value`);
- replace `_apply_structural_change_to_all_langs(page, apply_attribute)` with:

```python
        if attribute in PER_LANGUAGE_ATTRIBUTES:
            values = {lang: value}
            image_id = data.get('image_id')
            if attribute == 'alt' and image_id:
                site_image = SiteImage.objects.filter(pk=image_id).first()
                i18n = (site_image.alt_text_i18n or {}) if site_image else {}
                for code in (page.html_content_i18n or {}):
                    if code != lang and i18n.get(code):
                        values[code] = i18n[code]
            for code, code_value in values.items():
                _apply_change_to_lang(page, code, lambda s, v=code_value: apply_attribute(s, v))
        else:
            _apply_structural_change_to_all_langs(page, apply_attribute)
```

- [ ] **Step 4: Run to verify pass**

Run: `cd ~/Documents/djangopress-sites/checkinfaro-v3 && .venv/bin/python manage.py test djangopress.editor_v2 2>&1 | tail -4`
Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
cd ~/Documents/djangopress-sites/djangopress
git add src/djangopress/editor_v2/api_views.py src/djangopress/editor_v2/tests/test_structural_api.py
git commit -m "fix(editor): alt text stays per language; Splide runtime classes are never saved

Claude-Session: https://claude.ai/code/session_01WSpzVT1ezgnAA6UbDJmNtS"
```

---

### Task 6: JS recognition (`components.js`) + browser harness

**Files:**
- Create: `editor_v2/static/editor_v2/js/lib/components.js`
- Create: `editor_v2/tests/js/components_test.html`
- Modify: `editor_v2/static/editor_v2/js/lib/dom.js` — extend `RUNTIME_CLASS_RE`, export `isRuntimeClass`

**Interfaces:**
- Consumes: `isRuntimeInjected` from `dom.js`; fixtures from Task 1.
- Produces (ES exports of `lib/components.js`):
  - `findComponent(el) -> {root, kind} | null`, `detectKind(root) -> kind|null`, `itemsOf(comp) -> Element[]`
  - `itemFields(item) -> {image: HTMLImageElement|null, link: HTMLAnchorElement|null, texts: [{el, editable, value, label}]}`
  - `readText(el) -> string`, `minItems(comp) -> number`, `componentLabel(comp) -> {title, noun}`
  - `readSliderOptions(root) -> {ok: boolean, opts: object}`, `settingsFromOptions(opts) -> Settings`, `settingsChanges(settings, opts) -> object` (keys of `SETTING_KEYS`, `null` = delete)
  - `canSwapInPlace(html) -> boolean`
  - `Settings = {effect:'slide'|'fade', loop, autoplay, seconds, speed:'slow'|'normal'|'fast', arrows, dots, pauseOnHover, multi, perPage, tablet, mobile}`
- `dom.js`: `export function isRuntimeClass(c) -> boolean`.

- [ ] **Step 1: Write the harness** `editor_v2/tests/js/components_test.html`:

```html
<!doctype html>
<meta charset="utf-8">
<title>running</title>
<div class="editor-v2-content" id="host"></div>
<pre id="out"></pre>
<script type="module">
import {
    findComponent, itemsOf, itemFields, minItems, readSliderOptions,
    settingsFromOptions, settingsChanges, canSwapInPlace,
} from '../../static/editor_v2/js/lib/components.js';

const FIXTURES = ['hero_fade', 'loop_carousel', 'testimonials', 'card_carousel', 'gallery_grid',
                  'gallery_wrapped', 'splide_lightbox', 'gallery_hint', 'not_component'];
const fails = [];
let passed = 0;
const eq = (name, got, want) => {
    if (JSON.stringify(got) === JSON.stringify(want)) passed++;
    else fails.push(`${name}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`);
};
const host = document.getElementById('host');
const load = async (name) => { host.innerHTML = await (await fetch(`../fixtures/components/${name}.html`)).text(); };

for (const name of FIXTURES) {
    await load(name);
    const want = host.querySelector('section').dataset;
    const comp = findComponent(host.querySelector('[data-probe]'));
    eq(`${name} kind`, comp ? comp.kind : 'none', want.expectKind);
    if (!comp) continue;
    const items = itemsOf(comp);
    eq(`${name} count`, items.length, Number(want.expectCount));
    const f = itemFields(items[0]);
    eq(`${name} texts`, f.texts.length, Number(want.expectTexts));
    eq(`${name} editable`, f.texts.filter(t => t.editable).length, Number(want.expectEditable));
    eq(`${name} image`, f.image ? 1 : 0, Number(want.expectImage));
}

// clone ignored and stored order kept
await load('loop_carousel');
let comp = findComponent(host.querySelector('[data-probe]'));
eq('loop order', itemsOf(comp).map(i => itemFields(i).image.getAttribute('alt')), ['Um', 'Dois', 'Três', 'Quatro']);

// text reading
await load('testimonials');
comp = findComponent(host.querySelector('[data-probe]'));
eq('testimonial values', itemFields(itemsOf(comp)[1]).texts.map(t => t.value),
   ['“Best restaurant we\'ve been to in Faro. The meal was a symphony.”', 'travbud1 · Tripadvisor']);
eq('testimonial labels', itemFields(itemsOf(comp)[1]).texts.map(t => t.label), ['Quote', 'Text']);

// minimum items
await load('gallery_grid');
eq('gallery min', minItems(findComponent(host.querySelector('[data-probe]'))), 2);
await load('gallery_hint');
eq('hinted gallery min', minItems(findComponent(host.querySelector('[data-probe]'))), 1);

// settings: fade hero
await load('hero_fade');
comp = findComponent(host.querySelector('[data-probe]'));
let { ok, opts } = readSliderOptions(comp.root);
eq('fade ok', ok, true);
let s = settingsFromOptions(opts);
eq('fade settings', [s.effect, s.loop, s.autoplay, s.seconds, s.speed, s.arrows, s.dots, s.multi],
   ['fade', true, true, 5, 'slow', true, true, false]);
s.loop = false; s.seconds = 3;
eq('fade changes', settingsChanges(s, opts),
   { type: 'fade', rewind: false, autoplay: true, interval: 3000, speed: 1200, arrows: true, pagination: true, pauseOnHover: true });
s.effect = 'slide'; s.loop = true;
eq('slide+loop changes type/rewind', [settingsChanges(s, opts).type, settingsChanges(s, opts).rewind], ['loop', null]);

// settings: multi-item loop carousel
await load('loop_carousel');
comp = findComponent(host.querySelector('[data-probe]'));
({ opts } = readSliderOptions(comp.root));
s = settingsFromOptions(opts);
eq('multi settings', [s.effect, s.loop, s.multi, s.perPage, s.tablet, s.mobile], ['slide', true, true, 3, 2, 1]);
s.perPage = 4; s.mobile = 2;
eq('breakpoints merge', settingsChanges(s, opts).breakpoints, { '1024': { perPage: 2 }, '768': { perPage: 2 } });
eq('perPage', settingsChanges(s, opts).perPage, 4);

// invalid JSON
comp.root.setAttribute('data-splide', '{type: fade');
eq('invalid json', readSliderOptions(comp.root).ok, false);

// in-place swap guard
eq('swap plain', canSwapInPlace('<div class="splide"></div>'), true);
eq('swap template var', canSwapInPlace('<img src="{{ MEDIA_URL }}a.jpg">'), false);
eq('swap template tag', canSwapInPlace('<p>{% trans "x" %}</p>'), false);

document.title = fails.length ? `FAIL ${fails.length}` : `PASS ${passed}`;
document.getElementById('out').textContent = fails.join('\n') || `all ${passed} passed`;
</script>
```

- [ ] **Step 2: Run it to verify failure.** Serve the package root and open the harness with the playwright-cli skill (load `playwright-cli` first):

```bash
cd ~/Documents/djangopress-sites/djangopress/src/djangopress && python3 -m http.server 8765
```
(run in the background), then open `http://localhost:8765/editor_v2/tests/js/components_test.html` and read `document.title`.
Expected: the module fails to load (`components.js` 404); the title stays `running`.

- [ ] **Step 3: Extend `dom.js`.** Replace the `RUNTIME_CLASS_RE` line and add the export right below it:

```js
const RUNTIME_CLASS_RE = /^(ev2-|is-(active|visible|prev|next|initialized|rendered|overflow|focus-in)$|splide--|splide__slide--clone$)/;

/** Runtime/editor state class (Splide, ev2-) — shown to nobody, saved never. Mirror of components.RUNTIME_CLASS_RE. */
export function isRuntimeClass(c) {
    return RUNTIME_CLASS_RE.test(c);
}
```

- [ ] **Step 4: Implement** `editor_v2/static/editor_v2/js/lib/components.js`:

```js
/**
 * Editable components — Splide sliders and lightbox galleries — recognised by
 * structure in the live DOM. Mirror of editor_v2/components.py: keep the rules
 * in step (shared fixtures in editor_v2/tests/fixtures/components/, harness
 * in editor_v2/tests/js/components_test.html).
 */
import { isRuntimeInjected } from './dom.js';

const TEXT_SLIDE_MIN_CHARS = 40;
const SKIP_TAGS = new Set(['IMG', 'SVG', 'SCRIPT', 'STYLE', 'PICTURE', 'VIDEO', 'IFRAME', 'SOURCE', 'BR', 'TEMPLATE']);
const INLINE_TAGS = new Set(['STRONG', 'EM', 'B', 'I', 'BR', 'SPAN', 'A', 'SMALL', 'SUP', 'SUB', 'U', 'MARK']);
export const SPEED_PRESETS = { slow: 1200, normal: 800, fast: 400 };

const tagOf = (el) => el.tagName.toUpperCase();
const realChildren = (el) => Array.from(el.children).filter(c => !isRuntimeInjected(c));

// --- text ---

export function readText(el) {
    const parts = [];
    (function walk(node) {
        for (const child of node.childNodes) {
            if (child.nodeType === Node.TEXT_NODE) parts.push(child.nodeValue.replace(/\s+/g, ' '));
            else if (child.nodeType === Node.ELEMENT_NODE) {
                const tag = tagOf(child);
                if (tag === 'BR') parts.push('\n');
                else if (tag !== 'SCRIPT' && tag !== 'STYLE' && tag !== 'TEMPLATE') walk(child);
            }
        }
    })(el);
    return parts.join('').split('\n').map(l => l.trim()).join('\n').trim();
}

const isLeafy = (el) => Array.from(el.children).every(c => INLINE_TAGS.has(tagOf(c)));
const isEditableLeaf = (el) => Array.from(el.children).every(c => tagOf(c) === 'BR');

function textLeaves(item) {
    if (isLeafy(item) && readText(item)) return [item];
    const out = [];
    (function walk(node) {
        for (const child of node.children) {
            if (isRuntimeInjected(child) || SKIP_TAGS.has(tagOf(child)) || child.getAttribute('aria-hidden') === 'true') continue;
            if (isLeafy(child)) { if (readText(child)) out.push(child); }
            else walk(child);
        }
    })(item);
    return out;
}

function labelFor(el) {
    const tag = tagOf(el);
    if (tag === 'BLOCKQUOTE') return 'Quote';
    if (tag === 'CITE') return 'Author';
    if (/^H[1-6]$/.test(tag)) return 'Title';
    if (tag === 'A' || tag === 'BUTTON') return 'Button';
    return 'Text';
}

// --- recognition ---

function imageOf(item) {
    const candidates = [...(tagOf(item) === 'IMG' ? [item] : []), ...item.querySelectorAll('img')];
    return candidates.find(img => img.getAttribute('aria-hidden') !== 'true' && !img.closest('.splide__slide--clone')) || null;
}

function lightboxLinkOf(el) {
    if (tagOf(el) === 'A' && el.hasAttribute('data-lightbox')) return el;
    const links = el.querySelectorAll('a[data-lightbox]');
    return links.length === 1 ? links[0] : null;
}

function splideSlides(root) {
    const list = root.querySelector('.splide__list');
    if (!list) return [];
    return Array.from(list.children).filter(c => tagOf(c) === 'LI' && c.classList.contains('splide__slide') && !isRuntimeInjected(c));
}

const galleryItems = (root) => realChildren(root).filter(c => lightboxLinkOf(c));
const isImageSlide = (slide) => !!imageOf(slide) && readText(slide).length < TEXT_SLIDE_MIN_CHARS;

export function detectKind(root) {
    if (!root || !root.classList) return null;
    if (root.classList.contains('splide')) {
        const slides = splideSlides(root);
        if (!slides.length) return null;
        const images = slides.filter(isImageSlide).length;
        return images * 2 > slides.length ? 'slider' : 'text-slider';
    }
    const n = galleryItems(root).length;
    if (n >= 2 || (n >= 1 && root.getAttribute('data-media-collection') === 'lightbox')) return 'gallery';
    return null;
}

/** The component containing `el` ({root, kind}) or null. A .splide ancestor wins over a gallery. */
export function findComponent(el) {
    const section = el?.closest?.('[data-section]');
    if (!section) return null;
    const splide = el.closest('.splide');
    if (splide && splide !== section && section.contains(splide)) {
        const kind = detectKind(splide);
        return kind ? { root: splide, kind } : null;
    }
    for (let node = el; node && node !== section; node = node.parentElement) {
        if (detectKind(node) === 'gallery') return { root: node, kind: 'gallery' };
    }
    return null;
}

export function itemsOf(comp) {
    return comp.kind === 'gallery' ? galleryItems(comp.root) : splideSlides(comp.root);
}

export function itemFields(item) {
    return {
        image: imageOf(item),
        link: lightboxLinkOf(item),
        texts: textLeaves(item).map(el => ({ el, editable: isEditableLeaf(el), value: readText(el), label: labelFor(el) })),
    };
}

export function minItems(comp) {
    return comp.kind === 'gallery' && comp.root.getAttribute('data-media-collection') !== 'lightbox' ? 2 : 1;
}

export function componentLabel(comp) {
    if (comp.kind === 'slider') return { title: 'Image slider', noun: 'images' };
    if (comp.kind === 'text-slider') return { title: 'Slider', noun: 'slides' };
    return { title: 'Gallery', noun: 'images' };
}

/** Raw stored HTML can be swapped in only when it has no Django template syntax to render. */
export function canSwapInPlace(html) {
    return !!html && !/\{[{%]/.test(html);
}

// --- slider settings (data-splide) ---

export function readSliderOptions(root) {
    const raw = root.getAttribute('data-splide');
    if (!raw) return { ok: true, opts: {} };
    try {
        const opts = JSON.parse(raw);
        return opts && typeof opts === 'object' && !Array.isArray(opts) ? { ok: true, opts } : { ok: false, opts: {} };
    } catch (_) {
        return { ok: false, opts: {} };
    }
}

function nearestSpeed(ms) {
    let best = 'normal';
    for (const [name, value] of Object.entries(SPEED_PRESETS)) {
        if (Math.abs(value - ms) < Math.abs(SPEED_PRESETS[best] - ms)) best = name;
    }
    return best;
}

function breakpointKeys(bps) {
    const keys = Object.keys(bps || {}).filter(k => /^\d+$/.test(k)).map(Number).sort((a, b) => a - b);
    const mobile = keys.find(k => k <= 800) ?? 768;
    const tablet = keys.filter(k => k > mobile && k <= 1280).pop() ?? 1024;
    return { mobile: String(mobile), tablet: String(tablet) };
}

export function settingsFromOptions(opts) {
    const type = opts.type || 'slide';
    const perPage = opts.perPage || 1;
    const bps = opts.breakpoints || {};
    const keys = breakpointKeys(bps);
    return {
        effect: type === 'fade' ? 'fade' : 'slide',
        loop: type === 'loop' || !!opts.rewind,
        autoplay: !!opts.autoplay,
        seconds: Math.max(1, Math.round((opts.interval ?? 5000) / 1000)),
        speed: nearestSpeed(opts.speed ?? 400),
        arrows: opts.arrows !== false,
        dots: opts.pagination !== false,
        pauseOnHover: opts.pauseOnHover !== false,
        multi: type !== 'fade' && (perPage > 1 || Object.keys(bps).length > 0),
        perPage,
        tablet: bps[keys.tablet]?.perPage ?? perPage,
        mobile: bps[keys.mobile]?.perPage ?? 1,
    };
}

/** The data-splide changes for the server (null deletes a key). */
export function settingsChanges(s, opts) {
    const c = {};
    if (s.effect === 'fade') { c.type = 'fade'; c.rewind = !!s.loop; }
    else if (s.loop) { c.type = 'loop'; c.rewind = null; }
    else { c.type = 'slide'; c.rewind = false; }
    c.autoplay = !!s.autoplay;
    c.interval = s.seconds * 1000;
    c.speed = SPEED_PRESETS[s.speed] ?? 800;
    c.arrows = !!s.arrows;
    c.pagination = !!s.dots;
    c.pauseOnHover = !!s.pauseOnHover;
    if (s.multi && s.effect !== 'fade') {
        c.perPage = s.perPage;
        const bps = JSON.parse(JSON.stringify(opts.breakpoints || {}));
        const keys = breakpointKeys(bps);
        bps[keys.tablet] = { ...(bps[keys.tablet] || {}), perPage: s.tablet };
        bps[keys.mobile] = { ...(bps[keys.mobile] || {}), perPage: s.mobile };
        c.breakpoints = bps;
    }
    return c;
}
```

- [ ] **Step 5: Run the harness to verify pass** — reload `http://localhost:8765/editor_v2/tests/js/components_test.html`.
Expected: `document.title` is `PASS <n>` and `#out` says `all <n> passed`. If a fixture assertion fails, fix `components.js` (never the fixture: the Python side already passes against it).

- [ ] **Step 6: Commit**

```bash
cd ~/Documents/djangopress-sites/djangopress
git add src/djangopress/editor_v2/static/editor_v2/js/lib/components.js src/djangopress/editor_v2/static/editor_v2/js/lib/dom.js src/djangopress/editor_v2/tests/js
git commit -m "feat(editor): components.js — structural recognition and slider settings mapping, with browser harness

Claude-Session: https://claude.ai/code/session_01WSpzVT1ezgnAA6UbDJmNtS"
```

---

### Task 7: Client plumbing and bug fixes

**Files:**
- Modify: `templates/base.html:101-127` (Splide mount, asset versions)
- Modify: `static/js/lightbox.js:136-153`
- Modify: `editor_v2/static/editor_v2/js/lib/dom.js` (`initDynamicComponents`)
- Modify: `editor_v2/static/editor_v2/js/modules/changes.js` (`save`, `findElement`, export `saveNow`)
- Modify: `editor_v2/static/editor_v2/js/lib/structural.js` (`run`)
- Modify: `editor_v2/static/editor_v2/js/modules/history.js` (`init`)
- Modify: `editor_v2/static/editor_v2/js/modules/sidebar.js:144,331,465,580,642,926`, `modules/selection.js:132`, `modules/images-panel.js:66`
- Modify: `editor_v2/static/editor_v2/js/modules/image-picker.js` (`applyImage`, upload → `imageId`)

**Interfaces:**
- Produces: `saveNow(): Promise<boolean>` exported from `modules/changes.js`; events `history:refresh` (no payload) and `toast:show` (`{text, withUndo}`) handled by `history.js`; every mounted Splide root keeps its instance at `el.__splide`; attribute changes may carry `imageId`.

- [ ] **Step 1: `base.html`** — replace the Splide mount script and bump the asset versions:

```html
    <script>
      document.addEventListener('DOMContentLoaded', function() {
        document.querySelectorAll('.splide').forEach(function(el) {
          el.__splide = new Splide(el).mount();
        });
      });
    </script>
```

In the same file change `editor_v2/css/editor.css?v=22` → `?v=23` and `editor_v2/js/editor.js' %}?v=36` → `?v=37`.

- [ ] **Step 2: `static/js/lightbox.js`** — inside the `[data-lightbox]` click listener, right after `e.preventDefault();` add:

```js
            // Editor v2: clicking selects the image, it must not open the overlay.
            if (window.EDITOR_CONFIG) return;
```

In `dom.js` `initDynamicComponents`: store the instance (`el.__splide = new window.Splide(el).mount();`) and add the same `if (window.EDITOR_CONFIG) return;` after its `e.preventDefault();`.

- [ ] **Step 3: `changes.js`** — `save()` returns a boolean, `findElement` is clone-aware, attribute saves carry language and image id:

```js
import { resolveSelector } from '../lib/dom.js';
...
function findElement(selector) {
    return selector ? resolveSelector(selector) : null;
}
```

In `save()`: `return true;` in the "no pending changes" branch and after `console.log('[ev2] save: success');`; `return false;` at the end of the `catch`. In the attribute loop body add `language: language,` and `image_id: c.imageId || null,`. After `save`:

```js
/** Save pending edits now (used before structural and component operations). */
export function saveNow() {
    return save();
}
```

- [ ] **Step 4: `structural.js`** — save pending edits before any verb. Add `import { getPendingCount, saveNow } from '../modules/changes.js';` and make `run` start with:

```js
    if (getPendingCount() > 0 && !(await saveNow())) return null;
```

- [ ] **Step 5: `history.js`** — in `init()` before `await refresh();`:

```js
    unsubs.push(events.on('history:refresh', refresh));
    unsubs.push(events.on('toast:show', ({ text, withUndo }) => showToast(text, withUndo)));
```

- [ ] **Step 6: Clone-aware lookups.** Import `resolveSelector` where missing and replace:
  - `sidebar.js:144` `document.querySelector(sel)` → `resolveSelector(sel)`
  - `sidebar.js:331` same
  - `sidebar.js:926` same
  - `selection.js:132` same
  - `images-panel.js:66` `document.querySelector(selector)` → `resolveSelector(selector)`

Verify none remain: `grep -n "document.querySelector(sel\|document.querySelector(selector" src/djangopress/editor_v2/static/editor_v2/js -r` → no output.

- [ ] **Step 7: Runtime classes in the Design tab.** In `sidebar.js` import `isRuntimeClass` from `../lib/dom.js` and replace every `c.startsWith('ev2-')` with `isRuntimeClass(c)` and every `!c.startsWith('ev2-')` with `!isRuntimeClass(c)` (lines ~465, ~580-581, ~642-643). Rename the local `ev2Classes` to `runtimeClasses` in those two blocks. Verify: `grep -n "startsWith('ev2-')" src/djangopress/editor_v2/static/editor_v2/js/modules/sidebar.js` → no output.

- [ ] **Step 8: Image picker sends the library id with alt.** In `image-picker.js` change `applyImage(url, alt)` to `applyImage(url, alt, imageId = null)`, add `imageId` to the `alt` `change:attribute` payload, call `applyImage(selectedImage.url, selectedImage.alt, selectedImage.id)` in `applySelection` and `applyImage(img.url, img.alt_text || alt, img.id)` in `uploadAndSelect`.

- [ ] **Step 9: Verify in the browser.** Restart checkinfaro-v3's dev server (it runs `--noreload`): from the manager dashboard (`http://localhost:9000/site/checkinfaro-v3/`) Stop then Start, or `curl -X POST` the manager's `/site/checkinfaro-v3/stop/` and `/start/` with its CSRF cookie. Hard-reload `http://localhost:8134/pt/proposta-2/?edit=v2` (logged in; see Task 11 Step 1 for the session cookie), then check:
  - no console errors;
  - `document.querySelectorAll('.splide')` all have `__splide`;
  - clicking a gallery image selects it and no `#lightbox` overlay opens;
  - selecting a slide in a `type:"loop"` slider and saving a class change does not add `is-active` to the stored HTML (`sqlite3 db.sqlite3 "select html_content_i18n from core_page where id=6" | grep -c 'is-active'` stays 0).

- [ ] **Step 10: Run Python tests** (`manage.py test djangopress.editor_v2`, expected `OK`) and **commit**:

```bash
cd ~/Documents/djangopress-sites/djangopress
git add src/djangopress/templates/base.html src/djangopress/static/js/lightbox.js src/djangopress/editor_v2/static
git commit -m "fix(editor): clone-aware lookups, no runtime classes in the Design tab, no lightbox while editing, save before verbs

Claude-Session: https://claude.ai/code/session_01WSpzVT1ezgnAA6UbDJmNtS"
```

---

### Task 8: Image picker "pick" mode (single and multiple)

**Files:**
- Modify: `editor_v2/static/editor_v2/js/modules/image-picker.js`

**Interfaces:**
- Produces: `events.emit('image-picker:open', { mode: 'pick', multiple: boolean, onPick: (images) => void })`. `images` is `[{id, url, alt}]` (one entry unless `multiple`). Library tab: in multiple mode clicks toggle; the Select button reads "Add N images". Upload tab: one image.

- [ ] **Step 1: Implement.** Add module state next to `currentMode`:

```js
let pickCallback = null;
let pickMultiple = false;
let pickedImages = [];
```

In `open(data)`, before the `if (mode === 'img' …)` guard:

```js
    if (mode === 'pick') {
        pickCallback = typeof data.onPick === 'function' ? data.onPick : null;
        pickMultiple = !!data.multiple;
        pickedImages = [];
        if (!pickCallback) return;
    }
```

and extend the title line: `titleEl.textContent = mode === 'background' ? 'Select Background Image' : mode === 'pick' && pickMultiple ? 'Select Images' : 'Select Image';`

In `selectLibraryImage(item)`, at the top:

```js
    if (currentMode === 'pick' && pickMultiple) {
        const img = { id: item.dataset.imgId, url: item.dataset.url, alt: item.dataset.alt, title: item.dataset.title };
        const at = pickedImages.findIndex(p => p.id === img.id);
        if (at >= 0) { pickedImages.splice(at, 1); item.classList.remove('selected'); }
        else { pickedImages.push(img); item.classList.add('selected'); }
        setStatus(pickedImages.length ? `${pickedImages.length} selected` : '');
        updateButtons();
        return;
    }
```

`applySelection()` becomes:

```js
function applySelection() {
    if (currentMode === 'pick') {
        const images = (pickMultiple ? pickedImages : [selectedImage]).filter(Boolean)
            .map(i => ({ id: i.id, url: i.url, alt: i.alt || '' }));
        const cb = pickCallback;
        close();
        if (images.length && cb) cb(images);
        return;
    }
    if (!selectedImage || !currentEl) return;
    applyImage(selectedImage.url, selectedImage.alt, selectedImage.id);
    close();
}
```

In `uploadAndSelect()`: change the guard to `if (!selectedFile || (!currentEl && currentMode !== 'pick')) return;` and replace the "Apply the uploaded image" line with:

```js
        const img = result.image;
        if (currentMode === 'pick') {
            const cb = pickCallback;
            cache = null;
            close();
            if (cb) cb([{ id: img.id, url: img.url, alt: img.alt_text || alt }]);
            return;
        }
        applyImage(img.url, img.alt_text || alt, img.id);
```

`updateButtons()` — the select button:

```js
    if (selectB) {
        const n = currentMode === 'pick' && pickMultiple ? pickedImages.length : (selectedImage ? 1 : 0);
        selectB.disabled = n === 0;
        selectB.textContent = currentMode === 'pick' && pickMultiple ? (n ? `Add ${n} image${n === 1 ? '' : 's'}` : 'Add images') : 'Select Image';
    }
```

`close()` additionally resets `pickCallback = null; pickMultiple = false; pickedImages = [];`. In `switchModalTab`, also reset `pickedImages = [];` and remove `.selected` from grid items.

- [ ] **Step 2: Verify in the browser** (server restart not needed — static only; hard-reload the editor page). In the console:

```js
const { events } = await import('/static/editor_v2/js/lib/events.js');
events.emit('image-picker:open', { mode: 'pick', multiple: true, onPick: (imgs) => console.log('PICKED', imgs) });
```

Click two library images → button reads "Add 2 images" → click → console shows `PICKED` with two `{id, url, alt}`. Repeat with `multiple: false` → one image. Then check the normal "Change Image" on an `<img>` still works (src + alt applied, Save works).

- [ ] **Step 3: Commit**

```bash
cd ~/Documents/djangopress-sites/djangopress
git add src/djangopress/editor_v2/static/editor_v2/js/modules/image-picker.js
git commit -m "feat(editor): image picker pick mode with multi-select for the component panel

Claude-Session: https://claude.ai/code/session_01WSpzVT1ezgnAA6UbDJmNtS"
```

---

### Task 9: The component panel

**Files:**
- Create: `editor_v2/static/editor_v2/js/modules/component-panel.js`
- Modify: `editor_v2/static/editor_v2/js/modules/sidebar.js` (`renderContentTab`)
- Modify: `editor_v2/static/editor_v2/js/editor.js` (init)
- Modify: `editor_v2/static/editor_v2/css/editor.css` (append)

**Interfaces:**
- Consumes: `lib/components.js` (Task 6), `saveNow`/`getPendingCount` (Task 7), `history:refresh`/`toast:show` (Task 7), picker pick mode (Task 8), `duplicateElement` from `lib/structural.js`, endpoint (Task 4).
- Produces: `prependComponentCard(container, selectedEl) -> boolean`, `init()`, `destroy()`.

- [ ] **Step 1: Implement** `modules/component-panel.js`:

```js
/**
 * Component panel — a card at the top of the Content tab for a recognised
 * slider, text slider or lightbox gallery: item list (drag to reorder),
 * per-item fields, add / remove, slider settings. Every change is one
 * POST /component/ applied server-side to every language copy; the returned
 * HTML replaces the component in place (full reload as the fallback).
 */
import { events } from '../lib/events.js';
import { api } from '../lib/api.js';
import { getCssSelector } from '../lib/dom.js';
import { duplicateElement } from '../lib/structural.js';
import {
    findComponent, itemsOf, itemFields, componentLabel, minItems, readSliderOptions,
    settingsFromOptions, settingsChanges, canSwapInPlace,
} from '../lib/components.js';
import { getPendingCount, saveNow } from './changes.js';

const AFTER_RELOAD_KEY = 'ev2-after-reload';
const expanded = new Map();          // root selector -> open item index
let settingsOpen = false;
let settingsTimer = null;
let busy = false;

const cfg = () => window.EDITOR_CONFIG || {};
const esc = (s) => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

// --- rendering ---

export function prependComponentCard(container, selectedEl) {
    const comp = selectedEl ? findComponent(selectedEl) : null;
    if (!comp) return false;
    const rootSel = getCssSelector(comp.root);
    if (!rootSel) return false;
    const items = itemsOf(comp);
    const current = items.findIndex(it => it === selectedEl || it.contains(selectedEl));
    if (current >= 0) expanded.set(rootSel, current);
    const open = expanded.has(rootSel) ? Math.min(expanded.get(rootSel), items.length - 1) : -1;
    const { title, noun } = componentLabel(comp);

    const card = document.createElement('div');
    card.className = 'ev2-comp-card';
    card.innerHTML = `
        <div class="ev2-comp-head"><span class="ev2-comp-title">${esc(title)}</span><span class="ev2-comp-count">${items.length} ${esc(noun)}</span></div>
        <ol class="ev2-comp-list">${items.map((it, i) => rowHtml(comp, it, i, i === open, items.length)).join('')}</ol>
        <div class="ev2-comp-add">${addHtml(comp)}</div>
        ${comp.kind === 'gallery' ? '' : settingsHtml(comp)}
        <div class="ev2-comp-status" aria-live="polite"></div>`;
    container.insertBefore(card, container.firstChild);
    bindCard(card, comp, rootSel);
    return true;
}

function rowHtml(comp, item, i, isOpen, n) {
    const f = itemFields(item);
    const thumb = f.image
        ? `<img class="ev2-comp-thumb" src="${esc(f.image.getAttribute('src'))}" alt="">`
        : `<span class="ev2-comp-thumb ev2-comp-thumb-text">${i + 1}</span>`;
    const summary = f.texts[0]?.value || f.image?.getAttribute('alt') || `Item ${i + 1}`;
    return `<li class="ev2-comp-row${isOpen ? ' is-open' : ''}" data-index="${i}">
        <div class="ev2-comp-row-head" data-act="open">
            <span class="ev2-comp-grip" title="Drag to reorder" aria-hidden="true">⋮⋮</span>${thumb}
            <span class="ev2-comp-summary">${esc(summary.slice(0, 70))}</span>
        </div>
        ${isOpen ? `<div class="ev2-comp-fields">${fieldsHtml(comp, f, i, n)}</div>` : ''}
    </li>`;
}

function field(key, label, value, multiline) {
    const input = multiline
        ? `<textarea data-field="${key}" rows="${Math.min(6, Math.max(2, Math.ceil(value.length / 38)))}">${esc(value)}</textarea>`
        : `<input type="text" data-field="${key}" value="${esc(value)}">`;
    return `<label class="ev2-comp-field"><span>${esc(label)}</span>${input}</label>`;
}

function fieldsHtml(comp, f, i, n) {
    let h = '';
    if (f.image) {
        h += `<div class="ev2-comp-image"><img src="${esc(f.image.getAttribute('src'))}" alt="">
              <button type="button" class="ev2-btn-sm ev2-btn-sm-primary" data-act="replace">Replace image</button></div>`;
        h += field('alt', 'Alt text (describes the image)', f.image.getAttribute('alt') || '', false);
    }
    if (f.link && comp.kind === 'gallery') {
        h += field('caption', 'Caption (shown when the image is enlarged)', f.link.getAttribute('data-alt') || '', false);
    }
    f.texts.forEach((t, k) => {
        h += t.editable
            ? field(`text-${k}`, t.label, t.value, true)
            : `<div class="ev2-comp-field"><span>${esc(t.label)}</span><p class="ev2-comp-readonly">${esc(t.value)}</p>
               <p class="ev2-comp-hint">Formatted text — double-click it on the page to edit.</p></div>`;
    });
    const atMin = n <= minItems(comp);
    h += `<div class="ev2-comp-row-actions">
        <button type="button" class="ev2-btn-sm" data-act="up" ${i === 0 ? 'disabled' : ''}>↑ Earlier</button>
        <button type="button" class="ev2-btn-sm" data-act="down" ${i === n - 1 ? 'disabled' : ''}>↓ Later</button>
        <button type="button" class="ev2-btn-sm ev2-btn-sm-danger" data-act="remove" ${atMin ? 'disabled title="This is the minimum number of items"' : ''}>Remove</button>
    </div>`;
    return h;
}

function addHtml(comp) {
    if (comp.kind === 'text-slider') {
        return `<button type="button" class="ev2-btn-sm ev2-btn-sm-primary" data-act="add-text">+ Add slide</button>
                <div class="ev2-comp-addform" hidden></div>`;
    }
    return `<button type="button" class="ev2-btn-sm ev2-btn-sm-primary" data-act="add-images">+ Add images</button>`;
}

function settingsHtml(comp) {
    const { ok, opts } = readSliderOptions(comp.root);
    if (!ok) return `<div class="ev2-comp-settings"><p class="ev2-comp-hint">These slider settings can't be edited here.</p></div>`;
    const s = settingsFromOptions(opts);
    const check = (k, label) => `<label class="ev2-comp-check"><input type="checkbox" data-set="${k}" ${s[k] ? 'checked' : ''}> ${label}</label>`;
    const num = (k, label, min, max) => `<label class="ev2-comp-num"><span>${label}</span><input type="number" data-set="${k}" min="${min}" max="${max}" value="${s[k]}"></label>`;
    const opt = (v, label, cur) => `<option value="${v}" ${cur === v ? 'selected' : ''}>${label}</option>`;
    return `<details class="ev2-comp-settings" ${settingsOpen ? 'open' : ''}>
        <summary>Slider settings</summary>
        <label class="ev2-comp-num"><span>Effect</span><select data-set="effect">${opt('slide', 'Slide', s.effect)}${opt('fade', 'Fade', s.effect)}</select></label>
        ${check('loop', 'Loop back to the start')}
        ${check('autoplay', 'Play automatically')}
        ${num('seconds', 'Seconds per slide', 1, 30)}
        <label class="ev2-comp-num"><span>Transition</span><select data-set="speed">${opt('slow', 'Slow', s.speed)}${opt('normal', 'Normal', s.speed)}${opt('fast', 'Fast', s.speed)}</select></label>
        ${check('arrows', 'Arrows')}
        ${check('dots', 'Dots')}
        ${check('pauseOnHover', 'Pause on hover')}
        ${s.multi && s.effect !== 'fade' ? `<div class="ev2-comp-perrow"><span>Items per row</span>
            ${num('perPage', 'Desktop', 1, 8)}${num('tablet', 'Tablet', 1, 8)}${num('mobile', 'Mobile', 1, 8)}</div>` : ''}
    </details>`;
}

// --- interaction ---

function afterIndex(rootSel, n) {
    const i = expanded.get(rootSel);
    return Number.isInteger(i) && i >= 0 && i < n ? i : n - 1;
}

function bindCard(card, comp, rootSel) {
    card.addEventListener('click', (e) => {
        const btn = e.target.closest('[data-act]');
        if (!btn || btn.disabled || busy) return;
        const row = btn.closest('.ev2-comp-row');
        const i = row ? Number(row.dataset.index) : null;
        const n = itemsOf(comp).length;
        switch (btn.dataset.act) {
            case 'open': return focusItem(comp, rootSel, i);
            case 'up': return move(comp, n, i, -1);
            case 'down': return move(comp, n, i, 1);
            case 'remove':
                if (confirm('Remove this item? You can undo it afterwards.')) runOp(comp, 'remove', { index: i });
                return;
            case 'replace': return pickImages(false, imgs => runOp(comp, 'replace_image', { index: i, image: imgs[0] }, i));
            case 'add-images': return pickImages(true, imgs => runOp(comp, 'add_images', { after: afterIndex(rootSel, n), images: imgs }));
            case 'add-text': return showAddForm(card, comp, rootSel);
            case 'add-text-submit': return submitAddForm(card, comp, rootSel);
            case 'add-text-cancel': card.querySelector('.ev2-comp-addform').hidden = true; return;
        }
    });
    card.addEventListener('change', (e) => {
        const input = e.target.closest('[data-field]');
        if (input) {
            const i = Number(input.closest('.ev2-comp-row').dataset.index);
            const key = input.dataset.field;
            if (key.startsWith('text-')) {
                if (!input.value.trim()) { alert("Text can't be empty — remove the item instead."); return; }
                runOp(comp, 'update_item', { index: i, texts: { [key.slice(5)]: input.value } }, i);
            } else {
                runOp(comp, 'update_item', { index: i, [key]: input.value }, i);
            }
            return;
        }
        if (e.target.closest('[data-set]')) scheduleSettings(card, comp, rootSel);
    });
    card.querySelector('details.ev2-comp-settings')?.addEventListener('toggle', (e) => { settingsOpen = e.target.open; });
    bindDrag(card, comp);
}

function bindDrag(card, comp) {
    let from = null;
    card.querySelectorAll('.ev2-comp-row').forEach(row => {
        const grip = row.querySelector('.ev2-comp-grip');
        grip.addEventListener('mousedown', () => row.setAttribute('draggable', 'true'));
        row.addEventListener('dragstart', (e) => {
            from = Number(row.dataset.index);
            row.classList.add('is-dragging');
            e.dataTransfer.effectAllowed = 'move';
        });
        row.addEventListener('dragend', () => {
            row.removeAttribute('draggable');
            row.classList.remove('is-dragging');
            card.querySelectorAll('.is-drop-target').forEach(r => r.classList.remove('is-drop-target'));
        });
        row.addEventListener('dragover', (e) => { if (from !== null) { e.preventDefault(); row.classList.add('is-drop-target'); } });
        row.addEventListener('dragleave', () => row.classList.remove('is-drop-target'));
        row.addEventListener('drop', (e) => {
            e.preventDefault();
            const to = Number(row.dataset.index);
            const start = from;
            from = null;
            if (start === null || start === to) return;
            const order = [...Array(itemsOf(comp).length).keys()];
            order.splice(start, 1);
            order.splice(to, 0, start);
            runOp(comp, 'reorder', { order }, to);
        });
    });
}

function focusItem(comp, rootSel, i) {
    const item = itemsOf(comp)[i];
    if (!item) return;
    expanded.set(rootSel, i);
    comp.root.__splide?.go(i);
    comp.root.scrollIntoView({ behavior: 'smooth', block: 'center' });
    const f = itemFields(item);
    events.emit('selection:request', f.image || f.texts[0]?.el || item);
}

function move(comp, n, i, delta) {
    const j = i + delta;
    if (j < 0 || j >= n) return;
    const order = [...Array(n).keys()];
    [order[i], order[j]] = [order[j], order[i]];
    runOp(comp, 'reorder', { order }, j);
}

function pickImages(multiple, onPick) {
    events.emit('image-picker:open', { mode: 'pick', multiple, onPick });
}

function showAddForm(card, comp, rootSel) {
    const items = itemsOf(comp);
    const after = afterIndex(rootSel, items.length);
    const f = itemFields(items[after]);
    const editable = f.texts.map((t, k) => ({ ...t, k })).filter(t => t.editable);
    if (!editable.length) {   // only formatted text: copy the slide, edit it on the page
        duplicateElement(getCssSelector(items[after]));
        return;
    }
    const form = card.querySelector('.ev2-comp-addform');
    form.innerHTML = editable.map(t => `<label class="ev2-comp-field"><span>${esc(t.label)}</span>
            <textarea data-new="${t.k}" rows="2" placeholder="${esc(t.value.slice(0, 80))}"></textarea></label>`).join('')
        + (f.image ? '<p class="ev2-comp-hint">The new slide starts with the same image — replace it after adding.</p>' : '')
        + `<div class="ev2-comp-row-actions">
             <button type="button" class="ev2-btn-sm ev2-btn-sm-primary" data-act="add-text-submit">Add</button>
             <button type="button" class="ev2-btn-sm" data-act="add-text-cancel">Cancel</button></div>`;
    form.hidden = false;
    form.querySelector('textarea')?.focus();
}

function submitAddForm(card, comp, rootSel) {
    const texts = {};
    for (const ta of card.querySelectorAll('[data-new]')) {
        if (!ta.value.trim()) { alert('Fill in every field.'); ta.focus(); return; }
        texts[ta.dataset.new] = ta.value.trim();
    }
    runOp(comp, 'add_text_item', { after: afterIndex(rootSel, itemsOf(comp).length), texts });
}

function scheduleSettings(card, comp, rootSel) {
    clearTimeout(settingsTimer);
    settingsTimer = setTimeout(() => {
        const { opts } = readSliderOptions(comp.root);
        const s = settingsFromOptions(opts);
        for (const key of Object.keys(s)) {
            const input = card.querySelector(`[data-set="${key}"]`);
            if (!input) continue;
            if (input.type === 'checkbox') s[key] = input.checked;
            else if (input.type === 'number') {
                const v = parseInt(input.value, 10);
                s[key] = Number.isFinite(v) ? Math.min(Number(input.max), Math.max(Number(input.min), v)) : s[key];
            } else s[key] = input.value;
        }
        runOp(comp, 'set_settings', { settings: settingsChanges(s, opts) }, afterIndex(rootSel, itemsOf(comp).length));
    }, 600);
}

// --- server round trip ---

function setBusy(on, text = '') {
    busy = on;
    const card = document.querySelector('.ev2-comp-card');
    card?.classList.toggle('is-busy', on);
    const status = card?.querySelector('.ev2-comp-status');
    if (status) status.textContent = text;
}

function toastText(res) {
    let text = res.label || 'Saved';
    const up = (list) => list.map(l => l.toUpperCase()).join(', ');
    if (res.translated_languages?.length) text += ` · translated to ${up(res.translated_languages)} (review it there)`;
    if (res.untranslated_languages?.length) text += ` · not translated to ${up(res.untranslated_languages)} — edit it there`;
    return text;
}

function swapRoot(oldRoot, html) {
    const tpl = document.createElement('template');
    tpl.innerHTML = html.trim();
    const fresh = tpl.content.firstElementChild;
    if (!fresh) return null;
    try { oldRoot.__splide?.destroy(true); } catch (_) { /* already gone */ }
    oldRoot.replaceWith(fresh);
    if (fresh.classList.contains('splide') && window.Splide) {
        fresh.__splide = new window.Splide(fresh).mount();
        fresh.__splide.Components?.Autoplay?.pause();
    }
    return fresh;
}

async function runOp(comp, op, args, focus = null) {
    if (busy) return;
    if (getPendingCount() > 0 && !(await saveNow())) return;
    const c = cfg();
    const rootSel = getCssSelector(comp.root);
    const body = {
        page_id: c.pageId, language: c.language, root: rootSel, kind: comp.kind,
        count: itemsOf(comp).length, op, args,
    };
    if (c.contentTypeId && c.objectId) { body.content_type_id = c.contentTypeId; body.object_id = c.objectId; }
    const translating = ['add_text_item', 'add_images', 'replace_image'].includes(op) && (c.languages || []).length > 1;
    setBusy(true, translating ? 'Saving and translating…' : 'Saving…');
    let res;
    try {
        res = await api.post('/component/', body);
    } catch (err) {
        setBusy(false);
        alert(err.message || 'Could not save');
        return;
    }
    setBusy(false);
    if (!res.success) { alert(res.error || 'Could not save'); return; }

    const index = focus ?? res.index ?? 0;
    expanded.set(rootSel, index);
    if (res.skipped_languages?.length) {
        alert(`Saved, but not in ${res.skipped_languages.join(', ').toUpperCase()}: this part of the page is different there.`);
    }
    const fresh = canSwapInPlace(res.html) ? swapRoot(comp.root, res.html) : null;
    if (!fresh) {
        try {
            sessionStorage.setItem(AFTER_RELOAD_KEY, JSON.stringify({ selector: rootSel }));
            sessionStorage.setItem('ev2-toast-pending', JSON.stringify({ label: toastText(res) }));
        } catch (_) { /* private mode */ }
        window.location.reload();
        return;
    }
    events.emit('history:refresh');
    events.emit('toast:show', { text: toastText(res), withUndo: true });
    const next = { root: fresh, kind: comp.kind };
    const item = itemsOf(next)[index];
    fresh.__splide?.go(index);
    const f = item ? itemFields(item) : null;
    events.emit('selection:request', f?.image || f?.texts[0]?.el || item || fresh);
}

// --- lifecycle ---

export function init() {
    // Autoplay would move the slide being edited out from under the cursor.
    document.querySelectorAll('.editor-v2-content .splide').forEach(el => el.__splide?.Components?.Autoplay?.pause());
}

export function destroy() {
    clearTimeout(settingsTimer);
    expanded.clear();
}
```

- [ ] **Step 2: Wire it.** In `sidebar.js`: `import { findComponent } from '../lib/components.js';` and `import { prependComponentCard } from './component-panel.js';`. In `renderContentTab()` replace `const collectionEl = findMediaCollection(selectedEl);` with `const collectionEl = findComponent(selectedEl) ? null : findMediaCollection(selectedEl);` and replace `prependRepeatPanel(c);` with:

```js
    if (!prependComponentCard(c, selectedEl)) prependRepeatPanel(c);
```

In `editor.js`: `import * as componentPanel from './modules/component-panel.js';` and call `componentPanel.init();` after `viewport.init();`.

- [ ] **Step 3: Styles** — append to `editor.css`:

```css
/* --- Component panel (sliders, galleries) --- */
.ev2-comp-card { border: 1px solid var(--ev2-border); border-radius: 8px; padding: 10px; margin-bottom: 12px; background: var(--ev2-bg); }
.ev2-comp-card.is-busy { opacity: .6; pointer-events: none; }
.ev2-comp-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px; }
.ev2-comp-title { font-weight: 600; font-size: 13px; color: var(--ev2-text); }
.ev2-comp-count { font-size: 12px; color: var(--ev2-text-secondary); }
.ev2-comp-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.ev2-comp-row { border: 1px solid var(--ev2-border-light); border-radius: 6px; background: var(--ev2-bg); }
.ev2-comp-row.is-open { border-color: var(--ev2-primary); box-shadow: 0 0 0 2px var(--ev2-primary-alpha); }
.ev2-comp-row.is-dragging { opacity: .4; }
.ev2-comp-row.is-drop-target { border-color: var(--ev2-primary); background: var(--ev2-primary-light); }
.ev2-comp-row-head { display: flex; align-items: center; gap: 8px; padding: 6px; cursor: pointer; }
.ev2-comp-row-head:hover { background: var(--ev2-bg-hover); }
.ev2-comp-grip { cursor: grab; color: var(--ev2-border-dark); font-size: 12px; letter-spacing: -2px; user-select: none; }
.ev2-comp-thumb { width: 40px; height: 30px; object-fit: cover; border-radius: 4px; flex: none; background: var(--ev2-bg-subtle); }
.ev2-comp-thumb-text { display: flex; align-items: center; justify-content: center; font-size: 11px; color: var(--ev2-text-secondary); }
.ev2-comp-summary { font-size: 12px; color: var(--ev2-text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ev2-comp-fields { padding: 4px 8px 10px; display: flex; flex-direction: column; gap: 8px; }
.ev2-comp-image { display: flex; align-items: center; gap: 8px; }
.ev2-comp-image img { width: 96px; height: 64px; object-fit: cover; border-radius: 4px; }
.ev2-comp-field { display: flex; flex-direction: column; gap: 3px; font-size: 12px; color: var(--ev2-text-secondary); }
.ev2-comp-field input, .ev2-comp-field textarea { font: inherit; font-size: 13px; color: var(--ev2-text); border: 1px solid var(--ev2-border); border-radius: 4px; padding: 5px 7px; resize: vertical; }
.ev2-comp-readonly { margin: 0; font-size: 12px; color: var(--ev2-text); }
.ev2-comp-hint { margin: 0; font-size: 11px; color: var(--ev2-text-secondary); }
.ev2-comp-row-actions { display: flex; gap: 6px; flex-wrap: wrap; }
.ev2-comp-add { margin-top: 8px; display: flex; flex-direction: column; gap: 8px; }
.ev2-comp-addform { display: flex; flex-direction: column; gap: 8px; }
.ev2-comp-settings { margin-top: 10px; border-top: 1px solid var(--ev2-border-light); padding-top: 8px; font-size: 12px; }
.ev2-comp-settings summary { cursor: pointer; font-weight: 600; color: var(--ev2-text); margin-bottom: 6px; }
.ev2-comp-check { display: flex; align-items: center; gap: 6px; margin: 4px 0; color: var(--ev2-text); }
.ev2-comp-num { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin: 4px 0; color: var(--ev2-text); }
.ev2-comp-num input { width: 64px; }
.ev2-comp-perrow { margin-top: 6px; }
.ev2-comp-status { font-size: 11px; color: var(--ev2-text-secondary); min-height: 14px; margin-top: 6px; }
```

- [ ] **Step 4: Verify in the browser** (hard-reload `http://localhost:8134/pt/proposta-2/?edit=v2`; take a copy of page 6 first as in Task 11 Step 1):
  - Click an image in "foto-vieiras" → the Content tab shows "Image slider · N images", the clicked slide expanded, the element's image fields below the card.
  - Click row 3 → the slider moves to slide 3 and that image is selected.
  - Drag row 1 below row 2 → toast "Reordered items", thumbnails in the new order, no page reload; reload the page → order persists.
  - "↑ Earlier" / "↓ Later" work; "Remove" asks for confirmation, removes, the toast has Undo, Undo restores.
  - Slider settings: Effect → Slide, Loop on → the slider remounts as a sliding loop within ~1 s; reload → persists.
  - Testimonials slider ("testemunhos"): card says "Slider · N slides"; edit the author text → saved in PT only (switch to EN: unchanged); "+ Add slide" → form, Add → new slide appears after the open one; EN shows a translated version (or the "not translated" toast when no AI key).
  - No console errors throughout.

- [ ] **Step 5: Commit**

```bash
cd ~/Documents/djangopress-sites/djangopress
git add src/djangopress/editor_v2/static src/djangopress/templates/base.html
git commit -m "feat(editor): component panel for sliders, text sliders and galleries

Claude-Session: https://claude.ai/code/session_01WSpzVT1ezgnAA6UbDJmNtS"
```

---

### Task 10: `check_site --only components`, AI registry, skills, docs

**Files:**
- Modify: `editor_v2/components.py` (append `audit`)
- Modify: `core/management/commands/check_site.py`
- Test: `core/tests/test_check_site.py` (append), `editor_v2/tests/test_components.py` (append)
- Modify: `ai/utils/components/__init__.py:124-126`
- Modify: `skills/djangopress-html-reference/SKILL.md` (after the "Lightbox gallery pattern" paragraph), `skills/edit-site/SKILL.md`, `skills/djangopress-architecture/SKILL.md:116`, `CLAUDE.md` (Key Reminders, after line 181)

**Interfaces:**
- Produces: `components.audit(soup) -> list[str]`; `check_site` has check `components` whose problems are **warnings** (printed, in JSON under `warnings`, exit code unaffected).

- [ ] **Step 1: Write the failing tests.** Append to `editor_v2/tests/test_components.py`:

```python
import importlib


class AuditTest(SimpleTestCase):
    def test_fixtures_have_no_problems(self):
        for p in FIXTURES.glob('*.html'):
            with self.subTest(fixture=p.stem):
                self.assertEqual(components.audit(load(p.stem)), [])

    def test_reports_broken_slider_and_scattered_gallery(self):
        soup = BeautifulSoup(
            '<section data-section="a"><div class="splide" data-splide="{bad"><ul><li>x</li></ul></div></section>'
            '<section data-section="b"><div><a href="/1.jpg" data-lightbox="z"><img src="/1.jpg"/></a></div>'
            '<p>t</p><div><div><a href="/2.jpg" data-lightbox="z"><img src="/2.jpg"/></a></div></div></section>',
            'html.parser')
        problems = components.audit(soup)
        self.assertEqual(len(problems), 3, problems)
        self.assertTrue(any('no slides' in p for p in problems))
        self.assertTrue(any('not a JSON object' in p for p in problems))
        self.assertTrue(any('lightbox group "z"' in p for p in problems))


class RegistryExamplesTest(SimpleTestCase):
    """The AI component docs must produce markup the editor panel recognises."""

    def test_examples_are_recognised(self):
        import re
        for name in ('slider', 'carousel', 'lightbox'):
            module = importlib.import_module(f'djangopress.ai.utils.components.{name}')
            blocks = re.findall(r'```html\n(.*?)```', module.FULL_REFERENCE, re.S)
            self.assertTrue(blocks, name)
            for block in blocks:
                soup = BeautifulSoup(f'<section data-section="x">{block}</section>', 'html.parser')
                with self.subTest(component=name, block=block[:60]):
                    self.assertEqual(components.audit(soup), [])
                    for root in soup.select('.splide'):
                        self.assertIsNotNone(components.detect(root))
```

Append to `core/tests/test_check_site.py` (reuse that file's existing setup helpers for creating a Page — read its first 60 lines and follow the same pattern):

```python
class ComponentsCheckTest(TestCase):
    def test_component_problems_are_warnings(self):
        SiteSettings.load()
        Page.objects.create(
            title_i18n={'pt': 'X'}, slug_i18n={'pt': 'x'}, is_active=True,
            html_content_i18n={'pt': '<section data-section="a" id="a"><div class="splide" data-splide="{bad">'
                                     '<div class="splide__track"><ul class="splide__list"><li class="splide__slide">x</li>'
                                     '</ul></div></div></section>'},
        )
        checker = SiteChecker(only=['components'])
        failures = checker.run()
        self.assertEqual(failures, [])
        self.assertEqual(len(checker.warnings), 1)
        self.assertEqual(checker.warnings[0]['check'], 'components')
```

(import `SiteChecker` from `djangopress.core.management.commands.check_site` if the file doesn't already.)

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/Documents/djangopress-sites/checkinfaro-v3 && .venv/bin/python manage.py test djangopress.editor_v2.tests.test_components djangopress.core.tests.test_check_site 2>&1 | tail -4`
Expected: ERROR — no attribute `audit` / `warnings`. If `RegistryExamplesTest` fails on a real example (not just on the missing `audit`), fix that example in `ai/utils/components/<name>.py` so it matches the shapes in Step 4, not the test.

- [ ] **Step 3: Implement `audit`** (append to `components.py`):

```python
# --- audit (check_site) ----------------------------------------------------------

def _where(el):
    section = el.find_parent(attrs={'data-section': True})
    return f' in section "{section["data-section"]}"' if section else ''


def audit(soup):
    """Problems that stop the editor's component panel from managing a slider or gallery."""
    problems = []
    for root in soup.select('.splide'):
        if not splide_slides(root):
            problems.append(f'slider{_where(root)} has no slides (needs .splide__track > ul.splide__list > li.splide__slide)')
        raw = root.get('data-splide')
        if raw:
            try:
                ok = isinstance(json.loads(raw), dict)
            except ValueError:
                ok = False
            if not ok:
                problems.append(f'slider{_where(root)}: data-splide is not a JSON object')
    groups = {}
    for a in soup.select('a[data-lightbox]'):
        groups.setdefault(a.get('data-lightbox'), []).append(a)
    for name, links in groups.items():
        if len(links) >= 2 and any(find_for(a) is None for a in links):
            problems.append(f'lightbox group "{name}": items are not siblings in one container — the editor cannot manage them')
    return problems
```

In `check_site.py`:
- add `'components'` to `CHECK_NAMES` and to the module docstring's "Checks:" list;
- `from djangopress.editor_v2 import components as editor_components`;
- in `SiteChecker.__init__` add `self.warnings = []`; add `def warn(self, check, message): self.warnings.append({'check': check, 'message': message})`;
- call `self.check_components()` in `run()` after `self.check_dom_parity()`;
- add:

```python
    def check_components(self):
        """Sliders / galleries the editor's component panel can't manage. Warnings only."""
        if not self.enabled('components'):
            return
        for page in Page.objects.filter(is_active=True):
            for lang, html in sorted((page.html_content_i18n or {}).items()):
                if not html:
                    continue
                for problem in editor_components.audit(soup_of(html)):
                    self.warn('components', f'page {page.id} ({lang}): {problem}')
```

- in `Command.handle`: keep `checker = SiteChecker(only=only or None)` / `failures = checker.run()`; JSON output becomes `{'ok': not failures, 'failures': failures, 'warnings': checker.warnings}`; in human output print, before the FAIL/OK line, `WARN — {n} warning(s):` followed by `  [{check}] {message}` lines when there are warnings.

- [ ] **Step 4: Docs and prompts.**

`ai/utils/components/__init__.py` lines 124-126 — use names that exist:

```python
            '- User wants a single-image slider: ["slider"]\n'
            '- User wants a multi-card carousel: ["carousel"]\n'
            '- User wants a gallery with lightbox: ["lightbox"]\n'
            '- User wants tabs and an accordion: ["tabs", "accordion"]\n\n'
```

`skills/djangopress-html-reference/SKILL.md` — after the "Lightbox gallery pattern" block add:

```markdown
**Editable components (editor panel):** the inline editor gives sliders and galleries a panel (thumbnails, drag to reorder, replace/add/remove, slider settings) when they use these shapes — keep to them:
- **Slider:** `.splide > .splide__track > ul.splide__list > li.splide__slide`, options in `data-splide='{…}'` (valid JSON, single-quoted attribute). Image slides hold one `<img>` (a short caption is fine); text slides (testimonials, cards) hold their text in plain elements — `blockquote`, `p`, `h3`, `cite` — one per field, with only `<br>` inside if staff should edit it from the panel (inline formatting like `<strong>` makes that field read-only there).
- **Gallery:** the grid's direct children are the items; each item is, or contains exactly one, `<a href="full.jpg" data-lightbox="group" data-alt="Caption"><img …></a>`. Don't wrap some items differently from others.
- `data-media-collection` is optional. `check_site --only components` warns when a slider or lightbox group doesn't match.
```

`skills/edit-site/SKILL.md` — in the section about sliders/images (search for "Splide" or "lightbox"; if none, at the end of the images section) add one line:

```markdown
- Staff reorder, add and remove slides and gallery images themselves from the editor's component panel — don't assume slide order or count is fixed, and keep new sliders/galleries in the shapes from `djangopress-html-reference` ("Editable components").
```

`skills/djangopress-architecture/SKILL.md` — after line 116 add:

```markdown
- `POST /editor-v2/api/component/` — component panel operations on a slider / text slider / lightbox gallery (`reorder`, `remove`, `set_settings`, `replace_image`, `add_images`, `add_text_item`, `update_item`); recognition in `editor_v2/components.py` mirrored by `static/editor_v2/js/lib/components.js`; checkpointed, every language (update_item: current language), new text translated (staff)
```

`CLAUDE.md` — after line 181 ("Editor operations must create a `kind='checkpoint'` …") add:

```markdown
- **Editor component panel** (sliders, galleries) recognises components by structure in `editor_v2/components.py` and `editor_v2/static/editor_v2/js/lib/components.js`. Change the two together and keep `editor_v2/tests/fixtures/components/` passing on both sides (`test_components` + the browser harness `editor_v2/tests/js/components_test.html`).
```

- [ ] **Step 5: Run to verify pass**

Run: `cd ~/Documents/djangopress-sites/checkinfaro-v3 && .venv/bin/python manage.py test djangopress.editor_v2 djangopress.core 2>&1 | tail -4` → `OK`.
Then: `cd ~/Documents/djangopress-sites/checkinfaro-v3 && .venv/bin/python manage.py check_site --only components` → prints `OK` or `WARN` lines, exit code 0.

- [ ] **Step 6: Commit**

```bash
cd ~/Documents/djangopress-sites/djangopress
git add -A src/djangopress/editor_v2/components.py src/djangopress/editor_v2/tests src/djangopress/core src/djangopress/ai/utils/components src/djangopress/skills CLAUDE.md
git commit -m "feat(check_site): components check (warnings); docs and AI prompts for editable slider/gallery shapes

Claude-Session: https://claude.ai/code/session_01WSpzVT1ezgnAA6UbDJmNtS"
```

---

### Task 11: End-to-end verification on checkinfaro-v3

**Files:** none changed (unless a check fails — then fix in the owning task's files and commit with `fix(editor): …`).

- [ ] **Step 1: Protect page 6 and log in the test browser.**

```bash
cd ~/Documents/djangopress-sites/checkinfaro-v3
sqlite3 db.sqlite3 "select html_content_i18n from core_page where id=6" > "$TMPDIR/page6-before.json"
.venv/bin/python manage.py shell -c "
from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
u = get_user_model().objects.filter(is_superuser=True).order_by('id').first()
s = SessionStore(); s['_auth_user_id'] = str(u.pk); s['_auth_user_backend'] = 'django.contrib.auth.backends.ModelBackend'; s['_auth_user_hash'] = u.get_session_auth_hash(); s.create()
print(s.session_key)"
```

Set that key as the `sessionid` cookie for `localhost:8134` in the playwright-cli browser (see the playwright-cli skill), restart the dev server from the manager (Stop/Start), and open `http://localhost:8134/pt/proposta-2/?edit=v2`.

- [ ] **Step 2: Run the Task 9 Step 4 checklist end to end**, plus:
  - Gallery (any `a[data-lightbox]` grid on the page, or on home page 3 if page 6 has none): card "Gallery · N images", "+ Add images" with two picks → two new items after the open one, both languages (switch to EN), caption field edits `data-alt` in PT only.
  - "Replace image" on a slide → new image in PT and EN; EN alt comes from the library's EN alt or a translation.
  - Loop slider: after a reorder, clicking any visible slide selects a real slide (not a clone) — the card highlights the right row.
  - `manage.py check_site --only components,dom-parity` on checkinfaro-v3 → no failures.

- [ ] **Step 3: Restore page 6** so the user starts from their own content:

```bash
cd ~/Documents/djangopress-sites/checkinfaro-v3
.venv/bin/python manage.py shell -c "
import json, os
from djangopress.core.models import Page
p = Page.objects.get(pk=6); p.html_content_i18n = json.load(open(os.path.join(os.environ['TMPDIR'], 'page6-before.json'))); p._change_summary = 'Restored after component-panel testing'; p.save()"
```

- [ ] **Step 4: Full regression**

Run: `cd ~/Documents/djangopress-sites/checkinfaro-v3 && .venv/bin/python manage.py test djangopress 2>&1 | tail -4` → `OK`. Re-run the JS harness → `PASS <n>`.

- [ ] **Step 5: Hand over** — report to the user what was verified, with the URL `http://localhost:8134/pt/proposta-2/?edit=v2`, and that the engine branch `feature/editor-component-panels` is not merged (sites in production install `@main`).
