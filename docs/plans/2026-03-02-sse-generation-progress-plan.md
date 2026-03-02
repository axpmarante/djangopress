# SSE Real-Time Generation Progress — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace simulated/fake progress indicators with real-time Server-Sent Events (SSE) that report actual step completion during AI page generation and refinement.

**Architecture:** Add an `on_progress` callback parameter to service methods. New SSE view endpoints wrap the service in a thread and yield `text/event-stream` events as steps complete. Frontend reads the stream via `fetch()` + `ReadableStream` and updates a step-list UI. Original synchronous endpoints stay for backward compatibility (management commands, `generate_site`).

**Tech Stack:** Django `StreamingHttpResponse`, native browser `ReadableStream` API, `queue.Queue` for thread→generator communication. Zero new dependencies.

---

## Task 1: Add `on_progress` callback to `generate_page()`

**Files:**
- Modify: `ai/services.py:578-712`

**Step 1: Add the callback parameter**

In `generate_page()` at line 578, add `on_progress=None` to the signature:

```python
def generate_page(
    self,
    brief: str,
    language: str = 'pt',
    model_override: str = None,
    reference_images: list = None,
    outline: list = None,
    on_progress=None,        # NEW
) -> Dict:
```

**Step 2: Add a `notify` helper inside the method**

Right after the docstring (around line 600), add:

```python
def notify(step, status, **extra):
    if on_progress:
        on_progress({"step": step, "status": status, **extra})
```

**Step 3: Insert notify calls at each pipeline step**

Insert `notify()` calls around the existing steps. Do NOT change any logic — just add calls before and after each step:

1. **Before component selection** (~line 624):
   ```python
   notify("component_selection", "running")
   ```
   **After component selection** (~line 630):
   ```python
   notify("component_selection", "done")
   ```

2. **Before HTML generation LLM call** (~line 654):
   ```python
   notify("html_generation", "running", model=model)
   ```
   **After HTML extraction** (~line 693):
   ```python
   notify("html_generation", "done", chars=len(raw_html))
   ```

3. **Before parallel step 2+3** (~line 697):
   ```python
   notify("templatize_translate", "running")
   ```
   **After parallel step 2+3** (~line 706):
   ```python
   notify("templatize_translate", "done")
   ```

4. **At the end** (~line 711):
   ```python
   notify("complete", "done")
   ```

**Step 4: Verify existing callers are unaffected**

Run: `cd /Users/antoniomarante/Documents/DjangoSites/djangopress && grep -rn "generate_page(" ai/ --include="*.py" | grep -v "test_" | grep -v "__pycache__"`

Confirm all existing callers don't pass `on_progress`, so the default `None` keeps them working.

**Step 5: Commit**

```bash
git add ai/services.py
git commit -m "feat(ai): add on_progress callback to generate_page"
```

---

## Task 2: Add `on_progress` callback to `refine_page_with_html()`

**Files:**
- Modify: `ai/services.py:909-1090`

**Step 1: Add the callback parameter**

In `refine_page_with_html()` at line 909, add `on_progress=None`:

```python
def refine_page_with_html(
    self,
    page_id: int,
    instructions: str,
    section_name: str = None,
    language: str = 'pt',
    model_override: str = None,
    reference_images: list = None,
    conversation_history: str = None,
    handle_images: bool = False,
    on_progress=None,        # NEW
) -> Dict:
```

**Step 2: Add `notify` helper and calls**

Same pattern as Task 1. Insert around key steps:

1. Before/after de-templatize (~line 976): `notify("prepare", "running/done")`
2. Before/after component selection (~line 990): `notify("component_selection", "running/done")`
3. Before/after refinement LLM call (~line 1041): `notify("refine_html", "running/done", model=model)`
4. Before/after templatize+translate (~line 1087): `notify("templatize_translate", "running/done")`
5. At the end: `notify("complete", "done")`

**Step 3: Commit**

```bash
git add ai/services.py
git commit -m "feat(ai): add on_progress callback to refine_page_with_html"
```

---

## Task 3: Add `on_progress` callback to `refine_global_section()`

**Files:**
- Modify: `ai/services.py:714-907`

