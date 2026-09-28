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


def _lang_from_value(v):
    v = str(v or "").strip().lower()
    if not v:
        return None
    if v.startswith("zh") or "chinese" in v or "中文" in v or "汉" in v or "漢" in v:
        return "zh"
    return "en"


def detect_lang():
    """English by default; Chinese when the user's Claude Code or system language is Chinese."""
    forced = os.environ.get("CTXRW_LANG", "").strip().lower()
    if forced in ("zh", "en"):
        return forced
    for name in ("settings.local.json", "settings.json"):
        try:
            with open(os.path.join(CLAUDE_DIR, name)) as f:
                lang = _lang_from_value(json.load(f).get("language"))
            if lang:
                return lang
        except (OSError, ValueError, AttributeError):
            pass
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        v = os.environ.get(var, "")
        if v and v not in ("C", "POSIX", "C.UTF-8"):
            if v.lower().startswith("zh"):
                return "zh"
            break
    if sys.platform == "darwin" and os.environ.get("CTXRW_NO_APPLE_LANG") != "1":
        try:
            out = subprocess.run(["defaults", "read", "-g", "AppleLanguages"], capture_output=True, text=True, timeout=2).stdout
            first = re.findall(r'"?([A-Za-z][\w-]*)"?', out)
            if first and first[0].lower().startswith("zh"):
                return "zh"
        except Exception:
            pass
    return "en"


LANG_CODE = detect_lang()


def L(en, zh):
    return zh if LANG_CODE == "zh" else en


USAGE = L("""/context-rewrite — find/replace the system prompt, system-reminders and conversation before each request is sent

Quick start
  1. /context-rewrite install                set up claude --yrb, then run claude --yrb --continue in a new terminal tab
  2. /context-rewrite auto <description>     say what to change in one sentence and Claude writes the rule; or /context-rewrite capture to see the original text and write it yourself
  3. /context-rewrite list                   show rules; /context-rewrite off to pause; if anything breaks, run /context-rewrite doctor

Setup
  install                      set up claude --yrb (safe to rerun; the rc file only ever gets one block)
  uninstall                    remove everything: --yrb, proxy, rules, and the plugin itself
  doctor                       check every part and fix what can be fixed automatically

Snapshots (taken automatically before rules or rc files change; the last 30 are kept)
  snapshots                    list snapshots
  snapshot [name]              take one manually
  restore [n]                  roll back to a snapshot; without n, list them. Runs without the model, so it works even when requests are failing
                               also works from a terminal: python3 ~/.claude/context-rewrite/ctxrw.py restore 1
  help                         show this help

AI-written rules
  auto <description>           describe the change in one sentence; Claude (sonnet, low) finds the original text, drafts rules, and adds the ones you tick

Find the original text
  capture                      show the system prompt and injected content actually sent in the last request (before rewriting), and save it to a file

Rules
  "find" "replace" [options]   add a rule, effective from the next request ("add" is optional)
      --regex                  match find as a regex; use \\1 in replace for groups
      --ignore-case            case-insensitive
      --scope [system,user,assistant] only replace in these places (default: all three); leave the value empty to pick from a menu
  list                         list rules
  rm [n...]                    delete rules; without n, pick from a menu
  toggle [n...]                enable / disable rules; without n, pick from a menu
  scope [n] [system,user,assistant|all]   change where a rule applies; missing arguments open a menu

Switch
  on | off                     master switch, effective from the next request
  status                       master switch, proxy state, whether this session is --yrb, and the rules

Only sessions started with claude --yrb are rewritten; other sessions are untouched.
Commands with complete arguments print their result directly: nothing enters the conversation and the model is not called.
Commands that open a menu need Claude to show it, which costs one model call.""",
"""/context-rewrite — 发送请求前，对 system prompt、system-reminder 和对话内容做 find/replace

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
弹出选择框的命令需要 Claude 来显示界面，会调用一次模型。""")

PIDFILE = os.path.join(HOME, "proxy.pid")
SNAP_DIR = os.path.join(HOME, "snapshots")
SNAP_KEEP = 30
ACTION = {"name": ""}

COMMANDS = {"snapshot", "snapshots", "restore", "doctor", "on", "off", "status", "list", "add", "add-json", "auto", "rm", "toggle", "scope", "start", "install", "capture", "uninstall", "hook", "ui"}
SCOPES = ("system", "user", "assistant")
SCOPE_DESC = {"system": "system prompt",
              "user": L("user messages, system-reminders, tool results", "用户消息、system-reminder、工具结果"),
              "assistant": L("the model's earlier replies", "模型之前的回复")}
SECTION_LABELS = {"first_user": L("first user message", "第一条 user 消息"),
                  "last_user": L("last user message", "最后一条 user 消息")}


