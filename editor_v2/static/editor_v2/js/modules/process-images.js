/**
 * Process Images Module — modal for scanning, AI-suggesting, and processing page images.
 *
 * Reuses existing API endpoints:
 *   POST /ai/api/analyze-page-images/
 *   POST /ai/api/process-page-images/
 *   POST /ai/api/search-unsplash/
 *   GET  /editor-v2/api/media-library/
 */
import { events } from '../lib/events.js';
import { api } from '../lib/api.js';

const config = () => window.EDITOR_CONFIG || {};

let modal, body, grid, emptyEl, statusEl, suggestBtn, processBtn, scopeBadge, closeBtn, backdrop;
let images = [];
let libraryImages = [];
let scope = null; // null = full page, or section name

function esc(s) {
  return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ── Init ──

export function init() {
  modal = document.getElementById('ev2-process-images-modal');
  if (!modal) return;

  body = document.getElementById('ev2-pimg-body');
  grid = document.getElementById('ev2-pimg-grid');
  emptyEl = document.getElementById('ev2-pimg-empty');
  statusEl = document.getElementById('ev2-pimg-status');
  suggestBtn = document.getElementById('ev2-pimg-suggest');
  processBtn = document.getElementById('ev2-pimg-process');
  scopeBadge = document.getElementById('ev2-pimg-scope-badge');
  closeBtn = document.getElementById('ev2-pimg-close');
  backdrop = modal.querySelector('.ev2-process-images-backdrop');

  closeBtn.addEventListener('click', close);
  backdrop.addEventListener('click', close);
  suggestBtn.addEventListener('click', aiSuggest);
  processBtn.addEventListener('click', processSelected);

  // Top bar button
  const topbarBtn = document.getElementById('ev2-pimg-topbar-btn');
  if (topbarBtn) topbarBtn.addEventListener('click', () => open({}));

  // Sidebar footer button
  const sidebarBtn = document.getElementById('ev2-pimg-sidebar-btn');
  if (sidebarBtn) sidebarBtn.addEventListener('click', () => open({}));

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && isOpen()) close();
  });

  events.on('process-images:open', open);
}

function isOpen() {
  return modal && !modal.classList.contains('hidden');
}

// ── Open / Close ──

async function open(data = {}) {
  scope = data.section || null;

  // Show scope badge
  if (scope) {
    scopeBadge.textContent = scope;
    scopeBadge.style.display = '';
  } else {
    scopeBadge.style.display = 'none';
  }

  setStatus('Scanning images...');
  modal.classList.remove('hidden');

  scanImages();

  if (images.length === 0) {
    emptyEl.style.display = '';
    grid.style.display = 'none';
    setStatus('');
    updateProcessBtn();
    return;
  }

  emptyEl.style.display = 'none';
  grid.style.display = '';

  // Fetch library before rendering so dropdown has options
  await fetchLibrary();

  renderCards();
  setStatus(`${images.length} image(s) found`);
  updateProcessBtn();
}

function close() {
  modal.classList.add('hidden');
  images = [];
  grid.innerHTML = '';
  setStatus('');
}

// ── Scan Images ──

function scanImages() {
  images = [];
  const contentArea = document.querySelector('.editor-v2-content main') ||
                      document.querySelector('.editor-v2-content') ||
                      document.querySelector('main');
  if (!contentArea) return;

  let container;
  if (scope) {
    container = contentArea.querySelector(`[data-section="${scope}"]`);
    if (!container) return;
  } else {
    container = contentArea;
  }

  const imgEls = container.querySelectorAll('img');
  imgEls.forEach((img, i) => {
    images.push({
      index: i,
      src: img.getAttribute('src') || '',
      alt: img.getAttribute('alt') || '',
      name: img.getAttribute('data-image-name') || img.getAttribute('alt') || `image-${i}`,
      prompt: img.getAttribute('data-image-prompt') || '',
      action: 'generate',
      aspect_ratio: '16:9',
      selected: true,
      library_image_id: null,
      unsplash_photo_id: null,
      unsplash_url: null,
      photographer: null,
      library_suggestions: [],
      unsplash_results: [],
    });
  });
}

// ── Fetch Library ──

async function fetchLibrary() {
  try {
    const data = await api.get('/media-library/');
    libraryImages = data.images || data || [];
  } catch (err) {
    console.warn('Failed to fetch media library:', err);
    libraryImages = [];
  }
}

// ── Render Cards ──

