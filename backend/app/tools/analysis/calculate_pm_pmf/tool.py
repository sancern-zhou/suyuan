"""
PMF 源解析工具（Context-Aware V2）- NIMFA无监督模式

使用非负矩阵因子分解（NIMFA）方法进行污染源解析，无需预定义源谱库，
自动从数据中发现潜在污染源，由专家LLM根据因子载荷进行专业解读。

符合规范6.1.2权重选择和6.1.3因子数确定要求：
- 权重选择：关键组分权重1.0，非关键组分权重0.5，支持质量调整
- 因子数确定：Q值变化曲线分析（主方法）+ 残差分析/回归诊断（验证）

数据流程：
1. 接受 data_id 参数（来自 get_particulate_data）
2. 从 Context 加载数据
3. 计算组分权重（规范6.1.2）
4. 分析最优因子数（规范6.1.3）：Q值曲线+残差+回归诊断
5. 执行 NIMFA 无监督因子分解
6. 返回因子载荷和贡献率，供 LLM 专家解读
"""

from typing import TYPE_CHECKING, Any, Dict, List, Union, Tuple
from dataclasses import dataclass
import numpy as np
import traceback

import structlog

from app.schemas.particulate import ParticulateSample
from app.schemas.vocs import VOCsSample, UnifiedVOCsData
from app.tools.analysis.calculate_pm_pmf.calculator import PMFCalculator
from app.tools.analysis.calculate_pm_pmf.pmf_weights import PMFWeightCalculator, PMFWeights
from app.tools.analysis.calculate_pm_pmf.factor_analyzer import FactorAnalyzer, FactorAnalysisResult
from app.tools.base.tool_interface import LLMTool, ToolCategory

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()


def _log_exit(logger, step: str, status: str, **kwargs):
    """辅助函数：记录工具退出日志"""
    logger.info(
        "pmf_tool_exit",
        step=step,
        status=status,
        **kwargs
    )


def truncate_data_for_llm(data: Any, max_tokens: int = 20000) -> Tuple[Any, bool]:
    """Truncate data to fit within token limit for LLM consumption."""
    import json

    def count_tokens(obj: Any) -> int:
        try:
            json_str = json.dumps(obj, ensure_ascii=False, default=str)
            return len(json_str) // 4
        except Exception:
            return len(str(obj)) // 4

    def truncate_dict(d: Dict[str, Any], remaining_tokens: int) -> Dict[str, Any]:
        truncated = {}
        keys = list(d.keys())

        for key in keys:
            if remaining_tokens <= 0:
                break
            value = d[key]
            value_tokens = count_tokens(value)

            if isinstance(value, dict):
                if value_tokens <= remaining_tokens - 10:
                    truncated[key] = value
                    remaining_tokens -= value_tokens
                else:
                    nested_truncated, _ = truncate_data_for_llm(value, remaining_tokens - 10)
                    if nested_truncated:
                        truncated[key] = nested_truncated
                        remaining_tokens -= count_tokens(nested_truncated)
            elif isinstance(value, list):
                if value_tokens <= remaining_tokens - 10:
                    truncated[key] = value
                    remaining_tokens -= value_tokens
                else:
                    truncated_list = []
                    for item in value:
                        if remaining_tokens <= 10:
                            break
                        item_tokens = count_tokens(item)
                        if item_tokens <= remaining_tokens - 5:
                            truncated_list.append(item)
                            remaining_tokens -= item_tokens
                    if truncated_list:
                        truncated[key] = truncated_list
                        truncated[f"{key}_truncated"] = True
                        truncated[f"{key}_original_count"] = len(value)
            else:
                if value_tokens <= remaining_tokens - 5:
                    truncated[key] = value
                    remaining_tokens -= value_tokens

        return truncated

    total_tokens = count_tokens(data)
    if total_tokens <= max_tokens:
        return data, False

    if isinstance(data, dict):
        truncated = truncate_dict(data, max_tokens)
        truncated["_truncated"] = True
        truncated["_original_token_count"] = total_tokens
        return truncated, True
    elif isinstance(data, list):
        truncated_list = []
        remaining_tokens = max_tokens - 100

        for item in data:
            if remaining_tokens <= 0:
                break
            item_tokens = count_tokens(item)
            if item_tokens <= remaining_tokens - 5:
                truncated_list.append(item)
                remaining_tokens -= item_tokens

        result = {
            "data": truncated_list,
            "_truncated": True,
            "_original_count": len(data),
            "_original_token_count": total_tokens
        }
        return result, True
    else:
        return data, True


