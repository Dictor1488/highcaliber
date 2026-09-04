# -*- coding: utf-8 -*-
"""Standalone High Caliber battle progress indicator for World of Tanks.

Core award logic is recovered from rajcel.inBattleStatistics:
- required damage = ceil(total enemy team HP / 5)
- player damage against enemies reduces the remaining amount
- a direct hit/damage hit on a living ally marks the award as wasted

UI follows the same passive GameFace/Wulf pattern used by Dictor1488/HpT.
"""

import json
import logging
import os

import BigWorld
import GUI

from Avatar import PlayerAvatar
from BattleFeedbackCommon import BATTLE_EVENT_TYPE
from constants import VEHICLE_HIT_FLAGS
from frameworks.wulf import ViewModel, ViewSettings, ViewFlags, WindowFlags, WindowLayer, WindowStatus
from gui.battle_control.controllers import feedback_events
from gui.battle_control.controllers.battle_field_ctrl import BattleFieldCtrl, IBattleFieldListener
from gui.impl.pub import ViewImpl, WindowImpl
from helpers import dependency, getClientLanguage
from skeletons.gui.impl import IGuiLoader

try:
    from openwg_gameface import ModDynAccessor
    _OPENWG_OK = True
except Exception:
    ModDynAccessor = None
    _OPENWG_OK = False

MOD_ID = 'me.inq.highcaliber'
MOD_VERSION = '0.1.0'
RES_MAP_ITEM_ID = 'mods/highcaliber/HighCaliberBattle/layoutID'

_logger = logging.getLogger('INQHighCaliber')

_CONFIG_DIR = os.path.join('mods', 'configs', 'highcaliber')
_CONFIG_PATH = os.path.join(_CONFIG_DIR, 'settings.json')
_DEFAULT_CONFIG = {
    'enabled': True,
    'drag': True,
    'offsetX': 380,
    'offsetY': 0,
    'scale': 1.0,
    'showDoneText': True,
    'showWastedText': True,
    'colorProgress': '#F8F400',
    'colorDone': '#60FF00',
    'colorWasted': '#FE0E00'
}

_LOCALIZATION = {
    'en': ('Done!', 'Wasted!'),
    'ru': (u'Готово!', u'Потеряно!'),
    'uk': (u'Готово!', u'Втрачено!'),
    'ua': (u'Готово!', u'Втрачено!'),
    'de': ('Geschafft!', 'Verwirkt!'),
    'pl': (u'Gotowe!', u'Utracone!'),
    'cs': (u'Hotovo!', u'Ztraceno!'),
    'sk': (u'Hotovo!', u'Stratené!'),
    'fr': (u'Fait !', u'Perdu !'),
    'es': (u'¡Hecho!', u'¡Perdido!'),
    'it': ('Fatto!', 'Perso!'),
    'pt': ('Feito!', 'Perdido!'),
    'pt_br': ('Feito!', 'Perdido!'),
    'tr': (u'Tamam!', u'Kaybedildi!'),
    'hu': (u'Kész!', u'Elveszett!'),
    'ro': ('Gata!', 'Pierdut!'),
    'bg': (u'Готово!', u'Загубено!'),
    'sr': (u'Готово!', u'Изгубљено!'),
    'hr': ('Gotovo!', 'Izgubljeno!'),
    'sl': ('Končano!', 'Izgubljeno!'),
    'nl': ('Klaar!', 'Verloren!'),
    'sv': ('Klart!', 'Förlorat!'),
    'no': ('Ferdig!', 'Tapt!'),
    'da': ('Færdig!', 'Tabt!'),
    'fi': ('Valmis!', 'Menetetty!'),
    'el': (u'Έτοιμο!', u'Χάθηκε!'),
    'et': ('Valmis!', 'Kaotatud!'),
    'lv': ('Gatavs!', 'Zaudēts!'),
    'lt': ('Baigta!', 'Prarasta!'),
    'zh_cn': (u'完成!', u'已失去!'),
    'zh_tw': (u'完成!', u'已失去!'),
    'ja': (u'完了!', u'失敗!'),
    'ko': (u'완료!', u'실패!'),
    'th': (u'สำเร็จ!', u'พลาด!'),
    'vi': (u'Xong!', u'Mất!')
}


def _load_config():
    data = dict(_DEFAULT_CONFIG)
    try:
        if not os.path.isdir(_CONFIG_DIR):
            os.makedirs(_CONFIG_DIR)
        if os.path.isfile(_CONFIG_PATH):
            with open(_CONFIG_PATH, 'r') as stream:
                loaded = json.load(stream)
            if isinstance(loaded, dict):
                data.update(loaded)
        else:
            with open(_CONFIG_PATH, 'w') as stream:
                json.dump(data, stream, indent=2, sort_keys=True)
    except Exception:
        _logger.exception('Failed to load High Caliber config')
    return data


