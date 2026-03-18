"""
calculate_carbon: 碳组分分析（SOC/POC/EC、EC/OC 比值）

支持 Context-Aware V2，使用 ExecutionContext 管理数据生命周期。
支持 UnifiedParticulateData 格式（components 嵌套结构）和扁平 DataFrame 格式。

计算完成后，通过原始数据的 data_id 传递给 smart_chart_generator 生成碳组分堆积图，
同时使用 ParticulateVisualizer 生成 EC/OC 散点图。
"""
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union
import hashlib
import warnings
import structlog
from scipy import stats
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np

from app.utils.data_standardizer import get_data_standardizer

logger = structlog.get_logger()

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

try:
    from app.agent.context.data_context_manager import DataContextManager
except Exception:
    DataContextManager = Any

from app.tools.visualization.particulate_visualizer import ParticulateVisualizer

DEFAULT_OC_TO_OM = 1.4


def _hash_dataframe(df: pd.DataFrame) -> str:
    try:
        b = df.to_csv(index=False).encode("utf-8")
        return hashlib.md5(b).hexdigest()
    except Exception:
        return ""


def _normalize_series(series: pd.Series) -> pd.Series:
    """参考参考项目 normalization：(x - min) / (max - min)；保留 NaN"""
    if series.dropna().empty:
        return series.copy() * np.nan
    vmax = series.max(skipna=True)
    vmin = series.min(skipna=True)
    if np.isclose(vmax, vmin):
        return series.apply(lambda v: 0.0 if pd.notna(v) else np.nan)
    return (series - vmin) / (vmax - vmin)


