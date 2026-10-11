#!/bin/sh
# Claude Code hook: record the latest event for this agent.
# usage: hook.sh <event>   (hook JSON arrives on stdin)
# Writes ~/.ccm/state/$CCM_NAME as: event <TAB> epoch <TAB> hook-json
[ -n "$CCM_NAME" ] || exit 0
d="$HOME/.ccm/state"
mkdir -p "$d"
t="$d/.$CCM_NAME.$$"
{ printf '%s\t%s\t' "$1" "$(date +%s)"; tr -d '\n'; echo; } > "$t" && mv "$t" "$d/$CCM_NAME"
exit 0
