# Site Build Pipeline (Level A) — Design Spec

**Date:** 2026-09-15
**Status:** Draft
**Repo:** djangopress (engine). No changes to djangopress-manager in this level.
**Goal:** Make it possible to produce several DjangoPress sites in one day at the quality level of the O Marisco redesign, by splitting the current single interactive session into three phases that can run separately: **intake** (research, then one block of questions), **build** (unattended, self-verifying), **review** (interactive, with `edit-site`). The same phases serve a single site done by hand.

---

## Context

The current workflow for a new site or redesign is one long interactive Claude Code session inside the site's directory: brainstorming questions, briefing, a long implementation plan, subagents executing it. It produces good sites, but:

- It is fully serial and needs the operator present in every phase of every site.
- Generic DjangoPress knowledge is rediscovered per site. The O Marisco pre-flight found four real defects that apply to every site: internal links need the language prefix, `ContentVersion`'s snapshot field is `snapshot`, `slugify` keeps accents in `SiteImage` keys, and PDFs must be printed with the Playwright-bundled Chromium binary because `require('playwright')` does not resolve from a temp directory.
- The best artifact of that session, `scripts/check_site.py`, lives in one site only.
- Plans are ~1800 lines because every save is an inline `manage.py shell -c` snippet transcribed by a subagent.
- The briefing's design section is what stops a site from looking templated, and it is optional in the template.
- `create-briefing` interleaves research and questions, so the operator must sit through the research.
- `generate-site` may ask questions mid-run, so it cannot run unattended.

Everything in this spec lands in the engine (`src/djangopress/`). Skills are symlinked into every child site from the editable install, so changes are live everywhere the moment they are saved. The O Marisco run in progress is driven by its written plan, not by the skills, so it is not affected.

### Operator workflow this enables

**One site, by hand** (unchanged in shape):

```
/create-briefing <url and/or document>   → research, one block of questions, briefing.md
/generate-site briefings/<slug>.md       → unattended build, stops in default language
/edit-site ...                           → interactive refinement
/generate-site (translation pass) + /deploy-site-railway when design is signed off
```

**Five sites in a day:**

1. Evening before, or first thing: run `/create-briefing` for all five in parallel tabs. Each stops after research with a draft briefing and a short list of questions.
2. Answer the five question lists back to back. Each session finalizes its briefing.
3. Launch `/generate-site` on all five in parallel. Each ends with a build report and screenshots.
4. Afternoon: review each site, refine with `/edit-site`.
5. Translation and deploy when each design is signed off, unchanged from today.

---

## Design

### Component 1: `manage.py check_site`

A management command in `src/djangopress/core/management/commands/check_site.py`. It is the generic form of O Marisco's `scripts/check_site.py`, run by every skill as the single verification gate. `beautifulsoup4` is already a dependency.

#### Checks

Each failure is one line, prefixed with a check name in brackets.

| Check | Rule |
|---|---|
| `settings` | `homepage` set. `enabled_languages` non-empty. `default_language` is one of them. `gcs_folder` non-empty. `site_name_i18n[default]` set and not `DjangoPress`. Design colors not all at template defaults (`primary_color` `#1E3A8A`, `background_color` `#FFFFFF`, `text_color` `#1F2937`, `secondary_color` `#64748B` together mean settings were never configured). |
| `page-html` | Every active page has non-empty `html_content_i18n[default]`. |
| `forbidden-tag` | No `html`, `head`, `body`, `header`, `nav`, `footer` in page HTML. |
| `sections` | Every top-level `<section>` has `data-section` equal to `id`, matching `^[a-z][a-z0-9-]*$`, unique in the page. A page with no top-level sections fails. |
| `images` | No `placehold.co` src. No leftover `data-image-prompt` / `data-image-name`. `aria-hidden="true"` images have empty `alt`; other images have non-empty `alt`. |
| `anchors` | Every `href="#x"` resolves to an `id="x"` in the same page. |
| `links` | Every internal `href` starting with `/` begins with `/<enabled-lang>/`, `/media/`, `/static/`, or `/backoffice/`. Catches links written without the language prefix. |
| `meta` | Every active page has `meta_title_i18n[default]` and `meta_description_i18n[default]`. |
| `home` | Exactly one page has slug `home` in the default language, and it is `SiteSettings.homepage`. For every language present in that page's `slug_i18n`, the slug is `home`. |
| `dom-parity` | For pages with more than one language, the structural signature (depth, tag, classes, id, data-section for every element) is identical across languages. Reports the first differing element index. |
| `global-section` | `main-header` and `main-footer` exist, are active, and have a default-language template. |
| `menu` | At least one active `MenuItem`. Every item linked to a page links to an active page. |
| `seo` | `custom_head_code` contains at least one `application/ld+json` block that parses. If `@type` is in the known table, the required keys are present. Table: `Restaurant` (name, telephone, address, geo, openingHoursSpecification, servesCuisine, priceRange), `LocalBusiness` (name, telephone, address), `Organization` (name, url). Unknown types only need to parse. |

