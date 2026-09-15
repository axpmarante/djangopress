# Editor v2 — Image Discovery (Solution A) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new "Images" tab to the editor v2 sidebar that lists every editable `<img>` on the page, grouped by section, so the user can discover and edit images that the click-and-edit flow can't reach (background images, Splide clones, marquee duplicates).

**Scope:** Solution A only — Solutions B (in-page badges) and C (slide manager) from the design doc are explicitly out of scope.

**Architecture:**
- New self-contained module `static/editor_v2/js/modules/images-panel.js` that mirrors the `ai-panel.js` pattern: it listens for `sidebar:tab-changed` and renders into the shared `#ev2-tab-content` container when its own tab is active.
- One sidebar button added to `partials/editor.html`. One `init()` call added to `editor.js`. No changes to `sidebar.js` (its hardcoded `renderActiveTab()` switch simply won't match `'images'`, leaving the panel module's render in place — same contract as `ai-panel.js`).
- Discovery filter is a pure function that walks `[data-section] img` and drops `aria-hidden="true"`, Splide clones, and `[data-editor-skip="true"]`. Within each section, images are deduped by `src` (first wins, count of dupes shown as `× N`).
- Click on a thumbnail emits `selection:request` (handled by `selection.js`), scrolls the target into view, briefly flashes the `<img>`, then emits `image-picker:open` (handled by `image-picker.js`). Both events already exist — no new bus contracts.
- The `aria-hidden="true"` convention for decorative/clone duplicates becomes part of the documented HTML contract in the `djangopress-html-reference` skill.

**Tech Stack:** Vanilla JS (ES modules), CSS, Markdown (skill doc).

**Test reference:** Cuíca child project at `/Users/antoniomarante/Documents/DjangoSites/cuica`, page id=3 (home, PT). Live: https://web-production-0107c.up.railway.app/.

Run locally with:

```bash
cd /Users/antoniomarante/Documents/DjangoSites/cuica
pip install -e ../djangopress
python manage.py runserver 8000
# Open http://localhost:8000/pt/?edit=v2 logged in as superuser
```

Expected discovery counts on the Cuíca PT home (page id=3):

| Section | Visible `<img>` total | After filter | After section dedup |
|---|---|---|---|
| hero | 2 (+ Splide clones) | 2 | 2 |
| dois-mundos | 2 | 2 | 2 |
| cuica-praia | 1 | 1 | 1 |
| sabores | 4 | 4 | 4 |
| terrace-lounge | 50 | 26 (24 `aria-hidden` dropped) | 26 |
| **Total** | — | **35** | **35** |

---

### Task 1: Document the `aria-hidden="true"` convention in the html-reference skill

**Files:**
- Modify: `src/djangopress/skills/djangopress-html-reference/SKILL.md`

**Why first:** Solution A's discovery filter relies on this contract. Documenting it before the code lands means future generated/refined HTML will be correctly tagged, and the engineer applying the filter has a doc to point reviewers at.

- [ ] **Step 1: Add the convention right after the existing "pointer-events trap" section** (around line 41 — find the line that ends with `Otherwise leave it clickable so its children can be reached.` and insert after the blank line that follows it):

````markdown
**Decorative & duplicate images — `aria-hidden="true"`:** Mark any `<img>` that is purely decorative or a visual duplicate of another image with `aria-hidden="true"` and an empty `alt=""`. The editor v2's "Images" sidebar tab uses this attribute to filter such images out of the discoverable list, so the user only sees one editable entry per logical image.

The two patterns that require this:

1. **Marquee / scrolling-row duplicates** — when CSS `transform: translateX(-50%)` needs the image set duplicated in the DOM to produce a seamless loop. The duplicate copies are decorative; the originals are the source of truth.

   ```html
   <div class="marquee-track">
     <!-- Originals: editable -->
     <img src="/media/photo-1.jpg" alt="Praia ao pôr do sol" />
     <img src="/media/photo-2.jpg" alt="Terrace ao entardecer" />
     <!-- Duplicates: decorative, NOT editable -->
     <img src="/media/photo-1.jpg" alt="" aria-hidden="true" />
     <img src="/media/photo-2.jpg" alt="" aria-hidden="true" />
   </div>
   ```

