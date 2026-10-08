"""Typed Win32 bindings. HWND/HANDLE and ULONG_PTR must be pointer-sized."""
from __future__ import annotations

import ctypes as ct
from ctypes import wintypes as wt

user32 = ct.WinDLL("user32", use_last_error=True)
kernel32 = ct.WinDLL("kernel32", use_last_error=True)


def _bind(dll, name, args, result):
    fn = getattr(dll, name)
    fn.argtypes, fn.restype = args, result
    return fn


WNDENUMPROC = ct.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
EnumWindows = _bind(user32, "EnumWindows", [WNDENUMPROC, wt.LPARAM], wt.BOOL)
EnumChildWindows = _bind(user32, "EnumChildWindows", [wt.HWND, WNDENUMPROC, wt.LPARAM], wt.BOOL)
IsWindow = _bind(user32, "IsWindow", [wt.HWND], wt.BOOL)
IsWindowVisible = _bind(user32, "IsWindowVisible", [wt.HWND], wt.BOOL)
IsWindowEnabled = _bind(user32, "IsWindowEnabled", [wt.HWND], wt.BOOL)
IsIconic = _bind(user32, "IsIconic", [wt.HWND], wt.BOOL)
IsZoomed = _bind(user32, "IsZoomed", [wt.HWND], wt.BOOL)
GetWindowTextW = _bind(user32, "GetWindowTextW", [wt.HWND, wt.LPWSTR, ct.c_int], ct.c_int)
GetClassNameW = _bind(user32, "GetClassNameW", [wt.HWND, wt.LPWSTR, ct.c_int], ct.c_int)
GetWindow = _bind(user32, "GetWindow", [wt.HWND, wt.UINT], wt.HWND)
GetForegroundWindow = _bind(user32, "GetForegroundWindow", [], wt.HWND)
GetLastActivePopup = _bind(user32, "GetLastActivePopup", [wt.HWND], wt.HWND)
GetDlgItem = _bind(user32, "GetDlgItem", [wt.HWND, ct.c_int], wt.HWND)
FindWindowExW = _bind(user32, "FindWindowExW", [wt.HWND, wt.HWND, wt.LPCWSTR, wt.LPCWSTR], wt.HWND)
GetDlgCtrlID = _bind(user32, "GetDlgCtrlID", [wt.HWND], ct.c_int)
GetParent = _bind(user32, "GetParent", [wt.HWND], wt.HWND)
GetWindowThreadProcessId = _bind(user32, "GetWindowThreadProcessId", [wt.HWND, ct.POINTER(wt.DWORD)], wt.DWORD)
GetClientRect = _bind(user32, "GetClientRect", [wt.HWND, ct.POINTER(wt.RECT)], wt.BOOL)
ClientToScreen = _bind(user32, "ClientToScreen", [wt.HWND, ct.POINTER(wt.POINT)], wt.BOOL)
ShowWindow = _bind(user32, "ShowWindow", [wt.HWND, ct.c_int], wt.BOOL)
SetForegroundWindow = _bind(user32, "SetForegroundWindow", [wt.HWND], wt.BOOL)
SetThreadDpiAwarenessContext = _bind(user32, "SetThreadDpiAwarenessContext", [wt.HANDLE], wt.HANDLE)
GetSystemMetrics = _bind(user32, "GetSystemMetrics", [ct.c_int], ct.c_int)
GetCursorPos = _bind(user32, "GetCursorPos", [ct.POINTER(wt.POINT)], wt.BOOL)
VkKeyScanW = _bind(user32, "VkKeyScanW", [wt.WCHAR], ct.c_short)
OpenProcess = _bind(kernel32, "OpenProcess", [wt.DWORD, wt.BOOL, wt.DWORD], wt.HANDLE)
CloseHandle = _bind(kernel32, "CloseHandle", [wt.HANDLE], wt.BOOL)
QueryFullProcessImageNameW = _bind(kernel32, "QueryFullProcessImageNameW", [wt.HANDLE, wt.DWORD, wt.LPWSTR, ct.POINTER(wt.DWORD)], wt.BOOL)
TerminateProcess = _bind(kernel32, "TerminateProcess", [wt.HANDLE, wt.UINT], wt.BOOL)
WaitForSingleObject = _bind(kernel32, "WaitForSingleObject", [wt.HANDLE, wt.DWORD], wt.DWORD)


class MOUSEINPUT(ct.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD),
                ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ct.c_size_t)]


