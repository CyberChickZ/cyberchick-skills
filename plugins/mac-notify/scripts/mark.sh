#!/bin/bash
# usage: mark.sh <session>  —— 用户提交消息时调用：记下此刻最前面的终端 tab（后台会话继承的环境变量指向的不是用户正在看的 tab）
f="${XDG_CACHE_HOME:-$HOME/.cache}/mac-notify/tabs/$1"
mkdir -p "$(dirname "$f")"
front=$(lsappinfo info -only bundleid "$(lsappinfo front)" | sed -n 's/.*"\(.*\)".*/\1/p')
case "$front" in
  com.googlecode.iterm2)
    r=$(osascript -e 'tell application "iTerm2" to tell current session of current window to return (unique id) & " " & (tty)' 2>/dev/null) ;;
  com.apple.Terminal)
    r=" $(osascript -e 'tell application "Terminal" to get tty of selected tab of front window' 2>/dev/null)" ;;
  *) exit 0 ;;
esac
[ -n "${r// /}" ] && echo "$front $r" >"$f"
