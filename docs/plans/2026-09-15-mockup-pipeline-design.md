# Mockup Pipeline (Level A2) — Design Spec

**Date:** 2026-09-15
**Status:** Draft
**Repo:** djangopress (engine). No manager changes.
**Depends on:** Site Build Pipeline (Level A), merged in 3.6.0.
**Goal:** Put an approved image between the briefing and the build. From the final briefing, generate a master one-page mockup, one at a time until the operator approves it; every section is then rendered in high resolution from that master, one at a time with a check after each; a design system and per-section UI specs are extracted from the images; the build implements them. The mockup is mandatory: `generate-site` refuses to run without an approved master and an extracted design system.

---

## Context

Today the first time anyone sees the design is after the build. The operator has been generating full-page mockups by hand in ChatGPT and finds them the best way to validate look and feel and content architecture before any code exists, with two caveats: the images contain invented facts (prices, addresses, bottle labels), and repeating the process per site by hand does not scale to five sites a day.

The operator's own process documents (a master-reference workflow, a master section prompt, and a per-section prompt pack) define the method this spec automates:

- A **master one-page** image is the approved design system: palette, type pairing, grid, spacing, buttons, photography treatment, decorative language.
- Each **section** is then generated separately at higher resolution with the master (and optionally a crop of the section) as reference images, under an explicit instruction not to redesign.
- The AI supplies **form**; the briefing supplies **facts**. Wrong text, prices, maps and addresses in the images are never copied.

The engine already has `LLMBase.generate_image()` for Google image models, an `OpenAI` client wired from `OPENAI_API_KEY` in `ai/utils/llm_config.py`, and the `openai` SDK (2.36.0 in current sites) whose image endpoints accept free-form `size` strings, list-valued `image` inputs on edits, and `input_fidelity`. Nothing exists for OpenAI image generation.

### Provider decision

Only two models are used, both from OpenAI, released 2026-09-08:

| Model | Role | Why |
|---|---|---|
| `gpt-image-2.5-sunburst` | Every master, every section, every regeneration | Built for precision across chained edits, which is exactly "another master with this one as reference" and "expand this section without redesigning". A master may be right at the first try, so it is rendered at final quality. |
| `gpt-image-2.5-flare` | Optional cheap exploration (`--model flare`) | Same price per token, about half the latency; available when the operator wants quick throwaway variants. Not used by default. |

No other image model is called. `LLMBase.generate_image()` (Google) stays untouched for site photography.

### Size rules (from the OpenAI image guide)

`size` is `WIDTHxHEIGHT`; both multiples of 16; aspect ratio between 1:3 and 3:1; no edge above 3840; total pixels between 655,360 and 8,294,400; above 2560×1440 is experimental. Quality: `low`, `medium`, `high`, `xhigh`, `max`, `auto`.

A real one-page is taller than 1:3, so a master is rendered at the 1:3 limit with sections compressed, which is enough to choose a direction. Detail comes from the section renders.

### Pricing (per million tokens, identical for both models)

Text input $5, image input $8, image output $30. OpenAI's per-image estimates exist only for `gpt-image-2` (high quality 1536×1024 ≈ $0.165) and it states 2.5 uses different token counts. The command therefore records `usage` from every response and computes cost from the token rates, so the real number is known after the first site. Conservative budget per site at high quality: 1–2 masters + 14 sections + a handful of regenerations ≈ $3–5.

---

## Where it sits in the flow

```
Novo site (manager)
  → create-briefing: research, draft briefing, question block, answers → FINAL briefing
  → mockup-site master: ONE one-page from the final briefing (Sunburst, high)   ← new
      not right? → mockup-site master <note>: another, with the previous as reference
      right?     → mockup-site approve <n>: becomes 00-master.png (no API call)
  → mockup-site section next: the next section from the master (Sunburst, high)
      operator looks; "ok" → next; note → mockup-site section <name> <note>
      (mockup-site sections: render all remaining without stopping, when confident)
  → extract-design: design-system.md + per-section UI specs; briefing Pages and
    Design Preferences rewritten from the master; SiteSettings design fields set
  → generate-site (gated on 00-master.png + design-system.md)
  → review / translate / deploy (unchanged)
```

The briefing is final before any image exists: the questions were asked and answered on the text. Images then settle the design, one at a time, because the first master or the first render of a section may already be right. The operator is present during the mockup phase by design; for five sites the masters and sections of all five still run in parallel tabs, each stopping at its own check points.

---

## Components

### Component 1: `ai/utils/openai_images.py`

A small module with no Django dependency beyond settings access:

```python
MODELS = {'flare': 'gpt-image-2.5-flare', 'sunburst': 'gpt-image-2.5-sunburst'}
PRICE_PER_M = {'text_in': 5.0, 'image_in': 8.0, 'image_out': 30.0}

def validate_size(size: str) -> tuple[int, int]      # raises ValueError with the violated rule
def cost_usd(usage) -> float                          # from usage.input_tokens_details / output_tokens
def generate(prompt, *, size, quality, model, client=None) -> ImageResult
def edit(prompt, *, references: list[Path], size, quality, model, client=None) -> ImageResult   # no input_fidelity: gpt-image-2.5 rejects it
```

