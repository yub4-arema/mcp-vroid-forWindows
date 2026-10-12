"""Where the driver reads its helper binary and writes its artifacts.

Unlike the original spike (which kept everything next to the source tree),
an installed package must not scribble into site-packages, so every location
is overridable by environment variable and defaults to XDG state.

    MCP_VROID_CAPTURES  screenshots       default $XDG_STATE_HOME/mcp-vroid/captures
    MCP_VROID_OUT       exported files    default $XDG_STATE_HOME/mcp-vroid/out
    MCP_VROID_VPOINTER  the vpointer bin  default <repo>/native/vpointer, then $PATH
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent      # .../mcp_vroid
REPO = PACKAGE.parent.parent                          # .../<checkout>  (src layout)


def _state_home() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or
                    Path.home() / "AppData" / "Local")
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")


def tesseract_path() -> str | None:
    """An explicit override wins, even if invalid (never silently ignore it)."""
    override = os.environ.get("MCP_VROID_TESSERACT")
    if override:
        path = Path(override).expanduser()
        return str(path) if path.is_file() else shutil.which(override)
    found = shutil.which("tesseract")
    if found:
        return found
    if sys.platform == "win32":
        for root in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
            path = Path(root) / "Tesseract-OCR" / "tesseract.exe"
            if path.is_file():
                return str(path)
    return None


def tesseract_status() -> dict:
    path = tesseract_path()
    result = {"path": path, "present": bool(path), "eng": False}
    if path:
        try:
            probe = subprocess.run([path, "--list-langs"], capture_output=True,
                                   text=True, encoding="utf-8", timeout=5,
                                   creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            result["eng"] = probe.returncode == 0 and "eng" in probe.stdout.splitlines()
            if probe.returncode:
                result["error"] = probe.stderr.strip()
        except (OSError, subprocess.TimeoutExpired) as exc:
            result["error"] = str(exc)
    return result


def _dir(env: str, default: Path) -> Path:
    p = Path(os.environ.get(env) or default).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p


CAPTURES = _dir("MCP_VROID_CAPTURES", _state_home() / "mcp-vroid/captures")
OUT = _dir("MCP_VROID_OUT", _state_home() / "mcp-vroid/out")


def _find_vpointer() -> Path:
    env = os.environ.get("MCP_VROID_VPOINTER")
    if env:
        return Path(env).expanduser()
    for cand in (REPO / "native" / "vpointer", PACKAGE / "native" / "vpointer"):
        if cand.exists():
            return cand
    which = shutil.which("vpointer")
    if which:
        return Path(which)
    return REPO / "native" / "vpointer"          # reported in the error message


VPOINTER = _find_vpointer()
NATIVE = VPOINTER.parent
