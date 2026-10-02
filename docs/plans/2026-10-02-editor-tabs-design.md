# Editor tabs refresh: Content, Structure, Images

**Date:** 2026-10-02
**Status:** Approved (mockup approved 2026-10-02: https://claude.ai/artifact/2i69EdUai6RUyaW8TYcKFS, "ficou bom podes avançar", including the parts marked NEW)
**Repo:** djangopress engine, branch `feature/editor-tabs`, from `feature/editor-chat` (not yet merged to main)
**Audience:** agency staff (editors); UI copy in English, as in the Design and Chat tabs.

**Goal:** the three remaining sidebar tabs speak the operator's language:
- roles and names instead of tags and classes;
- every field shows what the other language says;
- links are picked rather than typed;
- the page outline reads like a table of contents with actions;
- the image list shows what needs fixing.

## Facts from the code (2026-10-02)

**Today's tabs**
- **Content** (`modules/sidebar.js` `renderContentTab`): one element at a time.
  - Text → `input.textContent = value` with `change:content`. On an element with inline formatting this wipes the formatting.
  - Link → text plus a raw `href`.
  - Image → preview, "Change Image", alt, raw `src`.
  - Containers → a list of tags (`p`, `h2`, `a`).
  - A component card (sliders, galleries) and the media-collection view sit on top.
- **Structure** (`renderStructureTab`): a tag tree (`div.mx-auto`, `img.h-[44vh]`), with ▲▼+ on sections only.
- **Images** (`modules/images-panel.js`):
  - grouped by section, captioned by file name;
  - a click selects the image and opens the image picker.

**Saving**
- `href` is saved with `_apply_structural_change_to_all_langs`, so the same value goes to every language. A `/pt/…` link lands in EN as it is.
- `alt`, `title`, `aria-label`, `data-alt` and `placeholder` are saved per language (`PER_LANGUAGE_ATTRIBUTES`).

**Existing pieces to reuse**
- **Structural verbs** (`lib/structural.js`, `structure.py`): duplicate, move up/down, insert and remove for elements and sections. They checkpoint, apply to every language and reload.
- **Element roles:** `lib/element-types.js` `elementType()`.
- **Image analysis:** `ContentGenerationService.describe_images` (vision, `image_analysis` model) for library images.
- **Image picker:** the `image-picker:open` event, with Library, Upload and Unsplash tabs.
- **Placeholder generation:** `process-images:open {section}`.

## 1. Content tab (`modules/content-panel.js`, new; `sidebar.js` delegates to it)

**Header, on every selection**
- Breadcrumb: page title › section label › role, each clickable.
- Kind icon, a role title and a one-line description, e.g. "Image on the right, title, two texts and two buttons" for a section.
- "PT · Editing Portuguese. Each language keeps its own text."

**Section selected: the section form**
- Every writable item in the section, in page order, named by role:
  - Eyebrow (short uppercase text above a heading);
  - Heading, Text, Button, Link, Image.
- Collection rules:
  - items inside a slider or gallery are left to the component card;
  - runtime clones are skipped.
- Fields:
  - text fields are inputs or textareas that type into the page, as now;
  - buttons and links show their label plus "Goes to: <kind> <value>";
  - images show a thumbnail, file name, alt and **Replace**.
- Hovering a field highlights the element; "Open" selects it.

**Heading or text selected**
- The text with a character count, and the other language's text underneath.
- Heading level H1 / H2 / H3 / H4 / Text:
  - a new structural verb retags the element in every language, with a checkpoint and Undo;
  - the hint "This page already has an H1" appears when choosing H1 and another H1 exists.
- "Also in this block": chips for the sibling items.
- **Formatted text** (element children such as `b`, `i`, `a`, `br`): the field is read-only with "Has formatting: edit it on the page", and a button starts inline editing (`inline-edit:trigger`). The sidebar never writes `textContent` over formatting.

**Button or link selected**
- **Label.**
- **Goes to:** Page | Section | Phone | Email | WhatsApp | Web address.
  - Page and Section come from `GET /editor-v2/api/link-targets/`: pages with their URL in the editing language, and their sections.
  - Phone → `tel:+…` (spaces removed).
  - Email → `mailto:`.
  - WhatsApp → `https://wa.me/<digits>?text=<message>`.
  - The current `href` is parsed back into a kind and a value.
- **Open in a new tab** → `target="_blank" rel="noopener"`.
- **Advanced:** the raw link.
- **Saving `href`:** internal links are localised per language with `ai_apply.localize_internal_links` (server change). Every other `href` is saved as today.

**Image selected**
- Preview with "W × H · sharp / may look soft at this size" (`naturalWidth` against the rendered width × 1.5).
- Replace (picker), Media library, Upload, Unsplash (the picker opened on that tab), Generate (process images for the section).
- Alt text with a counter (125 recommended) and **Describe the photo**:
  - `POST /editor-v2/api/describe-image/ {selector, …}` returns an alt per enabled language;
  - the current language goes into the field as an unsaved change;
  - the other languages are written straight away, per language.
- Focus point: Top / Center / Bottom / Left / Right → `object-{pos}` classes through `change:classes`.
- Advanced: image address.

**Other language line**
- Every text field shows the other enabled language's text.
- Source: `GET /editor-v2/api/page-copies/` (all language copies of the page or object). The same selector is resolved in each copy with DOMParser; the structure is the same in every language.
- With more than two languages, the line shows each one.
- If the text is missing there, the line says "EN: missing".

**Unchanged:** the component card (sliders, galleries) and the media-collection view.

## 2. Structure tab (`modules/structure-panel.js`, new)

- **Header:** page title, section count, and "Find a section, title or button…" (filters by section name and by the texts inside).
- **Global rows:** Header and Footer at the top and bottom, as "shared by all pages" (not editable here).
- **One row per section:**
  - drag handle, chevron, label;
  - description in words, built from the roles inside, e.g. "Photo + title + 2 texts + 2 buttons";
  - "Slider · 5 slides" / "Gallery · 12 photos" from the component detection.
- **Hover actions:** Move up, Move down, Duplicate, Hide on mobile / Show on mobile, Remove.
  - Hide on mobile is the class `max-md:hidden` on the section, through `change:classes`. It is shown as a tag on the row.
- **"+ Add section"** between rows (the existing section inserter).
- **Opening a section** (the selected one opens by itself) lists its items by role and text, with a thumbnail for images. A click selects the item.
- **Drag a section** onto another position → `move-section` with a new `before` parameter (the section to place it in front of; `null` = last), in every language, with one checkpoint.

## 3. Images tab (`modules/images-panel.js`, rewritten)

- **Summary:** "Images on this page N", plus filter chips: All, No alt text, Placeholder, Low resolution. Counts are computed in the browser:
  - **Placeholder** = `placehold.co` src or `data-image-prompt`;
  - **Low resolution** = loaded and `naturalWidth` < rendered width × 1.5;
  - **No alt text** = empty alt.
- **Grouped by section label.** Each thumbnail is captioned with its alt (amber "No alt text" when missing), with flag badges and a ×N duplicate count.
- **A click** selects the image on the page and opens an inline card here:
  - the alt field, saved as a normal change;
  - Replace…;
  - Describe the photo;
  - Show on page.
- **A section with placeholders** gets "Generate N placeholder(s)" (`process-images:open`).

## Server changes

| Change | Where |
|---|---|
| Internal `href` localised per language | `api_views.update_page_element_attribute` |
| `retag-element` verb (`structure.retag_element`): h1–h4, p | `structure.py`, `api_views`, URL |
| `move-section` takes `before` | `structure.place_section`, `api_views.move_section` |
| `GET link-targets` | `api_views` (editor_required) |
| `GET page-copies` | `api_views` (editor_required) |
| `POST describe-image`: vision alt per language; writes the other languages | `ai/services.describe_image_alt`, `api_views` (superuser_required, because it calls the AI) |

The image bytes come from the SiteImage whose file the `src` points to. Otherwise they are fetched by URL, but only when that exact `src` is in the page.

## Out of scope

- An SEO tab.
- Editing other languages side by side; the line is read-only.
- Drag-and-drop of elements inside a section.
- Focus point for background images.

## Testing

- **Python:**
  - href localisation (internal vs external);
  - `retag_element` (every language, attributes kept, checkpoint, refused tags);
  - `place_section` / `move-section before`;
  - link-targets shape;
  - page-copies for a page and a news post;
  - describe-image (mocked LLM; SiteImage path; src must be on the page; other languages written; superuser only).
- **JS harnesses:**
  - a pure `lib/content-model.js`: roles for a section's items (eyebrow detection), the section description, link parsing and building (`tel`, `mailto`, `wa.me`, internal, URL), the image quality verdict, other-language resolution from a copy, the formatted-text check;
  - `structure-panel` and `images-panel` driven with a fixture page (filters and counts, a drag computing `before`, hide-on-mobile toggling the class).
- **Browser (demo-ai-eval):**
  - the section form types into the page and saves;
  - a link picked as Page saves `/pt/…` and `/en/…`;
  - the heading level changes in both languages;
  - Describe the photo;
  - drag a section;
  - Images filters.
