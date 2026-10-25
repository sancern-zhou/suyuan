# -*- coding: utf-8 -*-
"""生成 ODS 兜底表白名单（execute_jiangsu_mart_sql 的原始层兜底通道）。

设计目标：**同步进 jiangsu_ods 的表不允许 Agent 查不到**。
mart/dim 契约覆盖不到的表（低频字典、人员关系、明细流水等），
至少能通过同一个 SQL 工具以原始表形式托底查询。

兜底清单的推导规则（全自动，避免人工清单漂移）：
    fallback = (sync_config.json 的全部逻辑表 - 分片表) - (已被 mart/dim 契约覆盖的源表)
               + EXTRA_FALLBACK（mart 覆盖了但没暴露行级明细的表）

覆盖判定 = 该 ODS 表被某个 dbt 模型 source() 引用，且该模型名出现在
sync/datasets/*.yaml（即已进入 Agent 可见契约）。

用法:
  python gen_ods_fallback_contract.py            # 生成并写入 ods_contract.txt
  python gen_ods_fallback_contract.py --check    # 校验生成物（dq_check 漂移检测）
  python gen_ods_fallback_contract.py --print    # 仅打印
  python gen_ods_fallback_contract.py --grant    # 给 agent_reader 授权清单内表的 SELECT

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
TARGET_PATH = resolve_agent_path(
    "backend/app/tools/query/jiangsu_ops_sql_query/ods_contract.txt"
)

# 按站分片的大表（alarmlog_2026_3001a / integrated_h_2026_3001a）：由 mart 聚合表统一暴露，
# 单站分片不单独进白名单，否则 200 张表会淹没契约文本。
SHARD_RE = re.compile(r"^(alarmlog|integrated_h)_\d{4}_\d{4}[a-z]$")

# mart 已覆盖、但 mart 未暴露行级明细/映射关系，仍需原始表兜底的例外。
# 判断标准：mart 只给了汇总值或部分列，而"某条明细/某条映射是什么"仍不可查。
EXTRA_FALLBACK = {
    "bsd_usergroup",           # dim_person 只给班组名/数量，班组编码与单位类型未暴露
    "bsd_usergroup_user",      # dim_person 只给人员所属班组名，人↔班组映射未暴露
    "bsd_usergroup_station",   # dim_person 只给责任站点数，班组→站点清单未暴露
    "mtc_working_order_detail",  # mart 只给节点数，处理人/节点流水未暴露
    "opa_kq_attendance",       # mart 只给站点×日签到次数，个人签到明细未暴露
}

# 每张兜底表的用途说明（必须人工登记；新增同步表若落到兜底清单而没有说明，生成直接失败，
# 逼一次"这表要不要给 Agent 查"的决策）。
ODS_TABLE_NOTES = {
    "alm_rule": "告警规则配置（约19条），解释告警为何触发、阈值来源",
    "bsd_maintenanceunit": "运维单位字典（code 对应工单 operationunitid）",
    "bsd_region": "行政区划字典（areacode/level/经纬度）",
    "bsd_supply": "质控耗材领用台账（滤膜/硅胶/纸带），数量字段大面积为空，仅作旁证",
    "bsd_usergroup": "班组字典（groupcode/groupname/归属单位）",
    "bsd_usergroup_user": "班组→人员映射（groupcode + userid，关联 dim_person）",
    "bsd_usergroup_station": "班组→责任站点映射（usergroup_guid 实为班组编码 groupcode）",
    "bsd_usergroup_station_devicetype": "班组→站点→设备类型责任矩阵",
    "mot_alarm": "平台内部告警历史（约6.4万行）；站点告警优先查 mart_alarm_event_analysis",
    "mtc_dataentry": "数据补录单（工单号+站点+时段）",
    "mtc_dataentry_data": "补录明细（站点×时间点×污染物）",
    "mtc_fault": "故障单设备处置扩展（按 workingordercode 关联工单）",
    "mtc_faultcontent": "故障现象字典",
    "mtc_faultcontentitem": "工单→故障现象多选关系",
    "mtc_taskitem": "工单逐项任务进度（约12万行，按 workingordercode 关联）",
    "mtc_working_order_detail": "工单流转流水，含处理人 processusername 与各节点起止时间",
    "opa_kq_attendance": "到站签到明细（个人签到；mart 只给站点×日次数）",
    "opa_qcqa_deduction": "质控扣分明细（考核扣分溯源）",
    "qa_standardmaterialstorage": "标准物质台账（标气标液证书号与有效期，与人员持证无关）",
    "qc_historymonthresultoverview": "质控月度概览（年×月×污染物×区域）",
    "qc_task": "质控任务定义（uniquecode/污染物/任务名/站点）",
    "rf_common": "非故障工单表单体矩阵（补录/审核类工单取值）",
    "rf_ruleitem": "工单任务规则项字典（ruleitemtag → 名称）",
    "wfl_workflow": "工作流定义（流程模板）",
    "wfl_workflowtask": "工作流节点定义（guid 对应工单 currentpoint，解释当前节点）",
    "wo_commonfile": "工单附件索引（仅文件路径，不存内容）",
}

GUIDE_HEADER = (
    "\n\n【ODS 兜底表（原始层，低频/明细取证用；共{n}张）】\n"
    "仅当上方 mart/dim 契约无法回答时使用。兜底表为平台原值，无业务口径加工；"
    "引用请写全限定名 jiangsu_ods.<表名>；查询必须带过滤条件与 LIMIT，禁止全表扫描；"
    "列结构用 describe_table 获取。\n"
)

FILE_HEADER = (
    "# generated from sync_config.json + datasets/*.yaml + dbt/models by "
    "gen_ods_fallback_contract.py — DO NOT EDIT BY HAND\n"
    "# 兜底清单 = 已同步逻辑表 - 已被 mart/dim 契约覆盖的源表 + EXTRA_FALLBACK；"
    "漂移检测见 dq_check.py\n"
)


def _resolve_sync_config() -> Path:
    candidates = [
        SYNC_DIR / "sync_config.json",
        Path(r"E:\Tools\suyuan-jiangsu\sync\sync_config.json"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise SystemExit("sync_config.json 未找到(找过: %s)" % "; ".join(str(c) for c in candidates))


def synced_logical_tables() -> list[str]:
    cfg = json.loads(_resolve_sync_config().read_text(encoding="utf-8"))
    return sorted(t for t in cfg["tables"] if not SHARD_RE.match(t))


def contract_datasets() -> set[str]:
    return {p.stem for p in DATASETS_DIR.glob("*.yaml")}


def source_usage() -> dict[str, set[str]]:
    """ODS 表 -> 引用它的 dbt 模型名集合。"""
    usage: dict[str, set[str]] = {}
    if not DBT_MODELS_DIR.is_dir():
        raise SystemExit("dbt models dir not found: %s" % DBT_MODELS_DIR)
    for path in DBT_MODELS_DIR.rglob("*.sql"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(
            r"source\(\s*'jiangsu_ods'\s*,\s*'([A-Za-z0-9_]+)'\s*\)", text
        ):
            usage.setdefault(match.group(1).lower(), set()).add(path.stem)
    return usage


def fallback_tables() -> tuple[list[str], list[str]]:
    """返回 (兜底表清单, 被 mart 覆盖而排除的表清单)。"""
    datasets = contract_datasets()
    usage = source_usage()
    fallback, covered = [], []
    for table in synced_logical_tables():
        models = usage.get(table, set())
        if models & datasets:
            if table in EXTRA_FALLBACK:
                fallback.append(table)
            else:
                covered.append(table)
        else:
            fallback.append(table)
    return sorted(set(fallback)), sorted(covered)


def build_contract() -> str:
    tables, _covered = fallback_tables()
    missing = [t for t in tables if t not in ODS_TABLE_NOTES]
    if missing:
        raise SystemExit(
            "以下兜底表缺少用途说明，请在 ODS_TABLE_NOTES 登记后再生成: " + ", ".join(missing)
        )
    segments = []
    for table in tables:
        segments.append("\n- {t}：{note}".format(t=table, note=ODS_TABLE_NOTES[table]))
    body = GUIDE_HEADER.format(n=len(tables)) + "".join(segments)
    return FILE_HEADER + "TABLES: " + ",".join(tables) + "\nGUIDE_START" + body + "\nGUIDE_END\n"


def _dsn() -> str:
    dsn = os.getenv("DATABASE_URL", "").replace("+asyncpg", "")
    if dsn:
        return dsn
    try:
        from dotenv import load_dotenv

        load_dotenv(r"E:\suyuan\backend\.env.jiangsu-ops")
        dsn = os.getenv("DATABASE_URL", "").replace("+asyncpg", "")
    except Exception:  # noqa: BLE001
        dsn = ""
    if not dsn:
        raise SystemExit("DATABASE_URL 未配置，无法授权")
    return dsn


async def grant_select(tables: list[str]) -> int:
    import asyncpg

    conn = await asyncpg.connect(_dsn())
    try:
        for table in tables:
            await conn.execute(
                f'GRANT SELECT ON jiangsu_ods."{table}" TO agent_reader'
            )
        # 兜底查询的"数据截至"时点来自同步心跳(只读元数据, 不含业务数据)
        await conn.execute("GRANT SELECT ON jiangsu_sync.sync_watermark TO agent_reader")
        rows = await conn.fetch(
            """SELECT table_name FROM information_schema.role_table_grants
               WHERE grantee='agent_reader' AND table_schema='jiangsu_ods'"""
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
        "| mart-covered:", len(covered),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
