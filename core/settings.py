"""设置中心：把关键配置项以表单形式暴露给桌面/Web 端修改。"""

from core.config import CONFIG, save_config

SETTING_ITEMS = [
    {"key": "llm.api_key", "label": "DeepSeek API Key", "type": "password",
     "description": "DeepSeek 平台的 API Key，用于 AI 信息提炼；留空则使用关键词规则降级"},
    {"key": "llm.base_url", "label": "DeepSeek Base URL", "type": "text",
     "description": "API 服务地址，默认 DeepSeek，可更换任意 OpenAI 兼容服务"},
    {"key": "llm.model", "label": "DeepSeek 模型", "type": "text",
     "description": "使用的模型名，默认 deepseek-chat"},
    {"key": "server.port", "label": "Web 端口", "type": "int",
     "description": "Web 管理界面端口，修改后需重启生效"},
    {"key": "phone.port", "label": "手机联动端口", "type": "int",
     "description": "鸿蒙手机端连接端口，修改后需重启生效"},
    {"key": "collect.interval_seconds", "label": "采集轮询间隔(秒)", "type": "int",
     "description": "微信/手动信息扫描入库的频率"},
    {"key": "collect.wechat_enabled", "label": "启用微信采集", "type": "bool",
     "description": "是否读取微信会话列表作为信息来源（需微信已登录）"},
    {"key": "collect.ocr_enabled", "label": "启用 OCR 识别", "type": "bool",
     "description": "后台静默识别屏幕指定区域文字（用于钉钉等无法读取的界面）"},
    {"key": "ocr.interval_seconds", "label": "OCR 识别间隔(秒)", "type": "int",
     "description": "OCR 后台轮询频率"},
    {"key": "ocr.region", "label": "OCR 识别区域", "type": "text",
     "description": "left,top,width,height，屏幕左上角为原点，如 0,0,800,600"},
    {"key": "ocr.engine", "label": "OCR 引擎", "type": "text",
     "description": "rapidocr(默认，无需安装) / tesseract(需安装 Tesseract)"},
    {"key": "wechat.send_enabled", "label": "启用微信自动发送", "type": "bool",
     "description": "微信通知是否自动发送；关闭则只生成通知文本"},
    {"key": "wechat.notify_target", "label": "微信通知目标", "type": "text",
     "description": "自动发送的目标群聊或联系人名称"},
    {"key": "wechat.print_target", "label": "印刷微信联系人", "type": "text",
     "description": "印刷交付时自动发送文件的微信联系人名称（提前用号码加好友）"},
    {"key": "wechat.send_delay", "label": "微信发送延迟(秒)", "type": "int",
     "description": "搜索目标后等待结果出现的秒数，网络慢时可调大"},
    {"key": "speech.whisper_model", "label": "Whisper 模型", "type": "text",
     "description": "录音转文字模型：tiny/base/small/medium/large，越大越准越慢"},
]


def _get_path(cfg, path):
    cur = cfg
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _set_path(cfg, path, value):
    parts = path.split(".")
    cur = cfg
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value


def _coerce(value, vtype):
    try:
        if vtype == "int":
            return int(value)
        if vtype == "bool":
            return str(value).lower() in ("1", "true", "yes", "on")
    except (TypeError, ValueError):
        return value
    return value


def items():
    return list(SETTING_ITEMS)


def get_settings():
    out = {}
    for it in SETTING_ITEMS:
        out[it["key"]] = _get_path(CONFIG, it["key"])
    return out


def update_settings(mapping):
    allowed = {i["key"] for i in SETTING_ITEMS}
    for k, v in (mapping or {}).items():
        if k not in allowed:
            continue
        vtype = next((i["type"] for i in SETTING_ITEMS if i["key"] == k), None)
        _set_path(CONFIG, k, _coerce(v, vtype) if vtype else v)
    save_config()
    return get_settings()
