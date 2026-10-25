# -*- coding: utf-8 -*-
"""生成 ODS 兜底表白名单（execute_guangdong_mart_sql 的原始层兜底通道）。

设计目标：**同步进 guangdong_ods 的表不允许 Agent 查不到**。
mart/dim/高频表单契约覆盖不到的表（中低频表单 rf_m_*/rf_q_*/rf_hy_*/rf_y_*、
检查评分 sec_checkscore* 等），至少能通过同一个 SQL 工具以原始表形式托底查询。

兜底清单的推导规则（全自动，避免人工清单漂移）：
    fallback = (dbt/models/sources.yml 声明的全部 ODS 表)
               - (已被契约覆盖的源表)
               + EXTRA_FALLBACK（mart 覆盖了但没暴露行级明细的表）

覆盖判定 = 该表在 sync/datasets/*.yaml 有自己的契约（dataset 同名 yaml），
          或被某个 dbt 模型 source() 引用且该模型名出现在 datasets/*.yaml。

同步范围取 sources.yml（仓库内提交的 ODS 层声明，与 dbt 模型同源维护）；
真实库面由 audit_ods_coverage.py 对照 pg_class 复核，库里有、声明里没有的表
会在审计中作为 GAP 直接暴露。

用法:
  PYTHONPATH=backend python projects/guangdong/data-ops/sync/gen_ods_fallback_contract.py            # 生成并写入 ods_contract.txt
  PYTHONPATH=backend python projects/guangdong/data-ops/sync/gen_ods_fallback_contract.py --check    # 校验生成物（dq_check 漂移检测）
  PYTHONPATH=backend python projects/guangdong/data-ops/sync/gen_ods_fallback_contract.py --print    # 仅打印
  PYTHONPATH=backend python projects/guangdong/data-ops/sync/gen_ods_fallback_contract.py --grant    # 给 agent_reader 授权清单内表的 SELECT

退出码: --check 不一致或存在未登记用途的表时返回 1。
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

from app.utils.path_config import resolve_agent_path, format_agent_path

SYNC_DIR = Path(__file__).resolve().parent
DATASETS_DIR = SYNC_DIR / "datasets"
DBT_MODELS_DIR = SYNC_DIR.parent / "dbt" / "models"
SOURCES_YML = DBT_MODELS_DIR / "sources.yml"
TARGET_PATH = resolve_agent_path(
    "backend/app/tools/query/guangdong_ops_sql_query/ods_contract.txt"
)

# 广东源库为单库年度窗口（无按站分片大表），无需分片排除；
# 若后续引入按站分片表，在此登记正则，避免分片淹没兜底契约。
SHARD_RE = re.compile(r"^$")

# mart 已覆盖、但仍需原始表兜底的例外（广东现行无；登记标准：
# mart 只给了汇总值或部分列，而"某条明细/某条映射是什么"仍不可查时启用）。
EXTRA_FALLBACK: set[str] = set()

# 每张兜底表的用途说明（必须人工登记；新增同步表若落到兜底清单而没有说明，
# 生成直接失败，逼一次"这表要不要给 Agent 查"的决策）。
ODS_TABLE_NOTES = {
    # ---- 质控季度表单（rf_q_*） ----
    "rf_q_gaseousflowcheck": "气态分析仪流量检查记录表（季度）",
    "rf_q_gaseousmultipoint_co": "CO 分析仪多点校准记录表（季度）",
    "rf_q_gaseousmultipoint_no2": "NO2 分析仪多点校准记录表（季度）",
    "rf_q_gaseousmultipoint_o3": "O3 分析仪多点校准记录表（季度）",
    "rf_q_gaseousmultipoint_so2": "SO2 分析仪多点校准记录表（季度）",
    "rf_q_gaseousprecision_co": "CO 分析仪精密度检查记录表（季度）",
    "rf_q_gaseousprecision_no2": "NO2 分析仪精密度检查记录表（季度）",
    "rf_q_gaseousprecision_o3": "O3 分析仪精密度检查记录表（季度）",
    "rf_q_gaseousprecision_so2": "SO2 分析仪精密度检查记录表（季度）",
    "rf_q_longopticalpath_no2": "NO2 长光程分析仪检查记录表（季度）",
    "rf_q_longopticalpath_o3": "O3 长光程分析仪检查记录表（季度）",
    "rf_q_longopticalpath_so2": "SO2 长光程分析仪检查记录表（季度）",
    "rf_q_pm10runstatuscheck": "PM10 分析仪运行状态检查记录表（季度）",
    "rf_q_pm25runstatuscheck": "PM2.5 分析仪运行状态检查记录表（季度）",
    "rf_q_pmpressure": "颗粒物压力检查记录表（季度）",
    "rf_q_stationdeviceclean": "站点设备清洁记录表（季度）",
    "rf_q_stationmaintaincheck": "站房维护检查记录表（季度）",
    # ---- 月度表单（rf_m_*） ----
    "rf_m_gaseouscalicheck": "气态分析仪校准检查记录表（月度）",
    "rf_m_gaseouscalidevicecheck": "气态校准设备检查记录表（月度）",
    "rf_m_gaseousflowcheck": "气态分析仪流量检查记录表（月度）",
    "rf_m_manualcomparison": "手工比对记录表（月度）",
    "rf_m_manualcomparisondetail": "手工比对明细记录表（月度，与 rf_m_manualcomparison 按表单关联）",
    "rf_m_membraneweighing": "滤膜称重记录表（月度）",
    "rf_m_pmdevicemaintain": "颗粒物仪器维护记录表（月度）",
    "rf_m_stationdevicemaintain": "站点设备维护记录表（月度）",
    "rf_m_stationmaintaincheck": "站房维护检查记录表（月度）",
    # ---- 半年表单（rf_hy_*） ----
    "rf_hy_environmenthumidity": "环境湿度校准记录表（半年）",
    "rf_hy_gaseouscalidevicecheck": "气态校准设备检查记录表（半年）",
    "rf_hy_noxconversionrate": "NOx 分析仪转化率检查记录表（半年）",
    "rf_hy_o3valuepass": "O3 校准仪（工作标准）量值传递记录表（半年）",
    "rf_hy_stationdevicemaintain": "站点设备维护记录表（半年）",
    "rf_hy_visibilitycali": "能见度仪校准记录表（半年）",
    # ---- 年度维保表单（rf_y_*） ----
    "rf_y_devicechange": "设备更换记录表（年度）",
    "rf_y_devicerepair": "设备维修记录表（年度）",
    "rf_y_preventivemaintenance": "预防性维护记录表（年度）",
    # ---- 两周表单（rf_tw_*） ----
    "rf_tw_cleancuttinghead": "颗粒物切割头清洗记录表（两周）",
    "rf_tw_pmflowcalibrate": "颗粒物流量校准记录表（两周）",
    "rf_tw_pmflowcheck": "颗粒物流量检查记录表（两周）",
    # ---- 周检长尾表单（rf_w_*，高频周检主体 8 张在主契约） ----
    "rf_w_graincalibrationcheck_pm10": "PM10 颗粒物校准检查记录表（每周）",
    "rf_w_graincalibrationcheck_pm25": "PM2.5 颗粒物校准检查记录表（每周）",
    "rf_w_graincalibrationcheckattach": "颗粒物校准检查附件表（每周）",
    "rf_w_longopticalpath": "长光程分析仪运行状况检查记录表（每周）",
    "rf_w_standard_all": "标准物质检查记录表（每周）",
    # ---- 组分网/仪器巡检表单 ----
    "rf_bcmonitorinspection": "BC（黑碳）仪监测巡检记录表单（组分网）",
    "rf_pm1monitorinspection": "PM1 监测巡检记录表单（组分网）",
    "sup_rf_monthnephelometercheck": "组分网浊度仪月检查记录表单",
    "sup_rf_nephelometercalibration": "组分网浊度仪校准记录表单",
    # ---- 现场检查（SEC）表单 ----
    "rf_sec_inspection": "现场检查（SEC）巡检表单",
    "rf_sec_instrumentrecord": "现场检查（SEC）仪器记录表单",
    "rf_sec_monitoringcheck": "现场检查（SEC）监测核查表单",
    # ---- 现场检查评分 ----
    "sec_checkscore": "现场检查评分明细（dbo.SEC_CHECKSCORE；评分溯源用，考核汇总用 mart_performance_analysis）",
    "sec_checkscore_sx": "现场检查评分变体表（dbo.SEC_CHECKSCORE_SX，历史留存）",
    "sec_checkscore_sxnew": "现场检查评分变体表（dbo.SEC_CHECKSCORE_SXNEW，历史留存）",
}

GUIDE_HEADER = (
    "\n\n【ODS 兜底表（原始层，中低频表单/明细取证用；共{n}张）】\n"
    "仅当上方契约表无法回答时使用。兜底表为平台原值，无业务口径加工；"
    "引用请写全限定名 guangdong_ods.<表名>；查询必须带过滤条件与 LIMIT，禁止全表扫描；"
    "列结构用 describe_table 获取（表单题目项列不逐列说明，按列名语义取用）。\n"
)

FILE_HEADER = (
    "# generated from dbt/models/sources.yml + datasets/*.yaml + dbt/models by "
    "gen_ods_fallback_contract.py — DO NOT EDIT BY HAND\n"
    "# 兜底清单 = 已同步 ODS 表(sources.yml) - 已被契约覆盖的源表 + EXTRA_FALLBACK；"
    "漂移检测见 dq_check.py，库面复核见 audit_ods_coverage.py\n"
)


def synced_logical_tables() -> list[str]:
    """ODS 层声明的同步表清单（dbt/models/sources.yml，仓库内提交）。"""
    if not SOURCES_YML.is_file():
        raise SystemExit("sources.yml 未找到: %s" % SOURCES_YML)
    tables = re.findall(r"^  - name: ([A-Za-z0-9_]+)\s*$", SOURCES_YML.read_text(encoding="utf-8"), re.M)
    if not tables:
        raise SystemExit("sources.yml 未解析到任何 source 表")
    return sorted(t.lower() for t in tables if not SHARD_RE.match(t.lower()))


def contract_datasets() -> set[str]:
    return {p.stem.lower() for p in DATASETS_DIR.glob("*.yaml")}


def source_usage() -> dict[str, set[str]]:
    """ODS 表 -> 引用它的 dbt 模型名集合。"""
    usage: dict[str, set[str]] = {}
    if not DBT_MODELS_DIR.is_dir():
        raise SystemExit("dbt models dir not found: %s" % DBT_MODELS_DIR)
    for path in DBT_MODELS_DIR.rglob("*.sql"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(
            r"source\(\s*'guangdong_ods'\s*,\s*'([A-Za-z0-9_]+)'\s*\)", text
        ):
            usage.setdefault(match.group(1).lower(), set()).add(path.stem.lower())
    return usage


def fallback_tables() -> tuple[list[str], list[str]]:
    """返回 (兜底表清单, 被契约覆盖的表清单)。"""
    datasets = contract_datasets()
    usage = source_usage()
    fallback, covered = [], []
    for table in synced_logical_tables():
        models = usage.get(table, set())
        if table in datasets or (models & datasets):
            if table in EXTRA_FALLBACK:
                fallback.append(table)
            else:
                covered.append(table)
        else:
            fallback.append(table)
    overlap = sorted(set(fallback) & datasets)
    if overlap:
        raise SystemExit("兜底表与主契约重名（契约 yaml 与兜底互斥）: " + ", ".join(overlap))
    return sorted(set(fallback)), sorted(set(covered))


def build_contract() -> str:
    tables, _covered = fallback_tables()
    missing = [t for t in tables if t not in ODS_TABLE_NOTES]
    if missing:
        raise SystemExit(
            "以下兜底表缺少用途说明，请在 ODS_TABLE_NOTES 登记后再生成: " + ", ".join(missing)
        )
    stale = sorted(set(ODS_TABLE_NOTES) - set(tables))
    if stale:
        raise SystemExit(
            "ODS_TABLE_NOTES 存在已不在同步范围/契约中的表，请清理: " + ", ".join(stale)
        )
    segments = []
    for table in tables:
        segments.append("\n- {t}：{note}".format(t=table, note=ODS_TABLE_NOTES[table]))
    body = GUIDE_HEADER.format(n=len(tables)) + "".join(segments)
    return FILE_HEADER + "TABLES: " + ",".join(tables) + "\nGUIDE_START" + body + "\nGUIDE_END\n"


def _dsn() -> str:
    dsn = os.getenv("OPS_MART_DATABASE_URL", "").replace("+asyncpg", "")
    if dsn:
        return dsn
    cfg = SYNC_DIR / "sync_config.json"
    if cfg.is_file():
        try:
            dsn = json.loads(cfg.read_text(encoding="utf-8"))["target"]["dsn"]
        except Exception:  # noqa: BLE001
            dsn = ""
    if not dsn:
        raise SystemExit("OPS_MART_DATABASE_URL / sync_config.json target.dsn 均未配置，无法授权")
    return dsn


async def grant_select(tables: list[str]) -> int:
    import asyncpg

    conn = await asyncpg.connect(_dsn())
    try:
        for table in tables:
            await conn.execute(
                f'GRANT SELECT ON guangdong_ods."{table}" TO agent_reader'
            )
        # 兜底查询的"数据截至"时点来自同步水位(只读元数据, 不含业务数据)
        await conn.execute("GRANT SELECT ON guangdong_sync.ods_sync_watermark TO agent_reader")
        rows = await conn.fetch(
            """SELECT table_name FROM information_schema.role_table_grants
               WHERE grantee='agent_reader' AND table_schema='guangdong_ods'"""
        )
    finally:
        await conn.close()
    granted = {r["table_name"] for r in rows}
    missing = [t for t in tables if t not in granted]
    print(f"granted: {len(tables) - len(missing)}/{len(tables)} tables to agent_reader")
    if missing:
        print("MISSING GRANT: " + ", ".join(missing))
        return 1
    return 0


def main() -> int:
    content = build_contract()
    if "--print" in sys.argv:
        print(content)
        return 0
    if "--grant" in sys.argv:
        tables, _ = fallback_tables()
        return asyncio.run(grant_select(tables))
    if "--check" in sys.argv:
        try:
            deployed = io.open(TARGET_PATH, encoding="utf-8").read()
        except OSError:
            print("ODS CONTRACT DRIFT: ods_contract.txt missing at", TARGET_PATH)
            return 1
        if deployed == content:
            print("ODS CONTRACT OK: ods_contract.txt matches sync scope")
            return 0
        print(
            "ODS CONTRACT DRIFT: ods_contract.txt differs — run gen_ods_fallback_contract.py"
        )
        return 1
    io.open(TARGET_PATH, "w", encoding="utf-8", newline="\n").write(content)
    tables, covered = fallback_tables()
    print(
        "written:", format_agent_path(TARGET_PATH),
        "| fallback tables:", len(tables),
        "| contract-covered:", len(covered),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
