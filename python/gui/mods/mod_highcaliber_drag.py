# -*- coding: utf-8 -*-
"""Ctrl-drag support for the standalone High Caliber indicator.

Drag follows the working MARKS GameFace pattern:
- GameFace only reports drag start/end.
- Python reads GUI.mcursor() every frame while LMB is held.
- The small Wulf window itself is moved directly.
- Window/parent resize events reflow the panel after display mode changes.
"""

import json
import os

import BigWorld
import GUI

try:
    import InputHandler
except Exception:
    InputHandler = None

from frameworks.wulf import ViewModel, PositionAnchor
from gui.mods import mod_highcaliber as hc

_CTRL_KEYS = (29, 157)
_BASE_WIDTH = 150.0
_BASE_HEIGHT = 40.0

_editing = False
_installed = False
_orig_model_init = None
_orig_model_initialize = None
_orig_view_push = None
_orig_window_ready = None
_orig_process_shot_results = None
_ctrl_poll = None
_drag_callback = None
_drag_cursor_start = None
_drag_window_start = None
_drag_last_xy = None
_resize_callback = None
_bound_window = None
_bound_parent = None


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
    """Physical pixels per logical Wulf unit, same model used by MARKS."""
    try:
        physical = _pair(GUI.screenResolution())
        logical = _pair(getattr(getattr(window, 'parent', None), 'size', None))
        if physical is None or logical is None or logical[0] <= 0 or logical[1] <= 0:
            return 1.0
        scale = ((physical[0] / logical[0]) + (physical[1] / logical[1])) * 0.5
        return max(0.5, min(4.0, float(scale)))
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
        physical = GUI.screenResolution()
        scale = _interface_scale(window)
        return (float(physical[0]) / scale, float(physical[1]) / scale)
    except Exception:
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
    if _drag_cursor_start is not None:
        return
    window = _window()
    if window is None:
        return
    try:
        x, y = _position_from_config(window)
        x, y = _move_window(window, x, y)
        old_x = int(hc._CONFIG.get('offsetX', 380))
        old_y = int(hc._CONFIG.get('offsetY', 0))
        _config_from_position(window, x, y)
        if old_x != hc._CONFIG.get('offsetX') or old_y != hc._CONFIG.get('offsetY'):
            _save_config()
    except Exception:
        hc._logger.exception('Failed to position High Caliber window')


def _cursor_position_px():
    resolution = GUI.screenResolution()
    width = float(resolution[0])
    height = float(resolution[1])
    pos = GUI.mcursor().position
    return ((pos.x * 0.5 + 0.5) * width,
            (0.5 - pos.y * 0.5) * height)


def _left_mouse_down():
    try:
        import Keys
        return bool(BigWorld.isKeyDown(Keys.KEY_LEFTMOUSE))
    except Exception:
        return True


def _drag_start():
    global _drag_cursor_start, _drag_window_start, _drag_last_xy
    if not _editing or not hc._CONFIG.get('drag', True):
        return
    window = _window()
    if window is None or _drag_cursor_start is not None:
        return
    try:
        start_x, start_y = _position_from_config(window)
        start_x, start_y = _move_window(window, start_x, start_y)
        _drag_cursor_start = _cursor_position_px()
        _drag_window_start = (start_x, start_y)
        _drag_last_xy = (start_x, start_y)
        _drag_tick()
    except Exception:
        _drag_cursor_start = None
        _drag_window_start = None
        _drag_last_xy = None
        hc._logger.exception('High Caliber drag start failed')


def _drag_tick():
    global _drag_callback, _drag_last_xy
    _drag_callback = None
    if _drag_cursor_start is None or _drag_window_start is None:
        return
    if not _left_mouse_down():
        _drag_end()
        return
    window = _window()
    if window is None:
        _drag_end()
        return
    try:
        cursor_x, cursor_y = _cursor_position_px()
        scale = _interface_scale(window)
        x = _drag_window_start[0] + (cursor_x - _drag_cursor_start[0]) / scale
        y = _drag_window_start[1] + (cursor_y - _drag_cursor_start[1]) / scale
        _drag_last_xy = _move_window(window, x, y)
    except Exception:
        hc._logger.exception('High Caliber drag tick failed')
        _drag_end()
        return
    try:
        _drag_callback = BigWorld.callback(0.0, _drag_tick)
    except Exception:
        _drag_callback = None


