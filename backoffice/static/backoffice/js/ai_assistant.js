/**
 * AI Assistant JavaScript
 * Handles AI content generation, preview, and saving
 */

// Global state
let currentGenerationType = 'section';
let generatedData = null;
let currentPageSlug = null;

/**
 * Initialize AI Assistant
 */
function initAIAssistant(pageSlug = null) {
    currentPageSlug = pageSlug;

    // Load pages for dropdown
    loadPagesDropdown();

    // Load sections for refine dropdown if we have a page
    if (pageSlug) {
        loadSectionsForRefine(pageSlug);
    }
}

/**
 * Open AI Modal
 */
function openAIModal(type = 'section', pageSlug = null) {
    currentGenerationType = type;
    currentPageSlug = pageSlug;

    document.getElementById('aiModal').style.display = 'block';
    document.getElementById('aiModal').classList.remove('hidden');

    // Switch to appropriate tab
    switchAITab(type);

    // Set page slug if provided
    if (pageSlug && document.getElementById('pageSlug')) {
        document.getElementById('pageSlug').value = pageSlug;
    }

    // Reset form
    resetAIModal();
}

/**
 * Close AI Modal
 */
function closeAIModal() {
    document.getElementById('aiModal').style.display = 'none';
    document.getElementById('aiModal').classList.add('hidden');
    resetAIModal();
}

/**
 * Reset AI Modal
 */
function resetAIModal() {
    // Clear forms
    document.getElementById('briefPage').value = '';
    document.getElementById('briefSection').value = '';
    document.getElementById('refineInstructions').value = '';

    // Reset generated data
    generatedData = null;

    // Hide preview and error
    document.getElementById('aiPreview').classList.add('hidden');
    document.getElementById('aiError').classList.add('hidden');
    document.getElementById('aiLoading').classList.add('hidden');

    // Show/hide buttons
    document.getElementById('btnGenerate').classList.remove('hidden');
    document.getElementById('btnSave').classList.add('hidden');
}

/**
 * Switch AI Tab
 */
function switchAITab(type) {
    currentGenerationType = type;

    // Update tab styling
    ['page', 'section', 'refine'].forEach(t => {
        const tab = document.getElementById('tab' + t.charAt(0).toUpperCase() + t.slice(1));
        const form = document.getElementById('form' + t.charAt(0).toUpperCase() + t.slice(1));

        if (t === type) {
            tab.classList.remove('text-gray-600', 'border-transparent');
            tab.classList.add('text-blue-600', 'border-blue-500');
            form.classList.remove('hidden');
        } else {
            tab.classList.remove('text-blue-600', 'border-blue-500');
            tab.classList.add('text-gray-600', 'border-transparent');
            form.classList.add('hidden');
        }
    });

    resetAIModal();
}

/**
 * Load pages dropdown
 */
async function loadPagesDropdown() {
    try {
        const response = await fetch('/backoffice/pages/', {
            headers: {
                'Accept': 'application/json'
            }
        });

        // Note: This assumes you'll add a JSON response option to the pages view
        // For now, we'll populate from the current page context if available
        // You may need to create an API endpoint for this

    } catch (error) {
        console.error('Error loading pages:', error);
    }
}

/**
 * Load sections for refine dropdown
 */
async function loadSectionsForRefine(pageSlug) {
    if (!pageSlug) return;

    const selectEl = document.getElementById('refineSectionId');
    // Populate from current page context
    // This would ideally come from an API endpoint
}

/**
 * Get CSRF Token
 */
function getCSRFToken() {
    return document.querySelector('[name=csrfmiddlewaretoken]')?.value ||
           document.cookie.split('; ').find(row => row.startsWith('csrftoken='))?.split('=')[1];
}

/**
 * Generate Content
 */
