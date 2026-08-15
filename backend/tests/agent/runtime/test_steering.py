import json

import pytest

from app.agent.runtime.steering import RedisSteeringStore, SteeringRegistry


class FakeRedis:
    """Small shared Redis script harness for steering registry contract tests."""

    def __init__(self, *, unavailable: bool = False):
        self.unavailable = unavailable
        self.hashes = {}
        self.lists = {}

    async def eval(self, script, numkeys, *args):
        if self.unavailable:
            raise ConnectionError("redis unavailable")

        keys = list(args[:numkeys])
        argv = list(args[numkeys:])
        marker = script.splitlines()[0].strip()

        if marker == "-- steering:register":
            active_key, queue_key = keys
            run_id, mode, _ttl, steerable = argv
            if steerable != "1":
                self.hashes.pop(active_key, None)
                self.lists.pop(queue_key, None)
                return 0
            self.hashes[active_key] = {
                "run_id": run_id,
                "mode": mode,
                "status": "accepting",
            }
            self.lists.pop(queue_key, None)
            return 1

        if marker == "-- steering:add":
            active_key, queue_key = keys
            active = self.hashes.get(active_key)
            if not active or active.get("status") != "accepting":
                return 0
            self.lists.setdefault(queue_key, []).append(argv[0])
            return 1

        if marker == "-- steering:drain":
            active_key, queue_key = keys
            active = self.hashes.get(active_key)
            if not active or active.get("run_id") != argv[0]:
                return []
            return self.lists.pop(queue_key, [])

        if marker == "-- steering:begin_completion":
            active_key, queue_key = keys
            active = self.hashes.get(active_key)
            if not active or active.get("run_id") != argv[0]:
                return ["missing"]
            items = self.lists.pop(queue_key, [])
            if items:
                return ["drained", *items]
            active["status"] = "closing"
            return ["closing"]

        if marker == "-- steering:mark_closing":
            active_key = keys[0]
            active = self.hashes.get(active_key)
            if not active or active.get("run_id") != argv[0]:
                return 0
            active["status"] = "closing"
            return 1

        if marker == "-- steering:close_and_drain":
            active_key, queue_key = keys
            active = self.hashes.get(active_key)
            if not active or active.get("run_id") != argv[0]:
                return []
            active["status"] = "closing"
            return self.lists.pop(queue_key, [])

        if marker == "-- steering:unregister":
            active_key, queue_key = keys
            active = self.hashes.get(active_key)
            if not active or active.get("run_id") != argv[0]:
                return 0
            self.hashes.pop(active_key, None)
            self.lists.pop(queue_key, None)
            return 1

        if marker == "-- steering:is_active":
            active = self.hashes.get(keys[0])
            if not active:
                return []
            return [active["run_id"], active["mode"], active["status"]]

        raise AssertionError(f"unknown script marker: {marker}")

    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_accepts_and_drains_steering_for_active_assistant_run():
    registry = SteeringRegistry()
    await registry.register("session-1", "run-1", "assistant")

    accepted = await registry.add_input("session-1", "请改成表格")
    drained = await registry.drain("session-1", "run-1")

    assert accepted is True
    assert [item.content for item in drained] == ["请改成表格"]
    assert await registry.drain("session-1", "run-1") == []


@pytest.mark.asyncio
async def test_preserves_client_steering_input_id_through_queue():
    registry = SteeringRegistry()
    await registry.register("session-1", "run-1", "assistant")

    assert await registry.add_input(
        "session-1",
        "请改成表格",
        input_id="client-steer-1",
    ) is True

    [item] = await registry.drain("session-1", "run-1")
    assert item.input_id == "client-steer-1"


@pytest.mark.asyncio
async def test_rejects_steering_when_run_is_not_active_or_not_steerable():
    registry = SteeringRegistry()
    await registry.register("session-1", "run-1", "query")

    assert await registry.add_input("session-1", "补充条件") is False
    assert await registry.add_input("missing-session", "补充条件") is False
    assert await registry.drain("session-1", "run-1") == []


