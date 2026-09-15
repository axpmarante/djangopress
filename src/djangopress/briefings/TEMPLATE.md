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

[One entry per page. Describe the sections in order, with the content each holds
and the CTA. "The home page" is not a description.]

- **Home**: 1. Hero — [message, CTAs]. 2. [Section] — [content]. 3. ...
- **About**: ...
- **Contact**: form (reuse the template's `contact` DynamicForm), map, hours.

## Header
[Navigation style, logo placement, CTA button, language switcher, mobile menu.
If omitted, the template's default header is refined, not replaced.]

## Footer
[Columns, links, contact, social icons, copyright.
If omitted, the template's default footer is refined, not replaced.]

## Design Preferences

Required. This section is what keeps the site from looking like a template.

- **Palette** (hex, with roles):
  - Background:
  - Surface (cards, blocks):
  - Text:
  - Accent (CTAs, prices, highlights):
  - Secondary (links, supporting):
  - Dark block (one inverted section):
- **Type pair** (Google Fonts): headings — [font]; body — [font]
- **Corner radius**: [e.g. 4px, 12px, pill]
- **Layout signature**: [one sentence: the recurring compositional idea, e.g.
  "12-column grid with text in 5 columns and image in 6, vertically offset"]
- **Motif**: [one decorative device used consistently, or "none"]
- **Avoid**: [what the local competition does that this site will not]
- **References**: [up to three URLs]

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