_CONFIG = _load_config()


def _safe_float(value, fallback):
    try:
        return float(value)
    except Exception:
        return fallback


def _client_language():
    try:
        language = getClientLanguage() or 'en'
    except Exception:
        language = 'en'
    try:
        language = language.lower().replace('-', '_')
    except Exception:
        language = 'en'
    if language in _LOCALIZATION:
        return language
    short = language.split('_', 1)[0]
    if short in _LOCALIZATION:
        return short
    return 'en'


def _status_texts():
    return _LOCALIZATION.get(_client_language(), _LOCALIZATION['en'])


class HighCaliberState(object):

    def __init__(self):
        self.reset()

    def reset(self):
        self.totalEnemyHP = 0
        self.requiredDamage = 0
        self.damage = 0
        self.teamHit = False
        self.ready = False

    def setTotalEnemyHP(self, totalHP):
        try:
            totalHP = int(totalHP)
        except Exception:
            return False
        if totalHP <= 0:
            return False
        changed = totalHP != self.totalEnemyHP
        self.totalEnemyHP = totalHP
        self.requiredDamage = (totalHP + 4) // 5
        self.ready = True
        return changed

    def addDamage(self, damage):
        try:
            damage = int(damage)
        except Exception:
            return False
        if damage <= 0:
            return False
        self.damage += damage
        return True

    def setTeamHit(self):
        if self.teamHit:
            return False
        self.teamHit = True
        return True

    def remaining(self):
        return max(0, self.requiredDamage - self.damage)

    def status(self):
        if self.teamHit:
            return 'wasted'
        if self.ready and self.remaining() <= 0:
            return 'done'
        return 'progress'


_STATE = HighCaliberState()


class HighCaliberModel(ViewModel):

    def __init__(self, properties=1, commands=1):
        super(HighCaliberModel, self).__init__(properties=properties, commands=commands)

    def _initialize(self):
        super(HighCaliberModel, self)._initialize()
        self._addStringProperty('payload', '{}')
        self.onResized = self._addCommand('onResized')
        self.onResized += self.__onResized

    def __onResized(self, sizeMap=None, *args):
        # The GameFace surface is intentionally fullscreen. Keep the Wulf
        # window fixed at the top-left; the 150x40 indicator itself moves
        # locally inside the surface in JS, which avoids per-frame Wulf moves.
        try:
            listener = _listener
            window = None if listener is None else listener.window
            if window is not None:
                window.move(0, 0)
        except Exception:
            pass

    def getPayload(self):
        return self._getString(0)

    def setPayload(self, value):
        self._setString(0, value)


class HighCaliberView(ViewImpl):
    if _OPENWG_OK:
        viewLayoutID = ModDynAccessor(RES_MAP_ITEM_ID)
    else:
        viewLayoutID = None

    def __init__(self):
        if not _OPENWG_OK:
            raise RuntimeError('OpenWG.Gameface is required')
        settings = ViewSettings(
            HighCaliberView.viewLayoutID(),
            flags=ViewFlags.VIEW,
            model=HighCaliberModel()
        )
        super(HighCaliberView, self).__init__(settings)
        self.__lastPayload = None

    @property
    def viewModel(self):
        return super(HighCaliberView, self).getViewModel()

    def push(self):
        status = _STATE.status()
        doneText, wastedText = _status_texts()
        try:
            screenW, screenH = GUI.screenResolution()
        except Exception:
            screenW, screenH = (1920, 1080)
        payload = {
            'visible': bool(_CONFIG.get('enabled', True) and _STATE.ready),
            'status': status,
            'remaining': _STATE.remaining(),
            'damage': _STATE.damage,
            'requiredDamage': _STATE.requiredDamage,
            'scale': _CONFIG.get('scale', 1.0),
            'offsetX': _CONFIG.get('offsetX', 380),
            'offsetY': _CONFIG.get('offsetY', 0),
            'screenWidth': int(screenW),
            'screenHeight': int(screenH),
            'showDoneText': bool(_CONFIG.get('showDoneText', True)),
            'showWastedText': bool(_CONFIG.get('showWastedText', True)),
            'doneText': doneText,
            'wastedText': wastedText,
            'dragEnabled': bool(_CONFIG.get('drag', True)),
            'colorProgress': _CONFIG.get('colorProgress', '#F8F400'),
            'colorDone': _CONFIG.get('colorDone', '#60FF00'),
            'colorWasted': _CONFIG.get('colorWasted', '#FE0E00')
        }
        try:
            raw = json.dumps(payload, separators=(',', ':'), sort_keys=True)
        except Exception:
            raw = '{}'
        if raw == self.__lastPayload:
            return
        with self.viewModel.transaction() as model:
            model.setPayload(raw)
        self.__lastPayload = raw

    def hide(self):
        payload = {'visible': False}
        try:
            raw = json.dumps(payload, separators=(',', ':'), sort_keys=True)
        except Exception:
            raw = '{}'
        with self.viewModel.transaction() as model:
            model.setPayload(raw)
        self.__lastPayload = raw


