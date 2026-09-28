#!/usr/bin/env python3
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time

CLAUDE_DIR = os.path.expanduser(os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude")
HOME = os.path.expanduser(os.environ.get("CTXRW_HOME") or os.path.join(CLAUDE_DIR, "context-rewrite"))
RULES = os.path.join(HOME, "rules.json")
SESSIONS = os.path.join(HOME, "sessions")
PORT = int(os.environ.get("CTXRW_PORT", "8787"))
SRC = os.path.dirname(os.path.abspath(__file__))
RCS = [os.path.expanduser(p) for p in os.environ.get("CTXRW_RCS", "~/.zshrc:~/.bashrc").split(":")]
PLUGINS_DIR = os.path.expanduser(os.environ.get("CTXRW_PLUGINS_DIR") or os.path.join(CLAUDE_DIR, "plugins"))
MARK_BEGIN = "# >>> context-rewrite >>>"
MARK_END = "# <<< context-rewrite <<<"
RC_BLOCK = f'{MARK_BEGIN}\n[ -f "{HOME}/yrb.sh" ] && . "{HOME}/yrb.sh"\n{MARK_END}\n'
FILES = ("ctxrw.py", "proxy.py", "yrb.sh")
USER_SKILL = os.path.join(os.path.expanduser(os.environ.get("CTXRW_SKILLS_DIR") or os.path.join(CLAUDE_DIR, "skills")), "yrb")
SKILL_MARK = "<!-- managed by context-rewrite -->"

USAGE = """/context-rewrite — 发送请求前，对 system prompt、system-reminder 和对话内容做 find/replace

快速开始
  1. /context-rewrite install                装上 claude --yrb，然后新开终端 tab 执行 claude --yrb --continue
  2. /context-rewrite auto <描述>            用一句话说想改什么，Claude 帮你写规则；或者 /context-rewrite capture 看原文后自己写
  3. /context-rewrite list                   看规则；/context-rewrite off 临时关掉；出问题先跑 /context-rewrite doctor

安装
  install                      装上 claude --yrb（可重复执行，rc 里只会有一段）
  uninstall                    彻底卸载：--yrb、proxy、规则、插件本身
  doctor                       检查每个环节，能修的自动修好

快照（改规则、改 rc 之前都会自动存一份，保留最近 30 份）
  snapshots                    列出快照
  snapshot [名字]              手动存一份
  restore [序号]               恢复到某个快照；不写序号就列出快照。不经过模型，对话报错时也能用
                               终端里也能用: python3 ~/.claude/context-rewrite/ctxrw.py restore 1
  help                         显示这份说明

AI 编写
  auto <描述>                  用一句话描述想改什么，由 Claude（sonnet, low）找原文、写规则，勾选确认后写入

找原文
  capture                      显示上一次实际发出去的 system prompt 和注入内容（替换前），并存成文件

规则
  "原文" "替换" [选项]          加一条规则，下一次请求生效（add 可省略）
      --regex                  原文按正则匹配，替换里可以用 \\1 引用分组
      --ignore-case            忽略大小写
      --scope [system,user,assistant] 只在指定位置替换（默认三处都替换）；--scope 后面不写就弹出选择框
  list                         列出规则
  rm [序号...]                 删除规则；不写序号就弹出选择框
  toggle [序号...]             启用 / 停用规则；不写序号就弹出选择框
  scope [序号] [system,user,assistant|all]   修改规则的替换位置；参数不全就弹出选择框

开关
  on | off                     总开关，下一次请求生效
  status                       总开关、proxy 状态、当前会话是否 --yrb、规则列表

只有用 claude --yrb 启动的会话会被替换，其他会话不受影响。
参数写全的命令直接显示结果，不进对话历史、不调用模型；
弹出选择框的命令需要 Claude 来显示界面，会调用一次模型。"""

PIDFILE = os.path.join(HOME, "proxy.pid")
SNAP_DIR = os.path.join(HOME, "snapshots")
SNAP_KEEP = 30
ACTION = {"name": ""}

COMMANDS = {"snapshot", "snapshots", "restore", "doctor", "on", "off", "status", "list", "add", "add-json", "auto", "rm", "toggle", "scope", "start", "install", "capture", "uninstall", "hook", "ui"}
SCOPES = ("system", "user", "assistant")
SCOPE_DESC = {"system": "system prompt", "user": "用户消息、system-reminder、工具结果", "assistant": "模型之前的回复"}


def load():
    try:
        with open(RULES) as f:
            return json.load(f)
    except FileNotFoundError:
        return {"enabled": True, "rules": []}


def take_snapshot(action, rcs=()):
    import datetime
    files = {}
    if os.path.exists(RULES):
        files["rules.json"] = RULES
    for rc in rcs:
        if os.path.exists(rc):
            files["rc-" + os.path.basename(rc).lstrip(".")] = rc
    if not files:
        return None
    now = datetime.datetime.now()
    sid = now.strftime("%Y%m%d-%H%M%S-%f")[:-3]
    d = os.path.join(SNAP_DIR, sid)
    os.makedirs(d, exist_ok=True)
    for name, src in files.items():
        shutil.copy2(src, os.path.join(d, name))
    try:
        n_rules = len(json.load(open(RULES)).get("rules", [])) if os.path.exists(RULES) else 0
    except (OSError, json.JSONDecodeError):
        n_rules = "?"
    with open(os.path.join(d, "meta.json"), "w") as f:
        json.dump({"time": now.strftime("%Y-%m-%d %H:%M:%S"), "action": action or "",
                   "files": files, "rules": n_rules}, f, ensure_ascii=False, indent=2)
    snaps = list_snapshots()
    for old in snaps[SNAP_KEEP:]:
        shutil.rmtree(os.path.join(SNAP_DIR, old["id"]), ignore_errors=True)
    return sid


def list_snapshots():
    out = []
    try:
        ids = sorted(os.listdir(SNAP_DIR), reverse=True)
    except OSError:
        return out
    for sid in ids:
        try:
            with open(os.path.join(SNAP_DIR, sid, "meta.json")) as f:
                m = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        m["id"] = sid
        out.append(m)
    return out


def show_snapshots(snaps):
    if not snaps:
        print("还没有快照（改规则或 install 之前会自动存）")
        return
    print("快照（最新在前）：")
    for i, m in enumerate(snaps, 1):
        what = []
        if "rules.json" in m["files"]:
            what.append(f"规则 {m['rules']} 条")
        what += [os.path.basename(p) for k, p in m["files"].items() if k.startswith("rc-")]
        print(f"  {i:>2}. {m['time']}  {m['action'][:30]}  —  " + " + ".join(what))
    print("\n恢复: /context-rewrite restore <序号>（恢复前会先把当前状态也存一份，恢复本身可以撤销）")


def restore(args):
    snaps = list_snapshots()
    if not args:
        show_snapshots(snaps)
        return
    key = args[0]
    m = None
    if key.isdigit() and 1 <= int(key) <= len(snaps):
        m = snaps[int(key) - 1]
    else:
        m = next((x for x in snaps if x["id"] == key), None)
    if not m:
        sys.exit("没有这个快照，/context-rewrite restore 看列表")
    rcs = [p for k, p in m["files"].items() if k.startswith("rc-")]
    take_snapshot("restore 之前", rcs)
    for name, dst in m["files"].items():
        shutil.copy2(os.path.join(SNAP_DIR, m["id"], name), dst)
        print(f"✓ 已恢复 {dst}")
    print(f"\n已回到 {m['time']} 的状态（{m['action']}）。撤销这次恢复: /context-rewrite restore 1")
    if "rules.json" in m["files"]:
        print("规则从下一次请求开始按快照生效。")
        show(load())
    if rcs:
        print("rc 文件已恢复，新开的终端生效。")


def save(cfg):
    os.makedirs(HOME, exist_ok=True)
    new = json.dumps(cfg, ensure_ascii=False, indent=2)
    if os.path.exists(RULES) and open(RULES).read() != new:
        take_snapshot(f"{ACTION['name']} 之前")
    tmp = RULES + ".tmp"
    with open(tmp, "w") as f:
        f.write(new)
    os.replace(tmp, RULES)


def running():
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def yrb_session():
    return os.environ.get("CTXRW_YRB") == "1" and f":{PORT}" in os.environ.get("ANTHROPIC_BASE_URL", "")


def sync_files():
    os.makedirs(HOME, exist_ok=True)
    for name in FILES:
        src, dst = os.path.join(SRC, name), os.path.join(HOME, name)
        if src != dst and (not os.path.exists(dst) or open(src, "rb").read() != open(dst, "rb").read()):
            shutil.copy(src, dst)


def target_rcs():
    return [rc for rc in RCS if os.path.exists(rc) or rc.endswith("zshrc")]


def installed():
    return os.path.exists(os.path.join(HOME, "yrb.sh")) and any(
        os.path.exists(rc) and RC_BLOCK in open(rc).read() for rc in target_rcs())


def plugin_installed():
    return bool(installed_plugin_entries())


def stale_files():
    return [n for n in FILES if not os.path.exists(os.path.join(HOME, n)) or
            (os.path.join(SRC, n) != os.path.join(HOME, n) and open(os.path.join(SRC, n), "rb").read() != open(os.path.join(HOME, n), "rb").read())]


def remove_skill():
    """旧版本会额外生成 ~/.claude/skills/yrb，导致菜单里出现两个命令；现在插件自带的 /context-rewrite 就够了，清掉旧的。"""
    md = os.path.join(USER_SKILL, "SKILL.md")
    if os.path.exists(md) and SKILL_MARK in open(md).read():
        shutil.rmtree(USER_SKILL, ignore_errors=True)
        print(f"✓ 已删除旧版生成的 {USER_SKILL}")
        return True
    return False


def install():
    sync_files()
    pending = [rc for rc in target_rcs() if not (os.path.exists(rc) and RC_BLOCK in open(rc).read())]
    if pending:
        take_snapshot("install 之前", pending)
    changed = remove_skill()
    done, failed = migrate_legacy()
    for d in done:
        print(f"✓ 已卸载{d}（旧版命令 /context-rewrite:yrb，会和新版重复拦截）")
        changed = True
    for f in failed:
        print(f"✗ {f}")
    for rc in target_rcs():
        text = open(rc).read() if os.path.exists(rc) else ""
        if RC_BLOCK in text:
            print(f"· {rc} 已装好，跳过")
            continue
        if MARK_BEGIN in text:
            strip_rc(rc)
            text = open(rc).read()
        with open(rc, "a") as f:
            f.write(("\n" if text and not text.endswith("\n") else "") + "\n" + RC_BLOCK)
        print(f"✓ 已写入 {rc}")
        changed = True
    print(f"✓ 脚本已同步到 {HOME}")
    if not changed:
        print("（已经是安装好的状态，没有改动）")
    print()
    if yrb_session():
        print("当前会话已经是 --yrb 启动的，规则现在就生效，不用重启。")
        return
    print("最后一步：用 --yrb 重启这段对话（二选一）")
    print("  · 推荐：关掉或新开一个终端 tab，执行")
    print("      claude --yrb --continue")
    print("  · 留在当前 tab：退出 claude 后执行")
    print("      source ~/.zshrc && claude --yrb --continue")
    print()
    print("注意：source 必须在 claude 外面、你自己的终端里执行；在对话里用 ! 执行没有用。")
    print("之后新开的终端里直接 claude --yrb 就行。")


def stop_proxy():
    if not running():
        return None
    pids = set()
    try:
        with open(PIDFILE) as f:
            pids.add(int(f.read().strip()))
    except (OSError, ValueError):
        pass
    r = subprocess.run(["lsof", "-nP", "-t", f"-iTCP:{PORT}", "-sTCP:LISTEN"], capture_output=True, text=True)
    for line in r.stdout.split():
        pid = int(line)
        cmd = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True).stdout
        if "proxy.py" in cmd:
            pids.add(pid)
    for pid in pids:
        try:
            os.kill(pid, 15)
        except (ProcessLookupError, PermissionError):
            pass
    for _ in range(20):
        if not running():
            return True
        time.sleep(0.1)
    return not running()


