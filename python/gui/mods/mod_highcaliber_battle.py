# -*- coding: utf-8 -*-
"""WoT 2.4 battle lifecycle fix for INQ High Caliber.

The current client no longer exposes BattleFieldCtrl.addBattleFieldListener().
Use BattleFieldCtrl.setViewComponents only as a battle-start hook and as the
source of the already calculated total enemy team HP. The actual GameFace view
is created by mod_highcaliber's retrying battle-ready loader.
"""

import BigWorld

from gui.battle_control.controllers.battle_field_ctrl import BattleFieldCtrl
from gui.mods import mod_highcaliber as hc

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

        total = int(getattr(self, '_BattleFieldCtrl__totalEnemiesHealth', 0) or 0)
        if total <= 0:
            total = _fallback_total_enemy_hp()

        if total > 0:
            hc._STATE.setTotalEnemyHP(total)

        # Important: create the UI manager regardless of whether HP was obtained
        # immediately. Its own loader waits until the real battle UI is ready.
        hc._listener = hc.HighCaliberBattleListener()

        if total > 0:
            hc._push_ui()
            hc._logger.info('High Caliber battle UI started; totalEnemyHP=%s required=%s',
                            hc._STATE.totalEnemyHP, hc._STATE.requiredDamage)
        else:
            hc._logger.warning('High Caliber battle UI started without enemy HP; waiting for fallback data')
    except Exception:
        hc._logger.exception('Failed to start High Caliber battle UI')
    return result


# mod_highcaliber.py installs an older wrapper first; replace it with the 2.4-safe
# one after import. This module name sorts after mod_highcaliber.py and before the
# drag helper, so all later helpers see the corrected battle hook.
BattleFieldCtrl.setViewComponents = _set_view_components
hc._set_view_components = _set_view_components


def init():
    hc._logger.info('High Caliber WoT 2.4 battle lifecycle fix installed')


def fini():
    pass
