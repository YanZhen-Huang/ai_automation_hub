"""手动输入：用户录入/粘贴文本作为信息源，随后交 AI 提炼。"""

from core.events import bus
from storage import db


def submit_manual(text, meeting_id=None, meta=None):
    """录入一段文本进入信息库，并发布 info.new 事件。返回 info item id。"""
    text = (text or "").strip()
    if not text:
        return None
    item_id = db.add_info_item("manual", text, meeting_id=meeting_id, meta=meta)
    bus().publish("info.new", {"id": item_id, "source": "manual", "content": text})
    return item_id
