from app.services.ops_audit.rules.o3_transfer_quality_rules import check_o3_transfer_quality_values


def test_o3_transfer_quality_is_disabled_until_rf_field_mapping_is_confirmed():
    issues = []
    order = {"WORKINGORDERCODE": "CH2606171781674497475"}
    form = {
        "WORKINGORDERCODE": "CH2606171781674497475",
        "DELIVER1VALUE": "398",
        "WORKDENSITY1VALUE": "399",
        "DELIVER2VALUE": "",
        "WORKDENSITY2VALUE": "",
        "DELIVER3VALUE": "/",
        "WORKDENSITY3VALUE": "/",
    }

    check_o3_transfer_quality_values(order, [("RF_HY_O3VALUEPASS", form)], issues)

    assert issues == []


def test_o3_transfer_quality_does_not_compare_current_transposed_template_fields():
    issues = []
    order = {"WORKINGORDERCODE": "WO-O3-TRANSFER-DIFF"}
    form = {
        "WORKINGORDERCODE": "WO-O3-TRANSFER-DIFF",
        "DELIVER1VALUE": "398",
        "WORKDENSITY1VALUE": "400",
        "DELIVER2VALUE": "199",
        "WORKDENSITY2VALUE": "205",
        "DELIVER3VALUE": "99",
        "WORKDENSITY3VALUE": "100",
    }

    check_o3_transfer_quality_values(order, [("RF_HY_O3VALUEPASS", form)], issues)

    assert issues == []
