#!/bin/bash
# usage: notify.sh <message> [title] [open-url]
msg="${1:?message required}"
title="${2:-Claude Code}"
url="$3"
sub="$(basename "$PWD")"
if command -v terminal-notifier >/dev/null; then
  args=(-title "$title" -subtitle "$sub" -message "$msg" -sound Glass -group "claude-$PPID")
  [ -n "$url" ] && args+=(-open "$url")
  [ -n "$__CFBundleIdentifier" ] && args+=(-activate "$__CFBundleIdentifier")
  terminal-notifier "${args[@]}" >/dev/null
else
  osascript -e 'on run a' -e 'display notification (item 1 of a) with title (item 2 of a) subtitle (item 3 of a) sound name "Glass"' -e 'end run' "$msg" "$title" "$sub"
fi
