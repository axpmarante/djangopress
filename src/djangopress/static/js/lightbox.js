/**
 * Simple Lightbox for Project Gallery Images
 */

class Lightbox {
    constructor() {
        this.currentIndex = 0;
        this.images = [];
        this.init();
    }

    init() {
        // Create lightbox HTML structure
        this.createLightboxHTML();

        // Attach event listeners
        this.attachEventListeners();
    }

    createLightboxHTML() {
        const lightboxHTML = `
            <div id="lightbox" class="lightbox" style="display: none;">
                <div class="lightbox-overlay"></div>
                <div class="lightbox-content">
                    <button class="lightbox-close" aria-label="Close lightbox">
                        <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                        </svg>
                    </button>
                    <button class="lightbox-prev" aria-label="Previous image">
                        <svg class="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="3">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7"></path>
                        </svg>
                    </button>
                    <button class="lightbox-next" aria-label="Next image">
                        <svg class="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="3">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7"></path>
                        </svg>
                    </button>
                    <div class="lightbox-image-container">
                        <img id="lightbox-image" src="" alt="" class="lightbox-image">
                        <div class="lightbox-caption"></div>
                    </div>
                    <div class="lightbox-counter"></div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', lightboxHTML);
    }

    attachEventListeners() {
        // Close button
        document.querySelector('.lightbox-close').addEventListener('click', () => this.close());

        // Overlay click
        document.querySelector('.lightbox-overlay').addEventListener('click', () => this.close());

        // Navigation buttons
        document.querySelector('.lightbox-prev').addEventListener('click', () => this.prev());
        document.querySelector('.lightbox-next').addEventListener('click', () => this.next());

        // Keyboard navigation
        document.addEventListener('keydown', (e) => {
            if (document.getElementById('lightbox').style.display === 'flex') {
                if (e.key === 'Escape') this.close();
                if (e.key === 'ArrowLeft') this.prev();
                if (e.key === 'ArrowRight') this.next();
            }
        });
    }

    open(images, startIndex = 0) {
        this.images = images;
        this.currentIndex = startIndex;
        this.updateImage();

        const lightbox = document.getElementById('lightbox');
        lightbox.style.display = 'flex';
        document.body.style.overflow = 'hidden';

        // Fade in animation
        setTimeout(() => {
            lightbox.classList.add('active');
        }, 10);
    }

    close() {
        const lightbox = document.getElementById('lightbox');
        lightbox.classList.remove('active');

        setTimeout(() => {
            lightbox.style.display = 'none';
            document.body.style.overflow = '';
        }, 300);
    }

    updateImage() {
        const img = document.getElementById('lightbox-image');
        const caption = document.querySelector('.lightbox-caption');
        const counter = document.querySelector('.lightbox-counter');

        const currentImage = this.images[this.currentIndex];

        img.src = currentImage.src;
        img.alt = currentImage.alt;
        caption.textContent = currentImage.alt;
        counter.textContent = `${this.currentIndex + 1} / ${this.images.length}`;

        // Update button visibility
        document.querySelector('.lightbox-prev').style.display = this.currentIndex === 0 ? 'none' : 'flex';
        document.querySelector('.lightbox-next').style.display = this.currentIndex === this.images.length - 1 ? 'none' : 'flex';
    }

    next() {
        if (this.currentIndex < this.images.length - 1) {
            this.currentIndex++;
            this.updateImage();
        }
    }

    prev() {
        if (this.currentIndex > 0) {
            this.currentIndex--;
            this.updateImage();
        }
    }
}

// Initialize lightbox when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    const lightbox = new Lightbox();
    window.__lightbox = lightbox;

    // Attach to all gallery images
    document.querySelectorAll('[data-lightbox]').forEach((element) => {
        element.addEventListener('click', (e) => {
            e.preventDefault();

            // Get all images in the same gallery group
            const galleryName = element.dataset.lightbox;
            const galleryElements = Array.from(
                document.querySelectorAll(`[data-lightbox="${galleryName}"]`)
            );
            const galleryImages = galleryElements.map(el => ({
                src: el.href || el.dataset.src || el.src || '',
                alt: el.dataset.alt || el.alt || ''
            }));

            // Use index within this gallery group, not global index
            const clickedIndex = galleryElements.indexOf(element);
            lightbox.open(galleryImages, clickedIndex);
        });
    });
});
