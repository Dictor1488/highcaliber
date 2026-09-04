# -*- coding: utf-8 -*-
"""Ctrl-drag support and High Caliber shot-result compatibility fix."""

import json
import os

try:
    import InputHandler
    import Keys
except Exception:
    InputHandler = None
    Keys = None

from constants import VEHICLE_HIT_FLAGS
from frameworks.wulf import ViewModel
from gui.mods import mod_highcaliber as hc

_editing = False
_installed = False
_orig_model_init = None
_orig_model_initialize = None
_orig_view_push = None
_orig_process_shot_results = None


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


def _push_edit_payload():
    view = _view()
    if view is None:
        return
    try:
        raw = view.viewModel.getPayload()
        data = json.loads(raw or '{}')
        if not isinstance(data, dict):
            return
        data['dragEnabled'] = bool(hc._CONFIG.get('drag', True))
        data['editing'] = bool(_editing)
        updated = json.dumps(data, separators=(',', ':'), sort_keys=True)
        with view.viewModel.transaction() as model:
            model.setPayload(updated)
    except Exception:
        hc._logger.exception('Failed to push High Caliber edit state')


def _model_init(self, properties=1, commands=2):
    ViewModel.__init__(self, properties=properties, commands=2)


def _on_dragged(data=None, *args):
    if not _editing or not hc._CONFIG.get('drag', True):
        return
    try:
        dx = float(data.get('dx', 0) or 0)
        dy = float(data.get('dy', 0) or 0)
        final = bool(data.get('final', False))
        game_scale = max(0.01, float(data.get('gameScale', 1.0) or 1.0))
    except Exception:
        return

    hc._CONFIG['offsetX'] = int(round(hc._CONFIG.get('offsetX', 380) + dx / game_scale))
    hc._CONFIG['offsetY'] = int(round(hc._CONFIG.get('offsetY', 0) + dy / game_scale))

    try:
        ui_scale = max(0.5, min(2.0, float(hc._CONFIG.get('scale', 1.0) or 1.0)))
        surface_width = int(220 * game_scale * ui_scale + 0.999)
        surface_height = int(56 * game_scale * ui_scale + 0.999)
        hc._move_window(surface_width, surface_height, game_scale)
        hc._push_ui()
        _push_edit_payload()
    except Exception:
        pass

    if final:
        _save_config()


def _model_initialize(self):
    _orig_model_initialize(self)
    self.onDragged = self._addCommand('onDragged')
    self.onDragged += _on_dragged


def _view_push(self):
    _orig_view_push(self)
    _push_edit_payload()


def _is_ctrl(event):
    if event is None or Keys is None:
        return False
    try:
        key = event.key
    except Exception:
        return False
    for name in ('KEY_LCONTROL', 'KEY_RCONTROL', 'KEY_CONTROL'):
        value = getattr(Keys, name, None)
        if value is not None and key == value:
            return True
    return False


def _set_editing(value):
    global _editing
    value = bool(value and hc._CONFIG.get('drag', True))
    if _editing == value:
        return
    _editing = value
    _push_edit_payload()


def _on_key_down(event):
    if _is_ctrl(event):
        _set_editing(True)


def _on_key_up(event):
    if _is_ctrl(event):
        _set_editing(False)


def _fixed_process_shot_results(player, results):
    if hc._STATE.teamHit or not hc._CONFIG.get('enabled', True):
        return
    try:
        arena_vehicles = player.arena.vehicles
        player_vehicle_id = player.playerVehicleID
        player_team = player.team
        hit_mask = (VEHICLE_HIT_FLAGS.IS_ANY_DAMAGE_MASK |
                    VEHICLE_HIT_FLAGS.ATTACK_IS_DIRECT_PROJECTILE)
        dead_before_mask = getattr(VEHICLE_HIT_FLAGS, 'VEHICLE_WAS_DEAD_BEFORE_ATTACK', 0)

        for raw in results:
            vehicle_id = (raw >> 32) & 0xFFFFFFFF
            flags = raw & 0xFFFFFFFF
            if dead_before_mask and flags & dead_before_mask:
                continue
            if vehicle_id == player_vehicle_id:
                continue
            vehicle = arena_vehicles.get(vehicle_id)
            if not vehicle:
                continue
            if vehicle.get('team') != player_team:
                continue
            if not vehicle.get('isAlive', True):
                continue
            if flags & hit_mask:
                if hc._STATE.markTeamHit():
                    hc._push_ui()
                    _push_edit_payload()
                break
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
    hc.HighCaliberView.push = _view_push
    hc._process_shot_results = _fixed_process_shot_results

    if InputHandler is not None:
        try:
            InputHandler.g_instance.onKeyDown += _on_key_down
            InputHandler.g_instance.onKeyUp += _on_key_up
        except Exception:
            hc._logger.exception('Failed to install High Caliber Ctrl input')

    _installed = True


def _restore():
    global _installed, _editing
    if not _installed:
        return

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
    _installed = False


def init():
    _install()


def fini():
    _restore()


def onDisconnected():
    _set_editing(False)


def onAccountBecomeNonPlayer():
    _set_editing(False)
