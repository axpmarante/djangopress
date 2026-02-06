/**
 * Image Selection and Upload Module
 * Handles featured image and gallery image selection/upload for forms
 *
 * Requirements:
 * - Form must have featured_image and/or gallery_images fields
 * - API endpoint: /backoffice/api/upload-images/
 * - CSRF token in form
 */

// Featured Image Modal Functions
function openFeaturedImageModal() {
    document.getElementById('featuredImageModal').classList.remove('hidden');
    document.body.style.overflow = 'hidden';
}

function closeFeaturedImageModal() {
    document.getElementById('featuredImageModal').classList.add('hidden');
    document.body.style.overflow = 'auto';
}

function selectFeaturedImage(imageId, imageUrl, imageTitle) {
    // Get the form's featured image field (may have different IDs based on form)
    const selectField = document.querySelector('select[name="featured_image"]');
    if (!selectField) {
        console.error('Featured image select field not found');
        return;
    }

    selectField.value = imageId;

    // Update the preview display
    const displayDiv = document.getElementById('featured-image-display');
    if (displayDiv) {
        displayDiv.innerHTML = `
            <div class="relative inline-block">
                <img id="featured-preview" src="${imageUrl}" alt="${imageTitle}" class="w-64 h-40 object-cover rounded-lg shadow-md">
                <button type="button" onclick="clearFeaturedImage()" class="absolute top-2 right-2 bg-red-600 text-white rounded-full p-1 hover:bg-red-700 transition-colors">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                    </svg>
                </button>
            </div>
            <p id="featured-title" class="text-sm text-gray-600 mt-2">${imageTitle}</p>
        `;
    }

    // Close the modal
    closeFeaturedImageModal();
}

function clearFeaturedImage() {
    // Clear the hidden select field
    const selectField = document.querySelector('select[name="featured_image"]');
    if (selectField) {
        selectField.value = '';
    }

    // Update the preview display
    const displayDiv = document.getElementById('featured-image-display');
    if (displayDiv) {
        displayDiv.innerHTML = `
            <div class="w-64 h-40 bg-gray-100 rounded-lg flex items-center justify-center">
                <p class="text-gray-400 text-sm">No image selected</p>
            </div>
        `;
    }
}

function filterModalImages() {
    const searchTerm = document.getElementById('modal-search').value.toLowerCase();
    const items = document.querySelectorAll('.modal-image-item');

    items.forEach(item => {
        const searchText = item.dataset.searchText || '';
        if (searchText.includes(searchTerm)) {
            item.style.display = 'block';
        } else {
            item.style.display = 'none';
        }
    });
}

// Featured Image Upload Modal Functions
let selectedFeaturedFile = null;

function openFeaturedUploadModal() {
    document.getElementById('featuredUploadModal').classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    resetFeaturedUploadModal();
}

function closeFeaturedUploadModal() {
    document.getElementById('featuredUploadModal').classList.add('hidden');
    document.body.style.overflow = 'auto';
    resetFeaturedUploadModal();
}

function resetFeaturedUploadModal() {
    selectedFeaturedFile = null;
    const fileInput = document.getElementById('featured-file-upload');
    if (fileInput) fileInput.value = '';

    const previewDiv = document.getElementById('featured-upload-preview');
    if (previewDiv) previewDiv.classList.add('hidden');

    const previewContainer = document.getElementById('featured-preview-container');
    if (previewContainer) previewContainer.innerHTML = '';

    const progressDiv = document.getElementById('featured-upload-progress');
    if (progressDiv) progressDiv.classList.add('hidden');

    const statusDiv = document.getElementById('featured-upload-status');
    if (statusDiv) statusDiv.classList.add('hidden');

    const uploadButton = document.getElementById('featured-upload-button');
    if (uploadButton) uploadButton.disabled = true;

    const progressBar = document.getElementById('featured-progress-bar');
    if (progressBar) progressBar.style.width = '0%';

    const progressText = document.getElementById('featured-progress-text');
    if (progressText) progressText.textContent = '0%';
}

function handleFeaturedFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;

    selectedFeaturedFile = file;
    displayFeaturedPreview(file);

    const uploadButton = document.getElementById('featured-upload-button');
    if (uploadButton) uploadButton.disabled = false;
}

