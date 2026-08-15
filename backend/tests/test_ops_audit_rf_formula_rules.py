from app.services.ops_audit.rules.rf_formula_rules import _standard_flow_formula


def test_quarter_gas_standard_flow_uses_api_0c_standard_temperature():
    form = {
        "CalculationMethod": "API",
        "RF_Qa_60": "6078.177",
        "RF_Qs_60": "5448.087",
        "P_Pa": "755.50",
        "T_Ta": "29.77",
    }

    violations = _standard_flow_formula(
        "RF_Q_GaseousFlowCheck",
        form,
        "60",
        abs_tol=0.2,
    )

    assert violations == []


def test_quarter_gas_standard_flow_uses_te25_25c_standard_temperature():
    form = {
        "CalculationMethod": "TE_25",
        "RF_Qa_60": "6078.177",
        "RF_Qs_60": "5946.996",
        "P_Pa": "755.50",
        "T_Ta": "29.77",
    }

    violations = _standard_flow_formula(
        "RF_Q_GaseousFlowCheck",
        form,
        "60",
        abs_tol=0.2,
    )

    assert violations == []


def test_quarter_gas_standard_flow_uses_src_uncorrected_flow():
    form = {
        "CalculationMethod": "SRC",
        "RF_Qa_85": "8384.433",
        "RF_Qs_85": "8384.433",
        "P_Pa": "753.5",
        "T_Ta": "23.7",
    }

    violations = _standard_flow_formula(
        "RF_Q_GaseousFlowCheck",
        form,
        "85",
        abs_tol=0.2,
    )

    assert violations == []


def test_quarter_gas_standard_flow_flags_mismatch_for_declared_method():
    form = {
        "CalculationMethod": "API",
        "RF_Qa_85": "8655.167",
        "RF_Qs_85": "8538.794",
        "P_Pa": "754.26",
        "T_Ta": "26.78",
    }

    violations = _standard_flow_formula(
        "RF_Q_GaseousFlowCheck",
        form,
        "85",
        abs_tol=0.2,
    )

    assert violations
    assert violations[0]["formula_id"] == "standard_flow_qs_85"
    assert round(violations[0]["expected"], 3) == 7822.452


def test_quarter_gas_standard_flow_matches_raoping_chengbei_sample():
    form = {
        "CalculationMethod": "API",
        "RF_Qa_85": "9396.731",
        "RF_Qs_85": "8457.882",
        "P_Pa": "753.2",
        "T_Ta": "27.59",
    }

    violations = _standard_flow_formula(
        "RF_Q_GaseousFlowCheck",
        form,
        "85",
        abs_tol=0.2,
    )

    assert violations == []
