/**
 * Image Selection Modal for Frontend Builder
 * Handles image selection and upload functionality
 */

// Global state
let selectedImageData = null;
let currentElement = null;
let selectedFile = null;

/**
 * Public API for Simple Editor - Defined early to ensure availability
 */
window.ImageModal = {
    open: function(callback) {
        if (!callback || typeof callback !== 'function') {
            console.error('ImageModal.open requires a callback function');
            return;
        }

        console.log('🎯 ImageModal.open called');

        // Store the callback
        this._callback = callback;

        // Open the modal
        const modal = document.getElementById('builderImageModal');
        if (!modal) {
            console.error('Image modal not found in DOM');
            return;
        }

        modal.classList.remove('hidden');

        // Load images
        if (typeof loadBuilderImages === 'function') {
            loadBuilderImages();
        }

        // Switch to select tab
        if (typeof switchImageModalTab === 'function') {
            switchImageModalTab('select');
        }

        // Override the apply function to use our callback
        window._originalApplyBuilderImageSelection = window.applyBuilderImageSelection;
        window.applyBuilderImageSelection = () => {
            if (selectedImageData && this._callback) {
                // Call the callback with the selected image URL
                this._callback(selectedImageData.url);

                // Close modal
                if (typeof closeBuilderImageModal === 'function') {
                    closeBuilderImageModal();
                }

                // Restore original function
                if (window._originalApplyBuilderImageSelection) {
                    window.applyBuilderImageSelection = window._originalApplyBuilderImageSelection;
                }
            }
        };

        console.log('✅ Image modal opened');
    },

    close: function() {
        if (typeof closeBuilderImageModal === 'function') {
            closeBuilderImageModal();
        }
    }
};

console.log('✅ ImageModal API initialized at top of file');

/**
 * Open the image modal
 */
function openBuilderImageModal(element) {
    currentElement = element;
    selectedImageData = null;
    selectedFile = null;

    const modal = document.getElementById('builderImageModal');
    modal.classList.remove('hidden');

    // Load images from API
    loadBuilderImages();

    // Switch to select tab by default
    switchImageModalTab('select');
}

/**
 * Close the image modal
 */
function closeBuilderImageModal() {
    const modal = document.getElementById('builderImageModal');
    modal.classList.add('hidden');
    currentElement = null;
    selectedImageData = null;
    selectedFile = null;
}

/**
 * Switch between modal tabs
 */
function switchImageModalTab(tabName) {
    // Update tab buttons
    document.querySelectorAll('.image-modal-tab').forEach(btn => {
        if (btn.dataset.tab === tabName) {
            btn.classList.add('active', 'border-blue-600', 'text-blue-600');
            btn.classList.remove('border-transparent', 'text-gray-500');
        } else {
            btn.classList.remove('active', 'border-blue-600', 'text-blue-600');
            btn.classList.add('border-transparent', 'text-gray-500');
        }
    });

    // Update tab content
    document.querySelectorAll('.image-modal-tab-content').forEach(content => {
        content.classList.add('hidden');
    });

    if (tabName === 'select') {
        document.getElementById('selectImageTab').classList.remove('hidden');
        document.getElementById('builderSelectBtn').classList.remove('hidden');
        document.getElementById('builderUploadBtn').classList.add('hidden');
    } else if (tabName === 'upload') {
        document.getElementById('uploadImageTab').classList.remove('hidden');
        document.getElementById('builderSelectBtn').classList.add('hidden');
        document.getElementById('builderUploadBtn').classList.remove('hidden');
    }
}

/**
 * Load images from API
 */
async function loadBuilderImages() {
    const loading = document.getElementById('builderImagesLoading');
    const grid = document.getElementById('builderImageGrid');
    const empty = document.getElementById('builderImagesEmpty');

    loading.classList.remove('hidden');
    grid.classList.add('hidden');
    empty.classList.add('hidden');

    try {
        const response = await fetch('/editor/api/images/');
        const data = await response.json();

        if (data.success && data.images.length > 0) {
            renderBuilderImages(data.images);
            grid.classList.remove('hidden');
        } else {
            empty.classList.remove('hidden');
        }
    } catch (error) {
        console.error('Error loading images:', error);
        empty.classList.remove('hidden');
    } finally {
        loading.classList.add('hidden');
    }
}

