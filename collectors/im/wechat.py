from core.config import CONFIG

from collectors.base import Collector, register
from collectors import uia_common


class WeChatCollector(Collector):
    """微信会话列表采集（UIA 只读，不点击、不修改）。"""

    source = "wechat"

    def is_enabled(self):
        return bool(CONFIG.get("collect", {}).get("wechat_enabled", False))

    def collect(self):
        auto = uia_common.get_uia()
        if auto is None:
            return []
        win = uia_common.find_window(auto, name_kw=("微信",),
                                     class_kw=("WeChat",))
        if win is None:
            return []
        texts = uia_common.collect_messages(
            win, "[微信]", max_items=30,
            skip=("微信", "搜一搜", "看一看"))
        return [{"source": self.source, "content": t, "meta": None}
                for t in texts]


register("wechat", WeChatCollector())
