"""
Reduction Scenario Simulator

减排情景模拟器 - 定量模拟不同VOCs/NOx减排比例对O3的影响。

功能:
1. 模拟5种标准减排路径
2. 自定义减排比例模拟
3. 计算减排效率和达标可行性
4. 生成减排路径图

参考:
- D:\溯源\参考\OBM\EKMA.py 的减排路线设计
"""

from typing import Dict, List, Any, Optional, Tuple
import numpy as np
from dataclasses import dataclass
from datetime import datetime
import structlog

logger = structlog.get_logger()


@dataclass
class ReductionPath:
    """减排路径数据类"""
    name: str
    voc_ratio: float  # VOCs减排比例
    nox_ratio: float  # NOx减排比例
    o3_values: List[float]  # O3浓度序列
    reduction_percentages: List[float]  # 减排百分比序列
    final_o3: float
    reduction_efficiency: float  # 每1%减排对应的O3下降
    reaches_target: bool  # 是否达到目标值
    steps_to_target: Optional[int]  # 达到目标需要的步数


class ReductionSimulator:
    """
    减排情景模拟器
    
    模拟不同VOCs/NOx减排组合对O3浓度的影响。
    
    使用:
        simulator = ReductionSimulator()
        result = simulator.simulate_all_paths(o3_surface, voc_axis, nox_axis)
    """
    
    # 标准减排路径定义
    STANDARD_PATHS = {
        "vocs_only": {"name": "仅减VOCs", "voc_ratio": 1.0, "nox_ratio": 0.0},
        "nox_only": {"name": "仅减NOx", "voc_ratio": 0.0, "nox_ratio": 1.0},
        "equal": {"name": "等比例", "voc_ratio": 1.0, "nox_ratio": 1.0},
        "vocs_2_nox_1": {"name": "VOCs优先(2:1)", "voc_ratio": 2.0, "nox_ratio": 1.0},
        "vocs_1_nox_2": {"name": "NOx优先(1:2)", "voc_ratio": 1.0, "nox_ratio": 2.0},
    }
    
    # O3控制目标值 (ppb)
    O3_TARGET_LEVEL_1 = 160  # 一级标准 (µg/m³ ≈ 75 ppb)
    O3_TARGET_LEVEL_2 = 100  # 二级标准 (µg/m³ ≈ 47 ppb)
    
    def __init__(self, o3_target: float = 75.0):
        """
        初始化模拟器

        Args:
            o3_target: O3控制目标值 (ppb)
        """
        self.o3_target = o3_target
    
    def simulate_all_paths(
        self,
        o3_surface: np.ndarray,
        voc_factors: List[float],
        nox_factors: List[float],
        current_o3: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        模拟所有标准减排路径
        
        Args:
            o3_surface: O3响应曲面 (2D array)
            voc_factors: VOC缩放因子列表
            nox_factors: NOx缩放因子列表
            current_o3: 当前O3浓度(可选)
        
        Returns:
            模拟结果字典
        """
        n_voc, n_nox = o3_surface.shape
        
        # 找到当前状态位置(因子=1.0)
        voc_current_idx = min(range(len(voc_factors)), 
                             key=lambda i: abs(voc_factors[i] - 1.0))
        nox_current_idx = min(range(len(nox_factors)), 
                             key=lambda i: abs(nox_factors[i] - 1.0))
        
        if current_o3 is None:
            current_o3 = float(o3_surface[voc_current_idx, nox_current_idx])
        
        # 模拟每条路径
        paths_results = {}
        for path_id, path_def in self.STANDARD_PATHS.items():
            path_result = self._simulate_path(
                o3_surface=o3_surface,
                voc_factors=voc_factors,
                nox_factors=nox_factors,
                voc_start_idx=voc_current_idx,
                nox_start_idx=nox_current_idx,
                voc_ratio=path_def["voc_ratio"],
                nox_ratio=path_def["nox_ratio"],
                path_name=path_def["name"]
            )
            paths_results[path_id] = path_result
        
        # 找到最优路径
        best_path_id = self._find_best_path(paths_results)
        
        # 生成可视化数据
        viz_data = self._generate_visualization(
            paths_results, current_o3, voc_factors, nox_factors
        )
        
        return {
            "status": "success",
            "success": True,
            "data": {
                "current_o3": current_o3,
                "target_o3": self.o3_target,
                "paths": {
                    pid: self._path_to_dict(p) 
                    for pid, p in paths_results.items()
                },
                "best_path": best_path_id,
                "best_path_info": self._path_to_dict(paths_results[best_path_id]),
                "feasibility_analysis": self._analyze_feasibility(paths_results, current_o3)
            },
            "visuals": [viz_data],
            "metadata": {
                "schema_version": "v2.0",
                "generator": "ReductionSimulator",
                "generator_version": "1.0.0",
                "o3_target": self.o3_target,
                "analysis_time": datetime.now().isoformat()
            },
            "summary": self._generate_summary(paths_results, best_path_id, current_o3)
        }
    
    def _simulate_path(
        self,
        o3_surface: np.ndarray,
        voc_factors: List[float],
        nox_factors: List[float],
        voc_start_idx: int,
        nox_start_idx: int,
        voc_ratio: float,
        nox_ratio: float,
        path_name: str
    ) -> ReductionPath:
        """模拟单条减排路径"""
        n_voc, n_nox = o3_surface.shape
        
        o3_values = []
        reduction_pcts = []
        
        i, j = voc_start_idx, nox_start_idx
        start_o3 = float(o3_surface[i, j])
        
        # 沿路径前进
        step = 0
        while i >= 0 and j >= 0:
            o3_val = float(o3_surface[i, j])
            o3_values.append(o3_val)
            
            # 计算减排百分比
            if voc_ratio + nox_ratio > 0:
                total_reduction = step * 2 / (voc_ratio + nox_ratio) * 5  # 每步约5%
            else:
                total_reduction = 0
            reduction_pcts.append(min(total_reduction, 100))
            
            # 移动到下一个网格点
            if voc_ratio > 0 and nox_ratio > 0:
                # 同时减排
                voc_step = max(1, int(voc_ratio))
                nox_step = max(1, int(nox_ratio))
                i -= voc_step
                j -= nox_step
            elif voc_ratio > 0:
                i -= 2
            elif nox_ratio > 0:
                j -= 2
            else:
                break
            
            step += 1
            
            # 防止无限循环
            if step > 100:
                break
        
        # 计算减排效率
        if len(o3_values) > 1:
            o3_reduction = start_o3 - o3_values[-1]
            total_steps = len(o3_values) - 1
            efficiency = o3_reduction / (total_steps * 5) if total_steps > 0 else 0
        else:
            efficiency = 0
        
        # 检查是否达到目标
        reaches_target = any(v <= self.o3_target for v in o3_values)
        steps_to_target = None
        if reaches_target:
            for idx, v in enumerate(o3_values):
                if v <= self.o3_target:
                    steps_to_target = idx
                    break
        
        return ReductionPath(
            name=path_name,
            voc_ratio=voc_ratio,
            nox_ratio=nox_ratio,
            o3_values=o3_values,
            reduction_percentages=reduction_pcts,
            final_o3=o3_values[-1] if o3_values else start_o3,
            reduction_efficiency=efficiency,
            reaches_target=reaches_target,
            steps_to_target=steps_to_target
        )
    
    def _find_best_path(self, paths_results: Dict[str, ReductionPath]) -> str:
        """找到最优减排路径"""
        # 优先选择能达标的路径
        reachable_paths = {
            pid: p for pid, p in paths_results.items() 
            if p.reaches_target
        }
        
        if reachable_paths:
            # 选择达标最快的
            return min(reachable_paths.items(), 
                      key=lambda x: x[1].steps_to_target or float('inf'))[0]
        else:
            # 选择减排效率最高的
            return max(paths_results.items(),
                      key=lambda x: x[1].reduction_efficiency)[0]
    
    def _path_to_dict(self, path: ReductionPath) -> Dict:
        """将ReductionPath转换为字典"""
        return {
            "name": path.name,
            "voc_ratio": path.voc_ratio,
            "nox_ratio": path.nox_ratio,
            "o3_values": path.o3_values,
            "reduction_percentages": path.reduction_percentages,
            "final_o3": path.final_o3,
            "reduction_efficiency": round(path.reduction_efficiency, 3),
            "reaches_target": path.reaches_target,
            "steps_to_target": path.steps_to_target
        }
    
    def _analyze_feasibility(
        self,
        paths_results: Dict[str, ReductionPath],
        current_o3: float
    ) -> Dict:
        """分析减排可行性"""
        reachable_count = sum(1 for p in paths_results.values() if p.reaches_target)
        
        if current_o3 <= self.o3_target:
            status = "already_compliant"
            message = f"当前O3浓度({current_o3:.1f} ppb)已达标"
        elif reachable_count == 0:
            status = "difficult"
            message = f"所有路径均难以在合理减排幅度内达标(目标: {self.o3_target} ppb)"
        elif reachable_count < 3:
            status = "challenging"
            message = f"部分路径可达标，建议采用最优路径"
        else:
            status = "feasible"
            message = f"多条路径可达标，减排空间较大"
        
        return {
            "status": status,
            "message": message,
            "reachable_paths_count": reachable_count,
            "total_paths": len(paths_results),
            "gap_to_target": max(0, current_o3 - self.o3_target)
        }
    
    def _generate_visualization(
        self,
        paths_results: Dict[str, ReductionPath],
        current_o3: float,
        voc_factors: List[float],
        nox_factors: List[float]
    ) -> Dict:
        """生成减排路径可视化数据"""
        series = []
        colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]
        
        for idx, (path_id, path) in enumerate(paths_results.items()):
            series.append({
                "name": path.name,
                "data": path.o3_values,
                "color": colors[idx % len(colors)],
                "type": "line"
            })
        
        return {
            "id": f"reduction_paths_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "type": "line",
            "title": "减排路径O3响应曲线",
            "data": {
                "x": list(range(max(len(p.o3_values) for p in paths_results.values()))),
                "series": series
            },
            "layout": {
                "xaxis": {"title": "减排步数"},
                "yaxis": {"title": "O3浓度 (ppb)"},
                "shapes": [
                    {
                        "type": "line",
                        "y0": self.o3_target,
                        "y1": self.o3_target,
                        "line": {"color": "red", "dash": "dash"},
                        "label": f"目标值 ({self.o3_target} ppb)"
                    }
                ]
            },
            "meta": {
                "schema_version": "3.1",
                "generator": "ReductionSimulator",
                "scenario": "reduction_paths",
                "layout_hint": "wide"
            }
        }
    
    def _generate_summary(
        self,
        paths_results: Dict[str, ReductionPath],
        best_path_id: str,
        current_o3: float
    ) -> str:
        """生成分析摘要"""
        best_path = paths_results[best_path_id]
        
        if current_o3 <= self.o3_target:
            return f"当前O3浓度({current_o3:.1f} ppb)已满足控制目标({self.o3_target} ppb)。"
        
        if best_path.reaches_target:
            return (
                f"减排模拟完成。当前O3: {current_o3:.1f} ppb，目标: {self.o3_target} ppb。"
                f"最优路径: {best_path.name}，"
                f"预计{best_path.steps_to_target}步(约{best_path.steps_to_target*5}%减排)可达标。"
                f"减排效率: {best_path.reduction_efficiency:.2f} ppb/步。"
            )
        else:
            return (
                f"减排模拟完成。当前O3: {current_o3:.1f} ppb，目标: {self.o3_target} ppb。"
                f"最优路径: {best_path.name}，"
                f"最终可达{best_path.final_o3:.1f} ppb，"
                f"距目标仍有{best_path.final_o3 - self.o3_target:.1f} ppb差距。"
                f"建议加大减排力度或采用综合控制措施。"
            )
    
    def simulate_custom_path(
        self,
        o3_surface: np.ndarray,
        voc_factors: List[float],
        nox_factors: List[float],
        voc_reduction_pct: float,
        nox_reduction_pct: float
    ) -> Dict[str, Any]:
        """
        模拟自定义减排比例
        
        Args:
            o3_surface: O3响应曲面
            voc_factors: VOC因子列表
            nox_factors: NOx因子列表
            voc_reduction_pct: VOCs减排百分比 (0-100)
            nox_reduction_pct: NOx减排百分比 (0-100)
        
        Returns:
            模拟结果
        """
        n_voc, n_nox = o3_surface.shape
        
        # 计算目标因子
        target_voc_factor = 1.0 - voc_reduction_pct / 100
        target_nox_factor = 1.0 - nox_reduction_pct / 100
        
        # 找到最近的网格点
        voc_idx = min(range(len(voc_factors)), 
                     key=lambda i: abs(voc_factors[i] - target_voc_factor))
        nox_idx = min(range(len(nox_factors)), 
                     key=lambda i: abs(nox_factors[i] - target_nox_factor))
        
        # 获取当前和目标O3
        current_idx_voc = min(range(len(voc_factors)), 
                             key=lambda i: abs(voc_factors[i] - 1.0))
        current_idx_nox = min(range(len(nox_factors)), 
                             key=lambda i: abs(nox_factors[i] - 1.0))
        
        current_o3 = float(o3_surface[current_idx_voc, current_idx_nox])
        target_o3 = float(o3_surface[voc_idx, nox_idx])
        
        o3_change = target_o3 - current_o3
        change_pct = o3_change / current_o3 * 100 if current_o3 > 0 else 0
        
        return {
            "success": True,
            "data": {
                "voc_reduction_pct": voc_reduction_pct,
                "nox_reduction_pct": nox_reduction_pct,
                "current_o3": current_o3,
                "predicted_o3": target_o3,
                "o3_change": o3_change,
                "o3_change_pct": change_pct,
                "reaches_target": target_o3 <= self.o3_target
            },
            "summary": (
                f"自定义减排模拟: VOCs减排{voc_reduction_pct}%, NOx减排{nox_reduction_pct}%。"
                f"O3从{current_o3:.1f}变化到{target_o3:.1f} ppb ({change_pct:+.1f}%)。"
                f"{'可达标' if target_o3 <= self.o3_target else '未达标'}。"
            )
        }
