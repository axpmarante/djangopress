import { events } from '../lib/events.js';
import { api } from '../lib/api.js';
import { $, $$, getCssSelector, isTextElement, getTransVar, getSections, getTagLabel } from '../lib/dom.js';
import { CATEGORIES, HOVER_CATEGORIES, COLOR_FAMILIES, COLOR_SHADES, COLOR_KEYWORDS } from '../lib/tailwind-classes.js';
import { parseClasses, buildClassString } from '../lib/class-parser.js';

let activeTab = 'content';
let selectedEl = null;
const handlers = {};

// --- Escape ---

function esc(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// --- Tailwind class dropdowns ---

function renderClassDropdowns(classes, extraCategories = []) {
    const { matched } = parseClasses(classes, { extraCategories });
    let html = '';

    const allCategories = [...CATEGORIES, ...extraCategories];

    for (const group of allCategories) {
        html += `<div class="ev2-class-group">`;
        html += `<div class="ev2-class-group-label">${esc(group.group)}</div>`;

        for (const cat of group.items) {
            const key = `${group.group}:${cat.label}`;
            const entry = matched.get(key);

            html += `<div class="ev2-class-row">`;
            html += `<label>${esc(cat.label)}</label>`;

            if (cat.type === 'color') {
                const family = entry?.color?.family || '';
                const shade = entry?.color?.shade || '';
                const prefix = cat.prefixes[0];
                const isKeyword = ['white', 'black', 'transparent', 'current'].includes(family);

                html += `<div class="ev2-color-selects">`;
                html += `<select class="ev2-class-select" data-cat="${esc(key)}" data-color="family" data-prefix="${esc(prefix)}">`;
                html += `<option value="">None</option>`;
                for (const kw of COLOR_KEYWORDS) {
                    html += `<option value="${kw}"${family === kw ? ' selected' : ''}>${kw}</option>`;
                }
                for (const f of COLOR_FAMILIES) {
                    html += `<option value="${f}"${family === f ? ' selected' : ''}>${f}</option>`;
                }
                html += `</select>`;
                html += `<select class="ev2-class-select" data-cat="${esc(key)}" data-color="shade" data-prefix="${esc(prefix)}"${isKeyword || !family ? ' disabled' : ''}>`;
                html += `<option value="">—</option>`;
                for (const s of COLOR_SHADES) {
                    html += `<option value="${s}"${shade === s ? ' selected' : ''}>${s}</option>`;
                }
                html += `</select>`;
                html += `</div>`;
            } else if (cat.exact) {
                const current = entry?.value || '';
                html += `<select class="ev2-class-select" data-cat="${esc(key)}" data-exact="true">`;
                html += `<option value="">None</option>`;
                for (const v of cat.values) {
                    html += `<option value="${v}"${current === v ? ' selected' : ''}>${v}</option>`;
                }
                html += `</select>`;
            } else {
                const current = entry?.value ?? '';
                const hasMatch = !!entry;
                html += `<select class="ev2-class-select" data-cat="${esc(key)}" data-prefix="${esc(cat.prefixes[0])}">`;
                html += `<option value="__none__"${!hasMatch ? ' selected' : ''}>None</option>`;
                for (const v of cat.values) {
                    const display = v === '' ? `${cat.prefixes[0]}` : `${cat.prefixes[0]}-${v}`;
                    html += `<option value="${v}"${hasMatch && current === v ? ' selected' : ''}>${display}</option>`;
                }
                html += `</select>`;
            }

            html += `</div>`;
        }

        html += `</div>`;
    }

    return html;
}

// --- Media collection detection ---

function findMediaCollection(el) {
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

function renderMediaCollection(container, collectionEl) {
    const type = collectionEl.getAttribute('data-media-collection') || 'media';
    const section = collectionEl.closest('[data-section]');
    const sectionName = section ? section.getAttribute('data-section') : null;
    // Filter out Splide cloned slides (type:"loop" clones elements)
    const imgs = Array.from(collectionEl.querySelectorAll('img'))
        .filter(img => !img.closest('.splide__slide--clone'));

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

    if (sectionName) {
        html += '<button type="button" class="ev2-btn-change-img" id="ev2-media-process-btn">Process Section Images</button>';
    }

    html += '<p class="ev2-media-hint">Click a thumbnail to edit individually</p>';

    container.innerHTML = html;

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

    const processBtn = container.querySelector('#ev2-media-process-btn');
    if (processBtn && sectionName) {
        processBtn.addEventListener('click', () => {
            events.emit('process-images:open', { section: sectionName });
        });
    }
}

// --- Content tab ---

function renderContentTab() {
    const c = $('#ev2-tab-content');
    if (!c) return;
    if (!selectedEl) {
        c.innerHTML = '<p class="ev2-placeholder ev2-empty-state">Select an element to edit</p>';
        return;
    }
    const tag = selectedEl.tagName;
    const selector = getCssSelector(selectedEl) || '';

    if (tag === 'IMG') renderImageFields(c, selector);
    else if (tag === 'A') renderLinkFields(c, selector);
    else if (isTextElement(selectedEl)) renderTextField(c, selector);
    else {
        const collectionEl = findMediaCollection(selectedEl);
        if (collectionEl) renderMediaCollection(c, collectionEl);
        else c.innerHTML = '<p class="ev2-placeholder ev2-empty-state">Select a text element to edit content</p>';
    }
}

function renderTextField(container, selector) {
    const transVar = getTransVar(selectedEl);
    const fieldKey = transVar || '';
    const label = transVar ? `trans.${transVar}` : selectedEl.tagName.toLowerCase();
    const text = selectedEl.textContent.trim();
    const isLong = text.length > 80;

    let html = `<div class="ev2-field"><label class="ev2-label">${esc(label)}</label>`;
    if (isLong) {
        html += `<textarea class="ev2-textarea" data-field-key="${esc(fieldKey)}" data-selector="${esc(selector)}">${esc(text)}</textarea>`;
    } else {
        html += `<input class="ev2-input" type="text" data-field-key="${esc(fieldKey)}" data-selector="${esc(selector)}" value="${esc(text)}" />`;
    }
    if (transVar) html += `<p class="ev2-hint">Variable: {{ trans.${esc(transVar)} }}</p>`;
    html += '</div>';

    container.innerHTML = html;
    attachContentListeners(container);
}

function renderImageFields(container, selector) {
    const src = selectedEl.getAttribute('src') || '';
    const alt = selectedEl.getAttribute('alt') || '';
    container.innerHTML = `
        <div class="ev2-img-preview-wrap">
            <img src="${esc(src)}" alt="${esc(alt)}" class="ev2-img-preview" />
        </div>
        <div class="ev2-field">
            <button type="button" class="ev2-btn-change-img" id="ev2-change-img-btn">Change Image</button>
        </div>
        <div class="ev2-field"><label class="ev2-label">Alt text</label>
            <input class="ev2-input" type="text" data-attr="alt" data-selector="${esc(selector)}" value="${esc(alt)}" /></div>
        <div class="ev2-field"><label class="ev2-label">Image URL</label>
            <input class="ev2-input ev2-input-mono" type="text" data-attr="src" data-selector="${esc(selector)}" value="${esc(src)}" /></div>`;
    attachContentListeners(container);
    const changeBtn = container.querySelector('#ev2-change-img-btn');
    if (changeBtn) changeBtn.addEventListener('click', () => events.emit('image-picker:open'));
}

function renderLinkFields(container, selector) {
    const transVar = getTransVar(selectedEl);
    const fieldKey = transVar || '';
    const label = transVar ? `trans.${transVar}` : selectedEl.tagName.toLowerCase();
    const text = selectedEl.textContent.trim();
    const href = selectedEl.getAttribute('href') || '';
    container.innerHTML = `
        <div class="ev2-field"><label class="ev2-label">${esc(label)}</label>
            <input class="ev2-input" type="text" data-field-key="${esc(fieldKey)}" data-selector="${esc(selector)}" value="${esc(text)}" />
            ${transVar ? `<p class="ev2-hint">Variable: {{ trans.${esc(transVar)} }}</p>` : ''}</div>
        <div class="ev2-field"><label class="ev2-label">Link URL</label>
            <input class="ev2-input" type="text" data-attr="href" data-selector="${esc(selector)}" value="${esc(href)}" /></div>`;
    attachContentListeners(container);
}

function attachContentListeners(container) {
    for (const input of $$('.ev2-input, .ev2-textarea', container)) {
        input.addEventListener('input', () => onContentInput(input));
    }
}

function onContentInput(input) {
    const selector = input.dataset.selector;
    const attr = input.dataset.attr;
    const fieldKey = input.dataset.fieldKey;
    const value = input.value;

    if (attr) {
        const oldValue = selectedEl.getAttribute(attr) || '';
        selectedEl.setAttribute(attr, value);
        events.emit('change:attribute', {
            type: 'attribute', selector, attribute: attr,
            value, oldValue, tagName: selectedEl.tagName.toLowerCase(),
        });
    } else {
        const oldValue = selectedEl.textContent;
        selectedEl.textContent = value;
        events.emit('change:content', {
            type: 'content', selector, fieldKey: fieldKey || '', value, oldValue,
        });
    }
}

// --- YouTube helpers ---

function extractYouTubeId(url) {
    if (!url) return null;
    const m = url.match(/(?:youtube\.com\/watch\?.*v=|youtube\.com\/embed\/|youtu\.be\/)([a-zA-Z0-9_-]{11})/);
    return m ? m[1] : null;
}

function videoDisplayUrl(url) {
    const id = extractYouTubeId(url);
    return id ? `https://www.youtube.com/watch?v=${id}` : (url || '');
}

// --- Design tab ---

function renderDesignTab() {
    const container = $('#ev2-tab-content');
    if (!container) return;
    if (!selectedEl) {
        container.innerHTML = '<p class="ev2-placeholder ev2-empty-state">Select an element to edit classes</p>';
        return;
    }

    const selector = getCssSelector(selectedEl) || '';
    const tag = selectedEl.tagName.toLowerCase();
    const id = selectedEl.id || '';
    const classes = selectedEl.className.split(/\s+/).filter(c => !c.startsWith('ev2-')).join(' ');
    const info = id ? `&lt;${tag} id="${esc(id)}"&gt;` : `&lt;${tag}&gt;`;
    const isSection = selectedEl.hasAttribute('data-section');

    let html = `<p class="ev2-element-info">${info}</p>`;

    // --- Section background controls ---
    if (isSection) {
        // Parse background image (may include overlay gradient)
        const bg = parseBgImage(selectedEl.style.backgroundImage);

        // Background Image
        html += '<div class="ev2-design-section">';
        html += '<label class="ev2-label">Background Image</label>';
        if (bg.url) {
            html += `<div class="ev2-bg-preview" style="background-image:url('${esc(bg.url)}')"></div>`;
            html += '<div class="ev2-bg-actions">';
            html += '<button type="button" class="ev2-btn-sm ev2-btn-sm-primary" id="ev2-bg-img-change">Change</button>';
            html += '<button type="button" class="ev2-btn-sm ev2-btn-sm-danger" id="ev2-bg-img-remove">Remove</button>';
            html += '</div>';
        } else {
            html += '<button type="button" class="ev2-btn-change-img" id="ev2-bg-img-add">Add Background Image</button>';
        }
        html += '</div>';

        // Background Video
        const bgIframe = selectedEl.querySelector(':scope > iframe[data-bg-video]');
        const bgVideoEl = selectedEl.querySelector(':scope > video');
        const hasVideo = !!(bgIframe || bgVideoEl);
        const videoType = bgIframe ? 'youtube' : (bgVideoEl ? 'video' : '');
        const videoSrc = bgIframe ? bgIframe.getAttribute('src') : (bgVideoEl?.querySelector('source')?.getAttribute('src') || '');

        html += '<div class="ev2-design-section">';
        html += '<label class="ev2-label">Background Video</label>';
        if (hasVideo) {
            const ytId = extractYouTubeId(videoSrc);
            if (ytId) {
                html += `<div class="ev2-video-preview" style="background-image:url('https://img.youtube.com/vi/${esc(ytId)}/hqdefault.jpg')"></div>`;
            }
            html += `<span class="ev2-video-badge">${esc(videoType === 'youtube' ? 'YouTube' : 'Video')}</span>`;
            html += `<p class="ev2-video-url">${esc(videoDisplayUrl(videoSrc))}</p>`;
            html += '<button type="button" class="ev2-btn-sm ev2-btn-sm-danger" id="ev2-video-remove">Remove Video</button>';
        } else {
            html += '<div class="ev2-video-input-row">';
            html += '<input type="text" class="ev2-input" id="ev2-video-url" placeholder="Paste a YouTube URL" />';
            html += '</div>';
            html += '<button type="button" class="ev2-btn-sm ev2-btn-sm-primary" id="ev2-video-set" style="margin-top:6px">Set Video</button>';
        }
        html += '</div>';

        // Overlay (always available for sections)
        // Read from data-overlay attribute first, fall back to parsing backgroundImage
        const overlayAttr = selectedEl.getAttribute('data-overlay') || '';
        let overlayHex = '#000000';
        let overlayPct = 0;
        if (overlayAttr) {
            const om = overlayAttr.match(/rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)/);
            if (om) {
                overlayHex = '#' + [om[1], om[2], om[3]].map(n => parseInt(n).toString(16).padStart(2, '0')).join('');
                overlayPct = Math.round(parseFloat(om[4]) * 100);
            }
        } else if (bg.overlayColor) {
            overlayHex = bg.overlayColor;
            overlayPct = Math.round((bg.overlayOpacity || 0) * 100);
        }

        html += '<div class="ev2-design-section">';
        html += '<label class="ev2-label">Overlay</label>';
        html += '<div class="ev2-overlay-row">';
        html += `<input type="color" class="ev2-color-input" id="ev2-overlay-color" value="${overlayHex}" />`;
        html += `<input type="range" class="ev2-range" id="ev2-overlay-opacity" min="0" max="100" value="${overlayPct}" />`;
        html += `<span class="ev2-overlay-value" id="ev2-overlay-value">${overlayPct}%</span>`;
        html += '</div>';
        if (overlayPct > 0) {
            html += '<button type="button" class="ev2-btn-sm ev2-btn-sm-danger" id="ev2-overlay-remove" style="margin-top:6px">Remove Overlay</button>';
        }
        html += '</div>';

        // Background Color
        const bgColor = selectedEl.style.backgroundColor || '';
        const colorValue = bgColor ? rgbToHex(bgColor) : '#ffffff';

        html += '<div class="ev2-design-section">';
        html += '<label class="ev2-label">Background Color</label>';
        html += '<div class="ev2-color-row">';
        html += `<input type="color" class="ev2-color-input" id="ev2-bg-color-input" value="${colorValue}" />`;
        html += `<span class="ev2-color-value" id="ev2-bg-color-value">${bgColor || 'none'}</span>`;
        if (bgColor) {
            html += '<button type="button" class="ev2-btn-sm ev2-btn-sm-danger" id="ev2-bg-color-remove">Remove</button>';
        }
        html += '</div>';
        html += '</div>';
    }

    // --- Tailwind class dropdowns ---
    const isInteractive = tag === 'a' || tag === 'button';
    const extraCats = isInteractive ? HOVER_CATEGORIES : [];
    html += '<div class="ev2-design-section" id="ev2-class-dropdowns">';
    html += renderClassDropdowns(classes, extraCats);
    html += '</div>';

    // --- CSS Classes (always shown) ---
    html += `<div class="ev2-design-section"><label class="ev2-label">CSS Classes</label>
        <textarea class="ev2-textarea" id="ev2-classes-input" data-selector="${esc(selector)}">${esc(classes)}</textarea>
        <p class="ev2-hint">Space-separated Tailwind classes</p></div>`;

    container.innerHTML = html;

    // --- Bind class editor ---
    const textarea = $('#ev2-classes-input', container);
    const dropdownContainer = container.querySelector('#ev2-class-dropdowns');

    if (textarea) {
        textarea.addEventListener('input', () => {
            const newClasses = textarea.value;
            const ev2Classes = selectedEl.className.split(/\s+/).filter(c => c.startsWith('ev2-'));
            const oldValue = selectedEl.className.split(/\s+/).filter(c => !c.startsWith('ev2-')).join(' ');
            selectedEl.className = [...ev2Classes, ...newClasses.split(/\s+/).filter(Boolean)].join(' ');
            events.emit('change:classes', {
                type: 'classes', selector, value: newClasses, oldValue,
            });
            // Sync dropdowns
            if (dropdownContainer) {
                dropdownContainer.innerHTML = renderClassDropdowns(newClasses, extraCats);
            }
        });
    }

    // --- Bind class dropdowns ---
    if (dropdownContainer) {
        dropdownContainer.addEventListener('change', (e) => {
            const select = e.target.closest('.ev2-class-select');
            if (!select) return;

            const currentClasses = selectedEl.className.split(/\s+/).filter(c => !c.startsWith('ev2-')).join(' ');
            const { matched, unmatched } = parseClasses(currentClasses, { extraCategories: extraCats });

            const catKey = select.dataset.cat;
            const colorRole = select.dataset.color;

            if (colorRole) {
                const prefix = select.dataset.prefix;
                const row = select.closest('.ev2-class-row');
                const familySel = row.querySelector('[data-color="family"]');
                const shadeSel = row.querySelector('[data-color="shade"]');
                const family = familySel.value;
                const shade = shadeSel.value;
                const isKeyword = ['white', 'black', 'transparent', 'current'].includes(family);

                shadeSel.disabled = !family || isKeyword;

                if (!family) {
                    matched.delete(catKey);
                } else {
                    matched.set(catKey, {
                        prefix,
                        value: isKeyword ? `${prefix}-${family}` : `${prefix}-${family}-${shade || '500'}`,
                        color: { family, shade: isKeyword ? '' : (shade || '500') },
                    });
                    if (!isKeyword && !shade) shadeSel.value = '500';
                }
            } else {
                const val = select.value;
                if (val === '__none__' || val === '') {
                    matched.delete(catKey);
                } else {
                    const prefix = select.dataset.prefix || '';
                    const isExact = select.dataset.exact === 'true';
                    if (isExact) {
                        matched.set(catKey, { prefix: '', value: val });
                    } else {
                        matched.set(catKey, { prefix, value: val, fullClass: val === '' ? prefix : `${prefix}-${val}` });
                    }
                }
            }

            const newClasses = buildClassString(matched, unmatched, { extraCategories: extraCats });
            const ev2Classes = selectedEl.className.split(/\s+/).filter(c => c.startsWith('ev2-'));
            const oldValue = currentClasses;
            selectedEl.className = [...ev2Classes, ...newClasses.split(/\s+/).filter(Boolean)].join(' ');

            if (textarea) textarea.value = newClasses;

            events.emit('change:classes', {
                type: 'classes', selector, value: newClasses, oldValue,
            });
        });
    }

    // --- Bind section background controls ---
    if (isSection) {
        const addBtn = container.querySelector('#ev2-bg-img-add');
        const changeBtn = container.querySelector('#ev2-bg-img-change');
        const removeBtn = container.querySelector('#ev2-bg-img-remove');
        const colorInput = container.querySelector('#ev2-bg-color-input');
        const colorRemove = container.querySelector('#ev2-bg-color-remove');
        const overlayColor = container.querySelector('#ev2-overlay-color');
        const overlayOpacity = container.querySelector('#ev2-overlay-opacity');
        const overlayRemove = container.querySelector('#ev2-overlay-remove');

        if (addBtn) addBtn.addEventListener('click', () => events.emit('image-picker:open', { mode: 'background' }));
        if (changeBtn) changeBtn.addEventListener('click', () => events.emit('image-picker:open', { mode: 'background' }));
        if (removeBtn) removeBtn.addEventListener('click', () => {
            const bg = parseBgImage(selectedEl.style.backgroundImage);
            emitStyleChange(selector, () => {
                // Keep standalone overlay if present, remove just the image URL
                if (bg.overlayOpacity > 0 && bg.overlayColor) {
                    selectedEl.style.backgroundImage = composeBgImage('', bg.overlayColor, bg.overlayOpacity);
                } else {
                    selectedEl.style.backgroundImage = '';
                }
            });
            renderDesignTab();
        });

        // Overlay controls
        if (overlayColor || overlayOpacity) {
            const applyOverlay = () => {
                const bg = parseBgImage(selectedEl.style.backgroundImage);
                const color = overlayColor ? overlayColor.value : (bg.overlayColor || '#000000');
                const opacity = overlayOpacity ? parseInt(overlayOpacity.value) / 100 : (bg.overlayOpacity || 0);
                emitStyleChange(selector, () => {
                    selectedEl.style.backgroundImage = composeBgImage(bg.url, color, opacity);
                });
                // Set semantic data-overlay attribute for LLM readability
                if (opacity > 0) {
                    const { r, g, b } = hexToRgb(color);
                    emitAttrChange(selector, 'data-overlay', `rgba(${r}, ${g}, ${b}, ${opacity})`);
                } else {
                    emitAttrChange(selector, 'data-overlay', '');
                }
                const valSpan = container.querySelector('#ev2-overlay-value');
                if (valSpan) valSpan.textContent = `${Math.round(opacity * 100)}%`;
            };
            if (overlayColor) overlayColor.addEventListener('input', applyOverlay);
            if (overlayOpacity) overlayOpacity.addEventListener('input', applyOverlay);
        }
        if (overlayRemove) overlayRemove.addEventListener('click', () => {
            const bg = parseBgImage(selectedEl.style.backgroundImage);
            emitStyleChange(selector, () => {
                selectedEl.style.backgroundImage = composeBgImage(bg.url, null, 0);
            });
            emitAttrChange(selector, 'data-overlay', '');
            renderDesignTab();
        });

        // Background color controls
        if (colorInput) {
            colorInput.addEventListener('input', () => {
                emitStyleChange(selector, () => { selectedEl.style.backgroundColor = colorInput.value; });
                const valSpan = container.querySelector('#ev2-bg-color-value');
                if (valSpan) valSpan.textContent = colorInput.value;
            });
        }
        if (colorRemove) colorRemove.addEventListener('click', () => {
            emitStyleChange(selector, () => { selectedEl.style.backgroundColor = ''; });
            renderDesignTab();
        });

        // Background video controls
        const videoSetBtn = container.querySelector('#ev2-video-set');
        const videoRemoveBtn = container.querySelector('#ev2-video-remove');
        const videoUrlInput = container.querySelector('#ev2-video-url');
        const pageId = window.EDITOR_CONFIG?.pageId;
        const sectionId = selectedEl.getAttribute('data-section') || selectedEl.id;

        if (videoSetBtn && videoUrlInput) {
            videoSetBtn.addEventListener('click', async () => {
                const url = videoUrlInput.value.trim();
                if (!url || !pageId || !sectionId) return;
                videoSetBtn.disabled = true;
                videoSetBtn.textContent = 'Setting...';
                try {
                    await api.post('/update-section-video/', {
                        page_id: pageId, section_id: sectionId, video_url: url
                    });
                    window.location.reload();
                } catch (err) {
                    videoSetBtn.disabled = false;
                    videoSetBtn.textContent = 'Set Video';
                    alert('Error: ' + err.message);
                }
            });
        }
        if (videoRemoveBtn) {
            videoRemoveBtn.addEventListener('click', async () => {
                if (!pageId || !sectionId) return;
                videoRemoveBtn.disabled = true;
                videoRemoveBtn.textContent = 'Removing...';
                try {
                    await api.post('/update-section-video/', {
                        page_id: pageId, section_id: sectionId, video_url: ''
                    });
                    window.location.reload();
                } catch (err) {
                    videoRemoveBtn.disabled = false;
                    videoRemoveBtn.textContent = 'Remove Video';
                }
            });
        }
    }
}

function emitStyleChange(selector, applyFn) {
    const oldStyle = selectedEl.getAttribute('style') || '';
    applyFn();
    const newStyle = selectedEl.getAttribute('style') || '';
    if (oldStyle !== newStyle) {
        events.emit('change:attribute', {
            type: 'attribute', selector, attribute: 'style',
            value: newStyle, oldValue: oldStyle, tagName: selectedEl.tagName.toLowerCase(),
        });
    }
}

function emitAttrChange(selector, attr, value) {
    const oldValue = selectedEl.getAttribute(attr) || '';
    if (value) {
        selectedEl.setAttribute(attr, value);
    } else {
        selectedEl.removeAttribute(attr);
    }
    const newValue = value || '';
    if (oldValue !== newValue) {
        events.emit('change:attribute', {
            type: 'attribute', selector, attribute: attr,
            value: newValue, oldValue, tagName: selectedEl.tagName.toLowerCase(),
        });
    }
}

function rgbToHex(rgb) {
    if (!rgb) return '#ffffff';
    if (rgb.startsWith('#')) return rgb;
    const match = rgb.match(/(\d+)/g);
    if (!match || match.length < 3) return '#ffffff';
    return '#' + match.slice(0, 3).map(n => parseInt(n).toString(16).padStart(2, '0')).join('');
}

function hexToRgb(hex) {
    const m = hex.replace('#', '').match(/.{2}/g);
    if (!m) return { r: 0, g: 0, b: 0 };
    return { r: parseInt(m[0], 16), g: parseInt(m[1], 16), b: parseInt(m[2], 16) };
}

// Parse backgroundImage value: may be "url(...)" or "linear-gradient(rgba(...), rgba(...)), url(...)"
function parseBgImage(bgImage) {
    if (!bgImage || bgImage === 'none') return { url: '', overlayColor: '', overlayOpacity: 0 };

    let url = '';
    let overlayColor = '';
    let overlayOpacity = 0;

    const urlMatch = bgImage.match(/url\(["']?([^"')]+)["']?\)/);
    if (urlMatch) url = urlMatch[1];

    const gradMatch = bgImage.match(/linear-gradient\(\s*rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)/);
    if (gradMatch) {
        const r = parseInt(gradMatch[1]);
        const g = parseInt(gradMatch[2]);
        const b = parseInt(gradMatch[3]);
        overlayOpacity = parseFloat(gradMatch[4]);
        overlayColor = '#' + [r, g, b].map(n => n.toString(16).padStart(2, '0')).join('');
    }

    return { url, overlayColor, overlayOpacity };
}

// Compose backgroundImage value from url + optional overlay
function composeBgImage(url, overlayColor, overlayOpacity) {
    const hasOverlay = overlayOpacity > 0 && overlayColor;
    if (hasOverlay) {
        const { r, g, b } = hexToRgb(overlayColor);
        const rgba = `rgba(${r}, ${g}, ${b}, ${overlayOpacity})`;
        if (url) return `linear-gradient(${rgba}, ${rgba}), url('${url}')`;
        return `linear-gradient(${rgba}, ${rgba})`;
    }
    if (url) return `url('${url}')`;
    return '';
}

// --- Structure tab ---

function renderStructureTab() {
    const container = $('#ev2-tab-content');
    if (!container) return;

    const sections = getSections();
    if (sections.length === 0) {
        container.innerHTML = '<p class="ev2-placeholder ev2-empty-state">No sections found</p>';
        return;
    }

    const selectedSel = selectedEl ? getCssSelector(selectedEl) : null;
    let html = '<div class="ev2-tree">';

    for (const section of sections) {
        const sectionSel = getCssSelector(section) || '';
        const isCurrent = sectionSel === selectedSel;
        html += `<div class="ev2-tree-item${isCurrent ? ' current' : ''}" data-tree-selector="${esc(sectionSel)}">`;
        html += `<strong>${esc(getTagLabel(section))}</strong></div>`;

        // Show direct children with editable content
        for (const child of section.children) {
            const childSel = getCssSelector(child) || '';
            const isChildCurrent = childSel === selectedSel;
            const label = getTagLabel(child);
            html += `<div class="ev2-tree-item${isChildCurrent ? ' current' : ''}" data-tree-selector="${esc(childSel)}">`;
            html += `<span class="ev2-tree-indent"></span>${esc(label)}`;

            // Show text preview for text elements
            if (isTextElement(child)) {
                const preview = child.textContent.trim().slice(0, 30);
                if (preview) html += ` <span style="color:var(--ev2-text-faint)">${esc(preview)}${child.textContent.trim().length > 30 ? '...' : ''}</span>`;
            }
            html += '</div>';

            // One more level deep for key elements
            for (const grandchild of child.children) {
                if (!isTextElement(grandchild) && grandchild.tagName !== 'IMG' && grandchild.tagName !== 'A') continue;
                const gcSel = getCssSelector(grandchild) || '';
                const isGcCurrent = gcSel === selectedSel;
                html += `<div class="ev2-tree-item${isGcCurrent ? ' current' : ''}" data-tree-selector="${esc(gcSel)}">`;
                html += `<span class="ev2-tree-indent"></span><span class="ev2-tree-indent"></span>${esc(getTagLabel(grandchild))}`;
                if (isTextElement(grandchild)) {
                    const preview = grandchild.textContent.trim().slice(0, 25);
                    if (preview) html += ` <span style="color:var(--ev2-text-faint)">${esc(preview)}${grandchild.textContent.trim().length > 25 ? '...' : ''}</span>`;
                }
                html += '</div>';
            }
        }
    }
    html += '</div>';
    container.innerHTML = html;

    // Click handler for tree items
    container.addEventListener('click', onTreeClick);
}

function onTreeClick(e) {
    const item = e.target.closest('.ev2-tree-item');
    if (!item) return;
    const sel = item.dataset.treeSelector;
    if (!sel) return;
    const el = document.querySelector(sel);
    if (el) {
        events.emit('selection:request', el);
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
}

function renderActiveTab() {
    if (activeTab === 'content') renderContentTab();
    else if (activeTab === 'design') renderDesignTab();
    else if (activeTab === 'structure') renderStructureTab();
}

// --- Tab switching ---

function onTabClick(e) {
    const btn = e.target.closest('.ev2-tab[data-tab]');
    if (!btn) return;
    const tab = btn.dataset.tab;
    if (tab === activeTab) return;

    $$('.ev2-tab').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    activeTab = tab;
    renderActiveTab();
    events.emit('sidebar:tab-changed', tab);
}

// --- Selection handler ---

function onSelectionChanged(el) {
    selectedEl = el;
    renderActiveTab();
}

function onSwitchTab(tab) {
    const btn = $(`.ev2-tab[data-tab="${tab}"]`);
    if (!btn) return;
    $$('.ev2-tab').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    activeTab = tab;
    renderActiveTab();
    events.emit('sidebar:tab-changed', tab);
}

// --- Language bar ---

function onLangClick(e) {
    const btn = e.target.closest('.ev2-lang-btn');
    if (!btn || btn.classList.contains('active')) return;
    const lang = btn.dataset.lang;
    const url = new URL(window.location.href);
    url.pathname = url.pathname.replace(/^\/[a-z]{2}(\/|$)/, `/${lang}$1`);
    url.searchParams.set('edit', 'v2');
    window.location.href = url.toString();
}

// --- Save / Discard / Status ---

function onSaveClick() { events.emit('changes:save'); }
function onDiscardClick() { events.emit('changes:discard'); renderActiveTab(); }

function onChangesCount(count) {
    const saveBtn = $('#ev2-save-btn');
    const discardBtn = $('#ev2-discard-btn');
    const status = $('#ev2-status');
    const topSave = $('#ev2-save-topbar-btn');
    const badge = $('#ev2-change-count');

    if (saveBtn) saveBtn.disabled = count === 0;
    if (discardBtn) discardBtn.disabled = count === 0;
    if (status) status.textContent = count === 0 ? 'No changes' : `${count} change${count !== 1 ? 's' : ''}`;
    if (topSave) topSave.disabled = count === 0;
    if (badge) {
        badge.textContent = count;
        badge.classList.toggle('hidden', count === 0);
    }
}

function onChangesSaved() {
    const status = $('#ev2-status');
    if (status) {
        status.textContent = 'Saved';
        setTimeout(() => { status.textContent = 'No changes'; }, 2000);
    }
}

function onChangesError(msg) {
    const status = $('#ev2-status');
    if (status) {
        status.textContent = msg || 'Save failed';
        status.style.color = '#dc2626';
        setTimeout(() => { status.style.color = ''; }, 3000);
    }
}

function onUndoState({ canUndo, canRedo }) {
    const undoBtn = $('#ev2-undo-btn');
    const redoBtn = $('#ev2-redo-btn');
    if (undoBtn) undoBtn.disabled = !canUndo;
    if (redoBtn) redoBtn.disabled = !canRedo;
}

// --- Bind / Unbind helpers ---

function bindEl(selector, event, fn) {
    const el = $(selector);
    if (el) { el.addEventListener(event, fn); return el; }
    return null;
}

function unbindEl(selector, event, fn) {
    const el = $(selector);
    if (el) el.removeEventListener(event, fn);
}

// --- Lifecycle ---

export function init() {
    handlers.tabClick = onTabClick;
    handlers.langClick = onLangClick;
    handlers.saveClick = onSaveClick;
    handlers.discardClick = onDiscardClick;
    handlers.undoClick = () => events.emit('changes:undo');
    handlers.redoClick = () => events.emit('changes:redo');
    handlers.topbarSave = () => events.emit('changes:save');
    handlers.selectionChanged = onSelectionChanged;
    handlers.changesCount = onChangesCount;
    handlers.changesSaved = onChangesSaved;
    handlers.changesError = onChangesError;
    handlers.undoState = onUndoState;
    handlers.switchTab = onSwitchTab;

    // DOM event listeners
    bindEl('.ev2-tabs', 'click', handlers.tabClick);
    bindEl('.ev2-language-bar', 'click', handlers.langClick);
    bindEl('#ev2-save-btn', 'click', handlers.saveClick);
    bindEl('#ev2-discard-btn', 'click', handlers.discardClick);
    bindEl('#ev2-undo-btn', 'click', handlers.undoClick);
    bindEl('#ev2-redo-btn', 'click', handlers.redoClick);
    bindEl('#ev2-save-topbar-btn', 'click', handlers.topbarSave);

    // Event bus listeners
    events.on('selection:changed', handlers.selectionChanged);
    events.on('changes:count', handlers.changesCount);
    events.on('changes:saved', handlers.changesSaved);
    events.on('changes:error', handlers.changesError);
    events.on('changes:undo-state', handlers.undoState);
    events.on('sidebar:switch-tab', handlers.switchTab);

    renderActiveTab();
}

export function destroy() {
    unbindEl('.ev2-tabs', 'click', handlers.tabClick);
    unbindEl('.ev2-language-bar', 'click', handlers.langClick);
    unbindEl('#ev2-save-btn', 'click', handlers.saveClick);
    unbindEl('#ev2-discard-btn', 'click', handlers.discardClick);
    unbindEl('#ev2-undo-btn', 'click', handlers.undoClick);
    unbindEl('#ev2-redo-btn', 'click', handlers.redoClick);
    unbindEl('#ev2-save-topbar-btn', 'click', handlers.topbarSave);

    events.off('selection:changed', handlers.selectionChanged);
    events.off('changes:count', handlers.changesCount);
    events.off('changes:saved', handlers.changesSaved);
    events.off('changes:error', handlers.changesError);
    events.off('changes:undo-state', handlers.undoState);
    events.off('sidebar:switch-tab', handlers.switchTab);

    selectedEl = null;
    activeTab = 'content';
}