**Step 1: Add the callback parameter**

```python
def refine_global_section(
    self,
    section_key: str,
    refinement_instructions: str,
    model_override: str = None,
    prompt_version: str = 'v2',
    on_progress=None,        # NEW
) -> Dict:
```

**Step 2: Add notify calls**

1. Before/after loading section from DB: `notify("load_section", ...)`
2. Before/after building prompt: `notify("build_prompt", ...)`
3. Before/after LLM call: `notify("refine_html", ...)`
4. Before/after templatize+translate: `notify("templatize_translate", ...)`
5. At end: `notify("complete", "done")`

**Step 3: Commit**

```bash
git add ai/services.py
git commit -m "feat(ai): add on_progress callback to refine_global_section"
```

---

## Task 4: Create SSE streaming utility

**Files:**
- Create: `ai/utils/sse.py`

**Step 1: Create the SSE helper module**

```python
"""
Server-Sent Events (SSE) utilities for streaming AI progress to the browser.
"""
import json
import queue
import threading
from django.http import StreamingHttpResponse


def sse_event(data, event=None):
    """Format a single SSE event string."""
    lines = []
    if event:
        lines.append(f"event: {event}")
    lines.append(f"data: {json.dumps(data)}")
    lines.append("")
    lines.append("")
    return "\n".join(lines)


def run_with_progress(service_method, kwargs, timeout=300):
    """
    Run a service method in a background thread, yielding SSE events
    as the on_progress callback fires.

    Args:
        service_method: Bound method (e.g. service.generate_page)
        kwargs: Dict of keyword arguments for the method
        timeout: Max seconds to wait for completion

    Yields:
        SSE-formatted strings (event + data lines)
    """
    progress_queue = queue.Queue()
    result_holder = {}

    def on_progress(event_data):
        progress_queue.put(("progress", event_data))

    def worker():
        try:
            result = service_method(**kwargs, on_progress=on_progress)
            result_holder["result"] = result
            progress_queue.put(("done", None))
        except Exception as e:
            progress_queue.put(("error", str(e)))

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    while True:
        try:
            msg_type, payload = progress_queue.get(timeout=timeout)
        except queue.Empty:
            yield sse_event({"error": "Generation timed out"}, event="error")
            return

        if msg_type == "progress":
            yield sse_event(payload, event="progress")
        elif msg_type == "done":
            yield sse_event({"success": True, "page_data": result_holder["result"]}, event="complete")
            return
        elif msg_type == "error":
            yield sse_event({"error": payload}, event="error")
            return


def sse_response(generator):
    """Wrap an SSE generator in a StreamingHttpResponse."""
    response = StreamingHttpResponse(
        generator,
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
```

**Step 2: Commit**

```bash
git add ai/utils/sse.py
git commit -m "feat(ai): add SSE streaming utility module"
```

---

## Task 5: Create SSE view for page generation

**Files:**
- Modify: `ai/views.py` (add new view function after `generate_page_api`)
- Modify: `ai/urls.py` (add new URL pattern)

**Step 1: Add the streaming view to `ai/views.py`**

Add after the existing `generate_page_api` function (~line 113):

```python
@superuser_required
@require_http_methods(["POST"])
def generate_page_stream(request):
    """SSE endpoint for page generation with real-time progress."""
    from .utils.sse import run_with_progress, sse_response

    content_type = request.content_type or ''

    if 'multipart' in content_type:
        brief = request.POST.get('brief', '')
        language = request.POST.get('language', 'pt')
        model = request.POST.get('model', None)
        reference_images = request.FILES.getlist('reference_images', [])
    else:
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            data = {}
        brief = data.get('brief', '')
        language = data.get('language', 'pt')
        model = data.get('model', None)
        reference_images = []

    if not brief:
        from .utils.sse import sse_event
        return sse_response(iter([sse_event({"error": "Brief is required"}, event="error")]))

    service = ContentGenerationService()
    kwargs = {
        "brief": brief,
        "language": language,
        "model_override": model,
        "reference_images": reference_images if reference_images else None,
    }

    return sse_response(run_with_progress(service.generate_page, kwargs))
```

