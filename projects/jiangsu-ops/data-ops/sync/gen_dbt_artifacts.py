# -*- coding: utf-8 -*-
"""gen_dbt_artifacts.py — 从契约单一事实源派生 dbt 工件。

与 gen_tool_contract.py 同一设计哲学: datasets/*.yaml 是唯一手工维护的契约源,
本脚本将其渲染为 dbt 项目的三件套(全部为生成物, 不要手改):

  1. dbt/models/sources.yml   — jiangsu_ods 全部源表(sync_config.json 的表清单)
  2. dbt/models/schema.yml    — 11 张 mart/dim 模型的描述/列文档/数据测试
  3. dbt/snapshots/*.sql      — 字典/规则表每日 check 快照(SCD2 变更留痕)

用法: python gen_dbt_artifacts.py          # 重新生成
      python gen_dbt_artifacts.py --check  # 校验生成物是否与源一致(供 dq_check 调用)

修改口径/加表请改 datasets/*.yaml 或 sync_config.json, 然后重跑本脚本。
"""
import io
import json
import sys
from pathlib import Path

import yaml

SYNC_DIR = Path(__file__).resolve().parent
DBT_DIR = SYNC_DIR.parent / "dbt"
DATASETS_DIR = SYNC_DIR / "datasets"

# ---------------------------------------------------------------- 测试配置
# key = 模型名; value = {列名: [测试...]}, severity=warn 的测试不阻塞构建。
# 已知数据现实的容差(如 5 张 CAL 校准工单无站点码)用 warn, 其余硬性。
MODEL_TESTS = {
    "dim_station": {
        "station_code": ["unique", "not_null"],
        "uniquecode": ["not_null"],
    },
    "dim_device": {
        "device_code": ["warn_unique"],
    },
    "mart_work_order_analysis": {
        "id": ["unique", "not_null"],
        "station_code": ["warn_not_null"],  # 已知 ~5 张 CAL 校准单无站点码
    },
    "mart_alarm_event_analysis": {
        "id": ["unique", "not_null"],
    },
    "mart_station_device_health": {
        "station_code": ["unique", "not_null"],
    },
    "mart_station_daily_profile": {
        "profile_date": ["not_null"],
        "station_code": ["not_null"],
    },
    "mart_qc_execution_analysis": {
        "id": ["unique", "not_null"],
        "station_code": ["warn_not_null"],  # 经 uniquecode 关联, 个别未挂站
    },
    "mart_qc_arrangement_analysis": {
        "id": ["unique", "not_null"],
    },
    "mart_inspection_analysis": {
        "id": ["unique", "not_null"],
    },
    "mart_performance_analysis": {
        "station_code": ["warn_not_null"],
        "perf_month": ["warn_not_null"],
    },
    "mart_blackout_analysis": {
        "id": ["unique", "not_null"],
    },
    "mart_qc_backorder_analysis": {
        "id": ["unique", "not_null"],
        "station_code": ["warn_not_null"],  # 窗口内实测 0% 空, 保守 warn
    },
    "dim_device_parameter": {
        "devicemodel": ["not_null"],
        "parameterid": ["not_null"],
        "parameter_name": ["not_null"],  # 模型已过滤空参数名, 硬测守住
        "devicemodel_id": ["warn_not_null"],  # 型号码非数字则置空(理论不出现)
    },
    "mart_device_lifecycle_analysis": {
        "event_id": ["unique", "not_null"],
        "event_time": ["not_null"],
        "station_code": ["warn_not_null"],  # 部分日志无站点码且设备为入库/孤儿设备
    },
}

# 源表新鲜度: 只对"有干净更新时间列"的源声明(其余表的时效由 dq_check.py 的
# watermark 心跳负责, 不要在此硬凑)。warn_after=24h 仅告警不阻塞。
SOURCE_FRESHNESS = {
    "mtc_working_order": "updatetime",
    "mtc_working_order_detail": "updatetime",
    "qc_historyresult": "create_time",
    "pw_taskitem": "updatetime",
    "bsd_station": "updatetime",
}