def _drag_end():
    global _drag_callback, _drag_cursor_start, _drag_window_start, _drag_last_xy
    if _drag_callback is not None:
        try:
            BigWorld.cancelCallback(_drag_callback)
        except Exception:
            pass
        _drag_callback = None
    if _drag_cursor_start is None:
        return

    window = _window()
    final_xy = _drag_last_xy
    _drag_cursor_start = None
    _drag_window_start = None
    _drag_last_xy = None
    if window is None or final_xy is None:
        return
    try:
        x, y = _config_from_position(window, final_xy[0], final_xy[1])
        _move_window(window, x, y)
        _save_config()
        hc._logger.info('High Caliber position saved: x=%s y=%s',
                        hc._CONFIG.get('offsetX'), hc._CONFIG.get('offsetY'))
        hc._push_ui()
    except Exception:
        hc._logger.exception('High Caliber drag end failed')


def _push_edit_state():
    view = _view()
    if view is None:
        return
    try:
        with view.viewModel.transaction() as model:
            model.setEditing(bool(_editing))
    except Exception:
        hc._logger.exception('Failed to push High Caliber edit state')


def _reflow_after_resize():
    global _resize_callback
    _resize_callback = None
    try:
        _apply_saved_position()
        hc._push_ui()
        _push_edit_state()
        hc._logger.info('High Caliber reflowed after display resize')
    except Exception:
        hc._logger.exception('Failed to reflow High Caliber after display resize')


def _schedule_resize_reflow(*args):
    """Debounce Wulf resize storms caused by windowed/fullscreen switches."""
    global _resize_callback
    _drag_end()
    if _resize_callback is not None:
        try:
            BigWorld.cancelCallback(_resize_callback)
        except Exception:
            pass
    try:
        # Let the main Wulf window finish applying its new logical size first.
        _resize_callback = BigWorld.callback(0.15, _reflow_after_resize)
    except Exception:
        _resize_callback = None
        _reflow_after_resize()


def _detach_resize_hooks():
    global _bound_window, _bound_parent
    window = _bound_window
    parent = _bound_parent
    _bound_window = None
    _bound_parent = None
    if window is not None:
        try:
            window.onSizeChanged -= _schedule_resize_reflow
        except Exception:
            pass
    if parent is not None:
        try:
            parent.onSizeChanged -= _schedule_resize_reflow
        except Exception:
            pass


def _attach_resize_hooks(window):
    global _bound_window, _bound_parent
    if window is None:
        return
    if _bound_window is window:
        return
    _detach_resize_hooks()
    _bound_window = window
    try:
        window.onSizeChanged += _schedule_resize_reflow
    except Exception:
        pass
    try:
        parent = getattr(window, 'parent', None)
        if parent is not None:
            parent.onSizeChanged += _schedule_resize_reflow
            _bound_parent = parent
    except Exception:
        _bound_parent = None


def _model_init(self, properties=2, commands=2):
    ViewModel.__init__(self, properties=2, commands=2)


def _model_get_editing(self):
    return self._getBool(1)


def _model_set_editing(self, value):
    self._setBool(1, bool(value))


def _on_dragged(data=None, *args):
    if not isinstance(data, dict):
        return
    phase = data.get('phase')
    if phase == 'start':
        _drag_start()
    elif phase == 'end':
        _drag_end()


def _model_initialize(self):
    _orig_model_initialize(self)
    self._addBoolProperty('editing', False)
    self.onDragged = self._addCommand('onDragged')
    self.onDragged += _on_dragged


def _view_push(self):
    _orig_view_push(self)
    _push_edit_state()
    _apply_saved_position()


def _window_ready(self):
    _orig_window_ready(self)
    _attach_resize_hooks(self)
    try:
        BigWorld.callback(0.0, _apply_saved_position)
    except Exception:
        _apply_saved_position()


def _event_key(event):
    try:
        return int(event.key)
    except Exception:
        return None


def _is_ctrl_event(event):
    key = _event_key(event)
    if key in _CTRL_KEYS:
        return True
    for name in ('isCtrlDown', 'isControlDown'):
        try:
            value = getattr(event, name, None)
            if callable(value) and value():
                return True
            if value is True:
                return True
        except Exception:
            pass
    return False


