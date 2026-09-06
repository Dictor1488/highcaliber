from MainGun.utils import logger
from MainGun import initialize, finalize
from MainGun import legacy_drag

__version__ = '0.2.0'
__author__ = 'INQ / MainGun runtime'
__mod_name__ = 'HighCaliber'


def init():
    try:
        legacy_drag.install()
        initialize()
        logger.info('[HighCaliber] loaded successfully: v%s', __version__)
    except Exception as e:
        logger.error('[HighCaliber] loading failed: %s', e)
        import traceback
        logger.error('Traceback: %s', traceback.format_exc())


def fini():
    try:
        finalize()
    except Exception as e:
        logger.error('[HighCaliber] shutdown failed: %s', e)
    finally:
        try:
            legacy_drag.uninstall()
        except Exception:
            pass
