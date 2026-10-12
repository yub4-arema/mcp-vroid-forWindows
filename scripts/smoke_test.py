#!/usr/bin/env python3
"""Start the server over stdio, list its tools, and call the read-only ones.

Never touches VRoid: it calls vroid_status (no input, no OCR) and, only if
`--screenshot` is passed AND a VRoid window exists, one passive capture. No
clicks, no keys.

    uv run python scripts/smoke_test.py [--screenshot]
"""

from __future__ import annotations

import sys
import os
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters, stdio_client

REPO = Path(__file__).resolve().parent.parent


async def main(screenshot: bool) -> int:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_vroid"],
        cwd=str(REPO),
        env={k: v for k, v in os.environ.items() if k.startswith("MCP_VROID_")},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print(f"initialized: {init.server_info.name} {init.server_info.version}")

            tools = (await session.list_tools()).tools
            print(f"\n{len(tools)} tools:")
            for t in tools:
                first = (t.description or "").strip().splitlines()[0]
                print(f"  - {t.name}: {first}")
            expected = {"vroid_launch", "vroid_status", "vroid_release",
                        "vroid_screenshot", "vroid_find_text", "vroid_find_button",
                        "vroid_current_screen", "vroid_click", "vroid_drag",
                        "vroid_scroll", "vroid_type", "vroid_key",
                        "vroid_new_character", "vroid_open_tab", "vroid_set_slider",
                        "vroid_set_color", "vroid_export_vrm", "vroid_save_project"}
            if {t.name for t in tools} != expected:
                raise RuntimeError("MCP tool list changed")

            print("\nvroid_status:")
            res = await session.call_tool("vroid_status", {})
            for block in res.content:
                if getattr(block, "text", None):
                    print(block.text)
            if res.is_error:
                print("!! vroid_status returned an error")
                return 1

            present = bool((res.structured_content or {})
                           .get("window", {}).get("present"))
            if screenshot and present:
                print("\nvroid_screenshot (passive, no input):")
                shot = await session.call_tool("vroid_screenshot",
                                               {"tag": "smoke"})
                for block in shot.content:
                    kind = getattr(block, "type", "?")
                    if kind == "image":
                        print(f"  image: {len(block.data)} b64 chars, "
                              f"{block.mime_type}")
                    elif getattr(block, "text", None):
                        print("  " + block.text.replace("\n", "\n  "))
                if shot.is_error:
                    return 1
            elif screenshot:
                print("\nno VRoid window - skipping the screenshot check")
    print("\nsmoke test OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(anyio.run(main, "--screenshot" in sys.argv))