class KEYBDINPUT(ct.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ct.c_size_t)]


class HARDWAREINPUT(ct.Structure):
    _fields_ = [("uMsg", wt.DWORD), ("wParamL", wt.WORD), ("wParamH", wt.WORD)]


class _InputUnion(ct.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ct.Structure):
    _anonymous_ = ("data",)
    _fields_ = [("type", wt.DWORD), ("data", _InputUnion)]


SendInput = _bind(user32, "SendInput", [wt.UINT, ct.POINTER(INPUT), ct.c_int], wt.UINT)


def check(ok):
    if not ok:
        raise ct.WinError(ct.get_last_error())


def ensure_dpi_awareness():
    # anyio invokes the driver on worker threads. Set the context on each
    # caller so geometry, ImageGrab and SendInput all use physical pixels.
    check(SetThreadDpiAwarenessContext(ct.c_void_p(-4)))  # PER_MONITOR_AWARE_V2


def desktop_geometry():
    ensure_dpi_awareness()
    return tuple(GetSystemMetrics(i) for i in (76, 77, 78, 79))


def window_text(hwnd):
    buf = ct.create_unicode_buffer(1024)
    GetWindowTextW(hwnd, buf, len(buf))
    return buf.value


def window_class(hwnd):
    buf = ct.create_unicode_buffer(256)
    GetClassNameW(hwnd, buf, len(buf))
    return buf.value


def process_id(hwnd):
    pid = wt.DWORD()
    GetWindowThreadProcessId(hwnd, ct.byref(pid))
    return pid.value


def process_path(hwnd):
    handle = OpenProcess(0x1000, False, process_id(hwnd))  # QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    try:
        buf, size = ct.create_unicode_buffer(32768), wt.DWORD(32768)
        return buf.value if QueryFullProcessImageNameW(handle, 0, buf, ct.byref(size)) else ""
    finally:
        CloseHandle(handle)


def enum_windows():
    windows = []

    @WNDENUMPROC
    def visit(hwnd, _):
        if IsWindowVisible(hwnd):
            windows.append(hwnd)
        return True

    check(EnumWindows(visit, 0))
    return windows


def client_geometry(hwnd):
    ensure_dpi_awareness()
    rect, origin = wt.RECT(), wt.POINT()
    check(GetClientRect(hwnd, ct.byref(rect)))
    check(ClientToScreen(hwnd, ct.byref(origin)))
    return origin.x, origin.y, rect.right - rect.left, rect.bottom - rect.top


def child_windows(hwnd):
    children = []

    @WNDENUMPROC
    def visit(child, _):
        children.append(child)
        return True

    EnumChildWindows(hwnd, visit, 0)
    return children


def filename_control(hwnd):
    """Find the filename Edit in classic and Explorer-style file dialogs.

    edt1/cmb13 may be nested in an Explorer child template. Modern dialogs
    also use an Edit with ID 1001 inside the filename ComboBox. Require that
    parent class so the search/address Edit cannot be mistaken for a filename.
    """
    children = child_windows(hwnd)
    candidates = [GetDlgItem(hwnd, control_id) for control_id in (0x480, 0x47C)]
    candidates += [child for child in children if GetDlgCtrlID(child) in (0x480, 0x47C)]
    for candidate in candidates:
        if not candidate:
            continue
        if window_class(candidate).lower() == "edit":
            return candidate
        for child in child_windows(candidate):
            if window_class(child).lower() == "edit":
                return child
    for child in children:
        if (GetDlgCtrlID(child) == 1001 and window_class(child).lower() == "edit"
                and window_class(GetParent(child)).lower() in ("combobox", "comboboxex32")):
            return child
    return None


def send(*events):
    if not events:
        return
    array = (INPUT * len(events))(*events)
    if SendInput(len(array), array, ct.sizeof(INPUT)) != len(array):
        raise RuntimeError("SendInput failed; run VRoid and the MCP server at the same "
                           "privilege level in an unlocked interactive Windows session "
                           f"(Win32 error {ct.get_last_error()})")


def keyboard(vk=0, scan=0, flags=0):
    return INPUT(type=1, ki=KEYBDINPUT(vk, scan, flags, 0, 0))


def mouse(flags, data=0, x=0, y=0):
    return INPUT(type=0, mi=MOUSEINPUT(x, y, data & 0xFFFFFFFF, flags, 0, 0))
