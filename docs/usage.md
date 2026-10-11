# Using ccm

## Requirements

On the machine where you run ccm:

- Python 3.11 or newer
- `ssh` (only for remote hosts)

On every host that runs agents (including this machine, if you use `local`):

- `tmux` 3.2 or newer
- `claude` (Claude Code), reachable from your login shell
- `python3` (any 3.6+; standard library only)
- for remote hosts: SSH login with a key. ccm runs SSH in batch mode and never asks for a password.

## Install

```sh
cd ~/projects/ssh-claude-manager
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

If `python3 -m venv` fails with "ensurepip is not available", install your distribution's venv package (for example `sudo apt install python3-venv`) and repeat.

## Set up SSH access to a host

```sh
ssh-keygen -t ed25519          # once, if you have no key yet
ssh-copy-id user@host          # once per host
ssh user@host true             # must succeed without a password prompt
```

A short alias in `~/.ssh/config` keeps the agent list readable, because ccm shows only the first 10 characters of a host name:

```
Host build1
    HostName build1.example.com
    User lafe
```

## Start ccm

```sh
.venv/bin/ccm                  # hosts from the config file; `local` if there is none
.venv/bin/ccm build1 build2    # hosts given on the command line override the config
.venv/bin/ccm local build1     # this machine plus a remote host
```

## Configuration

`~/.config/ccm/config.toml`. Every key is optional.

| Key | Default | Meaning |
|---|---|---|
| `hosts` | `["local"]` | SSH destinations (aliases or `user@host`). `local` means this machine, without SSH. |
| `poll_seconds` | `3` | How often each host is read. |
| `default_dir` | `"~"` | Directory pre-filled in the new-agent dialog. |
| `history` | `30` | Chat messages loaded per agent. |

```toml
hosts = ["build1", "build2"]
poll_seconds = 3
default_dir = "~/projects"
```

## The screen

```
┌ agents ────────────────────────────┬ api-refactor@build1 · permission 2m · screen ┐
│ ! api-refactor   build1      2m    │ Do you want to proceed?                      │
│ ? db-migrate     build2     40s    │ ❯ 1. Yes                                     │
│ ✓ docs           build1      9m    │   2. No                                      │
│ ⋯ tests          build2     12s    │                                              │
├────────────────────────────────────┴──────────────────────────────────────────────┤
│ reply to the selected agent — enter sends, esc leaves                             │
└ i Reply  a Attach  n New  x Kill  t Chat/screen  r Refresh  q Quit ───────────────┘
```

Left: agents, most-needed first. Each row shows state, name, host and how long the agent has been in that state. Right: the selected agent's chat, or its live terminal screen. The title of the right panel names the agent, its state and which view is shown; the bottom border shows its working directory.

### States and order

| Glyph | State | Meaning | Order |
|---|---|---|---|
| `!` | permission | A dialog is blocking the agent (tool permission, folder trust). | 1 |
| `?` | question | Claude finished its turn with a question for you. | 2 |
| `✓` | done | Claude finished its turn. | 3 |
| `·` | idle / unknown | Started and waiting for a first prompt, or no state reported. | 3 |
| `✗` | error | The last turn ended in an API error. | 4 |
| `⋯` | working | Claude is busy. | 5 |
| `…` | starting | The session was created less than a minute ago and has not reported yet. | 5 |

Within a group, the agent that has waited longest comes first.

A host that cannot be reached appears as a dimmed `✗ host: reason` line at the bottom of the list. The other hosts keep updating.

## Keys

| Key | Action |
|---|---|
| `j` / `k`, arrows | Select an agent. |
| `i` or `enter` | Focus the reply box. `enter` sends, `esc` goes back to the list. |
| `1` `2` `3` | Choose that option in the prompt of an agent in the `!` state. |
| `esc` | With the list focused: cancel the prompt of an agent in the `!` state. |
| `a` | Attach to the agent's tmux session. Detach with `ctrl-b d` to return. |
| `t` | Switch the preview between chat and live screen. |
| `n` | Start a new agent. |
| `x` | Kill the agent (asks first). |
| `r` | Refresh now. |
| `q` | Quit. Agents keep running. |

## Common tasks

### Start an agent

Press `n`, pick the host, give a name (letters, digits, `-`, `_`), a directory and optionally a first prompt, then press `enter`. The agent appears within a few seconds.

The first time Claude Code runs in a directory it asks whether you trust the folder. The agent then shows `!` and the screen view shows the question. That dialog has no numbered choices, so press `a` to attach, answer it, and detach with `ctrl-b d`. The first prompt you entered is sent once the dialog is answered.

### Reply to an agent

Select it, press `i`, type, press `enter`. Multi-line text pasted into the box is sent as one message.

ccm refuses to send a reply while the agent shows a prompt (`!`). Typed text followed by Enter would answer the dialog instead, possibly with the wrong choice. Answer the prompt first.

### Answer a permission prompt

Select the `!` agent. The preview switches to the live screen so you can read the prompt. Press `1`, `2` or `3` for the option, or `esc` to cancel. For anything else, attach with `a`.

### Work in an agent directly

Press `a`. You are now in the agent's tmux session and can use Claude Code as usual, including slash commands. `ctrl-b d` returns to ccm.

### Stop an agent

Press `x` and confirm with `y`. This closes the tmux session; the conversation stays in Claude Code's history on that host and can be resumed there with `claude --resume`.

## Names on the host

Each agent is a tmux session called `ccm-<name>`. You can use plain tmux on the host at any time:

```sh
tmux ls
tmux attach -t ccm-api-refactor
```

Only sessions started from ccm are listed. A Claude Code session you started by hand has no hooks and does not appear.
