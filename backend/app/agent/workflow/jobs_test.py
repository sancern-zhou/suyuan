import pytest

from app.agent.workflow.jobs import WorkflowJobStore, _ENQUEUE_SCRIPT, _CLAIM_SCRIPT, _RECOVER_SCRIPT


class _FakeRedis:
    def __init__(self):
        self.hashes = {}
        self.lists = {}
        self.streams = {}
        self.sequence = 0
        self.last_xread_block = "unset"

    async def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    async def eval(self, script, number_of_keys, *args):
        keys, argv = args[:number_of_keys], args[number_of_keys:]
        target = self.hashes.setdefault(keys[0], {})
        if script == _ENQUEUE_SCRIPT:
            if target.get("session_id") and target["session_id"] != argv[1]:
                return -1
            if target.get("status") in {"queued", "running"}:
                return 0
            target.update(dict(zip(
                ("job_id", "workflow_id", "session_id", "status", "payload", "snapshot", "updated_at", "last_sequence"),
                (argv[0], argv[0], argv[1], "queued", argv[2], argv[3], argv[4], "0"),
            )))
            self.lists.setdefault(keys[1], []).append(argv[0])
            return 1
        if script == _CLAIM_SCRIPT:
            if target.get("status") != "queued":
                return 0
            target.update(status="running", owner=argv[0], updated_at=argv[1])
            return 1
        if script == _RECOVER_SCRIPT:
            if target.get("status") != argv[0] or target.get("updated_at") != argv[1]:
                return 0
            target.update(status="queued", updated_at=argv[2])
            self.lists.setdefault(keys[1], []).append(argv[3])
            return 1
        raise AssertionError("unknown Lua script")

    async def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)

    async def hset(self, key, key_arg=None, value=None, mapping=None):
        target = self.hashes.setdefault(key, {})
        if mapping is not None:
            target.update(mapping)
        elif key_arg is not None:
            target[key_arg] = value
        return 1

    async def expire(self, key, seconds):
        return True

    async def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)

    async def blpop(self, key, timeout=0):
        values = self.lists.get(key, [])
        if not values:
            return None
        return key, values.pop(0)

    async def xadd(self, key, values, maxlen=None, approximate=True):
        self.sequence += 1
        event_id = f"{self.sequence}-0"
        self.streams.setdefault(key, []).append((event_id, dict(values)))
        return event_id

    async def xread(self, streams, count=100, block=0):
        self.last_xread_block = block
        result = []
        for key, after in streams.items():
            after_number = int(str(after).split("-", 1)[0])
            entries = [item for item in self.streams.get(key, []) if int(item[0].split("-", 1)[0]) > after_number]
            if entries:
                result.append((key, entries[:count]))
        return result

    async def scan_iter(self, match=None):
        for key in self.hashes:
            yield key


@pytest.mark.asyncio
async def test_workflow_job_store_claims_idempotently_and_streams_events():
    store = WorkflowJobStore(_FakeRedis(), prefix="test:workflow")
    definition = {"workflow_id": "wf-1", "nodes": []}
    snapshot = {"workflow_id": "wf-1", "status": "queued", "runtime": {"events": []}}
    queued = await store.enqueue(session_id="s-1", workflow_id="wf-1", definition=definition, snapshot=snapshot)
    duplicate = await store.enqueue(session_id="s-1", workflow_id="wf-1", definition=definition, snapshot=snapshot)
    assert queued.status == duplicate.status == "queued"

    claimed = await store.claim(timeout=0)
    assert claimed.workflow_id == "wf-1"
    await store.publish_snapshot("wf-1", {"status": "running", "runtime": {"events": [{"sequence": 1, "event_type": "task.running"}]}})
    events = await store.read_events("wf-1")
    assert any(event.get("type") == "runtime" for _, event in events)
    assert store.redis.last_xread_block is None


@pytest.mark.asyncio
async def test_workflow_job_store_does_not_wait_for_missing_event_stream():
    redis = _FakeRedis()
    store = WorkflowJobStore(redis, prefix="test:workflow")

    assert await store.read_events("missing") == []
    assert redis.last_xread_block is None


@pytest.mark.asyncio
async def test_recovered_job_reads_latest_snapshot_and_keeps_session_owner():
    store = WorkflowJobStore(_FakeRedis(), prefix="test:recovery")
    await store.enqueue(session_id="s1", workflow_id="wf", definition={}, snapshot={})
    await store.claim()
    latest = {"status": "running", "node_results": {"air": {"success": True}}}
    await store.publish_snapshot("wf", latest)
    assert (await store.get("wf")).snapshot == latest
    with pytest.raises(ValueError, match="another session"):
        await store.enqueue(session_id="s2", workflow_id="wf", definition={}, snapshot={})
    await store.redis.hset(store.state_key("wf"), "updated_at", "0")
    assert await store.recover_expired() == 1
    assert (await store.claim()).snapshot == latest


@pytest.mark.asyncio
async def test_recovery_requeues_job_lost_between_pop_and_claim():
    store = WorkflowJobStore(_FakeRedis(), prefix="test:lost")
    await store.enqueue(session_id="s", workflow_id="wf", definition={}, snapshot={})
    await store.redis.blpop(store.queue_key)
    await store.redis.hset(store.state_key("wf"), "updated_at", "0")
    assert await store.recover_expired() == 1
    assert (await store.claim()).workflow_id == "wf"
