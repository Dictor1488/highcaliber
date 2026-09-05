# -*- coding: utf-8 -*-
"""Visibility guard for the layer-7 High Caliber battle window.

High Caliber intentionally lives on WindowLayer.WINDOW (7), so it is not
recomposed/dimmed with the normal battle VIEW layer. Keep layer 7, but suppress
the indicator while temporary battle overlays are active.

WoT 2.4 no longer exposes the old top-level InputHandler module, so TAB/N/B
tracking uses AvatarInputHandler.handleKeyEvent, the same proven input path as
the High Caliber drag helper.
"""

import BigWorld

from gui.impl.pub import WindowImpl
from gui.mods import mod_highcaliber as hc

_installed = False
_blocking_windows = {}
_key_blocked = False

_orig_window_load = None
_orig_window_destroy = None
_orig_view_push = None

_avatar_key_original = None
_avatar_key_wrapper = None

# Keep this narrow: passive layer-7 mod windows must not suppress High Caliber.
_BLOCKER_TOKENS = (
    'prebattlehighlights',
    'ingamemenu',
    'fullstats',
    'battlefullstats',
    'battlemission',
    'battlequest',
    'personalmission',
    'missionwindow',
    'missionswindow',
    'questwindow',
    'questswindow',
    'reservewindow',
    'reserveswindow',
    'battlepasswindow',
)


def _listener_view():
    try:
        listener = hc._listener
        return None if listener is None else listener.view
    except Exception:
        return None


def _window_text(window):
    parts = []
    try:
        parts.append(window.__class__.__name__)
    except Exception:
        pass
    try:
        content = getattr(window, 'content', None)
        if content is not None:
            parts.append(content.__class__.__name__)
    except Exception:
        pass
    try:
        parts.append(repr(window))
    except Exception:
        pass
    try:
        return ' '.join(parts).lower()
    except Exception:
        return ''


def _is_highcaliber_window(window):
    try:
        return isinstance(window, hc.HighCaliberWindow)
    except Exception:
        try:
            return window.__class__.__name__ == 'HighCaliberWindow'
        except Exception:
            return False


def _is_blocker(window):
    if _is_highcaliber_window(window):
        return False
    text = _window_text(window)
    for token in _BLOCKER_TOKENS:
        if token in text:
            return True
    return False


def _keys_down():
    """TAB = roster/stats, N = battle tasks, B = reserves/loadout."""
    try:
        import Keys
        for key in (
                getattr(Keys, 'KEY_TAB', None),
                getattr(Keys, 'KEY_N', None),
                getattr(Keys, 'KEY_B', None)):
            if key is not None:
                try:
                    if BigWorld.isKeyDown(key):
                        return True
                except Exception:
                    pass
    except Exception:
        pass
    return False


def _suppressed():
    return bool(_blocking_windows or _key_blocked)


def _apply_visibility():
    view = _listener_view()
    if view is None:
        return
    try:
        if _suppressed():
            view.hide()
        else:
            _orig_view_push(view)
    except Exception:
        hc._logger.exception('Failed to update High Caliber overlay visibility')


def _view_push(self):
    if _suppressed():
        try:
            self.hide()
        except Exception:
            hc._logger.exception('Failed to suppress High Caliber UI')
        return
    return _orig_view_push(self)


def _window_load(self, *args, **kwargs):
    result = _orig_window_load(self, *args, **kwargs)
    try:
        if _is_blocker(self):
            label = _window_text(self)
            _blocking_windows[id(self)] = label
            hc._logger.info('High Caliber hidden by battle overlay: %s', label)
            _apply_visibility()
        elif _is_highcaliber_window(self):
            _apply_visibility()
    except Exception:
        hc._logger.exception('High Caliber overlay load hook failed')
    return result


def _window_destroy(self, *args, **kwargs):
    key = id(self)
    was_blocker = key in _blocking_windows
    try:
        return _orig_window_destroy(self, *args, **kwargs)
    finally:
        if was_blocker:
            try:
                label = _blocking_windows.pop(key, '')
                hc._logger.info('High Caliber battle overlay closed: %s', label)
                _apply_visibility()
            except Exception:
                hc._logger.exception('High Caliber overlay destroy hook failed')


def _sample_keys():
    global _key_blocked
    blocked = _keys_down()
    if blocked == _key_blocked:
        return
    _key_blocked = blocked
    try:
        hc._logger.info('High Caliber hotkey overlay suppression: %s', blocked)
    except Exception:
        pass
    _apply_visibility()


def _install_input():
    """Install on the current AvatarInputHandler chain without breaking drag."""
    global _avatar_key_original, _avatar_key_wrapper
    if _avatar_key_wrapper is not None:
        return
    try:
        from AvatarInputHandler import AvatarInputHandler

        original = AvatarInputHandler.handleKeyEvent

        def _key_wrapper(self, *args, **kwargs):
            result = original(self, *args, **kwargs)
            try:
                _sample_keys()
            except Exception:
                hc._logger.exception('High Caliber overlay key sample failed')
            return result

        _key_wrapper._inq_hc_overlay_original = original
        AvatarInputHandler.handleKeyEvent = _key_wrapper
        _avatar_key_original = original
        _avatar_key_wrapper = _key_wrapper
        hc._logger.info('High Caliber TAB/N/B overlay hotkey hook installed')
    except Exception:
        hc._logger.exception('Failed to install High Caliber overlay hotkey guard')


def _restore_input():
    global _avatar_key_original, _avatar_key_wrapper
    try:
        from AvatarInputHandler import AvatarInputHandler
        if (_avatar_key_wrapper is not None and
                AvatarInputHandler.handleKeyEvent is _avatar_key_wrapper):
            AvatarInputHandler.handleKeyEvent = _avatar_key_original
    except Exception:
        pass
    _avatar_key_original = None
    _avatar_key_wrapper = None


def init():
    global _installed
    global _orig_window_load, _orig_window_destroy, _orig_view_push
    if _installed:
        return

    _orig_window_load = WindowImpl.load
    _orig_window_destroy = WindowImpl.destroy
    _orig_view_push = hc.HighCaliberView.push

    WindowImpl.load = _window_load
    WindowImpl.destroy = _window_destroy
    hc.HighCaliberView.push = _view_push
    _install_input()

    _installed = True
    hc._logger.info('High Caliber layer-7 overlay visibility guard installed')


def fini():
    global _installed, _key_blocked
    if not _installed:
        return

    _restore_input()
    try:
        if WindowImpl.load is _window_load:
            WindowImpl.load = _orig_window_load
        if WindowImpl.destroy is _window_destroy:
            WindowImpl.destroy = _orig_window_destroy
        if hc.HighCaliberView.push is _view_push:
            hc.HighCaliberView.push = _orig_view_push
    except Exception:
        pass

    _blocking_windows.clear()
    _key_blocked = False
    _installed = False