class HighCaliberWindow(WindowImpl):

    def __init__(self, parent=None):
        super(HighCaliberWindow, self).__init__(
            WindowFlags.WINDOW,
            content=HighCaliberView(),
            layer=WindowLayer.VIEW,
            name='INQHighCaliber',
            parent=parent
        )

    def _onReady(self):
        self.show(focus=False)
        try:
            self.move(0, 0)
        except Exception:
            pass


def _get_main_window():
    try:
        guiLoader = dependency.instance(IGuiLoader)
        windowsManager = getattr(guiLoader, 'windowsManager', None)
        if windowsManager is None:
            return None
        return windowsManager.getMainWindow()
    except Exception:
        return None


def _battle_ready_to_show():
    try:
        player = BigWorld.player()
        arena = getattr(player, 'arena', None)
    except Exception:
        return False
    if arena is None:
        return False
    try:
        period = int(getattr(arena, 'period', -1))
    except Exception:
        period = -1
    if period < 1:
        return False
    if period >= 2:
        return True
    try:
        vehicle = None
        fn = getattr(player, 'getVehicleAttached', None)
        if callable(fn):
            vehicle = fn()
        if vehicle is None:
            vehicle = getattr(player, 'vehicle', None)
        if vehicle is None:
            return False
        health = getattr(vehicle, 'health', None)
        if health is not None and int(health) <= 0:
            return False
    except Exception:
        return False
    try:
        inputHandler = getattr(player, 'inputHandler', None)
        ctrl = getattr(inputHandler, 'ctrl', None) if inputHandler is not None else None
        if ctrl is None:
            return False
        for attr in ('curVehicleID', 'vehicleID', 'controlledVehicleID'):
            try:
                if getattr(ctrl, attr, None):
                    return True
            except Exception:
                pass
        for method in ('getCameraType', 'getControlModeName', 'getModeName'):
            try:
                fn = getattr(ctrl, method, None)
                if callable(fn) and fn():
                    return True
            except Exception:
                pass
        return getattr(inputHandler, 'camera', None) is not None
    except Exception:
        return False


def _move_window(surfaceWidth, surfaceHeight, gameScale=1.0):
    # Kept for compatibility with older helper packages. New smooth drag keeps
    # the fullscreen Wulf surface fixed and does not call this during dragging.
    listener = _listener
    window = None if listener is None else listener.window
    if window is None:
        return
    try:
        window.move(0, 0)
    except Exception:
        pass


class HighCaliberBattleListener(IBattleFieldListener):

    def __init__(self):
        self.window = None
        self.view = None
        self._retryCallback = None
        self.loadWindow()

    def _retryLoad(self, retry):
        self._retryCallback = None
        self.loadWindow(retry)

    def loadWindow(self, retry=0):
        if not _OPENWG_OK or not _CONFIG.get('enabled', True) or self.window is not None:
            return
        if not _battle_ready_to_show():
            if retry < 300 and self._retryCallback is None:
                self._retryCallback = BigWorld.callback(0.1, lambda: self._retryLoad(retry + 1))
            return
        parent = _get_main_window()
        status = None if parent is None else getattr(parent, 'windowStatus', None)
        if parent is None or getattr(parent, 'proxy', None) is None or status != WindowStatus.LOADED:
            if retry < 100 and self._retryCallback is None:
                self._retryCallback = BigWorld.callback(0.1, lambda: self._retryLoad(retry + 1))
            return
        try:
            self.window = HighCaliberWindow(parent=parent)
            self.window.load()
            self.view = self.window.content
            self.view.push()
        except Exception:
            _logger.exception('Failed to load High Caliber window')
            self.window = None
            self.view = None

    def destroy(self):
        if self._retryCallback is not None:
            try:
                BigWorld.cancelCallback(self._retryCallback)
            except Exception:
                pass
            self._retryCallback = None
        if self.view is not None:
            try:
                self.view.hide()
            except Exception:
                pass
        if self.window is not None:
            try:
                self.window.destroy()
            except Exception:
                pass
        self.window = None
        self.view = None

    def updateVehicleHealth(self, vehicleID, newHealth, maxHealth):
        pass

    def updateTeamHealth(self, alliesHP, enemiesHP, totalAlliesHP, totalEnemiesHP):
        if _STATE.setTotalEnemyHP(totalEnemiesHP):
            _push_ui()

    def updateDeadVehicles(self, aliveAllies, deadAllies, aliveEnemies, deadEnemies):
        pass


def _get_listener():
    return _listener


_listener = None
_orig_setViewComponents = BattleFieldCtrl.setViewComponents


