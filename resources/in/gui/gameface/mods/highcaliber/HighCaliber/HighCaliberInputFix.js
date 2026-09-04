(function () {
    'use strict';

    var root = null;
    var last = null;

    function enabledNow() {
        try {
            if (!window.model || window.model.editing !== true) return false;
        } catch (e) {
            return false;
        }
        root = root || document.getElementById('root');
        if (!root || root.className.indexOf('hidden') >= 0) return false;
        return true;
    }

    function apply() {
        var enabled = enabledNow();
        if (enabled !== last) {
            last = enabled;
            try { document.documentElement.style.pointerEvents = enabled ? 'auto' : 'none'; } catch (e) {}
            try { document.body.style.pointerEvents = enabled ? 'auto' : 'none'; } catch (e2) {}
            if (root) root.style.pointerEvents = enabled ? 'auto' : 'none';
        }
        if (window.requestAnimationFrame) window.requestAnimationFrame(apply);
        else window.setTimeout(apply, 16);
    }

    function start() {
        root = document.getElementById('root');
        apply();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start);
    } else {
        start();
    }
}());
