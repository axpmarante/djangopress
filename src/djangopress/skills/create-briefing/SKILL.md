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
.venv/bin/python manage.py shell -c "
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

Read `briefings/TEMPLATE.md` (if the site does not have it, run `.venv/bin/python manage.py sync_skills` once, which copies it from the package). Write `briefings/<slug>.md` following it exactly, **every section filled with a concrete proposal** — no placeholders, no "TBD". The build skill must be able to run from this draft unchanged.

Rules for the draft:

- **Business** is the most important section: three to five paragraphs of polished prose from the audit and the document. Reputation with numbers. Tone of voice stated. Competitive positioning named.
- **Existing Site** (URL modes): one row per current page with keep / merge / drop and a reason.
- **Integrations**: from 1b, with the embed method proposed.
- **Pages**: one entry per page with its purpose and meta title/description. Do **not** list sections in order — the design concept decides grouping and sequence.
- **Content**: per page, a flat list of what must be communicated. Mark every fact, name, price, award, label and CTA `(required)`; give messages 3–5 `keywords:`; give CTAs `→ /page/` or `→ #section`. Menu items come from `briefings/<slug>-menu.json` when it exists — reference it in the Menu item. This list is the content contract the build verifies.
- **Design Constraints**: only what every concept must respect. Brand colors **only** if they are a brand asset (logo, existing identity) — otherwise `none`. Fill **Direction** only with what the operator or the client actually said; never invent a direction. Set **Mode** to `conventional` unless the operator or the document asked for something different; write `bold` only then. Fill **Avoid** with what the direct competition does (look at two or three competitors' sites in the same street, marina or niche). References are context, never models. State the image constraints line from the largest widths. Never propose a palette, type pair, layout signature or motif here.
- **Images**: strategy from the inventory. State the constraints line from the largest widths.
- **Additional Notes**: SEO focus phrases (two or three, in the default language and in English), the JSON-LD `@type`. Also read the site's `contact` DynamicForm schema and write a `form fields:` line with its field names in order (proposing `phone` when the schema doesn't already have it) and a `form service options:` line with the service `<select>`'s options.
- **Domain**: the current `gcs_folder`. Never propose changing it.

### 2b. Reference candidates

Search (WebSearch) for four or five well-made sites or templates of the same sector — real company sites and template demos both count — and list them with the URL and one line on their structure and register. Put the list under `## Design Constraints` → `References (candidates)` in the draft, and add ONE question to the block: which one or two the operator likes and what in them (hero, colours, where the form sits). In Phase 3, keep only the chosen ones as `- **References**:` with a one-line structure note each; drop the rest.

Then write `## Open Questions` right after the title. Five to eight questions. Each is something only the operator or the client can answer, carries the proposed default, and would change the build if answered differently. Never ask what the research already answered. Typical questions:

- Pages to merge or drop (redesigns)
- Integration to keep vs. replace (PicklyMenu vs. PDF, reservation widget)
- Languages beyond the default
- Contact email when none is published
- Whether the old photos are acceptable or a shoot is planned
- Any non-negotiable colours or fonts (default: none — the concepts choose)
- Design direction for the three concepts: register (solid/trustworthy · premium/architectural ·
  direct/urgent · warm/local · other), light or dark, what makes the current site look
  unprofessional (default: none — the concepts roam; the answer goes into Design Constraints →
  Direction and Avoid)
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

Re-read the whole file once. Check: every `## ` section from the template is present; Design Constraints is filled (brand colors may be `none`); every `## Content` line parses as `- (required)? Kind: text [— keywords: …] [→ /page/ or → #section]`; Pages do not fix section order; Domain equals `gcs_folder`.

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

---

## Key principles

- **Research first, ask last, ask once.** The operator's time is the scarce resource.
- **Every question carries its default.** A briefing with open questions is still buildable.
- **The draft is complete.** If you would leave a section blank, propose something and make it a question instead.
- **Facts vs. intent.** Crawl is fact, document is intent, operator answer wins over both.
- **Output must parse.** `## ` section names exactly as in `briefings/TEMPLATE.md`.
