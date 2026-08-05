"""智能采集引擎：AI + 模拟操作 + OCR 自动遍历聊天会话采集信息。
流程：定位窗口 → 读会话列表 → AI 筛选重点对象 → 模拟点击 → OCR 消息区 → 提炼入库。
安全：默认仅前台窗口、单轮自动停、每步失败跳过、可一键停止。"""

import ctypes
import threading
import time

from ai.extract import extract, extract_tasks, select_sessions
from collectors import uia_common
from collectors.ocr import ocr_region
from core.config import CONFIG
from core.events import bus
from core.logger import get_logger
from storage import db

log = get_logger("smart_scan")

_APP_KW = {
    "wechat": (("微信",), ("WeChat",)),
    "dingtalk": (("钉钉", "DingTalk"), ("DingTalk",)),
    "feishu": (("飞书", "Feishu", "Lark"), ("Feishu", "Lark", "FTWin")),
}


class SmartScanEngine:
    def __init__(self):
        self.status = "idle"  # idle / running / stopped
        self.progress = []
        self._lock = threading.RLock()

    def _publish(self, msg):
        with self._lock:
            self.progress.append((time.strftime("%H:%M:%S"), msg))
            self.progress = self.progress[-20:]
        bus().publish("scan.progress", {"msg": msg, "status": self.status})
        log.info("智能采集: %s", msg)

    def _stopped(self):
        with self._lock:
            return self.status == "stopped"

    def run_once(self):
        with self._lock:
            if self.status == "running":
                return
            self.status = "running"
        self._publish("开始采集")
        try:
            self._run()
        except Exception:
            log.exception("智能采集异常")
            self._publish("采集异常")
        finally:
            with self._lock:
                self.status = "idle"
            self._publish("采集结束")

    def stop(self):
        with self._lock:
            self.status = "stopped"
        self._publish("已停止")

    # ---------- 主流程 ----------

    def _run(self):
        cfg = CONFIG.get("scan", {})
        app = cfg.get("app", "wechat")
        auto = uia_common.get_uia()
        if auto is None:
            self._publish("UIA 不可用")
            return
        win = self._get_window(auto, app)
        if win is None:
            self._publish(f"未找到 {app} 窗口（前台可见）")
            return
        self._publish("已定位窗口")

        names = self._read_sessions(win)
        if not names:
            self._publish("未读取到会话列表")
            return
        self._publish(f"读取到 {len(names)} 个会话")

        focus = cfg.get("focus_names", "")
        role = cfg.get("role", "")
        try:
            max_n = int(cfg.get("max_sessions", 5))
        except (TypeError, ValueError):
            max_n = 5
        targets = select_sessions(names, focus, role, max_n)
        if not targets:
            self._publish("AI 未筛选到目标会话")
            return
        self._publish("目标会话: " + "、".join(targets))

        for t in targets:
            if self._stopped():
                return
            if not self._click_session(win, t):
                continue
            try:
                delay = float(cfg.get("load_delay", 1.5))
            except (TypeError, ValueError):
                delay = 1.5
            time.sleep(delay)
            if self._stopped():
                return
            texts = self._ocr_message_area(win)
            if not texts:
                self._publish(f"{t}: 未识别到文本")
                continue
            self._ingest(t, texts)
            self._publish(f"{t}: 采集 {len(texts)} 条")

    # ---------- 定位 / 读取 / 点击 / OCR ----------

    def _get_window(self, auto, app):
        cfg = CONFIG.get("scan", {})
        kw = _APP_KW.get(app, _APP_KW["wechat"])
        if cfg.get("focus_only", True):
            try:
                hwnd = ctypes.windll.user32.GetForegroundWindow()
                win = auto.ControlFromHandle(hwnd)
                if win is not None and self._match(win, kw):
                    return win
            except Exception:
                log.exception("前台窗口获取失败")
            return None
        return uia_common.find_window(auto, name_kw=kw[0], class_kw=kw[1])

    @staticmethod
    def _match(win, kw):
        try:
            name = win.Name or ""
            cls = win.ClassName or ""
            return any(k in name for k in kw[0]) or any(k in cls for k in kw[1])
        except Exception:
            return False

    @staticmethod
    def _read_sessions(win):
        texts = uia_common.collect_messages(win, "", max_items=40,
                                            skip=("微信", "搜一搜", "看一看", "扫一扫"))
        names, seen = [], set()
        for t in texts:
            first = t.split("\n")[0].strip()
            if "] " in first:
                first = first.split("] ", 1)[-1].strip()
            if first and first not in seen and len(first) < 30:
                seen.add(first)
                names.append(first)
        return names

    def _click_session(self, win, target):
        try:
            item = win.Control(searchDepth=8, Name=target)
            if item is None:
                item = self._find_conv(win, target)
            if item is None:
                self._publish(f"未找到会话 {target}")
                return False
            item.Click()
            return True
        except Exception:
            log.exception("点击会话失败 %s", target)
            return False

    def _find_conv(self, win, target):
        best = None

        def walk(c, depth):
            nonlocal best
            if best is not None or depth > 6:
                return
            try:
                children = c.GetChildren()
            except Exception:
                return
            for ch in children:
                try:
                    name = (ch.Name or "").strip()
                    if name and target in name:
                        best = ch
                        return
                except Exception:
                    pass
                walk(ch, depth + 1)

        walk(win, 0)
        return best

    def _ocr_message_area(self, win):
        cfg = CONFIG.get("scan", {})
        try:
            rect = win.BoundingRectangle
            l, t, r, b = rect.left, rect.top, rect.right, rect.bottom
            try:
                top_ratio = float(cfg.get("msg_top", 0.4))
            except (TypeError, ValueError):
                top_ratio = 0.4
            h = b - t
            if h <= 0:
                return []
            bbox = (l, int(t + h * top_ratio), r, b)
        except Exception:
            return []
        return ocr_region(bbox)

    # ---------- 去重入库 + 提炼 ----------

    def _ingest(self, session, texts):
        existing = {i["content"] for i in db.list_info_items(limit=1000)}
        new, seen = [], set()
        for t in texts:
            content = f"[{session}] {t}"
            if content in existing or content in seen:
                continue
            seen.add(content)
            new.append(content)
        for c in new:
            db.add_info_item("ocr", c)
        if not new:
            return
        cfg = CONFIG.get("scan", {})
        role = cfg.get("role", "")
        res = extract(new, role=role)
        if res.get("is_meeting_related"):
            bus().publish("notification",
                          {"title": "智能采集·会议相关",
                           "message": res.get("summary") or session})
        added = 0
        for t in extract_tasks(new, role=role):
            _, is_new = db.add_task_unique(t["title"], t["detail"], t["due_date"])
            if is_new:
                added += 1
        bus().publish("info.new", {"count": len(new)})
        if added:
            bus().publish("task.new", {"count": added})


engine = SmartScanEngine()
