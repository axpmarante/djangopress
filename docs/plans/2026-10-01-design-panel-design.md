# Editor — element-aware Design panel

**Date:** 2026-10-01
**Status:** Draft for review
**Repo:** djangopress (engine). Branch `feature/design-panel` (from `feature/editor-dialogs`).
**Mockup (approved 2026-10-01):** https://claude.ai/artifact/CxRgw6z2HeuZjdhdSskAmf
**Audience:** agency staff. Simple adjustments without AI, in the style of Elementor / Webflow. The UI stays in English for now.

**Goal:** replace the Design tab's list of Tailwind dropdowns with a panel that adapts to the selected element:
- visual controls (brand swatches, segmented buttons, sliders in px, a box-model diagram) with the preview updating live;
- values per screen size (desktop / tablet / mobile), previewed at the real width;
- the less common parameters under **More options**;
- the raw classes under **Advanced**.

---

## Context (facts from the code, 2026-10-01)

- **Tailwind:** pages load the Tailwind **Play CDN** (`templates/base.html:15`). There is no build step anywhere: no config, no CLI, Docker only runs `collectstatic`. Any class the panel writes (`text-[#C42014]`, `max-md:hidden`, `object-[50%_30%]`, `md:max-lg:grid-cols-2`) renders immediately, in the editor and in production. Breakpoints are the v3 defaults: md 768, lg 1024.
- **Current Design tab** (`sidebar.js renderDesignTab`, `lib/tailwind-classes.js`, `lib/class-parser.js`):
  - It matches whole tokens only, so responsive, arbitrary and `max-*` classes are never read.
  - Writing a dropdown uses the family's first prefix, so `py-4` becomes `p-N`.
  - Hex colours and palette colours end up side by side and conflict.
  - Classes are reordered on every write.
  - Undo sets `className` and drops runtime classes.
- **Saving classes:** `change:classes` → `/update-page-classes/` writes **every language copy** (`api_views.py:497-591`), checkpointed by `/checkpoint/` before each save. Inline styles (section background image and overlay, `data-overlay`) go through `/update-page-attribute/`, also in every language.
- **Device preview:** the Desktop/Tablet/Mobile buttons narrow `.editor-v2-content` to 768/375 px (`viewport.js`, `editor.css:61-77`). Media queries still follow the browser window, so the "Mobile" preview shows desktop styles. Responsive editing can't be judged today.
- **Site tokens:** `SiteSettings` has the colour fields `primary_color`, `primary_color_hover`, `secondary_color`, `accent_color`, `background_color`, `text_color` and `heading_color` (hex). It has fonts in `heading_font`, `body_font` and `h1_font`…`h6_font`, plus button colours. `design_guide` holds the extract-design palette table as markdown. Sites also use many `[#hex]` classes directly in their HTML. None of this reaches the editor today.
- **Site-wide restyle** exists only as assistant tools (`site_assistant/tools/style_tools.py`: `find_elements`, `restyle_elements`, with per-page checkpoints and Undo).

---

## 1. Element types — one panel per type

A new `lib/element-types.js` classifies the selected element:

| Type | Recognised by |
|---|---|
| `section` | has `data-section` |
| `container` | grid/flex element (computed `display`) with 2 or more element children, not a component root (sliders and galleries keep their Content panel) |
| `button` | `a` or `button` with a background, border or padding class, or `role="button"` |
| `link` | any other `a` (text link) |
| `heading` | `h1`–`h6` |
| `text` | `p`, `li`, `blockquote`, `span`, `label`, `small`, `figcaption` |
| `image` | `img`, `picture`, or a full-bleed image layer |
| `other` | anything else |

The `other` type gets the generic panel: Spacing, Visibility & border, Advanced.

