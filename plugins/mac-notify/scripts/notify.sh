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

cache="${XDG_CACHE_HOME:-$HOME/.cache}/mac-notify"
build() { # build <swift> <out>
  [ -x "$2" ] || { mkdir -p "$(dirname "$2")" && swiftc -O -o "$2" "$dir/$1" 2>>"$cache/build.log"; }
}

appdir="$cache/Claude Notify.app"
appbin="$appdir/Contents/MacOS/notifier-$(shasum "$dir/notifier.swift" | cut -c1-12)"
if [ ! -x "$appbin" ]; then
  rm -rf "$appdir"; mkdir -p "$appdir/Contents/Resources"
  icon=/Applications/Claude.app/Contents/Resources/electron.icns
  [ -f "$icon" ] && cp "$icon" "$appdir/Contents/Resources/AppIcon.icns"
  cat >"$appdir/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleIdentifier</key><string>com.cyberchick.mac-notify</string>
<key>CFBundleName</key><string>Claude</string>
<key>CFBundleDisplayName</key><string>Claude</string>
<key>CFBundleExecutable</key><string>$(basename "$appbin")</string>
<key>CFBundleIconFile</key><string>AppIcon</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>LSUIElement</key><true/>
<key>NSAppleEventsUsageDescription</key><string>点击通知时切回对应的终端窗口和标签页</string>
</dict></plist>
PLIST
  build notifier.swift "$appbin" && codesign -s - --force "$appdir" 2>/dev/null
fi

sid="${ITERM_SESSION_ID:-$TERM_SESSION_ID}"
[[ "$sid" =~ ^w[0-9]+t[0-9]+p[0-9]+:(.+)$ ]] && uuid="${BASH_REMATCH[1]}"
p=$$ tty=
while [ "${p:-1}" -gt 1 ]; do
  read -r pp t <<<"$(ps -o ppid=,tty= -p "$p")"
  [ -n "$t" ] && [ "$t" != "??" ] && { tty="/dev/$t"; break; }
  p=$pp
done
bundle="$__CFBundleIdentifier"
case "$TERM_PROGRAM" in iTerm.app) bundle="${bundle:-com.googlecode.iterm2}" ;; Apple_Terminal) bundle="${bundle:-com.apple.Terminal}" ;; esac

if [ -x "$appbin" ]; then
  open -n -g "$appdir" --args "${title:-Claude Code}" "$sub" "$msg" "$dir/focus.sh" "$url" "$uuid" "$tty" "$bundle" "${MAC_NOTIFY_SESSION:-$CLAUDE_CODE_SESSION_ID}"
else
  osascript -e 'on run a' -e 'display notification (item 1 of a) with title (item 2 of a) subtitle (item 3 of a) sound name "Glass"' -e 'end run' "$msg" "${title:-Claude Code}" "$sub"
fi

[ "$level" -ge 2 ] || exit 0
bin="$cache/alert-$(shasum "$dir/alert.swift" | cut -c1-12)"
build alert.swift "$bin" || exit 0
[ "$level" -ge 3 ] && afplay /System/Library/Sounds/Sosumi.aiff &
nohup "$bin" "$level" "$count" "$msg" "$title" >/dev/null 2>&1 &
