from app.api.project_config_routes import runtime_project_config
from app.project_config.loader import load_project_context


def test_runtime_project_config_contains_only_public_manifest_data():
    context = load_project_context("default")

    payload = runtime_project_config(context=context)

    assert payload == {
        "schemaVersion": 1,
        "project": "default",
        "modules": ["core", "legacy"],
        "frontend": {
            "theme": "default",
            "brand_name": "风清气智",
            "features": {},
        },
    }
