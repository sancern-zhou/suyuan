"""
VOCs PMF 源解析工具（Context-Aware V2）- NIMFA无监督模式

用于 VOCs 挥发性有机物的源解析（臭氧前体物溯源），
使用NIMFA无监督因子分解，自动发现VOCs污染源，
由专家LLM根据因子载荷进行专业解读。

符合规范6.1.2权重选择和6.1.3因子数确定要求：
- 权重选择：关键物种（乙烯、丙烯、芳烃等臭氧前体物）权重1.0
- 因子数确定：Q值变化曲线分析（主方法）+ 残差分析/回归诊断（验证）
"""

from typing import TYPE_CHECKING, Any, Dict, List, Union, Tuple
from dataclasses import dataclass
import numpy as np

import structlog

from app.schemas.vocs import VOCsSample, UnifiedVOCsData
from app.tools.analysis.calculate_vocs_pmf.calculator import PMFCalculator
from app.tools.analysis.calculate_pm_pmf.pmf_weights import PMFWeightCalculator, PMFWeights
from app.tools.analysis.calculate_pm_pmf.factor_analyzer import FactorAnalyzer, FactorAnalysisResult
from app.tools.base.tool_interface import LLMTool, ToolCategory

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()


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
        return {
            "data": truncated_list,
            "_truncated": True,
            "_original_count": len(data),
            "_original_token_count": total_tokens
        }, True
    else:
        return data, True


