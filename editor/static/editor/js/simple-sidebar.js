/**
 * Simple Sidebar
 * Shows element properties and allows editing
 */

(function() {
  'use strict';

  // State
  let currentElement = null;
  let currentData = null;
  let inputDebounceTimer = null;
  let originalSectionHTML = null; // For reverting AI changes
  let aiChangesApplied = false;
  let refinedSection = null;

  // DOM elements
  let sidebar, contentTab, designTab, structureTab, aiTab;
  let contentFields, classesInput;
  let parentsTree, currentElementDisplay, childrenTree;
  let aiTabButton, aiInstructions, aiModel, aiGenerateBtn, aiLoading, aiStatus, aiChangesInfo;
  let saveBtn, discardBtn, statusEl;

  // Initialize
  function init() {
    // Get DOM elements
    sidebar = document.getElementById('editor-sidebar');
    contentTab = document.getElementById('editor-content-tab');
    designTab = document.getElementById('editor-design-tab');
    structureTab = document.getElementById('editor-structure-tab');
    aiTab = document.getElementById('editor-ai-tab');
    contentFields = document.getElementById('editor-content-fields');
    classesInput = document.getElementById('editor-classes-input');
    parentsTree = document.getElementById('editor-parents-tree');
    currentElementDisplay = document.getElementById('editor-current-element');
    childrenTree = document.getElementById('editor-children-tree');
    aiTabButton = document.querySelector('.editor-tab[data-tab="ai"]');
    aiInstructions = document.getElementById('editor-ai-instructions');
    aiModel = document.getElementById('editor-ai-model');
    aiGenerateBtn = document.getElementById('editor-ai-generate-btn');
    aiLoading = document.getElementById('editor-ai-loading');
    aiStatus = document.getElementById('editor-ai-status');
    aiChangesInfo = document.getElementById('editor-ai-changes-info');
    saveBtn = document.getElementById('editor-save-btn');
    discardBtn = document.getElementById('editor-discard-btn');
    statusEl = document.getElementById('editor-status');

    if (!sidebar) {
      console.error('❌ Sidebar element not found');
      return;
    }

    attachEventListeners();
    console.log('✅ Simple sidebar initialized');
  }

  // Attach event listeners
  function attachEventListeners() {
    // Listen for element selection
    document.addEventListener('editor:elementSelected', handleElementSelected);

    // Tab switching
    document.querySelectorAll('.editor-tab').forEach(tab => {
      tab.addEventListener('click', () => switchTab(tab.dataset.tab));
    });

    // Classes input
    classesInput.addEventListener('input', debounceClassesChange);

    // AI Generate button
    if (aiGenerateBtn) {
      aiGenerateBtn.addEventListener('click', generateAIRefinement);
    }

    // Save/Discard buttons (will be handled by tracker)
    saveBtn.addEventListener('click', () => {
      document.dispatchEvent(new CustomEvent('editor:saveChanges'));
    });

    discardBtn.addEventListener('click', () => {
      document.dispatchEvent(new CustomEvent('editor:discardChanges'));
    });
  }

  // Handle element selected
  function handleElementSelected(e) {
    currentData = e.detail;
    currentElement = currentData.element;

    console.log('📝 Sidebar received element:', currentData);

    // Update header
    updateHeader();

    // Populate content tab
    populateContentTab();

    // Populate design tab
    populateDesignTab();

    // Populate structure tab
    populateStructureTab();

    // Check if element is a section and show/hide AI tab
    const isSection = currentElement.tagName && currentElement.tagName.toLowerCase() === 'section';
    if (aiTabButton) {
      aiTabButton.style.display = isSection ? 'flex' : 'none';
    }

    // Populate AI tab if section
    if (isSection) {
      populateAITab();
    }

    // Switch to content tab by default
    switchTab('content');
  }

  // Update header
  function updateHeader() {
    const tagEl = document.getElementById('editor-element-tag');
    const idEl = document.getElementById('editor-element-id');

    tagEl.textContent = `<${currentData.tagName}>`;

    if (currentData.elementId || currentData.id) {
      idEl.textContent = currentData.elementId || `#${currentData.id}`;
    } else {
      idEl.textContent = '';
    }
  }

  // Switch tab
  function switchTab(tabName) {
    // Update tab buttons
    document.querySelectorAll('.editor-tab').forEach(tab => {
      if (tab.dataset.tab === tabName) {
        tab.classList.add('active');
      } else {
        tab.classList.remove('active');
      }
    });

    // Update tab panels
    document.querySelectorAll('.editor-tab-panel').forEach(panel => {
      panel.classList.remove('active');
    });

    if (tabName === 'content') {
      contentTab.classList.add('active');
    } else if (tabName === 'design') {
      designTab.classList.add('active');
    } else if (tabName === 'structure') {
      structureTab.classList.add('active');
    } else if (tabName === 'ai') {
      aiTab.classList.add('active');
    }
  }

  // Populate content tab
  function populateContentTab() {
    contentFields.innerHTML = '';

    // Text elements (H1-H6)
    if (currentData.isHeading) {
      createTextField('Content', currentData.textContent, (value) => {
        currentElement.textContent = value;
        trackChange('content', value);
      });
    }

    // Rich text elements (P, DIV)
    else if (currentData.isText && (currentData.tagName === 'p' || currentData.tagName === 'div')) {
      const hasRichContent = currentData.innerHTML !== currentData.textContent;

      if (hasRichContent) {
        createRichTextField('Content', currentData.innerHTML, (value) => {
          currentElement.innerHTML = value;
          trackChange('content', value);
        });
      } else {
        createTextArea('Content', currentData.textContent, (value) => {
          currentElement.textContent = value;
          trackChange('content', value);
        });
      }
    }

    // Links
    else if (currentData.isLink) {
      createTextField('Link Text', currentData.textContent, (value) => {
        currentElement.textContent = value;
        trackChange('content', value);
      });

      createTextField('Link URL', currentData.href || '', (value) => {
        currentElement.setAttribute('href', value);
        trackChange('attribute', { name: 'href', value });
      });
    }

    // Images
    else if (currentData.isImage) {
      createImageField(currentData.src, currentData.alt);
    }

    // Other elements - just show classes
    else {
      contentFields.innerHTML = '<p class="editor-placeholder">This element type doesn\'t have editable content. Use the Design tab to edit classes.</p>';
    }
  }

  // Create text field
  function createTextField(label, value, onChange) {
    const field = document.createElement('div');
    field.className = 'editor-field';

    const labelEl = document.createElement('label');
    labelEl.textContent = label;

    const input = document.createElement('input');
    input.type = 'text';
    input.value = value || '';
    input.addEventListener('input', debounce((e) => onChange(e.target.value), 300));

    field.appendChild(labelEl);
    field.appendChild(input);
    contentFields.appendChild(field);
  }

  // Create textarea
  function createTextArea(label, value, onChange) {
    const field = document.createElement('div');
    field.className = 'editor-field';

    const labelEl = document.createElement('label');
    labelEl.textContent = label;

    const textarea = document.createElement('textarea');
    textarea.className = 'editor-textarea';
    textarea.rows = 6;
    textarea.value = value || '';
    textarea.addEventListener('input', debounce((e) => onChange(e.target.value), 300));

    field.appendChild(labelEl);
    field.appendChild(textarea);
    contentFields.appendChild(field);
  }

  // Create rich text field
  function createRichTextField(label, value, onChange) {
    const field = document.createElement('div');
    field.className = 'editor-field';

    const labelEl = document.createElement('label');
    labelEl.textContent = label;

    // Toolbar
    const toolbar = document.createElement('div');
    toolbar.className = 'editor-richtext-toolbar';

    const buttons = [
      { label: 'B', command: 'bold', title: 'Bold' },
      { label: 'I', command: 'italic', title: 'Italic' },
      { label: 'U', command: 'underline', title: 'Underline' },
      { label: 'UL', command: 'insertUnorderedList', title: 'Bullet List' },
      { label: 'OL', command: 'insertOrderedList', title: 'Numbered List' },
      { label: 'Link', command: 'createLink', title: 'Insert Link' }
    ];

    buttons.forEach(btn => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'editor-richtext-btn';
      button.textContent = btn.label;
      button.title = btn.title;
      button.addEventListener('click', () => {
        if (btn.command === 'createLink') {
          const url = prompt('Enter URL:');
          if (url) document.execCommand(btn.command, false, url);
        } else {
          document.execCommand(btn.command, false, null);
        }
        textarea.focus();
      });
      toolbar.appendChild(button);
    });

    // Editable textarea
    const textarea = document.createElement('div');
    textarea.contentEditable = true;
    textarea.className = 'editor-textarea';
    textarea.style.minHeight = '150px';
    textarea.style.padding = '10px';
    textarea.innerHTML = value || '';

    textarea.addEventListener('input', debounce(() => {
      onChange(textarea.innerHTML);
    }, 300));

    field.appendChild(labelEl);
    field.appendChild(toolbar);
    field.appendChild(textarea);
    contentFields.appendChild(field);
  }

  // Create image field
  function createImageField(src, alt) {
    // Image preview
    if (src) {
      const preview = document.createElement('img');
      preview.src = src;
      preview.alt = alt || '';
      preview.className = 'editor-image-preview';
      contentFields.appendChild(preview);
    }

    // Change image button
    const field = document.createElement('div');
    field.className = 'editor-field';

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'editor-btn editor-btn-secondary'; // editor-btn class makes selector ignore it
    button.textContent = '📷 Change Image';
    button.style.width = '100%';
    button.addEventListener('click', (e) => {
      // Debug logging
      console.log('🖼️ Image button clicked');
      console.log('window.ImageModal:', window.ImageModal);
      console.log('window.ImageModal.open:', window.ImageModal?.open);

      // Open image modal if available
      if (window.ImageModal && typeof window.ImageModal.open === 'function') {
        console.log('✅ Opening image modal...');
        window.ImageModal.open((imageUrl) => {
          currentElement.setAttribute('src', imageUrl);
          trackChange('attribute', { name: 'src', value: imageUrl });
          // Refresh sidebar
          populateContentTab();
        });
      } else {
        console.error('❌ ImageModal not available:', {
          hasImageModal: !!window.ImageModal,
          hasOpenFunction: typeof window.ImageModal?.open
        });
        alert('Image modal not available. Please check that image-modal.js is loaded.');
      }
    });

    field.appendChild(button);
    contentFields.appendChild(field);

    // Alt text
    createTextField('Alt Text', alt || '', (value) => {
      currentElement.setAttribute('alt', value);
      trackChange('attribute', { name: 'alt', value });
    });
  }

  // Populate design tab
  function populateDesignTab() {
    classesInput.value = currentData.classString || '';
  }

  // Populate AI tab
  function populateAITab() {
    if (!aiInstructions || !aiStatus || !aiChangesInfo) return;

    // Clear previous state
    aiInstructions.value = '';
    aiStatus.textContent = '';
    aiStatus.className = 'editor-ai-status';
    aiChangesInfo.style.display = 'none';
    aiGenerateBtn.disabled = false;

    // Reset AI state
    originalSectionHTML = null;
    aiChangesApplied = false;
    refinedSection = null;
  }

  // Generate AI refinement
  async function generateAIRefinement() {
    const pageId = currentData.pageId;
    const sectionName = currentData.sectionName;
    const instructions = aiInstructions.value.trim();

    // Validation
    if (!pageId) {
      showAIStatus('error', 'This page doesn\'t have an ID. Cannot refine.');
      return;
    }

    if (!instructions) {
      showAIStatus('error', 'Please enter instructions for what you want to change.');
      return;
    }

    // Store original HTML before making changes
    if (!originalSectionHTML) {
      originalSectionHTML = currentElement.outerHTML;
    }

    // Show loading
    aiGenerateBtn.disabled = true;
    aiLoading.style.display = 'block';
    aiStatus.textContent = '';
    aiChangesInfo.style.display = 'none';

    try {
      console.log('🤖 Calling AI API:', { pageId, sectionName, instructions });

      const response = await fetch('/ai/api/refine-page-with-html/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCSRFToken()
        },
        body: JSON.stringify({
          page_id: pageId,
          instructions: instructions,
          section_name: sectionName,
          model: aiModel.value
        })
      });

      const result = await response.json();

      if (result.success && result.section) {
        console.log('✅ AI response received:', result.section);
        refinedSection = result.section;
        applyAIChanges(result.section);
      } else {
        throw new Error(result.error || 'Unknown error');
      }

    } catch (error) {
      console.error('❌ AI generation error:', error);
      showAIStatus('error', `Error: ${error.message}`);
      aiGenerateBtn.disabled = false;
    } finally {
      aiLoading.style.display = 'none';
    }
  }

  // Apply AI changes to the page
  function applyAIChanges(section) {
    if (!section || !section.html_template) {
      showAIStatus('error', 'Invalid AI response: no HTML template');
      return;
    }

    try {
      // Render the template with actual content
      const renderedHTML = renderSectionTemplate(section);

      // Update the section's HTML in the DOM
      currentElement.outerHTML = renderedHTML;

      // Re-select the element (since we replaced it)
      const updatedElement = document.querySelector(`[data-page-id="${currentData.pageId}"] section[data-section="${currentData.sectionName}"]`);
      if (updatedElement) {
        currentElement = updatedElement;
        currentData.element = updatedElement;
      }

      // Mark as applied
      aiChangesApplied = true;

      // Dispatch event for tracker to handle AI save
      document.dispatchEvent(new CustomEvent('editor:aiChangesApplied', {
        detail: {
          pageId: currentData.pageId,
          refinedSection: section
        }
      }));

      // Show success message
      showAIStatus('success', '✨ AI changes applied! Review the page and click "Save Changes" to keep them.');
      aiChangesInfo.style.display = 'block';

      // Enable save button
      if (saveBtn) {
        saveBtn.disabled = false;
      }

      console.log('✅ AI changes applied to DOM');

    } catch (error) {
      console.error('❌ Error applying AI changes:', error);
      showAIStatus('error', `Failed to apply changes: ${error.message}`);
    } finally {
      aiGenerateBtn.disabled = false;
    }
  }

  // Revert AI changes
  function revertAIChanges() {
    if (!originalSectionHTML || !aiChangesApplied) {
      console.log('⚠️ No AI changes to revert');
      return;
    }

    try {
      // Restore original HTML
      currentElement.outerHTML = originalSectionHTML;

      // Re-select the element
      const restoredElement = document.querySelector(`[data-page-id="${currentData.pageId}"] section[data-section="${currentData.sectionName}"]`);
      if (restoredElement) {
        currentElement = restoredElement;
        currentData.element = restoredElement;
      }

      // Reset state
      originalSectionHTML = null;
      aiChangesApplied = false;
      refinedSection = null;

      // Dispatch event
      document.dispatchEvent(new CustomEvent('editor:aiChangesReverted'));

      showAIStatus('success', 'AI changes reverted.');
      aiChangesInfo.style.display = 'none';

      console.log('↩️ AI changes reverted');

    } catch (error) {
      console.error('❌ Error reverting AI changes:', error);
      showAIStatus('error', `Failed to revert changes: ${error.message}`);
    }
  }

  // Render section template with content
  function renderSectionTemplate(section) {
    let html = section.html_template;
    const content = section.content || {};
    const translations = content.translations || {};

    // Get current language from URL
    const currentLang = getCurrentLanguage();
    const langContent = translations[currentLang] || {};

    console.log('🎨 Rendering template:', { currentLang, langContent });

    // Replace all {{trans.field}} with actual content
    html = html.replace(/\{\{trans\.(\w+)\}\}/g, (match, field) => {
      const value = langContent[field];
      if (value !== undefined && value !== null) {
        return value;
      }
      console.warn(`⚠️ Missing content for {{trans.${field}}}`);
      return match; // Keep original if not found
    });

    // Replace {{trans.field|safe}} (with safe filter)
    html = html.replace(/\{\{trans\.(\w+)\|safe\}\}/g, (match, field) => {
      const value = langContent[field];
      if (value !== undefined && value !== null) {
        return value;
      }
      console.warn(`⚠️ Missing content for {{trans.${field}|safe}}`);
      return match;
    });

    return html;
  }

  // Get current language from URL
  function getCurrentLanguage() {
    const path = window.location.pathname;
    if (path.startsWith('/pt/')) return 'pt';
    if (path.startsWith('/en/')) return 'en';
    return 'pt'; // Default
  }

  // Show AI status message
  function showAIStatus(type, message) {
    aiStatus.textContent = message;
    aiStatus.className = `editor-ai-status ${type}`;
  }

  // Get CSRF token
  function getCSRFToken() {
    const name = 'csrftoken';
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
      const cookies = document.cookie.split(';');
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === (name + '=')) {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }

  // Populate structure tab
  function populateStructureTab() {
    if (!currentElement || !parentsTree || !currentElementDisplay || !childrenTree) return;

    // Build parents breadcrumb
    buildParentsTree();

    // Display current element
    displayCurrentElement();

    // Build children tree
    buildChildrenTree();
  }

  // Build parents breadcrumb trail
  function buildParentsTree() {
    parentsTree.innerHTML = '';

    const parents = [];
    let element = currentElement.parentElement;

    // Traverse up to body (but don't include body)
    while (element && element.tagName && element.tagName.toLowerCase() !== 'body') {
      // Skip editor UI elements
      if (!isEditorElement(element)) {
        parents.unshift(element); // Add to beginning of array
      }
      element = element.parentElement;
    }

    // Create node for each parent
    parents.forEach((parent, index) => {
      const node = createTreeNode(parent, false);
      parentsTree.appendChild(node);
    });

    if (parents.length === 0) {
      parentsTree.innerHTML = '<p class="editor-placeholder">No parent elements</p>';
    }
  }

  // Display current element
  function displayCurrentElement() {
    const tag = currentElement.tagName.toLowerCase();
    const id = currentElement.id ? `#${currentElement.id}` : '';
    const classes = Array.from(currentElement.classList)
      .filter(c => !c.startsWith('editor-'))
      .join(' ');

    currentElementDisplay.innerHTML = `
      <span class="editor-current-element-tag">&lt;${tag}&gt;</span>
      ${id ? `<span class="editor-current-element-id">${id}</span>` : ''}
      ${classes ? `<span class="editor-current-element-classes">${classes}</span>` : ''}
    `;
  }

  // Build children tree
  function buildChildrenTree() {
    childrenTree.innerHTML = '';

    const children = Array.from(currentElement.children).filter(child => !isEditorElement(child));

    if (children.length === 0) {
      childrenTree.innerHTML = '<p class="editor-placeholder">No child elements</p>';
      return;
    }

    // Create node for each child
    children.forEach(child => {
      const node = createTreeNode(child, true);
      childrenTree.appendChild(node);

      // If child has children, show count
      const grandchildren = Array.from(child.children).filter(c => !isEditorElement(c));
      if (grandchildren.length > 0) {
        // Add expand/collapse functionality here if needed
      }
    });
  }

  // Create a tree node element
  function createTreeNode(element, isChild) {
    const node = document.createElement('div');
    node.className = isChild ? 'editor-tree-child' : 'editor-tree-node';

    const tag = element.tagName.toLowerCase();
    const id = element.id ? `#${element.id}` : '';
    const classes = Array.from(element.classList)
      .filter(c => !c.startsWith('editor-'))
      .slice(0, 3) // Only show first 3 classes
      .join(' ');

    // Count children
    const childCount = Array.from(element.children).filter(c => !isEditorElement(c)).length;

    node.innerHTML = `
      <span class="editor-tree-node-tag">&lt;${tag}&gt;</span>
      ${id ? `<span class="editor-tree-node-id">${id}</span>` : ''}
      ${classes ? `<span class="editor-tree-node-classes">${classes}</span>` : ''}
      ${childCount > 0 ? `<span class="editor-tree-children-count">${childCount} child${childCount > 1 ? 'ren' : ''}</span>` : ''}
    `;

    // Add click handler to select this element
    node.addEventListener('click', (e) => {
      e.stopPropagation();
      selectElementFromTree(element);
    });

    return node;
  }

  // Check if element is part of editor UI
  function isEditorElement(element) {
    if (!element || !element.classList) return false;
    const classList = Array.from(element.classList);
    return classList.some(c => c.startsWith('editor-')) ||
           element.id === 'editor-sidebar' ||
           element.closest('#editor-sidebar') !== null;
  }

  // Select element from tree
  function selectElementFromTree(element) {
    // Simulate a click on the element to select it
    const event = new MouseEvent('click', {
      bubbles: true,
      cancelable: true,
      view: window
    });
    element.dispatchEvent(event);
  }

  // Debounce classes change
  function debounceClassesChange(e) {
    clearTimeout(inputDebounceTimer);
    inputDebounceTimer = setTimeout(() => {
      handleClassesChange(e.target.value);
    }, 300);
  }

  // Handle classes change
  function handleClassesChange(newClasses) {
    const classArray = newClasses.split(' ').filter(c => c.trim());

    // Update element
    currentElement.className = classArray.join(' ');

    // Track change
    trackChange('classes', classArray);

    console.log('🎨 Classes changed:', classArray);
  }

  // Track change
  function trackChange(type, value) {
    if (!currentElement || !currentData) return;

    const changeData = {
      type: type,
      pageId: currentData.pageId,
      elementId: currentData.elementId,
      element: currentElement,
      value: value,
      jsonPath: currentData.jsonPath
    };

    document.dispatchEvent(new CustomEvent('editor:change', {
      detail: changeData
    }));
  }

  // Debounce helper
  function debounce(func, wait) {
    let timeout;
    return function(...args) {
      clearTimeout(timeout);
      timeout = setTimeout(() => func.apply(this, args), wait);
    };
  }

  // Public API
  window.SimpleSidebar = {
    init: init,
    hasAIChanges: () => aiChangesApplied,
    getRefinedSection: () => refinedSection,
    revertAIChanges: revertAIChanges
  };

  // Auto-init when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
