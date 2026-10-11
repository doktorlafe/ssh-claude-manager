from __future__ import annotations

import json
import re
from importlib import resources
from shlex import quote

from .config import LOCAL
from .model import Agent, from_probe
from .transport import Result, run, ssh_opts

PREFIX = "ccm-"
NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
KEYS = {"1", "2", "3", "Escape", "Enter"}
REMOTE_FILES = ("hook.sh", "launch.sh", "settings.json")
# $SHELL -lic: the user's login shell, so claude is on PATH as it is interactively.
# Kept to syntax that sh, bash, zsh and fish all accept.
LAUNCH = "exec $SHELL -lic 'exec sh ~/.ccm/launch.sh'"
BOOTSTRAP = (
    "import json,os,sys\n"
    "d=os.path.expanduser('~/.ccm')\n"
    "for s in ('state','prompts'):os.makedirs(os.path.join(d,s),exist_ok=True)\n"
    "for n,c in json.load(sys.stdin).items():open(os.path.join(d,n),'w').write(c)\n"
)


def _remote(name: str) -> str:
    return resources.files("ccm.remote").joinpath(name).read_text()


def _target(name: str) -> str:
    return quote(f"={PREFIX}{name}:")


def _dir(path: str) -> str:
    path = path.strip() or "~"
    if path == "~":
        return '"$HOME"'
    if path.startswith("~/"):
        return '"$HOME"/' + quote(path[2:])
    return quote(path)


class ProbeError(Exception):
    pass


async def probe(host: str, history: int = 30) -> list[Agent]:
    r = await run(host, f"python3 - {int(history)}", _remote("probe.py").encode())
    if not r.ok:
        raise ProbeError(r.message)
    try:
        return from_probe(host, json.loads(r.out))
    except ValueError:
        raise ProbeError("unreadable probe output") from None


async def bootstrap(host: str) -> Result:
    """Install/refresh the hook, launcher and settings under ~/.ccm on the host."""
    files = {n: _remote(n) for n in REMOTE_FILES}
    return await run(host, "python3 -c " + quote(BOOTSTRAP), json.dumps(files).encode())


async def spawn(host: str, name: str, directory: str, prompt: str = "") -> Result:
    if not NAME_RE.match(name):
        return Result(2, "", "name may only contain letters, digits, - and _")
    r = await bootstrap(host)
    if not r.ok:
        return r
    qn = quote(name)
    script = (
        f'rm -f "$HOME/.ccm/state/"{qn}; cat > "$HOME/.ccm/prompts/"{qn} && cd {_dir(directory)} && '
        f"tmux new-session -d -s {quote(PREFIX + name)} -x 200 -y 50 "
        f"-e {quote('CCM_NAME=' + name)} {quote(LAUNCH)}"
    )
    return await run(host, script, prompt.strip().encode())


async def send(host: str, name: str, text: str) -> Result:
    """Paste text into the agent's prompt and submit it."""
    t = _target(name)
    script = (f"tmux load-buffer -b ccm - && tmux paste-buffer -p -d -b ccm -t {t} && "
              f"sleep 0.3 && tmux send-keys -t {t} Enter")
    return await run(host, script, text.strip().encode())


async def send_key(host: str, name: str, key: str) -> Result:
    if key not in KEYS:
        return Result(2, "", f"key not allowed: {key}")
    return await run(host, f"tmux send-keys -t {_target(name)} {key}")


async def kill(host: str, name: str) -> Result:
    return await run(host, f'tmux kill-session -t {quote("=" + PREFIX + name)}; '
                           f'rm -f "$HOME/.ccm/state/"{quote(name)}')


def attach_argv(host: str, name: str) -> list[str]:
    """Interactive attach command; run it with the TUI suspended."""
    cmd = ["tmux", "attach-session", "-t", f"={PREFIX}{name}"]
    if host == LOCAL:
        return ["env", "-u", "TMUX", *cmd]
    return ["ssh", *ssh_opts(batch=False), "-t", "--", host, " ".join(quote(c) for c in cmd)]
