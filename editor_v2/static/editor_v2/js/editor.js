/**
 * Editor v2 — main entry point.
 *
 * Loaded as <script type="module"> by the editor template.
 * Imports and initialises all feature modules in order.
 */

import * as changes       from './modules/changes.js';
import * as selection     from './modules/selection.js';
import * as sidebar       from './modules/sidebar.js';
import * as inlineEdit    from './modules/inline-edit.js';
import * as contextMenu   from './modules/context-menu.js';
import * as commandPalette from './modules/command-palette.js';
import * as aiPanel       from './modules/ai-panel.js';
import * as imagePicker   from './modules/image-picker.js';
import * as versions         from './modules/versions.js';
import * as sectionInserter  from './modules/section-inserter.js';
import * as sectionModal     from './modules/section-modal.js';
import * as processImages    from './modules/process-images.js';

document.addEventListener('DOMContentLoaded', () => {
    changes.init();
    selection.init();
    sidebar.init();
    inlineEdit.init();
    contextMenu.init();
    commandPalette.init();
    aiPanel.init();
    imagePicker.init();
    versions.init();
    sectionInserter.init();
    sectionModal.init();
    processImages.init();

    console.log('Editor v2 active');
});