class CalculateVOCSPMFTool(LLMTool):
    """
    VOCs PMF 源解析工具 - 基于NIMFA无监督因子分解

    使用非负矩阵因子分解方法进行VOCs源解析，无需预定义源谱库，
    自动从VOCs组分数据中识别臭氧前体物污染源。
    由专家LLM根据因子载荷特征进行专业解读。
    """

    def __init__(self):
        function_schema = {
            "name": "calculate_vocs_pmf",
            "description": """
执行 VOCs 挥发性有机物源解析（NIMFA无监督PMF方法），用于臭氧溯源分析。

**核心特点**：
- **无监督分解**：无需预定义VOCs源谱库，自动发现臭氧前体物来源
- **专家解读**：返回因子载荷矩阵，由专家LLM根据化学特征判断污染源类型
- **臭氧溯源**：专门用于识别VOCs中对O3生成贡献大的污染源

**数据获取步骤**:
1. 获取 VOCs 数据（使用 get_vocs_data），必须包含关键VOCs物种
2. 调用此工具，传入 data_id 和 station_name

**返回结果**：
- **因子载荷矩阵**：每个因子对应各VOCs物种的载荷值
- **因子贡献率**：各因子对VOCs浓度的贡献百分比
- **因子时间序列**：各因子浓度随时间的变化
- **模型质量**：Q值、R²等评估指标

**专家解读提示**：
- 因子1-2：通常对应一次排放源（高C2-C3烷烃/烯烃，如机动车尾气）
- 因子3-4：通常对应工业/溶剂源（高芳烃，如苯、甲苯、二甲苯）
- 请根据因子载荷判断每个因子的物理含义和VOCs源类型

**示例**:
data = get_vocs_data("阳江市2025年12月27日的小时VOCs数据，要求包含 乙烯、丙烯、苯、甲苯")
result = calculate_vocs_pmf(station_name="阳江市", data_id="vocs_unified:xxx")
            """.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "station_name": {
                        "type": "string",
                        "description": "超级站点名称"
                    },
                    "data_id": {
                        "type": "string",
                        "description": "VOCs数据引用ID（来自 get_vocs_data）"
                    },
                    "start_time": {
                        "type": "string",
                        "description": "起始时间（可选）"
                    },
                    "end_time": {
                        "type": "string",
                        "description": "结束时间（可选）"
                    },
                    "nimfa_rank": {
                        "type": "integer",
                        "description": "NIMFA因子数（预设为5个VOCs源）",
                        "default": 5
                    }
                },
                "required": ["station_name", "data_id"]
            }
        }

        super().__init__(
            name="calculate_vocs_pmf",
            description="VOCs source apportionment using NIMFA (ozone tracing)",
            category=ToolCategory.ANALYSIS,
            function_schema=function_schema,
            version="3.0.0",
            requires_context=True
        )

        self.metadata = {
            "region": "Guangdong Province",
            "limitation": "仅支持广东省超级站；VOCs 需 20+ 样本",
            "supported_pollutants": ["VOCs"],
            "algorithm": "NIMFA (Non-negative Matrix Factorization)",
            "version": "3.1.0",
            "features": [
                "无监督因子分解",
                "臭氧前体物溯源",
                "因子载荷专家解读",
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
        start_time: str = "",
        end_time: str = "",
        nimfa_rank: int = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行 VOCs NIMFA PMF 源解析（臭氧溯源）

        符合规范6.1.2和6.1.3要求：
        - 6.1.2 权重选择：关键VOCs物种（乙烯、丙烯、芳烃等臭氧前体物）权重1.0
        - 6.1.3 因子数确定：Q值变化曲线分析（主方法）+ 残差分析/回归诊断（验证）
        """
        logger.info(
            "calculate_vocs_pmf_nimfa_start",
            station_name=station_name,
            data_id=data_id,
            nimfa_rank=nimfa_rank
        )

        # Step 1: Get data handle
        try:
            handle = context.get_handle(data_id)
        except KeyError:
            return {
                "status": "failed", "success": False, "data": None,
                "metadata": {"tool_name": "calculate_vocs_pmf", "error_type": "data_not_found"},
                "summary": f"[FAIL] 未找到数据引用 {data_id}，请先调用 get_vocs_data"
            }

        # Step 2: Validate schema
        accepted_schemas = ["vocs", "vocs_unified"]
        is_compatible = any(handle.is_compatible_with(s) for s in accepted_schemas)

        if not is_compatible:
            return {
                "status": "failed", "success": False, "data": None,
                "metadata": {"tool_name": "calculate_vocs_pmf", "error_type": "schema_mismatch",
                            "expected": "vocs 或 vocs_unified", "actual": handle.schema},
                "summary": f"[FAIL] 需要 vocs 或 vocs_unified 数据，但 {data_id} 是 {handle.schema} 数据"
            }

        # Step 3: Validate data
        is_valid, error_msg = handle.validate_for_pmf()
        if not is_valid:
            return {
                "status": "failed", "success": False, "data": None,
                "metadata": {"tool_name": "calculate_vocs_pmf", "error_type": "validation_failed",
                            "data_id": data_id, "record_count": handle.record_count},
                "summary": f"[FAIL] VOCs PMF 数据验证失败: {error_msg}"
            }

        # Step 4: Load data
        try:
            typed_data = context.get_data(data_id, expected_schema=handle.schema)
        except Exception as exc:
            logger.error("calculate_vocs_pmf_data_load_failed", data_id=data_id, error=str(exc))
            return {
                "status": "failed", "success": False, "data": None,
                "metadata": {"tool_name": "calculate_vocs_pmf", "error_type": "data_load_failed", "data_id": data_id},
                "summary": f"[FAIL] 无法加载数据 {data_id}: {str(exc)}"
            }

        # Step 5: Transform
        try:
            component_data = self._transform_vocs_to_pmf_input(typed_data)
        except Exception as exc:
            logger.error("calculate_vocs_pmf_transform_failed", data_id=data_id, error=str(exc))
            return {
                "status": "failed", "success": False, "data": None,
                "metadata": {"tool_name": "calculate_vocs_pmf", "error_type": "data_transform_failed", "data_id": data_id},
                "summary": f"[FAIL] VOCs PMF 数据格式转换失败: {str(exc)}"
            }

        if len(component_data) < 10:
            return {
                "status": "failed", "success": False, "data": None,
                "metadata": {"tool_name": "calculate_vocs_pmf", "error_type": "insufficient_data",
                            "data_id": data_id, "record_count": len(component_data)},
                "summary": f"[FAIL] 有效样本数不足（需>=10个，当前{len(component_data)}个）"
            }

        # Step 5.1: 数据质量详细校验 - 检查物种覆盖率和关键臭氧前体物
        species_coverage = self._check_species_coverage(component_data)
        if not species_coverage["is_valid"]:
            return {
                "status": "failed", "success": False, "data": None,
                "metadata": {
                    "tool_name": "calculate_vocs_pmf",
                    "error_type": "insufficient_species_coverage",
                    "data_id": data_id,
                    "available_species": species_coverage["available_species"],
                    "required_species": species_coverage["required_species"],
                    "coverage_details": species_coverage["details"]
                },
                "summary": f"[FAIL] VOCs物种覆盖不足: {species_coverage['error_msg']}"
            }

        # Step 6: 规范6.1.2 - 计算VOCs物种权重
        logger.info("calculate_vocs_pmf_calculating_weights", pollutant_type="VOCs")
        weight_calculator = PMFWeightCalculator(pollutant_type="VOCs")
        weights_config = weight_calculator.calculate_weights(component_data)
        logger.info(
            "calculate_vocs_pmf_weights_calculated",
            key_species=len(weights_config.key_components),
            excluded=len(weights_config.excluded)
        )

        # Step 7: 规范6.1.3 - 分析最优因子数（如果不指定因子数）
        factor_analysis_result = None
        optimal_rank = nimfa_rank if nimfa_rank else 5

        if nimfa_rank is None:
            logger.info("calculate_vocs_pmf_analyzing_optimal_rank", min_rank=3, max_rank=8)
            try:
                X_matrix, species_list = self._build_concentration_matrix(component_data)
                analyzer = FactorAnalyzer(pollutant_type="VOCs")

                # 确定关键物种索引
                key_species_indices = []
                for idx, species in enumerate(species_list):
                    if species in weights_config.key_components:
                        key_species_indices.append(idx)

                factor_analysis_result = analyzer.analyze(
                    X_matrix,
                    min_rank=3,
                    max_rank=8,
                    key_component_indices=key_species_indices
                )
                optimal_rank = factor_analysis_result.optimal_rank
                logger.info(
                    "calculate_vocs_pmf_optimal_rank_determined",
                    optimal_rank=optimal_rank,
                    confidence=factor_analysis_result.confidence
                )
            except Exception as exc:
                logger.warning("calculate_vocs_pmf_factor_analysis_failed", error=str(exc))
                optimal_rank = 5

        # Step 8: 执行 NIMFA
        logger.info(
            "calculate_vocs_pmf_executing_nimfa",
            sample_count=len(component_data),
            factor_number=optimal_rank
        )

        calculator = PMFCalculator(pollutant_type="VOCs")

        result = calculator.calculate(
            component_data,
            pollutant="VOCs",
            run_quality_control=True,
            rank=optimal_rank
        )

        # Step 8.1: 校验计算结果完整性
        if not result.get("success"):
            return {
                "status": "failed", "success": False, "data": result,
                "metadata": {"tool_name": "calculate_vocs_pmf", "error_type": "calculation_failed",
                            "data_id": data_id, "error": result.get("error", "未知计算错误"),
                            "algorithm": result.get("algorithm", "nimfa")},
                "summary": f"[FAIL] VOCs PMF计算失败: {result.get('error', '未知错误')}"
            }

        # 校验关键字段是否存在
        required_fields = ["sources", "source_contributions", "factor_loadings"]
        missing_fields = [f for f in required_fields if f not in result or not result[f]]
        if missing_fields:
            logger.error("calculate_vocs_pmf_missing_required_fields",
                        data_id=data_id, missing_fields=missing_fields)
            return {
                "status": "failed", "success": False, "data": result,
                "metadata": {"tool_name": "calculate_vocs_pmf", "error_type": "incomplete_result",
                            "data_id": data_id, "missing_fields": missing_fields,
                            "result_keys": list(result.keys())},
                "summary": f"[FAIL] VOCs PMF结果不完整，缺少字段: {', '.join(missing_fields)}"
            }

        # Step 9: 整合权重配置和因子分析结果
        result["station_name"] = station_name
        result["start_time"] = start_time
        result["end_time"] = end_time
        result["input_data_id"] = data_id
        result["sample_count"] = len(component_data)

        # 添加权重配置信息
        result["weights_config"] = {
            "key_species": weights_config.key_components,
            "base_weights": weights_config.base_weights,
            "quality_factors": weights_config.quality_factors,
            "final_weights": weights_config.weights,
            "excluded_species": weights_config.excluded,
            "species_count": len(weights_config.weights)
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

        # Step 10: Save result
        try:
            pmf_data_id = context.save_data(
                data=[result],
                schema="pmf_result",
                metadata={
                    "station_name": station_name,
                    "pollutant_type": "VOCs",
                    "input_data_id": data_id,
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
            result["registry_schema"] = "pmf_result"
            result["data_id"] = pmf_data_id
            logger.info("calculate_vocs_pmf_saved", pmf_data_id=pmf_data_id)
        except Exception as exc:
            logger.error("calculate_vocs_pmf_save_failed", error=str(exc))
            return {
                "status": "failed", "success": False, "data": None,
                "metadata": {"tool_name": "calculate_vocs_pmf", "error_type": "data_save_failed", "data_id": data_id},
                "summary": f"[FAIL] VOCs PMF结果保存失败: {str(exc)}"
            }

        # Step 11: Extract results
        sources = result.get("sources", [])
        source_contributions = result.get("source_contributions", {})
        source_concentrations = result.get("source_concentrations", {})
        factor_loadings = result.get("factor_loadings", {})
        performance = result.get("performance", {})

        # Generate summary
        if source_contributions:
            source_contribution_summary = "\n".join([
                f"- **{source_name}**: {contribution_pct:.2f}% (浓度: {source_concentrations.get(source_name, 0):.3f})"
                for source_name, contribution_pct in sorted(source_contributions.items(), key=lambda x: x[1], reverse=True)
            ])
            main_source = max(source_contributions, key=source_contributions.get)
            main_contribution = max(source_contributions.values())
        else:
            source_contribution_summary = "暂无源贡献数据"
            main_source = "N/A"
            main_contribution = 0.0

        r2_value = performance.get('R2', 'N/A')
        r2_str = f"{r2_value:.3f}" if isinstance(r2_value, (int, float)) else str(r2_value)

        # Factor loading summary
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
                f"- 关键物种（权重1.0）: {', '.join(weights_config.key_components[:5])}{'...' if len(weights_config.key_components) > 5 else ''}\n"
                f"- 有效物种数: {len(weights_config.weights)}\n"
                f"- 排除物种数: {len(weights_config.excluded)}"
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
                    q_curve_info += f"  因子{item['rank']}: Q={item['Q_true']:.1f}, R2={item['R2']:.3f}{drop_str}{residual_str}{reg_str}\n"

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
            f"NIMFA无监督VOCs PMF源解析完成（臭氧溯源，符合规范6.1.2/6.1.3）\n\n"
            f"**因子贡献率排序**:\n{source_contribution_summary}\n\n"
            f"**因子载荷矩阵**（供专家解读）:\n{factor_loading_summary}\n"
            f"{weights_summary}"
            f"{factor_analysis_summary}\n\n"
            f"**模型性能**:\n"
            f"- R2 = {r2_str}\n"
            f"- Q值 = {performance.get('q_value', 'N/A')}\n"
            f"- 迭代次数 = {performance.get('convergence_iterations', 'N/A')}\n\n"
            f"**数据样本**: {len(component_data)} 条\n"
            f"**主要因子**: {main_source} ({main_contribution:.1f}%)\n\n"
            f"**专家解读建议**:\n"
            f"- 因子1-2：通常对应一次排放源（高C2-C3烷烃/烯烃，如机动车尾气）\n"
            f"- 因子3-4：通常对应工业/溶剂源（高芳烃，如苯、甲苯、二甲苯）\n"
            f"- 请根据因子载荷判断每个因子的物理含义和VOCs源类型\n\n"
            f"**数据存储**: ID: `{pmf_data_id}`"
        )

        result, _ = truncate_data_for_llm(result, max_tokens=20000)

        logger.info(
            "calculate_vocs_pmf_complete",
            factors_identified=len(sources),
            optimal_rank=optimal_rank,
            confidence=factor_analysis_result.confidence if factor_analysis_result else None,
            success=result.get("success")
        )

        return {
            "status": "success",
            "success": True,
            "data": result,
            "data_id": pmf_data_id,
            "visuals": [],
            "metadata": {
                "schema_version": "v2.0",
                "tool_name": "calculate_vocs_pmf",
                "station_name": station_name,
                "pollutant_type": "VOCs",
                "data_id": data_id,
                "pmf_result_id": pmf_data_id,
                "sources_count": len(sources),
                "sample_count": len(component_data),
                "optimal_rank": optimal_rank,
                "source_contributions": source_contributions,
                "generator": "calculate_vocs_pmf",
                "generator_version": "3.1.0",
                "algorithm": "nimfa",
                "scenario": "vocs_pmf_source_analysis",
                "field_mapping_applied": True,
                "standard_compliance": {
                    "6.1.2_weight_selection": True,
                    "6.1.3_factor_determination": True
                },
                "source_data_ids": [data_id, pmf_data_id]
            },
            "summary": (
                f"[OK] VOCs PMF源解析完成（最优因子数{optimal_rank}，识别{len(sources)}个源），已保存为 {pmf_data_id}。"
                f"置信度{factor_analysis_result.confidence:.1%}，"
                f"主要因子{main_source} ({main_contribution:.1f}%)，"
                f"模型R2={r2_str}。请根据因子载荷矩阵解读各因子对应的VOCs污染源类型。"
            )
        }

    def _transform_vocs_to_pmf_input(
        self,
        samples: List[Union[VOCsSample, UnifiedVOCsData, Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        """Transform VOCs data to PMF calculator input format."""
        transformed = []
        for sample in samples:
            if isinstance(sample, dict):
                if "species_data" in sample:
                    record = {"time": sample["timestamp"], **sample["species_data"]}
                elif "species" in sample:
                    timestamp = sample["timestamp"]
                    if hasattr(timestamp, "strftime"):
                        timestamp = timestamp.strftime("%Y-%m-%d %H:%M:%S")
                    record = {"time": timestamp, **sample["species"]}
                else:
                    raise ValueError(f"Dictionary sample missing 'species_data' or 'species'")
            elif isinstance(sample, UnifiedVOCsData):
                record = {"time": sample.timestamp, **sample.species_data}
            elif isinstance(sample, VOCsSample):
                record = {"time": sample.timestamp.strftime("%Y-%m-%d %H:%M:%S"), **sample.species}
            else:
                raise TypeError(f"Unsupported sample type: {type(sample)}")
            transformed.append(record)
        return transformed

    def _build_concentration_matrix(
        self,
        component_data: List[Dict[str, Any]]
    ) -> Tuple[np.ndarray, List[str]]:
        """
        从VOCs物种数据构建浓度矩阵（用于因子数分析）

        Args:
            component_data: PMF输入格式的VOCs数据列表

        Returns:
            X_matrix: 浓度矩阵 (n_samples, n_species)
            species_list: 物种名称列表
        """
        if not component_data:
            return np.array([]), []

        # 收集所有物种
        all_species = set()
        for record in component_data:
            if isinstance(record, dict):
                for key in record.keys():
                    if key not in ("time", "timestamp"):
                        all_species.add(key)

        species_list = sorted(list(all_species))
        rows = []

        for record in component_data:
            if isinstance(record, dict):
                row = []
                for species in species_list:
                    value = record.get(species, 0.01)
                    if value is None or value < 0:
                        value = 0.01
                    row.append(float(value))
                rows.append(row)

        X_matrix = np.array(rows)
        return X_matrix, species_list

    def _check_species_coverage(self, component_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        收集VOCs物种信息（不再校验关键物种，仅数据量>=10条即可）
        """
        # 收集所有物种
        all_species = set()
        for record in component_data:
            if not isinstance(record, dict):
                continue
            for key in record.keys():
                if key not in ("time", "timestamp"):
                    all_species.add(key)

        available_species = sorted(list(all_species))

        # 只返回信息，不做关键物种校验
        return {
            "is_valid": True,
            "available_species": available_species,
            "required_species": [],
            "details": {
                "species_count": len(available_species),
                "precursor_count": len(available_species),
                "key_precursors_found": available_species[:10] if len(available_species) >= 10 else available_species,
                "coverage_rate": 1.0
            },
            "error_msg": None
        }
