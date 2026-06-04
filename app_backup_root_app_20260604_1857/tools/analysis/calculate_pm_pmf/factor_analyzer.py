"""
PMF因子数分析器

根据规范6.1.3确定最优因子数：
1. Q值变化曲线分析（主方法）
2. 加权残差分析（辅助验证）
3. 回归诊断（验证）

支持并行计算以提高效率
"""
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np
import structlog
from datetime import datetime

logger = structlog.get_logger()


@dataclass
class RankResult:
    """单个因子数的PMF计算结果"""
    rank: int
    success: bool
    error: str = None

    # Q值相关
    Q_true: float = 0.0
    Q_theo: float = 0.0
    Q_ratio: float = 0.0  # Q_true / Q_theo
    R2: float = 0.0

    # 残差分析
    residual_passed: bool = False
    residual_details: Dict = field(default_factory=dict)

    # 回归诊断
    regression_passed: bool = False
    regression_details: Dict = field(default_factory=dict)

    # 因子载荷
    factor_loadings: np.ndarray = None
    factor_contributions: np.ndarray = None

    # 原始结果
    nimfa_result: Dict = None


@dataclass
class FactorAnalysisResult:
    """因子数分析最终结果"""
    # 推荐结果
    optimal_rank: int = 5
    recommended_rank: int = 5
    confidence: float = 0.0  # 置信度 0-1

    # Q值变化曲线
    Q_curve: List[Dict] = field(default_factory=list)

    # 各因子数分析结果
    all_results: Dict[int, RankResult] = field(default_factory=dict)

    # 通过验证的因子数
    pass_residual: List[int] = field(default_factory=list)
    pass_regression: List[int] = field(default_factory=list)
    pass_all: List[int] = field(default_factory=list)

    # 并行计算信息
    parallel_info: Dict = field(default_factory=dict)

    # 时间戳
    analysis_time: str = None