def section_label(key):
    return SECTION_LABELS.get(key, key)


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
        print(L("No snapshots yet (one is taken automatically before rules change or install runs)",
                "还没有快照（改规则或 install 之前会自动存）"))
        return
    print(L("Snapshots (newest first):", "快照（最新在前）："))
    for i, m in enumerate(snaps, 1):
        what = []
        if "rules.json" in m["files"]:
            what.append(L(f"{m['rules']} rules", f"规则 {m['rules']} 条"))
        what += [os.path.basename(p) for k, p in m["files"].items() if k.startswith("rc-")]
        print(f"  {i:>2}. {m['time']}  {m['action'][:30]}  —  " + " + ".join(what))
    print(L("\nRestore: /context-rewrite restore <n> (the current state is snapshotted first, so a restore can be undone)",
            "\n恢复: /context-rewrite restore <序号>（恢复前会先把当前状态也存一份，恢复本身可以撤销）"))


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
        sys.exit(L("No such snapshot; run /context-rewrite restore to list them",
                   "没有这个快照，/context-rewrite restore 看列表"))
    rcs = [p for k, p in m["files"].items() if k.startswith("rc-")]
    take_snapshot(L("before restore", "restore 之前"), rcs)
    for name, dst in m["files"].items():
        shutil.copy2(os.path.join(SNAP_DIR, m["id"], name), dst)
        print(L(f"✓ restored {dst}", f"✓ 已恢复 {dst}"))
    print(L(f"\nBack to the state of {m['time']} ({m['action']}). Undo this restore: /context-rewrite restore 1",
            f"\n已回到 {m['time']} 的状态（{m['action']}）。撤销这次恢复: /context-rewrite restore 1"))
    if "rules.json" in m["files"]:
        print(L("Rules from the snapshot apply from the next request.", "规则从下一次请求开始按快照生效。"))
        show(load())
    if rcs:
        print(L("rc files restored; new terminals pick them up.", "rc 文件已恢复，新开的终端生效。"))


def save(cfg):
    os.makedirs(HOME, exist_ok=True)
    new = json.dumps(cfg, ensure_ascii=False, indent=2)
    if os.path.exists(RULES) and open(RULES).read() != new:
        take_snapshot(L(f"before {ACTION['name']}", f"{ACTION['name']} 之前"))
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


def stale_files():
    return [n for n in FILES if not os.path.exists(os.path.join(HOME, n)) or
            (os.path.join(SRC, n) != os.path.join(HOME, n) and open(os.path.join(SRC, n), "rb").read() != open(os.path.join(HOME, n), "rb").read())]


def remove_skill():
    """Old versions generated ~/.claude/skills/yrb, which showed up as a second command; the plugin's own command is enough now."""
    md = os.path.join(USER_SKILL, "SKILL.md")
    if os.path.exists(md) and SKILL_MARK in open(md).read():
        shutil.rmtree(USER_SKILL, ignore_errors=True)
        print(L(f"✓ removed {USER_SKILL} left by an old version", f"✓ 已删除旧版生成的 {USER_SKILL}"))
        return True
    return False


def install():
    sync_files()
    pending = [rc for rc in target_rcs() if not (os.path.exists(rc) and RC_BLOCK in open(rc).read())]
    if pending:
        take_snapshot(L("before install", "install 之前"), pending)
    changed = remove_skill()
    done, failed = migrate_legacy()
    for d in done:
        print(L(f"✓ uninstalled {d} (old /context-rewrite:yrb command; it would intercept commands twice)",
                f"✓ 已卸载{d}（旧版命令 /context-rewrite:yrb，会和新版重复拦截）"))
        changed = True
    for f in failed:
        print(f"✗ {f}")
    if bundle_installed():
        print(L(f"⚠ the old bundle plugin {BUNDLE} is still installed and also intercepts /context-rewrite. Run: claude plugin uninstall {BUNDLE}",
                f"⚠ 旧的合集插件 {BUNDLE} 还装着，会重复拦截 /context-rewrite。执行: claude plugin uninstall {BUNDLE}"))
    for rc in target_rcs():
        text = open(rc).read() if os.path.exists(rc) else ""
        if RC_BLOCK in text:
            print(L(f"· {rc} already set up, skipped", f"· {rc} 已装好，跳过"))
            continue
        if MARK_BEGIN in text:
            strip_rc(rc)
            text = open(rc).read()
        with open(rc, "a") as f:
            f.write(("\n" if text and not text.endswith("\n") else "") + "\n" + RC_BLOCK)
        print(L(f"✓ wrote {rc}", f"✓ 已写入 {rc}"))
        changed = True
    print(L(f"✓ scripts synced to {HOME}", f"✓ 脚本已同步到 {HOME}"))
    if not changed:
        print(L("(already installed, nothing changed)", "（已经是安装好的状态，没有改动）"))
    print()
    if yrb_session():
        print(L("This session was already started with --yrb, so rules apply now; no restart needed.",
                "当前会话已经是 --yrb 启动的，规则现在就生效，不用重启。"))
        return
    print(L("Last step: restart this conversation with --yrb (pick one)", "最后一步：用 --yrb 重启这段对话（二选一）"))
    print(L("  · Recommended: close this terminal tab or open a new one, then run", "  · 推荐：关掉或新开一个终端 tab，执行"))
    print("      claude --yrb --continue")
    print(L("  · Stay in this tab: exit claude, then run", "  · 留在当前 tab：退出 claude 后执行"))
    print("      source ~/.zshrc && claude --yrb --continue")
    print()
    print(L("Note: source must run in your own terminal, outside claude; running it with ! inside the conversation has no effect.",
            "注意：source 必须在 claude 外面、你自己的终端里执行；在对话里用 ! 执行没有用。"))
    print(L("From then on, just run claude --yrb in any new terminal.", "之后新开的终端里直接 claude --yrb 就行。"))


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
    sys.exit(L(f"context-rewrite: proxy failed to start, see {HOME}/proxy.err",
               f"context-rewrite: proxy 启动失败，看 {HOME}/proxy.err"))


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


LEGACY_PLUGINS = {"context-rewrite@context-rewrite"}
LEGACY_MARKETPLACES = {"context-rewrite"}
BUNDLE = "cyberchick-skills@cyberchick-skills"


def installed_plugin_entries(match):
    try:
        with open(os.path.join(PLUGINS_DIR, "installed_plugins.json")) as f:
            plugins = json.load(f).get("plugins", {})
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    return [(key, e) for key, entries in plugins.items() if match(key) for e in entries]


def has_marketplace(name):
    try:
        with open(os.path.join(PLUGINS_DIR, "known_marketplaces.json")) as f:
            return name in json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return False