**Step 2: Add URL pattern to `ai/urls.py`**

Add after line 11 (`generate-page/`):

```python
path('api/generate-page/stream/', views.generate_page_stream, name='generate_page_stream'),
```

**Step 3: Commit**

```bash
git add ai/views.py ai/urls.py
git commit -m "feat(ai): add SSE streaming endpoint for page generation"
```

---

## Task 6: Create SSE views for chat refinement and header/footer

**Files:**
- Modify: `ai/views.py` (add 3 new view functions)
- Modify: `ai/urls.py` (add 3 new URL patterns)

**Step 1: Add chat refinement streaming view**

Add after `chat_refine_page_api` (~line 710). This follows the same pattern as the existing `chat_refine_page_api` but wraps the service call in SSE:

```python
@superuser_required
@require_http_methods(["POST"])
def chat_refine_page_stream(request):
    """SSE endpoint for chat-based page refinement with real-time progress."""
    from .utils.sse import run_with_progress, sse_response, sse_event
    from .models import RefinementSession

    content_type = request.content_type or ''
    if 'multipart' in content_type:
        message = request.POST.get('message', '')
        page_id = request.POST.get('page_id')
        session_id = request.POST.get('session_id')
        model = request.POST.get('model', None)
        handle_images = request.POST.get('handle_images', 'false').lower() == 'true'
        reference_images = request.FILES.getlist('reference_images', [])
    else:
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            data = {}
        message = data.get('message', '')
        page_id = data.get('page_id')
        session_id = data.get('session_id')
        model = data.get('model', None)
        handle_images = data.get('handle_images', False)
        reference_images = []

    if not message or not page_id:
        return sse_response(iter([sse_event({"error": "Message and page_id required"}, event="error")]))

    try:
        page = Page.objects.get(id=page_id)
    except Page.DoesNotExist:
        return sse_response(iter([sse_event({"error": "Page not found"}, event="error")]))

    # Session management (same as chat_refine_page_api)
    session = None
    conversation_history = ''
    if session_id:
        try:
            session = RefinementSession.objects.get(id=session_id, page=page)
            conversation_history = session.get_formatted_history()
        except RefinementSession.DoesNotExist:
            pass

    if not session:
        session = RefinementSession(
            page=page,
            title=message[:80],
            model_used=model or 'gemini-flash',
            created_by=request.user if request.user.is_authenticated else None,
        )
        session.save()

    session.add_message('user', message)

    service = ContentGenerationService()
    kwargs = {
        "page_id": page.id,
        "instructions": message,
        "language": page.get_default_language(),
        "model_override": model,
        "reference_images": reference_images if reference_images else None,
        "conversation_history": conversation_history,
        "handle_images": handle_images,
    }

    # We need to wrap run_with_progress to also handle post-processing
    # (session save, diff computation) after the service completes
    import queue as queue_mod
    progress_queue = queue_mod.Queue()
    result_holder = {}

    def on_progress(event_data):
        progress_queue.put(("progress", event_data))

    def worker():
        try:
            result = service.refine_page_with_html(**kwargs, on_progress=on_progress)

            # Post-processing: save to DB, compute diff (same as chat_refine_page_api)
            old_sections = set()
            import re
            for match in re.finditer(r'data-section="([^"]+)"', page.html_content or ''):
                old_sections.add(match.group(1))

            page.html_content = result['html_content']
            page.content = result['content']
            page.save()

            new_sections = set()
            for match in re.finditer(r'data-section="([^"]+)"', result['html_content']):
                new_sections.add(match.group(1))

            sections_changed = list(new_sections - old_sections) if new_sections != old_sections else ['content updated']

            assistant_msg = f"I've updated the page based on your request. Sections affected: {', '.join(sections_changed)}"
            session.add_message('assistant', assistant_msg)
            session.save()

            result_holder["result"] = {
                "session_id": session.id,
                "assistant_message": assistant_msg,
                "sections_changed": sections_changed,
                "html_content": result['html_content'],
                "content": result['content'],
            }
            progress_queue.put(("done", None))
        except Exception as e:
            progress_queue.put(("error", str(e)))

    import threading
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    def event_generator():
        while True:
            try:
                msg_type, payload = progress_queue.get(timeout=300)
            except queue_mod.Empty:
                yield sse_event({"error": "Refinement timed out"}, event="error")
                return
            if msg_type == "progress":
                yield sse_event(payload, event="progress")
            elif msg_type == "done":
                yield sse_event({"success": True, **result_holder["result"]}, event="complete")
                return
            elif msg_type == "error":
                yield sse_event({"error": payload}, event="error")
                return

    return sse_response(event_generator())
```

