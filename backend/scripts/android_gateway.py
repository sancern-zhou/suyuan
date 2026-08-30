"""Minimal Android gateway with social chat and attachment routes.

The Alibaba key is loaded at runtime from the local deployment env file and is
never logged or embedded in source control.
"""

import os
import sys
from pathlib import Path

from fastapi import FastAPI
import uvicorn

# Running this file directly puts ``scripts`` first on sys.path; add the
# backend root so the existing ``app`` package resolves consistently.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _load_key_file() -> None:
    # Keep the desktop-only env file out of the repository while allowing the
    # USB development gateway to use the same credentials as the web service.
    env_path = Path(r"D:\下载\.env (2)")
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if name in {"BAILIAN_API_KEY", "KNOWLEDGE_RERANK_API_KEY"} and not os.environ.get(name):
            os.environ[name] = value.strip().strip('"').strip("'")


_load_key_file()

from app.api.social_app_routes import router as social_router
from app.api.upload_routes import router as upload_router

app = FastAPI()
app.include_router(social_router)
app.include_router(upload_router, prefix="/api/upload")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
