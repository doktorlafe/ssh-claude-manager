# How ccm works

ccm has no daemon and no database. The dashboard holds no state of its own: every few seconds it asks each host what its agents are doing and redraws. Quitting ccm changes nothing on the hosts.

```
 your machine                              agent host
┌───────────────────────┐   ssh (one     ┌──────────────────────────────────────┐
│ ccm TUI               │   multiplexed  │ tmux session ccm-<name>              │
│  poll loop per host ──┼── connection) ─┼─► python3 - < probe.py               │
│  actions (send, key,  │                │     reads ~/.ccm/state/<name>        │
│   spawn, kill)       ─┼────────────────┼─►   reads transcript .jsonl          │
│                       │                │     tmux capture-pane                │
└───────────────────────┘                │ claude ── hooks ─► ~/.ccm/hook.sh    │
                                         │                     writes state file│
                                         └──────────────────────────────────────┘
```

## Source layout

| File | Role |
|---|---|
| `src/ccm/__main__.py` | Command line: reads the config, applies host arguments, starts the app. |
| `src/ccm/config.py` | Loads `~/.config/ccm/config.toml`. |
| `src/ccm/transport.py` | Runs a shell script on a host (`ssh` or, for `local`, `sh -c`) with stdin and a timeout. |
| `src/ccm/actions.py` | Everything ccm does to a host: probe, bootstrap, spawn, send, send key, kill, attach command. |
| `src/ccm/model.py` | The `Agent` record, the event-to-state rules and the sort order. Pure functions. |
| `src/ccm/app.py` | The Textual interface: list, preview, reply box, dialogs, key bindings, poll loops. |
| `src/ccm/remote/probe.py` | Runs on the host. Reports sessions, state, transcript tail and screen as JSON. |
| `src/ccm/remote/hook.sh` | Runs on the host as a Claude Code hook. Records the latest event. |
| `src/ccm/remote/launch.sh` | Runs on the host inside the tmux session. Starts `claude`. |
| `src/ccm/remote/settings.json` | Claude Code settings that register the hooks. |

## Files on a host

Created under `~/.ccm/` the first time you start an agent on that host, and refreshed on every start:

| Path | Content |
|---|---|
| `hook.sh`, `launch.sh`, `settings.json` | Copies of the files in `src/ccm/remote/`. |
| `state/<name>` | One line: `event <TAB> unix-time <TAB> hook JSON`. Rewritten on every hook event. |
| `prompts/<name>` | The first prompt, written before launch and deleted by `launch.sh` when it reads it. |

The probe is not stored on the host. It is piped to `python3 -` on every poll.

## Starting an agent

`actions.spawn` does this in two SSH calls:

1. **Bootstrap.** The three remote files are sent as JSON on stdin to a short `python3 -c` program that writes them into `~/.ccm/`.
2. **Launch.** The first prompt is written from stdin to `~/.ccm/prompts/<name>`, then:

   ```sh
   cd <directory> && tmux new-session -d -s ccm-<name> -x 200 -y 50 \
       -e CCM_NAME=<name> "exec $SHELL -lic 'exec sh ~/.ccm/launch.sh'"
   ```

`$SHELL -lic` starts your login shell in interactive mode so that `claude` is found on the same `PATH` you get when you log in yourself. A non-interactive SSH command usually has a shorter `PATH`. The command string uses only syntax that sh, bash, zsh and fish share.

`launch.sh` then runs `claude --settings ~/.ccm/settings.json --name <name> [-- <prompt>]`. The `--settings` file applies to that process only, so the host's own Claude Code configuration is untouched and sessions you start by hand are not affected.

`CCM_NAME` is inherited by `claude` and by its hooks. `hook.sh` exits at once when it is not set.

## How state is detected

### Hook events

`settings.json` registers one hook per event; each calls `hook.sh <event>`.

| Claude Code event | Written as | Resulting state |
|---|---|---|
| `SessionStart` | `SessionStart` | idle |
| `UserPromptSubmit`, `PreToolUse`, `PostToolUse` | same | working |
| `Notification`, matcher `permission_prompt\|elicitation_dialog` | `Permission` | permission |
| `Stop` | `Stop` | done, question or error (see below) |
| `SessionEnd` | `SessionEnd` | not shown: the tmux session is gone |

The hook's JSON input is stored with the event. ccm uses two fields from it: `transcript_path`, to find the chat, and `cwd`.

### Refinements in `model.derive_state`

