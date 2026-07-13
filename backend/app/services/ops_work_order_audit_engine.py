#!/usr/bin/env python3
"""Fetch and audit recent finished operations work orders.

The script intentionally keeps the first pass deterministic: it only checks
field completeness, status/time consistency, workflow coverage, and obvious RF
form quality issues. Semantic judgement can consume the produced JSON later.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pyodbc


ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from config.settings import Settings  # noqa: E402
from app.services.ops_audit.config import (  # noqa: E402
    load_brand_aliases,
    load_device_identity_profiles,
    load_low_value_remarks,
    load_rf_field_profiles,
)
from app.services.ops_audit.models import Issue  # noqa: E402
from app.services.ops_audit.report_writer import write_report as modular_write_report  # noqa: E402
from app.services.ops_audit.rule_taxonomy import is_excluded_rule  # noqa: E402
from app.services.ops_audit.rules.device_consistency_rules import (  # noqa: E402
    check_device_identity_consistency,
    merge_device_history,
)
from app.services.ops_audit.rules.base import add_issue  # noqa: E402
from app.services.ops_audit.rules.attachment_rules import (  # noqa: E402
    attachment_review_candidate_rule_ids,
    check_attachment_requirements,
)
from app.services.ops_audit.rules.attachment_ocr_rules import build_flow_visual_tasks, run_flow_visual_task  # noqa: E402
from app.services.ops_audit.rules.multipoint_curve_visual_rules import (  # noqa: E402
    build_multipoint_curve_visual_tasks,
    run_multipoint_curve_visual_task,
)
from app.services.ops_audit.semantic.ocr_adapter import flow_visual_provider_summary  # noqa: E402
from app.services.ops_audit.rules.lifecycle_rules import check_lifecycle_closure as check_modular_lifecycle_closure  # noqa: E402
from app.services.ops_audit.rules.o3_transfer_quality_rules import check_o3_transfer_quality_values  # noqa: E402
from app.services.ops_audit.rules.o3_value_pass_xls_rules import check_o3_value_pass_xls_values  # noqa: E402
from app.services.ops_audit.rules.rf_abnormal_remark_rules import check_rf_abnormal_remarks  # noqa: E402
from app.services.ops_audit.rules.rf_calibration_date_rules import check_rf_calibration_dates  # noqa: E402
from app.services.ops_audit.rules.rf_enum_rules import check_rf_enum_values  # noqa: E402
from app.services.ops_audit.rules.rf_formula_rules import check_rf_formula_values  # noqa: E402
from app.services.ops_audit.rules.rf_humidity_rules import check_rf_environment_humidity_values  # noqa: E402
from app.services.ops_audit.rules.rf_multipoint_rules import check_rf_multipoint_values  # noqa: E402
from app.services.ops_audit.rules.rf_pm_pressure_rules import check_rf_pm_pressure_values  # noqa: E402
from app.services.ops_audit.rules.rf_position_rules import check_rf_field_positions  # noqa: E402
from app.services.ops_audit.rules.rf_range_rules import check_rf_range_values  # noqa: E402
from app.services.ops_audit.rules.rf_required_rules import check_rf_required_fields  # noqa: E402
from app.services.ops_audit.rules.rf_time_rules import check_rf_time_ranges  # noqa: E402
from app.services.ops_audit.rules.rf_unit_rules import check_rf_unit_values  # noqa: E402
from app.services.ops_audit.rules.rf_visibility_rules import check_rf_visibility_values  # noqa: E402
from app.services.ops_audit.rules.workflow_rules import check_workflow_completeness  # noqa: E402
from app.services.ops_audit.scoring import (  # noqa: E402
    COMMON_PATTERN_ELIGIBLE_RULES,
    COMMON_PATTERN_MIN_AFFECTED_ORDERS,
    COMMON_PATTERN_ORDER_RATIO,
    CRITICAL_HARD_ERROR_RULES,
    HARD_ERROR_RULES,
    SEVERITY_PENALTY,
    apply_rule_pattern_assessment as modular_apply_rule_pattern_assessment,
    classify_rule_patterns as modular_classify_rule_patterns,
)
from app.services.ops_audit.semantic_candidates import build_semantic_candidates as modular_build_semantic_candidates  # noqa: E402
from app.services.ops_audit.semantic.reviewer import build_semantic_review_results as modular_build_semantic_review_results  # noqa: E402
from app.services.ops_audit.semantic.reviewer import build_semantic_review_tasks as modular_build_semantic_review_tasks  # noqa: E402


OUTPUT_DIR = BACKEND / "backend_data_registry" / "memory" / "ops" / "audit"
logger = logging.getLogger(__name__)

RF_TABLES = [
    "RF_W_GASEOUSCHECK_CO",
    "RF_W_GASEOUSCHECK_NOX",
    "RF_W_GASEOUSCHECK_O3",
    "RF_W_GASEOUSCHECK_SO2",
    "RF_W_GrainCalibrationCheck_PM10",
    "RF_W_GrainCalibrationCheck_PM25",
    "RF_W_GrainCalibrationCheckAttach",
    "RF_W_INSPECTION",
    "RF_W_INSPECTIONSUMMARY",
    "RF_W_LONGOPTICALPATH",
    "RF_W_OTHERDEVICECHECK",
    "RF_W_PMCHECK",
    "RF_W_STANDARD_ALL",
    "RF_TW_CleanCuttingHead",
    "RF_TW_PmFlowCalibrate",
    "RF_TW_PmFlowCheck",
    "RF_M_GASEOUSCALICHECK",
    "RF_M_GASEOUSCALIDEVICECHECK",
    "RF_M_GASEOUSFLOWCHECK",
    "RF_M_MANUALCOMPARISON",
    "RF_M_MANUALCOMPARISONDETAIL",
    "RF_M_MEMBRANEWEIGHING",
    "RF_M_PMDEVICEMAINTAIN",
    "RF_M_STATIONDEVICEMAINTAIN",
    "RF_M_StationMaintainCheck",
    "RF_Q_GASEOUSMULTIPOINT_CO",
    "RF_Q_GASEOUSMULTIPOINT_NO2",
    "RF_Q_GASEOUSMULTIPOINT_O3",
    "RF_Q_GASEOUSMULTIPOINT_SO2",
    "RF_Q_GASEOUSPRECISION_CO",
    "RF_Q_GASEOUSPRECISION_NO2",
    "RF_Q_GASEOUSPRECISION_O3",
    "RF_Q_GASEOUSPRECISION_SO2",
    "RF_Q_GaseousFlowCheck",
    "RF_Q_LONGOPTICALPATH_NO2",
    "RF_Q_LONGOPTICALPATH_O3",
    "RF_Q_LONGOPTICALPATH_SO2",
    "RF_Q_PM10RUNSTATUSCHECK",
    "RF_Q_PM25RUNSTATUSCHECK",
    "RF_Q_PMPRESSURE",
    "RF_Q_STATIONDEVICECLEAN",
    "RF_Q_StationMaintainCheck",
    "RF_Y_DEVICECHANGE",
    "RF_Y_DEVICEREPAIR",
    "RF_Y_PreventiveMaintenance",
    "RF_SEC_INSPECTION",
    "RF_SEC_INSTRUMENTRECORD",
    "RF_SEC_MONITORINGCHECK",
    "RF_PM1MonitorInspection",
    "RF_BCMonitorInspection",
    "SEC_CHECKSCORE",
    "SEC_CHECKSCORE_SX",
    "SEC_CHECKSCORE_SXNEW",
    "Sup_RF_MonthNepheloMeterCheck",
    "Sup_RF_NepheloMeterCalibration",
    "RF_HY_EnvironmentHumidity",
    "RF_HY_GASEOUSCALIDEVICECHECK",
    "RF_HY_STATIONDEVICEMAINTAIN",
    "RF_HY_StationMaintainCheck",
    "RF_HY_O3VALUEPASS",
    "RF_HY_VISIBILITYCALI",
    "RF_HY_NOXCONVERSIONRATE",
    "qa_appraisalcalibrationlog",
    "qa_appraisalcalibrationmanagem",
    "qa_calibrationpass",
    "qa_ozonecalibration",
    "qa_ozonetransfer",
    "qa_standardmateriallog",
    "qa_standardmaterialstorage",
]

LOW_VALUE_REMARKS = load_low_value_remarks()
BRAND_ALIASES = load_brand_aliases()
RF_FIELD_PROFILES = load_rf_field_profiles()
DEVICE_IDENTITY_PROFILE = load_device_identity_profiles()
EXCLUDED_AUDIT_ORDER_TYPES = {"SupCheck"}

FORM_RANGE_PROFILES = {
    "RF_W_GASEOUSCHECK_CO": {
        "form_name": "一氧化碳（CO）分析仪运行状况检查记录表（每周）",
        "pollutant_type": "CO",
        "enabled_brands": {"THERMO"},
        "fields": {
            "sample_pressure": {
                "label": "采样压力",
                "db_field": "CYYLCHECKVALUE",
                "ranges": {
                    "THERMO": {"min": 250, "max": 1000, "unit": "mmHg"},
                },
            },
            "sample_flow": {
                "label": "采样流量",
                "db_field": "CYLLCHECKVALUE",
                "ranges": {
                    "THERMO": {"min": 0.350, "max": 1.500, "unit": "L/min"},
                },
            },
            "sample_temperature": {
                "label": "样品温度",
                "db_field": "FYCHECKVALUE",
                "ranges": {
                    "THERMO": {"min": 8, "max": 47, "unit": "℃"},
                },
            },
            "optical_temperature": {
                "label": "光室温度",
                "db_field": "GSWDCHECKVALUE",
                "ranges": {
                    "THERMO": {"min": 40, "max": 52, "unit": "℃"},
                },
            },
            "slope": {
                "label": "斜率",
                "db_field": "YLCHECKVALUE",
                "ranges": {
                    "THERMO": {"min": 0.500, "max": 2.000},
                },
            },
            "offset": {
                "label": "截距",
                "db_field": "JGCHECKVALUE",
                "ranges": {
                    "THERMO": {"min": -10.75, "max": None, "operator": ">"},
                },
            },
        },
    },
    "RF_W_GASEOUSCHECK_O3": {
        "form_name": "臭氧（O3）分析仪运行状况检查记录表（每周）",
        "pollutant_type": "O3",
        "enabled_brands": {"THERMO"},
        "fields": {
            "measurement_signal_a": {
                "label": "测量信号A",
                "db_field": "GYCHECKVALUE",
                "ranges": {
                    "THERMO": {"min": 45000, "max": 150000, "unit": "HZ"},
                },
            },
            "measurement_signal_b": {
                "label": "测量信号B",
                "db_field": "GYBCHECKVALUE",
                "ranges": {
                    "THERMO": {"min": 45000, "max": 150000, "unit": "HZ"},
                },
            },
            "reference_signal_a": {
                "label": "参比信号A",
                "db_field": "ZWDCHECKVALUE",
                "ranges": {
                    "THERMO": {"min": 45000, "max": 150000, "unit": "HZ"},
                },
            },
            "reference_signal_b": {
                "label": "参比信号B",
                "db_field": "ZWDBCHECKVALUE",
                "ranges": {
                    "THERMO": {"min": 45000, "max": 150000, "unit": "HZ"},
                },
            },
            "sample_pressure": {
                "label": "压力",
                "db_field": "CYYLCHECKVALUE",
                "ranges": {
                    "THERMO": {"min": 200, "max": 1000, "unit": "mmHg"},
                },
            },
            "sample_flow_a": {
                "label": "采样流量A",
                "db_field": "CYLLCHECKVALUE",
                "ranges": {
                    "THERMO": {"min": 0.400, "max": 1.400, "unit": "L/min"},
                },
            },
            "sample_flow_b": {
                "label": "采样流量B",
                "db_field": "CYLLBCHECKVALUE",
                "ranges": {
                    "THERMO": {"min": 0.400, "max": 1.400, "unit": "L/min"},
                },
            },
            "sample_temperature": {
                "label": "样品温度",
                "db_field": "FYCHECKVALUE",
                "ranges": {
                    "THERMO": {"min": 15, "max": 45, "unit": "℃"},
                },
            },
            "slope": {
                "label": "斜率",
                "db_field": "YLCHECKVALUE",
                "ranges": {
                    "THERMO": {"min": 0.500, "max": 2.000},
                },
            },
            "offset": {
                "label": "截距",
                "db_field": "JGCHECKVALUE",
                "ranges": {
                    "THERMO": {"min": -26.5, "max": None, "operator": ">"},
                },
            },
        },
    },
    "RF_W_GASEOUSCHECK_NOX": {
        "form_name": "氮氧化物（NOx）分析仪运行状况检查记录表（每周）",
        "pollutant_type": "NOX",
        "enabled_brands": {"API"},
        "fields": {
            "sample_flow": {
                "label": "采样流量",
                "db_field": "CYLLCHECKVALUE",
                "ranges": {
                    "API": {"min": 450, "max": 550, "unit": "ml/min"},
                },
            },
            "ozone_flow": {
                "label": "臭氧流量",
                "db_field": "CYLLIANGCHECKVALUE",
                "ranges": {
                    "API": {"min": 65, "max": 95, "unit": "ml/min"},
                },
            },
            "reference_pmt_signal": {
                "label": "参考PMT信号",
                "db_field": "PMTCHECKVALUE",
                "ranges": {
                    "API": {"min": 0, "max": 5000, "unit": "mV"},
                },
            },
            "high_voltage": {
                "label": "高压电源",
                "db_field": "GYCHECKVALUE",
                "ranges": {
                    "API": {"min": 450, "max": 900, "unit": "V"},
                },
            },
            "reaction_temperature": {
                "label": "反应室温度",
                "db_field": "FYCHECKVALUE",
                "ranges": {
                    "API": {"min": 49, "max": 51, "unit": "℃"},
                },
            },
            "converter_temperature": {
                "label": "转化炉温度",
                "db_field": "ZHLCHECKVALUE",
                "ranges": {
                    "API": {"min": 310, "max": 320, "unit": "℃"},
                },
            },
            "reaction_pressure": {
                "label": "反应室压力",
                "db_field": "FYSHICHECKVALUE",
                "ranges": {
                    "API": {"max": 10, "operator": "<", "unit": "In-Hg-A"},
                },
            },
            "sample_pressure": {
                "label": "采样压力",
                "db_field": "CYYLCHECKVALUE",
                "ranges": {
                    "API": {"min": 25, "max": 30, "unit": "In-Hg-A"},
                },
            },
            "nox_slope": {
                "label": "NOx斜率",
                "db_field": "NOXYLCHECKVALUE",
                "ranges": {
                    "API": {"min": 0.7, "max": 1.3},
                },
            },
            "nox_offset": {
                "label": "NOx截距",
                "db_field": "NOXJGCHECKVALUE",
                "ranges": {
                    "API": {"min": -10, "max": 150, "unit": "mV"},
                },
            },
            "no_slope": {
                "label": "NO斜率",
                "db_field": "NOYLCHECKVALUE",
                "ranges": {
                    "API": {"min": 0.7, "max": 1.3},
                },
            },
            "no_offset": {
                "label": "NO截距",
                "db_field": "NOJGCHECKVALUE",
                "ranges": {
                    "API": {"min": -50, "max": 150, "unit": "mV"},
                },
            },
        },
    },
    "RF_W_GASEOUSCHECK_SO2": {
        "form_name": "二氧化硫（SO2）分析仪运行状况检查记录表（每周）",
        "pollutant_type": "SO2",
        "enabled_brands": {"THERMO"},
        "fields": {
            "sample_pressure": {
                "label": "采样压力",
                "db_field": "CYYLCHECKVALUE",
                "ranges": {
                    "THERMO": {"min": 400, "max": 1000, "unit": "mmHg"},
                },
            },
            "sample_flow": {
                "label": "室采样流量",
                "db_field": "CYLLCHECKVALUE",
                "ranges": {
                    "THERMO": {"min": 0.350, "max": 0.750, "unit": "L/min"},
                },
            },
            "uv_lamp_intensity": {
                "label": "紫外灯光强",
                "db_field": "ZWDCHECKVALUE",
                "ranges": {
                    "THERMO": {"min": 40, "max": 100, "unit": "%"},
                },
            },
            "slope": {
                "label": "斜率",
                "db_field": "YLCHECKVALUE",
                "ranges": {
                    "THERMO": {"min": 0.500, "max": 2.000},
                },
            },
            "offset": {
                "label": "截距",
                "db_field": "JGCHECKVALUE",
                "ranges": {
                    "THERMO": {"min": 0, "max": None, "operator": ">"},
                },
            },
            "high_voltage": {
                "label": "高压电源",
                "db_field": "GYCHECKVALUE",
                "ranges": {
                    "THERMO": {"min": -1200, "max": -500, "unit": "V"},
                },
            },
            "reaction_temperature": {
                "label": "反应室温度",
                "db_field": "FYCHECKVALUE",
                "ranges": {
                    "THERMO": {"min": 43, "max": 47, "unit": "℃"},
                },
            },
        },
    },
    "RF_W_PMCHECK": {
        "form_name": "颗粒物 PM10/PM2.5 自动监测分析仪运行状况检查记录（每周）",
        "pollutant_types": {"PM10", "PM2.5", "PM25"},
        "enabled_brands": {"THERMO"},
        "fields": {
            "main_flow": {
                "label": "流量(Main Flow)",
                "db_field": "MAINFLOWVALUE",
                "optional_when_remark_contains": {"无流量检查", "无测流量"},
                "ranges": {
                    "THERMO": {"min": 15.87, "max": 17.54, "unit": "L/min"},
                },
            },
            "air_temperature": {
                "label": "采样管温度(Air.Temp)",
                "db_field": "AIRTEMPVALUE",
                "ranges": {
                    "THERMO": {"max": 50, "operator": "<=", "unit": "℃"},
                },
            },
        },
    }
}

def connect() -> pyodbc.Connection:
    settings = Settings()
    conn_str = re.sub(
        r"DATABASE=\w+",
        "DATABASE=AirPollutionAnalysis",
        settings.sqlserver_connection_string,
        flags=re.IGNORECASE,
    )
    return pyodbc.connect(conn_str, timeout=30)


def rows(cursor: pyodbc.Cursor, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    cursor.execute(sql, *(params or []))
    columns = [column[0] for column in cursor.description]
    result = []
    for row in cursor.fetchall():
        record = dict(zip(columns, row))
        for key, value in list(record.items()):
            if isinstance(value, datetime):
                record[key] = value.strftime("%Y-%m-%d %H:%M:%S")
            elif isinstance(value, Decimal):
                record[key] = float(value)
            elif isinstance(value, bytes):
                record[key] = value.hex()
        result.append(record)
    return result


def select_final_rf_form_versions(table: str, forms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return RF rows unchanged while validating whether version filtering is needed."""

    return forms


