# -*- coding: utf-8 -*-
"""Add bsd_devicetype dictionary to sync_config.json (idempotent)."""
import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

PATH = r"E:\Tools\suyuan-jiangsu\sync\sync_config.json"
cfg = json.load(open(PATH, encoding="utf-8"))

spec = {
    "source_db": "air_province_bsd",
    "source_table": "dbo.bsd_DeviceType",
    "columns": [
        "Id", "Code", "Name", "CreateTime", "CreateUserId", "UpdateTime",
        "UpdateUserId", "status", "OrderId", "PollutantCode",
    ],
    "column_types": {
        "Id": "integer",
        "CreateTime": "timestamp",
        "UpdateTime": "timestamp",
        "status": "boolean",
        "OrderId": "integer",
    },
    "mode": "daily_full",
    "apply_window": False,
    "pk": ["Id"],
}

if "bsd_devicetype" in cfg["tables"]:
    print("update: bsd_devicetype")
else:
    print("add: bsd_devicetype")
cfg["tables"]["bsd_devicetype"] = spec

with open(PATH, "w", encoding="utf-8", newline="\n") as f:
    json.dump(cfg, f, ensure_ascii=False, indent=2)
    f.write("\n")
print("total tables:", len(cfg["tables"]))