def _extract_carbon_columns(records: List[Dict], carbon_info: Dict[str, Dict]) -> pd.DataFrame:
    """从 UnifiedParticulateData 格式的记录中提取碳组分数据到 DataFrame。

    使用全局 DataStandardizer 进行字段映射（OC、EC、PM2.5 等字段名变体统一处理）
    数据格式：UnifiedParticulateData（components 嵌套结构或扁平结构）

    Args:
        records: 包含 components 字段或扁平结构的记录列表
        carbon_info: 碳组分信息字典（用于日志记录）

    Returns:
        包含碳组分列的 DataFrame
    """
    if not records:
        logger.warning("[_extract_carbon_columns] 输入记录列表为空")
        return pd.DataFrame()

    # 使用全局 DataStandardizer 进行字段映射
    standardizer = get_data_standardizer()

    # 调试：记录第一条原始记录的结构
    first_record = records[0]
    if hasattr(first_record, 'model_dump'):
        first_record_dict = first_record.model_dump()
    else:
        first_record_dict = dict(first_record)

    logger.info(
        "[_extract_carbon_columns] 原始数据结构分析",
        first_record_keys=list(first_record_dict.keys())[:15],
        has_components='components' in first_record_dict,
        components_type=type(first_record_dict.get('components')).__name__ if 'components' in first_record_dict else None,
        sample_timestamp=first_record_dict.get('timestamp'),
        sample_station_code=first_record_dict.get('station_code'),
    )

    # 如果有 components 字段，调试其内容
    if 'components' in first_record_dict:
        components = first_record_dict['components']
        if isinstance(components, dict):
            logger.info(
                "[_extract_carbon_columns] components 字段内容",
                component_keys=list(components.keys()),
                sample_values={k: v for k, v in list(components.items())[:5]}
            )

    rows = []
    for idx, record in enumerate(records):
        # Pydantic 模型转字典
        # 注意：UnifiedParticulateData.model_dump() 已经包含 from_raw_data 映射后的字段名（EC/OC）
        # 无需再次调用 standardizer.standardize()
        if hasattr(record, 'model_dump'):
            record_dict = record.model_dump()
        else:
            record_dict = dict(record)

        # 调试：记录第一条处理中的记录
        if idx == 0:
            logger.info(
                "[_extract_carbon_columns] 第一条记录",
                keys=list(record_dict.keys())[:15],
                has_components='components' in record_dict,
                components_keys=list(record_dict.get('components', {}).keys()) if 'components' in record_dict else None
            )

        # 提取时间戳（直接从 record_dict 获取）
        timestamp = record_dict.get('timestamp')
        if idx == 0:
            logger.info("[_extract_carbon_columns] timestamp提取", timestamp_value=timestamp)

        # 提取 components（直接使用 record_dict，from_raw_data 已完成 EC/OC 映射）
        components = record_dict.get('components', {})
        if idx == 0:
            logger.info(
                "[_extract_carbon_columns] components提取",
                is_dict=isinstance(components, dict),
                keys=list(components.keys()) if isinstance(components, dict) else None
            )

        # 构建行数据
        row = {'timestamp': timestamp}

        # 尝试从 components 提取 OC、EC
        if isinstance(components, dict):
            if 'OC' in components:
                row['OC'] = components['OC']
                if idx == 0:
                    logger.info("[_extract_carbon_columns] 从components提取OC", value=components['OC'])
            if 'EC' in components:
                row['EC'] = components['EC']
                if idx == 0:
                    logger.info("[_extract_carbon_columns] 从components提取EC", value=components['EC'])

        # 检查顶层是否有 OC、EC（扁平结构）
        for key in ['OC', 'EC']:
            if key not in row:
                # 尝试各种可能的字段名变体
                for variant in [key, key.lower(), f'{key.lower()}_', f'{key}_']:
                    if variant in record_dict:
                        row[key] = record_dict[variant]
                        if idx == 0:
                            logger.info(f"[_extract_carbon_columns] 从顶层提取{key}", variant=variant, value=record_dict[variant])
                        break

        # PM2.5 直接从 record_dict 获取
        if 'PM2_5' in record_dict:
            row['PM2.5'] = record_dict['PM2_5']
        # 处理其他可能的 PM2.5 字段变体（兜底）
        for key in ['PM2.5', 'PM₂.₅', 'pm25', 'PM25']:
            if key in record_dict and 'PM2.5' not in row:
                row['PM2.5'] = record_dict[key]
                if idx == 0:
                    logger.info(f"[_extract_carbon_columns] 找到PM2.5字段", original_key=key, value=record_dict[key])
                break

        if idx == 0:
            logger.info(
                "[_extract_carbon_columns] 最终行数据",
                row_keys=list(row.keys()),
                has_oc='OC' in row,
                has_ec='EC' in row,
                has_pm25='PM2.5' in row
            )

        rows.append(row)

    df = pd.DataFrame(rows)

    # 记录最终 DataFrame 的列信息
    logger.info(
        "[_extract_carbon_columns] DataFrame 构建完成",
        columns=list(df.columns),
        row_count=len(df),
        has_oc='OC' in df.columns,
        oc_notna=df['OC'].notna().sum() if 'OC' in df.columns else 0,
        has_ec='EC' in df.columns,
        ec_notna=df['EC'].notna().sum() if 'EC' in df.columns else 0,
        has_pm25='PM2.5' in df.columns,
        pm25_notna=df['PM2.5'].notna().sum() if 'PM2.5' in df.columns else 0
    )

    # 设置时间戳索引
    if 'timestamp' in df.columns and df['timestamp'].notna().any():
        df = df.set_index('timestamp')

    return df