/**
 * Render images in the grid
 */
function renderBuilderImages(images) {
    const grid = document.getElementById('builderImageGrid');
    grid.innerHTML = '';

    images.forEach(img => {
        const item = document.createElement('div');
        item.className = 'builder-image-item group';
        item.dataset.imageId = img.id;
        item.dataset.imageUrl = img.url;
        item.dataset.imageTitle = img.title;
        item.dataset.searchText = `${img.title.toLowerCase()} ${img.tags.toLowerCase()}`;

        item.innerHTML = `
            <div class="aspect-square relative rounded-lg overflow-hidden border-2 border-gray-300 hover:border-blue-500 transition-all hover:shadow-lg">
                <img src="${img.url}"
                     alt="${img.alt_text}"
                     class="w-full h-full object-cover">
                <!-- Selection Checkmark -->
                <div class="builder-image-checkmark">
                    <svg class="w-12 h-12 text-white" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
                    </svg>
                </div>
            </div>
            <p class="text-xs text-gray-600 mt-1 truncate text-center" title="${img.title}">${img.title}</p>
            ${img.category ? `<p class="text-xs text-gray-400 text-center">${img.category}</p>` : ''}
        `;

        item.addEventListener('click', () => selectBuilderImage(img));

        grid.appendChild(item);
    });
}

/**
 * Select an image from the grid
 */
function selectBuilderImage(imageData) {
    selectedImageData = imageData;

    // Update UI - remove previous selection
    document.querySelectorAll('.builder-image-item').forEach(item => {
        item.classList.remove('selected');
    });

    // Add selection to clicked item
    const selectedItem = document.querySelector(`[data-image-id="${imageData.id}"]`);
    if (selectedItem) {
        selectedItem.classList.add('selected');
    }

    // Enable select button
    document.getElementById('builderSelectBtn').disabled = false;

    // Update selected info
    document.getElementById('builderSelectedInfo').textContent = `Selected: ${imageData.title}`;
}

/**
 * Filter images by search term
 */
function filterBuilderImages() {
    const searchTerm = document.getElementById('builderImageSearch').value.toLowerCase();
    const items = document.querySelectorAll('.builder-image-item');

    items.forEach(item => {
        const searchText = item.dataset.searchText || '';
        if (searchText.includes(searchTerm)) {
            item.classList.remove('hidden');
        } else {
            item.classList.add('hidden');
        }
    });
}

/**
 * Handle file selection for upload
 */
function handleBuilderFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;

    // Validate file type
    if (!file.type.startsWith('image/')) {
        alert('Please select an image file');
        return;
    }

    // Validate file size (10MB)
    if (file.size > 10 * 1024 * 1024) {
        alert('File size must be less than 10MB');
        return;
    }

    selectedFile = file;

    // Show preview
    const reader = new FileReader();
    reader.onload = (e) => {
        const preview = document.getElementById('builderPreviewContainer');
        preview.innerHTML = `<img src="${e.target.result}" alt="Preview" class="max-h-64 rounded-lg shadow-md">`;
        document.getElementById('builderUploadPreview').classList.remove('hidden');
    };
    reader.readAsDataURL(file);

    // Show details form
    document.getElementById('builderImageDetails').classList.remove('hidden');

    // Pre-fill title from filename
    const titleInput = document.getElementById('builderImageTitle');
    if (!titleInput.value) {
        titleInput.value = file.name.replace(/\.[^/.]+$/, ''); // Remove extension
    }

    // Enable upload button
    document.getElementById('builderUploadBtn').disabled = false;
}

/**
 * Upload the selected image
 */
