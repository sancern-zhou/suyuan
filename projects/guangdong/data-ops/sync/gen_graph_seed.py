# -*- coding: utf-8 -*-
"""Generate the Guangdong data-semantics knowledge-graph seed from data-ops sources.

单一来源约定：与 gen_tool_contract.py 相同——datasets/*.yaml（表契约）与
semantic/registry.yaml（指标口径）是唯一人工维护源；本脚本的生成物

  projects/guangdong/data-ops/graph/graph_seed.json        # 图谱种子（结构化实体/关系）
  projects/guangdong/data-ops/graph/广东数据语义契约.md     # 种子锚点文档（上传知识库后确定性建图）

由 sync/graph_seed_sync.py 消费写入「广东数据语义」知识库并置 confirmed，
供问数入口实体链接（graph_entry_context）与知识问答使用。

策展部分说明：查询路由实体（语义层点查/受控SQL/监测接口/组分/气象/站点目录）
的中文别名是人工策展的稳定关键词，与提示词数据路由保持一致；改动须同步
projects/guangdong/prompts/gd_query.md。

用法:
  PYTHONPATH=backend python projects/guangdong/data-ops/sync/gen_graph_seed.py            # 生成并写入两个产物
  PYTHONPATH=backend python projects/guangdong/data-ops/sync/gen_graph_seed.py --check    # 漂移检测（不一致退出码 1）
  PYTHONPATH=backend python projects/guangdong/data-ops/sync/gen_graph_seed.py --print    # 仅打印统计

退出码: --check 不一致时返回 1（供 dq_check.py / 调度日志判别）。
"""
from __future__ import annotations

import datetime as dt
import io
import json
import os
import sys

try:
    import yaml  # PyYAML, backend venv 自带
except ImportError:  # pragma: no cover
    yaml = None

from app.utils.path_config import resolve_agent_path, format_agent_path

SYNC_DIR = resolve_agent_path("projects/guangdong/data-ops/sync")
YAML_DIR = SYNC_DIR / "datasets"
REGISTRY_PATH = resolve_agent_path("projects/guangdong/data-ops/semantic/registry.yaml")
GRAPH_DIR = resolve_agent_path("projects/guangdong/data-ops/graph")
SEED_PATH = GRAPH_DIR / "graph_seed.json"
DOC_PATH = GRAPH_DIR / "广东数据语义契约.md"

PROMPT_VERSION = "guangdong_data_semantics_seed_v1"
EXTRACTOR_NAME = "guangdong_data_semantics_seeder"
DOCUMENT_FILENAME = "广东数据语义契约.md"
ANCHOR_MARKER = "## 指标口径与查询路由"
KB_BINDING_KEY = "data_semantics"

# 表 -> 数据域 的精确归属；新增 dataset yaml 必须在此登记，否则生成器失败。
TABLE_DOMAIN = {
    # 工单域
    "working_orders": "工单",
    "working_order_details": "工单",
    "wo_commonfile": "工单",
    "wo_commonfile_links": "工单",
    "mart_work_order_analysis": "工单",
    # 告警域
    "alm_alarm": "告警",
    "alm_home": "告警",
    "mart_alarm_notify_analysis": "告警",
    "mart_station_alarm_status": "告警",
    # 巡检与表单域
    "mart_inspection_task_analysis": "巡检",
    "rf_w_inspection": "巡检",
    "rf_w_inspectionsummary": "巡检",
    "rf_w_gaseouscheck_so2": "巡检",
    "rf_w_gaseouscheck_nox": "巡检",
    "rf_w_gaseouscheck_co": "巡检",
    "rf_w_gaseouscheck_o3": "巡检",
    "rf_w_otherdevicecheck": "巡检",
    "rf_w_pmcheck": "巡检",
    "sup_rf_common": "巡检",
    "sup_rf_ambienttemperature": "巡检",
    "sup_rf_deviceflowcheck": "巡检",
    "sup_rf_monitorinspection": "巡检",
    "sup_rf_pm1monitorinspection": "巡检",
    "pw_task": "巡检",
    "pw_taskitem": "巡检",
    "mtc_ordertaskitem": "巡检",
    "sup_mtc_taskitem": "巡检",
    "sup_devicedaycheck": "巡检",
    # 绩效域
    "mart_performance_analysis": "绩效",
    "opa_performance": "绩效",
    "opa_stationperformancescore": "绩效",
    "opa_datareceiverate": "绩效",
    # 设备域
    "dim_device": "设备",
    "log_device": "设备",
    "mart_device_lifecycle_analysis": "设备",
    # 站点与组织域
    "dim_station": "站点与组织",
    "dim_station_user": "站点与组织",
    "dim_user": "站点与组织",
    # 质控域
    "sec_blackoutreportdetail": "质控",
    "sec_blackoutreporttimespan": "质控",
    "sec_qcblackout": "质控",
    "qul_qualitydate": "质控",
}

