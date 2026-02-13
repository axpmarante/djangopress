/**
 * Image Picker — modal media library browser for IMG elements and section backgrounds.
 * Opens a full modal with library grid + search + upload.
 * Modes: 'img' (default) — sets src/alt on IMG; 'background' — sets style.backgroundImage on section.
 */
import { events } from '../lib/events.js';
import { api } from '../lib/api.js';
import { $, getElementId } from '../lib/dom.js';

function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

let cache = null;
let allImages = [];
let currentEl = null;
let currentElementId = null;
let currentMode = 'img'; // 'img' or 'background'
let selectedImage = null;
let selectedFile = null;
let activeModalTab = 'library';
let unsubs = [];

// --- DOM refs ---

const el = {
    modal:      () => $('#ev2-image-modal'),
    backdrop:   () => $('.ev2-image-modal-backdrop'),
    close:      () => $('#ev2-image-modal-close'),
    search:     () => $('#ev2-image-modal-search'),
    grid:       () => $('#ev2-image-modal-grid'),
    status:     () => $('#ev2-image-modal-status'),
    selectBtn:  () => $('#ev2-image-modal-select'),
    cancelBtn:  () => $('#ev2-image-modal-cancel'),
    uploadBtn:  () => $('#ev2-image-modal-upload-btn'),
    libraryTab: () => $('#ev2-image-modal-library'),
    uploadTab:  () => $('#ev2-image-modal-upload'),
    dropZone:   () => $('#ev2-image-drop-zone'),
    fileInput:  () => $('#ev2-image-file-input'),
    uploadPreview: () => $('#ev2-image-upload-preview'),
    uploadThumb:   () => $('#ev2-image-upload-thumb'),
    uploadTitle:   () => $('#ev2-image-upload-title'),
    uploadAlt:     () => $('#ev2-image-upload-alt'),
};

// --- Open / Close ---

function open(data) {
    const mode = (data && data.mode) || 'img';
    // In img mode, require an IMG element; in background mode, accept any element
    if (mode === 'img' && (!currentEl || currentEl.tagName !== 'IMG')) return;
    if (mode === 'background' && !currentEl) return;

    currentMode = mode;
    const modal = el.modal();
    if (!modal) return;

    // Update modal title
    const titleEl = modal.querySelector('.ev2-image-modal-header h3');
    if (titleEl) titleEl.textContent = mode === 'background' ? 'Select Background Image' : 'Select Image';

    selectedImage = null;
    selectedFile = null;
    activeModalTab = 'library';
    setStatus('');
    updateButtons();
    switchModalTab('library');
    modal.classList.remove('hidden');

    // Load images
    if (!cache) {
        fetchImages('');
    } else {
        allImages = cache;
        renderGrid(allImages);
    }

    const search = el.search();
    if (search) { search.value = ''; search.focus(); }
}

function close() {
    const modal = el.modal();
    if (modal) modal.classList.add('hidden');
    selectedImage = null;
    selectedFile = null;
    currentMode = 'img';
    resetUpload();
}

// --- Tab switching ---

function switchModalTab(tab) {
    activeModalTab = tab;
    const libBody = el.libraryTab();
    const uplBody = el.uploadTab();
    const selectB = el.selectBtn();
    const uploadB = el.uploadBtn();

    if (libBody) libBody.style.display = tab === 'library' ? '' : 'none';
    if (uplBody) uplBody.style.display = tab === 'upload' ? '' : 'none';
    if (selectB) selectB.style.display = tab === 'library' ? '' : 'none';
    if (uploadB) uploadB.style.display = tab === 'upload' ? '' : 'none';

    // Update tab buttons
    const tabs = document.querySelectorAll('.ev2-image-modal-tab');
    tabs.forEach(t => t.classList.toggle('active', t.dataset.modalTab === tab));

    selectedImage = null;
    selectedFile = null;
    setStatus('');
    updateButtons();
}

// --- Fetch / Search ---

async function fetchImages(query) {
    const grid = el.grid();
    if (!grid) return;
    grid.innerHTML = '<div class="ev2-image-modal-loading">Loading images...</div>';

    try {
        let images;
        if (query) {
            const res = await api.get('/media-library/', { search: query });
            images = res.images || [];
        } else {
            const res = await api.get('/images/');
            images = res.images || [];
            cache = images;
        }
        allImages = images;
        renderGrid(images);
    } catch {
        grid.innerHTML = '<div class="ev2-image-modal-empty">Failed to load images</div>';
    }
}

function filterImages(query) {
    if (!query) {
        renderGrid(allImages);
        return;
    }
    const q = query.toLowerCase();
    const filtered = allImages.filter(img => {
        const searchText = `${img.title || ''} ${img.alt_text || ''} ${img.tags || ''}`.toLowerCase();
        return searchText.includes(q);
    });
    renderGrid(filtered);
}

