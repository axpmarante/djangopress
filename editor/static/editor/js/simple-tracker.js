/**
 * Simple Change Tracker
 * Tracks all changes and saves them to the database
 */

(function() {
  'use strict';

  // State
  let pendingChanges = [];
  let changeHistory = []; // Stack of applied changes for undo
  let historyIndex = -1; // Current position in history (-1 = no history)
  let aiPageData = null; // AI-refined page data
  let aiPageId = null;
  let saveBtn, discardBtn, statusEl;
  let undoBtn, redoBtn;

  // Initialize
  function init() {
    saveBtn = document.getElementById('editor-save-btn');
    discardBtn = document.getElementById('editor-discard-btn');
    statusEl = document.getElementById('editor-status');
    undoBtn = document.getElementById('editor-undo-btn');
    redoBtn = document.getElementById('editor-redo-btn');

    if (!saveBtn || !discardBtn || !statusEl) {
      console.error('❌ Tracker UI elements not found');
      return;
    }

    attachEventListeners();
    updateUndoRedoButtons();
    console.log('✅ Simple tracker initialized');
  }

  // Attach event listeners
  function attachEventListeners() {
    // Listen for changes
    document.addEventListener('editor:change', handleChange);

    // Listen for AI changes
    document.addEventListener('editor:aiChangesApplied', handleAIChanges);
    document.addEventListener('editor:aiChangesReverted', handleAIReverted);

    // Listen for save/discard
    document.addEventListener('editor:saveChanges', saveChanges);
    document.addEventListener('editor:discardChanges', discardChanges);

    // Undo/Redo buttons
    if (undoBtn) {
      undoBtn.addEventListener('click', undo);
    }
    if (redoBtn) {
      redoBtn.addEventListener('click', redo);
    }

    // Keyboard shortcuts
    document.addEventListener('keydown', handleKeyboardShortcuts);
  }

  // Handle change
  function handleChange(e) {
    const change = e.detail;

    console.log('📝 Change tracked:', change);

    // Store old value if not already stored (for undo)
    if (!change.oldValue) {
      change.oldValue = getElementCurrentValue(change);
    }

    // Add to history (clear redo stack if we're in the middle of history)
    if (historyIndex < changeHistory.length - 1) {
      // User made a new change after undoing, clear the redo stack
      changeHistory = changeHistory.slice(0, historyIndex + 1);
    }
    changeHistory.push(change);
    historyIndex++;

    // Find if this element already has a pending change of this type
    const existingIndex = pendingChanges.findIndex(c =>
      c.pageId === change.pageId &&
      c.elementId === change.elementId &&
      c.type === change.type &&
      (c.type !== 'attribute' || c.value.name === change.value.name)
    );

    if (existingIndex >= 0) {
      // Update existing change but preserve the original oldValue
      // (the DB still has the first old value, not intermediate ones)
      const originalOldValue = pendingChanges[existingIndex].oldValue;
      pendingChanges[existingIndex] = change;
      if (originalOldValue !== undefined) {
        pendingChanges[existingIndex].oldValue = originalOldValue;
      }
    } else {
      // Add new change
      pendingChanges.push(change);
    }

    updateUI();
    updateUndoRedoButtons();
  }

  // Handle AI changes
  function handleAIChanges(e) {
    const { pageId, refinedSection } = e.detail;

    console.log('🤖 AI changes tracked:', { pageId, refinedSection });

    // Store AI page data
    aiPageData = refinedSection;
    aiPageId = pageId;

    // Enable save button
    saveBtn.disabled = false;
    statusEl.textContent = 'AI changes pending';
    statusEl.className = 'editor-status';
  }

  // Handle AI changes reverted
  function handleAIReverted() {
    console.log('↩️ AI changes reverted in tracker');

    // Clear AI data
    aiPageData = null;
    aiPageId = null;

    // Update UI
    updateUI();
  }

  // Update UI
  function updateUI() {
    const hasChanges = pendingChanges.length > 0 || aiPageData !== null;

    saveBtn.disabled = !hasChanges;
    discardBtn.disabled = !hasChanges;

    if (aiPageData !== null) {
      statusEl.textContent = 'AI changes pending';
      statusEl.className = 'editor-status';
    } else if (hasChanges) {
      statusEl.textContent = `${pendingChanges.length} unsaved change${pendingChanges.length > 1 ? 's' : ''}`;
      statusEl.className = 'editor-status';
    } else {
      statusEl.textContent = '';
      statusEl.className = 'editor-status';
    }
  }

  // Save changes
  async function saveChanges() {
    if (pendingChanges.length === 0 && aiPageData === null) return;

    console.log('💾 Saving changes...', { pendingChanges, aiPageData });

    statusEl.textContent = 'Saving...';
    statusEl.className = 'editor-status';
    saveBtn.disabled = true;

    try {
      let allResults = [];

      // Save AI changes first if they exist
      if (aiPageData !== null) {
        console.log('🤖 Saving AI changes for page:', aiPageId);
        const aiResult = await saveAIPage();
        allResults.push(aiResult);

        // Clear AI data after saving
        if (aiResult.success) {
          aiPageData = null;
          aiPageId = null;
        }
      }

      // Save regular changes
      if (pendingChanges.length > 0) {
        // Group changes by type
        const contentChanges = pendingChanges.filter(c => c.type === 'content');
        const classChanges = pendingChanges.filter(c => c.type === 'classes');
        const attributeChanges = pendingChanges.filter(c => c.type === 'attribute');

        let savePromises = [];

        // Save content changes
        for (let change of contentChanges) {
          savePromises.push(saveContentChange(change));
        }

        // Save class changes
        for (let change of classChanges) {
          savePromises.push(saveClassChange(change));
        }

        // Save attribute changes
        for (let change of attributeChanges) {
          savePromises.push(saveAttributeChange(change));
        }

        // Wait for all saves
        const results = await Promise.all(savePromises);
        allResults = allResults.concat(results);
      }

      // Check if all succeeded
      const allSuccess = allResults.every(r => r.success);

      if (allSuccess) {
        statusEl.textContent = '✅ All changes saved!';
        statusEl.className = 'editor-status success';
        pendingChanges = [];
        updateUI();

        // Clear success message after 3 seconds
        setTimeout(() => {
          if (statusEl.textContent === '✅ All changes saved!') {
            statusEl.textContent = '';
          }
        }, 3000);
      } else {
        const failedCount = allResults.filter(r => !r.success).length;
        statusEl.textContent = `❌ ${failedCount} change${failedCount > 1 ? 's' : ''} failed to save`;
        statusEl.className = 'editor-status error';
        saveBtn.disabled = false;
      }

    } catch (error) {
      console.error('Save error:', error);
      statusEl.textContent = '❌ Error saving changes';
      statusEl.className = 'editor-status error';
      saveBtn.disabled = false;
    }
  }

  // Save content change
  async function saveContentChange(change) {
    const fieldKey = change.jsonPath || change.elementId;
    if (!change.pageId || !fieldKey) {
      console.warn('⚠️ Skipping content save: missing pageId or field_key', change);
      return { success: true }; // Don't block other saves
    }

    try {
      const response = await fetch('/editor/api/update-page-content/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCSRFToken()
        },
        body: JSON.stringify({
          page_id: change.pageId,
          field_key: fieldKey,
          value: change.value,
          language: getCurrentLanguage()
        })
      });

      const data = await response.json();

      if (data.success) {
        console.log('✅ Content saved:', fieldKey);
        return { success: true };
      } else {
        console.error('❌ Content save failed:', data.error);
        return { success: false, error: data.error };
      }
    } catch (error) {
      console.error('Content save error:', error);
      return { success: false, error: error.message };
    }
  }

  // Save class change
  async function saveClassChange(change) {
    if (!change.pageId || !change.elementId) {
      console.warn('⚠️ Skipping class save: missing pageId or elementId', change);
      return { success: true };
    }

    try {
      // Convert array of classes to space-separated string
      const classString = Array.isArray(change.value)
        ? change.value.join(' ')
        : change.value;

      const response = await fetch('/editor/api/update-page-classes/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCSRFToken()
        },
        body: JSON.stringify({
          page_id: change.pageId,
          element_id: change.elementId,
          new_classes: classString
        })
      });

      const data = await response.json();

      if (data.success) {
        console.log('✅ Classes saved:', change.elementId);
        return { success: true };
      } else {
        console.error('❌ Classes save failed:', data.error);
        return { success: false, error: data.error };
      }
    } catch (error) {
      console.error('Classes save error:', error);
      return { success: false, error: error.message };
    }
  }

  // Save attribute change
  async function saveAttributeChange(change) {
    if (!change.pageId) {
      console.warn('⚠️ Skipping attribute save: missing pageId', change);
      return { success: true };
    }

    // When elementId is missing, we need old_value + tag_name for fallback lookup
    if (!change.elementId && !change.oldValue) {
      console.warn('⚠️ Skipping attribute save: no elementId and no oldValue for fallback', change);
      return { success: true };
    }

    try {
      const payload = {
        page_id: change.pageId,
        element_id: change.elementId || null,
        attribute: change.value.name,
        value: change.value.value
      };

      // Send fallback data when elementId is missing
      if (!change.elementId) {
        payload.old_value = change.oldValue;
        payload.tag_name = change.element ? change.element.tagName.toLowerCase() : null;
        console.log('📌 Using old_value fallback for attribute save:', payload);
      }

      const response = await fetch('/editor/api/update-page-attribute/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCSRFToken()
        },
        body: JSON.stringify(payload)
      });

      const data = await response.json();

      if (data.success) {
        console.log('✅ Attribute saved:', change.value.name);
        return { success: true };
      } else {
        console.error('❌ Attribute save failed:', data.error);
        return { success: false, error: data.error };
      }
    } catch (error) {
      console.error('Attribute save error:', error);
      return { success: false, error: error.message };
    }
  }

  // Save AI-refined section
  async function saveAIPage() {
    try {
      const sectionName = window.SimpleSidebar ? window.SimpleSidebar.getLastSectionName() : null;

      if (!sectionName || !aiPageData || !aiPageData.html_template) {
        console.error('❌ Missing AI section data for save');
        return { success: false, error: 'Missing section data' };
      }

      console.log('💾 Saving AI section:', aiPageId, sectionName, aiPageData);

      const response = await fetch('/editor/api/save-ai-section/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCSRFToken()
        },
        body: JSON.stringify({
          page_id: aiPageId,
          section_name: sectionName,
          html_template: aiPageData.html_template,
          content: aiPageData.content
        })
      });

      const data = await response.json();

      if (data.success) {
        console.log('✅ AI section saved successfully');
        return { success: true };
      } else {
        console.error('❌ AI section save failed:', data.error);
        return { success: false, error: data.error };
      }
    } catch (error) {
      console.error('AI section save error:', error);
      return { success: false, error: error.message };
    }
  }

  // Discard changes
  function discardChanges() {
    if (!confirm('Are you sure you want to discard all unsaved changes?')) {
      return;
    }

    // If AI changes exist, revert them first
    if (aiPageData !== null && window.SimpleSidebar) {
      window.SimpleSidebar.revertAIChanges();
    }

    // Reload page to revert changes
    window.location.reload();
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

  // Get current language
  function getCurrentLanguage() {
    // Try to get from URL path
    const path = window.location.pathname;
    if (path.startsWith('/en/')) return 'en';
    if (path.startsWith('/pt/')) return 'pt';

    // Default to English
    return 'en';
  }

  // Get current value of an element for undo
  function getElementCurrentValue(change) {
    const element = change.element;
    if (!element) return null;

    if (change.type === 'content') {
      return element.innerHTML || element.textContent;
    } else if (change.type === 'classes') {
      return Array.from(element.classList).filter(c => !c.startsWith('editor-'));
    } else if (change.type === 'attribute') {
      return element.getAttribute(change.value.name) || '';
    }
    return null;
  }

  // Apply change to DOM element
  function applyChangeToDOM(change, value) {
    const element = change.element;
    if (!element) return;

    if (change.type === 'content') {
      if (element.tagName.match(/^H[1-6]$/)) {
        element.textContent = value;
      } else {
        element.innerHTML = value;
      }
    } else if (change.type === 'classes') {
      const classArray = Array.isArray(value) ? value : value.split(' ').filter(c => c.trim());
      element.className = classArray.join(' ');
    } else if (change.type === 'attribute') {
      if (value) {
        element.setAttribute(change.value.name, value);
      } else {
        element.removeAttribute(change.value.name);
      }
    }
  }

  // Undo last change
  function undo() {
    if (historyIndex < 0) return;

    const change = changeHistory[historyIndex];
    console.log('⏪ Undoing change:', change);

    // Revert DOM to old value
    applyChangeToDOM(change, change.oldValue);

    // Move back in history
    historyIndex--;

    // Remove from pending changes
    const pendingIndex = pendingChanges.findIndex(c =>
      c.pageId === change.pageId &&
      c.elementId === change.elementId &&
      c.type === change.type &&
      (c.type !== 'attribute' || c.value.name === change.value.name)
    );
    if (pendingIndex >= 0) {
      pendingChanges.splice(pendingIndex, 1);
    }

    updateUI();
    updateUndoRedoButtons();
  }

  // Redo last undone change
  function redo() {
    if (historyIndex >= changeHistory.length - 1) return;

    historyIndex++;
    const change = changeHistory[historyIndex];
    console.log('⏩ Redoing change:', change);

    // Reapply DOM change
    applyChangeToDOM(change, change.value);

    // Add back to pending changes
    pendingChanges.push(change);

    updateUI();
    updateUndoRedoButtons();
  }

  // Handle keyboard shortcuts
  function handleKeyboardShortcuts(e) {
    // Ignore if user is typing in an input field
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable) {
      return;
    }

    // Ctrl+Z or Cmd+Z - Undo
    if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) {
      e.preventDefault();
      undo();
    }

    // Ctrl+Y or Cmd+Y or Ctrl+Shift+Z - Redo
    if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) {
      e.preventDefault();
      redo();
    }
  }

  // Update undo/redo button states
  function updateUndoRedoButtons() {
    if (!undoBtn || !redoBtn) return;

    // Enable undo if we have history
    const canUndo = historyIndex >= 0;
    undoBtn.disabled = !canUndo;

    // Enable redo if we're not at the end of history
    const canRedo = historyIndex < changeHistory.length - 1;
    redoBtn.disabled = !canRedo;
  }

  // Public API
  window.SimpleTracker = {
    init: init,
    getPendingChanges: () => pendingChanges,
    clearChanges: () => {
      pendingChanges = [];
      updateUI();
    }
  };

  // Auto-init when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
