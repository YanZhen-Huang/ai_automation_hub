"""信息提炼：把采集到的文本提炼为会议准备相关信息。
有 LLM Key 用 AI，否则用关键词规则降级。
"""

import json
import re

from ai import llm
from core.logger import get_logger

log = get_logger("extract")

SYSTEM_PROMPT = """你是会议准备助手。用户会提供一批收集到的信息（聊天消息、录音转写、手动录入等）。
请判断这些信息是否与本公司的会议准备相关，并提炼出有用内容。

输出 JSON，字段：
- is_meeting_related: bool，是否包含会议准备相关信息
- summary: 一句话总结（<=40字）
- points: 数组，每条为会议相关的要点/需准备事项（简洁，每条<=30字）
- prep_reminders: 数组，明确需要准备的资源类事项（如会议室、茶水、音响、材料印刷、桌牌、通知等），无则空数组

只输出 JSON，不要其他内容。"""

KEYWORDS = ["会议", "开会", "汇报", "会议室", "茶水", "音响", "投影", "材料", "PPT",
            "印刷", "桌牌", "签字", "通知", "议程", "纪要", "接待", "周会", "例会"]


def _rule_extract(texts):
    joined = "\n".join(texts)
    hit = sum(1 for kw in KEYWORDS if kw in joined)
    related = hit > 0
    points = []
    for kw in KEYWORDS:
        for line in joined.splitlines():
            if kw in line and line.strip() and len(line) < 60:
                if line.strip() not in points:
                    points.append(line.strip())
                break
    return {
        "is_meeting_related": related,
        "summary": "检测到会议相关关键词" if related else "未发现会议相关信息",
        "points": points[:10],
        "prep_reminders": [],
    }


def extract(texts):
    if not texts:
        return {"is_meeting_related": False, "summary": "无内容",
                "points": [], "prep_reminders": []}
    if not llm.available():
        return _rule_extract(texts)
    try:
        resp = llm.chat([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(texts, ensure_ascii=False)},
        ], temperature=0.1)
        m = re.search(r"\{.*\}", resp, re.S)
        data = json.loads(m.group(0)) if m else {}
        return {
            "is_meeting_related": bool(data.get("is_meeting_related")),
            "summary": str(data.get("summary", ""))[:40],
            "points": [str(p)[:30] for p in (data.get("points") or [])],
            "prep_reminders": [str(p)[:30] for p in (data.get("prep_reminders") or [])],
        }
    except Exception:
        log.exception("AI 提炼失败，降级规则")
        return _rule_extract(texts)


# ── 会议室 / 与会人员 / 材料生成 ──

ROOM_RE = re.compile(
    r"([0-9]+[Ff][\d\-]*[\u4e00-\u9fff]{0,3}|"
    r"[\u4e00-\u9fff]{1,3}号楼[\d\-]*|"
    r"[A-Za-z0-9\u4e00-\u9fff]{2,8}会议室)")
UNAVAIL_WORDS = ["不可用", "维修", "不能用", "没空", "被占", "停用", "订满",
                 "没有", "装修", "关闭", "取消"]


def _rule_unavailable_rooms(texts):
    rooms = []
    for line in (texts or []):
        for m in ROOM_RE.finditer(line):
            room = m.group(0).strip()
            if not room:
                continue
            window = line[m.end():m.end() + 18]
            if any(w in window for w in UNAVAIL_WORDS) and room not in rooms:
                rooms.append(room)
    return rooms


def extract_rooms(texts):
    """从信息中提炼"不可用"的会议室列表。"""
    if not texts:
        return []
    if not llm.available():
        return _rule_unavailable_rooms(texts)
    try:
        prompt = ("从以下信息中找出被标记为不可用/维修/被占/取消的会议室名称。"
                  "输出 JSON 数组，无则 []。\n" + json.dumps(texts, ensure_ascii=False))
        resp = llm.chat([{"role": "system", "content": "只输出 JSON 数组"},
                         {"role": "user", "content": prompt}], temperature=0)
        m = re.search(r"\[.*\]", resp, re.S)
        data = json.loads(m.group(0)) if m else []
        return [str(x).strip() for x in data if x][:20]
    except Exception:
        log.exception("AI 会议室提炼失败，降级")
        return _rule_unavailable_rooms(texts)


def extract_attendees(texts):
    """从信息中提炼与会人员候选名单。无 Key 或无信息返回空（走人工录入）。"""
    if not texts or not llm.available():
        return []
    try:
        prompt = ("从以下信息中提取需要参会/出席的人员姓名列表。"
                  "输出 JSON 字符串数组，无法确定则 []。\n"
                  + json.dumps(texts, ensure_ascii=False))
        resp = llm.chat([{"role": "system", "content": "只输出 JSON 数组"},
                         {"role": "user", "content": prompt}], temperature=0)
        m = re.search(r"\[.*\]", resp, re.S)
        data = json.loads(m.group(0)) if m else []
        return [str(x).strip() for x in data if x][:50]
    except Exception:
        log.exception("AI 与会人员提炼失败")
        return []


MATERIAL_PROMPT = """你是一位会议材料撰写专家。根据收集到的信息，为会议《{title}》撰写汇报材料。
输出 JSON：
{{"summary": "一句话摘要", "chapters": [{{"heading": "章节标题", "points": ["要点1", "要点2"]}}]}}
要求：2-4 个章节，每章 2-5 个要点，基于信息内容，不得编造。"""


def generate_materials(title, texts):
    """生成结构化汇报材料 {summary, chapters:[{heading, points}]}。"""
    if not texts:
        return {"summary": "无信息", "chapters": []}
    if llm.available():
        try:
            resp = llm.chat([
                {"role": "system", "content": "只输出 JSON"},
                {"role": "user", "content": MATERIAL_PROMPT.format(title=title)
                 + "\n\n信息：\n" + json.dumps(texts, ensure_ascii=False)},
            ], temperature=0.3, max_tokens=2000)
            m = re.search(r"\{.*\}", resp, re.S)
            data = json.loads(m.group(0)) if m else {}
            return {
                "summary": str(data.get("summary", ""))[:80],
                "chapters": data.get("chapters") or [],
            }
        except Exception:
            log.exception("AI 材料生成失败，降级")
    res = _rule_extract(texts)
    return {"summary": res.get("summary", ""),
            "chapters": [{"heading": "要点", "points": res.get("points", [])}]}
