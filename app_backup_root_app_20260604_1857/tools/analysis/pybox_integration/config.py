"""
PyBox Integration Configuration

配置管理和依赖检测
"""

import os
from typing import Optional
from dataclasses import dataclass, field
import structlog

logger = structlog.get_logger()

# 检测PyBox依赖是否可用
PYBOX_AVAILABLE = False
ASSIMULO_AVAILABLE = False
NUMBA_AVAILABLE = False

try:
    import numba
    NUMBA_AVAILABLE = True
except ImportError:
    pass  # Numba未安装，不打印日志

try:
    from assimulo.solvers import CVode
    from assimulo.problem import Explicit_Problem
    ASSIMULO_AVAILABLE = True
    PYBOX_AVAILABLE = True
except ImportError:
    pass  # Assimulo不可用，不打印日志

# 模块根目录
MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
MECHANISMS_DIR = os.path.join(MODULE_DIR, "mechanisms")


@dataclass
class PyBoxConfig:
    """PyBox集成配置"""
    
    # 化学机理
    mechanism: str = "MCM_APINENE"
    mechanism_file: Optional[str] = None
    
    # 模拟参数
    simulation_time: float = 7200.0  # 秒 (2小时)
    batch_step: float = 60.0  # 秒 (1分钟输出间隔)
    
    # 环境条件
    temperature: float = 298.15  # K (25°C)
    pressure: float = 101325.0  # Pa (1 atm)
    relative_humidity: float = 0.5  # 50%
    
    # 光化学参数
    hour_of_day: float = 12.0  # 正午
    latitude: float = 23.0  # 广州纬度
    day_of_year: int = 180  # 夏季
    
    # EKMA网格参数
    ekma_grid_resolution: int = 21  # 21x21 = 441点（标准模式默认），11x11=121点（快速模式）
    voc_factor_range: tuple = (0.0, 2.0)  # VOC缩放范围
    nox_factor_range: tuple = (0.0, 3.0)  # NOx缩放范围
    
    # ODE求解器参数 - 放宽容差以提高速度（参考AtChem2配置）
    atol: float = 1e-4  # 绝对容差：从1e-10放宽1000倍
    rtol: float = 1e-4   # 相对容差：从1e-6放宽100倍
    maxsteps: int = 50000  # 最大步数限制
    max_step: float = 300.0  # 最大步长(秒)，避免过度精细积分
    
    # 性能参数
    use_numba: bool = True
    parallel_simulations: bool = False
    max_workers: int = 4
    
    # 输出控制
    verbose: bool = False
    progress_callback: Optional[callable] = None
    suppress_console: bool = True  # 关闭assimulo控制台统计输出
    
    def __post_init__(self):
        """初始化后处理"""
        # 设置机理文件路径
        if self.mechanism_file is None:
            self.mechanism_file = os.path.join(
                MECHANISMS_DIR,
                f"{self.mechanism}.eqn.txt"
            )
        
        # 检查Numba可用性
        if self.use_numba and not NUMBA_AVAILABLE:
            self.use_numba = False
    
    @classmethod
    def for_fast_ekma(cls) -> "PyBoxConfig":
        """快速EKMA配置(较低分辨率)"""
        return cls(
            ekma_grid_resolution=21,
            simulation_time=3600.0,
            verbose=False
        )
    
    @classmethod
    def for_precise_ekma(cls) -> "PyBoxConfig":
        """精确EKMA配置(高分辨率)"""
        return cls(
            ekma_grid_resolution=51,
            simulation_time=14400.0,
            atol=1e-12,
            rtol=1e-8,
            verbose=True
        )
    
    @classmethod
    def for_summer_guangzhou(cls) -> "PyBoxConfig":
        """广州夏季配置"""
        return cls(
            temperature=303.15,  # 30°C
            relative_humidity=0.75,
            latitude=23.13,
            day_of_year=200,  # 7月中旬
            hour_of_day=14.0  # 下午2点(O3峰值时段)
        )


# 默认配置实例
DEFAULT_CONFIG = PyBoxConfig()