DOMAIN_LOCAL_IDS = {name: f"domain_{name}" for name in sorted(set(TABLE_DOMAIN.values()))}

CUBE_LABELS = {
    "WorkOrder": "工单",
    "AlarmNotify": "告警通知",
    "StationAlarmStatus": "站点告警",
    "DeviceLifecycle": "设备生命周期",
    "InspectionTask": "巡检",
    "Performance": "绩效",
}

# 查询路由实体（人工策展的稳定层）：名称/别名用于问数入口实体匹配。
QUERY_TOOLS = [
    {
        "local_id": "tool_semantic_metrics",
        "name": "语义层指标点查",
        "aliases": ["guangdong_query_metrics", "指标点查", "指标查询"],
        "description": (
            "按注册口径点查运维指标（工单/告警通知/站点告警态势/设备生命周期/巡检/绩效），"
            "走 Cube 语义层，口径唯一并返回解释元数据；指标统计类问题优先用它。"
        ),
    },
    {
        "local_id": "tool_mart_sql",
        "name": "运维明细受控SQL",
        "aliases": ["execute_guangdong_mart_sql", "execute_ops_sql_query", "明细", "取证"],
        "description": (
            "guangdong_mart 42 张契约表字段级查询 + guangdong_ods 兜底表（引用写全限定名），"
            "SELECT-only 白名单；明细、自定义聚合、字段取证用它，写 SQL 前先 describe_table 取契约。"
        ),
    },
    {
        "local_id": "tool_monitor_api",
        "name": "监测数据实时接口",
        "aliases": [
            "query_gd_suncere_city_day", "query_gd_suncere_city_hour", "get_5min_data",
            "analyze_city_pollutant_rankings", "空气质量", "浓度", "排名", "同比", "达标",
        ],
        "description": (
            "环境监测浓度/排名/同比/达标/小时与5分钟数据走监测数据接口中台实时查询，"
            "不入运维数仓，禁止用运维表近似替代。"
        ),
    },
    {
        "local_id": "tool_component",
        "name": "组分数据查询",
        "aliases": [
            "get_vocs_species", "get_vocs_ofp", "get_pm25_ionic", "get_pm25_carbon",
            "组分", "VOCs", "OFP", "源解析", "碳组分", "离子", "颗粒物组分",
        ],
        "description": "组分网超站数据：VOCs 物种与 OFP、PM2.5 离子/碳组分/地壳元素/溯源等专项查询。",
    },
    {
        "local_id": "tool_weather",
        "name": "气象数据查询",
        "aliases": ["get_weather_data", "get_observed_meteorology", "气象", "风玫瑰", "风速", "降水", "天气"],
        "description": "气象观测/预报/历史数据查询，支持风玫瑰等专项输出。",
    },
    {
        "local_id": "tool_station_catalog",
        "name": "站点目录",
        "aliases": [
            "guangdong_station_catalog", "monitoring_station_catalog",
            "component_station_catalog", "站点名录", "运维单位", "站点归属",
        ],
        "description": (
            "运维台账 432 站 / 监测体系站点 / 38 个组分超站名录与归属，"
            "是按站点过滤取数的前置步骤。"
        ),
    },
]

# 域 -> 查询工具 的默认路由
DOMAIN_QUERY_VIA = {
    "工单": ["tool_semantic_metrics", "tool_mart_sql"],
    "告警": ["tool_semantic_metrics", "tool_mart_sql"],
    "巡检": ["tool_semantic_metrics", "tool_mart_sql"],
    "绩效": ["tool_semantic_metrics", "tool_mart_sql"],
    "设备": ["tool_semantic_metrics", "tool_mart_sql"],
    "站点与组织": ["tool_station_catalog", "tool_mart_sql"],
    "质控": ["tool_mart_sql"],
}


