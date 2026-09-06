# -*- coding: utf-8 -*-
"""WoT 2.4 battle integration for INQ High Caliber.

High Caliber is hosted on WindowLayer.WINDOW (layer 7) from creation. The
native 150x40 window owns placement; GameFace only renders the local indicator.
The overlay is enabled only in standard random battles.
"""

import BigWorld
import GUI

from constants import ARENA_BONUS_TYPE
from frameworks.wulf import WindowFlags, WindowLayer, WindowStatus
from gui.battle_control.controllers.battle_field_ctrl import BattleFieldCtrl
from gui.impl.pub import WindowImpl
from gui.mods import mod_highcaliber as hc


_base_set_view_components = hc._orig_setViewComponents
_base_view_push = hc.HighCaliberView.push
_avatar_key_original = None
_avatar_key_wrapper = None
_key_blocked = False
_last_hidden = None
_last_window_position = None

_BASE_WIDTH = 150.0
_BASE_HEIGHT = 40.0


def _is_random_battle():
    try:
        arena = getattr(BigWorld.player(), 'arena', None)
        return arena is not None and getattr(arena, 'bonusType', None) == ARENA_BONUS_TYPE.REGULAR
    except Exception:
        return False


def _fallback_total_enemy_hp():
    try:
        player = BigWorld.player()
        arena = getattr(player, 'arena', None)
        vehicles = {} if arena is None else getattr(arena, 'vehicles', {})
        player_team = getattr(player, 'team', None)
        total = 0
        for data in vehicles.itervalues():
            try:
                if data.get('team') == player_team:
                    continue
                hp = data.get('maxHealth', 0) or 0
                if not hp:
                    vehicle_type = data.get('vehicleType')
                    hp = getattr(vehicle_type, 'maxHealth', 0) if vehicle_type is not None else 0
                total += int(hp or 0)
            except Exception:
                pass
        return total
    except Exception:
        return 0


def _destroy_listener():
    global _last_window_position
    listener = hc._listener
    if listener is None:
        return
    try:
        listener.destroy()
    except Exception:
        hc._logger.exception('Failed to destroy High Caliber battle listener')
    hc._listener = None
    _last_window_position = None


def _set_view_components(self, *args, **kwargs):
    result = _base_set_view_components(self, *args, **kwargs)
    try:
        _destroy_listener()
        hc._STATE.reset()
        _reset_overlay_state()

        if not _is_random_battle():
            hc._logger.info('High Caliber disabled for non-random battle')
            return result

        total = int(getattr(self, '_BattleFieldCtrl__totalEnemiesHealth', 0) or 0)
        if total <= 0:
            total = _fallback_total_enemy_hp()
        if total > 0:
            hc._STATE.setTotalEnemyHP(total)

        hc._listener = hc.HighCaliberBattleListener()
        if total > 0:
            hc._push_ui()
        else:
            hc._logger.warning(
                'High Caliber battle UI started without enemy HP; waiting for fallback data')
    except Exception:
        hc._logger.exception('Failed to start High Caliber battle UI')
    return result


BattleFieldCtrl.setViewComponents = _set_view_components
hc._set_view_components = _set_view_components


# -----------------------------------------------------------------------------
# Stable layer-7 host and placement
# -----------------------------------------------------------------------------


def _highcaliber_window_init(self, parent=None):
    WindowImpl.__init__(
        self,
        WindowFlags.WINDOW,
        content=hc.HighCaliberView(),
        layer=getattr(WindowLayer, 'WINDOW', WindowLayer.OVERLAY),
        name='INQHighCaliber',
        parent=parent
    )


hc.HighCaliberWindow.__init__ = _highcaliber_window_init


def _pair(value):
    if value is None:
        return None
    try:
        return float(value.x), float(value.y)
    except Exception:
        try:
            return float(value[0]), float(value[1])
        except Exception:
            return None


def _logical_size(window):
    try:
        size = _pair(getattr(getattr(window, 'parent', None), 'size', None))
        if size is not None and size[0] > 0 and size[1] > 0:
            return size
    except Exception:
        pass
    try:
        w, h = GUI.screenResolution()[:2]
        if w > 0 and h > 0:
            return float(w), float(h)
    except Exception:
        pass
    return 1920.0, 1080.0


def _config_scale():
    try:
        scale = float(hc._CONFIG.get('scale', 1.0) or 1.0)
    except Exception:
        scale = 1.0
    return max(0.5, min(2.0, scale))


