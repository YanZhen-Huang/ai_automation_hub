from collectors.base import Collector, log, register


class WeChatCollector(Collector):
    """微信会话列表采集（UIA 只读，不点击、不修改）。"""

    source = "wechat"
    config_key = "collect"

    def is_enabled(self):
        return bool(CONFIG.get("collect", {}).get("wechat_enabled", False))

    def collect(self):
        auto = self._get_uia()
        if auto is None:
            return []
        win = self._find_window(auto)
        if win is None:
            return []
        return self._collect_messages(win)

    @staticmethod
    def _get_uia():
        try:
            import uiautomation as auto
            return auto
        except Exception:
            return None

    @staticmethod
    def _find_window(auto):
        root = auto.GetRootControl()
        for w in root.GetChildren():
            try:
                if not w.IsWindow:
                    continue
                name = w.Name or ""
                cls = w.ClassName or ""
                if ("微信" in name) or ("WeChat" in cls):
                    return w
            except Exception:
                continue
        return None

    @staticmethod
    def _collect_messages(win, max_items=30):
        out = []
        seen = set()

        def walk(ctrl, depth):
            if len(out) >= max_items or depth > 6:
                return
            try:
                children = ctrl.GetChildren()
            except Exception:
                return
            for c in children:
                try:
                    name = (c.Name or "").strip()
                except Exception:
                    name = ""
                if name and name not in seen:
                    if "\n" in name or len(name) > 6:
                        seen.add(name)
                        out.append({"source": "wechat",
                                    "content": f"[微信] {name}",
                                    "meta": None})
                        if len(out) >= max_items:
                            return
                walk(c, depth + 1)

        walk(win, 0)
        return out


register("wechat", WeChatCollector())
