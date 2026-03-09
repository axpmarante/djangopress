# Design Consistency Reports — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Persist design consistency analysis results to the database so users can review past analyses, fix skipped issues later, and mark issues as ignored/won't fix.

**Architecture:** New `DesignConsistencyReport` model in `ai/models.py`. Three new backoffice views (list, detail, update-status). The existing analysis stream saves the report after completion and returns the `report_id`. The detail page reuses the same results/fix UI from the current template.

**Tech Stack:** Django models, JSON fields, backoffice views with Tailwind templates, AJAX for status updates.

---

### Task 1: Add DesignConsistencyReport Model

**Files:**
- Modify: `src/djangopress/ai/models.py`

**Step 1: Add the model to ai/models.py**

Add after the `RefinementSession` class at the end of the file:

```python
class DesignConsistencyReport(models.Model):
    """Persisted design consistency analysis report."""
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
    )
    custom_rules = models.TextField(blank=True, default='')
    model_used = models.CharField(max_length=50, default='')
    report_data = models.JSONField(default=list)
    summary = models.JSONField(default=dict)
    issue_statuses = models.JSONField(default=dict)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        total = self.summary.get('total_issues', 0)
        return f"Report #{self.pk} — {total} issues ({self.created_at:%Y-%m-%d %H:%M})"

    def get_open_count(self):
        total = self.summary.get('total_issues', 0)
        return total - len(self.issue_statuses)

    def get_ignored_count(self):
        return sum(1 for v in self.issue_statuses.values() if v == 'ignored')

    def get_wont_fix_count(self):
        return sum(1 for v in self.issue_statuses.values() if v == 'wont_fix')
```

**Step 2: Create and run migration**

```bash
cd /Users/antoniomarante/Documents/DjangoSites/djangopress
python -c "
import django; import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'djangopress.config.settings'
django.setup()
from django.core.management import call_command
call_command('makemigrations', 'ai')
"
```

**Step 3: Commit**

```bash
git add src/djangopress/ai/models.py src/djangopress/ai/migrations/
git commit -m "feat: add DesignConsistencyReport model"
```

---

### Task 2: Save Report in analyze_consistency_stream

**Files:**
- Modify: `src/djangopress/ai/views.py` (around line 2735, the `worker()` function inside `analyze_consistency_stream`)

**Step 1: Modify the worker to save the report**

In `analyze_consistency_stream`, inside the `worker()` function, after the summary is computed (around line 2770), save the report before putting the complete event on the queue. The `request.user` needs to be captured before entering the thread.

Before the thread creation (~line 2729), capture the user:

```python
current_user = request.user
```

Inside `worker()`, after the summary dict is built (after `'total_pages': len(report),`), add:

```python
                # Save report to DB
                from djangopress.ai.models import DesignConsistencyReport
                db_report = DesignConsistencyReport.objects.create(
                    created_by=current_user if current_user.is_authenticated else None,
                    custom_rules=custom_rules,
                    model_used=model,
                    report_data=report,
                    summary={
                        'total_issues': total_issues,
                        'severity': severity_counts,
                        'categories': categories,
                        'affected_pages': affected_pages,
                        'total_pages': len(report),
                    },
                )
```

And in the `q.put(('complete', {...}))` dict, add `'report_id': db_report.pk` alongside `'success'`, `'report'`, and `'summary'`.

**Step 2: Commit**

```bash
git add src/djangopress/ai/views.py
git commit -m "feat: save consistency report to DB after analysis"
```

---

### Task 3: Add Backoffice Views

**Files:**
- Modify: `src/djangopress/backoffice/views.py` (add 3 new views near `DesignConsistencyView`)
- Modify: `src/djangopress/backoffice/urls.py` (add 3 new URL patterns)

**Step 1: Add views to backoffice/views.py**

Add after the existing `DesignConsistencyView` class (~line 1270):

