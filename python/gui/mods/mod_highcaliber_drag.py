# -*- coding: utf-8 -*-
"""Native Ctrl-drag support for the standalone High Caliber indicator.

The GameFace document is render-only.  Drag input is observed from WoT's own
battle input path and never depends on the GameFace hit rectangle, so changing
team panels or any other HUD layout cannot disable the gesture.

Only the High Caliber gesture matters here:
    Ctrl down              -> show edit outline / arm drag
    Ctrl + LMB on panel    -> begin drag
    mouse move             -> place the small Wulf window absolutely
    LMB/Ctrl release       -> persist once

There are no HUD/ears/resize listeners and no self-rescheduling input poll.
"""

import json
import os

import BigWorld
import GUI

from frameworks.wulf import ViewModel, PositionAnchor
from gui.mods import mod_highcaliber as hc

_BASE_WIDTH = 150.0
_BASE_HEIGHT = 40.0

_editing = False
_installed = False
_gesture_latched = False
_drag_active = False
_drag_grab = None
_drag_last_xy = None

_orig_model_init = None
_orig_model_initialize = None
_orig_view_push = None
_orig_window_ready = None

_avatar_key_original = None
_avatar_mouse_original = None
_avatar_key_wrapper = None
_avatar_mouse_wrapper = None
_gui_mouse_installed = False

_fallback_input_installed = False


def _save_config():
    try:
        if not os.path.isdir(hc._CONFIG_DIR):
            os.makedirs(hc._CONFIG_DIR)
        with open(hc._CONFIG_PATH, 'w') as stream:
            json.dump(hc._CONFIG, stream, indent=2, sort_keys=True)
    except Exception:
        hc._logger.exception('Failed to save High Caliber position')


def _view():
    try:
        listener = hc._listener
        return None if listener is None else listener.view
    except Exception:
        return None


def _window():
    try:
        listener = hc._listener
        return None if listener is None else listener.window
    except Exception:
        return None


def _pair(value):
    if value is None:
        return None
    try:
        return (float(value.x), float(value.y))
    except Exception:
        try:
            return (float(value[0]), float(value[1]))
        except Exception:
            return None


def _panel_size():
    try:
        scale = float(hc._CONFIG.get('scale', 1.0) or 1.0)
    except Exception:
        scale = 1.0
    scale = max(0.5, min(2.0, scale))
    return (_BASE_WIDTH * scale, _BASE_HEIGHT * scale)


def _interface_scale(window):
    """Physical pixels per logical Wulf unit."""
    try:
        physical = _pair(GUI.screenResolution())
        logical = _pair(getattr(getattr(window, 'parent', None), 'size', None))
        if physical is None or logical is None or logical[0] <= 0 or logical[1] <= 0:
            return 1.0
        value = ((physical[0] / logical[0]) + (physical[1] / logical[1])) * 0.5
        return max(0.5, min(4.0, float(value)))
    except Exception:
        return 1.0


def _parent_size(window):
    try:
        size = _pair(getattr(getattr(window, 'parent', None), 'size', None))
        if size is not None and size[0] > 0 and size[1] > 0:
            return size
    except Exception:
        pass
    try:
        physical = _pair(GUI.screenResolution())
        scale = _interface_scale(window)
        if physical is not None:
            return (physical[0] / scale, physical[1] / scale)
    except Exception:
        pass
    return (1920.0, 1080.0)


def _clamp_xy(window, x, y):
    parent_w, parent_h = _parent_size(window)
    panel_w, panel_h = _panel_size()
    max_x = max(0.0, parent_w - panel_w)
    max_y = max(0.0, parent_h - panel_h)
    return (max(0.0, min(float(x), max_x)),
            max(0.0, min(float(y), max_y)))


def _position_from_config(window):
    parent_w, _ = _parent_size(window)
    panel_w, _ = _panel_size()
    try:
        offset_x = float(hc._CONFIG.get('offsetX', 380) or 0)
    except Exception:
        offset_x = 380.0
    try:
        offset_y = float(hc._CONFIG.get('offsetY', 0) or 0)
    except Exception:
        offset_y = 0.0
    x = (parent_w - panel_w) * 0.5 + offset_x
    y = offset_y
    return _clamp_xy(window, x, y)


