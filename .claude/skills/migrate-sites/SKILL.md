---
name: migrate-sites
description: Use when migrating existing client websites to DjangoPress, or continuing a migration batch in progress. Covers all phases from briefing to deployment.
argument-hint: [phase] [batch-number]
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, AskUserQuestion, WebFetch, WebSearch, Task, Skill
---

# Mass Site Migration to DjangoPress

You are guiding the user through a batch migration of ~73 existing client websites to DjangoPress. Each site goes through 4 phases. Work is organized in batches to keep context focused.

The argument provided is: `$ARGUMENTS`

---

## Session Start

1. **Read the status file** to understand current progress:

```
Read: .claude/skills/migrate-sites/migration-status.md
```

2. **Determine what phase/batch to work on:**
   - If `$ARGUMENTS` specifies a phase and batch (e.g. `A 1`, `C 3`), use that.
   - If no argument, check the status file and suggest the next incomplete batch.
   - Ask the user to confirm before starting.

3. **Update the status file** at the end of each session with completed work.

---

## Phase A: Briefing Creation

**Batch size:** 5-10 sites per session.
**Input:** Site URL from the status file.
**Output:** `briefings/<slug>.md` for each site.

### For each site in the batch:

1. **Use `/create-briefing <url>`** — this skill handles web research, content extraction, and briefing writing.

2. **Migration-specific overrides** — After `/create-briefing` asks its questions, ensure:
   - **Languages:** Always PT (default) + EN.
   - **Pages:** Preserve the EXACT page structure from the existing site. List every page with its current sections. Note "migrate content" for each.
   - **Design:** "Migration — improve design with modern Tailwind aesthetics but keep brand identity. Reference existing color scheme."
   - **Business section:** Preserve the real content and tone from the existing site. This is a migration, not a creative rewrite.
   - **Images:** Decide per site — ask the user if the client has original photos or if we need Unsplash/AI.

3. **After the briefing is written**, verify it parses:
```bash
cd /Users/antoniomarante/Documents/DjangoSites/djangopress
python manage.py generate_site briefings/<slug>.md --dry-run
```

4. **Update status:** Mark site as `briefing: done` in the status file.

5. **Move to next site** in the batch.

### When the batch is complete:

Show a summary of all briefings created in this session. Ask if the user wants to continue with the next batch or switch phases.

---

## Phase B: Project Scaffolding

**Batch size:** All sites with completed briefings (can do 10-20 at once).
**Input:** Briefing files in `briefings/`.
**Output:** Child project directories in `/Users/antoniomarante/Documents/DjangoSites/`.

### For each site:

1. **Derive the project name** from the briefing filename (e.g. `willies-restaurante.md` → `willies-restaurante`).

2. **Run the scaffold script:**
```bash
cd /Users/antoniomarante/Documents/DjangoSites/djangopress
./scripts/new_site.sh <project-name> briefings/<slug>.md
```

3. **Verify** the project was created:
```bash
ls /Users/antoniomarante/Documents/DjangoSites/<project-name>/manage.py
```

4. **Update status:** Mark site as `scaffold: done`.

### Skip sites that already have projects:
Check before scaffolding:
```bash
ls /Users/antoniomarante/Documents/DjangoSites/<project-name> 2>/dev/null
```

---

## Phase C: Site Generation + Review

**Batch size:** 3-5 sites per session (generation is slow — each site takes 10-20 min).
**Input:** Scaffolded project with briefing file.
**Output:** Generated site with pages, header, footer.

### For each site:

1. **Navigate to the project:**
```bash
cd /Users/antoniomarante/Documents/DjangoSites/<project-name>
```

2. **Generate the site using the skill:**
```
/generate-site briefings/<slug>.md
```

3. **Quick quality check** — start the dev server and verify:
```bash
python manage.py runserver 8000
```
   Tell the user to check it at `http://localhost:8000/` and ask:
   - Do all pages load?
   - Does the header/footer look right?
   - Is the content accurate?
   - Any sections that need refinement?

4. **Refine if needed** — use `/generate-content` or chat refine in the backoffice.

5. **Update status:** Mark site as `generated: done`.

### Sites needing custom apps:

These 6 sites need `/add-app` AFTER page generation:
- `algarvelusttantric.pt` — booking/services
- `kissdiscoclub.com` — events/calendar
- `centralgarve.com` — listings/directory
- `arquitectosalgarve.pt` — portfolio/projects
- `portugalwebdesign.pt` — portfolio/case studies
- `roseusfabri.com` — catalog/shop

Ask the user what app type is needed for each before scaffolding it.

---

## Phase D: Deployment to Railway

**Batch size:** 5-10 sites per session.
**Input:** Generated and approved site.
**Output:** Live site on Railway.

### For each site:

1. **Navigate to the project** and use the deploy skill:
```
/deploy-site <project-name>
```

2. **After deployment**, verify:
   - Home page loads (200)
   - All pages accessible
   - Backoffice login works
   - Images display correctly

3. **Note the Railway URL** in the status file.

4. **Custom domain** — tell the user to:
   - Add the custom domain in Railway dashboard
   - Update DNS records at the registrar
   - Wait for SSL provisioning

5. **Update status:** Mark site as `deployed: done` with the Railway URL.

---

## Migration Rules (what's different from a new site)

1. **Preserve content.** The AI should reproduce the existing site's content, not invent new text. The briefing's Business section should contain the real business description from their current site.

2. **Preserve page structure.** Keep the same pages and section layout. Don't add or remove pages unless the user specifically asks.

3. **Improve design.** Use modern Tailwind CSS, responsive layouts, better typography. The design should be an upgrade, not a clone of the old site.

4. **All sites are PT + EN.** Portuguese is always the default language.

5. **Images are case-by-case.** Some clients have original photos (reuse via Unsplash or upload). Others need stock/AI images. Ask the user per site.

6. **Don't change the business.** The briefing should describe what the business IS, not what it could be. Preserve tone, services, and positioning.

---

## Key Principles

- **One phase at a time.** Don't mix phases in a session unless the user asks.
- **Update the status file.** Always update `migration-status.md` at the end of each session.
- **Commit progress.** After completing each site's phase, commit the briefing/changes.
- **Ask before deciding.** For each site, confirm image strategy and design direction with the user.
- **Skip what's done.** Check the status file and skip sites already completed for the current phase.