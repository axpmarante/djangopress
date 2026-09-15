# Editor v2 — Image Discovery & Edit Affordance

**Date:** 2026-05-07
**Status:** Draft (problem + solutions for future implementation)
**Origin:** Real frustration encountered while editing the Cuíca site (`cuica` child project, page id=3).

## Problem

The editor v2 is a "click-and-edit" surface: the user clicks an element on the rendered page and the editor opens the swap UI for that element. For images this works only when the click hits a bare, foreground `<img>`. In real-world layouts that pattern is rare — modern designs use overlays, gradients, content-on-top-of-image cards, and JS-driven carousels/marquees. In all those cases the click never reaches the `<img>`, so the user gets no feedback and has to navigate the Structure tree manually, expanding section after section to find the right `<img>`. The author of the page (Claude) knows there's an image there; the editor user has to hunt for it.

Three concrete failure modes observed on Cuíca's home page:

### 1. Image as background (cards with content overlay)

`dois-mundos` section — two large cards, each one an `<a>` with an absolute-positioned image and content layered on top:

```html
<a class="group relative block overflow-hidden h-[80vh]">
  <img class="absolute inset-0 w-full h-full object-cover">      <!-- behind everything -->
  <div class="absolute inset-0 bg-gradient-to-t ..."></div>      <!-- decorative gradient -->
  <div class="relative z-10 ...content with text + CTA..."></div> <!-- on top -->
</a>
```

Click anywhere visible → hits the gradient div or the content div. The `<img>` is never the click target. Adding `pointer-events-none` to the gradient does not help — the content wrapper still covers 100% of the card. **HTML alone cannot fix this** while preserving the visual design.

### 2. Splide-injected clones

`hero` section — Splide carousel with autoplay. Splide injects `splide__slide--clone` elements before/after the originals to produce the seamless infinite transition. The visible slide at any given moment may be a clone, not an original.

- If the editor binds handlers to original `<img>` only: clicking a clone does nothing.
- If the editor binds handlers to all `<img>`: clicking a clone "edits" something that gets re-cloned on the next render — the change appears lost.
- The editor v2 already filters Splide clones for `nth-child` calculation (per `djangopress-html-reference.md`), but the click → image resolution still fails in practice.

### 3. Marquee duplicates

`terrace-lounge` section — three rows of horizontal scrolling images. Each row contains its image set duplicated in HTML so that `transform: translateX(-50%)` appears continuous. The duplicate `<img>` tags carry `aria-hidden="true"` and empty `alt=""` to mark them as decorative, but the editor v2 does not filter on `aria-hidden`. Result: the user can edit the duplicate by mistake, the original stays unchanged, and the "same" image appears twice on the page in an inconsistent state.

Counts on the live Cuíca page (PT, page id=3):

| Section | `<img>` total | Editable cleanly | Pattern |
|---|---|---|---|
| `hero` | 2 | unreliable | Splide carousel |
| `dois-mundos` | 2 | impossible | image-as-background cards |
| `cuica-praia` | 1 | likely OK | image with caption box overlay |
| `sabores` | 4 | clean | grid of cards |
| `terrace-lounge` | 50 | 26 unique + 24 `aria-hidden` duplicates | 3-row marquee |

The editor v2 today exposes all 50 in `terrace-lounge` and offers no signal that 24 of them are clones of the others.

## Why HTML conventions alone don't solve this

The skill `djangopress-html-reference.md` already documents the relevant rules: `pointer-events-none` on decorative overlays, Splide nth-child filtering, lightbox patterns. These are necessary but not sufficient. The deeper issue is that the editor's UX assumes *the user can find the element by clicking* — when the page layout makes that impossible, no convention applied to HTML can rescue the interaction. The editor must do work itself.

## Possible Solutions

Two complementary surfaces. The first is high-impact and low-effort; the second is more polish-heavy but addresses the click-target problem head-on.

### Solution A — Images sidebar tab (recommended first step)

Add a new tab to the editor v2 sidebar (alongside Structure) listing every editable image on the page, grouped by section, with thumbnails. Clicking a thumbnail opens the existing image-picker swap UI for that `<img>`.

```
┌─ Sidebar ────────────────────────┐
│ Structure │ Images │ AI │ ...    │
├──────────────────────────────────┤
│ ▾ hero (2)                       │
│   [thumb] hero-praia-dia.jpg     │
│   [thumb] hero-terrace-sunset.jpg│
│ ▾ dois-mundos (2)                │
│   [thumb] card-praia.jpg         │
│   [thumb] card-terrace.jpg       │
│ ▾ cuica-praia (1)                │
│   [thumb] hamburguer-assinatura  │
│ ▾ sabores (4)                    │
│   …                              │
│ ▾ terrace-lounge (26 unique)     │
│   …                              │
└──────────────────────────────────┘
```

**Discovery filter** when building the list:

1. Start with `document.querySelectorAll('section[data-section] img')`.
2. Drop any `<img>` matching `[aria-hidden="true"]`. Document this convention in `djangopress-html-reference.md` as the standard way to mark decorative or clone duplicates.
3. Drop any `<img>` whose closest ancestor matches `.splide__slide--clone`.
4. Optionally drop by `[data-editor-skip="true"]` for explicit author opt-out.
5. Dedup by `src`: if the same URL appears multiple times in a section, keep the first occurrence and stash the rest as "siblings" (reflected as `× N` on the thumbnail).

