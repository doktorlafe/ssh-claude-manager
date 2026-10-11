# ccm

A small TUI that manages Claude Code agents running in tmux sessions on SSH hosts. It reads every agent's chat, sorts them by which one needs you most, and lets you answer without attaching.

```
! api-refactor   host1   2m     permission prompt on screen
? db-migrate     host2  40s     Claude asked a question
✓ docs           host1   9m     finished, waiting for you
✗ deploy         host2   1m     stopped on an API error
⋯ tests          host2  12s     working
```

Order: permission prompt, question, finished/idle, error, working; within a group the longest-waiting agent comes first.

## Install

```sh
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/ccm                 # hosts from the config file
.venv/bin/ccm host1 host2     # or name them; `local` means this machine
```

`~/.config/ccm/config.toml` (all keys optional):

```toml
hosts = ["host1", "host2"]   # aliases from ~/.ssh/config, or "local"
poll_seconds = 3
default_dir = "~/projects"
history = 30                 # chat messages shown per agent
```

Hosts need `tmux` (3.2+), `claude` and `python3`, and key-based SSH login (ccm never prompts for a password). Nothing is installed on a host apart from three small files in `~/.ccm/`.

## Keys

| Key | Action |
|---|---|
| `j` / `k`, arrows | select agent |
| `i` or `enter` | type a reply; `enter` sends, `esc` leaves |
| `1` `2` `3` `esc` | answer the prompt of an agent in the `!` state |
| `a` | attach to the agent's tmux session (detach with `ctrl-b d` to come back) |
| `t` | switch the preview between chat and the live terminal screen |
| `n` | start a new agent (host, name, directory, optional first prompt) |
| `x` | kill the agent's tmux session |
| `r` / `q` | refresh / quit |

Dialogs without numbered choices, such as the folder-trust question in a directory Claude has not seen before, show up as `!`; attach with `a` to answer them.

## How it works

- Agents are tmux sessions named `ccm-<name>`, started as `claude --settings ~/.ccm/settings.json`. That settings file adds hooks for this session only; the host's own Claude configuration is not changed.
- Each hook writes the latest event to `~/.ccm/state/<name>`. ccm maps events to states and, as a fallback, treats a dialog visible on the terminal screen as a permission prompt.
- Every few seconds ccm pipes `src/ccm/remote/probe.py` to `python3` on each host over one multiplexed SSH connection. The probe returns the sessions, their state, the tail of each transcript and the visible screen.
- Replies are pasted through a tmux buffer fed from stdin, so message text is never interpreted by a shell.

Only agents started from ccm are listed.

## Documentation

- [docs/usage.md](docs/usage.md): setup, configuration, the screen, keys and common tasks
- [docs/architecture.md](docs/architecture.md): how state detection, the probe and input sending work
- [docs/troubleshooting.md](docs/troubleshooting.md): error messages and fixes

## Tests

```sh
.venv/bin/pytest
```
