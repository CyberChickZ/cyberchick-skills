#!/bin/bash
# usage: notify.sh [-l 1|2|3] [-n count] <message> [title] [open-url]
level=1 count=3
while getopts "l:n:" o; do case $o in l) level=$OPTARG ;; n) count=$OPTARG ;; esac; done
shift $((OPTIND - 1))
msg="${1:?message required}"
title="$2"
url="$3"
sub="$(basename "$PWD")"
dir="$(cd "$(dirname "$0")" && pwd)"

if command -v terminal-notifier >/dev/null; then
  args=(-title "${title:-Claude Code}" -subtitle "$sub" -message "$msg" -sound Glass -group "claude-$PPID")
  [ -n "$url" ] && args+=(-open "$url")
  [ -n "$__CFBundleIdentifier" ] && args+=(-activate "$__CFBundleIdentifier")
  terminal-notifier "${args[@]}" >/dev/null
else
  osascript -e 'on run a' -e 'display notification (item 1 of a) with title (item 2 of a) subtitle (item 3 of a) sound name "Glass"' -e 'end run' "$msg" "$title" "$sub"
fi

[ "$level" -ge 2 ] || exit 0
cache="${XDG_CACHE_HOME:-$HOME/.cache}/mac-notify"
bin="$cache/alert-$(shasum "$dir/alert.swift" | cut -c1-12)"
if [ ! -x "$bin" ]; then
  mkdir -p "$cache" && swiftc -O -o "$bin" "$dir/alert.swift" 2>"$cache/build.log" || exit 0
fi
[ "$level" -ge 3 ] && afplay /System/Library/Sounds/Sosumi.aiff &
nohup "$bin" "$level" "$count" "$msg" "$title" >/dev/null 2>&1 &
