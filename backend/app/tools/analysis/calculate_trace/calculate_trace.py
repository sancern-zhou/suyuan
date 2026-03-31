"""
calculate_trace: 微量元素分析（铝归一化、Taylor 丰度对比、富集度）
计算完成后，使用ParticulateVisualizer生成微量元素富集因子柱状图。
"""
from typing import Any, Dict, List, Optional
import hashlib
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np

try:
    from app.agent.context.data_context_manager import DataContextManager
except Exception:
    DataContextManager = Any

# 添加 ParticulateVisualizer 导入
from app.tools.visualization.particulate_visualizer import ParticulateVisualizer


def _hash_dataframe(df: pd.DataFrame) -> str:
    try:
        b = df.to_csv(index=False).encode("utf-8")
        return hashlib.md5(b).hexdigest()
    except Exception:
        return ""


# =============================================================================
# 默认 Taylor 丰度字典 (地壳元素平均丰度, wt%)
# 参考: Taylor, S.R. (1964) abundances of elements in the earth's crust
#
# 字段名规范：使用英文字段名（与DataStandardizer.pm_component_field_mapping对齐）
# 前端图表显示中文由可视化层处理
# =============================================================================
DEFAULT_TAYLOR_ABUNDANCE = {
    # 地壳元素 (Crustal Elements)
    "Al": 8.23,      # 铝 Aluminum
    "Si": 28.15,     # 硅 Silicon
    "Ca": 4.15,      # 钙 Calcium
    "Fe": 5.63,      # 铁 Iron
    "Mg": 2.33,      # 镁 Magnesium
    "K": 2.59,       # 钾 Potassium
    "Na": 2.82,      # 钠 Sodium
    "Ti": 0.565,     # 钛 Titanium
    # 微量元素 (Trace Elements)
    "Mn": 0.095,     # 锰 Manganese
    "Zn": 0.007,     # 锌 Zinc
    "Pb": 0.001,     # 铅 Lead
    "Cu": 0.005,     # 铜 Copper
    "Cd": 0.00002,   # 镉 Cadmium
    "Cr": 0.01,      # 铬 Chromium
    "Ni": 0.0075,    # 镍 Nickel
    "As": 0.00018,   # 砷 Arsenic
    "Hg": 0.000008,  # 汞 Mercury
    "V": 0.0135,     # 钒 Vanadium
    "Co": 0.0025,    # 钴 Cobalt
}


def trace_elements_normalize(trace_data: pd.DataFrame, al_data: pd.Series) -> Optional[pd.DataFrame]:
    if trace_data is None or al_data is None:
        return None
    common_index = trace_data.index.intersection(al_data.index)
    if len(common_index) < 1:
        return None
    trace_data = trace_data.loc[common_index].copy()
    al_data = al_data.loc[common_index].copy().replace(0, np.nan)
    normalized = trace_data.div(al_data, axis=0)
    normalized = normalized.dropna(axis=1, how='all').dropna(axis=0, how='all')
    if normalized.empty:
        return None
    return normalized


def divide_by_taylor(normalized_data: pd.DataFrame, taylor_dict: Dict[str, float]) -> Optional[pd.DataFrame]:
    valid_cols = [col for col in normalized_data.columns if col in taylor_dict]
    if not valid_cols:
        return None
    final = normalized_data[valid_cols].copy()
    for col in valid_cols:
        t = taylor_dict.get(col, None)
        if t in (0, None) or pd.isna(t):
            final.drop(col, axis=1, inplace=True)
            continue
        final[col] = final[col] / float(t)
    final = final.dropna(axis=1, how='all')
    if final.empty:
        return None
    return final