def remove_plugins(match, label, marketplaces=()):
    """Uninstall plugins matched by full key (plus old marketplaces). Returns (done, failed)."""
    done, failed = [], []
    claude = shutil.which("claude") or "claude"
    cmds = [([claude, "plugin", "uninstall", key, "--scope", e.get("scope", "user"), "-y"], e.get("projectPath"), f"{label} {key}")
            for key, e in installed_plugin_entries(match)]
    cmds += [([claude, "plugin", "marketplace", "remove", m], None, L(f"old marketplace {m}", f"旧 marketplace {m}"))
             for m in marketplaces if has_marketplace(m)]
    for cmd, cwd, label in cmds:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd or None, timeout=60)
            if r.returncode:
                raise RuntimeError((r.stderr or r.stdout).strip())
            done.append(label)
        except Exception as ex:
            failed.append(L(f"{label}: {ex}; run manually: {' '.join(cmd)}", f"{label}: {ex}；手动执行 {' '.join(cmd)}"))
    return done, failed


def migrate_legacy():
    """The old context-rewrite@context-rewrite plugin (/context-rewrite:yrb) has hooks that would intercept commands alongside this one."""
    return remove_plugins(lambda k: k in LEGACY_PLUGINS, L("old plugin", "旧插件"), LEGACY_MARKETPLACES)


def bundle_installed():
    """Versions 0.5–0.6 shipped every tool in one cyberchick-skills plugin, which also carries context-rewrite's hooks."""
    return bool(installed_plugin_entries(lambda k: k == BUNDLE))


def uninstall():
    ok = True
    was_yrb = yrb_session()
    for rc in RCS:
        if strip_rc(rc):
            print(L(f"✓ removed --yrb from {rc}", f"✓ 已从 {rc} 移除 --yrb"))
    remove_skill()

    stopped = stop_proxy()
    if stopped:
        print(L(f"✓ proxy stopped (127.0.0.1:{PORT} released)", f"✓ proxy 已停止（127.0.0.1:{PORT} 已释放）"))
    elif stopped is False:
        ok = False
        print(L(f"✗ could not stop the proxy; find it with lsof -nP -iTCP:{PORT} -sTCP:LISTEN and kill it",
                f"✗ proxy 没能停掉，手动执行: lsof -nP -iTCP:{PORT} -sTCP:LISTEN 找到进程后 kill"))

    legacy_plist = os.path.expanduser("~/Library/LaunchAgents/com.context-rewrite.proxy.plist")
    if os.path.exists(legacy_plist):
        subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/com.context-rewrite.proxy"], capture_output=True)
        os.remove(legacy_plist)
        print(L("✓ removed the old launchd agent", "✓ 已移除旧版 launchd 常驻"))

    done, failed = remove_plugins(lambda k: k.split("@")[0] == "context-rewrite", L("plugin", "插件"), LEGACY_MARKETPLACES)
    for d in done:
        print(L(f"✓ uninstalled {d}", f"✓ 已卸载{d}"))
    for f in failed:
        ok = False
        print(f"✗ {f}")

    if os.path.exists(HOME):
        shutil.rmtree(HOME, ignore_errors=True)
        print(L(f"✓ deleted {HOME} (rules, logs, scripts)", f"✓ 已删除 {HOME}（规则、日志、脚本）"))

    left = [HOME] if os.path.exists(HOME) else []
    left += [rc for rc in RCS if os.path.exists(rc) and MARK_BEGIN in open(rc).read()]
    if left or not ok:
        print(L("⚠ not fully removed: ", "⚠ 未完全清除: ") + "; ".join(left or [L("see failures above", "见上方失败项")]))
    else:
        print(L("✓ fully uninstalled", "✓ 已 100% 卸载"))
    print()
    if was_yrb:
        print(L("This session was started with --yrb and the proxy is now stopped, so the next message will fail. Exit and reopen normally: claude --continue",
                "当前这个会话是 --yrb 启动的，proxy 已停，接下来发消息会连不上。退出后用普通方式重开即可：claude --continue"))
        print(L("Other --yrb sessions need a restart too; normal sessions are unaffected.",
                "其他 --yrb 会话同理需要重开；普通会话不受任何影响。"))
    print(L("Terminals that are already open still have the claude function in memory, but it falls back to a normal launch; new terminals won't have it.",
            "已经开着的终端里 claude 函数还在内存中，但会自动退回普通启动；新开的终端里就彻底没有了。"))
    print(L("The cyberchick-skills marketplace stays (it has other tools); to reinstall: /plugin install context-rewrite@cyberchick-skills",
            "cyberchick-skills marketplace 保留（里面还有别的工具）；要重新装：/plugin install context-rewrite@cyberchick-skills"))


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


def snapshot_text(res, bar="─" * 60, english=False):
    snap = res["snapshot"]
    n = len(snap['system'])
    blocks = f"{n} block" + ("" if n == 1 else "s")
    out = [f"══ SYSTEM PROMPT ({blocks}) ══" if english else
           L(f"══ SYSTEM PROMPT ({blocks}) ══", f"══ SYSTEM PROMPT ({n} 块) ══")]
    for t in snap["system"]:
        out += [t, bar]
    for label, ts in snap["messages"]:
        if english:
            out.append(f"══ {label.replace('_', ' ')} message (includes injected system-reminders) ══")
        else:
            out.append(L(f"══ {section_label(label)} (includes injected system-reminders) ══",
                         f"══ {section_label(label)}（含注入的 system-reminder）══"))
        for t in ts:
            out += [t, bar]
    return "\n".join(out)


