"""运行状态采集：供桌面/Web 端透明展示各服务与进程状态。"""

import os
import socket
import time

from core.config import CONFIG
from core.logger import get_logger
from storage import db

log = get_logger("status")


def _port_open(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


def service_status():
    server_port = CONFIG.get("server", {}).get("port", 8780)
    phone_port = CONFIG.get("phone", {}).get("port", 8781)
    return {
        "services": [
            {"name": "Web 服务", "key": "web",
             "port": server_port,
             "running": _port_open(server_port),
             "url": f"http://127.0.0.1:{server_port}"},
            {"name": "手机联动", "key": "phone",
             "port": phone_port,
             "running": _port_open(phone_port),
             "url": f"http://127.0.0.1:{phone_port}"},
            {"name": "信息采集", "key": "collect",
             "interval": CONFIG.get("collect", {}).get("interval_seconds", 300),
             "running": True},
            {"name": "OCR 识别", "key": "ocr",
             "enabled": bool(CONFIG.get("collect", {}).get("ocr_enabled")),
             "interval": CONFIG.get("ocr", {}).get("interval_seconds", 120),
             "running": bool(CONFIG.get("collect", {}).get("ocr_enabled"))},
            {"name": "AI 提炼", "key": "llm",
             "available": bool(CONFIG.get("llm", {}).get("api_key")),
             "running": True},
            {"name": "微信联动", "key": "wechat",
             "send_enabled": bool(CONFIG.get("wechat", {}).get("send_enabled")),
             "running": True},
            {"name": "智能采集", "key": "scan",
             "enabled": bool(CONFIG.get("scan", {}).get("enabled")),
             "running": bool(CONFIG.get("scan", {}).get("enabled"))},
        ],
        "process": {
            "pid": os.getpid(),
            "app": CONFIG.get("app", {}).get("name", ""),
            "version": CONFIG.get("app", {}).get("version", ""),
            "data_dir": str(CONFIG.get("_base_dir", "")) or "data/",
        },
        "counts": {
            "info_items": _count("info_items"),
            "meetings": _count("meetings"),
            "prep_items": _count("prep_items"),
            "rooms": _count("rooms"),
            "tasks": _count("tasks"),
            "action_logs": _count("action_logs"),
        },
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def _count(table):
    try:
        from storage import db as _db
        conn = _db.get_conn()
        try:
            r = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
            return r["n"] if r else 0
        finally:
            conn.close()
    except Exception:
        return -1


def recent_logs(limit=15):
    path = None
    try:
        from core.config import DATA_DIR
        path = DATA_DIR / "app.log"
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        return lines[-limit:]
    except Exception:
        return []
