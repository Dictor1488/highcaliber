# -*- coding: utf-8 -*-
"""Native Ctrl-drag for the passive High Caliber GameFace surface.

The Wulf window stays fixed on WindowLayer.VIEW. Dragging only changes the
indicator's logical offset inside that surface and pushes the new model state.
This avoids moving destroyed Wulf windows and keeps GameFace sizing independent
from the 150x40 indicator geometry.
"""

import json
import os

import BigWorld
import GUI

from frameworks.wulf import ViewModel
from gui.mods import mod_highcaliber as hc

_BASE_WIDTH = 150.0
_BASE_HEIGHT = 40.0
_EDGE_TOLERANCE = 2.0

_editing = False
_installed = False
_gesture_latched = False
_drag_active = False
_drag_start_cursor = None
_drag_start_offsets = None

_orig_model_init = None
_orig_model_initialize = None
_orig_view_push = None

_avatar_key_original = None
_avatar_mouse_original = None
_avatar_key_wrapper = None
_avatar_mouse_wrapper = None
_gui_mouse_installed = False
_fallback_input_installed = False


def _battle_active():
    try:
        return getattr(BigWorld.player(), 'arena', None) is not None
    except Exception:
        return False


def _save_config():
    try:
        if not os.path.isdir(hc._CONFIG_DIR):
            os.makedirs(hc._CONFIG_DIR)
        with open(hc._CONFIG_PATH, 'w') as stream:
            json.dump(hc._CONFIG, stream, indent=2, sort_keys=True)
    except Exception:
        hc._logger.exception('Failed to save High Caliber position')


def _listener_parts():
    try:
        listener = hc._listener
        if listener is None:
            return None, None
        window = listener.window
        view = listener.view
        if window is None or view is None:
            return None, None
        if getattr(view, 'viewModel', None) is None:
            return None, None
        # Destroyed Wulf windows are detached from their area and lose content.
        if getattr(window, 'content', None) is None:
            return None, None
        return window, view
    except Exception:
        return None, None


def _view():
    return _listener_parts()[1]


def _window():
    return _listener_parts()[0]


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


def _screen_resolution():
    try:
        width, height = GUI.screenResolution()[:2]
        if width > 0 and height > 0:
            return (float(width), float(height))
    except Exception:
        pass
    return (1920.0, 1080.0)


def _parent_logical_size(window):
    try:
        size = _pair(getattr(getattr(window, 'parent', None), 'size', None))
        if size is not None and size[0] > 0 and size[1] > 0:
            return size
    except Exception:
        pass
    return _screen_resolution()


def _window_scale(window):
    screen_w, screen_h = _screen_resolution()
    logical_w, logical_h = _parent_logical_size(window)
    if logical_w <= 0 or logical_h <= 0:
        return (1.0, 1.0)
    sx = screen_w / float(logical_w)
    sy = screen_h / float(logical_h)
    if not 0.4 <= sx <= 4.0:
        sx = 1.0
    if not 0.4 <= sy <= 4.0:
        sy = 1.0
    return (sx, sy)


def _config_scale():
    try:
        value = float(hc._CONFIG.get('scale', 1.0) or 1.0)
    except Exception:
        value = 1.0
    return max(0.5, min(2.0, value))


def _offsets():
    try:
        x = float(hc._CONFIG.get('offsetX', 380) or 0)
    except Exception:
        x = 380.0
    try:
        y = float(hc._CONFIG.get('offsetY', 0) or 0)
    except Exception:
        y = 0.0
    return x, y


def _clamp_offsets(window, x, y):
    parent_w, parent_h = _parent_logical_size(window)
    scale = _config_scale()
    panel_w = _BASE_WIDTH * scale
    panel_h = _BASE_HEIGHT * scale
    min_x = -(parent_w - panel_w) * 0.5
    max_x = (parent_w - panel_w) * 0.5
    max_y = max(0.0, parent_h - panel_h)
    return (max(min_x, min(float(x), max_x)),
            max(0.0, min(float(y), max_y)))


def _panel_pixel_rect(window):
    parent_w, _ = _parent_logical_size(window)
    sx, sy = _window_scale(window)
    scale = _config_scale()
    ox, oy = _offsets()
    logical_x = (parent_w - _BASE_WIDTH * scale) * 0.5 + ox
    logical_y = oy
    return (logical_x * sx,
            logical_y * sy,
            _BASE_WIDTH * scale * sx,
            _BASE_HEIGHT * scale * sy)


def _cursor_pixels():
    try:
        norm_x, norm_y = GUI.mcursor().position
        screen_w, screen_h = _screen_resolution()
        return ((float(norm_x) + 1.0) * 0.5 * screen_w,
                (1.0 - float(norm_y)) * 0.5 * screen_h)
    except Exception:
        return None


def _cursor_on_panel(window, cursor):
    if cursor is None:
        return False
    x, y, w, h = _panel_pixel_rect(window)
    return (x - _EDGE_TOLERANCE <= cursor[0] <= x + w + _EDGE_TOLERANCE and
            y - _EDGE_TOLERANCE <= cursor[1] <= y + h + _EDGE_TOLERANCE)


def _push_edit_state():
    view = _view()
    if view is None:
        return
    try:
        model = view.viewModel
        if model is None:
            return
        with model.transaction() as tx:
            tx.setEditing(bool(_editing))
    except Exception:
        # Destruction can race an input edge by one frame. Do not log a false
        # error once the battle/view is already gone.
        if _battle_active() and _view() is not None:
            hc._logger.exception('Failed to push High Caliber edit state')


def _push_position():
    view = _view()
    if view is None:
        return
    try:
        view.push()
    except Exception:
        if _battle_active() and _view() is not None:
            hc._logger.exception('Failed to push High Caliber position')


