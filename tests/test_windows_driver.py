"""Behavior checks; no real pointer or keyboard events are sent."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_artifacts = tempfile.TemporaryDirectory()
os.environ.setdefault("MCP_VROID_CAPTURES", str(Path(_artifacts.name) / "captures"))
os.environ.setdefault("MCP_VROID_OUT", str(Path(_artifacts.name) / "out"))

from PIL import Image
from mcp_vroid import session_env
from mcp_vroid.driver import actions, capture, input as inputs, locate, paths, window, windows


class Coordinates(unittest.TestCase):
    def test_physical_pixel_origin_and_crop(self):
        shot = capture.Shot(Image.new("RGB", (100, 80)), Path("shot.png"), 12, 35, 1)
        self.assertEqual(shot.to_layout(40, 10), (52, 45))
        self.assertEqual(shot.crop((20, 5, 90, 75)).to_layout(3, 4), (35, 44))

    def test_linux_scale_unchanged(self):
        shot = capture.Shot(Image.new("RGB", (125, 100)), Path("shot.png"), 30, 50, 1.25)
        self.assertEqual(shot.to_layout(50, 25), (70, 70))

    def test_capture_bbox_and_origin(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "shot.png"
            with patch("PIL.ImageGrab.grab", return_value=Image.new("RGB", (20, 30))) as grab:
                shot = windows.grab_region(10, 25, 20, 30, path)
            grab.assert_called_once_with(bbox=(10, 25, 30, 55), all_screens=True)
            self.assertEqual((shot.ox, shot.oy, shot.scale), (10, 25, 1))
            self.assertTrue(path.exists())

    def test_screen_geometry_is_virtual_screen(self):
        metrics = {76: -1920, 77: -200, 78: 4480, 79: 1640}
        win32api = MagicMock()
        win32api.GetSystemMetrics.side_effect = metrics.__getitem__
        with patch.dict("sys.modules", {"win32api": win32api}):
            self.assertEqual(windows.screen_geometry(), (-1920, -200, 4480, 1640))

    def test_double_click_preserves_image_space_and_button(self):
        shot = capture.Shot(Image.new("RGB", (100, 100)), Path("shot.png"), 12, 35, 1)
        with patch.object(window, "IS_WINDOWS", True), patch.object(inputs, "_guard"), \
                patch.object(windows, "click") as click, patch("time.sleep"):
            inputs.double_click(10, 20, space="image", shot=shot, button="right")
        click.assert_called_once_with(22, 55, "right", 3, double=True)


@unittest.skipUnless(os.name == "nt", "pywinauto input helpers require Windows")
class InputBehavior(unittest.TestCase):
    def test_focus_attachment_is_detached_after_failure(self):
        with patch.object(windows, "_gui") as gui, \
                patch("win32api.GetCurrentThreadId", return_value=10), \
                patch("win32process.GetWindowThreadProcessId", return_value=(20, 30)), \
                patch("win32process.AttachThreadInput") as attach:
            gui.return_value.SetForegroundWindow.side_effect = RuntimeError("refused")
            with self.assertRaisesRegex(RuntimeError, "refused to focus"):
                windows._focus_attached(50)
            self.assertEqual([c.args for c in attach.call_args_list],
                             [(10, 20, True), (10, 20, False)])

    def test_scroll_sign_and_horizontal_wheel(self):
        with patch.object(windows, "assert_vroid_focused"), \
                patch.object(windows, "_gui") as gui, \
                patch("pywinauto.mouse.scroll") as scroll, \
                patch("win32api.mouse_event") as event:
            gui.return_value.GetCursorPos.return_value = (50, 70)
            windows.scroll(3)
            scroll.assert_called_once_with(coords=(50, 70), wheel_dist=-3)
            windows.scroll(-2, horizontal=True)
            event.assert_called_once_with(0x1000, 0, 0, -240, 0)

    def test_key_aliases_and_real_shortcut_key(self):
        self.assertEqual(windows.key_name("Return"), "{ENTER}")
        self.assertEqual(windows.key_name("Escape"), "{ESC}")
        self.assertEqual(windows.key_name("Prior"), "{PGUP}")
        with patch.object(windows, "assert_vroid_focused"), \
                patch("pywinauto.keyboard.send_keys") as send, patch("time.sleep"):
            windows.key("s", mods=["ctrl", "shift"])
        self.assertEqual([c.args[0] for c in send.call_args_list],
                         ["^+s", "{VK_SHIFT up}", "{VK_CONTROL up}"])
        self.assertFalse(send.call_args_list[0].kwargs["vk_packet"])

    def test_literal_text_is_not_a_shortcut(self):
        from pywinauto.keyboard import parse_keys
        text = "a+^%~(){} 日本語"
        parsed = parse_keys(windows.escape_text(text), with_spaces=True)
        self.assertEqual(len(parsed), len(text))
        self.assertEqual("".join(a.key for a in parsed), text)
        self.assertTrue(all(a.down and a.up for a in parsed))

    def test_failed_shortcut_releases_modifiers(self):
        with patch.object(windows, "assert_vroid_focused"), \
                patch("pywinauto.keyboard.send_keys", side_effect=[OSError("input failed"), None, None]) as send:
            with self.assertRaises(OSError):
                windows.key("s", mods=["ctrl", "shift"])
        self.assertEqual([c.args[0] for c in send.call_args_list][-2:],
                         ["{VK_SHIFT up}", "{VK_CONTROL up}"])

    def test_newline_and_tab(self):
        self.assertEqual(windows.escape_text("a\r\nb\tc"), "a{ENTER}b{TAB}c")

    def test_unknown_key_fails_before_input(self):
        with patch("pywinauto.keyboard.send_keys") as send:
            with self.assertRaises(ValueError):
                windows.key("not-a-key")
            send.assert_not_called()

    def test_focus_refusal_sends_no_input(self):
        with patch.object(windows, "is_vroid_focused", return_value=False), \
                patch("pywinauto.keyboard.send_keys") as send, \
                patch("pywinauto.mouse.move") as move:
            with self.assertRaises(RuntimeError):
                windows.type_text("private text")
            with self.assertRaises(RuntimeError):
                windows.move(30, 50)
            send.assert_not_called()
            move.assert_not_called()

    def test_drag_releases_on_focus_loss(self):
        with patch.object(windows, "assert_vroid_focused"), \
                patch.object(windows, "move", side_effect=RuntimeError("lost focus")), \
                patch.object(windows, "_gui") as gui, \
                patch("pywinauto.mouse.press"), patch("pywinauto.mouse.release") as release, \
                patch("time.sleep"):
            gui.return_value.GetCursorPos.return_value = (3, 4)
            with self.assertRaises(RuntimeError):
                windows.drag(1, 2, 3, 4, "left", 24)
            release.assert_called_once_with(button="left", coords=(3, 4))


class WindowIdentity(unittest.TestCase):
    def test_refused_focus_does_not_inject_pointer_or_keys(self):
        gui = MagicMock()
        gui.GetForegroundWindow.return_value = 99
        with patch.object(windows, "_gui", return_value=gui), patch("time.sleep"), \
                patch.object(windows, "_focus_attached") as attach:
            with self.assertRaisesRegex(RuntimeError, "refused to focus"):
                windows._focus_handle(10)
        gui.SetForegroundWindow.assert_called_once_with(10)
        attach.assert_called_once_with(10)
    def test_title_alone_does_not_match(self):
        gui = MagicMock()
        gui.IsWindowVisible.return_value = True
        gui.GetWindow.return_value = 0
        gui.GetWindowText.return_value = "VRoid Studio - Chrome"
        with patch.object(windows, "_gui", return_value=gui), \
                patch.object(windows, "_handles", return_value=[10]), \
                patch.object(windows, "_pid", return_value=123), \
                patch.object(windows, "_process_path", return_value="C:/chrome.exe"):
            self.assertIsNone(windows._main_hwnd())

    def test_owner_chain_requires_same_process(self):
        gui = MagicMock()
        gui.GetWindow.side_effect = lambda hwnd, _: {30: 20, 20: 10}.get(hwnd, 0)
        with patch.object(windows, "_gui", return_value=gui), \
                patch.object(windows, "_pid", return_value=123):
            self.assertTrue(windows._owned(30, 10))
            self.assertFalse(windows._owned(40, 10))
        with patch.object(windows, "_gui", return_value=gui), \
                patch.object(windows, "_pid", side_effect=lambda hwnd: hwnd):
            self.assertFalse(windows._owned(30, 10))

    def test_active_modal_does_not_maximize_main(self):
        win = window.Window("10", "UnityWndClass", "VRoid Studio", 0, 0, 100, 100,
                            None, True)
        with patch.object(windows, "_active_target", return_value=20), \
                patch.object(windows, "_gui") as gui, \
                patch.object(windows, "focus", return_value=win):
            windows.fullscreen(win)
            gui.return_value.ShowWindow.assert_not_called()

    def test_release_ignores_reused_hwnd(self):
        with patch.object(windows, "_previous_window", (10, 123)), \
                patch.object(windows, "_remembered", True), \
                patch.object(windows, "_gui") as gui, \
                patch.object(windows, "_pid", return_value=456), \
                patch.object(windows, "_focus_handle") as focus:
            gui.return_value.IsWindow.return_value = True
            self.assertIsNone(windows.release()["restored_window"])
            focus.assert_not_called()


class ReleaseBehavior(unittest.TestCase):
    def test_release_survives_refused_focus(self):
        with patch.object(windows, "_previous_window", (10, 123)), \
                patch.object(windows, "_remembered", True), \
                patch.object(windows, "_gui") as gui, \
                patch.object(windows, "_pid", return_value=123), \
                patch.object(windows, "_focus_handle",
                             side_effect=RuntimeError("refused")):
            gui.return_value.IsWindow.return_value = True
            self.assertIsNone(windows.release()["restored_window"])
            self.assertIsNone(windows._previous_window)
            self.assertFalse(windows._remembered)


class LaunchBehavior(unittest.TestCase):
    def test_launch_defaults_to_steam(self):
        env = {k: v for k, v in os.environ.items() if k != "MCP_VROID_EXE"}
        with patch.dict(os.environ, env, clear=True), \
                patch("os.startfile", create=True) as start, \
                patch("subprocess.Popen") as popen:
            windows.launch()
        start.assert_called_once_with("steam://rungameid/1486350")
        popen.assert_not_called()

    def test_launch_uses_configured_exe(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / "VRoidStudio.exe"
            exe.touch()
            with patch.dict(os.environ, {"MCP_VROID_EXE": str(exe)}), \
                    patch("os.startfile", create=True) as start, \
                    patch("subprocess.DETACHED_PROCESS", 8, create=True), \
                    patch("subprocess.Popen") as popen:
                windows.launch()
            start.assert_not_called()
            popen.assert_called_once_with([str(exe)], cwd=str(exe.parent),
                                          creationflags=8)

    def test_launch_rejects_missing_exe(self):
        with patch.dict(os.environ, {"MCP_VROID_EXE": "C:/missing/VRoidStudio.exe"}), \
                patch("subprocess.Popen") as popen:
            with self.assertRaisesRegex(FileNotFoundError, "MCP_VROID_EXE"):
                windows.launch()
        popen.assert_not_called()


class WorkflowVerification(unittest.TestCase):
    def test_small_text_retry_is_windows_only(self):
        image = capture.Shot(Image.new("RGB", (2000, 1000)), Path("fields.png"), 0, 0, 1)
        captions = {"Name": locate.Match("Name", 95, 800, 400, 50, 20),
                    "Creators": locate.Match("Creators", 95, 800, 600, 70, 20)}
        def find_text(_, text, **kwargs):
            if text == "Settings":
                return locate.Match("Settings", 95, 970, 100, 60, 20)
            if text in captions:
                return [captions[text]]
            if text == "WindowsT" or (text == "mcp" and kwargs.get("upscale") == 4):
                return locate.Match(text, 60, 800, 620, 80, 20)
            return None
        for is_windows in (True, False):
            with self.subTest(windows=is_windows), \
                    patch.object(window, "IS_WINDOWS", is_windows), \
                    patch.object(actions, "shot", return_value=image), \
                    patch.object(locate, "find_text", side_effect=find_text) as find, \
                    patch.object(inputs, "click"), patch.object(inputs, "clear_field"), \
                    patch.object(inputs, "type_text"), patch("time.sleep"):
                if is_windows:
                    actions._fill_vrm_settings("WindowsTest", "mcp-vroid")
                else:
                    with self.assertRaisesRegex(RuntimeError, "Creators field did not take"):
                        actions._fill_vrm_settings("WindowsTest", "mcp-vroid")
                    self.assertFalse(any(c.kwargs.get("psm") == 7 for c in find.call_args_list))

    def test_existing_outputs_refuse_before_focus(self):
        import anyio
        from mcp_vroid import server
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "existing.vroid"
            target.write_bytes(b"keep")
            with patch.object(window, "IS_WINDOWS", True), \
                    patch.object(server, "_ensure_ready") as ready:
                with self.assertRaises(FileExistsError):
                    anyio.run(server.vroid_save_project, str(target.with_suffix("")))
                with self.assertRaises(FileExistsError):
                    anyio.run(server.vroid_export_vrm, str(target), "Test", "Tester")
                ready.assert_not_called()
            self.assertEqual(target.read_bytes(), b"keep")

    def test_export_format_requires_selected_radio(self):
        image = capture.Shot(Image.new("RGB", (2000, 1000)), Path("format.png"), 0, 0, 1)
        match = locate.Match("VRMO.O", 90, 900, 350, 70, 16)
        def find_text(_, label, **kwargs):
            self.assertTrue(kwargs["exact"])
            return match if label == "VRMO.O" else None
        with patch.object(actions, "shot", return_value=image), \
                patch.object(locate, "find_text", side_effect=find_text), \
                patch.object(locate, "find_color_blobs", return_value=[]), \
                patch.object(inputs, "click"), patch("time.sleep"):
            with self.assertRaisesRegex(RuntimeError, "radio was not selected"):
                actions.select_export_format("0.0")

    def test_unknown_export_version_rejected_before_input(self):
        with patch.object(actions, "shot") as shot, patch.object(inputs, "click") as click:
            with self.assertRaises(ValueError):
                actions.select_export_format("2.0")
            shot.assert_not_called()
            click.assert_not_called()


class EnvironmentAndFiles(unittest.TestCase):
    def test_windows_enabled_button_colors_exclude_disabled_gray(self):
        from mcp_vroid.driver import locate
        from PIL import ImageDraw
        image = Image.new("RGB", (300, 150), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((10, 10, 110, 40), fill=(0, 150, 250))
        draw.rectangle((10, 60, 110, 90), fill=(0, 125, 209))
        draw.rectangle((10, 110, 110, 140), fill=(180, 180, 180))
        with patch.object(locate.sys, "platform", "win32"):
            self.assertEqual(len(locate.find_color_blobs(image)), 2)
        with patch.object(locate.sys, "platform", "linux"):
            self.assertEqual(len(locate.find_color_blobs(image)), 1)

    def test_windows_skips_wayland_discovery(self):
        with patch.object(session_env.sys, "platform", "win32"), \
                patch.object(session_env, "ensure_windows_dpi") as dpi, \
                patch.object(session_env, "_runtime_dir") as runtime:
            self.assertEqual(session_env.ensure_session_env(), {})
            dpi.assert_called_once()
            runtime.assert_not_called()

    def test_linux_environment_still_restores_display(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(session_env.sys, "platform", "linux"), \
                    patch.dict(os.environ, {"XDG_RUNTIME_DIR": temp}, clear=True):
                result = session_env.ensure_session_env()
                self.assertIn("DISPLAY", result)

    def test_windows_state_home(self):
        with patch.object(paths.sys, "platform", "win32"), \
                patch.dict(os.environ, {"LOCALAPPDATA": "local-app-data"}):
            self.assertEqual(paths._state_home(), Path("local-app-data"))

    def test_tesseract_override_and_missing_override(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / "tesseract.exe"
            exe.touch()
            with patch.dict(os.environ, {"MCP_VROID_TESSERACT": str(exe)}):
                self.assertEqual(paths.tesseract_path(), str(exe))
            with patch.dict(os.environ, {"MCP_VROID_TESSERACT": str(exe) + "missing"}), \
                    patch.object(paths.shutil, "which", return_value=None):
                self.assertIsNone(paths.tesseract_path())

    def test_tesseract_standard_windows_location(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / "Tesseract-OCR" / "tesseract.exe"
            exe.parent.mkdir()
            exe.touch()
            with patch.dict(os.environ, {"ProgramFiles": temp}, clear=True), \
                    patch.object(paths.sys, "platform", "win32"), \
                    patch.object(paths.shutil, "which", return_value=None):
                self.assertEqual(paths.tesseract_path(), str(exe))

    def test_windows_existing_outputs_are_preserved(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(window, "IS_WINDOWS", True):
            for name, save in (("model.vrm", actions.export_vrm),
                               ("model.vroid", actions.save_project_as)):
                path = Path(temp) / name
                path.write_bytes(b"existing model")
                with patch.object(inputs, "hotkey") as key, patch.object(actions, "shot") as shot:
                    with self.assertRaises(FileExistsError):
                        save(path)
                    key.assert_not_called()
                    shot.assert_not_called()
                self.assertEqual(path.read_bytes(), b"existing model")

    def test_save_dialog_uses_native_path_and_waits_for_close(self):
        with patch.object(windows, "find_save_dialog", return_value=20), \
                patch.object(windows, "_focus_handle") as focus, \
                patch.object(windows, "key") as key, \
                patch.object(windows, "type_text") as type_text, \
                patch.object(windows, "_gui") as gui:
            gui.return_value.IsWindow.return_value = False
            path = Path("Japanese 日本語") / "model.vrm"
            windows.save_dialog(path)
            focus.assert_called_once_with(20)
            type_text.assert_called_once_with(str(path.resolve()))
            self.assertEqual([c.args[0] for c in key.call_args_list], ["n", "a", "Return"])

    def test_linux_capture_keeps_grim(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "shot.png"
            Image.new("RGB", (125, 100)).save(path)
            with patch.object(window, "IS_WINDOWS", False), \
                    patch.object(capture, "output_scale", return_value=1.25), \
                    patch.object(capture.subprocess, "run") as run:
                shot = capture.grab_region(0, 0, 100, 80, path=path)
                self.assertEqual(run.call_args.args[0][0], "grim")
                self.assertEqual(shot.scale, 1.25)


if __name__ == "__main__":
    unittest.main()
