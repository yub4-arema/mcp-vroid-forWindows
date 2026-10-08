"""Win32 regressions. All SendInput calls are mocked; no desktop input."""
import ctypes as ct
import os
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from PIL import Image

if sys.platform == "win32":
    from mcp_vroid.driver import _win32 as N, _windows_input as I, _windows_window as W
    from mcp_vroid.driver import actions as A, capture as C
    from mcp_vroid.driver._models import Window


@unittest.skipUnless(sys.platform == "win32", "requires Win32")
class WindowsTests(unittest.TestCase):
    def test_input_abi_size(self):
        self.assertEqual(ct.sizeof(N.INPUT), 40 if ct.sizeof(ct.c_void_p) == 8 else 28)

    def test_virtual_desktop_coordinates(self):
        geometry = (-1920, -200, 3840, 1400)
        self.assertEqual(I._absolute(-1920, -200, geometry), (0, 0))
        self.assertEqual(I._absolute(1919, 1199, geometry), (65535, 65535))
        with self.assertRaises(ValueError):
            I._absolute(1920, 100, geometry)

    def test_unicode_surrogate_pairs(self):
        events = I._unicode_events("土😀")
        self.assertEqual([e.ki.wScan for e in events], [0x571F, 0x571F, 0xD83D, 0xD83D, 0xDE00, 0xDE00])
        self.assertEqual([e.ki.dwFlags for e in events], [4, 6, 4, 6, 4, 6])
        self.assertTrue(all(e.ki.wVk == 0 for e in events))

    def test_browser_title_does_not_grant_focus(self):
        with patch.object(N, "GetForegroundWindow", return_value=1), patch.object(N, "IsWindow", return_value=True), patch.object(N, "process_path", return_value="C:/Chrome/chrome.exe"), patch.object(N, "GetWindow", return_value=0), patch.object(N, "window_text", return_value="VRoid Studio - Chrome"):
            self.assertFalse(W.is_vroid_focused())
            with self.assertRaisesRegex(RuntimeError, "refusing to act"):
                W.assert_vroid_focused()

    def test_owned_dialog_allowed(self):
        with patch.object(N, "IsWindow", return_value=True), patch.object(N, "process_path", side_effect=lambda hwnd: "C:/VRoid/VRoidStudio.exe" if hwnd == 10 else "C:/Windows/dialog.exe"), patch.object(N, "GetWindow", side_effect=lambda hwnd, _: 10 if hwnd == 20 else 0):
            self.assertTrue(W.is_vroid_handle(20))

    def test_guard_blocks_every_input_kind(self):
        calls = [lambda: I.move(0, 0, space="layout"), lambda: I.click(0, 0),
                 lambda: I.drag(0, 0, 10, 10), lambda: I.scroll(1),
                 lambda: I.hscroll(1), lambda: I.type_text("test"), lambda: I.key("Return")]
        with patch.object(I.W, "assert_vroid_focused", side_effect=RuntimeError("blocked")), patch.object(N, "send") as send:
            for call in calls:
                with self.assertRaises(RuntimeError):
                    call()
            send.assert_not_called()

    def test_double_click_retains_shot_and_button(self):
        shot = object()
        with patch.object(I, "click") as click:
            I.double_click(3, 4, button="right", space="image", shot=shot)
        for call in click.call_args_list:
            self.assertEqual(call.kwargs["button"], "right")
            self.assertEqual(call.kwargs["space"], "image")
            self.assertIs(call.kwargs["shot"], shot)

    def test_drag_releases_on_focus_loss(self):
        with patch.object(I, "_guard"), patch.object(I, "_resolve", side_effect=[(0, 0), (20, 20)]), patch.object(N, "desktop_geometry", return_value=(0, 0, 100, 100)), patch.object(I, "_move", side_effect=[None, RuntimeError("focus lost")]), patch.object(N, "send") as send, patch.object(I.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "focus lost"):
                I.drag(0, 0, 20, 20)
            self.assertEqual(send.call_args_list[0].args[0].mi.dwFlags, 2)
            self.assertEqual(send.call_args_list[-1].args[0].mi.dwFlags, 4)

    def test_click_releases_if_hold_is_interrupted(self):
        with patch.object(I, "_guard"), patch.object(I, "_resolve", return_value=(10, 10)), patch.object(N, "ensure_dpi_awareness"), patch.object(N, "GetCursorPos", return_value=True), patch.object(I, "_move"), patch.object(N, "send") as send, patch.object(I.time, "sleep", side_effect=[None, None, RuntimeError("interrupted")]):
            with self.assertRaisesRegex(RuntimeError, "interrupted"):
                I.click(10, 10, moves=1)
        self.assertEqual([call.args[0].mi.dwFlags for call in send.call_args_list], [2, 4])

    def test_scroll_sign(self):
        with patch.object(I, "_guard"), patch.object(N, "send") as send, patch.object(I.time, "sleep"):
            I.scroll(1)
            self.assertEqual(send.call_args.args[0].mi.mouseData, (-120) & 0xFFFFFFFF)
            I.hscroll(1)
            self.assertEqual(send.call_args.args[0].mi.mouseData, 120)

    def test_shortcut_holds_modifiers_until_key_release(self):
        with patch.object(I, "_guard"), patch.object(N, "send") as send, patch.object(I.time, "sleep") as sleep:
            I.hotkey("ctrl+shift+s")
        events = [[(e.ki.wVk, e.ki.dwFlags) for e in call.args] for call in send.call_args_list]
        self.assertEqual(events, [[(17, 0), (16, 0)], [(83, 0)], [(83, 2), (16, 2), (17, 2)]])
        self.assertIn(unittest.mock.call(0.03), sleep.call_args_list)
        self.assertIn(unittest.mock.call(0.05), sleep.call_args_list)

    def test_shortcut_releases_on_focus_loss(self):
        with patch.object(I, "_guard", side_effect=[None, RuntimeError("focus lost")]), patch.object(N, "send") as send, patch.object(I.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "focus lost"):
                I.hotkey("ctrl+shift+s")
        self.assertEqual([(e.ki.wVk, e.ki.dwFlags) for e in send.call_args_list[-1].args],
                         [(83, 2), (16, 2), (17, 2)])

    def test_native_save_path(self):
        target = Path("C:/Users/test/モデル.vrm")
        self.assertEqual(A.to_wine_path(target), str(target.resolve()))
        self.assertFalse(A.to_wine_path(target).startswith("Z:"))

    def test_native_capture_origin(self):
        with tempfile.TemporaryDirectory() as td, patch.object(N, "ensure_dpi_awareness"), patch("PIL.ImageGrab.grab", return_value=Image.new("RGB", (100, 50))) as grab:
            shot = C.grab_region(-100, -50, 100, 50, path=Path(td) / "shot.png")
            grab.assert_called_once_with(bbox=(-100, -50, 0, 0), all_screens=True)
            self.assertEqual(shot.to_layout(25, 20), (-75, -30))
            self.assertEqual(shot.scale, 1.0)

    def test_send_failure_is_explicit(self):
        with patch.object(N, "SendInput", return_value=0), self.assertRaisesRegex(RuntimeError, "privilege level"):
            N.send(N.keyboard(vk=13))

    def test_native_save_dialog_uses_filename_control(self):
        win = Window("0x10", "#32770", "Save", 0, 0, 300, 200, 0, True)
        with ExitStack() as stack:
            stack.enter_context(patch.object(A, "_save_dialog_window", return_value=win))
            stack.enter_context(patch.object(A.W, "focus"))
            stack.enter_context(patch.object(N, "filename_control", return_value=32))
            stack.enter_context(patch.object(N, "client_geometry", return_value=(100, 200, 400, 20)))
            stack.enter_context(patch.object(N, "IsWindow", return_value=False))
            click = stack.enter_context(patch.object(A.I, "click"))
            stack.enter_context(patch.object(A.I, "clear_field"))
            text = stack.enter_context(patch.object(A.I, "type_text"))
            key = stack.enter_context(patch.object(A.I, "key"))
            target = Path("C:/exports/avatar.vrm")
            A._windows_save_dialog(target, 1)
            click.assert_called_once_with(300.0, 210.0, space="layout")
            text.assert_called_once_with(str(target.resolve()))
            key.assert_called_once_with("Return")

    def test_foreground_dialog_is_preserved(self):
        win = Window("0x10", "UnityWndClass", "VRoid", 0, 0, 100, 100, 0, True)
        with patch.object(W, "is_vroid_handle", return_value=True), patch.object(N, "IsIconic", return_value=False), patch.object(N, "GetForegroundWindow", return_value=32), patch.object(N, "SetForegroundWindow") as focus, patch.object(W, "assert_vroid_focused"), patch.object(W, "find_window", return_value=win), patch.object(W.time, "sleep"):
            W.focus(win)
            focus.assert_not_called()

    def test_nested_filename_control(self):
        with patch.object(N, "child_windows", side_effect=lambda hwnd: [20, 30] if hwnd == 10 else [30]), patch.object(N, "GetDlgItem", return_value=0), patch.object(N, "GetDlgCtrlID", side_effect=lambda hwnd: 0x47C if hwnd == 20 else 1001), patch.object(N, "window_class", side_effect=lambda hwnd: "Edit" if hwnd == 30 else "ComboBoxEx32"):
            self.assertEqual(N.filename_control(10), 30)

    def test_modern_filename_control_and_search_rejection(self):
        with patch.object(N, "child_windows", return_value=[30]), patch.object(N, "GetDlgItem", return_value=0), patch.object(N, "GetDlgCtrlID", return_value=1001), patch.object(N, "GetParent", return_value=20), patch.object(N, "window_class", side_effect=lambda hwnd: "Edit" if hwnd == 30 else "ComboBox"):
            self.assertEqual(N.filename_control(10), 30)
        with patch.object(N, "child_windows", return_value=[30]), patch.object(N, "GetDlgItem", return_value=0), patch.object(N, "GetDlgCtrlID", return_value=1001), patch.object(N, "GetParent", return_value=20), patch.object(N, "window_class", side_effect=lambda hwnd: "Edit" if hwnd == 30 else "SearchBox"):
            self.assertIsNone(N.filename_control(10))

    def test_other_apps_save_dialog_is_ignored(self):
        with patch.object(N, "enum_windows", return_value=[20]), patch.object(N, "window_class", return_value="#32770"), patch.object(W, "is_vroid_handle", return_value=False), patch.object(N, "filename_control") as filename:
            self.assertIsNone(W.save_dialog_window())
            filename.assert_not_called()

    def test_standalone_launch_preserves_spaces(self):
        with tempfile.TemporaryDirectory(prefix="VRoid Studio ") as td:
            exe = Path(td) / "VRoidStudio.exe"
            exe.touch()
            with patch.dict(os.environ, {"MCP_VROID_EXE": str(exe)}), patch.object(W, "_shell_launch") as launch:
                W.launch()
                launch.assert_called_once_with(str(exe.resolve()), str(exe.parent))

    def test_launch_uses_explorer_broker_and_releases_com(self):
        import pythoncom
        from unittest.mock import Mock
        shell = Mock()
        with patch.object(pythoncom, "CoInitialize") as init, patch.object(pythoncom, "CoUninitialize") as cleanup, patch("win32com.client.Dispatch", return_value=shell):
            W._shell_launch("C:/VRoid Studio/VRoidStudio.exe", "C:/VRoid Studio")
            shell.Windows.return_value.FindWindowSW.assert_called_once_with(0, 0, 8, 0, 1)
            shell.Windows.return_value.FindWindowSW.return_value.Document.Application.ShellExecute.assert_called_once_with("C:/VRoid Studio/VRoidStudio.exe", "", "C:/VRoid Studio", "open", 1)
            init.assert_called_once()
            cleanup.assert_called_once()

    def test_launch_without_explorer_never_creates_a_child_process(self):
        import pythoncom
        from unittest.mock import Mock
        shell = Mock()
        shell.Windows.return_value.FindWindowSW.return_value = None
        with patch.object(pythoncom, "CoInitialize"), patch.object(pythoncom, "CoUninitialize") as cleanup, patch("win32com.client.Dispatch", return_value=shell):
            with self.assertRaisesRegex(RuntimeError, "Explorer desktop is unavailable"):
                W._shell_launch("steam://rungameid/1486350")
            cleanup.assert_called_once()


if __name__ == "__main__":
    unittest.main()
