/**
 * Version Navigation — browse and restore DB page versions from the editor topbar.
 *
 * Uses the same DOM preview pattern as ai-panel.js (replace wrapper innerHTML,
 * restore on cancel). Navigating loads a version as a live preview without saving.
 * User can then "Restore" (commits to DB) or "Cancel" (returns to current).
 */
import { events } from '../lib/events.js';
import { api } from '../lib/api.js';
import { $ } from '../lib/dom.js';
import { shortcuts } from '../lib/shortcuts.js';
import { getPendingCount } from './changes.js';

const config = () => window.EDITOR_CONFIG || {};
function withEditableId(body) {
    const cfg = config();
    if (cfg.contentTypeId && cfg.objectId) { body.content_type_id = cfg.contentTypeId; body.object_id = cfg.objectId; }
    return body;
}

let unsubs = [];

// State
let versionList = [];      // [{version_number, change_summary, created_at, created_by}, ...]
let currentIndex = 0;      // 0 = latest (current page), higher = older
let isPreview = false;
let originalHtml = null;
let previewVersion = null;  // the version data currently shown

function detemplatize(html, translations, lang) {
    const trans = translations?.[lang] || {};
    return html.replace(/\{\{\s*trans\.(\w+)\s*\}\}/g, (_, key) => trans[key] || key);
}

export function init() {
    loadVersions();

    // Refresh version list after saves
    unsubs.push(events.on('changes:saved', () => loadVersions()));

    // Keyboard shortcuts
    shortcuts.register('ctrl+[', () => prev(), 'Previous version');
    shortcuts.register('ctrl+]', () => next(), 'Next version');

    // Bind static buttons
    $('#ev2-version-prev')?.addEventListener('click', prev);
    $('#ev2-version-next')?.addEventListener('click', next);
    $('#ev2-version-restore')?.addEventListener('click', restore);
    $('#ev2-version-cancel')?.addEventListener('click', cancel);
}

export function destroy() {
    unsubs.forEach(u => u());
    unsubs = [];
    shortcuts.unregister('ctrl+[');
    shortcuts.unregister('ctrl+]');
    cancel();
    versionList = [];
    currentIndex = 0;
}

/** Is a version preview currently active? Used by other modules to block actions. */
export function isPreviewing() {
    return isPreview;
}

async function loadVersions() {
    const pageId = config().pageId;
    if (!pageId) return;

    try {
        const res = await api.get(`/versions/${pageId}/`);
        if (res.success) {
            versionList = res.versions || [];
            // If we were previewing, reset to current
            if (!isPreview) currentIndex = 0;
            updateUI();
            // Show the nav once we know there are versions
            const nav = $('#ev2-version-nav');
            if (nav) nav.style.display = versionList.length > 0 ? '' : 'none';
        }
    } catch (err) {
        console.warn('Failed to load versions:', err);
    }
}

function canNavigate() {
    // Block if there are pending unsaved changes
    if (getPendingCount() > 0) {
        alert('Save or discard your changes before browsing versions.');
        return false;
    }
    return true;
}

async function prev() {
    if (!canNavigate()) return;
    if (currentIndex >= versionList.length - 1) return; // already at oldest
    currentIndex++;
    await showVersion();
}

async function next() {
    if (currentIndex <= 0) return; // already at latest
    if (!isPreview) return;
    currentIndex--;
    if (currentIndex === 0) {
        cancel();
        return;
    }
    await showVersion();
}

async function showVersion() {
    const version = versionList[currentIndex];
    if (!version) return;

    try {
        const res = await api.get(`/versions/${config().pageId}/${version.version_number}/`);
        if (!res.success) return;

        const versionData = res.version;
        previewVersion = versionData;

        // Store original page HTML before first preview
        const wrapper = document.querySelector('.editor-v2-content');
        if (!wrapper) return;
        if (!originalHtml) originalHtml = wrapper.innerHTML;

        // De-templatize and show
        const lang = config().language || 'pt';
        const translations = versionData.content?.translations || {};
        const html = detemplatize(versionData.html_content, translations, lang);
        wrapper.innerHTML = html;

        isPreview = true;
        document.body.classList.add('ev2-version-preview');
        showBar(versionData);
        updateUI();
    } catch (err) {
        console.error('Failed to load version:', err);
    }
}

function cancel() {
    if (!isPreview) return;
    const wrapper = document.querySelector('.editor-v2-content');
    if (wrapper && originalHtml) wrapper.innerHTML = originalHtml;
    originalHtml = null;
    previewVersion = null;
    isPreview = false;
    currentIndex = 0;
    document.body.classList.remove('ev2-version-preview');
    hideBar();
    updateUI();
}

async function restore() {
    if (!previewVersion) return;

    try {
        await api.post('/save-ai-page/', withEditableId({
            page_id: config().pageId,
            html_template: previewVersion.html_content,
            content: previewVersion.content,
        }));
        // Reload to show the restored version as current
        window.location.reload();
    } catch (err) {
        console.error('Failed to restore version:', err);
        alert('Failed to restore version: ' + err.message);
    }
}

function updateUI() {
    const label = $('#ev2-version-label');
    const prevBtn = $('#ev2-version-prev');
    const nextBtn = $('#ev2-version-next');

    if (!label || versionList.length === 0) return;

    const total = versionList.length;
    const current = versionList[currentIndex];
    const vNum = current ? current.version_number : 0;
    label.textContent = `v${vNum} / ${total}`;
    label.title = current?.change_summary || 'Version history';

    if (prevBtn) prevBtn.disabled = currentIndex >= total - 1;
    if (nextBtn) nextBtn.disabled = currentIndex <= 0;
}

function showBar(versionData) {
    const bar = $('#ev2-version-bar');
    const barLabel = $('#ev2-version-bar-label');
    if (!bar) return;

    const summary = versionData.change_summary
        ? ` \u2014 "${versionData.change_summary}"`
        : '';
    barLabel.textContent = `Previewing v${versionData.version_number}${summary}`;
    bar.style.display = '';
}

function hideBar() {
    const bar = $('#ev2-version-bar');
    if (bar) bar.style.display = 'none';
}