**Step 2: Add header/footer streaming views**

Add after the existing `refine_header_api` and `refine_footer_api`:

```python
@superuser_required
@require_http_methods(["POST"])
def refine_header_stream(request):
    """SSE endpoint for header refinement."""
    from .utils.sse import run_with_progress, sse_response, sse_event

    data = json.loads(request.body) if request.body else {}
    instructions = data.get('instructions', '')
    model = data.get('model', None)

    if not instructions:
        return sse_response(iter([sse_event({"error": "Instructions required"}, event="error")]))

    service = ContentGenerationService()
    kwargs = {
        "section_key": "main-header",
        "refinement_instructions": instructions,
        "model_override": model,
    }

    # Custom wrapper to save after completion
    import queue as queue_mod
    progress_queue = queue_mod.Queue()
    result_holder = {}

    def on_progress(event_data):
        progress_queue.put(("progress", event_data))

    def worker():
        try:
            from core.models import GlobalSection
            result = service.refine_global_section(**kwargs, on_progress=on_progress)
            section, _ = GlobalSection.objects.get_or_create(key='main-header')
            section.html_template = result['html_template']
            section.content = result['content']
            section.save()
            result_holder["result"] = result
            progress_queue.put(("done", None))
        except Exception as e:
            progress_queue.put(("error", str(e)))

    import threading
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    def event_generator():
        while True:
            try:
                msg_type, payload = progress_queue.get(timeout=300)
            except queue_mod.Empty:
                yield sse_event({"error": "Timed out"}, event="error")
                return
            if msg_type == "progress":
                yield sse_event(payload, event="progress")
            elif msg_type == "done":
                yield sse_event({"success": True, "data": result_holder["result"]}, event="complete")
                return
            elif msg_type == "error":
                yield sse_event({"error": payload}, event="error")
                return

    return sse_response(event_generator())


@superuser_required
@require_http_methods(["POST"])
def refine_footer_stream(request):
    """SSE endpoint for footer refinement."""
    from .utils.sse import run_with_progress, sse_response, sse_event

    data = json.loads(request.body) if request.body else {}
    instructions = data.get('instructions', '')
    model = data.get('model', None)

    if not instructions:
        return sse_response(iter([sse_event({"error": "Instructions required"}, event="error")]))

    service = ContentGenerationService()
    kwargs = {
        "section_key": "main-footer",
        "refinement_instructions": instructions,
        "model_override": model,
    }

    import queue as queue_mod
    progress_queue = queue_mod.Queue()
    result_holder = {}

    def on_progress(event_data):
        progress_queue.put(("progress", event_data))

    def worker():
        try:
            from core.models import GlobalSection
            result = service.refine_global_section(**kwargs, on_progress=on_progress)
            section, _ = GlobalSection.objects.get_or_create(key='main-footer')
            section.html_template = result['html_template']
            section.content = result['content']
            section.save()
            result_holder["result"] = result
            progress_queue.put(("done", None))
        except Exception as e:
            progress_queue.put(("error", str(e)))

    import threading
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    def event_generator():
        while True:
            try:
                msg_type, payload = progress_queue.get(timeout=300)
            except queue_mod.Empty:
                yield sse_event({"error": "Timed out"}, event="error")
                return
            if msg_type == "progress":
                yield sse_event(payload, event="progress")
            elif msg_type == "done":
                yield sse_event({"success": True, "data": result_holder["result"]}, event="complete")
                return
            elif msg_type == "error":
                yield sse_event({"error": payload}, event="error")
                return

    return sse_response(event_generator())
```

**Step 3: Add URL patterns to `ai/urls.py`**

