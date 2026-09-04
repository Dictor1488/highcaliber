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
from gui.impl.pub import ViewImpl, WindowImpl
from gui.battle_control.controllers import battle_field_ctrl, feedback_events
from gui.battle_control.controllers.battle_field_ctrl import IBattleFieldListener
from helpers import dependency, getClientLanguage
from skeletons.gui.impl import IGuiLoader

try:
    from openwg_gameface import ModDynAccessor
    _OPENWG_OK = True
except Exception:
    ModDynAccessor = None
    _OPENWG_OK = False


__version__ = '0.1.0'
_logger = logging.getLogger('[INQHighCaliber]')

RES_MAP_ITEM_ID = 'mods/highcaliber/HighCaliberBattle/layoutID'
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
_CONFIG = dict(_DEFAULT_CONFIG)

_listener = None
_current_ctrl = None
_orig_setViewComponents = None
_orig_stopControl = None
_orig_onBattleEvents = None
_orig_showShotResults = None


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


_STATUS_TEXTS = {
    'en': (u'Done!', u'Wasted!'),
    'ru': (u'Готово!', u'Потеряно!'),
    'uk': (u'Готово!', u'Втрачено!'),
    'ua': (u'Готово!', u'Втрачено!'),
    'de': (u'Geschafft!', u'Verwirkt!'),
    'pl': (u'Gotowe!', u'Utracone!'),
    'cs': (u'Hotovo!', u'Ztraceno!'),
    'sk': (u'Hotovo!', u'Stratené!'),
    'fr': (u'Terminé !', u'Perdu !'),
    'es': (u'¡Hecho!', u'¡Perdido!'),
    'it': (u'Fatto!', u'Perso!'),
    'pt': (u'Concluído!', u'Perdido!'),
    'pt_br': (u'Concluído!', u'Perdido!'),
    'tr': (u'Tamam!', u'Kaybedildi!'),
    'hu': (u'Kész!', u'Elveszett!'),
    'ro': (u'Gata!', u'Pierdut!'),
    'bg': (u'Готово!', u'Загубено!'),
    'sr': (u'Готово!', u'Изгубљено!'),
    'hr': (u'Gotovo!', u'Izgubljeno!'),
    'sl': (u'Končano!', u'Izgubljeno!'),
    'nl': (u'Klaar!', u'Verloren!'),
    'sv': (u'Klart!', u'Förlorad!'),
    'no': (u'Ferdig!', u'Tapt!'),
    'da': (u'Færdig!', u'Tabt!'),
    'fi': (u'Valmis!', u'Menetetty!'),
    'el': (u'Έτοιμο!', u'Χάθηκε!'),
    'et': (u'Valmis!', u'Kaotatud!'),
    'lv': (u'Gatavs!', u'Zaudēts!'),
    'lt': (u'Baigta!', u'Prarasta!'),
    'zh': (u'完成！', u'已失效！'),
    'zh_cn': (u'完成！', u'已失效！'),
    'zh_tw': (u'完成！', u'已失效！'),
    'ja': (u'達成！', u'失効！'),
    'ko': (u'완료!', u'상실!'),
    'th': (u'สำเร็จ!', u'เสียสิทธิ์!'),
    'vi': (u'Hoàn tất!', u'Đã mất!')
}


def _client_language():
    try:
        language = unicode(getClientLanguage() or 'en').strip().lower()
    except Exception:
        try:
            language = str(getClientLanguage() or 'en').strip().lower()
        except Exception:
            language = 'en'
    return language.replace('-', '_')


def _status_texts():
    language = _client_language()
    texts = _STATUS_TEXTS.get(language)
    if texts is not None:
        return texts
    root = language.split('_', 1)[0]
    return _STATUS_TEXTS.get(root, _STATUS_TEXTS['en'])


def _load_config():
    global _CONFIG
    cfg = dict(_DEFAULT_CONFIG)
    try:
        if not os.path.isdir(_CONFIG_DIR):
            os.makedirs(_CONFIG_DIR)
        if os.path.isfile(_CONFIG_PATH):
            with open(_CONFIG_PATH, 'r') as stream:
                stored = json.load(stream)
            if isinstance(stored, dict):
                for key in _DEFAULT_CONFIG:
                    if key in stored:
                        cfg[key] = stored[key]
        else:
            with open(_CONFIG_PATH, 'w') as stream:
                json.dump(cfg, stream, indent=2, sort_keys=True)
    except Exception:
        _logger.exception('Failed to load settings.json; defaults are used')

    cfg['enabled'] = bool(cfg.get('enabled', True))
    cfg['drag'] = bool(cfg.get('drag', True))
    cfg['offsetX'] = _safe_int(cfg.get('offsetX', 380), 380)
    cfg['offsetY'] = _safe_int(cfg.get('offsetY', 0), 0)
    cfg['scale'] = max(0.5, min(2.0, _safe_float(cfg.get('scale', 1.0), 1.0)))
    cfg['showDoneText'] = bool(cfg.get('showDoneText', True))
    cfg['showWastedText'] = bool(cfg.get('showWastedText', True))
    _CONFIG = cfg