2. **Pure decoration** — images used as visual texture (corner accents, ornamental dividers) that have no semantic content the user would want to swap.

Splide-injected clones (`.splide__slide--clone`) are filtered automatically by the editor without needing this attribute.

You can also opt an `<img>` (or any wrapper) out of the editor with `data-editor-skip="true"` if neither `aria-hidden` nor a Splide-clone class fits the situation.
````

- [ ] **Step 2: Verify the markdown renders cleanly**

```bash
grep -n "Decorative & duplicate images" /Users/antoniomarante/Documents/DjangoSites/djangopress/src/djangopress/skills/djangopress-html-reference/SKILL.md
```

Expected: one match.

- [ ] **Step 3: Commit**

```bash
git add src/djangopress/skills/djangopress-html-reference/SKILL.md
git commit -m "Document aria-hidden convention for decorative/duplicate images"
```

---

### Task 2: Add the Images tab button to the sidebar template

**Files:**
- Modify: `src/djangopress/editor_v2/templates/editor_v2/partials/editor.html` (around line 96-102, between the Structure tab and the AI/Chat tab)

- [ ] **Step 1: Insert a new tab button after the Structure tab and before the `{% if user.is_superuser %}` block**

Locate this block in the file (around lines 97-102):

```html
    <button class="ev2-tab" data-tab="structure">
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <path d="M2 2h5v5H2zM9 2h5v5H9zM2 9h5v5H2zM9 9h5v5H9z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" fill="none"/>
      </svg>
      <span>Structure</span>
    </button>
    {% if user.is_superuser %}
```

Insert directly after the Structure `</button>` (and before `{% if user.is_superuser %}`):

```html
    <button class="ev2-tab" data-tab="images">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
        <circle cx="8.5" cy="8.5" r="1.5"/>
        <polyline points="21 15 16 10 5 21"/>
      </svg>
      <span>Images</span>
    </button>
```

(The icon — frame + sun + mountain polyline — is the same vocabulary already used for the Process Images topbar button at lines 42-48 of the same file, so the visual language stays consistent.)

- [ ] **Step 2: Reload the editor in the browser and confirm the tab appears**

The Images tab should appear between Structure and Chat (or at the end if user is not a superuser). Clicking it does nothing yet — that's expected; the panel module is implemented in Task 3.

- [ ] **Step 3: Commit**

```bash
git add src/djangopress/editor_v2/templates/editor_v2/partials/editor.html
git commit -m "Add Images tab button to editor v2 sidebar"
```

---

### Task 3: Create the images-panel module skeleton and register it

**Files:**
- Create: `src/djangopress/editor_v2/static/editor_v2/js/modules/images-panel.js`
- Modify: `src/djangopress/editor_v2/static/editor_v2/js/editor.js`

- [ ] **Step 1: Create the new module with empty-state rendering only**

Write the full file at `src/djangopress/editor_v2/static/editor_v2/js/modules/images-panel.js`:

```js
/**
 * Images Panel — sidebar tab listing every editable image on the page,
 * grouped by section. Solves the "find the image you can't click on"
 * problem for image-as-background, Splide clones, and marquee duplicates.
 *
 * Mirrors the ai-panel.js pattern: takes over #ev2-tab-content when its
 * tab is active, listens for sidebar:tab-changed.
 */
import { events } from '../lib/events.js';
import { $, $$, getContentWrapper, getCssSelector } from '../lib/dom.js';

let activeTab = null;
let unsubs = [];

function esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function render() {
    const container = $('#ev2-tab-content');
    if (!container) return;

    container.innerHTML = '<p class="ev2-placeholder ev2-empty-state">No editable images on this page.</p>';
}

function onTabChanged(tab) {
    activeTab = tab;
    if (tab === 'images') render();
}

export function init() {
    unsubs.push(events.on('sidebar:tab-changed', onTabChanged));
}

export function destroy() {
    unsubs.forEach(fn => fn());
    unsubs = [];
    activeTab = null;
}
```

- [ ] **Step 2: Wire the module into the editor entrypoint**

In `src/djangopress/editor_v2/static/editor_v2/js/editor.js`:

a) Add the import next to the other module imports (around line 15, alongside `imagePicker`):

```js
import * as imagesPanel  from './modules/images-panel.js';
```

b) Add `imagesPanel.init();` inside the `DOMContentLoaded` handler, right after `imagePicker.init();` (around line 30):

```js
    imagePicker.init();
    imagesPanel.init();
```

- [ ] **Step 3: Reload the editor and click the Images tab**

Expected: the tab content area shows "No editable images on this page." even on Cuíca (no rendering logic yet — that's the next task).

- [ ] **Step 4: Commit**

```bash
git add src/djangopress/editor_v2/static/editor_v2/js/modules/images-panel.js \
        src/djangopress/editor_v2/static/editor_v2/js/editor.js
git commit -m "Add images-panel module skeleton with empty state"
```

---

### Task 4: Implement discovery, section grouping, and dedup

**Files:**
- Modify: `src/djangopress/editor_v2/static/editor_v2/js/modules/images-panel.js`

- [ ] **Step 1: Replace the placeholder `render()` with discovery + console output**

Replace the existing `render()` and add a `discoverImages()` helper. The full updated file should read:

```js
/**
 * Images Panel — sidebar tab listing every editable image on the page,
 * grouped by section. Solves the "find the image you can't click on"
 * problem for image-as-background, Splide clones, and marquee duplicates.
 *
 * Mirrors the ai-panel.js pattern: takes over #ev2-tab-content when its
 * tab is active, listens for sidebar:tab-changed.
 */
import { events } from '../lib/events.js';
import { $, $$, getContentWrapper, getCssSelector } from '../lib/dom.js';

let activeTab = null;
let unsubs = [];

function esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/**
 * Walk all sections and return the editable images, grouped by section
 * in DOM order. Within each section, dedup by src URL — first occurrence
 * wins, and the count of duplicates is attached as `dupCount` (>= 1).
 *
 * Filters applied:
 *   1. Only <img> inside [data-section]
 *   2. Drop [aria-hidden="true"] (and any descendant of an aria-hidden ancestor)
 *   3. Drop descendants of .splide__slide--clone (Splide runtime clones)
 *   4. Drop descendants of [data-editor-skip="true"] (explicit opt-out)
 */
function discoverImages() {
    const wrapper = getContentWrapper();
    if (!wrapper) return [];

    const sections = $$('[data-section]', wrapper);
    const groups = [];

    for (const section of sections) {
        const sectionName = section.getAttribute('data-section') || '';
        const imgs = $$('img', section).filter(img => {
            if (img.getAttribute('aria-hidden') === 'true') return false;
            if (img.closest('.splide__slide--clone')) return false;
            if (img.closest('[data-editor-skip="true"]')) return false;
            // Defensive: ancestor marked aria-hidden makes the whole subtree decorative
            if (img.parentElement && img.parentElement.closest('[aria-hidden="true"]')) return false;
            return true;
        });

        // Dedup by src within the section
        const seen = new Map(); // src -> entry
        for (const img of imgs) {
            const src = img.getAttribute('src') || '';
            const key = src.trim();
            if (!key) continue;
            const existing = seen.get(key);
            if (existing) {
                existing.dupCount += 1;
            } else {
                seen.set(key, {
                    img,
                    src,
                    alt: img.getAttribute('alt') || '',
                    dupCount: 1,
                });
            }
        }

        const entries = Array.from(seen.values());
        if (entries.length > 0) {
            groups.push({ section: sectionName, entries });
        }
    }

    return groups;
}

function render() {
    const container = $('#ev2-tab-content');
    if (!container) return;

    const groups = discoverImages();
    const total = groups.reduce((acc, g) => acc + g.entries.length, 0);

    if (total === 0) {
        container.innerHTML = '<p class="ev2-placeholder ev2-empty-state">No editable images on this page.</p>';
        return;
    }

    // Temporary render — Task 5 replaces this with thumbnail UI.
    let html = '<pre style="font-family:var(--ev2-font-mono);font-size:11px;white-space:pre-wrap;">';
    for (const group of groups) {
        html += `\n${esc(group.section)} (${group.entries.length})`;
        for (const entry of group.entries) {
            const dup = entry.dupCount > 1 ? ` × ${entry.dupCount}` : '';
            html += `\n  ${esc(entry.src)}${dup}`;
        }
    }
    html += '\n</pre>';
    container.innerHTML = html;

    console.log('[images-panel] discovered', { total, groups });
}

function onTabChanged(tab) {
    activeTab = tab;
    if (tab === 'images') render();
}

export function init() {
    unsubs.push(events.on('sidebar:tab-changed', onTabChanged));
}

export function destroy() {
    unsubs.forEach(fn => fn());
    unsubs = [];
    activeTab = null;
}
```

- [ ] **Step 2: Verify discovery counts on Cuíca**

Run the Cuíca dev server (see top of plan), open `http://localhost:8000/pt/?edit=v2`, click the Images tab.

Expected (from the table in the plan header):

```
hero (2)
  https://.../hero-praia-dia.jpg
  https://.../hero-terrace-sunset.jpg
dois-mundos (2)
  ...
cuica-praia (1)
  ...
sabores (4)
  ...
terrace-lounge (26)
  ...
```

Total entry count must be **35**. If it's 59, the `aria-hidden` filter isn't biting — open one of the duplicate `<img>` tags in DevTools and confirm the attribute is set on the marquee duplicates. If it's missing, that's a Cuíca content issue, not an editor bug — note it and continue (the filter logic is still correct).

- [ ] **Step 3: Commit**

```bash
git add src/djangopress/editor_v2/static/editor_v2/js/modules/images-panel.js
git commit -m "Implement image discovery, section grouping, and src dedup"
```

---

### Task 5: Render thumbnail UI + add CSS

**Files:**
- Modify: `src/djangopress/editor_v2/static/editor_v2/js/modules/images-panel.js`
- Modify: `src/djangopress/editor_v2/static/editor_v2/css/editor.css`

- [ ] **Step 1: Replace the temporary `<pre>` rendering with thumbnail UI**

In `images-panel.js`, replace the body of `render()` (everything after the `if (total === 0)` early return) with:

```js
    let html = '<div class="ev2-images-panel">';
    for (const group of groups) {
        html += `<div class="ev2-images-panel-group">`;
        html += `<div class="ev2-images-panel-header">`;
        html += `<span class="ev2-images-panel-section">${esc(group.section)}</span>`;
        html += `<span class="ev2-images-panel-count">${group.entries.length}</span>`;
        html += `</div>`;
        html += `<div class="ev2-images-panel-grid">`;
        for (let i = 0; i < group.entries.length; i++) {
            const entry = group.entries[i];
            const sel = getCssSelector(entry.img) || '';
            if (!sel) continue;
            const filename = (entry.src.split('/').pop() || '').split('?')[0];
            const dup = entry.dupCount > 1 ? `<span class="ev2-images-panel-dup">×${entry.dupCount}</span>` : '';
            const title = entry.alt || filename || `Image ${i + 1}`;
            html += `<button type="button" class="ev2-images-panel-thumb" data-img-selector="${esc(sel)}" title="${esc(title)}">`;
            html += `<img src="${esc(entry.src)}" alt="" loading="lazy" />`;
            html += dup;
            html += `<span class="ev2-images-panel-thumb-label">${esc(filename)}</span>`;
            html += `</button>`;
        }
        html += `</div></div>`;
    }
    html += '</div>';

    container.innerHTML = html;

    // Click handlers wired in Task 6 — leaving the data-img-selector attribute in place.
```

(The buttons render but don't act on click yet — Task 6 wires the handler.)

- [ ] **Step 2: Add styles to editor.css**

Append to the end of `src/djangopress/editor_v2/static/editor_v2/css/editor.css`:

```css
/* --------------------------------------------------------------------------
   Images Panel (sidebar tab — Solution A)
   -------------------------------------------------------------------------- */
.ev2-images-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.ev2-images-panel-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ev2-images-panel-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--ev2-border);
}

.ev2-images-panel-section {
  font-size: 13px;
  font-weight: 600;
  color: var(--ev2-text);
  font-family: var(--ev2-font-mono);
}

.ev2-images-panel-count {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 9999px;
  background: var(--ev2-primary-alpha);
  color: var(--ev2-primary);
}

.ev2-images-panel-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
}

.ev2-images-panel-thumb {
  position: relative;
  display: flex;
  flex-direction: column;
  padding: 0;
  border: 2px solid transparent;
  border-radius: var(--ev2-radius);
  background: transparent;
  cursor: pointer;
  overflow: hidden;
  transition: border-color 0.15s;
}

.ev2-images-panel-thumb:hover {
  border-color: var(--ev2-primary);
}

.ev2-images-panel-thumb img {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  display: block;
}

.ev2-images-panel-thumb-label {
  font-size: 10px;
  font-family: var(--ev2-font-mono);
  color: var(--ev2-text-faint);
  padding: 2px 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: left;
}

.ev2-images-panel-dup {
  position: absolute;
  top: 2px;
  right: 2px;
  font-size: 10px;
  font-weight: 700;
  background: rgba(0, 0, 0, 0.7);
  color: #fff;
  padding: 1px 5px;
  border-radius: 9999px;
  line-height: 1.2;
}

/* Brief flash highlight applied to the target <img> when the user clicks
   a thumbnail — see images-panel.js click handler. */
@keyframes ev2-image-flash {
  0%   { outline: 3px solid var(--ev2-primary); outline-offset: 4px; }
  100% { outline: 3px solid transparent;        outline-offset: 4px; }
}

.ev2-image-flash {
  animation: ev2-image-flash 1.2s ease-out;
}

/* Push scroll target below the editor topbar (matches existing scroll-padding) */
[data-section] img {
  scroll-margin-top: 5rem;
}
```

- [ ] **Step 3: Reload the editor and confirm the thumbnails render**

Click the Images tab on Cuíca. Expected: 5 section headers (`hero`, `dois-mundos`, `cuica-praia`, `sabores`, `terrace-lounge`) each with a count badge and a 3-column grid of thumbnails below. No duplicates within any section. The `terrace-lounge` group shows 26 thumbs.

Hover a thumb → primary-color border. Click does nothing yet (Task 6).

- [ ] **Step 4: Commit**

```bash
git add src/djangopress/editor_v2/static/editor_v2/js/modules/images-panel.js \
        src/djangopress/editor_v2/static/editor_v2/css/editor.css
git commit -m "Render images panel thumbnails grouped by section"
```

---

### Task 6: Wire click handler — select, scroll, flash, open picker

**Files:**
- Modify: `src/djangopress/editor_v2/static/editor_v2/js/modules/images-panel.js`

- [ ] **Step 1: Add the click handler at the end of `render()` (after `container.innerHTML = html;` and replacing the placeholder comment)**

```js
    container.querySelectorAll('.ev2-images-panel-thumb').forEach(btn => {
        btn.addEventListener('click', () => onThumbClick(btn.dataset.imgSelector));
    });
```

Then add the `onThumbClick` function above `render()` (or below — placement doesn't matter, but keep it grouped with the other panel logic):

```js
function onThumbClick(selector) {
    if (!selector) return;
    const img = document.querySelector(selector);
    if (!img) return;

    // Select the image (selection.js handles the highlight + sidebar sync).
    events.emit('selection:request', img);

    // Scroll into view (scroll-margin-top in CSS pushes it below the topbar).
    img.scrollIntoView({ behavior: 'smooth', block: 'center' });

    // Brief flash so the user can see which image they just targeted.
    img.classList.remove('ev2-image-flash');
    // Force reflow so the animation restarts on repeat clicks
    void img.offsetWidth;
    img.classList.add('ev2-image-flash');
    setTimeout(() => img.classList.remove('ev2-image-flash'), 1300);

    // Open the existing image-picker modal targeted at this <img>.
    events.emit('image-picker:open');
}
```

- [ ] **Step 2: Confirm the click flow on Cuíca**

For each section, click one thumbnail:

- `hero` first thumb → page scrolls to hero, image flashes, image-picker modal opens. Cancel.
- `dois-mundos` first thumb → page scrolls to the cards section, the `<img>` underneath the gradient/content layers flashes (this is the failure mode #1 — proves Solution A solves it). Modal opens. Cancel.
- `terrace-lounge` first thumb → page scrolls to the marquee, an original `<img>` flashes (not a duplicate). Modal opens. Cancel.

If clicking a thumbnail does NOT open the modal, check the browser console — most likely the `selection:request → image-picker:open` order races. Both listeners are synchronous; `selection.js` calls `select(img)` which calls `events.emit('selection:changed', img)`, which `image-picker.js` records as `currentEl`. So `image-picker:open` fires next on the same tick and reads the right element. If you see "image-picker: no current element", insert a `await Promise.resolve()` between the two emits — but verify first.

- [ ] **Step 3: Re-render the panel after a successful image swap**

When the user picks a new image from the modal, `image-picker.js` emits `change:attribute` with `attribute: 'src'` and `tagName: 'img'`. Subscribe to that and re-render so the thumbnail updates.

Add inside `init()`, before the existing `unsubs.push(...)` line:

```js
    unsubs.push(events.on('change:attribute', (data) => {
        if (activeTab === 'images' && data && data.attribute === 'src' && data.tagName === 'img') {
            render();
        }
    }));
```

- [ ] **Step 4: Verify swap → rerender**

Open Images tab → click a thumbnail → modal opens → pick a different image → modal closes. The thumbnail in the panel should update to the new image. (The user is still on the Images tab, so `render()` runs.)

- [ ] **Step 5: Commit**

```bash
git add src/djangopress/editor_v2/static/editor_v2/js/modules/images-panel.js
git commit -m "Wire images panel thumbnail clicks to picker + flash highlight"
```

---

### Task 7: Final smoke test against the design doc's acceptance criteria

**Files:** none (verification only)

- [ ] **Step 1: Run the acceptance checklist on Cuíca**

From `docs/plans/2026-05-07-editor-v2-image-discovery-design.md` (last section):

- [ ] Opening editor v2 on Cuíca's home page shows the new "Images" sidebar tab.
- [ ] The tab lists **35** image entries grouped into 5 sections (hero: 2, dois-mundos: 2, cuica-praia: 1, sabores: 4, terrace-lounge: 26 unique).
- [ ] The 24 `aria-hidden` marquee duplicates are NOT listed.
- [ ] Splide clones are NOT listed as separate entries.
- [ ] Clicking any thumbnail opens the image-picker UI targeted at the right `<img>`, scrolls the page, and briefly flashes the image.
- [ ] Pages with zero editable images render an empty state ("No editable images on this page."). Test by navigating to a child page with no `<img>` (or temporarily commenting out images in a test page) and reloading the editor.
- [ ] Existing click-on-image behavior continues to work where it works today (no regression). Quick check: `sabores` cards — click an image directly on the page; the existing flow opens the picker unchanged.

- [ ] **Step 2: Verify no regressions in the other sidebar tabs**

- Click Content, Design, Structure, Chat in turn. Each tab should render its own content as before. Switching back to Images should re-discover and render fresh.

- [ ] **Step 3: If something fails, file the gap as a follow-up — do NOT silently work around it**

Solution A has a tightly-specified scope. If acceptance fails, add a note to the design doc's "Future work" section explaining what didn't behave as expected, rather than expanding scope into Solution B/C territory.

- [ ] **Step 4: Final commit (only if any docs were touched during smoke test)**

If acceptance is clean and nothing else changed, no commit needed — Task 6 was the last code change.

---

## Summary of files touched

| File | Action |
|---|---|
| `src/djangopress/skills/djangopress-html-reference/SKILL.md` | Modify (Task 1) |
| `src/djangopress/editor_v2/templates/editor_v2/partials/editor.html` | Modify (Task 2) |
| `src/djangopress/editor_v2/static/editor_v2/js/modules/images-panel.js` | Create (Tasks 3, 4, 5, 6) |
| `src/djangopress/editor_v2/static/editor_v2/js/editor.js` | Modify (Task 3) |
| `src/djangopress/editor_v2/static/editor_v2/css/editor.css` | Modify (Task 5) |

No changes to `selection.js`, `sidebar.js`, or `image-picker.js`. No HTML migrations. No changes outside the `djangopress` package — Cuíca is untouched.