def capture():
    if os.environ.get("CLAUDECODE") and not yrb_session():
        sys.exit(L("capture only works in a session started with claude --yrb (normal sessions don't go through the proxy)",
                   "capture 只能在用 claude --yrb 启动的会话里用（普通会话不经过 proxy）"))
    if not running():
        sys.exit(L("the proxy is not running", "proxy 没在运行"))
    res = fetch_snapshot()
    if not res:
        sys.exit(L("This session hasn't sent a request yet; send any message first, then run capture",
                   "这个会话还没有发过请求，先随便发一句话，再执行 capture"))
    snap = res["snapshot"]
    out = [L(f"Original text of the last request ({snap['time']}, model={snap['model']}), before rewriting:",
             f"上一次请求（{snap['time']}，model={snap['model']}）的原文，替换之前："), ""]
    if not res["matched"]:
        out[1:1] = [L("⚠ No record for this session; showing the most recent --yrb session's request instead",
                      "⚠ 没找到当前会话的记录，下面显示的是最近一个 --yrb 会话的请求")]
    out.append(snapshot_text(res))
    text = "\n".join(out)
    path = os.path.join(HOME, "captured.txt")
    with open(path, "w") as f:
        f.write(text)
    print(text)
    print(L(f"\nSaved to {path}. Once you find the text to change: /context-rewrite \"find\" \"replace\"",
            f"\n已存到 {path}。找到要改的原文后：/context-rewrite \"原文\" \"替换\""))


def parse_args(raw):
    """`auto` takes free text (quotes, apostrophes, <>, newlines) verbatim; everything else is shell-like."""
    import shlex
    m = re.match(r"\s*auto(?:\s+(.*))?$", raw, re.S)
    if m:
        return ["auto"] + ([m.group(1).strip()] if m.group(1) and m.group(1).strip() else [])
    return shlex.split(raw)


def pending_path(sid):
    return os.path.join(HOME, "pending", re.sub(r"[^\w-]", "_", sid or "nosession") + ".json")


def hook():
    """UserPromptSubmit / UserPromptExpansion: intercept /context-rewrite, run it, and show the result to the user only (no context, no model call)."""
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
        m = re.match(r"^/(?:context-rewrite:)?context-rewrite(?:\s+(.*))?$", prompt, re.S)
        if not m:
            return
        raw = m.group(1) or ""
    elif event == "UserPromptExpansion":
        if inp.get("command_name") not in ("context-rewrite", "context-rewrite:context-rewrite"):
            return
        raw = inp.get("command_args") or ""
    else:
        return
    os.environ["CTXRW_SESSION_ID"] = inp.get("session_id", "")
    buf = io.StringIO()
    try:
        argv = parse_args(raw)
        if needs_ui(argv):
            # The skill body runs `ui` through a shell; hand the arguments over via a file so
            # quotes in them can never break that command line.
            os.makedirs(os.path.dirname(pending_path(inp.get("session_id"))), exist_ok=True)
            with open(pending_path(inp.get("session_id")), "w") as f:
                json.dump({"argv": argv, "time": time.time()}, f, ensure_ascii=False)
            return
        with contextlib.redirect_stdout(buf):
            try:
                main(argv)
            except SystemExit as e:
                if e.code not in (None, 0):
                    print(e.code if isinstance(e.code, str) else L(f"exit code {e.code}", f"退出码 {e.code}"))
    except ValueError as e:
        buf.write(L(f"could not parse arguments: {e}", f"参数解析失败: {e}"))
    print(json.dumps({"decision": "block", "reason": buf.getvalue().rstrip() or L("(no output)", "（无输出）")}, ensure_ascii=False))


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
    """Commands with missing arguments open a menu, which the model shows via AskUserQuestion."""
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
    state = L("on", "启用") if r.get("enabled", True) else L("off", "停用")
    scope = ",".join(r["scope"]) if r.get("scope") else L("all", "全部")
    extra = L(", regex", " 正则") if r.get("regex") else ""
    return L(f"{r['find']!r} → {r.get('replace', '')!r} ({state}, scope: {scope}{extra})",
             f"{r['find']!r} → {r.get('replace', '')!r}（{state}，范围: {scope}{extra}）")


def ui_language_line():
    return f"Write all question text, headers, option labels and descriptions shown to the user in {'Simplified Chinese' if LANG_CODE == 'zh' else 'English'}."