class HighCaliberState(object):

    def __init__(self):
        self.reset()

    def reset(self):
        self.totalEnemyHP = 0
        self.requiredDamage = 0
        self.damage = 0
        self.teamHit = False
        self.ready = False

    def setTotalEnemyHP(self, totalEnemyHP):
        totalEnemyHP = max(0, _safe_int(totalEnemyHP))
        if totalEnemyHP <= 0:
            return False
        required = (totalEnemyHP + 4) // 5
        changed = (not self.ready or self.totalEnemyHP != totalEnemyHP or self.requiredDamage != required)
        self.totalEnemyHP = totalEnemyHP
        self.requiredDamage = required
        self.ready = True
        return changed

    def addDamage(self, damage):
        damage = max(0, _safe_int(damage))
        if damage <= 0:
            return False
        self.damage += damage
        return True

    def markTeamHit(self):
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
        try:
            width = int(sizeMap['width'])
            height = int(sizeMap['height'])
            gameScale = _safe_float(sizeMap.get('gameScale', 1.0), 1.0)
        except Exception:
            return
        _move_window(width, height, gameScale)

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
        payload = {
            'visible': bool(_CONFIG.get('enabled', True) and _STATE.ready),
            'status': status,
            'remaining': _STATE.remaining(),
            'damage': _STATE.damage,
            'requiredDamage': _STATE.requiredDamage,
            'scale': _CONFIG.get('scale', 1.0),
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
    """Do not create the HUD while the team-loading screen still owns the battle space."""
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
    listener = _listener
    window = None if listener is None else listener.window
    if window is None:
        return
    try:
        screenW, _screenH = GUI.screenResolution()
        coordScale = max(0.01, _safe_float(gameScale, 1.0))
        x = int(max(0, round((screenW - surfaceWidth) / (2.0 * coordScale) + _CONFIG.get('offsetX', 380))))
        y = int(max(0, round(_CONFIG.get('offsetY', 0) / coordScale)))
        window.move(x, y)
    except Exception:
        _logger.exception('Failed to move High Caliber window')


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
    global _listener
    if _listener is None:
        _listener = HighCaliberBattleListener()
    return _listener


def _push_ui():
    try:
        listener = _get_listener()
        listener.loadWindow()
        if listener.view is not None:
            listener.view.push()
    except Exception:
        _logger.exception('Failed to update High Caliber UI')


def _seed_total_enemy_hp(ctrl):
    try:
        total = getattr(ctrl, '_BattleFieldCtrl__totalEnemiesHealth', 0)
        if _STATE.setTotalEnemyHP(total):
            _push_ui()
    except Exception:
        pass


def _patched_setViewComponents(self, *components):
    global _current_ctrl
    _current_ctrl = self
    listener = _get_listener()
    forwarded = list(components)
    if listener not in forwarded:
        forwarded.append(listener)
    result = _orig_setViewComponents(self, *tuple(forwarded))
    _seed_total_enemy_hp(self)
    _push_ui()
    return result


def _patched_stopControl(self):
    global _listener, _current_ctrl
    _current_ctrl = None
    if _listener is not None:
        try:
            _listener.destroy()
        except Exception:
            pass
    _listener = None
    _STATE.reset()
    return _orig_stopControl(self)


def _process_battle_events(player, events):
    if not _CONFIG.get('enabled', True):
        return
    try:
        provider = player.guiSessionProvider
        arenaDP = provider.getArenaDP()
        for data in events:
            event = feedback_events.PlayerFeedbackEvent.fromDict(data)
            if event.getBattleEventType() != BATTLE_EVENT_TYPE.DAMAGE:
                continue
            targetID = event.getTargetID()
            try:
                vehicleInfo = arenaDP.getVehicleInfo(targetID)
                if not arenaDP.isEnemyTeam(vehicleInfo.team):
                    continue
            except Exception:
                continue
            extra = event.getExtra()
            if extra is None:
                continue
            damage = _safe_int(extra.getDamage(), 0)
            if _STATE.addDamage(damage):
                _push_ui()
    except Exception:
        _logger.exception('Failed to process battle damage events')


def _patched_onBattleEvents(self, events):
    result = _orig_onBattleEvents(self, events)
    _process_battle_events(self, events)
    return result


def _extract_shot_result(raw):
    try:
        if isinstance(raw, (int, long)):
            return ((raw >> 32) & 0xFFFFFFFF, raw & 0xFFFFFFFF)
    except Exception:
        pass

    def _get(obj, names, default=None):
        for name in names:
            try:
                value = getattr(obj, name)
                if value is not None:
                    return value
            except Exception:
                pass
            try:
                value = obj[name]
                if value is not None:
                    return value
            except Exception:
                pass
            try:
                value = obj.get(name)
                if value is not None:
                    return value
            except Exception:
                pass
        return default

    vehicleID = _get(raw, ('vehicleID', 'vehicleId', 'targetID', 'targetId'), 0)
    flags = _get(raw, ('flags', 'hitFlags', 'result', 'hitResult'), 0)
    try:
        return (int(vehicleID or 0), int(flags or 0))
    except Exception:
        return (0, 0)


def _process_shot_results(player, results):
    if _STATE.teamHit or not _CONFIG.get('enabled', True):
        return
    try:
        arenaVehicles = player.arena.vehicles
        playerVehicleID = player.playerVehicleID
        playerTeam = player.team
        hitMask = VEHICLE_HIT_FLAGS.IS_ANY_DAMAGE_MASK | VEHICLE_HIT_FLAGS.ATTACK_IS_DIRECT_PROJECTILE
        deadBeforeMask = getattr(VEHICLE_HIT_FLAGS, 'VEHICLE_WAS_DEAD_BEFORE_ATTACK', 0)

        for raw in results:
            vehicleID, flags = _extract_shot_result(raw)
            if not vehicleID:
                continue
            if deadBeforeMask and flags & deadBeforeMask:
                continue
            if vehicleID == playerVehicleID:
                continue
            vehicle = arenaVehicles.get(vehicleID)
            if not vehicle:
                continue
            if vehicle.get('team') != playerTeam:
                continue
            if not vehicle.get('isAlive', True):
                continue
            if flags & hitMask:
                if _STATE.markTeamHit():
                    _push_ui()
                break
    except Exception:
        _logger.exception('Failed to process friendly shot result')


def _patched_showShotResults(self, results):
    _process_shot_results(self, results)
    return _orig_showShotResults(self, results)


def _install_hooks():
    global _orig_setViewComponents, _orig_stopControl
    global _orig_onBattleEvents, _orig_showShotResults

    if _orig_setViewComponents is None:
        _orig_setViewComponents = battle_field_ctrl.BattleFieldCtrl.setViewComponents
        _orig_stopControl = battle_field_ctrl.BattleFieldCtrl.stopControl
        battle_field_ctrl.BattleFieldCtrl.setViewComponents = _patched_setViewComponents
        battle_field_ctrl.BattleFieldCtrl.stopControl = _patched_stopControl

    if _orig_onBattleEvents is None:
        _orig_onBattleEvents = PlayerAvatar.onBattleEvents
        PlayerAvatar.onBattleEvents = _patched_onBattleEvents

    if _orig_showShotResults is None:
        _orig_showShotResults = PlayerAvatar.showShotResults
        PlayerAvatar.showShotResults = _patched_showShotResults


def _restore_hooks():
    global _orig_setViewComponents, _orig_stopControl
    global _orig_onBattleEvents, _orig_showShotResults
    try:
        if _orig_setViewComponents is not None:
            battle_field_ctrl.BattleFieldCtrl.setViewComponents = _orig_setViewComponents
        if _orig_stopControl is not None:
            battle_field_ctrl.BattleFieldCtrl.stopControl = _orig_stopControl
    except Exception:
        pass
    try:
        if _orig_onBattleEvents is not None:
            PlayerAvatar.onBattleEvents = _orig_onBattleEvents
        if _orig_showShotResults is not None:
            PlayerAvatar.showShotResults = _orig_showShotResults
    except Exception:
        pass
    _orig_setViewComponents = None
    _orig_stopControl = None
    _orig_onBattleEvents = None
    _orig_showShotResults = None


def _shutdown():
    global _listener, _current_ctrl
    _current_ctrl = None
    if _listener is not None:
        try:
            _listener.destroy()
        except Exception:
            pass
    _listener = None
    _STATE.reset()


def init():
    try:
        _load_config()
        if not _OPENWG_OK:
            _logger.error('OpenWG.Gameface is not available; mod UI cannot start')
            return
        _install_hooks()
        _logger.info('INQ High Caliber loaded, version=%s', __version__)
    except Exception:
        _logger.exception('INQ High Caliber init failed')


def fini():
    try:
        _shutdown()
        _restore_hooks()
    except Exception:
        _logger.exception('INQ High Caliber fini failed')


def onDisconnected():
    _shutdown()


def onAccountBecomeNonPlayer():
    _shutdown()