def _config_from_position(window, x, y):
    parent_w, _ = _parent_size(window)
    panel_w, _ = _panel_size()
    x, y = _clamp_xy(window, x, y)
    hc._CONFIG['offsetX'] = int(round(x - (parent_w - panel_w) * 0.5))
    hc._CONFIG['offsetY'] = int(round(y))
    return x, y


def _window_position(window):
    try:
        pos = _pair(getattr(window, 'position', None))
        if pos is not None:
            return _clamp_xy(window, pos[0], pos[1])
    except Exception:
        pass
    return _position_from_config(window)


def _move_window(window, x, y):
    x, y = _clamp_xy(window, x, y)
    try:
        window.move(int(round(x)), int(round(y)),
                    xAnchor=PositionAnchor.LEFT,
                    yAnchor=PositionAnchor.TOP)
    except TypeError:
        window.move(int(round(x)), int(round(y)))
    return x, y


def _apply_saved_position():
    """Apply config at creation/own Ctrl only; never from unrelated HUD updates."""
    if _drag_active:
        return
    window = _window()
    if window is None:
        return
    try:
        x, y = _position_from_config(window)
        _move_window(window, x, y)
    except Exception:
        hc._logger.exception('Failed to position High Caliber window')


def _cursor_logical(window):
    """Return free cursor in Wulf logical coordinates.

    Current WoT builds expose GUI.mcursor().position as clip coordinates during
    the normal battle path, but some paths/builds expose device pixels.  Accept
    both conventions and then divide by the actual interface scale.
    """
    try:
        pos = _pair(GUI.mcursor().position)
        resolution = _pair(GUI.screenResolution())
        if pos is None or resolution is None:
            return None
        if abs(pos[0]) <= 1.5 and abs(pos[1]) <= 1.5:
            px = (pos[0] * 0.5 + 0.5) * resolution[0]
            py = (0.5 - pos[1] * 0.5) * resolution[1]
        else:
            px, py = pos
        scale = _interface_scale(window)
        return (px / scale, py / scale)
    except Exception:
        return None


def _ctrl_down_now():
    try:
        import Keys
        left = getattr(Keys, 'KEY_LCONTROL', 29)
        right = getattr(Keys, 'KEY_RCONTROL', 157)
        return bool(BigWorld.isKeyDown(left) or BigWorld.isKeyDown(right))
    except Exception:
        for key in (29, 157):
            try:
                if BigWorld.isKeyDown(key):
                    return True
            except Exception:
                pass
    return False


def _lmb_down_now():
    try:
        import Keys
        return bool(BigWorld.isKeyDown(Keys.KEY_LEFTMOUSE))
    except Exception:
        return False


def _cursor_on_panel(window, cursor):
    if cursor is None:
        return False
    x, y = _position_from_config(window)
    w, h = _panel_size()
    # A tiny logical tolerance protects the edge from fractional UI scale.
    return (cursor[0] >= x - 2.0 and cursor[0] <= x + w + 2.0 and
            cursor[1] >= y - 2.0 and cursor[1] <= y + h + 2.0)


def _push_edit_state():
    view = _view()
    if view is None:
        return
    try:
        with view.viewModel.transaction() as model:
            model.setEditing(bool(_editing))
    except Exception:
        hc._logger.exception('Failed to push High Caliber edit state')


def _set_editing(value):
    global _editing
    value = bool(value and hc._CONFIG.get('drag', True) and _window() is not None)
    if value == _editing:
        return
    if not value:
        _finish_drag()
    _editing = value
    if _editing:
        # This is deliberately the only runtime position reassert: our Ctrl.
        _apply_saved_position()
    hc._logger.info('High Caliber edit mode: %s', _editing)
    _push_edit_state()


def _start_drag(window, cursor):
    global _drag_active, _drag_grab, _drag_last_xy
    if _drag_active or cursor is None:
        return
    try:
        # Own Ctrl just reasserted config, so use the actual applied position.
        x, y = _window_position(window)
        _drag_grab = (cursor[0] - x, cursor[1] - y)
        _drag_last_xy = (x, y)
        _drag_active = True
        hc._logger.info('High Caliber drag started')
    except Exception:
        _drag_active = False
        _drag_grab = None
        _drag_last_xy = None
        hc._logger.exception('High Caliber drag start failed')


