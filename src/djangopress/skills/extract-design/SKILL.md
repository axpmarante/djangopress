---
name: extract-design
description: Turn the approved mockups into an executable design system — sampled palette mapped to SiteSettings fields, a concrete Google Fonts pair, type scale, layout tokens, and a per-section UI spec — and write it into docs/design-system.md, the briefing and SiteSettings. Runs after mockup-site sections are approved and before generate-site.
argument-hint:
allowed-tools: Bash, Read, Write, Edit, Grep, Glob
---

# Extract the design system from the mockups

Inputs: `docs/mockups/00-master.png`, every `docs/mockups/NN-<name>.png`, the briefing. If the master or the sections are missing, say which command produces them and stop.

**Rule.** Form from the images, facts from the briefing. Any text, price, address, name, review or menu item you can read in an image is ignored; the briefing already holds the real ones.

## 1. Sample the palette

```bash
.venv/bin/python manage.py sample_palette docs/mockups/00-master.png --k 8 --json
```

Open the master with the Read tool. Assign roles to the sampled colors by where they appear: page background, card/surface, body text, accent (buttons, prices, highlights), secondary (links, supporting), dark block. Use the sampled hex values, rounded to the nearest 4 per channel; keep the briefing's palette only where the image confirms it.

## 2. Classify the typography

From the master and the hero section: heading face (serif / sans / slab / display; contrast; weight), body face. Map to a concrete Google Fonts pair, for example:

| Seen in the image | Google Fonts |
|---|---|
| high-contrast transitional serif headings | Playfair Display |
| low-contrast humanist serif headings | Lora |
| geometric sans headings | Bricolage Grotesque, Manrope |
| grotesk body | Instrument Sans, Inter Tight |
| humanist sans body | Source Sans 3 |

Record the classification next to the choice so a reviewer can disagree with the mapping, not the observation.

## 3. Write `docs/design-system.md`

```markdown
# <Site> — Design System (from docs/mockups/00-master.png, <date>)

## Tokens

### Palette (SiteSettings fields)
| Role | Hex | Field |
|---|---|---|
| background | #… | background_color |
| surface | #… | (Tailwind arbitrary value in HTML) |
| text | #… | text_color |
| headings | #… | heading_color |
| accent (CTAs, prices) | #… | primary_color, primary_button_bg |
| accent (secondary highlight) | #… | accent_color |
| secondary | #… | secondary_color |
| dark block | #… | (Tailwind arbitrary value in HTML) |

### Type
- Heading: <font> (<classification>) — field heading_font
- Body: <font> (<classification>) — field body_font
- Scale (desktop / mobile): h1 <size>/<size>, h2 …, body 16–18px, eyebrow 11–12px uppercase tracked

### Layout
- container_width: <7xl | 6xl | …>  (content width seen ≈ <px>)
- border_radius_preset: <none | sm | md | lg | …>
- shadow_preset: <none | sm | md | …>
- spacing_scale: <tight | normal | relaxed | loose>  (section padding seen ≈ <px>)
- Grid: <e.g. 12 columns, text 5 / image 6 offset>
- Buttons: height ≈ <px>, padding <px>, radius <px>, primary filled accent, secondary outlined
- Dividers and motifs: <what and where>
- Photography: <treatment, warmth, crop style>; max render width per image group from the briefing's Images constraints

## Sections

### 01-hero
Image: docs/mockups/01-hero.png
- Layout: <grid / split / full-bleed>, image ratio <w:h>, image max width <px>
- Background: <token>
- Elements in order: <eyebrow, h1, lead, primary CTA, secondary CTA, badge…>
- Editable text: <which elements>
- Notes: <anything the build must reproduce, e.g. offset, overlay, divider>

### 02-… (one per rendered section)
Image: docs/mockups/02-….png
```

## 4. Write back to the briefing

- `## Design Preferences`: replace the bullets with the token values (hex, font names, radius, layout signature, motif), keep the `Avoid` and `References` bullets and the `Reference mockup` line.
- `## Pages` → Home: rewrite the section list in the master's order; each entry `N. <name> — <purpose> — spec: docs/design-system.md → section NN-<name>`. Facts (dish names, prices, hours, contacts) stay exactly as they were.

## 5. Write SiteSettings

```bash
.venv/bin/python manage.py shell -c "
from djangopress.core.models import SiteSettings
s = SiteSettings.load()
s.background_color = '<hex>'; s.text_color = '<hex>'; s.heading_color = '<hex>'
s.primary_color = '<hex>'; s.secondary_color = '<hex>'; s.accent_color = '<hex>'
s.primary_button_bg = '<hex>'; s.primary_button_text = '<hex>'
s.heading_font = '<font>'; s.body_font = '<font>'
s.container_width = '<value>'; s.border_radius_preset = '<value>'; s.shadow_preset = '<value>'; s.spacing_scale = '<value>'
s.design_guide = open('docs/design-system.md').read().split('## Sections')[0]
s.save(); print('design system written')
"
.venv/bin/python manage.py check_site --only settings || true
```

## 6. Commit and report

```bash
git add docs/design-system.md briefings/ docs/mockups/00-master.png docs/mockups/prompts docs/mockups/costs.json docs/mockups/.gitignore
git commit -m "Design system extracted from approved mockups"
```

Print the token table and the section list, then: `Next: /generate-site briefings/<slug>.md` (add `rebuild` when the site already has pages).