function displayFeaturedPreview(file) {
    const previewContainer = document.getElementById('featured-preview-container');
    if (!previewContainer) return;

    previewContainer.innerHTML = '';

    const previewDiv = document.getElementById('featured-upload-preview');
    if (previewDiv) previewDiv.classList.remove('hidden');

    const reader = new FileReader();
    reader.onload = function(e) {
        const div = document.createElement('div');
        div.className = 'relative';
        div.innerHTML = `
            <img src="${e.target.result}" alt="${file.name}" class="w-64 h-40 object-cover rounded-lg shadow-md">
            <p class="text-sm text-gray-600 mt-2 text-center">${file.name}</p>
        `;
        previewContainer.appendChild(div);
    };
    reader.readAsDataURL(file);
}

async function uploadFeaturedImage() {
    if (!selectedFeaturedFile) return;

    const uploadButton = document.getElementById('featured-upload-button');
    const progressDiv = document.getElementById('featured-upload-progress');
    const progressBar = document.getElementById('featured-progress-bar');
    const progressText = document.getElementById('featured-progress-text');
    const statusDiv = document.getElementById('featured-upload-status');

    // Disable button and show progress
    if (uploadButton) uploadButton.disabled = true;
    if (progressDiv) progressDiv.classList.remove('hidden');
    if (statusDiv) statusDiv.classList.add('hidden');

    const formData = new FormData();
    formData.append('images', selectedFeaturedFile);

    // Add CSRF token
    const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

    try {
        const response = await fetch('/backoffice/api/upload-images/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken,
            },
            body: formData
        });

        const data = await response.json();

        if (response.ok) {
            // Update progress to 100%
            if (progressBar) progressBar.style.width = '100%';
            if (progressText) progressText.textContent = '100%';

            // Show success message
            if (statusDiv) {
                statusDiv.innerHTML = `
                    <div class="bg-green-50 border-l-4 border-green-500 p-4 rounded">
                        <div class="flex">
                            <div class="flex-shrink-0">
                                <svg class="h-5 w-5 text-green-400" fill="currentColor" viewBox="0 0 20 20">
                                    <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
                                </svg>
                            </div>
                            <div class="ml-3">
                                <p class="text-sm text-green-700">
                                    Successfully uploaded and set as featured image!
                                    ${data.optimized_count > 0 ? '(optimized)' : ''}
                                </p>
                            </div>
                        </div>
                    </div>
                `;
                statusDiv.classList.remove('hidden');
            }

            // Set as featured image
            if (data.uploaded_images && data.uploaded_images.length > 0) {
                const image = data.uploaded_images[0];
                selectFeaturedImage(image.id, image.url, image.title);

                // Close modal and reload page
                setTimeout(() => {
                    closeFeaturedUploadModal();
                    location.reload();
                }, 1500);
            }
        } else {
            throw new Error(data.error || 'Upload failed');
        }
    } catch (error) {
        console.error('Upload error:', error);
        if (statusDiv) {
            statusDiv.innerHTML = `
                <div class="bg-red-50 border-l-4 border-red-500 p-4 rounded">
                    <div class="flex">
                        <div class="flex-shrink-0">
                            <svg class="h-5 w-5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
                                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/>
                            </svg>
                        </div>
                        <div class="ml-3">
                            <p class="text-sm text-red-700">Error uploading image: ${error.message}</p>
                        </div>
                    </div>
                </div>
            `;
            statusDiv.classList.remove('hidden');
        }
        if (uploadButton) uploadButton.disabled = false;
    }
}

// Gallery Images Modal Functions
let selectedGalleryImages = new Set();

function openGalleryModal() {
    document.getElementById('galleryImageModal').classList.remove('hidden');
    document.body.style.overflow = 'hidden';

    // Initialize selected images from current state
    selectedGalleryImages.clear();
    document.querySelectorAll('#gallery-checkboxes-container input[type="checkbox"]:checked').forEach(checkbox => {
        selectedGalleryImages.add(parseInt(checkbox.value));
    });

    // Update visual state in modal
    updateGalleryModalVisuals();
    updateSelectedCount();
}

function closeGalleryModal() {
    document.getElementById('galleryImageModal').classList.add('hidden');
    document.body.style.overflow = 'auto';
}

function toggleGalleryImage(imageId, imageUrl, imageTitle) {
    if (selectedGalleryImages.has(imageId)) {
        selectedGalleryImages.delete(imageId);
    } else {
        selectedGalleryImages.add(imageId);
    }

    // Update visual feedback in modal
    const item = document.querySelector(`.gallery-modal-image-item[data-image-id="${imageId}"]`);
    if (item) {
        const border = item.querySelector('.gallery-item-border');
        const checkmark = item.querySelector('.gallery-item-checkmark');

        if (selectedGalleryImages.has(imageId)) {
            if (border) {
                border.classList.add('border-blue-500', 'shadow-lg');
                border.classList.remove('border-gray-300');
            }
            if (checkmark) checkmark.classList.remove('hidden');
        } else {
            if (border) {
                border.classList.remove('border-blue-500', 'shadow-lg');
                border.classList.add('border-gray-300');
            }
            if (checkmark) checkmark.classList.add('hidden');
        }
    }

    updateSelectedCount();
}

