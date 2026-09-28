import json

from app.services import ops_work_order_audit


def test_deterministic_audit_config_supports_visual_only_mode(monkeypatch, tmp_path):
    dataset_path = tmp_path / "dataset.json"
    dataset_path.write_text(json.dumps({"orders": []}), encoding="utf-8")
    captured = {}

    def fake_run_rule_engine(dataset, **kwargs):
        captured["dataset"] = dataset
        captured.update(kwargs)
        return {}

    monkeypatch.setattr(
        ops_work_order_audit,
        "modular_run_rule_engine",
        fake_run_rule_engine,
    )

    ops_work_order_audit.run_ops_work_order_deterministic_audit(
        ops_work_order_audit.OpsWorkOrderAuditConfig(
            input_dataset_path=dataset_path,
            output_dir=tmp_path,
            enable_visual=True,
            enable_non_visual=False,
            persist_outputs=False,
        )
    )

    assert captured["enable_visual"] is True
    assert captured["enable_non_visual"] is False