def _set_view_components(self, *args, **kwargs):
    global _listener
    result = _orig_setViewComponents(self, *args, **kwargs)
    try:
        if _listener is not None:
            try:
                self.removeBattleFieldListener(_listener)
            except Exception:
                pass
            _listener.destroy()
        _STATE.reset()
        _listener = HighCaliberBattleListener()
        self.addBattleFieldListener(_listener)
        total = getattr(self, '_BattleFieldCtrl__totalEnemiesHealth', 0)
        if _STATE.setTotalEnemyHP(total):
            _push_ui()
    except Exception:
        _logger.exception('Failed to attach High Caliber battle listener')
    return result


BattleFieldCtrl.setViewComponents = _set_view_components


def _push_ui():
    listener = _listener
    if listener is None:
        return
    try:
        if listener.view is not None:
            listener.view.push()
    except Exception:
        _logger.exception('Failed to update High Caliber UI')


def _on_battle_events(self, events):
    result = _orig_onBattleEvents(self, events)
    try:
        arenaDP = self.guiSessionProvider.getArenaDP()
        changed = False
        for data in events:
            event = feedback_events.PlayerFeedbackEvent.fromDict(data)
            if event.getBattleEventType() != BATTLE_EVENT_TYPE.DAMAGE:
                continue
            targetID = event.getTargetID()
            vehicleInfo = arenaDP.getVehicleInfo(targetID)
            if vehicleInfo is None or not arenaDP.isEnemyTeam(vehicleInfo.team):
                continue
            extra = event.getExtra()
            damage = 0 if extra is None else int(extra.getDamage())
            if _STATE.addDamage(damage):
                changed = True
        if changed:
            _push_ui()
    except Exception:
        _logger.exception('Failed to process High Caliber damage event')
    return result


_orig_onBattleEvents = PlayerAvatar.onBattleEvents
PlayerAvatar.onBattleEvents = _on_battle_events


def _extract_shot_result(raw):
    try:
        if isinstance(raw, (int, long)):
            vehicleID = int((raw >> 32) & 0xFFFFFFFF)
            flags = int(raw & 0xFFFFFFFF)
            return vehicleID, flags
    except Exception:
        pass
    try:
        getter = getattr(raw, 'get', None)
        if callable(getter):
            vehicleID = getter('vehicleID', getter('vehicleId', getter('targetID', getter('targetId', 0))))
            flags = getter('flags', getter('hitFlags', getter('vehicleHitFlags', 0)))
            return int(vehicleID or 0), int(flags or 0)
    except Exception:
        pass
    try:
        vehicleID = getattr(raw, 'vehicleID', getattr(raw, 'vehicleId', getattr(raw, 'targetID', getattr(raw, 'targetId', 0))))
        flags = getattr(raw, 'flags', getattr(raw, 'hitFlags', getattr(raw, 'vehicleHitFlags', 0)))
        return int(vehicleID or 0), int(flags or 0)
    except Exception:
        return 0, 0


def _process_shot_results(player, results):
    try:
        arena = getattr(player, 'arena', None)
        arenaVehicles = {} if arena is None else getattr(arena, 'vehicles', {})
        hitMask = VEHICLE_HIT_FLAGS.IS_ANY_DAMAGE_MASK | VEHICLE_HIT_FLAGS.ATTACK_IS_DIRECT_PROJECTILE
        deadBefore = getattr(VEHICLE_HIT_FLAGS, 'VEHICLE_WAS_DEAD_BEFORE_ATTACK', 0)
        for raw in results:
            vehicleID, flags = _extract_shot_result(raw)
            if not vehicleID:
                continue
            if deadBefore and flags & deadBefore:
                continue
            data = arenaVehicles.get(vehicleID)
            if not data:
                continue
            if vehicleID == getattr(player, 'playerVehicleID', 0):
                continue
            if data.get('team') != getattr(player, 'team', None):
                continue
            vehicle = BigWorld.entity(vehicleID)
            if vehicle is not None and getattr(vehicle, 'health', 1) <= 0:
                continue
            if flags & hitMask:
                if _STATE.setTeamHit():
                    _push_ui()
                break
    except Exception:
        _logger.exception('Failed to process friendly shot result')


_orig_showShotResults = PlayerAvatar.showShotResults


def _show_shot_results(self, results):
    result = _orig_showShotResults(self, results)
    _process_shot_results(self, results)
    return result


PlayerAvatar.showShotResults = _show_shot_results


def init():
    _logger.info('INQ High Caliber loaded, version=%s', MOD_VERSION)


def fini():
    global _listener
    if _listener is not None:
        try:
            _listener.destroy()
        except Exception:
            pass
        _listener = None


def onDisconnected():
    _STATE.reset()


def onAccountBecomeNonPlayer():
    _STATE.reset()