def ui(argv):
    import shlex
    if argv[:1] == ["--session"]:
        if len(argv) > 1 and not argv[1].startswith("$"):
            os.environ["CTXRW_SESSION_ID"] = argv[1]
        argv = argv[2:]
    if argv[:1] == ["--pending"]:
        p = pending_path(os.environ.get("CTXRW_SESSION_ID"))
        try:
            with open(p) as f:
                d = json.load(f)
            os.remove(p)
            if time.time() - d.get("time", 0) > 600:
                raise ValueError("stale")
            argv = d["argv"]
        except (OSError, ValueError, KeyError):
            print(L("No pending arguments found (the context-rewrite hook didn't run). Retry the command; if it keeps failing, run /context-rewrite doctor.",
                    "没找到这次的参数（context-rewrite 的 hook 没运行）。再执行一次；一直不行就跑 /context-rewrite doctor。"))
            return
    argv = normalize(argv)
    sid = os.environ.get("CTXRW_SESSION_ID")
    if not needs_ui(argv):
        main(argv)
        return
    me = f"python3 {os.path.abspath(__file__)}" + (f" --session {sid}" if sid else "")
    cmd, args = argv[0], argv[1:]
    rules = load()["rules"]
    shown = rules[:16]
    cancelled = L("Cancelled.", "已取消")
    head = ["[context-rewrite interactive] Use AskUserQuestion to show the menu below. After the user answers, run the matching command with Bash, then relay the command output to the user verbatim.",
            f"Do nothing else: no explanations, no summaries. If the user cancels or selects nothing, reply only \"{cancelled}\".",
            ui_language_line(), ""]

    def rule_options(title):
        out = [f"Question \"{title}\"; set multiSelect as noted below. Each question allows at most 4 options: with more than 4 rules, split them across several questions (4 rules each, at most 4 questions), with headers like \"Rules 1-4\", \"Rules 5-8\"."]
        out += [f"  label: \"#{i}\"  description: \"{rule_line(i, r)}\"" for i, r in enumerate(shown, 1)]
        if len(rules) > 16:
            out.append(f"({len(rules) - 16} more rules not listed; tell the user they can type /context-rewrite {cmd} <n> directly)")
        return out

    if cmd == "auto":
        auto_prompt(" ".join(args), me, rules)
        return

    scope_opts = [f"  label: \"{s}\"  description: \"{SCOPE_DESC[s]}\"" for s in SCOPES]
    if cmd in ("rm", "toggle"):
        verb = "delete" if cmd == "rm" else "enable / disable (selected rules flip state)"
        lines = head + rule_options(f"Which rules do you want to {verb}?") + ["multiSelect: true", "",
                 f"Run: {me} {cmd} <selected numbers, space-separated, without #>"]
    elif cmd == "scope":
        if args:
            lines = head + [f"Question \"Where should rule #{args[0]} apply?\" header \"Scope\" multiSelect: true"] + scope_opts + ["",
                     f"Run: {me} scope {args[0]} <selected items, comma-separated; write all if all three are selected>"]
        else:
            lines = head + ["Ask two questions in a single AskUserQuestion call:", "Question 1:"] + rule_options("Which rule's scope do you want to change?") + [
                "  (this question: multiSelect: false)",
                "Question 2: \"Where should it apply?\" header \"Scope\" multiSelect: true"] + scope_opts + ["",
                f"Run: {me} scope <selected rule number, without #> <selected scopes, comma-separated; write all if all three are selected>"]
    else:
        i = args.index("--scope")
        template = [a for a in args[:i + 1]] + ["__SCOPES__"] + args[i + 1:]
        lines = head + ["Question \"Where should this rule apply?\" header \"Scope\" multiSelect: true"] + scope_opts + ["",
                 f"Run (replace __SCOPES__ with the selected items, comma-separated; write all if all three are selected): {me} add {shlex.join(template)}"]
    print("\n".join(lines))