- **Question.** After `Stop`, if the last chat message is from Claude and ends with `?`, the state is `question`. While working, an `AskUserQuestion` tool call without a result also counts as `question`.
- **Error.** After `Stop`, if the last transcript record is marked as an API error, the state is `error`.
- **Dialog on screen.** If the visible screen matches `DIALOG_RE` (a numbered "1. Yes" choice, "Enter to confirm" or "Esc to cancel"), the state is `permission`. This applies while working and when no hook has fired at all. It catches the folder-trust dialog, which appears before any hook runs, and covers permission prompts if the notification hook is late or missing.
- **No state file.** `starting` for the first 60 seconds after the tmux session was created, then `unknown`.

### Order

`model.RANK` gives each state a tier; `sort_agents` sorts by tier, then by longest time in the current state, then by name. To change the order, edit `RANK`.

## The probe

One call per host per poll: `python3 - <history>` with `probe.py` on stdin. For every tmux session whose name starts with `ccm-` it collects:

- the parsed state file,
- the last `history` chat messages from the transcript,
- the names of tool calls that have no result yet,
- whether the last record is an API error,
- the visible screen (`tmux capture-pane -p`).

Output is one JSON object: `{"now": <host unix time>, "agents": [...]}`. Wait times are computed from the host's own clock (`now - ts`), so clock differences between machines do not matter.

### Reading the transcript

Claude Code writes each conversation as JSON Lines under `~/.claude/projects/`. The probe reads only the last 400 kB of the file and keeps:

- `user` records with typed text as **you** (text starting with `<` is skipped: those are slash-command and reminder wrappers),
- `assistant` text blocks as **claude**,
- `tool_use` blocks as a one-line **tool** entry, for example `Bash: pytest -q`.

It skips sub-agent records (`isSidechain`), meta records and compaction summaries. Each message is cut at 2000 characters.

## Sending input

**Reply** (`actions.send`): the text travels on stdin, never on a command line.

```sh
tmux load-buffer -b ccm - && tmux paste-buffer -p -d -b ccm -t '=ccm-<name>:' \
    && sleep 0.3 && tmux send-keys -t '=ccm-<name>:' Enter
```

`paste-buffer -p` uses bracketed paste, so newlines inside the message do not submit it early. The short pause lets Claude Code finish handling the paste before Enter arrives.

**Keys** (`actions.send_key`): `tmux send-keys` with a key from a fixed list (`1`, `2`, `3`, `Escape`, `Enter`). The interface sends them only to an agent in the `permission` state.

**Attach**: the interface suspends itself and runs `ssh -t <host> tmux attach-session -t =ccm-<name>` in the foreground. For `local` it runs tmux directly with `TMUX` unset, so it also works when ccm itself runs inside tmux.

**Kill**: `tmux kill-session`, then the state file is removed.

## SSH

Options used for every call (`transport.ssh_opts`):

| Option | Why |
|---|---|
| `ControlMaster=auto`, `ControlPath=~/.cache/ccm/cm-%C`, `ControlPersist=10m` | One connection per host is reused, so a poll costs milliseconds instead of a new login. |
| `BatchMode=yes` | Fail instead of waiting for a password. Not used for attach, which is interactive. |
| `ConnectTimeout=8` | An unreachable host cannot stall its poll loop for long. |

Each remote command is wrapped as `sh -c '<script>'`, so the scripts do not depend on the login shell. Calls time out after 20 seconds.

## Safety of input handling

- Agent names are limited to `[A-Za-z0-9_-]` when created and again when read back from tmux.
- Every value placed in a remote script is quoted with `shlex.quote`.
- Message text, first prompts and the remote files go over stdin.
- Host names starting with `-` are rejected, and `--` precedes the host in the `ssh` command.

## Interface internals

- One worker per host loops: probe, store the result in `by_host[host]`, rebuild the list, wait `poll_seconds` or until `refresh_now()` is called. A slow host delays only its own rows.
- `rebuild` re-sorts all agents and keeps the selection on the same agent, even when its position changes.
- The preview is repainted only when its text changed, so reading is not interrupted by scroll jumps.
- The preview shows the live screen by default for `permission`, `starting` and `unknown`, and the chat otherwise. `t` overrides this until you select another agent.

## Tests

`tests/test_model.py` covers state rules, question and dialog detection and the sort order. `tests/test_probe.py` covers transcript and state-file parsing. Neither needs tmux, SSH or Claude Code.

```sh
.venv/bin/pytest
```
