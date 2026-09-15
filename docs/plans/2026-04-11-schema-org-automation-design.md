# Schema.org Automation — Design Doc

**Date:** 2026-04-11
**Status:** Proposal
**Scope:** DjangoPress core — JSON-LD auto-injection for all pages

---

## Context

LLMs and AI agents (ChatGPT, Claude, Gemini, Perplexity) are becoming a major discovery channel for B2B SaaS. Their ability to cite and recommend content depends heavily on **structured data** — specifically Schema.org JSON-LD. Sites without rich markup are either skipped or summarized poorly.

DjangoPress currently has **zero Schema.org output**. Every child site loses visibility in AI answers, rich snippets, and knowledge graph results. We already ship `robots.txt` (recently enhanced with AI bot allowlist) and `llms.txt` (auto-generated from SiteSettings + active Pages). Schema.org is the missing third leg.

## Goals

1. **Zero-config baseline** — every DjangoPress page automatically ships with correct `Organization`, `WebSite`, `WebPage`, and `BreadcrumbList` schemas, without any site owner intervention.
2. **Specialization via simple config** — pages that are products, services, articles, or software apps can declare their type via a dropdown + JSON field, and get the right schema generated.
3. **Content auto-detection** — FAQ sections and HowTo steps already present in page HTML are detected and converted into `FAQPage` / `HowTo` schemas automatically. No duplication.
4. **Override escape hatch** — power users can still write raw `<script type="application/ld+json">` in their page HTML, and the system respects / merges it.
5. **Testable** — dev tooling to preview and validate the schemas generated for any page.

## Non-goals

- Generating schemas for content types DjangoPress doesn't manage (Event, Recipe, Course). Future work.
- Syncing with external databases (Google Merchant Center, etc.). Out of scope.
- Localized schemas for every language on every page — start with default language, expand later.
- AMP or MicroData formats. JSON-LD only (modern standard).

---

## Design overview

Four layers, applied in order at render time, each merging into a single `@graph`:

```
┌────────────────────────────────────────────────────────┐
│ Layer A: Base (automatic, zero-config)                 │
│  - Organization (from SiteSettings)                    │
│  - WebSite (with SearchAction)                         │
│  - WebPage (from Page metadata)                        │
│  - BreadcrumbList (from URL path)                      │
└────────────────────────────────────────────────────────┘
                         +
┌────────────────────────────────────────────────────────┐
│ Layer B: Specialization (Page.schema_type field)       │
│  - Product / SoftwareApplication / Service             │
│  - Article / NewsArticle / BlogPosting                 │
│  - LocalBusiness / Restaurant / Hotel                  │
│  Merged with Page.schema_data JSONField                │
└────────────────────────────────────────────────────────┘
                         +
┌────────────────────────────────────────────────────────┐
│ Layer C: Content auto-detection                        │
│  - FAQPage from <section data-section="faq">           │
│  - HowTo from numbered step divs                       │
│  - AggregateRating from testimonials markup            │
│  - VideoObject from <video> + <iframe> tags            │
└────────────────────────────────────────────────────────┘
                         +
┌────────────────────────────────────────────────────────┐
│ Layer D: Inline overrides                              │
│  <script type="application/ld+json"> in page HTML      │
│  parsed and merged (override by @type if conflict)     │
└────────────────────────────────────────────────────────┘
                         ↓
            Final @graph in <head>
```

## Model changes

### `Page` — two new fields

```python
class Page(models.Model):
    # ... existing fields ...

    SCHEMA_TYPE_CHOICES = [
        ('', 'WebPage (default)'),
        ('Product', 'Product'),
        ('SoftwareApplication', 'Software Application'),
        ('Service', 'Service'),
        ('Article', 'Article'),
        ('BlogPosting', 'Blog post'),
        ('NewsArticle', 'News article'),
        ('LocalBusiness', 'Local business'),
        ('Restaurant', 'Restaurant'),
        ('Event', 'Event'),
    ]

    schema_type = models.CharField(
        'Schema.org type',
        max_length=50,
        choices=SCHEMA_TYPE_CHOICES,
        blank=True,
        default='',
        help_text='Specialized schema.org type for this page. Leave empty for default WebPage.',
    )

    schema_data = models.JSONField(
        'Schema.org data',
        default=dict,
        blank=True,
        help_text=(
            'Additional schema fields merged with defaults. Common keys: '
            'price, priceCurrency, brand, category, rating, ratingCount, '
            'features, image, sku, availability.'
        ),
    )
```

Migration: `0xxx_add_page_schema_fields.py` — nullable, blank, safe.

### `SiteSettings` — no changes

Schema.org `Organization` block is generated from existing fields:
- `site_name_i18n` → `name`
- `site_description_i18n` → `description`
- `logo` → `logo`
- `contact_email` / `contact_phone` → `email` / `telephone`
- `facebook_url`, `instagram_url`, etc. → `sameAs`
- `contact_address_i18n` → `address.PostalAddress`

