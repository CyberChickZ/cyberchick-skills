#!/usr/bin/env python3
"""
Flow ledger — logs user prompts + tool calls + session lifecycle to
/tmp/claude_tool_ledger.log, one line per event.

File is trimmed in-place to stay under 1 MB (keeps last ~500 KB).
Silent fail on any exception (never breaks tool execution).
"""
import json
import os
import sys
import time
from pathlib import Path

# Recursion guard: claude-memory-compiler's flush.py spawns a bundled Claude
# CLI with CLAUDE_INVOKED_BY=memory_flush. Skip logging for that worker so
# it doesn't pollute the ledger with USER+STOP pairs for every flush.
if os.environ.get("CLAUDE_INVOKED_BY"):
    sys.exit(0)

LEDGER = Path("/tmp/claude_tool_ledger.log")
MAX_BYTES = 1_000_000
KEEP_BYTES = 500_000


def trim_if_needed() -> None:
    try:
        if LEDGER.exists() and LEDGER.stat().st_size > MAX_BYTES:
            data = LEDGER.read_bytes()
            tail = data[-KEEP_BYTES:]
            nl = tail.find(b"\n")
            if nl >= 0:
                tail = tail[nl + 1:]
            LEDGER.write_bytes(tail)
    except Exception:
        pass


def append(line: str) -> None:
    try:
        with open(LEDGER, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def one_line(s: str, limit: int) -> str:
    return str(s)[:limit].replace("\n", " ⏎ ")


try:
    raw = sys.stdin.read()
    data = json.loads(raw) if raw else {}

    event = data.get("hook_event_name", "?")
    session = str(data.get("session_id", "?"))[:8]
    ts = time.time()

    if event == "UserPromptSubmit":
        prompt = one_line(data.get("prompt", ""), 200)
        append(f"{ts:.3f} USER  session={session} | {prompt}\n")

    elif event == "PreToolUse":
        tool = data.get("tool_name", "?")
        inp = data.get("tool_input", {}) or {}
        if isinstance(inp, dict):
            summary = (
                inp.get("command")
                or inp.get("file_path")
                or inp.get("pattern")
                or inp.get("url")
                or inp.get("description")
                or ""
            )
        else:
            summary = str(inp)
        summary = one_line(summary, 150)
        append(f"{ts:.3f} START session={session} tool={tool:<12} | {summary}\n")

    elif event == "PostToolUse":
        tool = data.get("tool_name", "?")
        resp = data.get("tool_response", {})
        is_err = False
        if isinstance(resp, dict):
            is_err = bool(resp.get("is_error") or resp.get("error"))
        marker = "ERROR" if is_err else "OK"
        append(f"{ts:.3f} END   session={session} tool={tool:<12} | {marker}\n")

    elif event == "SessionStart":
        source = data.get("source", "?")
        append(f"{ts:.3f} BEGIN session={session} | source={source}\n")

    elif event == "SessionEnd":
        append(f"{ts:.3f} CLOSE session={session}\n")

    elif event == "Stop":
        append(f"{ts:.3f} STOP  session={session}\n")

    trim_if_needed()

except Exception:
    pass

sys.exit(0)