def calculate_carbon(
    data: Union[pd.DataFrame, List[Dict]],
    data_id: Optional[str] = None,
    carbon_type: str = "pm25",
    oc_to_om: float = DEFAULT_OC_TO_OM,
    poc_method: str = "ec_normalization",
) -> Dict[str, Any]:
    """计算碳组分分析结果。

    支持两种输入格式：
    1. DataFrame: 碳组分字段直接在顶层（如 OC, EC）
    2. 字典列表: UnifiedParticulateData 格式，碳组分在 components 字段中

    Args:
        data: 输入数据（DataFrame 或 包含 components 的记录列表）
        data_id: 原始数据ID
        carbon_type: 碳类型（pm25, pm10）
        oc_to_om: OC转OM系数
        poc_method: POC计算方法

    Returns:
        遵循 UDF v2.0 的分析结果
    """
    if data is None:
        raise ValueError("data 参数不能为 None")

    original_data_id = data_id

    # 统一转换为 DataFrame
    if isinstance(data, list):
        # 字典列表格式（包含 components 字段）
        df = _extract_carbon_columns(data, {})
    else:
        # DataFrame 格式
        df = data.copy()

    if df.empty:
        return {
            "status": "failed",
            "success": False,
            "data": None,
            "metadata": {"tool_name": "calculate_carbon", "error": "empty_data"},
            "summary": "[FAIL] 数据为空"
        }

    # 确保索引名称正确
    if df.index.name is None:
        df.index.name = "timestamp"

    # 提取核心列
    oc = df.get("OC")
    ec = df.get("EC")
    pm25 = df.get("PM2.5")

    # 记录原始数据中的有效记录数（用于 field_mapping_info）
    field_mapping_info = {
        "OC": int(oc.notna().sum()) if oc is not None else 0,
        "EC": int(ec.notna().sum()) if ec is not None else 0,
        "PM2.5": int(pm25.notna().sum()) if pm25 is not None else 0,
    }

    result_df = pd.DataFrame(index=df.index)
    result_df["OC"] = oc
    result_df["EC"] = ec
    result_df["PM2.5"] = pm25

    # 计算 POC 与 SOC
    if poc_method == "ec_normalization":
        nor_ec = _normalize_series(ec) if ec is not None else None
        if nor_ec is not None:
            poc = pd.Series(index=result_df.index, dtype=float)
            poc[:] = np.nan
            valid_mask = result_df["OC"].notna() & nor_ec.notna()
            poc[valid_mask] = result_df["OC"][valid_mask] * nor_ec[valid_mask]
            result_df["POC"] = poc
            result_df["SOC"] = result_df["OC"] - result_df["POC"]
        else:
            result_df["POC"] = np.nan
            result_df["SOC"] = np.nan
    else:
        result_df["POC"] = np.nan
        result_df["SOC"] = np.nan

    # 计算 EC/OC 比值
    ec_oc = pd.Series(index=result_df.index, dtype=float)
    ec_oc[:] = np.nan
    valid_mask = result_df["EC"].notna() & result_df["OC"].notna() & (result_df["OC"] != 0)
    ec_oc[valid_mask] = result_df["EC"][valid_mask] / result_df["OC"][valid_mask]
    result_df["EC_OC"] = ec_oc

    # ============================================================
    # 计算统计信息（供LLM分析解读）
    # ============================================================

    # 1) EC/OC 比值统计
    ec_oc_stats = {"sample_count": 0}
    if "EC_OC" in result_df.columns:
        ec_oc_valid = result_df["EC_OC"].dropna()
        if len(ec_oc_valid) > 0:
            ec_oc_stats = {
                "sample_count": int(len(ec_oc_valid)),
                "mean": round(float(np.mean(ec_oc_valid)), 4),
                "std": round(float(np.std(ec_oc_valid)), 4),
                "min": round(float(np.min(ec_oc_valid)), 4),
                "max": round(float(np.max(ec_oc_valid)), 4),
                "median": round(float(np.median(ec_oc_valid)), 4),
            }

    # 2) POC/SOC 统计
    poc_soc_stats = {"sample_count": 0}
    if "POC" in result_df.columns and "SOC" in result_df.columns:
        poc_valid = result_df["POC"].dropna()
        soc_valid = result_df["SOC"].dropna()
        if len(poc_valid) > 0 or len(soc_valid) > 0:
            poc_values = poc_valid.values
            soc_values = soc_valid.values
            poc_soc_stats = {
                "sample_count": int((result_df["POC"].notna() | result_df["SOC"].notna()).sum()),
                "poc_mean": round(float(np.mean(poc_values)), 4) if len(poc_values) > 0 else None,
                "soc_mean": round(float(np.mean(soc_values)), 4) if len(soc_values) > 0 else None,
                "poc_std": round(float(np.std(poc_values)), 4) if len(poc_values) > 0 else None,
                "soc_std": round(float(np.std(soc_values)), 4) if len(soc_values) > 0 else None,
            }
            # SOC 占比
            total_carbon = poc_values + soc_values
            total_valid = total_carbon[~np.isnan(total_carbon) & (total_carbon != 0)]
            if len(total_valid) > 0:
                soc_ratio = soc_values[~np.isnan(soc_values) & (total_carbon != 0)] / total_valid
                poc_ratio = poc_values[~np.isnan(poc_values) & (total_carbon != 0)] / total_valid
                poc_soc_stats["soc_ratio_mean"] = round(float(np.mean(soc_ratio)), 4) if len(soc_ratio) > 0 else None
                poc_soc_stats["poc_ratio_mean"] = round(float(np.mean(poc_ratio)), 4) if len(poc_ratio) > 0 else None

    # 3) OC/EC 与 PM2.5 关联统计
    pm25_correlation = {"sample_count": 0}
    if pm25 is not None and oc is not None:
        valid_mask = pm25.notna() & oc.notna()
        if valid_mask.sum() > 2:
            pm25_vals = pm25[valid_mask].values
            oc_vals = oc[valid_mask].values
            r_value, p_value = stats.pearsonr(pm25_vals, oc_vals)
            pm25_correlation = {
                "sample_count": int(valid_mask.sum()),
                "r_squared": round(r_value ** 2, 4),
                "correlation": round(r_value, 4),
                "p_value": round(float(p_value), 6) if p_value > 0 else 0.0,
            }

    # 4) 碳组分浓度统计
    carbon_stats = {}
    for col in ["OC", "EC", "POC", "SOC"]:
        if col in result_df.columns:
            values = result_df[col].dropna().values
            if len(values) > 0:
                carbon_stats[col] = {
                    "mean": round(float(np.mean(values)), 4),
                    "std": round(float(np.std(values)), 4),
                    "min": round(float(np.min(values)), 4),
                    "max": round(float(np.max(values)), 4),
                    "median": round(float(np.median(values)), 4),
                    "sample_count": int(len(values))
                }
            else:
                carbon_stats[col] = {"sample_count": 0}

    # 5) 二次有机碳判断
    secondary_organic = {"level": None, "soc_concentration": None}
    if "SOC" in result_df.columns:
        soc_valid = result_df["SOC"].dropna()
        if len(soc_valid) > 0:
            soc_mean = np.mean(soc_valid)
            # 基于 SOC 浓度判断二次有机碳贡献程度
            if soc_mean > 5:
                secondary_organic["level"] = "high"
            elif soc_mean > 2:
                secondary_organic["level"] = "medium"
            else:
                secondary_organic["level"] = "low"
            secondary_organic["soc_concentration"] = round(float(soc_mean), 4)
            secondary_organic["soc_max"] = round(float(np.max(soc_valid)), 4)
            secondary_organic["soc_min"] = round(float(np.min(soc_valid)), 4)

    # 合并所有统计信息
    statistics = {
        "ec_oc": ec_oc_stats,
        "poc_soc": poc_soc_stats,
        "pm25_correlation": pm25_correlation,
        "carbon": carbon_stats,
        "secondary_organic": secondary_organic,
    }

    metadata = {
        "generator": "calculate_carbon",
        "version": "1.0.0",
        "poc_method": poc_method,
        "oc_to_om": oc_to_om,
        "source_data_hash": _hash_dataframe(df) if isinstance(data, pd.DataFrame) else "",
        "schema_version": "v2.0",
        "scenario": "pm_carbon_analysis",
        "source_data_id": original_data_id,
        "field_mapping_applied": True,
        "field_mapping_info": field_mapping_info,
    }

    # 构建计算结果数据
    series_data = []
    for col in ["SOC", "POC", "EC"]:
        if col in result_df.columns:
            series_data.append({
                "name": col,
                "data": result_df[col].fillna(np.nan).tolist()
            })

    scatter_data = []
    valid_mask = result_df["EC"].notna() & result_df["OC"].notna()
    for i, idx in enumerate(result_df.index):
        # 使用 iloc 避免重复索引导致的 Series 返回问题
        ec_val = result_df["EC"].iloc[i]
        oc_val = result_df["OC"].iloc[i]
        if pd.notna(ec_val) and pd.notna(oc_val):
            scatter_data.append({
                "EC": round(float(ec_val), 3),
                "OC": round(float(oc_val), 3)
            })

    # 生成 EC/OC 散点图（使用 ParticulateVisualizer）
    visuals = []
    try:
        visualizer = ParticulateVisualizer()
        scatter_chart = visualizer.generate_ec_oc_scatter_chart(result_df, source_data_id=original_data_id)
        if scatter_chart:
            visuals.append(scatter_chart)
            logger.info("[calculate_carbon] EC/OC散点图生成成功")
    except Exception as viz_err:
        logger.warning(f"[calculate_carbon] EC/OC散点图生成失败: {viz_err}")

    # 生成摘要信息
    ec_oc_mean = ec_oc_stats.get("mean") if ec_oc_stats else None
    soc_mean_val = carbon_stats.get("SOC", {}).get("mean") if carbon_stats.get("SOC") else None
    secondary_level = secondary_organic.get("level") if secondary_organic else None

    # 添加图片URL到summary
    summary_lines = [
        f"✅ calculate_carbon 执行完成 - EC/OC均值: {ec_oc_mean}, SOC均值: {soc_mean_val}, 二次有机碳: {secondary_level}"
    ]

    # 如果有图表，添加图片URL
    if visuals:
        for visual in visuals:
            markdown_image = visual.get("markdown_image")
            if markdown_image:
                summary_lines.append(f"\n{markdown_image}")
                break  # 只添加第一张图

    summary = "\n".join(summary_lines)

    # 碳组分堆积图由smart_chart_generator通过data_id生成
    logger.info(
        "[calculate_carbon] 计算完成",
        has_oc="OC" in result_df.columns,
        has_ec="EC" in result_df.columns,
        has_pm25=pm25 is not None,
        has_poc="POC" in result_df.columns,
        has_soc="SOC" in result_df.columns,
        source_data_id=original_data_id,
        visuals_count=len(visuals),
        note="EC/OC散点图由ParticulateVisualizer生成，碳组分堆积图由smart_chart_generator生成"
    )

    return {
        "status": "success",
        "success": True,
        "data": None,  # 大量时序数据已省略，直接返回 statistics
        "visuals": visuals,  # EC/OC散点图（已包含image_url和markdown_image）
        "statistics": statistics,  # 统计结论供LLM分析
        "metadata": metadata
    }


