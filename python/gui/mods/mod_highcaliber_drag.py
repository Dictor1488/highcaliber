# -*- coding: utf-8 -*-
"""Native Ctrl-drag support for the standalone High Caliber indicator.

Drag follows the proven UnderPressurePH7/MainGun geometry:
- GUI.mcursor().position is converted directly to screen pixels;
- hit testing is done in screen pixels against the panel rectangle;
- the Wulf window is moved by converting screen pixels back through the
  actual window/interface scale;
- GameFace is render-only and never owns mouse input.

Input stays event-driven.  Only our Ctrl/LMB gesture is observed; there are no
HUD/ears/resize listeners and no permanent drag/input polling loop.
"""

import json
import os

import BigWorld
import GUI

from frameworks.wulf import ViewModel, PositionAnchor
from gui.mods import mod_highcaliber as hc

_BASE_WIDTH = 150.0
_BASE_HEIGHT = 40.0
_EDGE_TOLERANCE = 2.0

_editing = False
_installed = False
_gesture_latched = False
_drag_active = False
_drag_start_cursor = None
_drag_start_position = None
_drag_last_position = None

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


def _screen_resolution():
    try:
        width, height = GUI.screenResolution()[:2]
        if width > 0 and height > 0:
            return (float(width), float(height))
    except Exception:
        pass
    try:
        width = BigWorld.screenWidth()
        height = BigWorld.screenHeight()
        if width > 0 and height > 0:
            return (float(width), float(height))
    except Exception:
        pass
    return (1920.0, 1080.0)


def _cursor_pixels(cursor=None):
    """Exact MainGun cursor conversion: normalized GUI cursor -> screen px."""
    try:
        if cursor is None:
            cursor = GUI.mcursor()
        norm_x, norm_y = cursor.position
        screen_w, screen_h = _screen_resolution()
        return ((float(norm_x) + 1.0) * 0.5 * screen_w,
                (1.0 - float(norm_y)) * 0.5 * screen_h)
    except Exception:
        return None


def _config_scale():
    try:
        value = float(hc._CONFIG.get('scale', 1.0) or 1.0)
    except Exception:
        value = 1.0
    return max(0.5, min(2.0, value))


def _panel_logical_size():
    scale = _config_scale()
    return (_BASE_WIDTH * scale, _BASE_HEIGHT * scale)


def _parent_logical_size(window):
    try:
        size = _pair(getattr(getattr(window, 'parent', None), 'size', None))
        if size is not None and size[0] > 0 and size[1] > 0:
            return size
    except Exception:
        pass
    return _screen_resolution()


def _window_scale(window):
    """Screen pixels per Wulf logical unit, axis by axis.

    MainGun derives this from reported view size / native window size.  Our
    panel has a fixed GameFace surface, so the same conversion is obtained more
    directly from physical screen size / Wulf parent size.  This avoids the old
    clip-space/delta assumptions and remains correct at non-100% UI scale.
    """
    screen_w, screen_h = _screen_resolution()
    logical_w, logical_h = _parent_logical_size(window)
    if logical_w <= 0 or logical_h <= 0:
        return (1.0, 1.0)
    scale_x = screen_w / float(logical_w)
    scale_y = screen_h / float(logical_h)
    if not 0.4 <= scale_x <= 4.0:
        scale_x = 1.0
    if not 0.4 <= scale_y <= 4.0:
        scale_y = 1.0
    return (scale_x, scale_y)


def _panel_pixel_size(window):
    width, height = _panel_logical_size()
    scale_x, scale_y = _window_scale(window)
    return (width * scale_x, height * scale_y)


def _clamp_pixels(window, x, y):
    screen_w, screen_h = _screen_resolution()
    panel_w, panel_h = _panel_pixel_size(window)
    max_x = max(0.0, screen_w - panel_w)
    max_y = max(0.0, screen_h - panel_h)
    return (max(0.0, min(float(x), max_x)),
            max(0.0, min(float(y), max_y)))


def _logical_position_from_config(window):
    parent_w, _ = _parent_logical_size(window)
    panel_w, _ = _panel_logical_size()
    try:
        offset_x = float(hc._CONFIG.get('offsetX', 380) or 0)
    except Exception:
        offset_x = 380.0
    try:
        offset_y = float(hc._CONFIG.get('offsetY', 0) or 0)
    except Exception:
        offset_y = 0.0
    return ((parent_w - panel_w) * 0.5 + offset_x, offset_y)


def _pixel_position_from_config(window):
    logical_x, logical_y = _logical_position_from_config(window)
    scale_x, scale_y = _window_scale(window)
    return _clamp_pixels(window, logical_x * scale_x, logical_y * scale_y)


