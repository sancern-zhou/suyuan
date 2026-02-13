"""
PMF质量控制模块

提供PMF分析前的数据质量评估功能：
1. KMO检验 (Kaiser-Meyer-Olkin)
2. Bartlett球形度检验
3. nimfa PMF算法
4. Q值质量评估

Version: 1.0.0
Author: Claude Code
"""

from typing import Dict, List, Tuple, Optional, Any
import numpy as np
from scipy import stats
from scipy.spatial.distance import cdist
import structlog

logger = structlog.get_logger()


class PMFQualityController:
    """
    PMF质量控制器

    在执行PMF分析前进行数据质量评估和算法选择
    """

    def __init__(self):
        """初始化质量控制器"""
        self.kmo_threshold = 0.6  # KMO阈值
        self.bartlett_alpha = 0.05  # Bartlett检验显著性水平
        self.q_value_threshold = 5.0  # Q值阈值

    def run_quality_control(
        self,
        X_matrix: np.ndarray,
        component_names: List[str],
        pollutant_type: str
    ) -> Dict[str, Any]:
        """
        运行完整的质量控制检查

        Args:
            X_matrix: 浓度矩阵 (n_samples × n_components)
            component_names: 组分名称列表
            pollutant_type: 污染物类型 ("PM" or "VOCs")

        Returns:
            质量控制报告
        """
        logger.info(
            "pmf_quality_control_start",
            samples=X_matrix.shape[0],
            components=X_matrix.shape[1],
            pollutant_type=pollutant_type
        )

        # 1. KMO检验
        kmo_result = self._calculate_kmo(X_matrix)

        # 2. Bartlett球形度检验
        bartlett_result = self._calculate_bartlett_test(X_matrix)

        # 3. 数据预处理评估
        preprocessing_result = self._evaluate_preprocessing(X_matrix, component_names)

        # 4. 算法推荐
        algorithm_recommendation = self._recommend_algorithm(
            kmo_result, bartlett_result, preprocessing_result
        )

        # 5. 生成综合质量报告
        quality_report = {
            "kmo": kmo_result,
            "bartlett": bartlett_result,
            "preprocessing": preprocessing_result,
            "algorithm_recommendation": algorithm_recommendation,
            "overall_quality": self._assess_overall_quality(
                kmo_result, bartlett_result, preprocessing_result
            ),
            "warnings": self._generate_warnings(
                kmo_result, bartlett_result, preprocessing_result
            ),
            "recommendations": self._generate_recommendations(
                kmo_result, bartlett_result, preprocessing_result
            )
        }

        logger.info(
            "pmf_quality_control_complete",
            kmo_value=kmo_result["kmo"],
            bartlett_p=bartlett_result["p_value"],
            quality_score=quality_report["overall_quality"]["score"],
            recommended_algorithm=algorithm_recommendation["recommended_algorithm"]
        )

        return quality_report

    def _calculate_kmo(self, X_matrix: np.ndarray) -> Dict[str, Any]:
        """
        计算KMO检验值

        KMO (Kaiser-Meyer-Olkin) 检验测量变量间相关性和偏相关的大小，
        评估数据是否适合进行因子分析。

        Args:
            X_matrix: 数据矩阵

        Returns:
            KMO检验结果
        """
        try:
            # 计算相关矩阵
            corr_matrix = np.corrcoef(X_matrix.T)

            # 计算偏相关矩阵
            inv_corr = np.linalg.inv(corr_matrix + np.eye(len(corr_matrix)) * 1e-10)
            partial_corr = -inv_corr / np.sqrt(
                np.outer(np.diag(inv_corr), np.diag(inv_corr))
            )
            np.fill_diagonal(partial_corr, 0)

            # 计算KMO值
            sum_sq_corr = np.sum(corr_matrix ** 2) - np.sum(np.diag(corr_matrix) ** 2)
            sum_sq_partial = np.sum(partial_corr ** 2)

            kmo = sum_sq_corr / (sum_sq_corr + sum_sq_partial + 1e-10)
            kmo = float(np.clip(kmo, 0, 1))

            # 判断KMO值等级
            if kmo >= 0.9:
                adequacy = "极佳"
            elif kmo >= 0.8:
                adequacy = "很好"
            elif kmo >= 0.7:
                adequacy = "良好"
            elif kmo >= 0.6:
                adequacy = "一般"
            elif kmo >= 0.5:
                adequacy = "较差"
            else:
                adequacy = "不适合"

            # 判断是否通过KMO检验
            passed = kmo >= self.kmo_threshold

            result = {
                "kmo": kmo,
                "adequacy": adequacy,
                "passed": passed,
                "threshold": self.kmo_threshold,
                "interpretation": self._interpret_kmo(kmo)
            }

            logger.info(
                "pmf_kmo_calculated",
                kmo=kmo,
                adequacy=adequacy,
                passed=passed
            )

            return result

        except Exception as e:
            logger.error("pmf_kmo_calculation_failed", error=str(e))
            return {
                "kmo": 0.0,
                "adequacy": "计算失败",
                "passed": False,
                "threshold": self.kmo_threshold,
                "error": str(e)
            }

    def _interpret_kmo(self, kmo: float) -> str:
        """解释KMO值"""
        interpretations = {
            0.9: "数据非常适合进行因子分析",
            0.8: "数据适合进行因子分析",
            0.7: "数据尚可进行因子分析",
            0.6: "数据勉强适合进行因子分析",
            0.5: "数据不太适合进行因子分析",
            0.0: "数据完全不适合进行因子分析"
        }

        for threshold, desc in sorted(interpretations.items(), reverse=True):
            if kmo >= threshold:
                return desc

        return "KMO值解释未知"

    def _calculate_bartlett_test(self, X_matrix: np.ndarray) -> Dict[str, Any]:
        """
        计算Bartlett球形度检验

        检验原假设：相关矩阵是单位矩阵（变量间无相关性）
        如果拒绝原假设，说明变量间存在相关性，适合进行因子分析。

        Args:
            X_matrix: 数据矩阵

        Returns:
            Bartlett检验结果
        """
        try:
            # 计算相关矩阵
            n_samples, n_components = X_matrix.shape
            corr_matrix = np.corrcoef(X_matrix.T)

            # 计算统计量
            det_corr = np.linalg.det(corr_matrix)

            if det_corr <= 0:
                # 相关矩阵奇异，使用伪行列式
                det_corr = np.prod(np.linalg.eigvals(corr_matrix))
                det_corr = max(det_corr, 1e-10)

            # Bartlett统计量
            bartlett_stat = -(n_samples - 1 - (2 * n_components + 5) / 6) * np.log(det_corr)

            # 自由度
            df = n_components * (n_components - 1) / 2

            # p值
            p_value = 1 - stats.chi2.cdf(bartlett_stat, df)

            # 判断是否通过检验
            passed = p_value < self.bartlett_alpha

            result = {
                "statistic": float(bartlett_stat),
                "df": int(df),
                "p_value": float(p_value),
                "alpha": self.bartlett_alpha,
                "passed": passed,
                "interpretation": self._interpret_bartlett(p_value)
            }

            logger.info(
                "pmf_bartlett_calculated",
                statistic=bartlett_stat,
                df=df,
                p_value=p_value,
                passed=passed
            )

            return result

        except Exception as e:
            logger.error("pmf_bartlett_calculation_failed", error=str(e))
            return {
                "statistic": 0.0,
                "df": 0,
                "p_value": 1.0,
                "alpha": self.bartlett_alpha,
                "passed": False,
                "error": str(e)
            }

    def _interpret_bartlett(self, p_value: float) -> str:
        """解释Bartlett检验结果"""
        if p_value < 0.001:
            return "变量间存在极显著相关性，非常适合进行因子分析"
        elif p_value < 0.01:
            return "变量间存在显著相关性，适合进行因子分析"
        elif p_value < 0.05:
            return "变量间存在相关性，适合进行因子分析"
        elif p_value < 0.1:
            return "变量间存在弱相关性，不太适合进行因子分析"
        else:
            return "变量间无显著相关性，不适合进行因子分析"

    def _evaluate_preprocessing(
        self,
        X_matrix: np.ndarray,
        component_names: List[str]
    ) -> Dict[str, Any]:
        """
        评估数据预处理效果

        Args:
            X_matrix: 数据矩阵
            component_names: 组分名称列表

        Returns:
            预处理评估结果
        """
        try:
            # 缺失值评估
            missing_rate = np.isnan(X_matrix).sum() / X_matrix.size

            # 零值比例
            zero_rate = (X_matrix == 0).sum() / X_matrix.size

            # 数据变异系数
            cv_values = []
            for i in range(X_matrix.shape[1]):
                col = X_matrix[:, i]
                if col.std() > 0:
                    cv = col.std() / (col.mean() + 1e-10)
                    cv_values.append(cv)

            median_cv = np.median(cv_values) if cv_values else 0

            # 数据完整性评分
            completeness_score = max(0, 1 - missing_rate * 2)  # 缺失值惩罚

            # 数据变异性评分
            variability_score = min(1, median_cv / 0.5) if median_cv > 0 else 0

            # 综合评分
            overall_score = (completeness_score + variability_score) / 2

            result = {
                "missing_rate": float(missing_rate),
                "zero_rate": float(zero_rate),
                "median_cv": float(median_cv),
                "completeness_score": float(completeness_score),
                "variability_score": float(variability_score),
                "overall_score": float(overall_score),
                "component_count": len(component_names),
                "sample_count": X_matrix.shape[0]
            }

            logger.info(
                "pmf_preprocessing_evaluated",
                missing_rate=missing_rate,
                zero_rate=zero_rate,
                overall_score=overall_score
            )

            return result

        except Exception as e:
            logger.error("pmf_preprocessing_evaluation_failed", error=str(e))
            return {
                "missing_rate": 1.0,
                "zero_rate": 1.0,
                "median_cv": 0.0,
                "completeness_score": 0.0,
                "variability_score": 0.0,
                "overall_score": 0.0,
                "error": str(e)
            }

    def _recommend_algorithm(
        self,
        kmo_result: Dict[str, Any],
        bartlett_result: Dict[str, Any],
        preprocessing_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        基于质量控制结果推荐算法

        Args:
            kmo_result: KMO检验结果
            bartlett_result: Bartlett检验结果
            preprocessing_result: 预处理评估结果

        Returns:
            算法推荐
        """
        # 计算质量得分
        quality_score = 0

        # KMO得分
        if kmo_result.get("passed", False):
            quality_score += 40
        else:
            quality_score += 20

        # Bartlett得分
        if bartlett_result.get("passed", False):
            quality_score += 40
        else:
            quality_score += 20

        # 预处理得分
        quality_score += preprocessing_result.get("overall_score", 0) * 20

        # 算法推荐
        if quality_score >= 80:
            recommended = "nimfa"
            confidence = "高"
            reason = "数据质量优秀，推荐使用nimfa PMF算法"
        elif quality_score >= 60:
            recommended = "nimfa"
            confidence = "中"
            reason = "数据质量良好，可使用nimfa PMF算法"
        else:
            recommended = "simplified"
            confidence = "低"
            reason = "数据质量一般，建议使用简化PMF算法"

        # 是否需要nimfa
        kmo_passed = kmo_result.get("passed", False)
        bartlett_passed = bartlett_result.get("passed", False)
        preprocessing_score = preprocessing_result.get("overall_score", 0)

        nimfa_recommended = kmo_passed and bartlett_passed and preprocessing_score > 0.5

        return {
            "recommended_algorithm": recommended,
            "confidence": confidence,
            "reason": reason,
            "quality_score": float(quality_score),
            "nimfa_recommended": nimfa_recommended,
            "algorithm_details": {
                "nimfa": {
                    "name": "nimfa PMF算法",
                    "description": "基于nimfa库的完整PMF实现，提供更精确的因子分解",
                    "advantages": ["收敛性好", "结果稳定", "支持Q值评估"],
                    "requirements": ["KMO > 0.6", "Bartlett p < 0.05"]
                },
                "simplified": {
                    "name": "简化PMF算法",
                    "description": "基于源谱匹配的简化实现",
                    "advantages": ["计算快速", "无需数据质量检验", "适合初步分析"],
                    "requirements": []
                }
            }
        }

    def _assess_overall_quality(
        self,
        kmo_result: Dict[str, Any],
        bartlett_result: Dict[str, Any],
        preprocessing_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        评估数据整体质量

        Args:
            kmo_result: KMO检验结果
            bartlett_result: Bartlett检验结果
            preprocessing_result: 预处理评估结果

        Returns:
            整体质量评估
        """
        # 计算综合得分
        kmo_score = 100 if kmo_result.get("passed", False) else 60
        bartlett_score = 100 if bartlett_result.get("passed", False) else 60
        preprocessing_score = preprocessing_result.get("overall_score", 0) * 100

        overall_score = (kmo_score + bartlett_score + preprocessing_score) / 3

        # 质量等级
        if overall_score >= 90:
            grade = "A"
            level = "优秀"
        elif overall_score >= 80:
            grade = "B"
            level = "良好"
        elif overall_score >= 70:
            grade = "C"
            level = "一般"
        elif overall_score >= 60:
            grade = "D"
            level = "较差"
        else:
            grade = "F"
            level = "不适合"

        return {
            "score": float(overall_score),
            "grade": grade,
            "level": level,
            "components": {
                "kmo_score": float(kmo_score),
                "bartlett_score": float(bartlett_score),
                "preprocessing_score": float(preprocessing_score)
            }
        }

    def _generate_warnings(
        self,
        kmo_result: Dict[str, Any],
        bartlett_result: Dict[str, Any],
        preprocessing_result: Dict[str, Any]
    ) -> List[str]:
        """生成警告信息"""
        warnings = []

        if not kmo_result.get("passed", False):
            warnings.append(
                f"KMO值={kmo_result.get('kmo', 0):.3f}低于阈值{self.kmo_threshold}，"
                "数据可能不适合进行因子分析"
            )

        if not bartlett_result.get("passed", False):
            warnings.append(
                f"Bartlett检验p值={bartlett_result.get('p_value', 1):.3f}大于显著性水平"
                f"{self.bartlett_alpha}，变量间相关性不足"
            )

        missing_rate = preprocessing_result.get("missing_rate", 0)
        if missing_rate > 0.1:
            warnings.append(f"数据缺失率={missing_rate*100:.1f}%，建议补充数据")

        zero_rate = preprocessing_result.get("zero_rate", 0)
        if zero_rate > 0.3:
            warnings.append(f"零值比例={zero_rate*100:.1f}%，可能影响分析结果")

        return warnings

    def _generate_recommendations(
        self,
        kmo_result: Dict[str, Any],
        bartlett_result: Dict[str, Any],
        preprocessing_result: Dict[str, Any]
    ) -> List[str]:
        """生成建议"""
        recommendations = []

        if not kmo_result.get("passed", False):
            recommendations.append(
                "考虑增加样本数量或删除相关性低的变量以提高KMO值"
            )

        if not bartlett_result.get("passed", False):
            recommendations.append(
                "检查数据选择，考虑合并相关变量或增加时间跨度"
            )

        missing_rate = preprocessing_result.get("missing_rate", 0)
        if missing_rate > 0.05:
            recommendations.append("对缺失值进行插值处理")

        median_cv = preprocessing_result.get("median_cv", 0)
        if median_cv < 0.1:
            recommendations.append("某些组分变异系数过低，考虑剔除")

        return recommendations


class NIMFAWrapper:
    """
    NIMFA PMF算法包装器

    提供基于nimfa库的PMF算法实现
    """

    def __init__(self):
        """初始化nimfa包装器"""
        try:
            import nimfa
            self.nimfa = nimfa
            self.available = True
            logger.info("nimfa_library_loaded")
        except ImportError:
            self.nimfa = None
            self.available = False
            logger.warning("nimfa_library_not_available")

    def run_nimfa_pmf(
        self,
        X_matrix: np.ndarray,
        rank: int = 5,
        max_iter: int = 100,
        seed: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        运行NIMFA PMF算法

        Args:
            X_matrix: 数据矩阵
            rank: 因子数
            max_iter: 最大迭代次数
            seed: 随机种子

        Returns:
            NIMFA PMF结果
        """
        if not self.available:
            return {
                "success": False,
                "error": "nimfa库未安装，请运行: pip install nimfa"
            }

        try:
            # 转换为nimfa格式
            V = np.asarray(X_matrix)

            # 设置种子
            if seed is not None:
                np.random.seed(seed)

            # 使用nimfa NMF算法
            fm = self.nimfa.Nmf(V, rank=rank, max_iter=max_iter)
            fit_result = fm()  # nimfa 1.x: 返回 Mf_fit 对象

            # 提取结果 - Mf_fit对象用方法访问
            W = np.array(fit_result.basis())  # W矩阵
            H = np.array(fit_result.coef())   # H矩阵
            n_iter = fit_result.n_iter

            # 检查结果
            if W is None or H is None or W.size == 0:
                return {
                    "success": False,
                    "error": "无法从nimfa获取因子矩阵"
                }

            # 计算重构矩阵
            X_reconstructed = W @ H

            # 计算Q值
            residuals = X_matrix - X_reconstructed
            q_value = float(np.sum(residuals ** 2))

            # 计算稀疏度（手动计算）
            def calculate_sparseness(matrix):
                n = matrix.size
                if n == 0:
                    return 0.0
                return float(np.sqrt(n) - np.linalg.norm(matrix, ord=1) / (np.linalg.norm(matrix) + 1e-10))

            sparseness_W = calculate_sparseness(W)
            sparseness_H = calculate_sparseness(H)

            # 计算R²
            ss_tot = np.sum((X_matrix - X_matrix.mean()) ** 2)
            ss_res = np.sum(residuals ** 2)
            r2 = 1 - (ss_res / (ss_tot + 1e-10))
            evar = 1 - (ss_res / (ss_tot + 1e-10))

            result = {
                "success": True,
                "W_matrix": W.tolist(),  # 源贡献矩阵
                "H_matrix": H.tolist(),  # 源成分矩阵
                "X_reconstructed": X_reconstructed.tolist(),
                "q_value": q_value,
                "r2": float(r2),
                "sparseness": {
                    "W": sparseness_W,
                    "H": sparseness_H
                },
                "evar": float(evar),  # 解释方差
                "n_iter": int(n_iter),
            }

            logger.info(
                "nimfa_pmf_completed",
                rank=rank,
                q_value=q_value,
                r2=r2,
                n_iter=n_iter
            )

            return result

        except Exception as e:
            logger.error("nimfa_pmf_failed", error=str(e), exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

    def _calculate_q_value(self, X_observed: np.ndarray, fm) -> float:
        """
        计算Q值

        Q值是PMF模型拟合质量的重要指标

        Args:
            X_observed: 观测数据
            fm: 拟合的nimfa模型

        Returns:
            Q值
        """
        try:
            W = fm.basis()
            H = fm.coef()
            X_reconstructed = W @ H

            # 计算残差
            residuals = X_observed - X_reconstructed

            # 计算Q值
            Q = np.sum(residuals ** 2)

            return float(Q)

        except Exception as e:
            logger.error("q_value_calculation_failed", error=str(e))
            return 0.0

    def evaluate_q_value(self, q_value: float, expected_error: float = 1.0) -> Dict[str, Any]:
        """
        评估Q值

        Args:
            q_value: 实际Q值
            expected_error: 预期误差

        Returns:
            Q值评估结果
        """
        # Q值评估标准
        if q_value < expected_error * 0.5:
            quality = "优秀"
            passed = True
            comment = "模型拟合效果极佳"
        elif q_value < expected_error:
            quality = "良好"
            passed = True
            comment = "模型拟合效果良好"
        elif q_value < expected_error * 2:
            quality = "一般"
            passed = False
            comment = "模型拟合效果一般"
        else:
            quality = "差"
            passed = False
            comment = "模型拟合效果差，建议调整参数"

        return {
            "q_value": q_value,
            "expected_error": expected_error,
            "quality": quality,
            "passed": passed,
            "comment": comment
        }
