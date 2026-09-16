/**
 * Context Menu Module — right-click context menu with context-aware actions.
 */
import { events } from '../lib/events.js';
import { $, getContentWrapper, isTextElement, getCssSelector } from '../lib/dom.js';
import { insertBefore, insertAfterSection } from './section-inserter.js';
import {
  duplicateElement, moveElement, duplicateSection, moveSection,
  removeElement, removeSection, canMove, canMoveSection, insertElement,
} from '../lib/structural.js';
import { PRIMITIVES, buildSnippet, primitiveAnchor } from '../lib/snippets.js';

function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

const handlers = {};
let menu;

function getSection(el) {
  return el?.closest?.('[data-section]') || null;
}

function buildItems(el) {
  const items = [];
  const section = getSection(el);
  const aiEnabled = !!(window.EDITOR_CONFIG || {}).aiEnabled;

  if (isTextElement(el)) {
    items.push({ label: 'Edit Text', icon: '✎', hint: 'Dbl-click', action: () => events.emit('inline-edit:trigger', { element: el }) });
  }
  if (section) {
    const name = section.getAttribute('data-section');
    const selector = getCssSelector(el);
    const isElement = el !== section && !!selector;

    if (aiEnabled) {
      items.push(null);
      if (isElement) items.push({ label: 'AI Refine Element', icon: '✦', action: () => events.emit('context:ai-refine', { section: name, selector }) });
      items.push({ label: 'AI Refine Section', icon: '✦', action: () => events.emit('context:ai-refine', { section: name }) });
    }

    items.push(null);
    items.push({ label: 'Process Section Images', icon: '⬡', action: () => events.emit('process-images:open', { section: name }) });

    // Element verbs
    if (isElement) {
      items.push(null);
      const anchor = primitiveAnchor(el);
      const anchorSel = getCssSelector(anchor);
      if (anchorSel) {
        for (const p of PRIMITIVES) {
          items.push({ label: p.label, icon: '+', action: () => insertElement(anchorSel, 'after', buildSnippet(p.kind, anchor), { after: p.after }) });
        }
      }
      items.push({ label: 'Duplicate Element', icon: '⧉', action: () => duplicateElement(selector) });
      items.push({ label: 'Move Element Up', icon: '↑', disabled: !canMove(el, 'up'), action: () => moveElement(selector, 'up') });
      items.push({ label: 'Move Element Down', icon: '↓', disabled: !canMove(el, 'down'), action: () => moveElement(selector, 'down') });
      items.push({ label: 'Remove Element', icon: '✕', cls: 'danger', action: () => removeElement(selector) });
    }

    // Section verbs
    items.push(null);
    items.push({ label: 'Insert Section Before', icon: '+', action: () => insertBefore(name) });
    items.push({ label: 'Insert Section After', icon: '+', action: () => insertAfterSection(name) });
    items.push({ label: 'Duplicate Section', icon: '⧉', action: () => duplicateSection(name) });
    items.push({ label: 'Move Section Up', icon: '↑', disabled: !canMoveSection(section, 'up'), action: () => moveSection(name, 'up') });
    items.push({ label: 'Move Section Down', icon: '↓', disabled: !canMoveSection(section, 'down'), action: () => moveSection(name, 'down') });
    items.push({ label: 'Remove Section', icon: '✕', cls: 'danger', action: () => removeSection(name) });
  }

  items.push(null);
  items.push({ label: 'Copy Element HTML', icon: '⎘', action: () => navigator.clipboard.writeText(el.outerHTML) });
  if (section && section !== el) {
    items.push({ label: 'Select Section', icon: '▢', action: () => events.emit('selection:request', section) });
  }
  return items;
}

// ── Rendering ──

function renderMenu(items) {
  menu.innerHTML = items.map(item => {
    if (!item) return '<div class="ev2-context-sep"></div>';
    const hint = item.hint ? `<span class="ev2-command-result-hint">${esc(item.hint)}</span>` : '';
    const cls = (item.cls ? ` ev2-context-item--${item.cls}` : '') + (item.disabled ? ' ev2-context-item--disabled' : '');
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
  // A menu taller than the viewport (many items near the top edge) can still
  // end up with a negative top after the adjustment above; pin it on-screen
  // and let its own max-height/overflow handle the rest.
  if (menu.getBoundingClientRect().top < 0) menu.style.top = '4px';

  // Attach click handlers to items
  menu.querySelectorAll('.ev2-context-item').forEach(el => {
    const idx = parseInt(el.dataset.idx);
    const item = items[idx];
    if (!item || item.disabled) return;
    el.addEventListener('click', () => { hideMenu(); item.action(); });
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
