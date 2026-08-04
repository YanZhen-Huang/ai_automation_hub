from core.config import CONFIG
from core.logger import get_logger

log = get_logger("collectors")


class Collector:
    """采集源基类。collect() 返回 list[dict{source, content, meta}]。"""

    source = "base"
    config_key = None

    def is_enabled(self) -> bool:
        if not self.config_key:
            return True
        return bool(CONFIG.get(self.config_key, {}).get("enabled", False))

    def collect(self):
        raise NotImplementedError


_REGISTRY = {}


def register(name, collector):
    _REGISTRY[name] = collector


def collect_all():
    """采集所有已启用来源，单个来源异常不影响其他。"""
    out = []
    for name, c in _REGISTRY.items():
        try:
            if not c.is_enabled():
                continue
            out.extend(c.collect() or [])
        except Exception:
            log.exception("来源 %s 采集失败", name)
    return out


def get_registry():
    return dict(_REGISTRY)
