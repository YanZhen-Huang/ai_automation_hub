"""日期解析与规范化：把中文/数字日期统一为 YYYY-MM-DD。"""

import re
from datetime import datetime, timedelta


def parse_date(raw):
    """解析日期文本 → YYYY-MM-DD，无法解析返回 None。"""
    if not raw:
        return None
    s = str(raw).strip()
    now = datetime.now()
    if s == "今天":
        return now.strftime("%Y-%m-%d")
    if s == "明天":
        return (now + timedelta(days=1)).strftime("%Y-%m-%d")
    if s == "后天":
        return (now + timedelta(days=2)).strftime("%Y-%m-%d")

    weekdays = {"周一": 0, "周二": 1, "周三": 2, "周四": 3, "周五": 4, "周六": 5, "周日": 6,
                "星期一": 0, "星期二": 1, "星期三": 2, "星期四": 3, "星期五": 4,
                "星期六": 5, "星期日": 6, "星期天": 6}
    for name, target in weekdays.items():
        if name in s:
            diff = (target - now.weekday()) % 7
            if diff == 0:
                diff = 7
            return (now + timedelta(days=diff)).strftime("%Y-%m-%d")

    m = re.search(r"(\d{4})[年\-/\.](\d{1,2})[月\-/\.](\d{1,2})", s)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"(\d{1,2})[月\-/\.](\d{1,2})", s)
    if m:
        return f"{now.year:04d}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return None


def normalize_due(raw):
    """规范化截止日期；非法/空返回 None。"""
    if not raw:
        return None
    s = str(raw).strip()
    return parse_date(s) if s else None