def _ctrl_down_now():
    for key in _CTRL_KEYS:
        try:
            if BigWorld.isKeyDown(key):
                return True
        except Exception:
            pass
    return False


def _set_editing(value):
    global _editing
    value = bool(value and hc._CONFIG.get('drag', True) and hc._battle_ready_to_show())
    if _editing == value:
        return
    if not value:
        _drag_end()
    _editing = value
    hc._logger.info('High Caliber edit mode: %s', _editing)
    _push_edit_state()


def _on_key_down(event):
    if _is_ctrl_event(event):
        _set_editing(True)


def _on_key_up(event):
    key = _event_key(event)
    if key in _CTRL_KEYS:
        _set_editing(_ctrl_down_now())


def _ctrl_poll_tick():
    global _ctrl_poll
    _ctrl_poll = None
    try:
        _set_editing(_ctrl_down_now())
    except Exception:
        pass
    _schedule_ctrl_poll()


def _schedule_ctrl_poll():
    global _ctrl_poll
    if _ctrl_poll is None:
        try:
            _ctrl_poll = BigWorld.callback(0.05, _ctrl_poll_tick)
        except Exception:
            _ctrl_poll = None


def _stop_ctrl_poll():
    global _ctrl_poll
    if _ctrl_poll is not None:
        try:
            BigWorld.cancelCallback(_ctrl_poll)
        except Exception:
            pass
    _ctrl_poll = None


def _fixed_process_shot_results(player, results):
    try:
        return _orig_process_shot_results(player, results)
    except Exception:
        hc._logger.exception('Failed to process friendly shot result')


def _install():
    global _installed
    global _orig_model_init, _orig_model_initialize, _orig_view_push
    global _orig_window_ready, _orig_process_shot_results
    if _installed:
        return

    if 'drag' not in hc._CONFIG:
        hc._CONFIG['drag'] = True

    _orig_model_init = hc.HighCaliberModel.__init__
    _orig_model_initialize = hc.HighCaliberModel._initialize
    _orig_view_push = hc.HighCaliberView.push
    _orig_window_ready = hc.HighCaliberWindow._onReady
    _orig_process_shot_results = hc._process_shot_results

    hc.HighCaliberModel.__init__ = _model_init
    hc.HighCaliberModel._initialize = _model_initialize
    hc.HighCaliberModel.getEditing = _model_get_editing
    hc.HighCaliberModel.setEditing = _model_set_editing
    hc.HighCaliberView.push = _view_push
    hc.HighCaliberWindow._onReady = _window_ready
    hc._process_shot_results = _fixed_process_shot_results

    if InputHandler is not None:
        try:
            InputHandler.g_instance.onKeyDown += _on_key_down
            InputHandler.g_instance.onKeyUp += _on_key_up
        except Exception:
            hc._logger.exception('Failed to install High Caliber Ctrl input')

    _schedule_ctrl_poll()
    hc._logger.info('High Caliber MARKS-style Ctrl-drag installed; keys=%r', _CTRL_KEYS)
    _installed = True


def _restore():
    global _installed, _editing, _resize_callback
    if not _installed:
        return

    _drag_end()
    _stop_ctrl_poll()
    _detach_resize_hooks()
    if _resize_callback is not None:
        try:
            BigWorld.cancelCallback(_resize_callback)
        except Exception:
            pass
        _resize_callback = None

    if InputHandler is not None:
        try:
            InputHandler.g_instance.onKeyDown -= _on_key_down
            InputHandler.g_instance.onKeyUp -= _on_key_up
        except Exception:
            pass

    try:
        if _orig_model_init is not None:
            hc.HighCaliberModel.__init__ = _orig_model_init
        if _orig_model_initialize is not None:
            hc.HighCaliberModel._initialize = _orig_model_initialize
        if _orig_view_push is not None:
            hc.HighCaliberView.push = _orig_view_push
        if _orig_window_ready is not None:
            hc.HighCaliberWindow._onReady = _orig_window_ready
        if _orig_process_shot_results is not None:
            hc._process_shot_results = _orig_process_shot_results
    except Exception:
        pass

    _editing = False
    _installed = False


def init():
    _install()


def fini():
    _restore()


def onDisconnected():
    _set_editing(False)


def onAccountBecomeNonPlayer():
    _set_editing(False)