Add after the existing patterns:

```python
# SSE streaming endpoints
path('api/chat-refine-page/stream/', views.chat_refine_page_stream, name='chat_refine_page_stream'),
path('api/refine-header/stream/', views.refine_header_stream, name='refine_header_stream'),
path('api/refine-footer/stream/', views.refine_footer_stream, name='refine_footer_stream'),
```

**Step 4: Commit**

```bash
git add ai/views.py ai/urls.py
git commit -m "feat(ai): add SSE streaming endpoints for chat refine, header, and footer"
```

---

## Task 7: Create reusable JS SSE client

**Files:**
- Create: `backoffice/static/backoffice/js/sse-client.js`

**Step 1: Create the SSE client module**

This is a shared JS utility all templates will use:

```javascript
/**
 * SSE client for streaming AI generation progress.
 *
 * Usage:
 *   const sse = new SSEClient('/ai/api/generate-page/stream/', {
 *     csrfToken: '...',
 *     onProgress: (data) => updateStepUI(data),
 *     onComplete: (data) => showResults(data),
 *     onError: (data) => showError(data),
 *   });
 *   sse.start(formData);   // FormData or plain object
 */
class SSEClient {
    constructor(url, { csrfToken, onProgress, onComplete, onError }) {
        this.url = url;
        this.csrfToken = csrfToken;
        this.onProgress = onProgress || (() => {});
        this.onComplete = onComplete || (() => {});
        this.onError = onError || (() => {});
        this._abortController = null;
    }

    async start(body) {
        this._abortController = new AbortController();

        const isFormData = body instanceof FormData;
        const headers = { 'X-CSRFToken': this.csrfToken };
        if (!isFormData) {
            headers['Content-Type'] = 'application/json';
            body = JSON.stringify(body);
        }

        try {
            const response = await fetch(this.url, {
                method: 'POST',
                headers,
                body,
                signal: this._abortController.signal,
            });

            if (!response.ok) {
                this.onError({ error: `HTTP ${response.status}` });
                return;
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const events = this._parseEvents(buffer);
                buffer = events.remaining;

                for (const evt of events.parsed) {
                    if (evt.event === 'progress') {
                        this.onProgress(evt.data);
                    } else if (evt.event === 'complete') {
                        this.onComplete(evt.data);
                    } else if (evt.event === 'error') {
                        this.onError(evt.data);
                    }
                }
            }
        } catch (err) {
            if (err.name !== 'AbortError') {
                this.onError({ error: err.message });
            }
        }
    }

    abort() {
        if (this._abortController) {
            this._abortController.abort();
        }
    }

    _parseEvents(buffer) {
        const parsed = [];
        const blocks = buffer.split('\n\n');
        // Last block may be incomplete — keep it in the buffer
        const remaining = blocks.pop();

        for (const block of blocks) {
            if (!block.trim()) continue;
            let event = 'message';
            let dataLines = [];

            for (const line of block.split('\n')) {
                if (line.startsWith('event: ')) {
                    event = line.slice(7).trim();
                } else if (line.startsWith('data: ')) {
                    dataLines.push(line.slice(6));
                }
            }

            if (dataLines.length > 0) {
                try {
                    const data = JSON.parse(dataLines.join('\n'));
                    parsed.push({ event, data });
                } catch (e) {
                    // Skip malformed events
                }
            }
        }

        return { parsed, remaining };
    }
}
```

**Step 2: Commit**

```bash
git add backoffice/static/backoffice/js/sse-client.js
git commit -m "feat(backoffice): add reusable SSE client for AI progress streaming"
```

---

## Task 8: Update Generate Page template to use SSE

**Files:**
- Modify: `backoffice/templates/backoffice/ai_generate_page.html:194-211` (loading modal)
- Modify: `backoffice/templates/backoffice/ai_generate_page.html:393-474` (form submission + simulateProgress)

**Step 1: Replace the loading modal HTML (lines 195-211)**

Replace the simple spinner + progress bar with a step-list UI:

```html
<!-- Loading Indicator -->
<div id="loadingModal" class="hidden fixed inset-0 bg-gray-900 bg-opacity-50 z-50 flex items-center justify-center">
    <div class="bg-white rounded-lg p-8 max-w-md w-full mx-4 shadow-2xl">
        <div class="flex flex-col items-center">
            <div class="relative">
                <div class="animate-spin rounded-full h-16 w-16 border-b-4 border-purple-600"></div>
                <svg class="w-8 h-8 text-purple-600 absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/>
                </svg>
            </div>
            <p id="loadingTitle" class="mt-4 text-lg font-semibold text-gray-900">Generating your page...</p>
            <div id="stepList" class="mt-4 w-full space-y-2 text-sm">
                <div data-step="component_selection" class="flex items-center gap-2 text-gray-400">
                    <span class="step-icon w-5 h-5 flex items-center justify-center">&#9675;</span>
                    <span>Selecting components</span>
                    <span class="step-time ml-auto"></span>
                </div>
                <div data-step="html_generation" class="flex items-center gap-2 text-gray-400">
                    <span class="step-icon w-5 h-5 flex items-center justify-center">&#9675;</span>
                    <span>Generating HTML</span>
                    <span class="step-time ml-auto"></span>
                </div>
                <div data-step="templatize_translate" class="flex items-center gap-2 text-gray-400">
                    <span class="step-icon w-5 h-5 flex items-center justify-center">&#9675;</span>
                    <span>Extracting &amp; translating text</span>
                    <span class="step-time ml-auto"></span>
                </div>
            </div>
            <div id="progressBar" class="mt-4 w-full bg-gray-200 rounded-full h-1.5">
                <div id="progressFill" class="bg-purple-600 h-1.5 rounded-full transition-all duration-300" style="width: 0%"></div>
            </div>
        </div>
    </div>
</div>
```

**Step 2: Add the SSE client script tag**

Before the closing `{% endblock %}` or at the bottom of the script area, add:

```html
<script src="{% static 'backoffice/js/sse-client.js' %}"></script>
```

**Step 3: Replace `simulateProgress()` and the fetch call**

Replace the form submission handler (lines ~393-474) to use the SSE client. The key change is swapping the `fetch()` + `simulateProgress()` with `SSEClient`:

```javascript
// Replace the existing form submit handler
document.getElementById('generateForm').addEventListener('submit', async function(e) {
    e.preventDefault();
    showLoading();

    const formData = new FormData(this);
    const stepTimers = {};

    const STEP_PROGRESS = {
        component_selection: 15,
        html_generation: 70,
        templatize_translate: 100,
    };

    const sse = new SSEClient("{% url 'ai:generate_page_stream' %}", {
        csrfToken: '{{ csrf_token }}',
        onProgress: (data) => {
            const stepEl = document.querySelector(`[data-step="${data.step}"]`);
            if (!stepEl) return;

            if (data.status === 'running') {
                stepEl.classList.remove('text-gray-400');
                stepEl.classList.add('text-purple-700', 'font-medium');
                stepEl.querySelector('.step-icon').innerHTML = '<span class="animate-spin inline-block">&#9696;</span>';
                stepTimers[data.step] = Date.now();
            } else if (data.status === 'done') {
                stepEl.classList.remove('text-purple-700');
                stepEl.classList.add('text-green-600');
                stepEl.querySelector('.step-icon').innerHTML = '&#10003;';
                if (stepTimers[data.step]) {
                    const elapsed = ((Date.now() - stepTimers[data.step]) / 1000).toFixed(1);
                    stepEl.querySelector('.step-time').textContent = elapsed + 's';
                }
                document.getElementById('progressFill').style.width = (STEP_PROGRESS[data.step] || 0) + '%';
            }
        },
        onComplete: (data) => {
            document.getElementById('progressFill').style.width = '100%';
            hideLoading();
            if (data.success && data.page_data) {
                window.generatedPageData = data.page_data;
                displayResults(data.page_data);
            }
        },
        onError: (data) => {
            hideLoading();
            alert('Generation failed: ' + (data.error || 'Unknown error'));
        },
    });

    sse.start(formData);
});
```

**Step 4: Remove old `simulateProgress()` function**

