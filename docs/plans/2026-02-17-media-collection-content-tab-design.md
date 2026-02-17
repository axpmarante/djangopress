# Media Collection Overview in Content Tab

## Problem

When a user selects a section or container that holds a gallery, carousel, or slider in the inline editor, the Content tab shows "Select a text element to edit content" — no way to see or manage the images. The only option is clicking each `<img>` individually (difficult inside carousels where Splide clones slides) or using AI refinement to change images.

## Solution

Add a `data-media-collection` attribute to media-heavy components via component prompts. The editor Content tab detects this attribute and renders a visual thumbnail overview with a button to open Process Images scoped to that section.

## Detection

Single approach: `data-media-collection="type"` attribute on the container element.

- `carousel.py` prompt: `data-media-collection="carousel"` on the `.splide` div
- `lightbox.py` prompt: `data-media-collection="lightbox"` on the grid wrapper div
- Existing pages pick up the attribute on next AI refinement/regeneration (no migration command)

## Content Tab Behavior

When the selected element (or a parent up to the section) has `[data-media-collection]`:

1. **Header** — shows collection type badge ("Carousel", "Lightbox")
2. **Thumbnail grid** — all `<img>` tags inside the collection container, in DOM order
3. **Clickable thumbnails** — clicking one selects that `<img>` element, triggering standard image editing fields (Change Image, alt text, URL)
4. **"Process Section Images" button** — emits `process-images:open` scoped to the parent section

When `data-media-collection` is NOT found, falls back to the current empty state.

## Files Changed

| File | Change |
|------|--------|
| `editor_v2/static/editor_v2/js/modules/sidebar.js` | Add `renderMediaCollection()` + detection in `renderContentTab()` else branch |
| `ai/utils/components/carousel.py` | Add `data-media-collection="carousel"` to all examples in `FULL_REFERENCE` |
| `ai/utils/components/lightbox.py` | Add `data-media-collection="lightbox"` to all examples in `FULL_REFERENCE` |

No new API endpoints, no new JS modules, no new templates.
