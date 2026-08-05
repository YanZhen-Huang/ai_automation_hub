from core.config import CONFIG

from collectors.base import Collector, register
from collectors import uia_common


class OneNoteCollector(Collector):
    """OneNote 最近页面列表采集（UIA 只读）。"""

    source = "onenote"

    def is_enabled(self):
        return bool(CONFIG.get("collect", {}).get("onenote_enabled", False))

    def collect(self):
        auto = uia_common.get_uia()
        if auto is None:
            return []
        win = uia_common.find_window(auto, name_kw=("OneNote",),
                                     class_kw=("OneNote", "framework::CFrame"))
        if win is None:
            return []
        texts = uia_common.collect_messages(
            win, "[OneNote]", max_items=20,
            skip=("OneNote", "主页", "插入", "绘图"))
        return [{"source": self.source, "content": t, "meta": None}
                for t in texts]


register("onenote", OneNoteCollector())