The groups per type are the ones in the approved mockup:
- **Heading / text** — *Typography*: font (the site's fonts only), size (px), weight, align, colour. *More options*: line height, letter spacing, case, italic / underline, colour strength, text shadow, max width. Plus *Spacing* (box model).
- **Button** — *Button*: style (filled / outline / text link), size S/M/L, corners, align. *More options*: icon before/after, full width, text size, uppercase, shadow, hover effect (colour / lift / underline). Then *Colours* with a **Normal | Hover** switch, *Link* (URL, new tab), and *Spacing* (closed).
- **Link** — the text controls plus link colour, hover colour and underline.
- **Image** — *Image*: replace (opens the image picker), shape (original / 1:1 / 4:3 / 16:9 / 3:4), width %, corners. *More options*: focus point (click on the thumbnail → `object-[x%_y%]`), fit, shadow, black & white, zoom on hover, brightness, link.
- **Section**:
  - *Background*: none / colour / image. For an image: the current image with **Change…**, darken %, and text on it (dark / light). *More options*: overlay colour, focus point, fixed background.
  - *Layout*: space top/bottom S/M/L/XL, content width, align content. *More options*: height (fit / half screen / full screen), vertical align, divider lines.
  - Background video stays where it is today.
- **Container** — *Layout*: columns 1–4, gap, align items. *More options*: reverse the order on mobile, distribute.
- **Every type** — *Visibility & border* (closed): show on desktop/tablet/mobile, border width/colour/style, opacity, anchor (`id`). Then the actions *Apply to all similar*, *Copy style from…* and *Reset this element*. *Advanced* (closed): the class textarea, kept as it is today.

**Row behaviour (all controls):**
- **Changed:** a dot marks a value that differs from what the page had when the editor opened (or, on tablet/mobile, a value overridden for that screen).
- **Reset:** a ↺ button on the row resets it.
- **More options:** the group shows its count ("· 7") and remembers whether it was open while the same element stays selected.

## 2. A class model that understands variants and arbitrary values

A new pure module `lib/class-model.js` replaces `class-parser.js` / `tailwind-classes.js` for the new panel. The old modules stay for anything else that imports them.

**Properties.** A property (e.g. `fontSize`, `paddingTop`, `textColor`, `display`, `gridCols`) knows:
- the class families that set it: `text-{scale}` / `text-[40px]` for size; `p-`, `py-` and `pt-` for padding-top, each with the correct axis;
- how to parse a value: Tailwind scale → px, `[…]` arbitrary values, `/alpha` on colours;
- how to write one: spacing in multiples of 4 → scale (`pt-6`), anything else → arbitrary (`pt-[22px]`); font sizes always as `text-[40px]`; colours as `text-[#hex]` / `bg-[#hex]` (`/80` for strength).

**Effective values per screen.** For each property the model computes the value at the three screens from all of its classes:
- mobile (< 768): base, then `max-md:` / `max-lg:`;
- tablet (768–1023): base, then `md:`, then `max-lg:` / `md:max-lg:`;
- desktop (≥ 1024): base, then `md:` / `lg:`.

States (`hover:`) are a separate dimension, used by the button and link colour controls.

**Writing (Elementor semantics).** A change made on a screen also applies to the smaller screens that had no value of their own:
- *Desktop:* a desktop change also reaches tablet when tablet had the same value as desktop, and reaches mobile when mobile had the same value as tablet.
- *Tablet:* a tablet change cascades to mobile the same way.
- *Mobile:* a mobile change only affects mobile.

The model then removes every class of that property and re-emits it **mobile-first** (the convention the AI and the build pipeline already use): the base class is the mobile value, `md:` is added when tablet ≠ mobile, `lg:` when desktop ≠ tablet. Classes of other properties are not touched, and **class order is preserved**: new classes replace the old ones in place, or are appended.

**Bugs this fixes.**
- **Axis loss:** `py-4` stays `py-*`.
- **Conflicts:** a hex and a palette colour can no longer sit side by side.
- **Variants:** responsive and arbitrary classes are read, not ignored.
- **Order:** class order no longer changes on every write.
- **Undo:** keeps runtime classes. `changes.js` now restores only the stored classes and leaves `ev2-*`/Splide runtime classes in place.

## 3. Site tokens in the panel

New `GET /editor-v2/api/design-tokens/` (editor-only), cached per request. It returns:
- **Colours** (for the swatches):
  - First the named SiteSettings colours that are set: Primary, Primary hover, Secondary, Accent, Background, Text, Heading, button colours. Duplicates are removed.
  - Then up to 8 more `[#hex]` colours found most often in the site's pages and header/footer, named by hex.
  - White and black are always offered. **Other colour…** opens the native picker.
- **Fonts:** `heading_font`, `body_font` and any distinct `h1_font`…`h6_font`. The font control only offers these.
- **Scales:** the S/M/L/XL presets for section spacing and button sizes, derived from `spacing_scale` / `button_size` when set, else the defaults in the mockup.

## 4. True-width device preview

To make the device buttons truthful, Tablet and Mobile show the page in an `<iframe>` of that width, loading the same URL with `?ev2_frame=1`. That mode renders the page without the editor UI, plus a small bridge script. It is allowed only for editors, and works for inactive pages too (as `preview=true` does today). The bridge:
- **Selection:** highlights the selected element and sends a click on an element back to the parent as a selector, so the parent selects the same element.
- **Live mirror:** receives every pending `change:classes` / `change:attribute` from the parent and applies it by selector, so unsaved edits show at the real width.
- **Hidden elements:** an element hidden on that screen by a visibility class is shown hatched with a "Hidden on mobile" tag (editor-only inline override), so it stays selectable.

In Tablet/Mobile:
- the Design panel edits that screen's values;
- inline text editing, drag and structure actions ask you to switch to Desktop. They act on the desktop DOM, which is still the source of truth.

Desktop is the editor as today.

## 5. Apply to all similar, Copy style, Reset

- **Apply to all similar:**
  - *Matching:* finds the elements across every active page (and header/footer when the element is in one) with the same tag and the same class list as the element **had when it was selected**. The button shows the count ("6 buttons on 4 pages").
  - *Applying:* adds/removes the classes this element changed. It goes through a new `POST /editor-v2/api/restyle-similar/`, built on the same service as the assistant's `restyle_elements`. That logic moves to `core/services/restyle.py`, shared by both.
  - *Saving and Undo:* every page gets a checkpoint, every language is written, and the editor reports "Applied to 6 buttons on 4 pages" with Undo.
  - *Unsaved edits:* pending edits on the current page are saved first.
- **Copy style from…:** click another element of the same type. Its classes for the panel's properties replace this element's (other classes, such as layout hooks, stay).
- **Reset this element:** the classes it had when the editor opened.

## 6. What stays as it is

- Content tab, component panels (sliders, galleries), structure actions, inline text editing, image picker (now with Unsplash), dialogs.
- The section background image and overlay mechanism (inline style plus `data-overlay`). The panel reads and writes it.
- The section background **colour** moves from the inline style to a `bg-[#hex]` class. An inline `background-color` is removed when the panel sets the class, so the two mechanisms no longer fight.

## Out of scope

- Translating the editor UI.
- Absolute positioning, z-index, transforms, per-element custom CSS, extra fonts, animations.
- A `tailwind.config` editor.
- Global style presets (headings/buttons defined once for the whole site) — a later step. "Apply to all similar" covers the common case now.

## Testing

- **Class model (`lib/class-model.js`):** a browser harness like `tests/js/components_test.html` (`PASS n` / `FAIL n` in the title, run with Playwright). Cases:
  - parse and effective values on all three screens for mobile-first, desktop-first and mixed inputs;
  - each write rule (cascade, overrides, mobile-only);
  - axis kept (`py-4`);
  - hex vs palette colours;
  - order kept;
  - hover state;
  - spacing scale vs arbitrary values.
- **Element types:** harness cases over the existing component fixtures plus new ones (button vs link, container vs plain div, image layer).
- **Python:**
  - the design-tokens endpoint: named colours, frequency colours, fonts, no duplicates;
  - `restyle-similar`: match by tag and class list, every language, checkpoints, header/footer only when the element is there, Undo through the editor history;
  - the shared restyle service keeps the assistant tests green.
- **Browser (Playwright on a demo copy, never a client site):**
  - each element type shows its panel;
  - a mobile override is visible in the iframe at 390 px and not on desktop;
  - Apply to all similar and Undo;
  - save + reload keeps everything.
- **Manual:** a checklist like `docs/evals/2026-10-01-chat-manual-tests.md` for the panel.
