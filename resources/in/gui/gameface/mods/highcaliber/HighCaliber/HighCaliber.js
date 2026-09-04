(function () {
    'use strict';

    var BASE_WIDTH = 150;
    var BASE_HEIGHT = 40;
    var root = document.getElementById('root');
    var value = document.getElementById('value');
    var lastPayload = null;
    var lastEditing = null;
    var lastSurfaceKey = null;
    var currentCfg = {};

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

    // Same principle as MARKS: keep one small, stable native GameFace surface
    // and control its real click rectangle with setHitAreaPaddingsRem. Never
    // resize the view to fullscreen just to drag it.
    function resizeStableSurface(force) {
        var w = Math.max(1, Math.ceil(surfaceWidth()));
        var h = Math.max(1, Math.ceil(surfaceHeight()));
        var key = w + 'x' + h;
        if (!force && key === lastSurfaceKey) return;
        lastSurfaceKey = key;
        try {
            if (window.viewEnv && viewEnv.resizeViewRem) {
                viewEnv.resizeViewRem(w, h);
            } else if (window.viewEnv && viewEnv.resizeViewPx) {
                viewEnv.resizeViewPx(w, h);
            }
        } catch (e) {}
    }

    function updateHitArea(visible, editing) {
        try {
            if (!window.viewEnv || !viewEnv.setHitAreaPaddingsRem) return;
            var top, right, bottom, left;
            if (visible && editing) {
                top = right = bottom = left = 0;
            } else {
                // MARKS uses oversized equal paddings to collapse the native
                // GameFace hit rectangle completely while the HUD is passive.
                top = right = bottom = left = Math.ceil(Math.max(surfaceWidth(), surfaceHeight()) / 2);
            }
            try {
                viewEnv.setHitAreaPaddingsRem(top, right, bottom, left, 15);
            } catch (e1) {
                viewEnv.setHitAreaPaddingsRem(top, right, bottom, left);
            }
        } catch (e2) {}
    }

    function modelEditing() {
        try {
            return window.model && window.model.editing === true;
        } catch (e) {
            return false;
        }
    }

    function syncEditing(force) {
        var visible = currentCfg.visible === true;
        var editing = visible && currentCfg.dragEnabled !== false && modelEditing();
        if (!force && editing === lastEditing) return;
        lastEditing = editing;

        if (!root) return;
        root.className = visible ? (editing ? 'editing' : '') : 'hidden';
        root.style.pointerEvents = editing ? 'auto' : 'none';
        try { document.documentElement.style.pointerEvents = editing ? 'auto' : 'none'; } catch (e) {}
        try { document.body.style.pointerEvents = editing ? 'auto' : 'none'; } catch (e2) {}
        updateHitArea(visible, editing);
    }

    function render(cfg) {
        currentCfg = cfg || {};
        resizeStableSurface(false);

        if (root) {
            root.style.left = '0px';
            root.style.top = '0px';
            root.style.transform = 'scale(' + uiScale() + ')';
        }

        syncEditing(true);
        if (currentCfg.visible !== true) return;

        var status = String(currentCfg.status || 'progress');
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
            if (window.model && typeof window.model.onDragged === 'function') {
                window.model.onDragged({ phase: phase });
            }
        } catch (e) {}
    }

    function onMouseDown(e) {
        if (!root || root.className.indexOf('editing') < 0 || e.button !== 0) return;
        callDrag('start');
        if (e.preventDefault) e.preventDefault();
        if (e.stopPropagation) e.stopPropagation();
    }

    function onMouseUp() {
        callDrag('end');
    }

    function tickPayload() {
        var raw = window.model && window.model.payload ? String(window.model.payload) : '';
        if (raw === lastPayload) return;
        lastPayload = raw;
        var cfg = {};
        try { cfg = JSON.parse(raw || '{}'); } catch (e) { cfg = {}; }
        render(cfg);
    }

    function initialize() {
        resizeStableSurface(true);
        if (root) root.addEventListener('mousedown', onMouseDown, true);
        document.addEventListener('mouseup', onMouseUp, true);
        tickPayload();
        syncEditing(true);

        if (window.engine) {
            window.engine.on('viewEnv.onDataChanged', function () {
                tickPayload();
                syncEditing(true);
            });
            window.engine.on('self.onScaleUpdated', function () {
                lastSurfaceKey = null;
                resizeStableSurface(true);
                syncEditing(true);
            });
            window.engine.on('clientResized', function () {
                lastSurfaceKey = null;
                resizeStableSurface(true);
                syncEditing(true);
            });
        }
    }

    if (window.engine && window.engine.whenReady) {
        var domReady = window.isDomBuilt ? Promise.resolve() : new Promise(function (resolve) {
            window.engine.on('self.onDomBuilt', resolve);
        });
        Promise.all([window.engine.whenReady, domReady]).then(function () {
            requestAnimationFrame(function () { requestAnimationFrame(initialize); });
        });
    } else {
        window.model = {
            editing: true,
            payload: JSON.stringify({
                visible: true,
                status: 'progress',
                remaining: 2137,
                scale: 1,
                dragEnabled: true,
                colorProgress: '#F8F400',
                colorDone: '#60FF00',
                colorWasted: '#FE0E00',
                doneText: 'Done!',
                wastedText: 'Wasted!'
            })
        };
        initialize();
    }
}());
