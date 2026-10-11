import json

from ccm.remote.probe import read_state, read_transcript


def rec(kind, content, **extra):
    return json.dumps({"type": kind, "message": {"role": kind, "content": content}, **extra})


def write(tmp_path, lines):
    p = tmp_path / "t.jsonl"
    p.write_text("\n".join(lines) + "\n")
    return str(p)


def test_transcript_messages_and_pending(tmp_path):
    path = write(tmp_path, [
        json.dumps({"type": "permission-mode", "permissionMode": "default"}),
        rec("user", "fix the tests"),
        rec("user", "<local-command-stdout>noise</local-command-stdout>"),
        rec("user", "hidden", isMeta=True),
        rec("assistant", [{"type": "thinking", "thinking": "hm"}]),
        rec("assistant", [{"type": "text", "text": "Looking."},
                          {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "pytest  -q"}}]),
        rec("user", [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]),
        rec("assistant", [{"type": "text", "text": "sub"}], isSidechain=True),
        rec("assistant", [{"type": "tool_use", "id": "t2", "name": "AskUserQuestion", "input": {}}]),
        "not json",
    ])
    out = read_transcript(path, 30)
    assert out["messages"] == [
        {"role": "you", "text": "fix the tests"},
        {"role": "claude", "text": "Looking."},
        {"role": "tool", "text": "Bash: pytest -q"},
        {"role": "tool", "text": "AskUserQuestion"},
    ]
    assert out["pending"] == ["AskUserQuestion"]
    assert out["api_error"] is False
    assert len(read_transcript(path, 2)["messages"]) == 2


def test_api_error_only_when_last(tmp_path):
    err = rec("assistant", [{"type": "text", "text": "API Error"}], isApiErrorMessage=True)
    assert read_transcript(write(tmp_path, [err]), 30)["api_error"] is True
    assert read_transcript(write(tmp_path, [err, rec("user", "retry")]), 30)["api_error"] is False


def test_missing_transcript():
    assert read_transcript(None, 30)["messages"] == []
    assert read_transcript("/nonexistent/x.jsonl", 30)["messages"] == []


def test_read_state(tmp_path):
    p = tmp_path / "agent"
    p.write_text('Stop\t1700000000\t{"transcript_path": "/x/t.jsonl", "cwd": "/x"}\n')
    assert read_state(str(p)) == {"event": "Stop", "ts": 1700000000,
                                  "transcript_path": "/x/t.jsonl", "cwd": "/x"}
    p.write_text("garbage")
    assert read_state(str(p)) == {}
    assert read_state(str(tmp_path / "missing")) == {}
