"""固定工作流：会议准备。

一阶段（并行，除特殊要求外）：订会议室/茶水/服务/音响设施、备材料转PPT+印刷、人工定时间、微信通知、定签字表。
二阶段（串行）：定与会人员 → 打电话排桌牌 → 人工审查 → 提醒接待。
"""

from ai.extract import extract, generate_materials
from automation import actions, phrases
from core.config import CONFIG
from core.events import bus
from core.logger import get_logger
from storage import db

OUT_DIR = actions.OUT_DIR

log = get_logger("workflow")

PHASE1 = [
    {"code": "call_room", "name": "打电话要会议室"},
    {"code": "call_tea", "name": "打电话要茶水"},
    {"code": "call_service", "name": "打电话要服务"},
    {"code": "call_facilities", "name": "打电话要音响/投影等配套设施"},
    {"code": "prep_materials", "name": "准备汇报材料并转PPT后安排印刷"},
    {"code": "confirm_time", "name": "确定会议时间（人工）"},
    {"code": "notify_wechat", "name": "微信下通知"},
    {"code": "confirm_sign_list", "name": "确定签字表"},
]
PHASE2 = [
    {"code": "confirm_attendees", "name": "确定与会人员"},
    {"code": "call_table_card", "name": "打电话安排桌牌"},
    {"code": "manual_review", "name": "人工审查确认"},
    {"code": "remind_reception", "name": "提醒人工接待"},
]

CALL_CODES = {"call_room", "call_tea", "call_service", "call_facilities",
              "call_table_card"}
HUMAN_CODES = {"confirm_time", "confirm_sign_list", "confirm_attendees",
               "manual_review"}
# 需审批后真正执行的自动化动作
AUTO_CODES = CALL_CODES | {"prep_materials", "notify_wechat"}


def setup_meeting(title, start_time=None):
    """创建会议并挂载固定工作流动作项。返回 meeting_id。"""
    mid = db.create_meeting(title, start_time)
    items = []
    for i, it in enumerate(PHASE1):
        items.append({"phase": 1, **it, "order_index": i + 1})
    for i, it in enumerate(PHASE2):
        items.append({"phase": 2, **it, "order_index": i + 1})
    db.add_prep_items(mid, items)
    return mid


def run_phase1(meeting_id):
    """并行触发一阶段：所有待执行动作先进入"待审批"，由用户批准后执行。
    同时激活二阶段首项（待审批）。"""
    for item in db.list_prep_items(meeting_id):
        if item["phase"] == 1 and item["status"] == "pending":
            request_approval(item)
    _advance_phase2(meeting_id)


def request_approval(item):
    """将动作项置为"待审批"并通知用户。"""
    db.update_prep_item(item["id"], status="waiting", result="待审批")
    bus().publish("approval.requested",
                  {"item_id": item["id"], "name": item["name"],
                   "meeting_id": item["meeting_id"]})


def approve(item_id):
    """用户审批通过后执行；人工确认类动作则直接标记完成。
    会议室/桌牌动作若缺少必要信息（会议室/人员名单），先请求用户补充。"""
    item = db.get_prep_item(item_id)
    if item is None or item["status"] != "waiting":
        return
    meeting = db.get_meeting(item["meeting_id"]) or {}
    if item["code"] == "call_room" and not (meeting.get("room") or "").strip():
        bus().publish("room.select.requested",
                      {"item_id": item_id, "meeting_id": item["meeting_id"],
                       "name": item["name"]})
        return
    if item["code"] == "call_table_card" and not (meeting.get("attendees") or "").strip():
        bus().publish("attendees.requested",
                      {"item_id": item_id, "meeting_id": item["meeting_id"],
                       "name": item["name"]})
        return
    if item["code"] in HUMAN_CODES:
        _mark_done(item_id, "已确认")
        return
    execute_item(item)


def set_room(meeting_id, room):
    """用户选定会议室后，继续执行预订动作。"""
    db.update_meeting(meeting_id, room=room)
    _resume_waiting(meeting_id, "call_room")


def set_attendees(meeting_id, attendees, source="manual"):
    """用户确定与会人员后，继续执行桌牌动作。"""
    db.update_meeting(meeting_id, attendees=attendees, attendee_source=source)
    _resume_waiting(meeting_id, "call_table_card")


def _resume_waiting(meeting_id, code):
    for it in db.list_prep_items(meeting_id):
        if it["code"] == code and it["status"] == "waiting":
            approve(it["id"])


def candidates_for_room(meeting_id=None):
    """候选会议室 = 会议室库 - AI 提炼的不可用项（去重）。"""
    from ai.extract import extract_rooms
    infos = db.list_info_items(meeting_id) or db.list_info_items()
    unavailable = set(extract_rooms([i["content"] for i in infos]))
    seen, out = set(), []
    for r in db.list_rooms():
        if r["status"] != "active" or r["name"] in unavailable:
            continue
        if r["name"] in seen:
            continue
        seen.add(r["name"])
        out.append(r["name"])
    return out


