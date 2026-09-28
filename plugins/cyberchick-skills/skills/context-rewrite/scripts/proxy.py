#!/usr/bin/env python3
import http.client
import json
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

HOME = os.path.expanduser(os.environ.get("CTXRW_HOME") or os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude", "context-rewrite"))
RULES = os.path.join(HOME, "rules.json")
LOG = os.path.join(HOME, "proxy.log")
SESSIONS = os.path.join(HOME, "sessions")
PORT = int(os.environ.get("CTXRW_PORT", "8787"))
UPSTREAM = urlsplit(os.environ.get("CTXRW_UPSTREAM", "https://api.anthropic.com"))
HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te",
       "trailer", "trailers", "transfer-encoding", "upgrade", "host", "content-length"}
SKIP_BLOCKS = {"thinking", "redacted_thinking"}
PLACEHOLDER = "(removed)"

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


def snapshot(d, headers):
    """在内存里记住每个会话主 agent 最近一次请求的原文（替换前），供 capture 查看。"""
    if headers.get("x-claude-code-agent-id"):
        return
    sid = headers.get("x-claude-code-session-id") or "-"
    msgs = [m for m in d.get("messages", []) if isinstance(m, dict)]
    users = [m for m in msgs if m.get("role") == "user"]
    picks = []
    if users:
        picks.append(("第一条 user 消息", users[0]))
    if len(users) > 1:
        picks.append(("最后一条 user 消息", users[-1]))
    LAST[sid] = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "model": d.get("model"),
                 "system": texts(d.get("system", [])),
                 "messages": [(label, texts(m.get("content"))) for label, m in picks]}
    LAST["__latest__"] = sid


def watchdog(srv):
    started, known = time.time(), set()
    while True:
        time.sleep(10)
        try:
            known |= {int(n) for n in os.listdir(SESSIONS) if n.isdigit()}
        except OSError:
            pass
        alive = set()
        for pid in known:
            try:
                os.kill(pid, 0)
                alive.add(pid)
            except ProcessLookupError:
                try:
                    os.remove(os.path.join(SESSIONS, str(pid)))
                except OSError:
                    pass
            except PermissionError:
                alive.add(pid)
        known = alive
        if not alive and time.time() - started > 30:
            log("没有存活的 --yrb 会话，proxy 退出")
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
                            set(r.get("scope") or ["system", "user", "assistant"])))
            _cache["cfg"], _cache["compiled"] = cfg, out
        except Exception as e:
            log(f"rules.json 读取失败，沿用上一版: {e}")
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
        return d


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _proxy(self):
        n = int(self.headers.get("Content-Length") or 0)
        data = self.rfile.read(n) if n else b""
        path, _, query = self.path.partition("?")
        if path == "/__ctxrw/last":
            sid = dict(kv.partition("=")[::2] for kv in query.split("&") if kv).get("session", "")
            matched = sid in LAST
            key = sid if matched else LAST.get("__latest__")
            body = json.dumps({"matched": matched, "session": key, "snapshot": LAST.get(key)}, ensure_ascii=False).encode()
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
                log(f"{path} 请求体解析失败，原样转发: {e}")
            rules = compiled_rules() if d is not None else []
            if rules:
                try:
                    rw = Rewriter(rules)
                    d = rw.body(d)
                    replaced = rw.count
                    if rw.count:
                        data = json.dumps(d, ensure_ascii=False).encode()
                        log(f"{path} 替换 {rw.count} 处")
                except Exception as e:
                    log(f"{path} 改写失败，原样转发: {e}")

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
                log(f"{path} 替换后被 API 拒绝（HTTP 400，替换 {replaced} 处）: {err[:300]}")
                log(f"{path} 已自动回退：本次改用原文重发（某条规则可能有问题，跑 /yrb doctor 查看）")
                conn, resp = send(original)
                replaced = 0
        except Exception as e:
            log(f"上游连接失败: {e}")
            msg = json.dumps({"type": "error", "error": {"type": "api_error", "message": f"context-rewrite proxy: {e}"}}).encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)
            return

        if resp.status >= 400 and path.startswith("/v1/messages"):
            log(f"{path} 上游返回 HTTP {resp.status}" + (f"（本次替换 {replaced} 处）" if replaced else "（本次没有替换）"))
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
    log(f"proxy 启动 127.0.0.1:{PORT} -> {UPSTREAM.geturl()}")
    if os.environ.get("CTXRW_NO_WATCHDOG") != "1":
        threading.Thread(target=watchdog, args=(srv,), daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)
