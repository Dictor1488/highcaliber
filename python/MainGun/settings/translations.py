from ..utils import logger


class TranslationManager(object):
    def __init__(self):
        self._loaded = True

    def load(self, force=False):
        return True

    def get(self, key):
        values = {'modname': 'High Caliber', 'mainGun': 'High Caliber'}
        return values.get(key, key)


g_translationManager = TranslationManager()


def getTranslation(key):
    return g_translationManager.get(key)
