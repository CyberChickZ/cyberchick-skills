# context-rewrite

[English](README.md) | 简体中文

[cyberchick-skills](../../../../README.md) 里的一个插件，可以单独安装。命令：`/context-rewrite`（菜单里显示为 `/context-rewrite:context-rewrite`）；启动参数：`claude --yrb`。

Claude Code 每次请求都会带上一些自动注入的内容，比如默认 system prompt 和 `<system-reminder>`。其中有些行为可能不符合团队要求。这个插件可以在请求发出前对这些内容做 find/replace。

- 只对 `claude --yrb` 启动的会话生效（yrb = you are boss），其他会话完全不受影响
- 这些内容是 Claude Code 在本地每次请求时现拼的，既不在云端，也没有存成文件，所以只能每次请求都改一遍。Claude Code 的 hook 做不到这件事（官方文档写明 `UserPromptSubmit` "can't replace the prompt"），这里用一个只服务 `--yrb` 会话的本地 proxy 来做

## 安装
在任意 claude 对话里：
```
/plugin marketplace add CyberChickZ/cyberchick-skills
/plugin install context-rewrite@cyberchick-skills
/context-rewrite install
```
装好插件就有 `/context-rewrite` 命令。`install` 会在 `~/.zshrc` 末尾挂上 `--yrb`（如果存在 `~/.bashrc` 也会加），并把脚本放到 `~/.claude/context-rewrite/`。可以重复执行，rc 里永远只有一段。

然后新开一个终端 tab，执行 `claude --yrb --continue`（`--continue` 接着刚才那段对话）。如果想留在当前终端，就退出 claude 后执行 `source ~/.zshrc && claude --yrb --continue`。必须重新加载 rc，是因为退出后回到的那个 shell 还没读过新的 rc，子进程改不了它。

## 使用
```sh
claude --yrb              # 可以和其他参数叠加：claude --yrb --resume、claude --yrb --dangerously-skip-permissions ...
```
会话里：
```
/context-rewrite auto 删掉 {Co-Authored-By} 所在的行                  # 原文放 {…}，模型只选操作，脚本生成规则
/context-rewrite verify                                    # 逐条核对规则：上一次真实请求（主会话 + 子代理）里命中哪里、改前改后、proxy 实际替换几处
/context-rewrite capture                                   # 显示上一次实际发出去的 system prompt 和注入内容（替换前原文），同时存成文件
/context-rewrite "原文" "替换"                              # 手动加规则，下一次请求就生效
/context-rewrite "原文" "替换" --scope                      # --scope 后面不写：弹出选择框选替换位置
/context-rewrite 'foo\d+' 'bar' --regex                     # 正则
/context-rewrite list | status | on | off
/context-rewrite rm | toggle | scope                        # 不写序号：弹出选择框；也可以直接写 rm 2 3、toggle 1、scope 2 system
/context-rewrite install | uninstall
/context-rewrite doctor                                     # 检查每个环节，能修的自动修好
/context-rewrite restore [序号] | snapshots | snapshot [名字] # 快照：列出 / 回滚 / 手动存
/context-rewrite help                                       # 用法
```
- 参数写全的命令由 hook 直接执行：结果只显示给你，不进对话历史，不调用模型，不耗 token
- 参数没写全的 `rm` / `toggle` / `scope` / `--scope`，以及 `auto`，需要 Claude 弹出选择框（AskUserQuestion）或写规则。这一轮固定用 **sonnet + low effort**（skill 的 `model` / `effort` 字段），下一句话就切回你原来的模型
- `auto` 不把原文交给模型；模型只看去掉原文后的指令，选一种操作
- 替换后变成空的文本块会被去掉（API 不接受空文本块）；整条消息被清空时留 `(removed)` 占位
- 在同一个 `--yrb` 进程里 `/resume` 老对话、派出去的子 agent，都会经过替换
- 不是从你终端启动的会话（例如后台 agent）不会经过替换
- thinking 块带签名，不会被改；工具调用的参数也不会被改

### 自动补全
每个子命令也是一个独立命令，输入 `/context-rewrite:` 就会列出全部子命令和说明：
`/context-rewrite:install`、`:auto`、`:autowoc`、`:add`、`:capture`、`:verify`、`:list`、`:rm`、`:toggle`、`:scope`、`:on`、`:off`、`:status`、`:doctor`、`:restore`、`:snapshots`、`:snapshot`、`:uninstall`。
`/context-rewrite:capture` 和 `/context-rewrite capture` 完全一样。没有冲突时也可以直接敲短名，比如 `/capture`；`status`、`doctor`、`help` 这几个名字 Claude Code 自己在用，要敲全名。

### 子代理
子代理跑在同一个 claude 进程里，请求同样经过 proxy，所有规则对它们一样生效。
- `/context-rewrite:capture @general-purpose` 查看某个子代理上一次请求的原文（输入 `@` 选子代理即可，手打 `@agent-名字` 也行）。自定义子代理的类型统一记为 `custom`。不带参数的 `capture` 会列出已经记录到的子代理类型。
- `auto` 默认核对的范围是主会话**加上**每种子代理最近一次的完整请求，所以只出现在子代理提示词里的文字也能匹配上。

