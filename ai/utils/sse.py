"""
SSE (Server-Sent Events) streaming utilities.

Bridges the gap between service methods that accept on_progress callbacks
and Django's StreamingHttpResponse for real-time progress updates.
"""

import json
import queue
import threading

from django.http import StreamingHttpResponse


def sse_event(data, event=None):
    """
    Format a single SSE event string.

    Args:
        data: Dictionary to serialize as JSON in the data field.
        event: Optional event name (e.g. 'progress', 'complete', 'error').

    Returns:
        SSE-formatted string with two trailing newlines per spec.
    """
    lines = []
    if event:
        lines.append(f"event: {event}")
    lines.append(f"data: {json.dumps(data)}")
    lines.append("")
    lines.append("")
    return "\n".join(lines)


def run_with_progress(service_method, kwargs, timeout=300):
    """
    Generator that runs a service method in a background thread and yields
    SSE events as progress callbacks arrive.

    The service method must accept an `on_progress` keyword argument.

    Args:
        service_method: Callable that accepts **kwargs and on_progress.
        kwargs: Dictionary of keyword arguments to pass to service_method.
        timeout: Maximum seconds to wait for completion (default 300).

    Yields:
        SSE-formatted strings: progress events, then a final complete or error event.
    """
    q = queue.Queue()
    sentinel = object()

    def on_progress(event_data):
        q.put(("progress", event_data))

    def run():
        try:
            result = service_method(**kwargs, on_progress=on_progress)
            q.put(("complete", result))
        except Exception as e:
            q.put(("error", str(e)))
        finally:
            q.put(sentinel)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()

    while True:
        try:
            item = q.get(timeout=timeout)
        except queue.Empty:
            yield sse_event({"error": "Generation timed out"}, event="error")
            return

        if item is sentinel:
            return

        event_type, payload = item

        if event_type == "progress":
            yield sse_event(payload, event="progress")
        elif event_type == "complete":
            yield sse_event({"success": True, "page_data": payload}, event="complete")
        elif event_type == "error":
            yield sse_event({"error": payload}, event="error")


def sse_response(generator):
    """
    Wrap an SSE generator in a Django StreamingHttpResponse with
    appropriate headers for event streaming.

    Args:
        generator: An iterable that yields SSE-formatted strings.

    Returns:
        StreamingHttpResponse configured for SSE.
    """
    response = StreamingHttpResponse(generator, content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
