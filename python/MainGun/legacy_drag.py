# -*- coding: utf-8 -*-
"""Event-driven Ctrl+drag behavior matching the old INQ HighCaliber implementation."""

import json

import BigWorld
import Keys

try:
    import GUI
except Exception:
    GUI = None

from .utils import logger, cursorPixels
from .views.main_gun_panel import MainGunPanel

_installed = False
_editing = False
_gesture_latched = False
_drag_active = False
_drag_start_cursor = None
_drag_start_position = None

_avatar_key_original = None
_avatar_mouse_original = None
_avatar_key_wrapper = None
_avatar_mouse_wrapper = None
_gui_mouse_installed = False
_fallback_input_installed = False

_orig_build_payload = None
_orig_start_drag_ticker = None
_orig_stop_drag_ticker = None


def _panel():
    try:
        import MainGun
        return MainGun.g_mainGunPanel
    except Exception:
        return None


def _battle_active():
    panel = _panel()
    return bool(panel is not None and getattr(panel, '_isInitialized', False) and not getattr(panel, '_destroyed', True))


def _ctrl_down_now():
    try:
        return bool(BigWorld.isKeyDown(Keys.KEY_LCONTROL) or BigWorld.isKeyDown(Keys.KEY_RCONTROL))
    except Exception:
        return False


def _lmb_down_now():
    try:
        return bool(BigWorld.isKeyDown(Keys.KEY_LEFTMOUSE))
    except Exception:
        return False


def _cursor_pixels():
    if GUI is None:
        return None
    try:
        return cursorPixels(GUI.mcursor())
    except Exception:
        return None


def _publish_edit_state():
    panel = _panel()
    if panel is None:
        return
    try:
        panel._lastPayload = None
        panel.publish()
    except Exception:
        if _battle_active():
            logger.exception('[HighCaliber] failed to publish edit state')


def _set_editing(value):
    global _editing
    value = bool(value and _battle_active())
    if value == _editing:
        return
    if not value:
        _finish_drag()
    _editing = value
    _publish_edit_state()


def _start_drag(panel, cursor):
    global _drag_active, _drag_start_cursor, _drag_start_position
    if _drag_active or cursor is None:
        return
    _drag_active = True
    _drag_start_cursor = cursor
    _drag_start_position = tuple(panel._position)


def _move_drag(panel, cursor):
    if not _drag_active or cursor is None or _drag_start_cursor is None or _drag_start_position is None:
        return
    dx = cursor[0] - _drag_start_cursor[0]
    dy = cursor[1] - _drag_start_cursor[1]
    panel._setPosition(_drag_start_position[0] + dx, _drag_start_position[1] + dy)


def _finish_drag():
    global _drag_active, _drag_start_cursor, _drag_start_position
    panel = _panel()
    was_active = _drag_active
    _drag_active = False
    _drag_start_cursor = None
    _drag_start_position = None
    if was_active and panel is not None:
        try:
            panel._savePositionIfChanged()
        except Exception:
            pass


def _reset_state():
    global _editing, _gesture_latched
    _finish_drag()
    _editing = False
    _gesture_latched = False
    _publish_edit_state()


def _sample_input(mouse_move=False):
    global _gesture_latched

    panel = _panel()
    if panel is None or not _battle_active():
        if _gesture_latched or _drag_active or _editing:
            _reset_state()
        return

    try:
        ctrl = _ctrl_down_now()
        _set_editing(ctrl)
        gesture = bool(ctrl and _lmb_down_now())

        if gesture and not _gesture_latched:
            _gesture_latched = True
            cursor = _cursor_pixels()
            if cursor is not None and panel._isCursorOver(cursor):
                _start_drag(panel, cursor)
        elif not gesture and _gesture_latched:
            _gesture_latched = False
            _finish_drag()

        if mouse_move and gesture and _drag_active:
            _move_drag(panel, _cursor_pixels())
    except Exception:
        logger.exception('[HighCaliber] input sample failed')


def _handle_gui_mouse_event(event):
    _sample_input(mouse_move=True)
    return False


def _fallback_key_event(event):
    _sample_input(mouse_move=False)


def _build_payload(self):
    raw = _orig_build_payload(self)
    try:
        data = json.loads(raw)
        data['editing'] = bool(_editing and self._isInitialized and not self._destroyed)
        return json.dumps(data, ensure_ascii=False)
    except Exception:
        return raw


