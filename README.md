# cyberchick-skills

CyberChickZ 的 Claude Code 工具集，一个仓库装所有自己写的 skill 和 hook。

## 安装
```
/plugin marketplace add CyberChickZ/cyberchick-skills
/plugin install cyberchick-skills@cyberchick-skills     # skills
/plugin install cyberchick-hooks@cyberchick-skills      # 个人 hooks（可选）
```

## cyberchick-skills
菜单里显示为 `/cyberchick-skills:<名字>`，平时直接敲 `/<名字>`（除非有别的同名命令）。

| 命令 | 作用 | 备注 |
|---|---|---|
| `/context-rewrite` | 发送请求前，对 system prompt、system-reminder 和对话内容做 find/replace；用 `claude --yrb` 启动的会话生效 | [README](plugins/cyberchick-skills/skills/context-rewrite/README.md) |
| `/ai-job-search` | 全自动求职流水线：拉岗、预筛、选简历、派子代理填表、清邮箱、刷新看板 | 个人资料放本机 `~/.claude/cyberchick-skills/ai-job-search/`，第一次用会生成模板 |
| `/council` | 研究决策的盲审（反附和） | |
| `/xiaohongshu` | 小红书笔记、搜索、评论抓取和视频转录 | 依赖本机的 [Spider_XHS](https://github.com/cv-cat/Spider_XHS)，路径用 `XHS_HOME` 指定，默认 `~/git/Spider_XHS` |
| `/checkpoint-save` `/checkpoint-read` `/checkpoint-review` `/checkpoint-reload` | 把对话里的结论存进项目 memory、按需召回；上下文压缩后自动重载 | MIT |

## cyberchick-hooks
| Hook | 作用 |
|---|---|
| tool-ledger | 把用户输入、工具调用、会话起止记到 `/tmp/claude_tool_ledger.log`（超过 1MB 自动截断） |
| caffeinate | 会话期间阻止 Mac 休眠，会话结束时恢复 |

## 目录
```
.claude-plugin/marketplace.json
plugins/
  cyberchick-skills/   skills/<名字>/SKILL.md、hooks/hooks.json、scripts/
  cyberchick-hooks/    hooks/hooks.json、scripts/
```
加新工具：在 `plugins/cyberchick-skills/skills/` 下建目录，放 `SKILL.md`，升 `plugin.json` 和 `marketplace.json` 的版本号。