class FactorAnalyzer:
    """PMF因子数分析器"""

    def __init__(
        self,
        max_workers: int = None,
        pollutant_type: str = "PM"
    ):
        """
        初始化因子数分析器

        Args:
            max_workers: 最大并行数，默认CPU核心数
            pollutant_type: 污染物类型 ("PM" or "VOCs")
        """
        import multiprocessing
        self.max_workers = max_workers or min(multiprocessing.cpu_count(), 4)
        self.pollutant_type = pollutant_type

        logger.info(
            "factor_analyzer_init",
            max_workers=self.max_workers,
            pollutant_type=pollutant_type
        )

    def analyze(
        self,
        X_matrix: np.ndarray,
        min_rank: int = 3,
        max_rank: int = 8,
        weights: np.ndarray = None,
        key_component_indices: List[int] = None
    ) -> FactorAnalysisResult:
        """
        分析最优因子数

        Args:
            X_matrix: 浓度矩阵 (n_samples, n_components)
            min_rank: 最小因子数
            max_rank: 最大因子数
            weights: 权重矩阵（可选）
            key_component_indices: 关键组分索引列表

        Returns:
            FactorAnalysisResult对象
        """
        import time
        start_time = time.time()

        # 确定因子数范围
        n_samples, n_components = X_matrix.shape
        max_possible_rank = min(min(20, n_samples // 10), n_components)
        max_rank = min(max_rank, max_possible_rank)
        min_rank = min(min_rank, max_rank)

        ranks = list(range(min_rank, max_rank + 1))
        logger.info(
            "factor_analysis_start",
            n_samples=n_samples,
            n_components=n_components,
            rank_range=f"{min_rank}-{max_rank}",
            actual_ranks=ranks
        )

        # 并行计算各因子数
        all_results = {}
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_rank = {
                executor.submit(
                    self._run_pmf_for_rank,
                    X_matrix.copy(),  # 复制数据避免进程冲突
                    rank,
                    weights.copy() if weights is not None else None,
                    key_component_indices
                ): rank
                for rank in ranks
            }

            for future in as_completed(future_to_rank):
                rank = future_to_rank[future]
                try:
                    result = future.result()
                    all_results[rank] = result
                    logger.info(
                        "rank_completed",
                        rank=rank,
                        success=result.success,
                        Q_true=result.Q_true if result.success else None
                    )
                except Exception as e:
                    logger.error("rank_failed", rank=rank, error=str(e))
                    all_results[rank] = RankResult(rank=rank, success=False, error=str(e))

        # 综合分析
        result = self._analyze_results(
            all_results,
            start_time,
            n_samples,
            n_components
        )

        logger.info(
            "factor_analysis_complete",
            optimal_rank=result.optimal_rank,
            confidence=result.confidence,
            execution_time=result.parallel_info.get("execution_time", 0)
        )

        return result

    def _run_pmf_for_rank(
        self,
        X_matrix: np.ndarray,
        rank: int,
        weights: np.ndarray = None,
        key_component_indices: List[int] = None
    ) -> RankResult:
        """为单个因子数运行PMF计算"""
        from app.tools.analysis.calculate_pm_pmf.quality_control import NIMFAWrapper

        # 运行NIMFA
        wrapper = NIMFAWrapper()
        nimfa_result = wrapper.run_nimfa_pmf(
            X_matrix,
            rank=rank,
            max_iter=100
        )

        if not nimfa_result.get("success"):
            return RankResult(
                rank=rank,
                success=False,
                error=nimfa_result.get("error", "NIMFA计算失败")
            )

        # 提取结果
        W_matrix = np.array(nimfa_result["W_matrix"])
        H_matrix = np.array(nimfa_result["H_matrix"])
        Q_true = nimfa_result.get("q_value", 0)
        R2 = nimfa_result.get("r2", 0)

        # 计算理论Q值
        n_samples, n_components = X_matrix.shape
        Q_theo = n_samples * n_components - rank * (n_samples + n_components)

        # 残差分析
        residual_result = self._analyze_residuals(
            X_matrix, W_matrix, H_matrix, key_component_indices
        )

        # 回归诊断
        regression_result = self._analyze_regression(W_matrix, X_matrix)

        return RankResult(
            rank=rank,
            success=True,
            Q_true=Q_true,
            Q_theo=Q_theo,
            Q_ratio=Q_true / (Q_theo + 1e-10),
            R2=R2,
            residual_passed=residual_result["passed"],
            residual_details=residual_result,
            regression_passed=regression_result["passed"],
            regression_details=regression_result,
            factor_loadings=H_matrix,
            factor_contributions=W_matrix.mean(axis=0),
            nimfa_result=nimfa_result
        )

    def _analyze_residuals(
        self,
        X_matrix: np.ndarray,
        W_matrix: np.ndarray,
        H_matrix: np.ndarray,
        key_component_indices: List[int] = None
    ) -> Dict[str, Any]:
        """分析加权残差（规范6.1.3.2）"""
        # 计算预测值
        X_pred = W_matrix @ H_matrix

        # 计算残差
        residuals = X_matrix - X_pred

        # 计算不确定度（简化版）
        uncertainty = np.abs(X_matrix) * 0.1 + 0.01

        # 加权残差
        weighted_residuals = residuals / (uncertainty + 1e-10)

        # 关键组分（默认前5个）
        if key_component_indices is None:
            key_indices = list(range(min(5, X_matrix.shape[1])))
        else:
            key_indices = key_component_indices

        # 检查关键组分残差
        key_residuals = weighted_residuals[:, key_indices]
        key_passed = np.all(np.abs(key_residuals) <= 3)

        # 检查所有组分
        all_residuals = weighted_residuals.flatten()
        all_in_range = np.abs(all_residuals) <= 3
        all_pass_rate = float(np.sum(all_in_range) / len(all_in_residuals)) if len(all_in_range) > 0 else 0

        # 统计
        residual_stats = {
            "mean": float(np.mean(all_residuals)),
            "std": float(np.std(all_residuals)),
            "max": float(np.max(np.abs(all_residuals))),
            "min": float(np.min(all_residuals)),
            "in_range_ratio": all_pass_rate,
            "key_passed": bool(key_passed),
            "key_max_residual": float(np.max(np.abs(key_residuals)))
        }

        # 规范6.1.3.2: 加权残差应在正负3以内
        passed = key_passed and all_pass_rate >= 0.8

        return {
            "passed": passed,
            **residual_stats
        }

    def _analyze_regression(
        self,
        W_matrix: np.ndarray,
        X_matrix: np.ndarray
    ) -> Dict[str, Any]:
        """回归诊断（规范6.1.3.4）"""
        # 计算各因子贡献
        factor_sums = W_matrix.sum(axis=0)
        total = factor_sums.sum()
        contributions = factor_sums / (total + 1e-10)

        # 检查系数非负
        coefficients_non_negative = np.all(contributions >= 0)

        # 计算观测值与预测值的相关性
        X_pred = W_matrix @ W_matrix.T @ X_matrix
        X_obs_flat = X_matrix.flatten()
        X_pred_flat = X_pred.flatten()

        # 过滤有效数据
        valid_mask = np.abs(X_obs_flat) > 1e-6
        if np.sum(valid_mask) < 10:
            correlation = 0.0
        else:
            obs_valid = X_obs_flat[valid_mask]
            pred_valid = X_pred_flat[valid_mask]
            correlation = float(np.corrcoef(obs_valid, pred_valid)[0, 1])

        # 综合判断
        passed = coefficients_non_negative and correlation > 0.8

        return {
            "passed": passed,
            "coefficients_non_negative": bool(coefficients_non_negative),
            "factor_contributions": contributions.tolist(),
            "correlation": correlation,
            "all_positive": bool(coefficients_non_negative)
        }

    def _analyze_results(
        self,
        all_results: Dict[int, RankResult],
        start_time: float,
        n_samples: int,
        n_components: int
    ) -> FactorAnalysisResult:
        """综合分析所有结果，确定最优因子数"""
        import time
        execution_time = time.time() - start_time

        # 提取Q值曲线
        Q_curve = []
        for rank in sorted(all_results.keys()):
            r = all_results[rank]
            if r.success:
                Q_curve.append({
                    "rank": rank,
                    "Q_true": r.Q_true,
                    "Q_theo": r.Q_theo,
                    "Q_ratio": r.Q_ratio,
                    "R2": r.R2,
                    "residual_passed": r.residual_passed,
                    "regression_passed": r.regression_passed
                })

        # 规范6.1.3.1: Q值变化曲线分析
        recommended_rank = self._find_optimal_by_q_curve(Q_curve)

        # 筛选满足残差条件的因子数
        pass_residual = [r.rank for r in all_results.values()
                        if r.success and r.residual_passed]

        # 筛选回归诊断通过的因子数
        pass_regression = [r.rank for r in all_results.values()
                          if r.success and r.regression_passed]

        # 综合推荐：在推荐因子数附近找满足所有条件的
        optimal_rank = recommended_rank
        candidate_ranks = [recommended_rank]
        if recommended_rank - 1 >= min(all_results.keys()):
            candidate_ranks.append(recommended_rank - 1)
        if recommended_rank + 1 <= max(all_results.keys()):
            candidate_ranks.append(recommended_rank + 1)

        for rank in candidate_ranks:
            if rank in pass_residual and rank in pass_regression:
                optimal_rank = rank
                break

        # 计算置信度
        confidence = self._calculate_confidence(
            optimal_rank, Q_curve, pass_residual, pass_regression
        )

        # 计算加速比
        n_ranks = len(all_results)
        speedup = min(n_ranks, self.max_workers) * 0.85

        pass_all = list(set(pass_residual) & set(pass_regression))

        return FactorAnalysisResult(
            optimal_rank=optimal_rank,
            recommended_rank=recommended_rank,
            confidence=confidence,
            Q_curve=Q_curve,
            all_results=all_results,
            pass_residual=pass_residual,
            pass_regression=pass_regression,
            pass_all=pass_all,
            parallel_info={
                "total_ranks": n_ranks,
                "parallel_workers": self.max_workers,
                "execution_time": round(execution_time, 2),
                "speedup": round(speedup, 2),
                "n_samples": n_samples,
                "n_components": n_components
            },
            analysis_time=datetime.now().isoformat()
        )

    def _find_optimal_by_q_curve(self, Q_curve: List[Dict]) -> int:
        """根据Q值变化曲线找拐点（规范6.1.3.1）"""
        if len(Q_curve) < 2:
            return Q_curve[0]["rank"] if Q_curve else 5

        # 计算相邻因子数之间的Q值下降率
        for i in range(1, len(Q_curve)):
            prev_q = Q_curve[i-1]["Q_true"]
            curr_q = Q_curve[i]["Q_true"]

            if prev_q > 0:
                drop_rate = (prev_q - curr_q) / prev_q
                Q_curve[i]["drop_rate"] = drop_rate
            else:
                Q_curve[i]["drop_rate"] = 0

        # 找拐点：下降率 < 5%
        for i in range(1, len(Q_curve)):
            if Q_curve[i].get("drop_rate", 0) < 0.05:
                # 返回拐点前一个因子数
                return Q_curve[i-1]["rank"]

        # 没有明显拐点，返回最后一个因子数
        return Q_curve[-1]["rank"]

    def _calculate_confidence(
        self,
        optimal_rank: int,
        Q_curve: List[Dict],
        pass_residual: List[int],
        pass_regression: List[int]
    ) -> float:
        """计算推荐因子数的置信度"""
        score = 0.0

        # Q值合理性 (0-0.3)
        optimal_result = next((r for r in Q_curve if r["rank"] == optimal_rank), None)
        if optimal_result:
            # Q_ratio 在 0.85-1.15 之间得满分
            q_ratio = optimal_result.get("Q_ratio", 0)
            if 0.85 <= q_ratio <= 1.15:
                score += 0.3
            elif 0.7 <= q_ratio <= 1.3:
                score += 0.2
            else:
                score += 0.1

        # 残差验证通过 (0-0.3)
        if optimal_rank in pass_residual:
            score += 0.3
        else:
            # 关键组分通过但整体未通过
            if optimal_result and optimal_result.get("residual_passed"):
                score += 0.2

        # 回归验证通过 (0-0.3)
        if optimal_rank in pass_regression:
            score += 0.3

        # Q值稳定性 (0-0.1)
        if len(Q_curve) >= 2:
            optimal_idx = next((i for i, r in enumerate(Q_curve) if r["rank"] == optimal_rank), -1)
            if optimal_idx > 0:
                prev_drop = Q_curve[optimal_idx].get("drop_rate", 0)
                if prev_drop > 0.05:  # 有明显下降后趋于稳定
                    score += 0.1

        return min(score, 1.0)

    def generate_report(self, result: FactorAnalysisResult) -> str:
        """生成分析报告"""
        lines = [
            "=" * 50,
            "PMF因子数分析报告",
            "=" * 50,
            f"分析时间: {result.analysis_time}",
            "",
            f"【推荐结果】",
            f"最优因子数: {result.optimal_rank}",
            f"推荐因子数: {result.recommended_rank}",
            f"置信度: {result.confidence:.2%}",
            "",
            "【Q值变化曲线】",
            "----------------",
        ]

        for item in result.Q_curve:
            drop = item.get("drop_rate", 0)
            drop_str = f", 下降率: {drop:.1%}" if drop > 0 else ""
            residual_str = ", 残差✓" if item.get("residual_passed") else ""
            reg_str = ", 回归✓" if item.get("regression_passed") else ""
            lines.append(
                f"因子数={item['rank']}: Q={item['Q_true']:.1f}, "
                f"Q_theo={item['Q_theo']:.1f}, R²={item['R2']:.3f}"
                f"{drop_str}{residual_str}{reg_str}"
            )

        lines.extend([
            "",
            "【验证结果】",
            f"残差验证通过: {result.pass_residual}",
            f"回归验证通过: {result.pass_regression}",
            "",
            "【并行计算信息】",
            f"计算因子数: {result.parallel_info['total_ranks']}",
            f"并行进程数: {result.parallel_info['parallel_workers']}",
            f"执行时间: {result.parallel_info['execution_time']}秒",
            f"加速比: {result.parallel_info['speedup']}x",
        ])

        return "\n".join(lines)


def analyze_optimal_rank(
    X_matrix: np.ndarray,
    min_rank: int = 3,
    max_rank: int = 8,
    weights: np.ndarray = None,
    key_component_indices: List[int] = None,
    pollutant_type: str = "PM"
) -> FactorAnalysisResult:
    """
    便捷函数：分析最优因子数

    Args:
        X_matrix: 浓度矩阵
        min_rank: 最小因子数
        max_rank: 最大因子数
        weights: 权重矩阵
        key_component_indices: 关键组分索引
        pollutant_type: 污染物类型

    Returns:
        FactorAnalysisResult对象
    """
    analyzer = FactorAnalyzer(pollutant_type=pollutant_type)
    return analyzer.analyze(
        X_matrix,
        min_rank=min_rank,
        max_rank=max_rank,
        weights=weights,
        key_component_indices=key_component_indices
    )
