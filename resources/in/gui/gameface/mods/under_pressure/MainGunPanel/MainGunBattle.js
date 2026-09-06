(function () {
    'use strict';

    var root = document.getElementById('main-gun-root');
    var valueEl = document.getElementById('main-gun-remaining');
    var payload = {};
    var lastPayload = null;
    var lastSize = null;
    var initialized = false;

    function debug(message) {
        try {
            if (window.model && typeof window.model.onDebug === 'function') {
                window.model.onDebug({message: String(message)});
            }
        } catch (e) {}
    }

    function sendCmd(name, value) {
        try {
            if (window.model && typeof window.model.onCmd === 'function') {
                window.model.onCmd({name: String(name), value: String(value)});
                return true;
            }
        } catch (e) {
            debug('command failed: ' + e);
        }
        return false;
    }

    function readPayload() {
        var raw = window.model && window.model.payload ? String(window.model.payload) : '';
        if (raw === lastPayload) return false;
        lastPayload = raw;
        try { payload = JSON.parse(raw || '{}'); }
        catch (e) { payload = {}; }
        return true;
    }

    function resizeSurface() {
        var scale = Number(payload.scale) || 1;
        if (scale < 0.5) scale = 0.5;
        if (scale > 4.0) scale = 4.0;
        var w = Math.max(1, Math.round(150 * scale));
        var h = Math.max(1, Math.round(40 * scale));
        var key = w + 'x' + h + 'x' + w + 'x' + h;
        if (key === lastSize) return true;
        try {
            if (window.viewEnv && typeof viewEnv.resizeViewPx === 'function') {
                viewEnv.resizeViewPx(w, h);
                root.style.transform = 'scale(' + scale + ')';
                lastSize = key;
                sendCmd('onSize', key);
                return true;
            }
        } catch (e) {
            debug('resizeViewPx failed: ' + e);
        }
        return false;
    }

    function render() {
        readPayload();
        resizeSurface();

        var state = payload.state || {};
        var visible = payload.visible === true;
        var editing = payload.editing === true;
        var obtained = !!state.mainGunObtained;
        var failed = (!!state.failed || !!state.playerDead) && !obtained;
        var remaining = Math.max(0, parseInt(state.remaining, 10) || 0);

        if (root) {
            root.classList.toggle('main-gun-hidden', !visible);
            root.classList.toggle('main-gun-editing', editing && visible);
        }
        if (!valueEl) return;

        if (obtained) {
            valueEl.textContent = 'Done!';
            valueEl.style.color = '#60FF00';
        } else if (failed) {
            valueEl.textContent = 'Wasted!';
            valueEl.style.color = '#FE0E00';
        } else {
            valueEl.textContent = String(remaining);
            valueEl.style.color = '#F8F400';
        }
    }

    function poll() {
        var raw = window.model && window.model.payload ? String(window.model.payload) : '';
        if (raw !== lastPayload) render();
    }

    function initialize() {
        if (initialized) return;
        initialized = true;
        render();
        if (window.engine) {
            window.engine.on('viewEnv.onDataChanged', render);
            window.engine.on('self.onScaleUpdated', function () { lastSize = null; render(); });
            window.engine.on('clientResized', function () { lastSize = null; render(); });
        }
        if (window.viewEnv && typeof viewEnv.addDataChangedCallback === 'function') {
            try { viewEnv.addDataChangedCallback('model', 0, true); } catch (e) {}
        }
        window.setInterval(poll, 200);
        if (window.model && typeof window.model.onReady === 'function') {
            window.model.onReady({});
        }
    }

    function afterFrames() {
        requestAnimationFrame(function () {
            requestAnimationFrame(initialize);
        });
    }

    if (window.engine && window.engine.whenReady) {
        var domReady = window.isDomBuilt ? Promise.resolve() : new Promise(function (resolve) {
            window.engine.on('self.onDomBuilt', resolve);
        });
        Promise.all([window.engine.whenReady, domReady]).then(afterFrames);
    } else {
        afterFrames();
    }
}());
