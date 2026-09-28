---
name: context-rewrite
description: Find/replace the system prompt, system-reminders and conversation before each request is sent (add rules, toggle, capture original text, install/uninstall)
argument-hint: install | auto <instruction with {text}> | <find> <replace> [--scope] | capture | list | rm | toggle | scope | status | on | off | doctor | restore | uninstall
disable-model-invocation: true
model: sonnet
effort: low
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/skills/context-rewrite/scripts/ctxrw.py *) AskUserQuestion
---

!`python3 ${CLAUDE_PLUGIN_ROOT}/skills/context-rewrite/scripts/ctxrw.py ui --session ${CLAUDE_SESSION_ID} --pending`

If the output above starts with [context-rewrite interactive], follow those instructions exactly; otherwise relay the output to the user verbatim and do nothing else.
