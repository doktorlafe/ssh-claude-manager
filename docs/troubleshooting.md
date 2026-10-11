# Troubleshooting

To see what ccm sees on a host, run the probe by hand:

```sh
ssh <host> python3 - < src/ccm/remote/probe.py | python3 -m json.tool   # remote
python3 src/ccm/remote/probe.py | python3 -m json.tool                  # this machine
```

## A host shows `✗ host: ...`

The text after the host name is the last line of the SSH error.

| Message | Cause and fix |
|---|---|
| `Permission denied (publickey,password)` | No key login. Run `ssh-copy-id user@host`, then check that `ssh user@host true` works without a prompt. |
| `Could not resolve hostname` | Wrong name or alias. Check `~/.ssh/config` and the `hosts` list. |
| `Host key verification failed` | First contact with this host. Run `ssh <host>` once by hand and accept the key. |
| `timed out` | Host unreachable or very slow. ccm retries on the next poll. |
| `python3: not found` (or similar) | Install Python 3 on the host. |
| `unreadable probe output` | Something printed text before the probe's JSON, usually a shell start-up file that echoes on non-interactive logins. Make that output conditional on an interactive shell. |

## A new agent never appears

After `n`, ccm shows either "started <name>" or an error.

- **`duplicate session: ccm-<name>`**: an agent with that name already runs on the host. Choose another name or kill the old one.
- **`cd: ... No such file or directory`**: the directory does not exist on the host.
- **`unknown flag -e` / usage text from tmux**: tmux on the host is older than 3.2.
- **"started" but no row**: the session ended at once, usually because `claude` is not on the `PATH` of your login shell on that host. Check with `ssh <host> '$SHELL -lic "command -v claude"'`.

## An agent stays `…` then `·` and never changes

No hook has reported. Press `t` to look at the live screen.

- If a dialog is shown that ccm did not recognise, attach with `a` and answer it.
- If Claude Code is running normally, the hooks are not firing. Check on the host that `~/.ccm/settings.json` and `~/.ccm/hook.sh` exist, and that the session was started from ccm (`tmux show-environment -t ccm-<name> CCM_NAME`). A Claude Code version that rejects the settings file will also show this; start `claude --settings ~/.ccm/settings.json` by hand on the host to see its complaint.

## A permission prompt is not marked `!`

The agent stays `⋯` although it waits for you. Press `t`: if the prompt is visible, its wording does not match `DIALOG_RE` in `src/ccm/model.py` and the notification hook did not fire. Attach with `a` to answer it, and extend `DIALOG_RE` with a phrase from that prompt.

## An agent is marked `?` or `✓` wrongly

`question` only means the last message from Claude ends with `?`. A closing "Want me to continue?" counts; a question in the middle of a message does not. The rule is in `derive_state` in `src/ccm/model.py`.

## A reply was pasted but not submitted

The text sits in the agent's input line. Attach with `a` and press Enter. If this happens regularly on a slow host, raise the `sleep 0.3` in `actions.send`.

## "is showing a prompt" when you try to reply

Intended. The agent is in the `!` state, and typed text would answer the dialog. Answer the prompt with `1`/`2`/`3`/`esc` or attach with `a`, then reply.

## Attach fails or returns at once

- `no sessions` / `can't find session`: the agent has ended; the row disappears on the next poll.
- Password prompt: attach does not use batch mode, so SSH may ask. Set up key login.
- Detach with `ctrl-b d` (or your own tmux prefix). Exiting Claude Code inside the session ends the agent.

## SSH behaves oddly after a network change

ccm reuses one connection per host for 10 minutes. Close a stale one with:

```sh
ssh -o ControlPath=~/.cache/ccm/cm-%C -O exit <host>
```

or delete the sockets in `~/.cache/ccm/`.

## Removing ccm from a host

```sh
tmux ls | grep '^ccm-'        # agents still running
tmux kill-session -t ccm-<name>
rm -rf ~/.ccm
```

Conversations are kept by Claude Code itself under `~/.claude/projects/` and are not touched.