function renderCards() {
  grid.innerHTML = '';
  const unsplashEnabled = config().unsplashEnabled;

  images.forEach((img, idx) => {
    const card = document.createElement('div');
    card.className = 'ev2-pimg-card';
    card.dataset.idx = idx;

    // Build source radio options
    let radioHtml = `
      <label><input type="radio" name="pimg-action-${idx}" value="generate" ${img.action === 'generate' ? 'checked' : ''}><span>Generate</span></label>
      <label><input type="radio" name="pimg-action-${idx}" value="library" ${img.action === 'library' ? 'checked' : ''}><span>Library</span></label>`;
    if (unsplashEnabled) {
      radioHtml += `<label><input type="radio" name="pimg-action-${idx}" value="unsplash" ${img.action === 'unsplash' ? 'checked' : ''}><span>Unsplash</span></label>`;
    }

    // Library search query (default from prompt/alt/name)
    const libQuery = img.library_search_query || '';

    card.innerHTML = `
      <div class="ev2-pimg-card-header">
        <input type="checkbox" ${img.selected ? 'checked' : ''} data-role="select" />
        <span class="ev2-pimg-card-name" title="${esc(img.name)}">${esc(img.name)}</span>
      </div>
      <img class="ev2-pimg-thumb" src="${esc(img.src)}" alt="${esc(img.alt)}" onerror="this.style.display='none'" />
      <textarea class="ev2-pimg-prompt" placeholder="Image generation prompt..." data-role="prompt">${esc(img.prompt)}</textarea>
      <div class="ev2-pimg-row">
        <select class="ev2-pimg-aspect-select" data-role="aspect">
          <option value="1:1" ${img.aspect_ratio === '1:1' ? 'selected' : ''}>1:1</option>
          <option value="16:9" ${img.aspect_ratio === '16:9' ? 'selected' : ''}>16:9</option>
          <option value="4:3" ${img.aspect_ratio === '4:3' ? 'selected' : ''}>4:3</option>
          <option value="3:2" ${img.aspect_ratio === '3:2' ? 'selected' : ''}>3:2</option>
          <option value="9:16" ${img.aspect_ratio === '9:16' ? 'selected' : ''}>9:16</option>
        </select>
        <div class="ev2-pimg-radio-group">${radioHtml}</div>
      </div>
      <div class="ev2-pimg-sub-panel" data-role="library-panel" style="display:${img.action === 'library' ? '' : 'none'}">
        <div class="ev2-pimg-unsplash-panel">
          <div class="ev2-pimg-unsplash-search-row">
            <input class="ev2-pimg-unsplash-input" type="text" placeholder="Filter library..." value="${esc(libQuery)}" data-role="library-query" />
          </div>
          <div class="ev2-pimg-library-grid" data-role="library-grid"></div>
        </div>
      </div>
      <div class="ev2-pimg-sub-panel" data-role="unsplash-panel" style="display:${img.action === 'unsplash' ? '' : 'none'}">
        <div class="ev2-pimg-unsplash-panel">
          <div class="ev2-pimg-unsplash-search-row">
            <input class="ev2-pimg-unsplash-input" type="text" placeholder="Search Unsplash..." value="${esc(img.prompt || img.alt || img.name)}" data-role="unsplash-query" />
            <button class="ev2-pimg-unsplash-search-btn" data-role="unsplash-search">Search</button>
          </div>
          <div class="ev2-pimg-unsplash-grid" data-role="unsplash-grid"></div>
        </div>
      </div>
    `;

    // Bind events
    bindCardEvents(card, idx);
    grid.appendChild(card);

    // Render existing unsplash results if any
    if (img.unsplash_results && img.unsplash_results.length) {
      renderUnsplashResults(card, idx);
    }
  });
}

