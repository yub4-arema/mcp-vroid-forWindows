# Changelog

All notable changes to this project are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions
follow [semantic versioning](https://semver.org/).

## Unreleased

* Add native Windows window discovery, launch (Steam or `MCP_VROID_EXE`),
  focus/maximize and foreground restoration using typed Win32 APIs.
* Capture the client area with Pillow ImageGrab using physical pixels,
  including high-DPI and multiple monitors with negative origins.
* Add SendInput mouse, drag, wheel, hotkey and Unicode text support;
  identify VRoid by executable and allow its owned native dialogs.
* Handle native Windows save dialogs and paths for `.vrm` and `.vroid` files.
* Use LocalAppData for Windows outputs, discover Windows Tesseract installs,
  expose `MCP_VROID_TESSERACT`, and skip Unix session probing on Windows.
* Keep the Linux/Hyprland backend, restrict python-xlib to Linux, and declare
  the MCP 2 SDK required by the existing server imports.
* Document Windows setup and add Windows/Linux regression CI.
* Launch through Explorer so MCP stdio shutdown does not terminate VRoid.
* Hold clicks and keyboard chords long enough for Unity to observe them,
  releasing buttons/modifiers even when input is interrupted.
* Locate colour input boxes by their hex value to avoid matching checkbox
  captions containing the word "color".
* Validate the native editing/save/VRM 1.0 export flow on VRoid Studio 2.14.0.

## [0.1.0] — 2026-08-24

First public release.

### Added

* **MCP server** (`mcp-vroid`, stdio) exposing 18 tools over VRoid Studio:
  * lifecycle — `vroid_launch`, `vroid_status`, `vroid_release`
  * seeing — `vroid_screenshot`, `vroid_find_text`, `vroid_find_button`,
    `vroid_current_screen`
  * raw input — `vroid_click`, `vroid_drag`, `vroid_scroll`, `vroid_type`,
    `vroid_key`
  * flows — `vroid_new_character`, `vroid_open_tab`, `vroid_set_slider`,
    `vroid_set_color`, `vroid_export_vrm`, `vroid_save_project`
* **Driver engine** (`mcp_vroid.driver`): `grim` capture, tesseract OCR and
  OpenCV colour matching for locating, `hyprctl` for window management, and
  input through a `zwlr_virtual_pointer_unstable_v1` helper (pointer) plus
  X11 XTEST (keyboard and wheel).
* **`native/vpointer`** — a small C client for the Wayland virtual-pointer
  protocol, built by `native/build.sh`. Moves the real compositor cursor and
  needs no `/dev/uinput` access.
* **Session-environment recovery** so the server works when an MCP client
  launches it with a sanitised environment.
* **Focus guard** — every acting tool refuses to run unless VRoid Studio is
  the focused window; the idle screensaver is dismissed rather than typed
  into.
* **`vroid-driver` CLI** for driving the same engine from a shell.
* `scripts/smoke_test.py` — starts the server, lists tools, calls the
  read-only ones; never sends input.
* Documentation: README, [`docs/ui-map.md`](docs/ui-map.md).

### Known limitations

Calibrated against VRoid Studio 2.14.0 (English) at 2560×1440 / scale 1.25 on
Hyprland. See the README's *Limitations and brittleness* section.

[0.1.0]: https://github.com/nhodges/mcp-vroid/releases/tag/v0.1.0
