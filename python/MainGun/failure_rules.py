# -*- coding: utf-8 -*-
"""High Caliber failure display rules.

The HUD must show Wasted as soon as the player lands a direct shell hit on an
allied vehicle. Player death and an impossible remaining-HP situation do not
change the HUD to Wasted.
"""

_installed = False
_vehicle_hook_installed = False


def install(damage_tracker):
    global _installed, _vehicle_hook_installed
    if _installed:
        return

    cls = damage_tracker.DamageTracker
    original_init = cls.__init__
    original_start = cls._startBattleImpl
    original_stop = cls.stop

    def _init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self._teamDamageFailed = False

    def _startBattleImpl(self):
        self._teamDamageFailed = False
        return original_start(self)

    def _stop(self):
        self._teamDamageFailed = False
        return original_stop(self)

    def _isFailed(self):
        return bool(getattr(self, '_teamDamageFailed', False))

    cls.__init__ = _init
    cls._startBattleImpl = _startBattleImpl
    cls.stop = _stop
    cls._isFailed = _isFailed

    # Friendly fire in Random battles normally does not reduce allied HP, so
    # arena.onVehicleHealthChanged is not a reliable signal. Hook the vehicle
    # shell-impact callback instead: it contains both the target vehicle
    # (self.id) and attackerID even when the hit deals 0 HP damage.
    try:
        import Vehicle

        vehicle_cls = Vehicle.Vehicle
        original_show_damage_from_shot = vehicle_cls.showDamageFromShot

        def _showDamageFromShot(vehicle, *args, **kwargs):
            try:
                attackerID = args[0] if args else kwargs.get('attackerID')
                tracker = damage_tracker.g_tracker
                if tracker is not None and getattr(tracker, '_started', False):
                    playerID = tracker._playerVehicleID
                    targetID = getattr(vehicle, 'id', None)
                    isPlayerShot = (playerID is not None and
                                    tracker._sameVehicle(attackerID, playerID))
                    isOtherAlly = (targetID is not None and
                                   not tracker._sameVehicle(targetID, playerID) and
                                   tracker._isAllyVehicle(targetID))
                    if isPlayerShot and isOtherAlly and not tracker._teamDamageFailed:
                        tracker._teamDamageFailed = True
                        tracker._invalidate()
            except Exception:
                pass

            return original_show_damage_from_shot(vehicle, *args, **kwargs)

        vehicle_cls.showDamageFromShot = _showDamageFromShot
        _vehicle_hook_installed = True
    except Exception:
        # Keep the mod functional even if WG changes the Vehicle class API.
        _vehicle_hook_installed = False

    _installed = True
