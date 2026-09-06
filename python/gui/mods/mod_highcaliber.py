from MainGun.utils import logger
from MainGun import initialize, finalize

__version__ = '0.2.0'
__author__ = 'INQ / MainGun runtime'
__mod_name__ = 'HighCaliber'


def init():
    try:
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
