# cyberchick-skills

CyberChickZ 的 Claude Code 工具集。一个仓库（marketplace），每个工具是一个独立插件，想装哪个装哪个。

## 安装
```
/plugin marketplace add CyberChickZ/cyberchick-skills
/plugin install <插件名>@cyberchick-skills
```

## 插件
| 插件 | 命令 | 作用 |
|---|---|---|
| `context-rewrite` | `/context-rewrite` | 发送请求前，对 system prompt、system-reminder 和对话内容做 find/replace；用 `claude --yrb` 启动的会话生效。[README](plugins/context-rewrite/skills/context-rewrite/README.md) |
| `ai-job-search` | `/ai-job-search` | 全自动求职流水线：拉岗、预筛、选简历、派子代理填表、清邮箱、刷新看板。个人资料和筛岗偏好放本机 `~/.claude/cyberchick-skills/ai-job-search/`，第一次用会生成模板 |
| `council` | `/council` | 研究决策的 AI 盲审，防附和 |
| `xiaohongshu` | `/xiaohongshu` | 小红书笔记、搜索、评论抓取和视频转录。依赖本机的 [Spider_XHS](https://github.com/cv-cat/Spider_XHS)，路径用 `XHS_HOME` 指定，默认 `~/git/Spider_XHS` |
| `checkpoint` | `/checkpoint:save` `/checkpoint:read` `/checkpoint:review` `/checkpoint:reload` | 把对话里的结论存进项目 memory、按需召回；上下文压缩后自动重载（MIT） |
| `cyberchick-hooks` | 无 | 个人 hooks：tool-ledger（把输入、工具调用记到 `/tmp/claude_tool_ledger.log`）、caffeinate（会话期间阻止 Mac 休眠） |

菜单里显示为 `/<插件名>:<命令名>`（比如 `/context-rewrite:context-rewrite`），平时直接敲短名 `/context-rewrite` 就行，除非有别的同名命令。

## 目录
```
.claude-plugin/marketplace.json     插件清单
plugins/<插件名>/
  .claude-plugin/plugin.json
  skills/<命令名>/SKILL.md
  hooks/hooks.json                  （有 hook 的插件）
  scripts/
```
加新工具：在 `plugins/` 下建一个插件目录，在 `marketplace.json` 里登记；改动后升对应插件的版本号。
