from collectors.base import collect_all, get_registry, register  # noqa: F401
from collectors.manual import submit_manual
from collectors.speech import ingest_audio, transcribe_audio

import collectors.im.wechat  # noqa: F401  触发注册
