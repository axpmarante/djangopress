---
name: create-briefing
description: Interactive wizard to create a site briefing by researching the client online and asking targeted questions.
argument-hint: [client-name-or-url]
allowed-tools: Bash, Read, Write, Grep, Glob, AskUserQuestion, WebFetch, WebSearch
---

# Interactive Briefing Generator

You are creating a DjangoPress site briefing through research and conversation. The goal is to produce a `briefings/<slug>.md` file that follows the exact template format so `BriefingParser` in `ai/site_generator.py` can parse it.

The argument provided is: `$ARGUMENTS`

---

## Phase 1: Starting Point

Determine what the user gave you:

- **If `$ARGUMENTS` looks like a URL** (contains `http`, `www`, or `.com`/`.pt`/etc.) → treat it as the client website. Proceed to Phase 2 with this URL.
- **If `$ARGUMENTS` is a name** (text without URL patterns) → use it as the business name. Ask the user:

```
AskUserQuestion: "Do you have a website URL for <name>? (paste it, or skip to answer questions manually)"
Options: "Skip — no website", "Other" (for URL input)
```

- **If no argument** → ask:

```
AskUserQuestion: "What's the client/business name?"
Options: (free text via "Other")
```

Then ask for a website URL as above.

Store whatever you have: `business_name` (if known) and `website_url` (if provided).

---

## Phase 2: Web Research

**Only run this phase if a URL was provided.** If no URL, skip to Phase 3.

Research is the #1 value of this skill — don't ask the user for info that's on their website.

### 2a. Fetch and crawl the client website

**Step 1: Fetch the homepage.** Use `WebFetch` on the main URL. Extract:
- Business name and tagline
- What they do — services, products, specialties
- Contact info: email, phone, address
- Social media links (check header, footer, contact page)
- Visual style observations: colors, mood, typography, imagery style
- Any awards, certifications, press mentions
- Opening hours (if applicable)

**Step 2: Extract all internal links.** From the homepage, collect every link from:
- **Navigation bar** (including dropdown/submenu items)
- **CTA buttons** and prominent links in the hero/header area
- **Footer links** (quick links, service pages, legal pages)

Filter to internal links only (same domain). Deduplicate and ignore anchors (`#`), mailto, tel, and file downloads.

**Step 3: Fetch each page.** Use `WebFetch` on every internal link found. For each page extract:
- Page title and URL
- Main content summary (what the page is about, key sections)
- Specific services, products, or info listed
- Forms (contact, booking, quote request)
- Gallery or portfolio items
- Testimonials or reviews
- Any data not found on the homepage

Fetch pages in parallel where possible. If a page fails, note it and move on.

**Step 4: Build a complete site map.** Compile all findings into a structured overview of every page and its content. This becomes the foundation for the Pages section in the briefing.

### 2b. Fetch social media profiles

If you found social media links, use `WebFetch` on Instagram and Facebook pages to gather:
- Bio/description
- Follower counts
- Tone of voice and posting style
- Additional business details not on the website

**Graceful degradation:** If any fetch fails (blocked, timeout, 404), note it and move on. Never let a failed fetch block the process.

### 2c. Web search

Use `WebSearch` for `"<business name>" <city/location>` to find:
- Google reviews and ratings
- Awards or press mentions
- Google Maps listing
- Additional social profiles not found on the website
- Competitor context

### 2d. Present findings

Show the user everything you found, organized clearly:

```
Here's what I found about [Business Name]:

**Business:** [summary]
**Location:** [address]
**Contact:** [email, phone]
**Social Media:** [links found]
**Visual Style:** [observations about their current branding]
**Notable:** [awards, reviews, press]

**Site Map** (X pages crawled):
- **Home** (/) — [brief summary of content]
- **About** (/about) — [brief summary]
- **Services** (/services) — [brief summary]
- ... [every page found]

Does this look right? Anything to correct or add?
```

Use `AskUserQuestion` to confirm:
```
Question: "Is this information accurate? Anything to correct?"
Options: "Looks good — continue", "I'll make corrections" (Other)
```

