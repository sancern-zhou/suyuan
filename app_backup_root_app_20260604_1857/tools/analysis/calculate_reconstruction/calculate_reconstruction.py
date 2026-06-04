"""
calculate_reconstruction: 物质重构工具。
输入：data_id 或 UnifiedParticulateData（components嵌套结构）。
输出：遵循 UDF v2.0 的 dict（status, data, metadata, visuals 可选）。
支持 Context-Aware V2 架构，使用 DataStandardizer 进行字段标准化。
"""
from typing import Any, Dict, List, Optional, Union
import hashlib
import warnings
import structlog
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np

from app.utils.oxide_coefficients import (
    ELEMENT_NAME_MAP,
    element_to_oxide_mass,
)
from app.utils.data_standardizer import get_data_standardizer

logger = structlog.get_logger()

try:
    from app.agent.context.data_context_manager import DataContextManager
except Exception:
    DataContextManager = Any

# 默认重构组分信息
DEFAULT_COMPONENT_INFO = {
    "OM": {"description": "有机物", "default_factor": 1.4},
    "NO3": {"description": "硝酸盐", "molar_mass": 62.0049},
    "SO4": {"description": "硫酸盐", "molar_mass": 96.06},
    "NH4": {"description": "铵盐", "molar_mass": 18.038},
    "EC": {"description": "元素碳"},
    "crustal": {"description": "地壳物质"},
    "trace": {"description": "微量元素"},
}

# 导入统一的颗粒物可视化模块
try:
    from app.tools.visualization.particulate_visualizer import ParticulateVisualizer
except ImportError:
    ParticulateVisualizer = None

DEFAULT_OC_TO_OM = 1.4


