# Design Consistency Reports — Design

## Problem

Running a design consistency analysis is an LLM call that takes time and costs tokens. Currently the results are only shown in-memory on the page — if the user navigates away, they're lost and must re-run the analysis. Users want to come back later to fix issues they skipped.

## Solution

Persist analysis reports to the database. Add a list page for past analyses and a detail page to review/fix issues from any saved report. Individual issues can be marked as "ignored" or "won't fix".

## Model

New model in `ai/models.py`:

```python
class DesignConsistencyReport(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    custom_rules = models.TextField(blank=True)
    model_used = models.CharField(max_length=50)
    report_data = models.JSONField()         # full report list from LLM
    summary = models.JSONField(default=dict) # {total_issues, severity, categories, affected_pages, total_pages}
    issue_statuses = models.JSONField(default=dict)  # {"page_3_issue_0": "ignored", ...}

    class Meta:
        ordering = ['-created_at']
```

Issue status keys: `page_{id}_issue_{index}` or `section_{key}_issue_{index}`. Values: `"ignored"` or `"wont_fix"`. Absence means "open".

## URLs

- `/backoffice/ai/design-consistency/` — existing analysis launcher (unchanged)
- `/backoffice/ai/design-consistency/reports/` — list of past analyses
- `/backoffice/ai/design-consistency/reports/<id>/` — detail view with fix + ignore/won't-fix actions
- `/backoffice/ai/design-consistency/reports/<id>/update-status/` — AJAX endpoint to update issue_statuses
- `/backoffice/ai/design-consistency/reports/<id>/delete/` — delete a report

## Flow Changes

1. After analysis completes (in `analyze_consistency_stream`), save the report to DB
2. SSE complete event includes `report_id` so the frontend can redirect to the detail page
3. Detail page renders the same results UI as current, plus per-issue ignore/won't-fix buttons
4. Fix flow works from the detail page using the stored `report_data`
5. List page shows: date, user, issue counts (open/ignored/won't-fix), link to detail

## Pages

### List Page (`consistency_reports`)
- Table with columns: Date, Custom Rules (truncated), Total Issues, Open, Ignored, Won't Fix, Actions
- Link to each report's detail page
- Delete button per report

### Detail Page (`consistency_report_detail`)
- Same results rendering as current (summary card, per-page issue cards)
- Each issue has dropdown/buttons: Open (default), Ignored, Won't Fix
- Status changes saved via AJAX to `update-status` endpoint
- "Fix Selected" button works as current, using stored report_data
- After fixing, the report_data is NOT updated (it's a snapshot) — user can re-run if needed

## Sidebar

Add "Reports" link under the existing "Design Consistency" sidebar entry, or make the sidebar link go to the list page with an "Analyze New" button there.