Checks that only make sense once a build is complete (`images` placeholders, `menu`, `seo`) are still failures. The point of the command is "is this site done", and a partially built site is expected to fail. Skills read the named failures to know what is left.

#### Interface

```
python manage.py check_site            # human output, exit 0 on OK, 1 on FAIL
python manage.py check_site --json     # {"ok": bool, "failures": [{"check": "...", "message": "..."}]}
python manage.py check_site --only sections,links   # subset of checks
```

Output format matches the O Marisco script so nothing already written needs to change:

```
FAIL — 3 problem(s):

  [links] page 4 [pt]: href "/reservas/" is missing the language prefix
  ...
```

```
OK — all checks passed
```

#### Tests

`src/djangopress/core/tests/test_check_site.py`, Django `TestCase`, one test per check with a minimal fixture that triggers it and one that passes. The `links` and `home` checks get an extra test each because they encode the rulings that were expensive to discover.

#### What is not in it

Anything needing a browser: horizontal scroll, header legibility, rendering. That is the build skill's screenshot step.

---

### Component 2: `djangopress-html-reference` additions

New subsection **"Rulings that every site hits"**, placed after "Page HTML Rules". Each ruling is two to four lines with the exact wrong and right form:

1. **Internal links carry the language prefix.** `i18n_patterns` prefixes the default language too, so `reverse('core:home')` is `/pt/`. Page HTML is raw, so links are literal: `/pt/reservas/`, `/en/reservations/`, `/pt/#hero`. Header and footer are Django templates and use `{% url %}`. `check_site` enforces it under `links`.
2. **Versioning before mutation.** Both models have the method: `page.create_version(change_summary=...)` and `section.create_version(change_summary=...)`. Never write `ContentVersion` rows by hand; its snapshot field is `snapshot`, and hand-written rows are not what the backoffice restore reads.
3. **`SiteImage.key` is ASCII.** Fold with `unicodedata.normalize('NFKD', v).encode('ascii', 'ignore')` before slugifying. `slugify` alone keeps accents under Python 3's `\w`.
4. **Printing to PDF.** `require('playwright')` does not resolve from a temp directory. Use the bundled binary at `~/Library/Caches/ms-playwright/chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium` with `--headless --disable-gpu --no-pdf-header-footer --virtual-time-budget=10000 --print-to-pdf=OUT IN`.
5. **Always the site's venv.** `.venv/bin/python manage.py ...`. Scripts under `scripts/` need `PYTHONPATH=.` or the `sys.path` insert at the top.
6. **No git worktrees for site work.** `.env` and `.venv` are git-ignored, so a worktree cannot run `manage.py`. Use a branch in the same checkout.
7. **Verification is `manage.py check_site`.** Do not write per-site verification scripts.

The existing "Temporary File Pattern" section gains one line: "After every save, run `python manage.py check_site --only <relevant checks>`."

---

### Component 3: `create-briefing` becomes intake

Same skill name, so muscle memory and the manager's skill table keep working. New structure:

#### Phase 0: Detect mode from `$ARGUMENTS`

`$ARGUMENTS` may contain a URL, a path to a document (`.md`, `.txt`, `.pdf`, `.docx`), both, or nothing.