No migration needed.

---

## Implementation

### New module: `djangopress/core/schema_org.py`

```python
"""
Schema.org JSON-LD generation for DjangoPress pages.

Exposes a single public function `build_schema_graph(page, request)` that
returns a complete @graph dict ready to be serialized into a <script> tag.
"""

from typing import Optional
from django.http import HttpRequest
from djangopress.core.models import Page, SiteSettings


def build_schema_graph(page: Optional[Page], request: HttpRequest) -> dict:
    """
    Generate a complete Schema.org @graph for a page.

    Combines 4 layers:
    1. Base schemas (Organization, WebSite, WebPage, BreadcrumbList)
    2. Page.schema_type specialization
    3. Auto-detected content schemas (FAQPage, HowTo, AggregateRating)
    4. Inline <script> overrides in page HTML

    Returns a dict ready for json.dumps() with indent=2.
    """
    graph = []

    # Layer A: base schemas
    settings_obj = SiteSettings.load()
    graph.append(_build_organization(settings_obj, request))
    graph.append(_build_website(settings_obj, request))
    if page:
        graph.append(_build_webpage(page, request))
        graph.append(_build_breadcrumbs(page, request))

    # Layer B: page-type specialization
    if page and page.schema_type:
        specialized = _build_specialized(page, settings_obj, request)
        if specialized:
            graph.append(specialized)

    # Layer C: content auto-detection
    if page:
        graph.extend(_detect_content_schemas(page, request))

    # Layer D: inline overrides
    if page:
        inline = _extract_inline_schemas(page)
        graph = _merge_inline(graph, inline)

    return {'@context': 'https://schema.org', '@graph': graph}


def _build_organization(settings, request): ...
def _build_website(settings, request): ...
def _build_webpage(page, request): ...
def _build_breadcrumbs(page, request): ...
def _build_specialized(page, settings, request): ...
def _detect_content_schemas(page, request): ...
def _extract_inline_schemas(page): ...
def _merge_inline(graph, inline): ...
```

### Template integration

In `djangopress/templates/base.html`:

```django
{% load schema_tags %}
<head>
    ...
    {% schema_jsonld %}
    ...
</head>
```

New template tag `djangopress/core/templatetags/schema_tags.py`:

```python
from django import template
from django.utils.safestring import mark_safe
import json

from djangopress.core.schema_org import build_schema_graph

register = template.Library()

@register.simple_tag(takes_context=True)
def schema_jsonld(context):
    request = context.get('request')
    page = context.get('page_obj')
    graph = build_schema_graph(page, request)
    html = '<script type="application/ld+json">\n'
    html += json.dumps(graph, ensure_ascii=False, indent=2)
    html += '\n</script>'
    return mark_safe(html)
```

### Content auto-detection strategies

**FAQPage:** Parse page HTML with BeautifulSoup, find `<section data-section="faq">`. Inside, find chat-bubble cards with `data-q` and `data-a` attributes. Each becomes a `Question` / `Answer` pair.

**HowTo:** Find `<section data-section="how-it-works">` or sections with class containing `steps`. Look for numbered children (1, 2, 3...) with title + description. Convert to `HowToStep` array.

**AggregateRating:** Find `<section data-section="testimonials">`. Look for star rating patterns (`★★★★★` or `text-orange-500` w/ count). Count testimonials and calculate average.

**VideoObject:** Find `<video>` tags or YouTube `<iframe>` sources. Extract `src`, `title`, `duration` when available.

All detection is best-effort — if the HTML doesn't match patterns, the schema is skipped, no errors.

---

## Backoffice UI

New section in the Page edit view: **"Schema.org"**

```
┌──────────────────────────────────────────┐
│ Schema.org                               │
├──────────────────────────────────────────┤
│ Type: [SoftwareApplication ▼]            │
│                                          │
│ Additional data:                         │
│ ┌──────────────────────────────────┐    │
│ │ {                                │    │
│ │   "price": "49",                 │    │
│ │   "priceCurrency": "EUR",        │    │
│ │   "ratingValue": "4.9",          │    │
│ │   "ratingCount": "150",          │    │
│ │   "category": "Menu Management"  │    │
│ │ }                                │    │
│ └──────────────────────────────────┘    │
│                                          │
│ [Preview generated schema]               │
└──────────────────────────────────────────┘
```

Clicking "Preview" runs `build_schema_graph(page, request)` and shows the final JSON-LD — giving instant feedback without publishing.

---

## Dev tooling

### 1. Management command

```bash
python manage.py schema_preview <page_id> [--lang pt]
```

Prints the final JSON-LD for a page. Useful for debugging and CI.

### 2. Validation endpoint

`/backoffice/schema-validator/<page_id>/` — live preview with syntax check and Google rich result eligibility hints.

### 3. Test coverage

