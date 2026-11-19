"""tiktoken 离线词表引导：缓存目录固定、本地预热与缺表回退。"""

from pathlib import Path

import pytest

from app.utils import tiktoken_offline
from app.utils.token_budget import TokenBudgetManager


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    for name in ("TIKTOKEN_CACHE_DIR", "DATA_GYM_CACHE_DIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(tiktoken_offline, "default_cache_dir", lambda: tmp_path / "cache")
    return tmp_path / "cache"


def test_bootstrap_seeds_cache_from_local_sources():
    cache_dir = tiktoken_offline.bootstrap_tiktoken_cache()

    assert cache_dir is not None
    assert cache_dir.is_dir()
    assert tiktoken_offline.encoding_is_cached("cl100k_base", cache_dir)


def test_bootstrap_never_raises_without_seed_sources(monkeypatch, tmp_path):
    monkeypatch.setattr(tiktoken_offline, "_seed_dirs", lambda: [])

    cache_dir = tiktoken_offline.bootstrap_tiktoken_cache()

    assert cache_dir == tmp_path / "cache"
    assert not tiktoken_offline.encoding_is_cached("cl100k_base", cache_dir)


def test_manager_falls_back_when_encoding_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(tiktoken_offline, "_seed_dirs", lambda: [])

    manager = TokenBudgetManager(model="deepseek-chat")

    assert manager.use_tiktoken is False
    assert manager.tokenizer is None
    # 字符估算兜底：英文/中文都应返回非零 token 数
    assert manager.count_tokens("hello 你好 world") > 0


def test_manager_uses_tiktoken_when_cached():
    tiktoken_offline.bootstrap_tiktoken_cache()

    manager = TokenBudgetManager(model="deepseek-chat")

    assert manager.use_tiktoken is True
    assert manager.tokenizer is not None
    assert manager.count_tokens("hello world") > 0


def test_encoding_is_cached_ignores_empty_file(tmp_path):
    blob = tiktoken_offline.ENCODING_BLOB_SHA1["cl100k_base"]
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / blob).touch()

    assert tiktoken_offline.encoding_is_cached("cl100k_base", cache_dir) is False


def test_encoding_is_cached_rejects_unknown_encoding(tmp_path):
    assert tiktoken_offline.encoding_is_cached("no_such_encoding", tmp_path) is False
