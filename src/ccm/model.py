from __future__ import annotations

import re
from dataclasses import dataclass, field

# Lower rank = needs you sooner.
RANK = {
    "permission": 0,
    "question": 1,
    "done": 2,
    "idle": 2,
    "unknown": 2,
    "error": 3,
    "working": 4,
    "starting": 4,
}
GLYPH = {
    "permission": "!",
    "question": "?",
    "done": "✓",
    "idle": "·",
    "unknown": "·",
    "error": "✗",
    "working": "⋯",
    "starting": "…",
}
WORKING_EVENTS = {"UserPromptSubmit", "PreToolUse", "PostToolUse"}
# A dialog on screen that blocks the agent (tool permission, folder trust, ...).
DIALOG_RE = re.compile(r"^\s*(?:❯|>)?\s*1\. Yes|Enter to confirm|Esc to cancel", re.M)
STARTUP_GRACE = 60


@dataclass
class Agent:
    host: str
    name: str
    state: str
    wait: int  # seconds in the current state
    cwd: str = ""
    messages: list[dict] = field(default_factory=list)
    pane: str = ""

    @property
    def key(self) -> str:
        return f"{self.host}/{self.name}"


def derive_state(d: dict, now: int) -> str:
    event = d.get("event")
    dialog = bool(DIALOG_RE.search(d.get("pane") or ""))
    if event == "Permission":
        return "permission"
    if event in WORKING_EVENTS:
        if "AskUserQuestion" in (d.get("pending") or []):
            return "question"
        return "permission" if dialog else "working"
    if event in ("Stop", "SessionStart"):
        if d.get("api_error"):
            return "error"
        msgs = d.get("messages") or []
        if msgs and msgs[-1]["role"] == "claude" and msgs[-1]["text"].rstrip().endswith("?"):
            return "question"
        return "done" if event == "Stop" else "idle"
    # No hook has fired yet: claude is booting, stuck on a dialog, or not ours.
    if dialog:
        return "permission"
    return "starting" if now - (d.get("created") or 0) < STARTUP_GRACE else "unknown"


def from_probe(host: str, doc: dict) -> list[Agent]:
    now = doc.get("now") or 0
    agents = []
    for d in doc.get("agents") or []:
        since = d.get("ts") or d.get("created") or now
        agents.append(Agent(host=host, name=d["name"], state=derive_state(d, now),
                            wait=max(0, now - since), cwd=d.get("cwd") or "",
                            messages=d.get("messages") or [], pane=d.get("pane") or ""))
    return agents


def sort_agents(agents: list[Agent]) -> list[Agent]:
    """Most-needed first: by state tier, then longest waiting."""
    return sorted(agents, key=lambda a: (RANK.get(a.state, 9), -a.wait, a.key))


def fmt_wait(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h{seconds % 3600 // 60:02d}"
    return f"{seconds // 86400}d"