def load_yaml(path):
    text = io.open(path, encoding="utf-8").read()
    if yaml is not None:
        data = yaml.safe_load(text)
        if isinstance(data, dict):
            return data
    raise SystemExit(f"PyYAML 不可用，无法解析 {path}")


def _clean(text, limit=180):
    text = " ".join(str(text or "").split())
    return text[:limit] + "…" if len(text) > limit else text


def _source_stamp() -> str:
    """源文件最大修改时间，作为种子的确定性时间戳（保证 --check 幂等）。"""
    paths = [REGISTRY_PATH] + [
        YAML_DIR / name for name in os.listdir(YAML_DIR) if name.endswith(".yaml")
    ]
    latest = max(path.stat().st_mtime for path in paths)
    return dt.datetime.fromtimestamp(latest).strftime("%Y-%m-%d %H:%M")


def build_seed() -> dict:
    """从 datasets/*.yaml + registry.yaml 构建确定性图谱种子。"""
    docs = {}
    for fn in sorted(os.listdir(YAML_DIR)):
        if fn.endswith(".yaml"):
            docs[fn[:-5]] = load_yaml(os.path.join(YAML_DIR, fn))
    unmapped = sorted(set(docs) - set(TABLE_DOMAIN))
    if unmapped:
        raise SystemExit("datasets 未登记数据域归属（TABLE_DOMAIN）: " + ", ".join(unmapped))
    stale = sorted(set(TABLE_DOMAIN) - set(docs))
    if stale:
        raise SystemExit("TABLE_DOMAIN 登记了不存在的 dataset: " + ", ".join(stale))

    registry = load_yaml(REGISTRY_PATH)
    cubes = registry.get("cubes") or {}

    entities: list[dict] = []
    relations: list[dict] = []

    # 1) 数据域实体
    domain_tables: dict[str, list[str]] = {}
    for table, domain in TABLE_DOMAIN.items():
        domain_tables.setdefault(domain, []).append(table)
    for domain, local_id in sorted(DOMAIN_LOCAL_IDS.items()):
        entities.append({
            "local_id": local_id,
            "entity_type": "Domain",
            "name": domain,
            "aliases": [],
            "description": f"广东运维数仓数据域：{domain}（{len(domain_tables[domain])} 张契约表）",
            "attributes": {"table_count": len(domain_tables[domain])},
            "evidence_text": f"数据域 {domain}",
        })

    # 2) 契约表实体 + belongs_to / query_via
    for table, domain in sorted(TABLE_DOMAIN.items()):
        doc = docs[table]
        grain = _clean(doc.get("grain") or doc.get("summary") or doc.get("description") or "", 140)
        entities.append({
            "local_id": f"table_{table}",
            "entity_type": "MartTable",
            "name": table,
            "aliases": [table],
            "description": grain or f"广东运维数仓契约表 {table}",
            "attributes": {
                "数据域": domain,
                "freshness_slo": _clean(doc.get("freshness_slo") or "", 40),
                "owner": _clean(doc.get("owner") or "", 40),
            },
            "evidence_text": f"{table}（{grain}）",
        })
        relations.append({
            "source_local_id": f"table_{table}",
            "target_local_id": DOMAIN_LOCAL_IDS[domain],
            "relation_type": "belongs_to",
            "description": f"{table} 属于 {domain} 数据域",
            "evidence_text": f"{table} 属于 {domain}",
        })

    # 3) 查询路由实体（策展）+ 域级路由关系
    for tool in QUERY_TOOLS:
        entities.append({
            "local_id": tool["local_id"],
            "entity_type": "QueryTool",
            "name": tool["name"],
            "aliases": list(tool["aliases"]),
            "description": tool["description"],
            "attributes": {},
            "evidence_text": tool["name"],
        })
    for domain, tool_ids in sorted(DOMAIN_QUERY_VIA.items()):
        for tool_id in tool_ids:
            relations.append({
                "source_local_id": DOMAIN_LOCAL_IDS[domain],
                "target_local_id": tool_id,
                "relation_type": "query_via",
                "description": f"{domain} 类问题优先经 {tool_id}",
                "evidence_text": f"{domain} -> {tool_id}",
            })

    # 4) 指标实体（registry 口径）+ measured_in / derived_from / query_via
    name_counts: dict[str, int] = {}
    for cube in cubes.values():
        for measure in (cube.get("measures") or {}).values():
            name_counts[str(measure.get("name") or "")] = (
                name_counts.get(str(measure.get("name") or ""), 0) + 1
            )
    for cube_name, cube in sorted(cubes.items()):
        dataset = str(cube.get("dataset") or "")
        label = CUBE_LABELS.get(cube_name, cube_name)
        measures = cube.get("measures") or {}
        for key, measure in sorted(measures.items()):
            cn_name = str(measure.get("name") or key)
            display_name = cn_name if name_counts.get(cn_name, 0) == 1 else f"{label}{cn_name}"
            attributes = {"cube": cube_name, "measure": key}
            for field in ("numerator", "denominator", "time_basis"):
                if measure.get(field):
                    attributes[field] = str(measure[field])
            limitations = measure.get("limitations")
            if limitations:
                attributes["limitations"] = _clean(limitations, 160)
            entities.append({
                "local_id": f"metric_{cube_name}_{key}".lower(),
                "entity_type": "Metric",
                "name": display_name,
                "aliases": [cn_name, key, f"{cube_name}.{key}"],
                "description": _clean(measure.get("definition") or "", 200),
                "attributes": attributes,
                "evidence_text": f"{display_name}：{_clean(measure.get('definition') or '', 120)}",
            })
            if dataset in docs:
                relations.append({
                    "source_local_id": f"metric_{cube_name}_{key}".lower(),
                    "target_local_id": f"table_{dataset}",
                    "relation_type": "measured_in",
                    "description": f"{display_name} 由 {dataset} 计算",
                    "evidence_text": f"{display_name} -> {dataset}",
                })
            # 指标血缘：分子/分母引用同 cube 其他指标
            for field in ("numerator", "denominator"):
                ref = str(measure.get(field) or "")
                if ref in measures and ref != key:
                    relations.append({
                        "source_local_id": f"metric_{cube_name}_{key}".lower(),
                        "target_local_id": f"metric_{cube_name}_{ref}".lower(),
                        "relation_type": "derived_from",
                        "description": f"{display_name} 的{ '分子' if field == 'numerator' else '分母' }是 {measures[ref].get('name') or ref}",
                        "evidence_text": f"{display_name}.{field}={ref}",
                    })
            relations.append({
                "source_local_id": f"metric_{cube_name}_{key}".lower(),
                "target_local_id": "tool_semantic_metrics",
                "relation_type": "query_via",
                "description": f"{display_name} 优先走语义层点查（口径唯一）",
                "evidence_text": f"{display_name} -> guangdong_query_metrics",
            })

    local_ids = [entity["local_id"] for entity in entities]
    duplicates = sorted({lid for lid in local_ids if local_ids.count(lid) > 1})
    if duplicates:
        raise SystemExit("种子实体 local_id 重复: " + ", ".join(duplicates))

    return {
        "version": 1,
        "generated_at": _source_stamp(),
        "kb_binding_key": KB_BINDING_KEY,
        "prompt_version": PROMPT_VERSION,
        "extractor_name": EXTRACTOR_NAME,
        "document_filename": DOCUMENT_FILENAME,
        "anchor_marker": ANCHOR_MARKER,
        "entities": entities,
        "relations": relations,
    }


