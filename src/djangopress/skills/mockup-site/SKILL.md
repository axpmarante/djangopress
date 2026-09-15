---
name: mockup-site
description: Generate the approved-design mockups for a site with gpt-image-2.5 — one master one-page at a time from the final briefing until the operator approves it, then every section in high resolution from that master, one at a time with a check after each; for any section, three stacked alternatives in one render and a pick. Runs after the briefing is final and before any build; the build refuses to start without an approved master.
argument-hint: master [note] | approve <n> | section next | section <name> [note] | section <name> options [note] | section <name> pick <k> [note] | sections | costs
allowed-tools: Bash, Read, Write, Edit, Grep, Glob
---

# Mockups: one master → high-resolution sections, one at a time

The argument is: `$ARGUMENTS`. First word is the mode.

**Two rules.** Form comes from the image, facts come from the briefing: nothing seen in an image — a price, an address, a name, a menu item — is ever written into the site. And the approved master is the design: sections are never redesigned, only expanded from it.

**Rhythm.** Each mode renders at most one image and stops so the operator can look. The next call continues. The operator is present during this phase by design.

All commands run through the site venv: `.venv/bin/python manage.py …`. Every prompt is written to `docs/mockups/prompts/` before the call so the operator can read, edit and re-run it. Every render uses `--model sunburst --quality high` and `--budget <site budget>`. The site budget defaults to 5 (USD). Two optional trailing tokens on any mode's argument are stripped before anything reaches a prompt: `budget=<n>` raises the site budget for this and later calls (record it in `docs/mockups/budget.txt`, which is read first when present), and `model=flare` renders this call with the cheap model.

## Setup (every mode)

```bash
mkdir -p docs/mockups/prompts docs/mockups/crops
[ -f docs/mockups/.gitignore ] || printf '*.png\n!00-master.png\ncrops/\n' > docs/mockups/.gitignore
```

Read the briefing (`briefings/<slug>.md`, the only `.md` in `briefings/` besides `TEMPLATE.md` and `*-audit.md`). If it still has an `## Open Questions` section, stop: the briefing is not final; the operator finishes `/create-briefing` first. Read `briefings/<slug>-menu.json` if it exists, and `docs/mockups/costs.json` if it exists.

---

## `master [note]`

Renders **one** master one-page. `<n>` is the next free number (`master-v1.png` if none exists).

### Prompt: `docs/mockups/prompts/00-master-v<n>.md`

```
DESKTOP WEBSITE ONE-PAGE MOCKUP, full page from header to footer, rendered at
about 1440px wide, tall vertical layout, sections stacked top to bottom.
Photorealistic UI: real navigation bar, real buttons, real typography, real
photography. No device frame, no browser chrome, no annotations.

BRAND: <site name> — <one-line positioning from Business>.
LANGUAGE OF ALL TEXT: <default language name>. Use short, plausible placeholder
copy; never invent prices, addresses, phone numbers or awards.

AUDIENCE AND TONE: <2 sentences from Business>.

SECTIONS, in this order (one band each):
1. Header: <from Header section, or "logo left, 5 links, one CTA button, language switcher">
2. <section from Pages → Home entry, one line each, with its purpose and main element>
...
N. Footer: <from Footer section>

DESIGN DIRECTION (follow exactly):
- Palette: background <hex>, surface <hex>, text <hex>, accent <hex>, secondary <hex>, one dark block <hex>
- Type: headings <font or classification>, body <font or classification>
- Corner radius: <value>. Layout signature: <sentence>. Motif: <sentence or none>.
- Photography: <from Images: reuse real photos → "documentary, warm, no stock-look"; ai/unsplash → "editorial hospitality photography">
AVOID: <the Avoid list verbatim>.
```

When a previous master `master-v<n-1>.png` exists and a note was given, append:

```
ADJUSTMENT REQUESTED BY THE OPERATOR: <note verbatim>. Keep everything else
exactly as in the reference image: same sections, order, palette, type and
composition.
```

and pass the previous master as reference.

### Render

```bash
.venv/bin/python manage.py generate_mockup --prompt-file docs/mockups/prompts/00-master-v<n>.md \
  --out docs/mockups/master-v<n>.png --model sunburst --size 1280x3840 --quality high --budget <site budget> \
  [--ref docs/mockups/master-v<n-1>.png]
```

**Long pages.** When the numbered SECTIONS list has more than 9 entries (header and footer included), render two halves: `--out docs/mockups/master-v<n>-top.png` with sections 1..⌈N/2⌉ and the line `SHOW ONLY THE TOP HALF OF THE PAGE, ending mid-page`, then `master-v<n>-bottom.png` with the remaining sections, `--ref docs/mockups/master-v<n>-top.png`, and the line `CONTINUE THIS EXACT WEBSITE from where the reference ends; the header is NOT repeated; end with the footer`. Both halves keep `1280x3840`.

