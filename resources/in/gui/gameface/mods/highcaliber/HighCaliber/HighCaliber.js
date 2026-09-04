(function () {
    'use strict';

    var BASE_WIDTH = 220;
    var BASE_HEIGHT = 56;
    var root = document.getElementById('root');
    var value = document.getElementById('value');
    var lastPayload = null;
    var lastSize = null;
    var timer = null;

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

    function render(cfg) {
        if (cfg.visible !== true) {
            root.className = 'hidden';
            return;
        }

        root.className = '';
        resize(cfg.scale);

        var status = String(cfg.status || 'progress');
        if (status === 'wasted') {
            value.style.color = cfg.colorWasted || '#FE0E00';
            value.textContent = cfg.showWastedText === false ? String(Math.max(0, Math.round(num(cfg.remaining, 0)))) : 'Wasted!';
        } else if (status === 'done') {
            value.style.color = cfg.colorDone || '#60FF00';
            value.textContent = cfg.showDoneText === false ? '0' : 'Done!';
        } else {
            value.style.color = cfg.colorProgress || '#F8F400';
            value.textContent = String(Math.max(0, Math.round(num(cfg.remaining, 0))));
        }
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
        tick();
        window.setTimeout(tick, 100);
        window.setTimeout(tick, 500);
        if (window.engine) {
            window.engine.on('viewEnv.onDataChanged', tick);
            window.engine.on('self.onScaleUpdated', function () { lastSize = null; tick(); });
            window.engine.on('clientResized', function () { lastSize = null; tick(); });
        }
        if (!timer) timer = window.setInterval(tick, 1000);
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
                colorProgress: '#F8F400',
                colorDone: '#60FF00',
                colorWasted: '#FE0E00'
            })
        };
        initialize();
    }
}());
