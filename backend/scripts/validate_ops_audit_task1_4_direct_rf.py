import json
from pathlib import Path
from typing import Any

from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.o3_transfer_quality_rules import check_o3_transfer_quality_values
from app.services.ops_audit.rules.o3_value_pass_xls_rules import check_o3_value_pass_xls_values
from app.services.ops_audit.rules.rf_humidity_rules import check_rf_environment_humidity_values
from app.services.ops_audit.rules.rf_range_rules import check_rf_range_values
from app.services.ops_work_order_audit_engine import connect, rows


BASE_DIR = Path("backend_data_registry/ops_audit/task1_4_direct_rf_validation").resolve()
START = "2026-06-01 00:00:00"
END = "2026-06-29 00:00:00"
LIMIT_PER_TABLE = 500


def main() -> None:
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        cursor = conn.cursor()
        co_rows = _query_rf_rows(cursor, "RF_W_GASEOUSCHECK_CO")
        humidity_rows = _query_rf_rows(cursor, "RF_Q_GaseousFlowCheck")
        o3_rows = _query_rf_rows(cursor, "RF_HY_O3VALUEPASS")

    summary = {
        "scope": {
            "create_time_start": START,
            "create_time_end": END,
            "limit_per_table": LIMIT_PER_TABLE,
        },
        "source_counts": {
            "RF_W_GASEOUSCHECK_CO": len(co_rows),
            "RF_Q_GaseousFlowCheck": len(humidity_rows),
            "RF_HY_O3VALUEPASS": len(o3_rows),
        },
        "hits": {
            "co_ld_intercept": _check_co_rows(co_rows),
            "quarter_gaseous_humidity": _check_humidity_rows(humidity_rows),
            "o3_value_pass_fields": _check_o3_field_rows(o3_rows),
            "o3_transfer_quality": _check_o3_quality_rows(o3_rows),
        },
    }
    summary["hit_counts"] = {name: len(items) for name, items in summary["hits"].items()}
    summary["affected_order_counts"] = {
        name: len({item.get("code") for item in items}) for name, items in summary["hits"].items()
    }

    out = BASE_DIR / "direct_rf_validation_summary.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"summary_path": str(out), **summary["source_counts"], "hit_counts": summary["hit_counts"], "affected_order_counts": summary["affected_order_counts"]}, ensure_ascii=False, indent=2))


def _query_rf_rows(cursor: Any, table: str) -> list[dict[str, Any]]:
    return rows(
        cursor,
        f"""
        SELECT TOP {LIMIT_PER_TABLE}
            f.*,
            wo.CREATETIME AS ORDER_CREATETIME,
            wo.FINISHTIME AS ORDER_FINISHTIME,
            wo.MAINTENANCETYPE AS ORDER_MAINTENANCETYPE,
            wo.STATIONID AS ORDER_STATIONID
        FROM dbo.{table} f
        JOIN dbo.working_orders wo
          ON f.WORKINGORDERCODE = wo.WORKINGORDERCODE
        WHERE wo.DDWORKINGORDERSTATUS = 'Finish'
          AND wo.DDWORKINGORDERTYPE = 'Check'
          AND wo.CREATETIME >= ?
          AND wo.CREATETIME < ?
        ORDER BY wo.CREATETIME DESC
        """,
        [START, END],
    )


def _order(form: dict[str, Any]) -> dict[str, Any]:
    return {
        "WORKINGORDERCODE": form.get("WORKINGORDERCODE"),
        "CREATETIME": form.get("ORDER_CREATETIME"),
        "FINISHTIME": form.get("ORDER_FINISHTIME"),
        "MAINTENANCETYPE": form.get("ORDER_MAINTENANCETYPE"),
        "STATIONID": form.get("ORDER_STATIONID") or form.get("STATIONID"),
    }


def _check_co_rows(rows_: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hits = []
    for form in rows_:
        issues: list[Issue] = []
        check_rf_range_values(_order(form), [("RF_W_GASEOUSCHECK_CO", form)], issues)
        for issue in issues:
            if issue.rule_id != "RF_RANGE_OUT_OF_SPEC" or issue.field != "rf.RF_W_GASEOUSCHECK_CO.JGCHECKVALUE":
                continue
            evidence = _loads(issue.evidence)
            if evidence.get("brand") != "LD":
                continue
            hits.append(_hit(form, issue, evidence))
    return hits


def _check_humidity_rows(rows_: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hits = []
    for form in rows_:
        issues: list[Issue] = []
        check_rf_environment_humidity_values(_order(form), [("RF_Q_GaseousFlowCheck", form)], issues)
        for issue in issues:
            if issue.rule_id == "RF_Q_GASEOUS_FLOW_ENV_HUMIDITY_OUT_OF_RANGE":
                hits.append(_hit(form, issue, _loads(issue.evidence)))
    return hits


def _check_o3_field_rows(rows_: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hits = []
    wanted = {"RF_O3_VALUE_PASS_FLOW_VALUE_MISSING", "RF_O3_VALUE_PASS_FIELD_POSITION_SUSPECT"}
    for form in rows_:
        issues: list[Issue] = []
        check_o3_value_pass_xls_values(_order(form), [("RF_HY_O3VALUEPASS", form)], [], [], issues)
        for issue in issues:
            if issue.rule_id in wanted:
                hits.append(_hit(form, issue, _loads(issue.evidence)))
    return hits


def _check_o3_quality_rows(rows_: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hits = []
    for form in rows_:
        issues: list[Issue] = []
        check_o3_transfer_quality_values(_order(form), [("RF_HY_O3VALUEPASS", form)], issues)
        for issue in issues:
            if issue.rule_id == "RF_O3_TRANSFER_RESULT_INVALID":
                hits.append(_hit(form, issue, _loads(issue.evidence)))
    return hits


def _hit(form: dict[str, Any], issue: Issue, evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": form.get("WORKINGORDERCODE"),
        "station_id": form.get("ORDER_STATIONID") or form.get("STATIONID"),
        "maintenance_type": form.get("ORDER_MAINTENANCETYPE"),
        "created_at": form.get("ORDER_CREATETIME"),
        "rule_id": issue.rule_id,
        "field": issue.field,
        "message": issue.message,
        "evidence": evidence,
    }


def _loads(value: str) -> dict[str, Any]:
    try:
        return json.loads(value)
    except Exception:
        return {"raw": value}


if __name__ == "__main__":
    main()
