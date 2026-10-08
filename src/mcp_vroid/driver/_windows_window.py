"""VRoid window management using process identity and Win32 HWNDs."""
from __future__ import annotations

import os
import time
from pathlib import Path

from ._models import Window
from . import _win32 as N

# Windows does not move the app onto a virtual desktop. For compatibility
# with the shared lifecycle API, enter/leave carry a previous foreground HWND.
WORKSPACE = 0
STEAM_APPID = "1486350"


def is_vroid_handle(hwnd: int) -> bool:
    seen = set()
    while hwnd and hwnd not in seen and N.IsWindow(hwnd):
        seen.add(hwnd)
        if Path(N.process_path(hwnd)).name.lower() == "vroidstudio.exe":
            return True
        hwnd = N.GetWindow(hwnd, 4)  # GW_OWNER: includes owned native dialogs
    return False


def _make(hwnd: int) -> Window:
    return Window(hex(hwnd), N.window_class(hwnd), N.window_text(hwnd),
                  *N.client_geometry(hwnd), WORKSPACE,
                  N.GetForegroundWindow() == hwnd, bool(N.IsZoomed(hwnd)))


def find_window() -> Window | None:
    for hwnd in N.enum_windows():
        if (not N.GetWindow(hwnd, 4)
                and Path(N.process_path(hwnd)).name.lower() == "vroidstudio.exe"
                and N.window_class(hwnd) != "#32770"):
            return _make(hwnd)
    return None


def save_dialog_window() -> Window | None:
    for hwnd in N.enum_windows():
        if N.window_class(hwnd) == "#32770" and is_vroid_handle(hwnd):
            # Common file dialogs have the filename edit/combo control. Do
            # not mistake an overwrite confirmation or error message for it.
            if N.filename_control(hwnd):
                return _make(hwnd)
    return None


def is_vroid_focused() -> bool:
    return is_vroid_handle(N.GetForegroundWindow())


def assert_vroid_focused() -> None:
    if not is_vroid_focused():
        hwnd = N.GetForegroundWindow()
        raise RuntimeError("refusing to act: focused window is not VRoid Studio "
                           f"(title={N.window_text(hwnd)!r})")


def launch() -> None:
    exe = os.environ.get("MCP_VROID_EXE")
    if exe:
        path = Path(exe).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"MCP_VROID_EXE does not point to a file: {path}")
        _shell_launch(str(path), str(path.parent))
    else:
        _shell_launch(f"steam://rungameid/{STEAM_APPID}")


def _shell_launch(target: str, directory: str = "") -> None:
    """Ask the existing Explorer process to launch outside the MCP Job Object.

    stdio clients put the server and its descendants in a kill-on-close job.
    A direct Popen would discard VRoid (and unsaved work) on disconnect.
    The desktop Shell.Application belongs to Explorer, so VRoid survives.
    """
    import pythoncom
    from win32com.client import Dispatch

    pythoncom.CoInitialize()
    try:
        desktop = Dispatch("Shell.Application").Windows().FindWindowSW(0, 0, 8, 0, 1)
        if desktop is None:
            raise RuntimeError("Windows Explorer desktop is unavailable; launch VRoid manually")
        desktop.Document.Application.ShellExecute(target, "", directory, "open", 1)
    finally:
        pythoncom.CoUninitialize()


def wait_for_window(timeout: float = 180.0, poll: float = 2.0) -> Window:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        win = find_window()
        if win and win.w > 200 and win.h > 200:
            return win
        time.sleep(poll)
    raise TimeoutError(f"VRoid Studio window did not appear within {timeout}s")


def launch_and_wait(timeout: float = 240.0) -> Window:
    win = find_window()
    if win is None:
        launch()
        win = wait_for_window(timeout)
    return win


def active_workspace() -> int:
    return WORKSPACE


def park(win: Window, workspace: int = WORKSPACE) -> None:
    pass


def enter(workspace: int = WORKSPACE) -> int:
    hwnd = N.GetForegroundWindow() or 0
    return 0 if is_vroid_handle(hwnd) else hwnd


def leave(prev: int) -> None:
    if prev and N.IsWindow(prev):
        if not N.SetForegroundWindow(prev):
            raise RuntimeError("Windows refused to restore the previous foreground window")


def dismiss_screensaver() -> bool:
    return False


def focus(win: Window | None = None) -> Window:
    win = win or find_window()
    if win is None:
        raise RuntimeError("VRoid Studio window not found")
    hwnd = int(win.address, 16)
    if not is_vroid_handle(hwnd):
        raise RuntimeError("VRoid Studio window is no longer valid")
    if N.IsIconic(hwnd):
        N.ShowWindow(hwnd, 9)  # SW_RESTORE
    # Preserve the file dialog; trying to focus its disabled owner makes
    # subsequent keystrokes land in the wrong place.
    target = N.GetForegroundWindow()
    if not is_vroid_handle(target):
        target = N.GetLastActivePopup(hwnd)
        if not N.IsWindowVisible(target):
            target = hwnd
        N.SetForegroundWindow(target)
    time.sleep(0.25)
    assert_vroid_focused()
    return find_window() or win


def fullscreen(win: Window | None = None) -> Window:
    win = focus(win)
    hwnd = int(win.address, 16)
    if N.IsWindowEnabled(hwnd) and not N.IsZoomed(hwnd):
        N.ShowWindow(hwnd, 3)  # SW_MAXIMIZE (client geometry excludes titlebar)
        time.sleep(0.6)
    assert_vroid_focused()
    return find_window() or win


def prepare(timeout: float = 240.0) -> tuple[Window, int]:
    prev = enter()
    return fullscreen(launch_and_wait(timeout)), prev


def terminate() -> None:
    win = find_window()
    if win is None:
        return
    hwnd = int(win.address, 16)
    handle = N.OpenProcess(0x1000 | 0x0001 | 0x00100000, False, N.process_id(hwnd))
    N.check(handle)
    try:
        # Re-check identity before killing the process behind this HWND.
        if not is_vroid_handle(hwnd):
            raise RuntimeError("VRoid Studio process is no longer valid")
        N.check(N.TerminateProcess(handle, 0))
        if N.WaitForSingleObject(handle, 10000) != 0:
            raise TimeoutError("VRoid Studio did not exit within 10 seconds")
    finally:
        N.CloseHandle(handle)