| Inputs | Mode |
|---|---|
| URL only | **Redesign.** Crawl is the factual base. Draft proposes keeping the structure. Questions target what changes. |
| Document only | **New site.** Document converted to briefing format. Questions target gaps and design direction. |
| URL + document | **Redesign with brief.** Crawl is fact, document is intent. Questions target conflicts between the two. |
| Nothing | Ask for a business name and, if it exists, a URL or document. Then continue in the resulting mode. |

#### Phase 1: Research, no questions

Runs without user interaction. In order:

- Fetch the site, extract internal links from nav, CTAs and footer, fetch every page. Build the site map with sections per page.
- Fetch social profiles found. Web search for reviews, ratings, awards, Google Maps.
- If the site links to a PicklyMenu, ResDiary, or similar integration, record the URL and treat it as an integration to keep.
- **Image inventory.** List every image found on the old site with its URL and pixel dimensions. Group by subject (dishes, space, team, exterior). Note the largest width available per group. This decides whether the build may use full-bleed photography.
- If a document was given, read it fully and map its content onto the briefing sections.
- Write `briefings/<slug>-audit.md` with everything found, including the image inventory as a table.

Phase 1 must not call `AskUserQuestion`. A fetch that fails is noted in the audit and skipped.

#### Phase 2: Draft briefing and the question list

Write `briefings/<slug>.md` in the template format (Component 5), complete enough to build from as is. Every section is filled with a proposal, never left as a placeholder. The Design Direction section gets a concrete proposal derived from the business, the location, and what competitors in the same street or marina look like, with an explicit "avoid" list.

At the top of the file, right after the title, a section:

```markdown
## Open Questions

1. **Reservations.** The current site links to ResDiary. Keep it in an iframe on `/reservas/`? *Proposed: yes.*
2. **Menu.** PicklyMenu or a PDF hosted on the site? *Proposed: PDF, generated from the extracted menu.*
...
```

Rules for the list: between five and eight questions. Each is something only the operator or client can answer. Each carries the proposed default, so the build can proceed if the answer never comes. Nothing that research already answered.

Then print the questions to the console and stop the turn. This is the natural stopping point for an unattended run: the next message from the operator carries the answers.

#### Phase 3: Answers, one block

When the operator answers (in the next turn, or interactively via `AskUserQuestion` in batches of up to four when the tool is available), apply each answer to the briefing. Questions the operator leaves unanswered keep the proposed default. Move anything still needing the client to `## To Confirm With Client` at the end. Delete the `## Open Questions` section.

Show the final briefing and end with the existing hand-off: offer to run `generate-site` now.

#### What is removed

The step-by-step questionnaire (languages, page by page, mood) is gone. Those become proposals in the draft, and the operator corrects them in the answer block. The "Is the audit accurate?" confirmation is folded into the same block.

---

### Component 4: `generate-site` becomes the unattended build

Keeps its name and its existing "design-first, translate-last" principle and Phase 8 translation pass unchanged. What changes:

#### No questions

The skill never calls `AskUserQuestion` during a build. Ambiguities are resolved with the briefing's proposed defaults or, failing that, the most conventional choice, and every such decision is written to the build report under "Assumptions". `allowed-tools` drops `AskUserQuestion`.

#### Phase order

1. **Pre-flight.** Verify `.env`, venv, migrations. Run `check_site --json` to record the baseline. Read the briefing and the audit if present. Read `SiteSettings` to know what the template already created (privacy page, default header and footer, contact form, `gcs_folder`).
2. **Settings.** As today, default language only. `design_guide` is written **here**, from the briefing's Design Direction, before any page exists. It is the contract every page follows, so it cannot be derived after the home page.
3. **Images, when an inventory exists.** Download the inventory into `SiteImage` with ASCII keys, grouped as in the audit. When no inventory exists, pages use placeholders as today.
4. **Home page.** Written first, in the default language, then `check_site --only sections,links,anchors,images,forbidden-tag`. Fix until it passes.
5. **Remaining pages.** May be dispatched to parallel subagents, one per page, each receiving the briefing, the design guide, and the home page HTML as the style reference. Each subagent runs the same `check_site` subset on its page before reporting.
6. **Header, footer, menu.** As today.
7. **SEO.** `meta_*` on every page, JSON-LD in `custom_head_code` with the type matching the business, `og_image` from the inventory when available.
8. **Full verification loop.** `check_site` with all checks must pass. Then screenshots of every page at 390, 834 and 1440 wide into `docs/screenshots/<page>-<width>.png`, using `playwright-cli` or `npx playwright screenshot`. The skill reads each screenshot and checks a fixed list: no horizontal scroll at 390, header legible over the hero, no section that reads as broken, no image rendered wider than its source width, CTAs visible above the fold. Failures are fixed and the loop repeats, at most three times. Remaining issues go to the report.
9. **Build report.** `docs/build-report.md`: pages created with URLs, assumptions taken, `check_site` result, screenshot list, open items for review, and the exact next commands (edit, translate, deploy).
10. **Commit.** `db.sqlite3`, `docs/`, `briefings/` on the current branch. No `Co-Authored-By`.

