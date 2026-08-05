from core.config import CONFIG

from collectors.base import Collector, register
from collectors import uia_common


class DingTalkCollector(Collector):
    """钉钉会话列表采集（UIA 只读）。"""

    source = "dingtalk"

    def is_enabled(self):
        return bool(CONFIG.get("collect", {}).get("dingtalk_enabled", False))

    def collect(self):
        auto = uia_common.get_uia()
        if auto is None:
            return []
        win = uia_common.find_window(auto, name_kw=("钉钉", "DingTalk"),
                                     class_kw=("DingTalk",))
        if win is None:
            return []
        texts = uia_common.collect_messages(
            win, "[钉钉]", max_items=30,
            skip=("钉钉", "DingTalk", "工作台", "通讯录"))
        return [{"source": self.source, "content": t, "meta": None}
                for t in texts]


register("dingtalk", DingTalkCollector())
