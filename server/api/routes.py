from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from automation import phrases, workflows
from collectors import submit_manual
from core import settings as settings_center
from storage import db

router = APIRouter(prefix="/api")


class MeetingIn(BaseModel):
    title: str = ...  # noqa
    start_time: str | None = None


class DoneIn(BaseModel):
    result: str = ""


class InfoIn(BaseModel):
    text: str
    meeting_id: int | None = None


class NumberIn(BaseModel):
    number: str = ""


@router.get("/meetings")
def list_meetings():
    return db.list_meetings()


@router.post("/meetings")
def create_meeting(payload: MeetingIn):
    if not payload.title.strip():
        raise HTTPException(400, "会议主题不能为空")
    t = payload.start_time
    if t:
        from datetime import datetime
        ok = False
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                datetime.strptime(t, fmt)
                ok = True
                break
            except ValueError:
                continue
        if not ok:
            raise HTTPException(400, "时间格式不正确，示例：2026-08-06 14:00")
    mid = workflows.setup_meeting(payload.title, payload.start_time)
    workflows.run_phase1(mid)
    return meeting_detail(mid)


@router.get("/meetings/{meeting_id}")
def meeting_detail(meeting_id: int):
    meeting = db.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(404, "会议不存在")
    items = db.list_prep_items(meeting_id)
    return {
        "meeting": meeting,
        "items": items,
        "phase1": [i for i in items if i["phase"] == 1],
        "phase2": [i for i in items if i["phase"] == 2],
    }


@router.post("/meetings/{meeting_id}/prep/{item_id}/done")
def prep_done(meeting_id: int, item_id: int, payload: DoneIn):
    workflows.mark_done(item_id, payload.result)
    return meeting_detail(meeting_id)


@router.post("/meetings/{meeting_id}/prep/{item_id}/approve")
def prep_approve(meeting_id: int, item_id: int):
    workflows.approve(item_id)
    return meeting_detail(meeting_id)


@router.post("/meetings/{meeting_id}/run-phase1")
def run_phase1(meeting_id: int):
    workflows.run_phase1(meeting_id)
    return meeting_detail(meeting_id)


@router.get("/info")
def list_info(meeting_id: int | None = None, source: str | None = None):
    return db.list_info_items(meeting_id=meeting_id, source=source)


@router.post("/info")
def add_info(payload: InfoIn):
    item_id = submit_manual(payload.text, meeting_id=payload.meeting_id)
    return {"id": item_id}


@router.get("/logs")
def logs():
    return db.list_action_logs()


@router.get("/phone-numbers")
def phone_numbers():
    return db.all_numbers()


@router.put("/phone-numbers/{code}")
def set_phone_number(code: str, payload: NumberIn):
    db.set_number(code, payload.number)
    return {"code": code, "number": payload.number}


@router.get("/settings")
def get_settings():
    return {"items": settings_center.items(),
            "values": settings_center.get_settings()}


@router.put("/settings")
def update_settings(payload: dict):
    return {"values": settings_center.update_settings(payload)}


class RoomIn(BaseModel):
    name: str
    note: str = ""


@router.get("/status")
def status():
    from core import status as st
    return {"status": st.service_status(), "logs": st.recent_logs()}


@router.get("/rooms")
def list_rooms():
    return db.list_rooms()


@router.post("/rooms")
def add_room(payload: RoomIn):
    if not payload.name.strip():
        raise HTTPException(400, "会议室名称不能为空")
    return {"id": db.add_room(payload.name, payload.note)}


@router.delete("/rooms/{room_id}")
def remove_room(room_id: int):
    db.remove_room(room_id)
    return {"ok": True}


class TemplateIn(BaseModel):
    template: str
    use_ai: bool = False


@router.get("/templates")
def list_templates():
    out = []
    for code, label in phrases.TEMPLATE_CODES:
        t = db.get_template(code) or {}
        out.append({"code": code, "label": label,
                    "template": t.get("template", phrases.DEFAULT_TEMPLATES.get(code, "")),
                    "use_ai": bool(t.get("use_ai", 0))})
    return out


@router.put("/templates/{code}")
def set_template(code: str, payload: TemplateIn):
    db.set_template(code, payload.template, payload.use_ai)
    return {"ok": True}


class MeetingUpdate(BaseModel):
    title: str = ""
    start_time: str = ""
    room: str = ""
    location: str = ""
    attendees: str = ""


@router.put("/meetings/{meeting_id}")
def update_meeting(meeting_id: int, payload: MeetingUpdate):
    fields = {k: v for k, v in payload.model_dump().items() if v is not None}
    if fields:
        db.update_meeting(meeting_id, **fields)
    return meeting_detail(meeting_id)


@router.post("/meetings/{meeting_id}/set-room")
def set_room(meeting_id: int, payload: RoomIn):
    workflows.set_room(meeting_id, payload.name)
    return meeting_detail(meeting_id)


class AttendeesIn(BaseModel):
    attendees: str
    source: str = "manual"


@router.post("/meetings/{meeting_id}/set-attendees")
def set_attendees(meeting_id: int, payload: AttendeesIn):
    workflows.set_attendees(meeting_id, payload.attendees, payload.source)
    return meeting_detail(meeting_id)


@router.get("/meetings/{meeting_id}/room-candidates")
def room_candidates(meeting_id: int):
    return {"candidates": workflows.candidates_for_room(meeting_id)}


class TaskIn(BaseModel):
    title: str
    detail: str = ""
    due_date: str = ""


@router.get("/tasks")
def list_tasks(status: str | None = None):
    return db.list_tasks(status=status)


@router.post("/tasks")
def add_task(payload: TaskIn):
    if not payload.title.strip():
        raise HTTPException(400, "任务标题不能为空")
    from core.dates import normalize_due
    due = normalize_due(payload.due_date)
    if payload.due_date and due is None:
        raise HTTPException(400, "截止日期格式不正确，示例：2026-08-10 或 8月10日")
    return {"id": db.add_task_unique(payload.title.strip(), payload.detail,
                                     due, source="manual")[0]}


@router.post("/tasks/{task_id}/done")
def task_done(task_id: int):
    db.update_task(task_id, status=db.TASK_DONE)
    return {"ok": True}


@router.post("/tasks/{task_id}/dismiss")
def task_dismiss(task_id: int):
    db.update_task(task_id, status=db.TASK_DISMISSED)
    return {"ok": True}


@router.post("/tasks/{task_id}/reactivate")
def task_reactivate(task_id: int):
    db.update_task(task_id, status=db.TASK_ACTIVE)
    return {"ok": True}
