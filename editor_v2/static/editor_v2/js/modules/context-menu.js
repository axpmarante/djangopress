/**
 * Context Menu Module — right-click context menu with context-aware actions.
 */
import { events } from '../lib/events.js';
import { $, getContentWrapper, isTextElement } from '../lib/dom.js';

function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

const handlers = {};
let menu;

function getSection(el) {
  return el?.closest?.('[data-section]') || null;
}

function buildItems(el) {
  const items = [];
  const parent = el.parentElement;
  const section = getSection(el);

  if (parent && parent !== getContentWrapper()) {
    items.push({ label: 'Select Parent', icon: '↑', action: () => events.emit('selection:request', parent) });
  }
  if (isTextElement(el)) {
    items.push({ label: 'Edit Text', icon: '✎', hint: 'Dbl-click', action: () => events.emit('inline-edit:trigger', { element: el }) });
  }
  items.push({ label: 'Edit Classes', icon: '◑', action: () => events.emit('sidebar:switch-tab', 'design') });
  items.push(null); // separator
  if (section) {
    const name = section.getAttribute('data-section');
    const elId = el.getAttribute('data-element-id');
    if (elId && !el.hasAttribute('data-section')) {
      items.push({ label: 'AI Refine Element', icon: '✦', action: () => events.emit('context:ai-refine', { section: name, elementId: elId }) });
    }
    items.push({ label: 'AI Refine Section', icon: '✦', action: () => events.emit('context:ai-refine', { section: name }) });
    items.push(null);
  }
  items.push({ label: 'Copy Element HTML', icon: '⎘', action: () => navigator.clipboard.writeText(el.outerHTML) });
  if (section && section !== el) {
    items.push({ label: 'Select Section', icon: '▢', action: () => events.emit('selection:request', section) });
  }
  return items;
}

function renderMenu(items) {
  menu.innerHTML = items.map(item => {
    if (!item) return '<div class="ev2-context-sep"></div>';
    const hint = item.hint ? `<span class="ev2-command-result-hint">${esc(item.hint)}</span>` : '';
    return `<div class="ev2-context-item" data-idx="${items.indexOf(item)}">
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
