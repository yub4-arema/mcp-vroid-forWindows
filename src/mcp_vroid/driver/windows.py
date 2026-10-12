"""Windows implementation: pywinauto input, Win32 identity, Pillow capture.

Imports of Windows libraries are lazy so the Linux driver never loads them.
Geometry is the client area in physical desktop pixels, not the window frame.
"""
from __future__ import annotations

import ctypes
import os
import time
from pathlib import Path

_previous_window: tuple[int, int] | None = None
_remembered = False


def _gui():
    import win32gui
    return win32gui


def _pid(hwnd: int) -> int:
    import win32process
    return win32process.GetWindowThreadProcessId(hwnd)[1]


def _process_path(pid: int) -> str:
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return buffer.value
        return ""
    finally:
        kernel32.CloseHandle(handle)


def _handles() -> list[int]:
    handles = []
    _gui().EnumWindows(lambda hwnd, _: handles.append(hwnd), None)
    return handles


def _main_hwnd() -> int | None:
    gui = _gui()
    candidates = []
    for hwnd in _handles():
        try:
            if (gui.IsWindowVisible(hwnd) and not gui.GetWindow(hwnd, 4)
                    and gui.GetWindowText(hwnd).lower().startswith("vroid studio")
                    and Path(_process_path(_pid(hwnd))).name.lower() == "vroidstudio.exe"):
                candidates.append(hwnd)
        except OSError:  # A window may close during enumeration.
            continue
    if len(candidates) > 1:
        raise RuntimeError("Multiple VRoid Studio instances found; close all but one")
    return candidates[0] if candidates else None


def _owned(hwnd: int, main: int) -> bool:
    """Only the verified app itself or its same-process owner chain is allowed."""
    gui = _gui()
    if not hwnd or not gui.IsWindow(hwnd) or _pid(hwnd) != _pid(main):
        return False
    seen = set()
    while hwnd and hwnd not in seen:
        if hwnd == main:
            return True
        seen.add(hwnd)
        hwnd = gui.GetWindow(hwnd, 4)  # GW_OWNER
    return False


def find_window():
    from .window import Window
    hwnd = _main_hwnd()
    if hwnd is None:
        return None
    gui = _gui()
    left, top, right, bottom = gui.GetClientRect(hwnd)
    x, y = gui.ClientToScreen(hwnd, (left, top))
    return Window(address=str(hwnd), cls=gui.GetClassName(hwnd),
                  title=gui.GetWindowText(hwnd), x=x, y=y,
                  w=right - left, h=bottom - top, workspace=None,
                  focused=_owned(gui.GetForegroundWindow(), hwnd),
                  maximized=gui.GetWindowPlacement(hwnd)[1] == 3, pid=_pid(hwnd))


def window_dpi() -> int:
    from ctypes import wintypes
    main = _main_hwnd()
    if main is None:
        raise RuntimeError("VRoid Studio window not found")
    get_dpi = ctypes.WinDLL("user32").GetDpiForWindow
    get_dpi.argtypes = [wintypes.HWND]
    get_dpi.restype = wintypes.UINT
    dpi = get_dpi(main)
    if not dpi:
        raise RuntimeError("Could not determine VRoid window DPI")
    return dpi


def is_vroid_focused() -> bool:
    main = _main_hwnd()
    return main is not None and _owned(_gui().GetForegroundWindow(), main)


def assert_vroid_focused() -> None:
    if not is_vroid_focused():
        raise RuntimeError("refusing to act: focused window is not verified VRoid Studio "
                           f"or its owned dialog (foreground={_gui().GetForegroundWindow()})")


def remember_previous() -> None:
    global _previous_window, _remembered
    if _remembered:
        return
    gui = _gui()
    hwnd = gui.GetForegroundWindow()
    main = _main_hwnd()
    _previous_window = ((hwnd, _pid(hwnd)) if hwnd and gui.IsWindow(hwnd)
                        and (main is None or not _owned(hwnd, main)) else None)
    _remembered = True


def previous_window() -> int | None:
    return _previous_window[0] if _previous_window else None


def release() -> dict:
    global _previous_window, _remembered
    target = previous_window()
    restored = False
    if _previous_window:
        hwnd, pid = _previous_window
        if _gui().IsWindow(hwnd) and _pid(hwnd) == pid:
            _focus_handle(hwnd)
            restored = True
    _previous_window = None
    _remembered = False
    return {"restored_window": target if restored else None,
            "restored_workspace": None, "active_workspace": None}