async function generateContent() {
    const type = currentGenerationType;

    // Show loading
    document.getElementById('aiForm').classList.add('hidden');
    document.getElementById('aiLoading').classList.remove('hidden');
    document.getElementById('btnGenerate').classList.add('hidden');
    document.getElementById('aiError').classList.add('hidden');

    try {
        let endpoint, data;

        if (type === 'page') {
            endpoint = '/ai/api/generate-page/';
            data = {
                brief: document.getElementById('briefPage').value,
                page_type: 'general',  // Default value, backend will handle appropriately
                language: 'pt'  // Use site default language (Portuguese)
            };
        } else if (type === 'section') {
            endpoint = '/ai/api/generate-section/';
            data = {
                brief: document.getElementById('briefSection').value,
                section_type: document.getElementById('sectionType').value || null,
                page_slug: currentPageSlug || document.getElementById('pageSlug')?.value || null,
                insert_position: document.getElementById('insertPosition').value ? parseInt(document.getElementById('insertPosition').value) : null,
                language: 'pt'  // Use site default language (Portuguese)
            };
        } else if (type === 'refine') {
            endpoint = '/ai/api/refine-section/';
            data = {
                section_id: parseInt(document.getElementById('refineSectionId').value),
                instructions: document.getElementById('refineInstructions').value,
                language: 'pt'  // Use site default language (Portuguese)
            };
        }

        const response = await fetch(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (result.success) {
            generatedData = result;
            displayPreview(result, type);
        } else {
            showError(result.error || 'Failed to generate content');
        }

    } catch (error) {
        console.error('Generation error:', error);
        showError('An error occurred: ' + error.message);
    } finally {
        document.getElementById('aiLoading').classList.add('hidden');
        document.getElementById('aiForm').classList.remove('hidden');
    }
}

/**
 * Display Preview
 */
function displayPreview(result, type) {
    const previewEl = document.getElementById('previewContent');
    let html = '';
    let sections = [];

    if (type === 'page') {
        html = '<div class="space-y-6">';
        html += `<div class="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
                    <p class="text-sm text-blue-800"><strong>Generated ${result.count} sections</strong></p>
                 </div>`;

        result.sections.forEach((section, index) => {
            html += renderSectionPreview(section, index);
            sections.push({ section, index });
        });
        html += '</div>';

    } else if (type === 'section' || type === 'refine') {
        const section = result.section || result.sections[0];
        html = renderSectionPreview(section, 0);
        sections.push({ section, index: 0 });
    }

    previewEl.innerHTML = html;

    // After DOM is updated, render live previews
    setTimeout(() => {
        sections.forEach(({ section, index }) => {
            renderLivePreview(index, section);

            // Create tab switching function
            window['switchPreviewTab_' + index] = function(tab) {
                ['live', 'html', 'data'].forEach(t => {
                    const btn = document.getElementById('previewTab_' + index + '_' + t);
                    const content = document.getElementById('previewTabContent_' + index + '_' + t);
                    if (btn && content) {
                        if (t === tab) {
                            btn.className = 'preview-tab-active px-4 py-2 text-sm font-medium border-b-2 border-blue-500 text-blue-600';
                            content.classList.remove('hidden');
                        } else {
                            btn.className = 'preview-tab-inactive px-4 py-2 text-sm font-medium text-gray-600 hover:text-gray-800';
                            content.classList.add('hidden');
                        }
                    }
                });
            };
        });
    }, 100);

    // Show preview and save button
    document.getElementById('aiPreview').classList.remove('hidden');
    document.getElementById('btnSave').classList.remove('hidden');
}

/**
 * Render Section Preview
 */
function renderSectionPreview(section, index) {
    const ptContent = section.content?.translations?.pt || {};
    const enContent = section.content?.translations?.en || {};

    let html = `
        <div class="bg-white border border-gray-200 rounded-lg p-6 mb-4">
            <div class="flex items-center justify-between mb-4">
                <div class="flex items-center">
                    <span class="px-3 py-1 text-xs font-medium rounded-full bg-blue-100 text-blue-800 mr-3">
                        ${section.section_type}
                    </span>
                    <span class="text-sm text-gray-600">Order: ${section.order}</span>
                </div>
                <span class="text-xs font-mono text-gray-500">${section.key}</span>
            </div>

            <div class="space-y-4">
                <!-- Portuguese Content -->
                <div class="border-l-4 border-blue-500 pl-4">
                    <p class="text-xs font-semibold text-gray-500 uppercase mb-2">🇵🇹 Portuguese</p>
                    ${ptContent.title ? `<h4 class="text-lg font-bold text-gray-900 mb-1">${ptContent.title}</h4>` : ''}
                    ${ptContent.subtitle ? `<p class="text-sm text-gray-600 mb-2">${ptContent.subtitle}</p>` : ''}
                    ${ptContent.description ? `<p class="text-sm text-gray-700">${ptContent.description.substring(0, 200)}${ptContent.description.length > 200 ? '...' : ''}</p>` : ''}
                    ${ptContent.button_text ? `<button class="mt-2 px-4 py-2 bg-blue-600 text-white text-sm rounded">${ptContent.button_text}</button>` : ''}
                </div>

                <!-- English Content -->
                <div class="border-l-4 border-green-500 pl-4">
                    <p class="text-xs font-semibold text-gray-500 uppercase mb-2">🇬🇧 English</p>
                    ${enContent.title ? `<h4 class="text-lg font-bold text-gray-900 mb-1">${enContent.title}</h4>` : ''}
                    ${enContent.subtitle ? `<p class="text-sm text-gray-600 mb-2">${enContent.subtitle}</p>` : ''}
                    ${enContent.description ? `<p class="text-sm text-gray-700">${enContent.description.substring(0, 200)}${enContent.description.length > 200 ? '...' : ''}</p>` : ''}
                    ${enContent.button_text ? `<button class="mt-2 px-4 py-2 bg-green-600 text-white text-sm rounded">${enContent.button_text}</button>` : ''}
                </div>

                <!-- Live Preview / HTML Tabs -->
                <div class="bg-gray-50 rounded overflow-hidden">
                    <!-- Tab Headers -->
                    <div class="flex border-b border-gray-200">
                        <button onclick="switchPreviewTab_${index}('live')"
                                id="previewTab_${index}_live"
                                class="preview-tab-active px-4 py-2 text-sm font-medium border-b-2 border-blue-500 text-blue-600">
                            Live Preview
                        </button>
                        <button onclick="switchPreviewTab_${index}('html')"
                                id="previewTab_${index}_html"
                                class="preview-tab-inactive px-4 py-2 text-sm font-medium text-gray-600 hover:text-gray-800">
                            HTML Template
                        </button>
                        <button onclick="switchPreviewTab_${index}('data')"
                                id="previewTab_${index}_data"
                                class="preview-tab-inactive px-4 py-2 text-sm font-medium text-gray-600 hover:text-gray-800">
                            Design & Settings
                        </button>
                    </div>

                    <!-- Tab Content -->
                    <div id="previewTabContent_${index}_live" class="preview-tab-content p-4">
                        <div id="livePreview_${index}" class="border border-gray-300 rounded bg-white">
                            <div class="text-center py-8 text-gray-500">
                                <svg class="animate-spin h-8 w-8 text-blue-600 mx-auto mb-2" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                </svg>
                                Rendering preview...
                            </div>
                        </div>
                    </div>

                    <div id="previewTabContent_${index}_html" class="preview-tab-content hidden p-4">
                        ${section.html_template ? `
                            <pre class="text-xs text-gray-600 overflow-x-auto whitespace-pre-wrap bg-gray-900 text-green-400 p-3 rounded">${escapeHtml(section.html_template)}</pre>
                        ` : '<p class="text-gray-500 text-sm">No HTML template</p>'}
                    </div>

                    <div id="previewTabContent_${index}_data" class="preview-tab-content hidden p-4 space-y-2">
                        <div class="bg-blue-50 border border-blue-200 rounded p-3 mb-3">
                            <p class="text-xs font-semibold text-blue-900">ℹ️ Simplified Architecture</p>
                            <p class="text-xs text-blue-700 mt-1">Classes and URLs are now inline in the HTML template. Only translatable content is stored in JSON.</p>
                        </div>
                        <div>
                            <p class="text-xs font-semibold text-gray-700">Content (Translations):</p>
                            <pre class="text-xs text-gray-600 bg-white p-2 rounded border">${JSON.stringify(section.content, null, 2)}</pre>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;

    return html;
}

/**
 * Render live preview of a section
 */
function renderLivePreview(index, section) {
    const container = document.getElementById('livePreview_' + index);
    if (!container) return;

    try {
        // Create a simple template renderer
        let html = section.html_template || '<p class="p-4 text-gray-500">No HTML template available</p>';

        // Get the primary language content
        const trans = section.content?.translations?.pt || section.content?.translations?.en || {};

        // Replace template variables with actual content
        html = html.replace(/\{\{trans\.(\w+)\}\}/g, (match, field) => {
            return trans[field] || '';
        });

        // Replace section.id (use placeholder)
        html = html.replace(/\{\{section\.id\}\}/g, 'preview');

        // Replace LANGUAGE_CODE
        html = html.replace(/\{\{LANGUAGE_CODE\}\}/g, 'pt');

        // Handle simple {% for %} loops (basic support)
        html = html.replace(/\{% for (\w+) in trans\.(\w+) %\}([\s\S]*?)\{% endfor %\}/g, (match, itemVar, arrayName, loopContent) => {
            const array = trans[arrayName];
            if (!Array.isArray(array)) return '';

            return array.map(item => {
                let itemHtml = loopContent;
                // Replace {{item.field}} with actual values
                itemHtml = itemHtml.replace(new RegExp(`\\{\\{${itemVar}\\.(\\w+)\\}\\}`, 'g'), (m, field) => {
                    return item[field] || '';
                });
                return itemHtml;
            }).join('');
        });

        // Handle {% if %} conditionals (basic support)
        html = html.replace(/\{% if ([^%]+) %\}([\s\S]*?)\{% else %\}([\s\S]*?)\{% endif %\}/g, (match, condition, ifContent, elseContent) => {
            // Basic evaluation - since design/settings are removed, just return ifContent
            // In real rendering, Django will evaluate the condition properly
            return ifContent;
        });

        html = html.replace(/\{% if ([^%]+) %\}([\s\S]*?)\{% endif %\}/g, (match, condition, content) => {
            // Very basic - just return the content for now
            return content;
        });

        container.innerHTML = html;
    } catch (error) {
        console.error('Error rendering live preview:', error);
        container.innerHTML = `<div class="p-4 text-red-600">Error rendering preview: ${error.message}</div>`;
    }
}

/**
 * Escape HTML for display
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Show Error
 */
function showError(message) {
    const errorEl = document.getElementById('aiError');
    errorEl.textContent = message;
    errorEl.classList.remove('hidden');
    document.getElementById('btnGenerate').classList.remove('hidden');
}

/**
 * Regenerate Content
 */
function regenerateContent() {
    document.getElementById('aiPreview').classList.add('hidden');
    document.getElementById('btnSave').classList.add('hidden');
    document.getElementById('btnGenerate').classList.remove('hidden');
    generatedData = null;
}

/**
 * Save Generated Content
 */
async function saveGeneratedContent() {
    if (!generatedData) {
        showError('No content to save');
        return;
    }

    const type = currentGenerationType;

    // Show loading on save button
    const saveBtn = document.getElementById('btnSave');
    saveBtn.disabled = true;
    saveBtn.innerHTML = '<svg class="animate-spin h-5 w-5 text-white inline" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg> Saving...';

    try {
        let endpoint, data;

        if (type === 'page') {
            // Prompt for page slug and title
            const slug = prompt('Enter page slug (URL):');
            const title = prompt('Enter page title:');

            if (!slug || !title) {
                throw new Error('Page slug and title are required');
            }

            endpoint = '/ai/api/save-page/';
            data = {
                slug: slug,
                title: title,
                sections: generatedData.sections
            };
        } else if (type === 'section') {
            const pageSlugToSave = currentPageSlug || document.getElementById('pageSlug')?.value;

            if (!pageSlugToSave) {
                throw new Error('Page slug is required');
            }

            endpoint = '/ai/api/save-section/';
            data = {
                page_slug: pageSlugToSave,
                section: generatedData.section
            };
        } else if (type === 'refine') {
            const sectionId = document.getElementById('refineSectionId').value;

            endpoint = '/ai/api/update-section/';
            data = {
                section_id: parseInt(sectionId),
                section_data: generatedData.section
            };
        }

        const response = await fetch(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (result.success) {
            // Success! Close modal and reload page
            alert('Content saved successfully!');
            closeAIModal();
            window.location.reload();
        } else {
            showError(result.error || 'Failed to save content');
        }

    } catch (error) {
        console.error('Save error:', error);
        showError('An error occurred: ' + error.message);
    } finally {
        saveBtn.disabled = false;
        saveBtn.innerHTML = 'Save to Database';
    }
}

// Close modal on ESC key
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        closeAIModal();
    }
});

// Close modal when clicking outside
document.addEventListener('DOMContentLoaded', function() {
    const modal = document.getElementById('aiModal');
    if (modal) {
        modal.addEventListener('click', function(e) {
            if (e.target === this) {
                closeAIModal();
            }
        });
    }
});
