#!/bin/bash
# usage: remind.sh [-d 延迟秒] [-e] [-u url] "<要做的事>"
#        remind.sh --cancel [session]
# 每个会话同时只有一个提醒；用户下一次发消息或点击通知即自动取消。
dir="$(cd "$(dirname "$0")" && pwd)"
pending="${XDG_CACHE_HOME:-$HOME/.cache}/mac-notify/pending"
mkdir -p "$pending"

cancel() {
  for f in "$pending/$1".*; do
    [ -e "$f" ] || continue
    pid="${f##*.}"; pid="${pid#w}"
    kids=$(pgrep -P "$pid")
    kill "$pid" 2>/dev/null
    [ -n "$kids" ] && kill $kids 2>/dev/null
    rm -f "$f"
  done
}

if [ "$1" = "--cancel" ]; then
  cancel "${2:-${CLAUDE_CODE_SESSION_ID:-default}}"
  cache="${XDG_CACHE_HOME:-$HOME/.cache}/mac-notify"
  pkill -f "$cache/alert-" 2>/dev/null
  if [ -f "$cache/delivered" ]; then
    rm -f "$cache/delivered"
    open -n -g "$cache/Claude Notify.app" --args --clear 2>/dev/null
  fi
  exit 0
fi

delay=0 escalate= url=
while getopts "d:eu:" o; do case $o in d) delay=$OPTARG ;; e) escalate=1 ;; u) url=$OPTARG ;; esac; done
shift $((OPTIND - 1))
msg="${1:?message required}"
session="${CLAUDE_CODE_SESSION_ID:-default}"
export MAC_NOTIFY_SESSION="$session"

cancel "$session"
DELAY=$delay ESCALATE=$escalate STAMP="$pending/$session" nohup bash -c '
  trap "rm -f \"$STAMP.$$\"" EXIT
  n="$1"; shift
  sleep "$DELAY"
  "$n" -l 1 "$@"
  [ -n "$ESCALATE" ] || exit 0
  sleep 120; "$n" -l 2 "$@"
  sleep 180; "$n" -l 3 "$@"
' _ "$dir/notify.sh" "$msg" "" "$url" >/dev/null 2>&1 </dev/null &
touch "$pending/$session.$!"
echo "reminder set (session $session, pid $!)"