// --- Grid rendering ---

function renderGrid(images) {
    const grid = el.grid();
    if (!grid) return;

    if (!images.length) {
        grid.innerHTML = '<div class="ev2-image-modal-empty">No images found</div>';
        return;
    }

    grid.innerHTML = images.map(img =>
        `<div class="ev2-image-modal-item" data-img-id="${img.id}" data-url="${esc(img.url)}" data-alt="${esc(img.alt_text || img.title || '')}" data-title="${esc(img.title || '')}">
            <img src="${esc(img.url)}" alt="${esc(img.alt_text || '')}" loading="lazy" />
            <div class="ev2-image-modal-check">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
            </div>
            <span class="ev2-image-modal-item-title">${esc(img.title || 'Untitled')}</span>
        </div>`
    ).join('');

    grid.querySelectorAll('.ev2-image-modal-item').forEach(item => {
        item.addEventListener('click', () => selectLibraryImage(item));
    });
}

function selectLibraryImage(item) {
    // Deselect all
    const grid = el.grid();
    if (grid) grid.querySelectorAll('.ev2-image-modal-item').forEach(i => i.classList.remove('selected'));

    // Select this one
    item.classList.add('selected');
    selectedImage = {
        id: item.dataset.imgId,
        url: item.dataset.url,
        alt: item.dataset.alt,
        title: item.dataset.title,
    };
    setStatus(`Selected: ${selectedImage.title || 'Image'}`);
    updateButtons();
}

// --- Upload ---

function onFileSelected(file) {
    if (!file) return;
    if (!file.type.startsWith('image/')) {
        setStatus('Only image files are allowed');
        return;
    }
    if (file.size > 10 * 1024 * 1024) {
        setStatus('File too large (max 10 MB)');
        return;
    }

    selectedFile = file;
    const preview = el.uploadPreview();
    const thumb = el.uploadThumb();
    const titleInput = el.uploadTitle();
    const dropZone = el.dropZone();

    if (thumb) {
        const reader = new FileReader();
        reader.onload = (e) => { thumb.src = e.target.result; };
        reader.readAsDataURL(file);
    }
    if (preview) preview.style.display = '';
    if (dropZone) dropZone.style.display = 'none';
    if (titleInput) titleInput.value = file.name.replace(/\.[^/.]+$/, '');

    setStatus(`Ready to upload: ${file.name}`);
    updateButtons();
}

function resetUpload() {
    const preview = el.uploadPreview();
    const dropZone = el.dropZone();
    const fileInput = el.fileInput();
    const titleInput = el.uploadTitle();
    const altInput = el.uploadAlt();

    if (preview) preview.style.display = 'none';
    if (dropZone) dropZone.style.display = '';
    if (fileInput) fileInput.value = '';
    if (titleInput) titleInput.value = '';
    if (altInput) altInput.value = '';
    selectedFile = null;
}

async function uploadAndSelect() {
    if (!selectedFile || !currentEl) return;

    const uploadBtn = el.uploadBtn();
    if (uploadBtn) { uploadBtn.disabled = true; uploadBtn.textContent = 'Uploading...'; }
    setStatus('Uploading...');

    try {
        const title = el.uploadTitle()?.value || selectedFile.name;
        const alt = el.uploadAlt()?.value || '';

        const formData = new FormData();
        formData.append('image', selectedFile);
        formData.append('title', title);
        formData.append('alt_text', alt);

        const config = window.EDITOR_CONFIG || {};
        const response = await fetch(`${config.apiBase || '/editor-v2/api'}/images/upload/`, {
            method: 'POST',
            headers: { 'X-CSRFToken': config.csrfToken || '' },
            body: formData,
        });

        if (!response.ok) throw new Error(`Upload failed: ${response.status}`);
        const result = await response.json();
        if (!result.success) throw new Error(result.error || 'Upload failed');

        // Apply the uploaded image
        const img = result.image;
        applyImage(img.url, img.alt_text || alt);

        // Invalidate cache
        cache = null;
        close();
    } catch (err) {
        setStatus(`Error: ${err.message}`);
        if (uploadBtn) { uploadBtn.disabled = false; uploadBtn.textContent = 'Upload & Select'; }
    }
}

// --- Apply selection ---

function applySelection() {
    if (!selectedImage || !currentEl) return;
    applyImage(selectedImage.url, selectedImage.alt);
    close();
}

