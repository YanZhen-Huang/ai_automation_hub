"""OCR 采集：截取屏幕指定区域并识别文字（用于钉钉等无法 UIA 的界面）。
引擎：rapidocr(onnxruntime，默认) / tesseract(需安装)。
注意：由 main.py 独立调度，不注册进 collect_all。"""

from core.config import CONFIG
from collectors.base import Collector, log

_ocr = None


def _parse_region(region_str):
    try:
        parts = [int(p) for p in str(region_str).replace("，", ",").split(",")]
        if len(parts) != 4:
            return None
        left, top, width, height = parts
        return left, top, width, height
    except Exception:
        return None


def _get_rapidocr():
    global _ocr
    if _ocr is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _ocr = RapidOCR()
            log.info("RapidOCR 已加载")
        except Exception:
            log.warning("rapidocr 不可用")
            _ocr = False
    return _ocr if _ocr else None


def ocr_region(bbox):
    """识别 (left, top, width, height) 区域内的文字，返回文本行列表。"""
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab(bbox=bbox)
    except Exception:
        log.exception("截图失败")
        return []

    engine = CONFIG.get("ocr", {}).get("engine", "rapidocr")
    if engine == "rapidocr":
        model = _get_rapidocr()
        if model is None:
            return []
        import os
        import tempfile
        path = tempfile.mktemp(suffix=".png")
        try:
            img.save(path)
            result = model(path)
            lines = [r[1] for r in result[0]] if result and result[0] else []
            out = []
            for ln in lines:
                ln = (ln or "").strip()
                if ln and len(ln) >= 2:
                    out.append(ln[:60])
            return out[:30]
        except Exception:
            log.exception("RapidOCR 识别失败")
            return []
        finally:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
    return []


class OCRCollector(Collector):
    source = "ocr"
    config_key = "collect"

    def is_enabled(self):
        return bool(CONFIG.get("collect", {}).get("ocr_enabled", False))

    def collect(self):
        region = _parse_region(CONFIG.get("ocr", {}).get("region", "0,0,800,600"))
        if region is None:
            return []
        lines = ocr_region(region)
        if not lines:
            return []
        text = "，".join(l.strip() for l in lines if l.strip())
        if not text:
            return []
        return [{"source": "ocr", "content": f"[OCR] {text}", "meta": None}]
