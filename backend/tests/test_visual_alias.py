"""会话作用域图表短别名注册表（[[chart:chart_N]]）的单元测试。

核心契约：
- 会话内序号单调递增，跨轮不重号；
- 跨会话同名别名互不影响（resolve 按 session_id 隔离）；
- Finalizer 解析改写 [[chart:chart_N]] → 全局唯一 visual_id，fail-open；
- 别名形式必须满足 [[chart:<id>]] 协议字符集。
"""

import re

from app.agent.runtime.visual_alias import (
    InMemoryVisualAliasStore,
    RedisVisualAliasStore,
    VisualAliasRegistry,
    is_alias_id,
    resolve_chart_alias_markers,
)
from app.utils.visual_ids import VISUAL_ID_PATTERN
import re


class _FakeRedis:
    """仅实现 RedisVisualAliasStore 用到的最小接口。"""

    def __init__(self):
        self.strings: dict[str, int] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.ttls: dict[str, int] = {}

    def pipeline(self, transaction: bool = True):
        return _FakePipeline(self)

    async def expire(self, key: str, ttl: int):
        self.ttls[key] = ttl

    async def hset(self, key: str, mapping: dict[str, str]):
        self.hashes.setdefault(key, {}).update(mapping)

    async def hmget(self, key: str, fields: list[str]):
        data = self.hashes.get(key, {})
        return [data.get(field) for field in fields]


class _FakePipeline:
    def __init__(self, client: _FakeRedis):
        self._client = client
        self._keys: list[str] = []

    def incr(self, key: str):
        self._keys.append(key)

    async def execute(self):
        results = []
        for key in self._keys:
            self._client.strings[key] = self._client.strings.get(key, 0) + 1
            results.append(self._client.strings[key])
        return results


async def test_bind_allocates_monotonic_aliases_within_session():
    registry = VisualAliasRegistry()
    first = await registry.bind("s1", ["echarts_aaa_0", "echarts_aaa_1"])
    second = await registry.bind("s1", ["echarts_bbb_0"])
    assert first == {"chart_0": "echarts_aaa_0", "chart_1": "echarts_aaa_1"}
    assert second == {"chart_2": "echarts_bbb_0"}


async def test_cross_session_aliases_are_isolated():
    registry = VisualAliasRegistry()
    await registry.bind("s1", ["echarts_aaa_0"])
    await registry.bind("s2", ["echarts_bbb_0"])
    resolved_s1 = await registry.resolve_ids("s1", ["chart_0"])
    resolved_s2 = await registry.resolve_ids("s2", ["chart_0"])
    assert resolved_s1 == {"chart_0": "echarts_aaa_0"}
    assert resolved_s2 == {"chart_0": "echarts_bbb_0"}


async def test_bind_dedupes_visual_ids():
    registry = VisualAliasRegistry()
    mapping = await registry.bind("s1", ["echarts_aaa_0", "echarts_aaa_0"])
    assert mapping == {"chart_0": "echarts_aaa_0"}


async def test_bind_rejects_invalid_input():
    registry = VisualAliasRegistry()
    assert await registry.bind("s1", []) == {}
    assert await registry.bind("", ["echarts_aaa_0"]) == {}
    assert await registry.bind("s1", [None, "", 123]) == {}


async def test_redis_store_roundtrip_and_isolation():
    client_a = _FakeRedis()
    store_a = RedisVisualAliasStore(client_a, key_prefix="pfx", ttl_seconds=60)
    store_b = RedisVisualAliasStore(_FakeRedis(), key_prefix="pfx", ttl_seconds=60)

    seqs = await store_a.allocate("s1", 2)
    assert seqs == [0, 1]
    await store_a.store("s1", {"chart_0": "echarts_aaa_0", "chart_1": "echarts_aaa_1"})

    assert await store_a.lookup("s1", ["chart_0", "chart_1", "chart_9"]) == {
        "chart_0": "echarts_aaa_0",
        "chart_1": "echarts_aaa_1",
    }
    # 另一个 Redis（模拟另一 worker/另一会话空间）查不到
    assert await store_b.lookup("s1", ["chart_0"]) == {}

    # 跨轮不重号：计数器继续递增
    seqs = await store_a.allocate("s1", 1)
    assert seqs == [2]
    # TTL 已刷新
    assert client_a.ttls["pfx:seq:s1"] == 60


async def test_registry_falls_back_to_memory_when_redis_fails():
    class _BrokenStore:
        async def allocate(self, session_id, count):
            raise RuntimeError("redis down")

        async def store(self, session_id, mapping):
            raise RuntimeError("redis down")

        async def lookup(self, session_id, aliases):
            raise RuntimeError("redis down")

    registry = VisualAliasRegistry(redis_store=_BrokenStore())
    mapping = await registry.bind("s1", ["echarts_aaa_0"])
    assert mapping == {"chart_0": "echarts_aaa_0"}
    assert await registry.resolve_ids("s1", ["chart_0"]) == {"chart_0": "echarts_aaa_0"}


async def test_resolver_rewrites_known_aliases_and_keeps_unknown():
    registry = VisualAliasRegistry()
    await registry.bind("s1", ["echarts_aaa_0", "echarts_aaa_1"])
    text = (
        "结论一\n\n[[chart:chart_0]]\n\n中间说明\n\n[[chart:chart_7]]\n\n"
        "[[chart:echarts_full_id_0]] 结尾"
    )
    resolved = await resolve_chart_alias_markers(text, "s1", registry=registry)
    assert "[[chart:echarts_aaa_0]]" in resolved
    assert "[[chart:chart_7]]" in resolved  # 未绑定别名保持原样（fail-open）
    assert "[[chart:echarts_full_id_0]]" in resolved  # 全串 ID 不受影响


async def test_resolver_noop_without_markers_or_session():
    registry = VisualAliasRegistry()
    await registry.bind("s1", ["echarts_aaa_0"])
    assert await resolve_chart_alias_markers("无标记正文", "s1", registry=registry) == "无标记正文"
    assert await resolve_chart_alias_markers("[[chart:chart_0]]", None, registry=registry) == "[[chart:chart_0]]"
    assert await resolve_chart_alias_markers("", "s1", registry=registry) == ""


async def test_resolver_ignores_non_alias_ids_without_lookup():
    class _MustNotResolve:
        async def resolve_ids(self, session_id, aliases):
            raise AssertionError("不应为非别名 ID 触发解析")

    text = "正文\n\n[[chart:echarts_hnccwfa3se_0]]\n"
    assert await resolve_chart_alias_markers(text, "s1", registry=_MustNotResolve()) == text


def test_alias_ids_satisfy_visual_id_protocol():
    assert is_alias_id("chart_0")
    assert is_alias_id("chart_123456")
    assert not is_alias_id("chart_")
    assert not is_alias_id("chart_abc")
    assert not is_alias_id("echarts_hnccwfa3se_0")
    for alias in ("chart_0", "chart_42", "chart_999999"):
        assert re.fullmatch(VISUAL_ID_PATTERN, alias), alias


async def test_inmemory_store_isolation():
    store = InMemoryVisualAliasStore()
    await store.store("s1", {"chart_0": "a"})
    await store.store("s2", {"chart_0": "b"})
    assert await store.lookup("s1", ["chart_0"]) == {"chart_0": "a"}
    assert await store.lookup("s2", ["chart_0"]) == {"chart_0": "b"}
    assert await store.lookup("s3", ["chart_0"]) == {}
