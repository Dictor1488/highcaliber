# -*- coding: utf-8 -*-
"""High Caliber failure display rules.

The HUD must show Wasted only after the player actually damages an allied
vehicle. Player death and an impossible remaining-HP situation do not change
the HUD to Wasted.
"""

_installed = False


def install(damage_tracker):
    global _installed
    if _installed:
        return

    cls = damage_tracker.DamageTracker
    original_init = cls.__init__
    original_start = cls._startBattleImpl
    original_stop = cls.stop
    original_health = cls._onVehicleHealthChanged

    def _init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self._teamDamageFailed = False

    def _startBattleImpl(self):
        self._teamDamageFailed = False
        return original_start(self)

    def _stop(self):
        self._teamDamageFailed = False
        return original_stop(self)

    def _onVehicleHealthChanged(self, targetID, attackerID, damage):
        try:
            amount = int(damage or 0)
        except Exception:
            amount = 0

        if amount > 0:
            try:
                playerID = self._playerVehicleID
                isPlayer = playerID is not None and self._sameVehicle(attackerID, playerID)
                isOtherAlly = (self._isAllyVehicle(targetID) and
                               not self._sameVehicle(targetID, playerID))
                if isPlayer and isOtherAlly and not self._teamDamageFailed:
                    self._teamDamageFailed = True
            except Exception:
                pass

        original_health(self, targetID, attackerID, damage)

    def _isFailed(self):
        return bool(getattr(self, '_teamDamageFailed', False))

    cls.__init__ = _init
    cls._startBattleImpl = _startBattleImpl
    cls.stop = _stop
    cls._onVehicleHealthChanged = _onVehicleHealthChanged
    cls._isFailed = _isFailed
    _installed = True
