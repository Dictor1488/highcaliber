import { ModelObserver } from "../../libs/model.js";

const observer = ModelObserver();
const BASE_WIDTH = 150;
const BASE_HEIGHT = 40;
const root = document.getElementById('root');
const value = document.getElementById('value');
let currentCfg = {};
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

function collapseHitArea() {
    /* The VIEW surface is intentionally passive/fullscreen. Native battle
       input owns drag, so collapse GameFace hit testing over the whole view. */
    try {
        if (typeof viewEnv === 'undefined' || !viewEnv.setHitAreaPaddingsRem) return;
        const pad = Math.ceil(Math.max(window.innerWidth || 0, window.innerHeight || 0)) + 64;
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

function placeRoot() {
    if (!root) return;
    const scale = uiScale();
    const offsetX = num(currentCfg.offsetX, 380);
    const offsetY = num(currentCfg.offsetY, 0);

    /* offsetX is stored relative to the centred scaled indicator. Keeping the
       Wulf VIEW itself at 0,0 removes all native move/resize lifecycle races. */
    root.style.left = 'calc(50% + ' + offsetX + 'px - ' + ((BASE_WIDTH * scale) / 2) + 'px)';
    root.style.top = offsetY + 'px';
    root.style.transform = 'scale(' + scale + ')';
}

function renderModel(model) {
    currentCfg = parsePayload(model);
    const visible = currentCfg.visible === true;
    const editing = visible && currentCfg.dragEnabled !== false && !!(model && model.editing);
    lastEditing = editing;

    placeRoot();
    collapseHitArea();

    if (root) {
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

engine.whenReady.then(function () {
    collapseHitArea();
    observer.onUpdate(renderModel);
    observer.subscribe();
    renderModel(observer.model);
});
