import copy
import json
import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
CONFIG_FILE = DATA_DIR / "config.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)

DEFAULTS = {
    "app": {
        "name": "会议准备自动化工作台",
        "version": "0.1.0",
    },
    "llm": {
        "api_key": os.environ.get("DEEPSEEK_API_KEY", ""),
        "base_url": os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
    },
    "server": {
        "host": "127.0.0.1",
        "port": 8780,
    },
    "collect": {
        "interval_seconds": int(os.environ.get("COLLECT_INTERVAL", "300")),
        "wechat_enabled": True,
        "manual_enabled": True,
        "speech_enabled": True,
        "ocr_enabled": True,
    },
    "ocr": {
        "interval_seconds": 120,
        "region": "0,0,800,600",
        "engine": "rapidocr",
    },
    "wechat": {
        "send_enabled": False,
        "notify_target": "",
        "print_target": "",
        "send_delay": 3,
    },
    "speech": {
        "whisper_model": "small",
        "device": "auto",
    },
    "phone": {
        "enabled": True,
        "host": "0.0.0.0",     # 桌面端监听，供手机局域网访问
        "port": 8781,
        "token": "",
    },
    "desktop": {
        "live_enabled": True,
    },
}

CONFIG = copy.deepcopy(DEFAULTS)


def _deep_merge(base, override):
    for k, v in (override or {}).items():
        if v is None:
            continue
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


def load_config():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                _deep_merge(CONFIG, json.load(f))
        except Exception:
            pass
    return CONFIG


def save_config(cfg=None):
    global CONFIG
    if cfg is not None:
        CONFIG = cfg
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(CONFIG, f, ensure_ascii=False, indent=2)
    return CONFIG


load_config()

if not CONFIG.get("phone", {}).get("token"):
    import uuid as _uuid
    CONFIG["phone"]["token"] = _uuid.uuid4().hex[:16]
    save_config()
