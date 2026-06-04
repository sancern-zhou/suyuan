"""
PMF Calculator for VOCs - 基于NIMFA无监督因子分解的源解析计算引擎

算法: Non-negative Matrix Factorization (NIMFA)
特点: 无需预定义源谱库，自动从数据中发现潜在污染源

用于 VOCs 挥发性有机物源解析（臭氧溯源）
"""
from typing import Dict, List, Tuple, Optional, Any
import numpy as np
import structlog

from app.utils.data_standardizer import get_data_standardizer

logger = structlog.get_logger()


class PMFCalculator:
    """
    基于NIMFA的PMF计算器（VOCs版本）

    使用无监督矩阵分解算法，从VOCs组分数据中自动识别潜在污染源。
    由专家LLM根据因子载荷特征进行专业解读。
    """

    def __init__(self, pollutant_type: str = "VOCs"):
        """
        初始化计算器

        Args:
            pollutant_type: 污染物类型 ("VOCs" or "PM")
        """
        self.pollutant_type = pollutant_type

        logger.info(
            "pmf_calculator_initialized",
            pollutant_type=pollutant_type,
            algorithm="NIMFA (无监督因子分解)"
        )

    def calculate(
        self,
        component_data: List[Dict[str, Any]],
        pollutant: str = "VOCs",
        run_quality_control: bool = True,
        rank: int = 5,
        max_iter: int = 100
    ) -> Dict[str, Any]:
        """
        执行NIMFA PMF源解析计算

        Args:
            component_data: VOCs组分数据列表
            pollutant: 目标污染物 ("VOCs")
            run_quality_control: 是否运行质量控制检查 (默认True)
            rank: 因子数（预设为5个源）
            max_iter: 最大迭代次数

        Returns:
            {
                "success": True,
                "sources": [...],
                "timeseries": [...],
                "performance": {...},
                "quality_control": {...},
                "algorithm": "nimfa",
                "summary": "..."
            }
        """
        try:
            # 1. 数据验证
            validation_result = self._validate_data(component_data)
            if not validation_result["valid"]:
                return {
                    "success": False,
                    "error": validation_result["error"],
                    "summary": f"PMF计算失败: {validation_result['error']}"
                }

            # 2. 数据预处理
            X_matrix, components, timestamps = self._preprocess_data(component_data)
            logger.info("pmf_data_preprocessed",
                       samples=len(timestamps),
                       components=len(components))

            # 3. 质量控制检查
            quality_control_report = None
            if run_quality_control:
                from app.tools.analysis.calculate_pm_pmf.quality_control import (
                    PMFQualityController
                )
                qc = PMFQualityController()
                quality_control_report = qc.run_quality_control(
                    X_matrix, components, self.pollutant_type
                )
                logger.info(
                    "pmf_quality_control_complete",
                    kmo=quality_control_report["kmo"]["kmo"],
                    bartlett_passed=quality_control_report["bartlett"]["passed"],
                    overall_quality=quality_control_report["overall_quality"]["grade"]
                )

            # 4. 运行NIMFA
            from app.tools.analysis.calculate_pm_pmf.quality_control import NIMFAWrapper
            nimfa_wrapper = NIMFAWrapper()

            if not nimfa_wrapper.available:
                logger.warning("nimfa_not_available_using_simplified")
                result = self._simplified_factorization(
                    X_matrix, components, timestamps, pollutant, rank
                )
                result["quality_control"] = quality_control_report
                return result

            logger.info("pmf_running_nimfa", rank=rank)
            nimfa_result = nimfa_wrapper.run_nimfa_pmf(
                X_matrix,
                rank=rank,
                max_iter=max_iter
            )

            if not nimfa_result.get("success"):
                logger.warning("nimfa_failed_using_simplified")
                result = self._simplified_factorization(
                    X_matrix, components, timestamps, pollutant, rank
                )
                result["quality_control"] = quality_control_report
                result["nimfa_error"] = nimfa_result.get("error")
                return result

            # 5. 转换NIMFA结果为标准格式
            result = self._convert_nimfa_result(
                nimfa_result,
                components,
                timestamps,
                pollutant,
                quality_control_report
            )

            logger.info(
                "pmf_calculation_complete",
                factors=len(result.get("sources", [])),
                R2=result.get("performance", {}).get("R2", 0)
            )

            return result

        except Exception as e:
            logger.error("pmf_calculation_failed", error=str(e), exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "summary": f"PMF计算失败: {str(e)[:100]}"
            }

    def _simplified_factorization(
        self,
        X_matrix: np.ndarray,
        components: List[str],
        timestamps: List[str],
        pollutant: str,
        rank: int = 5
    ) -> Dict[str, Any]:
        """简化版因子分解（当NIMFA不可用时的替代方案）"""
        from scipy.linalg import svd
        from scipy.optimize import nnls

        n_samples, n_components = X_matrix.shape
        actual_rank = min(rank, n_samples, n_components)

        U, S, Vt = svd(X_matrix, full_matrices=False)
        W_matrix = U[:, :actual_rank] * S[:actual_rank]
        H_matrix = Vt[:actual_rank, :]

        G_matrix = np.zeros((n_samples, actual_rank))
        for i in range(n_samples):
            G_matrix[i, :], _ = nnls(H_matrix.T, X_matrix[i, :])

        mean_concentrations = G_matrix.mean(axis=0)
        total_conc = mean_concentrations.sum()
        contributions_pct = (mean_concentrations / (total_conc + 1e-10)) * 100

        selected_sources = [f"因子{i+1}" for i in range(actual_rank)]
        source_contributions = {s: float(contributions_pct[i]) for i, s in enumerate(selected_sources)}
        source_concentrations = {s: float(mean_concentrations[i]) for i, s in enumerate(selected_sources)}

        timeseries = []
        for i, time in enumerate(timestamps):
            record = {"time": time}
            for j, source in enumerate(selected_sources):
                record[source] = float(G_matrix[i, j])
            timeseries.append(record)

        X_reconstructed = G_matrix @ H_matrix
        ss_res = np.sum((X_matrix - X_reconstructed) ** 2)
        ss_tot = np.sum((X_matrix - X_matrix.mean()) ** 2)
        R2 = 1 - (ss_res / (ss_tot + 1e-10))

        return {
            "success": True,
            "pollutant": pollutant,
            "sources": [
                {
                    "source_name": name,
                    "contribution_pct": pct,
                    "concentration": source_concentrations.get(name, 0),
                    "confidence": "Low"
                }
                for name, pct in source_contributions.items()
            ],
            "source_contributions": source_contributions,
            "source_concentrations": source_concentrations,
            "timeseries": timeseries,
            "performance": {
                "R2": float(max(0.0, min(1.0, R2))),
                "RMSE": float(np.sqrt(np.mean((X_matrix - X_reconstructed) ** 2))),
                "convergence_iterations": 0,
                "algorithm": "simplified_svd_nmf"
            },
            "algorithm": "simplified",
            "summary": (
                f"NIMFA源解析完成（简化算法），识别出{len(selected_sources)}个因子，"
                f"模型拟合度R²={R2:.2f}。建议：由专家LLM根据组分特征解读因子含义。"
            )
        }

    def _validate_data(self, component_data: List[Dict]) -> Dict[str, Any]:
        """验证输入数据"""
        if not component_data or len(component_data) == 0:
            return {"valid": False, "error": "组分数据为空"}

        standardizer = get_data_standardizer()

        all_available = set()
        valid_records_count = 0

        for record in component_data:
            if not record or len(record) <= 1:
                continue

            if hasattr(record, 'model_dump'):
                record_dict = record.model_dump()
            else:
                record_dict = dict(record)

            standardized_record = standardizer.standardize(record_dict)

            if 'species_data' in standardized_record and isinstance(standardized_record['species_data'], dict):
                record_components = set(standardized_record['species_data'].keys())
            elif 'components' in standardized_record and isinstance(standardized_record['components'], dict):
                record_components = set(standardized_record['components'].keys())
            else:
                record_components = set(standardized_record.keys()) - {"time", "timestamp", "station_name", "station_code"}

            if record_components:
                all_available.update(record_components)
                valid_records_count += 1

        if valid_records_count < 10:
            return {
                "valid": False,
                "error": f"有效样本数不足（需≥10个，当前{valid_records_count}个）"
            }

        if len(all_available) < 3:
            return {
                "valid": False,
                "error": "可用组分/物种不足（需≥3个）"
            }

        logger.info(
            "pmf_data_validation_passed",
            valid_records=valid_records_count,
            available_components=list(all_available)
        )

        return {"valid": True}

    def _preprocess_data(
        self,
        component_data: List[Dict]
    ) -> Tuple[np.ndarray, List[str], List[str]]:
        """数据预处理：构建浓度矩阵"""
        timestamps = []
        rows = []

        standardizer = get_data_standardizer()
        all_components = set()

        for record in component_data:
            if not record or len(record) <= 1:
                continue

            if hasattr(record, 'model_dump'):
                record_dict = record.model_dump()
            else:
                record_dict = dict(record)

            standardized_record = standardizer.standardize(record_dict)

            # 提取物种数据
            if 'species_data' in standardized_record and isinstance(standardized_record['species_data'], dict):
                all_components.update(standardized_record['species_data'].keys())
            elif 'components' in standardized_record and isinstance(standardized_record['components'], dict):
                all_components.update(standardized_record['components'].keys())
            else:
                all_components.update(
                    k for k in standardized_record.keys()
                    if k not in ["time", "timestamp", "station_name", "station_code"]
                )

        components = sorted(list(all_components))

        for record in component_data:
            if not record or len(record) <= 1:
                continue

            if hasattr(record, 'model_dump'):
                record_dict = record.model_dump()
            else:
                record_dict = dict(record)

            standardized_record = standardizer.standardize(record_dict)

            timestamp = standardized_record.get('time') or standardized_record.get('timestamp', "")
            timestamps.append(timestamp)

            row = []
            if 'species_data' in standardized_record and isinstance(standardized_record['species_data'], dict):
                species_dict = standardized_record['species_data']
                for comp in components:
                    value = species_dict.get(comp, 0.0)
                    if value is None or value < 0:
                        value = 0.01
                    row.append(float(value))
            elif 'components' in standardized_record and isinstance(standardized_record['components'], dict):
                components_dict = standardized_record['components']
                for comp in components:
                    value = components_dict.get(comp, 0.0)
                    if value is None or value < 0:
                        value = 0.01
                    row.append(float(value))
            else:
                for comp in components:
                    value = standardized_record.get(comp, 0.0)
                    if value is None or value < 0:
                        value = 0.01
                    row.append(float(value))

            rows.append(row)

        X_matrix = np.array(rows)
        return X_matrix, components, timestamps

    def _merge_gas_data(
        self,
        pm_records: List[Any],
        gas_records: Optional[List[Any]] = None
    ) -> List[Dict[str, Any]]:
        """合并数据（VOCs版本，留空）"""
        if not gas_records:
            result = []
            for r in pm_records:
                if hasattr(r, 'model_dump'):
                    result.append(r.model_dump())
                else:
                    result.append(dict(r))
            return result
        return pm_records

    def _convert_nimfa_result(
        self,
        nimfa_result: Dict[str, Any],
        components: List[str],
        timestamps: List[str],
        pollutant: str,
        quality_control_report: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """将nimfa结果转换为标准PMFResult格式"""
        from datetime import datetime
        from app.schemas.pmf import PMFSourceContribution, PMFTimeSeriesPoint, PMFResult

        W_matrix = np.array(nimfa_result["W_matrix"])
        H_matrix = np.array(nimfa_result["H_matrix"])

        n_factors = H_matrix.shape[0]
        selected_sources = [f"因子{i+1}" for i in range(n_factors)]

        mean_concentrations = W_matrix.mean(axis=0)
        total_conc = mean_concentrations.sum()
        contributions_pct = (mean_concentrations / (total_conc + 1e-10)) * 100

        source_contributions = {s: float(contributions_pct[i]) for i, s in enumerate(selected_sources)}
        source_concentrations = {s: float(mean_concentrations[i]) for i, s in enumerate(selected_sources)}

        timeseries = []
        for i, time in enumerate(timestamps):
            record = {"time": time}
            for j, source in enumerate(selected_sources):
                record[source] = float(W_matrix[i, j])
            timeseries.append(record)

        performance = {
            "R2": nimfa_result.get("r2", 0.0),
            "RMSE": 0.0,
            "relative_error": 0.0,
            "convergence_iterations": nimfa_result.get("n_iter", 0),
            "q_value": nimfa_result.get("q_value", 0.0),
            "evar": nimfa_result.get("evar", 0.0)
        }

        sources = []
        for source_name in selected_sources:
            contribution_pct = source_contributions.get(source_name, 0.0)
            concentration = source_concentrations.get(source_name, 0.0)

            source_contribution = PMFSourceContribution(
                source_name=source_name,
                contribution_pct=contribution_pct,
                concentration=concentration,
                confidence="Medium"
            )
            sources.append(source_contribution)

        timeseries_converted = []
        for point in timeseries:
            time_str = point.pop("time")
            source_values = {s: float(point[s]) for s in selected_sources if s in point}

            try:
                time_obj = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                time_obj = datetime.now()

            timeseries_point = PMFTimeSeriesPoint(
                time=time_obj,
                source_values=source_values
            )
            timeseries_converted.append(timeseries_point)

        pmf_result_obj = PMFResult(
            pollutant=pollutant,
            station_name="",
            sources=sources,
            timeseries=timeseries_converted,
            performance=performance,
            schema_version="pmf.v1"
        )

        # 精简质量控制报告（只保留关键指标）
        quality_control_summary = None
        if quality_control_report:
            quality_control_summary = {
                "kmo": quality_control_report.get("kmo", {}).get("kmo"),
                "bartlett_passed": quality_control_report.get("bartlett", {}).get("passed"),
                "overall_quality": quality_control_report.get("overall_quality", {}).get("grade"),
                "preprocessing_score": quality_control_report.get("preprocessing", {}).get("score")
            }

        return {
            "success": True,
            "pollutant": pollutant,
            "sources": [source.model_dump(mode='json') for source in sources],
            "performance": performance,
            "schema_version": "pmf.v1",
            "source_contributions": source_contributions,
            "source_concentrations": source_concentrations,
            "quality_control": quality_control_summary,
            "algorithm": "nimfa",
            "nimfa_details": {
                "q_value": nimfa_result.get("q_value", 0.0),
                "evar": nimfa_result.get("evar", 0.0),
                "sparseness": nimfa_result.get("sparseness", {}),
                "n_iter": nimfa_result.get("n_iter", 0)
            },
            "factor_loadings": {
                f"因子{i+1}": {comp: float(H_matrix[i, j]) for j, comp in enumerate(components)}
                for i in range(n_factors)
            },
            "summary": (
                f"NIMFA无监督PMF源解析完成，识别出{n_factors}个因子。"
                f"Q值={nimfa_result.get('q_value', 0):.2f}，R²={nimfa_result.get('r2', 0):.2f}。"
                f"请专家LLM根据因子载荷矩阵解读各因子对应的污染源类型。"
            )
        }
