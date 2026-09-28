# context-rewrite: `claude --yrb` 让当前这一个 claude 进程经过本地 proxy；其他会话不受影响。
# 由 context-rewrite 插件自动安装，/context-rewrite:rw uninstall 自动移除。

if [ -n "$ZSH_VERSION" ]; then
  if (( $+functions[claude] )) && [[ $functions[claude] != *_ctxrw_run* ]]; then
    functions -c claude _ctxrw_orig_claude
  fi
elif [ -n "$BASH_VERSION" ]; then
  if declare -F claude >/dev/null && ! declare -f claude | grep -q _ctxrw_run; then
    eval "$(declare -f claude | sed '1s/^claude/_ctxrw_orig_claude/')"
  fi
fi

_ctxrw_run() {
  if typeset -f _ctxrw_orig_claude >/dev/null 2>&1; then
    _ctxrw_orig_claude "$@"
  else
    command claude "$@"
  fi
}

claude() {
  local yrb=0 a
  local -a args
  args=()
  for a in "$@"; do
    if [ "$a" = "--yrb" ]; then yrb=1; else args+=("$a"); fi
  done
  if [ "$yrb" = 0 ]; then
    _ctxrw_run "$@"
    return
  fi
  local d="${CTXRW_HOME:-${CLAUDE_CONFIG_DIR:-$HOME/.claude}/context-rewrite}"
  if [ ! -f "$d/ctxrw.py" ]; then
    echo "context-rewrite 未安装或已卸载，按普通方式启动" >&2
    _ctxrw_run "${args[@]}"
    return
  fi
  (
    mkdir -p "$d/sessions" && sh -c ': > "$1/$PPID"' _ "$d/sessions"
    python3 "$d/ctxrw.py" start --quiet || exit 1
    export ANTHROPIC_BASE_URL="http://127.0.0.1:${CTXRW_PORT:-8787}" CTXRW_YRB=1
    _ctxrw_run "${args[@]}"
  )
}
