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

  // AI chat state
  let aiConversationHistory = []; // [{role: 'user', content: '...'}, ...]
  let lastAISectionName = null;
  let aiSessionId = null; // RefinementSession ID for persistence

  // DOM elements
  let sidebar, contentTab, designTab, structureTab, aiTab;
  let contentFields, classesInput;
  let parentsTree, currentElementDisplay, childrenTree;
  let aiTabButton, aiModel, aiLoading, aiStatus, aiChangesInfo;
  let aiChatMessages, aiChatInput, aiChatSendBtn;
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
    aiModel = document.getElementById('editor-ai-model');
    aiLoading = document.getElementById('editor-ai-loading');
    aiStatus = document.getElementById('editor-ai-status');
    aiChangesInfo = document.getElementById('editor-ai-changes-info');
    aiChatMessages = document.getElementById('editor-ai-chat-messages');
    aiChatInput = document.getElementById('editor-ai-chat-input');
    aiChatSendBtn = document.getElementById('editor-ai-chat-send');
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

    // AI Chat send button
    if (aiChatSendBtn) {
      aiChatSendBtn.addEventListener('click', generateAIRefinement);
    }

    // AI Chat input - send on Enter (Shift+Enter for newline)
    if (aiChatInput) {
      aiChatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          generateAIRefinement();
        }
      });
    }

    // Context menu tab switching
    document.addEventListener('editor:switchTab', (e) => {
      const tab = e.detail && e.detail.tab;
      if (tab) {
        switchTab(tab);
        if (e.detail.focusInput && tab === 'ai' && aiChatInput) {
          setTimeout(() => aiChatInput.focus(), 50);
        }
      }
    });

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

    // Show AI tab when element is inside a section (has sectionName)
    const hasSection = !!currentData.sectionName;
    if (aiTabButton) {
      aiTabButton.style.display = hasSection ? 'flex' : 'none';
    }

    // Populate AI tab if inside a section
    if (hasSection) {
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

    // Simple text elements (H1-H6, SPAN, LABEL, BUTTON)
    if (currentData.isHeading || ['span', 'label', 'button'].includes(currentData.tagName)) {
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

    // Background image (available on any element)
    if (currentData.hasBackgroundImage) {
      createBackgroundImageField(currentData.backgroundImageUrl);
    }

    // Section images — show clickable thumbnails for <img> tags inside the
    // current section so users can reach images hidden behind overlays
    if (!currentData.isImage && currentData.sectionName) {
      showSectionImages();
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
      // Open image modal if available
      if (window.ImageModal && typeof window.ImageModal.open === 'function') {
        // Capture old src BEFORE DOM update for save fallback
        const oldSrc = currentElement.getAttribute('src') || '';
        window.ImageModal.open((imageUrl) => {
          currentElement.setAttribute('src', imageUrl);
          trackChange('attribute', { name: 'src', value: imageUrl }, oldSrc);
          // Refresh sidebar
          populateContentTab();
        });
      } else {
        alert('Image modal not available. Please check that image-modal.js is loaded.');
      }
    });

    field.appendChild(button);
    contentFields.appendChild(field);

    // Alt text
    const oldAlt = alt || '';
    createTextField('Alt Text', oldAlt, (value) => {
      const prevAlt = currentElement.getAttribute('alt') || '';
      currentElement.setAttribute('alt', value);
      trackChange('attribute', { name: 'alt', value }, prevAlt);
    });
  }

  // Create background image field
  function createBackgroundImageField(bgUrl) {
    // Separator
    const separator = document.createElement('hr');
    separator.style.cssText = 'border: none; border-top: 1px solid #e5e7eb; margin: 16px 0;';
    contentFields.appendChild(separator);

    const label = document.createElement('label');
    label.textContent = 'Background Image';
    label.style.cssText = 'display: block; font-size: 13px; font-weight: 600; color: #374151; margin-bottom: 6px;';
    contentFields.appendChild(label);

    // Preview
    if (bgUrl) {
      const preview = document.createElement('div');
      preview.style.cssText = `width: 100%; height: 120px; background-image: url('${bgUrl}'); background-size: cover; background-position: center; border: 1px solid #e5e7eb; border-radius: 6px; margin-bottom: 12px;`;
      contentFields.appendChild(preview);
    }

    // Change button
    const field = document.createElement('div');
    field.className = 'editor-field';
    field.style.marginBottom = '8px';

    const changeBtn = document.createElement('button');
    changeBtn.type = 'button';
    changeBtn.className = 'editor-btn editor-btn-secondary';
    changeBtn.textContent = 'Change Background Image';
    changeBtn.style.width = '100%';
    changeBtn.addEventListener('click', () => {
      if (window.ImageModal && typeof window.ImageModal.open === 'function') {
        window.ImageModal.open((imageUrl) => {
          currentElement.style.backgroundImage = `url('${imageUrl}')`;
          trackChange('attribute', { name: 'style', value: currentElement.getAttribute('style') });
          populateContentTab();
        });
      } else {
        alert('Image modal not available.');
      }
    });
    field.appendChild(changeBtn);
    contentFields.appendChild(field);

    // Remove button
    const removeField = document.createElement('div');
    removeField.className = 'editor-field';

    const removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.className = 'editor-btn editor-btn-secondary';
    removeBtn.textContent = 'Remove Background Image';
    removeBtn.style.cssText = 'width: 100%; color: #dc2626;';
    removeBtn.addEventListener('click', () => {
      currentElement.style.backgroundImage = 'none';
      trackChange('attribute', { name: 'style', value: currentElement.getAttribute('style') });
      populateContentTab();
    });
    removeField.appendChild(removeBtn);
    contentFields.appendChild(removeField);
  }

  // Show images inside the current section so users can select them
  // even when overlay divs block direct clicks on <img> tags
  function showSectionImages() {
    const sectionEl = findSectionElement();
    if (!sectionEl) return;

    const imgs = sectionEl.querySelectorAll('img');
    if (imgs.length === 0) return;

    // Separator
    const separator = document.createElement('hr');
    separator.style.cssText = 'border: none; border-top: 1px solid #e5e7eb; margin: 16px 0;';
    contentFields.appendChild(separator);

    const label = document.createElement('label');
    label.textContent = 'Section Images';
    label.style.cssText = 'display: block; font-size: 13px; font-weight: 600; color: #374151; margin-bottom: 8px;';
    contentFields.appendChild(label);

    const hint = document.createElement('p');
    hint.textContent = 'Click a thumbnail to select and edit that image';
    hint.style.cssText = 'font-size: 12px; color: #6b7280; margin-bottom: 8px;';
    contentFields.appendChild(hint);

    const grid = document.createElement('div');
    grid.style.cssText = 'display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px;';

    imgs.forEach(img => {
      const thumb = document.createElement('div');
      thumb.style.cssText = 'cursor: pointer; border: 2px solid #e5e7eb; border-radius: 6px; overflow: hidden; transition: all 0.2s;';
      thumb.addEventListener('mouseenter', () => { thumb.style.borderColor = '#3b82f6'; });
      thumb.addEventListener('mouseleave', () => { thumb.style.borderColor = '#e5e7eb'; });

      const preview = document.createElement('img');
      preview.src = img.src;
      preview.alt = img.alt || '';
      preview.style.cssText = 'width: 100%; height: 80px; object-fit: cover;';
      thumb.appendChild(preview);

      thumb.addEventListener('click', () => {
        // Select the img element via the selector (handles highlight removal)
        selectElementFromTree(img);
      });

      grid.appendChild(thumb);
    });

    contentFields.appendChild(grid);
  }

  // Populate design tab
  function populateDesignTab() {
    classesInput.value = currentData.classString || '';
  }

  // Populate AI tab
  function populateAITab() {
    if (!aiChatMessages || !aiStatus || !aiChangesInfo) return;

    const sectionName = currentData.sectionName;

    // If different section selected, reset conversation
    if (sectionName !== lastAISectionName) {
      aiConversationHistory = [];
      lastAISectionName = sectionName;
      aiSessionId = null;
      originalSectionHTML = null;
      aiChangesApplied = false;
      refinedSection = null;
    }

    // Clear status
    aiStatus.textContent = '';
    aiStatus.className = 'editor-ai-status';
    aiChangesInfo.style.display = 'none';

    // Render existing messages or empty state
    renderChatMessages();

    // Clear input
    if (aiChatInput) {
      aiChatInput.value = '';
      aiChatInput.disabled = false;
    }
    if (aiChatSendBtn) {
      aiChatSendBtn.disabled = false;
    }
  }

  // Render chat messages
  function renderChatMessages() {
    if (!aiChatMessages) return;

    if (aiConversationHistory.length === 0) {
      aiChatMessages.innerHTML = '<p class="editor-ai-chat-empty">Describe what to change in this section. AI will update it while preserving context from previous messages.</p>';
      return;
    }

    aiChatMessages.innerHTML = '';
    aiConversationHistory.forEach(msg => {
      const msgDiv = document.createElement('div');
      msgDiv.className = `editor-ai-chat-msg editor-ai-chat-${msg.role}`;
      msgDiv.textContent = msg.content;
      aiChatMessages.appendChild(msgDiv);
    });

    // Scroll to bottom
    aiChatMessages.scrollTop = aiChatMessages.scrollHeight;
  }

  // Find the parent <section> element for AI operations
  function findSectionElement() {
    if (!currentElement || !currentData.sectionName) return null;
    let el = currentElement;
    while (el && el !== document.body) {
      if (el.tagName && el.tagName.toLowerCase() === 'section' &&
          el.getAttribute('data-section') === currentData.sectionName) {
        return el;
      }
      el = el.parentElement;
    }
    return null;
  }

  // Generate AI refinement (chat-based)
  async function generateAIRefinement() {
    const pageId = currentData.pageId;
    const sectionName = currentData.sectionName;
    const instructions = aiChatInput ? aiChatInput.value.trim() : '';

    // Validation
    if (!pageId) {
      showAIStatus('error', 'This page doesn\'t have an ID. Cannot refine.');
      return;
    }

    if (!sectionName) {
      showAIStatus('error', 'Select an element inside a section first.');
      return;
    }

    if (!instructions) {
      showAIStatus('error', 'Please enter instructions.');
      return;
    }

    // Find the actual section element
    const sectionEl = findSectionElement();
    if (!sectionEl) {
      showAIStatus('error', 'Could not find parent section element.');
      return;
    }

    // Store original HTML before first change
    if (!originalSectionHTML) {
      originalSectionHTML = sectionEl.outerHTML;
    }

    // Add user message to history and render
    aiConversationHistory.push({ role: 'user', content: instructions });
    renderChatMessages();

    // Clear input and disable
    if (aiChatInput) aiChatInput.value = '';
    if (aiChatSendBtn) aiChatSendBtn.disabled = true;
    if (aiChatInput) aiChatInput.disabled = true;
    aiLoading.style.display = 'block';
    aiStatus.textContent = '';
    aiChangesInfo.style.display = 'none';

    try {
      console.log('🤖 Calling AI section refine:', { pageId, sectionName, instructions });

      const response = await fetch('/editor/api/refine-section/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCSRFToken()
        },
        body: JSON.stringify({
          page_id: pageId,
          section_name: sectionName,
          instructions: instructions,
          conversation_history: aiConversationHistory.slice(0, -1), // exclude the current message (it's in instructions)
          model: aiModel ? aiModel.value : 'gemini-flash',
          session_id: aiSessionId
        })
      });

      const result = await response.json();

      if (result.success && result.section) {
        console.log('✅ AI response received:', result.section);

        // Track session ID for persistence
        if (result.session_id) {
          aiSessionId = result.session_id;
        }

        // Add assistant message to history
        const assistantMsg = result.assistant_message || 'Changes applied.';
        aiConversationHistory.push({ role: 'assistant', content: assistantMsg });
        renderChatMessages();

        refinedSection = result.section;
        applyAIChanges(result.section);
      } else {
        // Remove user message on failure
        aiConversationHistory.pop();
        renderChatMessages();
        throw new Error(result.error || 'Unknown error');
      }

    } catch (error) {
      console.error('❌ AI generation error:', error);
      showAIStatus('error', `Error: ${error.message}`);
    } finally {
      aiLoading.style.display = 'none';
      if (aiChatSendBtn) aiChatSendBtn.disabled = false;
      if (aiChatInput) aiChatInput.disabled = false;
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

      // Find the section element to replace
      const sectionEl = findSectionElement();
      if (!sectionEl) {
        showAIStatus('error', 'Could not find section element to update.');
        return;
      }

      // Update the section's HTML in the DOM
      sectionEl.outerHTML = renderedHTML;

      // Re-select the section element (since we replaced it)
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
    }
  }

  // Revert AI changes
  function revertAIChanges() {
    if (!originalSectionHTML || !aiChangesApplied) {
      console.log('⚠️ No AI changes to revert');
      return;
    }

    try {
      // Find current section element and restore original HTML
      const sectionEl = findSectionElement() || currentElement;
      sectionEl.outerHTML = originalSectionHTML;

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

    // Replace all {{ trans.field }} with actual content (handles optional spaces)
    html = html.replace(/\{\{\s*trans\.(\w+)\s*\}\}/g, (match, field) => {
      const value = langContent[field];
      if (value !== undefined && value !== null) {
        return value;
      }
      console.warn(`⚠️ Missing content for {{trans.${field}}}`);
      return match; // Keep original if not found
    });

    // Replace {{ trans.field|safe }} (with safe filter, handles optional spaces)
    html = html.replace(/\{\{\s*trans\.(\w+)\|safe\s*\}\}/g, (match, field) => {
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

  // Track change (oldValue is optional, used for attribute save fallback)
  function trackChange(type, value, oldValue) {
    if (!currentElement || !currentData) return;

    const changeData = {
      type: type,
      pageId: currentData.pageId,
      elementId: currentData.elementId,
      element: currentElement,
      value: value,
      jsonPath: currentData.jsonPath
    };

    // Pass explicit oldValue so the tracker can use it for save fallback
    // (needed when elements lack data-element-id)
    if (oldValue !== undefined) {
      changeData.oldValue = oldValue;
    }

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
    getLastSectionName: () => lastAISectionName,
    revertAIChanges: revertAIChanges
  };

  // Auto-init when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
