# Media Collection Content Tab Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** When a section/container with `data-media-collection` is selected in the editor, show a thumbnail overview of all images with a button to open Process Images scoped to that section.

**Architecture:** Add `data-media-collection="type"` to component prompt examples (carousel, lightbox). In the sidebar Content tab, detect this attribute on the selected element or its ancestors, and render a thumbnail grid + Process Section Images button instead of the empty state.

**Tech Stack:** Vanilla JS (ES modules), CSS, Python (component prompt strings)

---

### Task 1: Update carousel component prompt

**Files:**
- Modify: `ai/utils/components/carousel.py`

**Step 1: Add `data-media-collection="carousel"` to all `.splide` div examples**

In `FULL_REFERENCE`, every `<div class="splide" ...>` element gets the attribute. There are 5 instances:

1. Basic Structure example (line ~28):
```html
<div class="splide" data-media-collection="carousel" data-splide='...'>
```

2. Image Gallery Carousel (line ~102):
```html
<div class="splide" data-media-collection="carousel" data-splide='...'>
```

3. Testimonials Carousel (line ~118):
```html
<div class="splide" data-media-collection="carousel" data-splide='...'>
```

4. Logo Strip (line ~134):
```html
<div class="splide" data-media-collection="carousel" data-splide='...'>
```

5. Hero with Fade Transition (line ~147):
```html
<div class="splide" data-media-collection="carousel" data-splide='...'>
```

Also add a row to the Required Class Names / Attributes table:

```
| `data-media-collection` | Outer wrapper `<div>` | Identifies the carousel as a media collection for the editor |
```

And add a bullet to the **Do** list:
```
- Always add `data-media-collection="carousel"` on the `.splide` element
```

**Step 2: Commit**

```bash
git add ai/utils/components/carousel.py
git commit -m "Add data-media-collection attribute to carousel component prompt"
```

---

### Task 2: Update lightbox component prompt

**Files:**
- Modify: `ai/utils/components/lightbox.py`

**Step 1: Add `data-media-collection="lightbox"` to the grid wrapper in all examples**

The attribute goes on the **parent container** that wraps all the `<a data-lightbox>` elements (typically a `<div class="grid ...">` or similar).

1. Basic Gallery example (line ~43):
```html
<div class="grid grid-cols-2 md:grid-cols-3 gap-4" data-media-collection="lightbox">
```

2. Team photos gallery (line ~63):
```html
<div class="grid grid-cols-3 gap-4" data-media-collection="lightbox">
```

3. Venue photos gallery (line ~74):
```html
<div class="grid grid-cols-3 gap-4 mt-8" data-media-collection="lightbox">
```

4. Hidden Items Pattern (line ~89):
```html
<div class="grid grid-cols-2 md:grid-cols-4 gap-4" data-media-collection="lightbox">
```

5. Combining with Splide (line ~119) — the `.splide` div already gets `data-media-collection="carousel"` from Task 1, so skip this one.

Also add a row to the Attributes Reference table:

```
| `data-media-collection` | Container `<div>` | No | Set to `"lightbox"` on the grid/container wrapping all `<a data-lightbox>` elements. Enables editor media overview. |
```

And add a bullet to the **Do** list:
```
- Add `data-media-collection="lightbox"` on the container wrapping all lightbox links
```

**Step 2: Commit**

```bash
git add ai/utils/components/lightbox.py
git commit -m "Add data-media-collection attribute to lightbox component prompt"
```

---

### Task 3: Add CSS for the media collection thumbnail grid

**Files:**
- Modify: `editor_v2/static/editor_v2/css/editor.css`

**Step 1: Add styles after the existing `.ev2-btn-change-img:hover` block (around line 925)**

```css
/* --- Media collection overview --- */

.ev2-media-collection-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.ev2-media-collection-header h4 {
  font-size: 13px;
  font-weight: 600;
  color: var(--ev2-text);
  margin: 0;
}

.ev2-media-collection-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 9999px;
  background: var(--ev2-primary-alpha);
  color: var(--ev2-primary);
  text-transform: capitalize;
}

.ev2-media-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
  margin-bottom: 12px;
}

.ev2-media-thumb {
  position: relative;
  aspect-ratio: 1;
  border-radius: var(--ev2-radius);
  overflow: hidden;
  border: 2px solid transparent;
  cursor: pointer;
  transition: border-color 0.15s;
}

.ev2-media-thumb:hover {
  border-color: var(--ev2-primary);
}

.ev2-media-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.ev2-media-thumb-index {
  position: absolute;
  top: 2px;
  left: 2px;
  font-size: 10px;
  font-weight: 700;
  background: rgba(0, 0, 0, 0.6);
  color: #fff;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}

.ev2-media-hint {
  font-size: 12px;
  color: var(--ev2-text-faint);
  margin-top: 8px;
}
```

**Step 2: Commit**

```bash
git add editor_v2/static/editor_v2/css/editor.css
git commit -m "Add CSS for media collection thumbnail grid in Content tab"
```

---

### Task 4: Add media collection rendering to sidebar Content tab

