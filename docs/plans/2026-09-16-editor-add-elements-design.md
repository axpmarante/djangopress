# Editor v2 — Adding and Arranging Elements Without a Developer

**Date:** 2026-09-16
**Status:** Draft for review
**Repo:** djangopress (engine, `src/djangopress/editor_v2/`). No changes to djangopress-manager.
**Goal:** Let non-technical agency staff make quick structural and design changes in the inline editor (add, duplicate, move, remove, insert a section, apply simple style presets) without asking a developer, while keeping AI agents as first-class editors of the same content.

---

## Context

The inline editor already covers editing what exists: click to select, double-click to edit text, Content / Design / Structure tabs, image swap, section background / overlay / video, undo/redo, versions, language switch. The context menu offers Remove Element, Remove Section, AI Refine and Insert Section Before/After. Every change is a surgical patch of the stored HTML with BeautifulSoup, and removals are applied to every language copy.

What is missing is the other half of structural editing:

- Adding a section only works by describing it to the AI (three Gemini variations, apply, translate, reload). No catalogue of ready sections. The insertion "+" bars planned in `2026-02-16-add-section-design.md` were never built; only the right-click entry exists.
- There is no way to add an element inside a section: no duplicate, no "add another card", no add button / paragraph / image. The only path is "AI Refine", which rewrites the element.
- Nothing can be reordered: sections cannot move up or down, cards cannot move within a grid. The Structure tab is navigation only. No move endpoint exists.
- Media collections list images but cannot add or remove one.
- The Design tab exposes Tailwind class dropdowns for every non-section element. Sections get friendly controls; everything else speaks Tailwind.
- All structural and AI endpoints (`refine-*`, `apply-option`, `remove-section`, `remove-element`, `versions`) are `superuser_required`. Ordinary staff can only edit text, attributes and classes.
- Manual text edits are saved for the current language only. AI-applied changes are auto-translated; manual ones are not.

### Decisions already taken (discussion of 2026-09-16)

1. **HTML per language stays the single source of truth.** No JSON block model, no bidirectional compiler. A block model would cap design freedom and penalise the AI pipeline (mockup → design system → free HTML), which is the primary editing vector.
2. **Every structural operation is "insert / move / remove a node at an anchor", applied to all language copies** with BeautifulSoup, with a version snapshot, committed immediately through its own endpoint (never queued with pending text/class changes, because inserts shift `nth-child` indices of later siblings).
3. **The editor must work on un-annotated HTML.** Detection of repeatable groups is heuristic first. A lightweight annotation (`data-repeat`) is added only if Phase 0 measures real failures, and even then it is optional, minimal, documented in one sentence and validated by `check_site`.
4. **Deterministic verbs for the common cases, AI for the rest.** Duplicate, move, remove and primitives make no LLM call. The LLM is used only to translate an inserted catalogue section and for the existing "describe with AI" flow.
5. The only "compiler" is one-way and one-shot: catalogue section templates rendered with the site's design tokens at insertion time. The result is plain HTML and is never re-derived.

---

## Phase 0 — Measure the repeat-group heuristic

**Purpose:** decide, with numbers, whether annotations are needed before building "Add another".

**Heuristic (`findRepeatGroup(el)`):** walk up from `el` to the section root; at each level, look at the parent's children (excluding runtime-injected nodes); the first level where `current` has at least one sibling with the same tag and the same sorted class set is the repeat group, and `current` is the repeat item.

**Spike:** a management command or one-off script that opens every site's `db.sqlite3` under `~/Documents/djangopress-sites/`, parses every page's HTML for the default language, and reports per section: number of candidate groups, group sizes, and ambiguous cases (nested groups, groups of size 2 whose items differ in child structure, items with per-item class variations such as `md:col-span-2`). Output is a markdown table; nothing is written to the sites.

**Exit criteria:** heuristic finds the visually obvious groups (service cards, team members, testimonials, FAQ items, gallery slides, pricing tiers) on the existing sites with no false positives that would place "Add another" at the wrong level. If it fails on a class of sections, Phase 6 becomes mandatory for those and the failure mode is recorded here.