def _config_from_pixel_position(window, x, y):
    x, y = _clamp_pixels(window, x, y)
    scale_x, scale_y = _window_scale(window)
    logical_x = x / scale_x if scale_x else x
    logical_y = y / scale_y if scale_y else y
    parent_w, _ = _parent_logical_size(window)
    panel_w, _ = _panel_logical_size()
    hc._CONFIG['offsetX'] = int(round(logical_x - (parent_w - panel_w) * 0.5))
    hc._CONFIG['offsetY'] = int(round(logical_y))
    return (x, y)


def _window_pixel_position(window):
    try:
        pos = _pair(getattr(window, 'position', None))
        if pos is not None:
            scale_x, scale_y = _window_scale(window)
            return _clamp_pixels(window, pos[0] * scale_x, pos[1] * scale_y)
    except Exception:
        pass
    return _pixel_position_from_config(window)


def _move_window_pixels(window, x, y):
    x, y = _clamp_pixels(window, x, y)
    scale_x, scale_y = _window_scale(window)
    logical_x = x / scale_x if scale_x else x
    logical_y = y / scale_y if scale_y else y
    try:
        window.move(int(round(logical_x)), int(round(logical_y)),
                    xAnchor=PositionAnchor.LEFT,
                    yAnchor=PositionAnchor.TOP)
    except TypeError:
        window.move(int(round(logical_x)), int(round(logical_y)))
    return (x, y)


def _apply_saved_position():
    """Apply config only at creation or our own Ctrl edge."""
    if _drag_active:
        return
    window = _window()
    if window is None:
        return
    try:
        x, y = _pixel_position_from_config(window)
        _move_window_pixels(window, x, y)
    except Exception:
        hc._logger.exception('Failed to position High Caliber window')


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


def _cursor_on_panel(window, cursor_pos):
    if cursor_pos is None:
        return False
    x, y = _pixel_position_from_config(window)
    width, height = _panel_pixel_size(window)
    return (x - _EDGE_TOLERANCE <= cursor_pos[0] <= x + width + _EDGE_TOLERANCE and
            y - _EDGE_TOLERANCE <= cursor_pos[1] <= y + height + _EDGE_TOLERANCE)


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
        _apply_saved_position()
    hc._logger.info('High Caliber edit mode: %s', _editing)
    _push_edit_state()


def _start_drag(window, cursor_pos):
    global _drag_active, _drag_start_cursor, _drag_start_position, _drag_last_position
    if _drag_active or cursor_pos is None:
        return
    try:
        start_position = _window_pixel_position(window)
        _drag_start_cursor = cursor_pos
        _drag_start_position = start_position
        _drag_last_position = start_position
        _drag_active = True
        hc._logger.info('High Caliber drag started')
    except Exception:
        _drag_active = False
        _drag_start_cursor = None
        _drag_start_position = None
        _drag_last_position = None
        hc._logger.exception('High Caliber drag start failed')


def _move_drag(window, cursor_pos):
    global _drag_last_position
    if (not _drag_active or cursor_pos is None or
            _drag_start_cursor is None or _drag_start_position is None):
        return
    try:
        dx = cursor_pos[0] - _drag_start_cursor[0]
        dy = cursor_pos[1] - _drag_start_cursor[1]
        _drag_last_position = _move_window_pixels(
            window,
            _drag_start_position[0] + dx,
            _drag_start_position[1] + dy)
    except Exception:
        hc._logger.exception('High Caliber drag move failed')
        _finish_drag()


def _finish_drag():
    global _drag_active, _drag_start_cursor, _drag_start_position, _drag_last_position
    if not _drag_active:
        _drag_start_cursor = None
        _drag_start_position = None
        _drag_last_position = None
        return

    window = _window()
    final_position = _drag_last_position
    _drag_active = False
    _drag_start_cursor = None
    _drag_start_position = None
    _drag_last_position = None

    if window is None or final_position is None:
        return
    try:
        x, y = _config_from_pixel_position(window, final_position[0], final_position[1])
        _move_window_pixels(window, x, y)
        _save_config()
        hc._logger.info('High Caliber position saved: x=%s y=%s',
                        hc._CONFIG.get('offsetX'), hc._CONFIG.get('offsetY'))
    except Exception:
        hc._logger.exception('High Caliber drag end failed')


def _sample_input(mouse_move=False):
    """Observe Ctrl/LMB only. Never consumes or alters the game's event."""
    global _gesture_latched
    try:
        ctrl = _ctrl_down_now()
        _set_editing(ctrl)

        gesture = bool(ctrl and _lmb_down_now())
        window = _window()

        if gesture and not _gesture_latched:
            _gesture_latched = True
            if window is not None:
                cursor_pos = _cursor_pixels()
                if _cursor_on_panel(window, cursor_pos):
                    _start_drag(window, cursor_pos)
        elif not gesture and _gesture_latched:
            _gesture_latched = False
            _finish_drag()

        if mouse_move and gesture and _drag_active and window is not None:
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
    hc._logger.info('High Caliber MainGun-style pixel Ctrl-drag installed')
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
