#!/bin/bash
# Checkpoint compact-recall hook
# Fires ONLY on compact — full memory reload after context compaction
# Reads all project memory files and injects as additionalContext

HOOK_INPUT=$(cat)
CWD=$(echo "$HOOK_INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('cwd',''))" 2>/dev/null || echo "")

# Derive project memory dir from cwd (Claude Code convention: / → -)
MEMORY_INDEX=""
if [ -n "$CWD" ]; then
  PROJECT_KEY=$(echo "$CWD" | sed 's|/|-|g')
  CANDIDATE="${HOME}/.claude/projects/${PROJECT_KEY}/memory/MEMORY.md"
  [ -f "$CANDIDATE" ] && MEMORY_INDEX="$CANDIDATE"
fi
# Fallback: scan all project dirs
if [ -z "$MEMORY_INDEX" ]; then
  for dir in "${HOME}/.claude/projects/"*/memory/MEMORY.md; do
    [ -f "$dir" ] && MEMORY_INDEX="$dir" && break
  done
fi

[ -z "$MEMORY_INDEX" ] && exit 0

MEMORY_DIR=$(dirname "$MEMORY_INDEX")
ENTRY_COUNT=$(grep -c '^\- \[' "$MEMORY_INDEX" 2>/dev/null || echo "0")
[ "$ENTRY_COUNT" -eq 0 ] && exit 0

# Collect ALL memory file contents for full injection
FULL_DUMP="[Checkpoint Post-Compact — Full Memory Reload]

Context was just compacted. Loading ALL ${ENTRY_COUNT} project memories to rebuild context.
Memory dir: ${MEMORY_DIR}/

"

for f in "${MEMORY_DIR}"/*.md; do
  [ "$(basename "$f")" = "MEMORY.md" ] && continue
  [ -f "$f" ] || continue
  FULL_DUMP="${FULL_DUMP}--- $(basename "$f") ---
$(cat "$f")

"
done

# JSON escape
escape_for_json() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    s="${s//$'\n'/\\n}"
    s="${s//$'\r'/\\r}"
    s="${s//$'\t'/\\t}"
    printf '%s' "$s"
}

escaped=$(escape_for_json "$FULL_DUMP")
printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' "$escaped"
exit 0
