from __future__ import annotations

from app.services.ops_audit.rules.o3_value_pass_xls_rules import check_o3_value_pass_xls_values


def test_o3_value_pass_xls_unavailable_local_path_is_not_reported() -> None:
    issues = []

    check_o3_value_pass_xls_values(
        {"WORKINGORDERCODE": "CH_TEST"},
        [
            (
                "RF_HY_O3VALUEPASS",
                {
                    "WORKINGORDERCODE": "CH_TEST",
                    "DEVICEDELIVERMODEL": "1.001",
                    "DELIVERFC": "-0.079",
                    "DENSITY1VALUE": "0.1",
                },
            )
        ],
        [{"FILENAME": "o3.xls", "FILEPATH": "/WebFiles/NewFiles/o3/missing.xls"}],
        [],
        issues,
    )

    assert issues == []

