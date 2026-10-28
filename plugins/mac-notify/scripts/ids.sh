# source 后得到 uuid / tty / bundle：当前终端 tab 的标识
sid="${ITERM_SESSION_ID:-$TERM_SESSION_ID}"
uuid= tty=
[[ "$sid" =~ ^w[0-9]+t[0-9]+p[0-9]+:(.+)$ ]] && uuid="${BASH_REMATCH[1]}"
p=$$
while [ "${p:-1}" -gt 1 ]; do
  read -r pp t <<<"$(ps -o ppid=,tty= -p "$p")"
  [ -n "$t" ] && [ "$t" != "??" ] && { tty="/dev/$t"; break; }
  p=$pp
done
bundle="$__CFBundleIdentifier"
case "$TERM_PROGRAM" in iTerm.app) bundle="${bundle:-com.googlecode.iterm2}" ;; Apple_Terminal) bundle="${bundle:-com.apple.Terminal}" ;; esac