### auto：说要改什么，原文放进 `{花括号}`
```
/context-rewrite auto 从 {- Entering financial credentials, bank/card/…} 到 {- Downloading or executing files from untrusted sources} 删除
/context-rewrite auto 把 {Creating accounts on the user's behalf} 替换成 {Creating accounts is fine}
```
1. 脚本把每个 `{…}` 里的原文逐字取出（不经过模型，不会抄错）。
2. 剩下的指令（「从 {0} 到 {1} 删除」）交给 Claude（sonnet、low effort、不给工具），它**只从下面 7 种操作里选一个编号**，不写正则：
   1 删这段文字 · 2 删所在整行 · 3 从 A 行删到 B 行（含两端）· 4 删 A 行和 B 行之间（保留两端）· 5 把这段文字换成 X · 6 把所在整行换成 X · 7 把 A 行到 B 行整体换成 X
   都不合适时选 8，只能填固定字段组合：`a`/`b`（找哪段、范围到哪段）、`unit`（文字 / 整行 / 整个文本块）、`keep`（保留哪端）、`new`（换成哪几段原文，或原来匹配到的 a/b）。脚本逐项校验，多一个字段、编号不对、有原文没用上都会拒绝，模型永远碰不到正则。
   这次调用是干净环境：自己的一句英文 system prompt 替换 Claude Code 默认提示词，在空目录里运行，不加载设置、CLAUDE.md、memory、skills、MCP、插件和 hooks。
3. 正则全部由脚本生成。原文只看字母、数字和汉字，中间的标点、空格、换行、markdown 一律忽略，所以 `{A'A  A . A}` 能匹配 `AAAA` 或 `A-A A.A`；Read 工具的行号和列表编号会先去掉。换整行时保留原来的缩进和列表符号。
4. 默认拿上一次完整请求（主会话 + 各子代理的 system、全部消息、工具描述）**按文本块**核对，和 proxy 实际替换的方式一样：命中才加，并给出改前/改后预览。A 和 B 不在同一个文本块里会直接报错（proxy 不能跨块替换）。`auto --no-check …` 或 `autowoc …` 不核对直接加。
5. 整个过程在 hook 里完成，不进对话历史。每次的记录存在 `~/.claude/context-rewrite/auto/`。

「从 A 到 B」默认连 A 和 B 一起删；只想删中间就说「保留两端」。

## 出问题时
先跑 `/context-rewrite doctor`。它会检查并自动修复下面这些：
- 脚本缺失或过期、rc 里的 `--yrb` 缺失或重复、`/context-rewrite` 命令丢失
- `rules.json` 损坏（备份后重置）、无效的正则或范围（停用那条规则）
- `--yrb` 会话里 proxy 挂了（重新启动）
- 旧版残留（launchd 常驻、全局 `ANTHROPIC_BASE_URL`）

修不了的会告诉你怎么处理：当前会话不是 `--yrb`、端口被别的程序占用。proxy 日志里最近的上游报错也会列出来；如果出错的请求里有替换，多半是某条规则把请求改坏了，先 `/context-rewrite off` 试试，再逐条 `/context-rewrite toggle` 排查。

## 坏了怎么恢复
**自动快照：** 改规则（加、删、开关、改范围）和 `install` 修改 rc 之前，都会自动存一份快照，保留最近 30 份，放在 `~/.claude/context-rewrite/snapshots/`。

```
/context-rewrite restore        # 列出快照
/context-rewrite restore 3      # 回到第 3 份；恢复前会先存一份当前状态，想撤销就 /context-rewrite restore 1
/context-rewrite snapshot 调好的一版   # 手动存一份
```
`restore` 由 hook 在本地执行，**不经过 API**，所以某条规则把请求改坏、对话一直报错时照样能用。

**proxy 自动兜底：** 如果某次请求在替换后被 API 以 HTTP 400 拒绝，proxy 会自动改用原文重发，对话不会卡住，同时在 `proxy.log` 里记下是哪次、错误是什么。`/context-rewrite doctor` 会把这些列出来，提示你关掉或回滚那条规则。

**连 claude 都不想开的时候：**
- 不带 `--yrb` 启动 claude 永远不会经过 proxy，不受规则影响
- 终端里可以直接执行：`python3 ~/.claude/context-rewrite/ctxrw.py restore`（或 `off`、`doctor`）

## 卸载
`/context-rewrite uninstall` 会依次：移除 rc 里的 `--yrb`（其余内容原样保留）、停止 proxy、删除 `~/.claude/context-rewrite`（规则、快照、日志、脚本）。context-rewrite 插件本身也会一起卸掉；cyberchick-skills marketplace 保留，因为里面还有别的工具。可以重复执行。
普通会话不受影响。正在运行的 `--yrb` 会话因为 proxy 已停，需要退出后用普通方式重开（`claude --continue`）。

## 原理
- `--yrb` 是一个 shell 函数：它只给这一个 claude 进程设置 `ANTHROPIC_BASE_URL=http://127.0.0.1:8787`，并登记这个会话。如果你原来就有自己的 `claude()` 函数（比如 `--yolo`），它会原样保留，再在外面套一层
- proxy 改写 `/v1/messages` 请求里的 `system`、消息文本和 `tool_result`，然后原样转发给 `api.anthropic.com`，header 全部透传，所以 claude.ai 订阅登录照常可用
- 没有存活的 `--yrb` 会话时 proxy 自动退出，不会常驻后台
- proxy 在内存里记住每个会话最近一次请求的原文（只记主 agent 的），供 `capture` 查看；不会写盘，只有执行 `capture` 时才会写到 `captured.txt`
- 输出语言：默认英文；Claude Code 的 `language` 设置是中文（或系统语言是中文）时显示中文。`CTXRW_LANG=zh|en` 可以强制指定
- 文件位置：`~/.claude/context-rewrite/`，包括 `rules.json`、`proxy.log`（只记替换次数，不记内容）、`captured.txt`
