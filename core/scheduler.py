import threading
import time
from collections.abc import Callable

from core.logger import get_logger

log = get_logger("scheduler")


class Scheduler:
    """单线程调度器：周期任务 + 定点任务。"""

    def __init__(self):
        self._jobs = []
        self._stop = threading.Event()
        self._thread = None

    def every(self, seconds: float, fn: Callable):
        self._jobs.append({"kind": "interval", "interval": seconds, "fn": fn})
        return self

    def at(self, hhmm: str, fn: Callable):
        self._jobs.append({"kind": "daily", "time": hhmm, "fn": fn,
                           "last": None})
        return self

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def _run(self):
        while not self._stop.is_set():
            hhmm = time.strftime("%H:%M", time.localtime())
            min_wait = 30
            for j in self._jobs:
                try:
                    if j["kind"] == "interval":
                        self._run_interval(j)
                        min_wait = min(min_wait, float(j.get("interval", 30)))
                    elif j["kind"] == "daily" and j["time"] == hhmm:
                        if j["last"] != hhmm:
                            j["last"] = hhmm
                            j["fn"]()
                except Exception:
                    log.exception("调度任务异常: %r", j)
            self._stop.wait(max(0.1, min_wait))

    @staticmethod
    def _run_interval(job):
        fn = job.get("fn")
        if not fn:
            return
        now = time.monotonic()
        if job.get("next") is None:
            job["next"] = now + job["interval"]
        if now >= job["next"]:
            job["next"] = now + job["interval"]
            fn()


_scheduler = Scheduler()


def scheduler() -> Scheduler:
    return _scheduler
