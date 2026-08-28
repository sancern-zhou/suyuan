import pytest

from app.services.jiangsu_feedback_loop import FeedbackLoopStore


def test_station_fault_workflow_uses_business_outcomes(tmp_path):
    store = FeedbackLoopStore(tmp_path)

    store.agent_recommendation(
        case_id="jiangsu:fault:event-1",
        scenario="station_fault_diagnosis",
        source_record_id="event-1",
        recommendation_id="draft-1",
        subject={"station_code": "1002A"},
        payload={"root_cause": "采集链路异常"},
    )
    store.human_review(
        case_id="jiangsu:fault:event-1",
        scenario="station_fault_diagnosis",
        decision="modified",
        actor_id="operator-1",
        payload={"changed_fields": ["remediation_plan"]},
    )
    store.business_action(
        case_id="jiangsu:fault:event-1",
        scenario="station_fault_diagnosis",
        action="create_fault_work_order",
        outcome="created",
        source_record_id="WO-1",
    )
    store.verification(
        case_id="jiangsu:fault:event-1",
        scenario="station_fault_diagnosis",
        outcome="resolved",
        source_record_id="WO-1",
        payload={"recovery_hours": 3.5},
    )

    case = store.materialize_case("jiangsu:fault:event-1")
    assert case is not None
    assert case.status == "closed"
    assert case.event_count == 5  # create + recommendation + review + action + verification

    metrics = store.metrics(scenario="station_fault_diagnosis")
    assert metrics["case_count"] == 1
    assert metrics["acceptance_rate"] == 1
    assert metrics["verification_success_rate"] == 1
    assert metrics["closed_case_count"] == 1


def test_invalid_workflow_transition_is_rejected(tmp_path):
    store = FeedbackLoopStore(tmp_path)
    store.ensure_case(case_id="case-1", scenario="station_fault_diagnosis")

    with pytest.raises(ValueError, match="不允许"):
        store.verification(
            case_id="case-1",
            scenario="station_fault_diagnosis",
            outcome="resolved",
        )


def test_audit_metrics_compare_agent_items_with_final_issue_list(tmp_path):
    store = FeedbackLoopStore(tmp_path)
    store.agent_recommendation(
        case_id="jiangsu:audit:run-1",
        scenario="ops_work_order_audit",
        source_record_id="dataset-1",
        recommendation_id="audit-1",
        payload={"ai_item_ids": ["a", "b", "c"]},
    )
    store.human_review(
        case_id="jiangsu:audit:run-1",
        scenario="ops_work_order_audit",
        decision="modified",
        payload={"ai_item_ids": ["a", "b", "c"], "final_item_ids": ["a", "b", "d", "e"]},
    )

    metrics = store.metrics(scenario="ops_work_order_audit")
    assert metrics["audit_labeled_review_count"] == 1
    assert metrics["issue_precision"] == pytest.approx(2 / 3)
    assert metrics["issue_recall"] == pytest.approx(2 / 4)
    assert metrics["issue_f1"] == pytest.approx(4 / 7)
