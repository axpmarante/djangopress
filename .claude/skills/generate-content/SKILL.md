---
name: generate-content
description: Guide through the full DjangoPress content generation workflow — from project briefing to finished pages with images, header, and footer.
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, AskUserQuestion, WebFetch
---

# DjangoPress Content Generation Guide

Walk the user through generating content for their DjangoPress site. This covers the full pipeline from project briefing to polished pages.

## Pre-flight Check

Before starting, verify the site is configured:

```bash
python manage.py shell -c "
from core.models import SiteSettings, Page
s = SiteSettings.objects.first()
if not s:
    print('ERROR: No SiteSettings found. Run /new-site first.')
else:
    print(f'Site: {s.get_site_name()}')
    print(f'Domain: {s.domain or \"NOT SET\"}')
    print(f'Languages: {s.get_language_codes()}')
    print(f'Default: {s.get_default_language()}')
    print(f'Briefing: {\"YES\" if s.project_briefing else \"MISSING\"}')
    print(f'Design guide: {\"YES\" if s.design_guide else \"MISSING\"}')
    print(f'Existing pages: {Page.objects.count()}')
    print(f'Active pages: {Page.objects.filter(is_active=True).count()}')
"
```

**If briefing is missing**, this is the most critical piece. Ask the user to describe their business in detail — the AI reads this for every generation. Write it to SiteSettings:

```bash
python manage.py shell -c "
from core.models import SiteSettings
s = SiteSettings.objects.first()
s.project_briefing = '''<detailed briefing>'''
s.save()
"
```

## Phase 1: Plan the Pages

Ask the user what pages their site needs. Common structures:

**Business/Corporate:**
- Home, About, Services, Portfolio/Projects, Contact

**Restaurant:**
- Home, Menu, About/Story, Gallery, Reservations, Contact

**Real Estate:**
- Home, Properties (listing app), About, Services, Contact

**E-commerce:**
- Home, Shop (app), About, FAQ, Contact

For each page, ask for a brief description of what it should contain (sections, content focus, tone).

## Phase 2: Generate Pages

### Option A: Bulk Generation (recommended for new sites)

Direct the user to `/backoffice/ai/` → **Bulk Pages**. They paste a multi-page description and the AI generates all pages at once.

### Option B: One at a Time

Direct to `/backoffice/ai/generate/page/`. For each page:
1. Enter the page brief/description
2. Select AI model (Gemini Pro recommended for speed)
3. Check "Add image placeholders" if the page needs images
4. Generate and review
5. Save to DB

### Option C: Via API (for scripting)

```bash
python manage.py shell -c "
from ai.services import ContentGenerationService
from core.models import SiteSettings

settings = SiteSettings.objects.first()
service = ContentGenerationService()

# Generate a page
result = service.generate_page(
    brief='Create a modern hero section with a call to action, followed by a services grid showing 6 services with icons, then a testimonials carousel, and a CTA banner.',
    model='gemini-pro',
    add_image_placeholders=True,
)
print('HTML length:', len(result.get('html', '')))
print('Translations:', list(result.get('content', {}).get('translations', {}).keys()))
"
```

## Phase 3: Refine Pages

After initial generation, each page likely needs refinement. Options:

### Chat Refinement (recommended)
Go to `/backoffice/ai/chat/refine/<page_id>/`. This is conversational — you can say things like:
- "Make the hero section more impactful with a darker overlay"
- "Add a pricing table section after services"
- "Change the testimonials to a 3-column grid instead of carousel"
- "Make the color scheme match our brand better"

The chat preserves history so the AI doesn't undo previous changes.

### Section-Level Refinement
Target specific sections by name (from `data-section` attributes). This is ~8x cheaper than regenerating the full page since only the target section is output.

## Phase 4: Generate Header & Footer

Go to `/backoffice/settings/header/` and `/backoffice/settings/footer/`.

Use "Quick AI Edit" with instructions like:
- "Create a modern sticky header with logo on the left, navigation links in the center, and a CTA button on the right. Include a mobile hamburger menu."
- "Create a footer with 4 columns: About, Quick Links, Contact Info, Newsletter signup. Include social media icons and copyright."

**Tip:** Upload reference screenshots for better results.

## Phase 5: Process Images

After all pages are generated with placeholders:

1. Go to `/backoffice/page/<id>/images/` for each page
2. Click **"AI Suggest Prompts"** — the AI analyzes the page context and suggests:
   - Generation prompts per image
   - Aspect ratios (1:1, 16:9, 4:3, etc.)
   - Matching images from the media library
3. Review and adjust suggestions
4. Click **"Process Selected"** to generate/assign images

## Phase 6: Design System & Polish

If not already done:

1. Go to `/backoffice/settings/` → Design System section
2. Set brand colors, fonts, button styles
3. Use "AI Generate Design Guide" to create consistency rules
4. Re-refine pages if the design system changed significantly

## Phase 7: Final Review

Checklist:
- [ ] All pages generated and refined
- [ ] Header and footer look good on all pages
- [ ] Image placeholders replaced with real images
- [ ] Design system colors/fonts applied
- [ ] Site looks good on mobile (check with browser dev tools)
- [ ] All languages have translations
- [ ] Home page slug is "home" in all languages
- [ ] Contact form works (if applicable)

## Quick Commands

```
/backoffice/ai/                         → AI generation hub
/backoffice/ai/generate/page/           → Generate single page
/backoffice/ai/bulk/pages/              → Bulk page generation
/backoffice/ai/chat/refine/<page_id>/   → Chat refinement
/backoffice/page/<id>/images/           → Process images
/backoffice/settings/header/            → Header editor
/backoffice/settings/footer/            → Footer editor
/backoffice/settings/                   → Design system & settings
```
