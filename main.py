import threading
import time
import tkinter as tk

from ai.extract import extract
from collectors import collect_all
from core.config import CONFIG
from core.events import bus
from core.logger import get_logger
from core.scheduler import scheduler
from desktop.app import DesktopApp
from storage import db

log = get_logger("main")


def _throttle(fn, key, default, worker):
    """按配置间隔节流执行（配置修改实时生效）。"""
    iv = CONFIG
    for part in key.split("."):
        iv = iv.get(part, {}) if isinstance(iv, dict) else iv
    try:
        iv = max(5, int(iv)) if not isinstance(iv, dict) else default
    except (TypeError, ValueError):
        iv = default
    now = time.time()
    if now - getattr(fn, "_last", 0) < iv:
        return
    fn._last = now
    worker()


def ingest(msgs):
    """去重入库（含批次内去重），返回新入库条目。"""
    existing = {i["content"] for i in db.list_info_items(limit=1000)}
    new, seen = [], set()
    for m in msgs:
        c = m.get("content")
        if not c or c in existing or c in seen:
            continue
        seen.add(c)
        new.append(m)
    for m in new:
        db.add_info_item(m["source"], m["content"])
    return new


def _collect_work():
    """多源采集 → 去重入库 → AI 提炼（会议相关则通知）。"""
    new = ingest(collect_all())
    if not new:
        return
    res = extract([m["content"] for m in new])
    if res.get("is_meeting_related"):
        bus().publish("notification",
                      {"title": "检测到会议相关信息",
                       "message": res.get("summary") or "已入库，可创建会议准备"})
    bus().publish("info.new", {"count": len(new)})
    log.info("采集 %d 条，会议相关: %s", len(new), res.get("is_meeting_related"))


def collect_once():
    _throttle(collect_once, "collect.interval_seconds", 300, _collect_work)


def _ocr_work():
    from collectors.ocr import OCRCollector
    new = ingest(OCRCollector().collect())
    if new:
        bus().publish("info.new", {"count": len(new)})
        log.info("OCR 识别 %d 条", len(new))


def collect_ocr():
    _throttle(collect_ocr, "ocr.interval_seconds", 120, _ocr_work)


def start_web():
    try:
        import uvicorn
        from server.app import app
        cfg = uvicorn.Config(app, host=CONFIG["server"]["host"],
                             port=CONFIG["server"]["port"],
                             log_level="warning", log_config=None,
                             access_log=False)
        uvicorn.Server(cfg).run()
    except Exception:
        log.exception("Web 服务启动失败")


def start_phone():
    if not CONFIG["phone"].get("enabled", True):
        return
    from automation.phone_link import PhoneLink
    try:
        PhoneLink.instance().start(CONFIG["phone"]["host"], CONFIG["phone"]["port"])
    except Exception:
        log.exception("手机联动服务启动失败，继续运行")


def setup_tray(root, events):
    import pystray
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (64, 64), "#141414")
    d = ImageDraw.Draw(img)
    d.polygon([(32, 10), (50, 54), (14, 54)], fill="#e11d2a")
    d.ellipse([25, 25, 39, 39], fill="#f2f0e6")

    def show(_i):
        events.put("show_main")

    def quit_app(_i):
        events.put("quit")

    icon = pystray.Icon("meeting_prep", img, "会议准备自动化工作台",
                        pystray.Menu(
                            pystray.MenuItem("显示主窗口", show),
                            pystray.MenuItem("退出", quit_app)))
    threading.Thread(target=icon.run, daemon=True).start()
    return icon


def main():
    import queue as _queue
    start_phone()
    threading.Thread(target=start_web, daemon=True).start()

    scheduler().every(15, collect_once)
    if CONFIG.get("collect", {}).get("ocr_enabled"):
        scheduler().every(15, collect_ocr)
    scheduler().start()

    events = _queue.Queue()

    def drain_events():
        while True:
            try:
                ev = events.get_nowait()
                if ev == "show_main":
                    root.deiconify()
                    root.lift()
                elif ev == "quit":
                    root.destroy()
            except _queue.Empty:
                break
        root.after(300, drain_events)

    root = tk.Tk()
    app = DesktopApp(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (root.withdraw(),))
    setup_tray(root, events)
    drain_events()
    log.info("工作台已启动：桌面窗口 + Web http://%s:%s + 手机联动端口 %s",
             CONFIG["server"]["host"], CONFIG["server"]["port"],
             CONFIG["phone"]["port"])
    try:
        app.run()
    finally:
        scheduler().stop()


if __name__ == "__main__":
    main()
