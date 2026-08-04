import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from core.config import BASE_DIR
from server.api.routes import router


def _frontend_dir():
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(getattr(sys, "_MEIPASS", "")) / "server" / "frontend")
        candidates.append(Path(sys.executable).resolve().parent / "server" / "frontend")
    candidates.append(BASE_DIR / "server" / "frontend")
    for c in candidates:
        try:
            if c.is_dir():
                return c
        except Exception:
            continue
    return None


def create_app():
    app = FastAPI(title="会议准备自动化工作台", version="0.1.0")
    app.include_router(router)

    frontend = _frontend_dir()
    if frontend is not None:
        app.mount("/", StaticFiles(directory=str(frontend), html=True),
                  name="frontend")
    return app


app = create_app()