def _select_rf_forms_with_filter_stats(
    table: str,
    forms: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    selected = select_final_rf_form_versions(table, forms)
    raw_count = len(forms)
    selected_count = len(selected)
    query_error = next((form.get("_query_error") for form in selected if form.get("_query_error")), None)
    stats = {
        "raw_count": raw_count,
        "selected_count": selected_count,
        "filtered_count": max(0, raw_count - selected_count),
        "query_error": query_error,
    }
    logger.info(
        "ops_audit_rf_form_filter_stats table=%s raw_count=%s selected_count=%s filtered_count=%s query_error=%s",
        table,
        stats["raw_count"],
        stats["selected_count"],
        stats["filtered_count"],
        stats["query_error"],
        extra={
            "table": table,
            "raw_count": stats["raw_count"],
            "selected_count": stats["selected_count"],
            "filtered_count": stats["filtered_count"],
            "query_error": stats["query_error"],
        },
    )
    return selected, stats


def _rf_business_identity(table: str, form: dict[str, Any]) -> tuple[str, Any] | None:
    normalized_table = re.sub(r"[^A-Z0-9]", "", table.upper())
    normalized_without_pollutant = re.sub(r"(CO|NOX|NO2|O3|SO2|PM10|PM25)$", "", normalized_table)
    preferred_keys = [
        f"{normalized_table}ID",
        f"{normalized_without_pollutant}ID",
    ]
    excluded = {
        "WORKINGORDERID",
        "WORKINGORDERCODE",
        "STATIONID",
        "DEVICEID",
        "AREAID",
        "OPERATIONSUNITID",
        "PREPARERUSERID",
        "REVIEWUSERID",
        "AUDITORUSERID",
    }
    for key in preferred_keys:
        if key in form and _has_value(form.get(key)):
            return (key, form.get(key))
    for key, value in form.items():
        upper_key = key.upper()
        if upper_key.endswith("ID") and upper_key not in excluded and _has_value(value):
            return (key, value)
    return None


def _deduplicate_rf_forms(forms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[tuple[str, str], ...]] = set()
    deduplicated: list[dict[str, Any]] = []
    for form in forms:
        signature = tuple(sorted((str(key), str(value)) for key, value in form.items()))
        if signature in seen:
            continue
        seen.add(signature)
        deduplicated.append(form)
    return deduplicated


def _has_value(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


@dataclass
class WorkOrderDatasetFilter:
    limit: int = 200
    order_statuses: list[str] | None = None  # 工单状态列表，支持 Finish/Doing/Wait/Invalid，不填默认查所有状态工单
    create_time_start: str | None = None
    create_time_end: str | None = None
    finish_time_start: str | None = None
    finish_time_end: str | None = None
    station_ids: list[str] | None = None
    order_types: list[str] | None = None
    maintenance_types: list[str] | None = None
    working_order_codes: list[str] | None = None


def _clean_values(values: list[str] | None) -> list[str]:
    if not values:
        return []
    return [str(value).strip() for value in values if str(value).strip()]


def effective_audit_order_types(order_types: list[str] | None) -> list[str] | None:
    if order_types is None:
        return None
    return [order_type for order_type in _clean_values(order_types) if order_type not in EXCLUDED_AUDIT_ORDER_TYPES]


def _station_meta_by_id(stations: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    meta: dict[str, dict[str, Any]] = {}
    for station in stations:
        station_id = _first_non_empty(
            station,
            ["STATIONID", "StationID", "station_id", "stationid", "ID", "id"],
        )
        if station_id is None:
            continue
        meta[str(station_id)] = {
            "station_name": _first_non_empty(
                station,
                ["STATIONNAME", "StationName", "station_name", "stationname", "NAME", "Name", "name"],
            ),
            "operation_unit": _first_non_empty(
                station,
                [
                    "OPERATIONUNIT",
                    "OPERATION_UNIT",
                    "OperationUnit",
                    "operation_unit",
                    "operationUnit",
                    "MAINTENANCEUNIT",
                    "MAINTENANCE_UNIT",
                    "maintenance_unit",
                    "运维单位",
                ],
            ),
        }
    return meta


def _first_non_empty(record: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = record.get(key)
        if value is not None and str(value).strip():
            return value
    return None


def _in_clause(column: str, values: list[str], params: list[Any]) -> str:
    placeholders = ", ".join("?" for _ in values)
    params.extend(values)
    return f"{column} IN ({placeholders})"


def _not_in_clause(column: str, values: list[str], params: list[Any]) -> str:
    placeholders = ", ".join("?" for _ in values)
    params.extend(values)
    return f"({column} IS NULL OR {column} NOT IN ({placeholders}))"


def _normalize_dataset_filter(filter_config: WorkOrderDatasetFilter | int) -> WorkOrderDatasetFilter:
    if isinstance(filter_config, int):
        return WorkOrderDatasetFilter(limit=filter_config)
    return filter_config


def fetch_dataset(filter_config: WorkOrderDatasetFilter | int) -> dict[str, Any]:
    filters = _normalize_dataset_filter(filter_config)
    limit = max(1, min(int(filters.limit or 200), 3000))
    station_ids = _clean_values(filters.station_ids)
    requested_order_types = _clean_values(filters.order_types)
    order_types = effective_audit_order_types(requested_order_types)
    maintenance_types = _clean_values(filters.maintenance_types)
    working_order_codes = _clean_values(filters.working_order_codes)
    order_statuses = _clean_values(filters.order_statuses)
    if working_order_codes:
        limit = max(limit, min(len(working_order_codes), 3000))

    order_params: list[Any] = []
    where_parts: list[str] = []

    # 状态过滤：传入状态时按状态筛选；不传时保留所有状态。
    if order_statuses:
        where_parts.append(_in_clause("DDWORKINGORDERSTATUS", order_statuses, order_params))

    if filters.create_time_start:
        where_parts.append("CREATETIME >= ?")
        order_params.append(filters.create_time_start)
    if filters.create_time_end:
        where_parts.append("CREATETIME < ?")
        order_params.append(filters.create_time_end)
    if filters.finish_time_start:
        where_parts.append("FINISHTIME >= ?")
        order_params.append(filters.finish_time_start)
    if filters.finish_time_end:
        where_parts.append("FINISHTIME < ?")
        order_params.append(filters.finish_time_end)
    if station_ids:
        where_parts.append(_in_clause("STATIONID", station_ids, order_params))
    if order_types:
        where_parts.append(_in_clause("DDWORKINGORDERTYPE", order_types, order_params))
    elif requested_order_types:
        where_parts.append("1 = 0")
    where_parts.append(_not_in_clause("DDWORKINGORDERTYPE", sorted(EXCLUDED_AUDIT_ORDER_TYPES), order_params))
    if maintenance_types:
        where_parts.append(_in_clause("MAINTENANCETYPE", maintenance_types, order_params))
    if working_order_codes:
        where_parts.append(_in_clause("WORKINGORDERCODE", working_order_codes, order_params))

    where_sql = " AND ".join(where_parts) if where_parts else "1 = 1"
    with connect() as conn:
        cursor = conn.cursor()
        orders = rows(
            cursor,
            f"""
            SELECT TOP {limit}
                WORKINGORDERID, STATIONID, DEVICEID, WORKINGORDERCODE,
                CREATETIME, UPDATETIME, DDORDERCREATETYPE, DDWORKINGORDERTYPE,
                DDURGENCYTYPE, DDWORKINGORDERSTATUS, DDISSUEDTYPE, ORDERTITLE,
                ORDERCONTENT, CURRENTWORKFLOWSTATUS, CURRENTWORKFLOWPOINT,
                FINISHTIME, PLANFINISHTIME, MAINTENANCETYPE, TOTALOVERTIME,
                TOTALEXPENSE
            FROM dbo.working_orders
            WHERE {where_sql}
            ORDER BY FINISHTIME DESC, CREATETIME DESC
            """,
            order_params,
        )
        codes = [row["WORKINGORDERCODE"] for row in orders if row.get("WORKINGORDERCODE")]
        if not codes:
            return {
                "query_info": {
                    "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "database": "AirPollutionAnalysis",
                    "order_filter": {
                        "status": order_statuses or "all",
                        "create_time_start": filters.create_time_start,
                        "create_time_end": filters.create_time_end,
                        "finish_time_start": filters.finish_time_start,
                        "finish_time_end": filters.finish_time_end,
                        "station_ids": station_ids,
                        "order_types": order_types,
                        "maintenance_types": maintenance_types,
                        "working_order_codes": working_order_codes,
                    },
                    "order_by": "FINISHTIME DESC, CREATETIME DESC",
                    "limit": limit,
                },
                "orders": [],
                "details": [],
                "attachments": [],
                "wo_commonfile": [],
                "stations": [],
                "devices": [],
                "device_history": {"orders": [], "rf_forms": {}, "query_info": {"skipped": True, "reason": "no_orders"}},
                "rf_forms": {},
            }

        code_placeholders = ", ".join("?" for _ in codes)
        details = rows(
            cursor,
            f"""
            SELECT
                WORKINGORDERCODE, PROCESSSTEP, PROCESSSTARTDATETIME,
                PROCESSENDDATETIME, PROCESSUSERID, PROCESSSTATUS,
                SUBMITREMARK, DESCRIPTIONTA, EXPENSE, PROCESSTIME
            FROM dbo.working_order_details
            WHERE WORKINGORDERCODE IN ({code_placeholders})
            ORDER BY WORKINGORDERCODE, PROCESSSTARTDATETIME, PROCESSSTEP
            """,
            codes,
        )
        attachments = rows(
            cursor,
            f"""
            SELECT TOP 6000 *
            FROM dbo.wo_commonfile_links
            WHERE refid IN ({code_placeholders}) OR remark IN ({code_placeholders})
            ORDER BY createdate DESC
            """,
            codes + codes,
        )

        wo_commonfile = rows(
            cursor,
            f"""
            SELECT TOP 6000 *
            FROM dbo.WO_COMMONFILE
            WHERE REFID IN ({code_placeholders})
            ORDER BY CREATEDATE DESC
            """,
            codes,
        )

        station_ids_for_query = sorted({str(row.get("STATIONID")) for row in orders if row.get("STATIONID")})
        stations = []
        if station_ids_for_query:
            station_placeholders = ", ".join("?" for _ in station_ids_for_query)
            try:
                stations = rows(
                    cursor,
                    f"""
                    SELECT TOP 3000
                        bs.STATIONID,
                        bs.NAME,
                        bs.CODE,
                        bs.UNIQUECODE,
                        op.DEPARTMENTID AS OPERATIONUNITID,
                        op.DEPARTMENTNAME AS OPERATIONUNIT
                    FROM dbo.base_station bs
                    OUTER APPLY (
                        SELECT TOP 1 sd.DEPARTMENTID, sd.DEPARTMENTNAME
                        FROM dbo.base_department_station bds
                        JOIN dbo.sys_department sd
                          ON bds.DEPARTMENTID = sd.DEPARTMENTID
                        WHERE bds.STATIONID = CAST(bs.STATIONID AS NVARCHAR(64))
                          AND sd.USERTYPE = '3'
                        ORDER BY
                            CASE WHEN sd.PARENTID = 'Default-3-OperationUnit' THEN 0 ELSE 1 END,
                            sd.DEPARTMENTNAME
                    ) op
                    WHERE CAST(bs.STATIONID AS NVARCHAR(64)) IN ({station_placeholders})
                    """,
                    station_ids_for_query,
                )
            except Exception:
                logger.exception("ops_audit_station_fetch_failed")
                conn.rollback()

        rf_forms: dict[str, list[dict[str, Any]]] = {}
        rf_form_filter_stats: dict[str, dict[str, Any]] = {}
        for table in RF_TABLES:
            try:
                table_rows = rows(
                    cursor,
                    f"""
                    SELECT TOP 3000 *
                    FROM dbo.{table}
                    WHERE WORKINGORDERCODE IN ({code_placeholders})
                    """,
                    codes,
                )
                selected_rows, stats = _select_rf_forms_with_filter_stats(table, table_rows)
                rf_forms[table] = selected_rows
                rf_form_filter_stats[table] = stats
            except Exception as exc:  # keep extraction useful if one table drifts
                error_rows = [{"_query_error": str(exc)}]
                selected_rows, stats = _select_rf_forms_with_filter_stats(table, error_rows)
                rf_forms[table] = selected_rows
                rf_form_filter_stats[table] = stats
                conn.rollback()

        device_ids = {str(row.get("DEVICEID")) for row in orders if row.get("DEVICEID")}
        device_codes = {
            str(form.get("DEVICECODE") or form.get("DEVICECODEN"))
            for forms in rf_forms.values()
            for form in forms
            if form.get("DEVICECODE") or form.get("DEVICECODEN")
        }
        device_where_parts = []
        device_params: list[Any] = []
        if device_ids:
            device_where_parts.append(_in_clause("DEVICEID", sorted(device_ids), device_params))
        if device_codes:
            device_where_parts.append(_in_clause("DEVICECODE", sorted(device_codes), device_params))
        devices = []
        if device_where_parts:
            devices = rows(
                cursor,
                f"""
                SELECT
                    DEVICEID, DEVICEBRAND, DEVICEMODEL, DEVICECODE,
                    STATIONID, POLLUTANTID, DEVICETYPE
                FROM dbo.base_device
                WHERE {" OR ".join(device_where_parts)}
                """,
                device_params,
            )
        device_history = _fetch_device_history(cursor, orders, limit=int(DEVICE_IDENTITY_PROFILE.get("history_limit", 5000)))

    return {
        "query_info": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "database": "AirPollutionAnalysis",
            "order_filter": {
                "status": order_statuses or "all",
                "create_time_start": filters.create_time_start,
                "create_time_end": filters.create_time_end,
                "finish_time_start": filters.finish_time_start,
                "finish_time_end": filters.finish_time_end,
                "station_ids": station_ids,
                "order_types": order_types,
                "maintenance_types": maintenance_types,
                "working_order_codes": working_order_codes,
            },
            "rf_form_filter_stats": rf_form_filter_stats,
            "order_by": "FINISHTIME DESC, CREATETIME DESC",
            "limit": limit,
        },
        "orders": orders,
        "details": details,
        "attachments": attachments,
        "wo_commonfile": wo_commonfile,
        "stations": stations,
        "devices": devices,
        "device_history": device_history,
        "rf_forms": rf_forms,
    }


def _fetch_device_history(cursor: pyodbc.Cursor, orders: list[dict[str, Any]], limit: int = 5000) -> dict[str, Any]:
    """Fetch recent same-station history for RF table identity checks."""

    keyed_orders = [
        order
        for order in orders
        if order.get("WORKINGORDERCODE")
        and order.get("STATIONID")
        and parse_time(order.get("CREATETIME"))
    ]
    if not keyed_orders:
        return {"orders": [], "rf_forms": {}, "query_info": {"skipped": True, "reason": "missing_station_or_time"}}

    history_days = int(DEVICE_IDENTITY_PROFILE.get("history_days", 90))
    per_order_limit = int(DEVICE_IDENTITY_PROFILE.get("previous_same_station_limit", 20) or 20)
    per_order_limit = max(1, min(per_order_limit, 100))
    total_limit = max(1, min(limit, 10000))
    history_orders_by_code: dict[str, dict[str, Any]] = {}

    try:
        for order in keyed_orders:
            if len(history_orders_by_code) >= total_limit:
                break
            create_time = parse_time(order.get("CREATETIME"))
            if not create_time:
                continue
            params: list[Any] = [
                order.get("STATIONID"),
                (create_time - timedelta(days=history_days)).strftime("%Y-%m-%d %H:%M:%S"),
                create_time.strftime("%Y-%m-%d %H:%M:%S"),
                order.get("WORKINGORDERCODE"),
            ]
            history_rows = rows(
                cursor,
                f"""
                SELECT TOP {per_order_limit}
                    WORKINGORDERID, STATIONID, DEVICEID, WORKINGORDERCODE,
                    CREATETIME, UPDATETIME, DDORDERCREATETYPE, DDWORKINGORDERTYPE,
                    DDURGENCYTYPE, DDWORKINGORDERSTATUS, DDISSUEDTYPE, ORDERTITLE,
                    ORDERCONTENT, CURRENTWORKFLOWSTATUS, CURRENTWORKFLOWPOINT,
                    FINISHTIME, PLANFINISHTIME, MAINTENANCETYPE, TOTALOVERTIME,
                    TOTALEXPENSE
                FROM dbo.working_orders
                WHERE STATIONID = ?
                  AND CREATETIME >= ?
                  AND CREATETIME < ?
                  AND WORKINGORDERCODE <> ?
                  AND DDWORKINGORDERSTATUS = 'Finish'
                ORDER BY CREATETIME DESC
                """,
                params,
            )
            for history_order in history_rows:
                code = history_order.get("WORKINGORDERCODE")
                if code and code not in history_orders_by_code:
                    history_orders_by_code[str(code)] = history_order
                    if len(history_orders_by_code) >= total_limit:
                        break
    except Exception as exc:
        cursor.connection.rollback()
        return {"orders": [], "rf_forms": {}, "query_info": {"error": str(exc)}}

    history_orders = list(history_orders_by_code.values())

    history_codes = [row["WORKINGORDERCODE"] for row in history_orders if row.get("WORKINGORDERCODE")]
    history_rf_forms: dict[str, list[dict[str, Any]]] = {}
    if history_codes:
        code_placeholders = ", ".join("?" for _ in history_codes)
        for table in RF_TABLES:
            try:
                table_rows = rows(
                    cursor,
                    f"""
                    SELECT TOP {max(1, min(limit, 10000))} *
                    FROM dbo.{table}
                    WHERE WORKINGORDERCODE IN ({code_placeholders})
                    """,
                    history_codes,
                )
                history_rf_forms[table], _ = _select_rf_forms_with_filter_stats(table, table_rows)
            except Exception as exc:
                history_rf_forms[table], _ = _select_rf_forms_with_filter_stats(table, [{"_query_error": str(exc)}])
                cursor.connection.rollback()

    return {
        "orders": history_orders,
        "rf_forms": history_rf_forms,
        "query_info": {
            "strategy": "previous_same_station",
            "history_days": history_days,
            "previous_same_station_limit": per_order_limit,
            "seed_order_count": len(keyed_orders),
            "station_count": len({str(order.get("STATIONID")) for order in keyed_orders}),
            "order_count": len(history_orders),
        },
    }


def is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(str(value), fmt)
        except ValueError:
            continue
    return None


def first_present(form: dict[str, Any], candidates: list[str]) -> tuple[str | None, Any]:
    for field in candidates:
        if field in form:
            return field, form.get(field)
    return None, None


def _group_records_by_order_code(records: list[dict[str, Any]], fields: list[str]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped_keys = set()
        for field in fields:
            value = record.get(field)
            if value is not None and str(value).strip():
                grouped_keys.add(str(value).strip())
        for key in grouped_keys:
            grouped[key].append(record)
    return grouped


def _rf_attachment_typecodes(records: list[dict[str, Any]]) -> list[str]:
    typecodes: set[str] = set()
    for record in records:
        for field in ("TYPECODE", "typecode", "TypeCode"):
            value = record.get(field)
            if value is not None and str(value).strip().lower().startswith("rf_"):
                typecodes.add(str(value).strip())
                break
    return sorted(typecodes)


def has_meaningful_text(value: Any) -> bool:
    if is_blank(value):
        return False
    return str(value).strip() not in LOW_VALUE_REMARKS


def normalize_device_brand(brand: Any, model: Any = None) -> str | None:
    brand_text = str(brand or "").strip()
    model_text = str(model or "").strip()
    if not brand_text and not model_text:
        return None

    brand_upper = brand_text.upper()
    model_upper = model_text.upper()
    for canonical, aliases in BRAND_ALIASES.items():
        if brand_upper in aliases:
            return canonical

    if model_upper.startswith(("43", "48", "49")) and brand_upper in {"", "TE", "THERMO"}:
        return "THERMO"
    return None


def parse_check_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    text = str(value).strip()
    if not text or text in {"/", "-", "无", "NA", "N/A"}:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None
    return float(match.group(0))


def range_text(spec: dict[str, Any]) -> str:
    lower = spec.get("min")
    upper = spec.get("max")
    unit = spec.get("unit") or ""
    if spec.get("operator") == ">" and lower is not None:
        return f">{lower}{unit}"
    if spec.get("operator") == ">=" and lower is not None:
        return f">={lower}{unit}"
    if spec.get("operator") == "<" and upper is not None:
        return f"<{upper}{unit}"
    if spec.get("operator") == "<=" and upper is not None:
        return f"<={upper}{unit}"
    if lower is not None and upper is not None:
        return f"{lower}～{upper}{unit}"
    if lower is not None:
        return f">={lower}{unit}"
    if upper is not None:
        return f"<={upper}{unit}"
    return f"未配置{unit}"


def is_value_in_range(value: float, spec: dict[str, Any]) -> bool:
    lower = spec.get("min")
    upper = spec.get("max")
    operator = spec.get("operator")
    if operator == ">" and lower is not None:
        return value > float(lower)
    if operator == ">=" and lower is not None:
        return value >= float(lower)
    if operator == "<" and upper is not None:
        return value < float(upper)
    if operator == "<=" and upper is not None:
        return value <= float(upper)
    if lower is not None and value < float(lower):
        return False
    if upper is not None and value > float(upper):
        return False
    return True


def resolve_device_context(
    order: dict[str, Any],
    form: dict[str, Any],
    devices_by_id: dict[str, dict[str, Any]] | None,
    devices_by_code: dict[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    device_id = str(order.get("DEVICEID") or "").strip()
    device_code = str(form.get("DEVICECODE") or form.get("DEVICECODEN") or "").strip()
    if device_id and devices_by_id and device_id in devices_by_id:
        return devices_by_id[device_id]
    if device_code and devices_by_code and device_code in devices_by_code:
        return devices_by_code[device_code]
    return {}


def check_form_range_profile(
    table: str,
    order: dict[str, Any],
    form: dict[str, Any],
    issues: list[Issue],
    devices_by_id: dict[str, dict[str, Any]] | None = None,
    devices_by_code: dict[str, dict[str, Any]] | None = None,
) -> None:
    profile = FORM_RANGE_PROFILES.get(table)
    if not profile:
        return
    pollutant = str(form.get("POLLUTANTTYPE") or "").upper()
    expected_pollutant = profile.get("pollutant_type")
    expected_pollutants = {str(item).upper() for item in profile.get("pollutant_types", set())}
    if expected_pollutant and pollutant != str(expected_pollutant).upper():
        return
    if expected_pollutants and pollutant not in expected_pollutants:
        return

    device_context = resolve_device_context(order, form, devices_by_id, devices_by_code)
    raw_brand_value = form.get("DEVICEBRAND") or device_context.get("DEVICEBRAND")
    raw_model_value = form.get("DEVICEMODEL") or device_context.get("DEVICEMODEL")
    brand = normalize_device_brand(raw_brand_value, raw_model_value)
    raw_brand = str(raw_brand_value or "").strip()
    model = str(raw_model_value or "").strip()
    device_code = str(form.get("DEVICECODE") or form.get("DEVICECODEN") or "").strip()
    device_source = "rf_form" if form.get("DEVICEBRAND") or form.get("DEVICEMODEL") else ("base_device" if device_context else "missing")
    if not brand:
        add_issue(
            issues,
            "RF_RANGE_BRAND_UNKNOWN",
            "表单结果合理性",
            "低",
            f"{table}.DEVICEBRAND",
            f"{profile['form_name']}仪器品牌无法匹配范围配置",
            f"brand={raw_brand or '<空>'}, model={model or '<空>'}, device_code={device_code or '<空>'}, source={device_source}",
        )
        return
    if brand not in profile.get("enabled_brands", set()):
        return

    for field_config in profile["fields"].values():
        ranges = field_config.get("ranges", {})
        spec = ranges.get(brand)
        if not spec:
            add_issue(
                issues,
                "RF_RANGE_PROFILE_MISSING",
                "表单结果合理性",
                "低",
                f"{table}.{field_config['db_field']}",
                f"{field_config['label']}缺少{brand}品牌正常范围配置",
                f"brand={raw_brand or '<空>'}, normalized_brand={brand}, model={model or '<空>'}, source={device_source}",
            )
            continue

        raw_value = form.get(field_config["db_field"])
        value = parse_check_number(raw_value)
        remark = str(form.get("REMARK") or form.get("REMARKS") or "")
        if value is None:
            optional_tokens = field_config.get("optional_when_remark_contains") or set()
            if any(token in remark for token in optional_tokens):
                continue
            add_issue(
                issues,
                "RF_RANGE_VALUE_MISSING",
                "表单完整性",
                "高",
                f"{table}.{field_config['db_field']}",
                f"{field_config['label']}检查值为空，无法按{brand}正常范围审核",
                f"value={raw_value}, expected_range={range_text(spec)}, brand={raw_brand or '<空>'}, model={model or '<空>'}, source={device_source}",
            )
            if not has_meaningful_text(remark):
                add_issue(
                    issues,
                    "RF_ABNORMAL_VALUE_NO_REMARK",
                    "结果合理性",
                    "中",
                    f"{table}.{field_config['db_field']}",
                    f"{field_config['label']}检查值为空且无有效说明",
                    f"value={raw_value}, expected_range={range_text(spec)}, remark={remark or '<空>'}",
                )
            continue

        if not is_value_in_range(value, spec):
            add_issue(
                issues,
                "RF_RANGE_OUT_OF_SPEC",
                "表单结果合理性",
                "高",
                f"{table}.{field_config['db_field']}",
                f"{field_config['label']}检查值超出{brand}正常范围",
                f"value={value}, expected_range={range_text(spec)}, brand={raw_brand or '<空>'}, model={model or '<空>'}, source={device_source}",
            )
            if not has_meaningful_text(remark):
                add_issue(
                    issues,
                    "RF_ABNORMAL_VALUE_NO_REMARK",
                    "结果合理性",
                    "中",
                    f"{table}.{field_config['db_field']}",
                    f"{field_config['label']}检查值超出正常范围且无有效说明",
                    f"value={value}, expected_range={range_text(spec)}, remark={remark or '<空>'}",
                )


def check_form_common_fields(table: str, form: dict[str, Any], issues: list[Issue]) -> None:
    prefix = table

    low_value_field_groups = RF_FIELD_PROFILES.get("low_value_field_groups", {})
    for label, fields in low_value_field_groups.items():
        field, value = first_present(form, fields)
        if field and not has_meaningful_text(value):
            add_issue(
                issues,
                "RF_REQUIRED_FIELD_LOW_VALUE",
                "表单完整性",
                "中",
                f"{prefix}.{field}",
                f"RF 表单{label}字段为空或信息量低",
                str(value),
            )

    temperature_field, temperature = first_present(
        form,
        RF_FIELD_PROFILES.get("temperature_fields", []),
    )
    humidity_field, humidity = first_present(
        form,
        RF_FIELD_PROFILES.get("humidity_fields", []),
    )
    if temperature_field and is_blank(temperature):
        add_issue(
            issues,
            "RF_ENV_TEMP_HUMIDITY_EMPTY",
            "表单完整性",
            "中",
            f"{prefix}.{temperature_field}",
            "RF 表单室内温度未填",
            "",
        )
    if humidity_field and is_blank(humidity):
        add_issue(
            issues,
            "RF_ENV_TEMP_HUMIDITY_EMPTY",
            "表单完整性",
            "中",
            f"{prefix}.{humidity_field}",
            "RF 表单室内湿度未填",
            "",
        )

    check_field, check_value = first_present(form, RF_FIELD_PROFILES.get("check_time_fields", []))
    start_field, start_value = first_present(form, RF_FIELD_PROFILES.get("start_time_fields", []))
    end_field, end_value = first_present(form, RF_FIELD_PROFILES.get("end_time_fields", []))
    check_time = parse_time(check_value)
    start_time = parse_time(start_value)
    end_time = parse_time(end_value)
    if check_field and start_field and end_field and check_time and start_time and end_time:
        if check_time < start_time or check_time > end_time:
            add_issue(
                issues,
                "RF_CHECK_TIME_OUTSIDE_RANGE",
                "时间合理性",
                "高",
                f"{prefix}.{check_field}",
                "RF 表单检查时间不在开始结束时间内",
                f"check={check_time}, start={start_time}, end={end_time}",
            )


def check_workflow(order: dict[str, Any], details: list[dict[str, Any]], issues: list[Issue]) -> None:
    if not details:
        add_issue(issues, "FLOW_MISSING", "流程完整性", "高", "working_order_details", "完工工单无流程详情", "")
        return

    steps = [detail.get("PROCESSSTEP") for detail in details]
    if "CreateOrder" not in steps:
        add_issue(issues, "FLOW_NO_CREATE", "流程完整性", "高", "PROCESSSTEP", "缺少创建步骤", ",".join(map(str, steps)))

    valid_process_steps_by_type = {
        "Check": {"CheckOrder"},
        "SupCheck": {"SupCheck_Check"},
        "Fault": {"FaultProcess", "CheckOrder"},
        "SECCheckCnemc": {"SECCheckCnemc", "OperationCheckCnemc"},
        "SupSECCheck": {"SECCheckCnemc", "OperationCheckCnemc", "SupCheck_Check"},
        "WorkRectify": {"WorkRectify", "CheckOrder"},
        "StationBlackOut": {"FaultProcess", "CheckOrder"},
    }
    expected_process_steps = valid_process_steps_by_type.get(order.get("DDWORKINGORDERTYPE"))
    if expected_process_steps and not (expected_process_steps & set(steps)):
        add_issue(issues, "FLOW_NO_CHECK", "流程完整性", "高", "PROCESSSTEP", "缺少检查/巡检处理步骤", ",".join(map(str, steps)))

    if order.get("DDWORKINGORDERTYPE") in {"Check", "SupCheck"} and "Review" not in steps:
        add_issue(issues, "FLOW_NO_REVIEW", "流程完整性", "中", "PROCESSSTEP", "检查/巡检工单缺少复核步骤", ",".join(map(str, steps)))

    previous_start = None
    for detail in details:
        step = detail.get("PROCESSSTEP") or ""
        start = parse_time(detail.get("PROCESSSTARTDATETIME"))
        end = parse_time(detail.get("PROCESSENDDATETIME"))
        if detail.get("PROCESSSTATUS") in {"1.00", 1, 1.0} and step != "CreateOrder" and end is None:
            add_issue(issues, "FLOW_END_EMPTY", "流程完整性", "中", "PROCESSENDDATETIME", "已完成流程步骤结束时间为空", step)
        if start and end and end < start:
            add_issue(issues, "FLOW_TIME_ORDER", "时间合理性", "高", "PROCESSENDDATETIME", "流程结束时间早于开始时间", f"{step}: {end} < {start}")
        if previous_start and start and start < previous_start:
            add_issue(issues, "FLOW_SEQUENCE", "时间合理性", "中", "PROCESSSTARTDATETIME", "流程开始时间顺序倒置", f"{step}: {start}")
        if start:
            previous_start = start

        remark = detail.get("SUBMITREMARK")
        if step != "CreateOrder" and (is_blank(remark) or str(remark).strip() in LOW_VALUE_REMARKS):
            add_issue(issues, "FLOW_REMARK_LOW_VALUE", "填报规范性", "中", "SUBMITREMARK", "处理备注为空或信息量低", str(remark))


def check_lifecycle_closure(order: dict[str, Any], details: list[dict[str, Any]], issues: list[Issue]) -> None:
    if order.get("DDWORKINGORDERSTATUS") != "Finish":
        return

    finish_time = parse_time(order.get("FINISHTIME"))
    plan_finish_time = parse_time(order.get("PLANFINISHTIME"))
    if finish_time and plan_finish_time:
        seconds_to_deadline = abs((plan_finish_time - finish_time).total_seconds())
        if seconds_to_deadline <= 30 * 60:
            add_issue(
                issues,
                "LIFECYCLE_FINISH_NEAR_DEADLINE",
                "生命周期闭环风险",
                "低",
                "FINISHTIME/PLANFINISHTIME",
                "工单临近计划截止时间完成",
                f"finish={finish_time}, plan_finish={plan_finish_time}, delta_minutes={round(seconds_to_deadline / 60, 1)}",
            )

    if not details:
        return

    effective_steps_by_type = {
        "Check": {"CheckOrder"},
        "SupCheck": {"SupCheck_Check"},
        "Fault": {"FaultProcess", "CheckOrder"},
        "SECCheckCnemc": {"SECCheckCnemc", "OperationCheckCnemc"},
        "SupSECCheck": {"SECCheckCnemc", "OperationCheckCnemc", "SupCheck_Check"},
        "WorkRectify": {"WorkRectify", "CheckOrder"},
        "StationBlackOut": {"FaultProcess", "CheckOrder"},
    }
    expected_steps = effective_steps_by_type.get(order.get("DDWORKINGORDERTYPE"), set())
    non_create_details = [detail for detail in details if detail.get("PROCESSSTEP") != "CreateOrder"]
    actual_steps = {detail.get("PROCESSSTEP") for detail in non_create_details}
    has_expected_processing = bool(expected_steps & actual_steps) if expected_steps else bool(non_create_details)
    has_meaningful_remark = any(
        not is_blank(detail.get("SUBMITREMARK")) and str(detail.get("SUBMITREMARK")).strip() not in LOW_VALUE_REMARKS
        for detail in non_create_details
    )
    if not has_expected_processing or not has_meaningful_remark:
        severity = "高" if not has_expected_processing else "中"
        add_issue(
            issues,
            "LIFECYCLE_FINISH_WITHOUT_EFFECTIVE_CLOSURE",
            "生命周期闭环风险",
            severity,
            "working_order_details",
            "已完成工单缺少有效闭环证据",
            f"steps={','.join(map(str, sorted(actual_steps))) or '<无>'}, has_meaningful_remark={has_meaningful_remark}",
        )


def check_rf_forms(
    order: dict[str, Any],
    forms: list[tuple[str, dict[str, Any]]],
    issues: list[Issue],
    devices_by_id: dict[str, dict[str, Any]] | None = None,
    devices_by_code: dict[str, dict[str, Any]] | None = None,
    rf_attachment_typecodes: list[str] | None = None,
    attachment_records: list[dict[str, Any]] | None = None,
) -> None:
    has_tw_cleaning_photo = _has_tw_cleaning_photo(attachment_records or [])
    tw_cleaning_candidate_added = False
    for table, form in forms:
        if form.get("_query_error"):
            continue
        prefix = table
        station = form.get("STATIONID")
        if station and str(station) != str(order.get("STATIONID")):
            add_issue(issues, "RF_STATION_MISMATCH", "一致性", "高", f"{prefix}.STATIONID", "RF 表单站点与工单站点不一致", f"form={station}, order={order.get('STATIONID')}")

        if "AUDITORUSERID" in form and is_blank(form.get("AUDITORUSERID")):
            add_issue(issues, "RF_AUDITOR_EMPTY", "表单完整性", "低", f"{prefix}.AUDITORUSERID", "表单审批人为空", "")

        if table == "RF_TW_CleanCuttingHead":
            if form.get("PollutantType") and form.get("PM_DeviceType") and str(form["PollutantType"]).upper() != str(form["PM_DeviceType"]).upper():
                add_issue(issues, "RF_TW_POLLUTANT_MISMATCH", "一致性", "高", "PollutantType/PM_DeviceType", "污染物类型与设备类型不一致", f"{form['PollutantType']} vs {form['PM_DeviceType']}")
            if not has_tw_cleaning_photo and not tw_cleaning_candidate_added:
                evidence = {
                    "working_order_code": order.get("WORKINGORDERCODE"),
                    "rf_table": table,
                    "field": "CleaningRemark",
                    "remark_candidates": _tw_cleaning_remarks(forms),
                    "attachment_summary": _attachment_summary(attachment_records or []),
                    "needs_semantic_review": True,
                    "review_basis": "未识别到切割头清洗照片，需语义复核备注是否说明无照片或清洗证据不足的合理原因。",
                }
                add_issue(
                    issues,
                    "RF_TW_REMARK_LOW_VALUE",
                    "填报规范性",
                    "中",
                    "rf.RF_TW_CleanCuttingHead.CleaningRemark",
                    "双周切割头清洗未识别到清洗照片，需语义复核备注说明是否合理",
                    json.dumps(evidence, ensure_ascii=False, default=str),
                )
                tw_cleaning_candidate_added = True

        if table.startswith("RF_Q_GASEOUSMULTIPOINT"):
            for field in ["XL", "JU", "XGXS"]:
                if field in form and is_blank(form.get(field)):
                    add_issue(issues, "RF_Q_MULTIPOINT_METRIC_EMPTY", "表单完整性", "高", field, "多点校准关键指标为空", "")
            if str(form.get("XZJG")) in {"0", "0.0"} and is_blank(form.get("REMARKS")):
                add_issue(issues, "RF_Q_PENDING_NO_REMARK", "结果合理性", "高", "XZJG/REMARKS", "校准结果待定/不合格但无说明", f"XZJG={form.get('XZJG')}")


def _has_tw_cleaning_photo(records: list[dict[str, Any]]) -> bool:
    for record in records:
        typecode = str(record.get("TYPECODE") or record.get("typecode") or record.get("TypeCode") or "").strip().upper()
        if not typecode.startswith("RF_TW_CLEANCUTTINGHEAD"):
            continue
        text = _attachment_text(record)
        if _attachment_looks_like_image(text) or any(keyword in text for keyword in ("清洁", "清洗", "切割器", "切割头")):
            return True
    return False


def _attachment_text(record: dict[str, Any]) -> str:
    fields = (
        "filename",
        "FILENAME",
        "FileName",
        "filepath",
        "FILEPATH",
        "file_url",
        "FILE_URL",
        "TYPECODE",
        "typecode",
        "TypeCode",
    )
    return " ".join(str(record.get(field) or "") for field in fields).strip()


def _attachment_looks_like_image(text: str) -> bool:
    normalized = text.lower()
    return any(ext in normalized for ext in (".jpg", ".jpeg", ".png", ".bmp", ".webp"))


def _tw_cleaning_remarks(forms: list[tuple[str, dict[str, Any]]]) -> dict[str, list[str]]:
    remarks: dict[str, list[str]] = {}
    for table, form in forms:
        if table != "RF_TW_CleanCuttingHead" or form.get("_query_error"):
            continue
        values = []
        for field in ("CleaningRemark", "REMARK", "REMARKS", "SUBMITREMARK"):
            if field in form:
                values.append(f"{field}={str(form.get(field) or '').strip()}")
        key = str(form.get("PollutantType") or form.get("PM_DeviceType") or "unknown")
        remarks.setdefault(key, []).extend(value for value in values if value not in remarks.get(key, []))
    return remarks


def _attachment_summary(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary = []
    for record in records[:20]:
        summary.append(
            {
                "typecode": record.get("TYPECODE") or record.get("typecode") or record.get("TypeCode"),
                "filename": record.get("FILENAME") or record.get("filename") or record.get("FileName"),
                "createdate": record.get("CREATEDATE") or record.get("createdate"),
            }
        )
    return summary


def severity_score(issues: list[Issue] | list[dict[str, Any]]) -> int:
    return 0 if issues else 100


def risk_level(score: int, issues: list[Issue] | list[dict[str, Any]]) -> str:
    issue_rule_ids = {
        issue.rule_id if isinstance(issue, Issue) else issue.get("rule_id")
        for issue in issues
    }
    return "有问题" if issue_rule_ids else ""


def dedupe_issues(issues: list[Issue]) -> list[Issue]:
    """Keep one issue for each rule/field/message emitted by legacy and modular rules."""

    deduped: list[Issue] = []
    seen: set[tuple[str, str, str]] = set()
    for issue in issues:
        key = (issue.rule_id, issue.field, issue.message)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(issue)
    return deduped


def _run_flow_visual_tasks(
    tasks: list[dict[str, Any]],
    record_issues_by_code: dict[str, list[Issue]],
) -> None:
    total = len(tasks)
    concurrency = max(1, int(os.getenv("OPS_AUDIT_FLOW_VISUAL_CONCURRENCY", "8") or "8"))
    concurrency = min(concurrency, max(total, 1))
    provider_limits = flow_visual_provider_summary()
    logger.info(
        "ops_audit_flow_visual_tasks_selected candidate_image_count=%s concurrency=%s providers=%s",
        total,
        concurrency,
        json.dumps(provider_limits, ensure_ascii=False),
    )
    if not tasks:
        return

    started_at = time.monotonic()
    completed = 0
    issue_count = 0
    progress_every = max(1, int(os.getenv("OPS_AUDIT_FLOW_VISUAL_PROGRESS_EVERY", "10") or "10"))
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        future_to_task = {executor.submit(_run_one_flow_visual_task, task): task for task in tasks}
        for future in as_completed(future_to_task):
            task = future_to_task[future]
            code = str(task.get("working_order_code") or "")
            completed += 1
            try:
                issues = future.result()
            except Exception as exc:
                logger.exception(
                    "ops_audit_flow_visual_task_failed working_order_code=%s filename=%s",
                    code,
                    (task.get("item") or {}).get("filename"),
                )
                issues = [
                    Issue(
                        "ATTACHMENT_FLOW_VISUAL_ERROR",
                        "附件读数一致性",
                        "低",
                        "attachment.vision.error",
                        f"流量照片视觉识别失败：{exc}",
                        json.dumps(
                            {
                                "working_order_code": code,
                                "filename": (task.get("item") or {}).get("filename"),
                                "source": (task.get("item") or {}).get("source_path"),
                                "error": str(exc),
                            },
                            ensure_ascii=False,
                            default=str,
                        ),
                        "稍后重试视觉识别，或人工核对该附件。",
                    )
                ]
            if issues:
                record_issues_by_code.setdefault(code, []).extend(issues)
                issue_count += len(issues)
            if completed == total or completed % progress_every == 0:
                logger.info(
                    "ops_audit_flow_visual_progress completed=%s total=%s issue_count=%s elapsed_seconds=%s",
                    completed,
                    total,
                    issue_count,
                    round(time.monotonic() - started_at, 2),
                )


def _run_one_flow_visual_task(task: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    if task.get("task_type") == "multipoint_curve_visual":
        run_multipoint_curve_visual_task(task, issues)
    else:
        run_flow_visual_task(task, issues)
    return issues


def audit_dataset(
    dataset: dict[str, Any],
    *,
    enable_visual: bool = True,
    visual_evidence_dir: Path | None = None,
) -> dict[str, Any]:
    visual_evidence_dir = (visual_evidence_dir or (OUTPUT_DIR / "visual_evidence" / "multipoint_curves")).resolve()
    details_by_code = defaultdict(list)
    for detail in dataset.get("details", []):
        details_by_code[detail.get("WORKINGORDERCODE")].append(detail)

    station_meta_by_id = _station_meta_by_id(dataset.get("stations", []))
    devices_by_id = {
        str(device.get("DEVICEID")): device
        for device in dataset.get("devices", [])
        if device.get("DEVICEID")
    }
    devices_by_code = {
        str(device.get("DEVICECODE")): device
        for device in dataset.get("devices", [])
        if device.get("DEVICECODE")
    }

    forms_by_code = defaultdict(list)
    for table, forms in dataset.get("rf_forms", {}).items():
        for form in forms:
            code = form.get("WORKINGORDERCODE")
            if code:
                forms_by_code[code].append((table, form))
    attachments_by_code = _group_records_by_order_code(dataset.get("attachments", []), ["refid", "REFID", "remark", "REMARK"])
    wo_commonfile_by_code = _group_records_by_order_code(dataset.get("wo_commonfile", []), ["REFID", "refid"])
    all_orders_for_device_consistency, all_forms_by_code = merge_device_history(dataset)

    records = []
    record_issues_by_code: dict[str, list[Issue]] = {}
    flow_visual_tasks: list[dict[str, Any]] = []
    for order in dataset.get("orders", []):
        code = order.get("WORKINGORDERCODE")
        station_meta = station_meta_by_id.get(str(order.get("STATIONID") or ""), {})
        issues: list[Issue] = []
        forms = forms_by_code.get(code, [])
        details = details_by_code.get(code, [])
        attachment_rf_typecodes = _rf_attachment_typecodes(attachments_by_code.get(str(code), [])) + _rf_attachment_typecodes(
            wo_commonfile_by_code.get(str(code), [])
        )

        check_workflow_completeness(order, details, issues)
        check_modular_lifecycle_closure(order, details, forms, issues)
        check_rf_required_fields(order, forms, issues)
        check_rf_time_ranges(order, forms, issues)
        check_rf_unit_values(order, forms, issues)
        check_rf_range_values(order, forms, issues)
        check_rf_formula_values(order, forms, issues)
        check_rf_environment_humidity_values(order, forms, issues)
        check_rf_multipoint_values(
            order,
            forms,
            issues,
            all_orders=all_orders_for_device_consistency,
            forms_by_code=all_forms_by_code,
        )
        check_rf_pm_pressure_values(order, forms, issues)
        check_rf_field_positions(order, forms, issues)
        check_rf_enum_values(order, forms, issues)
        check_rf_visibility_values(order, forms, issues)
        check_rf_abnormal_remarks(order, forms, issues)
        check_rf_calibration_dates(
            order,
            forms,
            issues,
            all_orders=all_orders_for_device_consistency,
            forms_by_code=all_forms_by_code,
        )

        check_rf_forms(
            order,
            forms,
            issues,
            devices_by_id,
            devices_by_code,
            attachment_rf_typecodes,
            attachments_by_code.get(str(code), []) + wo_commonfile_by_code.get(str(code), []),
        )
        check_device_identity_consistency(
            order,
            forms,
            all_orders_for_device_consistency,
            all_forms_by_code,
            devices_by_id,
            devices_by_code,
            issues,
        )
        check_attachment_requirements(
            order,
            forms,
            attachments_by_code.get(str(code), []),
            wo_commonfile_by_code.get(str(code), []),
            issues,
        )
        check_o3_value_pass_xls_values(
            order,
            forms,
            attachments_by_code.get(str(code), []),
            wo_commonfile_by_code.get(str(code), []),
            issues,
        )
        check_o3_transfer_quality_values(order, forms, issues)
        if enable_visual:
            order_flow_tasks = build_flow_visual_tasks(
                order,
                forms,
                attachments_by_code.get(str(code), []),
                wo_commonfile_by_code.get(str(code), []),
            )
            for task in order_flow_tasks:
                task["working_order_code"] = code
            flow_visual_tasks.extend(order_flow_tasks)
            multipoint_tasks = build_multipoint_curve_visual_tasks(
                order,
                forms,
                attachments_by_code.get(str(code), []),
                wo_commonfile_by_code.get(str(code), []),
                evidence_dir=visual_evidence_dir,
            )
            for task in multipoint_tasks:
                task["working_order_code"] = code
            flow_visual_tasks.extend(multipoint_tasks)
        record_issues_by_code[str(code)] = issues
        issues_for_record = [issue for issue in dedupe_issues(issues) if not is_excluded_rule(issue.rule_id)]
        attachment_review_rules = sorted(
            {
                issue.rule_id
                for issue in issues_for_record
                if issue.rule_id in attachment_review_candidate_rule_ids()
            }
        )
        records.append(
            {
                "working_order_code": code,
                "station_id": order.get("STATIONID"),
                "station_name": station_meta.get("station_name"),
                "operation_unit": station_meta.get("operation_unit"),
                "order_type": order.get("DDWORKINGORDERTYPE"),
                "create_type": order.get("DDORDERCREATETYPE"),
                "maintenance_type": order.get("MAINTENANCETYPE"),
                "create_time": order.get("CREATETIME"),
                "finish_time": order.get("FINISHTIME"),
                "plan_finish_time": order.get("PLANFINISHTIME"),
                "issue_count": len(issues_for_record),
                "issues": [asdict(issue) for issue in issues_for_record],
                "workflow_steps": [d.get("PROCESSSTEP") for d in details_by_code.get(code, [])],
                "rf_tables": sorted({table for table, _ in forms_by_code.get(code, [])}),
                "rf_attachment_typecodes": sorted(set(attachment_rf_typecodes)),
                "attachment_count": len(attachments_by_code.get(str(code), [])) + len(wo_commonfile_by_code.get(str(code), [])),
                "attachment_review_rules": attachment_review_rules,
                "attachment_review_required": bool(attachment_review_rules),
            }
        )

    if enable_visual:
        _run_flow_visual_tasks(flow_visual_tasks, record_issues_by_code)
    for record in records:
        code = str(record.get("working_order_code") or "")
        issues = [issue for issue in dedupe_issues(record_issues_by_code.get(code, [])) if not is_excluded_rule(issue.rule_id)]
        attachment_review_rules = sorted(
            {
                issue.rule_id
                for issue in issues
                if issue.rule_id in attachment_review_candidate_rule_ids()
            }
        )
        record["issue_count"] = len(issues)
        record["issues"] = [asdict(issue) for issue in issues]
        record["attachment_review_rules"] = attachment_review_rules
        record["attachment_review_required"] = bool(attachment_review_rules)

    rule_patterns = classify_rule_patterns(records)
    apply_rule_pattern_assessment(records, rule_patterns)

    issue_counter = Counter()
    deterministic_issue_counter = Counter()
    candidate_issue_counter = Counter()
    severity_counter = Counter()
    category_counter = Counter()
    assessment_counter = Counter()
    level_counter = Counter(record["audit_level"] for record in records if record.get("audit_level"))
    device_consistency_issue_count = 0
    attachment_issue_count = 0
    attachment_review_candidate_count = 0
    for record in records:
        if record.get("attachment_review_required"):
            attachment_review_candidate_count += 1
        for issue in record["issues"]:
            issue_counter[issue["rule_id"]] += 1
            severity_counter[issue["severity"]] += 1
            category_counter[issue["category"]] += 1
            assessment_counter[issue.get("assessment", "unclassified_issue")] += 1
            if issue["rule_id"] == "RF_DEVICE_IDENTITY_INCONSISTENT":
                device_consistency_issue_count += 1
            if str(issue["rule_id"]).startswith("ATTACHMENT_"):
                attachment_issue_count += 1
        for issue in record.get("deterministic_issues", []):
            deterministic_issue_counter[issue["rule_id"]] += 1
        for issue in record.get("candidate_issues", []):
            candidate_issue_counter[issue["rule_id"]] += 1

    return {
        "audit_info": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "order_count": len(records),
            "rule_stage": "deterministic_and_candidate_classification",
        },
        "summary": {
            "audit_level_counts": dict(level_counter),
            "severity_counts": dict(severity_counter),
            "category_counts": dict(category_counter),
            "assessment_counts": dict(assessment_counter),
            "top_rules": issue_counter.most_common(20),
            "deterministic_top_rules": deterministic_issue_counter.most_common(20),
            "candidate_top_rules": candidate_issue_counter.most_common(20),
            "common_patterns": [],
            "device_consistency_issue_count": device_consistency_issue_count,
            "attachment_issue_count": attachment_issue_count,
            "attachment_review_candidate_count": attachment_review_candidate_count,
        },
        "rule_patterns": rule_patterns,
        "records": records,
    }


def classify_rule_patterns(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    order_count = max(len(records), 1)
    raw_counter = Counter()
    affected_orders: dict[str, set[str]] = defaultdict(set)
    severity_by_rule: dict[str, Counter] = defaultdict(Counter)
    category_by_rule: dict[str, Counter] = defaultdict(Counter)
    order_type_by_rule: dict[str, Counter] = defaultdict(Counter)

    for record in records:
        code = record.get("working_order_code")
        for issue in record.get("issues", []):
            rule_id = issue.get("rule_id")
            raw_counter[rule_id] += 1
            affected_orders[rule_id].add(code)
            severity_by_rule[rule_id][issue.get("severity")] += 1
            category_by_rule[rule_id][issue.get("category")] += 1
            order_type_by_rule[rule_id][record.get("order_type") or "<空>"] += 1

    patterns: dict[str, dict[str, Any]] = {}
    for rule_id, raw_hit_count in raw_counter.items():
        affected_count = len(affected_orders[rule_id])
        affected_ratio = affected_count / order_count
        eligible = rule_id in COMMON_PATTERN_ELIGIBLE_RULES and rule_id not in HARD_ERROR_RULES
        is_common = (
            eligible
            and affected_count >= COMMON_PATTERN_MIN_AFFECTED_ORDERS
            and affected_ratio >= COMMON_PATTERN_ORDER_RATIO
        )
        if is_common:
            pattern_type = "common_pattern"
            recommendation = "命中覆盖面较高，建议先确认是否为系统字段设计、流程常态或历史填报习惯；确认前不作为高风险计分依据。"
        elif rule_id in HARD_ERROR_RULES:
            pattern_type = "deterministic_issue"
            recommendation = "该规则属于硬性结构/逻辑问题，可作为确定性问题处理。"
        else:
            pattern_type = "candidate_issue"
            recommendation = "该规则为疑似异常，可结合样例、RF表、附件和语义审核进一步判断。"

        patterns[rule_id] = {
            "rule_id": rule_id,
            "raw_hit_count": raw_hit_count,
            "affected_order_count": affected_count,
            "affected_order_ratio": round(affected_ratio, 4),
            "pattern_type": pattern_type,
            "eligible_for_common_pattern": eligible,
            "dominant_severity": severity_by_rule[rule_id].most_common(1)[0][0],
            "dominant_category": category_by_rule[rule_id].most_common(1)[0][0],
            "order_type_counts": dict(order_type_by_rule[rule_id]),
            "recommendation": recommendation,
        }
    return patterns


def apply_rule_pattern_assessment(records: list[dict[str, Any]], rule_patterns: dict[str, dict[str, Any]]) -> None:
    for record in records:
        scoring_by_rule: dict[str, dict[str, Any]] = {}
        common_pattern_rules = []
        candidate_rules = []
        deterministic_rules = []

        for issue in record.get("issues", []):
            pattern = rule_patterns.get(issue.get("rule_id"), {})
            pattern_type = pattern.get("pattern_type", "candidate_issue")
            issue["pattern_type"] = pattern_type
            if pattern_type == "common_pattern":
                issue["assessment"] = "common_pattern_pending_calibration"
                issue["score_effect"] = "excluded_pending_calibration"
                common_pattern_rules.append(issue.get("rule_id"))
                continue
            if _requires_semantic_assessment(issue):
                pattern_type = "candidate_issue"
            if pattern_type == "deterministic_issue":
                issue["assessment"] = "deterministic_issue"
                deterministic_rules.append(issue.get("rule_id"))
            else:
                issue["assessment"] = "candidate_issue"
                candidate_rules.append(issue.get("rule_id"))
            issue["score_effect"] = "scored"

            # Score each rule only once per work order, keeping the highest severity.
            existing = scoring_by_rule.get(issue["rule_id"])
            if existing is None or SEVERITY_PENALTY.get(issue["severity"], 0) > SEVERITY_PENALTY.get(existing["severity"], 0):
                scoring_by_rule[issue["rule_id"]] = issue

        scoring_issues = list(scoring_by_rule.values())
        score = severity_score(scoring_issues)
        record["score"] = score
        record["audit_level"] = risk_level(score, scoring_issues)
        record["scoring_issue_count"] = len(scoring_issues)
        record["scoring_issues"] = scoring_issues
        record["common_pattern_rules"] = sorted(set(common_pattern_rules))
        record["candidate_rules"] = sorted(set(candidate_rules))
        record["deterministic_rules"] = sorted(set(deterministic_rules))


def _requires_semantic_assessment(issue: dict[str, Any]) -> bool:
    evidence = issue.get("evidence")
    if not isinstance(evidence, str):
        return False
    return '"needs_semantic_review": true' in evidence or '"needs_semantic_review":true' in evidence


def write_report(audit: dict[str, Any], path: Path) -> None:
    summary = audit["summary"]
    records = audit["records"]
    high_risk = [record for record in records if record["audit_level"] == "高风险"]
    need_fix = [record for record in records if record["audit_level"] == "需补正"]

    lines = [
        "# 最近已完成工单确定性规则审核报告",
        "",
        f"- 生成时间：{audit['audit_info']['generated_at']}",
        f"- 审核阶段：{audit['audit_info']['rule_stage']}",
        f"- 工单数量：{audit['audit_info']['order_count']}",
        "",
        "## 总体分布",
        "",
    ]
    for key, value in summary["audit_level_counts"].items():
        lines.append(f"- {key}：{value}")
    lines.extend(["", "## 问题类别分布", ""])
    for key, value in summary["category_counts"].items():
        lines.append(f"- {key}：{value}")
    lines.extend(["", "## 高频规则", ""])
    for rule_id, count in summary["top_rules"][:10]:
        lines.append(f"- {rule_id}：{count}")
    if summary.get("common_patterns"):
        lines.extend(["", "## 群体常态/规则口径待确认", ""])
        for pattern in summary["common_patterns"][:10]:
            lines.append(
                f"- {pattern['rule_id']}：影响 {pattern['affected_order_count']} 个工单，"
                f"覆盖率 {pattern['affected_order_ratio']:.1%}；{pattern['recommendation']}"
            )

    lines.extend(["", "## 高风险/需补正工单", ""])
    for record in high_risk + need_fix:
        issue_list = record.get("scoring_issues") or record.get("issues") or []
        first_issue = issue_list[0]["message"] if issue_list else ""
        lines.append(
            f"- {record['working_order_code']} | 站点 {record['station_id']} | "
            f"{record['order_type']}/{record['maintenance_type']} | "
            f"{record['audit_level']} | {record['score']}分 | {first_issue}"
        )

    lines.extend(["", "## 后续语义审核输入建议", ""])
    lines.append("- 对存在 `FLOW_REMARK_LOW_VALUE`、报警/故障处置闭环不足的工单，进入大模型语义审核。")
    lines.append("- 语义审核重点判断备注是否覆盖原因、措施、结果，报警是否说明数据有效性和恢复情况。")
    lines.append("- 大模型只消费确定性规则筛出的异常工单，降低成本并减少误判面。")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_semantic_candidates(audit: dict[str, Any]) -> dict[str, Any]:
    semantic_rule_ids = {
        "FLOW_REMARK_LOW_VALUE",
        "RF_TW_REMARK_LOW_VALUE",
        "RF_Q_PENDING_NO_REMARK",
        "LIFECYCLE_FINISH_NEAR_DEADLINE",
        "LIFECYCLE_FINISH_WITHOUT_EFFECTIVE_CLOSURE",
        "RF_REQUIRED_FIELD_LOW_VALUE",
        "RF_ENV_TEMP_HUMIDITY_EMPTY",
        "RF_CHECK_TIME_OUTSIDE_RANGE",
        "RF_ABNORMAL_VALUE_NO_REMARK",
    }
    candidates = []
    for record in audit["records"]:
        matched_issues = [
            issue
            for issue in record.get("scoring_issues", [])
            if issue.get("assessment") != "common_pattern_pending_calibration"
            and (issue["rule_id"] in semantic_rule_ids or issue["severity"] == "高")
        ]
        if not matched_issues:
            continue
        candidates.append(
            {
                "working_order_code": record["working_order_code"],
                "station_id": record["station_id"],
                "order_type": record["order_type"],
                "maintenance_type": record["maintenance_type"],
                "finish_time": record["finish_time"],
                "deterministic_score": record["score"],
                "deterministic_level": record["audit_level"],
                "workflow_steps": record["workflow_steps"],
                "rf_tables": record["rf_tables"],
                "semantic_focus": sorted({issue["rule_id"] for issue in matched_issues}),
                "evidence_issues": matched_issues[:12],
            }
        )
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "purpose": "input_candidates_for_llm_semantic_audit",
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


# Phase 2 migration: keep legacy definitions in place for now, but route the
# public engine names through the modular ops_audit package.
classify_rule_patterns = modular_classify_rule_patterns
apply_rule_pattern_assessment = modular_apply_rule_pattern_assessment
write_report = modular_write_report
build_semantic_candidates = modular_build_semantic_candidates
build_semantic_review_tasks = modular_build_semantic_review_tasks
build_semantic_review_results = modular_build_semantic_review_results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--create-time-start")
    parser.add_argument("--create-time-end")
    parser.add_argument("--finish-time-start")
    parser.add_argument("--finish-time-end")
    parser.add_argument("--station-id", action="append", dest="station_ids")
    parser.add_argument("--order-type", action="append", dest="order_types")
    parser.add_argument("--maintenance-type", action="append", dest="maintenance_types")
    parser.add_argument("--working-order-code", action="append", dest="working_order_codes")
    parser.add_argument("--input", type=Path, help="Use an existing fetched dataset JSON instead of querying SQL Server")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.input:
        dataset = json.loads(args.input.read_text(encoding="utf-8"))
    else:
        dataset = fetch_dataset(
            WorkOrderDatasetFilter(
                limit=args.limit,
                create_time_start=args.create_time_start,
                create_time_end=args.create_time_end,
                finish_time_start=args.finish_time_start,
                finish_time_end=args.finish_time_end,
                station_ids=args.station_ids,
                order_types=args.order_types,
                maintenance_types=args.maintenance_types,
                working_order_codes=args.working_order_codes,
            )
        )
        (args.output_dir / "latest_finished_work_orders_dataset.json").write_text(
            json.dumps(dataset, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    audit = audit_dataset(dataset)
    (args.output_dir / "latest_finished_work_orders_deterministic_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    semantic_candidates = build_semantic_candidates(audit)
    (args.output_dir / "latest_finished_work_orders_semantic_candidates.json").write_text(
        json.dumps(semantic_candidates, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    semantic_review_tasks = build_semantic_review_tasks(audit)
    (args.output_dir / "latest_finished_work_orders_semantic_review_tasks.json").write_text(
        json.dumps(semantic_review_tasks, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    semantic_review_results = build_semantic_review_results(audit, dataset)
    (args.output_dir / "latest_finished_work_orders_semantic_review_results.json").write_text(
        json.dumps(semantic_review_results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_report(
        audit,
        args.output_dir / "latest_finished_work_orders_deterministic_report.md",
        dataset=dataset,
    )
    print(json.dumps(audit["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
