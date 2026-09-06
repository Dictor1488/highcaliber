import { ModelObserver } from "../../libs/model.js";

const observer = ModelObserver();
const root = document.getElementById('root');
const value = document.getElementById('value');
let currentCfg = {};

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
    try {
        if (typeof viewEnv === 'undefined' || !viewEnv.setHitAreaPaddingsRem) return;
        try {
            viewEnv.setHitAreaPaddingsRem(0, 0, 0, 0, 15);
        } catch (e) {
            viewEnv.setHitAreaPaddingsRem(0, 0, 0, 0);
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
    root.style.left = '0px';
    root.style.top = '0px';
    root.style.transform = 'scale(' + uiScale() + ')';
}

function renderModel(model) {
    currentCfg = parsePayload(model);
    const visible = currentCfg.visible === true;
    const editing = visible && currentCfg.dragEnabled !== false && !!(model && model.editing);

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
