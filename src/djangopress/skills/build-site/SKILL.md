---
name: build-site
description: Fast, unattended build of a one-page DjangoPress site from a content-only briefing — three complete design concepts built in parallel, one imported through the deterministic adapter, verified by check_site + a layout probe + one look at the mobile screenshot, then published. Supervised mode stops once so the operator picks a concept. Never asks questions.
argument-hint: briefings/<slug>.md [supervised] [concepts N] | briefings/<slug>.md pick <k> [notes]
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, Agent
---

# Build a site from three concepts

`$ARGUMENTS` = `<briefing> [supervised] [concepts N]`, or `<briefing> pick <k> [notes]` to resume a
supervised run. Default: unattended, 3 concepts. All commands run through the site venv:
`.venv/bin/python manage.py …`. **Never call `AskUserQuestion`.** Never edit the briefing.

Two rules. **Form from the concept, facts from the briefing**: builders take every name,
price, number and link from the packet, never from imagination. **Deterministic steps are
commands**: you never write settings, pages or menus by hand — `import_concept` does.

Budget: the whole run is ~12 of your turns. Do not add exploratory turns; every step below
names its command.

## Turn 1 — Prepare

```bash
.venv/bin/python manage.py build_prepare <briefing>
```

Stop and print the command's message if it fails (open questions, malformed content line).
Read `docs/build-packet.json` once; you will refer to `site.slug`, `site.default_language`,
`business.type` and `content.home.required` below.

## Turn 2 — Three concept briefs

```bash
.venv/bin/python manage.py build_prompt director --concepts <N>
```

Read `docs/concepts/prompts/director.md` and **answer it yourself in this turn** — you are the
creative director. Split your answer on the `===== CONCEPT <LABEL> =====` lines and write each
block to `docs/concepts/brief-<k>.md` (`k` = label in lowercase: `a`, `b`, `c`, …). Then, for each:

```bash
.venv/bin/python manage.py build_prompt builder <k>
```

## Turn 3 — Three sites in parallel

Dispatch one `Agent` (general-purpose) per concept **in a single message**. Each agent's whole
prompt is the content of `docs/concepts/prompts/builder-<k>.md` plus this line:

> Write the complete document with the Write tool to the OUTPUT path in one call. Do not run
> any command, do not read other files, do not stop before `</html>`. Report only the path.

Wait for all reports.

## Turn 4 — Screen

```bash
.venv/bin/python manage.py build_verify --files docs/concepts/concept-*.html
```

Read `docs/concepts/screen.json`. A concept with `hard_errors` (truncated, malformed) is
rebuilt **once**: dispatch its agent again with the same builder prompt plus
`The previous attempt stopped at <last section id>; the document must be complete and end with </html>.`,
then re-run the screening line. A second failure leaves that concept out.

## Turn 5 — Pick

**Supervised** (`supervised` in `$ARGUMENTS`): print one line per concept —
`<k> · <name> · <register> · <premise> · <clean|defects: n> · docs/concepts/concept-<k>.html` —
then `open docs/concepts/concept-*.html` and stop with:

```
Pick with: /build-site <briefing> pick <k> [what to change]
```

**Resuming with `pick <k> [notes]`**: if notes were given, edit `docs/concepts/concept-<k>.html`
per the notes in one pass (the builder's DOCUMENT CONTRACT still applies; facts unchanged), then
re-run the screening line for that file. Continue with Turn 6.

**Unattended**: `k` = the first concept with `"clean": true` in the order **b, a, c, d, e, f**.
If none is clean, `k = b` and the fix round below is mandatory.

## Turn 6 — Import

```bash
.venv/bin/python manage.py import_concept docs/concepts/concept-<k>.html --home
.venv/bin/python manage.py import_concept docs/concepts/concept-<j>.html --as-page homepage-v2   # every other concept, in key order: v2, v3, …
```

Exit 1 means adapter errors: read the JSON `errors`, fix the file (not the database), re-run. The
extra pages stay out of the menu; they render inside the shipped concept's header and footer.

## Turn 7 — Verify

```bash
.venv/bin/python manage.py build_verify
```

(starts its own dev server on a free port; pass `--port N` only to reuse a server you started)

Read `docs/verify.json`: `check_site` (non-residue failures), `content_missing`, `probe.defects`.

## Turn 8 — One fix round

Read `docs/screenshots/home-390.png` with the Read tool. One question only: *does any section
look broken, or outside this concept's direction?* Combine what you see with `docs/verify.json`
and apply every fix by editing `docs/concepts/concept-<k>.html` — never the database — then:

```bash
.venv/bin/python manage.py import_concept docs/concepts/concept-<k>.html --home
.venv/bin/python manage.py build_verify
```

(starts its own dev server on a free port; pass `--port N` only to reuse a server you started)

**One round.** Whatever remains goes to the report as open items.

## Turn 9 — Report, ledger, commit

Write `docs/build-report.md`:

```markdown
# <Site> — Build Report (<date>)

## Result
Shipped: concept <k> — <name> (<register>). check_site: <OK | n non-residue failures>. Probe: <n defects>. Content contract: <OK | n missing>.
Other concepts, live on this site: /<lang>/homepage-v2/ — <name> · /<lang>/homepage-v3/ — <name>   (files in docs/concepts/)

## Assumptions
- <where the briefing was silent, one line each>

## Open items
- <every remaining verify.json line and screenshot finding, one per line>
- <placeholder images: count, from check_site residue>

## Timing
prepare <s> · briefs <s> · builds <s> · screen <s> · import+verify <s> · fix <s>

## Next
- Switch concept: .venv/bin/python manage.py promote_concept <k> --publish
- Refine: /edit-site <what to change>
- Translate (after sign-off): /generate-site <briefing>
```

Then, for every concept, and `--shipped` only for `<k>`:

```bash
.venv/bin/python manage.py concept_ledger --append docs/concepts/brief-<k>.md --site <site.slug> --key <k> --vertical <business.type> [--shipped]
git add db.sqlite3 docs/ && git commit -m "Build <site> from concept <k> (<name>)"
```

No `Co-Authored-By` lines.

## Turn 10 — Publish

```bash
railway status
```

If this fails, print `Not on Railway yet: run /deploy-site-railway` and stop.

```bash
bash scripts/sync-to-prod.sh && railway redeploy -y
```

Print the live URL from `railway domain` (or the `.env` `RAILWAY_URL`), the report's Result
section, and stop.

## Error handling

- A command exits non-zero: read its JSON, fix the named file or line, retry once, then record
  the failure under Open items and continue.
- Playwright missing (`build_verify` exit 2): record "layout probe skipped" and continue; the
  `check_site` gate still applies.
- An agent reports without writing its file: dispatch it once more; then continue without that
  concept.
- Anything else: record and continue. The run must end with a report even when incomplete.
