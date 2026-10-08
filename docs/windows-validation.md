# Windows validation — 2026-10-08

Tested locally over real MCP stdio connections, using Python 3.11.5 (x64),
standalone VRoid Studio 2.14.0 and Tesseract with English traineddata.
High-level flows used VRoid's English UI. Captures covered client rectangles
of 1920×1171 and 3840×2126 physical pixels, with a capture scale of 1.0.
Only a newly created Fem test model was edited.

| Check | Observed result | Local evidence under `test-artifacts/` |
|---|---|---|
| MCP startup | Initialization, 18 registered tools, healthy Win32/Tesseract status | `scripts/smoke_test.py` output |
| OCR and creation | Start screen recognized, Create New located, Fem model created | `20261008-175302/report.json` |
| Body parameter | Head Size set to -0.100, confirmed visually | `20261008-175427/captures/006-body-parameter.png` |
| Project save | Native `.vroid` save succeeded | `20261008-180327/report.json` |
| VRM 1.0 export | 12,213,168-byte VRM, name WindowsTest, author mcp-vroid-test | `20261008-180426/report.json` |
| Unicode Save As | Saved Windowsテスト-日本語20261008.vroid; title contains the exact name | `20261008-181314/report.json` |
| Project reload | Japanese filename opened successfully; Head Size remained -0.100 | `20261008-182638/captures/004-reloaded-project.png` |
| Camera | Right drag visibly rotated the model | `20261008-181412/captures/002-camera-orbit.png` |
| Colour | Body Color changed from #FAEBDE to #F0D0C0, verified in the input box; Color and Dark Color restored and saved after the final OCR fix | `20261008-181703/captures/004-body-color-verified.png`, `20261008-183215/report.json` |
| Restart and release | New HWND, maximized window, previous foreground HWND restored | `20261008-181756/report.json` |
| MCP disconnect | A separate smoke connection still found the app and captured it after the launching connection exited | `scripts/smoke_test.py --screenshot` output |

The generated projects passed ZIP CRC checks, including model data and
thumbnail entries. The VRM's glTF 2 header and declared length matched the
file, and its JSON contained VRMC_vrm metadata, two meshes and 54 human bones.
These are structural checks; an independent VRM viewer was not tested.

## Regressions found and fixed

* A direct child-process launch was killed when MCP's Windows stdio Job
  Object closed. Launch now goes through the existing Explorer desktop COM
  object; the cold-start/disconnect test confirmed the app stays alive.
* Sending an entire key chord in one SendInput batch made Ctrl+Shift+S act
  as Save on an already saved model. Holding modifiers and the key separately
  produced Save As correctly. Mouse clicks likewise hold the button before
  releasing it. Both paths release input in `finally` blocks.
* OCR selected "color" in "Apply color when editing" instead of the Color
  setting. The colour flow now locates a real hex field and the label directly
  above it, matches the complete label row to distinguish Color from Dark
  Color, and tolerates OCR reading a zero as O. Tight label crops avoid
  blank space and partial swatches disrupting OCR. The subsequent screenshot
  showed the requested value.

Regression tests use mocked native input and never operate the desktop.
Windows result: 33 tests run, 32 passed, one Linux import test skipped.
The dependency lock check and wheel build passed; the wheel includes both
platform backends and excludes the local cache and test artifacts.

## Scope and remaining cases

Steam launch, VRM 0.0, Japanese high-level UI flows, actual negative-origin
multi-monitor input, and a live Linux desktop were not tested in this run.
Negative origins and focus guards have regression coverage. The CI workflow
is configured for Windows/Linux and Python 3.11/3.12; hosted CI has not been
run from this uncommitted checkout.

The forced restart displayed VRoid's first-run screens again. They were
completed and the UI returned to English before resuming tests. Complete
initial setup before using the high-level tools; `restart=true` forcibly
terminates VRoid and is intended only when losing unsaved state is acceptable.

Local screenshots, reports and generated models are ignored by Git. Use
`scripts/mcp_probe.py` with a reviewed JSON array of explicit MCP tool calls
to reproduce live tests; it sends real desktop input. Prefer
`scripts/smoke_test.py` for a passive startup check.