def merge_particulate_data_from_multiple_sources(
    data_context_manager: "DataContextManager",
    data_id: Optional[str] = None,
    data_id_carbon: Optional[str] = None,
    data_id_crustal: Optional[str] = None,
    data_id_trace: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    从多个独立的组分查询结果中合并数据。

    用于处理4个独立查询（水溶性离子、碳组分、地壳元素、微量元素）
    返回的合并数据。

    Args:
        data_context_manager: 数据上下文管理器
        data_id: 水溶性离子数据ID
        data_id_carbon: 碳组分数据ID (OC, EC)
        data_id_crustal: 地壳元素数据ID (Al, Si, Fe, Ca, Mg, K, Na, Ti)
        data_id_trace: 微量元素数据ID (Zn, Pb, Cu, Cd, As, etc.)

    Returns:
        合并后的数据列表（字典格式）
    """
    import pandas as pd
    from collections import defaultdict

    logger.info(
        "merge_particulate_data_from_multiple_sources",
        data_id=data_id,
        data_id_carbon=data_id_carbon,
        data_id_crustal=data_id_crustal,
        data_id_trace=data_id_trace
    )

    if data_context_manager is None:
        logger.warning("merge_particulate_data: data_context_manager is None")
        return []

    # 收集所有数据源
    data_sources = []
    if data_id:
        data_sources.append(("soluble", data_id))
    if data_id_carbon:
        data_sources.append(("carbon", data_id_carbon))
    if data_id_crustal:
        data_sources.append(("crustal", data_id_crustal))
    if data_id_trace:
        data_sources.append(("trace", data_id_trace))

    if not data_sources:
        logger.warning("merge_particulate_data: no data sources provided")
        return []

    # 收集所有原始数据
    all_raw_data = defaultdict(dict)
    source_timestamps = defaultdict(set)

    for source_type, d_id in data_sources:
        try:
            raw = data_context_manager.get_raw_data(d_id)
            if isinstance(raw, list):
                for record in raw:
                    if isinstance(record, dict):
                        # 提取时间戳作为合并键
                        timestamp = record.get("time") or record.get("timestamp") or record.get("datetime")
                        if timestamp:
                            # 收集该数据源的字段
                            for key, value in record.items():
                                if key not in ("time", "timestamp", "datetime"):
                                    all_raw_data[timestamp][f"{source_type}_{key}"] = value
                            source_timestamps[source_type].add(timestamp)
            elif isinstance(raw, dict):
                timestamp = raw.get("time") or raw.get("timestamp") or raw.get("datetime")
                if timestamp:
                    for key, value in raw.items():
                        if key not in ("time", "timestamp", "datetime"):
                            all_raw_data[timestamp][f"{source_type}_{key}"] = value
                    source_timestamps[source_type].add(timestamp)
        except Exception as e:
            logger.warning(f"merge_particulate_data: failed to load {source_type} data from {d_id}: {e}")

    if not all_raw_data:
        logger.warning("merge_particulate_data: no data extracted from any source")
        return []

    # 构建合并后的记录列表
    merged_records = []
    for timestamp, fields in sorted(all_raw_data.items()):
        record = {"timestamp": timestamp}
        # 移除源类型前缀，还原原始字段名
        for key, value in fields.items():
            # 处理带前缀的字段名
            if "_" in key:
                # 尝试分离前缀和字段名
                parts = key.split("_", 1)
                if len(parts) == 2:
                    field_name = parts[1]
                else:
                    field_name = key
            else:
                field_name = key
            record[field_name] = value
        merged_records.append(record)

    logger.info(
        "merge_particulate_data: completed",
        total_records=len(merged_records),
        source_timestamps={k: len(v) for k, v in source_timestamps.items()}
    )

    return merged_records


def _extract_components_from_records(records: List[Dict], oc_to_om: float = DEFAULT_OC_TO_OM) -> pd.DataFrame:
    """从 UnifiedParticulateData 格式的记录中提取重构所需的组分数据。

    支持两种格式：
    1. 扁平结构：离子字段直接在顶层（如 SO4, NO3, NH4, OC, EC）
    2. 嵌套结构：离子在 components 字段中
    """
    if not records:
        logger.warning("[_extract_components_from_records] 输入记录列表为空")
        return pd.DataFrame()

    standardizer = get_data_standardizer()

    first_record = records[0]
    if hasattr(first_record, 'model_dump'):
        first_record_dict = first_record.model_dump()
    else:
        first_record_dict = dict(first_record)

    has_nested_components = 'components' in first_record_dict and isinstance(first_record_dict.get('components'), dict)

    rows = []
    for idx, record in enumerate(records):
        if hasattr(record, 'model_dump'):
            record_dict = record.model_dump()
        else:
            record_dict = dict(record)

        standardized_record = standardizer.standardize(record_dict)
        timestamp = standardized_record.get('timestamp')
        row = {'timestamp': timestamp}

        if has_nested_components:
            components = standardized_record.get('components', {})
            row.update(components)
        else:
            reconstruction_fields = ['OC', 'EC', 'NO3', 'SO4', 'NH4', 'Ca', 'Mg', 'K', 'Na', 'Al', 'Si', 'Fe']
            for field in reconstruction_fields:
                if field in standardized_record:
                    row[field] = standardized_record[field]

        rows.append(row)

    df = pd.DataFrame(rows)
    if 'timestamp' in df.columns and df['timestamp'].notna().any():
        df = df.set_index('timestamp')

    return df


def _calculate_reconstruction_statistics(
    df: pd.DataFrame,
    component_cols: List[str],
    available_cols: List[str]
) -> Dict[str, Any]:
    """计算重构结果的统计信息。"""
    statistics = {}

    # 1) 各组分浓度统计
    concentration_stats = {}
    for col in available_cols:
        if col in df.columns:
            values = df[col].dropna().values
            if len(values) > 0:
                concentration_stats[col] = {
                    "mean": round(float(np.mean(values)), 4),
                    "std": round(float(np.std(values)), 4),
                    "min": round(float(np.min(values)), 4),
                    "max": round(float(np.max(values)), 4),
                    "median": round(float(np.median(values)), 4),
                    "sample_count": int(len(values)),
                    "description": DEFAULT_COMPONENT_INFO.get(col, {}).get("description", col)
                }
            else:
                concentration_stats[col] = {"sample_count": 0}
    statistics["concentration"] = concentration_stats

    # 2) 质量闭合度分析
    pm25_col = 'PM2.5' if 'PM2.5' in df.columns else 'PM2_5'
    if pm25_col in df.columns:
        pm25_values = df[pm25_col].dropna()
        if len(pm25_values) > 0 and available_cols:
            reconstruction_sum = df[available_cols].sum(axis=1)
            valid_mask = pm25_values.notna() & reconstruction_sum.notna()
            if valid_mask.sum() > 2:
                pm25_valid = pm25_values[valid_mask]
                recon_valid = reconstruction_sum[valid_mask]
                closure_ratio = float(recon_valid.sum() / pm25_valid.sum()) if pm25_valid.sum() > 0 else 0

                statistics["mass_closure"] = {
                    "closure_ratio": round(closure_ratio, 4),
                    "missing_mass_ratio": round(max(0, 1 - closure_ratio), 4),
                    "sample_count": int(valid_mask.sum())
                }

    # 3) 组分贡献度分析
    if available_cols and pm25_col in df.columns:
        pm25_sum = df[pm25_col].sum()
        if pm25_sum > 0:
            contributions = {}
            for col in available_cols:
                col_sum = df[col].sum()
                contributions[col] = {
                    "contribution_percent": round((col_sum / pm25_sum) * 100, 2)
                }
            statistics["contributions"] = contributions

    return statistics


def _interpret_closure_ratio(ratio: float) -> str:
    if ratio >= 0.9:
        return "excellent"
    elif ratio >= 0.7:
        return "good"
    elif ratio >= 0.5:
        return "moderate"
    else:
        return "poor"


def _hash_dataframe(df: pd.DataFrame) -> str:
    try:
        b = df.to_csv(index=False).encode("utf-8")
        return hashlib.md5(b).hexdigest()
    except Exception:
        return ""


def _aggregate_time(df: pd.DataFrame, reconstruction_type: str) -> pd.DataFrame:
    if "timestamp" in df.columns:
        df = df.set_index(pd.to_datetime(df["timestamp"]))
        if reconstruction_type == "daily":
            agg = df.resample("D").mean()
        elif reconstruction_type == "hourly":
            agg = df.resample("H").mean()
        else:
            agg = df.sort_index()
        agg = agg.reset_index().rename(columns={"index": "timestamp"})
        agg["timestamp"] = agg["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        return agg
    else:
        return df


def calculate_reconstruction(
    data: Optional[Union[pd.DataFrame, List[Dict]]] = None,
    data_id: Optional[str] = None,
    data_id_carbon: Optional[str] = None,
    data_id_crustal: Optional[str] = None,
    data_id_trace: Optional[str] = None,
    reconstruction_type: str = "full",
    oc_to_om: float = DEFAULT_OC_TO_OM,
    negative_handling: str = "clip",
    oxide_coeff_dict: Optional[Dict[str, float]] = None,
    data_context_manager: Optional["DataContextManager"] = None,
) -> Dict[str, Any]:
    """
    计算 7 大组分重构。

    支持两种输入格式：
    1. DataFrame: 扁平结构，字段直接在顶层
    2. 字典列表: UnifiedParticulateData 格式，离子在 components 字段中
    3. 多个独立数据源（data_id, data_id_carbon, data_id_crustal, data_id_trace）

    返回遵循 UDF v2.0 的 dict，使用统一的 visual 格式。
    """
    original_data_id = data_id

    if data is None:
        # 检查是否提供了多个独立的数据源
        if (data_id or data_id_carbon or data_id_crustal or data_id_trace) and data_context_manager:
            data = merge_particulate_data_from_multiple_sources(
                data_context_manager=data_context_manager,
                data_id=data_id,
                data_id_carbon=data_id_carbon,
                data_id_crustal=data_id_crustal,
                data_id_trace=data_id_trace
            )
        elif data_id and data_context_manager:
            raw = data_context_manager.get_raw_data(data_id)
            if isinstance(raw, list):
                data = raw
            elif isinstance(raw, dict):
                data = [raw]

        if data is None:
            return {
                "status": "failed",
                "success": False,
                "data": None,
                "metadata": {"tool_name": "calculate_reconstruction", "error": "empty_data"},
                "summary": "[FAIL] 数据为空"
            }

    # 统一转换为 DataFrame
    if isinstance(data, list):
        # 字典列表格式（包含 components 字段）
        df = _extract_components_from_records(data, oc_to_om)
    else:
        # DataFrame 格式
        df = data.copy()

    if df.empty:
        return {
            "status": "failed",
            "success": False,
            "data": None,
            "metadata": {"tool_name": "calculate_reconstruction", "error": "empty_data"},
            "summary": "[FAIL] 数据为空"
        }

    df.columns = [c.strip() for c in df.columns]

    # 处理负值策略
    if negative_handling == "clip":
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        df[numeric_cols] = df[numeric_cols].clip(lower=0)
    elif negative_handling == "rescale":
        for col in df.select_dtypes(include=[np.number]).columns:
            minv = df[col].min(skipna=True)
            if pd.notna(minv) and minv < 0:
                df[col] = df[col] - minv

    # 计算 OM
    if "OC" in df.columns:
        df["OM"] = df["OC"] * float(oc_to_om)
    else:
        df["OM"] = np.nan

    # 保留常见核心组分列
    for col in ("NO3", "SO4", "NH4", "EC"):
        if col not in df.columns:
            df[col] = np.nan

    # 计算地壳物质
    crustal_series = pd.Series(0.0, index=df.index, dtype=float)
    if oxide_coeff_dict:
        valid_elements = [col for col in oxide_coeff_dict.keys() if col in df.columns]
        for col in valid_elements:
            coeff = oxide_coeff_dict.get(col, None)
            if coeff is None:
                continue
            crustal_series = crustal_series + df[col].fillna(0.0).astype(float) * float(coeff)
    else:
        crustal_components = []
        for eng_sym, cn_name in ELEMENT_NAME_MAP.items():
            if eng_sym in df.columns:
                crustal_components.append(eng_sym)
            elif cn_name in df.columns:
                crustal_components.append(cn_name)
        for col in crustal_components:
            crustal_series = crustal_series + df[col].fillna(0.0).apply(
                lambda v, c=col: element_to_oxide_mass(v, c)
            )
    df["crustal"] = crustal_series

    # 微量元素
    core_and_crustal = set(["OC", "OM", "NO3", "SO4", "NH4", "EC", "crustal"])
    numeric_cols = [c for c in df.select_dtypes(include=[np.number]).columns if c not in core_and_crustal]
    if numeric_cols:
        df["trace"] = df[numeric_cols].sum(axis=1)
    else:
        df["trace"] = 0.0

    # 按时间聚合
    df_out = _aggregate_time(df, reconstruction_type)

    # 收集所有源数据ID
    source_data_ids = [original_data_id] if original_data_id else []
    if data_id_carbon:
        source_data_ids.append(data_id_carbon)
    if data_id_crustal:
        source_data_ids.append(data_id_crustal)
    if data_id_trace:
        source_data_ids.append(data_id_trace)

    metadata = {
        "generator": "calculate_reconstruction",
        "version": "1.0.0",
        "negative_handling": negative_handling,
        "oc_to_om": oc_to_om,
        "source_data_hash": _hash_dataframe(df) if isinstance(df, pd.DataFrame) else "",
        "schema_version": "v2.0",
        "scenario": "pm_reconstruction",
        "source_data_id": original_data_id,
        "source_data_ids": source_data_ids,  # 记录所有源数据ID
    }

    # 构建时间轴数据
    if "timestamp" in df_out.columns:
        timestamps = df_out["timestamp"].tolist()
    else:
        timestamps = [f"t{i}" for i in range(len(df_out))]

    # 组分列
    component_cols = ["OM", "NO3", "SO4", "NH4", "EC", "crustal", "trace"]
    available_cols = [c for c in component_cols if c in df_out.columns]

    # 构建时序图数据
    series_data = []
    for col in available_cols:
        series_data.append({
            "name": col,
            "data": df_out[col].fillna(np.nan).tolist()
        })

    # 使用统一的 ParticulateVisualizer 生成图表
    visuals = []
    if ParticulateVisualizer is not None:
        try:
            visualizer = ParticulateVisualizer()
            visuals = visualizer.generate_reconstruction_charts(df_out, available_cols, timestamps, source_data_id=original_data_id)
        except Exception as e:
            import logging
            logging.warning(f"使用 ParticulateVisualizer 生成图表失败: {e}")
            visuals = []

    # 如果 visualizer 生成失败，使用 Chart v3.1 格式作为备选
    if not visuals:
        import time
        chart_id = f"reconstruction_timeseries_{int(time.time())}"
        visuals = [
            {
                "id": chart_id,
                "type": "timeseries",
                "title": "PM2.5 七大组分重构时序图",
                "data": {
                    "x": timestamps,
                    "series": series_data
                },
                "meta": {
                    "schema_version": "3.1",
                    "generator": "calculate_reconstruction",
                    "generator_version": "1.0.0",
                    "scenario": "pm_reconstruction",
                    "layout_hint": "wide",
                    "interaction_group": "pm_analysis",
                    "data_flow": ["particulate_data", "reconstruction"],
                    "component_count": len(available_cols)
                }
            }
        ]

    # 计算统计信息
    statistics = _calculate_reconstruction_statistics(df_out, component_cols, available_cols)

    logger.info(
        "[calculate_reconstruction] 计算完成",
        available_cols=available_cols,
        records=len(df_out),
        visuals_count=len(visuals),
        closure_ratio=statistics.get("mass_closure", {}).get("closure_ratio")
    )

    # 生成摘要信息
    closure_ratio = statistics.get("mass_closure", {}).get("closure_ratio")

    # 添加图片URL到summary
    summary_lines = [
        f"[OK] calculate_reconstruction 执行完成 - 重构组分: {available_cols}, 质量闭合度: {closure_ratio}"
    ]

    # 如果有图表，添加图片URL
    if visuals:
        for visual in visuals:
            markdown_image = visual.get("markdown_image")
            if markdown_image:
                summary_lines.append(f"\n{markdown_image}")
                break  # 只添加第一张图

    summary = "\n".join(summary_lines)

    return {
        "status": "success",
        "success": True,
        "data": {
            "records": df_out.to_dict(orient="records"),
            "series": series_data,
            "statistics": statistics
        },
        "metadata": metadata,
        "visuals": visuals,
        "summary": summary,
    }


def build_reconstruction_dataframe(df: pd.DataFrame, variables_mapping: pd.DataFrame) -> pd.DataFrame:
    """
    基于参考项目的逻辑，把原始数据表与 variablesMapping 转换为用于重构的 DataFrame
    """
    df_local = df.copy()
    if "类型" in variables_mapping.columns and "变量" in variables_mapping.columns and "modelname" in variables_mapping.columns:
        mapping_dict = variables_mapping[variables_mapping["类型"] != "未测"].set_index("变量")["modelname"].to_dict()
        df_local = df_local.rename(columns=mapping_dict)

    crustal_df = variables_mapping[
        (variables_mapping.get("类型") == "地壳元素") &
        (variables_mapping.get("氧化物系数").notna())
    ].copy()
    dust_O_dict = {}
    if not crustal_df.empty:
        dust_O_dict = crustal_df.set_index("modelname")["氧化物系数"].to_dict()

    dust_vars = [col for col in df_local.columns if col in dust_O_dict]
    for element in dust_vars:
        df_local[element] = df_local[element] * float(dust_O_dict.get(element, 1.0))

    if "OC" in df_local.columns:
        df_local["有机物"] = df_local["OC"] * DEFAULT_OC_TO_OM
    else:
        df_local["有机物"] = np.nan

    def _first_existing(cols):
        for c in cols:
            if c in df_local.columns:
                return c
        return None

    no3_col = _first_existing(["NO3", "硝酸根", "硝酸盐"])
    so4_col = _first_existing(["SO4", "硫酸根", "硫酸盐"])
    nh4_col = _first_existing(["NH4", "铵离子", "铵盐"])
    ec_col = _first_existing(["EC", "元素碳"])
    pm25_col = _first_existing(["PM2.5", "PM₂.₅", "PM25"])

    df_out = pd.DataFrame(index=df_local.index)
    df_out["硝酸盐"] = df_local[no3_col] if no3_col in df_local.columns else np.nan
    df_out["硫酸盐"] = df_local[so4_col] if so4_col in df_local.columns else np.nan
    df_out["铵盐"] = df_local[nh4_col] if nh4_col in df_local.columns else np.nan
    df_out["有机物"] = df_local["有机物"]
    df_out["元素碳"] = df_local[ec_col] if ec_col in df_local.columns else np.nan

    if dust_vars:
        df_out["地壳物质"] = df_local[dust_vars].sum(axis=1, skipna=True)
    else:
        df_out["地壳物质"] = 0.0

    trace_vars = variables_mapping[variables_mapping.get("类型") == "微量元素"]["modelname"].tolist() if "类型" in variables_mapping.columns else []
    trace_vars = [v for v in trace_vars if v in df_local.columns]
    if trace_vars:
        df_out["微量元素"] = df_local[trace_vars].sum(axis=1, skipna=True)
    else:
        known = set(df_out.columns.tolist() + ["OC", "NO3", "SO4", "NH4", "EC"])
        numeric_cols = [c for c in df_local.select_dtypes(include=[np.number]).columns if c not in known]
        df_out["微量元素"] = df_local[numeric_cols].sum(axis=1) if numeric_cols else 0.0

    df_out["PM2.5"] = df_local[pm25_col] if pm25_col in df_local.columns else np.nan

    df_interpolated = df_out.interpolate(method="linear", axis=0, limit=None)
    df_daily = df_out.groupby(df_out.index.date).mean()
    try:
        df_daily.index = pd.to_datetime(df_daily.index)
    except Exception:
        pass

    return df_daily, df_interpolated


# ============================================================================
# 工具包装器类（用于注册到全局工具注册表）
# ============================================================================

from app.tools.base.tool_interface import LLMTool, ToolCategory


class CalculateReconstructionTool(LLMTool):
    """7大组分重构工具

    支持 Context-Aware V2，从 get_particulate_data 获取的标准化数据中自动提取
    components 字段进行计算。

    输入格式：UnifiedParticulateData（components 嵌套结构）
    """

    name = "calculate_reconstruction"
    description = "计算PM2.5的7大组分重构（OM、NO3、SO4、NH4、EC、地壳物质、微量元素），使用统一可视化格式"
    category = ToolCategory.ANALYSIS
    version = "1.0.0"
    requires_context = True

    def __init__(self):
        function_schema = {
            "name": "calculate_reconstruction",
            "description": """
执行PM2.5七大组分重构分析，计算有机物、硝酸盐、硫酸盐、铵盐、元素碳、地壳物质和微量元素。

**核心要求**:
- **必须查询OC/EC数据**才能计算OM（有机物）
- **必须查询地壳元素**（Al、Si、Ca、Mg等）才能计算地壳物质
- 碳组分和水溶性离子数据可从同一批颗粒物数据中获取

**数据来源**:
- 颗粒物数据：从 get_particulate_data 获取（components 字段包含 OC、EC、地壳元素等数据）
- 建议同时获取：水溶性离子（SO4、NO3、NH4）用于交叉验证

**输入格式**: UnifiedParticulateData（components 嵌套结构）
- 数据自动从 components 字段提取：OC、EC、NO3、SO4、NH4、Ca、Mg、K、Na、Al、Si、Fe 等
- PM2.5 浓度用于质量闭合度计算

**重构的7大组分**:
1. **OM（有机物）**: OC × 1.4（默认转换系数）
2. **NO3（硝酸盐）**: 直接从 components 提取
3. **SO4（硫酸盐）**: 直接从 components 提取
4. **NH4（铵盐）**: 直接从 components 提取
5. **EC（元素碳）**: 直接从 components 提取
6. **地壳物质**: 基于氧化物系数计算（Al→Al2O3、Si→SiO2、Ca→CaCO3、Mg→MgO 等）
7. **微量元素**: 除上述组分外的其他金属元素总和

**数据获取步骤**:
1. **获取颗粒物组分数据**（必须使用小时粒度）：
   - 调用 get_particulate_data 时，**必须在 question 中明确列出以下组分**：
     - 碳组分：OC（有机碳）、EC（元素碳）
     - 水溶性离子：SO4（硫酸盐）、NO3（硝酸盐）、NH4（铵盐）
     - 地壳元素：Al（铝）、Si（硅）、Ca（钙）、Mg（镁）、Fe（铁）、K（钾）
     - 微量元素：Na（钠）、Pb（铅）、Zn（锌）、Cu（铜）等
   - **正确示例**: get_particulate_data("深圳市2025年12月24日的PM2.5碳组分、水溶性离子、地壳元素、微量金属数据，时间粒度为小时，要求并发查询，要求包含 OC、EC、SO4（硫酸盐）、NO3（硝酸盐）、NH4（铵盐）、Ca（钙）、Mg（镁）、K（钾）、Na（钠）、Al（铝）、Si（硅）、Fe（铁）、Pb（铅）、Zn（锌）、Cu（铜）")

2. **调用此工具**：
   - 传入 data_id（必需）
   - 可选参数：oc_to_om（OC转OM系数，默认1.4）

**返回结果**:
- 各组分时序数据
- 质量闭合度分析（重构总和 / PM2.5）
- 各组分对 PM2.5 的贡献度百分比
- 专业图表：七大组分重构时序图

**示例**:
步骤1: particle_data = get_particulate_data("深圳市2025年12月24日的PM2.5组分数据...")
步骤2: result = calculate_reconstruction(
    data_id=particle_data["data_id"]  # 必需
)

**质量闭合度解读**:
- closure_ratio ≥ 0.9: 重构效果优秀
- 0.7 ≤ closure_ratio < 0.9: 重构效果良好
- 0.5 ≤ closure_ratio < 0.7: 重构效果一般
- closure_ratio < 0.5: 重构效果较差，可能缺少重要组分
            """.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "data_id": {
                        "type": "string",
                        "description": "水溶性离子/主颗粒物组分数据ID（来自 get_particulate_data），必需参数"
                    },
                    "data_id_carbon": {
                        "type": "string",
                        "description": "碳组分数据ID（来自独立的 get_particulate_data 查询 OC、EC），可选"
                    },
                    "data_id_crustal": {
                        "type": "string",
                        "description": "地壳元素数据ID（来自独立的 get_particulate_data 查询 Al、Si、Fe 等），可选"
                    },
                    "data_id_trace": {
                        "type": "string",
                        "description": "微量元素数据ID（来自独立的 get_particulate_data 查询 Zn、Pb、Cu 等），可选"
                    },
                    "reconstruction_type": {
                        "type": "string",
                        "enum": ["full", "daily", "hourly"],
                        "default": "full",
                        "description": "重构类型：full-保持原时间粒度，daily-日均值，hourly-小时均值"
                    },
                    "oc_to_om": {
                        "type": "number",
                        "default": 1.4,
                        "description": "OC到OM的转换系数，默认1.4（即OM = OC × 1.4）"
                    },
                    "negative_handling": {
                        "type": "string",
                        "enum": ["clip", "rescale"],
                        "default": "clip",
                        "description": "负值处理方式：clip-截断为0，rescale-平移为正"
                    },
                    "oxide_coeff_dict": {
                        "type": "object",
                        "description": "自定义地壳元素氧化物系数，如 {'Al': 1.89, 'Si': 2.14}"
                    }
                },
                "required": ["data_id"]
            }
        }

        super().__init__(
            name=self.name,
            description=self.description,
            category=self.category,
            version=self.version,
            requires_context=self.requires_context,
            function_schema=function_schema
        )

    async def execute(self, data_id=None, data_id_carbon=None, data_id_crustal=None, data_id_trace=None, data=None, reconstruction_type="full", oc_to_om=1.4, negative_handling="clip", oxide_coeff_dict=None, context=None, **kwargs):
        """执行7大组分重构计算"""
        data_context_manager = kwargs.get('data_context_manager')

        if data_context_manager is None and context is not None:
            if hasattr(context, 'data_manager'):
                data_context_manager = context.data_manager
            elif hasattr(context, 'get_data_manager'):
                data_context_manager = context.get_data_manager()
            elif isinstance(context, dict) and context.get('data_manager'):
                data_context_manager = context['data_manager']
            elif hasattr(context, 'get_data'):
                data_context_manager = context

        result = calculate_reconstruction(
            data_id=data_id,
            data_id_carbon=data_id_carbon,
            data_id_crustal=data_id_crustal,
            data_id_trace=data_id_trace,
            data=data,
            reconstruction_type=reconstruction_type,
            oc_to_om=oc_to_om,
            negative_handling=negative_handling,
            oxide_coeff_dict=oxide_coeff_dict,
            data_context_manager=data_context_manager
        )

        if data_context_manager is not None and result.get("success"):
            try:
                # 只保存可序列化的统计摘要，不保存visuals和复杂嵌套
                statistics = result.get("data", {}).get("statistics", {}) if result.get("data") else {}
                summary = {
                    "status": "success",
                    "available_components": [s["name"] for s in result.get("data", {}).get("series", [])],
                    "statistics": statistics,
                    "visuals_count": len(result.get("visuals", [])),
                    "visuals": [
                        {
                            "id": v.get("id"),
                            "title": v.get("title") or v.get("payload", {}).get("title"),
                            "type": v.get("type")
                        }
                        for v in result.get("visuals", [])
                    ]
                }
                result_data_id = data_context_manager.save_data(
                    data=[summary],
                    schema="particulate_analysis",
                    metadata={
                        "source_data_id": data_id,
                        "closure_ratio": statistics.get("mass_closure", {}).get("closure_ratio"),
                        "missing_mass_ratio": statistics.get("mass_closure", {}).get("missing_mass_ratio"),
                        "component_count": len(summary.get("available_components", []))
                    }
                )
                result["data_id"] = result_data_id
            except Exception as save_err:
                logger.warning(f"[calculate_reconstruction] 保存失败: {save_err}")

        return result


if __name__ == "__main__":
    # 简单的单元测试
    import pandas as pd
    test_data = pd.DataFrame({
        'OC': [10, 15, 20],
        'NO3': [5, 8, 12],
        'SO4': [8, 10, 15],
        'NH4': [3, 5, 7],
        'EC': [2, 3, 4],
        '钙': [1, 2, 3],
        '镁': [0.5, 1, 1.5]
    })
    result = calculate_reconstruction(data=test_data)
    print(f"Status: {result['status']}")
    print(f"Visuals count: {len(result.get('visuals', []))}")
    if result.get('visuals'):
        first = result['visuals'][0]
        print(f"First visual type: {first.get('type')}")
        print(f"First visual has payload: {'payload' in first}")