def build_document(seed: dict, cubes: dict | None = None) -> str:
    """渲染种子锚点文档（上传知识库后由 graph_seed_sync 确定性建图）。"""
    if cubes is None:
        cubes = (load_yaml(REGISTRY_PATH).get("cubes") or {})
    docs = {
        fn[:-5]: load_yaml(os.path.join(YAML_DIR, fn))
        for fn in sorted(os.listdir(YAML_DIR)) if fn.endswith(".yaml")
    }
    lines = [
        "# 广东数据语义契约",
        "",
        "- 来源：data-ops/sync/datasets/*.yaml + semantic/registry.yaml（生成物，勿手改）",
        f"- 生成时间：{seed['generated_at']}",
        "- 用途：问数入口图谱实体链接与知识问答的口径索引；字段级细节用 describe_table 获取。",
        "",
    ]
    by_type: dict[str, list[dict]] = {}
    for entity in seed["entities"]:
        by_type.setdefault(entity["entity_type"], []).append(entity)

    lines.append("## 数据域与查询路由")
    lines.append("")
    domain_names = [e["name"] for e in by_type.get("Domain", [])]
    lines.append("数据域：" + "、".join(domain_names))
    lines.append("")
    for tool in by_type.get("QueryTool", []):
        lines.append(f"- {tool['name']}：{tool['description']}")
    lines.append("")

    lines.append(ANCHOR_MARKER)
    lines.append("")
    for cube_name in sorted(cubes):
        cube = cubes[cube_name]
        label = CUBE_LABELS.get(cube_name, cube_name)
        lines.append(f"### {label}（{cube_name}，数据集 {cube.get('dataset')}）")
        lines.append("")
        applicability = _clean(cube.get("applicability") or "", 200)
        if applicability:
            lines.append(f"- 适用范围：{applicability}")
        for key, measure in sorted((cube.get("measures") or {}).items()):
            name_counts_seed = {}
            parts = [f"- {measure.get('name') or key}（{key}）：{_clean(measure.get('definition') or '', 160)}"]
            for field, label2 in (("numerator", "分子"), ("denominator", "分母"), ("time_basis", "时间基准")):
                if measure.get(field):
                    parts.append(f"{label2}={measure[field]}")
            if measure.get("limitations"):
                parts.append(f"限制：{_clean(measure['limitations'], 120)}")
            lines.append("；".join(parts))
        lines.append("")
    lines.append("## 契约表清单（按数据域）")
    lines.append("")
    for domain in sorted(DOMAIN_LOCAL_IDS):
        tables = sorted(t for t, d in TABLE_DOMAIN.items() if d == domain)
        lines.append(f"### {domain}（{len(tables)} 张）")
        lines.append("")
        for table in tables:
            doc = docs.get(table) or {}
            grain = _clean(doc.get("grain") or doc.get("summary") or "", 100)
            lines.append(f"- {table}（{grain}）")
        lines.append("")
    return "\n".join(lines)