def start():
    if running():
        return
    os.makedirs(HOME, exist_ok=True)
    p = subprocess.Popen([sys.executable, os.path.join(HOME, "proxy.py")], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=open(os.path.join(HOME, "proxy.err"), "a"),
                         start_new_session=True)
    with open(PIDFILE, "w") as f:
        f.write(str(p.pid))
    for _ in range(30):
        if running():
            return
        time.sleep(0.1)
    sys.exit(f"context-rewrite: proxy 启动失败，看 {HOME}/proxy.err")


def strip_rc(rc):
    if not os.path.exists(rc):
        return False
    text = open(rc).read()
    new = re.sub(r"\n*" + re.escape(MARK_BEGIN) + r".*?" + re.escape(MARK_END) + r"\n?", "\n", text, flags=re.S)
    if new == text:
        return False
    with open(rc, "w") as f:
        f.write(new)
    return True


def installed_plugin_entries(name):
    try:
        with open(os.path.join(PLUGINS_DIR, "installed_plugins.json")) as f:
            plugins = json.load(f).get("plugins", {})
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    return [(key, e) for key, entries in plugins.items() if key.split("@")[0] == name for e in entries]


def has_marketplace(name):
    try:
        with open(os.path.join(PLUGINS_DIR, "known_marketplaces.json")) as f:
            return name in json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return False


