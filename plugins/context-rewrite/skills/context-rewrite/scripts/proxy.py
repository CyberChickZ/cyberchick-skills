#!/usr/bin/env python3
import http.client
import json
import os
import re
import sys
import hashlib
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

HOME = os.path.expanduser(os.environ.get("CTXRW_HOME") or os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude", "context-rewrite"))
RULES = os.path.join(HOME, "rules.json")
LOG = os.path.join(HOME, "proxy.log")
PORT = int(os.environ.get("CTXRW_PORT", "8787"))
UPSTREAM = urlsplit(os.environ.get("CTXRW_UPSTREAM", "https://api.anthropic.com"))
HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te",
       "trailer", "trailers", "transfer-encoding", "upgrade", "host", "content-length"}
SKIP_BLOCKS = {"thinking", "redacted_thinking"}
PLACEHOLDER = "(removed)"
VERSION = hashlib.sha1(open(os.path.abspath(__file__), "rb").read()).hexdigest()[:12]

_cache = {"mtime": None, "cfg": {"enabled": False, "rules": []}, "compiled": []}


def log(msg):
    try:
        with open(LOG, "a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except OSError:
        pass


def texts(c):
    if isinstance(c, str):
        return [c]
    out = []
    for b in c if isinstance(c, list) else []:
        if isinstance(b, dict) and b.get("type") not in SKIP_BLOCKS:
            if isinstance(b.get("text"), str):
                out.append(b["text"])
            if b.get("type") == "tool_result" and "content" in b:
                out += texts(b["content"])
    return out


LAST = {}


AGENTS = {}  # (session, agent_type) -> latest subagent snapshot; ("*", agent_type) -> latest across sessions


def build_snapshot(d, headers):
    msgs = [m for m in d.get("messages", []) if isinstance(m, dict)]
    users = [m for m in msgs if m.get("role") == "user"]
    picks = []
    if users:
        picks.append(("first_user", users[0]))
    if len(users) > 1:
        picks.append(("last_user", users[-1]))
    by_role = {"user": [], "assistant": []}
    for m in msgs:
        by_role.setdefault(m.get("role", "user"), []).extend(texts(m.get("content")))
    tools = [t["description"] for t in d.get("tools", []) or [] if isinstance(t, dict) and isinstance(t.get("description"), str)]
    system = texts(d.get("system", []))
    return {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "model": d.get("model"),
            "agent_type": headers.get("x-claude-code-agent-type") or "main",
            "system": system,
            "messages": [(label, texts(m.get("content"))) for label, m in picks],
            # the whole request as searchable text, per rewrite scope
            "corpus": {"system": "\n".join(system), "user": "\n".join(by_role["user"]),
                       "assistant": "\n".join(by_role["assistant"]), "tools": "\n".join(tools)}}


def snapshot(d, headers):
    """Keep the latest original (pre-rewrite) request of each session's main agent, and of each subagent type,
    in memory for capture and rule checking."""
    cls = headers.get("x-claude-code-request-class")
    if cls == "compaction" or headers.get("x-claude-code-compaction"):
        return
    sid = headers.get("x-claude-code-session-id") or "-"
    snap = build_snapshot(d, headers)
    if headers.get("x-claude-code-agent-id") or cls in ("subagent", "workflow"):
        kind = headers.get("x-claude-code-agent-type") or cls or "subagent"
        AGENTS[(sid, kind)] = snap
        AGENTS[("*", kind)] = dict(snap, session=sid)
        return
    LAST[sid] = snap
    LAST["__latest__"] = sid


def agent_snapshot(sid, kind):
    """Latest snapshot of a subagent type: this session first, then any session (subagent prompts are fixed)."""
    kinds = {k for _, k in AGENTS}
    match = next((k for k in kinds if k.lower() == kind.lower()), None)
    if not match:
        return None, sorted(kinds)
    snap = AGENTS.get((sid, match)) or AGENTS.get(("*", match))
    return snap, sorted(kinds)


def merged_corpus(sid):
    """Main request of this session + the latest request of every subagent type, per scope."""
    parts, sources = {}, []
    main = LAST.get(sid) or LAST.get(LAST.get("__latest__"))
    snaps = ([("main", main)] if main else []) + [(k, AGENTS.get((sid, k)) or AGENTS.get(("*", k)))
                                                   for k in sorted({k for s, k in AGENTS if s != "*"} | {k for s, k in AGENTS if s == "*"})]
    for name, snap in snaps:
        if not snap:
            continue
        sources.append(name)
        for scope, text in snap["corpus"].items():
            parts.setdefault(scope, []).append(text)
    return {k: "\n".join(v) for k, v in parts.items()}, sources


def yrb_processes():
    """PIDs of processes started via `claude --yrb` for THIS proxy: their environment carries CTXRW_YRB=1 and
    ANTHROPIC_BASE_URL pointing at our port (claude itself and anything it spawned)."""
    import subprocess
    marker = f"ANTHROPIC_BASE_URL=http://127.0.0.1:{PORT}"
    pids = set()
    if os.path.isdir("/proc"):
        for d in os.listdir("/proc"):
            if not d.isdigit():
                continue
            try:
                env = open(f"/proc/{d}/environ", "rb").read().decode("utf-8", "replace").split("\0")
            except OSError:
                continue
            if "CTXRW_YRB=1" in env and marker in env:
                pids.add(int(d))
        return pids
    out = subprocess.run(["ps", "-Eww", "-ax", "-o", "pid=,command="], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if " CTXRW_YRB=1" in line and (marker + " ") in line + " ":
            pids.add(int(line.split(None, 1)[0]))
    return pids


ACTIVE = {"n": 0, "last": time.time()}


def watchdog(srv):
    started = time.time()
    while True:
        time.sleep(10)
        if ACTIVE["n"] or time.time() - ACTIVE["last"] < 30 or time.time() - started < 30:
            continue
        try:
            alive = yrb_processes()
        except Exception as e:
            log(f"watchdog: could not list processes ({e}); staying up")
            continue
        if not alive:
            log("no live --yrb sessions, proxy exiting")
            srv.shutdown()
            return


def compiled_rules():
    try:
        m = os.path.getmtime(RULES)
    except OSError:
        return []
    if m != _cache["mtime"]:
        _cache["mtime"] = m
        try:
            with open(RULES) as f:
                cfg = json.load(f)
            out = []
            for r in cfg.get("rules", []):
                if not r.get("enabled", True) or not r.get("find"):
                    continue
                pat = r["find"] if r.get("regex") else re.escape(r["find"])
                flags = re.IGNORECASE if r.get("ignore_case") else 0
                out.append((re.compile(pat, flags), r.get("replace", ""), r.get("regex", False),
                            set(r.get("scope") or ["system", "user", "assistant", "tools"])))
            _cache["cfg"], _cache["compiled"] = cfg, out
        except Exception as e:
            log(f"rules.json unreadable, keeping previous version: {e}")
    return _cache["compiled"] if _cache["cfg"].get("enabled") else []


class Rewriter:
    def __init__(self, rules):
        self.rules = rules
        self.count = 0

    def text(self, s, where):
        for pat, rep, is_regex, scope in self.rules:
            if where not in scope:
                continue
            if is_regex:
                s, n = pat.subn(rep, s)
            else:
                s, n = pat.subn(lambda _m, r=rep: r, s)
            self.count += n
        return s

    def content(self, c, where):
        if isinstance(c, str):
            new = self.text(c, where)
            return new if new.strip() or not c.strip() else PLACEHOLDER
        if isinstance(c, list):
            emptied = set()
            for i, b in enumerate(c):
                if not isinstance(b, dict) or b.get("type") in SKIP_BLOCKS:
                    continue
                if isinstance(b.get("text"), str):
                    old = b["text"]
                    b["text"] = self.text(old, where)
                    if old.strip() and not b["text"].strip():
                        emptied.add(i)
                if b.get("type") == "tool_result" and "content" in b:
                    b["content"] = self.content(b["content"], where)
            if emptied:
                kept = [b for i, b in enumerate(c) if i not in emptied]
                for i in sorted(emptied):
                    cc = c[i].get("cache_control")
                    prev = [b for j, b in enumerate(c) if j < i and j not in emptied and isinstance(b, dict)]
                    if cc and prev and "cache_control" not in prev[-1]:
                        prev[-1]["cache_control"] = cc
                c = kept or [{"type": "text", "text": PLACEHOLDER}]
        return c

    def body(self, d):
        if "system" in d:
            d["system"] = self.content(d["system"], "system")
            if d["system"] in ([{"type": "text", "text": PLACEHOLDER}], PLACEHOLDER):
                del d["system"]
        for msg in d.get("messages", []):
            if isinstance(msg, dict) and "content" in msg:
                msg["content"] = self.content(msg["content"], msg.get("role", "user"))
        for t in d.get("tools", []) or []:
            if isinstance(t, dict) and isinstance(t.get("description"), str):
                t["description"] = self.text(t["description"], "tools")
        return d


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _proxy(self):
        if self.path.startswith("/__ctxrw/"):  # internal status calls don't count as session activity
            return self._handle()
        ACTIVE["n"] += 1
        try:
            self._handle()
        finally:
            ACTIVE["n"] -= 1
            ACTIVE["last"] = time.time()

    def _handle(self):
        n = int(self.headers.get("Content-Length") or 0)
        data = self.rfile.read(n) if n else b""
        path, _, query = self.path.partition("?")
        if path == "/__ctxrw/version":
            body = json.dumps({"version": VERSION, "pid": os.getpid()}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path in ("/__ctxrw/last", "/__ctxrw/corpus"):
            from urllib.parse import parse_qs
            q = {k: v[0] for k, v in parse_qs(query).items()}
            sid = q.get("session", "")
            if path == "/__ctxrw/corpus":
                corpus, sources = merged_corpus(sid)
                body = json.dumps({"corpus": corpus, "sources": sources, "matched": sid in LAST}, ensure_ascii=False).encode()
            elif q.get("agent"):
                snap, kinds = agent_snapshot(sid, q["agent"])
                body = json.dumps({"matched": bool(snap), "session": (snap or {}).get("session", sid), "snapshot": snap,
                                   "agents": kinds}, ensure_ascii=False).encode()
            else:
                matched = sid in LAST
                key = sid if matched else LAST.get("__latest__")
                body = json.dumps({"matched": matched, "session": key, "snapshot": LAST.get(key),
                                   "agents": sorted({k for _, k in AGENTS})}, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        replaced = None
        original = data
        if data and self.command == "POST" and path.startswith("/v1/messages") and not path.endswith("count_tokens"):
            try:
                d = json.loads(data)
                snapshot(d, self.headers)
            except Exception as e:
                d = None
                log(f"{path}: failed to parse request body, forwarding as-is: {e}")
            rules = compiled_rules() if d is not None else []
            if rules:
                try:
                    rw = Rewriter(rules)
                    d = rw.body(d)
                    replaced = rw.count
                    if rw.count:
                        data = json.dumps(d, ensure_ascii=False).encode()
                        log(f"{path}: replaced {rw.count}")
                except Exception as e:
                    log(f"{path}: rewrite failed, forwarding as-is: {e}")

        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP}
        headers["Host"] = UPSTREAM.netloc
        if data:
            headers["Content-Length"] = str(len(data))
        Conn = http.client.HTTPSConnection if UPSTREAM.scheme == "https" else http.client.HTTPConnection

        def send(body):
            h = dict(headers)
            if body:
                h["Content-Length"] = str(len(body))
            c = Conn(UPSTREAM.hostname, UPSTREAM.port, timeout=900)
            c.request(self.command, UPSTREAM.path.rstrip("/") + self.path, body=body or None, headers=h)
            return c, c.getresponse()

        try:
            conn, resp = send(data)
            if resp.status == 400 and replaced:
                err = resp.read(2000).decode("utf-8", "replace")
                conn.close()
                log(f"{path}: rejected by API after rewrite (HTTP 400, replaced {replaced}): {err[:300]}")
                log(f"{path}: fell back to original body for this request (a rule may be broken; run /context-rewrite doctor)")
                conn, resp = send(original)
                replaced = 0
        except Exception as e:
            log(f"upstream connection failed: {e}")
            msg = json.dumps({"type": "error", "error": {"type": "api_error", "message": f"context-rewrite proxy: {e}"}}).encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)
            return

        if resp.status >= 400 and path.startswith("/v1/messages"):
            log(f"{path}: upstream HTTP {resp.status}" + (f" (replaced {replaced})" if replaced else " (no replacement)"))
        self.send_response(resp.status, resp.reason)
        length = resp.getheader("Content-Length")
        for k, v in resp.getheaders():
            if k.lower() not in HOP:
                self.send_header(k, v)
        if length is not None:
            self.send_header("Content-Length", length)
        else:
            self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        try:
            while True:
                chunk = resp.read1(65536)
                if not chunk:
                    break
                if length is None:
                    self.wfile.write(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
                else:
                    self.wfile.write(chunk)
                self.wfile.flush()
            if length is None:
                self.wfile.write(b"0\r\n\r\n")
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            conn.close()

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _proxy


if __name__ == "__main__":
    os.makedirs(HOME, exist_ok=True)
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    srv.daemon_threads = True
    log(f"proxy started 127.0.0.1:{PORT} -> {UPSTREAM.geturl()}")
    if os.environ.get("CTXRW_NO_WATCHDOG") != "1":
        threading.Thread(target=watchdog, args=(srv,), daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)
