class EventBus {
    constructor() {
        this._listeners = new Map();
    }

    on(event, fn) {
        if (!this._listeners.has(event)) {
            this._listeners.set(event, new Set());
        }
        this._listeners.get(event).add(fn);
        return () => this.off(event, fn);
    }

    off(event, fn) {
        const fns = this._listeners.get(event);
        if (fns) fns.delete(fn);
    }

    emit(event, data) {
        const fns = this._listeners.get(event);
        if (fns) {
            fns.forEach(fn => fn(data));
        }
    }
}

export const events = new EventBus();
