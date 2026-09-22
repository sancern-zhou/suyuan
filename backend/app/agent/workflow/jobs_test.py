import pytest

from app.agent.workflow.jobs import WorkflowJobStore


class _FakeRedis:
    def __init__(self):
        self.hashes = {}
        self.lists = {}
        self.streams = {}
        self.sequence = 0

    async def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

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
