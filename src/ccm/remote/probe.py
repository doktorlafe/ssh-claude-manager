"""Runs on the agent host (piped to `python3 -`). Stdlib only, read-only.

Prints one JSON document describing every ccm-* tmux session: the last hook
event, the tail of the chat transcript and the visible pane.
"""
import json
import os
import re
import subprocess
import sys
import time

PREFIX = "ccm-"
NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
STATE_DIR = os.path.expanduser("~/.ccm/state")
TAIL_BYTES = 400000
MAX_TEXT = 2000
BRIEF_KEYS = ("command", "file_path", "pattern", "description", "prompt", "url", "query")


def tmux(*args):
    try:
        r = subprocess.run(("tmux",) + args, stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, universal_newlines=True)
    except OSError:
        return ""
    return r.stdout if r.returncode == 0 else ""


def read_state(path):
    """Parse a state file written by hook.sh; {} if missing or malformed."""
    try:
        with open(path, errors="replace") as f:
            event, ts, payload = f.read().rstrip("\n").split("\t", 2)
        ts = int(ts)
    except (OSError, ValueError):
        return {}
    try:
        data = json.loads(payload)
    except ValueError:
        data = {}
    return {"event": event, "ts": ts,
            "transcript_path": data.get("transcript_path"), "cwd": data.get("cwd")}


def tool_brief(block):
    inp = block.get("input")
    name = block.get("name", "tool")
    if isinstance(inp, dict):
        for k in BRIEF_KEYS:
            if isinstance(inp.get(k), str):
                return "%s: %s" % (name, " ".join(inp[k].split())[:120])
    return name


def read_transcript(path, limit):
    """Tail a Claude Code transcript JSONL into chat messages.

    Returns {"messages": [{"role", "text"}], "pending": [tool names awaiting
    a result], "api_error": bool}.
    """
    out = {"messages": [], "pending": [], "api_error": False}
    try:
        with open(path, "rb") as f:
            size = f.seek(0, 2)
            start = max(0, size - TAIL_BYTES)
            f.seek(start)
            lines = f.read().decode("utf-8", "replace").splitlines()
    except (OSError, TypeError):
        return out
    if start:
        lines = lines[1:]
    msgs, pending = [], {}
    for line in lines:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        kind = rec.get("type")
        if kind not in ("user", "assistant") or rec.get("isSidechain") \
                or rec.get("isMeta") or rec.get("isCompactSummary"):
            continue
        content = (rec.get("message") or {}).get("content")
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        if not isinstance(content, list):
            continue
        out["api_error"] = bool(rec.get("isApiErrorMessage"))
        for block in content:
            if not isinstance(block, dict):
                continue
            t = block.get("type")
            if t == "text":
                text = (block.get("text") or "").strip()
                # slash-command and reminder wrappers, not something the user typed
                if not text or (kind == "user" and text.startswith("<")):
                    continue
                msgs.append({"role": "you" if kind == "user" else "claude",
                             "text": text[:MAX_TEXT]})
            elif t == "tool_use":
                pending[block.get("id")] = block.get("name", "tool")
                msgs.append({"role": "tool", "text": tool_brief(block)})
            elif t == "tool_result":
                pending.pop(block.get("tool_use_id"), None)
    out["messages"] = msgs[-limit:]
    out["pending"] = list(pending.values())
    return out


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    agents = []
    listing = tmux("list-sessions", "-F", "#{session_name}\t#{session_created}\t#{pane_current_path}")
    for row in listing.splitlines():
        parts = row.split("\t")
        if len(parts) != 3 or not parts[0].startswith(PREFIX):
            continue
        name = parts[0][len(PREFIX):]
        if not NAME_RE.match(name):
            continue
        state = read_state(os.path.join(STATE_DIR, name))
        agent = {"name": name, "created": int(parts[1] or 0),
                 "cwd": state.get("cwd") or parts[2],
                 "event": state.get("event"), "ts": state.get("ts"),
                 "pane": tmux("capture-pane", "-p", "-t", "=%s%s:" % (PREFIX, name)).rstrip()}
        agent.update(read_transcript(state.get("transcript_path"), limit))
        agents.append(agent)
    json.dump({"now": int(time.time()), "agents": agents}, sys.stdout)


if __name__ == "__main__":
    main()
