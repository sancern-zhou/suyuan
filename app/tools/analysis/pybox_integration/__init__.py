"""
PyBox Integration Module

集成PyBox箱模型引擎，实现完整化学机理的OBM分析。

功能:
- 完整RACM2化学机理模拟 (102物种, 504反应)
- EKMA等浓度曲线分析
- PO3臭氧生成速率分析
- RIR相对增量反应性分析
- 减排情景定量模拟
- VOCs物种映射

机理来源:
- RACM2: 参考项目 OBM-deliver_20200901/ekma_v0/ekma.fac

使用:
    from app.tools.analysis.pybox_integration import (
        FullEKMAAnalyzer,
        PyBoxAdapter,
        VOCsMapper,
        MechanismLoader,
        PYBOX_AVAILABLE
    )
"""

from .config import PyBoxConfig, PYBOX_AVAILABLE
from .vocs_mapper import (
    VOCsMapper,
    VOCS_TO_MCM_MAPPING,
    VOCS_TO_RACM2_MAPPING,
    RACM2_CLUSTER_DESCRIPTION,
)
from .mechanism_loader import (
    MechanismLoader,
    RACM2Mechanism,
    RACM2RateCalculator,
    RACM2_SPECIES,
    load_mechanism,
    is_mechanism_available,
)
from .pybox_adapter import PyBoxAdapter
from .ekma_full import FullEKMAAnalyzer
from .reduction_simulator import ReductionSimulator
from .po3_analyzer import PO3Analyzer
from .rir_analyzer import RIRAnalyzer

__all__ = [
    # 配置
    "PyBoxConfig",
    "PYBOX_AVAILABLE",
    # 物种映射
    "VOCsMapper",
    "VOCS_TO_MCM_MAPPING",
    "VOCS_TO_RACM2_MAPPING",
    "RACM2_CLUSTER_DESCRIPTION",
    # 机理加载
    "MechanismLoader",
    "RACM2Mechanism",
    "RACM2RateCalculator",
    "RACM2_SPECIES",
    "load_mechanism",
    "is_mechanism_available",
    # 核心功能
    "PyBoxAdapter",
    "FullEKMAAnalyzer",
    "ReductionSimulator",
    "PO3Analyzer",
    "RIRAnalyzer",
]