def _no_start_ticker(self):
    return


def _stop_ticker_and_legacy(self):
    try:
        if _orig_stop_drag_ticker is not None:
            _orig_stop_drag_ticker(self)
    finally:
        _reset_state()


def install():
    global _installed
    global _avatar_key_original, _avatar_mouse_original
    global _avatar_key_wrapper, _avatar_mouse_wrapper
    global _gui_mouse_installed, _fallback_input_installed
    global _orig_build_payload, _orig_start_drag_ticker, _orig_stop_drag_ticker

    if _installed:
        return

    _orig_build_payload = MainGunPanel.buildPayload
    _orig_start_drag_ticker = MainGunPanel._startDragTicker
    _orig_stop_drag_ticker = MainGunPanel._stopDragTicker
    MainGunPanel.buildPayload = _build_payload
    MainGunPanel._startDragTicker = _no_start_ticker
    MainGunPanel._stopDragTicker = _stop_ticker_and_legacy

    try:
        from AvatarInputHandler import AvatarInputHandler

        _avatar_key_original = AvatarInputHandler.handleKeyEvent
        def _key_wrapper(self, *args, **kwargs):
            result = _avatar_key_original(self, *args, **kwargs)
            _sample_input(mouse_move=False)
            return result
        _avatar_key_wrapper = _key_wrapper
        AvatarInputHandler.handleKeyEvent = _key_wrapper

        _avatar_mouse_original = AvatarInputHandler.handleMouseEvent
        def _mouse_wrapper(self, *args, **kwargs):
            result = _avatar_mouse_original(self, *args, **kwargs)
            _sample_input(mouse_move=True)
            return result
        _avatar_mouse_wrapper = _mouse_wrapper
        AvatarInputHandler.handleMouseEvent = _mouse_wrapper
    except Exception:
        logger.exception('[HighCaliber] failed to hook AvatarInputHandler drag')

    try:
        from gui import g_mouseEventHandlers
        g_mouseEventHandlers.add(_handle_gui_mouse_event)
        _gui_mouse_installed = True
    except Exception:
        pass

    try:
        from gui import InputHandler
        InputHandler.g_instance.onKeyDown += _fallback_key_event
        InputHandler.g_instance.onKeyUp += _fallback_key_event
        _fallback_input_installed = True
    except Exception:
        pass

    _installed = True
    logger.info('[HighCaliber] legacy event-driven Ctrl drag installed')


def uninstall():
    global _installed
    global _avatar_key_original, _avatar_mouse_original
    global _avatar_key_wrapper, _avatar_mouse_wrapper
    global _gui_mouse_installed, _fallback_input_installed

    if not _installed:
        return

    _reset_state()

    try:
        from AvatarInputHandler import AvatarInputHandler
        if _avatar_key_wrapper is not None and AvatarInputHandler.handleKeyEvent is _avatar_key_wrapper:
            AvatarInputHandler.handleKeyEvent = _avatar_key_original
        if _avatar_mouse_wrapper is not None and AvatarInputHandler.handleMouseEvent is _avatar_mouse_wrapper:
            AvatarInputHandler.handleMouseEvent = _avatar_mouse_original
    except Exception:
        pass

    if _gui_mouse_installed:
        try:
            from gui import g_mouseEventHandlers
            g_mouseEventHandlers.discard(_handle_gui_mouse_event)
        except Exception:
            pass

    if _fallback_input_installed:
        try:
            from gui import InputHandler
            InputHandler.g_instance.onKeyDown -= _fallback_key_event
            InputHandler.g_instance.onKeyUp -= _fallback_key_event
        except Exception:
            pass

    if _orig_build_payload is not None:
        MainGunPanel.buildPayload = _orig_build_payload
    if _orig_start_drag_ticker is not None:
        MainGunPanel._startDragTicker = _orig_start_drag_ticker
    if _orig_stop_drag_ticker is not None:
        MainGunPanel._stopDragTicker = _orig_stop_drag_ticker

    _avatar_key_original = None
    _avatar_mouse_original = None
    _avatar_key_wrapper = None
    _avatar_mouse_wrapper = None
    _gui_mouse_installed = False
    _fallback_input_installed = False
    _installed = False
