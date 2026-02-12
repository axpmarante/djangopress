# DjangoPress — Site Generation Guide

Quick reference for creating new sites with Claude Code.

---

## Workflow Options

### A. Briefing-Driven (recommended)

Let Claude Code research the client and write the briefing for you, then generate the site.

```
1. /create-briefing My Client     ← researches client, writes briefing interactively
2. /generate-site briefings/my-client.md
```

Or write the briefing manually:

```
1. cp briefings/TEMPLATE.md briefings/my-site.md
2. Edit briefings/my-site.md with your business details
3. /generate-site briefings/my-site.md
```

### B. New Project + Briefing

For production sites that need their own repo.

```
1. ./scripts/new_site.sh my-client briefings/my-client.md
2. cd ../my-client && source venv/bin/activate
3. /generate-site briefings/my-client.md
```

### C. Interactive (no briefing)

When you want to configure everything step by step.

```
1. /new-site my-project
2. /generate-content
```

### D. Batch / Non-Interactive

For scripted generation without Claude Code reviewing each step.

```
python manage.py generate_site briefings/my-site.md --dry-run        # preview
python manage.py generate_site briefings/my-site.md                  # full run
python manage.py generate_site briefings/my-site.md --skip-images    # faster
```

---

## Writing a Good Briefing

The briefing is the single most important input. A detailed briefing = a better site.

### Required Sections

| Section | What to Write | Example |
|---------|---------------|---------|
| **Business** | 2-5 paragraphs: what they do, audience, tone, USPs | "Family-owned restaurant in Ericeira, specializing in fresh seafood..." |
| **Languages** | Default + additional languages | Default: pt (Portuguese), Additional: en (English) |
| **Contact** | Email, phone, address, Google Maps URL | reservas@example.pt, +351 261 862 000 |
| **Pages** | Each page with `**Name**: description` format | **Home**: Hero with sunset photo, featured dishes, testimonial... |
| **Domain** | Storage identifier (lowercase, hyphens) | my-restaurant-pt |

### Optional but Valuable

| Section | Impact |
|---------|--------|
| **Social Media** | Links appear in header/footer automatically |
| **Header** | Specific nav style, CTAs, sticky behavior. If omitted, Claude picks a sensible default |
| **Footer** | Column layout, what to include. If omitted, auto-generated |
| **Design Preferences** | Colors, fonts, mood, references. If omitted, Claude picks based on industry |
| **Images** | Strategy: Unsplash, AI-generated, mix, or skip |
| **Additional Notes** | Special requirements, seasonal content, accessibility, legal |

### Page Description Tips

Be specific about **sections** you want, not just the topic:

```markdown
## Pages

- **Home**: Hero with a photo of the building at sunset. Welcome message about
  our heritage. Featured dishes section (3-4 items with photos). A testimonial
  quote. Opening hours and a "Reserve" CTA. Brief section about the terrace.

- **Menu**: Full menu by category: Starters, Fish, Meat, Desserts, Drinks.
  Each item with name, description, and price. Note about daily specials
  and dietary accommodations.
```

Not just:
```markdown
- **Home**: The home page
- **Menu**: Our menu
```

### Design Preferences Tips

You can be as specific or vague as you want:

**Specific** (Claude uses your exact values):
```markdown
## Design Preferences
- Colors: Primary #1B2A4A (navy), Accent #C4703F (terracotta), Background #FAF7F2
- Fonts: Playfair Display for headings, Inter for body
- Mood: Mediterranean warmth, elegant but approachable
```

**Vague** (Claude picks based on business type):
```markdown
## Design Preferences
Warm and inviting, traditional but modern. Should make people hungry.
```

**Omitted** — Claude uses industry conventions:
- Restaurant: warm earthy tones, serif headings
- Tech/SaaS: modern blues, sans-serif
- Medical: clean whites and teals
- Real Estate: dark luxury tones, elegant serif
- Creative agency: bold contrasts, spacious layout