def execute_item(item):
    code = item["code"]
    meeting = db.get_meeting(item["meeting_id"]) or {}
    try:
        if code in CALL_CODES:
            db.update_prep_item(item["id"], status="running")
            text = phrases.fill(code, meeting)
            actions.call_phone(item["id"], item["name"], text, db.get_number(code))

        elif code == "prep_materials":
            db.update_prep_item(item["id"], status="running")
            _prep_materials(item, meeting)

        elif code == "notify_wechat":
            text = _notify_text(meeting)
            target = _notify_target(meeting)
            ok = actions.send_wechat_text(text, target=target)
            if ok:
                result = f"已自动发送到「{target}」"
            else:
                actions.notify("微信通知（请手动发送）", f"目标:{target}\n{text}")
                result = f"未自动发送（目标:{target}），已生成通知文本"
            _mark_done(item["id"], result)

        elif code in HUMAN_CODES:
            db.update_prep_item(item["id"], status="waiting")
            actions.notify("会议准备 · 需人工确认", item["name"])

        elif code == "remind_reception":
            actions.notify("会议准备", "请提醒人工接待与会人员。")
            _mark_done(item["id"], "已提醒接待")

        else:
            _mark_done(item["id"], "")
    except Exception:
        log.exception("动作执行异常: %s", item["name"])
        db.update_prep_item(item["id"], status="waiting", result="执行出错，请重试")


def mark_done(item_id, result=""):
    """人工确认/完成某动作项。"""
    item = db.get_prep_item(item_id)
    if item is None:
        return
    _mark_done(item_id, result)


def _mark_done(item_id, result):
    db.update_prep_item(item_id, status="done", result=result)
    item = db.get_prep_item(item_id)
    if item and item["phase"] == 2:
        _advance_phase2(item["meeting_id"])
    bus().publish("prep.updated", {"item_id": item_id})


def _advance_phase2(meeting_id):
    """串行推进：找到第一个未完成项，若前一项已完成则进入"待审批"。"""
    items = [i for i in db.list_prep_items(meeting_id) if i["phase"] == 2]
    for idx, item in enumerate(items):
        if item["status"] == "done":
            continue
        if idx == 0 or items[idx - 1]["status"] == "done":
            if item["status"] == "pending":
                request_approval(item)
        break


def on_phone_result(payload):
    item_id = payload.get("item_id")
    if not item_id:
        return
    if payload.get("ok"):
        _mark_done(item_id, payload.get("confirmed") or "已确认")
    else:
        # 拨打失败：回到待审批，用户可重试
        db.update_prep_item(item_id, status="waiting",
                            result=payload.get("confirmed") or "拨打失败，可重试")
        bus().publish("prep.updated", {"item_id": item_id})


def _call_text(code, meeting):
    # 兼容旧调用：统一走话术中心
    return phrases.fill(code, meeting)


def _notify_text(meeting):
    parts = [f"会议通知：{meeting.get('title') or ''}"]
    if meeting.get("start_time"):
        parts.append(f"时间：{meeting['start_time']}")
    if meeting.get("room"):
        parts.append(f"地点：{meeting['room']}")
    parts.append("请准时参加。")
    return "\n".join(p for p in parts if p)


def _notify_target(meeting):
    return (meeting.get("notify_target") or "").strip() or \
        CONFIG.get("wechat", {}).get("notify_target", "") or "未指定"


def _prep_materials(item, meeting):
    """生成结构化汇报材料 → PPT + 文档 → 自动微信发文件给印刷方 → 电话安排印刷。"""
    infos = db.list_info_items(meeting.get("id")) or []
    texts = [i["content"] for i in infos[:50]]
    title = meeting.get("title") or "汇报材料"
    materials = generate_materials(title, texts)

    ppt = _make_ppt(title, materials)
    doc = _make_doc(title, materials)

    sent = False
    print_target = CONFIG.get("wechat", {}).get("print_target", "") or ""
    if print_target:
        sent = bool(actions.send_wechat_file(ppt, print_target))
        if not sent:
            sent = bool(actions.send_wechat_file(doc, print_target))

    actions.notify("汇报材料已生成",
                   f"PPT：{ppt}\n文档：{doc}\n已自动发送印刷：{'是' if sent else '否'}")

    text = phrases.fill("call_print", meeting,
                        {"file": str(ppt), "count": "1"})
    actions.call_phone(item["id"], "安排印刷", text, db.get_number("call_print"))


def _make_ppt(title, materials):
    """用结构化材料生成 PPT：封面 + 章节 + 总结。"""
    try:
        from pptx import Presentation
    except ImportError:
        return None
    import datetime
    prs = Presentation()
    cover = prs.slides.add_slide(prs.slide_layouts[0])
    cover.shapes.title.text = title
    if cover.placeholders[1]:
        cover.placeholders[1].text = materials.get("summary", "")

    for ch in (materials.get("chapters") or []):
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = ch.get("heading", "章节")
        body = slide.placeholders[1]
        tf = body.text_frame
        for i, p in enumerate((ch.get("points") or [])[:6]):
            if i == 0 and not tf.text:
                tf.text = p
            else:
                tf.add_paragraph().text = p

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = str(OUT_DIR / f"{stamp}_{actions.sanitize_filename(title)}.pptx")
    prs.save(path)
    return path


def _make_doc(title, materials):
    """生成汇报材料 markdown 文档。"""
    import datetime
    lines = [f"# {title}", "",
             f"**摘要**：{materials.get('summary', '')}", ""]
    for ch in (materials.get("chapters") or []):
        lines += [f"## {ch.get('heading', '')}"]
        lines += [f"- {p}" for p in (ch.get("points") or [])]
        lines.append("")
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = OUT_DIR / f"{stamp}_{actions.sanitize_filename(title)}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


def on_phone_timeout(payload):
    item_id = payload.get("item_id")
    if item_id:
        db.update_prep_item(item_id, status="waiting", result="手机未回传，已超时，可重试")
        bus().publish("prep.updated", {"item_id": item_id})


bus().subscribe("phone.result", on_phone_result)
bus().subscribe("phone.timeout", on_phone_timeout)
