"""公共 UIA 采集层：窗口匹配 + 控件树遍历收集文本。"""


def get_uia():
    try:
        import uiautomation as auto
        return auto
    except Exception:
        return None


def find_window(auto, name_kw=(), class_kw=()):
    """按窗口标题/类名关键词匹配主窗口，只读查找不操作。"""
    root = auto.GetRootControl()
    for w in root.GetChildren():
        try:
            if not w.IsWindow:
                continue
            name = w.Name or ""
            cls = w.ClassName or ""
            if name_kw and not any(k in name for k in name_kw):
                continue
            if class_kw and not any(k in cls for k in class_kw):
                continue
            return w
        except Exception:
            continue
    return None


def collect_messages(win, tag, max_items=30, skip=(), depth_limit=6):
    """通用只读采集：遍历控件树收集有内容的文本项，返回带标签文本列表。"""
    out = []
    seen = set()

    def walk(ctrl, depth):
        if len(out) >= max_items or depth > depth_limit:
            return
        children = []
        try:
            children = ctrl.GetChildren()
        except Exception:
            return
        for c in children:
            try:
                name = (c.Name or "").strip()
            except Exception:
                name = ""
            if name and name not in seen and not any(k in name for k in skip):
                if "\n" in name or len(name) > 6:
                    seen.add(name)
                    out.append(f"{tag} {name}")
                    if len(out) >= max_items:
                        return
            walk(c, depth + 1)

    walk(win, 0)
    return out
