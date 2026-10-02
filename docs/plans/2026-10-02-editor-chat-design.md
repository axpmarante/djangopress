# Editor Chat — quick edits, three real directions, better design

**Date:** 2026-10-02
**Status:** Approved (mockup approved 2026-10-02: https://claude.ai/artifact/NHmcZomof5zNPNqDvKmhKw)
**Repo:** djangopress (engine), branch `feature/editor-chat` from `main`.
**Audience:** agency staff (superusers; the Chat tab is AI-only). UI copy in English.

**Goal:** make the editor's Chat tab produce sections that look like the rest of the site rather than basic ones. It also makes the tab faster for specific requests and lets the operator compare and iterate on options.

---

## Context (facts from the code, 2026-10-02)

- **How a section/element refine runs today:**
  - `ai-panel.js` POSTs `/editor-v2/api/refine-multi/stream/` with a "3 options" checkbox that is on by default.
  - The server runs the `RefinementAgent` router (flash, low thinking). With `multi_option` on, the router is forced to regenerate, so the direct-edit fast paths never run.
  - `refine_section_only` makes **one** call that returns 3 variations separated by `<!-- OPTION_N -->`.
  - The prompt (`prompts.py get_section_refinement_prompt`) tells the model to *"keep output concise to fit all 3 options"* and to use **placehold.co** placeholders for any new image.
  - One malformed option fails all three.
  - The page HTML is sent as context, but there are no explicit design references, design vocabulary or directions.
- **Showing and applying results:**
  - Options are previewed one at a time by swapping the live DOM. There is no original toggle and no compare.
  - A follow-up starts from the stored HTML, never from the option being previewed.
  - Apply goes through `/apply-option/` (`ai_apply`: checkpoint, write, then translate every other language) and is followed by a **full page reload**.
- **Gaps in the current flow:**
  - **Cancel and progress:** there is no Cancel, and the agent path sends no progress events.
  - **Non-Page objects:** the stream endpoints use `Page.objects.get`, so news posts break.
  - **Reference images:** these are not offered, although the services accept `reference_images`.
  - **Logging:** routing calls are not logged.

## 1. Two kinds of request

The **mode** is `auto` by default. The client labels its guess under the input box, and the server decides:

| Mode | When | What happens |
|---|---|---|
| **quick** | specific requests: colours, sizes, spacing, text, "title in gold" | the router's direct-edit / apply-edits path. One result, **applied at once** with Undo. No new design is generated. |
| **explore** | open requests: "more elegant", "redesign", "3 directions/options/ideas", or when the router chooses to regenerate | **3 directions** generated in parallel (§2), shown one by one, nothing applied until the operator picks one |

- **Overrides:** the suggestion chips, the "Show 3 directions" action after a quick result, and an explicit `mode` in the request.
- **How auto decides:** keywords first, then the router's decision (direct edit → quick; regenerate → explore).
- **Page scope** keeps one result, as today.

## 2. Three directions in parallel

Each direction is its own generation call (`refine_section_only` / `refine_element_only` with `multi_option=False`), run in a thread pool:

| Key | Name | Brief given to the model |
|---|---|---|
| `refined` | Close to current | Same structure and content order; raise the craft: type scale, spacing rhythm, the site's details (eyebrows, dividers, accents). |
| `bold` | Bolder | Stronger contrast or a colour band from the site palette, larger display type, real imagery from the library. |
| `layout` | New layout | A different layout pattern the site already uses elsewhere (split, cards, editorial list), keeping the content. |

- **Arrival:** each direction is sent to the client as soon as it is ready (SSE `option` event).
- **Failures:** a failed direction is reported on its own; the others stay.
- **"Regenerate"** runs the three again.
- **The concise rule and the "3 variations" block are no longer used for directions.**

## 3. Design context ("Matches") and design vocabulary

New `ai/design_context.py`, `build_design_context(page, target_section, lang)`, returns:

- **Tokens:** colours and fonts from `editor_v2.design_tokens.collect_tokens()`.
- **Design guide:** `SiteSettings.design_guide`.
- **Reference sections:** 2–3 sections that best show the site's style. They are picked from:
  - the current page's other sections;
  - the home page hero;
  - the section with the richest repeated items (cards).

  Ranking is by distinct design classes, which shows the most crafted sections. Each is capped at 6 000 characters. Their names are returned for the UI ("style of: Hero, Eventos").
- **Design vocabulary:** recurring class combinations per role, counted across the site's pages, e.g. "eyebrow: `text-[11px] font-semibold uppercase tracking-[0.22em] text-[#C42014]`" or "section title: `font-['Fraunces'] font-light text-[46px]`". The roles are eyebrow, section title, body text, primary button, link, card, divider. The prompt says to **reuse** these rather than invent new ones.
- **Library images:** up to 12 media-library images (id, URL, alt/description), ranked by overlap with the section's text. New images must use these real URLs, not placehold.co. The placeholder pattern is kept only when nothing fits.

The context goes into the directions' prompts (new `design_context` argument, rendered as a "Site design" block). The "Matches" line in the Chat tab shows the palette, the fonts and the reference section names.

## 4. Design check before showing

New `ai/design_check.py`, `check_and_fix(html, tokens) → (html, notes)`, deterministic. It runs on every direction:

- **Generic Tailwind palette colours** (`bg-blue-500`, `text-gray-600`…) are replaced with the nearest site token colour.
- **Hex colours** close to a site colour (small ΔE) are snapped to it. Far ones are left and noted.
- **Fonts** not among the site fonts are replaced: headings get the heading font, everything else the body font.
- **Placeholder images** that remain are noted.
- **Why it fits:** each direction ends with `<!-- WHY: one sentence on how it matches the site -->`. It is parsed, stripped from the HTML and shown under the options.

## 5. Iterate, compare, apply

- **"Refine this one…"** sends the previewed option's HTML as `base_html`. The next turn starts from it, not from the stored section. The new result is shown with "Original / previous / new".
- **Original:** a tile that restores the current section.
- **Compare with original:** a temporary side-by-side in the page (two scaled copies), toggled from the result card.
- **Thumbnails:** each direction is shown as a scaled live copy of its HTML.
- **Apply without reload:**
  1. `apply-option` returns the saved HTML for the current language.
  2. The client swaps it in, re-runs `initDynamicComponents` and emits `history:refresh`.
  3. It shows the translated / not translated note with Undo. The chat stays.
- **Quick edits** apply the same way.
- **Translation:** an applied change whose visible text did not change (class / attribute only edits) is copied to the other languages **structurally, without re-translating** (new `ai_apply` path).

## 6. Progress, cancel, attachments, plumbing

- **New streaming endpoint:** `POST /editor-v2/api/chat/stream/` (JSON or multipart with `reference_images`) takes `{page_id | content_type_id+object_id, scope, section_name | selector, instructions, mode, base_html, session_id, run_id}`.
- **Events:**
  - `step {key, label, state}`: context → directions → check, or routing → edit;
  - `option {key, name, html, why, notes}`;
  - `option_failed {key, error}`;
  - `applied {html, translated, untranslated}`;
  - `complete {session_id, mode}`;
  - `error`.
- **Cancel:** `POST /editor-v2/api/chat/cancel/ {run_id}`, the same flag-file pattern as the site assistant. Directions already shown stay; pending ones are dropped.
- **Non-Page objects:** both chat endpoints use `_get_editable_object`, which fixes news.
- **Logging:** routing / agent calls are logged to `AICallLog` with `routing_tier`.
- **Old endpoints:** `refine-multi/*` and `refine-page/stream` stay for the section inserter modal and page scope.

## 7. The Chat tab UI (as the mockup)

- **Header:**
  - a target chip with an Element / Section / Page switch;
  - the "Matches" line (palette dots, fonts, reference names).
- **Thread:**
  - user messages, with attachment thumbnails;
  - progress cards with steps, elapsed time and Cancel;
  - result cards: tiles Original + A/B/C (loading shimmer until each arrives), and Apply / Refine this one… / Regenerate / Compare;
  - "Why it fits";
  - applied notes with Undo.
- **Composer:**
  - suggestion chips;
  - a textarea with attachments (clip, drag, paste; images up to 5 × 10 MB);
  - the intent label;
  - Send, which turns into Stop while a run is going.
- **History:** stays in `RefinementSession`. The session dropdown and New chat are kept.

## Out of scope

- The section inserter modal (new section): it keeps its own flow. It can adopt directions later.
- Page-scope directions.
- Model changes.

## Testing

- **Python:**
  - `design_context` (references chosen and capped, vocabulary roles found, library images ranked);
  - `design_check` (palette and font fixes, WHY parsed, notes);
  - directions service (3 parallel calls, one failure isolated, `base_html` used, design context and no "concise" rule in the prompt);
  - attribute-only apply (no translation call, other languages get the class change);
  - chat stream endpoint (events in order, quick auto-applies, cancel, multipart images, news object);
  - logging.
- **JS harness:** the intent classifier and the thumbnail/compare helpers.
- **Browser (demo-ai-eval):**
  - a quick request applies with Undo;
  - "more elegant" shows 3 directions one by one;
  - refine an option, compare, apply without reload, Undo.
- **Eval:** re-run the section cases (N1, N2, N6, N7, N9, C1, C2, C7) through the new endpoint in explore mode on demo-ai-eval, and compare screenshots, times and checks with `2026-10-01-results-phase-1-2.md`.
