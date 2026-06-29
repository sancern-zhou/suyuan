from app.services.ops_audit.rules.rf_position_rules import check_rf_field_positions


def test_monthly_flow_error_sign_mismatch_does_not_imply_swapped_fields():
    issues = []
    order = {"WORKINGORDERCODE": "CH2606191781834867744"}
    form = {
        "WORKINGORDERCODE": "CH2606191781834867744",
        "DISPLAYVALUECO": "1.113",
        "MEASUREDVALUECO": "1.123",
        "MEASUREDERRORCO": "0.89%",
    }

    check_rf_field_positions(order, [("RF_M_GASEOUSFLOWCHECK", form)], issues)

    matched = [issue for issue in issues if issue.rule_id == "RF_FIELD_POSITION_SUSPECT"]
    assert matched == []