async function uploadBuilderImage() {
    if (!selectedFile) return;

    const title = document.getElementById('builderImageTitle').value || selectedFile.name;
    const altText = document.getElementById('builderImageAlt').value;
    const category = document.getElementById('builderImageCategory').value;

    const formData = new FormData();
    formData.append('image', selectedFile);
    formData.append('title', title);
    formData.append('alt_text', altText);
    formData.append('category', category);

    // Show progress
    document.getElementById('builderUploadProgress').classList.remove('hidden');
    document.getElementById('builderUploadBtn').disabled = true;

    try {
        const response = await fetch('/editor/api/images/upload/', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.success) {
            // Update progress to 100%
            document.getElementById('builderProgressBar').style.width = '100%';
            document.getElementById('builderProgressText').textContent = '100%';

            // Show success message
            const status = document.getElementById('builderUploadStatus');
            status.className = 'p-4 bg-green-50 text-green-700 rounded-lg border border-green-200';
            status.innerHTML = '✅ Image uploaded successfully!';
            status.classList.remove('hidden');

            // Select the uploaded image
            selectedImageData = data.image;

            // Wait a moment, then apply selection
            setTimeout(() => {
                applyBuilderImageSelection();
            }, 1000);

        } else {
            throw new Error(data.error || 'Upload failed');
        }

    } catch (error) {
        console.error('Upload error:', error);
        const status = document.getElementById('builderUploadStatus');
        status.className = 'p-4 bg-red-50 text-red-700 rounded-lg border border-red-200';
        status.innerHTML = `❌ Error: ${error.message}`;
        status.classList.remove('hidden');
        document.getElementById('builderUploadBtn').disabled = false;
    }
}

/**
 * Apply the selected image to the element
 */
function applyBuilderImageSelection() {
    if (!selectedImageData || !currentElement) {
        console.error('No image selected or no element to update');
        return;
    }

    const sectionId = currentElement.dataset.sectionId;
    const jsonPath = currentElement.dataset.jsonPath;

    if (!sectionId || !jsonPath) {
        console.error('Missing sectionId or jsonPath on element');
        return;
    }

    const elementType = currentElement.tagName.toLowerCase();

    if (elementType === 'img') {
        // Update img src
        currentElement.src = selectedImageData.url;
        currentElement.alt = selectedImageData.alt_text || selectedImageData.title;

        console.log('✅ Image updated:', selectedImageData.url);

    } else if (currentElement.dataset.editable === 'image') {
        // Update background image
        // First try to update the element itself
        currentElement.style.backgroundImage = `url('${selectedImageData.url}')`;

        // Also check if there's a child element with background-image (for text_image_bg sections)
        const childWithBackground = currentElement.querySelector('[style*="background-image"]');
        if (childWithBackground) {
            childWithBackground.style.backgroundImage = `url('${selectedImageData.url}')`;
        }

        console.log('✅ Background image updated:', selectedImageData.url);
    }

    // Track the change using the frontend builder's image tracking system
    if (typeof window.trackImageChange === 'function') {
        // trackImageChange expects: (sectionId, imageKey, element, imageUrl)
        window.trackImageChange(sectionId, selectedImageData.id, currentElement, selectedImageData.url);
    } else if (typeof window.trackContentChange === 'function') {
        // Fallback to trackContentChange for backwards compatibility
        window.trackContentChange(sectionId, jsonPath, selectedImageData.url, currentElement);
    } else {
        console.warn('⚠️ No tracking function available');
    }

    // Refresh the sidebar to show the new image preview
    if (window.builderSidebar && typeof window.builderSidebar.loadContentTabForElement === 'function') {
        window.builderSidebar.loadContentTabForElement(currentElement);
    }

    // Close modal
    closeBuilderImageModal();

    // Show success notification (if notification system exists)
    if (typeof window.showNotification === 'function') {
        window.showNotification('Image updated - click "Save Changes" to persist', 'success');
    }
}

// Setup drag and drop
document.addEventListener('DOMContentLoaded', () => {
    const dropZone = document.getElementById('builderDropZone');
    if (!dropZone) return;

    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
        });
    });

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => {
            dropZone.classList.add('border-blue-500', 'bg-blue-50');
        });
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => {
            dropZone.classList.remove('border-blue-500', 'bg-blue-50');
        });
    });

    dropZone.addEventListener('drop', (e) => {
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            const fileInput = document.getElementById('builderFileUpload');
            fileInput.files = files;
            handleBuilderFileSelect({ target: fileInput });
        }
    });
});

// Note: window.ImageModal API is now defined at the top of this file for immediate availability