def auto_prompt(desc, me, rules):
    res = fetch_snapshot()
    cancelled = L("Cancelled.", "已取消")
    lines = [
        "[context-rewrite interactive · auto rule writing]",
        f"User request: {desc}",
        "",
        "Task: based on the user's request, find the passages to change in the \"original text of the last request\" below and write replacement rules. Do nothing beyond the steps below; no explanations.",
        "1. find must be copied verbatim from the original text (punctuation, spaces and line breaks must match); never write it from memory. Keep it short but unique.",
        "2. To delete, set replace to the empty string \"\"; to reword, write the new text.",
        "3. scope: if the text is in the SYSTEM PROMPT section use [\"system\"]; if it is in a user message or system-reminder use [\"user\"]; if it appears in both, omit scope.",
        "4. Only use \"regex\": true when the original text appears in several variants.",
        "5. Use AskUserQuestion to let the user tick which rules to add: multiSelect: true, one option per rule, labels \"Rule 1\", \"Rule 2\", …, "
        "description \"find summary → replace summary\" (at most 40 characters each). At most 4 options per question; split into more questions if needed. If you can't find relevant text, say so; never invent it.",
        ui_language_line(),
        "6. Write the ticked rules as a JSON array (fields find / replace / scope / regex) and run with Bash:",
        f"   {me} add-json <<'CTXRW_EOF'",
        "   [{\"find\": \"...\", \"replace\": \"...\", \"scope\": [\"system\"]}]",
        "   CTXRW_EOF",
        f"7. Relay the command output to the user verbatim. If the user selects nothing, reply only \"{cancelled}\".",
        "",
        "Existing rules (rules already in effect make the text below appear rewritten):",
    ]
    lines += [f"  #{i} {rule_line(i, r)}" for i, r in enumerate(rules, 1)] or ["  (none)"]
    lines.append("")
    if res:
        lines += ["══════════ original text of the last request (before rewriting) ══════════", snapshot_text(res, english=True)]
    else:
        lines += ["(No original text available: this session wasn't started with --yrb, or hasn't sent a message yet. Use the system prompt and "
                  "system-reminder text you can see in your own context; the result can't be verified when it is saved.)"]
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
            sys.exit(L(f"invalid rule: {r!r}", f"规则格式不对: {r!r}"))
        rule = {"find": r["find"], "replace": str(r.get("replace", "")), "enabled": True}
        if r.get("regex"):
            try:
                re.compile(r["find"])
            except re.error as e:
                sys.exit(L(f"invalid regex {r['find']!r}: {e}", f"正则无效 {r['find']!r}: {e}"))
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
            print(L(f"✓ added #{n} (couldn't verify: no record of the last request)",
                    f"✓ 已添加 #{n}（无法核对原文：没有上一次请求的记录）"))
            continue
        pat = re.compile(rule["find"] if rule.get("regex") else re.escape(rule["find"]), re.I if rule.get("ignore_case") else 0)
        where = {k: len(pat.findall(v)) for k, v in corpus.items() if k in (rule.get("scope") or ("system", "user"))}
        hits = sum(where.values())
        if hits:
            detail = ", ".join(f"{k} {v}" for k, v in where.items() if v)
            print(L(f"✓ added #{n}, {hits} match(es) in the last request ({detail})",
                    f"✓ 已添加 #{n}，在上一次请求里命中 {hits} 处（" + "，".join(f"{k} {v}" for k, v in where.items() if v) + "）"))
        else:
            print(L(f"⚠ added #{n}, but the text wasn't found in the last request, so it may never apply; remove it with /context-rewrite rm {n}",
                    f"⚠ 已添加 #{n}，但在上一次请求里没找到这段原文，可能不会生效；可以 /context-rewrite rm {n} 删掉"))
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

    print(L("context-rewrite diagnostics\n", "context-rewrite 诊断\n"))

    print(L("[setup]", "[安装]"))
    stale = stale_files()
    if stale:
        sync_files()
        fix(L(f"scripts missing or outdated, synced: {', '.join(stale)}", f"脚本缺失或过期，已同步: {', '.join(stale)}"))
    else:
        ok(L(f"scripts present: {HOME}", f"脚本齐全: {HOME}"))
    for rc in target_rcs():
        text = open(rc).read() if os.path.exists(rc) else ""
        n = text.count(MARK_BEGIN)
        if n == 1 and RC_BLOCK in text:
            ok(L(f"--yrb is set up in {rc}", f"{rc} 里有 --yrb"))
            continue
        take_snapshot(L("before doctor fixed rc", "doctor 修 rc 之前"), [rc])
        strip_rc(rc)
        text = open(rc).read() if os.path.exists(rc) else ""
        with open(rc, "a") as f:
            f.write(("\n" if text and not text.endswith("\n") else "") + "\n" + RC_BLOCK)
        fix(L(f"--yrb in {rc} was " + ("missing" if n == 0 else "duplicated or outdated") + ", rewritten (new terminals pick it up)",
              f"{rc} 里的 --yrb " + ("缺失" if n == 0 else "重复或过期") + "，已重写（新开的终端生效）"))
    if remove_skill():
        fix(L("removed ~/.claude/skills/yrb left by an old version", "删除了旧版生成的 ~/.claude/skills/yrb"))
    done, failed = migrate_legacy()
    if done:
        fix(L("uninstalled old versions: " + ", ".join(done) + " (they would intercept commands twice)",
              "卸载了旧版: " + "、".join(done) + "（它会和新版重复拦截命令）"))
    for f in failed:
        fail(L("old plugin could not be uninstalled", "旧版插件没卸掉"), f)
    clash = os.path.join(os.path.dirname(USER_SKILL), "context-rewrite", "SKILL.md")
    if os.path.exists(clash):
        fail(L(f"{os.path.dirname(clash)} is another skill with the same name; /context-rewrite runs it instead of this plugin",
               f"{os.path.dirname(clash)} 是另一个同名 skill，敲 /context-rewrite 会运行它而不是本插件"),
             L("use the full name /context-rewrite:context-rewrite, or rename that skill",
               "改用全名 /context-rewrite:context-rewrite，或者把那个 skill 改名"))
    else:
        ok(L("/context-rewrite is provided by the context-rewrite plugin", "/context-rewrite 命令由 context-rewrite 插件提供"))
    if bundle_installed():
        fail(L(f"the old bundle plugin {BUNDLE} is still installed and also intercepts /context-rewrite (runs twice)",
               f"旧的合集插件 {BUNDLE} 还装着，它也会拦截 /context-rewrite（重复执行）"),
             L(f"claude plugin uninstall {BUNDLE}, then install the plugins you need: /plugin install <name>@cyberchick-skills",
               f"claude plugin uninstall {BUNDLE}，再按需装单个插件：/plugin install <名字>@cyberchick-skills"))

    print(L("\n[rules]", "\n[规则]"))
    try:
        with open(RULES) as f:
            cfg = json.load(f)
        n_rules = len(cfg.get("rules", []))
        switch = "ON" if cfg.get("enabled", True) else "OFF"
        ok(L(f"rules.json readable, {n_rules} rules, master switch {switch}", f"rules.json 可读，{n_rules} 条规则，总开关 {switch}"))
    except FileNotFoundError:
        cfg = {"enabled": True, "rules": []}
        ok(L("no rules yet", "还没有规则"))
    except json.JSONDecodeError as e:
        backup = RULES + f".broken-{int(time.time())}"
        os.replace(RULES, backup)
        cfg = {"enabled": True, "rules": []}
        save(cfg)
        fix(L(f"rules.json was corrupted ({e}); backed up to {backup} and reset to empty",
              f"rules.json 损坏（{e}），已备份到 {backup} 并重置为空"))
    changed = False
    for i, r in enumerate(cfg.get("rules", []), 1):
        problem = None
        if not isinstance(r, dict) or not r.get("find"):
            problem = L("empty find text", "原文为空")
        elif r.get("regex"):
            try:
                re.compile(r["find"])
            except re.error as e:
                problem = L(f"invalid regex: {e}", f"正则无效: {e}")
        if isinstance(r, dict) and r.get("scope") and any(x not in SCOPES for x in r["scope"]):
            problem = L(f"invalid scope: {r['scope']}", f"范围无效: {r['scope']}")
        if problem and r.get("enabled", True):
            r["enabled"] = False
            changed = True
            fix(L(f"rule #{i}: {problem}, disabled", f"规则 #{i} {problem}，已停用"))
    if changed:
        save(cfg)

    print(L("\n[this session]", "\n[当前会话]"))
    if os.environ.get("CLAUDECODE"):
        if yrb_session():
            ok(L("this session was started with --yrb and is rewritten", "当前会话是 --yrb 启动的，会经过替换"))
        else:
            fail(L("this session wasn't started with --yrb, so rules don't apply to it", "当前会话不是 --yrb 启动的，规则对它不生效"),
                 L("open a new terminal tab and run claude --yrb --continue (in this tab, source ~/.zshrc first)",
                   "新开终端 tab 执行 claude --yrb --continue（当前 tab 要先 source ~/.zshrc）"))

    print("\n[proxy]")
    if running():
        r = subprocess.run(["lsof", "-nP", "-t", f"-iTCP:{PORT}", "-sTCP:LISTEN"], capture_output=True, text=True)
        cmds = [subprocess.run(["ps", "-o", "command=", "-p", p], capture_output=True, text=True).stdout.strip() for p in r.stdout.split()]
        if cmds and not any("proxy.py" in c for c in cmds):
            fail(L(f"port {PORT} is used by another program: {cmds[0][:80]}", f"端口 {PORT} 被别的程序占用: {cmds[0][:80]}"),
                 L("close that program, or start claude --yrb with CTXRW_PORT=<another port>",
                   "关掉那个程序，或用 CTXRW_PORT=其他端口 启动 claude --yrb"))
        else:
            ok(L(f"proxy running (127.0.0.1:{PORT})", f"proxy 在运行（127.0.0.1:{PORT}）"))
    elif yrb_session():
        try:
            start()
            fix(L("proxy wasn't running (this --yrb session couldn't connect); restarted it",
                  "proxy 没在运行（当前 --yrb 会话会连不上），已重新启动"))
        except SystemExit as e:
            fail(L("proxy failed to start", "proxy 启动失败"), str(e))
    else:
        ok(L("proxy not running (normal when there are no --yrb sessions)", "proxy 没在运行（没有 --yrb 会话时这是正常的）"))
    log = os.path.join(HOME, "proxy.log")
    if os.path.exists(log):
        # the Chinese keys match proxy.log lines written by versions before 0.8
        keys = ("upstream HTTP", "failed", "rejected by API", "fell back",
                "上游返回", "失败", "拒绝", "回退")
        errs = [l.rstrip() for l in open(log).readlines()[-200:] if any(k in l for k in keys)]
        if errs:
            print(L("  recent errors (proxy.log):", "  最近的错误（proxy.log）："))
            for l in errs[-5:]:
                print(f"    {l}")
            if any(re.search(r"replaced [1-9]|替换 [1-9]", l) for l in errs[-5:]):
                print(L("    → requests that failed had replacements, so a rule may have broken them: try /context-rewrite off, then /context-rewrite toggle rules one by one;",
                        "    → 出错的请求里有替换，可能是某条规则把请求改坏了：先 /context-rewrite off 试试，再逐条 /context-rewrite toggle 排查；"))
                print(L("      or /context-rewrite restore to roll back to the rules from before the problem",
                        "      或者 /context-rewrite restore 看快照，回到出问题之前的规则"))

    print(L("\n[leftovers from old versions]", "\n[旧版残留]"))
    legacy = []
    plist = os.path.expanduser("~/Library/LaunchAgents/com.context-rewrite.proxy.plist")
    if os.path.exists(plist):
        subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/com.context-rewrite.proxy"], capture_output=True)
        os.remove(plist)
        legacy.append(L("launchd agent", "launchd 常驻"))
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
            legacy.append(L("global ANTHROPIC_BASE_URL in settings.json", "settings.json 里的全局 ANTHROPIC_BASE_URL"))
    except (OSError, json.JSONDecodeError):
        pass
    if legacy:
        fix(L("cleaned up: " + ", ".join(legacy), "已清理: " + "、".join(legacy)))
    else:
        ok(L("no leftovers from old versions", "没有旧版残留"))

    snaps = list_snapshots()
    print(L("\n[snapshots]", "\n[快照]"))
    if snaps:
        ok(L(f"{len(snaps)} snapshots, newest {snaps[0]['time']} ({snaps[0]['action']}). Roll back: /context-rewrite restore",
             f"{len(snaps)} 份快照，最新 {snaps[0]['time']}（{snaps[0]['action']}）。回滚: /context-rewrite restore"))
    else:
        ok(L("no snapshots yet (one is taken automatically before rules change or install runs)",
             "还没有快照（改规则或 install 之前会自动存）"))

    print(L(f"\nResult: {ok_n} OK, {len(fixed)} fixed, {len(bad)} need your attention",
            f"\n结果: {ok_n} 项正常，{len(fixed)} 项已修复，{len(bad)} 项需要你处理"))


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
        sys.exit(L(f"scope must be {','.join(SCOPES)} or all, got: {v}", f"范围只能是 {','.join(SCOPES)} 或 all，收到: {v}"))
    return None if set(ss) == set(SCOPES) else [s for s in SCOPES if s in ss]


