"""
Component skill: Alpine.js Accordion.

Uses Alpine.js (pre-loaded in base.html) for expand/collapse behavior.
Uses x-show with x-transition for animation (x-collapse requires a separate plugin).
"""

NAME = "alpine-accordion"

DESCRIPTION = "Alpine.js accordion/collapsible sections with smooth expand/collapse animation."

INDEX_ENTRY = (
    "Alpine.js accordion. `x-data=\"{ open: null }\"` for single-open, "
    "`x-data=\"{ open: {} }\"` for multi-open. Toggle via `@click`, "
    "content with `x-show` + `x-transition`. Chevron rotation via `:class`."
)

FULL_REFERENCE = """\
### Accordion (Alpine.js)

Uses Alpine.js (`x-data`, `x-show`, `@click`) which is pre-loaded in `base.html`.

#### Single-Open Accordion (Default)

Only one item can be expanded at a time. Clicking an item closes the previously
open one.

```html
<div x-data="{ open: null }" class="space-y-2">
  <!-- Item 1 -->
  <div class="border rounded-lg overflow-hidden">
    <button @click="open = open === 1 ? null : 1" class="w-full flex justify-between items-center p-4 font-medium text-left hover:bg-gray-50 transition">
      <span>{{ trans.faq_1_question }}</span>
      <svg :class="open === 1 && 'rotate-180'" class="w-5 h-5 transition-transform duration-200 flex-shrink-0 ml-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
    </button>
    <div x-show="open === 1" x-transition:enter="transition ease-out duration-200" x-transition:enter-start="opacity-0 -translate-y-2" x-transition:enter-end="opacity-100 translate-y-0" x-transition:leave="transition ease-in duration-150" x-transition:leave-start="opacity-100 translate-y-0" x-transition:leave-end="opacity-0 -translate-y-2">
      <div class="px-4 pb-4 text-gray-600">{{ trans.faq_1_answer }}</div>
    </div>
  </div>

  <!-- Item 2 -->
  <div class="border rounded-lg overflow-hidden">
    <button @click="open = open === 2 ? null : 2" class="w-full flex justify-between items-center p-4 font-medium text-left hover:bg-gray-50 transition">
      <span>{{ trans.faq_2_question }}</span>
      <svg :class="open === 2 && 'rotate-180'" class="w-5 h-5 transition-transform duration-200 flex-shrink-0 ml-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
    </button>
    <div x-show="open === 2" x-transition:enter="transition ease-out duration-200" x-transition:enter-start="opacity-0 -translate-y-2" x-transition:enter-end="opacity-100 translate-y-0" x-transition:leave="transition ease-in duration-150" x-transition:leave-start="opacity-100 translate-y-0" x-transition:leave-end="opacity-0 -translate-y-2">
      <div class="px-4 pb-4 text-gray-600">{{ trans.faq_2_answer }}</div>
    </div>
  </div>

  <!-- Item 3 -->
  <div class="border rounded-lg overflow-hidden">
    <button @click="open = open === 3 ? null : 3" class="w-full flex justify-between items-center p-4 font-medium text-left hover:bg-gray-50 transition">
      <span>{{ trans.faq_3_question }}</span>
      <svg :class="open === 3 && 'rotate-180'" class="w-5 h-5 transition-transform duration-200 flex-shrink-0 ml-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
    </button>
    <div x-show="open === 3" x-transition:enter="transition ease-out duration-200" x-transition:enter-start="opacity-0 -translate-y-2" x-transition:enter-end="opacity-100 translate-y-0" x-transition:leave="transition ease-in duration-150" x-transition:leave-start="opacity-100 translate-y-0" x-transition:leave-end="opacity-0 -translate-y-2">
      <div class="px-4 pb-4 text-gray-600">{{ trans.faq_3_answer }}</div>
    </div>
  </div>
</div>
```

#### Multi-Open Accordion

Multiple items can be expanded simultaneously. Each item tracks its own state.

```html
<div x-data="{ open: {} }" class="space-y-2">
  <!-- Item 1 -->
  <div class="border rounded-lg overflow-hidden">
    <button @click="open[1] = !open[1]" class="w-full flex justify-between items-center p-4 font-medium text-left hover:bg-gray-50 transition">
      <span>{{ trans.service_1_title }}</span>
      <svg :class="open[1] && 'rotate-180'" class="w-5 h-5 transition-transform duration-200 flex-shrink-0 ml-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
    </button>
    <div x-show="open[1]" x-transition:enter="transition ease-out duration-200" x-transition:enter-start="opacity-0 -translate-y-2" x-transition:enter-end="opacity-100 translate-y-0" x-transition:leave="transition ease-in duration-150" x-transition:leave-start="opacity-100 translate-y-0" x-transition:leave-end="opacity-0 -translate-y-2">
      <div class="px-4 pb-4 text-gray-600">{{ trans.service_1_description }}</div>
    </div>
  </div>

  <!-- Item 2 -->
  <div class="border rounded-lg overflow-hidden">
    <button @click="open[2] = !open[2]" class="w-full flex justify-between items-center p-4 font-medium text-left hover:bg-gray-50 transition">
      <span>{{ trans.service_2_title }}</span>
      <svg :class="open[2] && 'rotate-180'" class="w-5 h-5 transition-transform duration-200 flex-shrink-0 ml-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
    </button>
    <div x-show="open[2]" x-transition:enter="transition ease-out duration-200" x-transition:enter-start="opacity-0 -translate-y-2" x-transition:enter-end="opacity-100 translate-y-0" x-transition:leave="transition ease-in duration-150" x-transition:leave-start="opacity-100 translate-y-0" x-transition:leave-end="opacity-0 -translate-y-2">
      <div class="px-4 pb-4 text-gray-600">{{ trans.service_2_description }}</div>
    </div>
  </div>
</div>
```

#### Default-Open State

To have an item open by default, set its value in the initial state:

```html
<!-- Single-open: item 1 open by default -->
<div x-data="{ open: 1 }" class="space-y-2">
  ...
</div>

<!-- Multi-open: items 1 and 3 open by default -->
<div x-data="{ open: { 1: true, 3: true } }" class="space-y-2">
  ...
</div>
```

#### Styled Variants

**Borderless / Clean:**
```html
<div x-data="{ open: null }" class="divide-y">
  <div>
    <button @click="open = open === 1 ? null : 1" class="w-full flex justify-between items-center py-4 font-medium text-left">
      <span>{{ trans.faq_1_question }}</span>
      <svg :class="open === 1 && 'rotate-180'" class="w-5 h-5 transition-transform duration-200 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
    </button>
    <div x-show="open === 1" x-transition:enter="transition ease-out duration-200" x-transition:enter-start="opacity-0" x-transition:enter-end="opacity-100" x-transition:leave="transition ease-in duration-150" x-transition:leave-start="opacity-100" x-transition:leave-end="opacity-0">
      <div class="pb-4 text-gray-600">{{ trans.faq_1_answer }}</div>
    </div>
  </div>
</div>
```

**Card-Style with Shadow:**
```html
<div x-data="{ open: null }" class="space-y-3">
  <div class="bg-white rounded-xl shadow-sm border overflow-hidden">
    <button @click="open = open === 1 ? null : 1" :class="open === 1 ? 'bg-blue-50' : ''" class="w-full flex justify-between items-center p-5 font-medium text-left transition">
      <span>{{ trans.faq_1_question }}</span>
      <svg :class="open === 1 && 'rotate-180'" class="w-5 h-5 transition-transform duration-200 flex-shrink-0 ml-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
    </button>
    <div x-show="open === 1" x-transition:enter="transition ease-out duration-200" x-transition:enter-start="opacity-0 -translate-y-2" x-transition:enter-end="opacity-100 translate-y-0" x-transition:leave="transition ease-in duration-150" x-transition:leave-start="opacity-100 translate-y-0" x-transition:leave-end="opacity-0 -translate-y-2">
      <div class="px-5 pb-5 text-gray-600">{{ trans.faq_1_answer }}</div>
    </div>
  </div>
</div>
```

#### Plus/Minus Icon Variant

Replace the chevron SVG with a plus/minus indicator:

```html
<button @click="open = open === 1 ? null : 1" class="w-full flex justify-between items-center p-4 font-medium text-left">
  <span>{{ trans.faq_1_question }}</span>
  <span class="text-2xl font-light flex-shrink-0 ml-4" x-text="open === 1 ? '−' : '+'"></span>
</button>
```

#### Animation Note

This system uses `x-show` with `x-transition` for accordion animation. The
Alpine.js `x-collapse` directive (which provides height-based animation) requires
the `@alpinejs/collapse` plugin, which is NOT loaded by default in `base.html`.

The `x-show` + `x-transition` approach provides a clean fade/slide animation that
works without any extra plugins. If height-based collapse animation is needed,
add this script to the page's head (before Alpine.js loads):

```html
<script defer src="https://cdn.jsdelivr.net/npm/@alpinejs/collapse@3.x.x/dist/cdn.min.js"></script>
```

Then you can use `x-collapse` instead of `x-transition`:
```html
<div x-show="open === 1" x-collapse>
  <div class="px-4 pb-4">Content</div>
</div>
```

#### Do's and Don'ts

**Do:**
- Use `text-left` on the button (it defaults to center alignment)
- Add `flex-shrink-0` to the chevron/icon so it doesn't compress
- Add `ml-4` spacing between the text and icon
- Use `overflow-hidden` on each accordion item container
- Use `{{ trans.xxx }}` for all visible text
- Add `hover:bg-gray-50 transition` on buttons for interactive feedback

**Don't:**
- Do NOT use `x-collapse` without loading the `@alpinejs/collapse` plugin
- Do NOT nest Alpine.js `x-data` scopes within accordion items (it creates a new scope that can't read the parent's `open` state)
- Do NOT use `display: none` or `hidden` classes — let Alpine handle visibility with `x-show`
- Do NOT forget `overflow-hidden` on the item container — content may peek out during transitions

#### Common Mistakes

1. **Using `x-collapse` without the plugin** — It silently fails and content just snaps open/closed with no animation. Use `x-show` + `x-transition` instead.
2. **Missing `text-left` on button** — Button text centers by default, which looks wrong for accordion headers.
3. **Chevron not rotating** — Make sure the `:class` binding matches the exact `open` comparison (e.g., `open === 1` not `open == 1`).
4. **Content overflowing during animation** — Add `overflow-hidden` to the accordion item's outer container.
5. **Nesting `x-data` inside items** — If each item has its own `x-data`, it creates an isolated scope and the "single open" behavior (from the parent `open` variable) breaks.
"""
