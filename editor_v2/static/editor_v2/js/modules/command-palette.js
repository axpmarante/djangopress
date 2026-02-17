import { events } from '../lib/events.js';
import { shortcuts } from '../lib/shortcuts.js';

let paletteEl, inputEl, resultsEl, backdropEl;
let selectedIndex = 0;
let filtered = [];

const commands = [
  { label: 'Save changes', shortcut: 'Ctrl+S', action: () => events.emit('changes:save') },
  { label: 'Undo', shortcut: 'Ctrl+Z', action: () => events.emit('changes:undo') },
  { label: 'Redo', shortcut: 'Ctrl+Shift+Z', action: () => events.emit('changes:redo') },
  { label: 'Discard all changes', action: () => events.emit('changes:discard') },
  { label: 'Switch to Content tab', action: () => events.emit('sidebar:switch-tab', 'content') },
  { label: 'Switch to Design tab', action: () => events.emit('sidebar:switch-tab', 'design') },
  { label: 'Switch to Structure tab', action: () => events.emit('sidebar:switch-tab', 'structure') },
  { label: 'Switch to AI tab', action: () => events.emit('sidebar:switch-tab', 'ai') },
  { label: 'Process Images', action: () => events.emit('process-images:open', {}) },
];

function getAllCommands() {
  const all = [...commands];
  const registered = shortcuts.getAll();
  for (const s of registered) {
    if (s.combo === 'ctrl+k') continue;
    if (s.description && !all.some(c => c.label === s.description)) {
      all.push({ label: s.description, shortcut: s.combo });
    }
  }
  return all;
}

function open() {
  paletteEl.classList.remove('hidden');
  inputEl.value = '';
  selectedIndex = 0;
  filtered = getAllCommands();
  render();
  inputEl.focus();
}

function close() {
  paletteEl.classList.add('hidden');
}

function isOpen() {
  return !paletteEl.classList.contains('hidden');
}

function render() {
  resultsEl.innerHTML = '';
  filtered.forEach((cmd, i) => {
    const li = document.createElement('li');
    li.className = 'ev2-command-result' + (i === selectedIndex ? ' selected' : '');
    const labelSpan = document.createElement('span');
    labelSpan.textContent = cmd.label;
    li.appendChild(labelSpan);
    if (cmd.shortcut) {
      const hint = document.createElement('span');
      hint.className = 'ev2-command-result-hint';
      hint.textContent = cmd.shortcut;
      li.appendChild(hint);
    }
    li.addEventListener('click', () => execute(cmd));
    resultsEl.appendChild(li);
  });
}

function execute(cmd) {
  close();
  if (cmd.action) cmd.action();
}

function onInput() {
  const q = inputEl.value.toLowerCase();
  filtered = getAllCommands().filter(c => c.label.toLowerCase().includes(q));
  selectedIndex = 0;
  render();
}

function onKeydown(e) {
  if (!isOpen()) return;
  if (e.key === 'Escape') { e.preventDefault(); close(); return; }
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    selectedIndex = Math.min(selectedIndex + 1, filtered.length - 1);
    render();
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    selectedIndex = Math.max(selectedIndex - 1, 0);
    render();
  } else if (e.key === 'Enter') {
    e.preventDefault();
    if (filtered[selectedIndex]) execute(filtered[selectedIndex]);
  }
}

export function init() {
  paletteEl = document.getElementById('ev2-command-palette');
  inputEl = document.getElementById('ev2-command-input');
  resultsEl = document.getElementById('ev2-command-results');
  backdropEl = paletteEl.querySelector('.ev2-command-backdrop');
  if (!paletteEl) return;

  shortcuts.register('ctrl+k', () => { isOpen() ? close() : open(); }, 'Command palette');
  inputEl.addEventListener('input', onInput);
  document.addEventListener('keydown', onKeydown);
  backdropEl.addEventListener('click', close);
  // Also handle Ctrl+K when input is focused (shortcuts.js skips inputs)
  inputEl.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') { e.preventDefault(); close(); }
  });
}

export function destroy() {
  if (inputEl) inputEl.removeEventListener('input', onInput);
  document.removeEventListener('keydown', onKeydown);
  if (backdropEl) backdropEl.removeEventListener('click', close);
}