# ============================================================================
# 工具包装器类（用于注册到全局工具注册表）
# ============================================================================

from app.tools.base.tool_interface import LLMTool, ToolCategory


class CalculateCarbonTool(LLMTool):
    """碳组分分析工具

    支持 Context-Aware V2，从 get_particulate_data 获取的标准化数据中自动提取
    components 字段进行计算。

    输入格式：UnifiedParticulateData（components 嵌套结构）
    """

    name = "calculate_carbon"
    description = "计算碳组分分析（POC、SOC、EC/OC比值），自动生成EC/OC散点图（ParticulateVisualizer）和碳组分堆积图（smart_chart_generator）"
    category = ToolCategory.ANALYSIS
    version = "1.0.0"
    requires_context = True

    def __init__(self):
        function_schema = {
            "name": "calculate_carbon",
            "description": """
执行碳组分分析，计算POC（一次有机碳）、SOC（二次有机碳）、EC/OC比值。

**数据来源**:
- 从 get_particulate_data 获取的数据（components 字段包含 OC、EC 数据）

**输入格式**: UnifiedParticulateData（components 嵌套结构）
- 数据自动从 components 字段提取：OC（有机碳）、EC（元素碳）
- 自动关联 PM2.5 数据用于相关性分析

**数据获取步骤**:
1. **获取碳组分数据**（必须使用小时粒度）：
   - 调用 get_particulate_data 时，**必须在 question 中明确列出碳组分**：
     - OC（有机碳）、EC（元素碳）
   - **正确示例**: get_particulate_data("揭阳市2025年12月24日的PM2.5碳组分数据，时间粒度为小时，要求包含 OC、EC")

2. **调用此工具**：
   - 传入 data_id（必需）

**返回结果**:
- POC（一次有机碳）、SOC（二次有机碳）浓度
- EC/OC 比值统计（均值、标准差、范围）
- 碳组分与 PM2.5 相关性分析
- 二次有机碳贡献程度判断（high/medium/low）
- 专业图表：EC/OC 散点图

**示例**:
calculate_carbon(
    data_id="particulate_unified:v1:xxx"  # 来自 get_particulate_data
)
            """.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "data_id": {
                        "type": "string",
                        "description": "颗粒物组分数据ID（来自 get_particulate_data）"
                    },
                    "carbon_type": {
                        "type": "string",
                        "enum": ["pm25", "pm10"],
                        "default": "pm25",
                        "description": "碳类型（PM2.5 或 PM10）"
                    },
                    "oc_to_om": {
                        "type": "number",
                        "default": 1.4,
                        "description": "OC转OM（有机物）系数"
                    },
                    "poc_method": {
                        "type": "string",
                        "enum": ["ec_normalization"],
                        "default": "ec_normalization",
                        "description": "POC计算方法"
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

    async def execute(
        self,
        context: "ExecutionContext",
        data_id: str,
        carbon_type: str = "pm25",
        oc_to_om: float = 1.4,
        poc_method: str = "ec_normalization",
        **kwargs
    ) -> Dict[str, Any]:
        """执行碳组分分析"""
        # Step 1: 获取标准化后的碳组分数据
        try:
            carbon_records = context.get_data(data_id)
            if not isinstance(carbon_records, list) or len(carbon_records) == 0:
                return {
                    "status": "failed",
                    "success": False,
                    "data": None,
                    "metadata": {"tool_name": "calculate_carbon", "error_type": "empty_data"},
                    "summary": "[FAIL] 数据为空或格式错误"
                }
            logger.info("[calculate_carbon] 加载碳组分数据", records=len(carbon_records))
        except KeyError:
            return {
                "status": "failed",
                "success": False,
                "data": None,
                "metadata": {"tool_name": "calculate_carbon", "error_type": "data_not_found"},
                "summary": f"[FAIL] 未找到数据 {data_id}"
            }
        except Exception as exc:
            return {
                "status": "failed",
                "success": False,
                "data": None,
                "metadata": {"tool_name": "calculate_carbon", "error": str(exc)},
                "summary": f"[FAIL] 数据加载失败: {exc}"
            }

        # Step 2: 执行计算
        result = calculate_carbon(
            data=carbon_records,
            data_id=data_id,
            carbon_type=carbon_type,
            oc_to_om=oc_to_om,
            poc_method=poc_method
        )

        # Step 3: 保存分析结论（供后续Agent引用）
        if result.get("success") and context is not None:
            try:
                statistics = result.get("statistics", {})
                visuals = result.get("visuals", [])
                summary = {
                    "status": "success",
                    "statistics": statistics,
                    "visuals_count": len(visuals),
                    "visuals": [
                        {
                            "id": v.get("id"),
                            "title": v.get("payload", {}).get("title"),
                            "type": v.get("meta", {}).get("chart_type"),
                            "image_url": v.get("payload", {}).get("image_url") or v.get("meta", {}).get("image_url"),
                            "markdown_image": v.get("payload", {}).get("markdown_image") or v.get("meta", {}).get("markdown_image"),
                        }
                        for v in visuals
                    ]
                }
                result_data_ref = context.save_data(
                    data=[summary],
                    schema="particulate_analysis",
                    metadata={
                        "source_data_id": data_id,
                        "ec_oc_mean": statistics.get("ec_oc", {}).get("mean"),
                        "soc_mean": statistics.get("poc_soc", {}).get("soc_mean"),
                        "poc_mean": statistics.get("poc_soc", {}).get("poc_mean"),
                        "secondary_level": statistics.get("secondary_organic", {}).get("level"),
                    }
                )
                result_data_id = result_data_ref["data_id"]
                result_file_path = result_data_ref["file_path"]
                result["data_id"] = result_data_id
                result["file_path"] = result_file_path
            except Exception as save_err:
                logger.warning(f"[calculate_carbon] 保存失败: {save_err}")

        return result


if __name__ == "__main__":
    # 简单的单元测试
    test_records = [
        {
            "timestamp": "2025-12-24 01:00:00",
            "components": {
                "OC": 12.5, "EC": 2.3
            },
            "PM2.5": 50.0
        },
        {
            "timestamp": "2025-12-24 02:00:00",
            "components": {
                "OC": 15.2, "EC": 3.1
            },
            "PM2.5": 60.0
        },
        {
            "timestamp": "2025-12-24 03:00:00",
            "components": {
                "OC": 18.0, "EC": 3.8
            },
            "PM2.5": 70.0
        },
        {
            "timestamp": "2025-12-24 04:00:00",
            "components": {
                "OC": 14.5, "EC": 2.8
            },
            "PM2.5": 55.0
        },
        {
            "timestamp": "2025-12-24 05:00:00",
            "components": {
                "OC": 16.0, "EC": 3.5
            },
            "PM2.5": 65.0
        }
    ]
    result = calculate_carbon(data=test_records)
    print(f"Status: {result['status']}")
    print(f"Visuals count: {len(result.get('visuals', []))}")
    print(f"Statistics: {result['data']['statistics']}")
    if result.get('visuals'):
        first = result['visuals'][0]
        print(f"First visual type: {first.get('type')}")
        print(f"First visual has payload: {'payload' in first}")
    print(f"Field mapping applied: {result['metadata'].get('field_mapping_applied')}")
    print(f"Field mapping info: {result['metadata'].get('field_mapping_info')}")
