(function () {
    'use strict';

    var BASE_WIDTH = 150;
    var BASE_HEIGHT = 40;
    var root = document.getElementById('root');
    var value = document.getElementById('value');
    var lastPayload = null;
    var lastSurfaceState = null;
    var payloadTimer = null;
    var editFrame = null;
    var lastEditing = null;
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

    function screenWidth() {
        return Math.max(1, num(currentCfg.screenWidth, 1920));
    }

    function screenHeight() {
        return Math.max(1, num(currentCfg.screenHeight, 1080));
    }

    function scaledWidth() {
        return BASE_WIDTH * currentScale;
    }

    function scaledHeight() {
        return BASE_HEIGHT * currentScale;
    }

    function computeBasePosition(cfg) {
        var nativeScale = gameUiScale();
        var uiScale = clamp(num(cfg.scale, 1), 0.5, 2.0);
        currentScale = nativeScale * uiScale;
        var screenW = Math.max(1, num(cfg.screenWidth, 1920));
        var screenH = Math.max(1, num(cfg.screenHeight, 1080));
        var offsetX = num(cfg.offsetX, 380);
        var offsetY = num(cfg.offsetY, 0);
        var maxLeft = Math.max(0, screenW - BASE_WIDTH * currentScale);
        var maxTop = Math.max(0, screenH - BASE_HEIGHT * currentScale);
        baseLeft = clamp(Math.round((screenW - BASE_WIDTH * currentScale) / 2 + offsetX * nativeScale), 0, maxLeft);
        baseTop = clamp(Math.round(offsetY * nativeScale), 0, maxTop);
    }

    function resizeAndMoveSurface(fullscreen, hidden, force) {
        if (!window.viewEnv || !viewEnv.resizeViewPx) return;

        var width;
        var height;
        var x;
        var y;

        if (hidden) {
            width = 1;
            height = 1;
            x = 0;
            y = 0;
        } else if (fullscreen) {
            width = Math.max(1, Math.round(screenWidth()));
            height = Math.max(1, Math.round(screenHeight()));
            x = 0;
            y = 0;
        } else {
            width = Math.max(1, Math.ceil(scaledWidth()));
            height = Math.max(1, Math.ceil(scaledHeight()));
            x = Math.round(baseLeft);
            y = Math.round(baseTop);
        }

        var state = width + 'x' + height + '@' + x + ',' + y;
        if (!force && state === lastSurfaceState) return;
        lastSurfaceState = state;

        try { viewEnv.resizeViewPx(width, height); } catch (e) {}

        try {
            if (window.model && typeof window.model.onResized === 'function') {
                window.model.onResized({
                    width: width,
                    height: height,
                    x: x,
                    y: y,
                    fullscreen: fullscreen === true,
                    gameScale: gameUiScale()
                });
            }
        } catch (e2) {}
    }

    function clampDragOffset(dx, dy) {
        var maxLeft = Math.max(0, screenWidth() - scaledWidth());
        var maxTop = Math.max(0, screenHeight() - scaledHeight());
        var left = clamp(baseLeft + dx, 0, maxLeft);
        var top = clamp(baseTop + dy, 0, maxTop);
        return { dx: left - baseLeft, dy: top - baseTop };
    }

    function applyRootPosition(dx, dy) {
        if (!root) return { dx: 0, dy: 0 };
        root.style.transform = 'scale(' + currentScale + ')';

        if (!dragging) {
            root.style.left = '0px';
            root.style.top = '0px';
            return { dx: 0, dy: 0 };
        }

        var limited = clampDragOffset(dx, dy);
        root.style.left = Math.round(baseLeft + limited.dx) + 'px';
        root.style.top = Math.round(baseTop + limited.dy) + 'px';
        return limited;
    }

    function setInputEnabled(enabled) {
        try { document.documentElement.style.pointerEvents = 'none'; } catch (e) {}
        try { document.body.style.pointerEvents = 'none'; } catch (e2) {}
        if (root) root.style.pointerEvents = enabled ? 'auto' : 'none';
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
        var edit = visible && currentCfg.dragEnabled !== false && modelEditing();
        if (!force && edit === lastEditing) return;
        lastEditing = edit;

        if (!root) return;
        if (!visible) {
            root.className = 'hidden';
            setInputEnabled(false);
            dragging = false;
            resizeAndMoveSurface(false, true, force);
            return;
        }

        root.className = edit ? 'editing' : '';
        setInputEnabled(edit);

        if (!edit && dragging) {
            dragging = false;
            dragDx = 0;
            dragDy = 0;
        }

        // Ctrl alone never creates a fullscreen hit area. The surface remains
        // exactly the size of the panel until mousedown starts a real drag.
        if (!dragging) {
            resizeAndMoveSurface(false, false, force);
            applyRootPosition(0, 0);
        }
    }

    function editingLoop() {
        syncEditing(false);
        if (window.requestAnimationFrame) editFrame = window.requestAnimationFrame(editingLoop);
        else editFrame = window.setTimeout(editingLoop, 16);
    }

    function render(cfg) {
        currentCfg = cfg || {};
        if (!dragging) computeBasePosition(currentCfg);
        syncEditing(true);
        if (currentCfg.visible !== true) return;

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
                window.model.onDragged({ dx: dx, dy: dy, final: final === true, start: start === true, gameScale: gameUiScale() });
            }
        } catch (e) {}
    }

    function pointerX(e) { return typeof e.screenX === 'number' ? e.screenX : e.clientX; }
    function pointerY(e) { return typeof e.screenY === 'number' ? e.screenY : e.clientY; }

    function flushDrag() {
        dragFrame = null;
        if (!dragging) return;
        var limited = applyRootPosition(dragDx, dragDy);
        dragDx = limited.dx;
        dragDy = limited.dy;
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

        // Only now, after the user actually grabbed the 150x40 panel, expand
        // the surface so mousemove/mouseup continue to arrive outside it.
        resizeAndMoveSurface(true, false, true);
        applyRootPosition(0, 0);
        sendDrag(0, 0, false, true);

        e.preventDefault();
        e.stopPropagation();
    }

    function onMouseMove(e) {
        if (!dragging) return;
        var limited = clampDragOffset(pointerX(e) - dragStartX, pointerY(e) - dragStartY);
        dragDx = limited.dx;
        dragDy = limited.dy;
        scheduleDrag();
        e.preventDefault();
        e.stopPropagation();
    }

    function onMouseUp(e) {
        if (!dragging) return;

        var limited = clampDragOffset(pointerX(e) - dragStartX, pointerY(e) - dragStartY);
        dragDx = limited.dx;
        dragDy = limited.dy;

        if (dragFrame !== null) {
            try {
                if (window.cancelAnimationFrame) window.cancelAnimationFrame(dragFrame);
                else window.clearTimeout(dragFrame);
            } catch (ex) {}
            dragFrame = null;
        }

        applyRootPosition(dragDx, dragDy);
        sendDrag(dragDx, dragDy, true, false);

        // Keep visual position continuous while Python persists the new config,
        // then immediately return to the small non-blocking surface.
        baseLeft += dragDx;
        baseTop += dragDy;
        dragging = false;
        dragDx = 0;
        dragDy = 0;
        resizeAndMoveSurface(false, false, true);
        applyRootPosition(0, 0);

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
        syncEditing(true);

        if (window.engine) {
            window.engine.on('viewEnv.onDataChanged', function () {
                tick();
                syncEditing(true);
            });
            window.engine.on('self.onScaleUpdated', function () {
                lastSurfaceState = null;
                tick();
                syncEditing(true);
            });
            window.engine.on('clientResized', function () {
                lastSurfaceState = null;
                tick();
                syncEditing(true);
            });
        }

        if (!payloadTimer) payloadTimer = window.setInterval(tick, 100);
        if (!editFrame) editingLoop();
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
                offsetX: 380,
                offsetY: 0,
                screenWidth: 1920,
                screenHeight: 1080,
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