def _render_seed_json(seed: dict) -> str:
    return json.dumps(seed, ensure_ascii=False, indent=1) + "\n"


def _normalize_seed_text(text: str, stamp: str) -> str:
    """--check 归一化：generated_at 由源文件 mtime 派生，checkout/重部署会触碰
    mtime 但内容未变，比较时把它对齐到当前生成值，避免误报漂移。"""
    data = json.loads(text)
    data["generated_at"] = stamp
    return _render_seed_json(data)


def _normalize_doc_text(text: str) -> str:
    import re

    return re.sub(r"- 生成时间：.*$", "- 生成时间：<stamp>", text, flags=re.MULTILINE)


def main() -> int:
    seed = build_seed()
    document = build_document(seed)
    if "--print" in sys.argv:
        counts = {}
        for entity in seed["entities"]:
            counts[entity["entity_type"]] = counts.get(entity["entity_type"], 0) + 1
        print("entities:", counts, "relations:", len(seed["relations"]))
        return 0
    if "--check" in sys.argv:
        problems = []
        try:
            deployed_seed = io.open(SEED_PATH, encoding="utf-8").read()
        except OSError:
            deployed_seed = None
        try:
            deployed_doc = io.open(DOC_PATH, encoding="utf-8").read()
        except OSError:
            deployed_doc = None
        if deployed_seed is None or _normalize_seed_text(deployed_seed, seed["generated_at"]) != _render_seed_json(seed):
            problems.append("graph_seed.json")
        if deployed_doc is None or _normalize_doc_text(deployed_doc) != _normalize_doc_text(document):
            problems.append(DOC_PATH.name)
        if problems:
            print("GRAPH SEED DRIFT:", ", ".join(problems), "— run gen_graph_seed.py")
            return 1
        print("GRAPH SEED OK: seed/document match datasets+registry")
        return 0
    os.makedirs(GRAPH_DIR, exist_ok=True)
    io.open(SEED_PATH, "w", encoding="utf-8", newline="\n").write(_render_seed_json(seed))
    io.open(DOC_PATH, "w", encoding="utf-8", newline="\n").write(document)
    counts = {}
    for entity in seed["entities"]:
        counts[entity["entity_type"]] = counts.get(entity["entity_type"], 0) + 1
    print("written:", format_agent_path(SEED_PATH), "entities:", counts,
          "relations:", len(seed["relations"]))
    print("written:", format_agent_path(DOC_PATH), "chars:", len(document))
    return 0


if __name__ == "__main__":
    sys.exit(main())
