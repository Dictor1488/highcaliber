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
    return BASE_WIDTH * uiScale();
}

function surfaceHeight() {
    return BASE_HEIGHT * uiScale();
}

function resizeStableSurface(force) {
    const w = Math.max(1, Math.ceil(surfaceWidth()));
    const h = Math.max(1, Math.ceil(surfaceHeight()));
    const key = w + 'x' + h;
    if (!force && key === lastSurfaceKey) return;
    lastSurfaceKey = key;
    try {
        if (typeof viewEnv !== 'undefined' && viewEnv.resizeViewRem)
            viewEnv.resizeViewRem(w, h);
        else if (typeof viewEnv !== 'undefined' && viewEnv.resizeViewPx)
            viewEnv.resizeViewPx(w, h);
    } catch (e) {}
}

function updateHitArea(visible, editing) {
    try {
        if (typeof viewEnv === 'undefined' || !viewEnv.setHitAreaPaddingsRem) return;
        let pad = 0;
        if (!(visible && editing))
            pad = Math.ceil(Math.max(surfaceWidth(), surfaceHeight()) / 2);
        try {
            viewEnv.setHitAreaPaddingsRem(pad, pad, pad, pad, 15);
        } catch (e) {
            viewEnv.setHitAreaPaddingsRem(pad, pad, pad, pad);
        }
    } catch (e) {}
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

    // Reassert native GameFace surface only when OUR Ctrl edit state changes.
    // No ears/HUD/layout/display events are observed.
    resizeStableSurface(editChanged);

    if (root) {
        root.style.left = '0px';
        root.style.top = '0px';
        root.style.transform = 'scale(' + uiScale() + ')';
        root.className = visible ? (editing ? 'editing' : '') : 'hidden';
    }

    updateHitArea(visible, editing);
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

function callDrag(phase) {
    try {
        const model = observer.model;
        if (model && typeof model.onDragged === 'function')
            model.onDragged({ phase: phase });
    } catch (e) {}
}

function bindDrag() {
    if (!root) return;
    root.addEventListener('mousedown', function (event) {
        if (event.button !== 0) return;
        const model = observer.model;
        const visible = currentCfg.visible === true;
        const editing = visible && currentCfg.dragEnabled !== false && !!(model && model.editing);
        if (!editing) return;
        callDrag('start');
        if (event.preventDefault) event.preventDefault();
    });
    document.addEventListener('mouseup', function () {
        callDrag('end');
    });
}

engine.whenReady.then(function () {
    resizeStableSurface(true);
    bindDrag();
    observer.onUpdate(renderModel);
    observer.subscribe();
    renderModel(observer.model);
});
