from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_legacy_cognitive_map_implementation_and_data_are_absent():
    removed = (
        BACKEND_ROOT / "app/agent/cognition",
        BACKEND_ROOT / "scripts/migrate_cognitive_maps_to_knowledge_bases.py",
        BACKEND_ROOT / "backend_data_registry/cognitive_maps",
    )
    assert all(not path.exists() for path in removed)
