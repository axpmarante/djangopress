# Mockup Pipeline (Level A2) — Design Spec

**Date:** 2026-09-15
**Status:** Draft
**Repo:** djangopress (engine). No manager changes.
**Depends on:** Site Build Pipeline (Level A), merged in 3.6.0.
**Goal:** Put an approved image between the briefing and the build. From the draft briefing, generate master one-page mockups; the operator picks one; every section is then rendered in high resolution from that master; a design system and per-section UI specs are extracted from the images; the build implements them. The mockup is mandatory: `generate-site` refuses to run without an approved master and an extracted design system.

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
| `gpt-image-2.5-flare` | Master variants | Same price as Sunburst, about half the latency; variants are for choosing a direction, not for detail. |
| `gpt-image-2.5-sunburst` | Promoted master, every section, regenerations | Built for precision across chained edits, which is exactly "expand this section without redesigning". |

No other image model is called. `LLMBase.generate_image()` (Google) stays untouched for site photography.

### Size rules (from the OpenAI image guide)

`size` is `WIDTHxHEIGHT`; both multiples of 16; aspect ratio between 1:3 and 3:1; no edge above 3840; total pixels between 655,360 and 8,294,400; above 2560×1440 is experimental. Quality: `low`, `medium`, `high`, `xhigh`, `max`, `auto`.

A real one-page is taller than 1:3, so a master is rendered at the 1:3 limit with sections compressed, which is enough to choose a direction. Detail comes from the section renders.

### Pricing (per million tokens, identical for both models)

Text input $5, image input $8, image output $30. OpenAI's per-image estimates exist only for `gpt-image-2` (high quality 1536×1024 ≈ $0.165) and it states 2.5 uses different token counts. The command therefore records `usage` from every response and computes cost from the token rates, so the real number is known after the first site. Conservative budget per site at high quality: 3 masters + 14 sections + 7 regenerations ≈ $4–5.

---

## Where it sits in the flow

```
Novo site (manager)
  → create-briefing Phase 1–2: research, draft briefing
  → mockup-site masters: 3 master variants (Flare, medium)          ← new
  → question block (create-briefing Phase 3) now includes "which master?"
  → mockup-site promote <n>: chosen variant re-rendered (Sunburst, high) → 00-master.png
  → mockup-site sections: every section from the master (Sunburst, high)
  → operator reviews; mockup-site section <name> regenerates one with a note
  → extract-design: design-system.md + per-section UI specs; briefing Pages and
    Design Preferences rewritten from the master; SiteSettings design fields set
  → generate-site (gated on 00-master.png + design-system.md)
  → review / translate / deploy (unchanged)
```

The operator touches the flow at three points: choosing a master, reviewing sections, and the build review. Everything else runs unattended. For a single site done by hand each skill is invoked explicitly; for five sites the masters and sections of all five run in parallel and the two choice points are batched.

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
def edit(prompt, *, references: list[Path], size, quality, model, input_fidelity='high', client=None) -> ImageResult
```

`ImageResult` carries `png_bytes`, `usage` (input text/image tokens, output tokens), `cost_usd`, `model`, `size`, `quality`, `elapsed_s`. `generate` calls `client.images.generate(model=..., prompt=..., size=..., quality=..., output_format='png', n=1)`; `edit` calls `client.images.edit(model=..., image=[open files...], prompt=..., size=..., quality=..., input_fidelity=...)`. The client comes from `OPENAI_API_KEY` (same env access as `llm_config.py`). Errors from the API surface as `ImageGenerationError(message, retryable: bool)`; rate-limit and 5xx are retried twice with backoff, content-policy and 4xx are not.

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

`src/djangopress/skills/mockup-site/SKILL.md`. Modes by first argument. All prompts are written to `docs/mockups/prompts/` first, so the operator can read and edit them and re-run.

**`masters`** — Builds `docs/mockups/prompts/00-master.md` from the draft briefing: Business (tone, positioning, audience), the Pages entry for the home page as the section list, Design Preferences (palette roles, type pair, layout signature, motif, avoid list), language, and the rule that the image is a desktop one-page at ~1440px with sections top to bottom and no invented facts beyond placeholder copy. Renders three variants with `flare`, `medium`, `1280x3840` into `master-v1.png` … `master-v3.png`, varying one axis per variant (composition density, photography vs. type-led, warm vs. cool neutral) while keeping the briefing's palette and avoid list. Prints the three paths and stops. When more than ~9 sections are listed, renders each variant as two halves (`-top`, `-bottom`) with the top as reference for the bottom.

**`promote <n>`** — Re-renders `master-v<n>.png` with `sunburst`, `high`, same size, edits endpoint with the variant as the only reference and the master prompt plus "keep this composition exactly; increase fidelity and legibility". Writes `00-master.png`. Records the choice in the briefing under Design Preferences → `Reference mockup: docs/mockups/00-master.png`.

**`sections`** — Reads `00-master.png` and identifies the section sequence with approximate y-ranges (top and bottom as fractions). Reconciles it with the briefing's Pages section: sections in the master but not in the briefing are added to the briefing as proposals; sections in the briefing but not in the master are appended to the render list without a crop. For each section writes `prompts/NN-<name>.md` with five blocks: master-reference instruction (the operator's "do not redesign" rule, verbatim), project context, section brief, content, consistency rules. Content is real: dish names and prices from the menu JSON, hours, phone, address from the briefing; navigation labels in the default language. Crops the master with `crop_mockup`, then renders with `sunburst`, `high`, references master + crop, size from the table below. Writes `docs/mockups/NN-<name>.png` and prints a contact sheet listing.

| Section type (by name or briefing note) | Size | Ratio |
|---|---|---|
| hero, cta, band, wine/inverted block | 1920×1088 | 16:9 |
| editorial split (about, story, product, events, location) | 1536×1024 | 3:2 |
| gallery, menu, pricing, grid of 4+ items | 1536×1536 | 1:1 |
| testimonials, trust bar | 1920×832 | 2.3:1 |
| header alone, footer | 1920×640 | 3:1 |

A `ratio:` line in the section's briefing entry overrides the table.

**`section <name> [note]`** — Regenerates one section, appending the operator's note to the prompt ("less text", "show the terrace", "use the dark treatment"). Keeps the previous file as `NN-<name>.prev.png`.

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

- Phase 2 ends by invoking `mockup-site masters` before printing the question block, and the block's first question becomes "Which master, 1, 2 or 3? Or what to change for another round?" with variant 1 as the proposed default.
- Phase 3 applies the choice with `mockup-site promote <n>` before finalizing the briefing. The hand-off offers `mockup-site sections` as the next step instead of `generate-site`.

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
- **Flare for variants, Sunburst for everything kept.** Same price; the split trades speed where detail does not matter.
- **Costs are measured, not estimated.** Every call appends to `costs.json`.
- **1:3 master.** Accept compression; halves only when the section list is long.
