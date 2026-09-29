# cyberchick-skills

CyberChickZ 的工具集，每个工具是一个独立插件。

## 安装

Claude Code：
```
/plugin marketplace add CyberChickZ/cyberchick-skills
/plugin install <插件名>@cyberchick-skills
```

Codex：
```sh
codex plugin marketplace add CyberChickZ/cyberchick-skills
codex plugin add <插件名>@cyberchick-skills
```

## 插件

| 插件 | 作用 | Codex |
|---|---|---|
| `context-rewrite` | 请求发出前改写 system prompt 和注入内容（[说明](plugins/context-rewrite/skills/context-rewrite/README.md)） | ✗ |
| `ai-job-search` | 自动找岗、填表投递、更新进度看板 | ✓ |
| `council` | 多代理盲审，防附和 | ✓ |
| `xiaohongshu` | 小红书抓取和视频转录，需要本机 [Spider_XHS](https://github.com/cv-cat/Spider_XHS) | ✓ |
| `checkpoint` | 把对话结论存进项目 memory、按需召回 | ✗ |
| `cyberchick-hooks` | 记录工具调用日志；会话期间防休眠 | ✓ |

## 目录

```
.claude-plugin/marketplace.json   Claude Code 清单
.agents/plugins/marketplace.json  Codex 清单
plugins/<插件名>/                 skills/、hooks/、scripts/
```
改动后升对应插件的版本号。
