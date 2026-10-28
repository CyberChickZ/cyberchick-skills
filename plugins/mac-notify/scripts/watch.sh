#!/bin/bash
# usage: watch.sh <session> <iterm-uuid> <tty>
# 提醒未处理期间轮询：用户自己切回对应终端 tab（先离开过再回来）就清除通知和提醒。最长 2 小时后退出。
session="$1" uuid="$2" tty="$3"
dir="$(cd "$(dirname "$0")" && pwd)"

here() {
  front=$(lsappinfo info -only bundleid "$(lsappinfo front)" | sed -n 's/.*"\(.*\)".*/\1/p')
  case "$front" in
    com.googlecode.iterm2)
      [ -n "$uuid" ] && [ "$(osascript -e 'tell application "iTerm2" to get unique id of current session of current window' 2>/dev/null)" = "$uuid" ] && return 0
      [ -n "$tty" ] && [ "$(osascript -e 'tell application "iTerm2" to get tty of current session of current window' 2>/dev/null)" = "$tty" ] ;;
    com.apple.Terminal)
      [ -n "$tty" ] && [ "$(osascript -e 'tell application "Terminal" to get tty of selected tab of front window' 2>/dev/null)" = "$tty" ] ;;
    *) return 1 ;;
  esac
}

left=
end=$((SECONDS + 7200))
while [ $SECONDS -lt $end ]; do
  sleep 2
  if here; then
    if [ -n "$left" ]; then
      rm -f "${XDG_CACHE_HOME:-$HOME/.cache}/mac-notify/pending/$session.w$$"
      exec "$dir/remind.sh" --cancel "$session"
    fi
  else
    left=1
  fi
done