def show(cfg):
    if not cfg["rules"]:
        print(L("  (no rules)", "  （无规则）"))
    for i, r in enumerate(cfg["rules"], 1):
        flags = [f for f, on in (("regex", r.get("regex")), ("ignore_case", r.get("ignore_case"))) if on]
        if r.get("scope"):
            flags.append("scope=" + ",".join(r["scope"]))
        mark = "✓" if r.get("enabled", True) else "✗"
        print(f"  {i}. [{mark}] {r['find']!r} → {r.get('replace', '')!r}" + (f"  ({' '.join(flags)})" if flags else ""))


def warn(cfg):
    if not cfg.get("enabled"):
        print(L("⚠ the master switch is OFF, so rules don't apply (/context-rewrite on)", "⚠ 总开关是 OFF，规则不会生效（/context-rewrite on）"))
    if os.environ.get("CLAUDECODE") and not yrb_session():
        print(L("⚠ this session wasn't started with claude --yrb, so rules don't apply to it; only --yrb sessions are rewritten",
                "⚠ 当前会话不是用 claude --yrb 启动的，规则对它不生效；用 --yrb 启动的会话才会替换"))


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
        sid = take_snapshot(L("manual: ", "手动: ") + (" ".join(args) or L("unnamed", "未命名")), target_rcs())
        print(L(f"✓ snapshot saved: {sid}", f"✓ 已存快照 {sid}") if sid else L("nothing to snapshot", "没有可存的内容"))
        return
    if cmd == "ui":
        ui(args)
        return

    if installed():
        sync_files()
    else:
        print(L("⚠ --yrb isn't set up yet; run /context-rewrite install first\n", "⚠ 还没安装 --yrb，先执行 /context-rewrite install\n"))
    cfg = load()
    if cmd in ("on", "off"):
        cfg["enabled"] = cmd == "on"
        save(cfg)
        print(L(f"Context rewriting {'enabled' if cfg['enabled'] else 'disabled'}, effective from the next request",
                f"上下文替换已{'开启' if cfg['enabled'] else '关闭'}，下一次请求生效"))
        warn(cfg)
    elif cmd == "status":
        print(L("Master switch: ", "总开关: ") + ("ON" if cfg.get("enabled") else "OFF"))
        print(f"proxy: " + (L("running", "运行中") if running() else L("not running", "未运行")) + f" (127.0.0.1:{PORT})")
        if os.environ.get("CLAUDECODE"):
            print(L("This session: ", "当前会话: ") + (L("--yrb, rewritten", "--yrb，经过替换") if yrb_session()
                                                     else L("normal session, not rewritten", "普通会话，不经过替换")))
        print(L("Rules:", "规则:"))
        show(cfg)
    elif cmd == "list":
        show(cfg)
    elif cmd == "capture":
        capture()
    elif cmd == "add-json":
        try:
            new = json.loads(" ".join(args) if args else sys.stdin.read())
        except json.JSONDecodeError as e:
            sys.exit(L(f"could not parse JSON: {e}", f"JSON 解析失败: {e}"))
        add_rules(new if isinstance(new, list) else [new], cfg)
        print()
        show(cfg)
        warn(cfg)
    elif cmd == "auto":
        sys.exit(L("Usage: /context-rewrite auto <describe the change in one sentence>, e.g. /context-rewrite auto remove every instruction to add Co-Authored-By",
                   "用法: /context-rewrite auto <用一句话描述想改什么>，例如 /context-rewrite auto 去掉所有要求加 Co-Authored-By 的说明"))
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
                sys.exit(L("--scope needs a value (system,user,assistant or all); inside a conversation, leaving it empty opens a menu",
                           "--scope 后面要写范围（system,user,assistant 或 all）；在对话里不写会弹出选择框"))
            else:
                pos.append(a)
            i += 1
        if len(pos) != 2:
            sys.exit(L("Two arguments needed: <find> <replace> (quote text with spaces; use \"\" for an empty replacement)",
                       "需要两个参数: <find> <replace>（含空格请加引号，replace 为空用 \"\"）"))
        if opts.get("regex"):
            try:
                re.compile(pos[0])
            except re.error as e:
                sys.exit(L(f"invalid regex: {e}", f"正则无效: {e}"))
        cfg["rules"].append({"find": pos[0], "replace": pos[1], "enabled": True, **opts})
        save(cfg)
        print(L(f"Added rule #{len(cfg['rules'])}, effective from the next request", f"已添加规则 #{len(cfg['rules'])}，下一次请求生效"))
        show(cfg)
        warn(cfg)
    elif cmd in ("rm", "toggle", "scope"):
        if not cfg["rules"]:
            print(L("No rules yet. Add one: /context-rewrite \"find\" \"replace\"", "还没有规则。加规则：/context-rewrite \"原文\" \"替换\""))
            return
        if not args or (cmd == "scope" and len(args) < 2):
            usage = L("<n> <system,user,assistant|all>", "<序号> <system,user,assistant|all>") if cmd == "scope" else L("<n...>", "<序号...>")
            sys.exit(L(f"Usage: /context-rewrite {cmd} {usage} (inside a conversation, leaving arguments out opens a menu)",
                       f"用法: /context-rewrite {cmd} {usage}（在对话里不写参数会弹出选择框）"))
        try:
            idx = parse_indices(args[:1] if cmd == "scope" else args, len(cfg["rules"]))
        except ValueError:
            sys.exit(L("Invalid number; check /context-rewrite list", "序号无效，先 /context-rewrite list 看看"))
        if cmd == "rm":
            for i in reversed(idx):
                cfg["rules"].pop(i)
            print(L(f"Deleted {len(idx)} rule(s)", f"已删除 {len(idx)} 条规则"))
        elif cmd == "toggle":
            for i in idx:
                cfg["rules"][i]["enabled"] = not cfg["rules"][i].get("enabled", True)
            states = [(i + 1, cfg["rules"][i]["enabled"]) for i in idx]
            print(L("Toggled: " + ", ".join(f"#{n} → {'on' if on else 'off'}" for n, on in states),
                    "已切换: " + "、".join(f"#{n} → {'启用' if on else '停用'}" for n, on in states)))
        else:
            sc = parse_scope(args[1])
            for i in idx:
                if sc:
                    cfg["rules"][i]["scope"] = sc
                else:
                    cfg["rules"][i].pop("scope", None)
            nums = [f"#{i + 1}" for i in idx]
            print(L("Scope changed: " + ", ".join(nums) + " → " + (",".join(sc) if sc else "all"),
                    "已修改范围: " + "、".join(nums) + " → " + (",".join(sc) if sc else "全部")))
        save(cfg)
        show(cfg)
    else:
        sys.exit(L(f"Unknown command: {cmd}\n{USAGE}", f"未知命令: {cmd}\n{USAGE}"))


if __name__ == "__main__":
    main(sys.argv[1:])