Phase 8 (translation) and the deploy hand-off keep their existing text. The final review text now points at the build report.

#### Length

Every inline `manage.py shell -c` snippet that duplicates `edit-site` is replaced by a one-line reference to the `edit-site` section that has it. The skill describes the pipeline and its gates. Target: under 400 lines, from 843.

---

### Component 5: Briefing template

`site_template/briefings/TEMPLATE.md` and the copy shipped in the package. `BriefingParser` splits on `## ` headers into a lowercase dict and only reads specific keys (business, languages, contact, social media, pages, header, footer, design preferences, images, domain, additional notes), so new sections are safe and existing section names are kept.

Changes:

- `## Open Questions` documented as the intake's working section, removed on finalization.
- `## Design Preferences` keeps its name for the parser but becomes structured and **required**:
  - Palette with roles: background, surface, text, accent, secondary, one dark block color. Hex values.
  - Type pair: heading font, body font, both Google Fonts.
  - Corner radius.
  - Layout signature: one sentence describing the recurring compositional idea.
  - Motif: one decorative device, or "none".
  - Avoid: what the local competition does that this site will not.
  - References: up to three URLs.
- `## Images` gains a required "Sources" list and a "Constraints" line stating the largest usable width per group, from the inventory.
- New `## Integrations`: third-party systems to keep (reservations, menus, booking engines), each with URL and how it is embedded.
- New `## Existing Site` (redesigns only): per current page, keep, merge, or drop, with a one-line reason.
- New `## To Confirm With Client`.

The O Marisco briefing already follows this shape in prose. The template makes it the rule.

---

### Component 6: Rollout and safety

- **Baseline commit first.** The engine has uncommitted edits to six skills and three template scripts (the design-first principle among them). Commit them as they are before any change in this spec, so the diff of this work is reviewable on its own.
- **Live skills.** Skills are symlinks to the editable install. Every save is immediately visible to every site. The O Marisco session is plan-driven and unaffected; its local `scripts/check_site.py` stays until that plan finishes, then the site switches to the command.
- **Manager.** `CLAUDE.md` in djangopress-manager: update the DjangoPress skills table descriptions for `create-briefing` and `generate-site`. No code changes.
- **Version bump** at the end (`bump_version`), so sites installed from the git tag pick up the command.
- **First real test.** The next site after O Marisco runs the full intake and build with the operator watching, before the remaining sites run in parallel.

---

## Out of scope (levels B and C)

- Build queue and intake launcher in the manager UI.
- `load_page`, `load_section`, `set_settings` management commands.
- Vertical blueprints (restaurant, tours and boats, real estate, local services).
- Any change to the translation pass or the deploy skill.

---

## Open decisions resolved in this spec

- **Keep skill names.** `create-briefing` and `generate-site` keep their names; the manager and CLAUDE.md files reference them.
- **`check_site` failures for unfinished sites are failures, not warnings.** The command answers "is this site done". Skills use `--only` for partial checks during a build.
- **Design guide before pages, not after home.** The briefing's Design Direction is now rich enough to write it first, and every page including home then follows it.
- **Screenshots are read by the model, not by a script.** Rendering problems do not reduce to assertions. The fixed checklist keeps the review consistent.
