"""独立 bge-m3 嵌入服务。

web/worker 进程此前各自加载一份 bge-m3（约 1G 内存），通过本服务把权重
收敛为全机一份，进程侧改用 EMBEDDING_SERVICE_URL 走 HTTP 调用（见
app.knowledge_base.remote_embedding）。独立进程启动：

    cd backend
    python -m app.services.embedding_server

默认监听 127.0.0.1:8020（EMBEDDING_SERVICE_HOST / EMBEDDING_SERVICE_PORT
可覆盖），仅供同机 web/worker 访问。
"""

from __future__ import annotations

import os
import threading

import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logger = structlog.get_logger()

_DEFAULT_PORT = 8020

app = FastAPI(title="suyuan-embedding-service", docs_url=None, redoc_url=None)

_model = None
_model_lock = threading.Lock()
# SentenceTransformer.encode 无线程安全承诺，所有推理串行化；
# 嵌入单条毫秒级，串行足够支撑当前规模。
_encode_lock = threading.Lock()
_loaded_dim: int | None = None


class EmbedRequest(BaseModel):
    texts: list[str]
    normalize: bool = True


def _resolve_model_path() -> str | None:
    """与 vector_store._init_embedding 相同的模型路径解析逻辑。"""
    local_path = os.getenv("BGE_M3_MODEL_PATH")
    if local_path and os.path.exists(local_path):
        return local_path
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(current_dir))
    candidate = os.path.join(project_root, "models", "bge-m3-model")
    return candidate if os.path.exists(candidate) else None


def get_model():
    global _model, _loaded_dim
    if _model is None:
        with _model_lock:
            if _model is None:
                from sentence_transformers import SentenceTransformer

                local_path = _resolve_model_path()
                if local_path:
                    logger.info("loading_bge_m3_from_local", path=local_path)
                    _model = SentenceTransformer(local_path)
                else:
                    logger.info("loading_bge_m3_from_hub")
                    _model = SentenceTransformer("BAAI/bge-m3")
                probe = _model.encode("test", normalize_embeddings=True)
                _loaded_dim = len(probe)
                logger.info("bge_m3_model_loaded", dim=_loaded_dim)
    return _model


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "model_loaded": _model is not None,
        "dim": _loaded_dim,
    }


@app.post("/embed")
def embed(request: EmbedRequest) -> dict:
    if not request.texts:
        raise HTTPException(status_code=400, detail="texts must not be empty")
    model = get_model()
    with _encode_lock:
        embeddings = model.encode(
            request.texts,
            normalize_embeddings=request.normalize,
            show_progress_bar=False,
        )
    return {"embeddings": embeddings.tolist(), "dim": len(embeddings[0])}


def main() -> None:
    import uvicorn

    host = os.getenv("EMBEDDING_SERVICE_HOST", "127.0.0.1")
    port = int(os.getenv("EMBEDDING_SERVICE_PORT", str(_DEFAULT_PORT)))
    # 启动即加载模型：加载失败直接退出，便于 supervisors/运维第一时间发现
    get_model()
    uvicorn.run(app, host=host, port=port, workers=1, log_level="info")


if __name__ == "__main__":
    main()