def migrate_legacy():
    """旧版叫 context-rewrite 插件（命令 /context-rewrite:yrb）。它的 hook 会和新版同时拦截命令，必须卸掉。返回 (已处理, 失败)。"""
    done, failed = [], []
    claude = shutil.which("claude") or "claude"
    cmds = [([claude, "plugin", "uninstall", key, "--scope", e.get("scope", "user"), "-y"], e.get("projectPath"), f"旧插件 {key}")
            for key, e in installed_plugin_entries("context-rewrite")]
    if has_marketplace("context-rewrite"):
        cmds.append(([claude, "plugin", "marketplace", "remove", "context-rewrite"], None, "旧 marketplace context-rewrite"))
    for cmd, cwd, label in cmds:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd or None, timeout=60)
            if r.returncode:
                raise RuntimeError((r.stderr or r.stdout).strip())
            done.append(label)
        except Exception as ex:
            failed.append(f"{label}: {ex}；手动执行 {' '.join(cmd)}")
    return done, failed


def uninstall():
    ok = True
    was_yrb = yrb_session()
    for rc in RCS:
        if strip_rc(rc):
            print(f"✓ 已从 {rc} 移除 --yrb")
    remove_skill()

    stopped = stop_proxy()
    if stopped:
        print(f"✓ proxy 已停止（127.0.0.1:{PORT} 已释放）")
    elif stopped is False:
        ok = False
        print(f"✗ proxy 没能停掉，手动执行: lsof -nP -iTCP:{PORT} -sTCP:LISTEN 找到进程后 kill")

    legacy_plist = os.path.expanduser("~/Library/LaunchAgents/com.context-rewrite.proxy.plist")
    if os.path.exists(legacy_plist):
        subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/com.context-rewrite.proxy"], capture_output=True)
        os.remove(legacy_plist)
        print("✓ 已移除旧版 launchd 常驻")

    done, failed = migrate_legacy()
    for d in done:
        print(f"✓ 已卸载{d}")
    for f in failed:
        ok = False
        print(f"✗ {f}")

    if os.path.exists(HOME):
        shutil.rmtree(HOME, ignore_errors=True)
        print(f"✓ 已删除 {HOME}（规则、日志、脚本）")

    left = [HOME] if os.path.exists(HOME) else []
    left += [rc for rc in RCS if os.path.exists(rc) and MARK_BEGIN in open(rc).read()]
    if left or not ok:
        print("⚠ 未完全清除: " + "; ".join(left or ["见上方失败项"]))
    else:
        print("✓ 已 100% 卸载")
    print()
    if was_yrb:
        print("当前这个会话是 --yrb 启动的，proxy 已停，接下来发消息会连不上。退出后用普通方式重开即可：claude --continue")
        print("其他 --yrb 会话同理需要重开；普通会话不受任何影响。")
    print("已经开着的终端里 claude 函数还在内存中，但会自动退回普通启动；新开的终端里就彻底没有了。")
    print("cyberchick-skills 插件本身还在（里面可能还有别的工具），/context-rewrite 命令还能用来重新 install。")
    print("连插件一起删：claude plugin uninstall cyberchick-skills@cyberchick-skills")