def _move_drag(window, cursor):
    global _drag_last_xy
    if not _drag_active or _drag_grab is None or cursor is None:
        return
    try:
        x = cursor[0] - _drag_grab[0]
        y = cursor[1] - _drag_grab[1]
        _drag_last_xy = _move_window(window, x, y)
    except Exception:
        hc._logger.exception('High Caliber drag move failed')
        _finish_drag()


def _finish_drag():
    global _drag_active, _drag_grab, _drag_last_xy
    if not _drag_active:
        _drag_grab = None
        _drag_last_xy = None
        return
    window = _window()
    final_xy = _drag_last_xy
    _drag_active = False
    _drag_grab = None
    _drag_last_xy = None
    if window is None or final_xy is None:
        return
    try:
        x, y = _config_from_position(window, final_xy[0], final_xy[1])
        _move_window(window, x, y)
        _save_config()
        hc._logger.info('High Caliber position saved: x=%s y=%s',
                        hc._CONFIG.get('offsetX'), hc._CONFIG.get('offsetY'))
    except Exception:
        hc._logger.exception('High Caliber drag end failed')


def _sample_input(mouse_move=False):
    """Observe only Ctrl/LMB.  Never consumes or modifies the game's event."""
    global _gesture_latched
    try:
        ctrl = _ctrl_down_now()
        _set_editing(ctrl)

        gesture = bool(ctrl and _lmb_down_now())
        window = _window()

        if gesture and not _gesture_latched:
            _gesture_latched = True
            if window is not None:
                cursor = _cursor_logical(window)
                if _cursor_on_panel(window, cursor):
                    _start_drag(window, cursor)
        elif not gesture and _gesture_latched:
            _gesture_latched = False
            _finish_drag()

        if mouse_move and gesture and _drag_active and window is not None:
            _move_drag(window, _cursor_logical(window))
    except Exception:
        hc._logger.exception('High Caliber input sample failed')


def _handle_gui_mouse_event(event):
    # gui.g_mouseEventHandlers is an observer registry. False means unconsumed.
    _sample_input(mouse_move=True)
    return False


def _fallback_key_event(event):
    _sample_input(mouse_move=False)


def _install_input():
    global _avatar_key_original, _avatar_mouse_original
    global _avatar_key_wrapper, _avatar_mouse_wrapper
    global _gui_mouse_installed, _fallback_input_installed

    # WoT 2.4 central battle dispatchers. Wrappers always call the original
    # first and preserve its return value; we only observe live key state.
    try:
        from AvatarInputHandler import AvatarInputHandler

        if _avatar_key_wrapper is None:
            original = AvatarInputHandler.handleKeyEvent
            original = getattr(original, '_inq_hc_original', original)

            def _key_wrapper(self, *args, **kwargs):
                result = original(self, *args, **kwargs)
                _sample_input(mouse_move=False)
                return result

            _key_wrapper._inq_hc_original = original
            AvatarInputHandler.handleKeyEvent = _key_wrapper
            _avatar_key_original = original
            _avatar_key_wrapper = _key_wrapper

        if _avatar_mouse_wrapper is None:
            original_mouse = AvatarInputHandler.handleMouseEvent
            original_mouse = getattr(original_mouse, '_inq_hc_original', original_mouse)

            def _mouse_wrapper(self, *args, **kwargs):
                result = original_mouse(self, *args, **kwargs)
                _sample_input(mouse_move=True)
                return result

            _mouse_wrapper._inq_hc_original = original_mouse
            AvatarInputHandler.handleMouseEvent = _mouse_wrapper
            _avatar_mouse_original = original_mouse
            _avatar_mouse_wrapper = _mouse_wrapper
    except Exception:
        hc._logger.exception('Failed to hook AvatarInputHandler for High Caliber drag')

    # Third WG-native observation point. This is a set, not a monkey patch.
    if not _gui_mouse_installed:
        try:
            from gui import g_mouseEventHandlers
            g_mouseEventHandlers.add(_handle_gui_mouse_event)
            _gui_mouse_installed = True
        except Exception:
            hc._logger.exception('Failed to join g_mouseEventHandlers for High Caliber drag')

    # Fallback key edges for builds where AvatarInputHandler is instantiated
    # through a path that bypasses the class method above. No timer/polling.
    if not _fallback_input_installed:
        try:
            import InputHandler
            InputHandler.g_instance.onKeyDown += _fallback_key_event
            InputHandler.g_instance.onKeyUp += _fallback_key_event
            _fallback_input_installed = True
        except Exception:
            pass


