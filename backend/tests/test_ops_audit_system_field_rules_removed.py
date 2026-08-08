from app.services.ops_audit.rule_engine import list_rule_catalog
from app.services.ops_work_order_audit_engine import check_rf_forms


REMOVED_SYSTEM_FIELD_RULE_IDS = {
    "RF_PREPARER_EMPTY",
    "RF_CREATEDATE_EMPTY",
}


def test_system_managed_rf_fields_are_not_listed_as_audit_rules():
    rule_ids = {rule["rule_id"] for rule in list_rule_catalog()["rules"]}

    assert not (REMOVED_SYSTEM_FIELD_RULE_IDS & rule_ids)


def test_system_managed_rf_fields_do_not_create_audit_issues():
    issues = []
    order = {
        "WORKINGORDERCODE": "WO-001",
        "DDWORKINGORDERTYPE": "Check",
        "STATIONID": "S001",
    }
    forms = [
        (
            "RF_W_INSPECTION",
            {
                "STATIONID": "S001",
                "PREPARERUSERID": "",
                "CREATEDATE": "",
            },
        )
    ]

    check_rf_forms(order, forms, issues)

    assert not (REMOVED_SYSTEM_FIELD_RULE_IDS & {issue.rule_id for issue in issues})
