"""桌面端 ↔ 鸿蒙手机端 联动（局域网 HTTP）。
桌面端：提交"拨打电话"任务，手机 App 轮询拉取、文字转语音拨打、回传确认信息。
"""

import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from core.config import CONFIG
from core.events import bus
from core.logger import get_logger

log = get_logger("phone")
TASK_TTL = 600          # 任务超时(秒)，超时重新投递
MAX_RETRIES = 3


def _token():
    return CONFIG.get("phone", {}).get("token", "") or ""


class _Handler(BaseHTTPRequestHandler):
    def _auth(self):
        from urllib.parse import urlparse, parse_qs
        tok = parse_qs(urlparse(self.path).query).get("token", [""])[0]
        if _token() and tok != _token():
            self._json({"error": "unauthorized"}, 401)
            return False
        return True

    def do_GET(self):
        if self.path.startswith("/phone/poll"):
            if not self._auth():
                return
            task = PhoneLink.instance().next_task()
            self._json(task if task else {})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path.startswith("/phone/result"):
            if not self._auth():
                return
            try:
                body = self._read_json()
            except Exception:
                self._json({"error": "bad json"}, 400)
                return
            PhoneLink.instance().on_result(body or {})
            self._json({"ok": True})
        else:
            self._json({"error": "not found"}, 404)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > 65536:
            raise ValueError("body too large")
        return json.loads(self.rfile.read(length) or b"{}")

    def _json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


class PhoneLink:
    _inst = None

    def __init__(self):
        self._queue = []
        self._tasks = {}
        self._lock = threading.RLock()
        self._server = None
        self._thread = None

    @classmethod
    def instance(cls):
        if cls._inst is None:
            cls._inst = PhoneLink()
        return cls._inst

    def start(self, host="0.0.0.0", port=8781):
        if self._server:
            return
        self._server = ThreadingHTTPServer((host, port), _Handler)
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        daemon=True)
        self._thread.start()
        log.info("手机联动服务已启动: %s:%s", host, port)

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def submit_call(self, item_id, action, text, number=""):
        """提交一个"打电话"任务供手机拉取。返回 task_id。"""
        task = {
            "task_id": uuid.uuid4().hex[:12],
            "item_id": item_id,
            "action": action,
            "text": text,
            "number": number,
            "created_at": time.time(),
            "retries": 0,
        }
        with self._lock:
            self._tasks[task["task_id"]] = task
            self._queue.append(task["task_id"])
        log.info("已提交打电话任务: %s -> %s", action, text)
        return task["task_id"]

    def next_task(self):
        """手机 GET 拉取下一个待拨打任务（含超时重投递）。"""
        now = time.time()
        with self._lock:
            # 回收超时未回传的任务，重新投递（超过重试上限则丢弃）
            expired = [tid for tid, t in self._tasks.items()
                       if now - t.get("created_at", now) > TASK_TTL]
            for tid in expired:
                t = self._tasks.get(tid)
                if t is None:
                    continue
                t["retries"] = t.get("retries", 0) + 1
                if t["retries"] > MAX_RETRIES:
                    log.warning("任务超时放弃: %s", t.get("action"))
                    self._tasks.pop(tid, None)
                    bus().publish("phone.timeout", {"item_id": t.get("item_id")})
                else:
                    t["created_at"] = now
                    self._queue.append(tid)
            if not self._queue:
                return None
            tid = self._queue.pop(0)
            return self._tasks.get(tid)

    def on_result(self, body):
        """手机 POST 回传拨打结果。"""
        tid = body.get("task_id")
        with self._lock:
            task = self._tasks.pop(tid, None) if tid else None
        if not task:
            return
        payload = {
            "task_id": tid,
            "item_id": task.get("item_id"),
            "action": task.get("action"),
            "ok": bool(body.get("ok", True)),
            "confirmed": (body.get("confirmed") or "").strip(),
        }
        log.info("手机回传: %s", payload)
        bus().publish("phone.result", payload)
