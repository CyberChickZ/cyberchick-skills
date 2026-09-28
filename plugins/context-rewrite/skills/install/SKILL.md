---
name: install
description: "context-rewrite: Install claude --yrb for context-rewrite (safe to run again)."
disable-model-invocation: true
model: sonnet
effort: low
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/skills/context-rewrite/scripts/ctxrw.py *) AskUserQuestion
---

!`python3 ${CLAUDE_PLUGIN_ROOT}/skills/context-rewrite/scripts/ctxrw.py ui --session ${CLAUDE_SESSION_ID} --pending`

If the output above starts with [context-rewrite interactive], follow those instructions exactly; otherwise relay the output to the user verbatim and do nothing else.
