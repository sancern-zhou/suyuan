# -*- coding: utf-8 -*-
"""Add B/C-domain tables to sync_config.json (idempotent)."""
import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

PATH = r"E:\Tools\suyuan-jiangsu\sync\sync_config.json"
cfg = json.load(open(PATH, encoding="utf-8"))

specs = {
    # 质控补测/回调安排日志(事实, 窗口≥2026-07-01)
    "qc_backorderarrangelog": {
        "source_db": "air_province_data",
        "source_table": "dbo.qc_backorderarrangelog",
        "columns": [
            "id", "uniquecode", "create_time", "start_time", "end_time",
            "datatype", "state", "pollutantname", "operator", "operationtype",
            "source", "backupip", "destination", "stationcode",
        ],
        "column_types": {
            "id": "integer",
            "datatype": "integer",
            "state": "integer",
            "operationtype": "integer",
            "source": "integer",
            "destination": "integer",
            "create_time": "timestamp",
            "start_time": "timestamp",
            "end_time": "timestamp",
        },
        "incremental_column": "create_time",
        "incremental_type": "datetime",
        "mode": "daily_full",
        "apply_window": True,
        "pk": ["id"],
    },
    # 质控耗材台账(台账级, 全量768行, 不开窗)
    "bsd_supply": {
        "source_db": "air_province_bsd",
        "source_table": "dbo.bsd_supply",
        "columns": [
            "Id", "supplyname", "supplybrand", "supplymodel", "supplycode",
            "supplynum", "supplyunit", "expireddate", "expireduserid",
            "operationsunitid", "remark", "createuserid", "createdate",
            "regionid", "processtype", "stationcode", "addcreatetime", "syyy",
            "usertype", "scope", "usednum", "workingordercode", "createusername",
        ],
        "column_types": {
            "Id": "integer",
            "supplynum": "double precision",
            "processtype": "numeric",
            "usednum": "integer",
            "expireddate": "timestamp",
            "createdate": "timestamp",
            "addcreatetime": "timestamp",
        },
        "mode": "daily_full",
        "apply_window": False,
        "pk": ["Id"],
    },
    # 设备型号健康参数阈值字典(全量428行, 开快照)
    "bsd_moniter_parameter": {
        "source_db": "air_province_bsd",
        "source_table": "dbo.bsd_moniter_parameter",
        "columns": [
            "id", "devicemodel", "parameterid", "series", "statusname",
            "toplimit", "lowlimit", "warntoplimit", "warnlowlimit", "unit",
            "status", "remark", "serialnumber", "createtime", "modifytime",
            "creator", "modifier", "describe", "warntype",
        ],
        "column_types": {
            "id": "integer",
            "toplimit": "numeric",
            "lowlimit": "numeric",
            "warntoplimit": "numeric",
            "warnlowlimit": "numeric",
            "status": "boolean",
            "serialnumber": "integer",
            "createtime": "timestamp",
            "modifytime": "timestamp",
        },
        "mode": "daily_full",
        "apply_window": False,
        "pk": ["id"],
    },
    # 设备报废审批(全量1行, 生命周期终点)
    "dev_scrap": {
        "source_db": "opa_product_data",
        "source_table": "dbo.DEV_SCRAP",
        "columns": [
            "id", "DEVICEID", "APPLYUSERID", "APPLYTIME", "SCRAPREASON",
            "ATTACHID", "APPROVEUSERID", "APPROVETIME", "APPROVEDESCRIPTION",
            "APPROVERESULT",
        ],
        "column_types": {
            "id": "integer",
            "DEVICEID": "integer",
            "APPLYUSERID": "integer",
            "APPROVEUSERID": "integer",
            "APPLYTIME": "timestamp",
            "APPROVETIME": "timestamp",
            "APPROVERESULT": "boolean",
        },
        "mode": "daily_full",
        "apply_window": False,
        "pk": ["id"],
    },
}

for name, spec in specs.items():
    if name in cfg["tables"]:
        print("update:", name)
    else:
        print("add:", name)
    cfg["tables"][name] = spec

with open(PATH, "w", encoding="utf-8", newline="\n") as f:
    json.dump(cfg, f, ensure_ascii=False, indent=2)
    f.write("\n")
print("total tables:", len(cfg["tables"]))
