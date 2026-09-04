(function () {
    'use strict';

    var BASE_WIDTH = 150;
    var BASE_HEIGHT = 40;
    var root = document.getElementById('root');
    var value = document.getElementById('value');
    var lastPayload = null;
    var lastSurfaceSize = null;
    var timer = null;
    var dragging = false;
    var dragStartX = 0;
    var dragStartY = 0;
    var dragDx = 0;
    var dragDy = 0;
    var dragFrame = null;
    var currentCfg = {};
    var currentScale = 1;
    var baseLeft = 0;
    var baseTop = 0;

    function num(v, d) {
        v = Number(v);
        return isNaN(v) ? d : v;
    }

    function clamp(v, min, max) {
        return Math.max(min, Math.min(max, v));
    }

    function gameUiScale() {
        try {
            if (window.viewEnv && typeof viewEnv.getScale === 'function') {
                return clamp(num(viewEnv.getScale(), 1), 0.5, 2.5);
            }
        } catch (e) {}
        return 1;
    }

    function resizeSurface(cfg) {
        var width = Math.max(1, Math.round(num(cfg.screenWidth, 1920)));
        var height = Math.max(1, Math.round(num(cfg.screenHeight, 1080)));
        var size = width + 'x' + height;
        if (size !== lastSurfaceSize && window.viewEnv && viewEnv.resizeViewPx) {
            lastSurfaceSize = size;
            viewEnv.resizeViewPx(width, height);
            try {
                if (window.model && typeof window.model.onResized === 'function') {
                    window.model.onResized({ width: width, height: height, gameScale: gameUiScale() });
                }
            } catch (e) {}
        }
    }

    function computeBasePosition(cfg) {
        var nativeScale = gameUiScale();
        var uiScale = clamp(num(cfg.scale, 1), 0.5, 2.0);
        currentScale = nativeScale * uiScale;
        var screenW = Math.max(1, num(cfg.screenWidth, 1920));
        var offsetX = num(cfg.offsetX, 380);
        var offsetY = num(cfg.offsetY, 0);
        baseLeft = Math.round((screenW - BASE_WIDTH * currentScale) / 2 + offsetX * nativeScale);
        baseTop = Math.max(0, Math.round(offsetY * nativeScale));
    }

    function applyRootPosition(dx, dy) {
        if (!root) return;
        root.style.left = Math.round(baseLeft + dx) + 'px';
        root.style.top = Math.round(baseTop + dy) + 'px';
        root.style.transform = 'scale(' + currentScale + ')';
    }

    function setInputEnabled(enabled) {
        try { document.documentElement.style.pointerEvents = 'none'; } catch (e) {}
        try { document.body.style.pointerEvents = 'none'; } catch (e) {}
        if (root) root.style.pointerEvents = enabled ? 'auto' : 'none';
    }

    function render(cfg) {
        currentCfg = cfg || {};
        resizeSurface(currentCfg);
        computeBasePosition(currentCfg);

        if (currentCfg.visible !== true) {
            if (root) root.className = 'hidden';
            setInputEnabled(false);
            dragging = false;
            return;
        }

        var edit = currentCfg.editing === true && currentCfg.dragEnabled !== false;
        root.className = edit ? 'editing' : '';
        setInputEnabled(edit);
        if (!dragging) applyRootPosition(0, 0);

        var status = String(currentCfg.status || 'progress');
        if (status === 'wasted') {
            value.style.color = currentCfg.colorWasted || '#FE0E00';
            value.textContent = currentCfg.showWastedText === false ? String(Math.max(0, Math.round(num(currentCfg.remaining, 0)))) : String(currentCfg.wastedText || 'Wasted!');
        } else if (status === 'done') {
            value.style.color = currentCfg.colorDone || '#60FF00';
            value.textContent = currentCfg.showDoneText === false ? '0' : String(currentCfg.doneText || 'Done!');
        } else {
            value.style.color = currentCfg.colorProgress || '#F8F400';
            value.textContent = String(Math.max(0, Math.round(num(currentCfg.remaining, 0))));
        }
    }

    function sendDrag(dx, dy, final, start) {
        try {
            if (window.model && typeof window.model.onDragged === 'function') {
                window.model.onDragged({
                    dx: dx,
                    dy: dy,
                    final: final === true,
                    start: start === true,
                    gameScale: gameUiScale()
                });
            }
        } catch (e) {}
    }

    function pointerX(e) { return typeof e.screenX === 'number' ? e.screenX : e.clientX; }
    function pointerY(e) { return typeof e.screenY === 'number' ? e.screenY : e.clientY; }

    function flushDrag() {
        dragFrame = null;
        if (!dragging) return;
        applyRootPosition(dragDx, dragDy);
    }

    function scheduleDrag() {
        if (dragFrame !== null) return;
        if (window.requestAnimationFrame) dragFrame = window.requestAnimationFrame(flushDrag);
        else dragFrame = window.setTimeout(flushDrag, 16);
    }

    function onMouseDown(e) {
        if (!root || root.className.indexOf('editing') < 0) return;
        if (e.button !== 0) return;
        dragging = true;
        dragStartX = pointerX(e);
        dragStartY = pointerY(e);
        dragDx = 0;
        dragDy = 0;
        sendDrag(0, 0, false, true);
        e.preventDefault();
        e.stopPropagation();
    }

    function onMouseMove(e) {
        if (!dragging) return;
        dragDx = pointerX(e) - dragStartX;
        dragDy = pointerY(e) - dragStartY;
        scheduleDrag();
        e.preventDefault();
        e.stopPropagation();
    }

    function onMouseUp(e) {
        if (!dragging) return;
        dragDx = pointerX(e) - dragStartX;
        dragDy = pointerY(e) - dragStartY;
        dragging = false;
        if (dragFrame !== null) {
            try {
                if (window.cancelAnimationFrame) window.cancelAnimationFrame(dragFrame);
                else window.clearTimeout(dragFrame);
            } catch (ex) {}
            dragFrame = null;
        }
        applyRootPosition(dragDx, dragDy);
        sendDrag(dragDx, dragDy, true, false);
        e.preventDefault();
        e.stopPropagation();
    }

    function tick() {
        var raw = window.model && window.model.payload ? String(window.model.payload) : '';
        if (raw === lastPayload) return;
        lastPayload = raw;
        var cfg = {};
        try { cfg = JSON.parse(raw || '{}'); } catch (e) { cfg = {}; }
        render(cfg);
    }

    function initialize() {
        if (root) root.addEventListener('mousedown', onMouseDown, true);
        window.addEventListener('mousemove', onMouseMove, true);
        window.addEventListener('mouseup', onMouseUp, true);
        tick();
        window.setTimeout(tick, 100);
        window.setTimeout(tick, 500);
        if (window.engine) {
            window.engine.on('viewEnv.onDataChanged', tick);
            window.engine.on('self.onScaleUpdated', function () { lastSurfaceSize = null; tick(); });
            window.engine.on('clientResized', function () { lastSurfaceSize = null; tick(); });
        }
        if (!timer) timer = window.setInterval(tick, 250);
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
            payload: JSON.stringify({
                visible: true,
                status: 'progress',
                remaining: 2137,
                scale: 1,
                offsetX: 380,
                offsetY: 0,
                screenWidth: 1920,
                screenHeight: 1080,
                dragEnabled: true,
                editing: true,
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