SOURCE_NOTES = {
    "mtc_working_order": "故障工单主表(5分钟增量, UpdateTime)",
    "mtc_working_order_detail": "工单流转节点明细(5分钟增量)",
    "alm_summary": "站点告警汇总(5分钟增量)",
    "bsd_station": "站点目录字典(5分钟增量)",
    "bsd_city": "地市字典(code 多层级重复, join 必须去重)",
    "bsd_device": "设备台账字典(每日全量)",
    "alm_rule": "告警规则配置(每日全量, 无更新时间列 → 见 snapshots/alm_rule.sql)",
    "rf_common": "非故障工单表单体 rFCommon 矩阵(5分钟增量, ops_audit 取数源)",
    "qc_historyresult": "质控执行结果(5分钟增量)",
    "qc_arrangeresult": "质控任务安排(每日全量)",
    "pw_taskitem": "巡检任务项(5分钟增量)",
    "pw_task": "巡检任务定义(每日全量)",
    "opa_performance_tworate": "月度两率考核(每日全量)",
    "opa_performance_qaqc": "月度三项评分(每日全量)",
    "mtc_blackout": "停电报备单(每日全量)",
    "opa_kq_attendance": "考勤签到(增量, 8月以来仅8条为源库现状)",
    "log_device": "设备生命周期状态变更日志(每日全量, 窗口≥2026-07-01; deviceidstate×eventstate 状态流转, WorkingOrderCode 可关联故障工单; 2026-10-04 新纳入, 解锁备机更换及时性场景)",
    "qc_backorderarrangelog": "质控补测/回调安排日志(每日全量, 窗口≥2026-07-01; state/datatype 枚举语义待平台确认; 补测风暴预警与质控闭环下游)",
    "bsd_supply": "质控耗材台账(每日全量; 滤膜/硅胶/纸带, 挂站点; 数量与工单字段源库大面积为空)",
    "bsd_moniter_parameter": "设备型号健康参数阈值字典(每日全量, 上下限/预警限; 供 dim_device_parameter; 开SCD2快照)",
    "dev_scrap": "设备报废审批(每日全量, 行数极少; 设备生命周期终点, 配合 log_device)",
    "bsd_devicetype": "设备类型字典(Code→Name, 27行; dim_device.device_type_name 的来源)",
}

# 每日 check 快照的字典/规则表。事实型大表(工单/告警/质控结果)不入快照 —— 
# 它们的变更历史本来就在业务主键上, 快照留给"上游会悄悄改配置"的场景。
SNAPSHOT_TABLES = [
    "alm_rule", "bsd_city", "bsd_device", "bsd_devicetype", "bsd_maintenanceunit", "bsd_moniter_parameter", "bsd_region",
    "bsd_station", "bsd_usergroup", "bsd_usergroup_station",
    "bsd_usergroup_station_devicetype", "bsd_usergroup_user",
    "mtc_faultcontent", "mtc_faultcontentitem", "opa_user_info", "pw_task",
    "qc_task", "qa_standardmaterialstorage", "rf_ruleitem",
    "wfl_workflow", "wfl_workflowtask",
]

DATASET_TO_MODEL = {
    "dim_station": "dim_station",
    "dim_device": "dim_device",
    "mart_work_order_analysis": "mart_work_order_analysis",
    "mart_alarm_event_analysis": "mart_alarm_event_analysis",
    "mart_station_device_health": "mart_station_device_health",
    "mart_station_daily_profile": "mart_station_daily_profile",
    "mart_qc_execution_analysis": "mart_qc_execution_analysis",
    "mart_qc_arrangement_analysis": "mart_qc_arrangement_analysis",
    "mart_inspection_analysis": "mart_inspection_analysis",
    "mart_performance_analysis": "mart_performance_analysis",
    "mart_blackout_analysis": "mart_blackout_analysis",
    "mart_qc_backorder_analysis": "mart_qc_backorder_analysis",
    "dim_device_parameter": "dim_device_parameter",
    "mart_device_lifecycle_analysis": "mart_device_lifecycle_analysis",
}


