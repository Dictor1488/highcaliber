(function () {
    'use strict';

    var BASE_WIDTH = 220;
    var BASE_HEIGHT = 56;
    var root = document.getElementById('root');
    var value = document.getElementById('value');
    var lastPayload = null;
    var lastSize = null;
    var timer = null;
    var dragging = false;
    var lastX = 0;
    var lastY = 0;

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

    function resize(scale) {
        var nativeScale = gameUiScale();
        var uiScale = clamp(num(scale, 1), 0.5, 2.0);
        var renderScale = nativeScale * uiScale;
        var width = Math.ceil(BASE_WIDTH * renderScale);
        var height = Math.ceil(BASE_HEIGHT * renderScale);
        var size = width + 'x' + height + '@' + nativeScale.toFixed(4);

        root.style.transform = 'scale(' + renderScale + ')';

        if (size !== lastSize && window.viewEnv && viewEnv.resizeViewPx) {
            lastSize = size;
            viewEnv.resizeViewPx(width, height);
            try {
                if (window.model && typeof window.model.onResized === 'function') {
                    window.model.onResized({
                        width: width,
                        height: height,
                        gameScale: nativeScale
                    });
                }
            } catch (e) {}
        }
    }

    function setInputEnabled(enabled) {
        var mode = enabled ? 'auto' : 'none';
        try { document.documentElement.style.pointerEvents = mode; } catch (e) {}
        try { document.body.style.pointerEvents = mode; } catch (e) {}
        if (root) root.style.pointerEvents = mode;
    }

    function render(cfg) {
        if (cfg.visible !== true) {
            if (root) root.className = 'hidden';
            setInputEnabled(false);
            dragging = false;
            return;
        }

        var edit = cfg.editing === true && cfg.dragEnabled !== false;
        root.className = edit ? 'editing' : '';
        setInputEnabled(edit);
        if (!edit) dragging = false;
        resize(cfg.scale);

        var status = String(cfg.status || 'progress');
        if (status === 'wasted') {
            value.style.color = cfg.colorWasted || '#FE0E00';
            value.textContent = cfg.showWastedText === false ? String(Math.max(0, Math.round(num(cfg.remaining, 0)))) : String(cfg.wastedText || 'Wasted!');
        } else if (status === 'done') {
            value.style.color = cfg.colorDone || '#60FF00';
            value.textContent = cfg.showDoneText === false ? '0' : String(cfg.doneText || 'Done!');
        } else {
            value.style.color = cfg.colorProgress || '#F8F400';
            value.textContent = String(Math.max(0, Math.round(num(cfg.remaining, 0))));
        }
    }

    function sendDrag(dx, dy, final) {
        try {
            if (window.model && typeof window.model.onDragged === 'function') {
                window.model.onDragged({
                    dx: dx,
                    dy: dy,
                    final: final === true,
                    gameScale: gameUiScale()
                });
            }
        } catch (e) {}
    }

    function pointerX(e) { return typeof e.screenX === 'number' ? e.screenX : e.clientX; }
    function pointerY(e) { return typeof e.screenY === 'number' ? e.screenY : e.clientY; }

    function onMouseDown(e) {
        if (!root || root.className.indexOf('editing') < 0) return;
        if (e.button !== 0) return;
        dragging = true;
        lastX = pointerX(e);
        lastY = pointerY(e);
        e.preventDefault();
        e.stopPropagation();
    }

    function onMouseMove(e) {
        if (!dragging) return;
        var px = pointerX(e);
        var py = pointerY(e);
        var dx = px - lastX;
        var dy = py - lastY;
        lastX = px;
        lastY = py;
        if (dx || dy) sendDrag(dx, dy, false);
        e.preventDefault();
        e.stopPropagation();
    }

    function onMouseUp(e) {
        if (!dragging) return;
        dragging = false;
        sendDrag(0, 0, true);
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
            window.engine.on('self.onScaleUpdated', function () { lastSize = null; tick(); });
            window.engine.on('clientResized', function () { lastSize = null; tick(); });
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