**Section grouping:** walk up from each `<img>` to its closest `[data-section]` ancestor; group entries by that section name; within each group, keep DOM order.

**Thumbnail rendering:** reuse the `<img src>` directly with `width="64" height="64"` — browsers will reuse the cached image. Fall back to a placeholder icon if `src` 404s.

**Click behavior:** `scroll-margin-top` to push the target below the editor toolbar (5rem matches the existing scroll-padding-top), highlight the `<img>` briefly, then call the existing image-picker open handler with the `<img>` element as target.

**No HTML migration required.** Existing pages benefit immediately without any author intervention.

### Solution B — In-page edit badges (overlay buttons)

In edit mode, the editor scans the DOM (using the same discovery filter as Solution A) and injects a small overlay button on top of each editable `<img>`:

```
┌──────────────────────┐
│      <img src=…>     │
│  ┌──────────────┐    │
│  │ ✎ Trocar img │    │ ← injected by editor, position:absolute,
│  └──────────────┘    │   z-index higher than any content/overlay
└──────────────────────┘
```

The badge:

- Sits at fixed top-left or center of the image's bounding rect, repositioned on scroll/resize via `IntersectionObserver` + `ResizeObserver`.
- Uses `z-index: 2147483646` (just below the editor's own UI z-index) so it always wins over overlays and content layers.
- Click opens the same image-picker swap UI as Solution A.
- For Splide carousels and marquees, render a single badge per *unique* image (whichever clone/duplicate is currently most visible in the viewport), labeled `Trocar imagem (× N visible)`.

This solves the "image as background" case directly: the user no longer has to click on the `<img>` — the badge is always reachable.

**Tradeoffs vs. Solution A:**

- (+) Restores click-and-edit on the page itself (Solution A only adds a sidebar shortcut).
- (-) More positioning code, more edge cases (badge clipping in `overflow:hidden` containers, repositioning during Splide animation, performance with 50+ badges on Cuíca's marquee).
- (-) Must hide gracefully when not in edit mode.

### Solution C — Slide/marquee manager (only if A and B aren't enough)

For Splide and marquee containers, replace per-image badges with a single container-level badge: `Gerir N imagens deste slider`. Click opens a modal with the canonical list of images (add/remove/reorder/edit each). The modal writes to a single source-of-truth (e.g., `data-slides='[…]'` on the container) and a JS helper renders the visual elements at runtime.

Larger scope — requires:

- A new HTML pattern for "data-driven" slides documented in `djangopress-html-reference.md`.
- Migration path for existing sites with hard-coded `<li class="splide__slide">` slides.
- Engine-side renderer for the data-driven pattern.

Defer until A and B prove insufficient.

## Recommended sequence

1. **Solution A** first — biggest discovery win for least code. Self-contained as a new sidebar module.
2. **Solution B** next — fixes the click-and-edit experience on the page itself.
3. Document the `aria-hidden="true"` and (optional) `[data-editor-skip="true"]` conventions in `djangopress-html-reference.md` so authors can opt elements out explicitly.
4. **Solution C** only if Splide/marquee management remains painful after A + B.

## Implementation pointers (for the future plan doc)

The editor v2 lives at `src/djangopress/editor_v2/`:

| Concern | File |
|---|---|
| Click → element resolution (current behavior) | `static/editor_v2/js/modules/selection.js` |
| Image picker / swap UI | `static/editor_v2/js/modules/image-picker.js` |
| Sidebar tabs (Structure today) | `static/editor_v2/js/modules/sidebar.js` |
| Editor entrypoint | `static/editor_v2/js/editor.js` |
| Editor styles | `static/editor_v2/css/editor.css` |
| Toolbar / template | `templates/editor_v2/partials/editor.html` |

For Solution A, the new module would live at `static/editor_v2/js/modules/images-panel.js` and register itself as a sidebar tab. The image-picker module already accepts an `<img>` element as input — reuse that entry point.

For Solution B, badge injection probably belongs in a new `static/editor_v2/js/modules/image-badges.js` toggled on by the same flag that activates the editor.

## Acceptance criteria

A future session implementing Solution A is done when:

- Opening the editor v2 on Cuíca's home page shows the new "Images" sidebar tab.
- The tab lists 35 image entries grouped into 5 sections (hero: 2, dois-mundos: 2, cuica-praia: 1, sabores: 4, terrace-lounge: 26 unique). The 24 `aria-hidden` marquee duplicates are not listed.
- Splide clones are not listed as separate entries.
- Clicking any thumbnail opens the existing image-picker UI targeted at the right `<img>`, scrolls the page so the image is visible, and highlights it briefly.
- Pages with zero editable images render an empty state ("No editable images on this page").
- The existing click-on-image behavior continues to work where it works today (no regression).

For Solution B: clicking the `dois-mundos` first card opens the image-picker for `card-praia.jpg`; clicking the `terrace-lounge` marquee opens the image-picker for the unique image under the cursor (not a duplicate).