def _focus_handle(hwnd: int) -> None:
    gui = _gui()
    if gui.GetForegroundWindow() == hwnd:
        return
    # HwndWrapper.set_focus moves the real pointer before attempting focus.
    # Use window-management APIs directly so refused focus injects no input.
    gui.ShowWindow(hwnd, 9 if gui.IsIconic(hwnd) else 5)  # RESTORE / SHOW
    try:
        gui.SetForegroundWindow(hwnd)
    except Exception:
        # pywin32 raises pywintypes.error, which is not an OSError.
        pass
    if gui.GetForegroundWindow() != hwnd:
        _focus_attached(hwnd)
    time.sleep(0.12)
    if gui.GetForegroundWindow() != hwnd:
        raise RuntimeError("Windows refused to focus the target window; bring it forward manually")


def _focus_attached(hwnd: int) -> None:
    """Share foreground focus briefly, without synthesizing keyboard/mouse input.

    https://learn.microsoft.com/windows/win32/api/winuser/nf-winuser-attachthreadinput
    """
    import win32api
    import win32process
    gui = _gui()
    current = win32api.GetCurrentThreadId()
    foreground = gui.GetForegroundWindow()
    target = win32process.GetWindowThreadProcessId(foreground)[0] if foreground else current
    attached = False
    try:
        if target != current:
            win32process.AttachThreadInput(current, target, True)
            attached = True
        gui.SetForegroundWindow(hwnd)
    except Exception as exc:
        raise RuntimeError("Windows refused to focus the target window; bring it forward manually") from exc
    finally:
        if attached:
            win32process.AttachThreadInput(current, target, False)


def _active_target(main: int) -> int:
    gui = _gui()
    current = gui.GetForegroundWindow()
    if _owned(current, main):
        return current
    from ctypes import wintypes
    get_popup = ctypes.WinDLL("user32").GetLastActivePopup
    get_popup.argtypes = [wintypes.HWND]
    get_popup.restype = wintypes.HWND
    popup = get_popup(main)
    if popup != main and gui.IsWindowVisible(popup) and _owned(popup, main):
        return popup
    return main


def focus(win=None):
    win = win or find_window()
    if win is None:
        raise RuntimeError("VRoid Studio window not found")
    _focus_handle(_active_target(int(win.address)))
    assert_vroid_focused()
    return find_window()


def fullscreen(win=None):
    """Maximize the client while leaving an active owned modal in front."""
    win = win or find_window()
    if win is None:
        raise RuntimeError("VRoid Studio window not found")
    main = int(win.address)
    if _active_target(main) == main and not win.maximized:
        _gui().ShowWindow(main, 3)  # SW_MAXIMIZE
        time.sleep(0.6)
    return focus(win)


def launch() -> None:
    os.startfile("steam://rungameid/1486350")


def restart() -> None:
    import win32api
    import win32event
    win = find_window()
    if win is None:
        return
    # Terminate only the PID whose image path and main window we just verified.
    handle = win32api.OpenProcess(0x0001 | 0x00100000 | 0x1000, False, win.pid)
    try:
        if Path(_process_path(win.pid)).name.lower() != "vroidstudio.exe":
            raise RuntimeError("VRoid process identity changed before restart")
        win32api.TerminateProcess(handle, 0)
        if win32event.WaitForSingleObject(handle, 10000) != 0:
            raise TimeoutError("VRoid Studio did not exit within 10 seconds")
    finally:
        handle.Close()


def prepare(timeout: float = 240.0):
    from .window import launch_and_wait
    remember_previous()
    win = fullscreen(launch_and_wait(timeout))
    return win, None


def grab_region(x: int, y: int, w: int, h: int, path: Path):
    from PIL import ImageGrab
    from .capture import Shot
    if w <= 0 or h <= 0:
        raise ValueError("Capture region must have positive width and height")
    image = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).convert("RGB")
    image.save(path)
    return Shot(image, path, x, y, 1.0)


def screen_geometry() -> tuple[int, int, int, int]:
    import win32api
    return 0, 0, win32api.GetSystemMetrics(0), win32api.GetSystemMetrics(1)


def move(x: float, y: float) -> None:
    from pywinauto import mouse
    assert_vroid_focused()
    mouse.move(coords=(round(x), round(y)))


def click(x: float, y: float, button: str, moves: int = 3, double: bool = False) -> None:
    from pywinauto import mouse
    assert_vroid_focused()
    cx, cy = _gui().GetCursorPos()
    for i in range(1, max(1, moves) + 1):
        t = i / max(1, moves)
        move(cx + (x - cx) * t, cy + (y - cy) * t)
        time.sleep(0.012)
    time.sleep(0.06)
    assert_vroid_focused()
    action = mouse.double_click if double else mouse.click
    action(button=button, coords=(round(x), round(y)))


