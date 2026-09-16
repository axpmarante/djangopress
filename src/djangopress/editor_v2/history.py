"""
One-click undo/redo over PageVersion snapshots.

Kinds (PageVersion.kind):
  auto        post-save snapshot written by core/signals.py (ignored here)
  checkpoint  state BEFORE a user operation, labelled with that operation
  undo        state BEFORE an undo ran (= the redo point), labelled like the undone op
  redo        state BEFORE a redo ran, labelled like the redone op

Undo target: walking newest→oldest, `undo` adds one pending undo, `redo` removes
one, and a `checkpoint` is either consumed by a pending undo or is the target.
Redo target: walking newest→oldest, `redo` adds one pending redo, `undo` is either
consumed by a pending redo or is the target, and a `checkpoint` (a new operation)
ends the search — there is nothing to redo any more.
"""


def find_undo_target(versions):
    pending_undos = 0
    for v in versions:
        if v.kind == 'undo':
            pending_undos += 1
        elif v.kind == 'redo':
            pending_undos -= 1
        elif v.kind == 'checkpoint':
            if pending_undos > 0:
                pending_undos -= 1
            else:
                return v
    return None


def find_redo_target(versions):
    pending_redos = 0
    for v in versions:
        if v.kind == 'redo':
            pending_redos += 1
        elif v.kind == 'undo':
            if pending_redos > 0:
                pending_redos -= 1
            else:
                return v
        elif v.kind == 'checkpoint':
            return None
    return None


def _entry(v):
    return {'version_number': v.version_number, 'label': v.change_summary} if v else None


def history_state(page):
    """{'undo': {...}|None, 'redo': {...}|None} for a Page; empty for other editables."""
    versions_rel = getattr(page, 'versions', None)
    if versions_rel is None or not hasattr(page, 'html_content_i18n'):
        return {'undo': None, 'redo': None}
    versions = list(versions_rel.order_by('-version_number').only('kind', 'change_summary', 'version_number'))
    return {'undo': _entry(find_undo_target(versions)), 'redo': _entry(find_redo_target(versions))}