def fetch_snapshot():
    import urllib.request
    if not running():
        return None
    sid = os.environ.get("CTXRW_SESSION_ID", "")
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/__ctxrw/last?session={sid}", timeout=5) as r:
            res = json.load(r)
    except Exception:
        return None
    return res if res.get("snapshot") else None


def snapshot_text(res, bar="─" * 60):
    snap = res["snapshot"]
    out = [f"══ SYSTEM PROMPT ({len(snap['system'])} 块) ══"]
    for t in snap["system"]:
        out += [t, bar]
    for label, ts in snap["messages"]:
        out.append(f"══ {label}（含注入的 system-reminder）══")
        for t in ts:
            out += [t, bar]
    return "\n".join(out)


def capture():
    if os.environ.get("CLAUDECODE") and not yrb_session():
        sys.exit("capture 只能在用 claude --yrb 启动的会话里用（普通会话不经过 proxy）")
    if not running():
        sys.exit("proxy 没在运行")
    res = fetch_snapshot()
    if not res:
        sys.exit("这个会话还没有发过请求，先随便发一句话，再执行 capture")
    snap = res["snapshot"]
    bar = "─" * 60
    out = [f"上一次请求（{snap['time']}，model={snap['model']}）的原文，替换之前：", ""]
    if not res["matched"]:
        out[1:1] = ["⚠ 没找到当前会话的记录，下面显示的是最近一个 --yrb 会话的请求"]
    out += [f"══ SYSTEM PROMPT ({len(snap['system'])} 块) ══"]
    for t in snap["system"]:
        out += [t, bar]
    for label, ts in snap["messages"]:
        out.append(f"══ {label}（含注入的 system-reminder）══")
        for t in ts:
            out += [t, bar]
    text = "\n".join(out)
    path = os.path.join(HOME, "captured.txt")
    with open(path, "w") as f:
        f.write(text)
    print(text)
    print(f"\n已存到 {path}。找到要改的原文后：/context-rewrite \"原文\" \"替换\"")


def hook():
    """UserPromptSubmit / UserPromptExpansion：拦下 /context-rewrite，直接执行并把结果显示给用户，不进上下文、不调用模型。"""
    import contextlib
    import io
    import shlex
    try:
        inp = json.load(sys.stdin)
    except Exception:
        return
    event = inp.get("hook_event_name")
    if event == "UserPromptSubmit":
        prompt = (inp.get("prompt") or "").strip()
        m = re.match(r"^/(?:cyberchick-skills:)?context-rewrite(?:\s+(.*))?$", prompt, re.S)
        if not m:
            return
        raw = m.group(1) or ""
    elif event == "UserPromptExpansion":
        if inp.get("command_name") not in ("context-rewrite", "cyberchick-skills:context-rewrite"):
            return
        raw = inp.get("command_args") or ""
    else:
        return
    os.environ["CTXRW_SESSION_ID"] = inp.get("session_id", "")
    buf = io.StringIO()
    try:
        argv = shlex.split(raw)
        if needs_ui(argv):
            return
        with contextlib.redirect_stdout(buf):
            try:
                main(argv)
            except SystemExit as e:
                if e.code not in (None, 0):
                    print(e.code if isinstance(e.code, str) else f"退出码 {e.code}")
    except ValueError as e:
        buf.write(f"参数解析失败: {e}")
    print(json.dumps({"decision": "block", "reason": buf.getvalue().rstrip() or "（无输出）"}, ensure_ascii=False))


def normalize(argv):
    if argv and argv[0] not in COMMANDS and len(argv) >= 2:
        return ["add"] + argv
    return argv


def bare_scope(args):
    if "--scope" not in args:
        return False
    i = args.index("--scope")
    return i == len(args) - 1 or args[i + 1].startswith("--")


def needs_ui(argv):
    """参数不全、需要弹选择框的命令：交给模型用 AskUserQuestion。"""
    argv = normalize(argv)
    if not argv:
        return False
    cmd, args = argv[0], argv[1:]
    if cmd in ("rm", "toggle"):
        return not args and bool(load()["rules"])
    if cmd == "scope":
        return len(args) < 2 and bool(load()["rules"])
    if cmd == "add":
        return bare_scope(args)
    if cmd == "auto":
        return bool(args)
    return False


def rule_line(i, r):
    state = "启用" if r.get("enabled", True) else "停用"
    scope = ",".join(r["scope"]) if r.get("scope") else "全部"
    extra = " 正则" if r.get("regex") else ""
    return f"{r['find']!r} → {r.get('replace', '')!r}（{state}，范围: {scope}{extra}）"