---

## Phase 1 — Structural verbs and permissions

### Backend (`editor_v2/api_views.py`, `editor_v2/urls.py`)

All endpoints follow the `remove_element` pattern: resolve the editable object (`_get_editable_object`), validate the selector in the current language, `create_version`, `_apply_structural_change_to_all_langs`, save, return `success` plus the selector of the affected node so the frontend can re-select after reload.

| Endpoint | Body | Behaviour |
|---|---|---|
| `POST api/duplicate-element/` | `page_id`, `selector` | `copy.copy(node)` inserted after the original, in every language copy. Any `id` attributes inside the clone are stripped (ids inside sections are not used by the editor; duplicates would break anchors). |
| `POST api/move-element/` | `page_id`, `selector`, `direction: 'up' \| 'down'` | Swap with previous / next sibling that is not runtime-injected, in every language copy. No-op with `success: true, moved: false` at the edges. |
| `POST api/insert-element/` | `page_id`, `selector`, `position: 'before' \| 'after' \| 'append'`, `html` | Insert a snippet relative to the anchor, identical in every language. Used by primitives (Phase 1) and later by the catalogue for in-section items. Snippet is sanitised: must parse to exactly one top-level element, no `<script>`, no `<section>`. |
| `POST api/duplicate-section/` | `page_id`, `section_name` | Clone the section after itself in every language, renaming `data-section` and `id` to the first free `name-2`, `name-3`, and rewriting any `href="#name"` inside the clone to the new anchor. |
| `POST api/move-section/` | `page_id`, `section_name`, `direction` | Swap with the adjacent `<section>` in every language. |

Rules shared by all:

- Validation happens on the current language; application on all languages. A language copy where the selector does not resolve is skipped (same as today), and the response lists skipped languages so the UI can warn.
- The version `change_summary` names the verb and the target (`Duplicated element in "services"`).
- No LLM calls.

### Frontend