Delete lines 463-474 (the `simulateProgress` function) — it's no longer needed.

**Step 5: Commit**

```bash
git add backoffice/templates/backoffice/ai_generate_page.html backoffice/static/backoffice/js/sse-client.js
git commit -m "feat(backoffice): replace simulated progress with real SSE steps in generate page"
```

---

## Task 9: Update Chat Refinement template to use SSE

**Files:**
- Modify: `backoffice/templates/backoffice/ai_chat_refine.html:97-107` (typing indicator)
- Modify: `backoffice/templates/backoffice/ai_chat_refine.html:351-445` (sendMessage)

**Step 1: Replace the typing indicator HTML (lines 97-107)**

Replace the bouncing dots with a step-based indicator:

```html
<!-- Typing/Progress Indicator -->
<div id="typingIndicator" class="hidden flex items-start gap-3 max-w-2xl">
    <div class="w-8 h-8 rounded-full bg-purple-100 flex items-center justify-center flex-shrink-0">
        <svg class="w-4 h-4 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/>
        </svg>
    </div>
    <div class="bg-gray-100 rounded-lg px-4 py-3 text-sm text-gray-600">
        <div id="chatStepText" class="flex items-center gap-2">
            <span class="animate-spin inline-block">&#9696;</span>
            <span id="chatStepLabel">Processing...</span>
        </div>
    </div>
</div>
```

**Step 2: Add SSE client script**

```html
<script src="{% static 'backoffice/js/sse-client.js' %}"></script>
```

**Step 3: Update `sendMessage()` function**

Replace the `fetch()` call in `sendMessage()` (lines ~370-429) with SSE:

```javascript
// Inside sendMessage(), replace the fetch block with:
const STEP_LABELS = {
    prepare: 'Preparing page...',
    component_selection: 'Analyzing components...',
    refine_html: 'Refining HTML...',
    templatize_translate: 'Updating translations...',
    complete: 'Finishing up...',
};

const sse = new SSEClient("{% url 'ai:chat_refine_page_stream' %}", {
    csrfToken: '{{ csrf_token }}',
    onProgress: (data) => {
        if (data.status === 'running') {
            document.getElementById('chatStepLabel').textContent = STEP_LABELS[data.step] || data.step;
        }
    },
    onComplete: (data) => {
        document.getElementById('typingIndicator').classList.add('hidden');
        document.getElementById('sendButton').disabled = false;

        if (data.success) {
            currentSessionId = data.session_id;
            renderMessage('assistant', data.assistant_message);
            // Update preview if visible
            if (data.html_content) {
                updatePreview(data.html_content);
            }
        }
    },
    onError: (data) => {
        document.getElementById('typingIndicator').classList.add('hidden');
        document.getElementById('sendButton').disabled = false;
        renderMessage('assistant', 'Error: ' + (data.error || 'Unknown error'));
    },
});

const body = new FormData();
body.append('message', message);
body.append('page_id', pageId);
if (currentSessionId) body.append('session_id', currentSessionId);
body.append('model', selectedModel);
body.append('handle_images', handleImages);
// Add reference images if any

sse.start(body);
```

**Step 4: Commit**

```bash
git add backoffice/templates/backoffice/ai_chat_refine.html
git commit -m "feat(backoffice): replace typing indicator with real step progress in chat refine"
```

---

## Task 10: Update Header/Footer edit templates to use SSE

**Files:**
- Modify: `backoffice/templates/backoffice/header_edit.html` (~line 443, the fetch call)
- Modify: `backoffice/templates/backoffice/footer_edit.html` (similar pattern)

**Step 1: Add SSE script and update the header refinement fetch**

In `header_edit.html`, replace the `fetch('/ai/api/refine-header/', ...)` call with SSE:

```javascript
// Replace the existing fetch call with:
const sse = new SSEClient("{% url 'ai:refine_header_stream' %}", {
    csrfToken: '{{ csrf_token }}',
    onProgress: (data) => {
        if (data.status === 'running') {
            statusEl.textContent = stepLabels[data.step] || 'Processing...';
        }
    },
    onComplete: (data) => {
        hideLoading();
        if (data.success) {
            // Update preview with new header HTML
            displayRefinedSection(data.data);
        }
    },
    onError: (data) => {
        hideLoading();
        alert('Refinement failed: ' + (data.error || 'Unknown error'));
    },
});
sse.start({ instructions, model });
```