def ui(argv):
    import shlex
    if argv[:1] == ["--session"]:
        if len(argv) > 1 and not argv[1].startswith("$"):
            os.environ["CTXRW_SESSION_ID"] = argv[1]
        argv = argv[2:]
    argv = normalize(argv)
    sid = os.environ.get("CTXRW_SESSION_ID")
    if not needs_ui(argv):
        main(argv)
        return
    me = f"python3 {os.path.abspath(__file__)}" + (f" --session {sid}" if sid else "")
    cmd, args = argv[0], argv[1:]
    rules = load()["rules"]
    shown = rules[:16]
    head = ["[context-rewrite 交互选择] 用 AskUserQuestion 弹出下面的选择框，用户选完后用 Bash 执行对应命令，再把命令输出原样告诉用户。",
            "除此之外不要做任何事，不要解释、不要总结。用户取消或什么都没选时，只回复「已取消」。", ""]

    def rule_options(title):
        out = [f"问题「{title}」，multiSelect 按下面要求设置。选项每个问题最多 4 个：规则超过 4 条时拆成多个问题（每个问题 4 条，最多 4 个问题），header 写「规则 1-4」「规则 5-8」这样。"]
        out += [f"  label: \"#{i}\"  description: \"{rule_line(i, r)}\"" for i, r in enumerate(shown, 1)]
        if len(rules) > 16:
            out.append(f"（还有 {len(rules) - 16} 条没列出，提示用户可以直接输入 /context-rewrite {cmd} <序号>）")
        return out

    if cmd == "auto":
        auto_prompt(" ".join(args), me, rules)
        return

    scope_opts = [f"  label: \"{s}\"  description: \"{SCOPE_DESC[s]}\"" for s in SCOPES]
    if cmd in ("rm", "toggle"):
        verb = "删除" if cmd == "rm" else "启用 / 停用（选中的会切换状态）"
        lines = head + rule_options(f"要{verb}哪些规则？") + ["multiSelect: true", "",
                 f"执行: {me} {cmd} <选中的序号，空格分隔，不带 #>"]
    elif cmd == "scope":
        if args:
            lines = head + [f"问题「规则 #{args[0]} 在哪些位置替换？」header「替换范围」multiSelect: true"] + scope_opts + ["",
                     f"执行: {me} scope {args[0]} <选中的项，逗号分隔；三个都选就写 all>"]
        else:
            lines = head + ["在同一次 AskUserQuestion 里问两个问题：", "问题 1：" ] + rule_options("改哪条规则的替换范围？") + [
                "  （这一问 multiSelect: false）",
                "问题 2：「在哪些位置替换？」header「替换范围」multiSelect: true"] + scope_opts + ["",
                f"执行: {me} scope <选中的规则序号，不带 #> <选中的范围，逗号分隔；三个都选就写 all>"]
    else:
        i = args.index("--scope")
        template = [a for a in args[:i + 1]] + ["__SCOPES__"] + args[i + 1:]
        lines = head + [f"问题「这条规则在哪些位置替换？」header「替换范围」multiSelect: true"] + scope_opts + ["",
                 f"执行（把 __SCOPES__ 换成选中的项，逗号分隔；三个都选就写 all）: {me} add {shlex.join(template)}"]
    print("\n".join(lines))


def auto_prompt(desc, me, rules):
    res = fetch_snapshot()
    lines = [
        "[context-rewrite 交互选择 · 自动编写规则]",
        f"用户需求：{desc}",
        "",
        "任务：根据用户需求，从下面「上一次请求原文」里找到要修改的片段，编写替换规则。除下面的步骤外不要做任何事，不要解释。",
        "1. find 必须从原文里逐字复制（标点、空格、换行都要一致），不要凭记忆写。尽量短，但要能唯一定位。",
        "2. 要删除就把 replace 写成空字符串 \"\"；要改写就写改写后的文字。",
        "3. scope：原文在 SYSTEM PROMPT 部分就写 [\"system\"]，在 user 消息或 system-reminder 里就写 [\"user\"]；两边都有就省略 scope。",
        "4. 只有原文存在多种写法时才用 \"regex\": true。",
        "5. 用 AskUserQuestion 让用户勾选要添加的规则：multiSelect: true，每条规则一个选项，label 写「规则1」「规则2」…，"
        "description 写「find 摘要 → replace 摘要」（各不超过 40 字）。每个问题最多 4 个选项，超过就拆成多个问题。找不到相关原文时直接告诉用户，不要编造。",
        "6. 把用户勾选的规则写成 JSON 数组（字段 find / replace / scope / regex），用 Bash 执行：",
        f"   {me} add-json <<'CTXRW_EOF'",
        "   [{\"find\": \"...\", \"replace\": \"...\", \"scope\": [\"system\"]}]",
        "   CTXRW_EOF",
        "7. 把命令输出原样告诉用户。用户什么都没选时只回复「已取消」。",
        "",
        "已有规则（已生效的规则会让下面的原文显示成替换后的样子）：",
    ]
    lines += [f"  #{i} {rule_line(i, r)}" for i, r in enumerate(rules, 1)] or ["  （无）"]
    lines.append("")
    if res:
        lines += ["══════════ 上一次请求原文（替换前）══════════", snapshot_text(res)]
    else:
        lines += ["（没拿到上一次请求原文：当前会话不是 --yrb 启动的，或还没发过消息。只能根据你自己上下文里看到的 system prompt 和 system-reminder 原文来找；"
                  "写入时会提示无法核对。）"]
    print("\n".join(lines))


