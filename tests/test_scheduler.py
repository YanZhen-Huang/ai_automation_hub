"""core.scheduler 单元测试：周期/定点任务调度。"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.scheduler import Scheduler


def test_interval_fires():
    calls = []
    s = Scheduler()
    s.every(0.1, lambda: calls.append(1))
    s.start()
    time.sleep(0.35)
    s.stop()
    assert len(calls) >= 2


def test_interval_respects_interval():
    calls = []
    s = Scheduler()
    s.every(0.2, lambda: calls.append(1))
    s.start()
    time.sleep(0.1)
    s.stop()
    assert len(calls) == 0


def test_run_interval_first_call_schedules_only():
    job = {"kind": "interval", "interval": 5.0, "fn": lambda: calls.append(1)}
    calls = []
    Scheduler._run_interval(job)
    assert calls == []
    assert job["next"] is not None


def test_run_interval_fires_when_due():
    calls = []
    job = {"kind": "interval", "interval": 10.0, "fn": lambda: calls.append(1)}
    Scheduler._run_interval(job)
    assert calls == []  # 首次只排期
    job["next"] = 0  # 强制立即到期
    Scheduler._run_interval(job)
    assert calls == [1]


def test_no_jobs_runs_quietly():
    s = Scheduler()
    s.start()
    time.sleep(0.05)
    s.stop()
    assert True


def test_start_idempotent():
    calls = []
    s = Scheduler()
    s.every(0.05, lambda: calls.append(1))
    s.start()
    s.start()
    time.sleep(0.15)
    s.stop()
    assert len(calls) >= 1


def test_stop_without_start():
    s = Scheduler()
    s.stop()
    assert True