- Unit tests for each layer builder (`_build_organization`, etc.)
- Integration test: full `build_schema_graph` for a page with all 4 layers
- Snapshot tests comparing generated JSON against fixtures
- Google Rich Results Test via the public API (CI-optional)

---

## Migration strategy

### Phase 1: Backward-compatible add (week 1)
- Add `schema_type` + `schema_data` fields to Page (nullable)
- Add `build_schema_graph` module
- Add `schema_jsonld` template tag
- Add to `base.html` (outputs WebPage + Organization for every existing page automatically)

**No action required from site owners.** Every existing site ships with base schemas after upgrade.

### Phase 2: Opt-in specialization (week 2)
- Backoffice UI for schema fields
- Management command
- Inline override parser

Site owners can now start tagging pages with types. Old pages continue to work.

### Phase 3: Content auto-detection (week 3)
- Add FAQPage / HowTo / AggregateRating / VideoObject detectors
- Turn on per section marker (`data-section`) — no legacy HTML affected
- Document the markers in `djangopress-html-reference` skill

### Phase 4: Docs + examples (week 4)
- Update skills: `edit-site`, `generate-site`, `djangopress-html-reference`
- Add migration guide for existing sites
- Add example schemas in `docs/examples/schema/`

---

## Example: PicklyMenu page with full stack

With all 4 layers active, the `<head>` of `/pt/picklymenu/` outputs:

```json
{
  "@context": "https://schema.org",
  "@graph": [
    { "@type": "Organization", "name": "DinnerSoft", ... },
    { "@type": "WebSite", "url": "https://dinnersoft.pt", ... },
    { "@type": "WebPage", "name": "PicklyMenu — Menu Digital", ... },
    { "@type": "BreadcrumbList", ... },
    {
      "@type": "SoftwareApplication",
      "name": "PicklyMenu",
      "offers": { "price": "49", "priceCurrency": "EUR" },
      "aggregateRating": { "ratingValue": "4.9", "ratingCount": "150" }
    },
    {
      "@type": "FAQPage",
      "mainEntity": [/* auto-extracted from data-q/data-a cards */]
    },
    {
      "@type": "HowTo",
      "step": [/* auto-extracted from how-it-works numbered steps */]
    }
  ]
}
```

Site owner did **one thing**: picked "SoftwareApplication" from a dropdown and pasted `{"price":"49","ratingValue":"4.9","ratingCount":"150"}`. Everything else is automatic.

---

## Impact

| Change | Sites affected | Configuration | Value |
|---|---|---|---|
| Layer A (base) | 100% | Zero | Foundation — every page has Organization/WebPage |
| Layer B (type) | 30-50% (product pages) | 1 dropdown + 3-5 JSON keys | Rich snippets, AI recommendations |
| Layer C (auto) | 20-30% (sites with FAQs/how-tos) | Zero if HTML follows conventions | FAQ rich results in Google |
| Layer D (inline) | <5% (power users) | Raw JSON-LD | Full control |

**Estimated GEO impact** (based on early adopter SaaS data):
- +30-50% in LLM citations for specialized pages
- +15-25% in Google rich result clicks
- Immediate eligibility for Google's Knowledge Graph for Organization

---

## Open questions

1. **Multi-language schemas:** should we output separate schemas per language, or one combined with `inLanguage`? Recommendation: one per language, matched to `LANGUAGE_CODE` at render time.

2. **Caching:** schema generation runs on every request. Should we cache in Redis / locmem per (page_id, lang)? Recommendation: yes, with invalidation on Page save (similar to `slug_index`).

3. **Schema.org vocabulary evolution:** Schema.org publishes changes monthly. Should we version our vocabulary? Recommendation: follow latest stable, annual review.

4. **Inline `<script>` handling:** if a site has inline schema and page-type is also set, which wins? Recommendation: inline override wins per `@type` (replaces), non-conflicting types are merged.

5. **Backoffice JSON editor:** plain textarea vs. structured form fields? Recommendation: textarea with live validation first, structured form in future release.

---

## Decision points

1. ✅ Approve Layer A (base) as automatic — low risk, high value
2. ⚠️ Layer B fields on Page model — requires migration, low risk
3. ⚠️ Layer C auto-detection — requires HTML conventions (already using `data-section`)
4. ✅ Layer D inline override — safe, optional

**Recommended rollout:** ship Layer A immediately as part of the `robots.txt`/`llms.txt` enhancement. Layers B/C/D as a follow-up release with proper migration + docs.

---

## Appendix: llms.txt + robots.txt (already shipped)

The following are **already in main** as of this writing (same commit as this proposal):

- **`/robots.txt`** — explicit allowlist for 17 AI crawlers (GPTBot, ClaudeBot, PerplexityBot, Google-Extended, etc.) + references to sitemap + llms.txt
- **`/llms.txt`** — auto-generated markdown index from SiteSettings + active Pages, filters A/B variants, respects default language

These three together (`robots.txt` + `llms.txt` + Schema.org) form the complete **GEO stack** for DjangoPress sites.
