"""tiktoken 词表离线引导。

tiktoken 在首次初始化某个 encoding 时，会从
``openaipublic.blob.core.windows.net`` 下载 BPE 词表（1.7M），且 ``requests.get``
没有超时参数。内网环境该域名不可达时，TCP 连接会一直等到内核超时，实测
``import app.main`` / 任何构造 ``TokenBudgetManager`` 的脚本会被卡住 130s 以上。

这里在任何 encoding 初始化之前把缓存目录固定到本地，并从随包安装的
llama-index 静态缓存预热；仍然缺失时不发起网络请求，直接让调用方回退到
字符估算。
"""
from __future__ import annotations

import importlib.util
import os
import shutil
from pathlib import Path

import structlog

logger = structlog.get_logger()

# tiktoken 的缓存文件名是 sha1(blob_url)，与 official openai_public.py 对齐。
ENCODING_BLOB_SHA1: dict[str, str] = {
    "cl100k_base": "9b5ad71b2ce5302211f9c61530b329a4922fc6a4",
    "o200k_base": "fb374d419588a4632f3f557e76b4b70aebbca790",
}

_SEED_PACKAGES = (
    ("llama_index.core", "_static", "tiktoken_cache"),
)


def default_cache_dir() -> Path:
    from app.utils.path_config import BACKEND_ROOT

    return BACKEND_ROOT / "data" / "tiktoken_cache"


def _seed_dirs() -> list[Path]:
    dirs: list[Path] = []
    for package, *parts in _SEED_PACKAGES:
        try:
            spec = importlib.util.find_spec(package)
        except (ImportError, ValueError):
            continue
        if not spec or not spec.submodule_search_locations:
            continue
        for location in spec.submodule_search_locations:
            candidate = Path(location).joinpath(*parts)
            if candidate.is_dir():
                dirs.append(candidate)
    return dirs


def bootstrap_tiktoken_cache() -> Path | None:
    """固定 tiktoken 缓存目录并预热本地词表。

    Returns:
        实际生效的缓存目录；目录不可写时返回 ``None``。
    """
    cache_dir = Path(
        os.environ.get("TIKTOKEN_CACHE_DIR") or default_cache_dir()
    ).expanduser()
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("tiktoken_cache_dir_unusable", path=str(cache_dir), error=str(exc))
        return None

    # 必须在任何 get_encoding/encoding_for_model 之前写入，tiktoken 在调用时读取。
    os.environ["TIKTOKEN_CACHE_DIR"] = str(cache_dir)

    seeded: list[str] = []
    for seed_dir in _seed_dirs():
        for blob in ENCODING_BLOB_SHA1.values():
            target = cache_dir / blob
            if target.is_file() and target.stat().st_size > 0:
                continue
            source = seed_dir / blob
            if not (source.is_file() and source.stat().st_size > 0):
                continue
            try:
                shutil.copyfile(source, target)
                seeded.append(blob)
            except OSError as exc:
                logger.warning(
                    "tiktoken_cache_seed_failed",
                    source=str(source),
                    target=str(target),
                    error=str(exc),
                )

    available = [name for name in ENCODING_BLOB_SHA1 if encoding_is_cached(name, cache_dir)]
    logger.info(
        "tiktoken_cache_ready",
        path=str(cache_dir),
        seeded=seeded,
        available=available,
    )
    return cache_dir


def encoding_is_cached(encoding_name: str, cache_dir: Path | None = None) -> bool:
    """判断某个 encoding 的词表是否已在本地，避免触发下载。"""
    blob = ENCODING_BLOB_SHA1.get(encoding_name)
    if not blob:
        return False
    root = cache_dir
    if root is None:
        configured = os.environ.get("TIKTOKEN_CACHE_DIR")
        root = Path(configured) if configured else default_cache_dir()
    path = Path(root) / blob
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False
