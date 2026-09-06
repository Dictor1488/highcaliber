# -*- coding: utf-8 -*-
import json

from .settings import getTranslation
from .views import MainGunPanel

_installed = False
_original_build_payload = None


def install():
    global _installed, _original_build_payload
    if _installed:
        return
    _original_build_payload = MainGunPanel.buildPayload

    def _build_localized_payload(self):
        raw = _original_build_payload(self)
        try:
            data = json.loads(raw)
        except Exception:
            return raw
        l10n = data.setdefault('l10n', {})
        l10n['mainGun'] = getTranslation('mainGun')
        l10n['done'] = getTranslation('done')
        l10n['wasted'] = getTranslation('wasted')
        return json.dumps(data, ensure_ascii=False)

    MainGunPanel.buildPayload = _build_localized_payload
    _installed = True