def _restore_input():
    global _avatar_key_original, _avatar_mouse_original
    global _avatar_key_wrapper, _avatar_mouse_wrapper
    global _gui_mouse_installed, _fallback_input_installed

    try:
        from AvatarInputHandler import AvatarInputHandler
        if (_avatar_key_wrapper is not None and
                AvatarInputHandler.handleKeyEvent is _avatar_key_wrapper):
            AvatarInputHandler.handleKeyEvent = _avatar_key_original
        if (_avatar_mouse_wrapper is not None and
                AvatarInputHandler.handleMouseEvent is _avatar_mouse_wrapper):
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
            import InputHandler
            InputHandler.g_instance.onKeyDown -= _fallback_key_event
            InputHandler.g_instance.onKeyUp -= _fallback_key_event
        except Exception:
            pass

    _avatar_key_original = None
    _avatar_mouse_original = None
    _avatar_key_wrapper = None
    _avatar_mouse_wrapper = None
    _gui_mouse_installed = False
    _fallback_input_installed = False


def _model_init(self, properties=2, commands=1):
    # Core owns payload + its compatibility command. We only add editing bool.
    ViewModel.__init__(self, properties=2, commands=1)


def _model_get_editing(self):
    return self._getBool(1)


def _model_set_editing(self, value):
    self._setBool(1, bool(value))


def _model_initialize(self):
    _orig_model_initialize(self)
    self._addBoolProperty('editing', False)


def _view_push(self):
    # Data updates must never reposition or otherwise touch drag state.
    _orig_view_push(self)
    _push_edit_state()


def _window_ready(self):
    _orig_window_ready(self)
    try:
        BigWorld.callback(0.0, _apply_saved_position)
    except Exception:
        _apply_saved_position()


def _install():
    global _installed
    global _orig_model_init, _orig_model_initialize, _orig_view_push, _orig_window_ready
    if _installed:
        return

    if 'drag' not in hc._CONFIG:
        hc._CONFIG['drag'] = True

    _orig_model_init = hc.HighCaliberModel.__init__
    _orig_model_initialize = hc.HighCaliberModel._initialize
    _orig_view_push = hc.HighCaliberView.push
    _orig_window_ready = hc.HighCaliberWindow._onReady

    hc.HighCaliberModel.__init__ = _model_init
    hc.HighCaliberModel._initialize = _model_initialize
    hc.HighCaliberModel.getEditing = _model_get_editing
    hc.HighCaliberModel.setEditing = _model_set_editing
    hc.HighCaliberView.push = _view_push
    hc.HighCaliberWindow._onReady = _window_ready

    _install_input()
    hc._logger.info('High Caliber native event-driven Ctrl-drag installed')
    _installed = True


def _restore():
    global _installed, _editing, _gesture_latched
    if not _installed:
        return

    _finish_drag()
    _restore_input()

    try:
        if _orig_model_init is not None:
            hc.HighCaliberModel.__init__ = _orig_model_init
        if _orig_model_initialize is not None:
            hc.HighCaliberModel._initialize = _orig_model_initialize
        if _orig_view_push is not None:
            hc.HighCaliberView.push = _orig_view_push
        if _orig_window_ready is not None:
            hc.HighCaliberWindow._onReady = _orig_window_ready
    except Exception:
        pass

    _editing = False
    _gesture_latched = False
    _installed = False


def _reset_state():
    global _editing, _gesture_latched
    _finish_drag()
    _editing = False
    _gesture_latched = False


def init():
    _install()


def fini():
    _restore()


def onDisconnected():
    _reset_state()


def onAccountBecomeNonPlayer():
    _reset_state()
