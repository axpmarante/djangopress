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

- **Fresh site** (no pages yet): run Phases 0–8. Stop after Phase 8.
- **Built site, translation requested** (the operator asked for translation, or ran this skill again on a site that already passes `check_site` in the default language): run Phase 9 only.

Decide by reading the state in Phase 0.

---

## Phase 0: Pre-flight

```bash
test -f .env && echo "ENV OK" || echo "ENV MISSING"
.venv/bin/python -c "import djangopress; print('djangopress', djangopress.__version__ if hasattr(djangopress,'__version__') else 'ok')"
.venv/bin/python manage.py migrate --check >/dev/null 2>&1 && echo "MIGRATIONS OK" || echo "MIGRATIONS PENDING"
.venv/bin/python manage.py check_site --json || true
```

On a fresh site this reports many failures by design; on an existing site it will also list many `[links]` lines because engine-generated content never carried the language prefix. Neither is breakage; both are the to-do list.

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

Facts to hold: a fresh site has migrations applied, `gcs_folder` set to the project slug, and a `contact` DynamicForm. It has no pages and no `main-header`/`main-footer` rows; until those rows exist the site renders from the engine's fallback templates (`partials/header.html`, `partials/footer.html`). Phase 6 creates the rows from those fallbacks when absent. Never change `gcs_folder`.

Create a branch for the build if you are on `main` with a clean tree: `git checkout -b build-$(date +%Y%m%d)`. If the tree is dirty, stay where you are.

---

## Phase 1: Settings

Follow `edit-site` → *Settings* → *Update site identity / contact / social / design system*, in one shell call, from the briefing:

- `enabled_languages` = every language in the briefing (the full set, even though content is default-only for now); `default_language`.
- `site_name_i18n` for all languages (brand), `site_description_i18n` default only.
- `project_briefing` = the Business section verbatim.
- Contact, social URLs, `whatsapp_number` if any.
- Colors from Design Preferences: `background_color`, `text_color`, `primary_color` (accent), `secondary_color`, `accent_color`, `heading_color`; `heading_font`, `body_font`; `border_radius_preset`, `container_width`, `shadow_preset`, button colors from the palette.
- Privacy page: create the Privacy & Cookies Policy page now if no page slug contains `privacy` or `politica` — use `edit-site` → *Create Page* with `sort_order=999`, default language only. The footer in Phase 6 links to it.

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

Write the home page HTML in the default language to `/tmp/dp-page-new-<lang>.html`, following the design guide and the Pages section of the briefing. Then save it with `edit-site` → *Create Page* (steps 4, 6: create, then set as homepage), including `meta_title_i18n` and `meta_description_i18n`. The `edit-site` recipes loop over every enabled language; in a build write only the default-language key of each `*_i18n` field.

Internal links are literal with the language prefix: `/pt/reservas/`, `/pt/#menu` (`Rulings` §1).

Verify and fix until clean:

```bash
.venv/bin/python manage.py check_site --only sections,forbidden-tag,images,anchors,links,meta,home
```

Placeholder images are the only acceptable remaining `[images]` lines, and only under the placeholder strategies.

---

## Phase 5: Remaining pages

For every other page in the briefing, the same as Phase 4, **without** the homepage step. Pages are independent once the design guide and the home page exist, so you may dispatch them in parallel with the `Agent` tool, one agent per page, each given: the briefing path, the design guide (read it from settings), the home page HTML as the style reference, and the image map. Agents save and report the page id only; they do not run `check_site` (it evaluates the whole site and would chase each other's half-written pages). When all agents have reported, run the Phase 4 `check_site --only` line once yourself and fix what it lists.

Sequential is fine for three pages or fewer.

---

## Phase 6: Header, footer, menu

1. Menu: `edit-site` → *Menu Management* → *Rebuild menu from pages*, then adjust order and add anchor items for a one-pager (`/pt/#menu`) and the reservations CTA as a CTA item.
2. Header: create `main-header` from `partials/header.html` if the row is absent, then refine it per the briefing's Header section with `edit-site` → *Edit Header/Footer*. Keep `{% url %}` tags; keep the language switcher; make the mobile menu work with Alpine.
3. Footer: create `main-footer` from `partials/footer.html` if the row is absent, then refine it. Contact, hours, social icons, privacy link, copyright.

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

The gate passes when the command exits 0, or when every remaining line is an `[images]` line reading `unresolved placeholder` or `leftover data-image-* attribute` and the briefing's image strategy is `unsplash`, `ai` or `skip`. Under those strategies both kinds of `[images]` line are expected — do not strip the `data-image-*` attributes to silence them; they are what the later image step consumes. Anything else must be fixed before continuing.

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
