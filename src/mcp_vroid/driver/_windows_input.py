"""Physical-pixel mouse input and Unicode keyboard input using SendInput."""
from __future__ import annotations

import ctypes as ct
import time
from ctypes import wintypes as wt

from . import _win32 as N
from . import window as W

_SAFE = True
BUTTONS = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010),
           "middle": (0x0020, 0x0040)}
ALIASES = {"enter": 0x0D, "return": 0x0D, "esc": 0x1B, "escape": 0x1B,
           "tab": 0x09, "backspace": 0x08, "delete": 0x2E, "space": 0x20,
           "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
           "home": 0x24, "end": 0x23, "pageup": 0x21, "prior": 0x21,
           "pagedown": 0x22, "next": 0x22, "insert": 0x2D,
           "ctrl": 0x11, "control": 0x11, "control_l": 0x11,
           "shift": 0x10, "shift_l": 0x10, "alt": 0x12, "alt_l": 0x12,
           "super": 0x5B, "super_l": 0x5B, "meta": 0x5B, "win": 0x5B}
EXTENDED = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x5B}


def set_safety(on: bool) -> None:
    global _SAFE
    _SAFE = on


def _guard():
    if _SAFE:
        W.assert_vroid_focused()


def _resolve(x, y, space, shot=None):
    if space == "layout":
        return x, y
    if space == "image":
        if shot is None:
            raise ValueError("space='image' needs shot=")
        return shot.to_layout(x, y)
    if space != "window":
        raise ValueError(f"unknown coordinate space {space!r}")
    win = W.find_window()
    if win is None:
        raise RuntimeError("VRoid Studio window not found")
    return win.to_layout(x, y)


def _absolute(x, y, geometry):
    ox, oy, w, h = geometry
    if w <= 1 or h <= 1 or not (ox <= x < ox + w and oy <= y < oy + h):
        raise ValueError(f"point {(x, y)} is outside the Windows virtual desktop")
    return round((x - ox) * 65535 / (w - 1)), round((y - oy) * 65535 / (h - 1))


def _move(x, y):
    _guard()
    ax, ay = _absolute(x, y, N.desktop_geometry())
    N.send(N.mouse(0x0001 | 0x8000 | 0x4000, x=ax, y=ay))  # MOVE/ABSOLUTE/VIRTUALDESK


def move(x: float, y: float, space: str = "window", shot=None) -> None:
    _move(*_resolve(x, y, space, shot))


def _button(button):
    button = {1: "left", 2: "middle", 3: "right"}.get(button, button)
    if button not in BUTTONS:
        raise ValueError(f"unknown mouse button {button!r}")
    return BUTTONS[button]


def click(x, y, button="left", space="window", shot=None, settle=0.35, moves=3):
    _guard()
    down, up = _button(button)
    lx, ly = _resolve(x, y, space, shot)
    N.ensure_dpi_awareness()
    cur = wt.POINT()
    N.check(N.GetCursorPos(ct.byref(cur)))
    for i in range(1, max(1, moves) + 1):
        t = i / max(1, moves)
        _move(cur.x + (lx - cur.x) * t, cur.y + (ly - cur.y) * t)
        time.sleep(0.012)
    time.sleep(0.06)
    _guard()
    try:
        N.send(N.mouse(down))
        time.sleep(0.05)
    finally:
        N.send(N.mouse(up))
    time.sleep(settle)


def double_click(x, y, **kw):
    # Keep the same button, coordinate space and Shot for both clicks.
    settle = kw.pop("settle", 0.35)
    click(x, y, settle=0.05, **kw)
    click(x, y, settle=settle, **kw)


def drag(x1, y1, x2, y2, button="left", space="window", shot=None,
         steps=24, settle=0.4):
    _guard()
    if steps < 1:
        raise ValueError("steps must be positive")
    down, up = _button(button)
    ax, ay = _resolve(x1, y1, space, shot)
    bx, by = _resolve(x2, y2, space, shot)
    _absolute(bx, by, N.desktop_geometry())
    _move(ax, ay)
    time.sleep(0.12)
    _guard()
    N.send(N.mouse(down))
    try:
        for i in range(1, steps + 1):
            t = i / steps
            _move(ax + (bx - ax) * t, ay + (by - ay) * t)
            time.sleep(0.016)
    finally:
        # Always release even if the user changes focus during the drag.
        N.send(N.mouse(up))
    time.sleep(settle)


def _wheel(ticks, horizontal, x, y, space, shot, settle):
    _guard()
    if x is not None and y is not None:
        move(x, y, space, shot)
        time.sleep(0.2)
    # Shared API: positive vertical ticks = down; Win32 WHEEL = up.
    delta = (120 if ticks > 0 else -120) * (1 if horizontal else -1)
    for _ in range(abs(ticks)):
        _guard()
        N.send(N.mouse(0x1000 if horizontal else 0x0800, data=delta))
        time.sleep(0.07)
    time.sleep(settle)


def scroll(ticks, x=None, y=None, space="window", shot=None, settle=0.3, backend="win32"):
    _wheel(ticks, False, x, y, space, shot, settle)


def hscroll(ticks, x=None, y=None, space="window", shot=None, settle=0.3):
    _wheel(ticks, True, x, y, space, shot, settle)


def _vk(name):
    low = name.lower()
    if low in ALIASES:
        return ALIASES[low], []
    if low.startswith("f") and low[1:].isdigit() and 1 <= int(low[1:]) <= 24:
        return 0x70 + int(low[1:]) - 1, []
    if len(name) == 1:
        value = N.VkKeyScanW(name)
        if value != -1:
            mods = [vk for mask, vk in ((1, 0x10), (2, 0x11), (4, 0x12))
                    if (value >> 8) & mask]
            return value & 0xFF, mods
    raise ValueError(f"unsupported key {name!r}; use type_text for literal Unicode")


def _key_event(vk, up=False):
    return N.keyboard(vk=vk, flags=(1 if vk in EXTENDED else 0) | (2 if up else 0))


def key(name: str, mods=None, times=1):
    vk, automatic = _vk(name)
    modifiers = list(dict.fromkeys([_vk(m)[0] for m in (mods or [])] + automatic))
    for _ in range(times):
        _guard()
        # Unity samples modifier state by frame. Keep the chord pressed long
        # enough to observe it, then release even if focus changes or input fails.
        try:
            if modifiers:
                N.send(*[_key_event(m) for m in modifiers])
                time.sleep(0.03)
                _guard()
            N.send(_key_event(vk))
            time.sleep(0.05)
        finally:
            N.send(_key_event(vk, True),
                   *[_key_event(m, True) for m in reversed(modifiers)])
        time.sleep(0.06)
    time.sleep(0.12)


def _unicode_events(text):
    encoded = text.encode("utf-16-le")
    events = []
    for offset in range(0, len(encoded), 2):
        unit = int.from_bytes(encoded[offset:offset + 2], "little")
        events.extend((N.keyboard(scan=unit, flags=4), N.keyboard(scan=unit, flags=6)))
    return events


def type_text(text: str, delay_ms: int = 22):
    for ch in text:
        _guard()
        if ch in ("\n", "\t", "\r"):
            key("Tab" if ch == "\t" else "Return")
        else:
            N.send(*_unicode_events(ch))
        time.sleep(delay_ms / 1000)
    time.sleep(0.15)


def clear_field():
    key("a", mods=["ctrl"])
    key("BackSpace")


def hotkey(combo: str):
    *mods, name = combo.split("+")
    key(name, mods=mods)


def x_focus_ok():
    return W.is_vroid_focused()