Print and stop:

```
Master v<n>: docs/mockups/master-v<n>.png   $<cost>   site total $<total>
Approve with: /mockup-site approve <n>
Or ask for another: /mockup-site master <what to change>
```

---

## `approve <n>`

No API call. Copy `master-v<n>.png` to `docs/mockups/00-master.png` (for a two-half master, copy `-top` to `00-master.png` and `-bottom` to `00-master-bottom.png`). In the briefing, under `## Design Preferences`, add or replace the line `- **Reference mockup**: docs/mockups/00-master.png (v<n>)`. `00-master.png` is committed by `extract-design`; it is the design record and must survive a fresh clone, unlike the sections, which are regenerable. Print `Approved master v<n>. Next: /mockup-site section next` and stop.

---

## `section next`

Requires `docs/mockups/00-master.png`; otherwise say so and stop.

### 1. Section list (first call only)

If `docs/mockups/sections.json` does not exist: open `00-master.png` (and `00-master-bottom.png` if present) with the Read tool and write the section sequence you see, top to bottom, with the vertical extent of each as fractions of the image height:

```json
[
  {"nn": "01", "name": "hero", "type": "hero", "top": 0.00, "bottom": 0.16},
  {"nn": "02", "name": "trust-bar", "type": "trust", "top": 0.16, "bottom": 0.19}
]
```

Names: lowercase, hyphens, English. Types: `hero`, `band` (full-width photographic or colored band, CTA), `inverted` (dark block), `editorial` (text + image split), `grid` (3+ cards or items), `gallery`, `menu`, `pricing`, `testimonials`, `trust`, `header`, `footer`. For a bottom-half image, add `"image": "00-master-bottom.png"` to its entries.

Reconcile with the briefing's `## Pages` → Home: a section in the master but absent from the briefing is appended to the briefing's Home entry as `(proposed from mockup)`; a section in the briefing but absent from the master is appended to `sections.json` with `"top": null, "bottom": null` (no crop). Do not drop anything from the briefing.

### 2. Pick the next section

The first entry in `sections.json` whose `docs/mockups/NN-<name>.png` does not exist. If none is left, print `All sections rendered. Next: /extract-design` and stop.

### 3. Prompt: `docs/mockups/prompts/NN-<name>.md`

Five blocks, in this order:

```
MASTER REFERENCE. The first reference image is the approved master design of
this website. Do NOT redesign the brand. Do NOT create a new visual direction.
The new image must look like another screenshot from the exact same website,
rendered at much higher resolution: same typography and hierarchy, same
palette and background colors, same button design, same dividers, same image
grading and photography style, same spacing, content width and grid, same
decorative language. When unsure, prefer consistency with the master over
novelty.
<if a crop exists:> The second reference image is the crop of this section
from the master: keep its composition and element order; reconstruct it as a
polished high-resolution section, do not merely upscale it.

PROJECT: <site name> — <positioning>. Language of all text: <default language>.

SECTION TO CREATE: <NAME> (<type>). Purpose: <one sentence from the briefing>.

CONTENT (use exactly these words; no other text, prices or names):
<headline, subhead, labels, CTAs from the briefing; for menu/pricing sections
the real items from the menu JSON with their real prices; for contact
sections the real phone, address and hours; navigation labels for header>

OUTPUT: only this one section, desktop layout about 1440px wide, no browser
chrome, no annotations, no device frame.
```

### 4. Crop and render

When `top`/`bottom` are set:

```bash
.venv/bin/python manage.py crop_mockup docs/mockups/<image or 00-master.png> docs/mockups/crops/NN-<name>-crop.png --top <top> --bottom <bottom>
```