**Step 2: Do the same for footer_edit.html**

Same pattern, pointing to `refine_footer_stream`.

**Step 3: Commit**

```bash
git add backoffice/templates/backoffice/header_edit.html backoffice/templates/backoffice/footer_edit.html
git commit -m "feat(backoffice): use SSE progress for header/footer refinement"
```

---

## Task 11: Update Editor V2 AI panel to use SSE

**Files:**
- Modify: `editor_v2/static/editor_v2/js/modules/ai-panel.js:313-337`

**Step 1: Add SSE client import**

The editor uses ES modules. Add the SSE client as an importable module or load it as a script in the editor base template. The simplest approach: copy `sse-client.js` to `editor_v2/static/editor_v2/js/modules/sse-client.js` (or reference from backoffice static).

**Step 2: Replace the `api.post()` calls with SSE**

For each refinement scope (page, element, section), replace the `await api.post(...)` pattern with SSE streaming:

```javascript
// Replace direct api.post with SSE-wrapped call
function refineWithSSE(url, body, { onProgress, onComplete, onError }) {
    const sse = new SSEClient(url, {
        csrfToken: config().csrfToken,
        onProgress,
        onComplete,
        onError,
    });
    sse.start(body);
    return sse;
}
```

Update the existing `sendChat()` or equivalent function to use this wrapper, showing step labels in the AI panel's message area.

**Step 3: Commit**

```bash
git add editor_v2/static/editor_v2/js/modules/ai-panel.js
git commit -m "feat(editor): use SSE progress for inline AI refinement"
```

---

## Task 12: Manual integration test

**Files:** None (testing only)

**Step 1: Start the dev server**

```bash
cd /Users/antoniomarante/Documents/DjangoSites/djangopress
source .venv/bin/activate
python manage.py runserver 8000
```

**Step 2: Test page generation**

1. Go to `/backoffice/ai/generate/page/`
2. Enter a brief: "Simple hero page with headline and CTA"
3. Click Generate
4. Verify: step list shows real progress (component selection → HTML → translate)
5. Verify: each step shows a spinner while running, checkmark + time when done
6. Verify: results display correctly after completion

**Step 3: Test chat refinement**

1. Go to `/backoffice/ai/chat/refine/<page_id>/`
2. Send: "Make the headline bigger and change the button color to red"
3. Verify: typing indicator shows step labels (Preparing → Refining → Translating)
4. Verify: response appears after completion

**Step 4: Test header/footer refinement**

1. Go to `/backoffice/settings/header/`
2. Enter instructions and click refine
3. Verify: progress steps display correctly

**Step 5: Test error handling**

1. Temporarily break an API key in `.env`
2. Try generating a page
3. Verify: error event displays correctly in the UI

**Step 6: Test backward compatibility**

Verify that the original synchronous endpoints still work (used by `generate_site` management command):

```bash
python manage.py generate_site briefings/test.md --dry-run
```

---

## Summary

| Task | What | Files |
|------|------|-------|
| 1 | `on_progress` in `generate_page()` | `ai/services.py` |
| 2 | `on_progress` in `refine_page_with_html()` | `ai/services.py` |
| 3 | `on_progress` in `refine_global_section()` | `ai/services.py` |
| 4 | SSE utility module | `ai/utils/sse.py` (new) |
| 5 | SSE view for page generation | `ai/views.py`, `ai/urls.py` |
| 6 | SSE views for chat/header/footer | `ai/views.py`, `ai/urls.py` |
| 7 | Reusable JS SSE client | `backoffice/static/backoffice/js/sse-client.js` (new) |
| 8 | Generate page template | `ai_generate_page.html` |
| 9 | Chat refine template | `ai_chat_refine.html` |
| 10 | Header/footer templates | `header_edit.html`, `footer_edit.html` |
| 11 | Editor V2 AI panel | `ai-panel.js` |
| 12 | Manual integration test | N/A |
