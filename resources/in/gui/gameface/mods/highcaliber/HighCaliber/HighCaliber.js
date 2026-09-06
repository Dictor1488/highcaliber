import { ModelObserver } from "../../libs/model.js";

const observer = ModelObserver();
const BASE_WIDTH = 150;
const BASE_HEIGHT = 40;
const root = document.getElementById('root');
const value = document.getElementById('value');
let currentCfg = {};
let lastSurfaceKey = null;
let lastEditing = null;

function num(v, d) {
    v = Number(v);
    return isNaN(v) ? d : v;
}

function clamp(v, min, max) {
    return Math.max(min, Math.min(max, v));
}

function uiScale() {
    return clamp(num(currentCfg.scale, 1), 0.5, 2.0);
}

function surfaceWidth() {
    return Math.max(1, Math.ceil(BASE_WIDTH * uiScale()));
}

function surfaceHeight() {
    return Math.max(1, Math.ceil(BASE_HEIGHT * uiScale()));
}

function collapseHitArea() {
    try {
        if (typeof viewEnv === 'undefined' || !viewEnv.setHitAreaPaddingsRem) return;
        const pad = Math.ceil(Math.max(surfaceWidth(), surfaceHeight()) / 2) + 8;
        try {
            viewEnv.setHitAreaPaddingsRem(pad, pad, pad, pad, 15);
        } catch (e) {
            viewEnv.setHitAreaPaddingsRem(pad, pad, pad, pad);
        }
    } catch (e) {}
}

function resizeStableSurface(force) {
    const w = surfaceWidth();
    const h = surfaceHeight();
    const key = w + 'x' + h;
    if (!force && key === lastSurfaceKey) {
        collapseHitArea();
        return true;
    }

    let applied = false;
    try {
        if (w === BASE_WIDTH && h === BASE_HEIGHT &&
            typeof window.__inqPrimeHighCaliberSurface === 'function') {
            applied = !!window.__inqPrimeHighCaliberSurface();
        } else if (typeof viewEnv !== 'undefined' && viewEnv.resizeViewRem) {
            viewEnv.resizeViewRem(w, h);
            applied = true;
        } else if (typeof viewEnv !== 'undefined' && viewEnv.resizeViewPx) {
            viewEnv.resizeViewPx(w, h);
            applied = true;
        }
    } catch (e) {}

    if (applied) lastSurfaceKey = key;
    collapseHitArea();
    return applied;
}

function parsePayload(model) {
    let cfg = {};
    try { cfg = JSON.parse(String(model && model.payload ? model.payload : '{}')); }
    catch (e) { cfg = {}; }
    return cfg;
}

function renderModel(model) {
    currentCfg = parsePayload(model);
    const visible = currentCfg.visible === true;
    const editing = visible && currentCfg.dragEnabled !== false && !!(model && model.editing);
    const editChanged = lastEditing === null || editing !== lastEditing;
    lastEditing = editing;

    resizeStableSurface(editChanged);

    if (root) {
        root.style.left = '0px';
        root.style.top = '0px';
        root.style.transform = 'scale(' + uiScale() + ')';
        root.className = visible ? (editing ? 'editing' : '') : 'hidden';
    }

    if (!visible || !value) return;

    const status = String(currentCfg.status || 'progress');
    if (status === 'wasted') {
        value.style.color = currentCfg.colorWasted || '#FE0E00';
        value.textContent = currentCfg.showWastedText === false ?
            String(Math.max(0, Math.round(num(currentCfg.remaining, 0)))) :
            String(currentCfg.wastedText || 'Wasted!');
    } else if (status === 'done') {
        value.style.color = currentCfg.colorDone || '#60FF00';
        value.textContent = currentCfg.showDoneText === false ? '0' : String(currentCfg.doneText || 'Done!');
    } else {
        value.style.color = currentCfg.colorProgress || '#F8F400';
        value.textContent = String(Math.max(0, Math.round(num(currentCfg.remaining, 0))));
    }
}

/* The HTML has already registered the earliest possible engine.whenReady size
   callback. This call is only a module-time reinforcement, not the primary
   startup handshake. */
resizeStableSurface(true);

engine.whenReady.then(function () {
    resizeStableSurface(true);
    observer.onUpdate(renderModel);
    observer.subscribe();
    renderModel(observer.model);
});
