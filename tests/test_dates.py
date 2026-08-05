"""core.dates 单元测试：日期解析与规范化。"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.dates import normalize_due, parse_date

FMT = "%Y-%m-%d"


@pytest.fixture
def today():
    return datetime.now()


def test_empty_and_none():
    assert parse_date(None) is None
    assert parse_date("") is None
    assert parse_date("   ") is None
    assert normalize_due(None) is None
    assert normalize_due("") is None


def test_relative_days(today):
    assert parse_date("今天") == today.strftime(FMT)
    assert parse_date("明天") == (today + timedelta(days=1)).strftime(FMT)
    assert parse_date("后天") == (today + timedelta(days=2)).strftime(FMT)


def test_weekday_this_week(today):
    target = 0
    diff = (target - today.weekday()) % 7
    if diff == 0:
        diff = 7
    assert parse_date("周一") == (today + timedelta(days=diff)).strftime(FMT)


def test_weekday_variants(today):
    for name in ("星期一", "周二", "周日", "星期天"):
        target = {"星期一": 0, "周二": 1, "周日": 6, "星期天": 6}[name]
        diff = (target - today.weekday()) % 7
        if diff == 0:
            diff = 7
        assert parse_date(name) == (today + timedelta(days=diff)).strftime(FMT)


def test_next_weekday(today):
    for name, target in (("下周一", 0), ("下周三", 2), ("下周日", 6)):
        diff = (target - today.weekday()) % 7
        if diff == 0:
            diff = 7
        assert parse_date(name) == (today + timedelta(days=diff)).strftime(FMT)


def test_prev_weekday(today):
    for name, target in (("上周一", 0), ("上周五", 4), ("上星期日", 6)):
        diff = today.weekday() - target + 7
        assert parse_date(name) == (today - timedelta(days=diff)).strftime(FMT)


def test_full_date_variants():
    assert parse_date("2025年3月5日") == "2025-03-05"
    assert parse_date("2025-03-05") == "2025-03-05"
    assert parse_date("2025/12/31") == "2025-12-31"
    assert parse_date("2025.1.9") == "2025-01-09"


def test_month_day_no_year(today):
    assert parse_date("3月5日") == f"{today.year:04d}-03-05"
    assert parse_date("12-31") == f"{today.year:04d}-12-31"


def test_unparseable():
    assert parse_date("下个月") is None
    assert parse_date("尽快") is None
    assert parse_date("abc") is None
    assert parse_date("2025-13-99") is None


def test_normalize_due_strips_whitespace():
    assert normalize_due("  今天  ") == parse_date("今天")