```python
class ConsistencyReportsView(SuperuserRequiredMixin, TemplateView):
    """List of past design consistency analysis reports."""
    template_name = 'backoffice/consistency_reports.html'

    def get_context_data(self, **kwargs):
        from djangopress.ai.models import DesignConsistencyReport
        context = super().get_context_data(**kwargs)
        context['reports'] = DesignConsistencyReport.objects.all()[:50]
        return context


class ConsistencyReportDetailView(SuperuserRequiredMixin, TemplateView):
    """Detail view for a saved design consistency report."""
    template_name = 'backoffice/consistency_report_detail.html'

    def get_context_data(self, **kwargs):
        from djangopress.ai.models import DesignConsistencyReport
        context = super().get_context_data(**kwargs)
        report = DesignConsistencyReport.objects.get(pk=kwargs['pk'])
        context['report'] = report
        return context
```

**Step 2: Add URL patterns to backoffice/urls.py**

After the existing `design_consistency` path (line 94):

```python
    path('ai/design-consistency/reports/', views.ConsistencyReportsView.as_view(), name='consistency_reports'),
    path('ai/design-consistency/reports/<int:pk>/', views.ConsistencyReportDetailView.as_view(), name='consistency_report_detail'),
```

**Step 3: Add the update-status API endpoint**

Add to `src/djangopress/backoffice/api_views.py` (or `views.py` as a function view):

```python
@superuser_required
@require_http_methods(["POST"])
def update_issue_status(request, pk):
    """Update issue_statuses on a DesignConsistencyReport."""
    from djangopress.ai.models import DesignConsistencyReport
    report = DesignConsistencyReport.objects.get(pk=pk)
    data = json.loads(request.body)
    issue_key = data.get('issue_key')
    status = data.get('status')  # 'ignored', 'wont_fix', or None to clear

    if status:
        report.issue_statuses[issue_key] = status
    else:
        report.issue_statuses.pop(issue_key, None)
    report.save(update_fields=['issue_statuses'])

    return JsonResponse({
        'success': True,
        'open': report.get_open_count(),
        'ignored': report.get_ignored_count(),
        'wont_fix': report.get_wont_fix_count(),
    })
```

Add URL:
```python
    path('ai/design-consistency/reports/<int:pk>/update-status/', views.update_issue_status, name='consistency_update_status'),
```

And a delete view:
```python
@superuser_required
@require_http_methods(["POST"])
def delete_consistency_report(request, pk):
    from djangopress.ai.models import DesignConsistencyReport
    DesignConsistencyReport.objects.filter(pk=pk).delete()
    return JsonResponse({'success': True})
```

URL:
```python
    path('ai/design-consistency/reports/<int:pk>/delete/', views.delete_consistency_report, name='consistency_report_delete'),
```

**Step 4: Commit**

```bash
git add src/djangopress/backoffice/views.py src/djangopress/backoffice/urls.py
git commit -m "feat: add consistency report list, detail, and status update views"
```

---

### Task 4: Create List Template

**Files:**
- Create: `src/djangopress/backoffice/templates/backoffice/consistency_reports.html`

**Step 1: Create the template**

Standard backoffice list page extending `backoffice/base.html`. Shows a table of past reports with:
- Date (created_at, formatted)
- Custom Rules (truncated to 60 chars)
- Total Issues
- Open count (badge, green if 0)
- Ignored count (badge)
- Won't Fix count (badge)
- Link to detail page
- Delete button (with confirmation)

Include a prominent "Run New Analysis" button linking to the existing `/backoffice/ai/design-consistency/` page.

Follow the styling patterns from existing backoffice list templates (e.g., pages list, AI logs). Use the same breadcrumb, header, and table styling.

**Step 2: Commit**

```bash
git add src/djangopress/backoffice/templates/backoffice/consistency_reports.html
git commit -m "feat: add consistency reports list template"
```

---

### Task 5: Create Detail Template

**Files:**
- Create: `src/djangopress/backoffice/templates/backoffice/consistency_report_detail.html`

**Step 1: Create the template**

This template reuses the same results rendering from the current `design_consistency.html` — the summary card, per-page issue cards, fix flow, and fix summary. Key differences:

- Loads report data from `{{ report }}` context variable (JSON) instead of from the SSE response
- Each issue card has a status dropdown with options: Open, Ignored, Won't Fix
- Status changes are saved via AJAX POST to the `consistency_update_status` URL
- Issues marked as ignored/won't_fix are visually dimmed (opacity, strikethrough)
- The "Fix Selected" button only sends open issues (not ignored/won't_fix ones)
- The fix SSE flow works exactly as in the current template
- Breadcrumb: Dashboard > Design Consistency > Reports > Report #N

Pass `report.report_data`, `report.summary`, and `report.issue_statuses` as JSON into JS variables:

```html
<script>
    const reportId = {{ report.pk }};
    const analysisReport = {{ report.report_data|safe }};
    const analysisSummary = {{ report.summary|safe }};
    const issueStatuses = {{ report.issue_statuses|safe }};
</script>
```

For the status dropdown per issue, use a key format `page_{page_id}_issue_{issue_index}` or `section_{section_key}_issue_{issue_index}`. On change, POST to update-status endpoint:

```javascript
async function updateIssueStatus(issueKey, status) {
    await fetch(`/backoffice/ai/design-consistency/reports/${reportId}/update-status/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken'),
        },
        body: JSON.stringify({ issue_key: issueKey, status: status || null }),
    });
}
```

**Step 2: Commit**

```bash
git add src/djangopress/backoffice/templates/backoffice/consistency_report_detail.html
git commit -m "feat: add consistency report detail template with fix and status management"
```

---

### Task 6: Update Existing Analysis Page

**Files:**
- Modify: `src/djangopress/backoffice/templates/backoffice/design_consistency.html`

**Step 1: Redirect to detail page after analysis**

In the `onComplete` callback of the analysis SSE client (~line 358), after receiving `data.success` and `data.report_id`, redirect to the detail page instead of rendering results inline:

```javascript
onComplete: function(data) {
    hideLoading();
    setButtonLoading(analyzeBtn, false);

    if (data.success && data.report_id) {
        window.location.href = '/backoffice/ai/design-consistency/reports/' + data.report_id + '/';
    } else if (data.success) {
        // Fallback: render inline if no report_id (shouldn't happen)
        analysisReport = data.report;
        renderResults(data.report, data.summary);
    } else {
        alert('Analysis failed: ' + (data.error || 'Unknown error'));
    }
},
```

**Step 2: Add "Past Reports" link**

Add a link/button near the "Analyze All Pages" button:

```html
<a href="{% url 'backoffice:consistency_reports' %}" class="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50">
    View Past Reports
</a>
```

**Step 3: Commit**

```bash
git add src/djangopress/backoffice/templates/backoffice/design_consistency.html
git commit -m "feat: redirect to saved report after analysis, add past reports link"
```

---

### Task 7: Update Sidebar

**Files:**
- Modify: `src/djangopress/backoffice/templates/backoffice/includes/sidebar.html` (~line 193)

**Step 1: Update sidebar link**

Change the Design Consistency sidebar link to point to the reports list page. Update the active state check to match both URLs:

```html
<a href="{% url 'backoffice:consistency_reports' %}"
   class="flex items-center px-4 py-3 text-gray-300 rounded-lg hover:bg-gray-800 hover:text-white transition-colors {% if 'design-consistency' in request.path %}bg-gray-800 text-white{% endif %}">
```

**Step 2: Commit**

```bash
git add src/djangopress/backoffice/templates/backoffice/includes/sidebar.html
git commit -m "feat: sidebar links to consistency reports list"
```

---

### Task 8: Version Bump and Final Commit

**Step 1: Bump version to 2.5.0** (minor — new feature)

- `pyproject.toml`: `version = "2.5.0"`
- `src/djangopress/__init__.py`: `__version__ = '2.5.0'`

**Step 2: Run migration in a child project to verify**

```bash
cd /Users/antoniomarante/Documents/DjangoSites/centralgarve
pip install -e /Users/antoniomarante/Documents/DjangoSites/djangopress
python manage.py migrate
python manage.py check
```

**Step 3: Commit and push**

```bash
cd /Users/antoniomarante/Documents/DjangoSites/djangopress
git add pyproject.toml src/djangopress/__init__.py
git commit -m "feat: design consistency reports — persist and review analyses (v2.5.0)"
git push
```