If the user provides corrections, incorporate them.

---

## Phase 3: Interactive Questions

Fill in gaps not covered by web research. Use `AskUserQuestion` with structured options wherever possible. **Skip questions you already have answers for** from Phase 2.

### 3a. Languages

```
AskUserQuestion (multiSelect: true):
Question: "What languages should the site support?"
Options:
- "Portuguese (pt)" — most common default
- "English (en)"
- "French (fr)"
- "Spanish (es)"
(Other for additional languages)
```

Then ask which is the default language:
```
AskUserQuestion:
Question: "Which should be the default language?"
Options: [list selected languages]
```

### 3b. Pages

Suggest a page structure based on the industry/business type. Use what you know from the website research (if any) to make informed suggestions.

```
AskUserQuestion (multiSelect: true):
Question: "Which pages should the site have? (I've suggested based on [industry/current site])"
Options:
- "Home" — always included
- "[Industry-specific page 1]" — e.g. "Menu" for restaurant, "Services" for agency
- "[Industry-specific page 2]" — e.g. "Gallery", "Portfolio", "Products"
- "Contact"
(Other for additional pages)
```

Then for **each selected page**, ask for details. If you have info from the existing website, propose it:

```
For the [Page Name] page, what should it include?

[If you have existing website content]: "Based on their current site, I'd suggest:
- [Section 1 description]
- [Section 2 description]
- [Section 3 description]

Want to keep this structure, modify it, or describe something different?"
```

Be specific about sections — don't accept "the home page" as a description. Probe for:
- Hero section: what image/message
- Key content sections
- CTAs (calls to action)
- Special features (forms, maps, galleries, pricing tables)

### 3c. Current site feedback (if they have an existing site)

```
AskUserQuestion:
Question: "What do you like or dislike about the current site?"
Options:
- "Complete redesign — start fresh"
- "Keep the structure, refresh the look"
- "I'll describe specific changes" (Other)
```

### 3d. Design direction

```
AskUserQuestion (multiSelect: true):
Question: "What's the design mood you're going for?"
Options:
- "Elegant & refined"
- "Modern & clean"
- "Bold & energetic"
- "Warm & inviting"
(Other for specific colors, fonts, or reference sites)
```

If the user has specific colors, fonts, or reference sites, note them. If they chose a mood, you'll translate that into specific design values in the briefing.

### 3e. Image strategy

```
AskUserQuestion:
Question: "How should we handle images?"
Options:
- "Mix of Unsplash + AI (Recommended)" — stock photos for general imagery, AI for custom
- "Unsplash stock photos only"
- "AI-generated images only"
- "Skip for now — add images later"
```

### 3f. Domain identifier

Suggest a slug based on the business name and location:

```
AskUserQuestion:
Question: "What domain identifier should we use for storage? (lowercase, hyphens only)"
Options:
- "<suggested-slug>" — e.g. "omoinho-ericeira" based on the business name
- "<alternative-slug>" — shorter or different variant
(Other for custom input)
```

### 3g. Additional requirements

```
AskUserQuestion:
Question: "Any special requirements? (accessibility, legal, seasonal content, specific features)"
Options:
- "No, that covers everything"
- "Yes, I'll describe them" (Other)
```

---

## Phase 4: Write the Briefing

Compile all gathered information into the **exact format** that `BriefingParser` expects. Read the template first:

```
Read: briefings/TEMPLATE.md
```

### File format rules (critical for parsing)

The briefing **must** follow these rules or `BriefingParser` will fail:

1. **Title line:** `# Business Name — Site Briefing`
2. **Sections** use `## Section Name` (exact names: Business, Languages, Contact, Social Media, Pages, Header, Footer, Design Preferences, Images, Domain, Additional Notes)
3. **Languages format:**
   ```
   - Default: pt (Portuguese)
   - Additional: en (English), fr (French)
   ```
4. **Contact format:**
   ```
   - Email: name@example.com
   - Phone: +351 ...
   - Address:
     - pt: Rua ...
     - en: Street ...
   - Google Maps: https://maps.google.com/...
   ```
   For a single-language site or same address in all languages, just use `- Address: Street Name, City`
