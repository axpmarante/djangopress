# News Form Improvements — Design

## Goal

Improve the news app backoffice form with language tabs for i18n fields and modal-based image selection (reusing existing `image_selection_modals.html` partial). This form serves as the reference pattern for future decoupled apps.

## Architecture

Template-only + JS changes. No changes to Django form class, views, or models. The form still submits the same fields in the same format (JSON for i18n, IDs for images).

## Design

### 1. Language Tabs (Hybrid)

Tab bar at the top of the form showing all configured site languages (e.g. PT | EN). Switching tabs updates ALL i18n fields at once. Non-i18n fields stay visible always.

**Behavior:**
- On load: parse JSON from each i18n field, split into per-language textareas (one per lang, only active lang visible)
- On tab switch: hide current language inputs, show target language inputs
- On submit: JS reassembles per-language values back into JSON before POST
- Original JSON field becomes hidden, populated on submit

**i18n fields affected:** title, slug, excerpt, html_content, meta_description

**Non-i18n fields (always visible):** category, featured_image, gallery_images, is_published, published_date

### 2. Featured Image — Modal Picker

Replace `<select>` dropdown with visual picker:
- Thumbnail preview of current image (or placeholder with "Click to select")
- "Select Image" button → opens `#featuredImageModal` from `image_selection_modals.html`
- "Upload" button → opens `#featuredUploadModal`
- "Remove" link to clear selection
- Hidden `<input>` for SiteImage ID

### 3. Gallery Images — Modal Picker

Replace inline checkbox grid with:
- Horizontal grid of selected gallery thumbnails with per-image remove button
- "Add Images" button → opens `#galleryImageModal`
- "Upload" button → opens `#uploadImageModal`
- Hidden checkboxes populated by JS on modal confirm

### 4. Reusable Parts

Include existing partials:
- `backoffice/partials/image_selection_modals.html` — 4 modals (featured select, featured upload, gallery select, gallery upload)
- `backoffice/js/image_selection.js` — modal logic + upload handling

Build clean in news form first. Extract shared patterns (language tabs JS, form layout) into partials when second app needs them.

## Files to Change

- `backoffice/templates/backoffice/news_form.html` — template rewrite (language tabs, image modals, gallery display)
- No changes to: `news/forms.py`, `news/views.py`, `news/models.py`
