"""
Component skill: Image Lightbox / Gallery.

Custom lightbox (lightbox.js) is pre-loaded in base.html. It auto-discovers
elements with `data-lightbox` attributes and groups them into navigable galleries.
"""

NAME = "lightbox"

DESCRIPTION = "Image lightbox/gallery with keyboard navigation and grouping."

INDEX_ENTRY = (
    "Image lightbox. `data-lightbox=\"group-name\"` on `<a href=\"full.jpg\">` "
    "wrapping `<img>`. Same group name = navigable gallery. Caption via `data-alt`."
)

FULL_REFERENCE = """\
### Image Lightbox / Gallery

A custom lightbox (`lightbox.js`) is pre-loaded in `base.html`. It auto-discovers
all elements with `data-lightbox` attributes on page load.

#### How It Works

1. Add `data-lightbox="group-name"` to an `<a>` tag that wraps an `<img>`
2. The `<a>` tag's `href` is the full-size image URL shown in the lightbox
3. The `<img>` inside is the thumbnail shown on the page
4. All elements sharing the same `data-lightbox` group name become a single navigable gallery
5. Clicking any image opens the lightbox at that image's position in the group

#### Built-in Features

- **Keyboard navigation:** Left/Right arrows to navigate, Escape to close
- **Click navigation:** Prev/Next arrow buttons in the lightbox overlay
- **Overlay click to close:** Clicking the dark backdrop closes the lightbox
- **Image counter:** Shows "2 / 5" style position indicator
- **Caption:** Displayed below the image, sourced from `data-alt` attribute
- **Body scroll lock:** Page scrolling is disabled while lightbox is open

#### Basic Gallery

```html
<div class="grid grid-cols-2 md:grid-cols-3 gap-4">
  <a href="/media/photo-1-full.jpg" data-lightbox="gallery" data-alt="{{ trans.photo_1_caption }}">
    <img src="/media/photo-1-thumb.jpg" alt="{{ trans.photo_1_caption }}" class="w-full h-48 object-cover rounded-lg hover:opacity-90 transition cursor-pointer">
  </a>
  <a href="/media/photo-2-full.jpg" data-lightbox="gallery" data-alt="{{ trans.photo_2_caption }}">
    <img src="/media/photo-2-thumb.jpg" alt="{{ trans.photo_2_caption }}" class="w-full h-48 object-cover rounded-lg hover:opacity-90 transition cursor-pointer">
  </a>
  <a href="/media/photo-3-full.jpg" data-lightbox="gallery" data-alt="{{ trans.photo_3_caption }}">
    <img src="/media/photo-3-thumb.jpg" alt="{{ trans.photo_3_caption }}" class="w-full h-48 object-cover rounded-lg hover:opacity-90 transition cursor-pointer">
  </a>
</div>
```

#### Multiple Gallery Groups on the Same Page

Use different `data-lightbox` group names to create independent galleries.
Navigating within one gallery won't show images from another.

```html
<!-- Team photos gallery -->
<div class="grid grid-cols-3 gap-4">
  <a href="/media/team-1.jpg" data-lightbox="team" data-alt="Team Member 1">
    <img src="/media/team-1-thumb.jpg" alt="Team Member 1" class="w-full h-48 object-cover rounded-lg">
  </a>
  <a href="/media/team-2.jpg" data-lightbox="team" data-alt="Team Member 2">
    <img src="/media/team-2-thumb.jpg" alt="Team Member 2" class="w-full h-48 object-cover rounded-lg">
  </a>
</div>

<!-- Venue photos gallery (separate) -->
<div class="grid grid-cols-3 gap-4 mt-8">
  <a href="/media/venue-1.jpg" data-lightbox="venue" data-alt="Dining Room">
    <img src="/media/venue-1-thumb.jpg" alt="Dining Room" class="w-full h-48 object-cover rounded-lg">
  </a>
  <a href="/media/venue-2.jpg" data-lightbox="venue" data-alt="Garden Terrace">
    <img src="/media/venue-2-thumb.jpg" alt="Garden Terrace" class="w-full h-48 object-cover rounded-lg">
  </a>
</div>
```

#### Hidden Items Pattern

You can include lightbox items that are not visible on the page but still
navigable in the lightbox. This is useful for "show 4, but lightbox has 12":

```html
<div class="grid grid-cols-2 md:grid-cols-4 gap-4">
  <!-- Visible thumbnails -->
  <a href="/media/img-1.jpg" data-lightbox="portfolio" data-alt="Project 1">
    <img src="/media/img-1-thumb.jpg" alt="Project 1" class="w-full h-48 object-cover rounded-lg">
  </a>
  <a href="/media/img-2.jpg" data-lightbox="portfolio" data-alt="Project 2">
    <img src="/media/img-2-thumb.jpg" alt="Project 2" class="w-full h-48 object-cover rounded-lg">
  </a>
  <a href="/media/img-3.jpg" data-lightbox="portfolio" data-alt="Project 3">
    <img src="/media/img-3-thumb.jpg" alt="Project 3" class="w-full h-48 object-cover rounded-lg">
  </a>
  <a href="/media/img-4.jpg" data-lightbox="portfolio" data-alt="Project 4" class="relative">
    <img src="/media/img-4-thumb.jpg" alt="Project 4" class="w-full h-48 object-cover rounded-lg">
    <div class="absolute inset-0 bg-black/50 flex items-center justify-center rounded-lg">
      <span class="text-white text-xl font-bold">+8 more</span>
    </div>
  </a>
</div>
<!-- Hidden items still navigable in lightbox -->
<a href="/media/img-5.jpg" data-lightbox="portfolio" data-alt="Project 5" class="hidden"></a>
<a href="/media/img-6.jpg" data-lightbox="portfolio" data-alt="Project 6" class="hidden"></a>
<a href="/media/img-7.jpg" data-lightbox="portfolio" data-alt="Project 7" class="hidden"></a>
<!-- ... more hidden items ... -->
```

#### Combining with Splide Carousel

You can use lightbox links inside Splide slides to get both carousel and lightbox:

```html
<div class="splide" data-splide='{"type":"loop","perPage":3,"gap":"1rem","breakpoints":{"768":{"perPage":1}}}'>
  <div class="splide__track">
    <ul class="splide__list">
      <li class="splide__slide">
        <a href="/media/photo-1-full.jpg" data-lightbox="carousel-gallery" data-alt="Photo 1">
          <img src="/media/photo-1.jpg" alt="Photo 1" class="w-full h-64 object-cover rounded-lg">
        </a>
      </li>
      <li class="splide__slide">
        <a href="/media/photo-2-full.jpg" data-lightbox="carousel-gallery" data-alt="Photo 2">
          <img src="/media/photo-2.jpg" alt="Photo 2" class="w-full h-64 object-cover rounded-lg">
        </a>
      </li>
    </ul>
  </div>
</div>
```

Note: When combining with Splide `type:"loop"`, Splide clones slides, which may
duplicate `data-lightbox` elements. Use `type:"slide"` if exact gallery count matters.

#### Attributes Reference

| Attribute | Element | Required | Description |
|-----------|---------|----------|-------------|
| `data-lightbox` | `<a>` | Yes | Group name string. All elements with the same value form one gallery. |
| `href` | `<a>` | Yes | URL of the full-size image displayed in the lightbox. |
| `data-alt` | `<a>` | No | Caption text shown below the image in the lightbox. |

The lightbox also reads `data-src` and `src` as fallbacks for the image URL
(in order: `href` > `data-src` > `src`).

#### Do's and Don'ts

**Do:**
- Use `<a>` tags with `href` pointing to the full-size image
- Wrap each `<img>` thumbnail inside the `<a>` tag
- Use the same `data-lightbox` group name for images that should be navigable together
- Add `data-alt` for captions (use `{{ trans.xxx }}` for translated captions)
- Add `cursor-pointer` class to the `<a>` or `<img>` for visual affordance
- Use `hover:opacity-90 transition` for hover feedback

**Don't:**
- Do NOT add inline `<script>` to initialize the lightbox — it auto-initializes
- Do NOT put `data-lightbox` on the `<img>` tag — it must be on the `<a>` wrapper
- Do NOT use `data-lightbox` without an `href` (or `data-src`) — the lightbox needs a URL
- Do NOT forget the `<a>` wrapper — `data-lightbox` on a bare `<img>` won't create a clickable link
- Do NOT use the same group name for galleries that should be independent

#### Common Mistakes

1. **Putting `data-lightbox` on `<img>` instead of `<a>`** — The lightbox reads `href` from the `<a>` tag for the full-size image URL.
2. **Missing `href` on the `<a>` tag** — Without a URL, the lightbox has nothing to display.
3. **Same group name for unrelated galleries** — Images from both sections will appear in one combined gallery.
4. **Not adding `cursor-pointer`** — Users won't realize images are clickable without a pointer cursor.
"""
