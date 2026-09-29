# context-rewrite: `claude --yrb` routes only this one claude process through the local proxy; other sessions are untouched.
# Installed by /context-rewrite install and removed by /context-rewrite uninstall.
#
# claude() below is self-contained on purpose: some environments (for example Claude Code's own Bash tool) copy
# shell functions selectively and drop names starting with "_". If ctxrw_orig_claude is missing there, claude()
# still works and just runs the real binary.

if [ -n "$ZSH_VERSION" ]; then
  if (( $+functions[claude] )) && [[ $functions[claude] != *ctxrw-yrb-wrapper* ]]; then
    functions -c claude ctxrw_orig_claude
  fi
elif [ -n "$BASH_VERSION" ]; then
  if declare -F claude >/dev/null && ! declare -f claude | grep -q ctxrw-yrb-wrapper; then
    eval "$(declare -f claude | sed '1s/^claude/ctxrw_orig_claude/')"
  fi
fi

claude() {
  : ctxrw-yrb-wrapper
  local yrb=0 a d
  local -a args
  args=()
  for a in "$@"; do
    if [ "$a" = "--yrb" ]; then yrb=1; else args+=("$a"); fi
  done
  if [ "$yrb" = 0 ]; then
    if typeset -f ctxrw_orig_claude >/dev/null 2>&1; then ctxrw_orig_claude "$@"; else command claude "$@"; fi
    return
  fi
  d="${CTXRW_HOME:-${CLAUDE_CONFIG_DIR:-$HOME/.claude}/context-rewrite}"
  if [ ! -f "$d/ctxrw.py" ]; then
    local s="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/settings.json" zh=0
    case "$CTXRW_LANG" in
      zh) zh=1 ;;
      en) zh=0 ;;
      *)
        if [ -f "$s" ] && grep -Eiq '"language"[[:space:]]*:[[:space:]]*"[^"]*(chinese|中文|zh)' "$s"; then zh=1
        elif [ -f "$s" ] && grep -Eq '"language"[[:space:]]*:' "$s"; then zh=0
        else case "$LANG" in zh*) zh=1 ;; esac
        fi ;;
    esac
    if [ "$zh" = 1 ]; then
      echo "context-rewrite 未安装或已卸载，按普通方式启动" >&2
    else
      echo "context-rewrite is not installed (or was uninstalled); starting claude normally" >&2
    fi
    if typeset -f ctxrw_orig_claude >/dev/null 2>&1; then ctxrw_orig_claude "${args[@]}"; else command claude "${args[@]}"; fi
    return
  fi
  (
    python3 "$d/ctxrw.py" start --quiet || exit 1
    export ANTHROPIC_BASE_URL="http://127.0.0.1:${CTXRW_PORT:-8787}" CTXRW_YRB=1
    # Sessions hosted by the Claude Code daemon (Remote Control, background sessions) don't inherit this shell's
    # environment, but --settings does carry over, so pass the same variables through it as well.
    args=(--settings "{\"env\":{\"ANTHROPIC_BASE_URL\":\"$ANTHROPIC_BASE_URL\",\"CTXRW_YRB\":\"1\"}}" "${args[@]}")
    if typeset -f ctxrw_orig_claude >/dev/null 2>&1; then ctxrw_orig_claude "${args[@]}"; else command claude "${args[@]}"; fi
    rc=$?
    # claude has exited: stop the proxy right away if this was the last --yrb session
    env -u CTXRW_YRB -u ANTHROPIC_BASE_URL python3 "$d/ctxrw.py" stop-if-idle >/dev/null 2>&1
    exit $rc
  )
}
