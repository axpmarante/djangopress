"""
Component skill: Splide.js Slider (single-item).

Full-width single-item presentations: hero image banners, fullscreen photo
slideshows, single-testimonial rotators. Uses Splide.js with perPage:1.
Splide is pre-loaded in base.html (CSS + JS) and auto-mounts — no inline <script> needed.
"""

NAME = "slider"

DESCRIPTION = "Full-width image slider / slideshow for hero banners and photo presentations."

INDEX_ENTRY = (
    "Full-width image slider / slideshow (Splide.js). Use for hero image banners, "
    "fullscreen photo slideshows, before/after showcases — any single-image-at-a-time "
    "presentation. `perPage:1` with `type:\"fade\"` or `type:\"loop\"`. "
    "NOT for multi-item scrolling (use carousel instead)."
)

FULL_REFERENCE = """\
### Slider (Splide.js — Single Item)

Splide.js is pre-loaded in `base.html`. Every element with class `splide` is
automatically initialized on page load — do NOT add inline `<script>` tags.

Use the **slider** component for any presentation that shows one item at a time:
hero image banners, fullscreen photo slideshows, single-testimonial rotators,
before/after showcases.

For multi-item scrolling (multiple visible items), use the **carousel** component instead.

#### Basic Structure

```html
<div class="splide" data-media-collection="slider" data-splide='{"type":"fade","rewind":true,"autoplay":true,"interval":5000,"speed":1000,"arrows":true,"pagination":true}'>
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
| `splide` | Outer wrapper `<div>` | Identifies the slider for auto-init |
| `splide__track` | Inner wrapper `<div>` | Viewport / clipping container |
| `splide__list` | `<ul>` | Flex container that holds slides |
| `splide__slide` | `<li>` | Individual slide |

#### Attributes

| Attribute | Value | Purpose |
|-----------|-------|---------|
| `data-splide` | JSON string | All Splide configuration options (see table below) |
| `data-media-collection` | `"slider"` | **Required.** Identifies this as a slider media collection for the editor. Always use `"slider"`, not `"carousel"`. |

#### Configuration via `data-splide`

All options go in the `data-splide` JSON attribute on the `.splide` element.
The JSON must be valid (use double quotes for keys and string values).

**Core Options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `type` | string | `"slide"` | `"fade"` (crossfade — best for hero banners), `"loop"` (infinite loop), `"slide"` (stop at edges) |
| `rewind` | boolean | `false` | Rewind to first slide after last (use with `type:"fade"` or `type:"slide"`) |
| `autoplay` | boolean | `false` | Auto-advance slides |
| `interval` | number | `5000` | Autoplay interval in ms |
| `pauseOnHover` | boolean | `true` | Pause autoplay when user hovers |
| `pauseOnFocus` | boolean | `true` | Pause autoplay when a slide is focused |
| `speed` | number | `400` | Transition speed in ms (use 800-1000 for smooth fade effects) |
| `arrows` | boolean | `true` | Show prev/next arrow buttons |
| `pagination` | boolean | `true` | Show dot pagination |
| `drag` | boolean | `true` | Enable touch/mouse drag |
| `start` | number | `0` | Zero-based index of the initial slide |

**Note:** `perPage` is always `1` for sliders — do not set it higher.

#### Common Layouts

**Hero Image Slider (full-width, fade transition, autoplay, overlay text):**
```html
<section data-section="hero-slider" id="hero-slider" class="relative">
  <div class="splide" data-media-collection="slider" data-splide='{"type":"fade","rewind":true,"autoplay":true,"interval":5000,"speed":1000,"arrows":true,"pagination":true}'>
    <div class="splide__track">
      <ul class="splide__list">
        <li class="splide__slide">
          <div class="relative h-[600px] md:h-[80vh]">
            <img src="..." alt="..." class="absolute inset-0 w-full h-full object-cover">
            <div class="absolute inset-0 bg-black/40 flex items-center justify-center">
              <div class="text-center text-white px-4">
                <h2 class="text-4xl md:text-6xl font-bold mb-4">Welcome to Our World</h2>
                <p class="text-xl md:text-2xl">Discover extraordinary experiences</p>
              </div>
            </div>
          </div>
        </li>
        <li class="splide__slide">
          <div class="relative h-[600px] md:h-[80vh]">
            <img src="..." alt="..." class="absolute inset-0 w-full h-full object-cover">
            <div class="absolute inset-0 bg-black/40 flex items-center justify-center">
              <div class="text-center text-white px-4">
                <h2 class="text-4xl md:text-6xl font-bold mb-4">Quality & Excellence</h2>
                <p class="text-xl md:text-2xl">Crafted with passion and dedication</p>
              </div>
            </div>
          </div>
        </li>
      </ul>
    </div>
  </div>
</section>
```

**Fullscreen Photo Slideshow (minimal UI, large images, loop):**
```html
<section data-section="slideshow" id="slideshow" class="py-16 bg-black">
  <div class="max-w-6xl mx-auto px-4">
    <div class="splide" data-media-collection="slider" data-splide='{"type":"loop","perPage":1,"autoplay":true,"interval":4000,"speed":800,"arrows":true,"pagination":false}'>
      <div class="splide__track">
        <ul class="splide__list">
          <li class="splide__slide">
            <img src="..." alt="..." class="w-full h-[500px] md:h-[70vh] object-cover rounded-lg">
          </li>
          <li class="splide__slide">
            <img src="..." alt="..." class="w-full h-[500px] md:h-[70vh] object-cover rounded-lg">
          </li>
          <li class="splide__slide">
            <img src="..." alt="..." class="w-full h-[500px] md:h-[70vh] object-cover rounded-lg">
          </li>
        </ul>
      </div>
    </div>
  </div>
</section>
```

**Testimonial Slider (single testimonial at a time, autoplay, no arrows):**
```html
<section data-section="testimonials" id="testimonials" class="py-16 bg-gray-50">
  <div class="max-w-4xl mx-auto px-4">
    <h2 class="text-3xl font-bold text-center mb-10">What Our Clients Say</h2>
    <div class="splide" data-media-collection="slider" data-splide='{"type":"loop","perPage":1,"autoplay":true,"interval":6000,"pauseOnHover":true,"arrows":false,"pagination":true}'>
      <div class="splide__track">
        <ul class="splide__list">
          <li class="splide__slide">
            <div class="text-center max-w-2xl mx-auto px-8 py-6">
              <p class="text-lg italic mb-4">"An exceptional experience from start to finish. The team exceeded all our expectations."</p>
              <p class="font-semibold">Maria Santos</p>
            </div>
          </li>
          <li class="splide__slide">
            <div class="text-center max-w-2xl mx-auto px-8 py-6">
              <p class="text-lg italic mb-4">"Outstanding quality and attention to detail. Highly recommended!"</p>
              <p class="font-semibold">João Silva</p>
            </div>
          </li>
        </ul>
      </div>
    </div>
  </div>
</section>
```

#### Do's and Don'ts

**Do:**
- Use the exact class names: `splide`, `splide__track`, `splide__list`, `splide__slide`
- Put all options in the `data-splide` JSON attribute
- Always add `data-media-collection="slider"` on the `.splide` element
- Use `type:"fade"` for hero banners (smooth crossfade between full-width images)
- Use `type:"loop"` for continuous slideshows (wraps around seamlessly)
- Set `speed` to 800-1000 for smooth fade transitions (default 400 is too fast for hero slides)
- Set appropriate `interval` for autoplay (5000-6000ms for text-heavy slides, 3000-4000ms for image-only)
- Wrap content in `<li class="splide__slide">` — not `<div>`
- Use overlay `<div>` with `bg-black/40` or similar for text readability on hero images

**Don't:**
- Do NOT add inline `<script>` tags to initialize Splide — it auto-mounts
- Do NOT set `perPage` > 1 — that makes it a carousel, use the carousel component instead
- Do NOT use `<div>` for slides — they must be `<li>` inside a `<ul>`
- Do NOT put `data-splide` on anything other than the `.splide` element
- Do NOT forget the `.splide__track` wrapper — without it, Splide breaks
- Do NOT use CSS `overflow-hidden` on the `.splide` element (Splide handles this internally)
- Do NOT use `data-media-collection="carousel"` — use `"slider"` to correctly categorize the component
- Do NOT use `breakpoints` with `perPage` overrides — sliders are always 1 item per page

#### Common Mistakes

1. **Missing `.splide__track` wrapper** — Slides won't render. The structure must be `.splide > .splide__track > .splide__list > .splide__slide`.
2. **Invalid JSON in `data-splide`** — Use double quotes for all keys and string values. Single quotes cause a parse error.
3. **Using `<div>` instead of `<ul>/<li>`** — The list must be `<ul class="splide__list">` with `<li class="splide__slide">` children.
4. **Setting `perPage` > 1** — Sliders show one item at a time. If you need multiple visible items, use the **carousel** component.
5. **Adding Splide JS initialization scripts** — The auto-init in `base.html` handles this. Adding another `new Splide()` call causes double-initialization bugs.
6. **Using `type:"fade"` without `rewind:true`** — Fade transitions need `rewind:true` to cycle back to the first slide. Without it, the slider stops at the last slide.
7. **Forgetting text overlay styling on hero sliders** — Hero images need a dark overlay (`bg-black/40`) and white text to ensure readability across different images.
"""