function updateGalleryModalVisuals() {
    document.querySelectorAll('.gallery-modal-image-item').forEach(item => {
        const imageId = parseInt(item.dataset.imageId);
        const border = item.querySelector('.gallery-item-border');
        const checkmark = item.querySelector('.gallery-item-checkmark');

        if (selectedGalleryImages.has(imageId)) {
            if (border) {
                border.classList.add('border-blue-500', 'shadow-lg');
                border.classList.remove('border-gray-300');
            }
            if (checkmark) checkmark.classList.remove('hidden');
        } else {
            if (border) {
                border.classList.remove('border-blue-500', 'shadow-lg');
                border.classList.add('border-gray-300');
            }
            if (checkmark) checkmark.classList.add('hidden');
        }
    });
}

function updateSelectedCount() {
    const countElement = document.getElementById('selected-count');
    if (countElement) {
        countElement.textContent = selectedGalleryImages.size;
    }
}

function clearAllGallerySelections() {
    selectedGalleryImages.clear();
    updateGalleryModalVisuals();
    updateSelectedCount();
}

function applyGallerySelection() {
    // Update the hidden checkboxes
    document.querySelectorAll('#gallery-checkboxes-container input[type="checkbox"]').forEach(checkbox => {
        const imageId = parseInt(checkbox.value);
        checkbox.checked = selectedGalleryImages.has(imageId);
    });

    // Update the display
    updateGalleryDisplay();

    // Close the modal
    closeGalleryModal();
}

function updateGalleryDisplay() {
    const displayDiv = document.getElementById('selected-gallery-display');
    if (!displayDiv) return;

    if (selectedGalleryImages.size === 0) {
        displayDiv.innerHTML = `
            <div class="text-center py-8 bg-gray-50 rounded-lg border-2 border-dashed border-gray-300">
                <svg class="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/>
                </svg>
                <p class="text-gray-400 text-sm mt-2">No gallery images selected</p>
            </div>
        `;
        return;
    }

    let html = '<div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">';

    selectedGalleryImages.forEach(imageId => {
        const modalItem = document.querySelector(`.gallery-modal-image-item[data-image-id="${imageId}"]`);
        if (modalItem) {
            const imageUrl = modalItem.dataset.imageUrl;
            const imageTitle = modalItem.dataset.imageTitle;

            html += `
                <div class="selected-gallery-item relative group" data-image-id="${imageId}">
                    <img src="${imageUrl}" alt="${imageTitle}" class="w-full h-24 object-cover rounded-lg shadow">
                    <button type="button" onclick="removeGalleryImage(${imageId})" class="absolute top-1 right-1 bg-red-600 text-white rounded-full p-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                        </svg>
                    </button>
                    <p class="text-xs text-gray-600 mt-1 truncate" title="${imageTitle}">${imageTitle}</p>
                </div>
            `;
        }
    });

    html += '</div>';
    displayDiv.innerHTML = html;
}

function removeGalleryImage(imageId) {
    // Remove from the set
    selectedGalleryImages.delete(imageId);

    // Update the hidden checkbox
    const checkbox = document.querySelector(`#gallery-checkboxes-container input[value="${imageId}"]`);
    if (checkbox) {
        checkbox.checked = false;
    }

    // Update the display
    updateGalleryDisplay();
}

function filterGalleryModalImages() {
    const searchTerm = document.getElementById('gallery-modal-search').value.toLowerCase();
    const items = document.querySelectorAll('.gallery-modal-image-item');

    items.forEach(item => {
        const searchText = item.dataset.searchText || '';
        if (searchText.includes(searchTerm)) {
            item.style.display = 'block';
        } else {
            item.style.display = 'none';
        }
    });
}

// Gallery Upload Modal Functions
let selectedFiles = [];

function openUploadModal() {
    document.getElementById('uploadImageModal').classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    resetUploadModal();
}

function closeUploadModal() {
    document.getElementById('uploadImageModal').classList.add('hidden');
    document.body.style.overflow = 'auto';
    resetUploadModal();
}

