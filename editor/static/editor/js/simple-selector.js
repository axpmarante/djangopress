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
  let contextMenuEl = null;

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
    document.addEventListener('contextmenu', handleContextMenu, true);
  }

  // Remove event listeners
  function removeEventListeners() {
    document.removeEventListener('click', handleClick, true);
    document.removeEventListener('mouseover', handleMouseOver);
    document.removeEventListener('mouseout', handleMouseOut);
    document.removeEventListener('contextmenu', handleContextMenu, true);
    hideContextMenu();
  }

  // Handle click
  function handleClick(e) {
    // Always close context menu on left-click
    hideContextMenu();

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

      // Specifically check for sidebar elements and context menu
      if (
        id === 'editor-sidebar' ||
        id.startsWith('editor-') && id !== 'editor-content-wrapper' ||
        id.startsWith('admin-') ||
        (current.classList && current.classList.contains('editor-sidebar')) ||
        (current.classList && current.classList.contains('editor-tab')) ||
        (current.classList && current.classList.contains('editor-btn')) || // This includes editor-content-btn
        (current.classList && current.classList.contains('admin-toolbar')) ||
        (current.classList && current.classList.contains('editor-context-menu'))
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

    // Detect background image
    const bgImage = window.getComputedStyle(element).backgroundImage;
    const hasBackgroundImage = bgImage && bgImage !== 'none' && bgImage.startsWith('url(');
    let backgroundImageUrl = null;
    if (hasBackgroundImage) {
      const bgMatch = bgImage.match(/url\(['"]?([^'")\s]+)['"]?\)/);
      backgroundImageUrl = bgMatch ? bgMatch[1] : null;
    }

    // Detect background video (<video> or YouTube <iframe> as first child)
    let hasBackgroundVideo = false;
    let backgroundVideoUrl = null;
    let backgroundVideoType = null; // 'video' or 'youtube'
    const bgVideo = element.querySelector(':scope > video');
    const bgIframe = element.querySelector(':scope > iframe[src*="youtube"]');
    if (bgVideo) {
      hasBackgroundVideo = true;
      backgroundVideoType = 'video';
      const source = bgVideo.querySelector('source');
      backgroundVideoUrl = source ? source.getAttribute('src') : bgVideo.getAttribute('src');
    } else if (bgIframe) {
      hasBackgroundVideo = true;
      backgroundVideoType = 'youtube';
      backgroundVideoUrl = bgIframe.getAttribute('src');
    }

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
      alt: tagName === 'img' ? element.getAttribute('alt') : null,

      // Background image
      hasBackgroundImage: hasBackgroundImage,
      backgroundImageUrl: backgroundImageUrl,

      // Background video
      hasBackgroundVideo: hasBackgroundVideo,
      backgroundVideoUrl: backgroundVideoUrl,
      backgroundVideoType: backgroundVideoType
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

  // Handle right-click context menu
  function handleContextMenu(e) {
    if (!config.enabled) return;
    if (isEditorUI(e.target)) return;

    e.preventDefault();
    e.stopPropagation();

    // Select the element first (same as left-click)
    const element = e.target;
    selectElement(element);

    // Build menu items based on element context
    const items = buildMenuItems(element);
    showContextMenu(e.clientX, e.clientY, items);
  }

  // Build context menu items based on the selected element
  function buildMenuItems(element) {
    const items = [];
    const data = extractElementData(element);

    // Edit Content — always shown
    items.push({
      label: 'Edit Content',
      icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.83 2.83 0 114 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></svg>',
      action: () => {
        document.dispatchEvent(new CustomEvent('editor:switchTab', { detail: { tab: 'content' } }));
      }
    });

    // Edit Design — always shown
    items.push({
      label: 'Edit Design',
      icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>',
      action: () => {
        document.dispatchEvent(new CustomEvent('editor:switchTab', { detail: { tab: 'design' } }));
      }
    });

    // AI Refine Section — only if inside a <section> and AI is enabled (superuser)
    if (data.sectionName && window.EDITOR_AI_ENABLED) {
      items.push({ separator: true });
      items.push({
        label: 'AI Refine Section',
        icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l1.5 4.5H18l-3.5 2.5L16 14.5 12 11.5 8 14.5l1.5-4.5L6 7.5h4.5z"/></svg>',
        action: () => {
          document.dispatchEvent(new CustomEvent('editor:switchTab', { detail: { tab: 'ai', focusInput: true } }));
        }
      });
    }

    // Select Parent — if element has a parent that's not body
    const parent = element.parentElement;
    if (parent && parent.tagName && parent.tagName.toLowerCase() !== 'body') {
      items.push({ separator: true });
      items.push({
        label: 'Select Parent',
        icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5"/><path d="M5 12l7-7 7 7"/></svg>',
        action: () => {
          selectElement(parent);
        }
      });
    }

    // Copy Element ID — if element has data-element-id or id
    const elementId = element.getAttribute('data-element-id') || element.id;
    if (elementId) {
      items.push({
        label: 'Copy Element ID',
        icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>',
        action: (e) => {
          navigator.clipboard.writeText(elementId).then(() => {
            showToast(e.clientX || 0, e.clientY || 0, 'Copied!');
          });
        }
      });
    }

    return items;
  }

  // Show context menu at position
  function showContextMenu(x, y, items) {
    hideContextMenu();

    const menu = document.createElement('div');
    menu.className = 'editor-context-menu';

    items.forEach(item => {
      if (item.separator) {
        const sep = document.createElement('div');
        sep.className = 'editor-context-menu-separator';
        menu.appendChild(sep);
        return;
      }

      const menuItem = document.createElement('div');
      menuItem.className = 'editor-context-menu-item';
      menuItem.innerHTML = item.icon + '<span>' + item.label + '</span>';
      menuItem.addEventListener('click', (e) => {
        e.stopPropagation();
        hideContextMenu();
        item.action(e);
      });
      menu.appendChild(menuItem);
    });

    document.body.appendChild(menu);
    contextMenuEl = menu;

    // Position: clamp to viewport
    const rect = menu.getBoundingClientRect();
    const viewportW = window.innerWidth;
    const viewportH = window.innerHeight;

    let left = x;
    let top = y;

    if (x + rect.width > viewportW) {
      left = x - rect.width;
    }
    if (y + rect.height > viewportH) {
      top = y - rect.height;
    }

    // Ensure not off-screen on the left/top
    left = Math.max(4, left);
    top = Math.max(4, top);

    menu.style.left = left + 'px';
    menu.style.top = top + 'px';

    // Attach dismiss listeners
    setTimeout(() => {
      document.addEventListener('click', onDismissContextMenu);
      document.addEventListener('keydown', onDismissContextMenuKey);
      document.addEventListener('scroll', onDismissContextMenu, true);
      window.addEventListener('resize', onDismissContextMenu);
    }, 0);
  }

  // Hide context menu
  function hideContextMenu() {
    if (contextMenuEl) {
      contextMenuEl.remove();
      contextMenuEl = null;
    }
    document.removeEventListener('click', onDismissContextMenu);
    document.removeEventListener('keydown', onDismissContextMenuKey);
    document.removeEventListener('scroll', onDismissContextMenu, true);
    window.removeEventListener('resize', onDismissContextMenu);
  }

  // Dismiss handlers
  function onDismissContextMenu() {
    hideContextMenu();
  }

  function onDismissContextMenuKey(e) {
    if (e.key === 'Escape') {
      hideContextMenu();
    }
  }

  // Show a brief toast near cursor
  function showToast(x, y, message) {
    const toast = document.createElement('div');
    toast.className = 'editor-context-menu-toast';
    toast.textContent = message;
    toast.style.left = x + 'px';
    toast.style.top = (y - 30) + 'px';
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 1500);
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