def _set_editing(value):
    global _editing
    value = bool(value and _battle_active() and hc._CONFIG.get('drag', True)
                 and _view() is not None)
    if value == _editing:
        return
    if not value:
        _finish_drag()
    _editing = value
    _push_edit_state()


def _start_drag(window, cursor):
    global _drag_active, _drag_start_cursor, _drag_start_offsets
    if _drag_active or cursor is None:
        return
    _drag_active = True
    _drag_start_cursor = cursor
    _drag_start_offsets = _offsets()


def _move_drag(window, cursor):
    if not _drag_active or cursor is None or _drag_start_cursor is None:
        return
    sx, sy = _window_scale(window)
    dx = (cursor[0] - _drag_start_cursor[0]) / (sx if sx else 1.0)
    dy = (cursor[1] - _drag_start_cursor[1]) / (sy if sy else 1.0)
    x, y = _clamp_offsets(window,
                          _drag_start_offsets[0] + dx,
                          _drag_start_offsets[1] + dy)
    new_x = int(round(x))
    new_y = int(round(y))
    if (hc._CONFIG.get('offsetX') == new_x and
            hc._CONFIG.get('offsetY') == new_y):
        return
    hc._CONFIG['offsetX'] = new_x
    hc._CONFIG['offsetY'] = new_y
    _push_position()


def _finish_drag():
    global _drag_active, _drag_start_cursor, _drag_start_offsets
    was_active = _drag_active
    _drag_active = False
    _drag_start_cursor = None
    _drag_start_offsets = None
    if was_active:
        _save_config()


def _ctrl_down_now():
    try:
        import Keys
        return bool(BigWorld.isKeyDown(getattr(Keys, 'KEY_LCONTROL', 29)) or
                    BigWorld.isKeyDown(getattr(Keys, 'KEY_RCONTROL', 157)))
    except Exception:
        return False


def _lmb_down_now():
    try:
        import Keys
        return bool(BigWorld.isKeyDown(Keys.KEY_LEFTMOUSE))
    except Exception:
        return False


def _sample_input(mouse_move=False):
    global _gesture_latched

    if not _battle_active():
        if _gesture_latched or _drag_active or _editing:
            _reset_state()
        return

    window, view = _listener_parts()
    if window is None or view is None:
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
            if _cursor_on_panel(window, cursor):
                _start_drag(window, cursor)
        elif not gesture and _gesture_latched:
            _gesture_latched = False
            _finish_drag()

        if mouse_move and gesture and _drag_active:
            _move_drag(window, _cursor_pixels())
    except Exception:
        hc._logger.exception('High Caliber input sample failed')


def _handle_gui_mouse_event(event):
    _sample_input(mouse_move=True)
    return False


def _fallback_key_event(event):
    _sample_input(mouse_move=False)


def _install_input():
    global _avatar_key_original, _avatar_mouse_original
    global _avatar_key_wrapper, _avatar_mouse_wrapper
    global _gui_mouse_installed, _fallback_input_installed

    try:
        from AvatarInputHandler import AvatarInputHandler

        if _avatar_key_wrapper is None:
            original = AvatarInputHandler.handleKeyEvent

            def _key_wrapper(self, *args, **kwargs):
                result = original(self, *args, **kwargs)
                _sample_input(mouse_move=False)
                return result

            _key_wrapper._inq_hc_drag_original = original
            AvatarInputHandler.handleKeyEvent = _key_wrapper
            _avatar_key_original = original
            _avatar_key_wrapper = _key_wrapper

        if _avatar_mouse_wrapper is None:
            original_mouse = AvatarInputHandler.handleMouseEvent

            def _mouse_wrapper(self, *args, **kwargs):
                result = original_mouse(self, *args, **kwargs)
                _sample_input(mouse_move=True)
                return result

            _mouse_wrapper._inq_hc_drag_original = original_mouse
            AvatarInputHandler.handleMouseEvent = _mouse_wrapper
            _avatar_mouse_original = original_mouse
            _avatar_mouse_wrapper = _mouse_wrapper
    except Exception:
        hc._logger.exception('Failed to hook AvatarInputHandler for High Caliber drag')

    if not _gui_mouse_installed:
        try:
            from gui import g_mouseEventHandlers
            g_mouseEventHandlers.add(_handle_gui_mouse_event)
            _gui_mouse_installed = True
        except Exception:
            hc._logger.exception('Failed to join g_mouseEventHandlers for High Caliber drag')

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
    ViewModel.__init__(self, properties=2, commands=1)


def _model_get_editing(self):
    return self._getBool(1)


def _model_set_editing(self, value):
    self._setBool(1, bool(value))


def _model_initialize(self):
    _orig_model_initialize(self)
    self._addBoolProperty('editing', False)


def _view_push(self):
    if getattr(self, 'viewModel', None) is None:
        return
    _orig_view_push(self)
    _push_edit_state()


def _install():
    global _installed
    global _orig_model_init, _orig_model_initialize, _orig_view_push
    if _installed:
        return

    if 'drag' not in hc._CONFIG:
        hc._CONFIG['drag'] = True

    _orig_model_init = hc.HighCaliberModel.__init__
    _orig_model_initialize = hc.HighCaliberModel._initialize
    _orig_view_push = hc.HighCaliberView.push

    hc.HighCaliberModel.__init__ = _model_init
    hc.HighCaliberModel._initialize = _model_initialize
    hc.HighCaliberModel.getEditing = _model_get_editing
    hc.HighCaliberModel.setEditing = _model_set_editing
    hc.HighCaliberView.push = _view_push

    _install_input()
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