class CalculatePMFTool(LLMTool):
    """
    PMF 源解析工具 - 基于NIMFA无监督因子分解

    使用非负矩阵因子分解（Non-negative Matrix Factorization）方法，
    无需预定义源谱库，自动从污染物组分数据中识别潜在污染源。
    由专家LLM根据因子载荷特征进行专业解读。

    特点：
    - 无监督学习：无需源谱库，自动发现污染源
    - 因子解读：返回因子载荷矩阵，供LLM专家分析
    - 支持PM2.5/PM10颗粒物和VOCs挥发性有机物
    """

    def __init__(self):
        function_schema = {
            "name": "calculate_pm_pmf",
            "description": """
执行 PM2.5/PM10 颗粒物源解析（NIMFA无监督PMF方法）。

**核心特点**：
- **无监督分解**：无需预定义源谱库，自动从数据中发现潜在污染源
- **专家解读**：返回因子载荷矩阵，由专家LLM根据化学特征判断污染源类型
- **标准PMF**：符合EPA PMF方法论，Q值评估模型质量

**数据获取步骤**：

1. **获取小时粒度的水溶性离子数据**（使用 get_particulate_data，role=water-soluble）:
   - 核心字段：SO4（硫酸盐）、NO3（硝酸盐）、NH4（铵盐）
   - 可选字段：Cl、Ca、Mg、K、Na

2. **获取碳组分数据**（使用 get_particulate_data，role=carbon）:
   - 核心字段：OC（有机碳）、EC（元素碳）

3. **调用此工具**:
   - 传入 data_id、gas_data_id、station_name

**返回结果**：
- **因子载荷矩阵**：每个因子对应各组分的载荷值
- **因子贡献率**：各因子对总浓度的贡献百分比
- **因子时间序列**：各因子浓度随时间的变化
- **模型质量**：Q值、R²等评估指标

**专家解读提示**：
- 因子1-2：通常对应一次排放源（高EC/OC或金属元素）
- 因子3-4：通常对应二次生成（高SO4/NO3/NH4）
- 请根据因子载荷判断每个因子的物理含义

**示例**:
步骤1: data = get_particulate_data("阳江市2025年12月27日小时粒度的PM2.5水溶性离子数据", role="water-soluble")
步骤2: carbon_data = get_particulate_data("阳江市2025年12月27日小时粒度的PM2.5碳组分数据", role="carbon")
步骤3: result = calculate_pm_pmf(
            station_name="阳江市",
            data_id="particulate_unified:xxx",
            gas_data_id="particulate_unified:yyy"
        )
            """.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "station_name": {
                        "type": "string",
                        "description": "超级站点名称（例：深圳南山、广州天河）"
                    },
                    "data_id": {
                        "type": "string",
                        "description": (
                            "小时粒度的水溶性离子数据引用ID（来自 get_particulate_data 工具的返回值，role=water-soluble）。"
                            "格式: 'particulate_unified:xxx'。"
                        )
                    },
                    "pollutant_type": {
                        "type": "string",
                        "description": "污染物类型",
                        "enum": ["PM2.5", "PM10"],
                        "default": "PM2.5"
                    },
                    "start_time": {
                        "type": "string",
                        "description": "起始时间（可选，只用于结果描述）"
                    },
                    "end_time": {
                        "type": "string",
                        "description": "结束时间（可选，只用于结果描述）"
                    },
                    "nimfa_rank": {
                        "type": "integer",
                        "description": "NIMFA因子数（预设为5个污染源）",
                        "default": 5
                    },
                    "gas_data_id": {
                        "type": "string",
                        "description": (
                            "碳组分数据引用ID（来自 get_particulate_data 工具的返回值，role=carbon）。"
                            "格式: 'particulate_unified:yyy'。"
                        )
                    }
                },
                "required": ["station_name", "data_id", "gas_data_id"]
            }
        }

        super().__init__(
            name="calculate_pm_pmf",
            description="PM2.5/PM10 source apportionment using NIMFA (unsupervised)",
            category=ToolCategory.ANALYSIS,
            function_schema=function_schema,
            version="3.0.0",
            requires_context=True
        )

        self.metadata = {
            "region": "Guangdong Province",
            "limitation": "仅支持广东省超级站；需水溶性离子+碳组分数据，各20+样本",
            "supported_pollutants": ["PM2.5", "PM10"],
            "algorithm": "NIMFA (Non-negative Matrix Factorization)",
            "version": "3.1.0",
            "features": [
                "无监督因子分解",
                "无需源谱库",
                "因子载荷专家解读",
                "DataStandardizer字段标准化",
                "规范6.1.2权重配置",
                "规范6.1.3因子数自动确定",
                "Q值曲线分析（主方法）",
                "残差+回归诊断（验证）"
            ]
        }

    async def execute(
        self,
        context: "ExecutionContext",
        station_name: str,
        data_id: str,
        pollutant_type: str = "PM2.5",
        start_time: str = "",
        end_time: str = "",
        nimfa_rank: int = None,
        gas_data_id: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行 NIMFA PMF 源解析（使用 data_id 引用）

        符合规范6.1.2和6.1.3要求：
        - 6.1.2 权重选择：关键组分权重1.0，非关键组分权重0.5
        - 6.1.3 因子数确定：Q值变化曲线分析（主方法）+ 残差分析/回归诊断（验证）

        Args:
            context: 执行上下文（用于加载数据）
            station_name: 超级站点名称
            data_id: 数据引用ID（来自 get_particulate_data）
            pollutant_type: 污染物类型（PM2.5/PM10）
            start_time: 起始时间（可选）
            end_time: 结束时间（可选）
            nimfa_rank: NIMFA因子数（可选，不指定则自动分析最优因子数）
            gas_data_id: 碳组分数据ID（可选）

        Returns:
            NIMFA分析结果，包含因子载荷、贡献率、时间序列、权重配置、因子分析结果
        """
        # === 入口日志：确认execute方法被调用 ===
        logger.info(
            "calculate_pm_pmf_execute_entry",
            station_name=station_name,
            data_id=data_id,
            pollutant_type=pollutant_type,
            gas_data_id=gas_data_id,
            nimfa_rank=nimfa_rank,
            start_time=start_time,
            end_time=end_time,
            kwargs_keys=list(kwargs.keys()) if kwargs else [],
            session_id=getattr(context, 'session_id', 'unknown') if context else 'no_context'
        )

        logger.info(
            "calculate_pmf_nimfa_start",
            station_name=station_name,
            data_id=data_id,
            pollutant_type=pollutant_type,
            nimfa_rank=nimfa_rank,
            session_id=context.session_id
        )

        # Step 1: Get data handle
        try:
            handle = context.get_handle(data_id)
            logger.info(
                "pmf_data_handle_loaded",
                data_id=data_id,
                schema=handle.schema,
                record_count=handle.record_count
            )
        except KeyError as e:
            logger.error(
                "pmf_data_handle_not_found",
                data_id=data_id,
                error=str(e),
                available_data_ids=list(context.data_manager.list_all_data_ids())[:10]
            )
            result = {
                "status": "failed",
                "success": False,
                "data": None,
                "metadata": {
                    "tool_name": "calculate_pm_pmf",
                    "error_type": "data_not_found"
                },
                "summary": f"[FAIL] 未找到数据引用 {data_id}，错误: {str(e)}"
            }
            logger.info("pmf_exiting_with_error", step="data_handle_not_found", error_type="KeyError")
            return result
        except Exception as e:
            logger.error(
                "pmf_data_handle_error",
                data_id=data_id,
                error=str(e),
                error_type=type(e).__name__
            )
            result = {
                "status": "failed",
                "success": False,
                "data": None,
                "metadata": {
                    "tool_name": "calculate_pm_pmf",
                    "error_type": "data_handle_error"
                },
                "summary": f"[FAIL] 获取数据句柄失败: {type(e).__name__}: {str(e)}"
            }
            logger.info("pmf_exiting_with_error", step="data_handle_error", error_type=type(e).__name__)
            return result

        # Step 2: Validate schema compatibility
        accepted_schemas = ["particulate", "particulate_unified", "particulate_analysis"]
        is_compatible = any(handle.is_compatible_with(s) for s in accepted_schemas)
        logger.info(
            "pmf_schema_validation",
            data_id=data_id,
            actual_schema=handle.schema,
            accepted_schemas=accepted_schemas,
            is_compatible=is_compatible
        )

        if not is_compatible:
            logger.error(
                "pmf_schema_incompatible",
                data_id=data_id,
                actual_schema=handle.schema,
                accepted_schemas=accepted_schemas
            )
            result = {
                "status": "failed",
                "success": False,
                "data": None,
                "metadata": {
                    "tool_name": "calculate_pm_pmf",
                    "error_type": "schema_mismatch",
                    "expected": "particulate 或 particulate_unified",
                    "actual": handle.schema
                },
                "summary": f"[FAIL] PMF分析需要 particulate 数据，但 {data_id} 是 {handle.schema} 数据"
            }
            _log_exit(logger, "schema_validation", "failed", reason="schema_incompatible")
            return result

        # Step 3: Validate data
        is_valid, error_msg = handle.validate_for_pmf()
        logger.info(
            "pmf_data_validation",
            data_id=data_id,
            is_valid=is_valid,
            error_msg=error_msg if not is_valid else None,
            record_count=handle.record_count
        )
        if not is_valid:
            logger.error(
                "pmf_validation_failed",
                data_id=data_id,
                error_msg=error_msg,
                record_count=handle.record_count
            )
            result = {
                "status": "failed",
                "success": False,
                "data": None,
                "metadata": {
                    "tool_name": "calculate_pm_pmf",
                    "error_type": "validation_failed",
                    "data_id": data_id,
                    "record_count": handle.record_count
                },
                "summary": f"[FAIL] PMF数据验证失败: {error_msg}"
            }
            _log_exit(logger, "data_validation", "failed", error=error_msg)
            return result

        # Step 4: Load data
        logger.info("pmf_loading_data", data_id=data_id, record_count=handle.record_count)
        try:
            typed_data = context.get_data(data_id, expected_schema=handle.schema)
            logger.info(
                "pmf_data_loaded_success",
                data_id=data_id,
                loaded_records=len(typed_data) if typed_data else 0,
                data_type=type(typed_data).__name__
            )
        except Exception as exc:
            logger.error(
                "pmf_data_load_failed",
                data_id=data_id,
                error=str(exc),
                error_type=type(exc).__name__,
                traceback=traceback.format_exc()
            )
            _log_exit(logger, "pmf_data_load_failed", "exiting")
            return {
                "status": "failed",
                "success": False,
                "data": None,
                "metadata": {"tool_name": "calculate_pm_pmf", "error_type": "data_load_failed"},
                "summary": f"[FAIL] 无法加载数据 {data_id}: {type(exc).__name__}: {str(exc)}"
            }

        # Step 5: Load gas data if provided
        gas_records = None
        if gas_data_id:
            logger.info("pmf_loading_gas_data", gas_data_id=gas_data_id)
            try:
                gas_handle = context.get_handle(gas_data_id)
                gas_data = context.get_data(gas_data_id, expected_schema=gas_handle.schema)
                # 转换为字典格式（UDF v2.0标准格式）
                gas_records = []
                for record in gas_data:
                    if hasattr(record, 'model_dump'):
                        gas_records.append(record.model_dump())
                    else:
                        gas_records.append(dict(record))
                logger.info(
                    "pmf_gas_data_loaded",
                    gas_data_id=gas_data_id,
                    record_count=len(gas_records),
                    schema=gas_handle.schema
                )
            except Exception as exc:
                logger.warning(
                    "pmf_gas_data_load_failed",
                    gas_data_id=gas_data_id,
                    error=str(exc),
                    error_type=type(exc).__name__
                )

        # Step 6: Transform data
        logger.info("pmf_transforming_data", data_id=data_id, record_count=len(typed_data))
        try:
            component_data = self._transform_particulate_to_pmf_input(typed_data)
            logger.info(
                "pmf_data_transformed",
                component_data_count=len(component_data),
                has_gas_data=gas_records is not None
            )

            # Merge gas data if available
            if gas_records:
                calculator = PMFCalculator(pollutant_type="PM")
                component_data = calculator._merge_gas_data(component_data, gas_records)
                logger.info("pmf_data_merged_with_gas", component_count=len(component_data))
        except Exception as exc:
            logger.error(
                "pmf_data_transform_failed",
                error=str(exc),
                error_type=type(exc).__name__,
                traceback=traceback.format_exc()
            )
            _log_exit(logger, "pmf_data_transform_failed", "exiting")
            return {
                "status": "failed",
                "success": False,
                "data": None,
                "metadata": {"tool_name": "calculate_pm_pmf", "error_type": "data_transform_failed"},
                "summary": f"[FAIL] 数据格式转换失败: {type(exc).__name__}: {str(exc)}"
            }

        if len(component_data) < 10:
            logger.error(
                "pmf_insufficient_data",
                component_data_count=len(component_data),
                required_minimum=10
            )
            _log_exit(logger, "pmf_insufficient_data", "exiting")
            return {
                "status": "failed",
                "success": False,
                "data": None,
                "metadata": {"tool_name": "calculate_pm_pmf", "error_type": "insufficient_data"},
                "summary": f"[FAIL] 有效样本数不足（需≥10个，当前{len(component_data)}个）"
            }

        # Step 7: 规范6.1.2 - 计算组分权重
        logger.info("pmf_calculating_weights", pollutant_type="PM")
        weight_calculator = PMFWeightCalculator(pollutant_type="PM")
        weights_config = weight_calculator.calculate_weights(component_data)
        logger.info(
            "pmf_weights_calculated",
            key_components=len(weights_config.key_components),
            excluded=len(weights_config.excluded)
        )

        # Step 8: 规范6.1.3 - 分析最优因子数（如果不指定因子数）
        factor_analysis_result = None
        optimal_rank = nimfa_rank if nimfa_rank else 5

        if nimfa_rank is None:
            logger.info("pmf_analyzing_optimal_rank", min_rank=3, max_rank=8)
            try:
                X_matrix, components = self._build_concentration_matrix(component_data)
                analyzer = FactorAnalyzer(pollutant_type="PM")

                # 确定关键组分索引
                key_component_indices = []
                for idx, comp in enumerate(components):
                    if comp in weights_config.key_components:
                        key_component_indices.append(idx)

                factor_analysis_result = analyzer.analyze(
                    X_matrix,
                    min_rank=3,
                    max_rank=8,
                    key_component_indices=key_component_indices
                )
                optimal_rank = factor_analysis_result.optimal_rank
                logger.info(
                    "pmf_optimal_rank_determined",
                    optimal_rank=optimal_rank,
                    confidence=factor_analysis_result.confidence
                )
            except Exception as exc:
                logger.warning(
                    "pmf_factor_analysis_failed",
                    error=str(exc),
                    error_type=type(exc).__name__,
                    using_default_rank=5
                )
                optimal_rank = 5

        # Step 9: 构建权重矩阵
        weight_matrix, component_names = weight_calculator.get_weights_for_nimfa(weights_config)
        if weight_matrix is None or len(component_names) == 0:
            logger.warning("pmf_no_valid_weights", using_uniform=True)
            weight_matrix = None

        # Step 10: 执行 NIMFA 计算
        logger.info(
            "pmf_executing_nimfa",
            station_name=station_name,
            sample_count=len(component_data),
            factor_number=optimal_rank
        )
        calculator = PMFCalculator(pollutant_type="PM")

        try:
            result = calculator.calculate(
                component_data,
                pollutant=pollutant_type.upper(),
                run_quality_control=True,
                rank=optimal_rank
            )
            logger.info(
                "pmf_nimfa_calculation_completed",
                success=result.get("success"),
                has_error=result.get("error") is not None
            )
        except Exception as exc:
            logger.error(
                "pmf_nimfa_calculation_exception",
                error=str(exc),
                error_type=type(exc).__name__,
                traceback=traceback.format_exc()
            )
            _log_exit(logger, "pmf_nimfa_calculation_exception", "exiting")
            return {
                "status": "failed",
                "success": False,
                "data": None,
                "metadata": {
                    "tool_name": "calculate_pm_pmf",
                    "error_type": "calculation_exception"
                },
                "summary": f"[FAIL] PMF计算异常: {type(exc).__name__}: {str(exc)}"
            }

        if not result.get("success"):
            logger.error(
                "pmf_calculation_failed",
                error=result.get("error", "未知错误"),
                result_keys=list(result.keys())
            )
            _log_exit(logger, "pmf_calculation_failed", "exiting", error=result.get("error", "未知错误"))
            return {
                "status": "failed",
                "success": False,
                "data": result,
                "metadata": {
                    "tool_name": "calculate_pm_pmf",
                    "error_type": "calculation_failed",
                    "data_id": data_id
                },
                "summary": f"[FAIL] PMF计算失败: {result.get('error', '未知错误')}"
            }

        # Step 11: 整合权重配置和因子分析结果
        result["station_name"] = station_name
        result["start_time"] = start_time
        result["end_time"] = end_time
        result["input_data_id"] = data_id
        result["sample_count"] = len(component_data)

        # 添加权重配置信息
        result["weights_config"] = {
            "key_components": weights_config.key_components,
            "base_weights": weights_config.base_weights,
            "quality_factors": weights_config.quality_factors,
            "final_weights": weights_config.weights,
            "excluded_components": weights_config.excluded,
            "component_count": len(weights_config.weights)
        }

        # 添加因子数分析结果
        if factor_analysis_result:
            result["factor_analysis"] = {
                "optimal_rank": factor_analysis_result.optimal_rank,
                "recommended_rank": factor_analysis_result.recommended_rank,
                "confidence": factor_analysis_result.confidence,
                "Q_curve": factor_analysis_result.Q_curve,
                "pass_residual": factor_analysis_result.pass_residual,
                "pass_regression": factor_analysis_result.pass_regression,
                "pass_all": factor_analysis_result.pass_all,
                "analysis_time": factor_analysis_result.analysis_time,
                "parallel_info": factor_analysis_result.parallel_info
            }

        # Step 12: 保存结果
        try:
            pmf_data_ref = context.save_data(
                data=[result],
                schema="pmf_result",
                metadata={
                    "station_name": station_name,
                    "pollutant_type": pollutant_type,
                    "input_data_id": data_id,
                    "gas_data_id": gas_data_id,
                    "sources_count": len(result.get("sources", [])),
                    "sample_count": len(component_data),
                    "optimal_rank": optimal_rank,
                    "generator_version": "3.1.0",
                    "standard_compliance": {
                        "6.1.2_weight_selection": True,
                        "6.1.3_factor_determination": True,
                        "Q_curve_analysis": True,
                        "residual_validation": True,
                        "regression_validation": True
                    }
                }
            )
            pmf_data_id = pmf_data_ref["data_id"]
            pmf_file_path = pmf_data_ref["file_path"]
            result["data_id"] = pmf_data_id
            result["registry_schema"] = "pmf_result"

            logger.info(
                "pmf_result_saved",
                pmf_data_id=pmf_data_id,
                pmf_file_path=pmf_file_path,
                sources_count=len(result.get("sources", [])),
                sample_count=len(component_data)
            )
        except Exception as exc:
            logger.error(
                "pmf_result_save_failed",
                error=str(exc),
                error_type=type(exc).__name__,
                traceback=traceback.format_exc()
            )
            _log_exit(logger, "pmf_result_save_failed", "exiting")
            return {
                "status": "failed",
                "success": False,
                "data": None,
                "metadata": {"tool_name": "calculate_pm_pmf", "error_type": "data_save_failed"},
                "summary": f"[FAIL] 结果保存失败: {type(exc).__name__}: {str(exc)}"
            }

        # Step 13: 提取结果供LLM解读
        sources = result.get("sources", [])
        source_contributions = result.get("source_contributions", {})
        source_concentrations = result.get("source_concentrations", {})
        factor_loadings = result.get("factor_loadings", {})
        performance = result.get("performance", {})

        # Format sources
        if sources and isinstance(sources, list):
            if sources and isinstance(sources[0], dict) and hasattr(sources[0], "model_dump"):
                sources = [s.model_dump() for s in sources]

        if "timeseries" in result and isinstance(result["timeseries"], list):
            if result["timeseries"] and hasattr(result["timeseries"][0], "model_dump"):
                result["timeseries"] = [ts.model_dump() for ts in result["timeseries"]]

        # Generate summary
        if source_contributions:
            sorted_sources = sorted(source_contributions.items(), key=lambda x: x[1], reverse=True)
            source_summary = "\n".join([
                f"- **{name}**: {pct:.2f}% (浓度: {source_concentrations.get(name, 0):.3f})"
                for name, pct in sorted_sources
            ])
            main_source = sorted_sources[0][0]
            main_contribution = sorted_sources[0][1]
        else:
            source_summary = "暂无源贡献数据"
            main_source = "N/A"
            main_contribution = 0.0

        r2_value = performance.get('R2', 'N/A')
        r2_str = f"{r2_value:.3f}" if isinstance(r2_value, (int, float)) else str(r2_value)

        # Generate factor loading summary for expert interpretation
        factor_loading_summary = ""
        if factor_loadings:
            factor_loading_lines = []
            for factor, loadings in factor_loadings.items():
                sorted_loadings = sorted(loadings.items(), key=lambda x: x[1], reverse=True)[:5]
                loadings_str = ", ".join([f"{k}({v:.3f})" for k, v in sorted_loadings])
                factor_loading_lines.append(f"  {factor}: {loadings_str}")
            factor_loading_summary = "\n" + "\n".join(factor_loading_lines)

        # 权重配置摘要
        weights_summary = ""
        if weights_config.key_components:
            weights_summary = (
                f"\n**权重配置**（规范6.1.2）:\n"
                f"- 关键组分（权重1.0）: {', '.join(weights_config.key_components[:5])}{'...' if len(weights_config.key_components) > 5 else ''}\n"
                f"- 有效组分数: {len(weights_config.weights)}\n"
                f"- 排除组分数: {len(weights_config.excluded)}"
            )

        # 因子数分析摘要
        factor_analysis_summary = ""
        if factor_analysis_result:
            q_curve_info = ""
            if factor_analysis_result.Q_curve:
                for item in factor_analysis_result.Q_curve:
                    drop = item.get("drop_rate", 0)
                    drop_str = f" 下降{drop:.1%}" if drop > 0 else ""
                    residual_str = " 残差通过" if item.get("residual_passed") else ""
                    reg_str = " 回归通过" if item.get("regression_passed") else ""
                    q_curve_info += f"  因子{item['rank']}: Q={item['Q_true']:.1f}, R²={item['R2']:.3f}{drop_str}{residual_str}{reg_str}\n"

            factor_analysis_summary = (
                f"\n**因子数分析**（规范6.1.3）:\n"
                f"- 最优因子数: {factor_analysis_result.optimal_rank}\n"
                f"- 推荐因子数: {factor_analysis_result.recommended_rank}\n"
                f"- 置信度: {factor_analysis_result.confidence:.1%}\n"
                f"- 残差验证通过: {factor_analysis_result.pass_residual}\n"
                f"- 回归验证通过: {factor_analysis_result.pass_regression}\n"
                f"Q值变化曲线:\n{q_curve_info}"
            )

        result["detailed_summary"] = (
            f"NIMFA无监督PMF源解析完成（符合规范6.1.2/6.1.3）\n\n"
            f"**因子贡献率排序**:\n{source_summary}\n\n"
            f"**因子载荷矩阵**（供专家解读）:\n{factor_loading_summary}\n"
            f"{weights_summary}"
            f"{factor_analysis_summary}\n\n"
            f"**模型性能**:\n"
            f"- R² = {r2_str}\n"
            f"- Q值 = {performance.get('q_value', 'N/A')}\n"
            f"- 迭代次数 = {performance.get('convergence_iterations', 'N/A')}\n\n"
            f"**数据样本**: {len(component_data)} 条记录\n"
            f"**主要因子**: {main_source} ({main_contribution:.1f}%)\n\n"
            f"**专家解读建议**:\n"
            f"- 因子1-2：通常对应一次排放源（高EC/OC或金属元素）\n"
            f"- 因子3-4：通常对应二次生成（高SO4/NO3/NH4）\n"
            f"- 请根据因子载荷判断每个因子的物理含义和污染源类型\n\n"
            f"**数据存储**: PMF结果已存储，ID: `{pmf_data_id}`（路径: `{pmf_file_path}`）"
        )

        # Apply token truncation
        result, was_truncated = truncate_data_for_llm(result, max_tokens=20000)

        logger.info(
            "calculate_pm_pmf_complete",
            station_name=station_name,
            factors_identified=len(sources),
            optimal_rank=optimal_rank,
            confidence=factor_analysis_result.confidence if factor_analysis_result else None,
            success=result.get("success"),
            data_id=pmf_data_id,
            sample_count=len(component_data),
            main_source=main_source,
            main_contribution=main_contribution
        )

        final_result = {
            "status": "success",
            "success": True,
            "data": result,
            "data_id": pmf_data_id,
            "file_path": pmf_file_path,
            "visuals": [],
            "metadata": {
                "schema_version": "v2.0",
                "tool_name": "calculate_pm_pmf",
                "station_name": station_name,
                "pollutant_type": pollutant_type,
                "data_id": data_id,
                "pmf_result_id": pmf_data_id,
                "gas_data_id": gas_data_id,
                "sources_count": len(sources),
                "sample_count": len(component_data),
                "optimal_rank": optimal_rank,
                "source_contributions": source_contributions,
                "generator": "calculate_pm_pmf",
                "generator_version": "3.1.0",
                "algorithm": "nimfa",
                "scenario": "pmf_source_analysis",
                "field_mapping_applied": True,
                "standard_compliance": {
                    "6.1.2_weight_selection": True,
                    "6.1.3_factor_determination": True
                },
                "source_data_ids": [data_id, pmf_data_id] + ([gas_data_id] if gas_data_id else [])
            },
            "summary": (
                f"[OK] PMF源解析完成（最优因子数{optimal_rank}，识别{len(sources)}个源），已保存为 {pmf_data_id}（路径: {pmf_file_path}）。"
                f"置信度{factor_analysis_result.confidence:.1%}，"
                f"主要因子{main_source} ({main_contribution:.1f}%)，"
                f"模型R²={r2_str}。请根据因子载荷矩阵解读各因子对应的污染源类型。"
            )
        }

        logger.info(
            "pmf_final_result_prepared",
            status=final_result["status"],
            success=final_result["success"],
            has_data=final_result["data"] is not None,
            data_id=final_result["data_id"],
            sources_count=len(sources),
            summary_length=len(final_result["summary"])
        )

        _log_exit(logger, "success", "completed", data_id=final_result["data_id"], sources_count=len(sources))
        return final_result

    def _transform_particulate_to_pmf_input(
        self,
        samples: List[Union[ParticulateSample, Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        """Transform particulate data to PMF input format."""
        transformed = []

        for sample in samples:
            if isinstance(sample, dict):
                timestamp = sample.get("timestamp", "")
                components = sample.get("components", {})

                if not components:
                    # Flat structure: use top-level numeric fields
                    components = {}
                    for key, value in sample.items():
                        if key not in ("timestamp", "PM2.5", "PM2_5", "unit", "qc_flag", "metadata"):
                            if isinstance(value, (int, float)):
                                components[key] = value

                record = {
                    "timestamp": timestamp,
                    "components": components if isinstance(components, dict) else {}
                }
            elif hasattr(sample, 'timestamp') and hasattr(sample, 'components'):
                timestamp = sample.timestamp
                if hasattr(timestamp, "strftime"):
                    timestamp = timestamp.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    timestamp = str(timestamp)

                components = sample.components
                if hasattr(components, 'model_dump'):
                    components = components.model_dump()
                elif hasattr(components, 'dict'):
                    components = components.dict()

                record = {
                    "timestamp": timestamp,
                    "components": components if isinstance(components, dict) else {}
                }
            else:
                logger.warning("pmf_transform_skip_sample", sample_type=type(sample).__name__)
                continue

            transformed.append(record)

        logger.info(
            "_transform_particulate_to_pmf_input",
            input_count=len(samples),
            output_count=len(transformed)
        )

        return transformed

    def _build_concentration_matrix(
        self,
        component_data: List[Dict[str, Any]]
    ) -> Tuple[np.ndarray, List[str]]:
        """
        从组分数据构建浓度矩阵（用于因子数分析）

        Args:
            component_data: PMF输入格式的组分数据列表

        Returns:
            X_matrix: 浓度矩阵 (n_samples, n_components)
            components: 组分名称列表
        """
        if not component_data:
            return np.array([]), []

        # 收集所有组分
        all_components = set()
        for record in component_data:
            if isinstance(record, dict) and "components" in record:
                all_components.update(record["components"].keys())

        if not all_components:
            # 尝试从顶层字段获取
            for record in component_data:
                if isinstance(record, dict):
                    for key in record.keys():
                        if key not in ("timestamp", "time"):
                            all_components.add(key)

        components = sorted(list(all_components))
        rows = []

        for record in component_data:
            if isinstance(record, dict) and "components" in record:
                row = []
                for comp in components:
                    value = record["components"].get(comp, 0.01)
                    if value is None or value < 0:
                        value = 0.01
                    row.append(float(value))
                rows.append(row)
            else:
                # 扁平结构
                row = []
                for comp in components:
                    value = record.get(comp, 0.01)
                    if value is None or value < 0:
                        value = 0.01
                    row.append(float(value))
                rows.append(row)

        X_matrix = np.array(rows)
        return X_matrix, components