def add_rules(new, cfg):
    res = fetch_snapshot()
    corpus = None
    if res:
        snap = res["snapshot"]
        corpus = {"system": "\n".join(snap["system"]),
                  "user": "\n".join(t for _, ts in snap["messages"] for t in ts)}
    for r in new:
        if not isinstance(r, dict) or not isinstance(r.get("find"), str) or not r["find"]:
            sys.exit(f"规则格式不对: {r!r}")
        rule = {"find": r["find"], "replace": str(r.get("replace", "")), "enabled": True}
        if r.get("regex"):
            try:
                re.compile(r["find"])
            except re.error as e:
                sys.exit(f"正则无效 {r['find']!r}: {e}")
            rule["regex"] = True
        if r.get("ignore_case"):
            rule["ignore_case"] = True
        sc = r.get("scope")
        if sc:
            sc = parse_scope(",".join(sc) if isinstance(sc, list) else str(sc))
            if sc:
                rule["scope"] = sc
        cfg["rules"].append(rule)
        n = len(cfg["rules"])
        if corpus is None:
            print(f"✓ 已添加 #{n}（无法核对原文：没有上一次请求的记录）")
            continue
        pat = re.compile(rule["find"] if rule.get("regex") else re.escape(rule["find"]), re.I if rule.get("ignore_case") else 0)
        where = {k: len(pat.findall(v)) for k, v in corpus.items() if k in (rule.get("scope") or ("system", "user"))}
        hits = sum(where.values())
        if hits:
            print(f"✓ 已添加 #{n}，在上一次请求里命中 {hits} 处（" + "，".join(f"{k} {v}" for k, v in where.items() if v) + "）")
        else:
            print(f"⚠ 已添加 #{n}，但在上一次请求里没找到这段原文，可能不会生效；可以 /context-rewrite rm {n} 删掉")
    save(cfg)


