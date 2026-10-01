# Manual tests — editor Design panel

Requests to try by hand in the editor, with the expected result. Run on **demo-ai-lab**, never on a client site.

**Before you start**
- **New code:** in the manager, **Stop** then **Start** `demo-ai-lab` (templates and Python are cached until the server restarts).
- **Where:** open a page with `?edit=v2`, e.g. http://localhost:8134/?edit=v2, then select an element and open the **Design** tab.
- **After each test:** **Undo** (top bar) puts the page back.

**How to mark:** `[x]` passed · `[!]` passed with notes (write them below) · `[ ]` failed.

---

## 1. The panel fits the element

| ✓ | Do this | Expected |
|---|---|---|
| [ ] | Select a title (h1/h2) | **Heading**: Typography (font, size, weight, align, colour) · More options · 7 · Spacing · Visibility & border · Advanced |
| [ ] | Select a paragraph | **Text**, same groups as Heading |
| [ ] | Select a "Reservar" button | **Button**: Button (style, size, corners) · Colours (Normal / Hover) · Link · Spacing (closed). Shows the current style (Filled, M, Soft) |
| [ ] | Select a text link inside a paragraph | **Link**: Typography plus a Link group (hover colour, URL, new tab) |
| [ ] | Select a photo | **Image**: Replace…, shape, width, corners · More options (focus point, fit, shadow, black & white, zoom, brightness) |
| [ ] | Select a section | **Section**: Background (type, colour or image, darken, text on it, video) · Layout (space top/bottom, content width, align) |
| [ ] | Select a grid of cards | **Container**: columns, gap, align items · More options (reverse on mobile, distribute) |
| [ ] | Select a slider or gallery root | Generic panel (Spacing, Visibility & border); the slider/gallery controls stay in **Content** |

## 2. Changes show at once and save

| ✓ | Do this | Expected |
|---|---|---|
| [ ] | Title → Size slider | The title resizes while you drag; one change in the Save counter when you let go |
| [ ] | Title → a brand swatch | Colour changes; the swatch name shows below ("Primary", "Text"…) |
| [ ] | Title → **Other colour…** | Native picker; the hex shows below the swatches |
| [ ] | Button → Size **L**, Corners **Round** | Button grows and rounds; Save → reload → still there; **EN** page too |
| [ ] | Section → Space top/bottom **XL** | More space above and below; nothing else moves |
| [ ] | Section → Background **Image** | Image picker opens (Library / Upload / Unsplash); the picked photo becomes the background; **Darken** slider works |
| [ ] | Image → Focus point: click the bottom of the thumbnail | The visible part of the photo moves down |
| [ ] | Any row you changed | Orange dot by the label and ↺ on the right; ↺ puts that one value back |
| [ ] | **Advanced** → edit the classes by hand | The element updates; the rows above follow |

## 3. Screen sizes

| ✓ | Do this | Expected |
|---|---|---|
| [ ] | Top bar → **Mobile** | The page shows at phone width in a frame, laid out as on a phone (mobile menu, stacked columns) |
| [ ] | In Mobile, select the main title → Size 34 | Title is 34 in the frame. Back in **Desktop** it keeps its desktop size. The panel says "changes apply to mobile only" |
| [ ] | In Mobile, a row you changed | Orange dot = overridden on mobile; ↺ makes it follow tablet again |
| [ ] | In Desktop, change a size that tablet/mobile didn't override | All screens follow |
| [ ] | Image → Visibility & border → untick **Mobile** | In Mobile the image shows hatched with "Hidden on mobile" and can still be selected; on a real phone it's gone |
| [ ] | Click an element inside the Mobile frame | The editor selects it and the panel shows it |
| [ ] | Make a change, don't save, switch to Tablet | The frame already shows the change |

## 4. Apply to all, copy, reset

| ✓ | Do this | Expected |
|---|---|---|
| [ ] | Select a button | Under the groups: "N buttons with this style on M pages" |
| [ ] | Change its corners to Round → **Apply to all similar** | Saves, reloads, toast "Applied to … buttons on … pages". The other buttons with the same style are round, on the other pages and in EN too |
| [ ] | Undo on each page | Each page goes back (one Undo per page) |
| [ ] | Button → **Copy style from…** → click another button | This button takes the other one's look; Esc cancels the pick |
| [ ] | Change a few things → **Reset this element** | Back to how it was when the page was opened |

---

**What to report when something fails**
- the test number, the page and the element;
- what you expected and what happened;
- the classes in **Advanced** before and after, if relevant.