function resetUploadModal() {
    selectedFiles = [];
    const fileInput = document.getElementById('file-upload');
    if (fileInput) fileInput.value = '';

    const previewDiv = document.getElementById('upload-preview');
    if (previewDiv) previewDiv.classList.add('hidden');

    const previewGrid = document.getElementById('preview-grid');
    if (previewGrid) previewGrid.innerHTML = '';

    const progressDiv = document.getElementById('upload-progress');
    if (progressDiv) progressDiv.classList.add('hidden');

    const statusDiv = document.getElementById('upload-status');
    if (statusDiv) statusDiv.classList.add('hidden');

    const uploadButton = document.getElementById('upload-button');
    if (uploadButton) uploadButton.disabled = true;

    const progressBar = document.getElementById('progress-bar');
    if (progressBar) progressBar.style.width = '0%';

    const progressText = document.getElementById('progress-text');
    if (progressText) progressText.textContent = '0%';
}

function handleFileSelect(event) {
    const files = Array.from(event.target.files);
    if (files.length === 0) return;

    selectedFiles = files;
    displayPreview(files);

    const uploadButton = document.getElementById('upload-button');
    if (uploadButton) uploadButton.disabled = false;
}

function displayPreview(files) {
    const previewGrid = document.getElementById('preview-grid');
    if (!previewGrid) return;

    previewGrid.innerHTML = '';

    const previewDiv = document.getElementById('upload-preview');
    if (previewDiv) previewDiv.classList.remove('hidden');

    files.forEach((file, index) => {
        const reader = new FileReader();
        reader.onload = function(e) {
            const div = document.createElement('div');
            div.className = 'relative group';
            div.innerHTML = `
                <img src="${e.target.result}" alt="${file.name}" class="w-full h-24 object-cover rounded-lg shadow">
                <button type="button" onclick="removeFileFromSelection(${index})" class="absolute top-1 right-1 bg-red-600 text-white rounded-full p-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                    </svg>
                </button>
                <p class="text-xs text-gray-600 mt-1 truncate" title="${file.name}">${file.name}</p>
            `;
            previewGrid.appendChild(div);
        };
        reader.readAsDataURL(file);
    });
}

function removeFileFromSelection(index) {
    selectedFiles.splice(index, 1);
    const uploadPreviewDiv = document.getElementById('upload-preview');
    const uploadButton = document.getElementById('upload-button');

    if (selectedFiles.length === 0) {
        if (uploadPreviewDiv) uploadPreviewDiv.classList.add('hidden');
        if (uploadButton) uploadButton.disabled = true;
    } else {
        displayPreview(selectedFiles);
    }
}

