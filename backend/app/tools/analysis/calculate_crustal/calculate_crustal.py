"""
calculate_crustal: 地壳元素分析（氧化物转换、时间序列）

支持 Context-Aware V2，使用 ExecutionContext 管理数据生命周期。
计算完成后：
- 地壳元素箱线图：由ParticulateVisualizer直接生成图片
- 地壳元素时序图：由smart_chart_generator生成（需传入data_id）
"""
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union
import hashlib
import warnings
import structlog
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np

logger = structlog.get_logger()

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

try:
    from app.agent.context.data_context_manager import DataContextManager
except Exception:
    DataContextManager = Any

# 添加 ParticulateVisualizer 导入
from app.tools.visualization.particulate_visualizer import ParticulateVisualizer

# 默认地壳元素氧化物转换系数
DEFAULT_CRUSTAL_COEFFICIENTS = {
    "Al": 1.889,   # Al → Al₂O₃
    "Si": 2.139,   # Si → SiO₂
    "Fe": 1.430,   # Fe → Fe₂O₃
    "Ca": 1.399,   # Ca → CaO
    "Mg": 1.658,   # Mg → MgO
    "K": 1.204,    # K → K₂O
    "Na": 1.348,   # Na → Na₂O
    "Ti": 1.668,   # Ti → TiO₂
    "铝": 1.889,   # 中文别名
    "硅": 2.139,
    "铁": 1.430,
    "钙": 1.399,
    "镁": 1.658,
    "钾": 1.204,
    "钠": 1.348,
    "钛": 1.668,
}


def _extract_crustal_columns(records: List[Dict], oxide_coeff_dict: Dict[str, float]) -> pd.DataFrame:
    """从 UnifiedParticulateData 格式的记录中提取地壳元素数据到 DataFrame。

    数据格式：UnifiedParticulateData（components 嵌套结构）

    Args:
        records: 包含 components 字段的记录列表
        oxide_coeff_dict: 氧化物转换系数

    Returns:
        包含地壳元素列的 DataFrame
    """
    if not records:
        logger.warning("[_extract_crustal_columns] 输入记录列表为空")
        return pd.DataFrame()

    # 调试：记录第一条原始记录的结构
    first_record = records[0]
    if hasattr(first_record, 'model_dump'):
        first_record_dict = first_record.model_dump()
    else:
        first_record_dict = dict(first_record)

    logger.info(
        "[_extract_crustal_columns] 原始数据结构分析",
        first_record_keys=list(first_record_dict.keys())[:15],
        has_components='components' in first_record_dict,
        sample_timestamp=first_record_dict.get('timestamp'),
        sample_station_code=first_record_dict.get('station_code'),
    )

    # 如果有 components 字段，调试其内容
    if 'components' in first_record_dict:
        components = first_record_dict['components']
        if isinstance(components, dict):
            logger.info(
                "[_extract_crustal_columns] components 字段内容",
                component_keys=list(components.keys()),
                sample_values={k: v for k, v in list(components.items())[:5]}
            )

    rows = []
    for idx, record in enumerate(records):
        # Pydantic 模型转字典
        if hasattr(record, 'model_dump'):
            record_dict = record.model_dump()
        else:
            record_dict = dict(record)

        # 提取时间戳
        timestamp = record_dict.get('timestamp')
        if idx == 0:
            logger.info("[_extract_crustal_columns] timestamp提取", timestamp_value=timestamp)

        # 提取 components
        components = record_dict.get('components', {})
        if idx == 0:
            logger.info(
                "[_extract_crustal_columns] components提取",
                is_dict=isinstance(components, dict),
                keys=list(components.keys()) if isinstance(components, dict) else None
            )

        # 构建行数据
        row = {'timestamp': timestamp}

        # 合并所有 components 数据
        if isinstance(components, dict):
            row.update(components)

        if idx == 0:
            logger.info(
                "[_extract_crustal_columns] 最终行数据",
                row_keys=list(row.keys()),
                component_count=len(components) if isinstance(components, dict) else 0
            )

        rows.append(row)

    df = pd.DataFrame(rows)

    # 记录最终 DataFrame 的列信息
    # 获取氧化物转换系数字段（用于过滤）
    coeff_keys = set(oxide_coeff_dict.keys()) if oxide_coeff_dict else set(DEFAULT_CRUSTAL_COEFFICIENTS.keys())
    available_elements = [c for c in df.columns if c in coeff_keys]

    logger.info(
        "[_extract_crustal_columns] DataFrame 构建完成",
        columns=list(df.columns),
        row_count=len(df),
        available_elements=available_elements
    )

    # 设置时间戳索引
    if 'timestamp' in df.columns and df['timestamp'].notna().any():
        df = df.set_index('timestamp')

    return df


