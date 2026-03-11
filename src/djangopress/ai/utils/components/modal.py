"""
Component skill: Alpine.js Modal / Dialog.

Uses Alpine.js (pre-loaded in base.html) for show/hide logic. Features overlay
backdrop, z-index layering, and click-outside-to-close.
"""

NAME = "modal"

DESCRIPTION = "Alpine.js modal/dialog with backdrop overlay, transitions, and click-outside dismiss."

INDEX_ENTRY = (
    "Alpine.js modal. `x-data=\"{ open: false }\"`, trigger via `@click=\"open = true\"`. "
    "Overlay at z-40 + dialog at z-50 with `@click.self` to close on backdrop. "
    "`x-transition` for fade/scale. Add `overflow-hidden` to body when open."
)

FULL_REFERENCE = """\
### Modal / Dialog (Alpine.js)

Uses Alpine.js (`x-data`, `x-show`, `@click`, `x-transition`) which is pre-loaded
in `base.html`.

#### Basic Modal

```html
<div x-data="{ open: false }">
  <!-- Trigger button -->
  <button @click="open = true" class="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition">Open Details</button>

  <!-- Backdrop overlay -->
  <div x-show="open" x-transition.opacity.duration.300ms class="fixed inset-0 bg-black/50 z-40" @click="open = false"></div>

  <!-- Modal dialog -->
  <div x-show="open" x-transition:enter="transition ease-out duration-300" x-transition:enter-start="opacity-0 scale-95" x-transition:enter-end="opacity-100 scale-100" x-transition:leave="transition ease-in duration-200" x-transition:leave-start="opacity-100 scale-100" x-transition:leave-end="opacity-0 scale-95" class="fixed inset-0 z-50 flex items-center justify-center p-4" @click.self="open = false">
    <div class="bg-white rounded-xl shadow-2xl max-w-lg w-full p-6">
      <!-- Close button (top-right) -->
      <div class="flex justify-between items-start mb-4">
        <h3 class="text-xl font-bold">Details</h3>
        <button @click="open = false" class="text-gray-400 hover:text-gray-600 transition">
          <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
        </button>
      </div>
      <!-- Modal body -->
      <div class="text-gray-600 mb-6">
        <p>Here you can find more information about our services and how we can help you achieve your goals.</p>
      </div>
      <!-- Modal footer -->
      <div class="flex justify-end gap-3">
        <button @click="open = false" class="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition">Cancel</button>
        <button @click="open = false" class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition">Confirm</button>
      </div>
    </div>
  </div>
</div>
```

#### Z-Index Layering

The modal uses a two-layer z-index approach:

| Layer | z-index | Purpose |
|-------|---------|---------|
| Backdrop | `z-40` | Semi-transparent overlay that dims the page |
| Dialog wrapper | `z-50` | Flex container that centers the dialog |

The backdrop gets `@click="open = false"` to close on click.
The dialog wrapper gets `@click.self="open = false"` so clicking outside
the white dialog box (but within the wrapper) also closes it.

**Why two layers?** The backdrop provides the visual dimming and receives direct
click events. The dialog wrapper is a separate layer so the dialog content
(buttons, text, inputs) doesn't trigger the close behavior.

#### Modal Sizes

Control width with `max-w-*` on the dialog container:

| Size | Class | Typical Use |
|------|-------|-------------|
| Small | `max-w-sm` | Confirmations, alerts |
| Medium | `max-w-lg` | Default — forms, details |
| Large | `max-w-2xl` | Rich content, galleries |
| Extra Large | `max-w-4xl` | Data tables, dashboards |
| Full Width | `max-w-full mx-4` | Near-fullscreen content |

```html
<!-- Small confirmation modal -->
<div class="bg-white rounded-xl shadow-2xl max-w-sm w-full p-6">
  ...
</div>

<!-- Large content modal -->
<div class="bg-white rounded-xl shadow-2xl max-w-2xl w-full p-8">
  ...
</div>
```

#### Scrollable Modal Content

For modals with long content, add `max-h` and `overflow-y-auto` to the body area:

```html
<div class="bg-white rounded-xl shadow-2xl max-w-lg w-full flex flex-col max-h-[90vh]">
  <!-- Fixed header -->
  <div class="p-6 border-b flex-shrink-0">
    <div class="flex justify-between items-start">
      <h3 class="text-xl font-bold">Details</h3>
      <button @click="open = false" class="text-gray-400 hover:text-gray-600">
        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
      </button>
    </div>
  </div>
  <!-- Scrollable body -->
  <div class="p-6 overflow-y-auto">
    <p>This section contains detailed information about our services, policies, and terms. Please read through carefully before proceeding.</p>
  </div>
  <!-- Fixed footer -->
  <div class="p-6 border-t flex-shrink-0 flex justify-end gap-3">
    <button @click="open = false" class="px-4 py-2 bg-gray-100 rounded-lg">Close</button>
  </div>
</div>
```

#### Body Scroll Lock

To prevent the page from scrolling behind the modal, toggle `overflow-hidden`
on `document.body`:

```html
<div x-data="{ open: false }" x-init="$watch('open', val => document.body.classList.toggle('overflow-hidden', val))">
  ...
</div>
```

This uses Alpine's `$watch` to add/remove `overflow-hidden` on `<body>` whenever
`open` changes.

#### Image/Media Modal

```html
<div x-data="{ open: false }">
  <img @click="open = true" src="{{ MEDIA_URL }}site_images/thumb.jpg" alt="Preview" class="cursor-pointer rounded-lg hover:opacity-90 transition">

  <div x-show="open" x-transition.opacity class="fixed inset-0 bg-black/80 z-40" @click="open = false"></div>
  <div x-show="open" x-transition class="fixed inset-0 z-50 flex items-center justify-center p-8" @click.self="open = false">
    <img src="{{ MEDIA_URL }}site_images/full-size.jpg" alt="Full size" class="max-w-full max-h-[85vh] object-contain rounded-lg shadow-2xl">
  </div>
</div>
```

Note: For a full image gallery with navigation, use the `lightbox` component instead.
A single-image preview/modal like this is fine for isolated cases (e.g., a team
member bio photo).

#### Transition Options

**Default (scale + fade):**
```
x-transition:enter="transition ease-out duration-300"
x-transition:enter-start="opacity-0 scale-95"
x-transition:enter-end="opacity-100 scale-100"
x-transition:leave="transition ease-in duration-200"
x-transition:leave-start="opacity-100 scale-100"
x-transition:leave-end="opacity-0 scale-95"
```

**Slide up from bottom:**
```
x-transition:enter="transition ease-out duration-300"
x-transition:enter-start="opacity-0 translate-y-8"
x-transition:enter-end="opacity-100 translate-y-0"
x-transition:leave="transition ease-in duration-200"
x-transition:leave-start="opacity-100 translate-y-0"
x-transition:leave-end="opacity-0 translate-y-8"
```

**Simple fade (no scale):**
```
x-transition:enter="transition ease-out duration-200"
x-transition:enter-start="opacity-0"
x-transition:enter-end="opacity-100"
x-transition:leave="transition ease-in duration-150"
x-transition:leave-start="opacity-100"
x-transition:leave-end="opacity-0"
```

#### Do's and Don'ts

**Do:**
- Use `fixed inset-0` on both the backdrop and the dialog wrapper
- Use `z-40` for backdrop and `z-50` for the dialog wrapper
- Use `@click.self="open = false"` on the dialog wrapper (not `@click`)
- Use `@click="open = false"` on the backdrop (direct click handler)
- Include a visible close button (X icon) in the dialog — don't rely solely on backdrop click
- Use `x-transition` for smooth open/close animation
- Add body scroll lock via `$watch` for modals with long content

**Don't:**
- Do NOT use `@click="open = false"` on the dialog wrapper — use `@click.self` (otherwise clicking any content inside also closes the modal)
- Do NOT put the trigger button inside the dialog — it must be outside the `x-show` element
- Do NOT use the same `z-index` for both backdrop and dialog — the dialog must be higher
- Do NOT create multiple independent modals that can be open simultaneously — they fight for z-index and focus
- Do NOT forget `p-4` on the dialog wrapper — without it, the dialog touches screen edges on mobile
- Do NOT put `x-show` on the inner dialog `<div>` — put it on the outer `fixed` wrapper

#### Focus Trapping Note

Alpine.js core does not include focus trapping. For accessibility, keyboard users
can tab out of the modal into the page behind it. For most CMS landing pages this
is acceptable. If strict focus trapping is needed, use the `@alpinejs/focus` plugin:

```html
<script defer src="https://cdn.jsdelivr.net/npm/@alpinejs/focus@3.x.x/dist/cdn.min.js"></script>
```

Then add `x-trap="open"` to the dialog container:
```html
<div x-trap="open" class="bg-white rounded-xl shadow-2xl max-w-lg w-full p-6">
  ...
</div>
```

This plugin is NOT loaded by default in `base.html`.

#### Common Mistakes

1. **Using `@click` instead of `@click.self` on the dialog wrapper** — Every click inside the modal (buttons, inputs, text) bubbles up and closes the modal.
2. **Same z-index on backdrop and dialog** — The dialog content may not be clickable if the backdrop is at the same layer.
3. **Missing `p-4` on the dialog wrapper** — On mobile, the dialog extends to the very edge of the screen with no breathing room.
4. **Trigger button inside `x-show` area** — If the button is inside the hidden container, it's not visible when the modal is closed, so users can't open it.
5. **Multiple modals interfering** — If two modals use the same z-index values and can be open simultaneously, they overlap unpredictably. Design flows so only one modal is open at a time.
"""
