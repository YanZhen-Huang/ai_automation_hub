"""话术中心：各打电话动作的播报文本。
模板可在设置中人工定义（存 db phrase_templates），支持变量填充与 AI 润色。
变量：{title} {time} {room} {location} {attendees} {count} {file}
"""

from ai import llm
from core.logger import get_logger
from storage import db

log = get_logger("phrases")

DEFAULT_TEMPLATES = {
    "call_room": "您好，请帮我预订{room}会议室（会议时间 {time}）。请确认，谢谢。",
    "call_tea": "您好，请安排会场茶水服务（会议时间 {time}）。请确认，谢谢。",
    "call_service": "您好，请安排会场服务（会议时间 {time}）。请确认，谢谢。",
    "call_facilities": "您好，请准备音响、投影仪等配套设施（会议时间 {time}）。请确认，谢谢。",
    "call_table_card": "您好，请安排会议桌牌制作，共{count}人：{attendees}。请确认，谢谢。",
    "call_print": "您好，{title}的汇报材料已通过微信发送给您，共{count}份，请安排印刷并送到{location}。请确认，谢谢。",
}

TEMPLATE_CODES = [
    ("call_room", "预订会议室"),
    ("call_tea", "茶水"),
    ("call_service", "会场服务"),
    ("call_facilities", "音响/投影设施"),
    ("call_table_card", "桌牌制作"),
    ("call_print", "安排印刷"),
]


def _vars(meeting=None, extra=None):
    meeting = meeting or {}
    attendees = (meeting.get("attendees") or "").strip()
    count = "待定"
    if attendees:
        import re as _re
        names = [a for a in _re.split(r"[，,、\s]+", attendees) if a.strip()]
        count = str(len(names)) if names else "待定"
    v = {
        "title": meeting.get("title") or "",
        "time": meeting.get("start_time") or "时间待定",
        "room": meeting.get("room") or "待定",
        "location": meeting.get("location") or "前台",
        "attendees": attendees or "待定",
        "count": count,
        "file": "",
    }
    if extra:
        v.update(extra)
    return v


def fill(code, meeting=None, extra=None):
    """生成某动作的最终播报话术。"""
    tpl = db.get_template(code)
    text = (tpl["template"] if tpl else DEFAULT_TEMPLATES.get(code, "")).strip()
    if not text:
        text = DEFAULT_TEMPLATES.get(code, "您好，请确认相关安排。请确认，谢谢。")
    for k, val in _vars(meeting, extra).items():
        text = text.replace("{" + k + "}", str(val) if val is not None else "")
    if tpl and tpl["use_ai"]:
        text = polish(text)
    return text


def polish(text):
    """用 AI 把话术润色得更自然得体。无 Key 或失败返回原文本。"""
    if not llm.available():
        return text
    try:
        r = llm.chat([
            {"role": "system",
             "content": "你是行政接待助手。把下面的电话请求润色成自然得体的口语，"
                        "保留所有信息（时间/房间/人员/数量/地点），只输出润色后的结果。"},
            {"role": "user", "content": text},
        ], temperature=0.4, max_tokens=200)
        r = r.strip()
        return r if r else text
    except Exception:
        log.exception("话术润色失败")
        return text
