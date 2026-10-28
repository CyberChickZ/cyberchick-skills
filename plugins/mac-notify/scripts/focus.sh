#!/bin/bash
# usage: focus.sh <url> <iterm-session-uuid> <tty> <bundle-id> [session]
# 依次尝试：URL → iTerm2 会话 UUID → tty 匹配 iTerm2/Terminal 的 tab → 激活来源 app → 激活正在运行的终端
url="$1" uuid="$2" tty="$3" bundle="$4"
[ -n "$5" ] && "$(dirname "$0")/remind.sh" --cancel "$5"

[ -n "$url" ] && open "$url" && exit 0

running() { pgrep -xq "$1"; }

if [ -n "$uuid" ] && running iTerm2; then
  r=$(osascript - "$uuid" <<'EOF'
on run a
  tell application "iTerm2"
    repeat with w in windows
      repeat with t in tabs of w
        repeat with s in sessions of t
          if unique id of s is (item 1 of a) then
            select w
            select t
            select s
            activate
            return "ok"
          end if
        end repeat
      end repeat
    end repeat
  end tell
end run
EOF
  )
  [ "$r" = ok ] && exit 0
fi

if [ -n "$tty" ]; then
  if running iTerm2; then
    r=$(osascript - "$tty" <<'EOF'
on run a
  tell application "iTerm2"
    repeat with w in windows
      repeat with t in tabs of w
        repeat with s in sessions of t
          if tty of s is (item 1 of a) then
            select w
            select t
            select s
            activate
            return "ok"
          end if
        end repeat
      end repeat
    end repeat
  end tell
end run
EOF
    )
    [ "$r" = ok ] && exit 0
  fi
  if running Terminal; then
    r=$(osascript - "$tty" <<'EOF'
on run a
  tell application "Terminal"
    repeat with w in windows
      repeat with t in tabs of w
        if tty of t is (item 1 of a) then
          set selected of t to true
          set index of w to 1
          activate
          return "ok"
        end if
      end repeat
    end repeat
  end tell
end run
EOF
    )
    [ "$r" = ok ] && exit 0
  fi
fi

[ -n "$bundle" ] && open -b "$bundle" && exit 0
running iTerm2 && open -b com.googlecode.iterm2 && exit 0
running Terminal && open -b com.apple.Terminal && exit 0
exit 1