@pytest.mark.asyncio
async def test_redis_store_shares_active_run_and_fifo_queue_across_registry_instances():
    redis = FakeRedis()
    first_worker = SteeringRegistry(
        store=RedisSteeringStore(redis, key_prefix="test-steering", ttl_seconds=60)
    )
    second_worker = SteeringRegistry(
        store=RedisSteeringStore(redis, key_prefix="test-steering", ttl_seconds=60)
    )

    assert await first_worker.register("session/shared", "run-1", "assistant") is True
    assert await second_worker.add_input("session/shared", "重复") is True
    assert await second_worker.add_input("session/shared", "重复") is True

    drained = await first_worker.drain("session/shared", "run-1")

    assert [item.content for item in drained] == ["重复", "重复"]
    assert all(json.loads(item.to_json())["input_id"] for item in drained)


@pytest.mark.asyncio
async def test_begin_completion_atomically_closes_empty_run_and_rejects_late_input():
    redis = FakeRedis()
    registry = SteeringRegistry(
        store=RedisSteeringStore(redis, key_prefix="test-steering", ttl_seconds=60)
    )
    await registry.register("session-1", "run-1", "assistant")
    await registry.add_input("session-1", "先应用我")

    drained = await registry.begin_completion("session-1", "run-1")
    assert [item.content for item in drained] == ["先应用我"]
    assert await registry.add_input("session-1", "仍可进入下一轮") is True
    assert [item.content for item in await registry.begin_completion("session-1", "run-1")] == [
        "仍可进入下一轮"
    ]

    assert await registry.begin_completion("session-1", "run-1") == []
    assert await registry.add_input("session-1", "太晚了") is False


@pytest.mark.asyncio
async def test_unregister_from_old_run_does_not_remove_new_run_registration():
    redis = FakeRedis()
    registry = SteeringRegistry(
        store=RedisSteeringStore(redis, key_prefix="test-steering", ttl_seconds=60)
    )
    assert await registry.register("session-1", "run-old", "assistant") is True
    await registry.register("session-1", "run-new", "assistant")

    await registry.unregister("session-1", "run-old")

    assert await registry.add_input("session-1", "发给新任务") is True
    assert [item.content for item in await registry.drain("session-1", "run-new")] == ["发给新任务"]


@pytest.mark.asyncio
async def test_redis_failure_degrades_to_not_accepted_without_raising():
    registry = SteeringRegistry(
        store=RedisSteeringStore(
            FakeRedis(unavailable=True),
            key_prefix="test-steering",
            ttl_seconds=60,
        )
    )

    assert await registry.register("session-1", "run-1", "assistant") is False
    assert await registry.add_input("session-1", "转为排队") is False
    assert await registry.drain("session-1", "run-1") == []
    assert await registry.begin_completion("session-1", "run-1") == []


@pytest.mark.asyncio
async def test_non_steerable_run_clears_stale_redis_registration_for_session():
    redis = FakeRedis()
    registry = SteeringRegistry(
        store=RedisSteeringStore(redis, key_prefix="test-steering", ttl_seconds=60)
    )
    assert await registry.register("session-1", "run-old", "assistant") is True

    assert await registry.register("session-1", "run-query", "query") is False
    assert await registry.add_input("session-1", "不应发给旧任务") is False


@pytest.mark.asyncio
async def test_abnormal_close_atomically_drains_already_accepted_inputs():
    redis = FakeRedis()
    registry = SteeringRegistry(
        store=RedisSteeringStore(redis, key_prefix="test-steering", ttl_seconds=60)
    )
    await registry.register("session-1", "run-1", "assistant")
    await registry.add_input("session-1", "终止前已接受")

    deferred = await registry.close_and_drain("session-1", "run-1")

    assert [item.content for item in deferred] == ["终止前已接受"]
    assert await registry.add_input("session-1", "终止后到达") is False
