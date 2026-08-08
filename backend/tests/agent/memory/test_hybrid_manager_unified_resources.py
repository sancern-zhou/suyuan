from types import SimpleNamespace

from app.agent.memory.hybrid_manager import HybridMemoryManager


def _manager() -> HybridMemoryManager:
    manager = HybridMemoryManager.__new__(HybridMemoryManager)
    manager.session = SimpleNamespace(data_files={})
    return manager


def test_unified_resource_observation_is_preserved_without_legacy_registration():
    observation = {
        "success": True,
        "data": {"chunks": [1, 2]},
        "resources": [
            {
                "kind": "file",
                "locator": {"path": "/tmp/materialized.pdf"},
            }
        ],
        "resource_tracking": {"durable": True, "resource_ids": ["pdf-1"]},
    }

    assert _manager()._process_observation(observation, {}) is observation


def test_inline_structured_data_does_not_require_a_file_resource():
    observation = {"success": True, "data": [{"value": 1}]}

    assert _manager()._process_observation(observation, {}) is observation


def test_resource_locator_paths_are_discovered_from_unified_declarations():
    refs = _manager()._extract_observation_refs(
        {"resources": [{"locator": {"path": "/tmp/materialized.pdf"}}]}
    )

    assert refs == {
        "file_paths": ["/tmp/materialized.pdf"],
        "report_file_paths": [],
    }