**Files:**
- Modify: `editor_v2/static/editor_v2/js/modules/sidebar.js:17-31`

**Step 1: Add the `findMediaCollection` helper function**

Add after the `esc()` function (after line 13), before the `renderContentTab` function:

```javascript
// --- Media collection detection ---

function findMediaCollection(el) {
    // Walk up from selected element to find data-media-collection
    let current = el;
    const section = el.closest('[data-section]');
    const boundary = section || el.closest('.editor-v2-content') || document.body;
    while (current && current !== boundary.parentElement) {
        if (current.hasAttribute && current.hasAttribute('data-media-collection')) {
            return current;
        }
        current = current.parentElement;
    }
    return null;
}
```

**Step 2: Add the `renderMediaCollection` function**

Add after `renderLinkFields` (after line 85):

```javascript
function renderMediaCollection(container, collectionEl) {
    const type = collectionEl.getAttribute('data-media-collection') || 'media';
    const section = collectionEl.closest('[data-section]');
    const sectionName = section ? section.getAttribute('data-section') : null;
    const imgs = Array.from(collectionEl.querySelectorAll('img'));

    let html = '<div class="ev2-media-collection-header">';
    html += `<h4>${imgs.length} image${imgs.length !== 1 ? 's' : ''}</h4>`;
    html += `<span class="ev2-media-collection-badge">${esc(type)}</span>`;
    html += '</div>';

    if (imgs.length > 0) {
        html += '<div class="ev2-media-grid">';
        imgs.forEach((img, i) => {
            const src = img.getAttribute('src') || '';
            const alt = img.getAttribute('alt') || '';
            const sel = getCssSelector(img) || '';
            html += `<div class="ev2-media-thumb" data-media-select="${esc(sel)}" title="${esc(alt || `Image ${i + 1}`)}">`;
            html += `<img src="${esc(src)}" alt="${esc(alt)}" />`;
            html += `<span class="ev2-media-thumb-index">${i + 1}</span>`;
            html += '</div>';
        });
        html += '</div>';
    }

    // Process Section Images button
    if (sectionName) {
        html += `<button type="button" class="ev2-btn-change-img" id="ev2-media-process-btn">Process Section Images</button>`;
    }

    html += '<p class="ev2-media-hint">Click a thumbnail to edit it individually</p>';

    container.innerHTML = html;

    // Bind thumbnail clicks — select the <img> element
    for (const thumb of container.querySelectorAll('.ev2-media-thumb')) {
        thumb.addEventListener('click', () => {
            const sel = thumb.dataset.mediaSelect;
            if (!sel) return;
            const imgEl = document.querySelector(sel);
            if (imgEl) {
                events.emit('selection:request', imgEl);
                imgEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        });
    }

    // Bind Process Section Images button
    const processBtn = container.querySelector('#ev2-media-process-btn');
    if (processBtn && sectionName) {
        processBtn.addEventListener('click', () => {
            events.emit('process-images:open', { section: sectionName });
        });
    }
}
```

**Step 3: Update `renderContentTab` to detect media collections**

Replace line 30:
```javascript
    else c.innerHTML = '<p class="ev2-placeholder ev2-empty-state">Select a text element to edit content</p>';
```

With:
```javascript
    else {
        const collectionEl = findMediaCollection(selectedEl);
        if (collectionEl) renderMediaCollection(c, collectionEl);
        else c.innerHTML = '<p class="ev2-placeholder ev2-empty-state">Select a text element to edit content</p>';
    }
```

**Step 4: Commit**

```bash
git add editor_v2/static/editor_v2/js/modules/sidebar.js
git commit -m "Add media collection overview to Content tab when data-media-collection detected"
```

---

### Task 5: Manual testing

**Step 1: Start dev server**

```bash
python manage.py runserver 8000
```

**Step 2: Test with existing page**

Open a page in the editor (`?edit=v2`) that has a gallery/carousel section. Since existing pages won't have `data-media-collection` yet, the behavior should be unchanged (empty state message).

**Step 3: Test with the attribute injected via browser devtools**

1. In browser devtools, find a `.splide` container or lightbox grid
2. Add `data-media-collection="carousel"` (or `"lightbox"`) to it
3. Click the container or any non-image element inside it
4. Verify the Content tab shows the thumbnail grid
5. Click a thumbnail — verify it selects the `<img>` and switches to image editing fields
6. Click back on the container — verify the grid reappears
7. Click "Process Section Images" — verify the Process Images modal opens scoped to that section

**Step 4: Test AI generation**

Generate or refine a page that uses a carousel or lightbox gallery. Verify the generated HTML includes `data-media-collection` on the container.

**Step 5: Commit (if any fixes needed)**

---

### Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Update carousel prompt | `ai/utils/components/carousel.py` |
| 2 | Update lightbox prompt | `ai/utils/components/lightbox.py` |
| 3 | Add CSS for thumbnail grid | `editor_v2/static/editor_v2/css/editor.css` |
| 4 | Add rendering logic to sidebar | `editor_v2/static/editor_v2/js/modules/sidebar.js` |
| 5 | Manual testing | — |
