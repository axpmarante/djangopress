"""
Component skill: Alpine.js Tabs.

Uses Alpine.js (pre-loaded in base.html) for tab switching. Critical: panels
must use absolute positioning to prevent layout flicker during transitions.
"""

NAME = "alpine-tabs"

DESCRIPTION = "Alpine.js tabbed interface with fade transitions and absolute-positioned panels."

INDEX_ENTRY = (
    "Alpine.js tabs. `x-data=\"{ tab: 'tab1' }\"`, tab buttons with `@click`, "
    "panels with `x-show` + `absolute inset-0` (CRITICAL: prevents flicker). "
    "Container needs `relative overflow-hidden min-h-[Xpx]`. `x-cloak` on hidden panels."
)

FULL_REFERENCE = """\
### Tabs (Alpine.js)

Uses Alpine.js (`x-data`, `x-show`, `@click`) which is pre-loaded in `base.html`.

#### CRITICAL: Absolute Panel Positioning

Each tab panel MUST use `absolute inset-0` positioning so panels stack on top of
each other. Without this, both the entering and leaving panels are visible during
the transition, causing a jarring "flicker" where content doubles in height.

The container must have `relative overflow-hidden min-h-[Xpx]` to contain the
absolutely-positioned panels and prevent them from collapsing to zero height.

**Why `min-h-[Xpx]` is needed:** Since panels are `position: absolute`, they
don't contribute to the container's height. Set `min-h` to at least the tallest
panel's expected height. Common values: `min-h-[300px]`, `min-h-[400px]`,
`min-h-[500px]`. Choose based on content.

#### Basic Tabs

```html
<div x-data="{ tab: 'tab1' }">
  <!-- Tab buttons -->
  <div class="flex border-b">
    <button @click="tab = 'tab1'" :class="tab === 'tab1' ? 'border-b-2 border-blue-500 text-blue-600' : 'text-gray-500'" class="px-4 py-2 font-medium">{{ trans.tab1_label }}</button>
    <button @click="tab = 'tab2'" :class="tab === 'tab2' ? 'border-b-2 border-blue-500 text-blue-600' : 'text-gray-500'" class="px-4 py-2 font-medium">{{ trans.tab2_label }}</button>
    <button @click="tab = 'tab3'" :class="tab === 'tab3' ? 'border-b-2 border-blue-500 text-blue-600' : 'text-gray-500'" class="px-4 py-2 font-medium">{{ trans.tab3_label }}</button>
  </div>

  <!-- Tab panels — note: absolute positioning + min-h on container -->
  <div class="relative overflow-hidden min-h-[400px]">
    <div class="absolute inset-0 p-6" x-show="tab === 'tab1'" x-transition:enter="transition ease-out duration-300" x-transition:enter-start="opacity-0" x-transition:enter-end="opacity-100" x-transition:leave="transition ease-in duration-200" x-transition:leave-start="opacity-100" x-transition:leave-end="opacity-0">
      <p>{{ trans.tab1_content }}</p>
    </div>
    <div class="absolute inset-0 p-6" x-show="tab === 'tab2'" x-cloak x-transition:enter="transition ease-out duration-300" x-transition:enter-start="opacity-0" x-transition:enter-end="opacity-100" x-transition:leave="transition ease-in duration-200" x-transition:leave-start="opacity-100" x-transition:leave-end="opacity-0">
      <p>{{ trans.tab2_content }}</p>
    </div>
    <div class="absolute inset-0 p-6" x-show="tab === 'tab3'" x-cloak x-transition:enter="transition ease-out duration-300" x-transition:enter-start="opacity-0" x-transition:enter-end="opacity-100" x-transition:leave="transition ease-in duration-200" x-transition:leave-start="opacity-100" x-transition:leave-end="opacity-0">
      <p>{{ trans.tab3_content }}</p>
    </div>
  </div>
</div>
```

#### Key Attributes Explained

| Attribute | Where | Purpose |
|-----------|-------|---------|
| `x-data="{ tab: 'tab1' }"` | Outer wrapper | Alpine.js reactive state. `tab` holds the active tab ID. |
| `@click="tab = 'tabN'"` | Tab button | Sets the active tab on click. |
| `:class="tab === 'tabN' ? '...' : '...'"` | Tab button | Conditional active/inactive styling. |
| `x-show="tab === 'tabN'"` | Panel div | Shows/hides the panel based on active tab. |
| `x-cloak` | Initially-hidden panels | Prevents flash of unstyled content on page load. |
| `x-transition:enter` | Panel div | Fade-in animation. |
| `x-transition:leave` | Panel div | Fade-out animation. |
| `absolute inset-0` | Panel div | CRITICAL — stacks panels so only one is visible. |
| `relative overflow-hidden min-h-[Xpx]` | Panel container | Contains absolutely-positioned panels. |

#### Transition Configuration

The default fade transition:
```
x-transition:enter="transition ease-out duration-300"
x-transition:enter-start="opacity-0"
x-transition:enter-end="opacity-100"
x-transition:leave="transition ease-in duration-200"
x-transition:leave-start="opacity-100"
x-transition:leave-end="opacity-0"
```

For a faster/snappier feel, reduce durations:
```
x-transition:enter="transition ease-out duration-150"
x-transition:leave="transition ease-in duration-100"
```

For slide + fade effect:
```
x-transition:enter="transition ease-out duration-300"
x-transition:enter-start="opacity-0 translate-y-2"
x-transition:enter-end="opacity-100 translate-y-0"
x-transition:leave="transition ease-in duration-200"
x-transition:leave-start="opacity-100 translate-y-0"
x-transition:leave-end="opacity-0 -translate-y-2"
```

#### Pill-Style Tabs (Alternative Styling)

```html
<div x-data="{ tab: 'tab1' }">
  <div class="flex gap-2 mb-6">
    <button @click="tab = 'tab1'" :class="tab === 'tab1' ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'" class="px-5 py-2 rounded-full font-medium transition">{{ trans.tab1_label }}</button>
    <button @click="tab = 'tab2'" :class="tab === 'tab2' ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'" class="px-5 py-2 rounded-full font-medium transition">{{ trans.tab2_label }}</button>
  </div>
  <div class="relative overflow-hidden min-h-[300px]">
    <!-- panels with absolute inset-0 as above -->
  </div>
</div>
```

#### Card-Style Tabs

```html
<div x-data="{ tab: 'tab1' }">
  <div class="flex border-b border-gray-200">
    <button @click="tab = 'tab1'" :class="tab === 'tab1' ? 'bg-white border-t border-l border-r border-gray-200 -mb-px rounded-t-lg text-blue-600' : 'text-gray-500 hover:text-gray-700'" class="px-6 py-3 font-medium">{{ trans.tab1_label }}</button>
    <button @click="tab = 'tab2'" :class="tab === 'tab2' ? 'bg-white border-t border-l border-r border-gray-200 -mb-px rounded-t-lg text-blue-600' : 'text-gray-500 hover:text-gray-700'" class="px-6 py-3 font-medium">{{ trans.tab2_label }}</button>
  </div>
  <div class="relative overflow-hidden min-h-[400px] border border-t-0 border-gray-200 rounded-b-lg bg-white">
    <!-- panels with absolute inset-0 as above -->
  </div>
</div>
```

#### Vertical Tabs

```html
<div x-data="{ tab: 'tab1' }" class="flex gap-6">
  <!-- Vertical tab buttons -->
  <div class="flex flex-col space-y-1 min-w-[200px]">
    <button @click="tab = 'tab1'" :class="tab === 'tab1' ? 'bg-blue-50 text-blue-700 border-l-2 border-blue-600' : 'text-gray-600 hover:bg-gray-50'" class="text-left px-4 py-3 font-medium rounded-r transition">{{ trans.tab1_label }}</button>
    <button @click="tab = 'tab2'" :class="tab === 'tab2' ? 'bg-blue-50 text-blue-700 border-l-2 border-blue-600' : 'text-gray-600 hover:bg-gray-50'" class="text-left px-4 py-3 font-medium rounded-r transition">{{ trans.tab2_label }}</button>
  </div>
  <!-- Panel area -->
  <div class="relative overflow-hidden min-h-[400px] flex-1">
    <!-- panels with absolute inset-0 as above -->
  </div>
</div>
```

Note: Vertical tabs should collapse to horizontal on mobile using responsive
classes (e.g., `flex-col md:flex-row` on the outer container, and hide the
vertical button column on small screens).

#### Do's and Don'ts

**Do:**
- Use `absolute inset-0` on every panel — this is the #1 rule
- Set `min-h-[Xpx]` on the panel container (adjust to content)
- Add `x-cloak` on all initially-hidden panels
- Move padding from the container to each panel (`p-6` or `p-8`)
- Use `{{ trans.xxx }}` for all visible text (labels and content)
- Match active tab styling to the site's design system colors

**Don't:**
- Do NOT omit `absolute inset-0` on panels — this causes double-height flicker
- Do NOT put `overflow-hidden` on individual panels (only on the container)
- Do NOT forget `x-cloak` on hidden panels — they flash on page load without it
- Do NOT use `display: none` instead of `x-show` — Alpine manages visibility
- Do NOT set `min-h` too small — content will overflow and be clipped
- Do NOT add inline `<script>` — Alpine.js handles everything declaratively

#### Common Mistakes

1. **No `absolute inset-0` on panels** — Both entering and leaving panels are visible during transitions, causing a "jump" in content height. This is the most frequent issue.
2. **Missing `min-h-[Xpx]` on container** — Panels are absolute, so the container collapses to zero height and no content is visible.
3. **Forgetting `x-cloak`** — All panels briefly flash on page load before Alpine hides them.
4. **Padding on the container instead of panels** — With absolute positioning, padding on the container doesn't affect the panels. Put padding on each panel div.
5. **Tab state variable mismatch** — If `x-data` uses `tab: 'tab1'` but a button sets `tab = 'first'`, that panel will never show.
"""
