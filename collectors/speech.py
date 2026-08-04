"""本地录音转文字：faster-whisper 可选加载。未安装时返回 None。"""

from core.config import CONFIG
from core.logger import get_logger
from storage import db

log = get_logger("speech")

_model = None
_model_loaded = False


def _get_model():
    global _model, _model_loaded
    if _model_loaded:
        return _model
    _model_loaded = True
    try:
        from faster_whisper import WhisperModel
        _model = WhisperModel(CONFIG["speech"]["whisper_model"],
                              device=CONFIG["speech"]["device"])
        log.info("Whisper 模型已加载: %s", CONFIG["speech"]["whisper_model"])
    except Exception:
        log.warning("faster-whisper 不可用，录音转文字功能关闭")
        _model = None
    return _model


def transcribe_audio(path):
    """转写音频文件为文本。失败返回 None。"""
    model = _get_model()
    if model is None:
        return None
    try:
        segments, _info = model.transcribe(str(path), language="zh")
        return "".join(s.text for s in segments).strip()
    except Exception:
        log.exception("转写失败: %s", path)
        return None


def ingest_audio(path, meeting_id=None, meta=None):
    """转写音频并入库。返回 (item_id, text) 或 (None, None)。"""
    text = transcribe_audio(path)
    if not text:
        return None, None
    from core.events import bus
    item_id = db.add_info_item("speech", text, meeting_id=meeting_id, meta=meta)
    bus().publish("info.new", {"id": item_id, "source": "speech", "content": text})
    return item_id, text