function bindCardEvents(card, idx) {
  // Checkbox
  card.querySelector('[data-role="select"]').addEventListener('change', (e) => {
    images[idx].selected = e.target.checked;
    updateProcessBtn();
  });

  // Prompt
  card.querySelector('[data-role="prompt"]').addEventListener('input', (e) => {
    images[idx].prompt = e.target.value;
  });

  // Aspect ratio
  card.querySelector('[data-role="aspect"]').addEventListener('change', (e) => {
    images[idx].aspect_ratio = e.target.value;
  });

  // Radio buttons for action
  card.querySelectorAll(`input[name="pimg-action-${idx}"]`).forEach(radio => {
    radio.addEventListener('change', (e) => {
      images[idx].action = e.target.value;
      const libPanel = card.querySelector('[data-role="library-panel"]');
      const unsPanel = card.querySelector('[data-role="unsplash-panel"]');
      libPanel.style.display = e.target.value === 'library' ? '' : 'none';
      unsPanel.style.display = e.target.value === 'unsplash' ? '' : 'none';
    });
  });

  // Library thumbnail grid
  const libGridEl = card.querySelector('[data-role="library-grid"]');
  const libQueryInput = card.querySelector('[data-role="library-query"]');
  if (libGridEl) {
    renderLibraryGrid(libGridEl, idx, '');
    if (libQueryInput) {
      libQueryInput.addEventListener('input', () => {
        renderLibraryGrid(libGridEl, idx, libQueryInput.value.trim().toLowerCase());
      });
    }
  }

  // Unsplash search
  const searchBtn = card.querySelector('[data-role="unsplash-search"]');
  const queryInput = card.querySelector('[data-role="unsplash-query"]');
  if (searchBtn) {
    searchBtn.addEventListener('click', () => {
      const query = queryInput.value.trim();
      if (query) searchUnsplash(query, card, idx);
    });
    queryInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        const query = queryInput.value.trim();
        if (query) searchUnsplash(query, card, idx);
      }
    });
  }
}

// ── Library Grid ──