def _hash_dataframe(df: pd.DataFrame) -> str:
    try:
        b = df.to_csv(index=False).encode("utf-8")
        return hashlib.md5(b).hexdigest()
    except Exception:
        return ""


def calculate_crustal(
    data: Optional[Union[pd.DataFrame, List[Dict]]] = None,
    data_id: Optional[str] = None,
    oxide_coeff_dict: Optional[Dict[str, float]] = None,
    reconstruction_type: str = "full",
) -> Dict[str, Any]:
    """
    计算地壳元素氧化物转换和时间序列。
    计算完成后，通过原始数据的data_id传递给smart_chart_generator生成可视化图表。

    支持两种输入格式：
    1. DataFrame: 地壳元素字段直接在顶层（如 Al, Si, Fe, Ca, Mg）
    2. 字典列表: UnifiedParticulateData 格式，地壳元素在 components 字段中

    Args:
        data: 输入数据（DataFrame 或 包含 components 的记录列表）
        data_id: 原始数据ID（传递给smart_chart_generator生成图表）
        oxide_coeff_dict: dict mapping column -> oxide coefficient
        reconstruction_type: 时间聚合类型

    Returns:
        遵循 UDF v2.0 的 dict，包含计算结果和原始data_id（用于smart_chart_generator）
    """
    # 保存原始数据ID
    original_data_id = data_id

    if data is None:
        return {
            "status": "failed",
            "success": False,
            "data": None,
            "metadata": {"tool_name": "calculate_crustal", "error": "no_data"},
            "summary": "[FAIL] 数据为空"
        }

    # 统一转换为 DataFrame
    if isinstance(data, list):
        # 字典列表格式（包含 components 字段）
        # 从 UnifiedParticulateData 格式提取地壳元素
        df = _extract_crustal_columns(data, oxide_coeff_dict or DEFAULT_CRUSTAL_COEFFICIENTS)
    else:
        # DataFrame 格式
        df = data.copy()

    # 使用默认氧化物转换系数（如果未提供）
    if oxide_coeff_dict is None:
        oxide_coeff_dict = DEFAULT_CRUSTAL_COEFFICIENTS

    # 【关键修复】展平 species_data 嵌套字典到顶层列（兼容旧格式）
    if 'species_data' in df.columns:
        logger.info("[calculate_crustal] 检测到 species_data 字段，展开为顶层列")
        species_expanded = []
        for idx, row in df.iterrows():
            flat_row = row.to_dict()
            species_data = row.get('species_data')
            if isinstance(species_data, dict):
                flat_row.update(species_data)
            species_expanded.append(flat_row)
        df = pd.DataFrame(species_expanded)
        logger.info(
            "[calculate_crustal] species_data 展开完成",
            original_columns=list(data.columns) if hasattr(data, 'columns') else [],
            expanded_columns=list(df.columns)
        )

    # 过滤空列
    df = df.dropna(axis=1, how="all")
    valid_elements = [col for col in df.columns if col in oxide_coeff_dict]
    if not valid_elements:
        # 部分分析：即使没有标准地壳元素，也尝试从所有数值列中识别可能的地壳相关元素
        # 例如: calcium(Ca), magnesium(Mg), potassium(K), sodium(Na) 同时也是地壳元素
        # 检查 components 中是否有这些元素
        all_components = set()
        # data 是输入参数，可能需要从 df.columns 中提取
        # 因为 df 已经从 data 转换而来
        for col in df.columns:
            if col not in ['timestamp', 'index']:
                all_components.add(col)

        # 扩展地壳元素列表（包含同时是水溶性离子的地壳元素）
        extended_crustal_elements = {
            "Al": 1.889, "Si": 2.139, "Fe": 1.430, "Ca": 1.399, "Mg": 1.658, "K": 1.204, "Na": 1.348, "Ti": 1.668,
            "铝": 1.889, "硅": 2.139, "铁": 1.430, "钙": 1.399, "镁": 1.658, "钾": 1.204, "钠": 1.348, "钛": 1.668,
            # 兼容英文字段名
            "aluminum": 1.889, "silicon": 2.139, "iron": 1.430,
            "calcium": 1.399, "magnesium": 1.658, "potassium": 1.204, "sodium": 1.348, "titanium": 1.668,
        }

        valid_elements = [col for col in df.columns if col in extended_crustal_elements]

        if valid_elements:
            logger.info(f"[calculate_crustal] 部分分析模式：检测到 {len(valid_elements)} 个地壳元素: {valid_elements}")
            oxide_coeff_dict = extended_crustal_elements  # 使用扩展的转换系数
        else:
            # 完全没有可用的地壳元素
            return {
                "status": "success",
                "success": True,
                "data": [],
                "metadata": {
                    "generator": "calculate_crustal",
                    "version": "1.0.0",
                    "schema_version": "v2.0",
                    "note": "no valid crustal elements",
                    "available_components": list(all_components),
                    "source_data_id": original_data_id,
                },
                "visuals": [],
                "summary": f"✅ calculate_crustal 执行完成 - 未检测到有效的地壳元素，可用组分: {list(all_components)}"
            }

    dust_df = df[valid_elements].fillna(0).copy()
    # apply oxide coefficients
    for col in valid_elements:
        coeff = float(oxide_coeff_dict.get(col, 0.0))
        dust_df[col] = dust_df[col].astype(float) * coeff

    # sum to crustal
    crustal_series = dust_df.sum(axis=1)

    # aggregate if needed
    if "timestamp" in dust_df.columns:
        dust_df.index = pd.to_datetime(dust_df["timestamp"])
    if reconstruction_type == "daily":
        dust_df = dust_df.resample("D").mean()
        crustal_series = crustal_series.resample("D").mean()
    elif reconstruction_type == "hourly":
        dust_df = dust_df.resample("H").mean()
        crustal_series = crustal_series.resample("H").mean()

    metadata = {
        "generator": "calculate_crustal",
        "version": "1.0.0",
        "source_data_hash": _hash_dataframe(data),
        "schema_version": "v2.0",
        "scenario": "pm_crustal_analysis",
        # 保留原始数据ID，用于smart_chart_generator生成图表
        "source_data_id": original_data_id,
    }

    # 构建时间轴数据
    if isinstance(dust_df.index, pd.DatetimeIndex):
        timestamps = dust_df.index.strftime("%Y-%m-%dT%H:%M:%SZ").tolist()
    elif "timestamp" in dust_df.columns:
        timestamps = dust_df["timestamp"].tolist()
    else:
        timestamps = [f"t{i}" for i in range(len(dust_df))]

    # 构建计算结果数据
    series_data = []
    for col in dust_df.columns:
        series_data.append({
            "name": col,
            "data": dust_df[col].fillna(np.nan).tolist()
        })
    # 添加地壳物质总量
    series_data.append({
        "name": "地壳物质总量",
        "data": crustal_series.fillna(np.nan).tolist()
    })

    # 构建箱线图数据
    boxplot_data = []
    for col in dust_df.columns:
        col_data = dust_df[col].dropna().tolist()
        if col_data:
            boxplot_data.append({
                "name": col,
                "data": col_data
            })

    # 生成专业图表（使用 ParticulateVisualizer）
    visuals = []
    try:
        visualizer = ParticulateVisualizer()

        # 地壳元素箱线图
        boxplot_chart = visualizer.generate_crustal_boxplot_chart(dust_df, source_data_id=original_data_id)
        if boxplot_chart:
            visuals.append(boxplot_chart)
            logger.info("[calculate_crustal] 地壳元素箱线图生成成功")

    except Exception as viz_err:
        logger.warning(f"[calculate_crustal] 专业图表生成失败: {viz_err}")

    # 生成摘要信息
    crustal_mean = round(float(crustal_series.mean()), 4) if not crustal_series.empty else None
    crustal_max = round(float(crustal_series.max()), 4) if not crustal_series.empty else None
    element_count = len(dust_df.columns)

    # 检查是否是部分分析模式（使用扩展的地壳元素列表）
    is_partial_analysis = oxide_coeff_dict != DEFAULT_CRUSTAL_COEFFICIENTS
    standard_crustal = ["Al", "Si", "Fe", "Ti"]
    detected_standard = [e for e in valid_elements if e in standard_crustal or e in ["铝", "硅", "铁", "钛"]]
    detected_extended = [e for e in valid_elements if e not in detected_standard]

    # 添加图片URL到summary
    if is_partial_analysis and detected_extended:
        summary_lines = [
            f"✅ calculate_crustal 部分分析 - 地壳元素: {valid_elements}, 缺少标准元素: {[e for e in standard_crustal if e not in detected_standard]}, 地壳物质均值: {crustal_mean}, 最大值: {crustal_max}"
        ]
    else:
        summary_lines = [
            f"✅ calculate_crustal 执行完成 - 地壳元素数量: {element_count}, 地壳物质均值: {crustal_mean}, 最大值: {crustal_max}"
        ]

    # 如果有图表，添加图片URL
    if visuals:
        for visual in visuals:
            markdown_image = visual.get("markdown_image")
            if markdown_image:
                summary_lines.append(f"\n{markdown_image}")
                break  # 只添加第一张图

    summary = "\n".join(summary_lines)

    # 地壳元素时序图由smart_chart_generator通过data_id生成
    logger.info(
        "[calculate_crustal] 计算完成",
        dust_df_columns=list(dust_df.columns),
        source_data_id=original_data_id,
        visuals_count=len(visuals),
        note="地壳元素箱线图由ParticulateVisualizer生成，时序图由smart_chart_generator生成"
    )

    return {
        "status": "success",
        "success": True,
        "data": None,  # 大量时序数据已省略，直接返回统计摘要
        "visuals": visuals,  # 地壳元素箱线图（已包含image_url和markdown_image）
        "statistics": {  # 统计结论供LLM分析
            "element_count": len(dust_df.columns),
            "crustal_mean": round(float(crustal_series.mean()), 4) if not crustal_series.empty else None,
            "crustal_max": round(float(crustal_series.max()), 4) if not crustal_series.empty else None,
            "elements": list(dust_df.columns)
        },
        "metadata": metadata
    }
    # 原返回结构（保留注释供参考）
    # return {
    #     "status": "success",
    #     "success": True,
    #     "data": {
    #         "oxide_converted": dust_df.reset_index().rename(columns={"index": "timestamp"}).to_dict(orient="records"),
    #         "crustal": crustal_series.reset_index().rename(columns={"index": "timestamp", 0: "crustal"}).to_dict(orient="records") if not crustal_series.empty else [],
    #         "series": series_data,
    #         "boxplot_data": boxplot_data
    #     },
    #     "metadata": metadata,
    #     "visuals": visuals,
    #     "summary": summary,
    # }


