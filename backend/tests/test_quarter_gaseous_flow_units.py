from app.services.ops_audit.rules.rf_formula_rules import _check_quarter_gas_flow
from app.services.ops_audit.rules.rf_unit_rules import _check_unit_scale
from app.services.ops_audit.rules.rf_quarter_gaseous_flow_units import (
    normalize_quarter_gaseous_flow_to_l_min,
)


def test_high_quarter_gaseous_flow_points_are_normalized_from_ml_min_to_l_min():
    assert normalize_quarter_gaseous_flow_to_l_min("RF_Valuve_60", 6633) == 6.633
    assert normalize_quarter_gaseous_flow_to_l_min("RF_Qa_60", "6639.075") == 6.639075
    assert normalize_quarter_gaseous_flow_to_l_min("RF_Qs_60", "6050.926") == 6.050926


def test_low_quarter_gaseous_flow_points_stay_in_l_min():
    assert normalize_quarter_gaseous_flow_to_l_min("RF_Valuve_50", 56.02) == 56.02
    assert normalize_quarter_gaseous_flow_to_l_min("RF_Qa_50", "55.092") == 55.092
    assert normalize_quarter_gaseous_flow_to_l_min("RF_Qs_50", "50.211") == 50.211


def test_quarter_formula_checks_keep_original_field_units():
    form = {
        "RF_Valuve_60": "6633",
        "RF_Qa_60": "6639.075",
        "F_As1": "1",
        "F_Bs1": "6.075",
    }

    violations = _check_quarter_gas_flow("RF_Q_GaseousFlowCheck", form)

    assert not [item for item in violations if item["formula_id"] == "sample_flow_qa_60"]


def test_quarter_gaseous_flow_unit_rule_compares_normalized_l_min_value():
    violations = _check_unit_scale(
        "RF_Q_GaseousFlowCheck",
        {"RF_Qa_60": "6639.075"},
        {
            "id": "quarter_high_flow",
            "label": "季度气态流量高量程",
            "fixed_unit": "L/min",
            "value_fields": ["RF_Qa_60"],
            "value_normalizer": "quarter_gaseous_flow_l_min",
            "unit_scales": {"L/min": {"min": 0, "max": 20}},
        },
    )

    assert violations == []
