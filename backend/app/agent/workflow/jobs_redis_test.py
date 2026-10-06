"""Real Redis fault/race checks, using an isolated server rather than deployment data.

Run with PYTEST_REDIS_SERVER=/absolute/path/to/redis-server. With no binary configured,
these integration tests skip; the deterministic store/worker unit tests still run.
"""

import asyncio
import os
from pathlib import Path
import subprocess

import pytest
import pytest_asyncio
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from app.agent.workflow.jobs import WorkflowJobStore, WorkflowLeaseLost, _RECOVER_SCRIPT
from app.agent.workflow.worker import _run_job


@pytest_asyncio.fixture
async def isolated_redis(tmp_path):
    binary = os.environ.get("PYTEST_REDIS_SERVER")
    if not binary:
        pytest.skip("set PYTEST_REDIS_SERVER to run isolated real Redis tests")
    assert Path(binary).is_absolute() and Path(binary).is_file()
    socket_path = str(tmp_path / "redis.sock")
    process = subprocess.Popen(
        [binary, "--port", "0", "--unixsocket", socket_path, "--save", "",
         "--appendonly", "no", "--dir", str(tmp_path)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    client = Redis(unix_socket_path=socket_path, decode_responses=True,
                   socket_connect_timeout=1, socket_timeout=2)
    try:
        for _ in range(100):
            assert process.poll() is None, "isolated Redis exited before becoming ready"
            try:
                await client.ping()
                break
            except (RedisConnectionError, OSError):
                await asyncio.sleep(0.02)
        else:
            pytest.fail("isolated Redis did not become ready")
        yield client
    finally:
        await client.aclose()
        process.terminate()
        try:
            await asyncio.to_thread(process.wait, timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            await asyncio.to_thread(process.wait)


async def enqueue(store, snapshot=None):
    return await store.enqueue(session_id="s", workflow_id="wf", definition={"nodes": []},
                               snapshot=snapshot or {})


@pytest.mark.asyncio
async def test_partial_is_persisted_as_terminal_without_recovery(isolated_redis):
    store = WorkflowJobStore(isolated_redis, prefix="partial")
    await enqueue(store)
    job = await store.claim()
    await store.finish("wf", status="partial", result={"delivery": {"deliverable": True}}, lease_token=job.lease_token)
    assert (await store.get("wf")).status == "partial"
    assert await store.recover_expired() == 0
    assert (await store.read_events("wf"))[-1][1]["status"] == "partial"


@pytest.mark.asyncio
async def test_concurrent_enqueues_and_claims_have_one_owner(isolated_redis):
    stores = [WorkflowJobStore(isolated_redis, prefix="race") for _ in range(12)]
    await asyncio.gather(*(enqueue(store) for store in stores))
    assert await isolated_redis.llen(stores[0].queue_key) == 1
    claims = await asyncio.gather(*(store.claim(timeout=1) for store in stores[:2]))
    assert sum(job is not None for job in claims) == 1


@pytest.mark.asyncio
async def test_recovery_reads_latest_snapshot_and_rejects_stale_writes(isolated_redis):
    old = WorkflowJobStore(isolated_redis, prefix="recover")
    new = WorkflowJobStore(isolated_redis, prefix="recover")
    await enqueue(old)
    previous = await old.claim()
    snapshot = {"parent_mode": "expert", "max_concurrency": 2,
                "node_results": {"air": {"success": True}}, "status": "running"}
    await old.publish_snapshot("wf", snapshot, lease_token=previous.lease_token)
    await isolated_redis.hset(old.state_key("wf"), "updated_at", "0")
    assert sum(await asyncio.gather(*(new.recover_expired() for _ in range(8)))) == 1
    current = await new.claim()
    assert current.snapshot == snapshot
    assert current.lease_token != previous.lease_token
    state = await isolated_redis.hgetall(old.state_key("wf"))
    events = await old.read_events("wf")
    for operation in ("heartbeat", "snapshot", "finish"):
        with pytest.raises(WorkflowLeaseLost):
            if operation == "heartbeat":
                await old.heartbeat("wf", lease_token=previous.lease_token)
            elif operation == "snapshot":
                await old.publish_snapshot("wf", {"status": "failed"}, lease_token=previous.lease_token)
            else:
                await old.finish("wf", status="failed", lease_token=previous.lease_token)
    assert await isolated_redis.hgetall(old.state_key("wf")) == state
    assert await old.read_events("wf") == events
    await new.finish("wf", status="succeeded", lease_token=current.lease_token)
    with pytest.raises(WorkflowLeaseLost):
        await new.heartbeat("wf", lease_token=current.lease_token)


@pytest.mark.asyncio
async def test_same_worker_reclaim_and_resume_issue_new_tokens(isolated_redis):
    store = WorkflowJobStore(isolated_redis, prefix="same")
    await enqueue(store)
    previous = await store.claim()
    await isolated_redis.hset(store.state_key("wf"), "updated_at", "0")
    assert await store.recover_expired() == 1
    current = await store.claim()
    assert current.lease_token != previous.lease_token
    snapshot = {"status": "succeeded", "runtime": {"events": [{"sequence": 1}]}}
    for _ in range(2):
        await store.publish_snapshot("wf", snapshot, lease_token=current.lease_token)
    assert (await store.get("wf")).status == "running"
    assert sum(event.get("type") == "runtime" for _, event in await store.read_events("wf")) == 1
    await store.finish("wf", status="failed", result={"error": "retry"}, lease_token=current.lease_token)
    await enqueue(store, snapshot)
    assert await isolated_redis.hget(store.state_key("wf"), "result") is None
    resumed = await store.claim()
    with pytest.raises(WorkflowLeaseLost):
        await store.finish("wf", status="failed", lease_token=current.lease_token)
    await store.finish("wf", status="succeeded", lease_token=resumed.lease_token)


@pytest.mark.asyncio
async def test_pop_before_claim_crash_is_recoverable(isolated_redis):
    store = WorkflowJobStore(isolated_redis, prefix="pop")
    await enqueue(store)
    await isolated_redis.blpop(store.queue_key, timeout=1)
    await isolated_redis.hset(store.state_key("wf"), "updated_at", "0")
    assert await store.recover_expired() == 1
    assert (await store.claim()).workflow_id == "wf"


@pytest.mark.asyncio
async def test_heartbeat_during_recovery_prevents_takeover(isolated_redis, monkeypatch):
    store = WorkflowJobStore(isolated_redis, prefix="heartbeat")
    await enqueue(store)
    job = await store.claim()
    await isolated_redis.hset(store.state_key("wf"), "updated_at", "0")
    original_eval = isolated_redis.eval
    async def racing_eval(script, *args):
        if script == _RECOVER_SCRIPT:
            await store.heartbeat("wf", lease_token=job.lease_token)
        return await original_eval(script, *args)
    monkeypatch.setattr(isolated_redis, "eval", racing_eval)
    assert await store.recover_expired() == 0
    assert (await store.get("wf")).lease_token == job.lease_token


@pytest.mark.asyncio
async def test_worker_stops_when_other_execution_takes_over(isolated_redis, monkeypatch):
    from app.tools.agent_tools.run_agent_workflow import RunAgentWorkflowTool
    old = WorkflowJobStore(isolated_redis, prefix="worker")
    new = WorkflowJobStore(isolated_redis, prefix="worker")
    await enqueue(old)
    job = await old.claim()
    started, release, cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()
    async def execute(self, **kwargs):
        started.set()
        try:
            await release.wait()
            kwargs["context"].workflow_event_sink({"status": "running"})
            await asyncio.Event().wait()
        finally:
            cancelled.set()
    monkeypatch.setattr(RunAgentWorkflowTool, "execute", execute)
    task = asyncio.create_task(_run_job(job, old))
    try:
        await asyncio.wait_for(started.wait(), 1)
        await isolated_redis.hset(old.state_key("wf"), "updated_at", "0")
        assert await new.recover_expired() == 1
        current = await new.claim()
        release.set()
        await asyncio.wait_for(task, 2)
        assert cancelled.is_set()
        stored = await new.get("wf")
        assert stored.status == "running" and stored.lease_token == current.lease_token
        assert await isolated_redis.hget(new.state_key("wf"), "result") is None
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
