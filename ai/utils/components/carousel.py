"""
Component skill: Splide.js Carousel (multi-item).

Multi-item scrolling carousels: image gallery grids, logo strips, team member
cards, product cards. Uses Splide.js with perPage > 1.
Splide is pre-loaded in base.html (CSS + JS) and auto-mounts — no inline <script> needed.
"""

NAME = "carousel"

DESCRIPTION = "Multi-item Splide.js carousel for image galleries, logo strips, team cards, etc."

INDEX_ENTRY = (
    "Multi-item carousel (Splide.js). Use for scrolling through multiple visible items: "
    "image gallery grids, logo strips, team member cards, product cards. "
    "`.splide` container with `data-splide` JSON config, "
    "`.splide__track > .splide__list > .splide__slide` structure. "
    "NOT for single-image slideshows or hero banners (use slider instead)."
)

FULL_REFERENCE = """\
### Carousel (Splide.js — Multi-Item)

Splide.js is pre-loaded in `base.html`. Every element with class `splide` is
automatically initialized on page load — do NOT add inline `<script>` tags.

Use the **carousel** component for multi-item scrolling where several items are
visible at once: image gallery grids, logo strips, team member cards, product cards.

For single-item presentations (hero sliders, photo slideshows, testimonial rotators),
use the **slider** component instead.

#### Basic Structure

```html
<div class="splide" data-media-collection="carousel" data-splide='{"type":"loop","perPage":3,"gap":"1.5rem","breakpoints":{"768":{"perPage":1},"1024":{"perPage":2}}}'>
  <div class="splide__track">
    <ul class="splide__list">
      <li class="splide__slide"><!-- slide content --></li>
      <li class="splide__slide"><!-- slide content --></li>
      <li class="splide__slide"><!-- slide content --></li>
    </ul>
  </div>
</div>
```

#### Required Class Names

These class names are mandatory — Splide will not work without them:

| Class | Element | Purpose |
|-------|---------|---------|
| `splide` | Outer wrapper `<div>` | Identifies the carousel for auto-init |
| `splide__track` | Inner wrapper `<div>` | Viewport / clipping container |
| `splide__list` | `<ul>` | Flex container that holds slides |
| `splide__slide` | `<li>` | Individual slide |
| `data-media-collection` | Outer wrapper `<div>` | Identifies the carousel as a media collection for the editor |

#### Configuration via `data-splide`

All options go in the `data-splide` JSON attribute on the `.splide` element.
The JSON must be valid (use double quotes for keys and string values).

**Core Options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `type` | string | `"slide"` | `"slide"` (stop at edges), `"loop"` (infinite loop), `"fade"` (crossfade, only with perPage:1) |
| `perPage` | number | `1` | Number of slides visible at once |
| `perMove` | number | `1` | Number of slides to advance per click/swipe |
| `gap` | string | `"0px"` | Gap between slides, e.g. `"1rem"`, `"20px"` |
| `autoplay` | boolean | `false` | Auto-advance slides |
| `interval` | number | `5000` | Autoplay interval in ms |
| `pauseOnHover` | boolean | `true` | Pause autoplay when user hovers |
| `pauseOnFocus` | boolean | `true` | Pause autoplay when a slide is focused |
| `speed` | number | `400` | Transition speed in ms |
| `arrows` | boolean | `true` | Show prev/next arrow buttons |
| `pagination` | boolean | `true` | Show dot pagination |
| `drag` | boolean | `true` | Enable touch/mouse drag |
| `rewind` | boolean | `false` | Rewind to start when reaching the end (for `type:"slide"`) |
| `start` | number | `0` | Zero-based index of the initial slide |
| `focus` | string/number | — | `"center"` to center the active slide, or a number for offset |
| `trimSpace` | boolean | `true` | Remove empty space at the edges when perPage > 1 |
| `padding` | string/object | — | Add padding to reveal adjacent slides, e.g. `"2rem"` or `{"left":"2rem","right":"2rem"}` |

**Responsive Breakpoints:**

Use `breakpoints` to override options at specific viewport widths (max-width):

```json
{
  "perPage": 4,
  "gap": "1.5rem",
  "breakpoints": {
    "1024": { "perPage": 3 },
    "768": { "perPage": 2 },
    "480": { "perPage": 1, "gap": "0.75rem" }
  }
}
```

Keys are pixel widths (as strings). Values override the parent options below that width.

#### Common Layouts

**Image Gallery Carousel (loop, 3 per page):**
```html
<section data-section="gallery" id="gallery" class="py-16 bg-gray-50">
  <div class="max-w-6xl mx-auto px-4">
    <h2 class="text-3xl font-bold text-center mb-10">{{ trans.gallery_title }}</h2>
    <div class="splide" data-media-collection="carousel" data-splide='{"type":"loop","perPage":3,"gap":"1.5rem","breakpoints":{"768":{"perPage":1},"1024":{"perPage":2}}}'>
      <div class="splide__track">
        <ul class="splide__list">
          <li class="splide__slide">
            <img src="..." alt="..." class="w-full h-64 object-cover rounded-lg">
          </li>
          <!-- more slides -->
        </ul>
      </div>
    </div>
  </div>
</section>
```

**Logo Strip (many per page, no arrows or pagination):**
```html
<div class="splide" data-media-collection="carousel" data-splide='{"type":"loop","perPage":6,"gap":"2rem","autoplay":true,"interval":3000,"arrows":false,"pagination":false,"breakpoints":{"768":{"perPage":3},"480":{"perPage":2}}}'>
  <div class="splide__track">
    <ul class="splide__list">
      <li class="splide__slide flex items-center justify-center">
        <img src="..." alt="Partner" class="h-12 object-contain grayscale hover:grayscale-0 transition">
      </li>
    </ul>
  </div>
</div>
```

#### Do's and Don'ts

**Do:**
- Use the exact class names: `splide`, `splide__track`, `splide__list`, `splide__slide`
- Put all options in the `data-splide` JSON attribute
- Use `breakpoints` for responsive behavior
- Use `type:"loop"` for most carousels (avoids dead ends)
- Set `perPage` > 1 and use `breakpoints` for responsive overrides
- Always add `data-media-collection="carousel"` on the `.splide` element
- Wrap content in `<li class="splide__slide">` — not `<div>`

**Don't:**
- Do NOT add inline `<script>` tags to initialize Splide — it auto-mounts
- Do NOT use `<div>` for slides — they must be `<li>` inside a `<ul>`
- Do NOT put `data-splide` on anything other than the `.splide` element
- Do NOT use `type:"fade"` — fade only works with `perPage:1`, which is a slider pattern. Use the slider component instead.
- Do NOT use `perPage:1` — single-item presentations belong in the slider component
- Do NOT forget the `.splide__track` wrapper — without it, Splide breaks
- Do NOT use CSS `overflow-hidden` on the `.splide` element (Splide handles this internally)

#### Common Mistakes

1. **Missing `.splide__track` wrapper** — Slides won't render. The structure must be `.splide > .splide__track > .splide__list > .splide__slide`.
2. **Invalid JSON in `data-splide`** — Use double quotes for all keys and string values. Single quotes cause a parse error.
3. **Using `<div>` instead of `<ul>/<li>`** — The list must be `<ul class="splide__list">` with `<li class="splide__slide">` children.
4. **Using `perPage:1` or `type:"fade"`** — Single-item presentations are sliders, not carousels. Use the **slider** component for hero banners, photo slideshows, and testimonial rotators.
5. **Adding Splide JS initialization scripts** — The auto-init in `base.html` handles this. Adding another `new Splide()` call causes double-initialization bugs.
"""
