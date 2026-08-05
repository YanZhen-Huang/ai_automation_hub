import json
import sqlite3
from datetime import datetime

from core.config import DATA_DIR

DB_PATH = DATA_DIR / "meeting_prep.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS info_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    content TEXT NOT NULL,
    meeting_id INTEGER,
    meta TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS meetings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    start_time TEXT,
    status TEXT DEFAULT 'preparing',
    room TEXT DEFAULT '',
    location TEXT DEFAULT '',
    attendees TEXT DEFAULT '',
    attendee_source TEXT DEFAULT '',
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    note TEXT DEFAULT '',
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS phrase_templates (
    code TEXT PRIMARY KEY,
    template TEXT NOT NULL,
    use_ai INTEGER DEFAULT 0,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS prep_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id INTEGER NOT NULL,
    phase INTEGER NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    detail TEXT DEFAULT '',
    result TEXT DEFAULT '',
    order_index INTEGER DEFAULT 0,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS action_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER,
    action TEXT,
    status TEXT,
    message TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS phone_numbers (
    code TEXT PRIMARY KEY,
    number TEXT NOT NULL DEFAULT '',
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    detail TEXT DEFAULT '',
    due_date TEXT,
    source TEXT DEFAULT 'ai',
    status TEXT DEFAULT 'active',
    info_id INTEGER,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS meeting_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    path TEXT NOT NULL,
    ftype TEXT DEFAULT 'pptx',
    sent INTEGER DEFAULT 0,
    created_at TEXT
);
"""


def _now():
    return datetime.now().isoformat(timespec="seconds")


def get_conn():
    conn = sqlite3.connect(str(DB_PATH), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=8000")
    return conn


def init_db():
    conn = get_conn()
    try:
        conn.executescript(_SCHEMA)
        _ensure_columns(conn)
        conn.commit()
    finally:
        conn.close()


def _ensure_columns(conn):
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(meetings)").fetchall()}
    for col in ("room", "location", "attendees", "attendee_source",
                "auto_materials", "materials"):
        if col not in cols:
            if col in ("auto_materials",):
                conn.execute(f"ALTER TABLE meetings ADD COLUMN {col} INTEGER DEFAULT 1")
            else:
                conn.execute(f"ALTER TABLE meetings ADD COLUMN {col} TEXT DEFAULT ''")


# ---------- 信息库 ----------

def add_info_item(source, content, meeting_id=None, meta=None):
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO info_items (source, content, meeting_id, meta, created_at) "
            "VALUES (?,?,?,?,?)",
            (source, content, meeting_id,
             json.dumps(meta, ensure_ascii=False) if meta else None, _now()))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_info_items(meeting_id=None, source=None, limit=200):
    conn = get_conn()
    try:
        sql = "SELECT * FROM info_items"
        conds, args = [], []
        if meeting_id is not None:
            conds.append("meeting_id = ?")
            args.append(meeting_id)
        if source:
            conds.append("source = ?")
            args.append(source)
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        rows = conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def set_info_meeting(item_id, meeting_id):
    conn = get_conn()
    try:
        conn.execute("UPDATE info_items SET meeting_id = ? WHERE id = ?",
                     (meeting_id, item_id))
        conn.commit()
    finally:
        conn.close()


# ---------- 会议库 ----------

def create_meeting(title, start_time=None):
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO meetings (title, start_time, status, created_at) "
            "VALUES (?,?,?,?)",
            (title, start_time, "preparing", _now()))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_meetings(limit=100):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM meetings ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_meeting(meeting_id):
    conn = get_conn()
    try:
        r = conn.execute("SELECT * FROM meetings WHERE id = ?",
                         (meeting_id,)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def update_meeting(meeting_id, **fields):
    allowed = {"title", "start_time", "status", "room", "location",
               "attendees", "attendee_source", "auto_materials", "materials"}
    upd = {k: v for k, v in fields.items() if k in allowed}
    if not upd:
        return
    conn = get_conn()
    try:
        sql = "UPDATE meetings SET " + ", ".join(f"{k} = ?" for k in upd) + " WHERE id = ?"
        conn.execute(sql, list(upd.values()) + [meeting_id])
        conn.commit()
    finally:
        conn.close()


# ---------- 会议准备动作项 ----------

def add_prep_items(meeting_id, items):
    """items: list of dict(phase, code, name, order_index, detail). 批量事务。"""
    conn = get_conn()
    try:
        with conn:
            for it in items:
                conn.execute(
                    "INSERT INTO prep_items (meeting_id, phase, code, name, detail, "
                    "order_index, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                    (meeting_id, it["phase"], it["code"], it["name"],
                     it.get("detail", ""), it.get("order_index", 0), _now(), _now()))
    finally:
        conn.close()


def list_prep_items(meeting_id):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM prep_items WHERE meeting_id = ? ORDER BY phase, order_index",
            (meeting_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_prep_item(item_id):
    conn = get_conn()
    try:
        r = conn.execute("SELECT * FROM prep_items WHERE id = ?",
                         (item_id,)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def update_prep_item(item_id, status=None, result=None):
    conn = get_conn()
    try:
        sets, args = ["updated_at = ?"], [_now()]
        if status is not None:
            sets.append("status = ?")
            args.append(status)
        if result is not None:
            sets.append("result = ?")
            args.append(result)
        args.append(item_id)
        conn.execute(f"UPDATE prep_items SET {', '.join(sets)} WHERE id = ?", args)
        conn.commit()
    finally:
        conn.close()


# ---------- 动作日志 ----------

def add_action_log(item_id, action, status, message=""):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO action_logs (item_id, action, status, message, created_at) "
            "VALUES (?,?,?,?,?)",
            (item_id, action, status, message, _now()))
        conn.commit()
    finally:
        conn.close()


def list_action_logs(limit=200):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM action_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------- 电话号码配置 ----------

def get_number(code):
    conn = get_conn()
    try:
        r = conn.execute("SELECT number FROM phone_numbers WHERE code = ?",
                         (code,)).fetchone()
        return r["number"] if r else ""
    finally:
        conn.close()


def set_number(code, number):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO phone_numbers (code, number, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(code) DO UPDATE SET number = excluded.number, "
            "updated_at = excluded.updated_at",
            (code, number.strip(), _now()))
        conn.commit()
    finally:
        conn.close()


def all_numbers():
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM phone_numbers ORDER BY code").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------- 会议室库 ----------

def add_room(name, note=""):
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO rooms (name, status, note, created_at) VALUES (?,?,?,?)",
            (name.strip(), "active", note, _now()))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_rooms():
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM rooms ORDER BY id").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def remove_room(room_id):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM rooms WHERE id = ?", (room_id,))
        conn.commit()
    finally:
        conn.close()


# ---------- 话术模板 ----------

def get_template(code):
    conn = get_conn()
    try:
        r = conn.execute("SELECT * FROM phrase_templates WHERE code = ?",
                         (code,)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def set_template(code, template, use_ai=False):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO phrase_templates (code, template, use_ai, updated_at) "
            "VALUES (?,?,?,?) ON CONFLICT(code) DO UPDATE SET "
            "template=excluded.template, use_ai=excluded.use_ai, "
            "updated_at=excluded.updated_at",
            (code, template, 1 if use_ai else 0, _now()))
        conn.commit()
    finally:
        conn.close()


def all_templates():
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM phrase_templates ORDER BY code").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------- 待办任务 ----------

TASK_ACTIVE, TASK_DISMISSED, TASK_DONE = "active", "dismissed", "done"


def add_task(title, detail="", due_date=None, source="ai", info_id=None):
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO tasks (title, detail, due_date, source, status, info_id, "
            "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (title, detail, due_date, source, TASK_ACTIVE, info_id, _now(), _now()))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def add_task_unique(title, detail="", due_date=None, source="ai", info_id=None):
    """去重入库：未完成的同标题+截止任务跳过。返回 (id, is_new)。"""
    conn = get_conn()
    try:
        r = conn.execute(
            "SELECT id FROM tasks WHERE status != 'done' AND title = ? AND "
            "IFNULL(due_date,'') = IFNULL(?,'') LIMIT 1",
            (title, due_date)).fetchone()
        if r:
            return r["id"], False
        cur = conn.execute(
            "INSERT INTO tasks (title, detail, due_date, source, status, info_id, "
            "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (title, detail, due_date, source, TASK_ACTIVE, info_id, _now(), _now()))
        conn.commit()
        return cur.lastrowid, True
    finally:
        conn.close()


def list_tasks(status=None, limit=200):
    conn = get_conn()
    try:
        sql = "SELECT * FROM tasks"
        args = []
        if status:
            sql += " WHERE status = ?"
            args.append(status)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        rows = conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_task(task_id):
    conn = get_conn()
    try:
        r = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def update_task(task_id, status=None, due_date=None):
    conn = get_conn()
    try:
        sets, args = ["updated_at = ?"], [_now()]
        if status is not None:
            sets.append("status = ?")
            args.append(status)
        if due_date is not None:
            sets.append("due_date = ?")
            args.append(due_date)
        args.append(task_id)
        conn.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", args)
        conn.commit()
    finally:
        conn.close()


def remove_task(task_id):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
    finally:
        conn.close()


def due_tasks():
    """未完成且到期的任务（用于实况窗提醒）。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE status != 'done' AND due_date IS NOT NULL "
            "AND due_date != ''").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------- 会议材料与文件 ----------

def add_meeting_file(meeting_id, name, path, ftype):
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO meeting_files (meeting_id, name, path, ftype, sent, created_at) "
            "VALUES (?,?,?,?,0,?)",
            (meeting_id, name, path, ftype, _now()))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_meeting_files(meeting_id):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM meeting_files WHERE meeting_id = ? ORDER BY id",
            (meeting_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_meeting_file(file_id):
    conn = get_conn()
    try:
        r = conn.execute("SELECT * FROM meeting_files WHERE id = ?",
                         (file_id,)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def update_file_sent(file_id, sent=1):
    conn = get_conn()
    try:
        conn.execute("UPDATE meeting_files SET sent = ? WHERE id = ?",
                     (sent, file_id))
        conn.commit()
    finally:
        conn.close()


init_db()
