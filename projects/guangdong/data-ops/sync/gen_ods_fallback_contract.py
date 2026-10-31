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
    # ---- 站点-组织映射原始层 ----
    "sys_departmentstation": "站点-部门授权映射原始表（dbo.SYS_DEPARTMENTSTATION，约 518 行；"
        "dim_station_user 的部门取自人员所属部门，本表保留源系统站点×部门关系的原始层，部门维度取证用）",
    # ---- 组分网表单/业务表批量接入（2026-10-28 源库活跃度盘点）----
    "sup_rf_bcyearmaintain": "BC（黑碳）分析仪年度维护记录表单（组分网）",
    "sup_rf_calibration_noy": "NOy 分析仪校准记录表单（组分网）",
    "sup_rf_channelflowcalibration": "通道流量校准记录表单（组分网）",
    "sup_rf_chromatotecflowcheck": "Chromatotec 分析仪流量检查记录表单（组分网）",
    "sup_rf_chromatotecmonthmaintain": "Chromatotec 分析仪月维护记录表单（组分网）",
    "sup_rf_chromatotecquartermaintain": "Chromatotec 分析仪季维护记录表单（组分网）",
    "sup_rf_chromatotecweekcheck": "Chromatotec 分析仪周检记录表单（组分网）",
    "sup_rf_co2analyzerinspection": "CO2 分析仪巡检记录表单（组分网）",
    "sup_rf_co2devicemaintain": "CO2 分析仪设备维护记录表单（组分网）",
    "sup_rf_co2halfyeardevicemaintain": "CO2 分析仪半年维护记录表单（组分网）",
    "sup_rf_co2inspection": "CO2 分析仪检查记录表单（组分网）",
    "sup_rf_co2mulitypointcheck_q": "CO2 分析仪多点核查记录表单（季度，组分网）",
    "sup_rf_co2yeardevicemaintain": "CO2 分析仪年度维护记录表单（组分网）",
    "sup_rf_conversionrate_noy": "NOy 分析仪转化率检查记录表单（组分网）",
    "sup_rf_dailyinspection": "组分网设备日常巡检记录表单",
    "sup_rf_equipmentmaintenance": "组分网设备维护记录表单",
    "sup_rf_equipmentstatus": "组分网设备状态记录表单",
    "sup_rf_gacmonthmaintain": "GAC 月维护记录表单（组分网）",
    "sup_rf_gacquartermaintain": "GAC 季维护记录表单（组分网）",
    "sup_rf_gacweekmaintain": "GAC 周维护记录表单（组分网）",
    "sup_rf_gacweekmaintainbymarga": "GAC（MARGA 设备）周维护记录表单（组分网）",
    "sup_rf_gacyearmaintain": "GAC 年维护记录表单（组分网）",
    "sup_rf_heavymetalinspection": "重金属分析仪巡检记录表单（组分网）",
    "sup_rf_leakageratecalibration_i": "泄漏率校准记录表单（组分网）",
    "sup_rf_maintenancerecord": "组分网维护记录表单",
    "sup_rf_monthdevicemaintain_noy": "NOy 分析仪月维护记录表单（组分网）",
    "sup_rf_multicalibration": "组分网多点（多量程）校准记录表单",
    "sup_rf_n2oanalyzerinspection": "N2O 分析仪巡检记录表单（组分网）",
    "sup_rf_nh3analyzerinspection": "NH3 分析仪巡检记录表单（组分网）",
    "sup_rf_nh3calibration": "NH3 分析仪校准记录表单（组分网）",
    "sup_rf_nh3conversionrate": "NH3 分析仪转化率检查记录表单（组分网）",
    "sup_rf_nh3devicemultipoint": "NH3 设备多点校准记录表单（组分网）",
    "sup_rf_nh3gaseouscalidevicecheck": "NH3 气态校准设备检查记录表单（组分网）",
    "sup_rf_nh3instrumentdetectionlimit": "NH3 仪器检出限记录表单（组分网）",
    "sup_rf_nh3instrumentprecision": "NH3 仪器精密度记录表单（组分网）",
    "sup_rf_nh3monthdevicemaintain": "NH3 设备月维护记录表单（组分网）",
    "sup_rf_nh3responsetimeinspection": "NH3 响应时间检查记录表单（组分网）",
    "sup_rf_nmhc_qualitycontroldatadetail": "NMHC 质控数据明细（组分网）",
    "sup_rf_o3laserradarcalibration": "O3 激光雷达校准记录表单（组分网）",
    "sup_rf_o3laserradarcheck": "O3 激光雷达检查记录表单（组分网）",
    "sup_rf_o3laserradarmaintenance": "O3 激光雷达维护记录表单（组分网）",
    "sup_rf_ocechalfyearcheck": "OCEC 分析仪半年检记录表单（组分网）",
    "sup_rf_ocecmonthcheck": "OCEC 分析仪月检记录表单（组分网）",
    "sup_rf_ocecmultipointcheck": "OCEC 分析仪多点核查记录表单（组分网）",
    "sup_rf_ocecquarterhcheck": "OCEC 分析仪季检记录表单（组分网）",
    "sup_rf_ocecsinglecheck": "OCEC 分析仪单点核查记录表单（组分网）",
    "sup_rf_ocecweekcheck": "OCEC 分析仪周检记录表单（组分网）",
    "sup_rf_ocecyearcheck": "OCEC 分析仪年检记录表单（组分网）",
    "sup_rf_ptrmsweekcheck": "PTR-MS 周检记录表单（组分网）",
    "sup_rf_quarterlyequipment": "组分网季度设备检查记录表单",
    "sup_rf_repairerecord": "组分网维修记录表单",
    "sup_rf_ruleitemtask": "组分网规则任务生成记录（计划任务项来源）",
    "sup_rf_speedmetermaintain": "风速仪维护记录表单（组分网）",
    "sup_rf_thybhalfyearmaintain": "thyb（甲烷/非甲烷）半年维护记录表单（组分网）",
    "sup_rf_thybmonthmaintain": "thyb 月维护记录表单（组分网）",
    "sup_rf_thybquartermaintain": "thyb 季维护记录表单（组分网）",
    "sup_rf_thybweekcheck": "thyb 周检记录表单（组分网）",
    "sup_rf_thybyearmaintain": "thyb 年维护记录表单（组分网）",
    "sup_rf_turbidimeter": "浊度仪记录表单（组分网）",
    "sup_rf_urgmonthmaintain": "URG 月维护记录表单（组分网）",
    "sup_rf_urgquartermaintain": "URG 季维护记录表单（组分网）",
    "sup_rf_urgweekmaintain": "URG 周维护记录表单（组分网）",
    "sup_rf_urgyearmaintain": "URG 年维护记录表单（组分网）",
    "sup_rf_visibilitymeter": "能见度仪记录表单（组分网）",
    "sup_rf_vocqualitycontroldatadetail": "VOCs 质控数据明细（组分网）",
    "sup_rf_watersolubleionsblankcheck": "水溶性离子空白检查记录表单（组分网）",
    "sup_rf_watersolubleionscalibration": "水溶性离子校准记录表单（组分网）",
    "sup_rf_watersolubleionssinglecheck": "水溶性离子单点核查记录表单（组分网）",
    "sup_rf_week_radiationrecord": "辐射周检记录表单（组分网）",
    "sup_rf_year_radiationcalibration": "辐射年校准记录表单（组分网）",
    "sup_rf_zerospancalibration": "组分网零点/跨度校准记录表单",
    "sup_pw_task": "组分网计划任务头（周期/站点，完成率统计用）",
    "sup_pw_taskitem": "组分网计划任务项（完成/超期/转工单明细）",
    "sup_mtc_device": "组分网运维任务设备关联台账",
    "sup_devicelog": "组分网设备状态变更日志",
    "sup_device": "组分网设备台账",
    "sup_devicemodel": "组分网设备型号字典",
    "sup_effectrate": "组分网站点数据有效率统计",
    "sup_monthreport": "组分网月度报告数据",
    "sup_quarterlyreportupload": "组分网季度报告上传记录",
    "sup_referencematerial": "组分网标准物质台账",
    "sup_contractsetting": "组分网合同配置",
    "sup_powerfailurereport": "组分网停运申请报告主表（对应主网 SEC_BlackOutReport）",
    "sup_powerfailurereportdetail": "组分网停运报告明细（时段/停运原因）",
    "sup_nmhc_systemblank": "NMHC 系统空白数据（组分网质控）",
    "sup_nmhc_curveverificationpoint": "NMHC 曲线核查点数据（组分网质控）",
    "sup_vocs_curveverificationpoint": "VOCs 曲线核查点数据（组分网质控）",
    "sup_vocs_internalstandard": "VOCs 内标数据（组分网质控）",
    "sup_vocs_systemblank": "VOCs 系统空白数据（组分网质控）",
    "sup_sec_configdata": "组分网现场检查题目配置数据",
    "sup_scoresheet": "组分网现场检查评分记录",
    "sec_scoresheet": "现场检查评分记录（主网 SEC 评分明细）",
    # ---- 中期缺口批次（2026-10-28 P1）----
    "rf_ruleitemtask": "主网规则任务生成记录（计划任务项来源，含前后工单号与周期差；计划完成/超期溯源用）",
    "sec_configdata": "现场检查题目配置/评分数据（SEC 检查数据，对应组分网 sup_sec_configdata）",
    "rf_hy_humidity": "海盐湿度记录表单（与 rf_hy_environmenthumidity 为两张不同表单，历史量小）",
    "sec_flightcheck": "飞行检查工单表单（SEC 现场检查体系，2026 年仍有新增）",
    "drt_beta": "数据回补单表单（Beta 仪器类，对应 DataMakeup 工单）",
    "drt_gasanalyzer": "数据回补单表单（气态分析仪，含比对/质控数据列）",
    "drt_gasanalyzer_fiveparameters": "数据回补单表单（气态五参数）",
    "drt_gasanalyzer_nox": "数据回补单表单（NOx 分析仪）",
    "drt_teom": "数据回补单表单（TEOM 颗粒物）",
    "pw_unitplan": "运维单位计划（计划周期/单位/站点，计划执行台账）",
}

GUIDE_HEADER = (
    "\n\n【ODS 兜底表（原始层，中低频表单/明细取证用；共{n}张）】\n"
    "主契约覆盖高频工单域；本清单为平台原值兜底层，无业务口径加工。"
    "引用请写全限定名 guangdong_ods.<表名>；查询必须带过滤条件与 LIMIT，禁止全表扫描；"
    "字段结构以 describe_table 返回为准（表单题目项列不逐列说明，按列名语义取用）。\n"
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