def calculate_trace(
    data: Optional[pd.DataFrame] = None,
    data_id: Optional[str] = None,
    al_column: str = "Al",
    taylor_dict: Optional[Dict[str, float]] = None,
    data_context_manager: Optional["DataContextManager"] = None,
) -> Dict[str, Any]:
    """
    微量元素分析（铝归一化、Taylor 丰度对比、富集度）。
    计算完成后，通过原始数据的data_id传递给smart_chart_generator生成可视化图表。

    Args:
        data: DataFrame 包含微量元素列与铝列（已通过DataStandardizer标准化）
        data_id: 原始数据ID（传递给smart_chart_generator生成图表）
        al_column: 铝列名（用于归一化，默认"Al"，英文字段名）
        taylor_dict: Taylor丰度字典，如果不提供则使用默认字典（英文字段名）
        data_context_manager: 数据上下文管理器（包含DataStandardizer）

    Returns:
        遵循 UDF v2.0 的 dict，包含计算结果和原始data_id（用于smart_chart_generator）

    Note:
        - 数据字段应在DataStandardizer中标准化为英文字段名
        - 前端图表显示中文由可视化层处理
    """
    import structlog
    logger = structlog.get_logger()

    # 保存原始数据ID
    original_data_id = data_id

    # 【调试日志】记录 data_id 的完整值
    logger.info(
        "calculate_trace_data_id_received",
        data_id=data_id,
        data_id_length=len(data_id) if data_id else 0,
        data_id_hash=data_id.split(":")[-1] if data_id and ":" in data_id else None,
        data_context_manager_type=type(data_context_manager).__name__ if data_context_manager else None,
        session_id=data_context_manager.memory.session_id if data_context_manager else None,
        data_files_keys_count=len(data_context_manager.memory.session.data_files) if data_context_manager else 0,
        data_files_sample_keys=list(data_context_manager.memory.session.data_files.keys())[:3] if data_context_manager else []
    )

    # 使用默认 Taylor 丰度字典
    effective_taylor = taylor_dict or DEFAULT_TAYLOR_ABUNDANCE

    if data is None:
        if data_id and data_context_manager:
            try:
                # 使用 get_data() 获取类型化数据
                typed_data = data_context_manager.get_data(data_id)
                if isinstance(typed_data, list):
                    data = typed_data
            except Exception as e1:
                logger.warning(
                    "calculate_trace_get_data_failed",
                    data_id=data_id,
                    error=str(e1),
                    error_type=type(e1).__name__
                )
                # 降级到 get_raw_data()
                try:
                    raw = data_context_manager.get_raw_data(data_id)
                    if isinstance(raw, list):
                        data = pd.DataFrame(raw)
                except Exception as e2:
                    logger.error(
                        "calculate_trace_get_raw_data_failed",
                        data_id=data_id,
                        error=str(e2),
                        error_type=type(e2).__name__
                    )
        if data is None:
            raise ValueError(f"无法加载数据: data_id={data_id}")

    # 处理 UnifiedParticulateData 格式（字典列表）
    if isinstance(data, list) and len(data) > 0:
        # 从 components 字段提取微量元素数据
        rows = []
        for record in data:
            if hasattr(record, 'model_dump'):
                record_dict = record.model_dump()
            else:
                record_dict = dict(record)

            timestamp = record_dict.get('timestamp')
            components = record_dict.get('components', {})

            # 构建行数据（展平 components）
            row = {'timestamp': timestamp}
            if isinstance(components, dict):
                row.update(components)
            rows.append(row)

        df = pd.DataFrame(rows)
        logger.info(f"[calculate_trace] 从components字段提取数据，完成，列数: {len(df.columns)}")
    else:
        df = data.copy()

    # 数据已通过DataStandardizer标准化，直接使用英文字段名
    available_columns = list(df.columns)

    # 检查指定的al_column是否存在
    if al_column not in df.columns:
        # 如果指定的列不存在，尝试使用常见的地壳元素
        crustal_elements = ["Al", "Si", "Fe", "Ca", "Mg", "K", "Na", "Ti"]
        for elem in crustal_elements:
            if elem in df.columns:
                # 验证是否为数值列且有有效数据
                if pd.api.types.is_numeric_dtype(df[elem]) and df[elem].notna().sum() > 0:
                    al_column = elem
                    logger.info(f"[calculate_trace] 指定列不存在，使用地壳元素 {elem} 作为归一化参考")
                    break

    # 最终验证：检查是否有可用的参考列
    has_al_column = al_column in df.columns and pd.api.types.is_numeric_dtype(df[al_column])

    if not has_al_column:
        # 没有可用的参考列，返回基本统计信息
        logger.warning(f"[calculate_trace] 没有可用的参考列，available_columns={available_columns}")
        return {
            "status": "success",
            "success": True,
            "data": {
                "message": "没有可用的微量元素数据进行分析（缺少参考列）",
                "available_columns": available_columns,
                "requested_column": al_column,
            },
            "metadata": {
                "generator": "calculate_trace",
                "version": "1.2.0",
                "schema_version": "v2.0",
                "scenario": "pm_trace_analysis",
                "note": "数据已通过DataStandardizer标准化，但缺少参考列（Al或其他地壳元素）",
                "source_data_id": original_data_id,
            },
            "visuals": []
        }

    logger.info(f"[calculate_trace] 开始分析，reference_column={al_column}, available_columns={available_columns}")

    al_series = df[al_column]
    # 获取其他所有列作为微量元素（排除常见非数据列）
    exclude_cols = ['Code', 'StationName', 'TimePoint', 'timestamp', 'PM2.5', 'PM10', 'al_column',
                    'DataType', 'TimeType', 'species_data']
    trace_cols = [c for c in df.columns if c not in exclude_cols and c != al_column]

    # 如果没有微量元素列，返回提示
    if not trace_cols:
        logger.warning("[calculate_trace] 没有找到微量元素列")
        return {
            "status": "success",
            "success": True,
            "data": {
                "message": f"数据中没有可用的微量元素列（除{al_column}外）",
                "reference_column": al_column,
                "available_columns": available_columns,
            },
            "metadata": {
                "generator": "calculate_trace",
                "version": "1.2.0",
                "schema_version": "v2.0",
                "scenario": "pm_trace_analysis",
                "source_data_id": original_data_id,
            },
            "visuals": []
        }

    trace_df = df[trace_cols].copy()

    # 过滤空列
    trace_df = trace_df.dropna(axis=1, how='all')
    trace_cols = [c for c in trace_cols if c in trace_df.columns]

    if not trace_cols:
        return {
            "status": "success",
            "success": True,
            "data": {"message": "所有微量元素列均为空"},
            "metadata": {"generator": "calculate_trace", "version": "1.1.0", "schema_version": "v2.0", "source_data_id": original_data_id},
            "visuals": []
        }

    logger.info(f"[calculate_trace] 微量元素列: {trace_cols}, 参考列: {al_column}")

    normalized = trace_elements_normalize(trace_df, al_series)
    divided = divide_by_taylor(normalized, effective_taylor)

    # 构建时间索引
    if "TimePoint" in df.columns:
        time_index = pd.to_datetime(df["TimePoint"])
    elif "timestamp" in df.columns:
        time_index = pd.to_datetime(df["timestamp"])
    else:
        time_index = range(len(df))

    metadata = {
        "generator": "calculate_trace",
        "version": "1.1.0",
        "source_data_hash": _hash_dataframe(data),
        "schema_version": "v2.0",
        "scenario": "pm_trace_analysis",
        "reference_column": al_column,
        "trace_elements": trace_cols,
        # 保留原始数据ID，用于smart_chart_generator生成图表
        "source_data_id": original_data_id,
    }

    # 计算基础统计
    if not trace_df.empty:
        trace_stats = trace_df.describe().to_dict()
    else:
        trace_stats = {}

    # 构建富集因子数据
    enrichment_factors = []
    if divided is not None and not divided.empty:
        avg = divided.mean().sort_values(ascending=False)
        enrichment_factors = [{"name": k, "value": round(float(v), 4)} for k, v in avg.items()]

    # 生成专业图表（使用 ParticulateVisualizer）
    visuals = []
    try:
        if divided is not None and not divided.empty:
            visualizer = ParticulateVisualizer()
            enrichment_chart = visualizer.generate_trace_enrichment_chart(divided, source_data_id=original_data_id)
            if enrichment_chart:
                visuals.append(enrichment_chart)
                logger.info("[calculate_trace] 微量元素富集因子图生成成功")
    except Exception as viz_err:
        logger.warning(f"[calculate_trace] 专业图表生成失败: {viz_err}")

    logger.info(f"[calculate_trace] 计算完成，trace_elements={trace_cols}, reference_column={al_column}, visuals_count={len(visuals)}")

    # 添加图片URL到summary
    summary_lines = [
        f"✅ calculate_trace 执行完成 - 微量元素: {trace_cols}, 参考元素: {al_column}"
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
            "original": df.to_dict(orient="records") if len(df) <= 100 else df.head(100).to_dict(orient="records"),
            "trace_statistics": trace_stats,
            "normalized": normalized.reset_index().rename(columns={"index": "timestamp"}).to_dict(orient="records") if normalized is not None and not normalized.empty else [],
            "divided_by_taylor": divided.reset_index().rename(columns={"index": "timestamp"}).to_dict(orient="records") if divided is not None and not divided.empty else [],
            "enrichment_factors": enrichment_factors,
            "reference_column": al_column,
            "elements_analyzed": trace_cols,
        },
        "metadata": metadata,
        "visuals": visuals,  # 微量元素富集因子图由ParticulateVisualizer生成
        "summary": summary,
    }