def drag(ax: float, ay: float, bx: float, by: float, button: str, steps: int) -> None:
    from pywinauto import mouse
    assert_vroid_focused()
    mouse.press(button=button, coords=(round(ax), round(ay)))
    try:
        time.sleep(0.12)
        for i in range(1, max(1, steps) + 1):
            t = i / max(1, steps)
            move(ax + (bx - ax) * t, ay + (by - ay) * t)
            time.sleep(0.016)
    finally:
        # Release even on focus loss or failure so no button remains held.
        mouse.release(button=button, coords=_gui().GetCursorPos())


def scroll(ticks: int, horizontal: bool = False) -> None:
    from pywinauto import mouse
    import win32api
    assert_vroid_focused()
    if horizontal:
        win32api.mouse_event(0x1000, 0, 0, ticks * 120, 0)  # MOUSEEVENTF_HWHEEL
    else:
        mouse.scroll(coords=_gui().GetCursorPos(), wheel_dist=-ticks)


def escape_text(text: str) -> str:
    escapes = {"{": "{{}", "}": "{}}", "+": "{+}", "^": "{^}",
               "%": "{%}", "~": "{~}", "(": "{(}", ")": "{)}",
               "\n": "{ENTER}", "\t": "{TAB}"}
    return "".join(escapes.get(ch, ch) for ch in text.replace("\r\n", "\n"))


def type_text(text: str, delay_ms: int = 22) -> None:
    from pywinauto.keyboard import send_keys
    # Send in small units so focus is verified throughout a long string.
    for ch in text.replace("\r\n", "\n"):
        assert_vroid_focused()
        send_keys(escape_text(ch), pause=delay_ms / 1000,
                  with_spaces=True, with_tabs=True, with_newlines=True)


_KEYS = {"return": "ENTER", "enter": "ENTER", "escape": "ESC", "esc": "ESC",
         "backspace": "BACK", "delete": "DELETE", "space": "SPACE",
         "pageup": "PGUP", "prior": "PGUP", "pagedown": "PGDN", "next": "PGDN",
         "ctrl": "VK_CONTROL", "control": "VK_CONTROL", "control_l": "VK_CONTROL",
         "shift": "VK_SHIFT", "shift_l": "VK_SHIFT", "alt": "VK_MENU",
         "alt_l": "VK_MENU", "super": "LWIN", "meta": "LWIN", "super_l": "LWIN"}


def key_name(name: str) -> str:
    from pywinauto.keyboard import CODES
    key = _KEYS.get(name.lower(), name.upper())
    if len(name) == 1:
        return escape_text(name)
    if key not in CODES:
        raise ValueError(f"Unknown key {name!r}")
    return "{" + key + "}"


def key(name: str, mods: list[str] | None = None, times: int = 1) -> None:
    from pywinauto.keyboard import send_keys
    sequence = key_name(name)
    modifier_keys = []
    for mod in mods or []:
        mapped = _KEYS.get(mod.lower())
        if mapped not in {"VK_CONTROL", "VK_SHIFT", "VK_MENU", "LWIN"}:
            raise ValueError(f"Unknown modifier {mod!r}")
        modifier_keys.append(mapped)
    for _ in range(times):
        assert_vroid_focused()
        try:
            # Keep the combination in one parsed sequence. Unity needs time
            # to observe held modifiers before the character event arrives.
            prefixes = {"VK_CONTROL": "^", "VK_SHIFT": "+", "VK_MENU": "%",
                        "LWIN": "{LWIN down}"}
            combo = "".join(prefixes[mod] for mod in modifier_keys) + sequence
            if "LWIN" in modifier_keys:
                combo += "{LWIN up}"
            send_keys(combo, pause=0.12, vk_packet=False)
        finally:
            for mod in reversed(modifier_keys):
                send_keys("{" + mod + " up}")
        time.sleep(0.06)


def find_save_dialog() -> int | None:
    main = _main_hwnd()
    if main is None:
        return None
    gui = _gui()
    dialogs = [hwnd for hwnd in _handles() if gui.IsWindowVisible(hwnd)
               and gui.IsWindowEnabled(hwnd) and gui.GetClassName(hwnd) == "#32770"
               and _owned(hwnd, main)]
    current = gui.GetForegroundWindow()
    if current in dialogs:
        return current
    if len(dialogs) > 1:
        raise RuntimeError("Multiple owned save dialogs found")
    return dialogs[0] if dialogs else None


def save_dialog(out_path: Path, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    dialog = None
    while time.monotonic() < deadline:
        dialog = find_save_dialog()
        if dialog:
            break
        time.sleep(0.25)
    if dialog is None:
        raise TimeoutError("Windows save dialog never appeared")
    _focus_handle(dialog)
    key("n", mods=["alt"])
    key("a", mods=["ctrl"])
    type_text(str(out_path.resolve()))
    key("Return")
    while time.monotonic() < deadline:
        if not _gui().IsWindow(dialog):
            return
        time.sleep(0.25)
    raise TimeoutError("Windows save dialog did not close; inspect whole_screen screenshot")
