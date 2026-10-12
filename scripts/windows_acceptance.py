"""Opt-in attended Windows acceptance checks against the installed Steam app.

Creates a disposable model and outputs under out/windows-acceptance by default.
Run phases in order; each connects through the same public MCP tools as clients.
Never restarts VRoid; Save As and export reject existing targets.
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import sys
import time
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters, stdio_client

REPO = Path(__file__).resolve().parent.parent


def validate_vrm(path: Path, version: str, avatar_name: str | None = None,
                 creator: str | None = None) -> dict:
    data = path.read_bytes()
    magic, glb_version, length = struct.unpack_from("<4sII", data)
    if magic != b"glTF" or glb_version != 2 or length != len(data):
        raise RuntimeError(f"Invalid GLB file: {path}")
    chunk_length, chunk_type = struct.unpack_from("<II", data, 12)
    if chunk_type != 0x4E4F534A:
        raise RuntimeError("GLB has no first JSON chunk")
    doc = json.loads(data[20:20 + chunk_length])
    extension = "VRMC_vrm" if version == "1.0" else "VRM"
    if extension not in doc.get("extensions", {}):
        raise RuntimeError(f"Missing {extension} in {path}")
    spec = doc["extensions"][extension].get("specVersion")
    if spec != version:
        raise RuntimeError(f"Expected VRM {version}, got specVersion={spec!r}")
    meta = doc["extensions"][extension].get("meta", {})
    name_key = "name" if version == "1.0" else "title"
    if avatar_name is not None and meta.get(name_key) != avatar_name:
        raise RuntimeError(f"Unexpected avatar metadata: {meta!r}")
    authors = meta.get("authors", []) if version == "1.0" else [meta.get("author")]
    if creator is not None and creator not in authors:
        raise RuntimeError(f"Unexpected creator metadata: {meta!r}")
    return {"bytes": len(data), "extension": extension, "spec_version": spec,
            "meta": meta}


async def main(phase: str, out: Path, wait_foreground: bool = False,
               expected_dpi: int | None = None) -> None:
    if sys.platform != "win32":
        raise RuntimeError("This attended acceptance script is Windows-only")
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if wait_foreground:
        from mcp_vroid.driver import windows
        import ctypes
        print(f"Waiting up to 300 seconds for manual VRoid focus (DPI={expected_dpi})", flush=True)
        deadline = time.monotonic() + 300
        while True:
            win = windows.find_window()
            dpi = ctypes.windll.user32.GetDpiForWindow(int(win.address)) if win else None
            if (windows.is_vroid_focused() and
                    (expected_dpi is None or dpi == expected_dpi)):
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("Bring VRoid forward at the requested DPI before running the check")
            await anyio.sleep(0.5)
    env = {k: v for k, v in os.environ.items() if k.startswith("MCP_VROID_")}
    env.setdefault("MCP_VROID_CAPTURES", str(REPO / "captures"))
    env.setdefault("MCP_VROID_OUT", str(REPO / "out"))
    params = StdioServerParameters(command=sys.executable, args=["-m", "mcp_vroid"],
                                  cwd=str(REPO), env=env)
    report = []
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            async def call(tool_name: str, **kwargs):
                print(f"Calling {tool_name} {kwargs}", flush=True)
                result = await session.call_tool(tool_name, kwargs)
                texts = [c.text for c in result.content if getattr(c, "text", None)]
                report.append({"tool": tool_name, "arguments": kwargs,
                               "error": result.is_error, "text": texts,
                               "result": result.structured_content})
                print("\n".join(texts), flush=True)
                if result.is_error:
                    raise RuntimeError(f"{tool_name} failed")
                if result.structured_content is not None:
                    return result.structured_content
                # Image tools return metadata as a JSON text block alongside
                # image content, rather than structured_content.
                for block in reversed(texts):
                    try:
                        return json.loads(block)
                    except json.JSONDecodeError:
                        continue
                return None

            async def wait_screen(expected: str):
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    if (await call("vroid_current_screen"))["screen"] == expected:
                        return
                    await anyio.sleep(1)
                raise TimeoutError(f"VRoid did not show {expected}")

            async def editor():
                if (await call("vroid_current_screen"))["screen"] == "export_vrm":
                    capture = await call("vroid_screenshot", tag="return-to-editor")
                    size = capture["image_size"]
                    settings = await call("vroid_find_text", query="Settings", exact=True)
                    if settings["matches"]:
                        for _ in range(8):
                            await call("vroid_scroll", dy=10, x=size["w"] / 2,
                                       y=size["h"] * 0.62)
                            cancel = await call("vroid_find_text", query="Cancel", exact=True)
                            if cancel["matches"]:
                                target = cancel["matches"][0]
                                await call("vroid_click", x=target["x"], y=target["y"])
                                break
                        else:
                            raise RuntimeError("Could not close the previous VRM Settings dialog")
                    from mcp_vroid.driver import windows
                    close_xy = windows.window_dpi() / 4
                    await call("vroid_click", x=close_xy, y=close_xy)
                    await wait_screen("editor")

            try:
                await call("vroid_launch")
                if phase == "create":
                    await call("vroid_new_character", base="Fem")
                elif phase == "edit":
                    await call("vroid_open_tab", name="Body")
                    await call("vroid_set_slider", label="Head Size", value=-0.15)
                elif phase == "color":
                    await call("vroid_open_tab", name="Body")
                    await call("vroid_set_color", label="Light Color", hex="#FFEEDD")
                    if (out / "model.vroid").exists():
                        await call("vroid_save_project")
                elif phase == "save":
                    await call("vroid_save_project", name=str(out / "model.vroid"))
                elif phase in ("export10", "export00"):
                    await editor()
                    version = "1.0" if phase == "export10" else "0.0"
                    path = out / f"model-{version}.vrm"
                    await call("vroid_export_vrm", path=str(path), avatar_name="WindowsTest",
                               creator="mcp-vroid", version=version)
                    validation = validate_vrm(path, version, "WindowsTest", "mcp-vroid")
                    report.append({"vrm_validation": validation})
                    print(json.dumps(validation, ensure_ascii=True), flush=True)
                elif phase == "reopen":
                    screen = (await call("vroid_current_screen"))["screen"]
                    if screen == "unknown":
                        await wait_screen("start")
                        screen = "start"
                    if screen != "start":
                        await editor()
                        await call("vroid_save_project")
                        capture = await call("vroid_screenshot", tag="before-reopen")
                        size = capture["image_size"]
                        await call("vroid_click", x=size["w"] * 29 / 2560,
                                   y=size["h"] * 23 / 1440)
                        matches = await call("vroid_find_text", query="selection", exact=True)
                        target = matches["matches"][0]
                        await call("vroid_click", x=target["x"], y=target["y"])
                    await wait_screen("start")
                    matches = await call("vroid_find_text", query="Open", exact=True)
                    target = max(matches["matches"], key=lambda m: m["x"])
                    await call("vroid_click", x=target["x"], y=target["y"])
                    await anyio.sleep(1)
                    await call("vroid_key", combo="alt+n")
                    await call("vroid_type", text=str(out / "model.vroid"), clear_first=True)
                    await call("vroid_key", combo="Return")
                    await wait_screen("editor")
                    await call("vroid_open_tab", name="Body")
                    for value in ("-0.150", "FFEEDD"):
                        matches = await call("vroid_find_text", query=value)
                        if not matches["matches"]:
                            raise RuntimeError(f"Reopened model did not retain {value}")
                elif phase == "alignment":
                    await editor()
                    # OCR produces native capture pixels; verify those positions
                    # through actual tab clicks, then inspect the returned frames.
                    for name in ("Face", "Body"):
                        await call("vroid_open_tab", name=name)
                    from mcp_vroid.driver import windows
                    import ctypes
                    dpi = ctypes.windll.user32.GetDpiForWindow(int(windows.find_window().address))
                    if expected_dpi is not None and dpi != expected_dpi:
                        raise RuntimeError(f"Expected DPI {expected_dpi}, got {dpi}")
                    report.append({"dpi": dpi, "display_scale_percent": dpi * 100 / 96})
                await call("vroid_screenshot", tag=f"acceptance-{phase}")
            except Exception:
                try:
                    await call("vroid_screenshot", tag=f"failed-{phase}", whole_screen=True)
                except Exception:
                    pass
                raise
            finally:
                suffix = f"-{dpi}" if phase == "alignment" and "dpi" in locals() else ""
                (out / f"report-{phase}{suffix}.json").write_text(
                    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                await call("vroid_release")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["create", "edit", "color", "save", "export10", "export00",
                                         "reopen", "alignment"])
    parser.add_argument("--out", type=Path,
                        default=REPO / "out" / "windows-acceptance" / "日本語 models")
    parser.add_argument("--wait-foreground", action="store_true",
                        help="Wait for manual focus before using the public MCP tools")
    parser.add_argument("--dpi", type=int, help="Expected window DPI: 96/120/144 for 100/125/150%%")
    args = parser.parse_args()
    anyio.run(main, args.phase, args.out, args.wait_foreground, args.dpi)
