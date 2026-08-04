import threading
from collections import defaultdict
from collections.abc import Callable


class EventBus:
    """线程安全事件总线：模块间解耦通信。主题为字符串。"""

    def __init__(self):
        self._subs: dict[str, list[Callable]] = defaultdict(list)
        self._lock = threading.RLock()

    def subscribe(self, topic: str, handler: Callable):
        with self._lock:
            if handler not in self._subs[topic]:
                self._subs[topic].append(handler)

    def unsubscribe(self, topic: str, handler: Callable):
        with self._lock:
            if handler in self._subs[topic]:
                self._subs[topic].remove(handler)

    def publish(self, topic: str, payload=None):
        with self._lock:
            handlers = list(self._subs.get(topic, []))
        for h in handlers:
            try:
                h(payload)
            except Exception:
                import traceback
                traceback.print_exc()

    def clear(self):
        with self._lock:
            self._subs.clear()


# 全局单例
_bus = EventBus()


def bus() -> EventBus:
    return _bus
