# -*- coding: utf-8 -*-
"""WoT 2.4 battle integration for INQ High Caliber.

This module owns the battle-shell specific pieces:
- WoT 2.4 BattleFieldCtrl lifecycle compatibility;
- the intentional WINDOW/layer-7 host;
- clean suppression while WG battle overlays are open.

TAB/N/B are treated as hold-style battle overlays: High Caliber is hidden for
exactly as long as one of those keys is physically down. Persistent Wulf
windows are tracked independently until their destroy(). No cursor polling,
no timers and no toggle auto-close state are used.
"""

import BigWorld

from frameworks.wulf import WindowFlags, WindowLayer
from gui.battle_control.controllers.battle_field_ctrl import BattleFieldCtrl
from gui.impl.pub import WindowImpl
from gui.mods import mod_highcaliber as hc


# -----------------------------------------------------------------------------
# Battle lifecycle (WoT 2.4)
# -----------------------------------------------------------------------------

_base_set_view_components = hc._orig_setViewComponents


def _fallback_total_enemy_hp():
    """Best-effort fallback when BattleFieldCtrl private total is unavailable."""
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


def _set_view_components(self, *args, **kwargs):
    """Start a fresh High Caliber battle UI without obsolete listener APIs."""
    result = _base_set_view_components(self, *args, **kwargs)
    try:
        if hc._listener is not None:
            try:
                hc._listener.destroy()
            except Exception:
                pass
            hc._listener = None

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


# -----------------------------------------------------------------------------
# Intentional layer 7
# -----------------------------------------------------------------------------

_base_window_init = hc.HighCaliberWindow.__init__


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


# -----------------------------------------------------------------------------
# Overlay visibility
# -----------------------------------------------------------------------------

_blocking_windows = {}
_key_blocked = False
_last_hidden = None

_base_view_push = hc.HighCaliberView.push
_base_wulf_load = WindowImpl.load
_base_wulf_destroy = WindowImpl.destroy

_avatar_key_original = None
_avatar_key_wrapper = None

# Narrow names only. Passive mod windows on layer 7 must not hide High Caliber.
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


def _battle_active():
    try:
        return getattr(BigWorld.player(), 'arena', None) is not None
    except Exception:
        return False


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
        try:
            return window.__class__.__name__ == 'HighCaliberWindow'
        except Exception:
            return False


def _is_blocker(window):
    if not _battle_active() or _is_highcaliber_window(window):
        return False
    text = _window_text(window)
    for token in _BLOCKER_TOKENS:
        if token in text:
            return True
    return False


def _overlay_keys_down():
    """Return True while TAB, N or B is physically held."""
    try:
        import Keys
        for code in (
                getattr(Keys, 'KEY_TAB', None),
                getattr(Keys, 'KEY_N', None),
                getattr(Keys, 'KEY_B', None)):
            if code is None:
                continue
            try:
                if BigWorld.isKeyDown(code):
                    return True
            except Exception:
                pass
    except Exception:
        pass
    return False


def _suppressed():
    return bool(_blocking_windows or _key_blocked)


def _listener_parts():
    try:
        listener = hc._listener
        if listener is None:
            return None, None
        return listener.window, listener.view
    except Exception:
        return None, None


def _apply_visibility(reason='', force=False):
    """Hide/show the Wulf window itself and avoid redundant visibility churn."""
    global _last_hidden

    window, view = _listener_parts()
    if window is None or view is None:
        return

    hidden = _suppressed()
    if not force and hidden == _last_hidden:
        return

    try:
        if hidden:
            try:
                view.hide()
            except Exception:
                pass
            try:
                window.hide()
            except Exception:
                pass
        else:
            try:
                window.show(focus=False)
            except Exception:
                pass
            _base_view_push(view)

        _last_hidden = hidden
        hc._logger.info(
            'High Caliber overlay visibility: hidden=%s reason=%s',
            hidden, reason)
    except Exception:
        hc._logger.exception('Failed to update High Caliber overlay visibility')


def _guarded_view_push(self):
    """Damage/state updates must never resurrect the panel under a WG overlay."""
    if _suppressed():
        try:
            self.hide()
        except Exception:
            pass
        return
    return _base_view_push(self)


hc.HighCaliberView.push = _guarded_view_push


def _wulf_load(self, *args, **kwargs):
    result = _base_wulf_load(self, *args, **kwargs)
    try:
        if _is_blocker(self):
            label = _window_text(self)
            _blocking_windows[id(self)] = label
            _apply_visibility('wulf-open:' + label)
        elif _is_highcaliber_window(self):
            _apply_visibility('highcaliber-load', force=True)
    except Exception:
        hc._logger.exception('High Caliber Wulf overlay load hook failed')
    return result


def _wulf_destroy(self, *args, **kwargs):
    key = id(self)
    was_blocker = key in _blocking_windows
    try:
        return _base_wulf_destroy(self, *args, **kwargs)
    finally:
        if was_blocker:
            try:
                label = _blocking_windows.pop(key, '')
                _apply_visibility('wulf-close:' + label)
            except Exception:
                hc._logger.exception('High Caliber Wulf overlay destroy hook failed')


WindowImpl.load = _wulf_load
WindowImpl.destroy = _wulf_destroy


def _sample_overlay_keys():
    global _key_blocked

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
    _blocking_windows.clear()
    _key_blocked = False
    _last_hidden = None


def init():
    _install_key_hook()
    hc._logger.info(
        'High Caliber WoT 2.4 battle integration installed (WINDOW layer 7, clean overlay suppression)')


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
