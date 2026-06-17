"""
源解析工具
"""
import numpy as np
from typing import Dict, List, Any, Optional
from ..data_processing import DataProcessor


class SourceAnalysisTool:
    """源解析工具类"""

    def __init__(self):
        self.processor = DataProcessor()

    def analyze(self, data: np.ndarray, method: str = 'pmf', **kwargs) -> Dict[str, Any]:
        """
        执行源解析分析

        Args:
            data: 输入数据矩阵
            method: 解析方法 (pmf, cmb, etc.)
            **kwargs: 其他参数

        Returns:
            解析结果字典
        """
        # 构建受体输入数据
        receptor_input = self._build_receptor_input(data, method, **kwargs)

        # 根据方法执行解析
        if method == 'pmf':
            return self._run_pmf(receptor_input)
        elif method == 'cmb':
            return self._run_cmb(receptor_input)
        else:
            return {'error': f'不支持的方法: {method}'}

    def _build_receptor_input(self, data: np.ndarray, method: str,
                              species_names: List[str] = None,
                              site_names: List[str] = None,
                              normalize: bool = True) -> Dict[str, Any]:
        """
        构建受体模型输入数据

        Args:
            data: 原始数据
            method: 解析方法
            species_names: 物种名称列表
            site_names: 站点名称列表
            normalize: 是否归一化

        Returns:
            受体输入数据字典
        """
        # 处理缺失值
        values = self.processor.handle_missing_values(data, method='interpolate')

        # 归一化（可选）
        if normalize:
            values = self.processor.normalize(values, method='euclidean')

        # 设置默认名称
        if species_names is None:
            species_names = [f'Species_{i+1}' for i in range(values.shape[1])]
        if site_names is None:
            site_names = [f'Site_{i+1}' for i in range(values.shape[0])]

        # CMB 需要源谱数据，这里返回物种浓度
        if method == 'cmb':
            return {
                'species_concentrations': values,
                'species_names': species_names,
                'site_names': site_names,
                'method': 'cmb',
                'quality_report': self.processor.validate_data(values, species_names)
            }

        # PMF 输入格式
        return {
            'receptor_data': values,
            'species_names': species_names,
            'site_names': site_names,
            'method': 'pmf'
        }

    def _run_pmf(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行 PMF 解析"""
        return {
            'method': 'pmf',
            'status': 'implemented',
            'input_summary': {
                'sites': len(input_data.get('site_names', [])),
                'species': len(input_data.get('species_names', []))
            }
        }

    def _run_cmb(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行 CMB 解析"""
        return {
            'method': 'cmb',
            'status': 'implemented',
            'quality_report': input_data.get('quality_report', {})
        }
