"""Run an explicit JSON list of MCP calls and retain live-test evidence.

Unlike smoke_test.py, this can send input. Review the actions file before
running it. Stops at the first tool error and captures the resulting screen.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters, stdio_client

REPO = Path(__file__).resolve().parent.parent


def summarize(result):
    return {"is_error": bool(result.is_error),
            "structured_content": result.structured_content,
            "content": [{"type": block.type, "text": block.text}
                        if getattr(block, "text", None) is not None else
                        {"type": block.type, "mime_type": getattr(block, "mime_type", None)}
                        for block in result.content]}


async def run(args):
    actions = json.loads(Path(args.actions).read_text(encoding="utf-8-sig"))
    evidence = REPO / "test-artifacts" / datetime.now().strftime("%Y%m%d-%H%M%S")
    evidence.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["MCP_VROID_CAPTURES"] = str(evidence / "captures")
    env["MCP_VROID_OUT"] = str(REPO / "test-artifacts" / "out")
    if args.exe:
        env["MCP_VROID_EXE"] = args.exe
    params = StdioServerParameters(command=sys.executable, args=["-m", "mcp_vroid"],
                                   cwd=str(REPO), env=env)
    report = []
    print(f"Evidence: {evidence}", flush=True)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            with anyio.fail_after(30):
                await session.initialize()
            for action in actions:
                print(f"CALL {action}", flush=True)
                with anyio.fail_after(action.get("deadline", 240)):
                    result = await session.call_tool(action["tool"], action.get("arguments", {}))
                record = {"action": action, "result": summarize(result)}
                report.append(record)
                (evidence / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
                summary = record["result"].get("structured_content")
                if summary is None:
                    summary = record["result"]
                print(json.dumps(summary, ensure_ascii=False), flush=True)
                if result.is_error:
                    shot = await session.call_tool("vroid_screenshot", {"tag": "failure", "whole_screen": True})
                    report.append({"action": {"tool": "vroid_screenshot"}, "result": summarize(shot)})
                    (evidence / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
                    return 1
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("actions", help="JSON array of {tool, arguments} calls")
    parser.add_argument("--exe", help="Standalone VRoidStudio.exe path")
    raise SystemExit(anyio.run(run, parser.parse_args()))