def doctor():
    ok_n, fixed, bad = 0, [], []

    def ok(msg):
        nonlocal ok_n
        ok_n += 1
        print(f"✓ {msg}")

    def fix(msg):
        fixed.append(msg)
        print(f"🔧 {msg}")

    def fail(msg, how):
        bad.append(msg)
        print(f"✗ {msg}\n    → {how}")

    print("context-rewrite 诊断\n")

    print("[安装]")
    stale = stale_files()
    if stale:
        sync_files()
        fix(f"脚本缺失或过期，已同步: {', '.join(stale)}")
    else:
        ok(f"脚本齐全: {HOME}")
    for rc in target_rcs():
        text = open(rc).read() if os.path.exists(rc) else ""
        n = text.count(MARK_BEGIN)
        if n == 1 and RC_BLOCK in text:
            ok(f"{rc} 里有 --yrb")
            continue
        take_snapshot("doctor 修 rc 之前", [rc])
        strip_rc(rc)
        text = open(rc).read() if os.path.exists(rc) else ""
        with open(rc, "a") as f:
            f.write(("\n" if text and not text.endswith("\n") else "") + "\n" + RC_BLOCK)
        fix(f"{rc} 里的 --yrb " + ("缺失" if n == 0 else "重复或过期") + "，已重写（新开的终端生效）")
    if remove_skill():
        fix("删除了旧版生成的 ~/.claude/skills/yrb")
    done, failed = migrate_legacy()
    if done:
        fix("卸载了旧版: " + "、".join(done) + "（它会和新版重复拦截命令）")
    for f in failed:
        fail("旧版插件没卸掉", f)
    clash = os.path.join(os.path.dirname(USER_SKILL), "context-rewrite", "SKILL.md")
    if os.path.exists(clash):
        fail(f"{os.path.dirname(clash)} 是另一个同名 skill，敲 /context-rewrite 会运行它而不是本插件",
             "改用全名 /cyberchick-skills:context-rewrite，或者把那个 skill 改名")
    else:
        ok("/context-rewrite 命令由 cyberchick-skills 插件提供")

    print("\n[规则]")
    try:
        with open(RULES) as f:
            cfg = json.load(f)
        ok(f"rules.json 可读，{len(cfg.get('rules', []))} 条规则，总开关 {'ON' if cfg.get('enabled', True) else 'OFF'}")
    except FileNotFoundError:
        cfg = {"enabled": True, "rules": []}
        ok("还没有规则")
    except json.JSONDecodeError as e:
        backup = RULES + f".broken-{int(time.time())}"
        os.replace(RULES, backup)
        cfg = {"enabled": True, "rules": []}
        save(cfg)
        fix(f"rules.json 损坏（{e}），已备份到 {backup} 并重置为空")
    changed = False
    for i, r in enumerate(cfg.get("rules", []), 1):
        problem = None
        if not isinstance(r, dict) or not r.get("find"):
            problem = "原文为空"
        elif r.get("regex"):
            try:
                re.compile(r["find"])
            except re.error as e:
                problem = f"正则无效: {e}"
        if r.get("scope") and any(x not in SCOPES for x in r["scope"]):
            problem = f"范围无效: {r['scope']}"
        if problem and r.get("enabled", True):
            r["enabled"] = False
            changed = True
            fix(f"规则 #{i} {problem}，已停用")
    if changed:
        save(cfg)

    print("\n[当前会话]")
    if os.environ.get("CLAUDECODE"):
        if yrb_session():
            ok("当前会话是 --yrb 启动的，会经过替换")
        else:
            fail("当前会话不是 --yrb 启动的，规则对它不生效",
                 "新开终端 tab 执行 claude --yrb --continue（当前 tab 要先 source ~/.zshrc）")

    print("\n[proxy]")
    if running():
        r = subprocess.run(["lsof", "-nP", "-t", f"-iTCP:{PORT}", "-sTCP:LISTEN"], capture_output=True, text=True)
        cmds = [subprocess.run(["ps", "-o", "command=", "-p", p], capture_output=True, text=True).stdout.strip() for p in r.stdout.split()]
        if cmds and not any("proxy.py" in c for c in cmds):
            fail(f"端口 {PORT} 被别的程序占用: {cmds[0][:80]}", f"关掉那个程序，或用 CTXRW_PORT=其他端口 启动 claude --yrb")
        else:
            ok(f"proxy 在运行（127.0.0.1:{PORT}）")
    elif yrb_session():
        try:
            start()
            fix("proxy 没在运行（当前 --yrb 会话会连不上），已重新启动")
        except SystemExit as e:
            fail("proxy 启动失败", str(e))
    else:
        ok("proxy 没在运行（没有 --yrb 会话时这是正常的）")
    log = os.path.join(HOME, "proxy.log")
    if os.path.exists(log):
        errs = [l.rstrip() for l in open(log).readlines()[-200:] if "上游返回" in l or "失败" in l or "拒绝" in l or "回退" in l]
        if errs:
            print("  最近的错误（proxy.log）：")
            for l in errs[-5:]:
                print(f"    {l}")
            if any("替换" in l and "没有替换" not in l for l in errs[-5:]):
                print("    → 出错的请求里有替换，可能是某条规则把请求改坏了：先 /context-rewrite off 试试，再逐条 /context-rewrite toggle 排查；")
                print("      或者 /context-rewrite restore 看快照，回到出问题之前的规则")

    print("\n[旧版残留]")
    legacy = []
    plist = os.path.expanduser("~/Library/LaunchAgents/com.context-rewrite.proxy.plist")
    if os.path.exists(plist):
        subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/com.context-rewrite.proxy"], capture_output=True)
        os.remove(plist)
        legacy.append("launchd 常驻")
    settings = os.path.join(CLAUDE_DIR, "settings.json")
    try:
        with open(settings) as f:
            d = json.load(f)
        if f":{PORT}" in d.get("env", {}).get("ANTHROPIC_BASE_URL", ""):
            d["env"].pop("ANTHROPIC_BASE_URL")
            with open(settings + ".tmp", "w") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
                f.write("\n")
            os.replace(settings + ".tmp", settings)
            legacy.append("settings.json 里的全局 ANTHROPIC_BASE_URL")
    except (OSError, json.JSONDecodeError):
        pass
    if legacy:
        fix("已清理: " + "、".join(legacy))
    else:
        ok("没有旧版残留")

    snaps = list_snapshots()
    print("\n[快照]")
    if snaps:
        ok(f"{len(snaps)} 份快照，最新 {snaps[0]['time']}（{snaps[0]['action']}）。回滚: /context-rewrite restore")
    else:
        ok("还没有快照（改规则或 install 之前会自动存）")

    print(f"\n结果: {ok_n} 项正常，{len(fixed)} 项已修复，{len(bad)} 项需要你处理")


def parse_indices(args, n):
    out = []
    for a in args:
        for p in a.replace("#", "").split(","):
            if p.strip():
                i = int(p) - 1
                if not 0 <= i < n:
                    raise ValueError(p)
                out.append(i)
    if not out:
        raise ValueError("empty")
    return sorted(set(out))


def parse_scope(v):
    if v.strip().lower() in ("all", "*"):
        return None
    ss = [s.strip().lower() for s in v.split(",") if s.strip()]
    bad = [s for s in ss if s not in SCOPES]
    if bad or not ss:
        sys.exit(f"范围只能是 {','.join(SCOPES)} 或 all，收到: {v}")
    return None if set(ss) == set(SCOPES) else [s for s in SCOPES if s in ss]


def show(cfg):
    if not cfg["rules"]:
        print("  （无规则）")
    for i, r in enumerate(cfg["rules"], 1):
        flags = [f for f, on in (("regex", r.get("regex")), ("ignore_case", r.get("ignore_case"))) if on]
        if r.get("scope"):
            flags.append("scope=" + ",".join(r["scope"]))
        mark = "✓" if r.get("enabled", True) else "✗"
        print(f"  {i}. [{mark}] {r['find']!r} → {r.get('replace', '')!r}" + (f"  ({' '.join(flags)})" if flags else ""))


def warn(cfg):
    if not cfg.get("enabled"):
        print("⚠ 总开关是 OFF，规则不会生效（/context-rewrite on）")
    if os.environ.get("CLAUDECODE") and not yrb_session():
        print("⚠ 当前会话不是用 claude --yrb 启动的，规则对它不生效；用 --yrb 启动的会话才会替换")