# ============================================================================
# 工具包装器类（用于注册到全局工具注册表）
# ============================================================================

from app.tools.base.tool_interface import LLMTool, ToolCategory


class CalculateTraceTool(LLMTool):
    """微量元素分析工具

    计算微量元素的铝归一化、Taylor丰度对比、富集因子：
    - 微量元素富集因子图：由ParticulateVisualizer直接生成图片

    字段映射规范：
    - 使用DataStandardizer统一标准化字段名（英文）
    - 工具内部不再维护字段映射表（避免重复）
    - 前端图表显示中文由可视化层处理

    版本历史：
    - v1.2.0: 统一使用DataStandardizer字段映射，移除内部映射表
    - v1.1.0: 初始版本
    """
    name = "calculate_trace"
    description = "计算微量元素分析（铝归一化、Taylor丰度对比、富集度），自动生成富集因子图（ParticulateVisualizer）。数据字段需通过DataStandardizer标准化为英文字段名。"
    category = ToolCategory.ANALYSIS
    version = "1.2.0"
    requires_context = True  # 需要ExecutionContext来获取data_context_manager

    def __init__(self):
        super().__init__(
            name=self.name,
            description=self.description,
            category=self.category,
            version=self.version,
            requires_context=self.requires_context
        )

    async def execute(self, context=None, data=None, al_column="Al", taylor_dict=None, **kwargs):
        """
        执行微量元素分析

        Args:
            context: ExecutionContext
            data: 原始数据（已通过DataStandardizer标准化）
            al_column: 铝列名（默认"Al"，英文字段名）
            taylor_dict: Taylor丰度字典（可选，默认使用内置字典）
            **kwargs: 其他参数（包括data_context_manager, data_id）
        """
        data_context_manager = kwargs.get('data_context_manager')
        data_id = kwargs.get('data_id')

        if data_context_manager is None and context is not None:
            if hasattr(context, 'data_manager'):
                data_context_manager = context.data_manager
            elif hasattr(context, 'get_data_manager'):
                data_context_manager = context.get_data_manager()
            elif isinstance(context, dict) and context.get('data_manager'):
                data_context_manager = context['data_manager']
            elif hasattr(context, 'get_data'):
                data_context_manager = context

        result = calculate_trace(
            data=data,
            data_id=data_id,
            al_column=al_column,
            taylor_dict=taylor_dict,
            data_context_manager=data_context_manager
        )

        if data_context_manager is not None and result.get("success"):
            try:
                result_data_id = data_context_manager.save_data(
                    data=[result],
                    schema="particulate_analysis"
                )
                result["data_id"] = result_data_id
            except Exception as save_err:
                import structlog
                logging.warning(f"[calculate_trace] 保存结果失败: {save_err}")

        return result


if __name__ == "__main__":
    # 简单的单元测试
    import pandas as pd
    test_data = pd.DataFrame({
        '铝': [80, 85, 90],
        '铁': [50, 55, 60],
        '锰': [2, 2.5, 3]
    }).set_index(pd.date_range('2024-01-01', periods=3, freq='h'))
    taylor_dict = {'铁': 6.25, '锰': 0.095}
    result = calculate_trace(data=test_data, al_column='铝', taylor_dict=taylor_dict)
    print(f"Status: {result['status']}")
    print(f"Visuals count: {len(result.get('visuals', []))}")
    if result.get('visuals'):
        first = result['visuals'][0]
        print(f"First visual type: {first.get('type')}")
        print(f"First visual has payload: {'payload' in first}")