function renderLibraryGrid(gridEl, idx, filter) {
  gridEl.innerHTML = '';
  let filtered = libraryImages;
  if (filter) {
    filtered = libraryImages.filter(li => {
      const text = `${li.title || ''} ${li.alt_text || ''} ${li.tags || ''} ${li.key || ''}`.toLowerCase();
      return text.includes(filter);
    });
  }

  // Show up to 12 images (avoid huge grids)
  const shown = filtered.slice(0, 12);
  if (!shown.length) {
    gridEl.innerHTML = '<span style="font-size:11px;color:var(--ev2-text-faint)">No matching images</span>';
    return;
  }

  shown.forEach(li => {
    const thumb = document.createElement('div');
    thumb.className = `ev2-pimg-unsplash-thumb${images[idx].library_image_id === li.id ? ' selected' : ''}`;
    thumb.innerHTML = `
      <img src="${esc(li.url)}" alt="${esc(li.title || li.alt_text || '')}" />
      <span class="ev2-pimg-unsplash-photographer">${esc(li.title || li.key || `#${li.id}`)}</span>
    `;
    thumb.addEventListener('click', () => {
      images[idx].library_image_id = li.id;
      gridEl.querySelectorAll('.ev2-pimg-unsplash-thumb').forEach(t => t.classList.remove('selected'));
      thumb.classList.add('selected');
    });
    gridEl.appendChild(thumb);
  });

  if (filtered.length > 12) {
    const more = document.createElement('div');
    more.style.cssText = 'font-size:11px;color:var(--ev2-text-faint);grid-column:1/-1;text-align:center;padding:4px 0';
    more.textContent = `${filtered.length - 12} more — type to filter`;
    gridEl.appendChild(more);
  }
}

// ── Unsplash Search ──

async function searchUnsplash(query, card, idx) {
  const gridEl = card.querySelector('[data-role="unsplash-grid"]');
  gridEl.innerHTML = '<span class="ev2-pimg-spinner"></span> Searching...';

  try {
    const csrfToken = config().csrfToken;
    const resp = await fetch('/ai/api/search-unsplash/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken,
      },
      body: JSON.stringify({ query, per_page: 9 }),
    });
    const data = await resp.json();

    if (!data.success || !data.results.length) {
      gridEl.innerHTML = '<span style="font-size:11px;color:var(--ev2-text-faint)">No results found</span>';
      return;
    }

    images[idx].unsplash_results = data.results;
    renderUnsplashResults(card, idx);

  } catch (err) {
    gridEl.innerHTML = `<span style="font-size:11px;color:#dc2626">Error: ${esc(err.message)}</span>`;
  }
}

function renderUnsplashResults(card, idx) {
  const gridEl = card.querySelector('[data-role="unsplash-grid"]');
  const results = images[idx].unsplash_results || [];
  gridEl.innerHTML = '';

  results.forEach(photo => {
    const thumb = document.createElement('div');
    thumb.className = `ev2-pimg-unsplash-thumb${images[idx].unsplash_photo_id === photo.id ? ' selected' : ''}`;
    thumb.innerHTML = `
      <img src="${esc(photo.thumb_url)}" alt="${esc(photo.alt_description)}" />
      <span class="ev2-pimg-unsplash-photographer">${esc(photo.photographer)}</span>
    `;
    thumb.addEventListener('click', () => {
      images[idx].unsplash_photo_id = photo.id;
      images[idx].unsplash_url = photo.regular_url;
      images[idx].photographer = photo.photographer;
      // Highlight selected
      gridEl.querySelectorAll('.ev2-pimg-unsplash-thumb').forEach(t => t.classList.remove('selected'));
      thumb.classList.add('selected');
    });
    gridEl.appendChild(thumb);
  });
}

// ── AI Suggest ──

async function aiSuggest() {
  if (!images.length) return;

  suggestBtn.disabled = true;
  setStatus('<span class="ev2-pimg-spinner"></span> AI analyzing images...');

  const imageData = images.map(img => ({
    index: img.index,
    src: img.src,
    alt: img.alt,
    name: img.name,
  }));

  try {
    const csrfToken = config().csrfToken;
    const resp = await fetch('/ai/api/analyze-page-images/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken,
      },
      body: JSON.stringify({
        page_id: config().pageId,
        images: imageData,
        model: 'gemini-pro',
      }),
    });
    const data = await resp.json();

    if (data.success && data.suggestions) {
      // Apply suggestions to images
      for (const suggestion of data.suggestions) {
        const img = images.find(i => i.index === suggestion.index);
        if (!img) continue;
        if (suggestion.prompt) img.prompt = suggestion.prompt;
        if (suggestion.aspect_ratio) img.aspect_ratio = suggestion.aspect_ratio;
        if (suggestion.library_matches && suggestion.library_matches.length) {
          // Build library suggestion objects with URLs
          img.library_suggestions = suggestion.library_matches.map(id => {
            const lib = libraryImages.find(l => l.id === id);
            return lib ? { id: lib.id, url: lib.url || lib.thumbnail_url || '' } : { id, url: '' };
          }).filter(s => s.url);
        }
      }
      // Re-render all cards with updated data
      renderCards();
      setStatus(`AI suggestions applied to ${data.suggestions.length} image(s)`);
    } else {
      setStatus(data.error || 'AI analysis failed');
    }
  } catch (err) {
    setStatus(`Error: ${err.message}`);
  } finally {
    suggestBtn.disabled = false;
  }
}

// ── Process Selected ──

async function processSelected() {
  const selected = images.filter(i => i.selected);
  if (!selected.length) return;

  // Build image entries in the format the API expects
  const entries = [];
  for (const img of selected) {
    const entry = { image_name: img.name, image_src: img.src };

    if (img.action === 'library') {
      if (!img.library_image_id) {
        setStatus(`Please select a library image for "${img.name}"`);
        return;
      }
      entry.action = 'library';
      entry.library_image_id = img.library_image_id;
    } else if (img.action === 'unsplash') {
      if (!img.unsplash_photo_id) {
        setStatus(`Please select an Unsplash photo for "${img.name}"`);
        return;
      }
      entry.action = 'unsplash';
      entry.unsplash_photo_id = img.unsplash_photo_id;
      entry.unsplash_url = img.unsplash_url;
      entry.photographer = img.photographer;
    } else {
      entry.action = 'generate';
      entry.prompt = img.prompt || img.alt || img.name;
      entry.aspect_ratio = img.aspect_ratio;
    }

    entries.push(entry);
  }

  processBtn.disabled = true;
  suggestBtn.disabled = true;
  setStatus(`<span class="ev2-pimg-spinner"></span> Processing ${entries.length} image(s)...`);

  try {
    const csrfToken = config().csrfToken;
    const resp = await fetch('/ai/api/process-page-images/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken,
      },
      body: JSON.stringify({
        page_id: config().pageId,
        images: entries,
      }),
    });
    const data = await resp.json();

    if (data.success) {
      setStatus(data.report || 'Images processed successfully');
      // Reload page after short delay to show updated images
      setTimeout(() => window.location.reload(), 1500);
    } else {
      setStatus(`Error: ${data.error || 'Processing failed'}`);
      processBtn.disabled = false;
      suggestBtn.disabled = false;
    }
  } catch (err) {
    setStatus(`Error: ${err.message}`);
    processBtn.disabled = false;
    suggestBtn.disabled = false;
  }
}

// ── Helpers ──

function setStatus(html) {
  if (statusEl) statusEl.innerHTML = html;
}

function updateProcessBtn() {
  const count = images.filter(i => i.selected).length;
  processBtn.disabled = count === 0;
  processBtn.textContent = count > 0 ? `Process Selected (${count})` : 'Process Selected';
}

export function destroy() {
  close();
}