def main(argv):
    if argv[:1] == ["--session"]:
        if len(argv) > 1 and not argv[1].startswith("$"):
            os.environ["CTXRW_SESSION_ID"] = argv[1]
        argv = argv[2:]
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return
    if argv[0] not in COMMANDS and len(argv) >= 2:
        argv = ["add"] + argv
    cmd, args = argv[0], argv[1:]
    ACTION["name"] = " ".join(argv)[:60]

    if cmd == "hook":
        hook()
        return
    if cmd == "uninstall":
        uninstall()
        return
    if cmd == "install":
        install()
        return
    if cmd == "start":
        start()
        return
    if cmd == "doctor":
        doctor()
        return
    if cmd == "restore":
        restore(args)
        return
    if cmd == "snapshots":
        show_snapshots(list_snapshots())
        return
    if cmd == "snapshot":
        sid = take_snapshot("手动: " + (" ".join(args) or "未命名"), target_rcs())
        print(f"✓ 已存快照 {sid}" if sid else "没有可存的内容")
        return
    if cmd == "ui":
        ui(args)
        return

    if installed():
        sync_files()
    else:
        print("⚠ 还没安装 --yrb，先执行 /context-rewrite install\n")
    cfg = load()
    if cmd in ("on", "off"):
        cfg["enabled"] = cmd == "on"
        save(cfg)
        print(f"上下文替换已{'开启' if cfg['enabled'] else '关闭'}，下一次请求生效")
        warn(cfg)
    elif cmd == "status":
        print(f"总开关: {'ON' if cfg.get('enabled') else 'OFF'}")
        print(f"proxy: {'运行中' if running() else '未运行'} (127.0.0.1:{PORT})")
        if os.environ.get("CLAUDECODE"):
            print(f"当前会话: {'--yrb，经过替换' if yrb_session() else '普通会话，不经过替换'}")
        print("规则:")
        show(cfg)
    elif cmd == "list":
        show(cfg)
    elif cmd == "capture":
        capture()
    elif cmd == "add-json":
        try:
            new = json.loads(" ".join(args) if args else sys.stdin.read())
        except json.JSONDecodeError as e:
            sys.exit(f"JSON 解析失败: {e}")
        add_rules(new if isinstance(new, list) else [new], cfg)
        print()
        show(cfg)
        warn(cfg)
    elif cmd == "auto":
        sys.exit("用法: /context-rewrite auto <用一句话描述想改什么>，例如 /context-rewrite auto 去掉所有要求加 Co-Authored-By 的说明")
    elif cmd == "add":
        pos, opts, i = [], {}, 0
        while i < len(args):
            a = args[i]
            if a == "--regex":
                opts["regex"] = True
            elif a == "--ignore-case":
                opts["ignore_case"] = True
            elif a == "--scope" and i + 1 < len(args):
                i += 1
                sc = parse_scope(args[i])
                if sc:
                    opts["scope"] = sc
            elif a == "--scope":
                sys.exit("--scope 后面要写范围（system,user,assistant 或 all）；在对话里不写会弹出选择框")
            else:
                pos.append(a)
            i += 1
        if len(pos) != 2:
            sys.exit("需要两个参数: <find> <replace>（含空格请加引号，replace 为空用 \"\"）")
        if opts.get("regex"):
            try:
                re.compile(pos[0])
            except re.error as e:
                sys.exit(f"正则无效: {e}")
        cfg["rules"].append({"find": pos[0], "replace": pos[1], "enabled": True, **opts})
        save(cfg)
        print(f"已添加规则 #{len(cfg['rules'])}，下一次请求生效")
        show(cfg)
        warn(cfg)
    elif cmd in ("rm", "toggle", "scope"):
        if not cfg["rules"]:
            print("还没有规则。加规则：/context-rewrite \"原文\" \"替换\"")
            return
        if not args or (cmd == "scope" and len(args) < 2):
            sys.exit(f"用法: /context-rewrite {cmd} " + ("<序号> <system,user,assistant|all>" if cmd == "scope" else "<序号...>") + "（在对话里不写参数会弹出选择框）")
        try:
            idx = parse_indices(args[:1] if cmd == "scope" else args, len(cfg["rules"]))
        except ValueError:
            sys.exit("序号无效，先 /context-rewrite list 看看")
        if cmd == "rm":
            for i in reversed(idx):
                cfg["rules"].pop(i)
            print(f"已删除 {len(idx)} 条规则")
        elif cmd == "toggle":
            for i in idx:
                cfg["rules"][i]["enabled"] = not cfg["rules"][i].get("enabled", True)
            print("已切换: " + "、".join(f"#{i + 1} → {'启用' if cfg['rules'][i]['enabled'] else '停用'}" for i in idx))
        else:
            sc = parse_scope(args[1])
            for i in idx:
                if sc:
                    cfg["rules"][i]["scope"] = sc
                else:
                    cfg["rules"][i].pop("scope", None)
            print(f"已修改范围: " + "、".join(f"#{i + 1}" for i in idx) + " → " + (",".join(sc) if sc else "全部"))
        save(cfg)
        show(cfg)
    else:
        sys.exit(f"未知命令: {cmd}\n{USAGE}")


if __name__ == "__main__":
    main(sys.argv[1:])
