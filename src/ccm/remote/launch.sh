#!/bin/sh
# Started inside the agent's tmux session through the user's login shell,
# so PATH matches what they get interactively. CCM_NAME is set by tmux.
s="$HOME/.ccm/settings.json"
p="$HOME/.ccm/prompts/$CCM_NAME"
if [ -s "$p" ]; then
    prompt=$(cat "$p")
    rm -f "$p"
    exec claude --settings "$s" --name "$CCM_NAME" -- "$prompt"
fi
rm -f "$p"
exec claude --settings "$s" --name "$CCM_NAME"