5. **Social Media format:**
   ```
   - Instagram: https://instagram.com/handle
   - Facebook: https://facebook.com/page
   ```
   Supported platforms: Instagram, Facebook, LinkedIn, YouTube, Twitter, TikTok, Pinterest, WhatsApp
6. **Pages format:** Markdown list with bold names:
   ```
   - **Page Name**: Description of content and sections...
   ```
   Multi-line descriptions are fine — the parser reads until the next `- **` entry.
7. **Domain:** Just the identifier on its own line, e.g. `my-business-name`
8. **Images:** Must contain keywords for strategy detection:
   - "skip" → skip images
   - "unsplash" + "ai"/"mix"/"both" → mixed strategy
   - "unsplash" alone → unsplash preferred
   - anything else → AI generated

### Writing the Business section

This is the **most important section** — it becomes the `project_briefing` that drives ALL AI generation. Make it rich and detailed (3-5 paragraphs):

- What the business does and its specialties
- History and heritage (if known)
- Target audience
- Tone of voice and personality
- Unique selling points
- Location context and competitive positioning
- Awards, press, reputation (if found)

Use everything gathered from web research + user answers. Write it as polished prose, not bullet points.

### Writing the Pages section

For each page, write a **detailed** description with specific sections:

```
- **Home**: Hero with [specific image/message]. [Section about X]. [Section about Y].
  Testimonials or social proof. CTA to [action]. [Any other sections].

- **About**: The story of [business] — [specific narrative]. Team introduction.
  Philosophy/values. Awards and recognition.
```

Don't be vague. "The home page" is not a description. Describe what sections should exist and what content goes in them.

### Header and Footer

If the user didn't specify, suggest sensible defaults based on the industry:

**Header:** Transparent-to-solid on scroll, logo left, nav links, CTA button right, language switcher, mobile hamburger.

**Footer:** 3-column layout — (1) logo + description + social icons, (2) quick links, (3) contact info. Copyright line below.

### Compute the filename

Slugify the business name: lowercase, replace spaces and special characters with hyphens, remove accents:
- "O Moinho" → `o-moinho`
- "Prestige Real Estate Algarve" → `prestige-real-estate-algarve`
- "Café Central" → `cafe-central`

File path: `briefings/<slug>.md`

### Write the file

Use the `Write` tool to create the briefing file. Then show the user the full output:

```
Read: briefings/<slug>.md
```

Ask for confirmation:
```
AskUserQuestion:
Question: "How does the briefing look? Any section you'd like to refine?"
Options:
- "Looks great — done!"
- "Tweak the Business section"
- "Tweak the Pages"
- "Tweak Design Preferences"
(Other for specific edits)
```

If the user wants changes, edit the file and show it again. Repeat until they're satisfied.

---

## Phase 5: Next Steps

Once the briefing is finalized, tell the user:

```
Briefing saved to `briefings/<slug>.md`

Next steps:

  # Preview what will be generated:
  python manage.py generate_site briefings/<slug>.md --dry-run

  # Generate the full site (Claude Code reviews quality):
  /generate-site briefings/<slug>.md

  # Or generate without review (faster, non-interactive):
  python manage.py generate_site briefings/<slug>.md
```

---

## Key Principles

- **Research first, ask second.** Never ask the user for info you can find on their website or social media.
- **Show what you found.** Present research results and let the user correct before writing.
- **The Business section drives everything.** Spend the most effort making it detailed and compelling.
- **Suggest, don't demand.** Propose design values, page structures, and domain names. Let the user override.
- **Graceful degradation.** If `WebFetch` fails (site down, blocked, no URL), fall back to manual questions. Never let a failed fetch block the process.
- **Output must parse.** The file must match `TEMPLATE.md` format exactly — `BriefingParser` in `ai/site_generator.py` parses it.
- **Don't over-ask.** If you have enough info from research, skip redundant questions. 5 focused questions beat 15 tedious ones.
