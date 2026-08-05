from core.config import CONFIG

from collectors.base import Collector, register
from collectors import uia_common


class FeishuCollector(Collector):
    """飞书会话列表采集（UIA 只读）。"""

    source = "feishu"

    def is_enabled(self):
        return bool(CONFIG.get("collect", {}).get("feishu_enabled", False))

    def collect(self):
        auto = uia_common.get_uia()
        if auto is None:
            return []
        win = uia_common.find_window(auto, name_kw=("飞书", "Feishu", "Lark"),
                                     class_kw=("Feishu", "Lark", "FTWin"))
        if win is None:
            return []
        texts = uia_common.collect_messages(
            win, "[飞书]", max_items=30,
            skip=("飞书", "Feishu", "Lark", "搜索"))
        return [{"source": self.source, "content": t, "meta": None}
                for t in texts]


register("feishu", FeishuCollector())
