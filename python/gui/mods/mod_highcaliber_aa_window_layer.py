# -*- coding: utf-8 -*-
"""Keep High Caliber on the battle VIEW layer.

The panel is part of the normal battle HUD and therefore must stay below
higher-priority battle menus such as reserves, the TAB roster and mission
screens. Using WindowLayer.WINDOW made the standalone Wulf window render above
those menus.
"""

from frameworks.wulf import WindowFlags, WindowLayer
from gui.impl.pub import WindowImpl
from gui.mods import mod_highcaliber as hc

_installed = False
_orig_init = None


def _window_init(self, parent=None):
    WindowImpl.__init__(
        self,
        WindowFlags.WINDOW,
        content=hc.HighCaliberView(),
        layer=WindowLayer.VIEW,
        name='INQHighCaliber',
        parent=parent
    )


def init():
    global _installed, _orig_init
    if _installed:
        return
    _orig_init = hc.HighCaliberWindow.__init__
    hc.HighCaliberWindow.__init__ = _window_init
    _installed = True


def fini():
    global _installed
    if not _installed:
        return
    try:
        if _orig_init is not None:
            hc.HighCaliberWindow.__init__ = _orig_init
    except Exception:
        pass
    _installed = False
