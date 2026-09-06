# -*- coding: utf-8 -*-
"""WoT 2.4 battle integration for INQ High Caliber.

The High Caliber GameFace surface is a passive WindowLayer.VIEW surface owned
by the battle main window. The 150x40 indicator is positioned inside that
surface by JS; the Wulf window itself is never resized or dragged.
"""

import BigWorld

from gui.battle_control.controllers.battle_field_ctrl import BattleFieldCtrl
from gui.mods import mod_highcaliber as hc


_base_set_view_components = hc._orig_setViewComponents
_base_view_push = hc.HighCaliberView.push
_avatar_key_original = None
_avatar_key_wrapper = None
_key_blocked = False
_last_hidden = None


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
    listener = hc._listener
    if listener is None:
        return
    try:
        listener.destroy()
    except Exception:
        hc._logger.exception('Failed to destroy High Caliber battle listener')
    hc._listener = None


def _set_view_components(self, *args, **kwargs):
    result = _base_set_view_components(self, *args, **kwargs)
    try:
        _destroy_listener()
        hc._STATE.reset()
        _reset_overlay_state()

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


def _battle_active():
    try:
        return getattr(BigWorld.player(), 'arena', None) is not None
    except Exception:
        return False


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
            _base_view_push(view)
        _last_hidden = hidden
        hc._logger.info('High Caliber overlay visibility: hidden=%s reason=%s',
                        hidden, reason)
    except Exception:
        # A view may be destroyed in the same frame that an input event arrives.
        # Treat that as normal lifecycle churn, not an actionable mod error.
        if _battle_active():
            hc._logger.exception('Failed to update High Caliber overlay visibility')


def _guarded_view_push(self):
    if _key_blocked:
        try:
            if getattr(self, 'viewModel', None) is not None:
                self.hide()
        except Exception:
            pass
        return
    if getattr(self, 'viewModel', None) is None:
        return
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
    global _key_blocked, _last_hidden
    _key_blocked = False
    _last_hidden = None


def init():
    _install_key_hook()
    hc._logger.info(
        'High Caliber WoT 2.4 battle integration installed (passive VIEW host, no global Wulf hooks)')


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
