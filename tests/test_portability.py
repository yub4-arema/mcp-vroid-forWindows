"""Platform-independent regression tests; never inject desktop input."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from mcp_vroid import session_env
from mcp_vroid.driver import actions, capture, locate, paths


class PortabilityTests(unittest.TestCase):
    def test_windows_session_does_not_probe_unix(self):
        with patch.object(session_env.sys, "platform", "win32"), patch.object(session_env, "_runtime_dir") as probe:
            self.assertEqual(session_env.ensure_session_env(), {})
            probe.assert_not_called()

    def test_windows_state_home(self):
        with patch.object(paths.sys, "platform", "win32"), patch.dict(os.environ, {"LOCALAPPDATA": "C:/Users/test/AppData/Local"}):
            self.assertEqual(paths._state_home(), Path("C:/Users/test/AppData/Local"))

    def test_tesseract_override(self):
        with patch.dict(os.environ, {"MCP_VROID_TESSERACT": "C:/OCR/tesseract.exe"}):
            self.assertEqual(paths.tesseract_command(), str(Path("C:/OCR/tesseract.exe")))

    def test_crop_coordinates_with_negative_desktop_origin(self):
        shot = capture.Shot(Image.new("RGB", (200, 100)), Path("test.png"), -1920, -200, 1.0)
        self.assertEqual(shot.to_layout(100, 50), (-1820, -150))
        self.assertEqual(shot.crop((20, 10, 120, 60)).to_layout(5, 5), (-1895, -185))

    def test_linux_capture_keeps_scale(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "capture.png"
            Image.new("RGB", (250, 125)).save(target)
            with patch.object(capture.sys, "platform", "linux"), patch.object(capture, "output_scale", return_value=1.25), patch.object(capture.subprocess, "run") as run:
                shot = capture.grab_region(10, 20, 200, 100, path=target)
            self.assertEqual(shot.scale, 1.25)
            self.assertEqual(shot.to_layout(125, 50), (110, 60))
            self.assertEqual(run.call_args.args[0][0], "grim")

    def test_ocr_failure_is_reported(self):
        failure = subprocess.CalledProcessError(1, "tesseract", stderr="missing eng data")
        with patch.object(locate.subprocess, "run", side_effect=failure), self.assertRaises(subprocess.CalledProcessError):
            locate.ocr_words(Image.new("RGB", (40, 40)))

    def test_color_field_search_excludes_checkbox_caption(self):
        shot = capture.Shot(Image.new("RGB", (3840, 2126)), Path("test.png"), 0, 34, 1.0)
        # Measured UI positions: checkbox word 'color' at y=226, setting
        # label at y=303, and its hex value at (3678, 351).
        field = locate.Match("#FAEBDE", 96, 136, 282, 96, 12)
        label = locate.Match("Color", 96, 175, 30, 47, 14)
        with patch.object(locate, "ocr_words", side_effect=[[field], [label]]) as ocr:
            match = actions._find_color_field(shot, "Color")
        self.assertEqual(match.center, (3678, 351))
        self.assertEqual(ocr.call_args_list[1].args[0].height, 61)

    def test_color_does_not_match_dark_color_and_handles_ocr_zero(self):
        shot = capture.Shot(Image.new("RGB", (3840, 2126)), Path("test.png"), 0, 34, 1.0)
        fields = [locate.Match("#FODOCO", 96, 136, 282, 96, 12),
                  locate.Match("#FAEBDE", 99, 136, 402, 96, 12)]
        color = [locate.Match("Color", 96, 810, 30, 47, 14)]
        dark = [locate.Match("Dark", 99, 810, 30, 47, 14),
                locate.Match("Color", 99, 860, 30, 47, 14)]
        with patch.object(locate, "ocr_words", side_effect=[fields, color]):
            self.assertEqual(actions._find_color_field(shot, "Color").center, (3678, 351))
        with patch.object(locate, "ocr_words", side_effect=[fields, color, dark]):
            self.assertEqual(actions._find_color_field(shot, "Dark Color").center, (3678, 471))

    def test_color_flow_refuses_to_target_caption_without_hex_field(self):
        shot = capture.Shot(Image.new("RGB", (3840, 2126)), Path("test.png"), 0, 34, 1.0)
        with patch.object(locate, "ocr_words", return_value=[locate.Match("Color", 99, 10, 10, 47, 14)]), patch.object(actions, "_find_label") as label:
            self.assertIsNone(actions._find_color_field(shot, "Color"))
            label.assert_not_called()

    def test_linux_backend_imports_without_win32(self):
        if sys.platform == "win32":
            self.skipTest("Linux import checked on Linux CI")
        from mcp_vroid.driver import window, input
        self.assertEqual(window.find_window.__module__, "mcp_vroid.driver._linux_window")
        self.assertEqual(input.key.__module__, "mcp_vroid.driver._linux_input")


if __name__ == "__main__":
    unittest.main()