def _fmt_test(test: str) -> dict | str:
    """warn_ 前缀 = warn 级别, 不阻塞构建。"""
    if test.startswith("warn_"):
        return {test[5:]: {"config": {"severity": "warn"}}}
    return test


def render_sources_yml() -> str:
    cfg = json.loads((SYNC_DIR / "sync_config.json").read_text(encoding="utf-8"))
    tables = []
    for name in sorted(cfg["tables"]):
        entry = {"name": name}
        if name in SOURCE_NOTES:
            entry["description"] = SOURCE_NOTES[name]
        if name in SOURCE_FRESHNESS:
            entry["loaded_at_field"] = SOURCE_FRESHNESS[name]
            entry["freshness"] = {
                "warn_after": {"count": 24, "period": "hour"},
            }
        tables.append(entry)
    doc = {
        "version": 2,
        "sources": [
            {
                "name": "jiangsu_ods",
                "schema": "jiangsu_ods",
                "database": "suyuan_jiangsu",
                "description": (
                    "SQL Server 原库经 sync_table.py 同步落地的 ODS 层"
                    "(sync_config.json 为表清单事实源, 本文件由 gen_dbt_artifacts.py 生成)。"
                    "fact 表窗口自 2026-07-01, 更早历史不可查。"
                ),
                "tables": tables,
            }
        ],
    }
    return yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=100)


def render_schema_yml() -> str:
    models = []
    for dataset, model in DATASET_TO_MODEL.items():
        path = DATASETS_DIR / f"{dataset}.yaml"
        if not path.exists():
            continue
        contract = yaml.safe_load(path.read_text(encoding="utf-8"))
        desc_lines = [contract.get("description", "").strip()]
        caveats = contract.get("known_caveats") or []
        if caveats:
            desc_lines.append("已知口径注意: " + "; ".join(c.strip() for c in caveats))
        grain = contract.get("grain")
        if grain:
            desc_lines.append(f"粒度: {grain}")
        columns = []
        for col in contract.get("columns") or []:
            entry = {"name": col["name"], "description": col.get("business", "")}
            tests = MODEL_TESTS.get(model, {}).get(col["name"], [])
            if tests:
                entry["data_tests"] = [_fmt_test(t) for t in tests]
            columns.append(entry)
        models.append({
            "name": model,
            "description": "\n".join(d for d in desc_lines if d),
            "columns": columns,
        })
    doc = {"version": 2, "models": models}
    return yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=100)


def render_snapshots() -> dict[str, str]:
    out = {}
    for table in SNAPSHOT_TABLES:
        note = SOURCE_NOTES.get(table, "")
        out[f"{table}.sql"] = (
            "{% snapshot " + table + " %}\n"
            "-- 每日 check 快照(SCD2): 业务列哈希判变, 上游增删改自动留痕。\n"
            "-- business_columns 宏排除同步元数据列(_sync_batch 每次全量都变, 不排除会全表误判为变更)。\n"
            f"-- 源: jiangsu_ods.{table}{' — ' + note if note else ''}\n"
            "select {{ business_columns(source('jiangsu_ods', '" + table + "')) }}\n"
            "from {{ source('jiangsu_ods', '" + table + "') }}\n"
            "{% endsnapshot %}\n"
        )
    return out


def main() -> int:
    generated = {
        DBT_DIR / "models" / "sources.yml": render_sources_yml(),
        DBT_DIR / "models" / "schema.yml": render_schema_yml(),
    }
    for rel, content in render_snapshots().items():
        generated[DBT_DIR / "snapshots" / rel] = content

    if "--check" in sys.argv:
        drift = [
            str(p) for p, c in generated.items()
            if not p.exists() or p.read_text(encoding="utf-8") != c
        ]
        if drift:
            print("DBT_ARTIFACT_DRIFT: " + ", ".join(drift))
            print("请运行 python gen_dbt_artifacts.py 重新生成")
            return 1
        print("dbt artifacts OK (sources/schema/snapshots 与契约一致)")
        return 0

    for path, content in generated.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        # 无 BOM UTF-8(PowerShell UTF8 带 BOM 的坑, 见 2026-09-22 教训)
        with io.open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
