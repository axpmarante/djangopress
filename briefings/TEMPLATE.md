# [Business Name] — Site Briefing

> One line: what this is (new site / redesign of <url>) and the one-sentence brief.

## Open Questions

Working section written by `/create-briefing` after research and removed when the
briefing is finalized. Five to eight questions only the operator or the client can
answer, each with the proposed default so the build can proceed without an answer.

1. **[Topic].** [Question]? *Proposed: [default].*

## Business

[2-5 paragraphs: what they do, history, target audience, tone of voice, unique
selling points, competitive positioning, reputation (ratings, awards, press).
This becomes `project_briefing` and drives all generation. Polished prose, not bullets.]

## Languages
- Default: [code] ([name])
- Additional: [code] ([name]), ...

## Contact
- Email:
- Phone:
- Address: [single line, or per language as `- pt: ...` / `- en: ...`]
- Google Maps: [embed URL if available]

### Opening hours
[Table or list. Mark "to confirm" if taken from an old site.]

## Social Media
- Instagram:
- Facebook:
- [others: LinkedIn, YouTube, TikTok, Pinterest, WhatsApp, Twitter/X, TripAdvisor]

## Existing Site

[Redesigns only. One row per page of the current site.]

| Current page | Decision | Reason |
|---|---|---|
| / | keep / merge into X / drop | ... |

## Integrations

[Third-party systems to keep, one per line: what, URL, how it is embedded.]

- Reservations: [system] — [URL] — [iframe on /reservas/ | link | none]
- Menu: [PicklyMenu / PDF hosted on site / HTML page]

## Pages

[One entry per page: what the page is for and its meta. Do NOT list sections in order —
the design concept decides how content is grouped and sequenced.]

- **Home**: the one-page site — meta title: [..]; meta description: [..]
- **Reservas**: form (reuse the template's `contact` DynamicForm), map, hours.

## Content

[What each page must communicate, as a flat list. Items marked `(required)` form the
content contract: whichever design concept ships, every required item is verified
present. Grammar: `- (required)? Kind: text [— keywords: a, b, c] [→ /href/]`.
An item with keywords passes when one keyword appears; without keywords the text must
appear verbatim (use this for names, prices, awards, labels). A CTA carries `→ /page/` or
`→ #section`.]

### Home
- (required) Message: [the one-sentence positioning] — keywords: [3–5 words from it]
- (required) CTA: [label] → /[page]/
- (required) Proof: [award, rating, press — exact wording]
- (required) Contact: phone, address, opening hours (from ## Contact)
- Story: [what the story block should say]
- Gallery: [how many photos, of what]

## Header
[Navigation style, logo placement, CTA button, language switcher, mobile menu.
If omitted, the template's default header is refined, not replaced.]

## Footer
[Columns, links, contact, social icons, copyright.
If omitted, the template's default footer is refined, not replaced.]

## Design Constraints

[Only what every design concept must respect. Never a design: no palette roles, no font
pair, no layout signature — those are chosen per concept by `/build-site`.]

- **Brand colors**: [hex values only if non-negotiable — an existing logo or identity — or "none"]
- **Logo / brand assets**: [path or URL, or "none"]
- **Direction**: [the operator's steer in one or two sentences — register (e.g. "solid and trustworthy", "premium/architectural", "direct and urgent", "warm and local"), light or dark, photography-led or type-led. Concepts diverge within this; leave empty to let them roam]
- **Avoid**: [what the local competition does that this site will not; anything the client rejected — separated by `;`]
- **References**: [up to three URLs, context for the art director, never models to copy]
- **Image constraints**: [largest usable width per group, e.g. "dishes 680px, space 2560px" — decides whether full-bleed photography is possible]

## Images

- **Strategy**: reuse existing | unsplash | ai | mix | skip
- **Sources**: [where existing photos come from: old site, Facebook, PicklyMenu API,
  client folder. See `briefings/<slug>-audit.md` for the inventory.]
- **Constraints**: [largest usable width per group, e.g. "dishes 680px, space 2560px
  (2013)". Decides whether full-bleed photography is allowed.]

## Domain

[GCS folder identifier, lowercase with hyphens, e.g. `o-marisco`. Already set by
`new_site.sh` to the project slug; do not change once media has been uploaded.]

## Additional Notes

[SEO focus keywords, JSON-LD type, legal requirements, seasonal content,
anything out of scope.]

## To Confirm With Client

[Facts the build assumed and the client must confirm before launch.]

- 