- `lib/dom.js`: add `findRepeatGroup(el)` (Phase 0 heuristic) and `getRepeatItemLabel(group)` (a short label derived from the item's first heading or image alt, used in button text such as "Add another card").
- `modules/context-menu.js`: add **Duplicate**, **Move Up**, **Move Down** for any element inside a section, and **Duplicate Section**, **Move Section Up / Down** for sections. Keep the existing Remove entries. Items are enabled only when applicable (no Move Up on the first sibling).
- `modules/sidebar.js` Content tab: when the selected element is inside a repeat group, show a row at the top: `n items in this group` with buttons **Add another** (duplicates the group item that contains the selection), **Move left / right** and **Remove this one**. When the selection is a text or image inside an item, the buttons act on the enclosing item, not on the selection.
- `modules/sidebar.js` Structure tab: arrows next to each section for move up / down; the tree gains **+** on sections opening the Insert Section flow.
- Primitives: **Add** submenu in the context menu with **Paragraph**, **Heading**, **Button**, **Image**. Each inserts a minimal snippet after the selected element. Classes are copied from the nearest sibling of the same tag inside the section when one exists; otherwise a small default set. Image opens the existing image picker after insert. Text is a placeholder in the current language ("New paragraph"), and the element is selected and put into inline edit immediately.
- After any structural verb: reload the page (as today for remove and insert), then re-select the returned selector and scroll to it. In-place re-render without reload is a later improvement (Phase 5).

### Permissions

Today `remove-section`, `remove-element`, `apply-option`, `refine-*` and `versions` require `is_superuser`. The intended user for this work is agency staff, not superusers.

Proposal: a new decorator `editor_required` (`is_active and is_staff`) in `core/decorators.py`, applied to: `remove-section`, `remove-element`, `duplicate-*`, `move-*`, `insert-element`, `list_page_versions`, `get_page_version`. AI endpoints (`refine-*`, `apply-option`, `save-ai-*`) stay `superuser_required` for now; a follow-up can gate them with a setting if cost is acceptable.

**Decision needed:** confirm that "normal user" means `is_staff`, or whether a dedicated group/permission is preferred.

### Tests (`editor_v2/tests/`)

- Each endpoint: happy path on a two-language page; selector missing in one language is skipped and reported; version created; response selector resolves in the new HTML.
- Duplicate section: name uniqueness across repeated duplication (`x-2`, `x-3`), anchor rewrite.
- Move at edges is a no-op.
- `insert-element` rejects multi-root snippets, `<script>` and `<section>`.
- `findRepeatGroup` unit tests (JS, run in the existing test setup if any; otherwise a small Playwright check) on fixtures: 3-card grid, nested grid inside a card, FAQ list, slides with Splide clones present, single child (no group).

---

## Phase 2 — Discoverability

Everything in Phase 1 is reachable only by right-click, which non-technical users do not discover.

- **Insertion bars between sections.** On hover between two sections (and above the first / below the last), show a thin bar with a centred **+**. Clicking opens the Insert Section flow with the anchor set. This is the `section-inserter.js` behaviour described in the 2026-02-16 design and never built; the placeholder logic already exists, only the hover bars are new.
- **Floating element toolbar.** When an element is selected, a small toolbar above it: Duplicate, Move up, Move down, Delete, AI. It replaces nothing; the context menu stays as the full list.
- **Insert Section modal with two tabs:** *From catalogue* (Phase 3) and *Describe with AI* (current flow). Until Phase 3 lands, the modal is unchanged.
- Command palette entries for the new verbs, so keyboard users get them too.

---

## Phase 3 — Section catalogue

### Content

A set of section templates shipped with the engine, one file per pattern, in `editor_v2/templates/editor_v2/sections/`:

hero, features (3 columns), services (cards), about (image + text), testimonials, stats, team, gallery (lightbox grid), faq (accordion), pricing, cta, contact (form + details), logos (marquee), news (latest posts, only when the news app is installed).

Each template is a Django template producing one `<section data-section="{{ name }}" id="{{ name }}">` that follows `djangopress-html-reference` (Tailwind, Alpine, Splide/lightbox conventions, `pointer-events-none` on decorative overlays, `aria-hidden` on duplicates). Placeholder copy is written in the site's default language via the existing translation service only when it is not one of the bundled languages (bundle `pt` and `en` copy in the template; translate on the fly otherwise).

Design tokens come from `SiteSettings` (`primary_color`, `primary_color_hover`, `secondary_color`, `accent_color`, `border_radius_preset`, fonts). Tailwind runs from the CDN with no theme config, so templates use arbitrary-value classes (`bg-[#1e3a8a]`) exactly as generated pages do. **Investigation item before implementation:** confirm how `generate-site` currently maps tokens to classes on the existing sites, and reuse the same mapping so catalogue sections match generated ones.

### Flow

1. User opens Insert Section (bar, context menu or Structure tab) and picks *From catalogue*.
2. Grid of cards with a static thumbnail (PNG rendered once per template, committed) and a name. Selecting one renders the template server-side (`POST api/catalogue-section/` with `name`, `page_id`, `insert_after`) and previews it in the placeholder, exactly like an AI option today.
3. **Apply** reuses `apply-option` with `mode: 'insert'`, so the section name uniqueness, insertion in all languages and snippet translation already work.
4. Optional **Fill with AI** button after insert: runs the existing refine-section flow with a fixed instruction ("Replace the placeholder copy with real content for this site; keep the structure"). This is the only LLM step and it is opt-in.

### Out of scope for this phase

Using the catalogue inside `generate-site`. The generator keeps producing free HTML from the design system; the catalogue is for humans.

---

## Phase 4 — Design presets for humans

On the Design tab, for non-section elements, add a **Quick styles** block above the Tailwind dropdowns, and collapse the dropdowns and the raw class textarea under **Advanced**.

- **Text:** size (S / M / L / XL mapped to a fixed ladder of `text-*` classes per tag), weight (normal / medium / bold), alignment (left / centre / right), colour (site palette: primary, secondary, accent, dark, light, plus "inherit").
- **Buttons and links styled as buttons:** style preset (primary / outline / ghost) derived by *copying the classes of an existing button on the page* rather than from a fixed set, so presets match the site. The first pass shows "Match: hero button, contact button" as choices.
- **Spacing:** padding and gap presets (none / small / medium / large) for containers.
- **Images:** aspect (square / 4:3 / 16:9 / free), fit (cover / contain), rounding (from `border_radius_preset`).

Every preset is applied through the existing `change:classes` path, so undo/redo and Save keep working. No new endpoints.

---

## Phase 5 — Consistency improvements

- **Translate manual edits.** After saving text or attribute changes, offer **Translate these changes** in the status area. It sends the changed elements' HTML through `ContentGenerationService.translate_html` per target language and replaces them by selector in the other language copies, reusing the surgical logic in `apply_option`. Off by default; one click.
- **In-place apply for structural verbs.** Replace `window.location.reload()` with re-fetching the page fragment and re-initialising dynamic components, so selection and scroll position survive. Purely a UX gain; can be skipped.
- **Media collections:** *Add image* (opens the picker, inserts an `<img>` cloned from the first item's markup) and *Remove image* on the collection view, built on `insert-element` / `remove-element`.

---

## Phase 6 — Conditional: `data-repeat` annotation

Only if Phase 0 shows the heuristic misplacing "Add another" on real sites.

- Vocabulary: one boolean-style attribute on the repeat item, `data-repeat`, no values.
- `findRepeatGroup` prefers an annotated ancestor when present; heuristic otherwise.
- `djangopress-html-reference` gains one sentence: repeated items (cards, slides, FAQ entries) carry `data-repeat`.
- `check_site` gains one check: within a sibling group of identical signature, either all items carry `data-repeat` or none.
- Catalogue templates carry it from day one regardless, since it costs nothing there.

---

## Files touched (summary)

| Area | Files |
|---|---|
| Backend | `editor_v2/api_views.py`, `editor_v2/urls.py`, `core/decorators.py`, `editor_v2/tests/` |
| Frontend | `editor_v2/static/editor_v2/js/lib/dom.js`, `modules/context-menu.js`, `modules/sidebar.js`, `modules/section-inserter.js`, `modules/section-modal.js`, new `modules/element-toolbar.js`, `css/editor.css`, `templates/editor_v2/partials/editor.html` |
| Catalogue | new `editor_v2/templates/editor_v2/sections/*.html`, new `editor_v2/catalogue.py`, thumbnails under `editor_v2/static/editor_v2/img/sections/` |
| Docs / skills | `skills/djangopress-html-reference/SKILL.md` (Phase 6 only), `skills/djangopress-architecture/SKILL.md` (endpoint list), `CLAUDE.md` editor section |
| Spike | `core/management/commands/audit_repeat_groups.py` (Phase 0, may be deleted after) |

## Suggested order

Phase 0 (hours) → Phase 1 (the core; one implementation plan) → Phase 2 (small, same UI surface) → Phase 3 (largest; own implementation plan) → Phase 4 → Phase 5 → Phase 6 if needed.

## Explicitly out of scope

JSON block model, free drag-and-drop layout, a bidirectional compiler, editing header / footer inline (the editor supports generic editable objects through `content_type_id`, but header / footer wiring is not verified and is a separate topic), news layout editing.

## Open decisions

1. "Normal user" = `is_staff`, or a dedicated permission / group?
2. Start with Phases 1 + 2 (verbs and discoverability) or with Phase 3 (catalogue)? Recommendation: 1 + 2 first; they are deterministic, cheap, and make the catalogue more useful when it arrives.
3. Should AI endpoints also open to staff (with the classifier and cost implications), or remain superuser-only for now?
