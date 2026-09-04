# -*- coding: utf-8 -*-
"""Ctrl-drag support for the standalone High Caliber indicator."""

import json
import os

import BigWorld

try:
    import InputHandler
except Exception:
    InputHandler = None

from frameworks.wulf import ViewModel
from gui.mods import mod_highcaliber as hc

_CTRL_KEYS = (29, 157)

_editing = False
_installed = False
_orig_model_init = None
_orig_model_initialize = None
_orig_view_push = None
_orig_process_shot_results = None
_ctrl_poll = None
_drag_base_x = None
_drag_base_y = None


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


def _push_edit_state():
    """Push only the Ctrl/edit bit. Do not rebuild the JSON HUD payload."""
    view = _view()
    if view is None:
        return
    try:
        with view.viewModel.transaction() as model:
            model.setEditing(bool(_editing))
    except Exception:
        hc._logger.exception('Failed to push High Caliber edit state')


def _model_init(self, properties=2, commands=2):
    # payload is property 0, editing is property 1.
    ViewModel.__init__(self, properties=2, commands=2)


def _model_get_editing(self):
    return self._getBool(1)


def _model_set_editing(self, value):
    self._setBool(1, bool(value))


def _on_dragged(data=None, *args):
    global _drag_base_x, _drag_base_y
    if not _editing or not hc._CONFIG.get('drag', True):
        return
    try:
        dx = float(data.get('dx', 0) or 0)
        dy = float(data.get('dy', 0) or 0)
        final = bool(data.get('final', False))
        start = bool(data.get('start', False))
        game_scale = max(0.01, float(data.get('gameScale', 1.0) or 1.0))
    except Exception:
        return

    if start:
        _drag_base_x = int(hc._CONFIG.get('offsetX', 380))
        _drag_base_y = int(hc._CONFIG.get('offsetY', 0))
        return

    # All visual motion happens entirely in GameFace JS. Python only commits
    # the final delta after mouseup, so there is zero per-frame Wulf movement.
    if not final:
        return

    if _drag_base_x is None or _drag_base_y is None:
        _drag_base_x = int(hc._CONFIG.get('offsetX', 380))
        _drag_base_y = int(hc._CONFIG.get('offsetY', 0))

    hc._CONFIG['offsetX'] = int(round(_drag_base_x + dx / game_scale))
    hc._CONFIG['offsetY'] = int(round(_drag_base_y + dy / game_scale))
    _save_config()
    hc._logger.info('High Caliber position saved: x=%s y=%s', hc._CONFIG.get('offsetX'), hc._CONFIG.get('offsetY'))
    _drag_base_x = None
    _drag_base_y = None
    try:
        hc._push_ui()
        _push_edit_state()
    except Exception:
        pass


def _model_initialize(self):
    _orig_model_initialize(self)
    self._addBoolProperty('editing', False)
    self.onDragged = self._addCommand('onDragged')
    self.onDragged += _on_dragged


def _view_push(self):
    _orig_view_push(self)
    _push_edit_state()


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
    global _editing, _drag_base_x, _drag_base_y
    value = bool(value and hc._CONFIG.get('drag', True) and hc._battle_ready_to_show())
    if _editing == value:
        return
    _editing = value
    if not _editing:
        _drag_base_x = None
        _drag_base_y = None
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
            # Backup only. InputHandler events are the primary path.
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
    global _orig_process_shot_results
    if _installed:
        return

    if 'drag' not in hc._CONFIG:
        hc._CONFIG['drag'] = True

    _orig_model_init = hc.HighCaliberModel.__init__
    _orig_model_initialize = hc.HighCaliberModel._initialize
    _orig_view_push = hc.HighCaliberView.push
    _orig_process_shot_results = hc._process_shot_results

    hc.HighCaliberModel.__init__ = _model_init
    hc.HighCaliberModel._initialize = _model_initialize
    hc.HighCaliberModel.getEditing = _model_get_editing
    hc.HighCaliberModel.setEditing = _model_set_editing
    hc.HighCaliberView.push = _view_push
    hc._process_shot_results = _fixed_process_shot_results

    if InputHandler is not None:
        try:
            InputHandler.g_instance.onKeyDown += _on_key_down
            InputHandler.g_instance.onKeyUp += _on_key_up
        except Exception:
            hc._logger.exception('Failed to install High Caliber Ctrl input')

    _schedule_ctrl_poll()
    hc._logger.info('High Caliber Ctrl-drag helper installed; keys=%r', _CTRL_KEYS)
    _installed = True


def _restore():
    global _installed, _editing, _drag_base_x, _drag_base_y
    if not _installed:
        return

    _stop_ctrl_poll()

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
        if _orig_process_shot_results is not None:
            hc._process_shot_results = _orig_process_shot_results
    except Exception:
        pass

    _editing = False
    _drag_base_x = None
    _drag_base_y = None
    _installed = False


def init():
    _install()


def fini():
    _restore()


def onDisconnected():
    _set_editing(False)


def onAccountBecomeNonPlayer():
    _set_editing(False)
