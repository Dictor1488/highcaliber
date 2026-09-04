# -*- coding: utf-8 -*-
"""Guard High Caliber resize reflow so HUD layout changes (e.g. team ears) do not break drag."""

import GUI

from gui.mods import mod_highcaliber_drag as drag

_last_resolution = None
_orig_schedule_resize_reflow = drag._schedule_resize_reflow


def _screen_resolution():
    try:
        value = GUI.screenResolution()
        return (int(value[0]), int(value[1]))
    except Exception:
        return None


def _guarded_schedule_resize_reflow(*args):
    global _last_resolution
    current = _screen_resolution()
    if current is None:
        return
    if _last_resolution is None:
        _last_resolution = current
        return
    if current == _last_resolution:
        # Wulf parent/window sizes can change when battle HUD elements such as
        # the team panels ("ears") change state. That is not a display resize
        # and must not reflow/move the High Caliber surface or hit area.
        return
    _last_resolution = current
    _orig_schedule_resize_reflow(*args)


def init():
    global _last_resolution
    _last_resolution = _screen_resolution()
    drag._schedule_resize_reflow = _guarded_schedule_resize_reflow
    drag.hc._logger.info('High Caliber resize guard installed; resolution=%r', _last_resolution)


def fini():
    drag._schedule_resize_reflow = _orig_schedule_resize_reflow
