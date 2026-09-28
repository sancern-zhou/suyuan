"""Independent query columns for API facts and business classification.

Arrays remain ordered JSON arrays in their own columns (OPENJSON for exact
membership/grouping), never delimiter-joined strings or inferred lot pairs.
"""
import json
from decimal import Decimal

API_COLUMNS = {
    "bid_id": "bigint", "county": "nvarchar(100)",
    "caller_id": "bigint", "caller_base_type": "nvarchar(100)",
    "caller_type": "nvarchar(100)", "agency_name": "nvarchar(300)",
    "bid_type": "nvarchar(50)", "bid_process": "nvarchar(100)",
    "money": "decimal(24,4)", "money_wan": "decimal(24,4)",
    "bid_method": "nvarchar(100)", "bid_no": "nvarchar(500)",
    "signup_time": "nvarchar(100)", "tender_time": "nvarchar(100)",
    "service_end_date": "nvarchar(100)", "exists_bid_file": "int",
    "winner_names": "nvarchar(max)", "winner_ids": "nvarchar(max)",
    "winner_moneys": "nvarchar(max)", "tender_names": "nvarchar(max)",
    "sm_names": "nvarchar(max)", "brand_names": "nvarchar(max)",
}
ARRAY_COLUMNS = {"winner_names", "winner_ids", "winner_moneys", "tender_names", "sm_names", "brand_names"}
CLASSIFICATION_COLUMNS = {
    "business_type": "nvarchar(100)", "content_tags": "nvarchar(max)",
    "notice_stage": "nvarchar(50)", "classification_status": "nvarchar(50)",
    "tag_evidence": "nvarchar(max)",
}
QUERY_COLUMNS = {**API_COLUMNS, **CLASSIFICATION_COLUMNS}


def query_column_values(classification):
    api = classification.get("source_metadata", {}).get("api_list_fields", {})
    values = {}
    for name in API_COLUMNS:
        value = api.get(name)
        if name in ARRAY_COLUMNS and value is not None:
            if not isinstance(value, list):
                raise ValueError(f"Expected API array: {name}")
            value = json.dumps(value, ensure_ascii=False)
        elif value == "" and API_COLUMNS[name] in {"bigint", "int", "decimal(24,4)"}:
            value = None
        if value is not None and API_COLUMNS[name] == "decimal(24,4)":
            value = Decimal(str(value)).quantize(Decimal("0.0001"))
            if not value.is_finite():
                raise ValueError(f"Invalid API amount: {name}")
        values[name] = value
    for name in CLASSIFICATION_COLUMNS:
        value = classification.get(name)
        if name in {"content_tags", "tag_evidence"} and value is not None:
            value = json.dumps(value, ensure_ascii=False)
        values[name] = value
    return tuple(values.values())
