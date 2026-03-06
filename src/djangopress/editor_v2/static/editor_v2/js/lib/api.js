function getConfig() {
    const config = window.EDITOR_CONFIG || {};
    return {
        csrfToken: config.csrfToken || '',
        apiBase: config.apiBase || '/editor/api'
    };
}

async function request(url, options) {
    const response = await fetch(url, options);
    if (!response.ok) {
        let message = `HTTP ${response.status}`;
        try {
            const body = await response.json();
            message = body.error || body.message || message;
        } catch (_) {}
        throw new Error(message);
    }
    return response.json();
}

export const api = {
    post(endpoint, data = {}) {
        const { csrfToken, apiBase } = getConfig();
        return request(`${apiBase}${endpoint}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify(data)
        });
    },

    get(endpoint, params = {}) {
        const { apiBase } = getConfig();
        const qs = new URLSearchParams(params).toString();
        const url = qs ? `${apiBase}${endpoint}?${qs}` : `${apiBase}${endpoint}`;
        return request(url, {
            method: 'GET',
            headers: { 'Accept': 'application/json' }
        });
    }
};