# ============================================================================
# 工具包装器类（用于注册到全局工具注册表）
# ============================================================================

from app.tools.base.tool_interface import LLMTool, ToolCategory


class CalculateCrustalTool(LLMTool):
    """地壳元素分析工具

    支持 Context-Aware V2，使用 ExecutionContext 管理数据生命周期。

    计算地壳元素（Al, Si, Fe, Ca, Mg等）的氧化物转换：
    - 地壳元素箱线图：由ParticulateVisualizer直接生成图片
    - 地壳元素时序图：通过smart_chart_generator生成（需传入data_id）
    """
    name = "calculate_crustal"
    description = "计算地壳元素分析，自动生成地壳元素箱线图（ParticulateVisualizer）和时序图（smart_chart_generator）"
    category = ToolCategory.ANALYSIS
    version = "1.0.0"
    requires_context = True

    def __init__(self):
        function_schema = {
            "name": "calculate_crustal",
            "description": """
执行地壳元素分析，计算氧化物转换和地壳物质总量。

**数据来源**:
- 从 get_particulate_data 获取的数据（components 字段包含地壳元素：Al、Si、Fe、Ca、Mg等）

**输入格式**: UnifiedParticulateData（components 嵌套结构）
- 数据自动从 components 字段提取地壳元素
- 自动计算氧化物转换（乘以转换系数）

**氧化物转换系数**:
- Al → Al₂O₃: 1.889
- Si → SiO₂: 2.139
- Fe → Fe₂O₃: 1.430
- Ca → CaO: 1.399
- Mg → MgO: 1.658
- K → K₂O: 1.204
- Na → Na₂O: 1.348
- Ti → TiO₂: 1.668

**返回结果**:
- 氧化物转换后的地壳元素浓度
- 地壳物质总量（∑地壳元素氧化物）
- 专业图表：地壳元素箱线图

**示例**:
calculate_crustal(
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
                    "oxide_coeff_dict": {
                        "type": "object",
                        "description": "氧化物转换系数（可选，使用默认值）"
                    },
                    "reconstruction_type": {
                        "type": "string",
                        "enum": ["full", "daily", "hourly"],
                        "default": "full",
                        "description": "时间聚合类型"
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
        oxide_coeff_dict: Optional[Dict[str, float]] = None,
        reconstruction_type: str = "full",
        **kwargs
    ) -> Dict[str, Any]:
        """执行地壳元素分析"""
        # Step 1: 获取标准化后的地壳元素数据
        try:
            crustal_records = context.get_data(data_id)
            if not isinstance(crustal_records, list) or len(crustal_records) == 0:
                return {
                    "status": "failed",
                    "success": False,
                    "data": None,
                    "metadata": {"tool_name": "calculate_crustal", "error_type": "empty_data"},
                    "summary": "[FAIL] 数据为空或格式错误"
                }
            logger.info("[calculate_crustal] 加载地壳元素数据", records=len(crustal_records))
        except KeyError:
            return {
                "status": "failed",
                "success": False,
                "data": None,
                "metadata": {"tool_name": "calculate_crustal", "error_type": "data_not_found"},
                "summary": f"[FAIL] 未找到数据 {data_id}"
            }
        except Exception as exc:
            return {
                "status": "failed",
                "success": False,
                "data": None,
                "metadata": {"tool_name": "calculate_crustal", "error": str(exc)},
                "summary": f"[FAIL] 数据加载失败: {exc}"
            }

        # Step 2: 执行计算
        result = calculate_crustal(
            data=crustal_records,
            data_id=data_id,
            oxide_coeff_dict=oxide_coeff_dict,
            reconstruction_type=reconstruction_type,
        )

        # Step 3: 保存分析结论（供后续Agent引用）
        if result.get("success") and context is not None:
            try:
                statistics = result.get("statistics", {})
                visuals = result.get("visuals", [])
                element_count = statistics.get("element_count", 0)
                crustal_mean = statistics.get("crustal_mean")

                summary = {
                    "status": "success",
                    "element_count": element_count,
                    "crustal_mean": crustal_mean,
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
                        "element_count": element_count,
                        "crustal_mean": crustal_mean,
                    }
                )
                result_data_id = result_data_ref["data_id"]
                result_file_path = result_data_ref["file_path"]
                result["data_id"] = result_data_id
                result["file_path"] = result_file_path
            except Exception as save_err:
                logger.warning(f"[calculate_crustal] 保存失败: {save_err}")

        return result


if __name__ == "__main__":
    # 简单的单元测试
    import pandas as pd
    test_data = pd.DataFrame({
        '钙': [10, 15, 20],
        '镁': [5, 8, 12],
        '硅': [20, 25, 30]
    }).set_index(pd.date_range('2024-01-01', periods=3, freq='h'))
    oxide_coeffs = {'钙': 2.497, '镁': 1.658, '硅': 2.139}
    result = calculate_crustal(data=test_data, oxide_coeff_dict=oxide_coeffs)
    print(f"Status: {result['status']}")
    print(f"Visuals count: {len(result.get('visuals', []))}")
    if result.get('visuals'):
        first = result['visuals'][0]
        print(f"First visual type: {first.get('type')}")
        print(f"First visual has payload: {'payload' in first}")
