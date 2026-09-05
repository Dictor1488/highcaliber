# -*- coding: utf-8 -*-
"""Visibility guard for the layer-7 High Caliber battle window.

High Caliber intentionally lives on WindowLayer.WINDOW (7), so it is not
recomposed/dimmed with the normal battle VIEW layer.  The downside is that a
standalone layer-7 window created later can sit above WG battle overlays.

Keep layer 7, but suppress only the indicator contents while temporary battle
menus are active.  We cover both Wulf windows (prebattle highlights, missions,
reserves, full stats, ingame menu) and the hold-style battle hotkeys TAB/N/B.
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

_input_down_installed = False
_input_up_installed = False

# Tokens are intentionally narrow.  Do not treat every layer-7 window as a
# blocker: WN8/player panels and other passive mods can legitimately share it.
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
        return window.__class__.__name__ == 'HighCaliberWindow'


def _is_blocker(window):
    if _is_highcaliber_window(window):
        return False
    text = _window_text(window)
    for token in _BLOCKER_TOKENS:
        if token in text:
            return True
    return False


def _keys_down():
    """TAB = team/full stats, N = battle tasks, B = reserves/loadout."""
    try:
        import Keys
        key_codes = (
            getattr(Keys, 'KEY_TAB', None),
            getattr(Keys, 'KEY_N', None),
            getattr(Keys, 'KEY_B', None),
        )
        for key in key_codes:
            if key is not None and BigWorld.isKeyDown(key):
                return True
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
            # push() is wrapped below and therefore remains suppression-safe
            # even if another source updates damage during a menu transition.
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
            _blocking_windows[id(self)] = _window_text(self)
            hc._logger.info('High Caliber hidden by battle overlay: %s', _blocking_windows[id(self)])
            _apply_visibility()
        elif _is_highcaliber_window(self):
            # A blocker such as PrebattleHighlightsWindow can already be open
            # before HighCaliberWindow is created.
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


def _sample_keys(*args, **kwargs):
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
    global _input_down_installed, _input_up_installed
    try:
        import InputHandler
        if not _input_down_installed:
            InputHandler.g_instance.onKeyDown += _sample_keys
            _input_down_installed = True
        if not _input_up_installed:
            InputHandler.g_instance.onKeyUp += _sample_keys
            _input_up_installed = True
    except Exception:
        # Wulf window tracking still handles persistent/toggle-style menus.
        hc._logger.exception('Failed to install High Caliber overlay hotkey guard')


def _restore_input():
    global _input_down_installed, _input_up_installed
    try:
        import InputHandler
        if _input_down_installed:
            InputHandler.g_instance.onKeyDown -= _sample_keys
        if _input_up_installed:
            InputHandler.g_instance.onKeyUp -= _sample_keys
    except Exception:
        pass
    _input_down_installed = False
    _input_up_installed = False


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