Size by type (a `ratio:` line in the section's briefing entry overrides):

| type | size |
|---|---|
| hero, band, inverted | 1920x1088 |
| editorial | 1536x1024 |
| grid, gallery, menu, pricing | 1536x1536 |
| testimonials, trust | 1920x832 |
| header, footer | 1920x640 |

```bash
.venv/bin/python manage.py generate_mockup --prompt-file docs/mockups/prompts/NN-<name>.md \
  --out docs/mockups/NN-<name>.png --model sunburst --size <size> --quality high --budget <site budget> \
  --ref docs/mockups/00-master.png [--ref docs/mockups/crops/NN-<name>-crop.png]
```

### 5. Stop

```
Section NN-<name>: docs/mockups/NN-<name>.png   $<cost>   site total $<total>   (<k> of <N> done)
OK? → /mockup-site section next
Change it → /mockup-site section <name> <what to change>
```

---

## `section <name> [note]`

Regenerates `NN-<name>.png`. First rename `docs/mockups/NN-<name>.png` to `docs/mockups/NN-<name>.prev.png`. Then run the `section next` render line for this section with one more reference at the end: `--ref docs/mockups/NN-<name>.prev.png` (after the master and, when it exists, the crop). Append to the prompt file:

```
ADJUSTMENT REQUESTED BY THE OPERATOR: <note verbatim>. Everything else stays as
in the references.
```

Print the new path and the cost, then the same two options as `section next`.

---

## `section <name> options [note]`

Three alternative designs of ONE section in a single render, stacked, so the operator chooses before paying for a full-resolution section. Costs the same as one master.

1. `<n>` is the next free number for `docs/mockups/NN-<name>-options-v<n>.png`.
2. Prompt file `docs/mockups/prompts/NN-<name>-options-v<n>.md`: the master-reference block from `section next`; then, when `NN-<name>.png` exists, "The second reference image is the CURRENT version of this section; each option must be clearly better than it while staying in the same design system." (otherwise the crop is the second reference); then the PROJECT block; then:

```
TASK: Show THREE ALTERNATIVE DESIGNS of the SAME section "<NAME>", STACKED
VERTICALLY in one tall image. Each option is a complete DESKTOP section about
1440px wide (never a mobile layout), separated by a thin cream gap. Put a
small terracotta tag "OPÇÃO 1", "OPÇÃO 2", "OPÇÃO 3" in the top-left corner
of each.

Facts allowed (nothing else): <the section's facts from the briefing, listed>.

OPÇÃO 1 — <one-line title>. <composition, photography, elements>
OPÇÃO 2 — <one-line title>. <composition, photography, elements>
OPÇÃO 3 — <one-line title>. <composition, photography, elements>

No browser chrome, no annotations other than the three OPÇÃO tags, no device
frame.
```

   The three options differ on one axis each unless the operator's note says otherwise: composition (immersive full-bleed / editorial with whitespace / split), photography subject, and content treatment (list / objects / grouped). Every option carries the same facts. If a note was given, it drives all three ("three versions about the wine cellar", "three versions with the terrace").
3. Render, tall size, both references:

```bash
.venv/bin/python manage.py generate_mockup --prompt-file docs/mockups/prompts/NN-<name>-options-v<n>.md \
  --out docs/mockups/NN-<name>-options-v<n>.png --model sunburst --size 1280x3840 --quality high --budget <site budget> \
  --ref docs/mockups/00-master.png --ref docs/mockups/<NN-<name>.png | crops/NN-<name>-crop.png>
```

4. Print and stop:

```
Options for NN-<name>: docs/mockups/NN-<name>-options-v<n>.png   $<cost>   site total $<total>
Pick one → /mockup-site section <name> pick <k> [what to change in it]
Another round → /mockup-site section <name> options <note>
```

---

## `section <name> pick <k> [note]`

Renders the chosen option at full resolution and makes it the section's mockup.

1. Crop option `<k>` (1, 2 or 3) out of the latest `NN-<name>-options-v<n>.png` by thirds — top `(k-1)/3`, bottom `k/3`, widened by 0.02 on each side that is not an image edge — into `docs/mockups/crops/NN-<name>-option<k>-crop.png`. Open the crop with the Read tool and confirm it holds exactly one option; adjust the fractions if the tag of the next option is visible.
2. If `NN-<name>.png` exists, rename it to `NN-<name>.prev.png`.
3. Rewrite `docs/mockups/prompts/NN-<name>.md` as in `section next`, with the second-reference sentence replaced by: "The second reference image is the chosen design of this section (labelled OPÇÃO <k>): keep its composition, palette and elements; do not render the OPÇÃO tag." When a note was given, add the `ADJUSTMENT REQUESTED BY THE OPERATOR` block with it.
4. Render with the section's size from the type table:

```bash
.venv/bin/python manage.py generate_mockup --prompt-file docs/mockups/prompts/NN-<name>.md \
  --out docs/mockups/NN-<name>.png --model sunburst --size <size> --quality high --budget <site budget> \
  --ref docs/mockups/00-master.png --ref docs/mockups/crops/NN-<name>-option<k>-crop.png
```

5. Print the path and the cost, then the same two options as `section next`. When the section was already built in the site, remind the operator that `docs/design-system.md` (its `### NN-<name>` spec) and the page section must be updated next: `/extract-design` for the spec, then `/edit-site` or `/generate-site … rebuild`.

---

## `sections`

Renders every remaining section without stopping between them, with the same prompts and sizes as `section next`. For the operator who already trusts the master. Stop at the first non-retryable failure and report it; print the full list and the site total at the end.

---

## `costs`

Print `docs/mockups/costs.json` as a table (file, model, size, quality, tokens out, cost) and the total. No API calls.

---

## Failure handling

- `OPENAI_API_KEY is not set`: say which `.env` to edit and stop.
- A `budget` refusal: print the total and stop; the operator raises it with `budget=<n>` on the next call.
- A non-retryable API error: report the error text and the prompt file, and stop; the operator edits the prompt or changes the note.
- Never delete a rendered PNG except by the `.prev.png` rotation above.