`ImageResult` carries `png_bytes`, `usage` (input text/image tokens, output tokens), `cost_usd`, `model`, `size`, `quality`, `elapsed_s`. `generate` calls `client.images.generate(model=..., prompt=..., size=..., quality=..., output_format='png', n=1)`; `edit` calls `client.images.edit(model=..., image=[open files...], prompt=..., size=..., quality=..., output_format='png', n=1)` — no `input_fidelity`, which gpt-image-2.5 rejects. The client comes from `OPENAI_API_KEY` (same env access as `llm_config.py`). Errors from the API surface as `ImageGenerationError(message, retryable: bool)`; rate-limit and 5xx are retried twice with backoff, content-policy and 4xx are not.

Tests use a fake client object; no network. They cover `validate_size` for every rule, `cost_usd`, the edit call shape (list of files, `input_fidelity`), and the retry classification.

### Component 2: `manage.py generate_mockup`

`ai/management/commands/generate_mockup.py`. One command, one image per call, so skills compose it:

```
generate_mockup --prompt-file docs/mockups/prompts/00-master.md --out docs/mockups/master-v1.png \
                --model flare --size 1280x3840 --quality medium
generate_mockup --prompt-file docs/mockups/prompts/01-hero.md --out docs/mockups/01-hero.png \
                --model sunburst --size 1920x1088 --quality high \
                --ref docs/mockups/00-master.png --ref docs/mockups/crops/01-hero.png
```

Behaviour:

- `--ref` repeatable (up to 16); with any `--ref` the edits endpoint is used, otherwise generations.
- `--size` validated before any call; the error names the rule.
- On success writes the PNG and appends one record to `docs/mockups/costs.json`: timestamp, out path, model, size, quality, tokens, cost, elapsed. Prints `wrote <path>  <W>x<H>  $<cost>  (<elapsed>s)` and the site's running total from the file.
- `--budget <usd>`: refuses to call when the running total plus the last recorded cost of the same size/quality would exceed it. Default: none.
- `--dry-run`: validates and prints the request without calling.

Exit 1 with a one-line reason on any failure. Tests with the fake client: file written, costs.json appended, budget refusal, dry run, size error.

### Component 3: `manage.py crop_mockup`

`crop_mockup docs/mockups/00-master.png docs/mockups/crops/01-hero.png --top 0.00 --bottom 0.17`. Fractions of the image height; PIL crop; writes the file. Used by the skill to build the second reference for a section from the y-range it identified while reading the master. Tests: fraction validation, output dimensions.

### Component 4: `manage.py sample_palette`

`sample_palette docs/mockups/00-master.png --k 6 --json`. PIL + a simple k-means on a downscaled copy (no new dependency), ignoring near-white and near-black unless they dominate; prints hex values with share of pixels. Used by `extract-design` so palette values in the design system are sampled, not guessed. Tests on a synthetic three-color image.

### Component 5: skill `mockup-site`

`src/djangopress/skills/mockup-site/SKILL.md`. Modes by first argument. All prompts are written to `docs/mockups/prompts/` first, so the operator can read and edit them and re-run. Every render uses `sunburst`, `high` unless the operator passes `flare`.

**`master [note]`** — Builds `docs/mockups/prompts/00-master-v<n>.md` from the **final** briefing: Business (tone, positioning, audience), the Pages entry for the home page as the section list, Design Preferences (palette roles, type pair, layout signature, motif, avoid list), language, and the rule that the image is a desktop one-page at ~1440px with sections top to bottom and no invented facts beyond placeholder copy. `<n>` is the next free number. Renders one image, `1280x3840`, into `master-v<n>.png`. When a previous master exists and a note is given, the previous master is passed as reference and the note is appended as "ADJUSTMENT REQUESTED: …; keep everything else". Prints the path and stops: the operator either approves or asks for another with a note. When more than ~9 sections are listed, renders two halves (`-top`, `-bottom`) with the top as reference for the bottom.

**`approve <n>`** — Copies `master-v<n>.png` to `00-master.png` (no API call) and records `Reference mockup: docs/mockups/00-master.png (v<n>)` under Design Preferences in the briefing.

**`section next`** — Requires `00-master.png`. On the first call, reads the master and writes the section sequence with approximate y-ranges to `docs/mockups/sections.json` (`[{"nn": "01", "name": "hero", "type": "hero", "top": 0.0, "bottom": 0.16}, …]`), reconciled with the briefing's Pages entry: sections in the master but not in the briefing are added to the briefing as proposals; sections in the briefing but not in the master are appended with no crop. Then renders the first section in `sections.json` that has no `NN-<name>.png` yet: writes `prompts/NN-<name>.md` with five blocks (master-reference instruction verbatim, project context, section brief, real content from the briefing and menu JSON, consistency rules), crops the master with `crop_mockup`, renders with references master + crop, size from the table below. Prints the path and stops: the operator says "ok" (next call renders the next one) or gives a note.

