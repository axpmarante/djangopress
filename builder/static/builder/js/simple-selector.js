/**
 * Simple Element Selector
 * Click any element to edit it - no complex logic, just works
 */

(function() {
  'use strict';

  // Configuration
  const config = {
    enabled: false,
    highlightClass: 'editor-selected-element'
  };

  // State
  let selectedElement = null;

  // Initialize
  function init() {
    if (!config.enabled) return;

    attachEventListeners();
    addStyles();
    console.log('✅ Simple selector initialized');
  }

  // Add CSS for highlighting
  function addStyles() {
    const style = document.createElement('style');
    style.textContent = `
      .editor-selected-element {
        outline: 2px solid #3b82f6 !important;
        outline-offset: 2px;
        position: relative;
      }

      .editor-hover-element {
        outline: 1px dashed #3b82f6 !important;
        outline-offset: 2px;
        cursor: pointer;
      }
    `;
    document.head.appendChild(style);
  }

  // Attach event listeners
  function attachEventListeners() {
    document.addEventListener('click', handleClick, true); // Capture phase to catch before links
    document.addEventListener('mouseover', handleMouseOver);
    document.addEventListener('mouseout', handleMouseOut);
  }

  // Remove event listeners
  function removeEventListeners() {
    document.removeEventListener('click', handleClick, true);
    document.removeEventListener('mouseover', handleMouseOver);
    document.removeEventListener('mouseout', handleMouseOut);
  }

  // Handle click
  function handleClick(e) {
    console.log('🔵 Click detected:', {
      enabled: config.enabled,
      target: e.target.tagName,
      isEditorUI: isEditorUI(e.target)
    });

    if (!config.enabled) {
      console.log('❌ Selector not enabled');
      return;
    }

    // Ignore clicks on editor UI
    if (isEditorUI(e.target)) {
      console.log('⏭️ Ignoring editor UI click');
      return;
    }

    // Prevent default behavior (especially for links)
    e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation();

    const element = e.target;

    console.log('🖱️ Element clicked:', {
      tag: element.tagName,
      id: element.id,
      classes: element.className
    });

    selectElement(element);
  }

  // Handle mouse over for preview
  function handleMouseOver(e) {
    if (!config.enabled) return;
    if (isEditorUI(e.target)) return;
    if (e.target === selectedElement) return;

    e.target.classList.add('editor-hover-element');
  }

  // Handle mouse out
  function handleMouseOut(e) {
    if (!config.enabled) return;
    e.target.classList.remove('editor-hover-element');
  }

  // Check if element is part of editor UI (sidebar only, not content wrapper)
  function isEditorUI(element) {
    if (!element) return false;

    let current = element;
    while (current && current !== document.body) {
      const id = current.id || '';
      const className = current.className || '';

      // Ignore image modal and all its children
      if (id === 'builderImageModal' || current.closest('#builderImageModal')) {
        console.log('🚫 Ignoring image modal element');
        return true;
      }

      // Specifically check for sidebar elements
      if (
        id === 'editor-sidebar' ||
        id.startsWith('editor-') && id !== 'editor-content-wrapper' ||
        id.startsWith('admin-') ||
        (current.classList && current.classList.contains('editor-sidebar')) ||
        (current.classList && current.classList.contains('editor-tab')) ||
        (current.classList && current.classList.contains('editor-btn')) || // This includes editor-content-btn
        (current.classList && current.classList.contains('admin-toolbar'))
      ) {
        console.log('🚫 Ignoring editor UI element:', current.tagName, current.className);
        return true; // Return TRUE to ignore/skip this element
      }

      // Don't go past the content wrapper - everything inside is editable
      if (current.classList && current.classList.contains('editor-content-wrapper')) {
        return false;
      }

      current = current.parentElement;
    }
    return false;
  }

  // Select an element
  function selectElement(element) {
    // Remove previous selection
    if (selectedElement) {
      selectedElement.classList.remove(config.highlightClass);
    }

    // Add new selection
    selectedElement = element;
    element.classList.add(config.highlightClass);

    // Extract element information
    const elementData = extractElementData(element);

    // Fire custom event for sidebar to catch
    const event = new CustomEvent('editor:elementSelected', {
      detail: elementData,
      bubbles: true
    });
    document.dispatchEvent(event);

    console.log('✅ Element selected:', elementData);
  }

  // Extract element data
  function extractElementData(element) {
    const tagName = element.tagName.toLowerCase();

    // Get text content
    let textContent = '';
    if (['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'span', 'a', 'button', 'label'].includes(tagName)) {
      textContent = element.textContent.trim();
    }

    // Get innerHTML for rich text elements
    let innerHTML = '';
    if (['p', 'div'].includes(tagName)) {
      innerHTML = element.innerHTML;
    }

    // Get attributes
    const attributes = {};
    for (let attr of element.attributes) {
      attributes[attr.name] = attr.value;
    }

    // Find page wrapper
    const pageWrapper = findPageWrapper(element);
    const pageId = pageWrapper ? pageWrapper.getAttribute('data-page-id') : null;

    // Find section name (from data-section attribute on nearest <section>)
    const sectionElement = findParentSection(element);
    const sectionName = sectionElement ? sectionElement.getAttribute('data-section') : null;

    // Build data object
    const data = {
      element: element,
      tagName: tagName,
      elementId: element.getAttribute('data-element-id') || element.id || null,
      id: element.id || null,
      classes: Array.from(element.classList).filter(c => !c.startsWith('editor-')),
      classString: Array.from(element.classList).filter(c => !c.startsWith('editor-')).join(' '),
      textContent: textContent,
      innerHTML: innerHTML,
      attributes: attributes,
      pageId: pageId,
      sectionName: sectionName,
      jsonPath: element.getAttribute('data-json-path') || null,

      // Type flags
      isHeading: ['h1', 'h2', 'h3', 'h4', 'h5', 'h6'].includes(tagName),
      isText: ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'span'].includes(tagName),
      isRichText: ['p', 'div'].includes(tagName) && element.querySelector('strong, em, ul, ol, br'),
      isLink: tagName === 'a',
      isImage: tagName === 'img',
      isButton: tagName === 'button',

      // Special properties
      href: tagName === 'a' ? element.getAttribute('href') : null,
      src: tagName === 'img' ? element.getAttribute('src') : null,
      alt: tagName === 'img' ? element.getAttribute('alt') : null
    };

    return data;
  }

  // Find page wrapper ([data-page-id])
  function findPageWrapper(element) {
    let current = element;
    while (current && current !== document.body) {
      if (current.hasAttribute && current.hasAttribute('data-page-id')) {
        return current;
      }
      current = current.parentElement;
    }
    return null;
  }

  // Find parent section (data-section attribute)
  function findParentSection(element) {
    let current = element;
    while (current && current !== document.body) {
      if (current.tagName && current.tagName.toLowerCase() === 'section' &&
          current.hasAttribute('data-section')) {
        return current;
      }
      current = current.parentElement;
    }
    return null;
  }

  // Enable selector
  function enable() {
    config.enabled = true;
    init();
  }

  // Disable selector
  function disable() {
    config.enabled = false;
    removeEventListeners();

    // Remove highlights
    if (selectedElement) {
      selectedElement.classList.remove(config.highlightClass);
      selectedElement = null;
    }

    document.querySelectorAll('.editor-hover-element').forEach(el => {
      el.classList.remove('editor-hover-element');
    });
  }

  // Public API
  window.SimpleSelector = {
    init: init,
    enable: enable,
    disable: disable,
    isEnabled: () => config.enabled,
    getSelected: () => selectedElement
  };

})();
