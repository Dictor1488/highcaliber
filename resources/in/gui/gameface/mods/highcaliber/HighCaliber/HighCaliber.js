import { ModelObserver } from "../../libs/model.js";

const observer = ModelObserver();
const root = document.getElementById('root');
const value = document.getElementById('value');
let currentCfg = {};
let lastScale = null;
let lastClassName = null;
let lastText = null;
let lastColor = null;

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

function updateGeometry() {
    if (!root) return;
    const scale = uiScale();
    if (scale === lastScale) return;
    root.style.left = '0px';
    root.style.top = '0px';
    root.style.transform = 'scale(' + scale + ')';
    lastScale = scale;
}

function updateVisibility(visible, editing) {
    if (!root) return;
    const className = visible ? (editing ? 'editing' : '') : 'hidden';
    if (className === lastClassName) return;
    root.className = className;
    lastClassName = className;
}

function updateValue(text, color) {
    if (!value) return;
    if (color !== lastColor) {
        value.style.color = color;
        lastColor = color;
    }
    if (text !== lastText) {
        value.textContent = text;
        lastText = text;
    }
}

function renderModel(model) {
    currentCfg = parsePayload(model);
    const visible = currentCfg.visible === true;
    const editing = visible && currentCfg.dragEnabled !== false && !!(model && model.editing);

    updateGeometry();
    updateVisibility(visible, editing);

    if (!visible || !value) return;

    const status = String(currentCfg.status || 'progress');
    let text;
    let color;

    if (status === 'wasted') {
        color = currentCfg.colorWasted || '#FE0E00';
        text = currentCfg.showWastedText === false ?
            String(Math.max(0, Math.round(num(currentCfg.remaining, 0)))) :
            String(currentCfg.wastedText || 'Wasted!');
    } else if (status === 'done') {
        color = currentCfg.colorDone || '#60FF00';
        text = currentCfg.showDoneText === false ? '0' : String(currentCfg.doneText || 'Done!');
    } else {
        color = currentCfg.colorProgress || '#F8F400';
        text = String(Math.max(0, Math.round(num(currentCfg.remaining, 0))));
    }

    updateValue(text, color);
}

engine.whenReady.then(function () {
    try {
        if (window.__inqHighCaliberPrimeSurface) {
            window.__inqHighCaliberPrimeSurface();
        }
    } catch (e) {}
    collapseHitArea();
    observer.onUpdate(renderModel);
    observer.subscribe();
    renderModel(observer.model);
});