def _position_window(window=None):
    global _last_window_position
    try:
        if window is None:
            listener = hc._listener
            window = None if listener is None else listener.window
        if window is None or getattr(window, 'content', None) is None:
            return
        parent_w, parent_h = _logical_size(window)
        scale = _config_scale()
        panel_w = _BASE_WIDTH * scale
        panel_h = _BASE_HEIGHT * scale
        try:
            ox = float(hc._CONFIG.get('offsetX', 380) or 0)
        except Exception:
            ox = 380.0
        try:
            oy = float(hc._CONFIG.get('offsetY', 0) or 0)
        except Exception:
            oy = 0.0
        x = (parent_w - panel_w) * 0.5 + ox
        y = oy
        x = max(0.0, min(x, max(0.0, parent_w - panel_w)))
        y = max(0.0, min(y, max(0.0, parent_h - panel_h)))
        ix = int(round(x))
        iy = int(round(y))
        position_key = (id(window), ix, iy)
        if _last_window_position == position_key:
            return
        window.move(ix, iy)
        _last_window_position = position_key
    except Exception:
        if _battle_active():
            hc._logger.exception('Failed to position High Caliber window')


def _highcaliber_window_ready(self):
    self.show(focus=False)
    _position_window(self)


hc.HighCaliberWindow._onReady = _highcaliber_window_ready


def _battle_active():
    return _is_random_battle()


def _overlay_keys_down():
    try:
        import Keys
        for code in (getattr(Keys, 'KEY_TAB', None),
                     getattr(Keys, 'KEY_N', None),
                     getattr(Keys, 'KEY_B', None)):
            if code is not None and BigWorld.isKeyDown(code):
                return True
    except Exception:
        pass
    return False


def _listener_view():
    try:
        listener = hc._listener
        if listener is None:
            return None
        view = listener.view
        if view is None or getattr(view, 'viewModel', None) is None:
            return None
        return view
    except Exception:
        return None


def _apply_visibility(reason='', force=False):
    global _last_hidden
    view = _listener_view()
    if view is None:
        return

    hidden = bool(_key_blocked)
    if not force and hidden == _last_hidden:
        return

    try:
        if hidden:
            view.hide()
        else:
            _position_window()
            _base_view_push(view)
        _last_hidden = hidden
        hc._logger.info('High Caliber overlay visibility: hidden=%s reason=%s',
                        hidden, reason)
    except Exception:
        if _battle_active():
            hc._logger.exception('Failed to update High Caliber overlay visibility')


def _guarded_view_push(self):
    if not _battle_active():
        try:
            if getattr(self, 'viewModel', None) is not None:
                self.hide()
        except Exception:
            pass
        return
    if _key_blocked:
        try:
            if getattr(self, 'viewModel', None) is not None:
                self.hide()
        except Exception:
            pass
        return
    if getattr(self, 'viewModel', None) is None:
        return
    _position_window()
    return _base_view_push(self)


hc.HighCaliberView.push = _guarded_view_push


def _sample_overlay_keys():
    global _key_blocked
    if not _battle_active():
        if _key_blocked:
            _key_blocked = False
        return

    blocked = _overlay_keys_down()
    if blocked == _key_blocked:
        return
    _key_blocked = blocked
    _apply_visibility('TAB/N/B-down=%s' % blocked)


def _install_key_hook():
    global _avatar_key_original, _avatar_key_wrapper
    if _avatar_key_wrapper is not None:
        return
    try:
        from AvatarInputHandler import AvatarInputHandler
        original = AvatarInputHandler.handleKeyEvent
        original = getattr(original, '_inq_hc_battle_original', original)

        def _key_wrapper(self, *args, **kwargs):
            result = original(self, *args, **kwargs)
            try:
                _sample_overlay_keys()
            except Exception:
                hc._logger.exception('High Caliber overlay key sample failed')
            return result

        _key_wrapper._inq_hc_battle_original = original
        AvatarInputHandler.handleKeyEvent = _key_wrapper
        _avatar_key_original = original
        _avatar_key_wrapper = _key_wrapper
        hc._logger.info('High Caliber TAB/N/B hold overlay hook installed')
    except Exception:
        hc._logger.exception('Failed to install High Caliber overlay key hook')


def _reset_overlay_state():
    global _key_blocked, _last_hidden, _last_window_position
    _key_blocked = False
    _last_hidden = None
    _last_window_position = None


def init():
    _install_key_hook()
    hc._logger.info(
        'High Caliber WoT 2.4 battle integration installed (random only, WINDOW layer 7, native placement)')


def fini():
    global _avatar_key_original, _avatar_key_wrapper
    _reset_overlay_state()
    try:
        from AvatarInputHandler import AvatarInputHandler
        if (_avatar_key_wrapper is not None and
                AvatarInputHandler.handleKeyEvent is _avatar_key_wrapper):
            AvatarInputHandler.handleKeyEvent = _avatar_key_original
    except Exception:
        pass
    _avatar_key_original = None
    _avatar_key_wrapper = None


def onDisconnected():
    _reset_overlay_state()


def onAccountBecomeNonPlayer():
    _reset_overlay_state()