---

## What Happens During Generation

When you run `/generate-site`, Claude Code:

1. **Reads the briefing** — extracts all structured data, understands the business
2. **Confirms the plan** — shows you what it understood, asks to proceed
3. **Configures SiteSettings** — domain, languages, contact, social, design system colors/fonts
4. **Generates home page first** — establishes visual style for the rest
5. **Optionally generates a design guide** — improves consistency across pages
6. **Generates remaining pages** — one by one, reviewing HTML quality after each
7. **Creates menu items** — links navbar to all pages
8. **Generates header** — uses menu items + briefing instructions
9. **Generates footer** — contact info, links, social icons
10. **Processes images** — replaces placeholders with AI-generated or Unsplash photos
11. **Final summary** — lists everything created, any errors, next steps

### Claude Code Reviews Quality

After each page, Claude checks:
- All `<section>` tags have `data-section` and `id` attributes
- Text uses `{{ trans.xxx }}` variables (not hardcoded)
- Section structure matches the brief
- No empty sections or broken HTML
- Image placeholders have `data-image-prompt` metadata

If something is wrong, Claude refines the page automatically before moving on.

---

## After Generation

### Immediate Next Steps

1. **Start the server**: `python manage.py runserver 8000`
2. **Review the site**: visit `http://localhost:8000/`
3. **Upload logos**: go to `/backoffice/settings/` (domain is already set)
4. **Refine pages**: use `/backoffice/ai/chat/refine/<page_id>/` for conversational editing
5. **Process remaining images**: `/backoffice/page/<id>/images/` for manual control

### Common Adjustments

| Task | Where |
|------|-------|
| Change colors/fonts | `/backoffice/settings/` → Design System |
| Edit page content | `/backoffice/page/<id>/edit/` or add `?edit=true` to any page URL |
| Refine a page with AI | `/backoffice/ai/chat/refine/<page_id>/` |
| Regenerate header/footer | `/backoffice/settings/header/` or `footer/` → Quick AI Edit |
| Replace an image | `/backoffice/page/<id>/images/` |
| Add a new page | `/backoffice/ai/generate/page/` |
| Add a blog/app | `/add-app blog` |

---

## Key Rules to Remember

- **Home page slug must be `home` in ALL languages** — this is how the root URL works
- **Set domain BEFORE uploading logos/media** — it determines the storage folder
- **Project briefing is the #1 quality driver** — the more detail, the better the AI output
- **Header/footer need menu items first** — generate pages before header/footer
- **LocMemCache in dev** — restart the server to see GlobalSection changes, or use DummyCache
- **`base.html` handles `<html>`, `<head>`, `<body>`, header, footer** — page HTML is content only

---

## Example: Full Flow

```bash
# 1. Write the briefing (use TEMPLATE.md as starting point)
cp briefings/TEMPLATE.md briefings/windmill.md
# Edit with business details, pages, design preferences...

# 2. Preview what will be generated
python manage.py generate_site briefings/windmill.md --dry-run

# 3. Generate interactively (Claude Code reviews quality)
/generate-site briefings/windmill.md

# 4. Review and refine
python manage.py runserver 8000
# Visit http://localhost:8000/ — review each page
# Use chat refinement for adjustments

# 5. Deploy
# Push to GitHub, deploy to Railway/server
```

---

## Reference Files

| File | Purpose |
|------|---------|
| `briefings/TEMPLATE.md` | Empty briefing template — copy and fill in |
| `briefings/example-restaurant.md` | Complete example (O Moinho restaurant) |
| `CLAUDE.md` | Full project reference for Claude Code |
| `.claude/skills/generate-site/SKILL.md` | The skill's internal instructions |
| `ai/site_generator.py` | `SiteGenerator` engine (used by management command) |
| `ai/management/commands/generate_site.py` | Batch generation command |
| `scripts/new_site.sh` | New project setup script |
