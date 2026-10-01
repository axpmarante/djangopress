/**
 * AI saves reload the page; the toast after the reload says what happened to
 * the other languages (history.js shows it, with Undo).
 */
export function noteSaveAfterReload(res, what = 'Saved') {
    const up = (list) => list.map(l => l.toUpperCase()).join(', ');
    let label = what;
    if (res?.translated_languages?.length) label += ` · translated to ${up(res.translated_languages)} (review it there)`;
    if (res?.untranslated_languages?.length) label += ` · not translated to ${up(res.untranslated_languages)} — edit it there`;
    try { sessionStorage.setItem('ev2-toast-pending', JSON.stringify({ label })); } catch (_) { /* private mode */ }
}