| Section type (by name or briefing note) | Size | Ratio |
|---|---|---|
| hero, cta, band, wine/inverted block | 1920×1088 | 16:9 |
| editorial split (about, story, product, events, location) | 1536×1024 | 3:2 |
| gallery, menu, pricing, grid of 4+ items | 1536×1536 | 1:1 |
| testimonials, trust bar | 1920×832 | 2.3:1 |
| header alone, footer | 1920×640 | 3:1 |

A `ratio:` line in the section's briefing entry overrides the table.

**`section <name> [note]`** — Regenerates one section, appending the operator's note to the prompt ("less text", "show the terrace", "use the dark treatment"), with the previous render as a third reference. Keeps the previous file as `NN-<name>.prev.png`.

**`sections`** — Renders every remaining section without stopping, for when the operator is confident in the master. Same prompts and sizes as `section next`.

**`costs`** — Prints the site total and per-image lines from `costs.json`.

### Component 6: skill `extract-design`

`src/djangopress/skills/extract-design/SKILL.md`. Runs after sections are approved. Reads `00-master.png`, every `NN-*.png`, the briefing, and `sample_palette` output. Writes:

- **`docs/design-system.md`** with two parts. *Tokens*: palette with roles mapped to `SiteSettings` fields (`background_color`, `text_color`, `primary_color`, `secondary_color`, `accent_color`, `heading_color`, dark-block color), type pair mapped to two Google Fonts with the classification that led there (e.g. "high-contrast transitional serif display → Playfair Display"; "geometric grotesk body → Instrument Sans"), type scale, content width (`container_width`), `border_radius_preset`, `shadow_preset`, `spacing_scale`, button spec, image treatment rules. *Per-section UI spec*: for each `NN-<name>.png`, the layout grid, column split, image ratio and max render width, element list in order, background, and what is editable text.
- **Briefing updates**: Design Preferences rewritten from the tokens (values, not adjectives); Pages rewritten from the section sequence, with one entry per section carrying its spec file reference. Facts untouched.
- **`SiteSettings`**: the design fields above, and `design_guide` = the Tokens part of `design-system.md`.

Ends with `check_site --only settings` and a summary. Never invents facts from the images: any text, price, address or name seen in an image that is not in the briefing is ignored.

### Component 7: `generate-site` changes

- **Phase 0 gate (mandatory mockup):** if `docs/mockups/00-master.png` or `docs/design-system.md` is missing, print the two commands to produce them and stop. No flag to bypass; the operator asked for mandatory.
- **Phase 2:** the design guide is the Tokens part of `docs/design-system.md`, not derived from prose.
- **Phase 4/5:** each section's HTML is written with its `NN-<name>.png` and its UI spec open; the instruction is "match the layout, palette, type and rhythm of the image; take every word, number and link from the briefing". Home page order follows the design system's section list.
- **Phase 8c:** the visual checklist gains one item: "each section reads as the same design as its mockup".
- **Build report:** lists mockup files used and the design-system version.

### Component 8: `create-briefing` changes

Unchanged up to the final briefing: research, draft, question block, answers. Only the hand-off changes: after finalizing, offer `mockup-site master` as the next step instead of `generate-site`, and say the build comes after `extract-design`.

### Component 9: Rollout

- New skill directories are picked up by `sync_skills` (new_site.sh runs it; existing sites run it once).
- `openai` SDK: 2.36.0 already accepts free-form `size` and list `image`; no upgrade required. `pyproject.toml` pins `openai>=2.36`.
- Version bump to 3.7.0.
- `.env.example`: `OPENAI_API_KEY` comment updated to say it is used for mockups.
- First real run: the next site after O Marisco, with the operator watching, before the batch.

---

## Out of scope

- Mockup gallery and choice UI in the manager (level B).
- Google image models for mockups.
- Automatic client approval flow (sending mockups to the client).
- Per-page mockups beyond the home page and pages the briefing marks as key; inner pages inherit the design system.

---

## Decisions resolved in this spec

- **Mandatory, not optional.** The build gate has no bypass.
- **Facts from the briefing, form from the image.** Stated in every skill; `extract-design` explicitly ignores text seen in images.
- **Prompts are files.** Every prompt is written under `docs/mockups/prompts/` before the call, so the operator can edit and re-run a single section.
- **One master at a time, at final quality.** The first may be right; a second is an adjustment of the first, not a new draft. Flare stays available as an explicit cheap option.
- **Costs are measured, not estimated.** Every call appends to `costs.json`.
- **1:3 master.** Accept compression; halves only when the section list is long.
- **Sections one at a time by default.** The operator checks each render before the next; `sections` renders the rest in one go when they are confident.
- **Briefing final before any image.** Questions are answered on text; images settle design, not facts.
