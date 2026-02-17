/**
 * Context Menu Module — right-click context menu with context-aware actions.
 */
import { events } from '../lib/events.js';
import { api } from '../lib/api.js';
import { $, getContentWrapper, isTextElement, getCssSelector } from '../lib/dom.js';
import { insertBefore, insertAfterSection } from './section-inserter.js';

function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

const config = () => window.EDITOR_CONFIG || {};
const handlers = {};
let menu;

function getSection(el) {
  return el?.closest?.('[data-section]') || null;
}

function buildItems(el) {
  const items = [];
  const section = getSection(el);

  if (isTextElement(el)) {
    items.push({ label: 'Edit Text', icon: '✎', hint: 'Dbl-click', action: () => events.emit('inline-edit:trigger', { element: el }) });
  }
  if (section) {
    const name = section.getAttribute('data-section');
    const selector = getCssSelector(el);

    items.push(null); // separator

    // AI refine — available for any element (not the section tag itself)
    if (selector && el !== section) {
      items.push({ label: 'AI Refine Element', icon: '✦', action: () => events.emit('context:ai-refine', { section: name, selector }) });
    }
    items.push({ label: 'AI Refine Section', icon: '✦', action: () => events.emit('context:ai-refine', { section: name }) });

    items.push(null); // separator

    // Process images
    items.push({ label: 'Process Section Images', icon: '⬡', action: () => events.emit('process-images:open', { section: name }) });

    items.push(null); // separator

    // Insert section
    items.push({ label: 'Insert Section Before', icon: '+', action: () => insertBefore(name) });
    items.push({ label: 'Insert Section After', icon: '+', action: () => insertAfterSection(name) });

    items.push(null); // separator

    // Remove — any element inside section is removable
    if (el !== section && selector) {
      items.push({ label: 'Remove Element', icon: '✕', cls: 'danger', action: () => confirmRemoveElement(selector) });
    }
    items.push({ label: 'Remove Section', icon: '✕', cls: 'danger', action: () => confirmRemoveSection(name) });
  }

  items.push(null); // separator
  items.push({ label: 'Copy Element HTML', icon: '⎘', action: () => navigator.clipboard.writeText(el.outerHTML) });
  if (section && section !== el) {
    items.push({ label: 'Select Section', icon: '▢', action: () => events.emit('selection:request', section) });
  }
  return items;
}

// ── Remove with confirmation ──

function confirmRemoveSection(sectionName) {
  if (!confirm(`Remove section "${sectionName}"? This can be undone via version history.`)) return;
  removeSection(sectionName);
}

async function removeSection(sectionName) {
  try {
    const res = await api.post('/remove-section/', {
      page_id: config().pageId,
      section_name: sectionName,
    });
    if (res.success) {
      window.location.reload();
    } else {
      alert('Failed to remove section: ' + (res.error || 'Unknown error'));
    }
  } catch (err) {
    alert('Failed to remove section: ' + (err.message || err));
  }
}

function confirmRemoveElement(selector) {
  if (!confirm('Remove this element? This can be undone via version history.')) return;
  removeElement(selector);
}

async function removeElement(selector) {
  try {
    const res = await api.post('/remove-element/', {
      page_id: config().pageId,
      selector: selector,
    });
    if (res.success) {
      window.location.reload();
    } else {
      alert('Failed to remove element: ' + (res.error || 'Unknown error'));
    }
  } catch (err) {
    alert('Failed to remove element: ' + (err.message || err));
  }
}

// ── Rendering ──

function renderMenu(items) {
  menu.innerHTML = items.map(item => {
    if (!item) return '<div class="ev2-context-sep"></div>';
    const hint = item.hint ? `<span class="ev2-command-result-hint">${esc(item.hint)}</span>` : '';
    const cls = item.cls ? ` ev2-context-item--${item.cls}` : '';
    return `<div class="ev2-context-item${cls}" data-idx="${items.indexOf(item)}">
      <span>${item.icon || ''}</span><span style="flex:1">${esc(item.label)}</span>${hint}
    </div>`;
  }).join('');
  return items;
}

function showMenu(x, y, items) {
  renderMenu(items);
  menu.classList.remove('hidden');
  menu.style.left = x + 'px';
  menu.style.top = y + 'px';

  // Adjust if overflowing viewport
  const rect = menu.getBoundingClientRect();
  if (rect.right > window.innerWidth) menu.style.left = (x - rect.width) + 'px';
  if (rect.bottom > window.innerHeight) menu.style.top = (y - rect.height) + 'px';

  // Attach click handlers to items
  menu.querySelectorAll('.ev2-context-item').forEach(el => {
    const idx = parseInt(el.dataset.idx);
    const item = items[idx];
    if (item) el.addEventListener('click', () => { hideMenu(); item.action(); });
  });
}

function hideMenu() {
  if (menu) menu.classList.add('hidden');
}

function onContextMenu(e) {
  const wrapper = getContentWrapper();
  if (!wrapper?.contains(e.target)) return;
  e.preventDefault();
  const items = buildItems(e.target);
  if (!items.length) return;
  showMenu(e.clientX, e.clientY, items);
}

function onKeydown(e) {
  if (e.key === 'Escape') hideMenu();
}

export function init() {
  menu = $('#ev2-context-menu');
  if (!menu) return;

  handlers.contextmenu = onContextMenu;
  handlers.click = hideMenu;
  handlers.keydown = onKeydown;
  handlers.scroll = hideMenu;

  document.addEventListener('contextmenu', handlers.contextmenu);
  document.addEventListener('click', handlers.click);
  document.addEventListener('keydown', handlers.keydown);
  window.addEventListener('scroll', handlers.scroll, true);
}

export function destroy() {
  document.removeEventListener('contextmenu', handlers.contextmenu);
  document.removeEventListener('click', handlers.click);
  document.removeEventListener('keydown', handlers.keydown);
  window.removeEventListener('scroll', handlers.scroll, true);
  hideMenu();
}
