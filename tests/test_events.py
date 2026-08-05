"""core.events 单元测试：线程安全事件总线。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.events import EventBus


def test_subscribe_and_publish():
    bus = EventBus()
    got = []
    bus.subscribe("t", lambda p: got.append(p))
    bus.publish("t", "hello")
    assert got == ["hello"]


def test_publish_no_subscriber():
    bus = EventBus()
    bus.publish("missing")
    assert True


def test_unsubscribe():
    bus = EventBus()
    got = []
    h = lambda p: got.append(p)
    bus.subscribe("t", h)
    bus.unsubscribe("t", h)
    bus.publish("t", 1)
    assert got == []


def test_no_duplicate_subscribe():
    bus = EventBus()
    got = []
    h = lambda p: got.append(p)
    bus.subscribe("t", h)
    bus.subscribe("t", h)
    bus.publish("t", 1)
    assert got == [1]


def test_topics_isolated():
    bus = EventBus()
    a, b = [], []
    bus.subscribe("a", lambda p: a.append(p))
    bus.subscribe("b", lambda p: b.append(p))
    bus.publish("a", 1)
    bus.publish("b", 2)
    assert a == [1]
    assert b == [2]


def test_handler_exception_does_not_break_others(capsys):
    bus = EventBus()
    got = []

    def bad(p):
        raise RuntimeError("boom")

    bus.subscribe("t", bad)
    bus.subscribe("t", lambda p: got.append(p))
    bus.publish("t", 1)
    assert got == [1]
    assert "boom" in capsys.readouterr().err


def test_clear():
    bus = EventBus()
    got = []
    bus.subscribe("t", lambda p: got.append(p))
    bus.clear()
    bus.publish("t", 1)
    assert got == []