async function uploadImages() {
    if (selectedFiles.length === 0) return;

    const uploadButton = document.getElementById('upload-button');
    const progressDiv = document.getElementById('upload-progress');
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress-text');
    const statusDiv = document.getElementById('upload-status');

    // Disable button and show progress
    if (uploadButton) uploadButton.disabled = true;
    if (progressDiv) progressDiv.classList.remove('hidden');
    if (statusDiv) statusDiv.classList.add('hidden');

    const formData = new FormData();
    selectedFiles.forEach((file, index) => {
        formData.append('images', file);
    });

    // Add CSRF token
    const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

    try {
        const response = await fetch('/backoffice/api/upload-images/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken,
            },
            body: formData
        });

        const data = await response.json();

        if (response.ok) {
            // Update progress to 100%
            if (progressBar) progressBar.style.width = '100%';
            if (progressText) progressText.textContent = '100%';

            // Show success message
            if (statusDiv) {
                statusDiv.innerHTML = `
                    <div class="bg-green-50 border-l-4 border-green-500 p-4 rounded">
                        <div class="flex">
                            <div class="flex-shrink-0">
                                <svg class="h-5 w-5 text-green-400" fill="currentColor" viewBox="0 0 20 20">
                                    <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
                                </svg>
                            </div>
                            <div class="ml-3">
                                <p class="text-sm text-green-700">
                                    Successfully uploaded ${data.uploaded_count} image(s)!
                                    ${data.optimized_count > 0 ? `(${data.optimized_count} optimized)` : ''}
                                </p>
                            </div>
                        </div>
                    </div>
                `;
                statusDiv.classList.remove('hidden');
            }

            // Add uploaded images to gallery selection
            if (data.uploaded_images && data.uploaded_images.length > 0) {
                data.uploaded_images.forEach(image => {
                    selectedGalleryImages.add(image.id);

                    // Update the checkbox
                    const checkbox = document.querySelector(`#gallery-checkboxes-container input[value="${image.id}"]`);
                    if (checkbox) {
                        checkbox.checked = true;
                    }
                });

                // Update the gallery display
                updateGalleryDisplay();

                // Reload the page to refresh the image library in modals
                setTimeout(() => {
                    location.reload();
                }, 1500);
            }
        } else {
            throw new Error(data.error || 'Upload failed');
        }
    } catch (error) {
        console.error('Upload error:', error);
        if (statusDiv) {
            statusDiv.innerHTML = `
                <div class="bg-red-50 border-l-4 border-red-500 p-4 rounded">
                    <div class="flex">
                        <div class="flex-shrink-0">
                            <svg class="h-5 w-5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
                                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/>
                            </svg>
                        </div>
                        <div class="ml-3">
                            <p class="text-sm text-red-700">Error uploading images: ${error.message}</p>
                        </div>
                    </div>
                </div>
            `;
            statusDiv.classList.remove('hidden');
        }
        if (uploadButton) uploadButton.disabled = false;
    }
}

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', function() {
    // Featured image drop zone
    const featuredDropZone = document.getElementById('featured-drop-zone');
    if (featuredDropZone) {
        featuredDropZone.addEventListener('click', function() {
            document.getElementById('featured-file-upload').click();
        });

        featuredDropZone.addEventListener('dragover', function(e) {
            e.preventDefault();
            e.stopPropagation();
            this.classList.add('border-blue-500', 'bg-blue-50');
        });

        featuredDropZone.addEventListener('dragleave', function(e) {
            e.preventDefault();
            e.stopPropagation();
            this.classList.remove('border-blue-500', 'bg-blue-50');
        });

        featuredDropZone.addEventListener('drop', function(e) {
            e.preventDefault();
            e.stopPropagation();
            this.classList.remove('border-blue-500', 'bg-blue-50');

            const files = Array.from(e.dataTransfer.files).filter(file => file.type.startsWith('image/'));
            if (files.length > 0) {
                const fileInput = document.getElementById('featured-file-upload');
                const dataTransfer = new DataTransfer();
                dataTransfer.items.add(files[0]); // Only take first file
                fileInput.files = dataTransfer.files;

                handleFeaturedFileSelect({ target: fileInput });
            }
        });
    }

    // Gallery images drop zone
    const dropZone = document.getElementById('drop-zone');
    if (dropZone) {
        dropZone.addEventListener('click', function() {
            document.getElementById('file-upload').click();
        });

        dropZone.addEventListener('dragover', function(e) {
            e.preventDefault();
            e.stopPropagation();
            this.classList.add('border-blue-500', 'bg-blue-50');
        });

        dropZone.addEventListener('dragleave', function(e) {
            e.preventDefault();
            e.stopPropagation();
            this.classList.remove('border-blue-500', 'bg-blue-50');
        });

        dropZone.addEventListener('drop', function(e) {
            e.preventDefault();
            e.stopPropagation();
            this.classList.remove('border-blue-500', 'bg-blue-50');

            const files = Array.from(e.dataTransfer.files).filter(file => file.type.startsWith('image/'));
            if (files.length > 0) {
                const fileInput = document.getElementById('file-upload');
                const dataTransfer = new DataTransfer();
                files.forEach(file => dataTransfer.items.add(file));
                fileInput.files = dataTransfer.files;

                handleFileSelect({ target: fileInput });
            }
        });
    }

    // Close modals when clicking outside
    const modals = [
        { id: 'featuredImageModal', closeFunc: closeFeaturedImageModal },
        { id: 'featuredUploadModal', closeFunc: closeFeaturedUploadModal },
        { id: 'galleryImageModal', closeFunc: closeGalleryModal },
        { id: 'uploadImageModal', closeFunc: closeUploadModal }
    ];

    modals.forEach(modal => {
        const element = document.getElementById(modal.id);
        if (element) {
            element.addEventListener('click', function(e) {
                if (e.target === this) {
                    modal.closeFunc();
                }
            });
        }
    });

    // Close modals with Escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            const featuredModal = document.getElementById('featuredImageModal');
            const featuredUploadModal = document.getElementById('featuredUploadModal');
            const galleryModal = document.getElementById('galleryImageModal');
            const uploadModal = document.getElementById('uploadImageModal');

            if (featuredModal && !featuredModal.classList.contains('hidden')) {
                closeFeaturedImageModal();
            } else if (featuredUploadModal && !featuredUploadModal.classList.contains('hidden')) {
                closeFeaturedUploadModal();
            } else if (galleryModal && !galleryModal.classList.contains('hidden')) {
                closeGalleryModal();
            } else if (uploadModal && !uploadModal.classList.contains('hidden')) {
                closeUploadModal();
            }
        }
    });

    // Initialize gallery display on page load
    selectedGalleryImages.clear();
    document.querySelectorAll('#gallery-checkboxes-container input[type="checkbox"]:checked').forEach(checkbox => {
        selectedGalleryImages.add(parseInt(checkbox.value));
    });
});