function applyImage(url, alt) {
    if (!currentEl || !currentElementId) return;

    if (currentMode === 'background') {
        // Background image mode — preserve existing overlay if any
        const oldStyle = currentEl.getAttribute('style') || '';
        const oldBg = currentEl.style.backgroundImage || '';
        // Check for existing overlay gradient
        const gradMatch = oldBg.match(/linear-gradient\(\s*rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)[^)]*\)/);
        if (gradMatch) {
            // Preserve the overlay gradient with the new image URL
            currentEl.style.backgroundImage = `${gradMatch[0]}, url('${url}')`;
        } else {
            currentEl.style.backgroundImage = `url('${url}')`;
        }
        // Ensure cover + center if not already set
        if (!currentEl.style.backgroundSize) currentEl.style.backgroundSize = 'cover';
        if (!currentEl.style.backgroundPosition) currentEl.style.backgroundPosition = 'center';
        const newStyle = currentEl.getAttribute('style') || '';
        events.emit('change:attribute', {
            type: 'attribute', elementId: currentElementId,
            attribute: 'style', value: newStyle, oldValue: oldStyle,
            tagName: currentEl.tagName.toLowerCase(),
        });
    } else {
        // IMG element mode — update src and alt
        const oldSrc = currentEl.src || '';
        const oldAlt = currentEl.alt || '';
        currentEl.src = url;
        currentEl.alt = alt;
        events.emit('change:attribute', {
            type: 'attribute', elementId: currentElementId,
            attribute: 'src', value: url, oldValue: oldSrc, tagName: 'img',
        });
        events.emit('change:attribute', {
            type: 'attribute', elementId: currentElementId,
            attribute: 'alt', value: alt, oldValue: oldAlt, tagName: 'img',
        });
    }

    // Refresh sidebar to show new preview
    events.emit('selection:changed', currentEl);
}

// --- Helpers ---

function setStatus(text) {
    const s = el.status();
    if (s) s.textContent = text;
}

function updateButtons() {
    const selectB = el.selectBtn();
    const uploadB = el.uploadBtn();
    if (selectB) selectB.disabled = !selectedImage;
    if (uploadB) {
        uploadB.disabled = !selectedFile;
        uploadB.textContent = 'Upload & Select';
    }
}

// --- Selection tracking ---

function onSelectionChanged(element) {
    currentEl = element;
    currentElementId = element ? getElementId(element) : null;
}

// --- Event binding ---

function bindModalEvents() {
    el.backdrop()?.addEventListener('click', close);
    el.close()?.addEventListener('click', close);
    el.cancelBtn()?.addEventListener('click', close);
    el.selectBtn()?.addEventListener('click', applySelection);
    el.uploadBtn()?.addEventListener('click', uploadAndSelect);

    // Tab switching
    document.querySelectorAll('.ev2-image-modal-tab').forEach(tab => {
        tab.addEventListener('click', () => switchModalTab(tab.dataset.modalTab));
    });

    // Search (debounced)
    let searchTimer = null;
    el.search()?.addEventListener('input', (e) => {
        clearTimeout(searchTimer);
        const q = e.target.value.trim();
        searchTimer = setTimeout(() => {
            if (q) filterImages(q);
            else if (cache) renderGrid(cache);
            else fetchImages('');
        }, 300);
    });

    // File input
    el.fileInput()?.addEventListener('change', (e) => {
        if (e.target.files[0]) onFileSelected(e.target.files[0]);
    });

    // Drop zone click
    el.dropZone()?.addEventListener('click', () => el.fileInput()?.click());

    // Drag & drop
    const dz = el.dropZone();
    if (dz) {
        dz.addEventListener('dragover', (e) => { e.preventDefault(); dz.classList.add('ev2-dragover'); });
        dz.addEventListener('dragleave', () => dz.classList.remove('ev2-dragover'));
        dz.addEventListener('drop', (e) => {
            e.preventDefault();
            dz.classList.remove('ev2-dragover');
            if (e.dataTransfer.files[0]) onFileSelected(e.dataTransfer.files[0]);
        });
    }

    // Escape to close
    document.addEventListener('keydown', onKeydown);
}

function onKeydown(e) {
    if (e.key === 'Escape' && !el.modal()?.classList.contains('hidden')) {
        e.preventDefault();
        e.stopPropagation();
        close();
    }
}

// --- Lifecycle ---

export function init() {
    unsubs.push(events.on('selection:changed', onSelectionChanged));
    unsubs.push(events.on('image-picker:open', open));
    bindModalEvents();
}

export function destroy() {
    unsubs.forEach(fn => fn());
    unsubs = [];
    document.removeEventListener('keydown', onKeydown);
    cache = null;
    allImages = [];
    currentEl = null;
    currentElementId = null;
    currentMode = 'img';
    selectedImage = null;
    selectedFile = null;
}
