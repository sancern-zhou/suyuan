import pytest

from scripts.evaluate_scene_graph import calculate_graph_metrics


def test_graph_quality_metrics_from_gold_records():
    metrics = calculate_graph_metrics(
        predicted_entities={("enterprise", "企业A"), ("noise_source", "空压机")},
        gold_entities={
            ("enterprise", "企业A"),
            ("noise_source", "空压机"),
            ("complaint", "投诉1"),
        },
        predicted_relations={("企业A", "has_noise_source", "空压机")},
        gold_relations={("企业A", "has_noise_source", "空压机")},
        evidence_valid=[True],
    )

    assert metrics.entity_precision == 1.0
    assert metrics.entity_recall == pytest.approx(2 / 3)
    assert metrics.relation_f1 == 1.0
    assert metrics.evidence_support_rate == 1.0


def test_graph_quality_metrics_reports_extended_quality_signals():
    metrics = calculate_graph_metrics(
        predicted_entities={("enterprise", "企业A"), ("device", "空压机")},
        gold_entities={("enterprise", "企业A"), ("noise_source", "空压机")},
        predicted_relations={("企业A", "unknown", "空压机")},
        gold_relations={("企业A", "has_noise_source", "空压机")},
        evidence_valid=[True, False],
        entity_link_valid=[True, False],
        duplicate_entities=1,
        schema_violations=1,
        isolated_entities=1,
    )

    assert metrics.type_accuracy == 0.5
    assert metrics.entity_link_accuracy == 0.5
    assert metrics.duplicate_entity_rate == 0.5
    assert metrics.schema_violation_rate == pytest.approx(1 / 3)
    assert metrics.isolated_entity_rate == 0.5
