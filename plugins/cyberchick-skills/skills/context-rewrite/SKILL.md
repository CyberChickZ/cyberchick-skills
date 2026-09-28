---
name: context-rewrite
description: 发送请求前对 system prompt、system-reminder 和对话内容做 find/replace（加规则、开关、查看原文、安装卸载）
argument-hint: install | auto <描述> | <原文> <替换> [--scope] | capture | list | rm | toggle | scope | status | on | off | doctor | restore | uninstall
disable-model-invocation: true
model: sonnet
effort: low
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/skills/context-rewrite/scripts/ctxrw.py *) AskUserQuestion
---

!`python3 ${CLAUDE_PLUGIN_ROOT}/skills/context-rewrite/scripts/ctxrw.py ui --session ${CLAUDE_SESSION_ID} $ARGUMENTS`

如果上面是「交互选择」说明，就严格照做；否则把上面的输出原样告诉用户，不要做其他事。
