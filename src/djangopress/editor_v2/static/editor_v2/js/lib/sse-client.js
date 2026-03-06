/**
 * SSEClient — ES module for Server-Sent Events streaming in the editor.
 *
 * Usage:
 *   import { SSEClient } from '../lib/sse-client.js';
 *
 *   const sse = new SSEClient('/editor-v2/api/refine-page/stream/', {
 *       csrfToken: config().csrfToken,
 *       onProgress: (data) => { // data has step, status, etc.
 *       },
 *       onComplete: (data) => { // final result
 *       },
 *       onError: (data) => { // data.error has the message
 *       },
 *   });
 *   sse.start({ page_id: 1, instructions: '...' });
 *   sse.abort();  // cancel if needed
 */

export class SSEClient {
    /**
     * @param {string} url - The streaming endpoint URL.
     * @param {Object} options
     * @param {string} options.csrfToken - CSRF token for POST requests.
     * @param {function} [options.onProgress] - Called for each progress event.
     * @param {function} [options.onComplete] - Called when the stream signals completion.
     * @param {function} [options.onError] - Called on errors.
     */
    constructor(url, options = {}) {
        this.url = url;
        this.csrfToken = options.csrfToken || '';
        this.onProgress = options.onProgress || function () {};
        this.onComplete = options.onComplete || function () {};
        this.onError = options.onError || function () {};
        this._abortController = null;
    }

    /**
     * Start the streaming request.
     * @param {Object} body - Request payload (will be JSON-stringified).
     */
    async start(body) {
        this._abortController = new AbortController();

        const headers = {
            'X-CSRFToken': this.csrfToken,
            'Content-Type': 'application/json',
        };

        let response;
        try {
            response = await fetch(this.url, {
                method: 'POST',
                headers: headers,
                body: JSON.stringify(body),
                signal: this._abortController.signal,
            });
        } catch (err) {
            if (err.name === 'AbortError') return;
            this.onError({ error: err.message || 'Network error' });
            return;
        }

        if (!response.ok) {
            let errorMsg = 'HTTP ' + response.status;
            try {
                const text = await response.text();
                const json = JSON.parse(text);
                errorMsg = json.error || errorMsg;
            } catch (_) {}
            this.onError({ error: errorMsg });
            return;
        }

        // Read the SSE stream
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        try {
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const result = this._parseEvents(buffer);
                buffer = result.remaining;

                for (const event of result.parsed) {
                    this._dispatch(event);
                }
            }

            // Flush any remaining complete events
            if (buffer.trim()) {
                const result = this._parseEvents(buffer + '\n\n');
                for (const event of result.parsed) {
                    this._dispatch(event);
                }
            }
        } catch (err) {
            if (err.name === 'AbortError') return;
            this.onError({ error: err.message || 'Stream read error' });
        }
    }

    /**
     * Abort the in-flight request.
     */
    abort() {
        if (this._abortController) {
            this._abortController.abort();
            this._abortController = null;
        }
    }

    /**
     * Parse SSE events from a text buffer.
     * @param {string} buffer
     * @returns {{ parsed: Array<{event: string, data: *}>, remaining: string }}
     */
    _parseEvents(buffer) {
        const parsed = [];
        const blocks = buffer.split('\n\n');
        const remaining = blocks.pop();

        for (const block of blocks) {
            const trimmed = block.trim();
            if (!trimmed) continue;

            let eventType = 'message';
            let dataLines = [];

            const lines = trimmed.split('\n');
            for (const line of lines) {
                if (line.startsWith('event:')) {
                    eventType = line.slice(6).trim();
                } else if (line.startsWith('data:')) {
                    dataLines.push(line.slice(5).trim());
                }
            }

            if (dataLines.length === 0) continue;

            const raw = dataLines.join('\n');
            let data;
            try {
                data = JSON.parse(raw);
            } catch (_) {
                data = raw;
            }

            parsed.push({ event: eventType, data: data });
        }

        return { parsed: parsed, remaining: remaining || '' };
    }

    /**
     * Route a parsed event to the appropriate callback.
     * @param {{ event: string, data: * }} event
     */
    _dispatch(event) {
        switch (event.event) {
            case 'progress':
                this.onProgress(event.data);
                break;
            case 'complete':
                this.onComplete(event.data);
                break;
            case 'error':
                this.onError(event.data);
                break;
            default:
                this.onProgress(event.data);
                break;
        }
    }
}
