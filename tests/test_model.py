from ccm.model import derive_state, fmt_wait, from_probe, sort_agents

NOW = 1_000_000


def agent(name, event, ago, **extra):
    return {"name": name, "created": NOW - 5000, "event": event, "ts": NOW - ago, **extra}


def test_states():
    assert derive_state(agent("a", "Permission", 5), NOW) == "permission"
    assert derive_state(agent("a", "PreToolUse", 5), NOW) == "working"
    assert derive_state(agent("a", "Stop", 5), NOW) == "done"
    assert derive_state(agent("a", "SessionStart", 5), NOW) == "idle"
    assert derive_state(agent("a", "Stop", 5, api_error=True), NOW) == "error"
    assert derive_state({"name": "a", "created": NOW - 5}, NOW) == "starting"
    assert derive_state({"name": "a", "created": NOW - 500}, NOW) == "unknown"


def test_question_detection():
    asks = [{"role": "you", "text": "go"}, {"role": "claude", "text": "Keep the flag?  "}]
    assert derive_state(agent("a", "Stop", 5, messages=asks), NOW) == "question"
    tells = asks + [{"role": "claude", "text": "Done."}]
    assert derive_state(agent("a", "Stop", 5, messages=tells), NOW) == "done"
    assert derive_state(agent("a", "PreToolUse", 5, pending=["AskUserQuestion"]), NOW) == "question"


def test_dialog_on_screen_counts_as_permission():
    pane = "Do you want to proceed?\n ❯ 1. Yes\n   2. No"
    assert derive_state(agent("a", "PreToolUse", 5, pane=pane), NOW) == "permission"
    assert derive_state({"name": "a", "created": NOW - 500, "pane": pane}, NOW) == "permission"
    trust = " ❯ No, exit\n   Yes, I trust this folder\n\n Enter to confirm · Esc to cancel"
    assert derive_state({"name": "a", "created": NOW - 5, "pane": trust}, NOW) == "permission"
    assert derive_state(agent("a", "Stop", 5, pane="1. Yesterday's notes"), NOW) == "done"


def test_ranking():
    doc = {"now": NOW, "agents": [
        agent("busy", "PreToolUse", 900),
        agent("done-new", "Stop", 10),
        agent("done-old", "Stop", 600),
        agent("asks", "Stop", 30, messages=[{"role": "claude", "text": "Which one?"}]),
        agent("broken", "Stop", 999, api_error=True),
        agent("perm-new", "Permission", 5),
        agent("perm-old", "Permission", 50),
    ]}
    order = [a.name for a in sort_agents(from_probe("h", doc))]
    assert order == ["perm-old", "perm-new", "asks", "done-old", "done-new", "broken", "busy"]


def test_fmt_wait():
    assert [fmt_wait(s) for s in (5, 125, 3900, 200000)] == ["5s", "2m", "1h05", "2d"]
