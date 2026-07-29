import pytest

from app.lifecycle import knowledge_base as lifecycle


@pytest.mark.asyncio
async def test_knowledge_base_lifecycle_starts_and_stops_outbox(monkeypatch):
    calls = []

    async def record(name):
        calls.append(name)

    monkeypatch.setattr(
        "app.knowledge_base.tasks.start_processing_queue",
        lambda: record("queue-start"),
    )
    monkeypatch.setattr(
        "app.knowledge_base.tasks.stop_processing_queue",
        lambda: record("queue-stop"),
    )
    monkeypatch.setattr(lifecycle, "warmup_knowledge_base_models", lambda: record("warmup"))
    monkeypatch.setattr(
        "app.knowledge_base.index_outbox.start_index_outbox_worker",
        lambda: record("outbox-start"),
    )
    monkeypatch.setattr(
        "app.knowledge_base.index_outbox.stop_index_outbox_worker",
        lambda: record("outbox-stop"),
    )
    monkeypatch.setattr(lifecycle.asyncio, "sleep", lambda _seconds: record("sleep"))

    await lifecycle.start_knowledge_base_services()
    await lifecycle.stop_knowledge_base_services()

    assert calls.count("outbox-start") == 1
    assert calls.count("outbox-stop") == 1
    assert calls.index("outbox-start") > calls.index("queue-start")
    assert calls.index("outbox-stop") < calls.index("queue-stop")
